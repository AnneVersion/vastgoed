#!/usr/bin/env python3
"""Data Consultants Stays - Booking Engine & Admin Server (port 8088)
   PostgreSQL backend with connection pooling, logging, and input validation.
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import psycopg2
import psycopg2.pool
import psycopg2.extras

# ── Logging ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("vastgoed")

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
        logger.info("Database connection pool created (min=2, max=10)")
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


# ── Input validation ─────────────────────────────────────────

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PHONE_RE = re.compile(r"^[\+\d\s\-()]{6,20}$")

VALID_STATUSES = {"pending", "bevestigd", "geannuleerd", "voltooid"}
VALID_BETAALSTATUSES = {"openstaand", "betaald", "terugbetaald"}
VALID_METHODES = {"iDEAL", "creditcard", "bank", "ideal", ""}
VALID_TARIEF_TYPES = {"flexibel", "standaard", "niet_restitueerbaar", ""}


def validate_email(email):
    """Return True if email is valid or empty."""
    if not email:
        return True
    return bool(EMAIL_RE.match(email))


def validate_date(date_str):
    """Return True if date string is valid YYYY-MM-DD."""
    if not date_str:
        return False
    if not DATE_RE.match(date_str):
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_phone(phone):
    """Return True if phone is valid or empty."""
    if not phone:
        return True
    return bool(PHONE_RE.match(phone))


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
    d["id"] = d.get("extern_id") or str(d.get("id", ""))
    if d.get("onderhoud") is None:
        d["onderhoud"] = []
    for field in ("extern_id", "created_at", "updated_at"):
        d.pop(field, None)
    return d


def _reservering_to_api(row):
    """Convert a reserveringen DB row to the JSON format the frontend expects."""
    if row is None:
        return None
    d = _serialize(row)
    d["id"] = d.get("extern_id") or str(d.get("id", ""))
    d["pand_id"] = d.get("pand_extern_id") or d.get("pand_id", "")
    if d.get("check_in"):
        d["check_in"] = str(d["check_in"])
    if d.get("check_out"):
        d["check_out"] = str(d["check_out"])
    for field in ("extern_id", "pand_extern_id", "created_at", "updated_at"):
        d.pop(field, None)
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
    for field in ("extern_id", "reservering_extern_id", "created_at", "updated_at"):
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


# ── Pagination helper ────────────────────────────────────────

def _parse_pagination(qs):
    """Parse page and per_page from query string. Returns (offset, limit, page, per_page)."""
    try:
        page = max(1, int(qs.get("page", [1])[0]))
    except (ValueError, IndexError):
        page = 1
    try:
        per_page = min(100, max(1, int(qs.get("per_page", [50])[0])))
    except (ValueError, IndexError):
        per_page = 50
    offset = (page - 1) * per_page
    return offset, per_page, page, per_page


def _paginated_response(rows, total, page, per_page):
    """Build a paginated response envelope."""
    import math
    return {
        "data": rows,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": math.ceil(total / per_page) if per_page else 1,
        }
    }


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

    # ── HEALTH CHECK ──────────────────────────────────────────

    def _route_health(self, path):
        if self.command == "GET" and path == "/api/health":
            try:
                result = db_query("SELECT 1 as ok, NOW() as server_time", fetchone=True)
                woning_count = db_query("SELECT COUNT(*) as cnt FROM woningen", fetchone=True)["cnt"]
                res_count = db_query("SELECT COUNT(*) as cnt FROM reserveringen", fetchone=True)["cnt"]
                self._send_json({
                    "status": "healthy",
                    "database": "connected",
                    "server_time": str(result["server_time"]),
                    "counts": {
                        "woningen": woning_count,
                        "reserveringen": res_count,
                    }
                })
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                self._send_json({
                    "status": "unhealthy",
                    "database": "disconnected",
                    "error": str(e)
                }, 503)
            return True
        return False

    # ── PANDEN ROUTES ─────────────────────────────────────────

    def _route_panden(self, path):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        # GET /api/panden  (with optional pagination)
        if self.command == "GET" and path == "/api/panden":
            # Check if pagination requested
            if "page" in qs:
                offset, limit, page, per_page = _parse_pagination(qs)
                total = db_query("SELECT COUNT(*) as cnt FROM woningen", fetchone=True)["cnt"]
                rows = db_query(
                    "SELECT * FROM woningen ORDER BY id LIMIT %s OFFSET %s",
                    (limit, offset)
                )
                self._send_json(_paginated_response(
                    [_woning_to_api(r) for r in rows], total, page, per_page
                ))
            else:
                rows = db_query("SELECT * FROM woningen ORDER BY id")
                self._send_json([_woning_to_api(r) for r in rows])
            return True

        # POST /api/woningen (add new property)
        if self.command == "POST" and path == "/api/woningen":
            body = self._read_body()

            # Validate required fields
            if not body.get("naam"):
                self._send_json({"error": "Veld 'naam' is verplicht"}, 400)
                return True

            extern_id = body.pop("id", None) or str(uuid.uuid4())
            onderhoud = json.dumps(body.pop("onderhoud", []))
            huurder = json.dumps(body.pop("huurder", None))
            amenities = body.pop("amenities", [])
            kenmerken = body.pop("kenmerken", [])
            tarieven = json.dumps(body.pop("tarieven", {}))
            foto_urls = body.pop("foto_urls", [])

            try:
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
                logger.info(f"Woning aangemaakt: {extern_id} - {body.get('naam')}")
                self._send_json(_woning_to_api(row), 201)
            except Exception as e:
                logger.error(f"Fout bij aanmaken woning: {e}")
                self._send_json({"error": f"Database fout: {e}"}, 500)
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
            body.pop("id", None)

            existing = db_query(
                "SELECT * FROM woningen WHERE extern_id = %s", (pand_id,), fetchone=True
            )
            if not existing:
                self._send_json({"error": "Pand niet gevonden"}, 404)
                return True

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

            for arr_field in ("amenities", "kenmerken", "foto_urls"):
                if arr_field in body:
                    set_clauses.append(f"{arr_field} = %({arr_field})s")
                    params[arr_field] = body[arr_field]

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
                try:
                    row = db_execute(sql, params, returning=True)
                    logger.info(f"Woning bijgewerkt: {pand_id}")
                    self._send_json(_woning_to_api(row))
                except Exception as e:
                    logger.error(f"Fout bij bijwerken woning {pand_id}: {e}")
                    self._send_json({"error": f"Database fout: {e}"}, 500)
            else:
                self._send_json(_woning_to_api(existing))
            return True

        # DELETE /api/woningen/<id>
        m_del = re.match(r"^/api/woningen/([a-zA-Z0-9\-]+)$", path)
        if m_del and self.command == "DELETE":
            pand_id = m_del.group(1)
            count = db_execute("DELETE FROM woningen WHERE extern_id = %s", (pand_id,))
            if count:
                logger.info(f"Woning verwijderd: {pand_id}")
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
                logger.info(f"Onderhoud toegevoegd aan woning {pand_id}: {entry['beschrijving']}")
                self._send_json(entry, 201)
            else:
                self._send_json({"error": "Pand niet gevonden"}, 404)
            return True

        return False

    # ── RESERVERINGEN ROUTES ──────────────────────────────────

    def _route_reserveringen(self, path):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        # GET /api/reserveringen (with optional pagination)
        if self.command == "GET" and path == "/api/reserveringen":
            if "page" in qs:
                offset, limit, page, per_page = _parse_pagination(qs)
                total = db_query("SELECT COUNT(*) as cnt FROM reserveringen", fetchone=True)["cnt"]
                rows = db_query(
                    "SELECT * FROM reserveringen ORDER BY id LIMIT %s OFFSET %s",
                    (limit, offset)
                )
                self._send_json(_paginated_response(
                    [_reservering_to_api(r) for r in rows], total, page, per_page
                ))
            else:
                rows = db_query("SELECT * FROM reserveringen ORDER BY id")
                self._send_json([_reservering_to_api(r) for r in rows])
            return True

        # POST /api/reserveringen
        if self.command == "POST" and path == "/api/reserveringen":
            body = self._read_body()

            # Input validation
            errors = []
            if not body.get("gast_naam"):
                errors.append("gast_naam is verplicht")
            if body.get("gast_email") and not validate_email(body["gast_email"]):
                errors.append("Ongeldig e-mailadres")
            if body.get("gast_telefoon") and not validate_phone(body["gast_telefoon"]):
                errors.append("Ongeldig telefoonnummer")
            if body.get("check_in") and not validate_date(body["check_in"]):
                errors.append("Ongeldige check-in datum (gebruik YYYY-MM-DD)")
            if body.get("check_out") and not validate_date(body["check_out"]):
                errors.append("Ongeldige check-out datum (gebruik YYYY-MM-DD)")
            if body.get("check_in") and body.get("check_out") and body["check_in"] >= body["check_out"]:
                errors.append("Check-out moet na check-in liggen")
            if body.get("status") and body["status"] not in VALID_STATUSES:
                errors.append(f"Ongeldige status: {body['status']}")

            if errors:
                self._send_json({"error": "Validatiefouten", "details": errors}, 400)
                return True

            extern_id = _next_id("RES")
            pand_extern_id = body.get("pand_id", "")

            pand_row = db_query(
                "SELECT id FROM woningen WHERE extern_id = %s", (pand_extern_id,), fetchone=True
            )
            pand_db_id = pand_row["id"] if pand_row else None

            try:
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
                logger.info(f"Reservering aangemaakt: {extern_id} - {body.get('gast_naam')}")
                self._send_json(_reservering_to_api(row), 201)
            except Exception as e:
                logger.error(f"Fout bij aanmaken reservering: {e}")
                self._send_json({"error": f"Database fout: {e}"}, 500)
            return True

        # PUT /api/reserveringen/<id>
        m = re.match(r"^/api/reserveringen/([A-Z0-9\-]+)$", path)
        if m and self.command == "PUT":
            res_id = m.group(1)
            body = self._read_body()
            body.pop("id", None)

            # Validate email/phone if provided
            if body.get("gast_email") and not validate_email(body["gast_email"]):
                self._send_json({"error": "Ongeldig e-mailadres"}, 400)
                return True
            if body.get("status") and body["status"] not in VALID_STATUSES:
                self._send_json({"error": f"Ongeldige status: {body['status']}"}, 400)
                return True

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
                try:
                    row = db_execute(sql, params, returning=True)
                    logger.info(f"Reservering bijgewerkt: {res_id}")
                    self._send_json(_reservering_to_api(row))
                except Exception as e:
                    logger.error(f"Fout bij bijwerken reservering {res_id}: {e}")
                    self._send_json({"error": f"Database fout: {e}"}, 500)
            else:
                self._send_json(_reservering_to_api(existing))
            return True

        # DELETE /api/reserveringen/<id>
        if m and self.command == "DELETE":
            res_id = m.group(1)
            count = db_execute("DELETE FROM reserveringen WHERE extern_id = %s", (res_id,))
            if count:
                logger.info(f"Reservering verwijderd: {res_id}")
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "Reservering niet gevonden"}, 404)
            return True

        return False

    # ── BETALINGEN ROUTES ─────────────────────────────────────

    def _route_betalingen(self, path):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        # GET /api/betalingen (with optional pagination)
        if self.command == "GET" and path == "/api/betalingen":
            if "page" in qs:
                offset, limit, page, per_page = _parse_pagination(qs)
                total = db_query("SELECT COUNT(*) as cnt FROM betalingen", fetchone=True)["cnt"]
                rows = db_query(
                    "SELECT * FROM betalingen ORDER BY id LIMIT %s OFFSET %s",
                    (limit, offset)
                )
                self._send_json(_paginated_response(
                    [_betaling_to_api(r) for r in rows], total, page, per_page
                ))
            else:
                rows = db_query("SELECT * FROM betalingen ORDER BY id")
                self._send_json([_betaling_to_api(r) for r in rows])
            return True

        # POST /api/betalingen
        if self.command == "POST" and path == "/api/betalingen":
            body = self._read_body()

            # Validate
            if not body.get("bedrag") and body.get("bedrag") != 0:
                self._send_json({"error": "Veld 'bedrag' is verplicht"}, 400)
                return True
            try:
                float(body["bedrag"])
            except (ValueError, TypeError):
                self._send_json({"error": "Ongeldig bedrag"}, 400)
                return True

            extern_id = _next_id("PAY")
            res_extern_id = body.get("reservering_id", "")

            res_row = db_query(
                "SELECT id FROM reserveringen WHERE extern_id = %s",
                (res_extern_id,), fetchone=True
            )
            res_db_id = res_row["id"] if res_row else None

            try:
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
                logger.info(f"Betaling aangemaakt: {extern_id} - {body.get('bedrag')}")
                self._send_json(_betaling_to_api(row), 201)
            except Exception as e:
                logger.error(f"Fout bij aanmaken betaling: {e}")
                self._send_json({"error": f"Database fout: {e}"}, 500)
            return True

        # POST /api/betalingen/<id>/refund
        m_ref = re.match(r"^/api/betalingen/([A-Z0-9\-]+)/refund$", path)
        if m_ref and self.command == "POST":
            pay_id = m_ref.group(1)
            try:
                row = db_execute("""
                    UPDATE betalingen SET status = 'terugbetaald'
                    WHERE extern_id = %s RETURNING *
                """, (pay_id,), returning=True)
                if row:
                    api_row = _betaling_to_api(row)
                    res_extern_id = row.get("reservering_extern_id")
                    if res_extern_id:
                        db_execute("""
                            UPDATE reserveringen SET betaalstatus = 'terugbetaald'
                            WHERE extern_id = %s
                        """, (res_extern_id,))
                    logger.info(f"Betaling terugbetaald: {pay_id}")
                    self._send_json(api_row)
                else:
                    self._send_json({"error": "Betaling niet gevonden"}, 404)
            except Exception as e:
                logger.error(f"Fout bij terugbetaling {pay_id}: {e}")
                self._send_json({"error": f"Database fout: {e}"}, 500)
            return True

        return False

    # ── KALENDER ROUTE ────────────────────────────────────────

    def _route_kalender(self, path):
        if self.command == "GET" and path == "/api/kalender":
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            maand = int(params.get("maand", [datetime.now().month])[0])
            jaar = int(params.get("jaar", [datetime.now().year])[0])

            # Validate month/year
            if not (1 <= maand <= 12):
                self._send_json({"error": "Maand moet tussen 1 en 12 liggen"}, 400)
                return True
            if not (2020 <= jaar <= 2100):
                self._send_json({"error": "Jaar moet tussen 2020 en 2100 liggen"}, 400)
                return True

            panden = db_query("SELECT * FROM woningen ORDER BY id")
            reserveringen = db_query(
                "SELECT * FROM reserveringen WHERE status != 'geannuleerd'"
            )

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

            if not validate_date(checkin) or not validate_date(checkout):
                self._send_json({"error": "Ongeldige datumformat (gebruik YYYY-MM-DD)"}, 400)
                return True

            if checkin >= checkout:
                self._send_json({"error": "Checkout moet na checkin liggen"}, 400)
                return True

            panden = db_query("SELECT * FROM woningen ORDER BY id")

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

            # Validate dates
            if not validate_date(body["checkin"]) or not validate_date(body["checkout"]):
                self._send_json({"error": "Ongeldige datumformat (gebruik YYYY-MM-DD)"}, 400)
                return True
            if body["checkin"] >= body["checkout"]:
                self._send_json({"error": "Checkout moet na checkin liggen"}, 400)
                return True

            # Validate email if provided
            if body.get("gast_email") and not validate_email(body["gast_email"]):
                self._send_json({"error": "Ongeldig e-mailadres"}, 400)
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

            extern_id = _next_id("RES")
            try:
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

                logger.info(f"Boeking aangemaakt: {body['boekingnummer']} voor {body['appartement_id']}")
                self._send_json({
                    "success": True,
                    "boekingnummer": body["boekingnummer"],
                    "message": "Reservering succesvol aangemaakt"
                }, 201)
            except Exception as e:
                logger.error(f"Fout bij aanmaken boeking: {e}")
                self._send_json({"error": f"Database fout: {e}"}, 500)
            return True

        return False

    # ── STATS ROUTE ───────────────────────────────────────────

    def _route_stats(self, path):
        if self.command == "GET" and path == "/api/stats":
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            month_prefix = now.strftime("%Y-%m")

            try:
                totaal_woningen = db_query(
                    "SELECT COUNT(*) as cnt FROM woningen", fetchone=True
                )["cnt"]

                actieve_res = db_query(
                    "SELECT COUNT(*) as cnt FROM reserveringen WHERE status IN ('bevestigd', 'pending')",
                    fetchone=True
                )["cnt"]

                bezet = db_query("""
                    SELECT COUNT(DISTINCT w.id) as cnt
                    FROM woningen w
                    JOIN reserveringen r ON r.pand_extern_id = w.extern_id
                    WHERE r.status = 'bevestigd'
                      AND r.check_in <= %s AND r.check_out > %s
                """, (today, today), fetchone=True)["cnt"]

                bezettingsgraad = round((bezet / totaal_woningen * 100) if totaal_woningen else 0)

                omzet_row = db_query("""
                    SELECT COALESCE(SUM(bedrag), 0) as total FROM betalingen
                    WHERE status = 'voltooid'
                      AND TO_CHAR(datum, 'YYYY-MM') = %s
                """, (month_prefix,), fetchone=True)
                omzet_maand = float(omzet_row["total"])

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
            except Exception as e:
                logger.error(f"Fout bij ophalen statistieken: {e}")
                self._send_json({"error": f"Database fout: {e}"}, 500)
            return True
        return False

    # ── MAIN ROUTER ───────────────────────────────────────────

    def _route_api(self):
        path = urlparse(self.path).path

        if self._route_health(path):
            return True
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

    def log_message(self, fmt, *args):
        logger.info(f"{self.client_address[0]} - {args[0]}")


def main():
    port = 8088

    # Test database connection
    try:
        conn = get_conn()
        put_conn(conn)
        logger.info("Database connection OK")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        logger.error("Make sure PostgreSQL is running and the 'vastgoed' database exists.")
        logger.error("Run sql/01_schema.sql and sql/02_seed.sql first.")
        return

    server = ThreadingHTTPServer(("0.0.0.0", port), VastgoedHandler)
    logger.info(f"Data Consultants Stays server running on http://localhost:{port}")
    logger.info(f"Booking engine:  http://localhost:{port}/index.html")
    logger.info(f"Admin panel:     http://localhost:{port}/admin.html")
    logger.info(f"Health check:    http://localhost:{port}/api/health")
    logger.info("API endpoints:")
    logger.info("  GET  /api/health                              - Health check")
    logger.info("  GET  /api/panden                              - List apartments")
    logger.info("  GET  /api/panden?page=1&per_page=10           - Paginated listing")
    logger.info("  GET  /api/beschikbaarheid?checkin=&checkout=   - Check availability")
    logger.info("  POST /api/reservering                         - Create booking")
    logger.info("  GET  /api/reserveringen                       - List bookings")
    logger.info("  GET  /api/betalingen                          - List payments")
    logger.info("  GET  /api/stats                               - Dashboard stats")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped.")
        server.server_close()
        if _pool:
            _pool.closeall()


if __name__ == "__main__":
    main()
