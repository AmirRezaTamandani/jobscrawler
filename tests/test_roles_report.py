import unittest
from html.parser import HTMLParser

from jobscrawler.report import render_report
from jobscrawler.roles import match_roles


class TitleTests(unittest.TestCase):
    def test_titles(self):
        cases = {
            "کارشناس پرفورمنس مارکتینگ": ("performance",),
            "تحلیلگر بازاریابی (Performance Marketer)": ("performance",),
            "Performance & Campaign Specialist": ("performance",),
            "SEO Google Ads Specialist (دورکاری)": ("performance", "seo"),
            "کارشناس گوگل ادز": ("performance",),
            "کارشناس تبلیغات کلیکی": ("performance",),
            "کارشناس سئو و طراحی سایت": ("seo",),
            "کارآموز بهینه‌سازی موتورهای جست‌وجو": ("seo",),
            "کارشناس سئو و ادمین شبکه‌های اجتماعی": ("seo", "social"),
            "كارشناس شبكه هاي اجتماعي": ("social",),
            "ادمین اینستاگرام": ("social",),
            "بازیگر اینستاگرام": (),
            "ادمین فروش اینستاگرام": (),
            "کارشناس فروش آنلاین (سوشال-خانم)": (),
            "کارشناس شبکه‌های اجتماعی (هماهنگی فروش)": ("social",),
            "کارشناس فروش آنلاین و ادمین اینستاگرام": ("social",),
            "متخصص ارشد امنیت موبایل و شبکه‌های اجتماعی": (),
            "Social Media Manager": ("social",),
            "Performance Test Engineer": (),
            "Performance Management Expert (HR)": (),
            "Social Worker": (),
            "مهندس تست پرفورمنس": (),
            "Salesforce Administrator": (),
            "بازاریاب فروش (خدمات طراحی سایت و سئو)": (),
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(match_roles(title), expected)


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.links.append(dict(attrs)["href"])


class DigestTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "title": "SEO <script>bad()</script>", "roles": ("seo",),
            "url": "https://jobvision.ir/jobs/34?x=1&y=2", "company": "A&B",
            "location": "", "posted_at": "2026-11-20T17:00:00Z", "source": "jobvision",
        }

    def test_publication_and_discovery_dates_and_escaped_source_text(self):
        page = render_report("2026-11-21", [self.row], {"jobvision": None, "jobinja": "<iframe>"})
        dom = _Tags()
        dom.feed(page)
        self.assertEqual(dom.links, [self.row["url"]])
        self.assertEqual(dom.tags.count("script"), 1)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", page)
        self.assertNotIn("iframe", dom.tags)
        self.assertIn("۲۰۲۶/۱۱/۲۱ میلادی", page)
        self.assertIn("۲۰۲۶/۱۱/۲۰ میلادی", page)
        self.assertIn("دریافت از جابینجا ناموفق بود", page)

    def test_tehran_publication_date_and_counts_for_multi_role_listings(self):
        dual = dict(self.row, roles=("performance", "seo"), posted_at="2026-11-20T22:00:00Z")
        page = render_report("2026-11-22", [dual, self.row], {"jobvision": None})
        self.assertIn("۲۰۲۶/۱۱/۲۱ میلادی", page)
        self.assertIn("سئو <b>۲</b>", page)
        self.assertIn("پرفورمنس مارکتینگ <b>۱</b>", page)
        self.assertIn("۲ آگهی ثبت‌شده", page)
        self.assertIn("آگهی چندحوزه‌ای", page)

    def test_link_must_belong_to_its_source(self):
        for url in ("javascript:alert(1)", "https://example.com/",
                    "https://jobvision.ir.example.com", "https://jobvision.ir@evil.example",
                    "https://evil.example\\@jobvision.ir/x", "https://[x"):
            with self.subTest(url=url):
                page = render_report("2026-11-21", [dict(self.row, url=url)], {"jobvision": None})
                dom = _Tags()
                dom.feed(page)
                self.assertFalse(dom.links)

    def test_missing_sources_distinct_from_no_matches(self):
        partial = render_report("2026-11-21", [], {"jobvision": None, "jobinja": "timeout"})
        failed = render_report("2026-11-21", [], {"jobvision": "timeout", "jobinja": "timeout"})
        self.assertIn("در منابعی که بررسی شدند", partial)
        self.assertIn("نتیجهٔ این روز هنوز مشخص نیست", failed)
