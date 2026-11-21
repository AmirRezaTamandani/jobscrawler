"""Read the public, newest-first Jobinja keyword results."""

import re
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit

from ..http import HttpClient, SourceError
from ..models import Listing
from . import collect_pages


SEARCH_URL = "https://jobinja.ir/jobs"
_VOID_TAGS = set("area base br col embed hr img input link meta param source track wbr".split())
_JOB_PATH = re.compile(r"/companies/[^/]+/jobs/([A-Za-z0-9_-]+)(?:/[^/]*)?/?")
_TEHRAN = timezone(timedelta(hours=3, minutes=30))


def _posted_date(label: str, today: date) -> str | None:
    label = label.strip("() ")
    if label == "امروز":
        return today.isoformat()
    if label == "دیروز":
        return (today - timedelta(days=1)).isoformat()
    match = re.fullmatch(r"(\d{1,3}) روز پیش", label)
    return (today - timedelta(days=int(match[1]))).isoformat() if match else None


class _Results(HTMLParser):
    def __init__(self, today: date):
        super().__init__()
        self.today = today
        self.jobs: list[Listing] = []
        self.empty = False
        self.has_next = False
        # Within a card, nested tags inherit the field whose text they contain.
        self.frames: list[tuple[str, str]] = []
        self.values: dict[str, list[str]] = {}
        self.href = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if tag == "a" and "next" in (attrs.get("rel") or "").split():
            self.has_next = True
        if "c-jobSearch__noResult" in classes:
            self.empty = True
        if "c-jobListView__item" in classes:
            if self.frames:
                raise SourceError("Jobinja: encountered an unclosed job card")
            self.values = {}
            self.href = ""
            self.frames.append((tag, ""))
            return
        if not self.frames or tag in _VOID_TAGS:
            return
        field = self.frames[-1][1]
        if tag == "a" and "c-jobListView__titleLink" in classes:
            field = "title"
            self.href = attrs.get("href") or ""
        elif "c-jobListView__passedDays" in classes:
            field = "posted_at"
        elif "c-jobListView__metaItem" in classes:
            field = "meta"
        elif field == "meta" and tag == "i":
            # The icon identifies the following text inside the same metadata item.
            for icon, name in (("c-icon--construction", "company"), ("c-icon--place", "location")):
                if icon in classes:
                    self.frames[-1] = (self.frames[-1][0], name)
                    break
        self.frames.append((tag, field))

    def handle_data(self, data):
        if self.frames and self.frames[-1][1] in ("title", "company", "location", "posted_at"):
            self.values.setdefault(self.frames[-1][1], []).append(data)

    def handle_endtag(self, tag):
        if not self.frames or self.frames[-1][0] != tag:
            return
        self.frames.pop()
        if not self.frames:
            self.jobs.append(self._listing())

    def _listing(self) -> Listing:
        fields = {key: " ".join("".join(parts).split()) for key, parts in self.values.items()}
        link = urlsplit(urljoin(SEARCH_URL, self.href))
        match = _JOB_PATH.fullmatch(link.path)
        if link.scheme != "https" or link.netloc != "jobinja.ir" or not match or not fields.get("title"):
            raise SourceError("Jobinja: job card has an invalid title or detail link")
        return Listing(
            source="jobinja",
            source_id=match[1],
            title=fields["title"],
            company=fields.get("company", ""),
            location=fields.get("location", ""),
            url=f"https://jobinja.ir{link.path}",
            posted_at=_posted_date(fields.get("posted_at", ""), self.today),
        )


def _pages(client: HttpClient, terms: tuple[str, ...], max_pages: int):
    for term in terms:
        for page in range(1, max_pages + 1):
            query = urlencode({"filters[keywords][0]": term, "sort_by": "published_at_desc", "page": page})
            html = client.get(f"{SEARCH_URL}?{query}")
            results = _Results(datetime.now(_TEHRAN).date())
            results.feed(html)
            results.close()
            if results.frames or (not results.jobs and not results.empty):
                raise SourceError("Jobinja: incomplete or unrecognized search results page")
            yield results.jobs
            if not results.has_next:
                break


def fetch(client: HttpClient, terms: tuple[str, ...], max_pages: int) -> list[Listing]:
    return collect_pages(_pages(client, terms, max_pages))
