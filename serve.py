#!/usr/bin/env python3
"""DataConsultants Stays - Booking Engine & Admin Server (port 8088)
   PostgreSQL backend with connection pooling.
"""

import json
import os
import re
import uuid
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import psycopg2
import psycopg2.pool
import psycopg2.extras

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Database connection pool ──────────────────────────────────

DB_CONFIG = {
    "host": "localhost",
    "dbname": "vastgoed",
    "user": "postgres",
    "password": "postgres",
}

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2, maxconn=10, **DB_CONFIG
        )
    return _pool


def get_conn():
    return get_pool().getconn()


def put_conn(conn):
    get_pool().putconn(conn)


def db_query(sql, params=None, fetchone=False):
    """Execute a SELECT and return rows as list of dicts."""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetchone:
                row = cur.fetchone()
                return dict(row) if row else None
            return [dict(r) for r in cur.fetchall()]
    finally:
        put_conn(conn)


def db_execute(sql, params=None, returning=False):
    """Execute INSERT/UPDATE/DELETE. Returns row dict if RETURNING is used."""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            conn.commit()
            if returning:
                row = cur.fetchone()
                return dict(row) if row else None
            return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


# ── Helpers to convert DB rows to JSON-compatible API format ──

def _serialize(obj):
    """Make a dict JSON-serializable (handle Decimal, date, etc.)."""
    if obj is None:
        return obj
    from decimal import Decimal
    import datetime as dt
    cleaned = {}
    for k, v in obj.items():
        if isinstance(v, Decimal):
            cleaned[k] = float(v)
        elif isinstance(v, (dt.date, dt.datetime)):
            cleaned[k] = v.isoformat() if isinstance(v, dt.datetime) else str(v)
        elif isinstance(v, list):
            cleaned[k] = [float(x) if isinstance(x, Decimal) else x for x in v]
        else:
            cleaned[k] = v
    return cleaned


def _woning_to_api(row):
    """Convert a woningen DB row to the JSON format the frontend expects."""
    if row is None:
        return None
    d = _serialize(row)
    # The frontend uses extern_id as "id"
    d["id"] = d.get("extern_id") or str(d.get("id", ""))
    # Ensure onderhoud is a list
    if d.get("onderhoud") is None:
        d["onderhoud"] = []
    # Map amenities/kenmerken from PG arrays (already lists)
    # tarieven is already JSONB -> dict
    # Remove internal DB fields the frontend doesn't need
    for field in ("extern_id", "created_at", "updated_at"):
        d.pop(field, None)
    return d


def _reservering_to_api(row):
    """Convert a reserveringen DB row to the JSON format the frontend expects."""
    if row is None:
        return None
    d = _serialize(row)
    # Frontend uses extern_id as "id"
    d["id"] = d.get("extern_id") or str(d.get("id", ""))
    # Frontend uses pand_extern_id as "pand_id"
    d["pand_id"] = d.get("pand_extern_id") or d.get("pand_id", "")
    # Ensure check_in/check_out are strings
    if d.get("check_in"):
        d["check_in"] = str(d["check_in"])
    if d.get("check_out"):
        d["check_out"] = str(d["check_out"])
    for field in ("extern_id", "pand_extern_id", "created_at"):
        d.pop(field, None)
    # Remove internal serial pand_id (keep the extern one we set above)
    return d


def _betaling_to_api(row):
    """Convert a betalingen DB row to the JSON format the frontend expects."""
    if row is None:
        return None
    d = _serialize(row)
    d["id"] = d.get("extern_id") or str(d.get("id", ""))
    d["reservering_id"] = d.get("reservering_extern_id") or d.get("reservering_id", "")
    if d.get("datum"):
        d["datum"] = str(d["datum"])
    for field in ("extern_id", "reservering_extern_id", "created_at"):
        d.pop(field, None)
    return d


def _next_id(prefix):
    """Generate next sequential ID like RES-2026-009 from the database."""
    year = datetime.now().year
    table = "reserveringen" if prefix == "RES" else "betalingen"
    rows = db_query(
        f"SELECT extern_id FROM {table} WHERE extern_id LIKE %s ORDER BY extern_id DESC LIMIT 1",
        (f"{prefix}-{year}-%",)
    )
    if rows:
        parts = rows[0]["extern_id"].split("-")
        if len(parts) == 3:
            try:
                nxt = int(parts[2]) + 1
            except ValueError:
                nxt = 1
        else:
            nxt = 1
    else:
        nxt = 1
    return f"{prefix}-{year}-{nxt:03d}"


# ── HTTP Handler ─────────────────────────────────────────────

class VastgoedHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    # ── PANDEN ROUTES ─────────────────────────────────────────

    def _route_panden(self, path):
        # GET /api/panden
        if self.command == "GET" and path == "/api/panden":
            rows = db_query("SELECT * FROM woningen ORDER BY id")
            self._send_json([_woning_to_api(r) for r in rows])
            return True

        # POST /api/woningen (add new property)
        if self.command == "POST" and path == "/api/woningen":
            body = self._read_body()
            extern_id = body.pop("id", None) or str(uuid.uuid4())
            onderhoud = json.dumps(body.pop("onderhoud", []))
            huurder = json.dumps(body.pop("huurder", None))
            amenities = body.pop("amenities", [])
            kenmerken = body.pop("kenmerken", [])
            tarieven = json.dumps(body.pop("tarieven", {}))
            foto_urls = body.pop("foto_urls", [])

            row = db_execute("""
                INSERT INTO woningen (extern_id, naam, type, categorie, beschrijving,
                    adres, postcode, stad, lat, lng, oppervlakte_m2, kamers, slaapkamers,
                    badkamers, max_gasten, huurprijs, nachtprijs, schoonmaakkosten,
                    energielabel, amenities, kenmerken, tarieven, foto_urls, notities,
                    beschikbaar, beschikbaar_vanaf, huurder, onderhoud,
                    airbnb_url, rating, recensies)
                VALUES (%(extern_id)s, %(naam)s, %(type)s, %(categorie)s, %(beschrijving)s,
                    %(adres)s, %(postcode)s, %(stad)s, %(lat)s, %(lng)s, %(oppervlakte_m2)s,
                    %(kamers)s, %(slaapkamers)s, %(badkamers)s, %(max_gasten)s,
                    %(huurprijs)s, %(nachtprijs)s, %(schoonmaakkosten)s,
                    %(energielabel)s, %(amenities)s, %(kenmerken)s, %(tarieven)s::jsonb,
                    %(foto_urls)s, %(notities)s, %(beschikbaar)s, %(beschikbaar_vanaf)s,
                    %(huurder)s::jsonb, %(onderhoud)s::jsonb,
                    %(airbnb_url)s, %(rating)s, %(recensies)s)
                RETURNING *
            """, {
                "extern_id": extern_id,
                "naam": body.get("naam", ""),
                "type": body.get("type", ""),
                "categorie": body.get("categorie", ""),
                "beschrijving": body.get("beschrijving", ""),
                "adres": body.get("adres", ""),
                "postcode": body.get("postcode", ""),
                "stad": body.get("stad", ""),
                "lat": body.get("lat"),
                "lng": body.get("lng"),
                "oppervlakte_m2": body.get("oppervlakte_m2"),
                "kamers": body.get("kamers"),
                "slaapkamers": body.get("slaapkamers"),
                "badkamers": body.get("badkamers"),
                "max_gasten": body.get("max_gasten"),
                "huurprijs": body.get("huurprijs"),
                "nachtprijs": body.get("nachtprijs"),
                "schoonmaakkosten": body.get("schoonmaakkosten"),
                "energielabel": body.get("energielabel", ""),
                "amenities": amenities,
                "kenmerken": kenmerken,
                "tarieven": tarieven,
                "foto_urls": foto_urls,
                "notities": body.get("notities", ""),
                "beschikbaar": body.get("beschikbaar", True),
                "beschikbaar_vanaf": body.get("beschikbaar_vanaf"),
                "huurder": huurder,
                "onderhoud": onderhoud,
                "airbnb_url": body.get("airbnb_url"),
                "rating": body.get("rating"),
                "recensies": body.get("recensies", 0),
            }, returning=True)
            self._send_json(_woning_to_api(row), 201)
            return True

        # GET /api/panden/<id>
        m = re.match(r"^/api/panden/([a-zA-Z0-9\-]+)$", path)
        if m and self.command == "GET":
            pand_id = m.group(1)
            row = db_query(
                "SELECT * FROM woningen WHERE extern_id = %s", (pand_id,), fetchone=True
            )
            if row:
                self._send_json(_woning_to_api(row))
            else:
                self._send_json({"error": "Pand niet gevonden"}, 404)
            return True

        # PUT /api/panden/<id>  or  PUT /api/woningen/<id>
        m_put = re.match(r"^/api/(?:panden|woningen)/([a-zA-Z0-9\-]+)$", path)
        if m_put and self.command == "PUT":
            pand_id = m_put.group(1)
            body = self._read_body()
            body.pop("id", None)  # Don't overwrite extern_id

            # Build dynamic UPDATE
            existing = db_query(
                "SELECT * FROM woningen WHERE extern_id = %s", (pand_id,), fetchone=True
            )
            if not existing:
                self._send_json({"error": "Pand niet gevonden"}, 404)
                return True

            # Handle special fields
            set_clauses = []
            params = {}
            field_mapping = {
                "naam": "naam", "type": "type", "categorie": "categorie",
                "beschrijving": "beschrijving", "adres": "adres", "postcode": "postcode",
                "stad": "stad", "lat": "lat", "lng": "lng",
                "oppervlakte_m2": "oppervlakte_m2", "kamers": "kamers",
                "slaapkamers": "slaapkamers", "badkamers": "badkamers",
                "max_gasten": "max_gasten", "huurprijs": "huurprijs",
                "nachtprijs": "nachtprijs", "schoonmaakkosten": "schoonmaakkosten",
                "energielabel": "energielabel", "notities": "notities",
                "beschikbaar": "beschikbaar", "beschikbaar_vanaf": "beschikbaar_vanaf",
                "airbnb_url": "airbnb_url", "rating": "rating", "recensies": "recensies",
                "actief": "actief",
            }

            for json_key, db_col in field_mapping.items():
                if json_key in body:
                    set_clauses.append(f"{db_col} = %({db_col})s")
                    params[db_col] = body[json_key]

            # Array fields
            for arr_field in ("amenities", "kenmerken", "foto_urls"):
                if arr_field in body:
                    set_clauses.append(f"{arr_field} = %({arr_field})s")
                    params[arr_field] = body[arr_field]

            # JSONB fields
            if "tarieven" in body:
                set_clauses.append("tarieven = %(tarieven)s::jsonb")
                params["tarieven"] = json.dumps(body["tarieven"])
            if "onderhoud" in body:
                set_clauses.append("onderhoud = %(onderhoud)s::jsonb")
                params["onderhoud"] = json.dumps(body["onderhoud"])
            if "huurder" in body:
                set_clauses.append("huurder = %(huurder)s::jsonb")
                params["huurder"] = json.dumps(body["huurder"])

            if set_clauses:
                params["pand_id"] = pand_id
                sql = f"UPDATE woningen SET {', '.join(set_clauses)} WHERE extern_id = %(pand_id)s RETURNING *"
                row = db_execute(sql, params, returning=True)
                self._send_json(_woning_to_api(row))
            else:
                self._send_json(_woning_to_api(existing))
            return True

        # DELETE /api/woningen/<id>
        m_del = re.match(r"^/api/woningen/([a-zA-Z0-9\-]+)$", path)
        if m_del and self.command == "DELETE":
            pand_id = m_del.group(1)
            count = db_execute("DELETE FROM woningen WHERE extern_id = %s", (pand_id,))
            if count:
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "Pand niet gevonden"}, 404)
            return True

        # POST /api/panden/<id>/onderhoud
        m2 = re.match(r"^/api/panden/([a-zA-Z0-9\-]+)/onderhoud$", path)
        if m2 and self.command == "POST":
            pand_id = m2.group(1)
            body = self._read_body()
            entry = {
                "id": f"m{uuid.uuid4().hex[:6]}",
                "datum": body.get("datum", ""),
                "beschrijving": body.get("beschrijving", ""),
                "kosten": body.get("kosten", 0),
                "status": body.get("status", "gepland"),
            }
            row = db_execute("""
                UPDATE woningen
                SET onderhoud = COALESCE(onderhoud, '[]'::jsonb) || %s::jsonb
                WHERE extern_id = %s
                RETURNING id
            """, (json.dumps([entry]), pand_id), returning=True)
            if row:
                self._send_json(entry, 201)
            else:
                self._send_json({"error": "Pand niet gevonden"}, 404)
            return True

        return False

    # ── RESERVERINGEN ROUTES ──────────────────────────────────

    def _route_reserveringen(self, path):
        # GET /api/reserveringen
        if self.command == "GET" and path == "/api/reserveringen":
            rows = db_query("SELECT * FROM reserveringen ORDER BY id")
            self._send_json([_reservering_to_api(r) for r in rows])
            return True

        # POST /api/reserveringen
        if self.command == "POST" and path == "/api/reserveringen":
            body = self._read_body()
            extern_id = _next_id("RES")
            pand_extern_id = body.get("pand_id", "")

            # Look up internal pand_id
            pand_row = db_query(
                "SELECT id FROM woningen WHERE extern_id = %s", (pand_extern_id,), fetchone=True
            )
            pand_db_id = pand_row["id"] if pand_row else None

            row = db_execute("""
                INSERT INTO reserveringen (extern_id, pand_id, pand_extern_id, pand_naam,
                    gast_naam, gast_email, gast_telefoon, check_in, check_out,
                    gasten, tarief_type, nachtprijs, nachten, schoonmaakkosten, totaal,
                    status, betaalstatus, betaal_methode, opmerkingen, aangemaakt)
                VALUES (%(extern_id)s, %(pand_db_id)s, %(pand_extern_id)s, %(pand_naam)s,
                    %(gast_naam)s, %(gast_email)s, %(gast_telefoon)s,
                    %(check_in)s, %(check_out)s, %(gasten)s, %(tarief_type)s,
                    %(nachtprijs)s, %(nachten)s, %(schoonmaakkosten)s, %(totaal)s,
                    %(status)s, %(betaalstatus)s, %(betaal_methode)s,
                    %(opmerkingen)s, %(aangemaakt)s)
                RETURNING *
            """, {
                "extern_id": extern_id,
                "pand_db_id": pand_db_id,
                "pand_extern_id": pand_extern_id,
                "pand_naam": body.get("pand_naam", ""),
                "gast_naam": body.get("gast_naam", ""),
                "gast_email": body.get("gast_email", ""),
                "gast_telefoon": body.get("gast_telefoon", ""),
                "check_in": body.get("check_in"),
                "check_out": body.get("check_out"),
                "gasten": body.get("gasten", 1),
                "tarief_type": body.get("tarief_type", ""),
                "nachtprijs": body.get("nachtprijs"),
                "nachten": body.get("nachten"),
                "schoonmaakkosten": body.get("schoonmaakkosten"),
                "totaal": body.get("totaal"),
                "status": body.get("status", "pending"),
                "betaalstatus": body.get("betaalstatus", "openstaand"),
                "betaal_methode": body.get("betaal_methode", ""),
                "opmerkingen": body.get("opmerkingen", ""),
                "aangemaakt": body.get("aangemaakt", datetime.now().isoformat()),
            }, returning=True)
            self._send_json(_reservering_to_api(row), 201)
            return True

        # PUT /api/reserveringen/<id>
        m = re.match(r"^/api/reserveringen/([A-Z0-9\-]+)$", path)
        if m and self.command == "PUT":
            res_id = m.group(1)
            body = self._read_body()
            body.pop("id", None)

            existing = db_query(
                "SELECT * FROM reserveringen WHERE extern_id = %s", (res_id,), fetchone=True
            )
            if not existing:
                self._send_json({"error": "Reservering niet gevonden"}, 404)
                return True

            set_clauses = []
            params = {}
            updatable = [
                "pand_naam", "gast_naam", "gast_email", "gast_telefoon",
                "check_in", "check_out", "gasten", "tarief_type", "nachtprijs",
                "nachten", "schoonmaakkosten", "totaal", "status", "betaalstatus",
                "betaal_methode", "opmerkingen",
            ]
            for field in updatable:
                if field in body:
                    set_clauses.append(f"{field} = %({field})s")
                    params[field] = body[field]

            if set_clauses:
                params["res_id"] = res_id
                sql = f"UPDATE reserveringen SET {', '.join(set_clauses)} WHERE extern_id = %(res_id)s RETURNING *"
                row = db_execute(sql, params, returning=True)
                self._send_json(_reservering_to_api(row))
            else:
                self._send_json(_reservering_to_api(existing))
            return True

        # DELETE /api/reserveringen/<id>
        if m and self.command == "DELETE":
            res_id = m.group(1)
            count = db_execute("DELETE FROM reserveringen WHERE extern_id = %s", (res_id,))
            if count:
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "Reservering niet gevonden"}, 404)
            return True

        return False

    # ── BETALINGEN ROUTES ─────────────────────────────────────

    def _route_betalingen(self, path):
        # GET /api/betalingen
        if self.command == "GET" and path == "/api/betalingen":
            rows = db_query("SELECT * FROM betalingen ORDER BY id")
            self._send_json([_betaling_to_api(r) for r in rows])
            return True

        # POST /api/betalingen
        if self.command == "POST" and path == "/api/betalingen":
            body = self._read_body()
            extern_id = _next_id("PAY")
            res_extern_id = body.get("reservering_id", "")

            # Look up internal reservering_id
            res_row = db_query(
                "SELECT id FROM reserveringen WHERE extern_id = %s",
                (res_extern_id,), fetchone=True
            )
            res_db_id = res_row["id"] if res_row else None

            row = db_execute("""
                INSERT INTO betalingen (extern_id, reservering_id, reservering_extern_id,
                    gast_naam, bedrag, methode, bank, status, datum, beschrijving)
                VALUES (%(extern_id)s, %(res_db_id)s, %(res_extern_id)s,
                    %(gast_naam)s, %(bedrag)s, %(methode)s, %(bank)s,
                    %(status)s, %(datum)s, %(beschrijving)s)
                RETURNING *
            """, {
                "extern_id": extern_id,
                "res_db_id": res_db_id,
                "res_extern_id": res_extern_id,
                "gast_naam": body.get("gast_naam", ""),
                "bedrag": body.get("bedrag", 0),
                "methode": body.get("methode", "iDEAL"),
                "bank": body.get("bank", ""),
                "status": body.get("status", "pending"),
                "datum": body.get("datum", datetime.now().isoformat()),
                "beschrijving": body.get("beschrijving", ""),
            }, returning=True)
            self._send_json(_betaling_to_api(row), 201)
            return True

        # POST /api/betalingen/<id>/refund
        m_ref = re.match(r"^/api/betalingen/([A-Z0-9\-]+)/refund$", path)
        if m_ref and self.command == "POST":
            pay_id = m_ref.group(1)
            row = db_execute("""
                UPDATE betalingen SET status = 'terugbetaald'
                WHERE extern_id = %s RETURNING *
            """, (pay_id,), returning=True)
            if row:
                api_row = _betaling_to_api(row)
                # Also update the associated reservation
                res_extern_id = row.get("reservering_extern_id")
                if res_extern_id:
                    db_execute("""
                        UPDATE reserveringen SET betaalstatus = 'terugbetaald'
                        WHERE extern_id = %s
                    """, (res_extern_id,))
                self._send_json(api_row)
            else:
                self._send_json({"error": "Betaling niet gevonden"}, 404)
            return True

        return False

    # ── KALENDER ROUTE ────────────────────────────────────────

    def _route_kalender(self, path):
        if self.command == "GET" and path == "/api/kalender":
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            maand = int(params.get("maand", [datetime.now().month])[0])
            jaar = int(params.get("jaar", [datetime.now().year])[0])

            panden = db_query("SELECT * FROM woningen ORDER BY id")
            reserveringen = db_query(
                "SELECT * FROM reserveringen WHERE status != 'geannuleerd'"
            )

            # Build calendar data: for each pand, which dates are booked
            calendar = {}
            for pand in panden:
                eid = pand["extern_id"] or str(pand["id"])
                calendar[eid] = {
                    "naam": pand["naam"],
                    "boekingen": []
                }

            for res in reserveringen:
                try:
                    ci = datetime.combine(res["check_in"], datetime.min.time()) if res.get("check_in") else None
                    co = datetime.combine(res["check_out"], datetime.min.time()) if res.get("check_out") else None
                    if not ci or not co:
                        continue
                except (ValueError, TypeError):
                    continue

                month_start = datetime(jaar, maand, 1)
                if maand == 12:
                    month_end = datetime(jaar + 1, 1, 1)
                else:
                    month_end = datetime(jaar, maand + 1, 1)

                if ci < month_end and co > month_start:
                    pand_eid = res.get("pand_extern_id", "")
                    if pand_eid in calendar:
                        dates = []
                        current = max(ci, month_start)
                        end = min(co, month_end)
                        while current < end:
                            dates.append(current.strftime("%Y-%m-%d"))
                            current += timedelta(days=1)
                        res_eid = res.get("extern_id") or str(res.get("id", ""))
                        calendar[pand_eid]["boekingen"].append({
                            "reservering_id": res_eid,
                            "gast": res.get("gast_naam", ""),
                            "check_in": str(res["check_in"]),
                            "check_out": str(res["check_out"]),
                            "dates": dates,
                            "status": res.get("status", "")
                        })

            self._send_json({
                "maand": maand,
                "jaar": jaar,
                "kalender": calendar
            })
            return True

        return False

    # ── BOOKING ENGINE ROUTES ────────────────────────────────

    def _route_booking(self, path):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        # GET /api/beschikbaarheid?checkin=&checkout=
        if self.command == "GET" and path == "/api/beschikbaarheid":
            checkin = qs.get("checkin", [None])[0]
            checkout = qs.get("checkout", [None])[0]

            if not checkin or not checkout:
                self._send_json({"error": "checkin en checkout parameters zijn verplicht"}, 400)
                return True

            panden = db_query("SELECT * FROM woningen ORDER BY id")

            # Get all active reservations that might conflict
            conflicting_pand_ids = db_query("""
                SELECT DISTINCT pand_extern_id FROM reserveringen
                WHERE status != 'geannuleerd'
                  AND (
                    (check_in IS NOT NULL AND check_out IS NOT NULL
                     AND check_in < %s AND check_out > %s)
                    OR
                    (checkin IS NOT NULL AND checkout IS NOT NULL
                     AND checkin < %s AND checkout > %s)
                  )
            """, (checkout, checkin, checkout, checkin))
            blocked_eids = {r["pand_extern_id"] for r in conflicting_pand_ids}

            beschikbaar = []
            for pand in panden:
                eid = pand["extern_id"] or str(pand["id"])
                if eid not in blocked_eids:
                    beschikbaar.append({
                        "id": eid,
                        "naam": pand["naam"],
                        "categorie": pand.get("categorie", ""),
                        "stad": pand.get("stad", ""),
                        "nachtprijs": float(pand["nachtprijs"]) if pand.get("nachtprijs") else 0,
                        "max_gasten": pand.get("max_gasten", 0),
                        "slaapkamers": pand.get("slaapkamers", 0),
                        "oppervlakte_m2": pand.get("oppervlakte_m2", 0),
                        "beschikbaar": True
                    })

            self._send_json({
                "checkin": checkin,
                "checkout": checkout,
                "beschikbaar": beschikbaar,
                "aantal": len(beschikbaar)
            })
            return True

        # POST /api/reservering (booking engine creates booking)
        if self.command == "POST" and path == "/api/reservering":
            body = self._read_body()

            required = ["appartement_id", "checkin", "checkout"]
            missing = [f for f in required if not body.get(f)]
            if missing:
                self._send_json({"error": f"Verplichte velden ontbreken: {', '.join(missing)}"}, 400)
                return True

            if not body.get("boekingnummer"):
                body["boekingnummer"] = f"DCS-{uuid.uuid4().hex[:8].upper()}"
            if not body.get("datum_aangemaakt"):
                body["datum_aangemaakt"] = datetime.now().isoformat()
            if not body.get("status"):
                body["status"] = "bevestigd"

            # Check availability
            conflicts = db_query("""
                SELECT id FROM reserveringen
                WHERE status != 'geannuleerd'
                  AND (pand_extern_id = %s OR appartement_id = %s)
                  AND (
                    (check_in IS NOT NULL AND check_out IS NOT NULL
                     AND check_in < %s AND check_out > %s)
                    OR
                    (checkin IS NOT NULL AND checkout IS NOT NULL
                     AND checkin < %s AND checkout > %s)
                  )
                LIMIT 1
            """, (body["appartement_id"], body["appartement_id"],
                  body["checkout"], body["checkin"],
                  body["checkout"], body["checkin"]))

            if conflicts:
                self._send_json({
                    "error": "Dit appartement is niet beschikbaar voor de geselecteerde datums"
                }, 409)
                return True

            # Insert using the booking engine fields
            extern_id = _next_id("RES")
            db_execute("""
                INSERT INTO reserveringen (extern_id, pand_extern_id, appartement_id,
                    gast_naam, gast_email, gast_telefoon,
                    checkin, checkout, check_in, check_out,
                    gasten, nachtprijs, schoonmaakkosten, totaal,
                    status, boekingnummer, datum_aangemaakt, aangemaakt)
                VALUES (%(extern_id)s, %(appartement_id)s, %(appartement_id)s,
                    %(gast_naam)s, %(gast_email)s, %(gast_telefoon)s,
                    %(checkin)s, %(checkout)s, %(checkin)s, %(checkout)s,
                    %(gasten)s, %(nachtprijs)s, %(schoonmaakkosten)s, %(totaal)s,
                    %(status)s, %(boekingnummer)s, %(datum_aangemaakt)s, %(aangemaakt)s)
            """, {
                "extern_id": extern_id,
                "appartement_id": body["appartement_id"],
                "gast_naam": body.get("gast_naam", ""),
                "gast_email": body.get("gast_email", ""),
                "gast_telefoon": body.get("gast_telefoon", ""),
                "checkin": body["checkin"],
                "checkout": body["checkout"],
                "gasten": body.get("gasten", 1),
                "nachtprijs": body.get("nachtprijs"),
                "schoonmaakkosten": body.get("schoonmaakkosten"),
                "totaal": body.get("totaal"),
                "status": body["status"],
                "boekingnummer": body["boekingnummer"],
                "datum_aangemaakt": body["datum_aangemaakt"],
                "aangemaakt": body["datum_aangemaakt"],
            })

            self._send_json({
                "success": True,
                "boekingnummer": body["boekingnummer"],
                "message": "Reservering succesvol aangemaakt"
            }, 201)
            return True

        return False

    # ── STATS ROUTE ───────────────────────────────────────────

    def _route_stats(self, path):
        if self.command == "GET" and path == "/api/stats":
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            month_prefix = now.strftime("%Y-%m")

            totaal_woningen = db_query(
                "SELECT COUNT(*) as cnt FROM woningen", fetchone=True
            )["cnt"]

            actieve_res = db_query(
                "SELECT COUNT(*) as cnt FROM reserveringen WHERE status IN ('bevestigd', 'pending')",
                fetchone=True
            )["cnt"]

            # Bezettingsgraad: properties with a confirmed booking covering today
            bezet = db_query("""
                SELECT COUNT(DISTINCT w.id) as cnt
                FROM woningen w
                JOIN reserveringen r ON r.pand_extern_id = w.extern_id
                WHERE r.status = 'bevestigd'
                  AND r.check_in <= %s AND r.check_out > %s
            """, (today, today), fetchone=True)["cnt"]

            bezettingsgraad = round((bezet / totaal_woningen * 100) if totaal_woningen else 0)

            # Omzet deze maand
            omzet_row = db_query("""
                SELECT COALESCE(SUM(bedrag), 0) as total FROM betalingen
                WHERE status = 'voltooid'
                  AND TO_CHAR(datum, 'YYYY-MM') = %s
            """, (month_prefix,), fetchone=True)
            omzet_maand = float(omzet_row["total"])

            # Check-ins & check-outs vandaag
            checkins_vandaag_rows = db_query("""
                SELECT * FROM reserveringen
                WHERE check_in = %s AND status = 'bevestigd'
            """, (today,))

            checkouts_vandaag_rows = db_query("""
                SELECT * FROM reserveringen
                WHERE check_out = %s AND status = 'bevestigd'
            """, (today,))

            openstaand_rows = db_query("""
                SELECT * FROM reserveringen WHERE betaalstatus = 'openstaand'
            """)

            self._send_json({
                "totaal_woningen": totaal_woningen,
                "actieve_reserveringen": actieve_res,
                "bezettingsgraad": bezettingsgraad,
                "omzet_maand": omzet_maand,
                "checkins_vandaag": len(checkins_vandaag_rows),
                "checkouts_vandaag": len(checkouts_vandaag_rows),
                "openstaande_betalingen": len(openstaand_rows),
                "checkins_vandaag_detail": [_reservering_to_api(r) for r in checkins_vandaag_rows],
                "checkouts_vandaag_detail": [_reservering_to_api(r) for r in checkouts_vandaag_rows],
                "openstaand_detail": [_reservering_to_api(r) for r in openstaand_rows]
            })
            return True
        return False

    # ── MAIN ROUTER ───────────────────────────────────────────

    def _route_api(self):
        path = urlparse(self.path).path

        if self._route_booking(path):
            return True
        if self._route_panden(path):
            return True
        if self._route_reserveringen(path):
            return True
        if self._route_betalingen(path):
            return True
        if self._route_kalender(path):
            return True
        if self._route_stats(path):
            return True

        return False

    def do_GET(self):
        if self.path.startswith("/api/"):
            if not self._route_api():
                self._send_json({"error": "Not found"}, 404)
        else:
            super().do_GET()

    def do_PUT(self):
        if not self._route_api():
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if not self._route_api():
            self._send_json({"error": "Not found"}, 404)

    def do_DELETE(self):
        if not self._route_api():
            self._send_json({"error": "Not found"}, 404)

    def log_message(self, format, *args):
        print(f"[vastgoed] {args[0]}")


def main():
    port = 8088

    # Test database connection
    try:
        conn = get_conn()
        put_conn(conn)
        print("Database connection OK")
    except Exception as e:
        print(f"WARNING: Database connection failed: {e}")
        print("Make sure PostgreSQL is running and the 'vastgoed' database exists.")
        print("Run sql/01_create_tables.sql and sql/02_seed_data.sql first.")
        return

    server = ThreadingHTTPServer(("0.0.0.0", port), VastgoedHandler)
    print(f"DataConsultants Stays server running on http://localhost:{port}")
    print(f"Booking engine:  http://localhost:{port}/index.html")
    print(f"Admin panel:     http://localhost:{port}/admin.html")
    print(f"API endpoints:")
    print(f"  GET  /api/panden                              - List apartments")
    print(f"  GET  /api/beschikbaarheid?checkin=&checkout=   - Check availability")
    print(f"  POST /api/reservering                         - Create booking")
    print(f"  GET  /api/reserveringen                       - List bookings")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
        if _pool:
            _pool.closeall()


if __name__ == "__main__":
    main()
