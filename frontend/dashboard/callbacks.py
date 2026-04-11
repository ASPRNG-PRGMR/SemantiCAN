"""
Dash callbacks — pull data from Flask API and update all dashboard components.
"""

import requests
from dash import Input, Output, html
import plotly.graph_objects as go

from frontend.config import API_BASE

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor ="rgba(0,0,0,0)",
    font         =dict(color="#8b949e", size=11, family="JetBrains Mono, monospace"),
    margin       =dict(l=40, r=10, t=10, b=40),
    xaxis        =dict(gridcolor="#21262d", linecolor="#30363d", showgrid=True),
    yaxis        =dict(gridcolor="#21262d", linecolor="#30363d", showgrid=True),
    legend       =dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
    hovermode    ="x unified",
)

SEVERITY_COLOR = {
    "critical": "#f85149",
    "high":     "#d29922",
    "medium":   "#58a6ff",
    "low":      "#3fb950",
}

ECU_COLORS = [
    "#58a6ff", "#3fb950", "#d29922", "#f85149",
    "#bc8cff", "#79c0ff", "#56d364", "#ffa657",
]

# Max anomalous ECU lines to show individually (keeps chart readable)
MAX_ANOMALOUS_LINES = 5


def _get(endpoint: str, fallback=None):
    try:
        r = requests.get(f"{API_BASE}{endpoint}", timeout=2)
        r.raise_for_status()
        return r.json()
    except Exception:
        return fallback


def register_callbacks(app):

    @app.callback(
        Output("kpi-active",   "children"),
        Output("kpi-anomalous","children"),
        Output("kpi-last",     "children"),
        Output("kpi-anomalous","className"),
        Input("tick", "n_intervals"),
    )
    def update_kpis(_):
        data = _get("/api/summary", {})
        active    = data.get("active_ecus",    0)
        anomalous = data.get("anomalous_ecus", 0)
        last      = data.get("last_anomaly",   "—")

        if last and last != "—":
            last = last[11:19]   # show HH:MM:SS only

        cls = "kpi-value danger" if anomalous > 0 else "kpi-value ok"
        return str(active), str(anomalous), last, cls

    # ── Confidence history chart ───────────────────────────────────────
    @app.callback(
        Output("chart-confidence", "figure"),
        Input("tick", "n_intervals"),
    )
    def update_confidence(_):
        data = _get("/api/semantic-history", [])
        fig  = go.Figure(layout=CHART_LAYOUT)

        if not data:
            fig.add_annotation(text="Awaiting data...", showarrow=False,
                               font=dict(color="#8b949e"))
            return fig

        # Group by ECU, keep only last 20 readings per ECU
        by_ecu: dict = {}
        for row in data:
            by_ecu.setdefault(row["node_id"], []).append(row)
        for k in by_ecu:
            by_ecu[k] = sorted(by_ecu[k], key=lambda r: r["timestamp"])[-20:]

        # An ECU is anomalous if its LATEST confidence >= 70
        anomalous = [
            k for k, rows in by_ecu.items()
            if rows and rows[-1]["confidence"] >= 70
        ]

        # ── Normal baseline: single average band ─────────────────────
        normal_ecus = [k for k in by_ecu if k not in anomalous]
        if normal_ecus:
            time_vals: dict = {}
            for eid in normal_ecus:
                for r in by_ecu[eid]:
                    t = r["timestamp"][11:19]
                    time_vals.setdefault(t, []).append(r["confidence"])
            times = sorted(time_vals)
            avgs  = [sum(time_vals[t]) / len(time_vals[t]) for t in times]
            fig.add_trace(go.Scatter(
                x=times, y=avgs,
                name=f"Normal ({len(normal_ecus)} ECUs avg)",
                mode="lines",
                line=dict(color="#3fb950", width=1.5, dash="dot"),
                opacity=0.5,
            ))

        # ── Anomalous ECUs: top N by confidence, individual lines ─────
        # Sort by latest confidence descending and cap to MAX_ANOMALOUS_LINES
        anomalous_sorted = sorted(
            anomalous,
            key=lambda k: by_ecu[k][-1]["confidence"] if by_ecu[k] else 0,
            reverse=True,
        )[:MAX_ANOMALOUS_LINES]

        alert_colors = ["#f85149", "#d29922", "#bc8cff", "#ffa657", "#79c0ff"]
        for i, ecu_id in enumerate(anomalous_sorted):
            rows  = by_ecu[ecu_id]
            color = alert_colors[i % len(alert_colors)]
            fig.add_trace(go.Scatter(
                x    =[r["timestamp"][11:19] for r in rows],
                y    =[r["confidence"]        for r in rows],
                name =ecu_id,
                mode ="lines+markers",
                line =dict(color=color, width=2.5),
                marker=dict(size=5),
            ))

        # If there are more anomalous ECUs than MAX_ANOMALOUS_LINES, show a note
        extra = len(anomalous) - MAX_ANOMALOUS_LINES
        if extra > 0:
            fig.add_annotation(
                text=f"+{extra} more anomalous ECUs",
                xref="paper", yref="paper", x=1.0, y=1.02,
                showarrow=False,
                font=dict(color="#8b949e", size=10),
                xanchor="right",
            )

        if not anomalous and not normal_ecus:
            fig.add_annotation(text="No ECU data yet", showarrow=False,
                               font=dict(color="#8b949e"))

        fig.update_layout(
            yaxis=dict(range=[0, 105], title="Confidence",
                       gridcolor="#21262d", linecolor="#30363d"),
            xaxis=dict(gridcolor="#21262d", linecolor="#30363d",
                       tickangle=-45, nticks=8),
        )
        return fig

    # ── Violation rate chart ───────────────────────────────────────────
    @app.callback(
        Output("chart-violation-rate", "figure"),
        Input("tick", "n_intervals"),
    )
    def update_violation_rate(_):
        data = _get("/api/violation-rate", [])
        fig  = go.Figure(layout=CHART_LAYOUT)

        if not data:
            fig.add_annotation(text="Awaiting data...", showarrow=False,
                               font=dict(color="#8b949e"))
            return fig

        times  = [d["time"]  for d in data]
        counts = [d["count"] for d in data]

        max_count = max(counts) if counts else 1

        fig.add_trace(go.Bar(
            x=times, y=counts,
            marker_color="#f85149",
            marker_line_width=0,
            name="Violations",
        ))
        fig.update_layout(
            yaxis=dict(
                title="Count",
                # Add 20% headroom above max, minimum range of 4 so zero bars
                # don't look full-height on an empty chart
                range=[0, max(max_count * 1.2, 4)],
                dtick=1,
            ),
            showlegend=False,
        )
        return fig

    # ── Top anomalous ECUs ────────────────────────────────────────────
    @app.callback(
        Output("top-ecus", "children"),
        Input("tick", "n_intervals"),
    )
    def update_top_ecus(_):
        data = _get("/api/top-anomalous-ecus", [])
        if not data:
            return html.Div("No anomalous ECUs detected.",
                            style={"color": "#8b949e", "fontSize": "12px"})

        rows = []
        for item in data:
            pct = item["confidence"]
            rows.append(html.Div([
                html.Div([
                    html.Span(item["node_id"], style={"color": "#58a6ff", "fontWeight": "bold"}),
                    html.Span(f"  {pct:.0f}/100", style={"color": "#8b949e", "float": "right"}),
                ], style={"display": "flex", "justifyContent": "space-between"}),
                html.Div(className="risk-bar-bg", children=[
                    html.Div(className="risk-bar-fill",
                             style={"width": f"{min(pct, 100):.0f}%"}),
                ]),
            ], style={"marginBottom": "10px"}))
        return rows

    # ── Active alerts ─────────────────────────────────────────────────
    @app.callback(
        Output("alerts-panel",  "children"),
        Output("advisory-panel","children"),
        Input("tick", "n_intervals"),
    )
    def update_alerts(_):
        data = _get("/api/alerts", [])

        if not data:
            no_alert = html.Div("No active alerts.", style={"color": "#8b949e", "fontSize": "12px"})
            return no_alert, "No anomalies to report."

        rows = []
        last_advisory = ""
        for alert in data:
            sev  = alert.get("severity", "low")
            vtags = [
                html.Span(v.get("type", "unknown") if isinstance(v, dict) else str(v),
                          className="vtag")
                for v in alert.get("violations", [])
            ]
            rows.append(html.Div([
                html.Div([
                    html.Span(alert["node_id"], className="alert-node"),
                    html.Span(f"  {sev.upper()}", className=f"alert-sev {sev}"),
                    html.Span(f"  conf={alert['confidence']:.0f}",
                              style={"color": "#8b949e", "fontSize": "11px"}),
                ]),
                html.Div(vtags, style={"marginTop": "4px"}),
            ], className=f"alert-row {sev}"))

            if alert.get("ai_analysis"):
                last_advisory = alert["ai_analysis"]

        return rows, last_advisory or "Waiting for advisory..."

    # ── LSTM status badge ─────────────────────────────────────────────
    @app.callback(
        Output("lstm-badge-container", "children"),
        Input("tick", "n_intervals"),
    )
    def update_lstm_badge(_):
        status = _get("/api/lstm-status", {})
        trained = status.get("trained", False)
        samples = status.get("samples", 0)

        if trained:
            badge = html.Span("● LSTM Ready", className="lstm-badge ready")
        else:
            badge = html.Span(f"◌ LSTM Training ({samples} samples)",
                              className="lstm-badge training")
        return badge
