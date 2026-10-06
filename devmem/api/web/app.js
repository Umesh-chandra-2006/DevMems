/* DevMem memory inspector, Phase 8 Stop 1: timeline player and agent memory panel.
   Read-only: only GET requests to this server. No CDN, no JSX, no compiler: React.createElement through the helper `h`. */
(function () {
  "use strict";
  var h = function (type, props) { return React.createElement.apply(null, [type, props].concat([].slice.call(arguments, 2))); };
  var useState = React.useState, useEffect = React.useEffect, useRef = React.useRef, useMemo = React.useMemo;

  var STAGE = {
    0: { name: "infrastructure (sleep windows, ledger windows)", color: "var(--s0)" },
    1: { name: "Stage 1 priors", color: "var(--s1)" },
    2: { name: "Stage 2 episodic", color: "var(--s2)" },
    3: { name: "Stage 3 semantic", color: "var(--s3)" },
    4: { name: "Stage 4 identity", color: "var(--s4)" }
  };
  var LANE = { 1: 0, 2: 1, 3: 2, 4: 3, 0: 4 };
  var SPEEDS = [10, 30, 120, 600];

  function api(path) {
    return fetch(path).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) { throw new Error(j.detail || ("HTTP " + r.status)); } return j; });
    });
  }
  function toMin(s) { return Date.parse(s.replace(" ", "T") + "Z") / 60000; }
  function fromMin(m) { return new Date(Math.round(m) * 60000).toISOString().slice(0, 19).replace("T", " "); }
  function pretty(s) {
    var d = new Date(s.replace(" ", "T") + "Z");
    return d.toUTCString().slice(0, 16).replace(/^\w+, /, "") + " " + s.slice(11, 19);
  }

  function LabelBar(p) {
    var l = p.label || {};
    var kv = function (k, v) { return h("span", { className: "kv" }, k + " ", h("b", null, v == null ? "unknown" : String(v))); };
    return h("div", null,
      h("div", { className: "labelbar" },
        h("span", { className: "title" }, "DevMem Memory Inspector"),
        kv("run", l.run), kv("recorded or live", l.mode), kv("scripted or natural", l.origin), kv("model", l.model),
        kv("normalizer", l.normalizer), kv("stages", l.stages),
        h("span", { className: "ro" }, "read only")),
      h("div", { className: "nonclaim" }, "This view displays what was recorded in the run. It makes no claim about recall, coherence or efficiency. Label source: " +
        (l.label_source || "none") + (l.note ? ". " + l.note : "")));
  }

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

  function Player(p) {
    return h("div", { className: "player" },
      h("div", { className: "bar" },
        h("button", { className: p.playing ? "on" : "", onClick: p.onToggle }, p.playing ? "Pause" : "Play"),
        h("button", { onClick: function () { p.onSeek(p.tMin); } }, "Start"),
        h("span", { className: "kv" }, "speed (simulated minutes per second) "),
        SPEEDS.map(function (s) {
          return h("button", { key: s, className: p.speed === s ? "on" : "", onClick: function () { p.onSpeed(s); } }, String(s));
        }),
        h("span", { className: "clock" }, pretty(fromMin(p.t))),
        h("span", { className: "legend" }, [1, 2, 3, 4, 0].map(function (s) {
          return h("span", { key: s }, h("span", { className: "swatch", style: { background: STAGE[s].color } }), STAGE[s].name);
        }))),
      h(Track, { events: p.events, tMin: p.tMin, tMax: p.tMax, t: p.t, agent: p.agent, onSeek: p.onSeek }),
      h("input", { className: "scrub", type: "range", min: p.tMin, max: p.tMax, step: 1, value: Math.round(p.t),
        onChange: function (e) { p.onSeek(Number(e.target.value)); } }),
      h("div", { className: "hint" }, p.count + " recorded events on this timeline. Ticks of the selected agent are bright; other agents are faint. " +
        "Sleep and ledger ticks are per-window records, not exact instants."));
  }

  function Col(p) {
    return h("section", { className: "col", style: { "--c": p.color } },
      h("h2", null, p.title), h("div", { className: "sub" }, p.sub), p.extra, h("div", { className: "body" }, p.children));
  }

  function Priors(p) {
    var s = p.state.stage1_priors;
    return h(Col, { title: "Stage 1: priors", color: STAGE[1].color, sub: s.statements.length + " statements (source " + s.source + ")" },
      s.statements.length === 0 ? h("div", { className: "empty" }, "no persona file found for this agent") :
        s.statements.map(function (x, i) {
          return h("div", { className: "item", key: i }, x.statement, h("div", { className: "meta" }, h("span", { className: "chip" }, x.category)));
        }));
  }

  function Episodic(p) {
    var st = p.state.stage2_episodic, hide = p.hideIdle;
    var list = st.entries.filter(function (e) { return !(hide && e.is_idle_text); }).slice().reverse();
    var shown = list.slice(0, 400);
    var toggle = h("div", { className: "toggle" },
      h("input", { type: "checkbox", id: "hide-idle", checked: hide, onChange: function (e) { p.onHideIdle(e.target.checked); } }),
      h("label", { htmlFor: "hide-idle" }, "hide entries whose text contains \"idle\" (" + st.idle_text_entries + " up to this time)"));
    return h(Col, { title: "Stage 2: episodic", color: STAGE[2].color, extra: toggle,
      sub: st.entries_total_up_to_t + " entries up to this time, newest first" + (list.length > shown.length ? ", showing 400 of " + list.length : "") },
      shown.length === 0 ? h("div", { className: "empty" }, "nothing recorded yet at this time") :
        shown.map(function (e) {
          var cls = "item" + (p.hl[e.entry_id] ? " hl" : "") + (e.is_idle_text ? " dim" : "");
          var sc = e.scoring.status === "not recorded" ? "scoring context: not recorded" :
            "scored " + e.scoring.status + (e.scoring.trait_ids_in_prompt && e.scoring.trait_ids_in_prompt.length ? " with " + e.scoring.trait_ids_in_prompt.length + " trait(s) in the prompt" : "");
          return h("div", { className: cls, key: e.entry_id, id: "ep-" + e.entry_id },
            e.text,
            h("div", { className: "meta" },
              h("span", null, e.sim_time.slice(5, 16)),
              h("span", { className: "chip imp" }, "importance " + (e.importance == null ? "n/a" : e.importance)),
              h("span", { className: "chip" }, sc),
              e.consolidated_into ? h("span", { className: "chip" }, "in summary " + e.consolidated_into.split(":")[1]) : null,
              h("span", null, e.entry_id.split(":")[1])));
        }));
  }

  function Semantic(p) {
    var st = p.state.stage3_semantic;
    var list = st.summaries.slice().reverse();
    var sub = !st.available ? "no semantic table in this run" : (st.summaries.length + " summaries, " + st.sweeps.length + " sweep marker(s) up to this time");
    return h(Col, { title: "Stage 3: semantic", color: STAGE[3].color, sub: sub },
      list.length === 0 ? h("div", { className: "empty" }, st.available ? "no summary recorded up to this time" : "Stage 3 not present in this run") :
        list.map(function (s) {
          var cls = "item click" + (p.sel && p.sel.type === "summary" && p.sel.id === s.entry_id ? " sel" : "") + (p.hlSummary[s.entry_id] ? " hl" : "");
          var r = s.stage4_reinforcement;
          return h("div", { className: cls, key: s.entry_id, onClick: function () { p.onSelect({ type: "summary", id: s.entry_id }); } },
            s.summary,
            h("div", { className: "meta" },
              h("span", null, s.created_at.slice(5, 16)), h("span", { className: "chip imp" }, "importance " + s.importance),
              h("span", { className: "chip" }, s.source_entry_ids.length + " source entries"),
              h("span", { className: "chip" }, "reinforced " + s.times_reinforced + "x"),
              r ? h("span", { className: "chip" }, "counted nights " + JSON.stringify(r.day_set)) : null,
              h("span", null, s.entry_id.split(":")[1])));
        }));
  }

  function Identity(p) {
    var st = p.state.stage4_identity, ctx = p.state.identity_context_at_t;
    var traits = (st.traits || []).slice().reverse();
    var toggle = h("div", { className: "toggle" },
      h("input", { type: "checkbox", id: "diag", checked: p.diag, onChange: function (e) { p.onDiag(e.target.checked); } }),
      h("label", { htmlFor: "diag" }, "provenance diagnostic (cached embeddings only, no network)"));
    var sub = !st.available ? "no identity tables in this run" : (traits.length + " trait(s) created up to this time");
    return h(Col, { title: "Stage 4: identity", color: STAGE[4].color, sub: sub, extra: st.available ? toggle : null },
      traits.length === 0 ? h("div", { className: "empty" }, st.available ? "no trait recorded up to this time" : "Stage 4 not present in this run") :
        traits.map(function (t) {
          var open = p.sel && p.sel.type === "trait" && p.sel.id === t.trait_id;
          var pv = t.provenance;
          return h("div", { className: "item click" + (open ? " sel" : ""), key: t.trait_id, onClick: function () { p.onSelect({ type: "trait", id: t.trait_id }); } },
            t.text,
            h("div", { className: "meta" },
              h("span", { className: "chip path" }, t.path),
              h("span", null, "night " + t.created_night + ", " + t.created_sim_time.slice(5, 16)),
              h("span", { className: "chip" }, t.active_now ? "active now" : "not active now"),
              h("span", null, t.trait_id.split(":")[1])),
            open ? h("div", { className: "diag" },
              h("div", null, h("b", null, "sources "), t.source_semantic_ids.length ? t.source_semantic_ids.map(function (x) { return x.split(":")[1]; }).join(", ") + " (semantic) " : "",
                t.source_event_ids.length ? t.source_event_ids.map(function (x) { return x.split(":")[1]; }).join(", ") + " (event)" : ""),
              h("div", null, h("b", null, "path "), t.path === "pivotal" ? "pivotal: a single event scored at or above the threshold" :
                (t.path === "same_day" ? "same day: enough new source entries attached to one summary in one night" : "count based: counted on enough distinct nights")),
              h("div", null, h("b", null, "provenance diagnostic "), pv && pv.available ?
                ("cosine to priors text " + pv.cosine_to_priors_text + "; to sources " + pv.cosine_to_sources.map(function (c) { return c.cosine; }).join(", ") +
                  "; closer to the priors than to its best source: " + (pv.closer_to_priors_than_to_best_source ? "yes" : "no") + ". " + pv.note) :
                (pv ? pv.reason : "not available"))) : null);
        }),
      st.available ? h("div", null,
        h("div", { className: "sub", style: { borderTop: "1px solid var(--line)", paddingTop: 8 } }, "identity_context rendered at this time (what the scorer would add after the priors)"),
        h("div", { className: "ctxbox", style: { margin: "0 10px 12px" } }, ctx.text || ("(empty)" + (ctx.note ? " " + ctx.note : "")))) : null);
  }

  function App() {
    var _a = useState([]), runs = _a[0], setRuns = _a[1];
    var _b = useState(null), run = _b[0], setRun = _b[1];
    var _c = useState(null), meta = _c[0], setMeta = _c[1];
    var _d = useState(null), agent = _d[0], setAgent = _d[1];
    var _e = useState({ events: [], t_min: null, t_max: null, count: 0 }), tl = _e[0], setTl = _e[1];
    var _f = useState(0), t = _f[0], setT = _f[1];
    var _g = useState(false), playing = _g[0], setPlaying = _g[1];
    var _h = useState(120), speed = _h[0], setSpeed = _h[1];
    var _i = useState(null), state = _i[0], setState = _i[1];
    var _j = useState(true), hideIdle = _j[0], setHideIdle = _j[1];
    var _k = useState(null), sel = _k[0], setSel = _k[1];
    var _l = useState(false), diag = _l[0], setDiag = _l[1];
    var _m = useState(null), error = _m[0], setError = _m[1];
    var seq = useRef(0);

    useEffect(function () {
      api("/runs").then(function (r) {
        setRuns(r.runs);
        var pick = new URLSearchParams(location.search).get("run");
        var first = (pick && r.runs.find(function (x) { return x.run === pick; })) || r.runs.find(function (x) { return x.agents.length && x.label.label_source === "run_label.json"; }) || r.runs.find(function (x) { return x.agents.length; });
        if (first) { setRun(first.run); }
      }).catch(function (e) { setError(String(e)); });
    }, []);

    useEffect(function () {
      if (!run) { return; }
      setPlaying(false); setState(null);
      Promise.all([api("/runs/" + encodeURIComponent(run) + "/agents"), api("/runs/" + encodeURIComponent(run) + "/timeline")]).then(function (res) {
        setMeta(res[0]);
        var wanted = new URLSearchParams(location.search).get("agent");
        var names = res[0].agents.map(function (a) { return a.agent; });
        setAgent(names.indexOf(wanted) >= 0 ? wanted : names[0]);
        setTl(res[1]);
        var q = new URLSearchParams(location.search).get("t");
        setT(q ? toMin(q) : toMin(res[1].t_min));
        var pre = new URLSearchParams(location.search).get("select");   /* e.g. select=trait:Isabella Rodriguez:trait_2 (reproducible views) */
        if (pre && pre.indexOf(":") > 0) { setSel({ type: pre.split(":")[0], id: pre.slice(pre.indexOf(":") + 1) }); }
        if (new URLSearchParams(location.search).get("diag") === "1") { setDiag(true); }
        if (new URLSearchParams(location.search).get("idle") === "show") { setHideIdle(false); }
      }).catch(function (e) { setError(String(e)); });
    }, [run]);

    useEffect(function () {
      if (!run || !agent || tl.t_min == null) { return; }
      var my = ++seq.current;
      var timer = setTimeout(function () {
        api("/runs/" + encodeURIComponent(run) + "/agents/" + encodeURIComponent(agent) + "/state?t=" + encodeURIComponent(fromMin(t)) + (diag ? "&diagnostics=true" : ""))
          .then(function (s) { if (my === seq.current) { setState(s); setError(null); } })
          .catch(function (e) { if (my === seq.current) { setError(String(e)); } });
      }, 120);
      return function () { clearTimeout(timer); };
    }, [run, agent, t, diag, tl]);

    useEffect(function () {
      if (!playing) { return; }
      var tMax = toMin(tl.t_max);
      var id = setInterval(function () {
        setT(function (cur) { var n = cur + speed * 0.1; if (n >= tMax) { setPlaying(false); return tMax; } return n; });
      }, 100);
      return function () { clearInterval(id); };
    }, [playing, speed, tl]);

    var hl = {}, hlSummary = {};
    if (state && sel) {
      var sums = state.stage3_semantic.summaries;
      if (sel.type === "summary") {
        var s = sums.find(function (x) { return x.entry_id === sel.id; });
        if (s) { s.source_entry_ids.forEach(function (e) { hl[e] = true; }); }
      } else {
        var tr = (state.stage4_identity.traits || []).find(function (x) { return x.trait_id === sel.id; });
        if (tr) {
          tr.source_event_ids.forEach(function (e) { hl[e] = true; });
          tr.source_semantic_ids.forEach(function (sid) {
            hlSummary[sid] = true;
            var ss = sums.find(function (x) { return x.entry_id === sid; });
            if (ss) { ss.source_entry_ids.forEach(function (e) { hl[e] = true; }); }
          });
        }
      }
    }
    useEffect(function () {
      var first = Object.keys(hl)[0];
      if (first) { var el = document.getElementById("ep-" + first); if (el) { el.scrollIntoView({ block: "nearest" }); } }
    }, [sel]);
    function select(x) { setSel(sel && sel.type === x.type && sel.id === x.id ? null : x); }

    return h("div", null,
      h(LabelBar, { label: state ? state.label : (meta ? meta.label : null) }),
      error ? h("div", { className: "err" }, error) : null,
      h("div", { className: "controls" },
        h("label", null, "run"),
        h("select", { value: run || "", onChange: function (e) { setSel(null); setRun(e.target.value); } },
          runs.map(function (r) { return h("option", { key: r.run, value: r.run }, r.run + (r.agents.length ? " (" + r.agents.length + " agent" + (r.agents.length > 1 ? "s" : "") + ")" : " (no episodic data)")); })),
        h("span", { className: "kv" }, tl.t_min ? "recorded span " + tl.t_min + " to " + tl.t_max : "")),
      tl.t_min ? h(Player, { events: tl.events, count: tl.count, tMin: toMin(tl.t_min), tMax: toMin(tl.t_max), t: t, agent: agent, playing: playing, speed: speed,
        onToggle: function () { if (!playing && t >= toMin(tl.t_max)) { setT(toMin(tl.t_min)); } setPlaying(!playing); },
        onSeek: function (m) { setPlaying(false); setT(m); }, onSpeed: setSpeed }) : null,
      meta ? h("div", { className: "agents" }, meta.agents.map(function (a) {
        return h("button", { key: a.agent, className: agent === a.agent ? "on" : "", onClick: function () { setAgent(a.agent); setSel(null); } }, a.agent);
      })) : null,
      state ? h("div", { className: "cols" },
        h(Priors, { state: state }),
        h(Episodic, { state: state, hl: hl, hideIdle: hideIdle, onHideIdle: setHideIdle }),
        h(Semantic, { state: state, sel: sel, hlSummary: hlSummary, onSelect: select }),
        h(Identity, { state: state, sel: sel, onSelect: select, diag: diag, onDiag: setDiag })) :
        h("div", { className: "empty", style: { padding: 18 } }, "loading recorded state..."));
  }

  ReactDOM.createRoot(document.getElementById("root")).render(h(App));
})();
