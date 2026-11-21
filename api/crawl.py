"""Run a manually requested crawl with the same secret as scheduled runs."""

from hmac import compare_digest
from http import HTTPStatus
import os
from pathlib import Path
import threading
import time

from api import cron
from jobscrawler.crawl import SOURCES, collect, tehran_day
from jobscrawler.store import save_digest
from jobscrawler.web import json_response

_local_lock = threading.Lock()
_root = Path(__file__).resolve().parent.parent


def app(environ, start_response):
    if environ.get("REQUEST_METHOD") != "POST":
        body = b'{"error":"POST required"}'
        start_response("405 Method Not Allowed", [
            ("Content-Type", "application/json"), ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"), ("Allow", "POST"),
        ])
        return [body]
    secret = os.environ.get("CRON_SECRET", "")
    supplied = environ.get("HTTP_AUTHORIZATION", "")
    if not secret or not compare_digest(supplied.encode(), f"Bearer {secret}".encode()):
        return json_response(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})

    if os.environ.get("DATABASE_URL") or os.environ.get("VERCEL"):
        # Reuse scheduled execution, including storage errors and partial results.
        return cron.app({**environ, "REQUEST_METHOD": "GET"}, start_response)

    if not _local_lock.acquire(blocking=False):
        return json_response(start_response, HTTPStatus.CONFLICT, {"error": "Crawl already running"})
    try:
        day = tehran_day()
        result = collect(SOURCES, deadline=time.monotonic() + cron.CRAWL_BUDGET_SECONDS)
        sources = {name: cron._source_message(error) for name, error in result.sources.items()}
        save_digest(_root / "data/jobs.sqlite3", _root / "reports" / f"{day}.html",
                    day, result.matches, sources)
        status, http_status = "complete", HTTPStatus.OK
        if any(error is not None for error in sources.values()):
            status, http_status = "partial", HTTPStatus.MULTI_STATUS
            if all(error is not None for error in sources.values()) and not any(result.scanned.values()):
                status, http_status = "failed", HTTPStatus.BAD_GATEWAY
        return json_response(start_response, http_status, {
            "status": status, "day": day, "matched_listings": len(result.matches), "sources": sources,
        })
    except Exception:
        return json_response(start_response, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Could not save crawl"})
    finally:
        _local_lock.release()
