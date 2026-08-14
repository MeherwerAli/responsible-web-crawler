from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .crawler import Crawler
from .models import CrawlConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crawl a bounded set of same-origin HTML pages while respecting robots.txt.",
    )
    parser.add_argument("--start-url", required=True)
    parser.add_argument("--output", type=Path, default=Path("crawl-output.jsonl"))
    parser.add_argument("--max-pages", type=int, default=25)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--max-response-bytes", type=int, default=1_000_000)
    parser.add_argument("--user-agent", default="ResponsibleWebCrawler/0.1")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        config = CrawlConfig(
            start_url=args.start_url,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            delay_seconds=args.delay_seconds,
            timeout_seconds=args.timeout_seconds,
            max_response_bytes=args.max_response_bytes,
            user_agent=args.user_agent,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

    report = Crawler(config).crawl()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output_file:
        for page in report.pages:
            output_file.write(json.dumps(page.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        output_file.write(json.dumps(report.summary(), ensure_ascii=False, sort_keys=True) + "\n")

    print(
        f"Fetched {len(report.pages)} page(s); "
        f"skipped {len(report.skipped)} URL(s); "
        f"recorded {len(report.errors)} error(s); "
        f"output={args.output}"
    )
    return 0 if report.pages else 2
