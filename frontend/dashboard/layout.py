from dash import dcc, html
import dash_bootstrap_components as dbc

from frontend.config import REFRESH_INTERVAL_MS, DASHBOARD_TITLE


def _kpi_card(card_id: str, label: str, icon: str) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.Div(icon, className="kpi-icon"),
            html.H2(id=card_id, children="—", className="kpi-value"),
            html.P(label, className="kpi-label"),
        ]),
        className="kpi-card",
    )


def build_layout() -> html.Div:
    return html.Div([

        # ── Poll interval ──
        dcc.Interval(id="interval", interval=REFRESH_INTERVAL_MS, n_intervals=0),

        # ── Header ──
        html.Div([
            html.H1(DASHBOARD_TITLE, className="dashboard-title"),
            html.P("Live automotive ECU telemetry · Semantic anomaly detection · SOC view",
                   className="dashboard-subtitle"),
        ], className="dashboard-header"),

        # ── KPI row ──
        dbc.Row([
            dbc.Col(_kpi_card("kpi-active-ecus",    "Active ECUs",      "🖥️"),  md=4),
            dbc.Col(_kpi_card("kpi-anomalous-ecus", "Anomalous ECUs",   "⚠️"),  md=4),
            dbc.Col(_kpi_card("kpi-last-anomaly",   "Last Anomaly",     "🕐"),  md=4),
        ], className="kpi-row"),

        # ── Charts row ──
        dbc.Row([
            dbc.Col([
                html.H4("Semantic Confidence History", className="chart-title"),
                dcc.Graph(id="graph-history", config={"displayModeBar": False}),
            ], md=8),
            dbc.Col([
                html.H4("Violation Rate", className="chart-title"),
                dcc.Graph(id="graph-violation-rate", config={"displayModeBar": False}),
            ], md=4),
        ], className="chart-row"),

        # ── Bottom row: top ECUs + alerts + AI advisory ──
        dbc.Row([
            dbc.Col([
                html.H4("Top Anomalous ECUs", className="panel-title"),
                html.Div(id="top-ecus-panel", className="top-ecus-panel"),
            ], md=3),

            dbc.Col([
                html.H4("Active Semantic Alerts", className="panel-title"),
                html.Div(id="alerts-panel", className="alerts-panel"),
            ], md=5),

            dbc.Col([
                html.H4("AI Vehicle Advisory", className="panel-title"),
                html.Div(id="ai-advisory-panel", className="ai-advisory-panel"),
            ], md=4),
        ], className="bottom-row"),

    ], className="dashboard-root")
