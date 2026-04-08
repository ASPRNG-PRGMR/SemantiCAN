class FeatureExtractor:
    def __init__(self):
        self.prev_velocity = None
        self.prev_time = None

    def extract(self, timestamp, message):
        features = {}

        # Safe fallback if velocity is absent
        velocity = message.get("velocity", self.prev_velocity or 0.0)

        if self.prev_velocity is not None and self.prev_time is not None:
            dt = timestamp - self.prev_time
            if dt > 0:
                dv = velocity - self.prev_velocity
                features["derived_acceleration"] = dv / dt
            else:
                features["derived_acceleration"] = 0.0
        else:
            features["derived_acceleration"] = 0.0

        self.prev_velocity = velocity
        self.prev_time = timestamp

        return features
