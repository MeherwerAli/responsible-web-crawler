from __future__ import annotations

import hashlib
import time
from collections import deque
from email.message import Message
from http.client import HTTPResponse
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPRedirectHandler,
    OpenerDirector,
    Request,
    build_opener,
)
from urllib.robotparser import RobotFileParser

from .models import CrawlConfig, CrawlReport, PageResult
from .parser import normalize_url, parse_document, same_origin


class _CrossOriginRedirectError(RuntimeError):
    pass


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    def __init__(self, origin_url: str) -> None:
        super().__init__()
        self._origin_url = origin_url

    def redirect_request(
        self,
        request: Request,
        file_pointer: HTTPResponse,
        code: int,
        message: str,
        headers: Message,
        new_url: str,
    ) -> Request | None:
        if not same_origin(self._origin_url, new_url):
            raise _CrossOriginRedirectError(f"blocked cross-origin redirect to {new_url}")
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


class _RobotsPolicy:
    def __init__(self, origin_url: str, user_agent: str, timeout_seconds: float) -> None:
        self._origin_url = origin_url
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._parser = RobotFileParser()
        self._loaded = False
        self.failure_reason: str | None = None

    def load(self, opener: OpenerDirector) -> None:
        robots_url = normalize_url("/robots.txt", self._origin_url)
        if robots_url is None:
            self._deny_all("could not construct robots.txt URL")
            return

        self._parser.set_url(robots_url)
        request = Request(
            robots_url,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "text/plain,*/*;q=0.1",
            },
        )
        try:
            with opener.open(request, timeout=self._timeout_seconds) as response:
                body = response.read(512_001)
                if len(body) > 512_000:
                    self._deny_all("robots.txt exceeded 512000 bytes")
                    return
                charset = response.headers.get_content_charset() or "utf-8"
                self._parser.parse(_decode_body(body, charset).splitlines())
                self._loaded = True
        except HTTPError as error:
            if error.code == 404:
                self._allow_all()
            elif error.code in {401, 403}:
                self._deny_all(f"robots.txt returned HTTP {error.code}")
            else:
                self._deny_all(f"robots.txt returned HTTP {error.code}")
        except (OSError, URLError, TimeoutError, _CrossOriginRedirectError) as error:
            self._deny_all(f"robots.txt retrieval failed: {type(error).__name__}")

    def can_fetch(self, url: str) -> bool:
        return self._loaded and self._parser.can_fetch(self._user_agent, url)

    def _allow_all(self) -> None:
        self._parser.parse(["User-agent: *", "Allow: /"])
        self._loaded = True

    def _deny_all(self, reason: str) -> None:
        self._parser.parse(["User-agent: *", "Disallow: /"])
        self._loaded = True
        self.failure_reason = reason


class Crawler:
    def __init__(self, config: CrawlConfig) -> None:
        self._config = config
        normalized_start = normalize_url(config.start_url, config.start_url)
        if normalized_start is None:
            raise ValueError("start_url could not be normalized")
        self._start_url = normalized_start
        self._opener = build_opener(_SameOriginRedirectHandler(self._start_url))
        self._robots = _RobotsPolicy(
            self._start_url,
            config.user_agent,
            config.timeout_seconds,
        )
        self._last_request_started: float | None = None

    def crawl(self) -> CrawlReport:
        report = CrawlReport(start_url=self._start_url)
        self._robots.load(self._opener)
        self._last_request_started = time.monotonic()

        queue: deque[tuple[str, int]] = deque([(self._start_url, 0)])
        seen: set[str] = set()

        while queue and len(report.pages) < self._config.max_pages:
            url, depth = queue.popleft()
            if url in seen:
                continue
            seen.add(url)

            if depth > self._config.max_depth:
                report.skipped.append({"url": url, "reason": "depth-limit"})
                continue
            if not self._robots.can_fetch(url):
                reason = self._robots.failure_reason or "robots-disallow"
                report.skipped.append({"url": url, "reason": reason})
                continue

            try:
                page = self._fetch_page(url, depth)
            except (HTTPError, URLError, OSError, TimeoutError, _CrossOriginRedirectError) as error:
                report.errors.append({
                    "url": url,
                    "error": _safe_error(error),
                })
                continue

            if isinstance(page, dict):
                report.skipped.append(page)
                continue

            report.pages.append(page)
            if depth == self._config.max_depth:
                continue
            for link in page.links:
                if same_origin(self._start_url, link) and link not in seen:
                    queue.append((link, depth + 1))

        return report

    def _fetch_page(self, url: str, depth: int) -> PageResult | dict[str, str]:
        self._pace_request()
        request = Request(
            url,
            headers={
                "User-Agent": self._config.user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9",
            },
        )
        with self._opener.open(request, timeout=self._config.timeout_seconds) as response:
            final_url = normalize_url(response.geturl(), url)
            if final_url is None or not same_origin(self._start_url, final_url):
                raise _CrossOriginRedirectError("response left the starting origin")

            content_type = response.headers.get_content_type().lower()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                return {"url": final_url, "reason": f"content-type:{content_type}"}

            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    declared_length = int(content_length)
                except ValueError:
                    declared_length = None
                if declared_length is not None and declared_length > self._config.max_response_bytes:
                    return {"url": final_url, "reason": "response-size-limit"}

            body = response.read(self._config.max_response_bytes + 1)
            if len(body) > self._config.max_response_bytes:
                return {"url": final_url, "reason": "response-size-limit"}

            charset = response.headers.get_content_charset() or "utf-8"
            document = parse_document(_decode_body(body, charset), final_url)
            same_origin_links = [
                link for link in document.links if same_origin(self._start_url, link)
            ]
            return PageResult(
                url=final_url,
                status=response.status,
                depth=depth,
                title=document.title,
                description=document.description,
                author=document.author,
                published_at=document.published_at,
                language=document.language,
                canonical_url=document.canonical_url,
                content_sha256=hashlib.sha256(document.text.encode("utf-8")).hexdigest(),
                headings=document.headings,
                text=document.text,
                links=same_origin_links,
            )

    def _pace_request(self) -> None:
        if self._last_request_started is not None:
            elapsed = time.monotonic() - self._last_request_started
            remaining = self._config.delay_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_started = time.monotonic()


def _safe_error(error: BaseException) -> str:
    if isinstance(error, HTTPError):
        return f"HTTP {error.code}"
    return type(error).__name__


def _decode_body(body: bytes, charset: str) -> str:
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")
