"""Search phrases and title matching shared by every job source."""

import re
import unicodedata


# Search engines on the two sites can index Persian and Latin titles separately.
SEARCH_TERMS: tuple[str, ...] = (
    "پرفورمنس", "performance", "بازاریابی عملکردی", "PPC", "تبلیغات کلیکی", "Google Ads", "گوگل ادز",
    "سئو", "SEO", "شبکه های اجتماعی", "سوشال", "social media", "اینستاگرام",
)

_PERSIAN_LETTERS = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک", "أ": "ا", "إ": "ا", "ؤ": "و",
    "ة": "ه", "ۀ": "ه", "ـ": "",
})


def _normalize(title: str) -> str:
    value = unicodedata.normalize("NFKC", title).casefold().translate(_PERSIAN_LETTERS)
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[_\W]+", " ", value).split())


_PERFORMANCE = re.compile(
    r"\b(?:پرفورمنس(?:مارکتینگ|مارکتر)?|بازاریاب(?:ی)? عملکرد(?:ی| محور)|"
    r"تبلیغات (?:عملکرد(?:ی| محور)|کلیکی)|"
    r"performance (?:based )?(?:marketing|marketer|advertising|media buyer)|"
    r"(?:digital |growth )?marketing performance|paid (?:media|search|social)|"
    r"pay per click|ppc|google ads|گوگل ادز|تبلیغات گوگل)\b"
)
_TECHNICAL_PERFORMANCE = re.compile(
    r"\b(?:engineer(?:ing)?|software|testing|test|tester|qa|hr|hardware|athletic|"
    r"منابع انسانی|نرم افزار|سخت افزار|تست|ارزیابی عملکرد)\b"
)
_MARKETING_CONTEXT = re.compile(
    r"\b(?:marketing|marketer|acquisition|campaigns?|ads|تبلیغات|بازاریابی|کمپین|مارکتینگ|مارکتر)\b"
)
_PERFORMANCE_WORD = re.compile(r"\b(?:performance|پرفورمنس)\b")
_SEO = re.compile(
    r"\b(?:seo|s e o|سئو(?:کار|کاری)?|search engine optimi[sz]ation|"
    r"بهینه ?سازی (?:وب ?سایت |سایت )?(?:برای )?موتور(?:های?| ها(?:ی)?)? جست ?(?:و ?)?جو)\b"
)
_SOCIAL = re.compile(
    r"\b(?:social ?media|smm|social (?:marketing|marketer|community manager)|"
    r"شبکه(?: ها(?:ی)?|های?| ی)? اجتماعی|رسانه(?: ها(?:ی)?|های?| ی)? اجتماعی|"
    r"سوشال(?: ?مدیا)?|instagram|اینستاگرام|ادمین پیج)\b"
)
_CHANNEL_OCCUPATION = re.compile(
    r"\b(?:فروش(?:نده)?|بازیگر|مدلینگ|sales|actor|model|"
    r"(?:متخصص|کارشناس|مهندس)(?: ارشد)? امنیت|security (?:engineer|specialist))\b"
)
_SOCIAL_DUTY = re.compile(
    r"\b(?:محتوا|(?:ادمین|مدیر|کارشناس(?: ارشد)?) (?:پیج|اینستاگرام|شبکه|سوشال)|"
    r"content|social media (?:manager|specialist|strategist|editor|coordinator))\b"
)


def match_roles(title: str) -> tuple[str, ...]:
    """Return all requested roles supported by the listing's own title."""
    # A sales title may list what the business sells in parentheses.
    if re.search(r"\b(?:فروش|sales)\b", _normalize(title)):
        title = re.sub(r"[(（]\s*خدمات\b[^)）]*[)）]", " ", title)
    text = _normalize(title)
    matches: list[str] = []
    marketing_context = _MARKETING_CONTEXT.search(text)
    if _PERFORMANCE.search(text) or (_PERFORMANCE_WORD.search(text) and marketing_context):
        if marketing_context or not _TECHNICAL_PERFORMANCE.search(text):
            matches.append("performance")
    elif text == "performance":
        matches.append("performance")
    if _SEO.search(text):
        matches.append("seo")
    # For sales or acting titles, Instagram can be just the channel used for that work.
    if _SOCIAL.search(text) and (not _CHANNEL_OCCUPATION.search(text) or _SOCIAL_DUTY.search(text)):
        matches.append("social")
    return tuple(matches)
