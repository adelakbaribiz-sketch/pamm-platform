"""
P-2: Shadow Latency & Slippage Prediction.

Maintains per-destination execution profiles (mean/std/percentiles for both
latency and slippage), and a lightweight ONLINE linear model:
  predicted_latency_ms = w0 + w1*log(1+order_size) + w2*recent_volatility
  predicted_slippage_bps = u0 + u1*order_size

Weights are kept in memory (tenant_id, destination, model_version) and updated
incrementally via stochastic gradient descent (analytical closed-form for
linear regression with one feature is also supported, but the SGD path lets
us add features later without changing the API).

The model is intentionally simple — P-2's purpose is to be a *measurable
engineering artifact* whose calibration we can persist and audit. We do NOT
claim novelty or that it beats any specific broker latency; we measure and
record both predicted and actual values so calibration can be verified.

Throttling:
  If predicted_latency_ms > permitted_threshold, the caller can choose to
  queue/throttle the destination. The `throttle_applied` flag is recorded
  on the prediction so we can later measure how often throttling fired.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime, timezone
from collections import defaultdict
from sqlalchemy.orm import Session
from ..models import (ExecutionProfile, LatencyObservation, LatencyPrediction)
import numpy as np

CENT4 = Decimal("0.0001")

def q4(x) -> Decimal:
    return Decimal(x).quantize(CENT4)

@dataclass
class ModelWeights:
    """Per-(tenant, destination) weights for the linear model.
    weights[0] = intercept, weights[1] = log(1+size) coef, weights[2] = volatility coef."""
    latency: list[float] = field(default_factory=lambda: [50.0, 5.0, 0.5])
    slippage: list[float] = field(default_factory=lambda: [1.0, 0.5, 0.0])
    n_updates: int = 0
    learning_rate: float = 0.01

class LatencyPredictor:
    """Online linear predictor with persistent observations and calibration tracking."""
    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        # In-memory weights cache: (destination, symbol) -> ModelWeights
        # For M3 we keep a single shared cache per process; production would use Redis.
        self._weights: dict[tuple[str, str | None], ModelWeights] = {}

    def _get_weights(self, destination: str, symbol: str | None) -> ModelWeights:
        key = (destination, symbol)
        if key not in self._weights:
            self._weights[key] = ModelWeights()
        return self._weights[key]

    def features(self, order_size: Decimal | None, recent_volatility: float = 0.0) -> list[float]:
        size = float(order_size) if order_size is not None else 0.0
        return [1.0, math.log1p(max(size, 0.0)), max(recent_volatility, 0.0)]

    def predict(self, destination: str, symbol: str | None,
                order_size: Decimal | None, recent_volatility: float = 0.0,
                permitted_threshold_ms: float | None = None) -> LatencyPrediction:
        """Produce a prediction. Persist it as a 'pending' prediction (no actual yet)."""
        w = self._get_weights(destination, symbol)
        feats = self.features(order_size, recent_volatility)
        feats_arr = np.array(feats)
        pred_lat = float(np.dot(w.latency, feats_arr))
        pred_slip = float(np.dot(w.slippage, feats_arr))

        # Uncertainty interval: assume residual std ~ 0.3 * mean + small floor
        sigma = max(0.1 * pred_lat, 2.0)
        lower = q4(Decimal(str(max(pred_lat - 1.96 * sigma, 0.0))))
        upper = q4(Decimal(str(pred_lat + 1.96 * sigma)))

        throttle = (permitted_threshold_ms is not None and
                    pred_lat > permitted_threshold_ms)

        # Feature snapshot for reproducibility
        feat_snapshot = {
            "order_size": str(order_size) if order_size is not None else None,
            "recent_volatility": recent_volatility,
            "raw_features": feats,
        }

        p = LatencyPrediction(
            tenant_id=self.tenant_id,
            destination=destination,
            symbol=symbol,
            order_size=order_size,
            features=feat_snapshot,
            predicted_latency_ms=q4(Decimal(str(pred_lat))),
            predicted_lower_ms=lower,
            predicted_upper_ms=upper,
            predicted_slippage_bps=q4(Decimal(str(pred_slip))),
            model_version="v1-linear",
            throttle_applied=throttle,
        )
        self.db.add(p); self.db.flush()
        return p

    def observe(self, destination: str, symbol: str | None,
                order_size: Decimal | None, actual_latency_ms: int,
                actual_slippage_bps: Decimal | None,
                prediction: LatencyPrediction | None = None) -> LatencyObservation:
        """Record an observation; if a prediction was made earlier, close the loop
        by computing residuals and updating the model weights via SGD."""
        obs = LatencyObservation(
            tenant_id=self.tenant_id, destination=destination, symbol=symbol,
            order_size=order_size, latency_ms=actual_latency_ms,
            slippage_bps=actual_slippage_bps,
            prediction_id=prediction.id if prediction else None,
        )
        self.db.add(obs); self.db.flush()

        if prediction is not None:
            feats = prediction.features.get("raw_features", [1.0, 0.0, 0.0]) \
                    if prediction.features else [1.0, 0.0, 0.0]
            w = self._get_weights(destination, symbol)
            self._sgd_update(w.latency, feats, float(actual_latency_ms),
                              float(prediction.predicted_latency_ms))
            if actual_slippage_bps is not None:
                self._sgd_update(w.slippage, feats, float(actual_slippage_bps),
                                  float(prediction.predicted_slippage_bps or 0))
            w.n_updates += 1
            # Close the prediction loop
            prediction.actual_latency_ms = actual_latency_ms
            prediction.actual_slippage_bps = actual_slippage_bps
            prediction.residual_latency = q4(Decimal(str(actual_latency_ms)) - prediction.predicted_latency_ms)
            if actual_slippage_bps is not None:
                prediction.residual_slippage = q4(actual_slippage_bps - (prediction.predicted_slippage_bps or Decimal("0")))
            prediction.observed_at = datetime.now(timezone.utc)
            self.db.flush()

        # Update execution profile aggregates
        self._update_profile(destination, symbol, actual_latency_ms, actual_slippage_bps)
        return obs

    def _sgd_update(self, weights: list[float], features: list[float],
                    actual: float, predicted: float, lr: float | None = None):
        """One SGD step on MSE loss. lr defaults to ModelWeights.learning_rate."""
        err = predicted - actual
        rate = lr if lr is not None else 0.01
        for i in range(len(weights)):
            weights[i] -= rate * err * features[i]

    def _update_profile(self, destination: str, symbol: str | None,
                          latency_ms: int, slippage_bps: Decimal | None):
        """Recalculate execution_profile aggregates from observations.
        Naive approach: re-aggregate from rows. For production use a streaming estimator.
        """
        q = self.db.query(LatencyObservation).filter(
            LatencyObservation.tenant_id == self.tenant_id,
            LatencyObservation.destination == destination,
        )
        if symbol is None:
            q = q.filter(LatencyObservation.symbol.is_(None))
        else:
            q = q.filter(LatencyObservation.symbol == symbol)
        obs = q.order_by(LatencyObservation.observed_at.desc()).limit(1000).all()
        if not obs: return
        lats = np.array([o.latency_ms for o in obs], dtype=float)
        slips = np.array([float(o.slippage_bps) for o in obs if o.slippage_bps is not None], dtype=float)

        prof = self.db.query(ExecutionProfile).filter(
            ExecutionProfile.tenant_id == self.tenant_id,
            ExecutionProfile.destination == destination,
        )
        if symbol is None:
            prof = prof.filter(ExecutionProfile.symbol.is_(None))
        else:
            prof = prof.filter(ExecutionProfile.symbol == symbol)
        prof = prof.first()
        if not prof:
            prof = ExecutionProfile(tenant_id=self.tenant_id, destination=destination,
                                     symbol=symbol)
            self.db.add(prof); self.db.flush()
        prof.total_observations = len(obs)
        prof.latency_mean_ms = q4(Decimal(str(np.mean(lats))))
        prof.latency_std_ms = q4(Decimal(str(np.std(lats)))) if len(lats) > 1 else Decimal("0")
        prof.latency_p50_ms = q4(Decimal(str(np.percentile(lats, 50))))
        prof.latency_p95_ms = q4(Decimal(str(np.percentile(lats, 95))))
        prof.latency_p99_ms = q4(Decimal(str(np.percentile(lats, 99)))) if len(lats) >= 100 else prof.latency_p95_ms
        if len(slips) > 0:
            prof.slippage_mean_bps = q4(Decimal(str(np.mean(slips))))
            prof.slippage_std_bps = q4(Decimal(str(np.std(slips)))) if len(slips) > 1 else Decimal("0")
        prof.updated_at = datetime.now(timezone.utc)
        self.db.flush()

    def get_profile(self, destination: str, symbol: str | None) -> ExecutionProfile | None:
        q = self.db.query(ExecutionProfile).filter(
            ExecutionProfile.tenant_id == self.tenant_id,
            ExecutionProfile.destination == destination,
        )
        if symbol is None:
            q = q.filter(ExecutionProfile.symbol.is_(None))
        else:
            q = q.filter(ExecutionProfile.symbol == symbol)
        return q.first()

    def calibration_stats(self, destination: str, symbol: str | None, limit: int = 100
                          ) -> dict:
        """Return prediction-vs-actual stats for calibration evaluation."""
        q = self.db.query(LatencyPrediction).filter(
            LatencyPrediction.tenant_id == self.tenant_id,
            LatencyPrediction.destination == destination,
            LatencyPrediction.actual_latency_ms.is_not(None),
        )
        if symbol is None:
            q = q.filter(LatencyPrediction.symbol.is_(None))
        else:
            q = q.filter(LatencyPrediction.symbol == symbol)
        preds = q.order_by(LatencyPrediction.created_at.desc()).limit(limit).all()
        if not preds:
            return {"n": 0, "mae_ms": None, "bias_ms": None,
                    "within_95pct_interval_pct": None}
        n = len(preds)
        mae = sum(abs(p.residual_latency or 0) for p in preds) / n
        bias = sum(float(p.residual_latency or 0) for p in preds) / n
        within = 0
        for p in preds:
            if (p.predicted_lower_ms is not None and p.predicted_upper_ms is not None):
                actual = Decimal(str(p.actual_latency_ms))
                if p.predicted_lower_ms <= actual <= p.predicted_upper_ms:
                    within += 1
        return {
            "n": n,
            "mae_ms": q4(Decimal(str(mae))),
            "bias_ms": q4(Decimal(str(bias))),
            "within_95pct_interval_pct": q4(Decimal(str(within / n * 100))),
        }
