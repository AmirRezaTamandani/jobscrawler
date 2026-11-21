from datetime import date
from http import HTTPStatus
from urllib.parse import parse_qs
import logging

from jobscrawler.dashboard_store import read_dashboard
from jobscrawler.web import json_response


def app(environ, start_response):
    if environ.get("REQUEST_METHOD") != "GET":
        return json_response(start_response, HTTPStatus.METHOD_NOT_ALLOWED, {"error": "GET required."})
    try:
        query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True, max_num_fields=12)
        values = query.get("day")
        day = None if values is None else values[0]
        if values is not None and (len(values) != 1 or date.fromisoformat(day).isoformat() != day):
            raise ValueError("Invalid day")
    except ValueError:
        return json_response(start_response, HTTPStatus.BAD_REQUEST, {"error": "Use day=YYYY-MM-DD."})

    try:
        digest = read_dashboard(day)
    except KeyError:
        return json_response(start_response, HTTPStatus.NOT_FOUND, {"error": "Report date not found."})
    except Exception as exc:
        logging.error("Dashboard storage unavailable (%s)", type(exc).__name__)
        return json_response(start_response, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Dashboard unavailable."})
    return json_response(start_response, HTTPStatus.OK, digest)
