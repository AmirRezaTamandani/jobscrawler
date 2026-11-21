"""Local preview of the same static dashboard and WSGI functions served on Vercel."""

import argparse
from http import HTTPStatus
import mimetypes
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from api.cron import app as cron
from api.dashboard import app as dashboard
from .web import json_response


PUBLIC = Path(__file__).resolve().parent.parent / "public"


def app(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    if path == "/api/dashboard":
        return dashboard(environ, start_response)
    if path == "/api/cron":
        return cron(environ, start_response)
    if environ.get("REQUEST_METHOD") not in {"GET", "HEAD"}:
        return json_response(start_response, HTTPStatus.METHOD_NOT_ALLOWED, {"error": "GET required."})
    asset = (PUBLIC / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
    if not asset.is_relative_to(PUBLIC) or not asset.is_file():
        return json_response(start_response, HTTPStatus.NOT_FOUND, {"error": "Not found."})
    mime = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
    if mime.startswith("text/"):
        mime += "; charset=utf-8"
    start_response("200 OK", [("Content-Type", mime), ("Content-Length", str(asset.stat().st_size))])
    return [] if environ["REQUEST_METHOD"] == "HEAD" else [asset.read_bytes()]


class PreviewServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    with make_server("127.0.0.1", args.port, app, server_class=PreviewServer) as server:
        print(f"Felowin dashboard: http://127.0.0.1:{server.server_port}/", flush=True)
        server.serve_forever()
