from dash import dcc, html

from frontend.config import TITLE, SUBTITLE, REFRESH_INTERVAL


def build_layout() -> html.Div:
    return html.Div([

        # ── Live interval ──────────────────────────────────────────────
        dcc.Interval(id="tick", interval=REFRESH_INTERVAL, n_intervals=0),

        # Holds the FULL (uncapped) anomalous-ECU list so the "+N more"
        # modal always has the complete set to show, independent of how
        # many chips the hero displays at a glance.
        dcc.Store(id="store-anomalous-ecus-full", data=[]),

        # ── Header ────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.H1(TITLE),
                html.P(SUBTITLE),
            ]),
            html.Div(id="lstm-badge-container", style={"marginLeft": "auto", "alignSelf": "center"}),
        ], id="header"),

        # ── Hero: AI Advisory — the single most prominent element on the
        #    page. className is set by the callback (hero--critical/high/
        #    medium/low/ok) to tint the whole card by current severity.
        html.Div([
            html.Div([
                html.Div(id="hero-risk-block", className="hero-risk-block"),
                html.Div(id="hero-stats", className="hero-stats"),
            ], className="hero-top-row"),
            html.Div(id="hero-chips", className="hero-chips"),
            html.Div(id="hero-narrative", className="hero-narrative"),
        ], id="hero", className="hero"),

        # ── Body: two columns, both grow to fill remaining viewport ─────
        html.Div([

            # Left column: confidence chart, then Top Anomalous ECUs +
            # Detection Method stretched to fill all remaining height —
            # this is what stops the left column from stopping short and
            # leaving blank space below it while the right column runs to
            # the bottom of the page.
            html.Div([
                html.Div([
                    html.Div([
                        html.Span("Semantic Confidence History (per ECU)"),
                        html.Span(id="chart-confidence-note", className="panel-title-note"),
                    ], className="panel-title",
                       style={"display": "flex", "justifyContent": "space-between",
                              "alignItems": "baseline"}),
                    dcc.Graph(id="chart-confidence", config={"displayModeBar": False},
                              style={"height": "300px"}),
                ], className="panel panel-chart"),

                html.Div([
                    html.Div([
                        html.Div("Top Anomalous ECUs", className="panel-title"),
                        html.Div(id="top-ecus", className="top-ecus-list"),
                    ], className="panel panel-compact panel-fill"),

                    html.Div([
                        html.Div("Detection Method", className="panel-title"),
                        dcc.Graph(id="chart-detector", config={"displayModeBar": False},
                                  responsive=True, style={"flex": "1", "minHeight": "0"}),
                    ], className="panel panel-compact panel-fill"),
                ], className="panel-row panel-row-fill"),
            ], id="body-left"),

            # Right column: Active Alerts, full height. Narrower than
            # before — alert rows are compact clusters now, not spread
            # across the full column width, so the column itself doesn't
            # need to be as wide to avoid looking sparse.
            html.Div([
                html.Div([
                    html.Div("Active Alerts", className="panel-title"),
                    html.Div(id="alerts-panel", className="alerts-scroll"),
                ], className="panel panel-grow"),
            ], id="body-right"),

        ], id="body-grid"),

        # ── ECU modal — opened by clicking "+N more" in the hero's ECU
        #    chip row. Hidden by default via the "hidden" class.
        html.Div([
            html.Div([
                html.Div([
                    html.Span("All Anomalous ECUs"),
                    html.Button("✕", id="ecu-modal-close", className="modal-close", n_clicks=0),
                ], className="modal-header"),
                html.Div(id="ecu-modal-body", className="modal-body"),
            ], className="modal-box"),
        ], id="ecu-modal-overlay", className="modal-overlay hidden"),

    ], id="dashboard-root")
