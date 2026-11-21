import argparse
from collections import Counter
from pathlib import Path
import sys

from .crawl import DEFAULT_MAX_PAGES, SOURCES, collect, tehran_day
from .store import save_digest


ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Collect marketing jobs for Felowin's daily digest.")
    parser.add_argument("--source", choices=tuple(SOURCES), action="append",
                        help="Fetch only this source (repeatable). Default: both.")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                        help="Maximum search result pages per term per source (default: %(default)s).")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args(argv)
    if args.max_pages < 1:
        parser.error("--max-pages must be at least 1")

    selected = {name: SOURCES[name] for name in args.source or SOURCES}
    day = tehran_day()
    report_path = args.reports_dir / f"{day}.html"
    result = collect(selected, args.max_pages)
    matched = Counter(job.source for job, _ in result.matches)
    for name, error in result.sources.items():
        if error is not None:
            print(f"{name}: {error}", file=sys.stderr, flush=True)
        print(f"{name}: {matched[name]} matching listings in {result.scanned[name]} results", flush=True)
    count = save_digest(args.data_dir / "jobs.sqlite3", report_path, day, result.matches, result.sources)
    print(f"{count} first seen on {day}\n{report_path.resolve()}", flush=True)
    return 1 if any(error is not None for error in result.sources.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
