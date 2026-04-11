from dash import dcc, html

from frontend.config import TITLE, SUBTITLE, REFRESH_INTERVAL


def build_layout() -> html.Div:
    return html.Div([

        # ── Live interval ──────────────────────────────────────────────
        dcc.Interval(id="tick", interval=REFRESH_INTERVAL, n_intervals=0),

        # ── Header ────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.H1(TITLE),
                html.P(SUBTITLE),
            ]),
            html.Div(id="lstm-badge-container", style={"marginLeft": "auto", "alignSelf": "center"}),
        ], id="header"),

        # ── KPI strip ─────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div("Active ECUs",    className="kpi-label"),
                html.Div(id="kpi-active",  className="kpi-value ok"),
            ], className="kpi-card"),
            html.Div([
                html.Div("Anomalous ECUs", className="kpi-label"),
                html.Div(id="kpi-anomalous", className="kpi-value"),
            ], className="kpi-card"),
            html.Div([
                html.Div("Last Anomaly",  className="kpi-label"),
                html.Div(id="kpi-last",   className="kpi-value", style={"fontSize": "14px"}),
            ], className="kpi-card"),
        ], style={"display": "flex", "gap": "12px", "padding": "16px 24px 0"}),

        # ── Main body ─────────────────────────────────────────────────
        html.Div([

            # Left column: charts + AI Advisory
            html.Div([
                html.Div([
                    html.Div("Semantic Confidence History (per ECU)", className="panel-title"),
                    dcc.Graph(id="chart-confidence", config={"displayModeBar": False},
                              style={"height": "260px"}),
                ], className="panel"),

                html.Div([
                    html.Div("Violation Rate (10-second buckets)", className="panel-title"),
                    dcc.Graph(id="chart-violation-rate", config={"displayModeBar": False},
                              style={"height": "200px"}),
                ], className="panel"),

                # AI Advisory moved here — under the bar chart
                html.Div([
                    html.Div("AI Advisory (Local LSTM)", className="panel-title"),
                    html.Div(id="advisory-panel",
                             style={"color": "#8b949e", "fontSize": "12px",
                                    "lineHeight": "1.7", "whiteSpace": "pre-wrap"}),
                ], className="panel"),
            ], style={"flex": "2", "minWidth": 0}),

            # Right column: top ECUs + alerts only
            html.Div([
                html.Div([
                    html.Div("Top Anomalous ECUs", className="panel-title"),
                    html.Div(id="top-ecus"),
                ], className="panel"),

                html.Div([
                    html.Div("Active Alerts", className="panel-title"),
                    html.Div(id="alerts-panel",
                             style={"maxHeight": "520px", "overflowY": "auto"}),
                ], className="panel"),
            ], style={"flex": "1", "minWidth": "320px"}),

        ], style={"display": "flex", "gap": "16px", "padding": "16px 24px"}),

    ])
