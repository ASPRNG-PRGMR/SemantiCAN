class FeatureExtractor:
    """
    Per-ECU derived feature extraction.
    Keeps a separate velocity/time history per node_id so that
    ECU_002's velocity delta is never mixed with ECU_001's acceleration.
    """

    def __init__(self):
        self._prev: dict = {}   # node_id -> {"velocity": float, "time": float}

    def extract(self, timestamp: float, message: dict) -> dict:
        node_id  = message.get("node_id", "__global__")
        velocity = float(message.get("velocity", 0.0))
        features = {}

        prev = self._prev.get(node_id)
        if prev is not None:
            dt = timestamp - prev["time"]
            if dt > 0:
                features["derived_acceleration"] = (velocity - prev["velocity"]) / dt
            else:
                features["derived_acceleration"] = 0.0
        else:
            # First message for this ECU — no history yet, can't derive
            features["derived_acceleration"] = 0.0

        self._prev[node_id] = {"velocity": velocity, "time": timestamp}
        return features
