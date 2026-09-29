"""Command line interface."""

from __future__ import annotations

import argparse
import re
import sys

from . import __version__
from .analyze import FINDING_CODES, SEVERITIES, Analyzer, check_budgets
from .collect import DEFAULT_USER_AGENT, Collector, polite_sleep
from .report import to_json, to_markdown

EXIT_OK, EXIT_BUDGET, EXIT_ERROR = 0, 1, 2


def parse_size(text: str) -> int:
    """'150000', '150k', '150KB', '146KiB', '1.5MB' -> bytes (KB = 1000, KiB = 1024)."""
    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmM]?)(i?)[bB]?\s*", text)
    if not m:
        raise argparse.ArgumentTypeError(f"not a size: {text!r}")
    number, unit, binary = float(m.group(1)), m.group(2).lower(), m.group(3)
    base = 1024 if binary else 1000
    power = {"": 0, "k": 1, "m": 2}[unit]
    return int(number * base ** power)


def parse_fail_on(text: str) -> list[str]:
    allowed = set(FINDING_CODES) | set(SEVERITIES)
    items = [x.strip() for x in text.split(",") if x.strip()]
    bad = [x for x in items if x not in allowed]
    if bad:
        raise argparse.ArgumentTypeError(
            f"unknown --fail-on value(s): {', '.join(bad)}; use {', '.join(sorted(allowed))}")
    return items


def parse_viewport(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)x(\d+)", text.strip())
    if not m:
        raise argparse.ArgumentTypeError("viewport must look like 1366x768")
    return int(m.group(1)), int(m.group(2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="web-font-audit",
        description="Audit the web fonts a page loads, with headless Chromium and fontTools.")
    p.add_argument("urls", nargs="+", metavar="URL", help="page(s) to audit")
    p.add_argument("--format", choices=("markdown", "json"), default="markdown",
                   help="what to print on stdout (default: markdown)")
    p.add_argument("--md-out", metavar="FILE", help="also write the Markdown report to FILE")
    p.add_argument("--json-out", metavar="FILE", help="also write the JSON report to FILE")
    p.add_argument("--max-font-bytes", type=parse_size, metavar="SIZE",
                   help="budget: font bytes transferred per page (e.g. 150KB)")
    p.add_argument("--max-fonts", type=int, metavar="N", help="budget: font files per page")
    p.add_argument("--max-families", type=int, metavar="N", help="budget: font families used per page")
    p.add_argument("--fail-on", type=parse_fail_on, default=[], metavar="CODES",
                   help="comma list of finding codes or severities that fail the run, "
                        "e.g. font-display,legacy-format or warning")
    p.add_argument("--no-subset", action="store_true", help="skip the subsetting measurements")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between page loads (default 1)")
    p.add_argument("--timeout", type=float, default=30.0, help="page load timeout in seconds")
    p.add_argument("--viewport", type=parse_viewport, default=(1366, 768),
                   help="viewport used for 'above the fold' (default 1366x768)")
    p.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    p.add_argument("--version", action="version", version=f"web-font-audit {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    for url in args.urls:
        if not re.match(r"https?://", url):
            print(f"error: not an http(s) URL: {url}", file=sys.stderr)
            return EXIT_ERROR

    reports = []
    with Collector(user_agent=args.user_agent, viewport=args.viewport,
                   timeout=args.timeout) as collector:
        analyzer = Analyzer(decompress=collector.decompress, subset=not args.no_subset)
        last = None
        for url in args.urls:
            last = polite_sleep(last, args.delay)
            print(f"auditing {url}", file=sys.stderr)
            report = analyzer.analyze(collector.collect(url))
            report.budget_failures = check_budgets(
                report, args.max_font_bytes, args.max_fonts, args.max_families, args.fail_on)
            reports.append(report)
        brotli = collector.brotli

    budget_failed = any(r.budget_failures for r in reports)
    markdown = to_markdown(reports)
    json_text = to_json(reports, brotli=brotli, budget_failed=budget_failed)
    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as fh:
            fh.write(markdown)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(json_text + "\n")
    out = json_text + "\n" if args.format == "json" else markdown
    sys.stdout.buffer.write(out.encode("utf-8"))
    sys.stdout.flush()

    if any(r.error for r in reports):
        return EXIT_ERROR
    if budget_failed:
        print(f"budget exceeded on {sum(1 for r in reports if r.budget_failures)} page(s)",
              file=sys.stderr)
        return EXIT_BUDGET
    return EXIT_OK
