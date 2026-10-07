/* DevMem inspector: Findings, Where it differs, Edge cases, Side by side (Phase 8 UI addendum, 2026-10-07).
   Read-only. The first three tabs display `data/findings.json`, built offline from existing artifacts by devmem/api/build_findings.py (no LLM,
   no generated narrative: every "why" line is a fixed template filled with logged fields). Side by side reads the existing GET endpoints.
   No CDN, no JSX, no compiler. Exposed as window.Views. */
(function () {
  "use strict";
  var DM = window.DM, h = DM.h, api = DM.api;
  var useState = React.useState, useEffect = React.useEffect;
  var NOTE = "single run per arm; differences can be model noise; PILOT is not a result";

  function Note() { return h("div", { className: "keepnote" }, NOTE); }
  function Path(p) { return h("div", { className: "artpath" }, "artifact: ", h("code", null, p.path)); }
  function Table(p) {
    return h("table", { className: "tbl" },
      h("thead", null, h("tr", null, p.head.map(function (x, i) { return h("th", { key: i }, x); }))),
      h("tbody", null, p.rows.map(function (r, i) { return h("tr", { key: i, className: r.cls || "" }, r.cells.map(function (c, j) { return h("td", { key: j }, c); })); })));
  }
  function useFindings() {
    var _a = useState(null), d = _a[0], setD = _a[1];
    var _b = useState(null), err = _b[0], setErr = _b[1];
    useEffect(function () { api("/ui/data/findings.json").then(setD).catch(function (e) { setErr(String(e)); }); }, []);
    return { d: d, err: err };
  }
  function Wrap(p) {
    var f = useFindings();
    if (f.err) { return h("div", { className: "err" }, "findings data not found (" + f.err + "). Build it with: python devmem/api/build_findings.py"); }
    if (!f.d) { return h("div", { className: "empty", style: { padding: 18 } }, "loading..."); }
    return h("div", { className: "view" }, h(Note), p.render(f.d));
  }

  /* ---------------------------------------------------------------- Findings */
  function Findings() {
    return h(Wrap, { render: function (d) {
      var F = d.findings, inj = F.injections, calls = F.calls;
      var purposes = Object.keys(Object.assign({}, calls.arms.baseline.by_purpose, calls.arms.staged.by_purpose));
      return h("div", null,
        h("section", { className: "card" }, h("h3", null, "Injected events per arm (PILOT, live)"),
          h(Table, { head: ["id", "agent", "type", "authored step", "same step in both arms", "perceived (baseline, staged)", "importance baseline", "importance staged", "staged minus baseline"],
            rows: inj.rows.map(function (r) {
              return { cells: [r.id, r.agent, r.type, (r.baseline || r.staged || {}).step, r.same_authored_step ? "yes" : "no",
                (r.baseline ? (r.baseline.perceived ? "yes" : "NO") : "not reached") + ", " + (r.staged ? (r.staged.perceived ? "yes" : "NO") : "not reached"),
                r.baseline ? r.baseline.importance : "n/a", r.staged ? r.staged.importance : "n/a", r.importance_difference == null ? "n/a" : r.importance_difference] };
            }) }),
          h("div", { className: "small" }, inj.rule), h(Path, { path: inj.artifact })),
        h("section", { className: "card" }, h("h3", null, "Calls per purpose per arm (PILOT, live)"),
          h(Table, { head: ["purpose", "baseline", "staged"], rows: purposes.map(function (k) { return { cells: [k, calls.arms.baseline.by_purpose[k] || 0, calls.arms.staged.by_purpose[k] || 0] }; })
            .concat([{ cls: "total", cells: ["total", calls.arms.baseline.total, calls.arms.staged.total] }]) }),
          h("div", { className: "small" }, calls.note), h(Path, { path: calls.artifact })),
        h("section", { className: "card" }, h("h3", null, "Calls per awake agent-hour, per ledger window (windows under 0.3 awake agent-hours show n/a)"),
          ["baseline", "staged"].map(function (arm) {
            return h("div", { key: arm, className: "half" }, h("h4", { style: { color: arm === "baseline" ? "var(--baseline)" : "var(--staged)" } }, arm),
              h(Table, { head: ["window", "sim clock", "steps", "calls", "awake agent-hours", "calls per awake agent-hour"],
                rows: calls.windows[arm].filter(function (w) { return w.calls > 0; }).map(function (w) { return { cells: [w.label, w.sim_clock.slice(11, 16), w.steps, w.calls, w.awake_agent_hours, w.calls_per_awake_agent_hour == null ? "n/a" : w.calls_per_awake_agent_hour] }; }) }));
          }), h(Path, { path: calls.artifact })),
        h("section", { className: "card" }, h("h3", null, "Bugs the pilot and its checks caught"),
          h(Table, { head: ["bug", "caught by", "commit", "evidence"], rows: F.bugs.map(function (b) { return { cells: [b.bug, b.caught, h("code", null, b.commit), h("code", null, b.evidence)] }; }) }),
          h("div", { className: "small" }, "Commit ids are from this repository's history.")));
    } });
  }

  /* ---------------------------------------------------------------- Edge cases */
  function EdgeCases() {
    return h(Wrap, { render: function (d) {
      return h("div", null, h("div", { className: "flagbar" }, "KNOWN FAILURES AND WEAKNESSES"),
        d.edge_cases.map(function (e, i) {
          return h("section", { className: "card flag", key: i }, h("h3", null, e.title),
            h("div", null, h("b", null, "what "), e.what), h("div", null, h("b", null, "status "), e.status), h("div", null, h("b", null, "numbers "), e.numbers),
            h(Path, { path: e.evidence }));
        }));
    } });
  }

  /* ---------------------------------------------------------------- Where it differs and why */
  function Entry(p) {
    return h("div", { className: "entry" },
      h("div", null, h("span", { className: "lab" }, "WHAT "), p.what), h("div", null, h("span", { className: "lab" }, "WHERE "), p.where),
      h("div", null, h("span", { className: "lab" }, "WHY "), p.why), h("div", null, h("span", { className: "lab" }, "EVIDENCE "), h("code", null, p.evidence)));
  }
  function Differs() {
    return h(Wrap, { render: function (d) {
      var D = d.differs, S = D.scoring, C = D.consolidation, I = D.identity, V = D.divergence;
      var ex = S.examples;
      return h("div", null,
        h("section", { className: "card" }, h("h3", null, "1. Scoring (Stages 1 and 2)"),
          ex.map(function (e) {
            if (!e.available) { return h("div", { key: e.id, className: "empty" }, e.id + ": no example available" + (e.reason ? " (" + e.reason + ")" : "")); }
            return h("div", { key: e.id, className: "pair" },
              h(Entry, { what: e.id + " (" + e.agent + "): the same event scored by each arm: baseline " + e.baseline.importance + ", staged " + e.staged.importance + ".",
                where: e.run + "; injected at authored step " + e.baseline.step + ", " + e.baseline.clock, why: e.why,
                evidence: "docs/phase7_pilot_artifacts/*_injection_log.jsonl; devmem/storage/p7pilot_*/raw_replies.jsonl" }),
              h("div", { className: "two" },
                h("div", { className: "pbox base" }, h("b", null, "baseline prompt: lines only here (" + e.n_only_baseline + ")"), h("pre", null, e.lines_only_in_baseline_prompt.join("\n") || "none"), h("div", { className: "small" }, "reply: " + e.baseline_reply)),
                h("div", { className: "pbox stag" }, h("b", null, "staged prompt: lines only here (" + e.n_only_staged + "), the priors block and anything else"), h("pre", { className: "hlblock" }, e.lines_only_in_staged_prompt.join("\n") || "none"), h("div", { className: "small" }, "reply start: " + e.staged_reply.split("\n")[0]))));
          }),
          h("h4", null, "Phase 4 replay controls on the same events (mean of 3 repeats)"),
          S.phase4.rows.length ? h(Table, { head: ["event", "baseline", "staged", "mismatch priors", "neutral filler"], rows: S.phase4.rows.map(function (r) { return { cells: [r.id, r.baseline, r.staged, r.mismatch, r.filler] }; }) }) : h("div", { className: "empty" }, "no example available"),
          h("div", { className: "small" }, S.phase4.run), h(Path, { path: S.phase4.artifact })),
        h("section", { className: "card" }, h("h3", null, "2. Consolidation (Stage 3)"),
          !C.available ? h("div", { className: "empty" }, "no example available") : h("div", null,
            h(Entry, { what: "Night " + C.night + ": " + C.entries_considered + " entries considered, clusters " + JSON.stringify(C.log.cluster_size_histogram) + ", " + C.log.summaries_written + " summary written, " + C.log.entries_flagged + " sources flagged consolidated.",
              where: C.run + ", sim time " + C.log.sim_time, why: C.why, evidence: C.evidence }),
            h("h4", null, "Frozen setting and the setting Stop 3 used, on this night"),
            h(Table, { head: ["setting", "clusters", "summarized clusters with one theme", "same-theme pairs together", "cross-theme pairs merged"],
              rows: Object.keys(C.offline_relabel.settings).map(function (k) { var s = C.offline_relabel.settings[k]; return { cells: [k, s.clusters.map(function (c) { return c.size; }).join(", "), s.summarized_clusters_with_a_single_theme + " of " + s.clusters_that_would_be_summarized, s.same_theme_pairs_together, s.cross_theme_pairs_merged] }; }) }),
            C.semantic_rows.length ? h("div", null, h("h4", null, "Summary nodes in the recorded database"), C.semantic_rows.map(function (r, i) { return h("div", { className: "item", key: i }, JSON.stringify(r)); })) : null)),
        h("section", { className: "card" }, h("h3", null, "3. Identity (Stage 4)"),
          !I.available ? h("div", { className: "empty" }, "no example available") : I.traits.map(function (t) {
            return h("div", { key: t.trait_id, className: "pair" + (t.flag ? " flag" : "") },
              h(Entry, { what: "Trait " + t.trait_id + " born on night " + t.night + " by path " + t.path + ": " + t.text, where: I.run, why: t.why, evidence: I.evidence }),
              t.source_event_text ? h("div", { className: "small" }, "source event text: ", h("i", null, t.source_event_text)) : null,
              t.later_prompt_line && t.later_prompt_line.line ? h("div", { className: "ctxbox" }, "identity_context line in a later scoring prompt (night " + t.later_prompt_line.night + ", " + t.later_prompt_line.sim_time + "):\n" + t.later_prompt_line.line) : h("div", { className: "empty" }, "no later prompt line recorded for this trait"),
              t.flag ? h("div", { className: "flagbar small" }, t.flag) : null);
          })),
        h("section", { className: "card" }, h("h3", null, "4. Run divergence (pilot arms)"),
          !V.available ? h("div", { className: "empty" }, "no example available") : h("div", null,
            h("div", { className: "small" }, "Rule: " + V.rule), h("div", { className: "small" }, V.retrieval_note),
            V.agents.map(function (a) {
              return a.differs ? h("div", { key: a.agent, className: "pair" },
                h(Entry, { what: a.agent + ": recorded action text first differs.", where: V.run + ", step " + a.step + ", " + a.clock,
                  why: "Rule fired: the cleaned action strings are not identical. baseline: \"" + a.baseline_action + "\" | staged: \"" + a.staged_action + "\".", evidence: V.evidence }),
                h("div", { className: "two" },
                  h("div", { className: "pbox base" }, h("b", null, "stored before this clock (baseline node file)"), a.stored_before_baseline.map(function (n, i) { return h("div", { key: i, className: "small" }, n.created.slice(11, 19) + " " + n.type + ": " + n.text); })),
                  h("div", { className: "pbox stag" }, h("b", null, "stored before this clock (staged node file)"), a.stored_before_staged.map(function (n, i) { return h("div", { key: i, className: "small" }, n.created.slice(11, 19) + " " + n.type + ": " + n.text); })))) :
                h("div", { key: a.agent, className: "empty" }, a.agent + ": no difference in recorded action text over the common steps");
            }),
            h("h4", null, "Candidate causes that are mechanically present"), h("ul", null, V.candidate_causes_mechanically_present.map(function (c, i) { return h("li", { key: i }, c); })),
            h("div", { className: "keepnote strong" }, V.notice))));
    } });
  }

  /* ---------------------------------------------------------------- Side by side */
  var TAIL = /\s*\(duration in minutes:\s*\d+,\s*minutes left:\s*\d+\)/g;
  function clean(s) { return String(s || "").replace(TAIL, "").split("@")[0].trim(); }
  function SideBySide(p) {
    var _a = useState({ a: null, b: null }), meta = _a[0], setMeta = _a[1];
    var _b = useState([]), agents = _b[0], setAgents = _b[1];
    var _c = useState(null), agent = _c[0], setAgent = _c[1];
    var _d = useState("07:00"), from = _d[0], setFrom = _d[1];
    var _e = useState("07:30"), to = _e[0], setTo = _e[1];
    var _f = useState(null), data = _f[0], setData = _f[1];
    var _g = useState(null), error = _g[0], setError = _g[1];
    useEffect(function () {
      Promise.all([api("/runs/" + encodeURIComponent(p.runA) + "/movement/meta"), api("/runs/" + encodeURIComponent(p.runB) + "/movement/meta")])
        .then(function (r) { setMeta({ a: r[0], b: r[1] }); var names = (r[0].persona_names || []).slice(); setAgents(names); setAgent(function (c) { return c || names[0]; }); })
        .catch(function (e) { setError(String(e)); });
    }, [p.runA, p.runB]);
    useEffect(function () {
      if (!meta.a || !meta.b || !agent || !meta.a.available || !meta.b.available) { return; }
      var day = meta.a.t_min.slice(0, 10);
      var stepOf = function (m, hhmm) { return Math.round((Date.parse(day + "T" + hhmm + ":00Z") - Date.parse(m.start_time.replace(" ", "T") + "Z")) / 1000 / m.sec_per_step); };
      var s0 = stepOf(meta.a, from), s1 = stepOf(meta.a, to);
      if (!(s1 > s0) || s1 - s0 > 2500) { setError("choose a range of at most about 6 simulated hours with a later end"); return; }
      setError(null);
      var fr = function (run) { return api("/runs/" + encodeURIComponent(run) + "/movement/frames?from_step=" + s0 + "&to_step=" + s1 + "&stride=1"); };
      var th = function (run) { return api("/runs/" + encodeURIComponent(run) + "/agents/" + encodeURIComponent(agent) + "/thoughts?t=" + encodeURIComponent(day + " " + to + ":00")).catch(function () { return null; }); };
      Promise.all([fr(p.runA), fr(p.runB), th(p.runA), th(p.runB)]).then(function (r) { setData({ s0: s0, meta: meta, fa: r[0].frames, fb: r[1].frames, ta: r[2], tb: r[3], day: day, from: from }); })
        .catch(function (e) { setError(String(e)); });
    }, [meta.a, meta.b, agent, from, to]);

    function summarize(frames) {   /* run-length of cleaned action text; conversations as runs of steps with a chat line */
      var acts = [], convs = [], cur = null;
      frames.forEach(function (f) {
        var pa = f.p[agent]; if (!pa) { return; }
        var a = clean(pa[3]);
        if (!acts.length || acts[acts.length - 1].text !== a) { acts.push({ step: f.s, text: a }); }
        var chat = pa[4];
        if (chat && chat.length) {
          if (!cur) { cur = { step: f.s, lines: {}, order: [] }; convs.push(cur); }
          chat.forEach(function (c) { var k = c[0] + ": " + c[1]; if (!cur.lines[k]) { cur.lines[k] = 1; cur.order.push(k); } });
          cur.end = f.s;
        } else { cur = null; }
      });
      return { acts: acts, convs: convs };
    }
    var body = null;
    if (data) {
      var m = data.meta.a, clk = function (s) { return new Date(Date.parse(m.start_time.replace(" ", "T") + "Z") + s * m.sec_per_step * 1000).toISOString().slice(11, 19); };
      var A = summarize(data.fa), B = summarize(data.fb), mapB = {};
      data.fb.forEach(function (f) { mapB[f.s] = f; });
      var firstDiff = null;
      data.fa.forEach(function (f) { if (firstDiff == null && mapB[f.s] && f.p[agent] && mapB[f.s].p[agent] && clean(f.p[agent][3]) !== clean(mapB[f.s].p[agent][3])) { firstDiff = f.s; } });
      var col = function (S, which, accent, thoughts) {
        return h("div", { className: "col", style: { "--c": accent } }, h("h2", null, which), h("div", { className: "sub" }, "actions, conversations and thoughts of " + agent),
          h("div", { className: "body" },
            h("h4", null, "actions (run-length, simulated clock)"),
            S.acts.map(function (x, i) { return h("div", { key: i, className: "item" + (firstDiff != null && x.step <= firstDiff && (!S.acts[i + 1] || S.acts[i + 1].step > firstDiff) ? " hl" : "") }, h("span", { className: "chip" }, clk(x.step)), " " + x.text); }),
            h("h4", null, "conversations in this window: " + S.convs.length),
            S.convs.length ? S.convs.map(function (c, i) { return h("div", { key: i, className: "item" }, h("div", { className: "meta" }, "conversation " + (i + 1) + ": " + clk(c.step) + " to " + clk(c.end || c.step)), c.order.map(function (l, j) { return h("div", { key: j, className: "say" }, l); })); }) : h("div", { className: "empty" }, "none in this window"),
            h("h4", null, "thoughts stored up to the end of the window (the last 8 the endpoint returns)"),
            thoughts && thoughts.available ? thoughts.thoughts.filter(function (x) { return x.created.slice(11, 16) >= data.from; }).map(function (x, i) { return h("div", { key: i, className: "item" }, h("span", { className: "chip" }, x.created.slice(11, 19)), " " + x.description); }) : h("div", { className: "empty" }, "no thoughts recorded"),
            h("h4", null, "retrieved memory items"), h("div", { className: "empty" }, "not logged in these runs; the Where it differs tab lists what each arm had stored before a given clock")));
      };
      body = h("div", null,
        h("div", { className: firstDiff == null ? "keepnote" : "flagbar" }, firstDiff == null ? "No difference in the recorded action text over this window (" + data.fa.length + " common frames compared)." :
          "First step where the recorded action text differs: step " + firstDiff + " at " + clk(firstDiff) + ". Rule: the action text with the duration annotation removed and the part after '@' dropped, compared step by step for the chosen agent."),
        h("div", { className: "cols two" }, col(A, p.runA, "var(--baseline)", data.ta), col(B, p.runB, "var(--staged)", data.tb)));
    }
    return h("div", { className: "view" }, h(Note),
      h("div", { className: "controls" }, h("label", null, "agent"), h("select", { value: agent || "", onChange: function (e) { setAgent(e.target.value); } }, agents.map(function (n) { return h("option", { key: n, value: n }, n); })),
        h("label", null, "from (simulated hh:mm)"), h("input", { value: from, size: 5, onChange: function (e) { setFrom(e.target.value); } }),
        h("label", null, "to"), h("input", { value: to, size: 5, onChange: function (e) { setTo(e.target.value); } }),
        h("span", { className: "kv" }, "left = " + p.runA + ", right = " + p.runB)),
      error ? h("div", { className: "err" }, error) : null, body || h("div", { className: "empty", style: { padding: 18 } }, "loading..."));
  }

  window.Views = { Findings: Findings, EdgeCases: EdgeCases, Differs: Differs, SideBySide: SideBySide };
})();
