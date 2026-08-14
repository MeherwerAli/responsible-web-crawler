from __future__ import annotations

import unittest

from responsible_web_crawler.parser import normalize_url, parse_document, same_origin


class ParserTest(unittest.TestCase):
    def test_extracts_visible_content_and_normalizes_links(self) -> None:
        document = parse_document(
            """
            <html lang="en-GB">
              <head>
                <title> Example   Guide </title>
                <meta property="og:title" content="Metadata Guide">
                <meta name="description" content="A compact test article">
                <meta name="author" content="Example Author">
                <meta property="article:published_time" content="2026-08-14T08:00:00Z">
                <link rel="canonical" href="/guide">
                <style>hidden</style>
              </head>
              <body>
                <h1>Getting <em>started</em></h1>
                <p>Visible text</p>
                <script>secret script text</script>
                <a href="/about#team">About</a>
                <a href="mailto:test@example.org">Email</a>
                <a href="https://other.example/path">External</a>
              </body>
            </html>
            """,
            "https://docs.example.org/start/",
        )

        self.assertEqual("Metadata Guide", document.title)
        self.assertEqual("A compact test article", document.description)
        self.assertEqual("Example Author", document.author)
        self.assertEqual("2026-08-14T08:00:00Z", document.published_at)
        self.assertEqual("en-GB", document.language)
        self.assertEqual("https://docs.example.org/guide", document.canonical_url)
        self.assertEqual(["Getting started"], document.headings)
        self.assertIn("Visible text", document.text)
        self.assertNotIn("secret script text", document.text)
        self.assertEqual(
            [
                "https://docs.example.org/about",
                "https://other.example/path",
            ],
            document.links,
        )

    def test_rejects_credentials_and_non_http_schemes(self) -> None:
        self.assertIsNone(normalize_url("mailto:test@example.org", "https://example.org"))
        self.assertIsNone(normalize_url("https://user:password@example.org", "https://example.org"))
        self.assertIsNone(normalize_url("https://example.org:not-a-port/", "https://example.org"))

    def test_compares_effective_ports_when_matching_origins(self) -> None:
        self.assertTrue(same_origin("https://example.org/a", "https://example.org:443/b"))
        self.assertFalse(same_origin("https://example.org", "http://example.org"))
        self.assertFalse(same_origin("https://example.org", "https://example.org:8443"))


if __name__ == "__main__":
    unittest.main()
