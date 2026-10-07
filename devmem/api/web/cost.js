/* DevMem memory inspector: the cost view (Phase 8 Stop 2). Calls and tokens by purpose per recorded ledger window (a simulated hour in the
   arm runs and in Step D), side by side for two runs, from GET /runs/{run}/ledger/summary. Read-only. It shows recorded counts only: no
   score and no comparison verdict wording. */
(function () {
  "use strict";
  var DM = window.DM, h = DM.h;
  var useState = React.useState, useEffect = React.useEffect;
  var PALETTE = ["#6FA8DC", "#3FD0C1", "#A992F2", "#BFD7EA", "#3F6E96", "#7AA2F7", "#5F7C90", "#8EA7B8"];

  function colorFor(purposes, name) { return PALETTE[purposes.indexOf(name) % PALETTE.length]; }

  function CostPanel(p) {
    var led = p.led;
    if (!led) { return h("div", { className: "empty" }, "loading the ledger summary..."); }
    if (!led.available) { return h("div", { className: "nomove" }, "No recorded ledger windows for this run: " + led.reason); }
    var windows = led.windows;
    var purposes = [];
    windows.forEach(function (w) { Object.keys(w.by_purpose || {}).forEach(function (k) { if (purposes.indexOf(k) < 0) { purposes.push(k); } }); });
    purposes.sort();
    var maxCalls = Math.max.apply(null, windows.map(function (w) { return w.calls; }).concat([1]));
    var W = 640, H = 190, bw = Math.max(4, Math.floor((W - 40) / windows.length) - 3);
    var totals = {};
    windows.forEach(function (w) {
      Object.keys(w.by_purpose || {}).forEach(function (k) {
        var e = totals[k] || (totals[k] = { calls: 0, tokens_in: 0, tokens_out: 0 });
        e.calls += w.by_purpose[k].calls; e.tokens_in += w.by_purpose[k].tokens_in; e.tokens_out += w.by_purpose[k].tokens_out;
      });
    });
    var bars = windows.map(function (w, i) {
      var y = H - 30, x = 30 + i * (bw + 3), parts = [];
      purposes.forEach(function (k) {
        var c = (w.by_purpose[k] || {}).calls || 0;
        if (!c) { return; }
        var hh = (c / maxCalls) * (H - 60);
        y -= hh;
        parts.push(h("rect", { key: k, x: x, y: y, width: bw, height: hh, fill: colorFor(purposes, k) }, h("title", null, w.window + ": " + k + " " + c + " calls")));
      });
      return h("g", { key: i }, parts,
        h("text", { x: x, y: H - 16, fontSize: 8, fill: "var(--muted)", transform: "rotate(45 " + x + " " + (H - 16) + ")" }, w.sim_clock_end.slice(11, 16)));
    });
    return h("div", { className: "costpanel" },
      h("div", { className: "kv" }, led.totals.calls + " recorded calls, " + led.totals.tokens_in + " tokens in, " + led.totals.tokens_out + " tokens out, in " + windows.length + " ledger windows"),
      h("svg", { viewBox: "0 0 " + W + " " + H, className: "costchart", preserveAspectRatio: "xMidYMid meet" },
        h("line", { x1: 28, x2: 28, y1: 10, y2: H - 30, stroke: "var(--line)" }),
        h("text", { x: 2, y: 16, fontSize: 9, fill: "var(--muted)" }, maxCalls), h("text", { x: 2, y: H - 30, fontSize: 9, fill: "var(--muted)" }, "0"),
        bars),
      h("div", { className: "legend2" }, purposes.map(function (k) {
        return h("span", { key: k }, h("span", { className: "swatch", style: { background: colorFor(purposes, k) } }), k);
      })),
      h("table", { className: "costtable" },
        h("thead", null, h("tr", null, ["purpose", "calls", "tokens in", "tokens out"].map(function (x) { return h("th", { key: x }, x); }))),
        h("tbody", null, purposes.map(function (k) {
          return h("tr", { key: k }, h("td", null, k), h("td", null, totals[k].calls), h("td", null, totals[k].tokens_in), h("td", null, totals[k].tokens_out));
        }))),
      h("div", { className: "hint" }, "Windows are the recorded ledger windows (simulated hours); evaluation calls are never part of these windows. Sources: " + led.sources.join("; ") + "."));
  }

  function CostView(p) {
    var _a = useState({}), leds = _a[0], setLeds = _a[1];
    useEffect(function () {
      var alive = true;
      [p.runA, p.runB].forEach(function (r, i) {
        if (!r) { return; }
        DM.api("/runs/" + encodeURIComponent(r) + "/ledger/summary").then(function (j) { if (alive) { setLeds(function (o) { var n = Object.assign({}, o); n[i] = j; return n; }); } })
          .catch(function (e) { if (alive) { setLeds(function (o) { var n = Object.assign({}, o); n[i] = { available: false, reason: String(e) }; return n; }); } });
      });
      return function () { alive = false; };
    }, [p.runA, p.runB]);
    return h("div", { className: "costview" },
      [p.runA, p.runB].map(function (r, i) {
        return h("div", { className: "costcol", key: i },
          h("h3", null, (i === 0 ? "left: " : "right: ") + (r || "no run")), r ? h(CostPanel, { led: leds[i] }) : null);
      }));
  }

  window.Cost = { CostView: CostView };
})();
