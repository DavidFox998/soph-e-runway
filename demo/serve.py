#!/usr/bin/env python3
"""Demo server (Q3): stdlib http.server, nothing else.

  GET  /                -> demo/index.html
  GET  /events?since=N  -> {"events": [...], "head": M}   (the feed;
                            the UI consumes ONLY this)
  GET  /tamper          -> {"mode": "CLEAN|ARMED|IMPOSTOR"}
  POST /tamper {"mode"} -> flips the tamper state (atomic write)

A driver thread runs the three-beat demo on a loop. Set
SOPHE_DEMO_DRIVER=off to serve a static feed instead (tests do).
Paths default to this demo/ directory; SOPHE_DEMO_DIR overrides.
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO_DIR = os.environ.get("SOPHE_DEMO_DIR", HERE)
FEED_PATH = os.path.join(DEMO_DIR, "events.jsonl")
RECEIPT_PATH = os.path.join(DEMO_DIR, "receipt.jsonl")
TAMPER_PATH = os.path.join(DEMO_DIR, "tamper_state.json")
INDEX_PATH = os.path.join(HERE, "index.html")
ARCADE_PATH = os.path.join(HERE, "arcade.html")
MODES = ("CLEAN", "ARMED", "IMPOSTOR")


def _read_tamper() -> str:
    try:
        with open(TAMPER_PATH, encoding="utf-8") as f:
            mode = str(json.load(f).get("mode", "CLEAN"))
            return mode if mode in MODES else "CLEAN"
    except (OSError, ValueError):
        return "CLEAN"


def _write_tamper(mode: str) -> None:
    tmp = TAMPER_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"mode": mode}, f)
    os.replace(tmp, TAMPER_PATH)


def _driver() -> None:
    import sys
    sys.path.insert(0, os.path.join(HERE, "..", "src"))
    from runway.demo_feed import Feed
    from runway.demo_run import run_demo

    while True:
        for p in (FEED_PATH, RECEIPT_PATH):
            try:
                os.remove(p)
            except OSError:
                pass
        _write_tamper("CLEAN")
        try:
            run_demo(Feed(FEED_PATH), receipt_path=RECEIPT_PATH,
                     tamper_path=TAMPER_PATH, auto=True,
                     sleep=lambda s: time.sleep(1.4))
        except Exception:
            time.sleep(3)
        time.sleep(6)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the demo terminal clean
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/arcade"):
            path = ARCADE_PATH if parsed.path == "/arcade" else INDEX_PATH
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/events":
            import sys
            sys.path.insert(0, os.path.join(HERE, "..", "src"))
            from runway.demo_feed import read_events

            since = int(parse_qs(parsed.query).get("since", ["0"])[0])
            events, head = read_events(FEED_PATH, since)
            self._json({"events": events, "head": head})
        elif parsed.path == "/tamper":
            self._json({"mode": _read_tamper()})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/tamper":
            self._json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            mode = str(data.get("mode", "")).upper()
        except ValueError:
            mode = ""
        if mode not in MODES:
            self._json({"error": "mode must be CLEAN, ARMED or IMPOSTOR"}, 400)
            return
        _write_tamper(mode)
        self._json({"mode": mode})


def make_server(port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8791"))
    if os.environ.get("SOPHE_DEMO_DRIVER") != "off":
        threading.Thread(target=_driver, daemon=True).start()
    print(f"SOPH-E demo at http://127.0.0.1:{port}/")
    make_server(port).serve_forever()
