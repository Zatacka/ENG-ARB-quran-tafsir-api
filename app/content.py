from __future__ import annotations

import html
import re
import unicodedata
from html.parser import HTMLParser

_TAG_RE = re.compile(r"<[a-zA-Z][^>]*>")
_SVG_RE = re.compile(r"<\s*svg\b", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_NEWLINES_RE = re.compile(r"\n{3,}")
_ARABIC_MARKS_RE = re.compile(
    "[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)
_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "div", "dl", "dt",
    "dd", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2",
    "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol",
    "p", "pre", "section", "table", "tbody", "td", "tfoot", "th", "thead",
    "tr", "ul",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        value = html.unescape("".join(self.parts)).replace("\r\n", "\n")
        value = "\n".join(
            _WHITESPACE_RE.sub(" ", line).strip() for line in value.splitlines()
        )
        return _NEWLINES_RE.sub("\n\n", value).strip()


def contains_markup(value: str) -> bool:
    return bool(_TAG_RE.search(value or ""))


def content_format(value: str) -> str:
    if _SVG_RE.search(value or ""):
        return "svg"
    if contains_markup(value):
        return "html"
    return "plain_text"


def to_plain_text(value: str) -> str:
    if not value:
        return ""
    if not contains_markup(value):
        normalized = html.unescape(value).replace("\r\n", "\n")
        normalized = "\n".join(
            _WHITESPACE_RE.sub(" ", line).strip()
            for line in normalized.splitlines()
        )
        return _NEWLINES_RE.sub("\n\n", normalized).strip()

    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
        return parser.text()
    except Exception:
        return html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()


def has_meaningful_content(value: str, resource_type: str) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    if resource_type == "dependency_graph" or _SVG_RE.search(raw):
        return True
    return bool(to_plain_text(raw))


def normalize_arabic(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = _ARABIC_MARKS_RE.sub("", normalized)
    normalized = normalized.replace("ـ", "")
    normalized = normalized.translate(
        str.maketrans(
            {
                "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
                "ى": "ي", "ؤ": "و", "ئ": "ي", "ة": "ه",
            }
        )
    )
    return " ".join(normalized.casefold().split())
