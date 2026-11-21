import json
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile

from .models import Listing
from .report import render_report


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT NOT NULL,
    url TEXT NOT NULL,
    posted_at TEXT,
    roles TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);
CREATE INDEX IF NOT EXISTS jobs_by_day ON jobs(first_seen);
CREATE TABLE IF NOT EXISTS source_runs (
    day TEXT NOT NULL,
    source TEXT NOT NULL,
    error TEXT,
    PRIMARY KEY (day, source)
);
"""


def _write_report(path: Path, html: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False)
    temp = Path(stream.name)
    try:
        with stream:
            stream.write(html.encode("utf-8"))
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def save_digest(db_path: Path, report_path: Path, day: str,
                matches: list[tuple[Listing, tuple[str, ...]]],
                sources: dict[str, str | None]) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        with db:
            db.execute("BEGIN IMMEDIATE")
            db.executemany("""
                INSERT INTO jobs (source, source_id, title, company, location, url, posted_at, roles, first_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, source_id) DO UPDATE SET
                    title=excluded.title, company=excluded.company, location=excluded.location,
                    url=excluded.url, posted_at=COALESCE(excluded.posted_at, jobs.posted_at), roles=excluded.roles
            """, ((job.source, job.source_id, job.title, job.company, job.location, job.url,
                   job.posted_at, json.dumps(roles), day) for job, roles in matches))
            db.executemany("""
                INSERT INTO source_runs (day, source, error) VALUES (?, ?, ?)
                ON CONFLICT(day, source) DO UPDATE SET error=excluded.error
            """, ((day, source, error) for source, error in sources.items()))
            rows = [dict(row) for row in db.execute("""
                SELECT * FROM jobs WHERE first_seen=?
                ORDER BY date(posted_at, '+210 minutes') DESC, posted_at DESC, source, title, source_id
            """, (day,))]
            for row in rows:
                row["roles"] = tuple(json.loads(row["roles"]))
            status = dict(db.execute("SELECT source, error FROM source_runs WHERE day=?", (day,)))
            _write_report(report_path, render_report(day, rows, status))
        return len(rows)
    finally:
        db.close()
