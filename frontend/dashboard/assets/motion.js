/* ==========================================================================
   SemantiCAN motion layer

   The problem this file exists to solve:
   Dash re-renders component children wholesale on every 2s poll. Any CSS
   entry animation attached to those children therefore restarts every 2
   seconds, which is exactly what makes a live dashboard flicker. So the
   DOM cannot own animation state. This file owns it instead, in JS, keyed
   by stable identifiers (alert_id) that survive the re-render.

   It also tweens the risk gauge continuously between polls, so the number
   glides rather than stepping four times a minute.
   ========================================================================== */

(function () {
  "use strict";

  /* Runs at parse time, before Dash has mounted anything, so a standalone
     view opened with ?theme=dark never flashes the light theme first. The
     clientside callback below sets the same attribute a moment later; this
     just gets there before the first paint. */
  try {
    if (new URLSearchParams(window.location.search).get("theme") === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    }
  } catch (e) { /* URLSearchParams missing: fall through to light */ }

  var ARRIVE_ONCE_MS = 6000;   /* how long a new alert reads as "fresh" */
  var SEV_RANK = { low: 1, medium: 2, high: 3, critical: 4 };

  /* alert_id -> { firstSeen, announced, severity } */
  var seen = Object.create(null);
  var bootAt = Date.now();
  var booted = false;

  /* ── Risk gauge ──────────────────────────────────────────────────────
     Dash writes the target into data-risk; we tween toward it every frame.
     ARC_LEN is the drawn length of the 270-degree arc in style.css
     (r=54, sweep=270deg -> 54 * 270 * pi/180 = 254.5). */
  var ARC_LEN = 254.5;
  var gaugeShown = 0;
  var gaugeTarget = 0;

  /* The gauge arc is an SVG stroke set from JS, so it cannot inherit the
     severity token the way a CSS-styled element does. Read the token
     instead of duplicating the palette here: that way the arc follows a
     theme switch for free, and there is still only one place where
     #e5484d is written down. Cached per theme, since this runs every
     animation frame. */
  var palette = { theme: null, tiers: {} };

  function sevColor(tier) {
    var theme = document.documentElement.getAttribute("data-theme") || "light";
    if (palette.theme !== theme) palette = { theme: theme, tiers: {} };
    if (!palette.tiers[tier]) {
      var v = getComputedStyle(document.documentElement)
                .getPropertyValue("--sev-" + tier).trim();
      palette.tiers[tier] = v || "#6b7488";
    }
    return palette.tiers[tier];
  }

  function tierFor(risk) {
    if (risk >= 80) return "critical";
    if (risk >= 60) return "high";
    if (risk >= 40) return "medium";
    if (risk > 0)   return "low";
    return "nominal";
  }

  function instant() {
    if (document.documentElement.getAttribute("data-calm") === "on") return true;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function tickGauge() {
    var src = document.getElementById("risk-feed");
    if (src) {
      var t = parseFloat(src.getAttribute("data-risk"));
      if (!isNaN(t)) gaugeTarget = t;
    }

    var delta = gaugeTarget - gaugeShown;
    if (Math.abs(delta) < 0.05) {
      gaugeShown = gaugeTarget;
    } else {
      gaugeShown += delta * (instant() ? 1 : 0.11);
    }

    var arc = document.getElementById("gauge-arc");
    var val = document.getElementById("gauge-value");
    if (arc) {
      var frac = Math.max(0, Math.min(100, gaugeShown)) / 100;
      arc.style.strokeDashoffset = String(ARC_LEN * (1 - frac));
      arc.style.stroke = sevColor(tierFor(gaugeShown));
    }
    if (val) {
      /* Always one decimal: a value that changes width mid-tween makes the
         whole readout jitter, which is worse than the extra digit. */
      val.textContent = gaugeShown.toFixed(1);
    }
    requestAnimationFrame(tickGauge);
  }

  /* ── Feed heartbeat ─────────────────────────────────────────────────
     Pulses only when the underlying timestamp actually advances. A pulse
     on a timer would be decoration; this one is evidence the bus is live. */
  var lastBeat = null;
  function syncPulse() {
    var feed = document.getElementById("feed-stamp");
    var dot = document.getElementById("feed-dot");
    if (!feed || !dot) return;
    var stamp = feed.getAttribute("data-stamp") || "";
    if (stamp && stamp !== lastBeat) {
      lastBeat = stamp;
      if (!instant()) {
        dot.classList.remove("beat");
        void dot.offsetWidth;
        dot.classList.add("beat");
      }
    }
  }

  /* ── Alert arrival + escalation ─────────────────────────────────────
     Runs after every DOM mutation. Because `seen` lives outside the DOM,
     a card that has already arrived is never re-animated, no matter how
     many times Dash replaces its node. */
  function syncAlerts() {
    var now = Date.now();
    var cards = document.querySelectorAll(".alert-card[data-alert-id]");

    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      var id = card.getAttribute("data-alert-id");
      var sev = card.getAttribute("data-severity") || "low";
      var rec = seen[id];

      if (!rec) {
        seen[id] = { firstSeen: now, announced: true, severity: sev };
        /* Suppress the arrival animation for the first paint after load:
           on a page refresh mid-incident every existing alert is "new" to
           this tab, and 40 cards cascading in at once is noise, not signal. */
        if (booted && !instant()) card.classList.add("is-entering");
        if (booted) card.classList.add("is-fresh");
        continue;
      }

      if (SEV_RANK[sev] > SEV_RANK[rec.severity]) {
        rec.severity = sev;
        rec.escalatedAt = now;
        if (!instant()) card.classList.add("is-escalating");
      } else if (rec.escalatedAt && now - rec.escalatedAt < 900) {
        if (!instant()) card.classList.add("is-escalating");
      }

      if (now - rec.firstSeen < ARRIVE_ONCE_MS) card.classList.add("is-fresh");
    }
  }

  function sync() {
    mountGauge();
    syncPulse();
    syncAlerts();
  }

  /* The arc is injected rather than declared in layout.py because Dash's
     html module has no SVG primitives, and routing raw SVG through
     dcc.Markdown gets it sanitised away. Geometry: 270deg sweep, r=54,
     centred at (70,70) in a 140x140 box. */
  function mountGauge() {
    var wrap = document.getElementById("gauge-wrap");
    if (!wrap || wrap.querySelector(".gauge-svg")) return;
    var d = "M 31.82 108.18 A 54 54 0 1 1 108.18 108.18";
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "gauge-svg");
    svg.setAttribute("viewBox", "0 0 140 140");
    svg.setAttribute("aria-hidden", "true");
    var track = document.createElementNS(ns, "path");
    track.setAttribute("class", "gauge-track");
    track.setAttribute("d", d);
    var arc = document.createElementNS(ns, "path");
    arc.setAttribute("class", "gauge-arc");
    arc.setAttribute("id", "gauge-arc");
    arc.setAttribute("d", d);
    svg.appendChild(track);
    svg.appendChild(arc);
    wrap.insertBefore(svg, wrap.firstChild);
  }

  function boot() {
    var root = document.getElementById("console-root") || document.body;
    mountGauge();
    new MutationObserver(sync).observe(root, {
      childList: true, subtree: true, attributes: true,
      attributeFilter: ["data-stamp", "data-severity", "data-risk"]
    });
    sync();
    requestAnimationFrame(tickGauge);
    /* Anything present within the first second is pre-existing state, not
       an arrival. After that, new cards are genuinely new. */
    setTimeout(function () { booted = true; }, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  /* Dash clientside callbacks reach these. */
  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    semantican: {
      /* Light is the default, so an even click count means light and the
         attribute is removed rather than set to "light" — the stylesheet's
         :root block is the light theme, not an override of it.

         The starting point comes from ?theme=, which is how a standalone
         view inherits the console's theme. Clicks flip from there, so the
         button behaves the same whether the tab started light or dark. */
      applyTheme: function (n, search) {
        var startDark = false;
        try {
          startDark = new URLSearchParams(search || "").get("theme") === "dark";
        } catch (e) { /* leave startDark false */ }

        var flipped = (n || 0) % 2 === 1;
        var dark = startDark !== flipped;          /* xor */

        if (dark) {
          document.documentElement.setAttribute("data-theme", "dark");
        } else {
          document.documentElement.removeAttribute("data-theme");
        }

        /* The icon names the mode the click will switch *to*: a sun while
           dark, a moon while light. */
        var label = dark ? "Switch to light mode" : "Switch to dark mode";
        return [
          dark ? "icon-toggle mode-sun" : "icon-toggle mode-moon",
          label, label,
          dark ? "dark" : "light"
        ];
      },

      toggleCalm: function (n) {
        var on = (n || 0) % 2 === 1;
        document.documentElement.setAttribute("data-calm", on ? "on" : "off");
        return [on ? "Calm mode on" : "Calm mode", String(on)];
      },

      /* Plotly sizes itself to its container at draw time. The confidence
         chart keeps redrawing on the 2s poll while the Live pane is hidden,
         so it is holding dimensions measured against a display:none box by
         the time the pane comes back. One resize event after the class has
         actually landed is enough to make it re-measure. */
      afterTabSwitch: function (tab) {
        window.requestAnimationFrame(function () {
          window.dispatchEvent(new Event("resize"));
        });
        return tab || "live";
      }
    }
  });
})();
