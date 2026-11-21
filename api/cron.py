"""Authenticated daily crawl at GET /api/cron."""

from hmac import compare_digest
from http import HTTPStatus
import os
import re
import time

from jobscrawler.crawl import SOURCES, collect, tehran_day
from jobscrawler.dashboard_store import save_cloud_digest
from jobscrawler.web import json_response


# The Vercel function has a 300-second limit. Leave time to commit the daily digest.
CRAWL_BUDGET_SECONDS = 230


def _source_message(problem: str | None) -> str | None:
    if problem is None:
        return None
    status = re.search(r"\bHTTP (\d{3})\b", problem)
    if status:
        return f"منبع خطای HTTP {status[1]} برگرداند."
    if "time limit" in problem or "timed out" in problem:
        return "زمان دریافت آگهی‌ها به پایان رسید."
    if "robots.txt disallows" in problem:
        return "این منبع اجازهٔ دریافت خودکار این صفحه را نمی‌دهد."
    return "دریافت کامل آگهی‌ها از این منبع ممکن نشد."


def app(environ, start_response):
    if environ.get("REQUEST_METHOD") != "GET":
        return json_response(start_response, HTTPStatus.METHOD_NOT_ALLOWED, {"error": "GET required"})
    secret = os.environ.get("CRON_SECRET", "")
    authorization = environ.get("HTTP_AUTHORIZATION", "")
    if not secret or not compare_digest(authorization.encode(), f"Bearer {secret}".encode()):
        return json_response(start_response, HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
    if not os.environ.get("DATABASE_URL"):
        return json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Storage is not configured"})

    day = tehran_day()
    try:
        result = collect(SOURCES, deadline=time.monotonic() + CRAWL_BUDGET_SECONDS)
        sources = {name: _source_message(problem) for name, problem in result.sources.items()}
        save_cloud_digest(day, result.matches, sources)
    except Exception:
        # Driver and transport exception messages can include connection details.
        return json_response(start_response, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Could not save crawl"})

    status, http_status = "complete", HTTPStatus.OK
    if any(problem is not None for problem in sources.values()):
        status, http_status = "partial", HTTPStatus.MULTI_STATUS
        if all(problem is not None for problem in sources.values()) and not any(result.scanned.values()):
            status, http_status = "failed", HTTPStatus.BAD_GATEWAY
    return json_response(start_response, http_status, {
        "status": status,
        "day": day,
        "matched_listings": len(result.matches),
        "sources": sources,
    })
