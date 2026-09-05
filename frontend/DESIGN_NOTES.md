# SOC console redesign: decisions

Frontend, plus one additive change to `backend/core/ecu_registry.py`:
`ECU_ROLES`, `get_ecu_role` and `describe_ecu` were added so the console can
say what an ECU *is*. `get_ecu_weight`'s behaviour is unchanged and nothing in
the detection pipeline reads the new table.

## Design system

**Depth carries the chrome, contrast carries the data.** Neomorphism normally
fails in a SOC because it wants low contrast everywhere. Containers are
embossed or debossed from the base plane; anything an operator has to *read*
sits at full contrast on top of it. There is no soft-grey-on-soft-grey text.

The base plane is `#141821`, not near-black. A near-black base has no
luminance headroom to emboss a light edge from, which is why the previous
`#0d1117` surfaces could only be separated by hard borders.

**Two colour scales that never overlap.** Severity (`nominal → low → medium →
high → critical`) is sequential and means "how bad". Detector attribution
(`rule / lstm / both / unknown`) is categorical and means "which engine". A
hue never means two different things.

Mono is used for numeric readouts only, never for labels. Tabular figures
stop digits shifting sideways as values tick every two seconds.

## Layout

The AI advisory is the hero and the risk gauge is folded into the same deck
beside it, as context rather than a competing headline. The narrative is the
largest readable block on the page, capped at 76ch so it stays scannable
during an incident.

Panels are never created or destroyed at runtime. A panel that appears and
disappears forces an operator to re-learn the page exactly when the situation
is changing.

## Working against the API as it exists

- **`last_anomaly` is not the last anomaly.** In `get_summary()` it is
  `semantic_history[-1]["timestamp"]`, the newest message from *any* ECU. It
  is a feed heartbeat, so it is labelled "Feed" and "Last frame" and drives a
  liveness indicator. Backend naming is left alone by agreement.
- **Alerts never clear.** `ACTIVE_ALERTS` is append-only per `node_id` and
  nothing removes entries, so the stream only grows for the process lifetime.
  Severity filter and sort order are therefore load-bearing, not conveniences.
- **`ai_analysis` is frozen at alert-creation time.** It is selected by newest
  timestamp and always stamped with that alert's own time, so a stale
  narrative cannot read as a live assessment.
- **Consistency alerts are always `detector: "rule"`,** because `main.py`
  passes `lstm_conf=0.0` for them. The panel is titled "Caught by" rather than
  presented as a detector scorecard.
- **`/api/lstm-status` can return HTTP 500 with `{"error": ...}`.** Three badge
  states, not two: ready, training, unavailable.
- **`/api/violation-rate` is used** even though it was not in the brief's
  endpoint list. It exists in `api.py` and gives the SIEM-style rate view.

## Animation

Every animation fires on a data event, not on hover.

The 2-second poll is the hard constraint. Dash re-renders children wholesale,
so a CSS entry animation attached to those children restarts on every poll.
`assets/motion.js` therefore owns animation state in JS, keyed by `alert_id`,
which survives the re-render:

- Risk gauge tweens continuously between polls (arc offset, colour, digits),
  so the number glides rather than stepping four times a minute.
- A new alert animates in exactly once, then carries a recency bloom that
  decays over ~6s and rests. Arrival is suppressed for the first second after
  load, so refreshing mid-incident does not cascade forty cards at once.
- Severity escalation on an existing ECU gets one pulse ring, never a loop.
- The feed heartbeat pulses only when the timestamp actually advances.
- Violation-rate bars, meters and the attribution bar are HTML with CSS
  transitions, not Plotly. Six values do not need a plotting library, and a
  width/height tween glides where a Plotly redraw snaps.
- Plotly keeps `uirevision` plus a transition so traces morph instead of
  tearing down.

Calm mode and `prefers-reduced-motion` collapse all durations to ~1ms. The
layout never changes, only transit time.

## Judgement calls made during the build

1. **Dropped `dash_bootstrap_components` DARKLY.** It sets its own body
   background, font stack, card shadows and border colours, all of which
   fight the soft-depth surfaces and would need `!important` to override.
   `dash-bootstrap-components` is unused by the frontend, and a grep of the
   whole repository confirms nothing else imports it either, so it has been
   dropped from `requirements.txt`.
2. **Segmented controls are real buttons with server-side active state,**
   not styled `dcc.RadioItems`. Styling a radio's checked state needs the
   `:has()` selector, and a control this important should not depend on it.
3. **Detector breakdown is a segmented bar, not a donut.** At this panel size
   a donut is mostly hole, needs a legend anyway, and a width tween reads more
   clearly than an animated arc.
4. **The ~117 normal ECUs are collapsed into a min/max envelope with a mean
   line.** Drawing them individually is 117 near-identical lines that hide the
   handful that matter.
5. **ECU chips are ranked, not alphabetical.** Only eight fit; sorting by name
   put `ECU_003` ahead of `ECU_SPEED` and hid the actual incident behind a
   "+20 more" button. Cross-ECU findings rank first since `ecu_registry.py`
   weights them 5.
6. **Sentence case, not shouted caps,** for severity words. The colour already
   carries urgency; caps is the same signal twice.
7. **Highest-scoring ECUs live in the deck,** beside the gauge, so "how bad"
   and "which ones" are read together.
8. **`chip-more` is always present *and never rebuilt*,** hidden when there
   is no overflow rather than relying on `suppress_callback_exceptions` to
   mask a missing component. It started out inside the chips payload, so the
   2s poll destroyed and recreated it with `n_clicks` back at 0 — any click
   that did not finish its round trip before the next rebuild was simply
   lost, and the overflow modal opened or closed roughly a third of the
   time. The chip rows are now static containers whose *contents* change;
   the label, the row and the button around them are part of the layout. A
   control the operator clicks should not be destroyed four times a minute.
9. **The advisory string is parsed, and only the part that is not already on
   screen is rendered.** `generate_advisory` in `backend/ai/advisor.py`
   returns one deterministic string of five parts, and four of them restate
   something the deck already shows an inch away: the level is the headline,
   the risk score is the gauge, the ECU list is the Flagged chip row, and the
   violation list is the Violations chip row. Rendered whole it cost six
   lines of prose to repeat the panel around it, and buried the recommended
   response — the only part that appears nowhere else. `_advisory_parts` in
   `callbacks.py` matches the template and renders the response as the short
   list of distinct instructions it actually is, with a tier-coloured marker
   per line. Anything that does not match the template — including the
   `[Advisory unavailable: ...]` string `alerts.py` substitutes when the
   advisor raises — falls through and is shown verbatim, so a future change
   to the advisor's wording degrades to today's behaviour instead of being
   silently mangled by a half-matching regex. The raw string is still shown
   in full in the alert drawer. Backend text is left alone, per the rule at
   the top of this file.
10. **The scoring mode moves to the stamp line.** `(LSTM-scored)` versus
   `(pre-training baseline)` is the one fact in the preamble the rest of the
   page cannot tell you: the command bar's badge shows the model's state
   *now*, while `ai_analysis` is frozen at alert-creation time.

## Themes

Light is the default and dark is the override, which is the opposite of how
this started. The `:root` block is the light palette; `[data-theme="dark"]`
redefines only the colour tokens, so the two themes share every shadow,
radius, font and duration — the same design at two luminances rather than
two designs. Severity and detector hues are darkened for light, because the
same hue at the same lightness washes out on a light ground.

Two places cannot read a CSS custom property, and both are handled rather
than duplicated by accident:

- **Plotly.** A figure is data, serialised to JSON before any stylesheet
  exists, so the chart keeps a literal palette per theme in `callbacks.py`
  and takes the theme as a callback input. This is the one duplication the
  theming could not avoid, and it is the only literal colour left in Python.
- **The gauge arc.** An SVG stroke set from JS. `motion.js` reads the
  `--sev-*` token off the root element instead of holding its own copy, so
  the arc follows a theme switch for free; the lookup is cached per theme
  because it runs every animation frame.

Everything else that used to be a hex literal in Python is now
`var(--sev-critical)` and friends, so a theme switch moves inline styles
without Python being involved at all.

The toggle is a sun and a moon, both drawn in CSS — `☀` and `☾` render as
colour emoji on some platforms, as tofu on others, and neither can be
tinted. The icon names the mode the click switches *to*: a purple crescent
while light, a yellow sun while dark.

**The theme travels with a standalone link.** `?theme=dark` rides along on
the `↗` href, and `motion.js` applies it at parse time — before Dash has
mounted anything — so a standalone tab opened from a dark console never
flashes light first. The clientside callback sets the same attribute a
moment later and seeds its click parity from the same parameter, so the
button behaves identically whether the tab started light or dark. One
writer for `store-theme`, two ways in, for the same reason `set_tab` has
one writer and two.

## Tabs

Three views share the body area: **Live**, **Detection**, **Evaluation**.
The switcher sits in the command bar: a row of its own cost 45px of vertical
height to do a job the top bar had ~700px of dead width for. The bar shrinks
by dropping the least load-bearing items first — subtitle, then the
control's own label — rather than letting anything wrap. `?view=x&solo=1`
opens one view without the deck in a new browser tab, for reading the dense
reference tables away from a live incident.

This looks like a contradiction of "panels are never created or destroyed at
runtime", and it is worth being precise about why it is not. That rule is
about the page rearranging itself *underneath* an operator because the data
changed. A view that changes because someone clicked a tab is the opposite
case: it is the operator's own action, and they can undo it by clicking
back. The whole tab set is built once at import and only its visibility
changes; no pane is ever constructed or torn down.

Detection and Evaluation are static. They restate what is already in
`backend/core/checks.py`, `backend/core/consistency.py`, `docs/Detection.md`
and `docs/TARA.md`, so there is nothing to poll — the panes are built at
import from `reference.py` and no callback ever touches their contents.

`reference.py` is a copy of material that lives in those files, which means
it can drift from them. Two guards against that: the thresholds in it are
the ones the *code* applies rather than the ones the prose describes (that
distinction already mattered — `Detection.md` claimed the acceleration
mismatch rule fired at 2 m/s² while `checks.py` has always used 4.0, and the
doc has been corrected), and every evaluation figure carries the script and
the run that produced it. A number on a dashboard with no provenance is
indistinguishable from a number somebody typed in.

The class is `.view-tab`, not `.tab`. `dash-core-components` ships CSS for
its own `dcc.Tabs` under a bare `.tab` selector that sets `flex: 1`, which
silently stretched the buttons across the full width of the bar.

## Judgement calls, continued

11. **The top-ECU panel adapts instead of always ranking.**
   `/api/top-anomalous-ecus` sorts by `(risk, last_seen)` and caps at three,
   so once a crowd of ECUs sits at the ceiling together — 23 to 28 at 100.0
   is normal with the LSTM warm — the "top three" is whichever three
   reported most recently. It reshuffled every poll and ranked nothing. The
   panel now shows meters when scores actually separate and a count when
   they do not, and on a tie falls back to the only axis left that still
   discriminates: criticality. In practice that surfaces `ECU_BRAKE`,
   `ECU_SPEED` and `ECU_STEER` out of a two-dozen-way tie, which is the
   answer an operator wanted. It is also folded into the confidence-chart
   callback, since it needs the per-ECU last score that
   `/api/semantic-history` was already being fetched for.
12. **Hover says what is unknown, not just what is known.** The ECU tooltip
   reports criticality *and whether it came from a registry entry or the
   default*, because 120 of the 123 ids the simulator publishes are absent
   from `ecu_registry.py`. Rendering "criticality 2" alone would present an
   inventory gap as a finding. An ISO 21434 asset inventory would have to
   close that gap; the console's job is to make it visible.
13. **`data-tip`, not `title`.** The native tooltip has a half-second delay
   and cannot be styled. The cost was `#advisory-deck`'s `overflow: hidden`,
   which existed only to keep the severity tint inside the rounded corners —
   `border-radius: inherit` on the pseudo-element does that without also
   clipping every tooltip trying to leave the deck.
14. **The alert drawer leads with identity.** It was six key/value rows of
   equal weight, so "which ECU, how bad, how sure" was three lookups rather
   than one glance. Now the ECU is a headline with its registry role under
   it, confidence is a readout using the same meter language as the deck,
   and the alert id — a correlation key for a log grep — moved to a footer.

## Verification

Verified in a real browser (Chromium 152 via CDP) against the real backend —
`backend/main.py` with 120 simulated ECUs, the LSTM trained, and live
alerts — not against a mock.

Driven by clicking: all three tabs, the alert drawer (open, close, scrim,
survives the 2s re-render), the ECU overflow modal, severity filter, sort
order, calm mode. Measured at 1920×1080, 1440×900 and 1366×768. Zero browser
console errors and zero server-side callback exceptions across roughly ten
minutes of live traffic.

Four scenarios: active incident, all-clean, LSTM-unavailable, and backend
entirely down.

Fixed during that pass, each confirmed by measurement rather than by eye:

- `.rate-chart` never restated `flex-direction: row`, so it inherited
  `column` from `.panel-body`; the violation-rate buckets stacked vertically
  and overflowed the panel by 232px, which in turn pushed `#console-root`
  197px past `100vh` under `body { overflow: hidden }`.
- Below 1500px the deck's media query spanned `.top-ecus-well` but never
  placed `.deck-body`, so auto-placement dropped the narrative into the
  200px gauge column. A second bug in the same block: `.meter-list` is
  redefined later in the file at equal specificity, so the query's
  `flex-direction: row` never applied and the second deck row was roughly
  twice the height it needed.
- Overlay close buttons could be ignored. `ctx.triggered_id` reports one id
  and Dash batches simultaneous prop changes into a single call, so a click
  on `modal-close` arriving in the same batch as the poll that rebuilds the
  chip row was reported second and never acted on. Both overlays now check
  every triggered id, not just the first.
- The ECU overflow modal closed itself about 1.6s after opening.
  `update_deck` rebuilds `chip-more` on every poll with `n_clicks` back at
  0, which re-fired `toggle_modal`; a zero click count is a re-render, not a
  close.
- The deck read `store-alerts` as `State` while another callback wrote it on
  the same tick, so it always trailed the alert stream by one poll. One
  poller now writes summary, alerts and LSTM status into stores that the
  deck and the command bar read, which also removed a duplicate
  `/api/summary` fetch per tick.
- **Backend unreachable rendered as an all-clear.** `_get` returned `{}` or
  `[]` on failure, which is indistinguishable from clean, so the hero said
  "All ECUs nominal — reporting clean" with the gauge at 0.0. A failed fetch
  now carries `ok: False`; the deck says "No reading", the gauge holds its
  last value dimmed instead of tweening to zero, each panel says "Backend
  unreachable", and the alert store is left untouched so a dropped request
  does not wipe the board mid-incident.

`#console-root` also gained `overflow-y: auto`. The deck's row is `auto` and
grows with the length of the advisory text, so a fixed `100vh` box under
`overflow: hidden` can always hide content on a short viewport. A scrollbar
is a worse look and a much better console.
