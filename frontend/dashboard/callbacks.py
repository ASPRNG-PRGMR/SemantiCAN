"""
Dash callbacks — pull data from Flask API and update all dashboard components.
"""

import requests
import dash
from dash import Input, Output, State, html
import plotly.graph_objects as go

from frontend.config import API_BASE

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor ="rgba(0,0,0,0)",
    font         =dict(color="#8b949e", size=12, family="JetBrains Mono, monospace"),
    margin       =dict(l=44, r=140, t=10, b=44),
    xaxis        =dict(gridcolor="#21262d", linecolor="#30363d", showgrid=True),
    yaxis        =dict(gridcolor="#21262d", linecolor="#30363d", showgrid=True),
    legend       =dict(
        bgcolor="rgba(0,0,0,0)", font=dict(size=11),
        orientation="v", yanchor="top", y=1, xanchor="left", x=1.02,
    ),
    hovermode    ="x unified",
)

# Solid background + near-black text for every severity/violation badge.
# The previous scheme (dark-tinted background + bright colored text of the
# SAME hue, e.g. dark red bg + red text) reads as low-contrast "red on red"
# at small sizes — this is the actual bug being fixed, not just a color
# swap. Near-black text against a fully saturated background gives a much
# higher contrast ratio across every color in the set.
SEVERITY_COLOR = {
    "critical": "#f85149",
    "high":     "#d29922",
    "medium":   "#58a6ff",
    "low":      "#3fb950",
}

SEVERITY_LABEL = {
    "critical": "CRITICAL",
    "high":     "ELEVATED",
    "medium":   "ELEVATED",
    "low":      "LOW",
    "ok":       "NOMINAL",
}

DETECTOR_COLOR = {
    "rule":    "#58a6ff",
    "lstm":    "#bc8cff",
    "both":    "#3fb950",
    "unknown": "#8b949e",
}
DETECTOR_LABEL = {
    "rule": "Rule only", "lstm": "LSTM only", "both": "Both", "unknown": "Unknown",
}

# Max anomalous ECU lines to show individually on the trend chart
MAX_ANOMALOUS_LINES = 5

# Max ECU/violation chips shown at a glance in the hero before "+N more"
MAX_HERO_CHIPS = 8


def _get(endpoint: str, fallback=None):
    try:
        r = requests.get(f"{API_BASE}{endpoint}", timeout=2)
        r.raise_for_status()
        return r.json()
    except Exception:
        return fallback


def _hero_severity(alerts: list) -> str:
    severities = {a.get("severity", "low") for a in alerts}
    for level in ("critical", "high", "medium", "low"):
        if level in severities:
            return level
    return "ok"


def _format_ecu_label(node_id: str) -> str:
    """VEHICLE_CONSISTENCY::type1+type2 -> 'CROSS-ECU · type1, type2' —
    readable in a chip instead of the raw synthetic dedup key."""
    if node_id.startswith("VEHICLE_CONSISTENCY::"):
        types = node_id.split("::", 1)[1].replace("+", ", ")
        return f"CROSS-ECU · {types}"
    return node_id


def register_callbacks(app):

    # ── Hero: risk score, inline stats, chips, narrative ────────────────
    @app.callback(
        Output("hero", "className"),
        Output("hero-risk-block", "children"),
        Output("hero-stats", "children"),
        Output("hero-chips", "children"),
        Output("hero-narrative", "children"),
        Output("store-anomalous-ecus-full", "data"),
        Input("tick", "n_intervals"),
    )
    def update_hero(_):
        summary = _get("/api/summary", {})
        alerts  = _get("/api/alerts", [])

        risk    = summary.get("vehicle_risk", 0.0) or 0.0
        active  = summary.get("active_ecus", 0)
        anomalous = summary.get("anomalous_ecus", 0)
        last    = summary.get("last_anomaly") or "—"
        if last and last != "—":
            last = last[11:19]

        sev = _hero_severity(alerts)
        hero_class = f"hero hero--{sev}"

        risk_block = [
            html.Div(f"{risk:.1f}", className="hero-risk-number"),
            html.Div([
                html.Span(SEVERITY_LABEL.get(sev, "NOMINAL"), className="hero-risk-tag"),
                html.Span(" · VEHICLE RISK / 100", className="hero-risk-suffix"),
            ]),
        ]

        stats = [
            html.Div([html.Span("Active ECUs"), html.Span(str(active))], className="hero-stat"),
            html.Div([html.Span("Anomalous"), html.Span(str(anomalous))], className="hero-stat"),
            html.Div([html.Span("Last Anomaly"), html.Span(str(last))], className="hero-stat"),
        ]

        ecu_ids_full = sorted({a["node_id"] for a in alerts})
        violation_types = sorted({
            v.get("type", "unknown") if isinstance(v, dict) else str(v)
            for a in alerts for v in a.get("violations", [])
        })

        chips = []
        if ecu_ids_full:
            shown = ecu_ids_full[:MAX_HERO_CHIPS]
            spans = [html.Span(_format_ecu_label(e), className="chip chip-ecu") for e in shown]
            if len(ecu_ids_full) > MAX_HERO_CHIPS:
                spans.append(html.Button(
                    f"+{len(ecu_ids_full) - MAX_HERO_CHIPS} more",
                    id="ecu-more-btn", n_clicks=0,
                    className="chip chip-more chip-button",
                ))
            chips.append(html.Div([
                html.Span("ECUs", className="chip-row-label"),
                *spans,
            ], className="chip-row"))

        if violation_types:
            chips.append(html.Div([
                html.Span("Violations", className="chip-row-label"),
                *[html.Span(v, className="chip chip-violation") for v in violation_types],
            ], className="chip-row"))

        if not chips:
            chips = [html.Div("No active violations.", className="chip-row-empty")]

        narrative = "All ECUs nominal. No anomalies to report."
        for alert in alerts:
            if alert.get("ai_analysis"):
                narrative = alert["ai_analysis"]

        return hero_class, risk_block, stats, chips, narrative, ecu_ids_full

    # ── ECU modal: opened by the hero's "+N more" button ────────────────
    @app.callback(
        Output("ecu-modal-overlay", "className"),
        Output("ecu-modal-body", "children"),
        Input("ecu-more-btn", "n_clicks"),
        Input("ecu-modal-close", "n_clicks"),
        State("store-anomalous-ecus-full", "data"),
        prevent_initial_call=True,
    )
    def toggle_ecu_modal(_open_clicks, _close_clicks, all_ecus):
        triggered = dash.callback_context.triggered[0]["prop_id"]

        if triggered.startswith("ecu-more-btn"):
            body = html.Div(
                [html.Span(_format_ecu_label(e), className="chip chip-ecu chip-modal")
                 for e in (all_ecus or [])],
                className="modal-chip-grid",
            )
            return "modal-overlay visible", body

        # any other trigger (close button) — hide it
        return "modal-overlay hidden", dash.no_update

    # ── Confidence history chart ───────────────────────────────────────
    @app.callback(
        Output("chart-confidence", "figure"),
        Output("chart-confidence-note", "children"),
        Input("tick", "n_intervals"),
    )
    def update_confidence(_):
        data = _get("/api/semantic-history", [])
        fig  = go.Figure(layout=CHART_LAYOUT)

        if not data:
            fig.add_annotation(text="Awaiting data...", showarrow=False,
                               font=dict(color="#8b949e"))
            return fig, ""

        by_ecu: dict = {}
        for row in data:
            by_ecu.setdefault(row["node_id"], []).append(row)
        for k in by_ecu:
            by_ecu[k] = sorted(by_ecu[k], key=lambda r: r["timestamp"])[-20:]

        anomalous = [
            k for k, rows in by_ecu.items()
            if rows and rows[-1]["confidence"] >= 70
        ]

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

        extra = len(anomalous) - MAX_ANOMALOUS_LINES
        note = f"+{extra} more anomalous ECUs" if extra > 0 else ""

        if not anomalous and not normal_ecus:
            fig.add_annotation(text="No ECU data yet", showarrow=False,
                               font=dict(color="#8b949e"))

        fig.update_layout(
            yaxis=dict(range=[0, 105], title="Confidence",
                       gridcolor="#21262d", linecolor="#30363d"),
            xaxis=dict(gridcolor="#21262d", linecolor="#30363d",
                       tickangle=-45, nticks=8),
        )
        return fig, note

    # ── Detection Method donut ──────────────────────────────────────────
    @app.callback(
        Output("chart-detector", "figure"),
        Input("tick", "n_intervals"),
    )
    def update_detector_breakdown(_):
        data = _get("/api/detector-breakdown", {})
        fig  = go.Figure(layout=CHART_LAYOUT)

        labels, values, colors = [], [], []
        for key in ("rule", "lstm", "both", "unknown"):
            count = data.get(key, 0)
            if count > 0:
                labels.append(DETECTOR_LABEL[key])
                values.append(count)
                colors.append(DETECTOR_COLOR[key])

        if not values:
            fig.add_annotation(text="No active alerts", showarrow=False,
                               font=dict(color="#8b949e", size=12))
            fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            return fig

        fig.add_trace(go.Pie(
            labels=labels, values=values, hole=0.6,
            marker=dict(colors=colors, line=dict(color="#0d1117", width=2)),
            textinfo="value", textfont=dict(size=13, color="#e6edf3"),
            hoverinfo="label+percent",
        ))
        fig.update_layout(
            showlegend=True,
            legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.05,
                        bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
            margin=dict(l=10, r=90, t=10, b=10),
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
            return html.Div("No anomalous ECUs detected.", className="empty-note")

        rows = []
        for item in data:
            pct = item["confidence"]
            rows.append(html.Div([
                html.Div([
                    html.Span(item["node_id"], className="top-ecu-name"),
                    html.Span(f"{pct:.0f}/100", className="top-ecu-value"),
                ], className="top-ecu-row"),
                html.Div(className="risk-bar-bg", children=[
                    html.Div(className="risk-bar-fill",
                             style={"width": f"{min(pct, 100):.0f}%"}),
                ]),
            ], className="top-ecu-item"))
        return rows

    # ── Active alerts ─────────────────────────────────────────────────
    @app.callback(
        Output("alerts-panel", "children"),
        Input("tick", "n_intervals"),
    )
    def update_alerts(_):
        data = _get("/api/alerts", [])

        if not data:
            return html.Div("No active alerts.", className="empty-note")

        rows = []
        for alert in data:
            sev  = alert.get("severity", "low")
            vtags = [
                html.Span(v.get("type", "unknown") if isinstance(v, dict) else str(v),
                          className="vtag")
                for v in alert.get("violations", [])
            ]
            # Compact left-aligned cluster instead of spreading confidence
            # to the far right with margin-left:auto — that's what made
            # every row look like it had a huge dead gap in the middle on
            # a wide column. Everything sits together now; the panel can
            # be narrower without any single row looking sparse.
            rows.append(html.Div([
                html.Div([
                    html.Span(_format_ecu_label(alert["node_id"]), className="alert-node"),
                    html.Span(sev.upper(), className=f"pill pill--{sev}"),
                    html.Span(alert.get("detector", "unknown"), className="pill pill--detector"),
                    html.Span(f"conf={alert['confidence']:.0f}", className="alert-conf"),
                ], className="alert-row-top"),
                html.Div(vtags, className="alert-row-tags") if vtags else None,
            ], className=f"alert-row {sev}"))

        return rows

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
