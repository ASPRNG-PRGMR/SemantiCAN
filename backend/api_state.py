from collections import deque
from datetime import datetime, timedelta

# ---------------- Configuration ----------------
ROLLING_WINDOW_SECONDS = 60
RATE_BUCKET_SECONDS = 10
ANOMALY_THRESHOLD = 60.0

# ---------------- State ----------------
semantic_history: deque = deque()
violation_events: deque = deque()

ecu_last_seen: dict = {}
ecu_last_risk: dict = {}


# ---------------- Helpers ----------------
def _prune(q: deque, now: datetime):
    cutoff = now - timedelta(seconds=ROLLING_WINDOW_SECONDS)
    while q and q[0]["timestamp"] < cutoff:
        q.popleft()


# ---------------- Write APIs ----------------
def record_semantic_state(node_id: str, confidence: float):
    """Records latest semantic confidence for an ECU (0–100)."""
    now = datetime.utcnow()
    confidence = max(0.0, min(100.0, float(confidence)))

    ecu_last_seen[node_id] = now
    ecu_last_risk[node_id] = confidence

    semantic_history.append({
        "timestamp": now,
        "node_id": node_id,
        "confidence": confidence,
    })
    _prune(semantic_history, now)


def record_violation():
    now = datetime.utcnow()
    violation_events.append({"timestamp": now})
    _prune(violation_events, now)


# ---------------- Read APIs ----------------
def get_summary() -> dict:
    now = datetime.utcnow()
    _prune(semantic_history, now)
    _prune(violation_events, now)

    anomalous_ecus = sum(
        1 for risk in ecu_last_risk.values() if risk >= ANOMALY_THRESHOLD
    )

    last_anomaly = (
        semantic_history[-1]["timestamp"].isoformat() if semantic_history else None
    )

    return {
        "active_ecus": len(ecu_last_seen),
        "anomalous_ecus": anomalous_ecus,
        "last_anomaly": last_anomaly,
    }


def get_semantic_history() -> list:
    return [
        {
            "timestamp": e["timestamp"].isoformat(),
            "node_id": e["node_id"],
            "confidence": e["confidence"],
        }
        for e in semantic_history
    ]


def get_violation_rate() -> list:
    """Returns violation counts per fixed time bucket (SIEM-style)."""
    now = datetime.utcnow()
    buckets: dict = {}

    for v in violation_events:
        bucket = int((now - v["timestamp"]).total_seconds() // RATE_BUCKET_SECONDS)
        buckets[bucket] = buckets.get(bucket, 0) + 1

    result = []
    num_buckets = ROLLING_WINDOW_SECONDS // RATE_BUCKET_SECONDS
    for i in range(num_buckets):
        ts = now - timedelta(seconds=i * RATE_BUCKET_SECONDS)
        result.append({
            "time": ts.strftime("%H:%M:%S"),
            "count": buckets.get(i, 0),
        })

    return list(reversed(result))


def get_top_anomalous_ecus(limit: int = 3, threshold: float = ANOMALY_THRESHOLD) -> list:
    """Returns up to `limit` ECUs with highest risk ≥ threshold."""
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
            "node_id": node_id,
            "confidence": risk,
            "last_seen": ecu_last_seen[node_id].isoformat(),
        }
        for node_id, risk in candidates[:limit]
    ]
