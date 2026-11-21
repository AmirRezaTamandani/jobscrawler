import codecs
from concurrent.futures import Future
import http.client
import json
from threading import Thread
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser


class SourceError(Exception):
    """A public source could not provide usable results."""


USER_AGENT = "FelowinJobs/1.0"


class HttpClient:
    """One client per source, with sequential, paced requests per host."""

    def __init__(self, *, deadline: float | None = None):
        self._robots = {}
        self._next_request = {}
        self._deadline = deadline

    def _remaining(self):
        if self._deadline is None:
            return None
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise SourceError("Crawl time limit reached")
        return remaining

    def _read(self, url, *, headers=None, body=None, delay=1.0):
        host = urlsplit(url).netloc
        wait = max(0.0, self._next_request.get(host, 0) - time.monotonic())
        remaining = self._remaining()
        if remaining is not None and wait >= remaining:
            raise SourceError("Crawl time limit reached")
        time.sleep(wait)
        self._next_request[host] = time.monotonic() + delay
        request = Request(url, data=body, headers={**(headers or {}), "User-Agent": USER_AGENT})
        if self._deadline is None:
            return self._download(request)

        # A socket timeout alone cannot bound DNS resolution or trickled HTTP headers.
        # The source can stop waiting and save completed pages at its absolute deadline.
        transfer = Future()

        def download():
            try:
                transfer.set_result(self._download(request))
            except Exception as exc:
                transfer.set_exception(exc)

        Thread(target=download, daemon=True).start()
        try:
            return transfer.result(timeout=self._remaining())
        except TimeoutError as exc:
            if not transfer.done():
                raise SourceError("Crawl time limit reached") from exc
            raise

    def _download(self, request):
        remaining = self._remaining()
        timeout = 25 if remaining is None else min(25, remaining)
        with urlopen(request, timeout=timeout) as response:
            limit = 12 * 1024 * 1024
            raw = bytearray()
            while True:
                self._remaining()
                chunk = response.read1(min(65536, limit + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > limit:
                    raise SourceError(f"{request.host}: response exceeded 12 MiB")
            encoding = response.headers.get_content_charset() or "utf-8-sig"
            if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
                encoding = "utf-16"
            return raw.decode(encoding)

    def _request(self, url, *, headers=None, body=None):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        try:
            if origin not in self._robots:
                robots = RobotFileParser(f"{origin}/robots.txt")
                try:
                    lines = self._read(robots.url).splitlines()
                except HTTPError as exc:
                    if exc.code not in (404, 410):
                        raise
                    lines = []
                robots.parse(lines)
                self._robots[origin] = robots
            robots = self._robots[origin]
            if not robots.can_fetch(USER_AGENT, url):
                raise SourceError(f"{parts.netloc}: robots.txt disallows {parts.path}")
            delay = max(1.0, robots.crawl_delay(USER_AGENT) or 0)
            return self._read(url, headers=headers, body=body, delay=delay)
        except HTTPError as exc:
            detail = f" (Retry-After: {exc.headers['Retry-After']})" if exc.headers.get("Retry-After") else ""
            raise SourceError(f"{parts.netloc}: HTTP {exc.code}{detail}") from exc
        except (URLError, OSError, http.client.HTTPException, UnicodeError, LookupError) as exc:
            raise SourceError(f"{parts.netloc}: {exc}") from exc

    def get(self, url: str, *, headers=None) -> str:
        return self._request(url, headers=headers)

    def post_json(self, url: str, payload, *, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        raw = self._request(url, body=body, headers={
            "Content-Type": "application/json", "Accept": "application/json", **(headers or {}),
        })
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise SourceError(f"{urlsplit(url).netloc}: invalid JSON response") from exc
