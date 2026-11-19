import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quant_founds.engines.news_intel import NewsIntelligence
from quant_founds.providers.calendar import (
    parse_calendar,
    fetch_calendar,
    fetch_to_csv,
)


def _fake_transport(url):
    payload = [
        {"title": "Non-Farm Employment Change", "country": "USD",
         "date": "2026-11-06T08:30:00-05:00", "impact": "High",
         "forecast": "180K", "previous": "250K"},
        {"title": "ECB Press Conference", "country": "EUR",
         "date": "2026-11-06T07:45:00-05:00", "impact": "Medium"},
        {"title": "Consumer Confidence", "country": "EUR",
         "date": "2026-11-06T04:00:00-05:00", "impact": "Low"},
        {"title": "Bank Holiday", "country": "JPY",
         "date": "2026-11-06T00:00:00-05:00", "impact": "Holiday"},
        {"title": "Broken Row", "country": "",
         "date": "not-a-date", "impact": "High"},
    ]
    return payload



class TestCalendarProvider(unittest.TestCase):
    def test_parse_maps_impacts_and_skips_holiday_and_broken(self):
        events = parse_calendar(_fake_transport("http://x"))
        self.assertEqual(len(events), 3)
        self.assertEqual([e.impact for e in events], ["low", "medium", "high"])
        for e in events:
            self.assertEqual(e.timestamp.tzinfo, timezone.utc)
        self.assertEqual(events[-1].currency, "USD")
        self.assertEqual(events[-1].name, "Non-Farm Employment Change")

    def test_parse_sorts_by_time(self):
        events = parse_calendar(_fake_transport("http://x"))
        times = [e.timestamp for e in events]
        self.assertEqual(times, sorted(times))

    def test_offset_converted_to_utc(self):
        events = parse_calendar(_fake_transport("http://x"))
        high = [e for e in events if e.impact == "high"][0]
        self.assertEqual(high.timestamp, datetime(2026, 11, 6, 13, 30, tzinfo=timezone.utc))

    def test_fetch_calendar_uses_transport(self):
        events = fetch_calendar("http://x", transport=_fake_transport)
        self.assertEqual(len(events), 3)

    def test_roundtrip_csv_feeds_news_intelligence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "calendar.csv")
            n = fetch_to_csv(path, url="http://x", transport=_fake_transport)
            self.assertEqual(n, 3)
            events = NewsIntelligence.from_csv(path)
            self.assertEqual(len(events), 3)
            self.assertEqual(events[-1].impact, "high")

    def test_empty_payload(self):
        self.assertEqual(fetch_calendar("http://x", transport=lambda url: []), [])


if __name__ == "__main__":
    unittest.main()
