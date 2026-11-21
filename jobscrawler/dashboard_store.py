"""Daily dashboard reads and durable storage for the hosted crawler."""

from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3

from .models import Listing
from .store import SCHEMA


LOCAL_DB = Path(__file__).resolve().parent.parent / "data" / "jobs.sqlite3"
SEED = Path(__file__).with_name("seed.json")
TEHRAN = timezone(timedelta(hours=3, minutes=30))
FIELDS = "source, source_id, title, company, location, url, posted_at, roles, first_seen"
INSERT_JOB = f"INSERT INTO jobs ({FIELDS}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
UPSERT_JOB = INSERT_JOB + """
    ON CONFLICT (source, source_id) DO UPDATE SET
        title = excluded.title, company = excluded.company, location = excluded.location,
        url = excluded.url, posted_at = COALESCE(excluded.posted_at, jobs.posted_at),
        roles = excluded.roles, first_seen = LEAST(jobs.first_seen, excluded.first_seen)
"""
UPSERT_RUN = """
    INSERT INTO source_runs (day, source, error) VALUES (%s, %s, %s)
    ON CONFLICT (day, source) DO UPDATE SET error = excluded.error
"""


def _snapshot(day: str | None) -> dict:
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    if day is not None and day != seed["day"]:
        raise KeyError(day)
    return {**seed, "days": [seed["day"]], "mode": "snapshot"}


def _posted_day(job: dict) -> tuple[date, str]:
    value = job["posted_at"] or ""
    try:
        moment = datetime.fromisoformat(value)
        if moment.tzinfo:
            moment = moment.astimezone(TEHRAN)
        return moment.date(), value
    except ValueError:
        return date.min, ""


def _report(db, day: str | None, mode: str) -> dict:
    days = [row["day"] for row in db.execute("SELECT DISTINCT day FROM source_runs ORDER BY day DESC")]
    selected = days[0] if day is None and days else day
    if selected not in days:
        raise KeyError(selected)
    placeholder = "?" if mode == "local" else "%s"
    sources = {
        row["source"]: row["error"] for row in db.execute(
            f"SELECT source, error FROM source_runs WHERE day={placeholder} ORDER BY source", (selected,)
        )
    }
    rows = db.execute(f"SELECT {FIELDS} FROM jobs WHERE first_seen={placeholder}", (selected,))
    jobs = [dict(row) for row in rows]
    for job in jobs:
        job["roles"] = json.loads(job["roles"])
    # Keep ties identical across PostgreSQL collations and the packaged SQLite snapshot.
    jobs.sort(key=lambda j: (j["source"], j["title"], j["source_id"]))
    jobs.sort(key=_posted_day, reverse=True)
    return {"day": selected, "days": days, "sources": sources, "jobs": jobs, "mode": mode}


def _initialized(db):
    # All schema creation and seed writes commit together. This table is the marker.
    return db.execute("""
        SELECT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'felowin_jobs' AND c.relname = 'source_runs'
        ) AS ready
    """).fetchone()["ready"]


def _initialize_cloud(db):
    if _initialized(db):
        return
    # Parallel cold starts must not both create the schema or replay the snapshot.
    db.execute("SELECT pg_advisory_xact_lock(hashtext('felowin_jobs.initialize'))")
    if _initialized(db):
        return
    db.execute("CREATE SCHEMA IF NOT EXISTS felowin_jobs")
    db.execute("SET LOCAL search_path TO felowin_jobs")
    db.execute(SCHEMA, prepare=False)
    seed = _snapshot(None)
    with db.cursor() as cur:
        cur.executemany(INSERT_JOB, (
            (j["source"], j["source_id"], j["title"], j["company"], j["location"], j["url"],
             j["posted_at"], json.dumps(j["roles"]), j["first_seen"]) for j in seed["jobs"]
        ))
        cur.executemany(UPSERT_RUN, ((seed["day"], s, error) for s, error in seed["sources"].items()))


@contextmanager
def _cloud(db_url: str, *, read_only: bool = False):
    # The SQLite preview and packaged snapshot require only the standard library.
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(db_url, connect_timeout=10, row_factory=dict_row, prepare_threshold=None) as db:
        _initialize_cloud(db)
        db.commit()
        if read_only:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        db.execute("SET LOCAL search_path TO felowin_jobs")
        yield db


def read_dashboard(day: str | None = None) -> dict:
    if db_url := os.environ.get("DATABASE_URL"):
        with _cloud(db_url, read_only=True) as db:
            return _report(db, day, "live")
    if not os.environ.get("VERCEL") and LOCAL_DB.is_file():
        with closing(sqlite3.connect(f"{LOCAL_DB.as_uri()}?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            return _report(db, day, "local")
    return _snapshot(day)


def save_cloud_digest(day: str, matches: list[tuple[Listing, tuple[str, ...]]],
                      sources: dict[str, str | None]) -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is required to store scheduled results.")
    with _cloud(db_url) as db, db.cursor() as cur:
        # Consistent write order also prevents duplicate cron runs from deadlocking.
        ordered = sorted(matches, key=lambda pair: (pair[0].source, pair[0].source_id))
        cur.executemany(UPSERT_JOB, (
            (j.source, j.source_id, j.title, j.company, j.location, j.url, j.posted_at,
             json.dumps(roles), day) for j, roles in ordered
        ))
        cur.executemany(UPSERT_RUN, ((day, s, sources[s]) for s in sorted(sources)))
