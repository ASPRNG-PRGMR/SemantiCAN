"""
Dash callbacks. Reads the Flask API and fills the console.

Contract discipline: every field read below exists in backend/api.py or
backend/api_state.py today. Nothing is invented, and no backend file is
touched by this module.

Three of the endpoints have quirks the UI has to absorb rather than paper
over. They are handled at the point of use and commented there:
  * /api/summary's `last_anomaly` is a feed heartbeat, not an anomaly time.
  * /api/alerts never shrinks, so the stream needs filter and sort.
  * /api/alerts' `ai_analysis` is frozen at alert-creation time.
"""

import re
from datetime import datetime, timezone
from urllib.parse import parse_qs

import dash
import requests
from dash import Input, Output, State, html, ALL, ctx

import plotly.graph_objects as go

from frontend.dashboard.layout import SEVERITY_FILTERS, SORT_ORDERS, TABS

# A pure data module: a dict, a role table and three lookups, no side
# effects and no imports of its own. Reading it is how the console can say
# what an ECU *is* instead of only what it scored. The alternative was a
# seventh API round trip per poll for data that never changes at runtime.
from backend.core.ecu_registry import describe_ecu
from frontend.config import (
    API_BASE,
    MAX_ANOMALOUS_TRACES,
    MAX_DECK_CHIPS,
    ANOMALY_THRESHOLD,
    FEED_STALE_AFTER,
    FEED_DOWN_AFTER,
)

# ── Shared vocabulary ────────────────────────────────────────────────────

SEV_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}

# Inline styles point at the CSS custom properties rather than at literal
# hex, so a theme switch moves them without Python being involved at all.
# The palette lives in exactly one place, assets/style.css.
SEV_COLOR = {
    "nominal":  "var(--sev-nominal)",
    "low":      "var(--sev-low)",
    "medium":   "var(--sev-medium)",
    "high":     "var(--sev-high)",
    "critical": "var(--sev-critical)",
}

# Sentence case, not shouted caps. The colour already carries the urgency;
# setting the word in caps as well is just the same signal twice.
TIER_WORD = {
    "nominal":  "All ECUs nominal",
    "low":      "Low concern",
    "medium":   "Elevated",
    "high":     "High",
    "critical": "Critical",
}

DETECTOR_COLOR = {
    "rule":    "var(--det-rule)",
    "lstm":    "var(--det-lstm)",
    "both":    "var(--det-both)",
    "unknown": "var(--det-unknown)",
}
DETECTOR_WORD = {
    "rule":    "Physics rules",
    "lstm":    "LSTM",
    "both":    "Both engines",
    "unknown": "Unattributed",
}

# Plotly is the one place that cannot take a CSS variable: a figure is data,
# and it is serialised to JSON before any stylesheet exists. So the chart
# keeps a literal palette per theme, and the theme is passed in as a
# callback input. These values mirror the tokens in style.css by hand, which
# is the one duplication the theming could not avoid.
CHART = {
    "light": {
        "font":    "#4a5466",
        "grid":    "#d5dbe6",
        "line":    "#c8d0de",
        "hover":   "#f7f9fc",
        "hover_b": "#d5dbe6",
        "hover_f": "#161b26",
        "muted":   "#7a8497",
        "band":    "rgba(107,116,136,0.18)",
        "mean":    "#6b7488",
        "thresh":  "#b9c2d1",
        "traces":  ["#c22a30", "#b8531c", "#9a6a0d", "#6f47bd", "#2a66b8"],
    },
    "dark": {
        "font":    "#a3adc0",
        "grid":    "#1e2431",
        "line":    "#242b39",
        "hover":   "#1e2431",
        "hover_b": "#2a3140",
        "hover_f": "#e9edf5",
        "muted":   "#737d92",
        "band":    "rgba(95,106,128,0.16)",
        "mean":    "#5f6a80",
        "thresh":  "#3a4354",
        "traces":  ["#e5484d", "#e2733c", "#d99b2b", "#9d7ce8", "#4a8fe0"],
    },
}

MONO_STACK = ('ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, '
              "monospace")


def _chart(theme):
    return CHART.get(theme if theme in CHART else "light")


def _get(endpoint: str, fallback=None):
    try:
        r = requests.get(f"{API_BASE}{endpoint}", timeout=2)
        r.raise_for_status()
        return r.json()
    except Exception:
        return fallback


def _tier(risk: float) -> str:
    """Mirrors the thresholds in backend/ai/advisor.py's generate_advisory,
    so the word beside the gauge never contradicts the narrative under it."""
    if risk >= 80:
        return "critical"
    if risk >= 60:
        return "high"
    if risk >= 40:
        return "medium"
    if risk > 0:
        return "low"
    return "nominal"


def _parse_ts(value):
    """Alert timestamps are `datetime.utcnow().isoformat() + 'Z'`; the
    summary heartbeat is a bare naive isoformat. Both are UTC. Normalise so
    they can be compared and aged."""
    if not value:
        return None
    try:
        text = value[:-1] if value.endswith("Z") else value
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _clock(value) -> str:
    dt = _parse_ts(value)
    return dt.strftime("%H:%M:%S") if dt else "--:--:--"


def _ecu_label(node_id: str) -> str:
    """`VEHICLE_CONSISTENCY::a+b` is a synthetic dedup key from
    backend/main.py, not a real ECU. Render it as what it is."""
    if node_id.startswith("VEHICLE_CONSISTENCY::"):
        kinds = node_id.split("::", 1)[1].replace("+", ", ").replace("_", " ")
        return f"Cross-ECU: {kinds}"
    return node_id


def _ecu_tip(node_id: str, score=None) -> str:
    """Hover text for an ECU chip or meter.

    Deliberately reports the difference between "criticality 2" and "nobody
    has classified this ECU": 120 of the 123 ids the simulator publishes are
    absent from the registry and fall through to the default weight. Saying
    "criticality 2" alone would present that gap as a finding."""
    info = describe_ecu(node_id or "")
    lines = [info["ecu_id"]]

    if info["role"]:
        lines.append(info["role"])
    else:
        lines.append("Unclassified — no registry entry")

    weight = info["weight"]
    if info["registered"]:
        lines.append(f"Criticality {weight} of 5")
    else:
        lines.append(f"Criticality {weight} of 5 (registry default)")

    if score is not None:
        lines.append(f"Last score {float(score):.1f}")
    return "\n".join(lines)


def _is_cross_ecu(node_id: str) -> bool:
    return node_id.startswith("VEHICLE_CONSISTENCY")


def _violation_types(alert: dict):
    out = []
    for v in alert.get("violations", []):
        kind = v.get("type") if isinstance(v, dict) else str(v)
        if kind and kind not in out:
            out.append(kind)
    return out


def _pretty(kind: str) -> str:
    return kind.replace("_", " ")


# `generate_advisory` in backend/ai/advisor.py builds one deterministic
# string out of five parts, and four of them restate something the deck is
# already showing an inch away: the level is the headline, the risk score is
# the gauge, the ECU list is the Flagged chip row, and the violation list is
# the Violations chip row. Rendering all of it costs six lines of prose to
# say what the panel around it already says, and buries the one part that is
# not duplicated anywhere — the recommended response.
#
# Parsed, not reformatted upstream: backend/ is not modified by this
# frontend, and the raw string is still shown verbatim in the alert drawer,
# so nothing is lost, it just stops being the loudest thing on the page.
_ADVISORY_RE = re.compile(
    r"^\[(?P<level>[A-Z]+)\]\s*"
    r"Vehicle risk\s*(?P<risk>[\d.]+)\s*/\s*100\s*\((?P<mode>[^)]*)\)\.\s*"
    r"Anomalous ECUs:.*?\.\s*"
    r"Detected violations:.*?\.\s*"
    r"(?P<action>.+?)\s*"
    r"\[Local LSTM advisor[^\]]*\]\s*$",
    re.S,
)


def _advisory_parts(text: str):
    """(lines, scoring_mode, parsed).

    `parsed` is False for anything that does not match the known template —
    including the `[Advisory unavailable: ...]` string alerts.py substitutes
    when the advisor raises. In that case the text is passed through
    untouched rather than silently mangled by a half-matching regex."""
    text = (text or "").strip()
    m = _ADVISORY_RE.match(text)
    if not m:
        return [text], None, False

    action = " ".join(m.group("action").split())
    lines = [x.strip() for x in re.findall(r"[^.]+\.", action) if x.strip()]
    if not lines:
        return [text], None, False
    return lines, (m.group("mode") or "").strip() or None, True


def _triggered_ids() -> set:
    """Every component id that changed in this request, not just the first.

    `ctx.triggered_id` reports one id, and Dash batches simultaneous prop
    changes into a single call. A click on a close button that lands in the
    same batch as the 2s poll rebuilding `chip-more` or the alert cards can
    therefore be reported second and never acted on — the overlay stays
    open and the click looks lost. Prop names contain no dots, so the last
    one separates the id from the prop even for pattern-matching ids."""
    return {t["prop_id"].rsplit(".", 1)[0] for t in (ctx.triggered or [])}


def _newest_alert(alerts: list):
    if not alerts:
        return None
    return max(
        alerts,
        key=lambda a: _parse_ts(a.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
    )


TIE_EPSILON = 0.5      # scores this close count as the same score
MAX_TOP_METERS = 3     # meters that fit without the well scrolling


def _top_ecu_panel(by_ecu: dict):
    """Meters when the scores separate, a count when they do not.

    /api/top-anomalous-ecus sorts by (risk, last_seen) and caps at three, so
    when a large number of ECUs sit at the ceiling together — 28 of them at
    100.0 is normal once the LSTM is warm — the "top three" is just whichever
    three reported most recently. It reshuffles on every poll and ranks
    nothing. A tie is a fact about the fleet, so the panel states it."""
    last = {eid: rows[-1]["confidence"] for eid, rows in by_ecu.items() if rows}
    flagged = {e: v for e, v in last.items() if v >= ANOMALY_THRESHOLD}

    if not flagged:
        return html.Div("None above threshold", className="empty-note",
                        style={"justifyContent": "flex-start", "padding": "0"})

    ceiling = max(flagged.values())
    tied = [e for e, v in flagged.items() if v >= ceiling - TIE_EPSILON]

    if len(tied) <= MAX_TOP_METERS:
        ranked = sorted(flagged.items(), key=lambda kv: kv[1], reverse=True)
        return [
            html.Div([
                html.Div([
                    html.Span(_ecu_label(eid), className="meter-name"),
                    html.Span(f"{score:.0f}", className="meter-value"),
                ], className="meter-head"),
                html.Div(
                    html.Div(className="meter-fill", style={
                        "width": f"{min(score, 100):.0f}%",
                        "background": SEV_COLOR[_tier(score)],
                    }),
                    className="meter-track",
                ),
            ], className="meter", **{"data-tip": _ecu_tip(eid, score)})
            for eid, score in ranked[:MAX_TOP_METERS]
        ]

    # Tied. Rank by criticality instead, which is the only axis left that
    # still separates them — and say plainly when it does not separate them
    # either, which is the usual case while 120 of 123 ECUs are unregistered.
    critical = sorted(
        (e for e in tied if describe_ecu(e)["weight"] >= 4),
        key=lambda e: (-describe_ecu(e)["weight"], e),
    )

    body = [
        html.Div([
            html.Span(f"{len(tied)}", className="tie-count num"),
            html.Span(f"at {ceiling:.0f}", className="tie-scale"),
        ], className="tie-head"),
        html.Div("All at the ceiling — score no longer ranks them.",
                 className="tie-note"),
    ]

    if critical:
        body.append(html.Div([
            html.Div("Safety-critical", className="tie-label"),
            html.Div(
                [html.Span(_ecu_label(e), className="chip",
                           **{"data-tip": _ecu_tip(e, last[e])})
                 for e in critical[:6]],
                className="tie-chips",
            ),
        ], className="tie-critical"))
    else:
        body.append(html.Div(
            "None of them is registered as safety-critical.",
            className="tie-note tie-note--dim"))

    return html.Div(body, className="tie-well")


# ── Registration ─────────────────────────────────────────────────────────

def register_callbacks(app):

    # ── Poll once, fan out ───────────────────────────────────────────────
    # One request per endpoint per tick, into stores that every downstream
    # panel reads. Two things depend on this being a single callback:
    #
    #   * The deck used to fetch /api/summary itself while taking the alert
    #     store as State. Both fired on the same tick, so the State it read
    #     was the *previous* tick's alerts and the deck trailed the stream
    #     by one poll. Summary and alerts now land in one response, so
    #     everything the deck shows describes the same moment.
    #   * /api/summary was being fetched twice a tick, once here and once in
    #     the command-bar callback.
    #
    # A failed fetch is not an empty result. `ok: False` is what lets the
    # deck say "no reading" instead of "all clear", and the alert store is
    # deliberately left untouched so a dropped request does not wipe the
    # board mid-incident.
    @app.callback(
        Output("store-alerts", "data"),
        Output("store-summary", "data"),
        Output("store-lstm", "data"),
        Input("tick", "n_intervals"),
        State("store-alerts", "data"),
    )
    def poll(_, previous):
        summary = _get("/api/summary", None)
        alerts  = _get("/api/alerts", None)
        lstm    = _get("/api/lstm-status", None)

        # Rewriting the store with an equal payload still replaces every
        # card in the stream, and a rebuilt card comes back with n_clicks at
        # 0. A click that lands between the rebuild and its own round trip
        # is simply lost, which is why the drawer stops opening once alerts
        # accumulate. Holding the store still when nothing changed removes
        # that whole class of lost click while the board is settled.
        #
        # It does not remove it while alerts are genuinely arriving every
        # tick — that needs the stream to stop rebuilding rows that did not
        # change, which is a larger piece of work.
        if alerts is None or alerts == previous:
            alerts_out = dash.no_update
        else:
            alerts_out = alerts

        return (
            alerts_out,
            {"ok": summary is not None, "data": summary or {}},
            {"ok": lstm is not None, "data": lstm or {}},
        )

    # ── Advisory deck ────────────────────────────────────────────────────
    @app.callback(
        Output("advisory-deck", "className"),
        Output("deck-tier", "children"),
        Output("deck-tier", "style"),
        Output("deck-stamp", "children"),
        Output("deck-narrative", "children"),
        Output("deck-narrative", "className"),
        Output("deck-chip-row", "children"),
        Output("chip-more", "children"),
        Output("chip-more", "style"),
        Output("deck-violation-row", "children"),
        Output("chip-line-flagged", "style"),
        Output("chip-line-violations", "style"),
        Output("risk-feed", "data-risk"),
        Output("stat-active", "children"),
        Output("stat-anomalous", "children"),
        Output("stat-alerts", "children"),
        Output("stat-feed", "children"),
        Input("store-summary", "data"),
        Input("store-alerts", "data"),
    )
    def update_deck(summary_store, alerts):
        summary_store = summary_store or {}
        online = bool(summary_store.get("ok"))
        summary = summary_store.get("data") or {}
        alerts = alerts or []

        # Losing the backend is not the same as a clean vehicle, and the
        # largest element on the page must not say so. The stream below is
        # still showing the last alerts that arrived, so the count stays
        # real; every field that came from the dead summary reads as absent.
        if not online:
            return (
                "deck--offline",
                "No reading",
                {"color": "var(--ink-low)"},
                "",
                (f"The console cannot reach the API at {API_BASE}. Nothing on this "
                 "page is current and the risk score is the last value received, "
                 "not a live one. This is not an all-clear: an anomaly raised "
                 "while the feed is down will not appear here."),
                "deck-narrative",
                [], "", {"display": "none"}, [],
                {"display": "none"}, {"display": "none"},
                "",                       # motion.js holds the gauge where it is
                "--",
                "--",
                str(len(alerts)),
                "--:--:--",
            )

        risk = float(summary.get("vehicle_risk") or 0.0)
        tier = _tier(risk)

        newest = _newest_alert(alerts)

        # `ai_analysis` is generated once, when the alert is created, and
        # never refreshed. Showing it without saying when it was written
        # would let a stale narrative read as a live assessment, so it is
        # always stamped with its own alert's timestamp.
        if newest and newest.get("ai_analysis"):
            lines, mode, parsed = _advisory_parts(newest["ai_analysis"])
            if parsed:
                narrative = [html.Div(line, className="advice-line")
                             for line in lines]
                narrative_class = "deck-narrative deck-advice"
            else:
                narrative = lines[0]
                narrative_class = "deck-narrative"
            stamp = [
                "written ",
                html.Span(_clock(newest.get("timestamp")), className="num"),
                " for ",
                html.Span(_ecu_label(newest.get("node_id", "")), className="num"),
            ]
            # Whether the model was trained *at the time this advisory was
            # written* is not something the command bar can tell you: that
            # badge shows the model's state now, and `ai_analysis` is frozen
            # at alert-creation time.
            if mode:
                stamp += [" · ", html.Span(mode, className="advice-mode")]
        elif alerts:
            narrative = "Alerts are open but no advisory has been generated for them."
            narrative_class = "deck-narrative is-empty"
            stamp = ""
        else:
            narrative = ("No semantic inconsistencies detected. Physics rules, the "
                         "LSTM baseline and the cross-ECU consistency engine are all "
                         "reporting clean.")
            narrative_class = "deck-narrative is-empty"
            stamp = ""

        # Chips: which ECUs, and which violation kinds, in one glance.
        # Ranked, not alphabetical. Only MAX_DECK_CHIPS fit, so the ones
        # that fit have to be the ones that matter: sorting by name puts
        # ECU_003 in front of ECU_SPEED and hides the actual incident
        # behind a "+20 more" button.
        by_id: dict = {}
        for a in alerts:
            nid = a.get("node_id")
            if not nid:
                continue
            rank = (
                1 if _is_cross_ecu(nid) else 0,          # cross-ECU findings first:
                                                          # ecu_registry weights them 5
                SEV_RANK.get(a.get("severity", "low"), 0),
                a.get("confidence", 0),
            )
            if nid not in by_id or rank > by_id[nid]:
                by_id[nid] = rank
        ecu_ids = sorted(by_id, key=lambda n: (by_id[n], n), reverse=True)

        kinds = sorted({k for a in alerts for k in _violation_types(a)})

        shown = ecu_ids[:MAX_DECK_CHIPS]
        chip_row = [
            html.Span(
                _ecu_label(e),
                className="chip chip-cross" if _is_cross_ecu(e) else "chip",
                **{"data-tip": _ecu_tip(e)},
            )
            for e in shown
        ]

        overflow = len(ecu_ids) - len(shown)
        more_label = f"{overflow} more" if overflow > 0 else ""
        more_style = {} if overflow > 0 else {"display": "none"}

        violation_row = [
            html.Span(_pretty(k), className="chip chip-violation") for k in kinds
        ]

        flagged_style = {} if ecu_ids else {"display": "none"}
        violations_style = {} if kinds else {"display": "none"}

        # This is semantic_history[-1].timestamp: the newest frame from any
        # ECU. A heartbeat, not an anomaly time. Labelled "Last frame".
        heartbeat = _clock(summary.get("last_anomaly"))

        return (
            f"deck--{tier}",
            TIER_WORD[tier],
            {"color": SEV_COLOR[tier]},
            stamp,
            narrative,
            narrative_class,
            chip_row,
            more_label,
            more_style,
            violation_row,
            flagged_style,
            violations_style,
            f"{risk:.1f}",
            str(summary.get("active_ecus", 0)),
            str(summary.get("anomalous_ecus", 0)),
            str(len(alerts)),
            heartbeat,
        )

    # ── Feed liveness + LSTM state + clock ───────────────────────────────
    @app.callback(
        Output("feed-group", "className"),
        Output("feed-stamp", "children"),
        Output("feed-stamp", "data-stamp"),
        Output("lstm-group", "className"),
        Output("lstm-text", "children"),
        # The tick is kept as a trigger so the feed keeps ageing towards
        # stale and down even when the summary itself stops changing, which
        # is exactly what happens when the producer freezes but the API
        # still answers.
        Input("tick", "n_intervals"),
        Input("store-summary", "data"),
        Input("store-lstm", "data"),
    )
    def update_status(_, summary_store, lstm_store):
        summary_store = summary_store or {}
        summary = summary_store.get("data") or {}
        raw = summary.get("last_anomaly") if summary_store.get("ok") else None
        beat = _parse_ts(raw)

        if beat is None:
            feed_class, shown = "bar-group feed-down", "no signal"
        else:
            age = (datetime.now(timezone.utc) - beat).total_seconds()
            shown = beat.strftime("%H:%M:%S")
            if age > FEED_DOWN_AFTER:
                feed_class = "bar-group feed-down"
            elif age > FEED_STALE_AFTER:
                feed_class = "bar-group feed-stale"
            else:
                feed_class = "bar-group feed-live"

        # /api/lstm-status returns {"error": ...} with HTTP 500 if the
        # advisor cannot be imported, so a missing `trained` key is not the
        # same thing as "not trained yet". Three states, not two.
        lstm_store = lstm_store or {}
        status = lstm_store.get("data") if lstm_store.get("ok") else None
        if not status or "error" in status:
            lstm_class, lstm_text = "bar-group lstm-fault", "Model unavailable"
        elif status.get("trained"):
            steps = status.get("train_steps", 0)
            lstm_class = "bar-group lstm-ready"
            lstm_text = f"Model ready ({steps} steps)"
        else:
            samples = status.get("samples", 0)
            lstm_class = "bar-group lstm-training"
            lstm_text = f"Model training ({samples} samples)"

        return feed_class, shown, str(raw or ""), lstm_class, lstm_text

    @app.callback(Output("clock", "children"), Input("clock-tick", "n_intervals"))
    def update_clock(_):
        return datetime.now(timezone.utc).strftime("%H:%M:%S") + " UTC"

    # ── Confidence history ───────────────────────────────────────────────
    @app.callback(
        Output("chart-confidence", "figure"),
        Output("chart-note", "children"),
        # Folded in here rather than kept as its own callback: this panel
        # needs the per-ECU last score for every ECU, which is exactly what
        # /api/semantic-history was already being fetched for. As a separate
        # callback it meant pulling the largest payload on the page twice
        # per tick.
        Output("top-ecus", "children"),
        Input("tick", "n_intervals"),
        # A theme change has to redraw the figure, because Plotly bakes its
        # colours into the serialised trace rather than reading them from
        # the stylesheet the way everything else on the page does.
        Input("store-theme", "data"),
    )
    def update_confidence(_, theme):
        data = _get("/api/semantic-history", None)
        c = _chart(theme)

        fig = go.Figure()
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=c["font"], size=11, family=MONO_STACK),
            margin=dict(l=42, r=14, t=6, b=34),
            hovermode="x unified",
            hoverlabel=dict(bgcolor=c["hover"], bordercolor=c["hover_b"],
                            font=dict(color=c["hover_f"], size=11)),
            showlegend=False,
            # Keeps zoom/pan and trace identity across the 2s poll so Plotly
            # morphs the traces instead of tearing the whole plot down.
            uirevision="semantic-history",
            transition=dict(duration=420, easing="cubic-in-out"),
            xaxis=dict(showgrid=False, zeroline=False, linecolor=c["line"],
                       tickcolor=c["line"], nticks=7, tickangle=0),
            yaxis=dict(range=[0, 104], gridcolor=c["grid"], zeroline=False,
                       linecolor=c["line"], tickcolor=c["line"], dtick=25),
        )

        if not data:
            note = "Backend unreachable" if data is None else "Waiting for telemetry"
            fig.add_annotation(text=note, showarrow=False,
                               font=dict(color=c["muted"], size=12))
            return fig, "", html.Div(note, className="empty-note",
                                     style={"justifyContent": "flex-start",
                                            "padding": "0"})

        by_ecu: dict = {}
        for row in data:
            by_ecu.setdefault(row["node_id"], []).append(row)
        for key in by_ecu:
            by_ecu[key] = sorted(by_ecu[key], key=lambda r: r["timestamp"])[-24:]

        anomalous = [k for k, rows in by_ecu.items()
                     if rows and rows[-1]["confidence"] >= ANOMALY_THRESHOLD]
        normal = [k for k in by_ecu if k not in anomalous]

        # ~117 normal ECUs collapsed into a min/max envelope with a mean
        # line through it. Drawing them individually is 117 near-identical
        # lines: it hides the handful of traces that actually matter.
        if normal:
            buckets: dict = {}
            for eid in normal:
                for r in by_ecu[eid]:
                    buckets.setdefault(r["timestamp"][11:19], []).append(r["confidence"])
            times = sorted(buckets)
            lows = [min(buckets[t]) for t in times]
            highs = [max(buckets[t]) for t in times]
            means = [sum(buckets[t]) / len(buckets[t]) for t in times]

            fig.add_trace(go.Scatter(
                x=times, y=highs, mode="lines", line=dict(width=0),
                hoverinfo="skip", showlegend=False, name="",
            ))
            fig.add_trace(go.Scatter(
                x=times, y=lows, mode="lines", line=dict(width=0),
                fill="tonexty", fillcolor=c["band"],
                hoverinfo="skip", showlegend=False, name="",
            ))
            fig.add_trace(go.Scatter(
                x=times, y=means, mode="lines",
                line=dict(color=c["mean"], width=1.4),
                name=f"Normal ({len(normal)})",
                hovertemplate="normal mean %{y:.0f}<extra></extra>",
            ))

        ranked = sorted(anomalous,
                        key=lambda k: by_ecu[k][-1]["confidence"],
                        reverse=True)[:MAX_ANOMALOUS_TRACES]

        for i, eid in enumerate(ranked):
            rows = by_ecu[eid]
            fig.add_trace(go.Scatter(
                x=[r["timestamp"][11:19] for r in rows],
                y=[r["confidence"] for r in rows],
                mode="lines",
                line=dict(color=c["traces"][i % len(c["traces"])],
                          width=2, shape="spline", smoothing=0.4),
                name=_ecu_label(eid),
                hovertemplate="%{fullData.name} %{y:.0f}<extra></extra>",
            ))

        fig.add_hline(y=ANOMALY_THRESHOLD,
                      line=dict(color=c["thresh"], width=1, dash="dot"))

        overflow = len(anomalous) - len(ranked)
        if overflow > 0:
            note = f"{len(ranked)} of {len(anomalous)} flagged shown"
        elif anomalous:
            note = f"{len(anomalous)} flagged, {len(normal)} in band"
        else:
            note = f"{len(normal)} ECUs in band"

        return fig, note, _top_ecu_panel(by_ecu)

    # ── Violation rate ───────────────────────────────────────────────────
    # HTML bars rather than Plotly. Six values do not need a plotting
    # library, and a CSS height transition glides between polls where a
    # Plotly redraw snaps.
    @app.callback(Output("rate-chart", "children"), Input("tick", "n_intervals"))
    def update_rate(_):
        buckets = _get("/api/violation-rate", None)
        if not buckets:
            return html.Div(
                "Backend unreachable" if buckets is None else "No data yet",
                className="empty-note",
            )

        peak = max((b.get("count", 0) for b in buckets), default=0) or 1

        cols = []
        for b in buckets:
            count = b.get("count", 0)
            height = (count / peak) * 100 if count else 0
            cols.append(html.Div([
                html.Div(
                    html.Div(
                        className="rate-fill has-hits" if count else "rate-fill",
                        style={"height": f"{height:.1f}%"},
                    ),
                    className="rate-track",
                ),
                html.Span(str(count), className="rate-count"),
                html.Span(b.get("time", "")[3:], className="rate-time"),
            ], className="rate-col"))
        return cols

    # ── Detector attribution ─────────────────────────────────────────────
    @app.callback(
        Output("detector-body", "children"),
        Output("detector-note", "children"),
        Input("tick", "n_intervals"),
    )
    def update_detector(_):
        counts = _get("/api/detector-breakdown", None)
        if counts is None:
            return html.Div("Backend unreachable", className="empty-note"), ""

        total = sum(counts.get(k, 0) for k in ("rule", "lstm", "both", "unknown"))

        if not total:
            return html.Div("No open alerts", className="empty-note"), ""

        # A segmented bar rather than a donut. At this panel size a donut is
        # mostly hole, its labels need a legend anyway, and a width tween
        # reads far more clearly than an animated arc.
        segs, rows = [], []
        for key in ("rule", "lstm", "both", "unknown"):
            n = counts.get(key, 0)
            if not n:
                continue
            segs.append(html.Div(
                className="seg",
                style={"width": f"{n / total * 100:.2f}%",
                       "background": DETECTOR_COLOR[key]},
            ))
            rows.append(html.Div([
                html.Span(className="seg-swatch",
                          style={"background": DETECTOR_COLOR[key]}),
                html.Span(DETECTOR_WORD[key], className="seg-name"),
                html.Span(str(n), className="seg-count num"),
            ], className="seg-legend-row"))

        return (
            [html.Div(segs, className="seg-bar"),
             html.Div(rows, className="seg-legend")],
            f"{total} open",
        )

    # ── Alert stream ─────────────────────────────────────────────────────
    @app.callback(
        Output("stream-scroll", "children"),
        Output("stream-note", "children"),
        Input("store-alerts", "data"),
        Input("store-filter", "data"),
        Input("store-sort", "data"),
    )
    def update_stream(alerts, floor, order):
        alerts = alerts or []
        total = len(alerts)

        if floor and floor != "all":
            cutoff = SEV_RANK.get(floor, 0)
            alerts = [a for a in alerts
                      if SEV_RANK.get(a.get("severity", "low"), 0) >= cutoff]

        if not alerts:
            msg = ("No open alerts." if floor in (None, "all")
                   else "Nothing at this severity. Widen the filter to see the rest.")
            return html.Div(msg, className="empty-note"), f"0 of {total}"

        epoch = datetime.min.replace(tzinfo=timezone.utc)
        if order == "severity":
            alerts = sorted(
                alerts,
                key=lambda a: (SEV_RANK.get(a.get("severity", "low"), 0),
                               a.get("confidence", 0)),
                reverse=True,
            )
        elif order == "confidence":
            alerts = sorted(alerts, key=lambda a: a.get("confidence", 0), reverse=True)
        else:
            alerts = sorted(alerts,
                            key=lambda a: _parse_ts(a.get("timestamp")) or epoch,
                            reverse=True)

        cards = []
        for a in alerts:
            sev = a.get("severity", "low")
            node = a.get("node_id", "")
            det = a.get("detector", "unknown")
            kinds = _violation_types(a)

            meta = [
                html.Span(sev, className="tag tag-sev"),
                html.Span(DETECTOR_WORD.get(det, det), className=f"tag tag-det-{det}"),
            ]
            if kinds:
                meta.append(html.Span(_pretty(kinds[0]), className="tag"))
                if len(kinds) > 1:
                    meta.append(html.Span(f"+{len(kinds) - 1}", className="tag"))
            meta.append(html.Span(_clock(a.get("timestamp")), className="alert-time num"))

            cards.append(html.Button([
                html.Div([
                    html.Span(_ecu_label(node), className="alert-node"),
                    html.Span(f"{a.get('confidence', 0):.0f}", className="alert-conf"),
                ], className="alert-top"),
                html.Div(meta, className="alert-meta"),
            ],
                id={"type": "alert-card", "index": a.get("alert_id", node)},
                n_clicks=0,
                className=f"alert-card sev--{sev}",
                # motion.js keys arrival and escalation off these two, which
                # is how an entry animation survives a wholesale re-render
                # without re-firing every 2 seconds.
                **{"data-alert-id": a.get("alert_id", node), "data-severity": sev},
            ))

        note = str(total) if len(cards) == total else f"{len(cards)} of {total}"
        return cards, note

    # ── Segmented controls ───────────────────────────────────────────────
    # Two nearly identical callbacks rather than one generic one: Dash
    # resolves pattern-matching Inputs per `type`, so a shared handler would
    # have to guess which group fired and could not set both groups' classes
    # without them fighting over each other's outputs.
    @app.callback(
        Output("store-filter", "data"),
        Output({"type": "filter-severity", "index": ALL}, "className"),
        Output({"type": "filter-severity", "index": ALL}, "aria-pressed"),
        Input({"type": "filter-severity", "index": ALL}, "n_clicks"),
        State("store-filter", "data"),
    )
    def set_filter(_clicks, current):
        chosen = current or "all"
        trigger = ctx.triggered_id
        if isinstance(trigger, dict):
            chosen = trigger["index"]
        values = [v for v, _ in SEVERITY_FILTERS]
        return (
            chosen,
            ["seg-button is-active" if v == chosen else "seg-button" for v in values],
            ["true" if v == chosen else "false" for v in values],
        )

    @app.callback(
        Output("store-sort", "data"),
        Output({"type": "sort-order", "index": ALL}, "className"),
        Output({"type": "sort-order", "index": ALL}, "aria-pressed"),
        Input({"type": "sort-order", "index": ALL}, "n_clicks"),
        State("store-sort", "data"),
    )
    def set_sort(_clicks, current):
        chosen = current or "newest"
        trigger = ctx.triggered_id
        if isinstance(trigger, dict):
            chosen = trigger["index"]
        values = [v for v, _ in SORT_ORDERS]
        return (
            chosen,
            ["seg-button is-active" if v == chosen else "seg-button" for v in values],
            ["true" if v == chosen else "false" for v in values],
        )

    # ── Drawer ───────────────────────────────────────────────────────────
    @app.callback(
        Output("store-open-alert", "data"),
        Input({"type": "alert-card", "index": ALL}, "n_clicks"),
        Input("drawer-close", "n_clicks"),
        Input("drawer-scrim", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_drawer(card_clicks, _close, _scrim):
        trigger = ctx.triggered_id
        # Same batching hazard as the modal: a close or scrim click can
        # arrive alongside the poll that rebuilds every alert card.
        if {"drawer-close", "drawer-scrim"} & _triggered_ids():
            return None
        if isinstance(trigger, dict) and trigger.get("type") == "alert-card":
            # Dash fires this callback whenever the card list is rebuilt, so
            # ignore triggers where the click count is still zero.
            clicks = card_clicks if isinstance(card_clicks, (list, tuple)) else [card_clicks]
            if not any(c for c in clicks if c):
                return dash.no_update
            return trigger["index"]
        return dash.no_update

    @app.callback(
        Output("drawer", "className"),
        Output("drawer-scrim", "className"),
        Output("drawer-body", "children"),
        Input("store-open-alert", "data"),
        State("store-alerts", "data"),
    )
    def render_drawer(alert_id, alerts):
        if not alert_id:
            return "", "", None

        alert = next((a for a in (alerts or []) if a.get("alert_id") == alert_id), None)
        if alert is None:
            return "", "", None

        sev = alert.get("severity", "low")
        node = alert.get("node_id", "")
        det = alert.get("detector", "unknown")
        conf = float(alert.get("confidence", 0) or 0)
        info = describe_ecu(node)

        # The identity of the thing that fired is a headline, not a row in a
        # key/value table. Previously "Source / ECU_038" was the first of six
        # equally-weighted rows, so the drawer opened with no focal point and
        # the reader had to assemble the answer out of a grid.
        head = html.Div([
            html.Div([
                html.Span(_ecu_label(node), className="dr-ecu"),
                html.Span(sev, className="dr-sev",
                          style={"color": SEV_COLOR.get(sev)}),
            ], className="dr-title-row"),
            html.Div(info["role"] or "Unclassified — no registry entry",
                     className="dr-role"),
            html.Div([
                html.Div([
                    html.Span("Confidence", className="dr-metric-label"),
                    html.Span(f"{conf:.1f}", className="dr-metric-value num"),
                    html.Span("of 100", className="dr-metric-scale"),
                ], className="dr-metric-head"),
                html.Div(
                    html.Div(className="meter-fill", style={
                        "width": f"{min(conf, 100):.0f}%",
                        "background": SEV_COLOR[_tier(conf)],
                    }),
                    className="meter-track",
                ),
            ], className="dr-conf"),
        ], className="dr-head")

        facts = html.Div([
            html.Div([
                html.Span("Caught by", className="dr-fact-key"),
                html.Span(DETECTOR_WORD.get(det, det), className="dr-fact-val",
                          style={"color": DETECTOR_COLOR.get(det)}),
            ], className="dr-fact"),
            html.Div([
                html.Span("Raised", className="dr-fact-key"),
                html.Span(_clock(alert.get("timestamp")) + " UTC",
                          className="dr-fact-val num"),
            ], className="dr-fact"),
            html.Div([
                html.Span("Criticality", className="dr-fact-key"),
                html.Span(
                    f"{info['weight']} of 5" if info["registered"]
                    else f"{info['weight']} of 5 · registry default",
                    className="dr-fact-val",
                ),
            ], className="dr-fact"),
        ], className="dr-facts")

        findings = []
        for v in alert.get("violations", []):
            if not isinstance(v, dict):
                findings.append(html.Div(str(v), className="finding"))
                continue
            block = [
                html.Div([
                    html.Span(_pretty(v.get("type", "unknown")), className="finding-type"),
                    html.Span(v.get("severity", ""), className="tag",
                              style={"color": SEV_COLOR.get(v.get("severity"), "")}),
                ], className="finding-top"),
            ]
            # `detail` and `ecus` are only present on cross-ECU findings from
            # backend/core/consistency.py. Per-ECU rule violations from
            # checks.py carry type and severity only.
            if v.get("detail"):
                block.append(html.Div(v["detail"], className="finding-detail"))
            if v.get("ecus"):
                block.append(html.Div(
                    [html.Span("Correlated across ", className="finding-ecus")] +
                    [html.Span(e, className="chip tip-below",
                               **{"data-tip": _ecu_tip(e)}) for e in v["ecus"]],
                    className="finding-ecu-row"))
            findings.append(html.Div(block, className="finding"))

        if not findings:
            findings = [html.Div(
                "No rule violations recorded. This alert was raised by the LSTM "
                "on reconstruction error alone.",
                className="finding-detail",
            )]

        body = [
            head,
            facts,
            html.Div([
                html.Div("Findings", className="drawer-section-title"),
                *findings,
            ], className="drawer-section"),
        ]

        if alert.get("ai_analysis"):
            lines, mode, parsed = _advisory_parts(alert["ai_analysis"])
            written = _clock(alert.get("timestamp"))
            title = f"Advisory, written {written} UTC"
            if mode:
                title += f" · {mode}"
            body.append(html.Div([
                html.Div(title, className="drawer-section-title"),
                html.Div(
                    [html.Div(l, className="advice-line") for l in lines]
                    if parsed else lines[0],
                    className=("drawer-narrative deck-advice" if parsed
                               else "drawer-narrative"),
                ),
            ], className="drawer-section"))

        # The alert id is a correlation key for a log grep, not something a
        # reader needs at eye level. It was the sixth row of the old table.
        body.append(html.Div([
            html.Span("Alert id ", className="dr-fact-key"),
            html.Span(alert.get("alert_id", ""), className="num"),
        ], className="dr-footer"))

        return "open", "open", body

    # ── ECU overflow modal ───────────────────────────────────────────────
    @app.callback(
        Output("ecu-modal", "className"),
        Output("modal-grid", "children"),
        Input("chip-more", "n_clicks"),
        Input("modal-close", "n_clicks"),
        State("store-alerts", "data"),
        prevent_initial_call=True,
    )
    def toggle_modal(open_clicks, _close, alerts):
        if "modal-close" in _triggered_ids():
            return "", dash.no_update

        # update_deck rebuilds the chip row on every poll, and the fresh
        # `chip-more` arrives with n_clicks back at 0. That re-fires this
        # callback about a second and a half after the modal opens, so
        # treating a zero count as "close" shut the modal on its own before
        # it could be read. A rebuild leaves the overlay exactly as it is.
        if not open_clicks:
            return dash.no_update, dash.no_update

        # Same ranking as the deck chips, so the modal reads as a
        # continuation of the chip row rather than a differently-ordered list.
        ranked: dict = {}
        for a in (alerts or []):
            nid = a.get("node_id")
            if not nid:
                continue
            rank = (1 if _is_cross_ecu(nid) else 0,
                    SEV_RANK.get(a.get("severity", "low"), 0),
                    a.get("confidence", 0))
            if nid not in ranked or rank > ranked[nid]:
                ranked[nid] = rank
        ids = sorted(ranked, key=lambda n: (ranked[n], n), reverse=True)
        grid = [
            html.Span(_ecu_label(e),
                      className="chip chip-cross tip-below" if _is_cross_ecu(e)
                                else "chip tip-below",
                      **{"data-tip": _ecu_tip(e)})
            for e in ids
        ]
        return "open", grid

    # ── Tabs ─────────────────────────────────────────────────────────────
    # Same shape as the segmented controls, and for the same reason: the
    # active state lives on the server so selection never depends on a CSS
    # selector. The tab buttons are part of the static layout and are never
    # rebuilt, so unlike `chip-more` their n_clicks are not reset by a poll.
    @app.callback(
        Output("store-tab", "data"),
        Output("body-grid", "className"),
        Output("pane-detection", "className"),
        Output("pane-evaluation", "className"),
        Output("console-root", "className"),
        Output({"type": "tab", "index": ALL}, "className"),
        Output({"type": "tab", "index": ALL}, "aria-selected"),
        Input({"type": "tab", "index": ALL}, "n_clicks"),
        # The query string is a second way of choosing a tab, used by the
        # standalone links. Folding it into this callback rather than giving
        # it its own keeps `store-tab` with a single writer — two callbacks
        # writing one prop needs allow_duplicate and then races on load.
        Input("url", "search"),
        State("store-tab", "data"),
    )
    def set_tab(_clicks, search, current):
        keys = [k for k, _ in TABS]
        query = parse_qs((search or "").lstrip("?"))

        # `search` never changes after load (dcc.Location is read-only here),
        # so solo is safe to recompute on every trigger, including clicks.
        solo = query.get("solo", ["0"])[0] == "1"

        trigger = ctx.triggered_id
        if isinstance(trigger, dict) and trigger.get("type") == "tab":
            chosen = trigger["index"]
        else:
            wanted = query.get("view", [""])[0]
            chosen = wanted if wanted in keys else (current or "live")

        return (
            chosen,
            "pane is-active" if chosen == "live" else "pane",
            "pane is-active" if chosen == "detection" else "pane",
            "pane is-active" if chosen == "evaluation" else "pane",
            "is-solo" if solo else "",
            ["view-tab is-active" if k == chosen else "view-tab" for k in keys],
            ["true" if k == chosen else "false" for k in keys],
        )

    @app.callback(
        Output("open-solo", "href"),
        Input("store-tab", "data"),
        Input("store-theme", "data"),
    )
    def solo_href(tab, theme):
        # The theme rides along, so a standalone view opens in the theme the
        # console is already in rather than snapping back to the default.
        href = f"/?view={tab or 'live'}&solo=1"
        return href + "&theme=dark" if theme == "dark" else href

    # Plotly measures its container when it draws. The confidence chart keeps
    # being redrawn every 2s while the Live pane is hidden, so it comes back
    # sized for a display:none box; this nudges it once the pane is visible.
    app.clientside_callback(
        "window.dash_clientside.semantican.afterTabSwitch",
        Output("tab-bar", "data-tab"),
        Input("store-tab", "data"),
    )

    # ── Theme ────────────────────────────────────────────────────────────
    # Light is the default, so the absence of a data-theme attribute is a
    # valid state rather than an unset one. The store exists only because
    # the Plotly figure has to be rebuilt in Python when the theme changes.
    # One writer for the theme, two ways in: the button, and ?theme=dark on
    # a standalone link. Folded into a single callback for the same reason
    # set_tab is — two callbacks writing `store-theme` would need
    # allow_duplicate and then race on load.
    app.clientside_callback(
        "window.dash_clientside.semantican.applyTheme",
        Output("theme-toggle", "className"),
        Output("theme-toggle", "title"),
        Output("theme-toggle", "aria-label"),
        Output("store-theme", "data"),
        Input("theme-toggle", "n_clicks"),
        Input("url", "search"),
    )

    # ── Calm mode ────────────────────────────────────────────────────────
    app.clientside_callback(
        "window.dash_clientside.semantican.toggleCalm",
        Output("calm-toggle", "children"),
        Output("calm-toggle", "data-on"),
        Input("calm-toggle", "n_clicks"),
        prevent_initial_call=True,
    )
