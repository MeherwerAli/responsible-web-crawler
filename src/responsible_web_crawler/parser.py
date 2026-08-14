from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    description: str
    author: str
    published_at: str
    language: str
    canonical_url: str
    headings: list[str]
    text: str
    links: list[str]


class _DocumentParser(HTMLParser):
    _hidden_tags = {"script", "style", "template", "noscript"}
    _heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_depth = 0
        self._in_title = False
        self._heading_tag: str | None = None
        self._title_parts: list[str] = []
        self._heading_parts: list[str] = []
        self._headings: list[str] = []
        self._text_parts: list[str] = []
        self._metadata: dict[str, str] = {}
        self._language = ""
        self._canonical_href = ""
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in self._hidden_tags:
            self._hidden_depth += 1
            return
        if self._hidden_depth:
            return
        attributes = {
            name.lower(): value.strip()
            for name, value in attrs
            if value is not None and value.strip()
        }
        if normalized_tag == "html" and not self._language:
            self._language = attributes.get("lang", "")
        if normalized_tag == "meta":
            metadata_key = (
                attributes.get("property")
                or attributes.get("name")
                or attributes.get("itemprop")
            )
            metadata_value = attributes.get("content")
            if metadata_key and metadata_value:
                self._metadata.setdefault(metadata_key.lower(), metadata_value)
        if normalized_tag == "link":
            relation = {item.lower() for item in attributes.get("rel", "").split()}
            if "canonical" in relation and not self._canonical_href:
                self._canonical_href = attributes.get("href", "")
        if normalized_tag == "time" and not self._metadata.get("datepublished"):
            timestamp = attributes.get("datetime")
            if timestamp:
                self._metadata["datepublished"] = timestamp
        if normalized_tag == "title":
            self._in_title = True
        if normalized_tag in self._heading_tags:
            self._heading_tag = normalized_tag
            self._heading_parts = []
        if normalized_tag == "a":
            href = next((value for name, value in attrs if name.lower() == "href"), None)
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in self._hidden_tags:
            self._hidden_depth = max(0, self._hidden_depth - 1)
            return
        if self._hidden_depth:
            return
        if normalized_tag == "title":
            self._in_title = False
        if self._heading_tag == normalized_tag:
            heading = _normalize_text(" ".join(self._heading_parts))
            if heading:
                self._headings.append(heading)
            self._heading_tag = None
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._hidden_depth:
            return
        normalized = _normalize_text(data)
        if not normalized:
            return
        if self._in_title:
            self._title_parts.append(normalized)
        if self._heading_tag:
            self._heading_parts.append(normalized)
        self._text_parts.append(normalized)

    def document(self, base_url: str) -> ParsedDocument:
        links = {
            normalized
            for raw_link in self.links
            if (normalized := normalize_url(raw_link, base_url)) is not None
        }
        canonical_url = normalize_url(self._canonical_href, base_url)
        return ParsedDocument(
            title=self._first_metadata("og:title", "twitter:title")
            or _normalize_text(" ".join(self._title_parts)),
            description=self._first_metadata(
                "description",
                "og:description",
                "twitter:description",
            ),
            author=self._first_metadata("author", "article:author"),
            published_at=self._first_metadata(
                "article:published_time",
                "datepublished",
                "date",
                "pubdate",
            ),
            language=self._language or self._first_metadata("og:locale"),
            canonical_url=canonical_url or base_url,
            headings=self._headings,
            text=_normalize_text(" ".join(self._text_parts)),
            links=sorted(links),
        )

    def _first_metadata(self, *keys: str) -> str:
        return next((self._metadata[key] for key in keys if self._metadata.get(key)), "")


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def normalize_url(candidate: str, base_url: str) -> str | None:
    try:
        absolute, _fragment = urldefrag(urljoin(base_url, candidate.strip()))
        parsed = urlsplit(absolute)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        return None
    if parsed.username or parsed.password:
        return None

    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def origin_key(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    default_port = 443 if scheme == "https" else 80
    return scheme, (parsed.hostname or "").lower(), parsed.port or default_port


def same_origin(left: str, right: str) -> bool:
    try:
        return origin_key(left) == origin_key(right)
    except ValueError:
        return False


def parse_document(html: str, base_url: str) -> ParsedDocument:
    parser = _DocumentParser()
    parser.feed(html)
    parser.close()
    return parser.document(base_url)
