import json
from http import HTTPStatus
import unittest
from unittest.mock import Mock, patch

from api import crawl
from jobscrawler.crawl import CrawlResult


class ManualCrawlTests(unittest.TestCase):
    def request(self, method="POST", token="Bearer example"):
        start = Mock()
        response = crawl.app({"REQUEST_METHOD": method, "HTTP_AUTHORIZATION": token}, start)
        status, headers = start.call_args.args
        return int(status.split()[0]), dict(headers), json.loads(b"".join(response))

    @patch("api.crawl.collect")
    def test_requires_post_and_configured_secret(self, collect):
        with patch.dict("os.environ", {"CRON_SECRET": "example"}, clear=True):
            status, headers, _ = self.request(method="GET")
            self.assertEqual((status, headers["Allow"]), (405, "POST"))
            self.assertEqual(self.request(token="Bearer bad")[0], 401)
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(self.request()[0], 401)
        collect.assert_not_called()

    @patch.dict("os.environ", {"CRON_SECRET": "example"}, clear=True)
    @patch("api.crawl.save_digest")
    @patch("api.crawl.collect")
    def test_local_run_saves_partial_and_returns_status(self, collect, save):
        collect.return_value = CrawlResult([], {"jobinja": None, "jobvision": "HTTP 429 private"}, {"jobinja": 0, "jobvision": 0})
        status, headers, body = self.request()
        self.assertEqual((status, body["status"]), (207, "partial"))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("private", str(body))
        self.assertEqual(save.call_args.args[2], body["day"])

    @patch.dict("os.environ", {"CRON_SECRET": "example", "DATABASE_URL": "configured"}, clear=True)
    @patch("api.crawl.cron.app")
    def test_cloud_delegates_to_scheduled_runner(self, scheduled):
        scheduled.return_value = [b"{}"]
        crawl.app({"REQUEST_METHOD": "POST", "HTTP_AUTHORIZATION": "Bearer example"}, Mock())
        self.assertEqual(scheduled.call_args.args[0]["REQUEST_METHOD"], "GET")

    @patch.dict("os.environ", {"CRON_SECRET": "example"}, clear=True)
    def test_parallel_local_request_is_rejected(self):
        with crawl._local_lock:
            self.assertEqual(self.request()[0], HTTPStatus.CONFLICT)
