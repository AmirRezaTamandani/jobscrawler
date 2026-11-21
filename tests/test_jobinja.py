import unittest
from datetime import date
from urllib.parse import parse_qs, urlsplit

from jobscrawler.http import SourceError
from jobscrawler.sources import PartialSearchError
from jobscrawler.sources.jobinja import _Results, fetch


def card(job_id="t1ii"):
    return f"""
        <li class="o-listView__item c-jobListView__item">
          <div class="o-listView__itemInfo">
            <a href="/companies/venue/jobs/{job_id}/seo"><img src="/logo.png"></a>
            <h2><a class="c-jobListView__titleLink"
                   href="/companies/venue/jobs/{job_id}/seo?_ref=16&amp;_t=tracking">
              SEO &amp; Google Ads Specialist
            </a><span class="c-jobListView__passedDays">(۲ روز پیش)</span></h2>
            <ul>
              <li class="c-jobListView__metaItem"><i class="c-icon--construction"></i>
                  <span>ونیو مارکترز | The Venue Marketers</span></li>
              <li class="c-jobListView__metaItem"><i class="c-icon--place"></i>
                  <span>تهران، تهران</span></li>
              <li class="c-jobListView__metaItem"><i class="c-icon--resume"></i>
                  <span>قرارداد دورکاری</span></li>
            </ul>
          </div>
          <a href="/companies/venue/jobs/{job_id}/seo">ارسال رزومه</a>
        </li>"""


class Client:
    def __init__(self, *pages):
        self.pages = iter(pages)
        self.queries = []

    def get(self, url):
        self.queries.append(parse_qs(urlsplit(url).query))
        return next(self.pages)


class JobinjaTests(unittest.TestCase):
    def test_nested_card_and_date(self):
        page = _Results(date(2026, 11, 21))
        page.feed(card())
        job, = page.jobs
        self.assertEqual(job.title, "SEO & Google Ads Specialist")
        self.assertEqual(job.company, "ونیو مارکترز | The Venue Marketers")
        self.assertEqual(job.location, "تهران، تهران")
        self.assertEqual(job.posted_at, "2026-11-19")
        self.assertEqual(job.url, "https://jobinja.ir/companies/venue/jobs/t1ii/seo")

    def test_pages_and_keywords_deduplicate_by_short_id(self):
        client = Client(card() + '<a rel="next" href="?page=2"></a>', card("abC"), card())
        jobs = fetch(client, ("SEO", "سئو"), 4)
        self.assertEqual([job.source_id for job in jobs], ["t1ii", "abC"])
        self.assertEqual([q["page"][0] for q in client.queries], ["1", "2", "1"])
        self.assertEqual(client.queries[-1]["filters[keywords][0]"], ["سئو"])
        self.assertEqual(client.queries[0]["sort_by"], ["published_at_desc"])

    def test_only_explicit_empty_results_succeed(self):
        self.assertEqual(fetch(Client('<div class="c-jobSearch__noResult"></div>'), ("seo",), 2), [])
        for html in ("<title>Please wait</title>", card()[:-5], card().replace("/companies/", "//other.test/companies/")):
            with self.subTest(html=html[:45]), self.assertRaises(SourceError):
                fetch(Client(html), ("seo",), 2)

    def test_result_survives_failure_on_next_page(self):
        client = Client(card() + '<a rel="next" href="?page=2"></a>', "<title>Please wait</title>")
        with self.assertRaises(PartialSearchError) as error:
            fetch(client, ("SEO",), 2)
        self.assertEqual([job.source_id for job in error.exception.jobs], ["t1ii"])
