"""News Intelligence (engine 08) - economic events risk windows (blueprint 4.7).

Without a trusted external source this engine must never fabricate news:
it only evaluates events explicitly provided by config/CSV.
"""
from __future__ import annotations

from datetime import timedelta

from quant_founds.core.engine import AnalysisContext, BaseEngine
from quant_founds.core.enums import SourceMode
from quant_founds.core.models import EconomicEvent


class NewsIntelligence(BaseEngine):
    engine_id = "news"

    def __init__(self, events: list[EconomicEvent] | None = None,
                 block_minutes_before: int = 30,
                 block_minutes_after: int = 30,
                 block_impacts: list[str] | None = None,
                 currencies: list[str] | None = None):
        self.events = events or []
        self.before = timedelta(minutes=block_minutes_before)
        self.after = timedelta(minutes=block_minutes_after)
        self.impacts = set(block_impacts or ["high"])
        self.currencies = set(currencies or [])

    def analyze(self, ctx: AnalysisContext):
        now = ctx.last.timestamp
        matches: list[EconomicEvent] = []
        for ev in self.events:
            if self.impacts and ev.impact not in self.impacts:
                continue
            if self.currencies and ev.currency not in self.currencies:
                continue
            if now - self.before <= ev.timestamp <= now + self.after:
                matches.append(ev)

        blocked = bool(matches)
        details = [f"{e.currency}:{e.impact}@{e.timestamp.isoformat()} {e.name}" for e in matches]
        res = self.make_result(
            ctx,
            state="blocked" if blocked else ("clear" if self.events else "no_source"),
            score=0.0 if blocked else 100.0,
            confidence_label=("window_active" if blocked else
                              "no_trusted_source" if not self.events else "clear"),
            evidence=details[:5],
            data_quality=0.4 if not self.events else 1.0,
            source_mode=SourceMode.EXTERNAL if self.events else SourceMode.UNAVAILABLE,
            extras={"blocked": blocked, "events": details},
        )
        ctx.results[self.engine_id] = res
        return res

    @staticmethod
    def from_csv(path: str) -> list[EconomicEvent]:
        import csv
        from quant_founds.engines.data_engine import _parse_ts
        events = []
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                events.append(EconomicEvent(
                    timestamp=_parse_ts(row["timestamp"]),
                    currency=row.get("currency", ""),
                    impact=row.get("impact", "medium"),
                    name=row.get("name", ""),
                ))
        return events
