#!/usr/bin/env python3
"""DataConsultants Stays - Booking Engine & Admin Server (port 8088)"""

import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PANDEN_FILE = os.path.join(DATA_DIR, "panden.json")
RESERVERINGEN_FILE = os.path.join(DATA_DIR, "reserveringen.json")
BETALINGEN_FILE = os.path.join(DATA_DIR, "betalingen.json")
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

data_lock = threading.Lock()


def _load_json(filepath):
    with data_lock:
        if not os.path.exists(filepath):
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)


def _save_json(filepath, data):
    with data_lock:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def load_panden():
    return _load_json(PANDEN_FILE)


def save_panden(panden):
    _save_json(PANDEN_FILE, panden)


def load_reserveringen():
    return _load_json(RESERVERINGEN_FILE)


def save_reserveringen(data):
    _save_json(RESERVERINGEN_FILE, data)


def load_betalingen():
    return _load_json(BETALINGEN_FILE)


def save_betalingen(data):
    _save_json(BETALINGEN_FILE, data)


def _next_id(prefix, items):
    """Generate next sequential ID like RES-2026-009."""
    nums = []
    for item in items:
        parts = item.get("id", "").split("-")
        if len(parts) == 3:
            try:
                nums.append(int(parts[2]))
            except ValueError:
                pass
    nxt = max(nums, default=0) + 1
    year = datetime.now().year
    return f"{prefix}-{year}-{nxt:03d}"


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
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    # ── PANDEN ROUTES ─────────────────────────────────────────────

    def _route_panden(self, path):
        # GET /api/panden
        if self.command == "GET" and path == "/api/panden":
            self._send_json(load_panden())
            return True

        # POST /api/woningen  (add new property)
        if self.command == "POST" and path == "/api/woningen":
            body = self._read_body()
            panden = load_panden()
            body["id"] = str(uuid.uuid4())
            body.setdefault("onderhoud", [])
            body.setdefault("huurder", None)
            panden.append(body)
            save_panden(panden)
            self._send_json(body, 201)
            return True

        # GET /api/panden/<id>
        m = re.match(r"^/api/panden/([a-zA-Z0-9\-]+)$", path)
        if m and self.command == "GET":
            pand_id = m.group(1)
            panden = load_panden()
            pand = next((p for p in panden if p["id"] == pand_id), None)
            if pand:
                self._send_json(pand)
            else:
                self._send_json({"error": "Pand niet gevonden"}, 404)
            return True

        # PUT /api/panden/<id>  or  PUT /api/woningen/<id>
        m_put = re.match(r"^/api/(?:panden|woningen)/([a-zA-Z0-9\-]+)$", path)
        if m_put and self.command == "PUT":
            pand_id = m_put.group(1)
            body = self._read_body()
            panden = load_panden()
            idx = next((i for i, p in enumerate(panden) if p["id"] == pand_id), None)
            if idx is not None:
                body["id"] = pand_id
                # Merge: keep fields not in body
                merged = {**panden[idx], **body}
                panden[idx] = merged
                save_panden(panden)
                self._send_json(panden[idx])
            else:
                self._send_json({"error": "Pand niet gevonden"}, 404)
            return True

        # DELETE /api/woningen/<id>
        m_del = re.match(r"^/api/woningen/([a-zA-Z0-9\-]+)$", path)
        if m_del and self.command == "DELETE":
            pand_id = m_del.group(1)
            panden = load_panden()
            panden_new = [p for p in panden if p["id"] != pand_id]
            if len(panden_new) < len(panden):
                save_panden(panden_new)
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "Pand niet gevonden"}, 404)
            return True

        # POST /api/panden/<id>/onderhoud
        m2 = re.match(r"^/api/panden/([a-zA-Z0-9\-]+)/onderhoud$", path)
        if m2 and self.command == "POST":
            pand_id = m2.group(1)
            body = self._read_body()
            panden = load_panden()
            idx = next((i for i, p in enumerate(panden) if p["id"] == pand_id), None)
            if idx is not None:
                entry = {
                    "id": f"m{uuid.uuid4().hex[:6]}",
                    "datum": body.get("datum", ""),
                    "beschrijving": body.get("beschrijving", ""),
                    "kosten": body.get("kosten", 0),
                    "status": body.get("status", "gepland"),
                }
                panden[idx].setdefault("onderhoud", []).append(entry)
                save_panden(panden)
                self._send_json(entry, 201)
            else:
                self._send_json({"error": "Pand niet gevonden"}, 404)
            return True

        return False

    # ── RESERVERINGEN ROUTES ──────────────────────────────────────

    def _route_reserveringen(self, path):
        # GET /api/reserveringen
        if self.command == "GET" and path == "/api/reserveringen":
            self._send_json(load_reserveringen())
            return True

        # POST /api/reserveringen
        if self.command == "POST" and path == "/api/reserveringen":
            body = self._read_body()
            items = load_reserveringen()
            body["id"] = _next_id("RES", items)
            body.setdefault("status", "pending")
            body.setdefault("betaalstatus", "openstaand")
            body.setdefault("aangemaakt", datetime.now().isoformat())
            items.append(body)
            save_reserveringen(items)
            self._send_json(body, 201)
            return True

        # PUT /api/reserveringen/<id>
        m = re.match(r"^/api/reserveringen/([A-Z0-9\-]+)$", path)
        if m and self.command == "PUT":
            res_id = m.group(1)
            body = self._read_body()
            items = load_reserveringen()
            idx = next((i for i, r in enumerate(items) if r["id"] == res_id), None)
            if idx is not None:
                items[idx].update(body)
                items[idx]["id"] = res_id
                save_reserveringen(items)
                self._send_json(items[idx])
            else:
                self._send_json({"error": "Reservering niet gevonden"}, 404)
            return True

        # DELETE /api/reserveringen/<id>
        if m and self.command == "DELETE":
            res_id = m.group(1)
            items = load_reserveringen()
            new_items = [r for r in items if r["id"] != res_id]
            if len(new_items) < len(items):
                save_reserveringen(new_items)
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "Reservering niet gevonden"}, 404)
            return True

        return False

    # ── BETALINGEN ROUTES ─────────────────────────────────────────

    def _route_betalingen(self, path):
        # GET /api/betalingen
        if self.command == "GET" and path == "/api/betalingen":
            self._send_json(load_betalingen())
            return True

        # POST /api/betalingen
        if self.command == "POST" and path == "/api/betalingen":
            body = self._read_body()
            items = load_betalingen()
            body["id"] = _next_id("PAY", items)
            body.setdefault("status", "pending")
            body.setdefault("datum", datetime.now().isoformat())
            items.append(body)
            save_betalingen(items)
            self._send_json(body, 201)
            return True

        # POST /api/betalingen/<id>/refund
        m_ref = re.match(r"^/api/betalingen/([A-Z0-9\-]+)/refund$", path)
        if m_ref and self.command == "POST":
            pay_id = m_ref.group(1)
            items = load_betalingen()
            idx = next((i for i, b in enumerate(items) if b["id"] == pay_id), None)
            if idx is not None:
                items[idx]["status"] = "terugbetaald"
                save_betalingen(items)
                # Also update the associated reservation
                res_id = items[idx].get("reservering_id")
                if res_id:
                    reserveringen = load_reserveringen()
                    r_idx = next((i for i, r in enumerate(reserveringen) if r["id"] == res_id), None)
                    if r_idx is not None:
                        reserveringen[r_idx]["betaalstatus"] = "terugbetaald"
                        save_reserveringen(reserveringen)
                self._send_json(items[idx])
            else:
                self._send_json({"error": "Betaling niet gevonden"}, 404)
            return True

        return False

    # ── KALENDER ROUTE ────────────────────────────────────────────

    def _route_kalender(self, path):
        if self.command == "GET" and path == "/api/kalender":
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            maand = int(params.get("maand", [datetime.now().month])[0])
            jaar = int(params.get("jaar", [datetime.now().year])[0])

            reserveringen = load_reserveringen()
            panden = load_panden()

            # Build calendar data: for each pand, which dates are booked
            calendar = {}
            for pand in panden:
                calendar[pand["id"]] = {
                    "naam": pand["naam"],
                    "boekingen": []
                }

            for res in reserveringen:
                if res.get("status") == "geannuleerd":
                    continue
                try:
                    ci = datetime.strptime(res["check_in"], "%Y-%m-%d")
                    co = datetime.strptime(res["check_out"], "%Y-%m-%d")
                except (ValueError, KeyError):
                    continue

                # Check if this booking overlaps with requested month
                month_start = datetime(jaar, maand, 1)
                if maand == 12:
                    month_end = datetime(jaar + 1, 1, 1)
                else:
                    month_end = datetime(jaar, maand + 1, 1)

                if ci < month_end and co > month_start:
                    pand_id = res.get("pand_id", "")
                    if pand_id in calendar:
                        dates = []
                        current = max(ci, month_start)
                        end = min(co, month_end)
                        while current < end:
                            dates.append(current.strftime("%Y-%m-%d"))
                            current += timedelta(days=1)
                        calendar[pand_id]["boekingen"].append({
                            "reservering_id": res["id"],
                            "gast": res.get("gast_naam", ""),
                            "check_in": res["check_in"],
                            "check_out": res["check_out"],
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

    # ── BOOKING ENGINE ROUTES ────────────────────────────────────

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

            panden = load_panden()
            reserveringen = load_reserveringen()

            beschikbaar = []
            for pand in panden:
                conflict = False
                for res in reserveringen:
                    if res.get("status") == "geannuleerd":
                        continue
                    res_apt = res.get("appartement_id") or res.get("pand_id", "")
                    if res_apt != pand["id"]:
                        continue
                    res_ci = res.get("checkin") or res.get("check_in", "")
                    res_co = res.get("checkout") or res.get("check_out", "")
                    if checkin < res_co and checkout > res_ci:
                        conflict = True
                        break

                if not conflict:
                    beschikbaar.append({
                        "id": pand["id"],
                        "naam": pand["naam"],
                        "categorie": pand.get("categorie", ""),
                        "stad": pand.get("stad", ""),
                        "nachtprijs": pand.get("nachtprijs", 0),
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

            reserveringen = load_reserveringen()
            for res in reserveringen:
                if res.get("status") == "geannuleerd":
                    continue
                res_apt = res.get("appartement_id") or res.get("pand_id", "")
                if res_apt != body["appartement_id"]:
                    continue
                res_ci = res.get("checkin") or res.get("check_in", "")
                res_co = res.get("checkout") or res.get("check_out", "")
                if body["checkin"] < res_co and body["checkout"] > res_ci:
                    self._send_json({
                        "error": "Dit appartement is niet beschikbaar voor de geselecteerde datums"
                    }, 409)
                    return True

            reserveringen.append(body)
            save_reserveringen(reserveringen)

            self._send_json({
                "success": True,
                "boekingnummer": body["boekingnummer"],
                "message": "Reservering succesvol aangemaakt"
            }, 201)
            return True

        return False

    # ── STATS ROUTE ───────────────────────────────────────────────

    def _route_stats(self, path):
        if self.command == "GET" and path == "/api/stats":
            panden = load_panden()
            reserveringen = load_reserveringen()
            betalingen = load_betalingen()
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            month_start = now.strftime("%Y-%m-01")

            totaal_woningen = len(panden)
            actieve_res = sum(1 for r in reserveringen if r.get("status") in ("bevestigd", "pending"))

            # Bezettingsgraad: how many properties have an active booking covering today
            bezet = 0
            for pand in panden:
                for res in reserveringen:
                    if res.get("pand_id") == pand["id"] and res.get("status") == "bevestigd":
                        try:
                            ci = datetime.strptime(res["check_in"], "%Y-%m-%d")
                            co = datetime.strptime(res["check_out"], "%Y-%m-%d")
                            if ci <= now < co:
                                bezet += 1
                                break
                        except (ValueError, KeyError):
                            pass
            bezettingsgraad = round((bezet / totaal_woningen * 100) if totaal_woningen else 0)

            # Omzet deze maand
            omzet_maand = sum(
                b.get("bedrag", 0) for b in betalingen
                if b.get("status") == "voltooid" and b.get("datum", "")[:7] == now.strftime("%Y-%m")
            )

            # Check-ins & check-outs vandaag
            checkins_vandaag = [r for r in reserveringen if r.get("check_in") == today and r.get("status") == "bevestigd"]
            checkouts_vandaag = [r for r in reserveringen if r.get("check_out") == today and r.get("status") == "bevestigd"]
            openstaand = [r for r in reserveringen if r.get("betaalstatus") == "openstaand"]

            self._send_json({
                "totaal_woningen": totaal_woningen,
                "actieve_reserveringen": actieve_res,
                "bezettingsgraad": bezettingsgraad,
                "omzet_maand": omzet_maand,
                "checkins_vandaag": len(checkins_vandaag),
                "checkouts_vandaag": len(checkouts_vandaag),
                "openstaande_betalingen": len(openstaand),
                "checkins_vandaag_detail": checkins_vandaag,
                "checkouts_vandaag_detail": checkouts_vandaag,
                "openstaand_detail": openstaand
            })
            return True
        return False

    # ── MAIN ROUTER ───────────────────────────────────────────────

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
    server = ThreadingHTTPServer(("0.0.0.0", port), VastgoedHandler)
    # Ensure reserveringen.json exists
    if not os.path.exists(RESERVERINGEN_FILE):
        _save_json(RESERVERINGEN_FILE, [])

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


if __name__ == "__main__":
    main()
