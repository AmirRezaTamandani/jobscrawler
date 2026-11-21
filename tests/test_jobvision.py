import unittest
from unittest.mock import Mock

from jobscrawler.http import SourceError
from jobscrawler.sources import jobvision


def response(posts, *, page=1, size=30, total=None):
    return {
        "isSuccess": True,
        "data": {
            "currentPage": page,
            "pageSize": size,
            "jobPostCount": len(posts) if total is None else total,
            "searchId": "123456789",
            "jobPosts": posts,
        },
    }


class JobVisionTests(unittest.TestCase):
    def test_nationwide_search_maps_metadata_and_deduplicates_across_terms(self):
        first = {
            "id": 100,
            "title": "کارشناس سئو",
            "company": {"nameFa": "شرکت نمونه", "nameEn": "Example"},
            "location": {"province": {"titleFa": "تهران"}, "city": {"titleFa": "تهران"}},
            "firstActivationTime": {"date": "2026-11-19T06:00:00Z"},
            "activationTime": {"date": "2026-11-21T06:00:00Z"},
        }
        second = {"id": 101, "title": "SEO Specialist"}
        client = Mock()
        client.post_json.side_effect = [
            response([first], size=1, total=2),
            response([second], page=2, size=1, total=2),
            response([first]),
        ]
        jobs = jobvision.fetch(client, ("SEO", "سئو"), 3)
        self.assertEqual([item.source_id for item in jobs], ["100", "101"])
        self.assertEqual(jobs[0].source, "jobvision")
        self.assertEqual(jobs[0].title, "کارشناس سئو")
        self.assertEqual(jobs[0].company, "شرکت نمونه")
        self.assertEqual(jobs[0].location, "تهران")
        self.assertEqual(jobs[0].posted_at, "2026-11-19T06:00:00Z")
        self.assertEqual(jobs[0].url, "https://jobvision.ir/jobs/100")
        self.assertIsNone(jobs[1].posted_at)
        requests = [call.args[1] for call in client.post_json.call_args_list]
        self.assertEqual([req["requestedPage"] for req in requests], [1, 2, 1])
        self.assertEqual([req["sortBy"] for req in requests], [0, 0, 0])
        self.assertEqual([req["searchId"] for req in requests], [None, "123456789", None])
        self.assertTrue(all("locationWrapper" not in req for req in requests))

    def test_page_limit_and_empty_search(self):
        client = Mock()
        client.post_json.side_effect = [response([{"id": 1, "title": "SEO"}], total=100), response([])]
        jobs = jobvision.fetch(client, ("SEO", "nomatch"), 1)
        self.assertEqual([item.source_id for item in jobs], ["1"])
        self.assertEqual(client.post_json.call_count, 2)

    def test_errors_are_distinct_from_genuine_empty_results(self):
        for invalid in (
            {"isSuccess": False},
            {"isSuccess": True, "data": {}},
            response([{"id": "javascript:alert(1)", "title": "SEO"}]),
            response([{"id": 100}]),
            response([], total=1),
            response([], page=2),
        ):
            with self.subTest(invalid=invalid):
                client = Mock()
                client.post_json.return_value = invalid
                with self.assertRaises(SourceError):
                    jobvision.fetch(client, ("SEO",), 1)
