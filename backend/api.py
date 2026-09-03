from flask import Flask, jsonify

from backend.api_state import (
    get_summary,
    get_semantic_history,
    get_violation_rate,
    get_top_anomalous_ecus,
)

app = Flask(__name__)


def start_api(host: str = "127.0.0.1", port: int = 5000):
    app.run(host=host, port=port, debug=False, use_reloader=False)


@app.route("/api/summary")
def summary():
    return jsonify(get_summary())


@app.route("/api/semantic-history")
def semantic_history():
    return jsonify(get_semantic_history())


@app.route("/api/violation-rate")
def violation_rate():
    return jsonify(get_violation_rate())


@app.route("/api/alerts")
def alerts():
    from backend.core.alerts import get_active_alerts
    return jsonify(get_active_alerts())


@app.route("/api/top-anomalous-ecus")
def top_anomalous_ecus():
    return jsonify(get_top_anomalous_ecus(limit=3))


@app.route("/api/detector-breakdown")
def detector_breakdown():
    from backend.core.alerts import get_detector_breakdown
    return jsonify(get_detector_breakdown())


@app.route("/api/lstm-status")
def lstm_status():
    """Exposes LSTM training state for the dashboard status indicator."""
    try:
        from backend.ai.advisor import _advisor
        return jsonify({
            "trained":     _advisor._trained,
            "samples":     len(_advisor._buffer),
            "train_steps": _advisor._step_count,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
