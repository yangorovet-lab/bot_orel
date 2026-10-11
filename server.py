#!/usr/bin/env python3
"""Сервер лендинга: отдаёт страницу и /api/trains со свободными местами РЖД.

Запускать там, где РЖД отвечает (российский IP): python server.py [порт]
"""
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import rzd

ROOT = Path(__file__).resolve().parent
CACHE_TTL = int(os.environ.get("CACHE_TTL", "60"))  # секунд: не дёргаем РЖД чаще раза в минуту на дату
_cache, _lock = {}, threading.Lock()


def get_trains(frm, to, day):
    key = (frm, to, day)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
    data = rzd.trains_payload(frm, to, day)
    with _lock:
        _cache[key] = (time.time(), data)
    return data


def landing_html():
    subprocess.run(["sh", str(ROOT / "scripts/build_landing.sh")], cwd=ROOT, check=True,
                   env={**os.environ, "API_URL": ""}, stdout=subprocess.DEVNULL)
    return (ROOT / "_site/index.html").read_bytes()


class Handler(BaseHTTPRequestHandler):
    page = b""

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, code, obj):
        self.send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/trains":
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                self.send_json(200, get_trains(q.get("from"), q.get("to"), q.get("date")))
            except ValueError as e:
                self.send_json(400, {"error": str(e)})
            except Exception as e:
                self.log_error("РЖД: %s", e)
                self.send_json(502, {"error": "РЖД не ответил, попробуйте через минуту"})
        elif url.path in ("/", "/index.html"):
            self.send(200, self.page, "text/html; charset=utf-8")
        else:
            self.send_json(404, {"error": "not found"})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8080"))
    Handler.page = landing_html()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Лендинг: http://localhost:{port}/   API: /api/trains?from=2000140&to=2000000&date=ГГГГ-ММ-ДД",
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
