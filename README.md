# Responsible Web Crawler

A bounded Python crawler that makes its safety policy visible: it checks `robots.txt`, stays on the starting origin, identifies itself, waits between requests, rejects non-HTML responses, caps response size, and stops at explicit page and depth limits. Each record also includes generic article metadata and a deterministic content fingerprint.

The project uses only the Python standard library at runtime. It is a clean-room portfolio implementation; no client scraper, downloaded third-party scraper, private data, or prior Git history is included.

## What it demonstrates

- Robots Exclusion Protocol evaluation before page requests
- Same-origin URL normalization and redirect blocking
- Breadth-first crawling with deterministic page/depth limits
- Per-origin request pacing and an explicit user agent
- Bounded response reads and content-type checks
- Structured JSON Lines output suitable for later indexing
- Generic extraction of canonical URL, description, author, publication time, and language
- SHA-256 content fingerprints for deterministic downstream deduplication
- Offline HTTP-server tests for robots rules, loops, external links, and private paths

## Run it

Python 3.11 or newer is required.

```bash
python -m pip install -e .
responsible-crawler \
  --start-url https://docs.example.org/ \
  --output crawl-output.jsonl \
  --max-pages 25 \
  --max-depth 2 \
  --delay-seconds 1.0
```

Use a URL you own or are authorized to crawl. The command writes one JSON object per fetched HTML page, followed by a summary object.

Versioned GitHub Releases provide a wheel, source distribution, and SHA-256 checksums. Download a wheel from the [Releases page](https://github.com/MeherwerAli/responsible-web-crawler/releases), then install it with `python -m pip install ./responsible_web_crawler-<version>-py3-none-any.whl`.

```json
{
  "url": "https://docs.example.org/guide",
  "status": 200,
  "depth": 1,
  "title": "Guide",
  "description": "A compact introduction",
  "author": "Example Author",
  "published_at": "2026-08-14T08:00:00Z",
  "language": "en",
  "canonical_url": "https://docs.example.org/guide",
  "content_sha256": "...",
  "headings": ["Getting started"],
  "text": "...",
  "links": ["https://docs.example.org/reference"]
}
```

## Safety boundaries

The crawler intentionally does not provide:

- authenticated-session crawling;
- CAPTCHA bypass, proxy rotation, or identity evasion;
- cross-origin crawling;
- JavaScript execution or browser automation;
- social-network or search-engine harvesting presets;
- unbounded concurrency;
- automatic retries that could amplify load.

If `robots.txt` cannot be retrieved because of a network or server error, the crawler fails closed for that origin. A missing `robots.txt` (`404`) permits crawling; `401` and `403` disallow it. These choices are conservative implementation policy, not legal advice or proof that a crawl is permitted.

## Verify it

```bash
PYTHONPATH=src python -m unittest discover --start-directory tests --verbose
python -m pip wheel --no-deps --wheel-dir dist .
```

The tests use a local in-process HTTP server and make no internet requests.

## Design notes

- The queue is breadth-first so the depth limit has predictable behavior.
- Query strings are preserved because removing them can change resource identity; URL fragments are removed because they are not sent to the server.
- Redirects are accepted only when the final request remains on the exact starting origin.
- Page text is normalized for deterministic JSON output; scripts, styles, templates, and `noscript` content are excluded.
- Article metadata uses standard HTML, Open Graph, and schema-style meta fields; it does not contain source-specific selectors or publisher adapters.
- Results include skipped URLs and errors in the summary so a partial crawl cannot be mistaken for full coverage.

The robots behavior follows [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309), using Python's [`urllib.robotparser`](https://docs.python.org/3/library/urllib.robotparser.html) parser after controlled retrieval.

## License

[MIT](LICENSE)
