"""P-2 router: shadow latency prediction + calibration stats."""
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..auth import get_principal, Principal
from ..db import get_db
from ..models import LatencyPrediction, LatencyObservation, ExecutionProfile
from ..domain.latency import LatencyPredictor

router = APIRouter()

class PredictIn(BaseModel):
    destination: str
    symbol: str | None = None
    order_size: Decimal | None = None
    recent_volatility: float = 0.0
    permitted_threshold_ms: float | None = None

class ObserveIn(BaseModel):
    destination: str
    symbol: str | None = None
    order_size: Decimal | None = None
    latency_ms: int
    slippage_bps: Decimal | None = None
    prediction_id: str | None = None

@router.post("/latency/predict")
def predict(body: PredictIn,
            p: Annotated[Principal, Depends(get_principal)],
            db: Session = Depends(get_db)):
    pred = LatencyPredictor(db, p.tenant_id).predict(
        destination=body.destination, symbol=body.symbol,
        order_size=body.order_size, recent_volatility=body.recent_volatility,
        permitted_threshold_ms=body.permitted_threshold_ms,
    )
    db.commit()
    return {
        "prediction_id": pred.id,
        "predicted_latency_ms": str(pred.predicted_latency_ms),
        "predicted_lower_ms": str(pred.predicted_lower_ms),
        "predicted_upper_ms": str(pred.predicted_upper_ms),
        "predicted_slippage_bps": str(pred.predicted_slippage_bps),
        "throttle_applied": pred.throttle_applied,
        "model_version": pred.model_version,
    }

@router.post("/latency/observe")
def observe(body: ObserveIn,
            p: Annotated[Principal, Depends(get_principal)],
            db: Session = Depends(get_db)):
    pred = None
    if body.prediction_id:
        pred = db.query(LatencyPrediction).filter(LatencyPrediction.id == body.prediction_id,
                                                   LatencyPrediction.tenant_id == p.tenant_id).first()
        if not pred: raise HTTPException(404, "Prediction not found")
    obs = LatencyPredictor(db, p.tenant_id).observe(
        destination=body.destination, symbol=body.symbol,
        order_size=body.order_size, actual_latency_ms=body.latency_ms,
        actual_slippage_bps=body.slippage_bps, prediction=pred,
    )
    db.commit()
    return {
        "observation_id": obs.id,
        "prediction_id": pred.id if pred else None,
        "actual_latency_ms": obs.latency_ms,
        "actual_slippage_bps": str(obs.slippage_bps) if obs.slippage_bps else None,
        "residual_latency": str(pred.residual_latency) if pred and pred.residual_latency else None,
        "residual_slippage": str(pred.residual_slippage) if pred and pred.residual_slippage else None,
    }

@router.get("/latency/profiles/{destination}")
def get_profile(destination: str, p: Annotated[Principal, Depends(get_principal)],
               db: Session = Depends(get_db), symbol: str | None = None):
    prof = LatencyPredictor(db, p.tenant_id).get_profile(destination, symbol)
    if not prof: raise HTTPException(404, "Profile not found")
    return {
        "destination": prof.destination, "symbol": prof.symbol,
        "total_observations": prof.total_observations,
        "latency_mean_ms": str(prof.latency_mean_ms),
        "latency_std_ms": str(prof.latency_std_ms),
        "latency_p50_ms": str(prof.latency_p50_ms),
        "latency_p95_ms": str(prof.latency_p95_ms),
        "latency_p99_ms": str(prof.latency_p99_ms),
        "slippage_mean_bps": str(prof.slippage_mean_bps),
        "slippage_std_bps": str(prof.slippage_std_bps),
        "updated_at": prof.updated_at.isoformat(),
    }

@router.get("/latency/calibration")
def calibration_stats(p: Annotated[Principal, Depends(get_principal)],
                      db: Session = Depends(get_db),
                      destination: str = "simulated", symbol: str | None = None):
    return LatencyPredictor(db, p.tenant_id).calibration_stats(destination, symbol)
