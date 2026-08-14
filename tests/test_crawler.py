from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from responsible_web_crawler import CrawlConfig, Crawler


class _FixtureHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str]] = []

    def do_GET(self) -> None:
        self.requests.append((self.path, self.headers.get("User-Agent", "")))
        if self.path == "/robots.txt":
            self._send(200, "text/plain", "User-agent: *\nDisallow: /private\n")
        elif self.path == "/":
            self._send(
                200,
                "text/html",
                """
                <html lang="en"><head>
                <title>Home</title>
                <meta name="description" content="Fixture description">
                <meta name="author" content="Fixture Author">
                <meta property="article:published_time" content="2026-08-14T10:00:00Z">
                <link rel="canonical" href="/">
                </head><body>
                <h1>Fixture home</h1>
                <a href="/about">About</a>
                <a href="/bad-charset">Malformed charset</a>
                <a href="/bad-length">Malformed length</a>
                <a href="/large">Oversized page</a>
                <a href="/private">Private</a>
                <a href="/asset.pdf">PDF</a>
                <a href="/redirect">Redirect</a>
                <a href="https://outside.example/page">External</a>
                </body></html>
                """,
            )
        elif self.path == "/about":
            self._send(200, "text/html", '<title>About</title><a href="/">Home</a>')
        elif self.path == "/bad-charset":
            self._send_raw(
                200,
                "text/html; charset=not-a-real-codec",
                "<title>Bad charset</title>",
                None,
            )
        elif self.path == "/bad-length":
            self._send_with_length(200, "text/html", "<title>Bad length</title>", "invalid")
        elif self.path == "/large":
            self._send_with_length(200, "text/html", "", "1001")
        elif self.path == "/private":
            self._send(200, "text/html", "This must never be requested")
        elif self.path == "/asset.pdf":
            self._send(200, "application/pdf", "%PDF fixture")
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "https://outside.example/redirected")
            self.end_headers()
        else:
            self._send(404, "text/plain", "missing")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, content_type: str, body: str) -> None:
        encoded = body.encode("utf-8")
        self._send_with_length(status, content_type, body, str(len(encoded)))

    def _send_with_length(
        self,
        status: int,
        content_type: str,
        body: str,
        content_length: str,
    ) -> None:
        self._send_raw(
            status,
            f"{content_type}; charset=utf-8",
            body,
            content_length,
        )

    def _send_raw(
        self,
        status: int,
        content_type_header: str,
        body: str,
        content_length: str | None,
    ) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type_header)
        self.send_header("Content-Length", content_length or str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class CrawlerTest(unittest.TestCase):
    def setUp(self) -> None:
        _FixtureHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.start_url = f"http://{host}:{port}/"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_crawls_allowed_same_origin_html_and_reports_other_paths(self) -> None:
        report = Crawler(CrawlConfig(
            start_url=self.start_url,
            max_pages=10,
            max_depth=2,
            delay_seconds=0,
            timeout_seconds=2,
            max_response_bytes=1000,
            user_agent="PortfolioCrawlerTest/1.0",
        )).crawl()

        self.assertEqual(
            ["Home", "About", "Bad charset", "Bad length"],
            [page.title for page in report.pages],
        )
        self.assertEqual("Fixture description", report.pages[0].description)
        self.assertEqual("Fixture Author", report.pages[0].author)
        self.assertEqual("2026-08-14T10:00:00Z", report.pages[0].published_at)
        self.assertEqual("en", report.pages[0].language)
        self.assertEqual(self.start_url, report.pages[0].canonical_url)
        self.assertEqual(64, len(report.pages[0].content_sha256))
        self.assertEqual(
            [
                "/robots.txt",
                "/",
                "/about",
                "/asset.pdf",
                "/bad-charset",
                "/bad-length",
                "/large",
                "/redirect",
            ],
            [request_path for request_path, _user_agent in _FixtureHandler.requests],
        )
        self.assertNotIn("/private", [request_path for request_path, _ in _FixtureHandler.requests])
        self.assertTrue(all(user_agent == "PortfolioCrawlerTest/1.0" for _, user_agent in _FixtureHandler.requests))
        self.assertIn(
            {"url": self.start_url.removesuffix("/") + "/private", "reason": "robots-disallow"},
            report.skipped,
        )
        self.assertTrue(any(item["reason"] == "content-type:application/pdf" for item in report.skipped))
        self.assertTrue(any(item["reason"] == "response-size-limit" for item in report.skipped))
        self.assertEqual(1, len(report.errors))
        self.assertEqual("_CrossOriginRedirectError", report.errors[0]["error"])

    def test_fails_closed_when_robots_cannot_be_retrieved(self) -> None:
        unreachable_url = "http://127.0.0.1:1/"
        report = Crawler(CrawlConfig(
            start_url=unreachable_url,
            max_pages=1,
            delay_seconds=0,
            timeout_seconds=0.1,
        )).crawl()

        self.assertEqual([], report.pages)
        self.assertEqual(1, len(report.skipped))
        self.assertIn("robots.txt retrieval failed", report.skipped[0]["reason"])


if __name__ == "__main__":
    unittest.main()
