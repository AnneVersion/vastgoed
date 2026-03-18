#!/usr/bin/env python3
"""Vastgoed Verhuur - HTTP Server (port 8088)"""

import json
import os
import re
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PANDEN_FILE = os.path.join(DATA_DIR, "panden.json")
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

data_lock = threading.Lock()


def load_panden():
    with data_lock:
        with open(PANDEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_panden(panden):
    with data_lock:
        with open(PANDEN_FILE, "w", encoding="utf-8") as f:
            json.dump(panden, f, indent=2, ensure_ascii=False)


class VastgoedHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
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

    def _route_api(self):
        path = urlparse(self.path).path

        # GET /api/panden
        if self.command == "GET" and path == "/api/panden":
            panden = load_panden()
            self._send_json(panden)
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

        # PUT /api/panden/<id>
        if m and self.command == "PUT":
            pand_id = m.group(1)
            body = self._read_body()
            panden = load_panden()
            idx = next((i for i, p in enumerate(panden) if p["id"] == pand_id), None)
            if idx is not None:
                # Preserve id
                body["id"] = pand_id
                panden[idx] = body
                save_panden(panden)
                self._send_json(panden[idx])
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
                import uuid
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

    def log_message(self, format, *args):
        print(f"[vastgoed] {args[0]}")


def main():
    port = 8088
    server = ThreadingHTTPServer(("0.0.0.0", port), VastgoedHandler)
    print(f"Vastgoed server running on http://localhost:{port}")
    print(f"Public site:  http://localhost:{port}/index.html")
    print(f"Admin panel:  http://localhost:{port}/admin.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
