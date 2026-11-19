#!/usr/bin/env python3
"""Fetch the weekly economic calendar from the public REST API to a CSV
compatible with NewsConfig.events_csv.

Example:
    python scripts/fetch_calendar.py --out data/calendar.csv
Then point news.events_csv to that file (or run it periodically to refresh).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quant_founds.providers.calendar import FF_CALENDAR_URL, fetch_to_csv


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch weekly economic calendar to CSV")
    ap.add_argument("--out", default="data/calendar.csv")
    ap.add_argument("--url", default=FF_CALENDAR_URL)
    args = ap.parse_args()
    n = fetch_to_csv(args.out, url=args.url)
    print(f"saved {n} events -> {args.out}")


if __name__ == "__main__":
    main()
