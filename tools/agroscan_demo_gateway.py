#!/usr/bin/env python3
"""Pasarela HTTP limitada para demo con cloudflared (no sustituye autenticacion).

Se enlaza SOLO a 127.0.0.1. Cloudflare Quick Tunnel es un enlace publico:
use exclusivamente el clon de datos y cierre el tunel despues de la demo.
"""
from __future__ import annotations
import argparse
from collections import defaultdict, deque
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
import time
from urllib.parse import urlsplit

MAX_UPLOAD = 7 * 1024 * 1024
MAX_RESPONSE = 14 * 1024 * 1024
LOCK = threading.Lock()
COUNTS = defaultdict(deque)
ORIGINS = set()
UPSTREAM_PORT = 8000

ALLOWED_PREFIXES = (
    "/api/auth/", "/api/users", "/api/lots", "/api/evaluations",
    "/api/images", "/api/reviews", "/api/uncertainty",
    "/api/iot/status", "/api/health", "/api/vision/",
)
DENIED_PREFIXES = (
    "/api/admin", "/api/iot/measurements", "/api/iot/", # Se habilita /api/iot/status mas abajo.
)
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length", "x-forwarded-host", "x-forwarded-proto", "x-forwarded-for"}


def allowed_path(path: str) -> bool:
    if not path.startswith("/api/") or "//" in path or "\\" in path or "%" in path:
        return False
    if path == "/api/iot/status":
        return True
    if any(path == x or path.startswith(x + "/") for x in ("/api/admin", "/api/iot/measurements")):
        return False
    if path.startswith("/api/iot/"):
        return False
    return any(path == prefix or path.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def within_limit(client: str, path: str, method: str) -> bool:
    now = time.monotonic()
    login = path == "/api/auth/login" and method == "POST"
    key = (client, "login" if login else "general")
    window = 600 if login else 60
    maximum = 10 if login else 100
    with LOCK:
        history = COUNTS[key]
        while history and now - history[0] > window:
            history.popleft()
        if len(history) >= maximum:
            return False
        history.append(now)
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "AgroScan-Demo-Gateway"
    sys_version = ""

    def do_GET(self): self.forward()
    def do_POST(self): self.forward()
    def do_PUT(self): self.forward()
    def do_PATCH(self): self.forward()
    def do_DELETE(self): self.forward()
    def do_OPTIONS(self): self.forward()

    def send_json(self, status, message):
        body = json.dumps({"detail": message}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        origin = self.headers.get("Origin")
        if origin in ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def forward(self):
        path = urlsplit(self.path).path
        if not allowed_path(path):
            return self.send_json(403, "Ruta no publicada en la demostracion")
        if self.command not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}:
            return self.send_json(405, "Metodo no permitido")
        origin = self.headers.get("Origin")
        if origin and origin not in ORIGINS:
            return self.send_json(403, "Origen no autorizado")
        addr = self.headers.get("CF-Connecting-IP") or self.client_address[0]
        if not within_limit(addr, path, self.command):
            return self.send_json(429, "Demasiadas solicitudes; vuelve a intentar mas tarde")
        if self.headers.get("Transfer-Encoding"):
            return self.send_json(400, "No se admite Transfer-Encoding")
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.send_json(400, "Content-Length invalido")
        if size < 0 or size > MAX_UPLOAD:
            return self.send_json(413, "Carga demasiado grande")
        if self.command in {"POST", "PUT", "PATCH"} and not self.headers.get("Content-Length"):
            return self.send_json(411, "Content-Length requerido")
        try:
            data = self.rfile.read(size) if size else None

            # Recuperar el protocolo original validado por Cloudflare.
            cf_visitor = self.headers.get("CF-Visitor", "")
            try:
                visitor = json.loads(cf_visitor)
            except (TypeError, json.JSONDecodeError):
                visitor = {}

            original_scheme = visitor.get("scheme")

            headers = {
                k: v for k, v in self.headers.items()
                if k.lower() not in HOP_HEADERS
                and not k.lower().startswith("cf-")
            }

            headers["Host"] = f"127.0.0.1:{UPSTREAM_PORT}"
            headers["Connection"] = "close"

            if original_scheme == "https":
                headers["X-Forwarded-Proto"] = "https"
            conn = http.client.HTTPConnection("127.0.0.1", UPSTREAM_PORT, timeout=120)
            try:
                conn.request(self.command, self.path, body=data, headers=headers)
                upstream = conn.getresponse()
                response_body = upstream.read(MAX_RESPONSE + 1)
                if len(response_body) > MAX_RESPONSE:
                    return self.send_json(502, "Respuesta del servidor demasiado grande")
                self.send_response(upstream.status)
                for key, value in upstream.getheaders():
                    if key.lower() in HOP_HEADERS or key.lower() in {"server", "date", "content-encoding"}:
                        continue
                    self.send_header(key, value)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
            finally:
                conn.close()
        except (OSError, http.client.HTTPException) as exc:
            self.send_json(502, "FastAPI local no disponible")

    def log_message(self, fmt, *args):
        # No registrar URL ni encabezados que puedan incluir identificadores/tokens.
        print(f"[gateway] {self.address_string()} {self.command} {urlsplit(self.path).path} - {fmt % args}")


def main():
    global UPSTREAM_PORT
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True, help="https://tu-demo.vercel.app (sin ruta)")
    parser.add_argument("--listen-port", type=int, default=8787)
    parser.add_argument("--upstream-port", type=int, default=8000)
    args = parser.parse_args()
    parsed = urlsplit(args.origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        parser.error("--origin exige dominio HTTPS exacto, sin ruta ni query")
    origin = f"https://{parsed.netloc}"
    ORIGINS.update({origin, "http://localhost:5173", "http://127.0.0.1:5173"})
    UPSTREAM_PORT = args.upstream_port
    print(f"Gateway solo local 127.0.0.1:{args.listen_port}, origen autorizado: {origin}")
    print("DENEGADOS: endpoints IoT de escritura, backups, rutas externas /api y OpenAPI.")
    print("ATENCION: el tunel Cloudflare sera PUBLICO. Usar copia aislada y apagar al terminar.")
    server = ThreadingHTTPServer(("127.0.0.1", args.listen_port), Handler)
    try: server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == "__main__":
    main()
