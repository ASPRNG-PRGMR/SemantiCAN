from flask import Flask, jsonify

from backend.api_state import (
    get_summary,
    get_semantic_history,
    get_violation_rate,
    get_top_anomalous_ecus,
)

app = Flask(__name__)


def start_api():
    app.run(port=5000, debug=False, use_reloader=False)


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
