from http import HTTPStatus
import json


def json_response(start_response, status: HTTPStatus, data: dict) -> list[bytes]:
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
    ]
    if status == HTTPStatus.METHOD_NOT_ALLOWED:
        headers.append(("Allow", "GET"))
    start_response(f"{status.value} {status.phrase}", headers)
    return [body]
