"""Search the public listing endpoint used by JobVision's jobs page."""

from ..http import HttpClient, SourceError
from ..models import Listing
from . import collect_pages


SEARCH_URL = "https://candidateapi.jobvision.ir/api/v1/JobPost/List"
PAGE_SIZE = 30


def _text(record: object, *keys: str) -> str:
    if isinstance(record, dict):
        for key in keys:
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _listing(post: object) -> Listing:
    if not isinstance(post, dict):
        raise SourceError("JobVision returned an invalid job posting.")
    job_id = str(post.get("id", ""))
    title = _text(post, "title")
    if not (job_id.isascii() and job_id.isdecimal() and int(job_id) > 0 and title):
        raise SourceError("JobVision returned a posting without a valid ID or title.")

    location = post.get("location") or {}
    if not isinstance(location, dict):
        raise SourceError("JobVision returned an invalid location.")
    province = _text(location.get("province"), "titleFa", "title", "titleEn")
    city = _text(location.get("city"), "titleFa", "title", "titleEn")
    place = "، ".join(dict.fromkeys(part for part in (province, city) if part))
    posted_at = _text(post.get("firstActivationTime"), "date") or _text(post.get("activationTime"), "date")
    return Listing(
        source="jobvision",
        source_id=job_id,
        title=title,
        company=_text(post.get("company"), "nameFa", "nameEn"),
        location=place,
        url=f"https://jobvision.ir/jobs/{job_id}",
        posted_at=posted_at or None,
    )


def _pages(client: HttpClient, terms: tuple[str, ...], max_pages: int):
    for term in terms:
        search_id = None
        for page in range(1, max_pages + 1):
            payload = {
                "keyword": term,
                "sortBy": 0,  # JobVision's newest-first option
                "requestedPage": page,
                "pageSize": PAGE_SIZE,
                "searchId": search_id,
            }
            response = client.post_json(SEARCH_URL, payload)
            if not isinstance(response, dict) or response.get("isSuccess") is not True:
                raise SourceError("JobVision did not return a successful search response.")
            data = response.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("jobPosts"), list):
                raise SourceError("JobVision search response is missing jobPosts.")
            if data.get("currentPage") != page:
                raise SourceError("JobVision returned an unexpected page number.")
            total = data.get("jobPostCount")
            page_size = data.get("pageSize")
            if type(total) is not int or total < 0 or type(page_size) is not int or page_size < 1:
                raise SourceError("JobVision returned invalid pagination data.")
            posts = data["jobPosts"]
            if not posts and total > (page - 1) * page_size:
                raise SourceError("JobVision returned an empty page despite reporting available postings.")
            yield [_listing(post) for post in posts]
            if page * page_size >= total or not posts:
                break
            search_id = data.get("searchId")


def fetch(client: HttpClient, terms: tuple[str, ...], max_pages: int) -> list[Listing]:
    return collect_pages(_pages(client, terms, max_pages))
