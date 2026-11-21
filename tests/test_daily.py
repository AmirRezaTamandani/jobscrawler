from contextlib import closing, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from jobscrawler import __main__ as cli
from jobscrawler.http import SourceError
from jobscrawler.models import Listing


def listing(source):
    return Listing(source, "42", "SEO Specialist", "Felowin", "Tehran",
                   f"https://{source}.ir/jobs/42")


class DailyDigestTests(unittest.TestCase):
    def test_partial_run_retry_and_next_day(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            args = ["--data-dir", folder, "--reports-dir", folder]
            def unavailable(*args):
                raise SourceError("HTTP 503")

            def fetch(day, sources, extra_args=()):
                with (patch.object(cli, "SOURCES", sources),
                      patch.object(cli, "tehran_day", return_value=day),
                      redirect_stdout(StringIO()), redirect_stderr(StringIO())):
                    return cli.main([*args, *extra_args])

            day = "2026-11-20"
            both = {source: (lambda *args, name=source: [listing(name)] * 2)
                    for source in ("jobvision", "jobinja")}
            with_failure = {**both, "jobinja": unavailable}
            self.assertEqual(fetch(day, with_failure), 1)
            page = (root / f"{day}.html").read_text(encoding="utf-8")
            self.assertIn("HTTP 503", page)
            self.assertIn("https://jobvision.ir/jobs/42", page)

            self.assertEqual(fetch(day, both, ["--source", "jobinja"]), 0)
            page = (root / f"{day}.html").read_text(encoding="utf-8")
            self.assertNotIn("HTTP 503", page)
            for source in both:
                self.assertIn(listing(source).url, page)

            self.assertEqual(fetch("2026-11-21", both), 0)
            page = (root / "2026-11-21.html").read_text(encoding="utf-8")
            self.assertNotIn(listing("jobinja").url, page)
            with closing(sqlite3.connect(root / "jobs.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 2)
