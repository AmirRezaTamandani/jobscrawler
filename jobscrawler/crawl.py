"""Shared collection pipeline for the local command and scheduled Vercel function."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .http import HttpClient, SourceError
from .models import Listing
from .roles import SEARCH_TERMS, match_roles
from .sources import PartialSearchError, jobinja, jobvision


SOURCES = {"jobinja": jobinja.fetch, "jobvision": jobvision.fetch}
DEFAULT_MAX_PAGES = 5


def tehran_day() -> str:
    try:
        tz = ZoneInfo("Asia/Tehran")
    except ZoneInfoNotFoundError:
        # Windows installations without an IANA time zone database.
        tz = timezone(timedelta(hours=3, minutes=30))
    return datetime.now(tz).date().isoformat()


@dataclass
class CrawlResult:
    matches: list[tuple[Listing, tuple[str, ...]]]
    sources: dict[str, str | None]
    scanned: dict[str, int]


def collect(sources, max_pages=DEFAULT_MAX_PAGES, *, deadline: float | None = None) -> CrawlResult:
    result = CrawlResult([], {}, {})
    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        pending = {
            executor.submit(fetch, HttpClient(deadline=deadline), SEARCH_TERMS, max_pages): name
            for name, fetch in sources.items()
        }
        for future in as_completed(pending):
            name = pending[future]
            try:
                jobs = future.result()
                problem = None
            except PartialSearchError as exc:
                jobs, problem = exc.jobs, str(exc)
            except SourceError as exc:
                jobs, problem = [], str(exc)
            except Exception as exc:
                # A parser regression on one board must not discard the other board's jobs.
                jobs, problem = [], f"Unexpected source error ({type(exc).__name__})"
            result.sources[name] = problem
            result.scanned[name] = len(jobs)
            result.matches.extend((job, roles) for job in jobs if (roles := match_roles(job.title)))
    return result
