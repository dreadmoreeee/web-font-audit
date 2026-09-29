"""Audit the web fonts a page loads: files, @font-face rules, preloads,
font-display, formats and real subsetting savings."""

__version__ = "1.0.0"


def audit(urls, **options):
    """Audit one or more URLs and return a list of PageReport objects.

    Options: user_agent, viewport, timeout, delay, subset (bool).
    """
    from .analyze import Analyzer
    from .collect import DEFAULT_USER_AGENT, Collector, polite_sleep

    if isinstance(urls, str):
        urls = [urls]
    reports = []
    with Collector(user_agent=options.get("user_agent", DEFAULT_USER_AGENT),
                   viewport=options.get("viewport", (1366, 768)),
                   timeout=options.get("timeout", 30.0),
                   settle=options.get("settle", 1.0)) as collector:
        analyzer = Analyzer(decompress=collector.decompress, subset=options.get("subset", True))
        last = None
        for url in urls:
            last = polite_sleep(last, options.get("delay", 1.0))
            reports.append(analyzer.analyze(collector.collect(url)))
    return reports
