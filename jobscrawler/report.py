"""Render a portable, right-to-left daily digest."""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html import escape
from urllib.parse import urlsplit


SOURCE_NAMES = {"jobinja": "جابینجا", "jobvision": "جاب‌ویژن"}
SOURCE_DOMAINS = {"jobinja": "jobinja.ir", "jobvision": "jobvision.ir"}
ROLE_NAMES = {"performance": "پرفورمنس مارکتینگ", "seo": "سئو", "social": "شبکه‌های اجتماعی"}
_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_TEHRAN = timezone(timedelta(hours=3, minutes=30))
_STYLE = """
:root { color-scheme: light; font-family: Roboto, Tahoma, sans-serif; color: #142e30; background: #f6f8f7; }
* { box-sizing: border-box; }
body { margin: 0; line-height: 1.7; }
main { margin: 2.5rem auto; max-width: 74rem; padding: 0 1.2rem; }
header { border-inline-start: 4px solid #117362; padding-inline-start: 1rem; }
h1 { margin: 0 0 .25rem; font-size: clamp(1.5rem, 3vw, 2.15rem); }
h2 { font-size: 1.1rem; margin: 1.5rem 0 .65rem; }
p { margin: .25rem 0; }
.metadata, .sub, .source { color: #485f60; font-size: .88rem; }
.status { display: flex; flex-wrap: wrap; gap: .4rem 1.25rem; margin-top: 1rem; }
.error { color: #843616; }
.error summary { cursor: pointer; }
.error p { overflow-wrap: anywhere; }
.breakdown { display: flex; gap: .35rem 1.5rem; flex-wrap: wrap; margin: .25rem 0; }
.breakdown span { white-space: nowrap; }
.controls { display: flex; gap: .5rem 1rem; align-items: end; flex-wrap: wrap; margin: 1rem 0; }
.controls label { display: grid; gap: .15rem; font-size: .85rem; }
select, button, textarea { font: inherit; color: inherit; }
select, button { border: 1px solid #829c96; border-radius: .3rem; background: white; padding: .3rem .5rem; }
button { cursor: pointer; color: #005e51; }
button:disabled { opacity: .55; cursor: default; }
textarea { width: 100%; resize: vertical; }
[hidden] { display: none !important; }
table { width: 100%; border-collapse: collapse; background: #fff; border-block: 1px solid #d4dedc; }
th, td { text-align: start; padding: .75rem; vertical-align: top; }
thead { background: #ebf2ef; font-size: .85rem; }
tbody tr + tr { border-top: 1px solid #e0e8e6; }
.title { font-weight: 700; display: block; overflow-wrap: anywhere; }
.role, .company, .date { font-size: .91rem; }
a { color: #005e51; text-underline-offset: .2em; white-space: nowrap; }
a:focus-visible, summary:focus-visible { outline: 2px solid #007865; outline-offset: 3px; }
.cell-label { display: none; }
.empty { background: #fff; border: 1px solid #d4dedc; padding: 1rem; }
@media (max-width: 700px) {
  main { margin: 1.25rem auto; padding: 0 .75rem; }
  table, tbody, tr, td { display: block; }
  thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  tbody tr { padding: .85rem; }
  td { padding: .1rem 0; }
  td:last-child { padding-top: .4rem; }
  .cell-label { display: inline; color: #485f60; margin-inline-end: .35rem; }
}
@media print { :root { background: white; } main { max-width: none; margin: 0; } tr { break-inside: avoid; } .controls { display: none; } }
"""

_FILTER_SCRIPT = r"""
<script>
const controls = document.querySelector('.controls');
const role = document.querySelector('#role-filter');
const source = document.querySelector('#source-filter');
const copy = document.querySelector('#copy-list');
const count = document.querySelector('#shown');
const feedback = document.querySelector('#feedback');
const manual = document.querySelector('#manual-copy');
const rows = Array.from(document.querySelectorAll('tbody tr'));
function update() {
  const matches = rows.filter(row => {
    row.hidden = (role.value && !row.dataset.roles.split(' ').includes(role.value)) ||
                 (source.value && row.dataset.source !== source.value);
    return !row.hidden;
  });
  count.textContent = matches.length.toLocaleString('fa-IR') + ' آگهی در فهرست';
  copy.disabled = !matches.some(row => row.querySelector('a'));
  manual.hidden = true;
  feedback.textContent = '';
}
copy.addEventListener('click', async () => {
  const lines = rows.filter(row => !row.hidden && row.querySelector('a')).map(row =>
    row.querySelector('.title').textContent + ' | ' + row.querySelector('.company bdi').textContent +
    '\n' + row.querySelector('a').href);
  const digest = document.title + '\n\n' + lines.join('\n\n');
  try {
    await navigator.clipboard.writeText(digest);
    feedback.textContent = 'فهرست و لینک آگهی‌ها کپی شد.';
  } catch {
    manual.hidden = false;
    manual.value = digest;
    manual.select();
    feedback.textContent = 'متن انتخاب‌شده را کپی کنید.';
  }
});
role.addEventListener('change', update);
source.addEventListener('change', update);
controls.hidden = false;
update();
</script>"""


def _date_text(value: str) -> str:
    if not value:
        return "اعلام نشده"
    try:
        if len(value) == 10:
            stamp = date.fromisoformat(value)
        else:
            moment = datetime.fromisoformat(value)
            if moment.tzinfo:
                moment = moment.astimezone(_TEHRAN)
            stamp = moment.date()
        if stamp.year >= 1900:
            return stamp.isoformat().replace("-", "/").translate(_DIGITS) + " میلادی"
    except ValueError:
        pass
    return value


def _listing_link(url: str, source: str) -> str:
    domain = SOURCE_DOMAINS.get(source)
    if not domain or not url or "\\" in url or any(c.isspace() or ord(c) < 32 for c in url):
        return "لینک در دسترس نیست"
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        valid = (
            parsed.scheme in {"http", "https"} and parsed.username is None and parsed.password is None
            and (host == domain or host.endswith("." + domain)) and parsed.port in {None, 80, 443}
        )
    except ValueError:
        valid = False
    if not valid:
        return "لینک در دسترس نیست"
    return f'<a href="{escape(url, quote=True)}" rel="noreferrer">مشاهده آگهی</a>'


def _listing_row(row: dict) -> str:
    source = row["source"]
    name = escape(SOURCE_NAMES.get(source, source))
    title = escape(row["title"])
    roles = "، ".join(escape(ROLE_NAMES.get(k, k)) for k in row["roles"])
    company = escape(row.get("company") or "اعلام نشده")
    location = escape(row.get("location") or "اعلام نشده")
    published = escape(_date_text(row.get("posted_at") or ""))
    link = _listing_link(row["url"], source)
    return f"""<tr data-roles="{escape(" ".join(row["roles"]), quote=True)}" data-source="{escape(source, quote=True)}">
      <td><bdi class="title">{title}</bdi><span class="source">{name}</span></td>
      <td class="role"><span class="cell-label">حوزه</span>{roles}</td>
      <td class="company"><span class="cell-label">شرکت</span><bdi>{company}</bdi>
        <div class="sub"><span class="cell-label">موقعیت</span><bdi>{location}</bdi></div></td>
      <td class="date"><span class="cell-label">تاریخ درج</span><bdi>{published}</bdi></td>
      <td>{link}</td></tr>"""


def _options(keys, names: dict[str, str]) -> str:
    return "".join(f'<option value="{escape(k, quote=True)}">{escape(names.get(k, k))}</option>' for k in keys)


def render_report(day: str, rows: list[dict], sources: dict[str, str | None]) -> str:
    """Render listings first observed on day, with the latest check status of each source."""
    source_counts = Counter(row["source"] for row in rows)
    role_counts = Counter(role for row in rows for role in set(row["roles"]))
    status = []
    for key, problem in sources.items():
        name = escape(SOURCE_NAMES.get(key, key))
        total = str(source_counts[key]).translate(_DIGITS)
        if problem is None:
            status.append(f'<span>{name} بررسی شد. {total} آگهی ثبت‌شده</span>')
        else:
            status.append(f'<details class="error"><summary>دریافت از {name} ناموفق بود. {total} آگهی ثبت‌شده</summary>'
                          f'<p><bdi>{escape(problem)}</bdi></p></details>')

    if rows:
        totals = "".join(f'<span>{name} <b>{str(role_counts[k]).translate(_DIGITS)}</b></span>'
                         for k, name in ROLE_NAMES.items())
        note = '<p class="sub">آگهی چندحوزه‌ای در تعداد هر حوزه حساب می‌شود.</p>' if any(
            len(row["roles"]) > 1 for row in rows) else ""
        role_options = _options(ROLE_NAMES, ROLE_NAMES)
        source_options = _options(dict.fromkeys([*sources, *source_counts]), SOURCE_NAMES)
        body = f"""<div class="breakdown">{totals}</div>{note}
          <div class="controls" hidden>
            <label>حوزه<select id="role-filter"><option value="">همهٔ حوزه‌ها</option>{role_options}</select></label>
            <label>منبع<select id="source-filter"><option value="">همهٔ منابع</option>{source_options}</select></label>
            <button id="copy-list" type="button">کپی فهرست و لینک‌ها</button>
            <span id="shown" class="sub" role="status"></span>
            <span id="feedback" role="status"></span>
            <textarea id="manual-copy" rows="5" readonly aria-label="متن فهرست برای کپی دستی" hidden></textarea>
          </div><table aria-labelledby="list-title"><thead><tr>
          <th scope="col">عنوان و منبع</th><th scope="col">حوزه</th>
          <th scope="col">شرکت و موقعیت</th><th scope="col">تاریخ درج در منبع</th>
          <th scope="col">لینک اصلی</th></tr></thead><tbody>"""
        body += "".join(_listing_row(row) for row in rows) + "</tbody></table>" + _FILTER_SCRIPT
    elif sources and all(problem is not None for problem in sources.values()):
        body = '<p class="empty">دریافت آگهی‌ها ناموفق بود. نتیجهٔ این روز هنوز مشخص نیست.</p>'
    elif any(problem is not None for problem in sources.values()):
        body = '<p class="empty">در منابعی که بررسی شدند، آگهی تازه‌ای پیدا نشد.</p>'
    else:
        body = '<p class="empty">برای این تاریخ آگهی تازه‌ای در حوزه‌های انتخاب‌شده پیدا نشد.</p>'

    display_day = escape(_date_text(day))
    count = str(len(rows)).translate(_DIGITS)
    return f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>فرصت‌های شغلی فلووین | {display_day}</title><style>{_STYLE}</style></head>
<body><main><header><h1>فرصت‌های شغلی فلووین</h1>
<p class="metadata">تاریخ اولین مشاهده <time datetime="{escape(day, quote=True)}"><bdi>{display_day}</bdi></time></p>
</header><div class="status" aria-label="وضعیت منابع">{''.join(status)}</div>
<h2 id="list-title">آگهی‌های تازه‌یافته ({count})</h2>
{body}</main></body></html>"""
