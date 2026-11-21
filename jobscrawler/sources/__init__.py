"""Public job board adapters."""

from collections.abc import Iterable

from ..http import SourceError
from ..models import Listing


class PartialSearchError(SourceError):
    def __init__(self, message: str, jobs: list[Listing]):
        super().__init__(message)
        self.jobs = jobs


def collect_pages(pages: Iterable[list[Listing]]) -> list[Listing]:
    jobs = {}
    try:
        for page in pages:
            for job in page:
                jobs.setdefault(job.source_id, job)
    except SourceError as exc:
        if jobs:
            raise PartialSearchError(str(exc), list(jobs.values())) from exc
        raise
    return list(jobs.values())
