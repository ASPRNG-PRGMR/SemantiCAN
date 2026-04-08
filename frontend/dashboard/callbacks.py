import requests
import plotly.graph_objs as go
from dash import Input, Output, html
from dash.exceptions import PreventUpdate

from frontend.dashboard.app import app
from frontend.config import (
    SUMMARY_URL,
    ALERTS_URL,
    HISTORY_URL,
    RATE_URL,
    TOP_ECUS_URL,
)

# ── Palette ──
COLOR_SAFE     = "#00e5ff"
COLOR_WARN     = "#ffb300"
COLOR_CRITICAL = "#ff1744"
COLOR_BG       = "#0d1117"
COLOR_PANEL    = "#161b22"
COLOR_TEXT     = "#c9d1d9"

SEVERITY_COLOR = {
    "critical": COLOR_CRITICAL,
    "high":     COLOR_WARN,
    "medium":   "#ff6d00",
    "low":      COLOR_SAFE,
}


def _get(url: str, default):
    try:
        r = requests.get(url, timeout=2)
        r.raise_for_status()
        return r.json()
    except Exception:
        return default


# ────────────────────────────────────────────────
# KPI cards
# ────────────────────────────────────────────────
@app.callback(
    Output("kpi-active-ecus",    "children"),
    Output("kpi-anomalous-ecus", "children"),
    Output("kpi-last-anomaly",   "children"),
    Input("interval", "n_intervals"),
)
def update_kpis(_):
    summary = _get(SUMMARY_URL, {})
    active    = summary.get("active_ecus",    "—")
    anomalous = summary.get("anomalous_ecus", "—")
    last_ts   = summary.get("last_anomaly")
    last_str  = last_ts[:19].replace("T", " ") if last_ts else "—"
    return active, anomalous, last_str


# ────────────────────────────────────────────────
# Semantic confidence history chart
# ────────────────────────────────────────────────
@app.callback(
    Output("graph-history", "figure"),
    Input("interval", "n_intervals"),
)
def update_history(_):
    data = _get(HISTORY_URL, [])

    fig = go.Figure()

    if data:
        # Group by node_id for colour separation
        by_node: dict = {}
        for pt in data:
            by_node.setdefault(pt["node_id"], {"x": [], "y": []})
            by_node[pt["node_id"]]["x"].append(pt["timestamp"])
            by_node[pt["node_id"]]["y"].append(pt["confidence"])

        for node_id, pts in by_node.items():
            last_conf = pts["y"][-1] if pts["y"] else 0
            color = COLOR_CRITICAL if last_conf >= 60 else COLOR_SAFE
            fig.add_trace(go.Scatter(
                x=pts["x"], y=pts["y"],
                mode="lines",
                name=node_id,
                line=dict(color=color, width=1.5),
                opacity=0.85,
            ))

    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_PANEL,
        font=dict(color=COLOR_TEXT),
        margin=dict(l=40, r=20, t=20, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        xaxis=dict(gridcolor="#21262d", showgrid=True),
        yaxis=dict(gridcolor="#21262d", showgrid=True, range=[0, 105],
                   title="Confidence / Risk Score"),
    )
    return fig


# ────────────────────────────────────────────────
# Violation rate chart
# ────────────────────────────────────────────────
@app.callback(
    Output("graph-violation-rate", "figure"),
    Input("interval", "n_intervals"),
)
def update_violation_rate(_):
    data = _get(RATE_URL, [])

    times  = [d["time"]  for d in data]
    counts = [d["count"] for d in data]

    fig = go.Figure(go.Bar(
        x=times, y=counts,
        marker_color=COLOR_WARN,
        opacity=0.85,
    ))
    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_PANEL,
        font=dict(color=COLOR_TEXT),
        margin=dict(l=40, r=20, t=20, b=40),
        xaxis=dict(gridcolor="#21262d", tickangle=-45),
        yaxis=dict(gridcolor="#21262d", title="Violations"),
    )
    return fig


# ────────────────────────────────────────────────
# Top anomalous ECUs
# ────────────────────────────────────────────────
@app.callback(
    Output("top-ecus-panel", "children"),
    Input("interval", "n_intervals"),
)
def update_top_ecus(_):
    ecus = _get(TOP_ECUS_URL, [])

    if not ecus:
        return html.P("No anomalous ECUs detected.", className="panel-empty")

    rows = []
    for ecu in ecus:
        conf = ecu.get("confidence", 0)
        bar_color = COLOR_CRITICAL if conf >= 75 else COLOR_WARN
        rows.append(html.Div([
            html.Div([
                html.Span(ecu["node_id"], className="ecu-id"),
                html.Span(f"{conf:.0f}%", className="ecu-score"),
            ], className="ecu-row-header"),
            html.Div(className="ecu-bar-bg", children=[
                html.Div(style={
                    "width": f"{conf}%",
                    "background": bar_color,
                    "height": "6px",
                    "borderRadius": "3px",
                    "transition": "width 0.4s ease",
                })
            ]),
            html.P(
                ecu.get("last_seen", "")[:19].replace("T", " "),
                className="ecu-lastseen",
            ),
        ], className="ecu-card"))

    return rows


# ────────────────────────────────────────────────
# Active alerts panel
# ────────────────────────────────────────────────
@app.callback(
    Output("alerts-panel", "children"),
    Input("interval", "n_intervals"),
)
def update_alerts(_):
    alerts = _get(ALERTS_URL, [])

    if not alerts:
        return html.P("No active alerts.", className="panel-empty")

    cards = []
    for alert in alerts[:8]:  # show up to 8
        sev   = alert.get("severity", "low")
        color = SEVERITY_COLOR.get(sev, COLOR_SAFE)
        viols = alert.get("violations", [])
        viol_tags = [
            html.Span(v["type"].replace("_", " "), className="viol-tag",
                      style={"borderColor": color})
            for v in viols
        ]
        cards.append(html.Div([
            html.Div([
                html.Span(alert["node_id"], className="alert-node"),
                html.Span(sev.upper(), className="alert-severity",
                          style={"color": color}),
                html.Span(f"risk {alert.get('confidence', 0):.0f}%",
                          className="alert-confidence"),
            ], className="alert-header"),
            html.Div(viol_tags, className="alert-violations"),
            html.P(alert.get("timestamp", "")[:19].replace("T", " "),
                   className="alert-ts"),
        ], className="alert-card", style={"borderLeftColor": color}))

    return cards


# ────────────────────────────────────────────────
# AI advisory panel
# ────────────────────────────────────────────────
@app.callback(
    Output("ai-advisory-panel", "children"),
    Input("interval", "n_intervals"),
)
def update_advisory(_):
    alerts = _get(ALERTS_URL, [])

    if not alerts:
        return html.P("Awaiting anomaly data…", className="panel-empty")

    # Show the most recent AI analysis
    latest = sorted(alerts, key=lambda a: a.get("timestamp", ""), reverse=True)
    analysis = latest[0].get("ai_analysis", "No analysis available.")

    return html.Div([
        html.P(analysis, className="advisory-text"),
    ])
