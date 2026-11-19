"""AI Intelligence (engine 10) - optional, disabled by default (blueprint 4.9).

ML lives outside this trading loop in v1: it must be trained on external
data, versioned, evaluated out-of-sample, and only then registered. The
risk engine stays independent and may reject any model decision.
"""
from __future__ import annotations

from quant_founds.core.engine import AnalysisContext, BaseEngine
from quant_founds.core.enums import SourceMode


class AiIntelligence(BaseEngine):
    engine_id = "ai"

    def __init__(self, model=None, model_version: str = ""):
        self.model = model
        self.model_version = model_version

    def analyze(self, ctx: AnalysisContext):
        if self.model is None:
            res = self.make_result(
                ctx,
                state="disabled",
                score=None,
                confidence_label="unavailable",
                evidence=["no_registered_model"],
                data_quality=1.0,
                source_mode=SourceMode.UNAVAILABLE,
            )
            ctx.results[self.engine_id] = res
            return res
        features = self.features(ctx)
        label, score = self.model.classify(features)
        res = self.make_result(
            ctx,
            state=label,
            score=round(score, 1),
            confidence_label=f"model:{self.model_version}",
            evidence=[f"features={features}"],
            data_quality=0.8,
            source_mode=SourceMode.EXTERNAL,
        )
        ctx.results[self.engine_id] = res
        return res

    @staticmethod
    def features(ctx: AnalysisContext) -> dict:
        out: dict = {}
        for eid, res in ctx.results.items():
            out[eid] = getattr(res, "score", None)
        return out
