import json
import time
import unittest
from threading import Event
from unittest.mock import Mock, patch

from api import cron
from jobscrawler.crawl import CrawlResult, collect
from jobscrawler.http import HttpClient, SourceError
from jobscrawler.models import Listing
from jobscrawler.sources import PartialSearchError


class DeadlineTests(unittest.TestCase):
    def test_blocked_network_call_returns_by_deadline(self):
        client = HttpClient(deadline=time.monotonic() + 0.12)
        release = Event()
        try:
            with patch.object(client, "_download", side_effect=lambda *_: release.wait(3)):
                start = time.monotonic()
                with self.assertRaisesRegex(SourceError, "time limit"):
                    client.get("https://jobinja.ir/jobs")
                self.assertLess(time.monotonic() - start, 1.5)
        finally:
            release.set()

    def test_pacing_and_completed_pages_respect_deadline(self):
        job = Listing("jobvision", "1", "SEO", "", "", "https://jobvision.ir/jobs/1")
        def partly_available(client, terms, max_pages):
            raise PartialSearchError("Crawl time limit reached", [job])

        def delayed(client, terms, max_pages):
            client._next_request["jobinja.ir"] = time.monotonic() + 100
            client.get("https://jobinja.ir/jobs")

        sources = {"jobvision": partly_available, "jobinja": delayed}
        with patch("jobscrawler.http.urlopen") as fetch:
            result = collect(sources, deadline=time.monotonic() + 10)
        fetch.assert_not_called()
        self.assertEqual(result.scanned, {"jobvision": 1, "jobinja": 0})
        self.assertEqual(result.matches, [(job, ("seo",))])
        self.assertEqual(set(result.sources.values()), {"Crawl time limit reached"})


class CronTests(unittest.TestCase):
    def call(self, method="GET", authorization="Bearer example"):
        callback = Mock()
        data = cron.app({"REQUEST_METHOD": method, "HTTP_AUTHORIZATION": authorization}, callback)
        status, headers = callback.call_args.args
        self.assertEqual(dict(headers)["Cache-Control"], "no-store")
        return int(status.split()[0]), dict(headers), json.loads(b"".join(data))

    @patch("api.cron.collect")
    def test_only_authorized_get_can_start_work(self, crawl):
        with patch.dict("os.environ", {"DATABASE_URL": "", "CRON_SECRET": ""}, clear=True):
            self.assertEqual(self.call(authorization="Bearer ")[0], 401)
        with patch.dict("os.environ", {"CRON_SECRET": "example"}, clear=True):
            for invalid in ("", "Bearer wrong", "example", "Bearer example ", "Bearer آزمایشی"):
                self.assertEqual(self.call(authorization=invalid)[0], 401)
            code, headers, _ = self.call(method="POST")
            self.assertEqual((code, headers["Allow"]), (405, "GET"))
            self.assertEqual(self.call()[0], 503)
        crawl.assert_not_called()

    @patch.dict("os.environ", {"CRON_SECRET": "example", "DATABASE_URL": "test"})
    @patch("api.cron.save_cloud_digest")
    @patch("api.cron.collect")
    def test_run_outcomes_are_persisted_and_sanitized(self, crawl, save):
        for errors, scanned, code, label in (
            ((None, None), (0, 0), 200, "complete"),
            ((None, "HTTP 429 private"), (0, 0), 207, "partial"),
            (("private", "private"), (1, 0), 207, "partial"),
            (("private", "private"), (0, 0), 502, "failed"),
        ):
            with self.subTest(label=label, scanned=scanned):
                sources = ("jobvision", "jobinja")
                crawl.return_value = CrawlResult([], dict(zip(sources, errors)), dict(zip(sources, scanned)))
                observed, _, body = self.call()
                self.assertEqual((observed, body["status"]), (code, label))
                self.assertEqual(save.call_args.args, (body["day"], [], body["sources"]))
                self.assertNotIn("private", str(body))
        save.side_effect = RuntimeError("private credential")
        observed, _, body = self.call()
        self.assertEqual(observed, 500)
        self.assertNotIn("credential", str(body))
