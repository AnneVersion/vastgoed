#!/usr/bin/env python3
"""Data Consultants Stays - Luxury Short-Stay Booking Engine & Admin Server (port 8088)
   PostgreSQL backend with connection pooling, logging, and input validation.
   Features: contract generation, invoice generation, iDEAL simulation.
"""

import json
import logging
import math
import os
import re
import uuid
import urllib.request
from datetime import datetime, timedelta, date
from decimal import Decimal
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
    """Execute INSERT/UPDATE/DELETE. Return row if RETURNING, else rowcount."""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if returning:
                row = cur.fetchone()
                conn.commit()
                return dict(row) if row else None
            conn.commit()
            return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


# ── Input validation ─────────────────────────────────────────

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PHONE_RE = re.compile(r"^[\+\d\s\(\)\-]{6,20}$")

VALID_STATUSES = {"pending", "bevestigd", "geannuleerd", "voltooid"}
VALID_BETAALSTATUSES = {"openstaand", "betaald", "terugbetaald"}
VALID_METHODES = {"iDEAL", "creditcard", "bank", "ideal", ""}
VALID_TARIEF_TYPES = {"flexibel", "standaard", "niet_restitueerbaar", ""}


def validate_email(email):
    if not email:
        return True
    return bool(EMAIL_RE.match(email))


def validate_date(date_str):
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
    if not phone:
        return True
    return bool(PHONE_RE.match(phone))


# ── Helpers to convert DB rows to JSON-compatible API format ──

def _serialize(obj):
    if obj is None:
        return obj
    cleaned = {}
    for k, v in obj.items():
        if isinstance(v, Decimal):
            cleaned[k] = float(v)
        elif isinstance(v, (date, datetime)):
            cleaned[k] = v.isoformat() if isinstance(v, datetime) else str(v)
        elif isinstance(v, list):
            cleaned[k] = [float(x) if isinstance(x, Decimal) else x for x in v]
        else:
            cleaned[k] = v
    return cleaned


def _woning_to_api(row):
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
    year = datetime.now().year
    table_map = {"RES": "reserveringen", "PAY": "betalingen", "CON": "contracten", "FAC": "facturen"}
    table = table_map.get(prefix, "reserveringen")

    if prefix in ("CON",):
        rows = db_query(
            "SELECT contract_nr FROM contracten WHERE contract_nr LIKE %s ORDER BY contract_nr DESC LIMIT 1",
            (f"{prefix}-{year}-%",)
        )
        if rows:
            parts = rows[0]["contract_nr"].split("-")
            nxt = int(parts[2]) + 1 if len(parts) == 3 else 1
        else:
            nxt = 1
        return f"{prefix}-{year}-{nxt:04d}"

    if prefix in ("FAC",):
        rows = db_query(
            "SELECT factuur_nr FROM facturen WHERE factuur_nr LIKE %s ORDER BY factuur_nr DESC LIMIT 1",
            (f"DC-{year}-%",)
        )
        if rows:
            parts = rows[0]["factuur_nr"].split("-")
            nxt = int(parts[2]) + 1 if len(parts) == 3 else 1
        else:
            nxt = 1
        return f"DC-{year}-{nxt:04d}"

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
    return {
        "data": rows,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": math.ceil(total / per_page) if per_page else 1,
        }
    }


# ── iCal parsing ─────────────────────────────────────────────

def _parse_ical(ical_text):
    events = []
    in_event = False
    event = {}
    for line in ical_text.splitlines():
        line = line.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            event = {}
        elif line == "END:VEVENT":
            in_event = False
            events.append(event)
        elif in_event:
            if line.startswith("DTSTART"):
                event["start"] = line.split(":")[-1][:8]
            elif line.startswith("DTEND"):
                event["end"] = line.split(":")[-1][:8]
            elif line.startswith("SUMMARY"):
                event["summary"] = line.split(":", 1)[-1]
            elif line.startswith("UID"):
                event["uid"] = line.split(":", 1)[-1]
    return events


# ── Contract HTML Generation ─────────────────────────────────

def _generate_contract_html(data):
    """Generate a Dutch short-stay rental contract (huurovereenkomst)."""
    today = datetime.now().strftime("%d-%m-%Y")
    checkin_fmt = _fmt_date_nl(data.get("checkin", ""))
    checkout_fmt = _fmt_date_nl(data.get("checkout", ""))
    days = data.get("days", 0)
    months = round(days / 30, 1)
    maandprijs = data.get("maandprijs", 0)
    discount = data.get("discount", 0)
    discount_pct = int(discount * 100)
    huur_totaal = data.get("huur_totaal", 0)
    borg = data.get("borg", 0)
    servicekosten = data.get("servicekosten", 0)

    return f"""
    <h3>HUUROVEREENKOMST VOOR WOONRUIMTE<br>(Short-Stay)</h3>
    <p style="text-align:center;color:#8A8A8A;font-size:0.75rem;">Datum: {today}</p>

    <h4>Artikel 1 - Partijen</h4>
    <div class="contract-section">
      <p><strong>Verhuurder:</strong><br>
      Data Consultants B.V.<br>
      Keizersgracht 274, 1016 EV Amsterdam<br>
      KvK: 12345678 | BTW: NL123456789B01</p>

      <p style="margin-top:0.75rem;"><strong>Huurder:</strong><br>
      {data.get('gast_naam', '')}<br>
      E-mail: {data.get('gast_email', '')}<br>
      Telefoon: {data.get('gast_telefoon', '')}
      {'<br>Werkgever: ' + data['gast_bedrijf'] if data.get('gast_bedrijf') else ''}
      {'<br>BSN: ' + data['gast_bsn'] if data.get('gast_bsn') else ''}</p>
    </div>

    <h4>Artikel 2 - Het gehuurde</h4>
    <div class="contract-section">
      <p>De gemeubileerde woonruimte gelegen aan:<br>
      <strong>{data.get('property_naam', '')}</strong><br>
      {data.get('property_adres', '')}, {data.get('property_postcode', '')} {data.get('property_stad', '')}</p>
      <p>Het gehuurde is bestemd om te worden gebruikt als woonruimte voor maximaal
      {data.get('gasten', 1)} persoon/personen.</p>
    </div>

    <h4>Artikel 3 - Huurperiode</h4>
    <div class="contract-section">
      <p>De huurovereenkomst wordt aangegaan voor bepaalde tijd:<br>
      <strong>Ingangsdatum:</strong> {checkin_fmt}<br>
      <strong>Einddatum:</strong> {checkout_fmt}<br>
      <strong>Duur:</strong> {days} dagen ({months} maanden)</p>
      <p>Na afloop van de overeengekomen huurperiode eindigt de huurovereenkomst van
      rechtswege, zonder dat opzegging vereist is.</p>
    </div>

    <h4>Artikel 4 - Huurprijs en betalingsvoorwaarden</h4>
    <div class="contract-section">
      <table style="width:100%;border-collapse:collapse;">
        <tr><td style="padding:0.4rem;border:1px solid #ddd;">Maandelijkse huurprijs</td>
            <td style="padding:0.4rem;border:1px solid #ddd;text-align:right;">&euro; {maandprijs:,.2f}</td></tr>
        {'<tr><td style="padding:0.4rem;border:1px solid #ddd;">Korting (' + str(discount_pct) + '%)</td><td style="padding:0.4rem;border:1px solid #ddd;text-align:right;color:#2D8B4E;">-' + str(discount_pct) + '%</td></tr>' if discount > 0 else ''}
        <tr><td style="padding:0.4rem;border:1px solid #ddd;">Servicekosten per maand</td>
            <td style="padding:0.4rem;border:1px solid #ddd;text-align:right;">&euro; {servicekosten:,.2f}</td></tr>
        <tr><td style="padding:0.4rem;border:1px solid #ddd;">Waarborgsom (borg)</td>
            <td style="padding:0.4rem;border:1px solid #ddd;text-align:right;">&euro; {borg:,.2f}</td></tr>
        <tr style="font-weight:bold;"><td style="padding:0.4rem;border:1px solid #ddd;">Totale huur ({months} maanden)</td>
            <td style="padding:0.4rem;border:1px solid #ddd;text-align:right;">&euro; {huur_totaal:,.2f}</td></tr>
      </table>
      <p style="margin-top:0.75rem;">De huur dient maandelijks bij vooruitbetaling te worden voldaan, uiterlijk op de eerste
      dag van iedere kalendermaand, op rekeningnummer NL00 INGB 0000 0000 00 t.n.v.
      Data Consultants B.V., onder vermelding van het adres van het gehuurde.</p>
      <p>Alle genoemde bedragen zijn exclusief 21% BTW.</p>
    </div>

    <h4>Artikel 5 - Waarborgsom</h4>
    <div class="contract-section">
      <p>De huurder betaalt een waarborgsom van &euro; {borg:,.2f}. Deze waarborgsom wordt
      binnen 14 dagen na het einde van de huurovereenkomst terugbetaald, verminderd met
      eventuele kosten voor schade aan het gehuurde of achterstallige betalingen.</p>
    </div>

    <h4>Artikel 6 - Opzegtermijn</h4>
    <div class="contract-section">
      <p>Bij huurovereenkomsten korter dan 3 maanden: geen tussentijdse opzegging mogelijk.<br>
      Bij huurovereenkomsten van 3 maanden of langer: opzegtermijn van 1 maand.<br>
      Opzegging dient schriftelijk (per e-mail) te geschieden.</p>
    </div>

    <h4>Artikel 7 - Huisregels</h4>
    <div class="contract-section">
      <ol style="padding-left:1.5rem;">
        <li>Het gehuurde mag uitsluitend worden gebruikt als woonruimte.</li>
        <li>Huisdieren zijn niet toegestaan, tenzij schriftelijk anders overeengekomen.</li>
        <li>Roken is niet toegestaan in het gehuurde.</li>
        <li>De huurder is verantwoordelijk voor het normale onderhoud en het schoon houden.</li>
        <li>Overlast voor buren dient te worden voorkomen. Stilte tussen 22:00 en 07:00.</li>
        <li>Onderverhuur is niet toegestaan.</li>
        <li>De huurder dient zich in te schrijven bij de gemeente indien het verblijf langer
            dan 4 maanden duurt.</li>
      </ol>
    </div>

    <h4>Artikel 8 - Inbegrepen voorzieningen</h4>
    <div class="contract-section">
      <p>In de huurprijs zijn inbegrepen: gas, water, elektriciteit, internet,
      gemeentelijke belastingen en wekelijkse schoonmaak. De servicekosten dekken
      gebouwonderhoud, verzekering en administratiekosten.</p>
    </div>

    <h4>Artikel 9 - Algemene voorwaarden</h4>
    <div class="contract-section">
      <p>Op deze overeenkomst zijn de Algemene Voorwaarden van Data Consultants B.V.
      van toepassing, welke bij het aangaan van deze overeenkomst aan de huurder ter hand
      zijn gesteld. Op deze overeenkomst is Nederlands recht van toepassing.</p>
    </div>

    <h4>Artikel 10 - Ondertekening</h4>
    <div class="contract-section" style="margin-top:2rem;">
      <table style="width:100%;border:none;">
        <tr>
          <td style="width:50%;padding:1rem;border:none;vertical-align:top;">
            <p><strong>Verhuurder:</strong></p>
            <p>Data Consultants B.V.</p>
            <div style="height:60px;border-bottom:1px solid #333;margin:1rem 0;"></div>
            <p>Datum: {today}</p>
          </td>
          <td style="width:50%;padding:1rem;border:none;vertical-align:top;">
            <p><strong>Huurder:</strong></p>
            <p>{data.get('gast_naam', '')}</p>
            <div style="height:60px;border-bottom:1px solid #333;margin:1rem 0;"></div>
            <p>Datum: _______________</p>
          </td>
        </tr>
      </table>
    </div>
    """


def _fmt_date_nl(date_str):
    """Format YYYY-MM-DD to Dutch format."""
    if not date_str:
        return "-"
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        months_nl = ["januari", "februari", "maart", "april", "mei", "juni",
                     "juli", "augustus", "september", "oktober", "november", "december"]
        return f"{d.day} {months_nl[d.month - 1]} {d.year}"
    except (ValueError, IndexError):
        return str(date_str)


# ── Invoice HTML Generation ──────────────────────────────────

def _generate_invoice_html(data):
    """Generate a Dutch invoice (factuur)."""
    today = datetime.now().strftime("%d-%m-%Y")
    factuur_nr = data.get("factuur_nr", "")
    vervaldatum = data.get("vervaldatum", "")
    if isinstance(vervaldatum, (date, datetime)):
        vervaldatum = _fmt_date_nl(vervaldatum.strftime("%Y-%m-%d"))
    else:
        vervaldatum = _fmt_date_nl(str(vervaldatum))

    huur = float(data.get("huur_bedrag", 0))
    servicekosten = float(data.get("servicekosten", 0))
    borg = float(data.get("borg", 0))
    subtotaal = huur + servicekosten
    btw = subtotaal * 0.21
    totaal = subtotaal + btw + borg

    return f"""
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2rem;">
      <div>
        <h3 style="font-size:1.5rem;color:#B8860B;margin-bottom:0.5rem;">FACTUUR</h3>
        <p style="font-size:0.8rem;color:#8A8A8A;">Factuurnummer: <strong>{factuur_nr}</strong></p>
        <p style="font-size:0.8rem;color:#8A8A8A;">Factuurdatum: {today}</p>
        <p style="font-size:0.8rem;color:#8A8A8A;">Vervaldatum: {vervaldatum}</p>
      </div>
      <div style="text-align:right;">
        <p style="font-weight:bold;">Data Consultants B.V.</p>
        <p style="font-size:0.8rem;color:#8A8A8A;">Keizersgracht 274<br>1016 EV Amsterdam<br>
        KvK: 12345678<br>BTW: NL123456789B01<br>
        IBAN: NL00 INGB 0000 0000 00</p>
      </div>
    </div>

    <div style="margin-bottom:2rem;">
      <p style="font-weight:bold;margin-bottom:0.3rem;">Factuur aan:</p>
      <p>{data.get('gast_naam', '')}<br>
      {data.get('gast_email', '')}</p>
    </div>

    <p style="margin-bottom:1rem;font-size:0.85rem;">
      Betreft: Huur {data.get('property_naam', '')} - {data.get('days', 0)} dagen
    </p>

    <table style="width:100%;border-collapse:collapse;margin-bottom:1.5rem;">
      <thead>
        <tr style="background:#F5F0E8;">
          <th style="padding:0.6rem;border:1px solid #ddd;text-align:left;">Omschrijving</th>
          <th style="padding:0.6rem;border:1px solid #ddd;text-align:right;">Bedrag</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td style="padding:0.6rem;border:1px solid #ddd;">Huur {data.get('property_naam', '')}</td>
          <td style="padding:0.6rem;border:1px solid #ddd;text-align:right;">&euro; {huur:,.2f}</td>
        </tr>
        <tr>
          <td style="padding:0.6rem;border:1px solid #ddd;">Servicekosten</td>
          <td style="padding:0.6rem;border:1px solid #ddd;text-align:right;">&euro; {servicekosten:,.2f}</td>
        </tr>
        <tr style="border-top:2px solid #ddd;">
          <td style="padding:0.6rem;border:1px solid #ddd;font-weight:bold;">Subtotaal</td>
          <td style="padding:0.6rem;border:1px solid #ddd;text-align:right;font-weight:bold;">&euro; {subtotaal:,.2f}</td>
        </tr>
        <tr>
          <td style="padding:0.6rem;border:1px solid #ddd;">BTW (21%)</td>
          <td style="padding:0.6rem;border:1px solid #ddd;text-align:right;">&euro; {btw:,.2f}</td>
        </tr>
        <tr>
          <td style="padding:0.6rem;border:1px solid #ddd;">Waarborgsom (borg)</td>
          <td style="padding:0.6rem;border:1px solid #ddd;text-align:right;">&euro; {borg:,.2f}</td>
        </tr>
        <tr style="background:#F5F0E8;font-weight:bold;font-size:1.1rem;">
          <td style="padding:0.8rem;border:1px solid #ddd;">Totaal te voldoen</td>
          <td style="padding:0.8rem;border:1px solid #ddd;text-align:right;">&euro; {totaal:,.2f}</td>
        </tr>
      </tbody>
    </table>

    <div style="background:#FDFBF7;border:1px solid #E8E4DC;border-radius:6px;padding:1rem;margin-bottom:1.5rem;">
      <p style="font-weight:bold;margin-bottom:0.3rem;">Betaalgegevens</p>
      <p style="font-size:0.85rem;">
        IBAN: NL00 INGB 0000 0000 00<br>
        T.n.v.: Data Consultants B.V.<br>
        O.v.v.: {factuur_nr}
      </p>
    </div>

    <p style="font-size:0.8rem;color:#8A8A8A;">
      Betalingstermijn: 14 dagen na factuurdatum. Bij niet-tijdige betaling wordt
      de wettelijke rente in rekening gebracht. Op al onze facturen zijn de Algemene
      Voorwaarden van Data Consultants B.V. van toepassing.
    </p>
    """


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

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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

        # GET /api/panden
        if self.command == "GET" and path == "/api/panden":
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

        # POST /api/woningen
        if self.command == "POST" and path == "/api/woningen":
            body = self._read_body()
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
                        airbnb_url, rating, recensies,
                        maandprijs, weekprijs, borg, min_verblijf_dagen, max_verblijf_dagen, servicekosten_maand)
                    VALUES (%(extern_id)s, %(naam)s, %(type)s, %(categorie)s, %(beschrijving)s,
                        %(adres)s, %(postcode)s, %(stad)s, %(lat)s, %(lng)s, %(oppervlakte_m2)s,
                        %(kamers)s, %(slaapkamers)s, %(badkamers)s, %(max_gasten)s,
                        %(huurprijs)s, %(nachtprijs)s, %(schoonmaakkosten)s,
                        %(energielabel)s, %(amenities)s, %(kenmerken)s, %(tarieven)s::jsonb,
                        %(foto_urls)s, %(notities)s, %(beschikbaar)s, %(beschikbaar_vanaf)s,
                        %(huurder)s::jsonb, %(onderhoud)s::jsonb,
                        %(airbnb_url)s, %(rating)s, %(recensies)s,
                        %(maandprijs)s, %(weekprijs)s, %(borg)s,
                        %(min_verblijf_dagen)s, %(max_verblijf_dagen)s, %(servicekosten_maand)s)
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
                    "maandprijs": body.get("maandprijs"),
                    "weekprijs": body.get("weekprijs"),
                    "borg": body.get("borg"),
                    "min_verblijf_dagen": body.get("min_verblijf_dagen", 7),
                    "max_verblijf_dagen": body.get("max_verblijf_dagen", 730),
                    "servicekosten_maand": body.get("servicekosten_maand", 150),
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

        # PUT /api/panden/<id> or PUT /api/woningen/<id>
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
                "actief": "actief", "ical_url": "ical_url",
                "maandprijs": "maandprijs", "weekprijs": "weekprijs",
                "borg": "borg", "min_verblijf_dagen": "min_verblijf_dagen",
                "max_verblijf_dagen": "max_verblijf_dagen",
                "servicekosten_maand": "servicekosten_maand",
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

        # GET /api/reserveringen
        if self.command == "GET" and path == "/api/reserveringen":
            if "page" in qs:
                offset, limit, page, per_page = _parse_pagination(qs)
                total = db_query("SELECT COUNT(*) as cnt FROM reserveringen", fetchone=True)["cnt"]
                rows = db_query(
                    "SELECT * FROM reserveringen ORDER BY id DESC LIMIT %s OFFSET %s",
                    (limit, offset)
                )
                self._send_json(_paginated_response(
                    [_reservering_to_api(r) for r in rows], total, page, per_page
                ))
            else:
                rows = db_query("SELECT * FROM reserveringen ORDER BY id DESC")
                self._send_json([_reservering_to_api(r) for r in rows])
            return True

        # POST /api/reserveringen
        if self.command == "POST" and path == "/api/reserveringen":
            body = self._read_body()
            errors = []
            if not body.get("gast_naam"):
                errors.append("gast_naam is verplicht")
            if body.get("gast_email") and not validate_email(body["gast_email"]):
                errors.append("Ongeldig e-mailadres")
            if body.get("gast_telefoon") and not validate_phone(body["gast_telefoon"]):
                errors.append("Ongeldig telefoonnummer")
            if body.get("check_in") and not validate_date(body["check_in"]):
                errors.append("Ongeldige check-in datum")
            if body.get("check_out") and not validate_date(body["check_out"]):
                errors.append("Ongeldige check-out datum")
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
                logger.info(f"Reservering aangemaakt: {extern_id}")
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
        m_del = re.match(r"^/api/reserveringen/([A-Z0-9\-]+)$", path)
        if m_del and self.command == "DELETE":
            res_id = m_del.group(1)
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

        # GET /api/betalingen
        if self.command == "GET" and path == "/api/betalingen":
            if "page" in qs:
                offset, limit, page, per_page = _parse_pagination(qs)
                total = db_query("SELECT COUNT(*) as cnt FROM betalingen", fetchone=True)["cnt"]
                rows = db_query(
                    "SELECT * FROM betalingen ORDER BY id DESC LIMIT %s OFFSET %s",
                    (limit, offset)
                )
                self._send_json(_paginated_response(
                    [_betaling_to_api(r) for r in rows], total, page, per_page
                ))
            else:
                rows = db_query("SELECT * FROM betalingen ORDER BY id DESC")
                self._send_json([_betaling_to_api(r) for r in rows])
            return True

        # POST /api/betalingen
        if self.command == "POST" and path == "/api/betalingen":
            body = self._read_body()
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
                logger.info(f"Betaling aangemaakt: {extern_id}")
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

    # ── CONTRACT ROUTES ───────────────────────────────────────

    def _route_contracten(self, path):
        # POST /api/contract/generate
        if self.command == "POST" and path == "/api/contract/generate":
            body = self._read_body()
            contract_html = _generate_contract_html(body)
            contract_nr = _next_id("CON")

            # Try to store in DB
            contract_id = None
            try:
                row = db_execute("""
                    INSERT INTO contracten (contract_nr, contract_html)
                    VALUES (%s, %s) RETURNING id
                """, (contract_nr, contract_html), returning=True)
                contract_id = row["id"] if row else None
                logger.info(f"Contract gegenereerd: {contract_nr}")
            except Exception as e:
                logger.warning(f"Contract opslaan mislukt (tabel bestaat mogelijk niet): {e}")
                contract_id = contract_nr

            self._send_json({
                "contract_id": contract_id or contract_nr,
                "contract_nr": contract_nr,
                "contract_html": contract_html
            })
            return True

        # GET /api/contract/<id>
        m = re.match(r"^/api/contract/(\d+|CON-\d{4}-\d{4})$", path)
        if m and self.command == "GET":
            cid = m.group(1)
            try:
                if cid.startswith("CON-"):
                    row = db_query("SELECT * FROM contracten WHERE contract_nr = %s", (cid,), fetchone=True)
                else:
                    row = db_query("SELECT * FROM contracten WHERE id = %s", (int(cid),), fetchone=True)
                if row:
                    full_html = f"""<!DOCTYPE html><html lang="nl"><head><meta charset="UTF-8">
                    <title>Huurovereenkomst - {row.get('contract_nr','')}</title>
                    <style>body{{font-family:Verdana,sans-serif;max-width:800px;margin:2rem auto;
                    padding:2rem;line-height:1.8;font-size:14px;}}h3,h4{{margin-top:1.5rem;}}
                    table{{width:100%;border-collapse:collapse;margin:1rem 0;}}
                    td,th{{padding:0.5rem;border:1px solid #ddd;text-align:left;}}
                    @media print{{body{{margin:0;padding:1cm;}}}}</style></head>
                    <body>{row['contract_html']}</body></html>"""
                    self._send_html(full_html)
                else:
                    self._send_json({"error": "Contract niet gevonden"}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return True

        # GET /api/contracten (list)
        if self.command == "GET" and path == "/api/contracten":
            try:
                rows = db_query("SELECT id, contract_nr, reservering_id, ondertekend, ondertekend_datum, created_at FROM contracten ORDER BY id DESC")
                self._send_json([_serialize(r) for r in rows])
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return True

        # PUT /api/contracten/<id>/sign
        m_sign = re.match(r"^/api/contracten/(\d+)/sign$", path)
        if m_sign and self.command == "PUT":
            cid = int(m_sign.group(1))
            try:
                row = db_execute("""
                    UPDATE contracten SET ondertekend = TRUE, ondertekend_datum = NOW()
                    WHERE id = %s RETURNING *
                """, (cid,), returning=True)
                if row:
                    self._send_json(_serialize(row))
                else:
                    self._send_json({"error": "Contract niet gevonden"}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return True

        return False

    # ── FACTUUR ROUTES ────────────────────────────────────────

    def _route_facturen(self, path):
        # POST /api/factuur/generate
        if self.command == "POST" and path == "/api/factuur/generate":
            body = self._read_body()
            factuur_nr = _next_id("FAC")

            huur = float(body.get("huur_bedrag", 0))
            servicekosten = float(body.get("servicekosten", 0))
            borg = float(body.get("borg", 0))
            subtotaal = huur + servicekosten
            btw = subtotaal * 0.21
            totaal = subtotaal + btw + borg
            vervaldatum = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

            body["factuur_nr"] = factuur_nr
            body["vervaldatum"] = vervaldatum
            factuur_html = _generate_invoice_html(body)

            factuur_id = None
            try:
                row = db_execute("""
                    INSERT INTO facturen (factuur_nr, reservering_extern_id,
                        bedrag_excl_btw, btw_percentage, btw_bedrag, totaal,
                        status, vervaldatum, factuur_html)
                    VALUES (%s, %s, %s, 21.00, %s, %s, 'openstaand', %s, %s)
                    RETURNING id
                """, (factuur_nr, body.get("reservering_extern_id", ""),
                      subtotaal, btw, totaal, vervaldatum, factuur_html),
                    returning=True)
                factuur_id = row["id"] if row else None
                logger.info(f"Factuur gegenereerd: {factuur_nr}")
            except Exception as e:
                logger.warning(f"Factuur opslaan mislukt (tabel bestaat mogelijk niet): {e}")
                factuur_id = factuur_nr

            self._send_json({
                "factuur_id": factuur_id or factuur_nr,
                "factuur_nr": factuur_nr,
                "totaal": totaal,
                "vervaldatum": vervaldatum,
                "factuur_html": factuur_html,
            })
            return True

        # GET /api/factuur/<id>
        m = re.match(r"^/api/factuur/(\d+|DC-\d{4}-\d{4})$", path)
        if m and self.command == "GET":
            fid = m.group(1)
            try:
                if fid.startswith("DC-"):
                    row = db_query("SELECT * FROM facturen WHERE factuur_nr = %s", (fid,), fetchone=True)
                else:
                    row = db_query("SELECT * FROM facturen WHERE id = %s", (int(fid),), fetchone=True)
                if row:
                    full_html = f"""<!DOCTYPE html><html lang="nl"><head><meta charset="UTF-8">
                    <title>Factuur - {row.get('factuur_nr','')}</title>
                    <style>body{{font-family:Verdana,sans-serif;max-width:800px;margin:2rem auto;
                    padding:2rem;line-height:1.8;font-size:14px;}}
                    table{{width:100%;border-collapse:collapse;margin:1rem 0;}}
                    td,th{{padding:0.5rem;border:1px solid #ddd;text-align:left;}}
                    @media print{{body{{margin:0;padding:1cm;}}}}</style></head>
                    <body>{row['factuur_html']}</body></html>"""
                    self._send_html(full_html)
                else:
                    self._send_json({"error": "Factuur niet gevonden"}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return True

        # GET /api/facturen (list)
        if self.command == "GET" and path == "/api/facturen":
            try:
                rows = db_query("""
                    SELECT id, factuur_nr, reservering_extern_id,
                           bedrag_excl_btw, btw_bedrag, totaal, status, vervaldatum, created_at
                    FROM facturen ORDER BY id DESC
                """)
                self._send_json([_serialize(r) for r in rows])
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return True

        # PUT /api/facturen/<id>/status
        m_status = re.match(r"^/api/facturen/(\d+)/status$", path)
        if m_status and self.command == "PUT":
            fid = int(m_status.group(1))
            body = self._read_body()
            new_status = body.get("status", "")
            if new_status not in ("openstaand", "betaald", "verlopen"):
                self._send_json({"error": "Ongeldige status"}, 400)
                return True
            try:
                row = db_execute("""
                    UPDATE facturen SET status = %s WHERE id = %s RETURNING *
                """, (new_status, fid), returning=True)
                if row:
                    self._send_json(_serialize(row))
                else:
                    self._send_json({"error": "Factuur niet gevonden"}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return True

        return False

    # ── KALENDER ROUTE ────────────────────────────────────────

    def _route_kalender(self, path):
        if self.command == "GET" and path == "/api/kalender":
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            maand = int(params.get("maand", [datetime.now().month])[0])
            jaar = int(params.get("jaar", [datetime.now().year])[0])

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
                calendar[eid] = {"naam": pand["naam"], "boekingen": []}

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

            self._send_json({"maand": maand, "jaar": jaar, "kalender": calendar})
            return True
        return False

    # ── BOOKING ENGINE ROUTES ────────────────────────────────

    def _route_booking(self, path):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        # GET /api/beschikbaarheid
        if self.command == "GET" and path == "/api/beschikbaarheid":
            checkin = qs.get("checkin", [None])[0]
            checkout = qs.get("checkout", [None])[0]

            if not checkin or not checkout:
                self._send_json({"error": "checkin en checkout parameters zijn verplicht"}, 400)
                return True
            if not validate_date(checkin) or not validate_date(checkout):
                self._send_json({"error": "Ongeldige datumformat"}, 400)
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

            blocked_by_blokkade = db_query("""
                SELECT DISTINCT w.extern_id FROM beschikbaarheid_blokkades b
                JOIN woningen w ON w.id = b.woning_id
                WHERE b.datum_start < %s AND b.datum_einde > %s
            """, (checkout, checkin))
            for row in blocked_by_blokkade:
                if row.get("extern_id"):
                    blocked_eids.add(row["extern_id"])

            beschikbaar = []
            for pand in panden:
                eid = pand["extern_id"] or str(pand["id"])
                if eid not in blocked_eids:
                    beschikbaar.append({
                        "id": eid,
                        "naam": pand["naam"],
                        "categorie": pand.get("categorie", ""),
                        "stad": pand.get("stad", ""),
                        "maandprijs": float(pand["maandprijs"]) if pand.get("maandprijs") else 0,
                        "nachtprijs": float(pand["nachtprijs"]) if pand.get("nachtprijs") else 0,
                        "max_gasten": pand.get("max_gasten", 0),
                        "slaapkamers": pand.get("slaapkamers", 0),
                        "oppervlakte_m2": pand.get("oppervlakte_m2", 0),
                        "beschikbaar": True
                    })

            self._send_json({
                "checkin": checkin, "checkout": checkout,
                "beschikbaar": beschikbaar, "aantal": len(beschikbaar)
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
            if not validate_date(body["checkin"]) or not validate_date(body["checkout"]):
                self._send_json({"error": "Ongeldige datumformat"}, 400)
                return True
            if body["checkin"] >= body["checkout"]:
                self._send_json({"error": "Checkout moet na checkin liggen"}, 400)
                return True
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

            if not conflicts:
                blokkade_conflicts = db_query("""
                    SELECT b.id FROM beschikbaarheid_blokkades b
                    JOIN woningen w ON w.id = b.woning_id
                    WHERE (w.extern_id = %s)
                      AND b.datum_start < %s AND b.datum_einde > %s
                    LIMIT 1
                """, (body["appartement_id"], body["checkout"], body["checkin"]))
                if blokkade_conflicts:
                    conflicts = blokkade_conflicts

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
                logger.info(f"Boeking aangemaakt: {body['boekingnummer']}")
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

    # ── iCAL ROUTES ────────────────────────────────────────────

    def _route_ical(self, path):
        # GET /api/woningen/<id>/ical
        m_export = re.match(r"^/api/woningen/([a-zA-Z0-9\-]+)/ical$", path)
        if m_export and self.command == "GET":
            pand_id = m_export.group(1)
            pand = db_query(
                "SELECT * FROM woningen WHERE extern_id = %s", (pand_id,), fetchone=True
            )
            if not pand:
                try:
                    pand = db_query("SELECT * FROM woningen WHERE id = %s", (int(pand_id),), fetchone=True)
                except (ValueError, TypeError):
                    pass
            if not pand:
                self._send_json({"error": "Pand niet gevonden"}, 404)
                return True

            reserveringen = db_query("""
                SELECT * FROM reserveringen
                WHERE (pand_extern_id = %s OR pand_id = %s)
                  AND status != 'geannuleerd'
                ORDER BY check_in
            """, (pand.get("extern_id", ""), pand["id"]))

            cal_lines = [
                "BEGIN:VCALENDAR", "VERSION:2.0",
                "PRODID:-//Data Consultants Stays//Vastgoed//NL",
                f"X-WR-CALNAME:{pand['naam']}",
            ]
            for res in reserveringen:
                ci = res.get("check_in")
                co = res.get("check_out")
                if not ci or not co:
                    continue
                dtstart = ci.strftime("%Y%m%d") if hasattr(ci, 'strftime') else str(ci).replace("-", "")
                dtend = co.strftime("%Y%m%d") if hasattr(co, 'strftime') else str(co).replace("-", "")
                uid = res.get("extern_id") or str(res["id"])
                summary = res.get("gast_naam") or "Geboekt"
                cal_lines.extend([
                    "BEGIN:VEVENT",
                    f"DTSTART;VALUE=DATE:{dtstart}",
                    f"DTEND;VALUE=DATE:{dtend}",
                    f"SUMMARY:{summary}",
                    f"UID:{uid}@dataconsultantsstays.nl",
                    f"DESCRIPTION:Boeking {uid}",
                    "STATUS:CONFIRMED",
                    "END:VEVENT",
                ])

            blokkades = db_query(
                "SELECT * FROM beschikbaarheid_blokkades WHERE woning_id = %s", (pand["id"],)
            )
            for blok in blokkades:
                ds = blok["datum_start"]
                de = blok["datum_einde"]
                dtstart = ds.strftime("%Y%m%d") if hasattr(ds, 'strftime') else str(ds).replace("-", "")
                dtend = de.strftime("%Y%m%d") if hasattr(de, 'strftime') else str(de).replace("-", "")
                cal_lines.extend([
                    "BEGIN:VEVENT",
                    f"DTSTART;VALUE=DATE:{dtstart}",
                    f"DTEND;VALUE=DATE:{dtend}",
                    f"SUMMARY:{blok.get('reden') or 'Geblokkeerd'}",
                    f"UID:blokkade-{blok['id']}@dataconsultantsstays.nl",
                    "STATUS:CONFIRMED",
                    "END:VEVENT",
                ])

            cal_lines.append("END:VCALENDAR")
            ical_text = "\r\n".join(cal_lines) + "\r\n"

            body_bytes = ical_text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Disposition",
                             f'attachment; filename="{pand["naam"].replace(" ", "_")}.ics"')
            self.end_headers()
            self.wfile.write(body_bytes)
            return True

        # POST /api/woningen/<id>/ical-import
        m_import = re.match(r"^/api/woningen/([a-zA-Z0-9\-]+)/ical-import$", path)
        if m_import and self.command == "POST":
            pand_id = m_import.group(1)
            body = self._read_body()
            ical_url = body.get("ical_url", "").strip()
            if not ical_url:
                self._send_json({"error": "ical_url is verplicht"}, 400)
                return True

            pand = db_query("SELECT * FROM woningen WHERE extern_id = %s", (pand_id,), fetchone=True)
            if not pand:
                try:
                    pand = db_query("SELECT * FROM woningen WHERE id = %s", (int(pand_id),), fetchone=True)
                except (ValueError, TypeError):
                    pass
            if not pand:
                self._send_json({"error": "Pand niet gevonden"}, 404)
                return True

            try:
                req = urllib.request.Request(ical_url, headers={"User-Agent": "DataConsultantsStays/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    ical_text = resp.read().decode("utf-8", errors="replace")
            except Exception as e:
                self._send_json({"error": f"Kan iCal URL niet ophalen: {e}"}, 502)
                return True

            events = _parse_ical(ical_text)
            db_execute("UPDATE woningen SET ical_url = %s, ical_last_sync = NOW() WHERE id = %s",
                       (ical_url, pand["id"]))
            db_execute("DELETE FROM beschikbaarheid_blokkades WHERE woning_id = %s AND reden LIKE %s",
                       (pand["id"], "Airbnb:%"))

            imported = 0
            for ev in events:
                start = ev.get("start")
                end = ev.get("end")
                summary = ev.get("summary", "Airbnb boeking")
                if not start or not end:
                    continue
                try:
                    ds = datetime.strptime(start, "%Y%m%d").date()
                    de = datetime.strptime(end, "%Y%m%d").date()
                except ValueError:
                    continue
                db_execute("""
                    INSERT INTO beschikbaarheid_blokkades (woning_id, datum_start, datum_einde, reden)
                    VALUES (%s, %s, %s, %s)
                """, (pand["id"], ds, de, f"Airbnb: {summary}"))
                imported += 1

            logger.info(f"iCal import voor woning {pand_id}: {imported} blokkades")
            self._send_json({"success": True, "imported": imported, "ical_url": ical_url,
                             "last_sync": datetime.now().isoformat()})
            return True

        # POST /api/woningen/<id>/ical-sync
        m_sync = re.match(r"^/api/woningen/([a-zA-Z0-9\-]+)/ical-sync$", path)
        if m_sync and self.command == "POST":
            pand_id = m_sync.group(1)
            pand = db_query("SELECT * FROM woningen WHERE extern_id = %s", (pand_id,), fetchone=True)
            if not pand:
                try:
                    pand = db_query("SELECT * FROM woningen WHERE id = %s", (int(pand_id),), fetchone=True)
                except (ValueError, TypeError):
                    pass
            if not pand:
                self._send_json({"error": "Pand niet gevonden"}, 404)
                return True

            ical_url = pand.get("ical_url")
            if not ical_url:
                self._send_json({"error": "Geen iCal URL geconfigureerd"}, 400)
                return True

            try:
                req = urllib.request.Request(ical_url, headers={"User-Agent": "DataConsultantsStays/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    ical_text = resp.read().decode("utf-8", errors="replace")
            except Exception as e:
                self._send_json({"error": f"Kan iCal URL niet ophalen: {e}"}, 502)
                return True

            events = _parse_ical(ical_text)
            db_execute("DELETE FROM beschikbaarheid_blokkades WHERE woning_id = %s AND reden LIKE %s",
                       (pand["id"], "Airbnb:%"))

            imported = 0
            for ev in events:
                start = ev.get("start")
                end = ev.get("end")
                summary = ev.get("summary", "Airbnb boeking")
                if not start or not end:
                    continue
                try:
                    ds = datetime.strptime(start, "%Y%m%d").date()
                    de = datetime.strptime(end, "%Y%m%d").date()
                except ValueError:
                    continue
                db_execute("""
                    INSERT INTO beschikbaarheid_blokkades (woning_id, datum_start, datum_einde, reden)
                    VALUES (%s, %s, %s, %s)
                """, (pand["id"], ds, de, f"Airbnb: {summary}"))
                imported += 1

            db_execute("UPDATE woningen SET ical_last_sync = NOW() WHERE id = %s", (pand["id"],))
            logger.info(f"iCal sync voor woning {pand_id}: {imported} blokkades")
            self._send_json({"success": True, "imported": imported,
                             "last_sync": datetime.now().isoformat()})
            return True

        # GET /api/woningen/<id>/beschikbaarheid
        m_besch = re.match(r"^/api/woningen/([a-zA-Z0-9\-]+)/beschikbaarheid$", path)
        if m_besch and self.command == "GET":
            pand_id = m_besch.group(1)
            pand = db_query("SELECT * FROM woningen WHERE extern_id = %s", (pand_id,), fetchone=True)
            if not pand:
                try:
                    pand = db_query("SELECT * FROM woningen WHERE id = %s", (int(pand_id),), fetchone=True)
                except (ValueError, TypeError):
                    pass
            if not pand:
                self._send_json({"error": "Pand niet gevonden"}, 404)
                return True

            res_blocks = db_query("""
                SELECT check_in, check_out, gast_naam, extern_id, status
                FROM reserveringen
                WHERE (pand_extern_id = %s OR pand_id = %s) AND status != 'geannuleerd'
                ORDER BY check_in
            """, (pand.get("extern_id", ""), pand["id"]))

            blokkades = db_query("""
                SELECT datum_start, datum_einde, reden, id
                FROM beschikbaarheid_blokkades WHERE woning_id = %s ORDER BY datum_start
            """, (pand["id"],))

            blocked_dates = []
            for res in res_blocks:
                if res.get("check_in") and res.get("check_out"):
                    blocked_dates.append({
                        "start": str(res["check_in"]),
                        "end": str(res["check_out"]),
                        "type": "reservering",
                        "label": res.get("gast_naam") or res.get("extern_id") or "Geboekt",
                        "status": res.get("status", "")
                    })
            for blok in blokkades:
                blocked_dates.append({
                    "start": str(blok["datum_start"]),
                    "end": str(blok["datum_einde"]),
                    "type": "blokkade",
                    "label": blok.get("reden") or "Geblokkeerd",
                    "id": blok["id"]
                })

            self._send_json({
                "pand_id": pand_id, "pand_naam": pand["naam"],
                "ical_url": pand.get("ical_url"),
                "ical_last_sync": str(pand.get("ical_last_sync")) if pand.get("ical_last_sync") else None,
                "blocked": blocked_dates
            })
            return True

        # GET /api/woningen/<id>/blokkades
        m_blok = re.match(r"^/api/woningen/([a-zA-Z0-9\-]+)/blokkades$", path)
        if m_blok and self.command == "GET":
            pand_id = m_blok.group(1)
            pand = db_query("SELECT * FROM woningen WHERE extern_id = %s", (pand_id,), fetchone=True)
            if not pand:
                try:
                    pand = db_query("SELECT * FROM woningen WHERE id = %s", (int(pand_id),), fetchone=True)
                except (ValueError, TypeError):
                    pass
            if not pand:
                self._send_json({"error": "Pand niet gevonden"}, 404)
                return True

            blokkades = db_query(
                "SELECT * FROM beschikbaarheid_blokkades WHERE woning_id = %s ORDER BY datum_start",
                (pand["id"],)
            )
            self._send_json([_serialize(b) for b in blokkades])
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
                openstaand_rows = db_query(
                    "SELECT * FROM reserveringen WHERE betaalstatus = 'openstaand'"
                )

                # Extra stats for short-stay
                contract_count = 0
                factuur_count = 0
                try:
                    contract_count = db_query(
                        "SELECT COUNT(*) as cnt FROM contracten", fetchone=True
                    )["cnt"]
                    factuur_count = db_query(
                        "SELECT COUNT(*) as cnt FROM facturen", fetchone=True
                    )["cnt"]
                except Exception:
                    pass

                self._send_json({
                    "totaal_woningen": totaal_woningen,
                    "actieve_reserveringen": actieve_res,
                    "bezettingsgraad": bezettingsgraad,
                    "omzet_maand": omzet_maand,
                    "checkins_vandaag": len(checkins_vandaag_rows),
                    "checkouts_vandaag": len(checkouts_vandaag_rows),
                    "openstaande_betalingen": len(openstaand_rows),
                    "totaal_contracten": contract_count,
                    "totaal_facturen": factuur_count,
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
        if self._route_contracten(path):
            return True
        if self._route_facturen(path):
            return True
        if self._route_booking(path):
            return True
        if self._route_panden(path):
            return True
        if self._route_reserveringen(path):
            return True
        if self._route_betalingen(path):
            return True
        if self._route_ical(path):
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

    try:
        conn = get_conn()
        put_conn(conn)
        logger.info("Database connection OK")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        logger.error("Make sure PostgreSQL is running and the 'vastgoed' database exists.")
        logger.error("Run sql/01_schema.sql, sql/02_seed.sql and sql/03_short_stay_migration.sql first.")
        return

    server = ThreadingHTTPServer(("0.0.0.0", port), VastgoedHandler)
    logger.info(f"Data Consultants Stays - Luxury Short-Stay Platform")
    logger.info(f"Server running on http://localhost:{port}")
    logger.info(f"Booking engine:  http://localhost:{port}/index.html")
    logger.info(f"Admin panel:     http://localhost:{port}/admin.html")
    logger.info(f"Health check:    http://localhost:{port}/api/health")
    logger.info("API endpoints:")
    logger.info("  GET  /api/health                              - Health check")
    logger.info("  GET  /api/panden                              - List properties")
    logger.info("  GET  /api/beschikbaarheid?checkin=&checkout=   - Check availability")
    logger.info("  POST /api/reservering                         - Create booking")
    logger.info("  POST /api/contract/generate                   - Generate contract")
    logger.info("  GET  /api/contract/<id>                       - View contract")
    logger.info("  POST /api/factuur/generate                    - Generate invoice")
    logger.info("  GET  /api/factuur/<id>                        - View invoice")
    logger.info("  GET  /api/contracten                          - List contracts")
    logger.info("  GET  /api/facturen                            - List invoices")
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
