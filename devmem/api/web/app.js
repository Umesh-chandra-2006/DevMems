/* DevMem memory inspector: the app shell (Phase 8 Stop 1 and 2). Tabs: town replay (two synchronized panes, click an avatar to inspect),
   memory inspector (timeline player and the four-stage memory panel of Stop 1), cost view. The label bar is always visible and there is a
   live-calls panel. Read-only: only GET requests to this server. No CDN, no JSX, no compiler. */
(function () {
  "use strict";
  var DM = window.DM, h = DM.h, api = DM.api, toMin = DM.toMin, fromMin = DM.fromMin, pretty = DM.pretty, STAGE = DM.STAGE;
  var useState = React.useState, useEffect = React.useEffect, useRef = React.useRef, useMemo = React.useMemo;
  var LANE = { 1: 0, 2: 1, 3: 2, 4: 3, 0: 4 };
  var SPEEDS = [10, 30, 120, 600];
  var Q = new URLSearchParams(location.search);

  function Track(p) {
    var ev = p.events, lo = p.tMin, hi = p.tMax, W = 1000, H = 86, span = Math.max(1, hi - lo);
    var x = function (m) { return ((m - lo) / span) * W; };
    var ticks = useMemo(function () {
      return ev.map(function (e, i) {
        var lane = LANE[e.stage], mine = !e.agent || e.agent === p.agent;
        var y = 6 + lane * 15, ht = e.stage === 0 ? 5 : (e.kind === "episodic" ? 11 : 13);
        return h("line", { key: i, x1: x(toMin(e.t)), x2: x(toMin(e.t)), y1: y, y2: y + ht, stroke: STAGE[e.stage].color,
          strokeWidth: e.kind === "episodic" ? 1 : 2, opacity: mine ? (e.idle_text ? 0.35 : 0.95) : 0.12 });
      });
    }, [ev, lo, hi, p.agent]);
    var hours = [];
    var step = span > 60 * 48 ? 720 : (span > 60 * 12 ? 180 : 60);
    for (var m = Math.ceil(lo / step) * step; m <= hi; m += step) {
      hours.push(h("g", { key: "h" + m },
        h("line", { x1: x(m), x2: x(m), y1: 68, y2: 74, stroke: "var(--line)" }),
        h("text", { x: x(m) + 2, y: 84, fill: "var(--muted)", fontSize: 9 }, fromMin(m).slice(5, 16))));
    }
    function click(evt) {
      var r = evt.currentTarget.getBoundingClientRect();
      p.onSeek(lo + ((evt.clientX - r.left) / r.width) * span);
    }
    return h("svg", { className: "track", viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none", onClick: click },
      ticks, hours, h("line", { x1: x(p.t), x2: x(p.t), y1: 0, y2: H, stroke: "var(--gold-hi)", strokeWidth: 2 }));
  }

  function Clock(p) {   /* play, pause, speed, scrubber and the simulated clock; the town tab passes events=null (a plain scrubber) */
    return h("div", { className: "player" },
      h("div", { className: "bar" },
        h("button", { className: p.playing ? "on" : "", onClick: p.onToggle }, p.playing ? "Pause" : "Play"),
        h("button", { onClick: function () { p.onSeek(p.tMin); } }, "Start"),
        h("span", { className: "kv" }, "speed (simulated minutes per second) "),
        SPEEDS.map(function (s) { return h("button", { key: s, className: p.speed === s ? "on" : "", onClick: function () { p.onSpeed(s); } }, String(s)); }),
        h("span", { className: "clock" }, pretty(fromMin(p.t))),
        p.events ? h("span", { className: "legend" }, [1, 2, 3, 4, 0].map(function (s) {
          return h("span", { key: s }, h("span", { className: "swatch", style: { background: STAGE[s].color } }), STAGE[s].name);
        })) : null),
      p.events ? h(Track, { events: p.events, tMin: p.tMin, tMax: p.tMax, t: p.t, agent: p.agent, onSeek: p.onSeek }) : null,
      h("input", { className: "scrub", type: "range", min: p.tMin, max: p.tMax, step: 1, value: Math.round(Math.min(Math.max(p.t, p.tMin), p.tMax)),
        onChange: function (e) { p.onSeek(Number(e.target.value)); } }),
      h("div", { className: "hint" }, p.hint));
  }

  function useClock(range, startAt) {
    var _a = useState(startAt != null ? startAt : (range ? range[0] : 0)), t = _a[0], setT = _a[1];
    var _b = useState(false), playing = _b[0], setPlaying = _b[1];
    var _c = useState(120), speed = _c[0], setSpeed = _c[1];
    useEffect(function () {
      if (!playing || !range) { return; }
      var id = setInterval(function () {
        setT(function (cur) { var n = cur + speed * 0.1; if (n >= range[1]) { setPlaying(false); return range[1]; } return n; });
      }, 100);
      return function () { clearInterval(id); };
    }, [playing, speed, range && range[0], range && range[1]]);
    return { t: t, setT: setT, playing: playing, setPlaying: setPlaying, speed: speed, setSpeed: setSpeed };
  }

  /* ---------------------------------------------------------------- memory inspector (Stop 1) */
  function Inspector(p) {
    var run = p.run;
    var _a = useState(null), meta = _a[0], setMeta = _a[1];
    var _b = useState(null), agent = _b[0], setAgent = _b[1];
    var _c = useState({ events: [], t_min: null, t_max: null, count: 0 }), tl = _c[0], setTl = _c[1];
    var _i = useState(null), state = _i[0], setState = _i[1];
    var _j = useState(Q.get("idle") !== "show"), hideIdle = _j[0], setHideIdle = _j[1];
    var _k = useState(null), sel = _k[0], setSel = _k[1];
    var _l = useState(Q.get("diag") === "1"), diag = _l[0], setDiag = _l[1];
    var _m = useState(null), error = _m[0], setError = _m[1];
    var range = tl.t_min ? [toMin(tl.t_min), toMin(tl.t_max)] : null;
    var clk = useClock(range, Q.get("t") ? toMin(Q.get("t")) : null);
    var seq = useRef(0);

    useEffect(function () {
      if (!run) { return; }
      clk.setPlaying(false); setState(null);
      Promise.all([api("/runs/" + encodeURIComponent(run) + "/agents"), api("/runs/" + encodeURIComponent(run) + "/timeline")]).then(function (res) {
        setMeta(res[0]); p.onLabel(res[0].label);
        var wanted = Q.get("agent");
        var names = res[0].agents.map(function (a) { return a.agent; });
        setAgent(names.indexOf(wanted) >= 0 ? wanted : names[0]);
        setTl(res[1]);
        clk.setT(Q.get("t") ? toMin(Q.get("t")) : toMin(res[1].t_min));
        var pre = Q.get("select");
        if (pre && pre.indexOf(":") > 0) { setSel({ type: pre.split(":")[0], id: pre.slice(pre.indexOf(":") + 1) }); }
      }).catch(function (e) { setError(String(e)); });
    }, [run]);

    useEffect(function () {
      if (!run || !agent || tl.t_min == null) { return; }
      var my = ++seq.current;
      var timer = setTimeout(function () {
        api("/runs/" + encodeURIComponent(run) + "/agents/" + encodeURIComponent(agent) + "/state?t=" + encodeURIComponent(fromMin(clk.t)) + (diag ? "&diagnostics=true" : ""))
          .then(function (s) { if (my === seq.current) { setState(s); setError(null); } })
          .catch(function (e) { if (my === seq.current) { setError(String(e)); } });
      }, 120);
      return function () { clearTimeout(timer); };
    }, [run, agent, clk.t, diag, tl]);

    var sets = DM.highlightSets(state, sel);
    useEffect(function () {
      var first = Object.keys(sets.hl)[0];
      if (first) { var el = document.getElementById("ep-" + first); if (el) { el.scrollIntoView({ block: "nearest" }); } }
    }, [sel]);
    function select(x) { setSel(sel && sel.type === x.type && sel.id === x.id ? null : x); }

    return h("div", null,
      error ? h("div", { className: "err" }, error) : null,
      h("div", { className: "controls" }, h("span", { className: "kv" }, tl.t_min ? "recorded span " + tl.t_min + " to " + tl.t_max : "")),
      tl.t_min ? h(Clock, { events: tl.events, tMin: range[0], tMax: range[1], t: clk.t, agent: agent, playing: clk.playing, speed: clk.speed,
        onToggle: function () { if (!clk.playing && clk.t >= range[1]) { clk.setT(range[0]); } clk.setPlaying(!clk.playing); },
        onSeek: function (m) { clk.setPlaying(false); clk.setT(m); }, onSpeed: clk.setSpeed,
        hint: tl.count + " recorded events on this timeline. Ticks of the selected agent are bright; other agents are faint. Sleep and ledger ticks are per-window records, not exact instants." }) : null,
      meta ? h("div", { className: "agents" }, meta.agents.map(function (a) {
        return h("button", { key: a.agent, className: agent === a.agent ? "on" : "", onClick: function () { setAgent(a.agent); setSel(null); } }, a.agent);
      })) : null,
      state ? h("div", { className: "cols" },
        h(DM.Priors, { state: state }),
        h(DM.Episodic, { state: state, hl: sets.hl, hideIdle: hideIdle, onHideIdle: setHideIdle }),
        h(DM.Semantic, { state: state, sel: sel, hlSummary: sets.hlSummary, onSelect: select }),
        h(DM.Identity, { state: state, sel: sel, onSelect: select, diag: diag, onDiag: setDiag })) :
        h("div", { className: "empty", style: { padding: 18 } }, "loading recorded state..."));
  }

  /* ---------------------------------------------------------------- town tab: two panes, one clock */
  function TownTab(p) {
    var _a = useState({}), metas = _a[0], setMetas = _a[1];
    var los = ["left", "right"].map(function (k) { return metas[k] && metas[k].available ? toMin(metas[k].t_min) : null; }).filter(function (x) { return x != null; });
    var his = ["left", "right"].map(function (k) { return metas[k] && metas[k].available ? toMin(metas[k].t_max) : null; }).filter(function (x) { return x != null; });
    var range = los.length ? [Math.min.apply(null, los), Math.max.apply(null, his)] : null;
    var clk = useClock(range, Q.get("t") ? toMin(Q.get("t")) : null);
    var seeded = useRef(false);
    useEffect(function () { if (range && !seeded.current) { seeded.current = true; clk.setT(Q.get("t") ? toMin(Q.get("t")) : range[0]); } }, [range && range[0]]);
    function onMeta(id, m) { setMetas(function (o) { var n = Object.assign({}, o); n[id] = m; return n; }); }
    return h("div", null,
      range ? h(Clock, { events: null, tMin: range[0], tMax: range[1], t: clk.t, playing: clk.playing, speed: clk.speed,
        onToggle: function () { if (!clk.playing && clk.t >= range[1]) { clk.setT(range[0]); } clk.setPlaying(!clk.playing); },
        onSeek: function (m) { clk.setPlaying(false); clk.setT(m); }, onSpeed: clk.setSpeed,
        hint: "One clock drives both panes. A pane whose run has no frame at this time says so and keeps the avatars where they were last recorded." }) :
        h("div", { className: "empty", style: { padding: 18 } }, "loading movement metadata..."),
      h("div", { className: "panes" },
        ["left", "right"].map(function (id) {
          return h(window.Town.TownPane, { key: id, id: id, run: id === "left" ? p.runA : p.runB, runs: p.runs, t: clk.t, playing: clk.playing,
            onRun: p.onRun, onMeta: onMeta, onLabel: p.onLabel });
        })));
  }

  function LivePanel(p) {
    var _a = useState([]), rows = _a[0], setRows = _a[1];
    useEffect(function () {
      var alive = true;
      function poll() {
        Promise.all([p.runA, p.runB].filter(Boolean).map(function (r) { return api("/runs/" + encodeURIComponent(r) + "/status").catch(function () { return { run: r, available: false }; }); }))
          .then(function (res) { if (alive) { setRows(res); } });
      }
      poll();
      var id = setInterval(poll, 5000);
      return function () { alive = false; clearInterval(id); };
    }, [p.runA, p.runB]);
    var live = rows.filter(function (r) { return r.available && r.fresh; });
    return h("div", { className: "livepanel" },
      h("b", null, "Live calls "),
      live.length ? live.map(function (r) {
        var s = r.status;
        return h("span", { key: r.run, className: "kv" }, r.run + ": " + s.router_calls_total + " router calls, " + (s.quota_pauses || 0) + " quota pauses, clock " + s.sim_clock + ", injection pass " + (s.injection ? s.injection.pass + " of " + s.injection.resolved : "n/a") + " ");
      }) : h("span", { className: "kv" }, "no live segment is running (this panel shows the router call counter of a run that is writing run_status.json, and nothing otherwise)"));
  }

  function App() {
    var _a = useState([]), runs = _a[0], setRuns = _a[1];
    var _b = useState(Q.get("a") || Q.get("run") || null), runA = _b[0], setRunA = _b[1];
    var _c = useState(Q.get("b") || null), runB = _c[0], setRunB = _c[1];
    var _d = useState(Q.get("tab") || "town"), tab = _d[0], setTab = _d[1];
    var _e = useState({}), labels = _e[0], setLabels = _e[1];
    var _f = useState(null), error = _f[0], setError = _f[1];
    useEffect(function () {
      api("/runs").then(function (r) {
        setRuns(r.runs);
        var declared = r.runs.filter(function (x) { return x.agents.length && x.label.label_source === "run_label.json"; });
        var any = r.runs.filter(function (x) { return x.agents.length; });
        var pick = declared.concat(any);
        setRunA(function (cur) { return cur || (pick[0] && pick[0].run); });
        setRunB(function (cur) { return cur || (pick[1] && pick[1].run) || (pick[0] && pick[0].run); });
      }).catch(function (e) { setError(String(e)); });
    }, []);
    useEffect(function () {   /* the label bar must always show the runs on screen, whichever tab is open */
      [["left", runA], ["right", runB]].forEach(function (x) {
        if (x[1]) { api("/runs/" + encodeURIComponent(x[1]) + "/label").then(function (l) { onLabel(x[0], l); }).catch(function () {}); }
      });
    }, [runA, runB]);
    function onLabel(side, l) { setLabels(function (o) { var n = Object.assign({}, o); n[side] = l; return n; }); }
    function onRun(side, run) { if (side === "left") { setRunA(run); } else { setRunB(run); } }
    var shown = tab === "inspector" ? [labels.insp || labels.left] : [labels.left, labels.right];
    var tabBtn = function (id, text) { return h("button", { className: tab === id ? "on" : "", onClick: function () { setTab(id); } }, text); };
    var select2 = function (value, set) { return h("select", { value: value || "", onChange: function (e) { set(e.target.value); } }, runs.map(function (r) { return h("option", { key: r.run, value: r.run }, r.run); })); };
    return h("div", null,
      h(DM.LabelBar, { labels: shown }),
      error ? h("div", { className: "err" }, error) : null,
      h("div", { className: "tabs" }, tabBtn("town", "Town replay"), tabBtn("inspector", "Memory inspector"), tabBtn("cost", "Cost view"),
        h("span", { className: "kv" }, "runs found: " + runs.length)),
      h(LivePanel, { runA: runA, runB: runB }),
      !runA ? h("div", { className: "empty", style: { padding: 18 } }, "loading runs...") :
        tab === "town" ? h(TownTab, { runs: runs, runA: runA, runB: runB, onRun: onRun, onLabel: onLabel }) :
        tab === "cost" ? h("div", null,
          h("div", { className: "controls" }, h("label", null, "left"), select2(runA, setRunA), h("label", null, "right"), select2(runB, setRunB)),
          h(window.Cost.CostView, { runA: runA, runB: runB })) :
        h("div", null,
          h("div", { className: "controls" }, h("label", null, "run"), select2(runA, setRunA)),
          h(Inspector, { key: runA, run: runA, onLabel: function (l) { onLabel("insp", l); } })));
  }

  ReactDOM.createRoot(document.getElementById("root")).render(h(App));
})();
