from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class CrawlConfig:
    start_url: str
    max_pages: int = 25
    max_depth: int = 2
    delay_seconds: float = 1.0
    timeout_seconds: float = 10.0
    max_response_bytes: int = 1_000_000
    user_agent: str = "ResponsibleWebCrawler/0.1"

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.start_url)
            hostname = parsed.hostname
            parsed.port
        except ValueError as error:
            raise ValueError("start_url must be an absolute HTTP or HTTPS URL") from error
        if parsed.scheme.lower() not in {"http", "https"} or not hostname:
            raise ValueError("start_url must be an absolute HTTP or HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError("start_url must not contain credentials")
        if self.max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if self.max_depth < 0:
            raise ValueError("max_depth must be at least 0")
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds must not be negative")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        if self.max_response_bytes < 1:
            raise ValueError("max_response_bytes must be at least 1")
        if not self.user_agent.strip():
            raise ValueError("user_agent must not be empty")


@dataclass(frozen=True)
class PageResult:
    url: str
    status: int
    depth: int
    title: str
    description: str
    author: str
    published_at: str
    language: str
    canonical_url: str
    content_sha256: str
    headings: list[str]
    text: str
    links: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CrawlReport:
    start_url: str
    pages: list[PageResult] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "type": "summary",
            "start_url": self.start_url,
            "pages_fetched": len(self.pages),
            "urls_skipped": len(self.skipped),
            "errors": len(self.errors),
            "skipped": self.skipped,
            "error_details": self.errors,
        }
