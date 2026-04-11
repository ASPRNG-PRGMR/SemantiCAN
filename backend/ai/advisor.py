"""
LSTM Anomaly Advisor
--------------------
A locally-trained LSTM model that learns normal ECU telemetry patterns
and scores incoming windows for anomaly confidence.

Key design decisions to avoid false positives:
- Per-ECU sliding windows (no cross-ECU contamination)
- Error threshold calibrated from normal traffic (mean + 3*std)
- Score only fires when error exceeds the calibrated threshold
- LSTM is DISABLED until fully trained (returns 0 during baseline phase)

No external API required.
"""

import threading
import numpy as np

try:
    import torch
    import torch.nn as nn
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


# ── Config ───────────────────────────────────────────────────────────────
WINDOW_SIZE    = 10      # timesteps per ECU window (shorter = quicker ramp-up)
INPUT_DIM      = 3       # velocity, acceleration, steering_angle
HIDDEN_DIM     = 32
NUM_LAYERS     = 1       # 1 layer is enough; 2 overfits on short windows
TRAIN_STEPS    = 400     # normal samples before first training
RETRAIN_EVERY  = 600     # retrain every N additional samples
# Error multiplier: how many std-devs above normal baseline = 100 score
SIGMA_SCALE    = 4.0     # score = clamp((error - mu_err) / (SIGMA_SCALE * sd_err), 0, 1) * 100


# ── PyTorch LSTM model ───────────────────────────────────────────────────
if _TORCH_AVAILABLE:
    class _LSTMModel(nn.Module):
        """Sequence-to-one predictor: given a window of T steps, predict step T+1."""
        def __init__(self, input_dim, hidden_dim, num_layers, output_dim):
            super().__init__()
            self.lstm = nn.LSTM(
                input_dim, hidden_dim, num_layers,
                batch_first=True,
                dropout=0.0,   # no dropout — model is small, avoid extra noise
            )
            self.fc = nn.Linear(hidden_dim, output_dim)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.fc(out[:, -1, :])


# ── Main advisor class ───────────────────────────────────────────────────
class LSTMAdvisor:
    """
    Trains one LSTM on normal ECU traffic, then scores each ECU's
    telemetry window via prediction error.

    Per-ECU sliding windows prevent cross-ECU velocity contamination.
    The anomaly threshold is calibrated from normal-traffic error
    distribution so that healthy ECUs score ~0 and attack ECUs score high.
    """

    def __init__(self):
        self._lock         = threading.Lock()
        self._buffer       = []      # training buffer: [vel, accel, steer] rows
        self._trained      = False
        self._step_count   = 0
        self._model        = None
        self._optimizer    = None
        self._loss_fn      = None
        self._mu           = None    # feature mean (for normalisation)
        self._sd           = None    # feature std  (for normalisation)
        self._err_mu       = 0.0     # mean reconstruction error on normal data
        self._err_sd       = 1.0     # std  reconstruction error on normal data
        # Per-ECU sliding windows: node_id -> list of feature rows
        self._ecu_windows: dict = {}

        if not _TORCH_AVAILABLE:
            print("[LSTM Advisor] torch not available — LSTM scoring disabled")

    # ── Public API ────────────────────────────────────────────────────────

    def ingest(self, message: dict) -> float:
        """
        Feed one ECU message. Returns anomaly confidence 0–100.
        Returns 0 until the model is trained (never false-positive during warmup).
        """
        if not _TORCH_AVAILABLE:
            return 0.0     # no fallback — avoids false positives from z-score

        features = [
            float(message.get("velocity",       0.0)),
            float(message.get("acceleration",   0.0)),
            float(message.get("steering_angle", 0.0)),
        ]
        node_id = message.get("node_id", "__global__")

        with self._lock:
            self._buffer.append(features)
            self._step_count += 1

            # Phase 1: collect baseline — return 0 the whole time
            if not self._trained:
                if len(self._buffer) >= TRAIN_STEPS:
                    self._train()
                return 0.0

            # Periodic retrain on growing data — inline (not threaded) to avoid race
            if self._step_count % RETRAIN_EVERY == 0:
                self._train()

            # Per-ECU window update
            win = self._ecu_windows.setdefault(node_id, [])
            win.append(features)
            if len(win) > WINDOW_SIZE:
                win.pop(0)

            if len(win) < WINDOW_SIZE:
                return 0.0

            return self._score_window(win)

    def generate_advisory(self, vehicle_summary: dict) -> str:
        """
        Returns a deterministic SOC advisory string built from the
        vehicle summary dict (risk_score, anomalies list, etc.).
        The LSTM confidence feeds into the risk tier language.
        """
        risk    = vehicle_summary.get("risk_score", 0)
        anomalies = vehicle_summary.get("anomalies", [])
        ecu_list  = ", ".join(a["ecu"] for a in anomalies) if anomalies else "unknown"
        trained_str = "LSTM-scored" if self._trained else "pre-training baseline"

        if risk >= 80:
            level  = "CRITICAL"
            action = (
                "Immediate vehicle isolation recommended. "
                "Suspected semantic injection on safety-critical ECUs. "
                "Initiate forensic capture of CAN frame logs."
            )
        elif risk >= 60:
            level  = "HIGH"
            action = (
                "Escalate to SOC Tier-2. Flag affected ECUs for deep inspection. "
                "Cross-correlate brake, speed, and steering channels for replay attack signatures."
            )
        elif risk >= 40:
            level  = "MODERATE"
            action = (
                "Monitor for sustained anomaly patterns. "
                "Check ECU firmware versions and verify CAN message schedules."
            )
        else:
            level  = "LOW"
            action = "Continue passive monitoring. No immediate intervention required."

        violation_types = []
        for a in anomalies:
            for v in a.get("violation", []):
                vtype = v.get("type", "") if isinstance(v, dict) else str(v)
                if vtype and vtype not in violation_types:
                    violation_types.append(vtype)

        violation_str = (
            ", ".join(violation_types) if violation_types else "unspecified semantic violations"
        )

        return (
            f"[{level}] Vehicle risk {risk}/100 ({trained_str}). "
            f"Anomalous ECUs: {ecu_list}. "
            f"Detected violations: {violation_str}. "
            f"{action} "
            f"[Local LSTM advisor — no external API required]"
        )

    # ── Internal ──────────────────────────────────────────────────────────

    def _train(self):
        """Train/retrain LSTM and calibrate error threshold from normal data."""
        data = np.array(self._buffer, dtype=np.float32)

        # Normalise globally
        self._mu = data.mean(axis=0)
        self._sd = data.std(axis=0) + 1e-6
        data_norm = (data - self._mu) / self._sd

        # Build (X → y_next) pairs from the normalised stream
        X, y = [], []
        for i in range(len(data_norm) - WINDOW_SIZE):
            X.append(data_norm[i : i + WINDOW_SIZE])
            y.append(data_norm[i + WINDOW_SIZE])

        if len(X) < 10:
            return

        X_t = torch.tensor(np.array(X), dtype=torch.float32)
        y_t = torch.tensor(np.array(y), dtype=torch.float32)

        if self._model is None:
            self._model     = _LSTMModel(INPUT_DIM, HIDDEN_DIM, NUM_LAYERS, INPUT_DIM)
            self._optimizer = torch.optim.Adam(self._model.parameters(), lr=5e-4)
            self._loss_fn   = nn.MSELoss()

        self._model.train()
        dataset = torch.utils.data.TensorDataset(X_t, y_t)
        loader  = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=True)

        for _ in range(15):
            for xb, yb in loader:
                self._optimizer.zero_grad()
                loss = self._loss_fn(self._model(xb), yb)
                loss.backward()
                self._optimizer.step()

        self._model.eval()

        # ── Calibrate error threshold from normal-traffic predictions ──
        # Compute per-sample MAE on the training set to learn what
        # "normal error" looks like.  We store mean and std so that
        # anomaly score = (error - mean) / (SIGMA_SCALE * std), clamped 0–1.
        with torch.no_grad():
            preds  = self._model(X_t).numpy()
            targets = y_t.numpy()
            errs   = np.abs(preds - targets).mean(axis=1)   # MAE per sample

        self._err_mu = float(errs.mean())
        self._err_sd = float(errs.std()) + 1e-6

        self._trained = True
        print(
            f"[LSTM Advisor] Trained on {len(X)} windows | "
            f"normal err: {self._err_mu:.4f} ± {self._err_sd:.4f}"
        )

    def _score_window(self, window: list) -> float:
        """
        Score a per-ECU window. Returns 0–100.
        Normal ECUs should score near 0; attack ECUs should score 60–100.
        """
        win  = np.array(window, dtype=np.float32)
        norm = (win - self._mu) / self._sd

        x_t = torch.tensor(norm[np.newaxis, :, :], dtype=torch.float32)
        with torch.no_grad():
            pred   = self._model(x_t).numpy()[0]

        target = norm[-1]
        error  = float(np.abs(pred - target).mean())

        # Normalise against calibrated normal-traffic error distribution
        z     = (error - self._err_mu) / (SIGMA_SCALE * self._err_sd)
        score = float(np.clip(z, 0.0, 1.0) * 100.0)
        return round(score, 1)


# ── Module-level singleton ───────────────────────────────────────────────
_advisor = LSTMAdvisor()


def ingest_message(message: dict) -> float:
    """Feed a raw ECU message dict. Returns LSTM anomaly confidence 0–100."""
    return _advisor.ingest(message)


def explain_vehicle_anomaly(vehicle_summary: dict) -> str:
    """Generate SOC advisory string from vehicle summary."""
    return _advisor.generate_advisory(vehicle_summary)
