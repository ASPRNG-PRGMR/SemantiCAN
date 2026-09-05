"""
Static page structure for the SemantiCAN console.

The layout is fixed here and only ever filled by callbacks. No panel is
created or destroyed at runtime: panels that appear and disappear force an
operator to re-learn the page exactly when the situation is changing, which
is the opposite of what a console should do during an incident.

Zones, top to bottom:
  command bar     identity, feed liveness, LSTM state, calm mode, clock
  advisory deck   the hero: the narrative, with the risk gauge folded in
  body grid       confidence history + rate/attribution | alert stream
  drawer + modal  overlays, off-canvas until opened
"""

from dash import dcc, html

from frontend.config import TITLE, SUBTITLE, VEHICLE_LABEL, REFRESH_INTERVAL
from frontend.dashboard.reference import (
    RULES,
    CONSISTENCY_CHECKS,
    COVERAGE_GAPS,
    EVAL_PROVENANCE,
    EVAL_METRICS,
    EVAL_FINDINGS,
)


def _command_bar() -> html.Div:
    return html.Div([
        html.Div([
            html.Span(TITLE, className="mark-name"),
            html.Span(SUBTITLE, className="mark-sub"),
        ], className="mark"),

        html.Div(VEHICLE_LABEL, className="bar-group num vehicle-chip"),

        # The view switcher lives here rather than in a row of its own.
        # There was ~700px of dead bar between the vehicle chip and the feed
        # chip at 1920, and a whole 45px row underneath doing the same job.
        _tab_bar(),

        html.Div(className="bar-spacer"),

        # Feed liveness. This reads the newest telemetry timestamp, which is
        # what /api/summary's `last_anomaly` field actually holds. It is a
        # heartbeat, not an anomaly time, so it is labelled as one.
        html.Div([
            html.Span(id="feed-dot", className="pulse-dot"),
            html.Span("Feed", style={"color": "var(--ink-low)"}),
            html.Span("--:--:--", id="feed-stamp", className="num",
                      **{"data-stamp": ""}),
        ], id="feed-group", className="bar-group feed-down"),

        html.Div([
            html.Span(className="lstm-dot"),
            html.Span("Model starting", id="lstm-text"),
        ], id="lstm-group", className="bar-group lstm-training"),

        html.Button(
            html.Span(className="theme-icon"),
            id="theme-toggle", n_clicks=0,
            className="icon-toggle mode-moon",
            title="Switch to dark mode",
            **{"aria-label": "Switch to dark mode"},
        ),

        html.Button("Calm mode", id="calm-toggle", n_clicks=0,
                    className="calm-toggle", **{"data-on": "false"}),

        html.Div("--:--:--", id="clock", className="bar-group num"),
    ], id="commandbar")


def _advisory_deck() -> html.Div:
    """The hero. The narrative is the largest readable block on the page;
    the risk gauge sits beside it as context rather than as a rival
    headline."""
    return html.Div([

        html.Div([
            # motion.js injects the arc SVG here and drives it. Dash's html
            # module has no SVG primitives, and routing raw SVG through
            # dcc.Markdown gets it sanitised away.
            html.Div([
                html.Div([
                    html.Div("0.0", id="gauge-value", className="gauge-value"),
                    html.Div("of 100", className="gauge-scale"),
                ], className="gauge-readout"),
            ], id="gauge-wrap", className="gauge-wrap"),

            html.Div("Weighted vehicle risk", className="gauge-caption"),

            # Tween target. Never displayed; motion.js reads data-risk.
            html.Div(id="risk-feed", **{"data-risk": "0"},
                     style={"display": "none"}),
        ], className="gauge-well"),

        # "How bad" and "which ones" belong together. /api/top-anomalous-ecus
        # returns at most three, so this is a fixed-height block that never
        # scrolls and never pushes the narrative around.
        html.Div([
            html.Div("Highest scoring ECUs", className="gauge-caption",
                     style={"textAlign": "left", "marginBottom": "10px"}),
            html.Div(id="top-ecus", className="meter-list"),
        ], className="top-ecus-well"),

        html.Div([
            html.Div([
                html.Span("Starting up", id="deck-tier", className="deck-tier"),
                html.Span(id="deck-stamp", className="deck-stamp"),
            ], className="deck-headline"),

            html.Div("Waiting for the first telemetry frames.",
                     id="deck-narrative", className="deck-narrative is-empty"),

            # Both rows and the overflow button are part of the static
            # layout; only their contents change. `chip-more` used to be
            # rebuilt inside the chips payload on every poll, which reset
            # its n_clicks to 0 and lost any click that did not complete its
            # round trip before the next 2s rebuild. A control the operator
            # clicks should not be destroyed four times a minute.
            html.Div([
                html.Div([
                    html.Span("Flagged", className="chip-line-label"),
                    html.Div(id="deck-chip-row", className="chip-row"),
                    html.Button("", id="chip-more", n_clicks=0,
                                className="chip-more",
                                style={"display": "none"}),
                ], id="chip-line-flagged", className="chip-line"),
                html.Div([
                    html.Span("Violations", className="chip-line-label"),
                    html.Div(id="deck-violation-row", className="chip-row"),
                ], id="chip-line-violations", className="chip-line"),
            ], className="deck-chips"),

            html.Div([
                html.Div([
                    html.Span("ECUs reporting", className="stat-label"),
                    html.Span("0", id="stat-active", className="stat-value num"),
                ], className="stat-well"),
                html.Div([
                    html.Span("Anomalous", className="stat-label"),
                    html.Span("0", id="stat-anomalous", className="stat-value num"),
                ], className="stat-well"),
                html.Div([
                    html.Span("Open alerts", className="stat-label"),
                    html.Span("0", id="stat-alerts", className="stat-value num"),
                ], className="stat-well"),
                html.Div([
                    html.Span("Last frame", className="stat-label"),
                    html.Span("--:--:--", id="stat-feed",
                              className="stat-value dim num"),
                ], className="stat-well"),
            ], className="deck-stats"),
        ], className="deck-body"),

    ], id="advisory-deck", className="deck--nominal")


def _analysis_column() -> html.Div:
    return html.Div([

        html.Div([
            html.Div([
                html.Span("Semantic confidence", className="panel-title"),
                html.Span(id="chart-note", className="panel-note"),
            ], className="panel-head"),
            html.Div(
                dcc.Graph(
                    id="chart-confidence",
                    config={"displayModeBar": False},
                    responsive=True,
                    style={"height": "100%"},
                ),
                className="panel-body",
            ),
        ], className="panel"),

        html.Div([
            html.Div([
                html.Div([
                    html.Span("Violation rate", className="panel-title"),
                    html.Span("60s window", className="panel-note"),
                ], className="panel-head"),
                html.Div(id="rate-chart", className="panel-body rate-chart"),
            ], className="panel"),

            html.Div([
                html.Div([
                    html.Span("Caught by", className="panel-title"),
                    html.Span(id="detector-note", className="panel-note"),
                ], className="panel-head"),
                html.Div(id="detector-body", className="panel-body"),
            ], className="panel"),
        ], className="split-row"),

    ], id="col-analysis")


SEVERITY_FILTERS = [
    ("all",      "All"),
    ("medium",   "Medium+"),
    ("high",     "High+"),
    ("critical", "Critical"),
]

SORT_ORDERS = [
    ("newest",     "Newest"),
    ("severity",   "Severity"),
    ("confidence", "Confidence"),
]


def _seg_button(group: str, value: str, label: str, active: bool) -> html.Button:
    return html.Button(
        label,
        id={"type": group, "index": value},
        n_clicks=0,
        className="seg-button" + (" is-active" if active else ""),
        **{"aria-pressed": "true" if active else "false"},
    )


def _stream_column() -> html.Div:
    return html.Div([
        html.Div([
            html.Span("Alert stream", className="panel-title"),
            html.Span(id="stream-note", className="panel-note"),
        ], className="panel-head"),

        # ACTIVE_ALERTS in backend/core/alerts.py is append-only per node_id
        # and nothing ever removes an entry, so this list only grows for the
        # life of the process. Filter and sort are load-bearing here.
        #
        # Real buttons with server-side active state, rather than styled
        # RadioItems. Styling a radio's checked state needs :has(), and a
        # control this important should not depend on a selector the
        # browser might not support.
        html.Div([
            html.Div([
                html.Span("Severity", className="control-label"),
                html.Div(
                    [_seg_button("filter-severity", v, label, v == "all")
                     for v, label in SEVERITY_FILTERS],
                    className="segmented",
                ),
            ], className="control-row"),
            html.Div([
                html.Span("Sort", className="control-label"),
                html.Div(
                    [_seg_button("sort-order", v, label, v == "newest")
                     for v, label in SORT_ORDERS],
                    className="segmented",
                ),
            ], className="control-row"),
        ], className="stream-controls"),

        html.Div(id="stream-scroll", className="stream-scroll"),
    ], id="col-stream", className="panel")


TABS = [
    ("live",       "Live"),
    ("detection",  "Detection"),
    ("evaluation", "Evaluation"),
]


def _tab_bar() -> html.Div:
    """Real buttons with server-side active state, same as the segmented
    controls. Unlike the chip row these are built once and never rebuilt, so
    their n_clicks survive the poll."""
    return html.Div(
        [
            html.Span("View", className="tab-label"),
            *[
            html.Button(
                label,
                id={"type": "tab", "index": key},
                n_clicks=0,
                className="view-tab" + (" is-active" if key == "live" else ""),
                **{"role": "tab",
                   "aria-selected": "true" if key == "live" else "false"},
            )
            for key, label in TABS
            ],
            # Opens the current view on its own, without the advisory deck,
            # in a new browser tab. The reference panes are dense enough
            # that reading them beside a live incident is a compromise; this
            # is the escape hatch for when you want the whole thing.
            html.A(
                "\u2197",
                id="open-solo", href="/?view=live&solo=1", target="_blank",
                className="solo-link", title="Open this view in a new tab",
                **{"aria-label": "Open this view in a new tab"},
            ),
        ],
        id="tab-bar", **{"role": "tablist", "data-tab": "live"},
    )


def _sev_tag(severity: str) -> html.Span:
    return html.Span(severity, className=f"ref-sev ref-sev--{severity}")


def _threat_tags(ids) -> list:
    return [html.Span(t, className="ref-threat") for t in ids]


def _detection_pane() -> html.Div:
    """Static. Every row restates something already in backend/core and
    docs/, so there is nothing to poll and nothing to invalidate; the pane
    is built once at import and never touched by a callback."""
    return html.Div([

        html.Div([
            html.Div([
                html.Span("Physics rules", className="panel-title"),
                html.Span("backend/core/checks.py", className="panel-note"),
            ], className="panel-head"),
            html.Div([
                html.Div([
                    html.Div("Rule", className="ref-th"),
                    html.Div("Fires when", className="ref-th"),
                    html.Div("Severity", className="ref-th"),
                    html.Div("Protects", className="ref-th"),
                    html.Div("Threat", className="ref-th"),
                    html.Div("Security goal", className="ref-th"),
                ], className="ref-row ref-row--head"),
                *[
                    html.Div([
                        html.Div(r["rule"], className="ref-name num"),
                        html.Div(r["trigger"], className="ref-cell"),
                        html.Div(_sev_tag(r["severity"]), className="ref-cell"),
                        html.Div(r["protects"], className="ref-cell"),
                        html.Div(_threat_tags(r["threat"]), className="ref-cell ref-cell--threat"),
                        html.Div(r["goal"], className="ref-cell"),
                    ], className="ref-row")
                    for r in RULES
                ],
            ], className="ref-table ref-table--rules"),
        ], className="panel"),

        html.Div([
            html.Div([
                html.Span("Cross-ECU consistency", className="panel-title"),
                html.Span("backend/core/consistency.py", className="panel-note"),
            ], className="panel-head"),
            html.Div(
                "These reason across ECU_SPEED, ECU_BRAKE and ECU_STEER "
                "together, so a finding is attributed to the vehicle rather "
                "than to one ECU. None of the four per-ECU rules above ever "
                "reads brake_pressure, which is the gap this stage exists "
                "to close.",
                className="ref-lede",
            ),
            html.Div([
                html.Div([
                    html.Div("Check", className="ref-th"),
                    html.Div("Fires when", className="ref-th"),
                    html.Div("Severity", className="ref-th"),
                    html.Div("Across", className="ref-th"),
                    html.Div("Threat", className="ref-th"),
                ], className="ref-row ref-row--head"),
                *[
                    html.Div([
                        html.Div(c["rule"], className="ref-name num"),
                        html.Div(c["trigger"], className="ref-cell"),
                        html.Div(_sev_tag(c["severity"]), className="ref-cell"),
                        html.Div(c["ecus"], className="ref-cell"),
                        html.Div(_threat_tags(c["threat"]), className="ref-cell ref-cell--threat"),
                    ], className="ref-row")
                    for c in CONSISTENCY_CHECKS
                ],
            ], className="ref-table ref-table--consistency"),
        ], className="panel"),

        html.Div([
            html.Div([
                html.Span("Not covered", className="panel-title"),
                html.Span("docs/TARA.md", className="panel-note"),
            ], className="panel-head"),
            html.Div(
                "A coverage table that only lists what is caught is a "
                "marketing document. These are the open TARA entries.",
                className="ref-lede",
            ),
            html.Div([
                html.Div([
                    html.Span(tid, className="ref-threat"),
                    html.Span(title, className="ref-gap-title"),
                    html.Span(status, className="ref-gap-status"),
                ], className="ref-gap")
                for tid, title, status in COVERAGE_GAPS
            ], className="ref-gaps"),
        ], className="panel"),

    ], id="pane-detection", **{"role": "tabpanel"})


def _evaluation_pane() -> html.Div:
    """Also static, and deliberately stamped. These are recorded results
    from a specific run of a specific script, not a live measurement, and a
    number on a dashboard with no provenance reads as if it were live."""
    return html.Div([

        html.Div([
            html.Div([
                html.Span("Measured detection performance", className="panel-title"),
                html.Span("docs/Evaluation.md §4", className="panel-note"),
            ], className="panel-head"),
            html.Div(EVAL_PROVENANCE, className="ref-lede"),
            html.Div([
                html.Div([
                    html.Span(m["label"], className="stat-label"),
                    html.Span(m["value"], className=f"eval-value num tone--{m['tone']}"),
                    html.Span(m["detail"], className="eval-detail"),
                ], className="eval-tile")
                for m in EVAL_METRICS
            ], className="eval-tiles"),
        ], className="panel"),

        html.Div([
            html.Div([
                html.Span("What the numbers say", className="panel-title"),
                html.Span("the part that is not a pass mark", className="panel-note"),
            ], className="panel-head"),
            html.Div([
                html.Div([
                    html.Div(f["title"], className="finding-type"),
                    html.Div(f["body"], className="finding-detail"),
                ], className=f"finding eval-finding tone--{f['tone']}")
                for f in EVAL_FINDINGS
            ]),
        ], className="panel"),

    ], id="pane-evaluation", **{"role": "tabpanel"})


def build_layout() -> html.Div:
    return html.Div([

        dcc.Interval(id="tick", interval=REFRESH_INTERVAL, n_intervals=0),
        dcc.Interval(id="clock-tick", interval=1000, n_intervals=0),

        # Full alert payload, so the drawer and the overflow modal read
        # detail without re-fetching and without being limited to whatever
        # the stream currently has filtered into view.
        dcc.Store(id="store-alerts", data=[]),

        # One poller writes these; the deck and the command bar read them.
        # Fetching /api/summary inside the deck callback while a second
        # callback wrote the alert store on the same tick made the deck read
        # the previous tick's alerts, so it always trailed the stream by 2s.
        # Both stores land in the same response, so the deck now sees the
        # summary and the alerts that belong together.
        dcc.Store(id="store-summary", data={}),
        dcc.Store(id="store-lstm", data={}),
        dcc.Store(id="store-open-alert", data=None),
        dcc.Store(id="store-filter", data="all"),
        dcc.Store(id="store-sort", data="newest"),
        dcc.Store(id="store-tab", data="live"),
        dcc.Store(id="store-theme", data="light"),

        # Read-only. Nothing here ever navigates; the query string is how a
        # standalone view (?view=detection&solo=1) tells the console which
        # pane to open and to drop the deck.
        dcc.Location(id="url", refresh=False),

        _command_bar(),
        _advisory_deck(),

        # Exactly one pane is ever displayed, so #console-body always holds
        # one element regardless of which tab is up.
        html.Div([
            html.Div([
                _analysis_column(),
                _stream_column(),
            ], id="body-grid", className="pane is-active"),
            _detection_pane(),
            _evaluation_pane(),
        ], id="console-body"),

        html.Div(id="drawer-scrim", n_clicks=0),
        html.Div([
            html.Div([
                html.Span("Alert detail", className="drawer-title"),
                html.Button("\u00d7", id="drawer-close", n_clicks=0,
                            className="drawer-close", **{"aria-label": "Close"}),
            ], className="drawer-head"),
            html.Div(id="drawer-body"),
        ], id="drawer"),

        html.Div(
            html.Div([
                html.Div([
                    html.Span("All flagged ECUs", className="drawer-title"),
                    html.Button("\u00d7", id="modal-close", n_clicks=0,
                                className="drawer-close", **{"aria-label": "Close"}),
                ], className="drawer-head"),
                html.Div(id="modal-grid", className="modal-grid"),
            ], className="modal-box"),
            id="ecu-modal",
        ),

    ], id="console-root", className="")
