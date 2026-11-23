"""Stdlib HTTP server exposing POST /v1/run and POST /v1/describe for Forge remotes."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from winnow.http_bridge import describe_situation_payload, run_for_http


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _write_json(handler: BaseHTTPRequestHandler, status: int, body: dict[str, Any]) -> None:
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class WinnowHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        body = _read_json(self)
        situation = str(body.get("situation", "")).strip()

        if self.path == "/v1/describe":
            if not situation:
                _write_json(self, 400, {"error": "situation is required", "binary_only": True})
                return
            _write_json(self, 200, describe_situation_payload(situation))
            return

        if self.path == "/v1/run":
            if not situation:
                _write_json(self, 400, {"error": "situation is required", "binary_only": True})
                return
            _write_json(self, 200, run_for_http(situation))
            return

        _write_json(self, 404, {"error": "not found"})

    def do_GET(self) -> None:
        if self.path == "/health":
            _write_json(self, 200, {"status": "ok", "binary_only": True})
            return
        _write_json(self, 404, {"error": "not found"})


def serve(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), WinnowHandler)
    print(f"Winnow HTTP bridge listening on http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Winnow HTTP bridge for Forge remotes")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()