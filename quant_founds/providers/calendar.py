"""Live economic calendar via public REST API (blueprint 16, blueprint-section 19).

Fetches the weekly ForexFactory-style calendar JSON (no API key required),
maps it to EconomicEvent rows and can persist them as a CSV compatible with
NewsConfig.events_csv / NewsIntelligence.from_csv.

Network transport is injectable for tests - nothing here performs I/O unless
called with the default urllib transport.
"""
from __future__ import annotations

import csv
import json
import urllib.request
from datetime import datetime, timezone

from quant_founds.core.models import EconomicEvent

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

_IMPACT_MAP = {"high": "high", "medium": "medium", "low": "low"}


def urllib_get_json(url: str, headers: dict | None = None, timeout: float = 15.0):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "quant-founds/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_ff_date(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_calendar(items: list[dict]) -> list[EconomicEvent]:
    events = []
    for item in items:
        impact = _IMPACT_MAP.get(str(item.get("impact", "")).strip().lower(), "")
        if not impact:
            continue
        try:
            ts = _parse_ff_date(str(item.get("date", "")))
        except ValueError:
            continue
        events.append(EconomicEvent(
            timestamp=ts,
            currency=str(item.get("country", "")).strip().upper(),
            impact=impact,
            name=str(item.get("title", "")).strip(),
        ))
    events.sort(key=lambda e: e.timestamp)
    return events


def fetch_calendar(url: str = FF_CALENDAR_URL, transport=urllib_get_json,
                   timeout: float = 15.0) -> list[EconomicEvent]:
    return parse_calendar(transport(url))


def save_csv(events: list[EconomicEvent], path: str) -> int:
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "currency", "impact", "name"])
        for e in events:
            writer.writerow([
                e.timestamp.astimezone(timezone.utc).isoformat(),
                e.currency, e.impact, e.name,
            ])
    return len(events)


def fetch_to_csv(path: str, url: str = FF_CALENDAR_URL, transport=urllib_get_json) -> int:
    return save_csv(fetch_calendar(url, transport), path)
