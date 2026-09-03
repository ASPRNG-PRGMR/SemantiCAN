"""
In-memory rolling state store for the Flask API.
Keeps a 60-second sliding window of semantic confidence readings
and a SIEM-style violation-rate bucketing.
"""

from collections import deque
from datetime import datetime, timedelta

# ── Config ──────────────────────────────────────────────────────────────
ROLLING_WINDOW_SECONDS = 60
RATE_BUCKET_SECONDS    = 10
ANOMALY_THRESHOLD      = 70.0

# ── State ────────────────────────────────────────────────────────────────
semantic_history: deque = deque()
violation_events: deque = deque()

ecu_last_seen: dict = {}
ecu_last_risk: dict = {}


# ── Helpers ───────────────────────────────────────────────────────────────
def _prune(q: deque, now: datetime):
    cutoff = now - timedelta(seconds=ROLLING_WINDOW_SECONDS)
    while q and q[0]["timestamp"] < cutoff:
        q.popleft()


# ── Write APIs ────────────────────────────────────────────────────────────
def record_semantic_state(node_id: str, confidence: float):
    """Record latest semantic confidence for an ECU (0–100)."""
    now        = datetime.utcnow()
    confidence = max(0.0, min(100.0, float(confidence)))

    ecu_last_seen[node_id] = now
    ecu_last_risk[node_id] = confidence

    semantic_history.append({
        "timestamp":  now,
        "node_id":    node_id,
        "confidence": confidence,
    })
    _prune(semantic_history, now)


def record_violation():
    now = datetime.utcnow()
    violation_events.append({"timestamp": now})
    _prune(violation_events, now)


# ── Read APIs ─────────────────────────────────────────────────────────────
def get_summary() -> dict:
    now = datetime.utcnow()
    _prune(semantic_history, now)
    _prune(violation_events, now)

    anomalous_ecus = sum(
        1 for risk in ecu_last_risk.values() if risk >= ANOMALY_THRESHOLD
    )
    last_anomaly = (
        semantic_history[-1]["timestamp"].isoformat()
        if semantic_history else None
    )

    # vehicle_risk was previously only derivable by parsing the LSTM's free
    # text narrative (e.g. "Vehicle risk 85.7/100..."). Computed directly
    # here the same way backend/core/alerts.py does it internally, so the
    # dashboard hero can show a real number instead of regexing a sentence.
    try:
        from backend.core.alerts import get_active_alerts
        from backend.core.vehicle_risk import compute_vehicle_risk
        vehicle_risk = compute_vehicle_risk(get_active_alerts())
    except Exception:
        vehicle_risk = 0.0

    return {
        "active_ecus":    len(ecu_last_seen),
        "anomalous_ecus": anomalous_ecus,
        "last_anomaly":   last_anomaly,
        "vehicle_risk":   vehicle_risk,
    }


def get_semantic_history() -> list:
    return [
        {
            "timestamp":  e["timestamp"].isoformat(),
            "node_id":    e["node_id"],
            "confidence": e["confidence"],
        }
        for e in semantic_history
    ]


def get_violation_rate() -> list:
    """Violation counts in fixed time buckets (SIEM-style)."""
    now     = datetime.utcnow()
    buckets: dict = {}

    for v in violation_events:
        bucket = int(
            (now - v["timestamp"]).total_seconds() // RATE_BUCKET_SECONDS
        )
        buckets[bucket] = buckets.get(bucket, 0) + 1

    num_buckets = ROLLING_WINDOW_SECONDS // RATE_BUCKET_SECONDS
    result = []
    for i in range(num_buckets):
        ts = now - timedelta(seconds=i * RATE_BUCKET_SECONDS)
        result.append({
            "time":  ts.strftime("%H:%M:%S"),
            "count": buckets.get(i, 0),
        })

    return list(reversed(result))


def get_top_anomalous_ecus(limit: int = 3, threshold: float = ANOMALY_THRESHOLD) -> list:
    """Top `limit` ECUs with highest risk score above threshold."""
    candidates = [
        (node_id, risk)
        for node_id, risk in ecu_last_risk.items()
        if risk >= threshold
    ]

    if not candidates:
        return []

    candidates.sort(
        key=lambda item: (item[1], ecu_last_seen.get(item[0], datetime.min)),
        reverse=True,
    )

    return [
        {
            "node_id":   node_id,
            "confidence": risk,
            "last_seen": ecu_last_seen[node_id].isoformat(),
        }
        for node_id, risk in candidates[:limit]
    ]
