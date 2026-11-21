from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from jobscrawler import dashboard_store as store
from jobscrawler.models import Listing
from jobscrawler.store import SCHEMA


class DashboardStoreTests(unittest.TestCase):
    def test_vercel_without_database_uses_dated_snapshot(self):
        with patch.dict(os.environ, {"VERCEL": "1", "DATABASE_URL": ""}):
            report = store.read_dashboard()
            self.assertEqual(report["mode"], "snapshot")
            self.assertEqual(report["days"], [report["day"]])
            self.assertEqual(set(report["sources"]), {"jobvision", "jobinja"})
            self.assertTrue(report["jobs"])
            self.assertTrue(all(j["first_seen"] == report["day"] for j in report["jobs"]))
            self.assertEqual(report, store.read_dashboard(report["day"]))
            with self.assertRaises(KeyError):
                store.read_dashboard("1999-12-31")
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                store.save_cloud_digest(report["day"], [], {})

    def test_local_reads_historical_and_empty_days(self):
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "jobs.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.executescript(SCHEMA)
                db.executemany("INSERT INTO source_runs VALUES (?,?,?)", [
                    ("2026-11-21", "jobinja", None), ("2026-11-22", "jobvision", "timeout")
                ])
                db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                           ("jobinja", "1", "SEO", "Co", "", "https://jobinja.ir", None, '["seo"]', "2026-11-21"))
            with patch.object(store, "LOCAL_DB", path), patch.dict(os.environ, {"VERCEL": "", "DATABASE_URL": ""}):
                latest = store.read_dashboard()
                self.assertEqual(latest["mode"], "local")
                self.assertEqual(latest["days"], ["2026-11-22", "2026-11-21"])
                self.assertEqual(latest["jobs"], [])
                self.assertEqual(latest["sources"], {"jobvision": "timeout"})
                earlier = store.read_dashboard("2026-11-21")
                self.assertEqual(earlier["jobs"][0]["roles"], ["seo"])
                with self.assertRaises(KeyError):
                    store.read_dashboard("1999-12-31")


@unittest.skipUnless(os.environ.get("JOBSCRAWLER_TEST_POSTGRES_URL"), "requires disposable PostgreSQL with CREATEDB")
class CloudDashboardTests(unittest.TestCase):
    def test_concurrent_bootstrap_then_idempotent_cron_and_archive(self):
        import psycopg
        from psycopg.conninfo import make_conninfo
        from psycopg.sql import Identifier, SQL

        parent = os.environ["JOBSCRAWLER_TEST_POSTGRES_URL"]
        name = "digest_test_" + uuid4().hex
        with psycopg.connect(parent, autocommit=True) as admin:
            admin.execute(SQL("CREATE DATABASE {}").format(Identifier(name)))
            try:
                with patch.dict(os.environ, {"DATABASE_URL": make_conninfo(parent, dbname=name)}):
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        reports = list(pool.map(store.read_dashboard, [None] * 4))
                    self.assertTrue(all(r == reports[0] for r in reports))
                    self.assertEqual(reports[0]["mode"], "live")
                    original = store._snapshot(None)
                    self.assertEqual(reports[0]["jobs"], original["jobs"])
                    job = Listing("jobinja", "new-id", "SEO", "Co", "", "https://jobinja.ir")
                    next_day = "2030-01-06"
                    store.save_cloud_digest(next_day, [(job, ("seo",))], {"jobinja": None, "jobvision": "timeout"})
                    store.save_cloud_digest(next_day, [(job, ("seo",))], {"jobvision": None})
                    report = store.read_dashboard()
                    self.assertEqual(report["day"], next_day)
                    self.assertEqual(len(report["jobs"]), 1)
                    self.assertEqual(report["sources"], {"jobinja": None, "jobvision": None})
                    store.save_cloud_digest("2030-01-07", [(job, ("seo",))], {"jobinja": None})
                    self.assertEqual(store.read_dashboard()["jobs"], [])
                    self.assertEqual(store.read_dashboard(next_day)["jobs"][0]["first_seen"], next_day)
                    with self.assertRaises(KeyError):
                        store.read_dashboard("1999-12-31")
            finally:
                admin.execute(SQL("DROP DATABASE {}").format(Identifier(name)))
