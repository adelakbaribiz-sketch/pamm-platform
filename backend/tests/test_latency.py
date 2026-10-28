"""P-2: Shadow latency prediction tests."""
from decimal import Decimal
from app.domain.latency import LatencyPredictor

def test_predict_returns_pending_with_intervals(db_session, seeded_tenant):
    p = LatencyPredictor(db_session, seeded_tenant["tenant"].id)
    pred = p.predict(destination="simulated", symbol="EURUSD",
                     order_size=Decimal("1.0"), recent_volatility=0.1)
    assert pred.predicted_latency_ms > 0
    assert pred.predicted_lower_ms is not None
    assert pred.predicted_upper_ms is not None
    assert pred.predicted_lower_ms < pred.predicted_upper_ms
    assert pred.actual_latency_ms is None  # pending
    assert pred.model_version == "v1-linear"

def test_observe_closes_loop(db_session, seeded_tenant):
    p = LatencyPredictor(db_session, seeded_tenant["tenant"].id)
    pred = p.predict(destination="simulated", symbol="EURUSD",
                     order_size=Decimal("1.0"))
    obs = p.observe(destination="simulated", symbol="EURUSD",
                    order_size=Decimal("1.0"), actual_latency_ms=80,
                    actual_slippage_bps=Decimal("2.5"), prediction=pred)
    assert obs.latency_ms == 80
    assert obs.prediction_id == pred.id
    # The prediction should now have actuals filled in
    assert pred.actual_latency_ms == 80
    assert pred.actual_slippage_bps == Decimal("2.5")
    # Residual = actual - predicted
    assert pred.residual_latency is not None
    assert pred.residual_slippage is not None

def test_execution_profile_updates(db_session, seeded_tenant):
    p = LatencyPredictor(db_session, seeded_tenant["tenant"].id)
    # Add several observations
    for i in range(5):
        p.observe(destination="simulated", symbol="EURUSD",
                  order_size=Decimal("1.0"), actual_latency_ms=50 + i*5,
                  actual_slippage_bps=Decimal("1.0"))
    prof = p.get_profile("simulated", "EURUSD")
    assert prof is not None
    assert prof.total_observations == 5
    assert prof.latency_mean_ms > 0
    assert prof.latency_p50_ms > 0
    assert prof.latency_p95_ms >= prof.latency_p50_ms

def test_calibration_stats(db_session, seeded_tenant):
    """Calibration: fraction of actuals inside the 95% prediction interval."""
    p = LatencyPredictor(db_session, seeded_tenant["tenant"].id)
    # Generate predictions + actuals
    for i in range(10):
        pred = p.predict(destination="simulated", symbol="EURUSD", order_size=Decimal("1.0"))
        p.observe(destination="simulated", symbol="EURUSD",
                  order_size=Decimal("1.0"), actual_latency_ms=60 + i,
                  actual_slippage_bps=Decimal("1.0"), prediction=pred)
    stats = p.calibration_stats("simulated", "EURUSD")
    assert stats["n"] == 10
    assert stats["mae_ms"] is not None
    assert stats["bias_ms"] is not None
    assert 0 <= float(stats["within_95pct_interval_pct"]) <= 100

def test_throttle_applied_on_high_prediction(db_session, seeded_tenant):
    """If predicted latency > threshold, throttle_applied is True."""
    p = LatencyPredictor(db_session, seeded_tenant["tenant"].id)
    # Force a large order_size to push prediction up via log(1+size) term
    pred = p.predict(destination="slow_broker", symbol=None,
                     order_size=Decimal("1000000"),
                     permitted_threshold_ms=10.0)
    # 50 + 5 * log(1+1000000) = 50 + 5*13.8 = ~119ms; well above 10ms threshold
    assert pred.throttle_applied is True

def test_no_throttle_below_threshold(db_session, seeded_tenant):
    p = LatencyPredictor(db_session, seeded_tenant["tenant"].id)
    pred = p.predict(destination="fast_broker", symbol=None,
                     order_size=Decimal("1.0"),
                     permitted_threshold_ms=1000.0)
    assert pred.throttle_applied is False

def test_sgd_updates_weights(db_session, seeded_tenant):
    """Repeated observations of actual > predicted should reduce predicted over time."""
    p = LatencyPredictor(db_session, seeded_tenant["tenant"].id)
    pred1 = p.predict(destination="t", symbol="s", order_size=Decimal("1.0"))
    initial_pred = pred1.predicted_latency_ms
    # Simulate an actual much higher than predicted, repeat
    p.observe(destination="t", symbol="s", order_size=Decimal("1.0"),
              actual_latency_ms=200, actual_slippage_bps=None, prediction=pred1)
    pred2 = p.predict(destination="t", symbol="s", order_size=Decimal("1.0"))
    # Updated weights should now produce a higher prediction (learning)
    assert pred2.predicted_latency_ms > initial_pred, "SGD did not update weights toward actual"
