"""Online AI model (engine 10, blueprint 4.9): tiny self-contained learner.

A single-feature-map logistic regression trained incrementally from paper
trade outcomes (win=1, loss=0). It only ever ADJUSTS confidence: the risk
engine stays the final authority and any signal is submittable without it.
Persisted as JSON in the run directory - no external ML dependencies.
"""
from __future__ import annotations

import json
import math
import os

VERSION = "online-logit-v1"


class OnlineLogit:
    """Feature scores (0-100 engine scores) -> probability of a winning trade."""

    def __init__(self, lr: float = 0.05, l2: float = 1e-4,
                 version: str = VERSION):
        self.lr = lr
        self.l2 = l2
        self.version = version
        self.weights: dict[str, float] = {}
        self.bias = 0.0
        self.n_updates = 0
        self.n_wins = 0

    @property
    def ready(self) -> bool:
        return self.n_updates > 0

    def _vector(self, features: dict) -> dict[str, float]:
        out: dict[str, float] = {}
        for key, value in (features or {}).items():
            if value is None:
                continue
            try:
                x = float(value) / 100.0
            except (TypeError, ValueError):
                continue
            out[key] = max(-10.0, min(10.0, x))
        return out

    def probability(self, features: dict) -> float:
        vec = self._vector(features)
        z = self.bias + sum(self.weights.get(k, 0.0) * x for k, x in vec.items())
        z = max(-60.0, min(60.0, z))
        return 1.0 / (1.0 + math.exp(-z))

    def update(self, features: dict, outcome: float) -> float:
        """One SGD step on the logistic loss; 1.0 <= outcome <= 0."""
        vec = self._vector(features)
        p = self.probability(features)
        err = float(outcome) - p
        self.bias += self.lr * err
        for k, x in vec.items():
            w = self.weights.get(k, 0.0)
            self.weights[k] = w + self.lr * (err * x - self.l2 * w)
        self.n_updates += 1
        if outcome >= 0.5:
            self.n_wins += 1
        return p

    def classify(self, features: dict) -> tuple[str, float]:
        """AiIntelligence contract: (label, score 0-100)."""
        p = self.probability(features)
        if p >= 0.55:
            label = "bullish"
        elif p <= 0.45:
            label = "bearish"
        else:
            label = "neutral"
        return label, round(p * 100, 1)

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        row = {"version": self.version, "lr": self.lr, "l2": self.l2,
               "bias": self.bias, "n_updates": self.n_updates,
               "n_wins": self.n_wins, "weights": self.weights}
        with open(path, "w") as fh:
            json.dump(row, fh)

    @classmethod
    def load(cls, path: str) -> "OnlineLogit | None":
        try:
            with open(path) as fh:
                row = json.load(fh)
        except (OSError, ValueError):
            return None
        if row.get("version") != VERSION:
            return None
        obj = cls(lr=row.get("lr", 0.05), l2=row.get("l2", 1e-4),
                  version=row["version"])
        obj.bias = row.get("bias", 0.0)
        obj.n_updates = row.get("n_updates", 0)
        obj.n_wins = row.get("n_wins", 0)
        obj.weights = {k: float(v) for k, v in row.get("weights", {}).items()}
        return obj
