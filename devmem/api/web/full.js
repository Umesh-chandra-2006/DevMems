/* DevMem inspector: the full-run views (seminar of 2026-10-09). Read-only. They display data/full_run.json, built offline by devmem/api/build_full_run.py from the final
   day-3 results export, the evaluation outputs, the replay controls, the run logs and the saved memory (no LLM, no network, no generated narrative: every sentence is a fixed
   template filled with logged fields). Exposed as window.Full: Findings, Differs, EdgeCases, CostByClass, NightsView, TownTools, MarkerTrack. No CDN, no JSX. */
(function () {
  "use strict";
  var DM = window.DM, h = DM.h, api = DM.api;
  var useState = React.useState, useEffect = React.useEffect;
  var STANDING = "single run per arm; descriptive results; differences can be model noise";
  var CLASS_COLORS = { planning: "#6FA8DC", action_object_description: "#3FD0C1", dialogue: "#A992F2", importance_scoring: "#E0B84F", periodic_reflection: "#E07A5F",
    post_conversation_memo: "#C27BA0", consolidation: "#7AA2F7", identity: "#9BD17A", other: "#8EA7B8" };
  var CLASS_ORDER = ["planning", "action_object_description", "dialogue", "importance_scoring", "periodic_reflection", "post_conversation_memo", "consolidation", "identity", "other"];
  var ARM_COLOR = { baseline: "var(--baseline, #E0B84F)", staged: "var(--staged, #3FD0C1)" };
  var cache = null, pending = null;

  function load() {
    if (cache) { return Promise.resolve(cache); }
    if (!pending) { pending = api("/ui/data/full_run.json").then(function (d) { cache = d; return d; }); }
    return pending;
  }
  function useData() {
    var _a = useState(cache), d = _a[0], setD = _a[1];
    var _b = useState(null), err = _b[0], setErr = _b[1];
    useEffect(function () { if (!cache) { load().then(setD).catch(function (e) { pending = null; setErr(String(e)); }); } }, []);
    return { d: d, err: err };
  }
  function Wrap(p) {
    var f = useData();
    if (f.err) { return h("div", { className: "err" }, "full-run data not found (" + f.err + "). Build it with: python -m devmem.api.build_full_run"); }
    if (!f.d) { return h("div", { className: "empty", style: { padding: 18 } }, "loading the full-run data..."); }
    return h("div", { className: "view" }, h("div", { className: "keepnote" }, STANDING + ". FULL RUN, 3 simulated days."), p.render(f.d));
  }
  function Table(p) {
    return h("table", { className: "tbl" }, h("thead", null, h("tr", null, p.head.map(function (x, i) { return h("th", { key: i }, x); }))),
      h("tbody", null, p.rows.map(function (r, i) { return h("tr", { key: i, className: r.cls || "" }, r.cells.map(function (c, j) { return h("td", { key: j }, c); })); })));
  }
  function Tile(p) { return h("div", { className: "tile" }, h("div", { className: "tilek" }, p.k), h("div", { className: "tilev" }, p.v), p.sub ? h("div", { className: "small" }, p.sub) : null); }
  function Path(p) { return h("div", { className: "artpath" }, "artifact: ", h("code", null, p.path)); }
  function f2(x) { return x == null ? "n/a" : (typeof x === "number" ? String(Math.round(x * 1000) / 1000) : String(x)); }
  function clock(step) { var d = new Date(Date.UTC(2023, 1, 13, 0, 0, 0) + step * 10000); return d.toISOString().slice(0, 19).replace("T", " "); }

  function GroupedBars(p) {   /* groups: [{label, a, b, n}] with values in [0, max] */
    var W = 560, H = 190, max = p.max || 1, gw = (W - 50) / p.groups.length, bw = Math.min(46, gw / 3);
    return h("svg", { viewBox: "0 0 " + W + " " + H, className: "costchart", preserveAspectRatio: "xMidYMid meet" },
      h("line", { x1: 40, x2: 40, y1: 10, y2: H - 40, stroke: "var(--line)" }), h("line", { x1: 40, x2: W - 6, y1: H - 40, y2: H - 40, stroke: "var(--line)" }),
      [0, 0.5, 1].map(function (f) { return h("text", { key: f, x: 6, y: H - 40 - f * (H - 60) + 3, fontSize: 9, fill: "var(--muted)" }, f2(f * max)); }),
      p.groups.map(function (g, i) {
        var x0 = 50 + i * gw, ha = (g.a || 0) / max * (H - 60), hb = (g.b || 0) / max * (H - 60);
        return h("g", { key: i },
          h("rect", { x: x0, y: H - 40 - ha, width: bw, height: ha, fill: "#E0B84F" }, h("title", null, "baseline " + f2(g.a))),
          h("rect", { x: x0 + bw + 4, y: H - 40 - hb, width: bw, height: hb, fill: "#3FD0C1" }, h("title", null, "staged " + f2(g.b))),
          h("text", { x: x0, y: H - 26, fontSize: 10, fill: "var(--ink, #ddd)" }, g.label), h("text", { x: x0, y: H - 14, fontSize: 9, fill: "var(--muted)" }, "n = " + g.n),
          h("text", { x: x0, y: H - 44 - Math.max(ha, hb) - 2, fontSize: 9, fill: "var(--ink, #ddd)" }, f2(g.a) + " / " + f2(g.b)));
      }));
  }
  function Legend2() { return h("div", { className: "legend2" }, h("span", null, h("span", { className: "swatch", style: { background: "#E0B84F" } }), "baseline"), h("span", null, h("span", { className: "swatch", style: { background: "#3FD0C1" } }), "staged")); }

  function StackedByClass(p) {   /* rows: [{label, counts: {class: n}}] */
    var max = Math.max.apply(null, p.rows.map(function (r) { return CLASS_ORDER.reduce(function (s, k) { return s + (r.counts[k] || 0); }, 0); }).concat([1]));
    var W = 600, rh = 26, H = p.rows.length * rh + 20;
    return h("svg", { viewBox: "0 0 " + W + " " + H, className: "costchart", preserveAspectRatio: "xMidYMid meet" },
      p.rows.map(function (r, i) {
        var x = 130, y = 8 + i * rh;
        return h("g", { key: i }, h("text", { x: 4, y: y + 15, fontSize: 10, fill: "var(--ink, #ddd)" }, r.label),
          CLASS_ORDER.map(function (k) {
            var v = r.counts[k] || 0; if (!v) { return null; }
            var w = v / max * (W - 140); var el = h("rect", { key: k, x: x, y: y, width: w, height: 18, fill: CLASS_COLORS[k] }, h("title", null, r.label + ": " + k + " " + v)); x += w; return el;
          }),
          h("text", { x: x + 4, y: y + 14, fontSize: 9, fill: "var(--muted)" }, CLASS_ORDER.reduce(function (s, k) { return s + (r.counts[k] || 0); }, 0)));
      }));
  }
  function ClassLegend() { return h("div", { className: "legend2" }, CLASS_ORDER.map(function (k) { return h("span", { key: k }, h("span", { className: "swatch", style: { background: CLASS_COLORS[k] } }), k.replace(/_/g, " ")); })); }

  /* ---------------------------------------------------------------- Findings */
  function Findings() {
    return h(Wrap, { render: function (d) {
      var R = d.recall, rp = d.replay, m2 = d.m2, T = d.tiles;
      var sumByArm = function (a) {
        var tot = {}; var days = d.calls_by_class[a].unique_by_day_class || {};
        Object.keys(days).forEach(function (day) { Object.keys(days[day]).forEach(function (k) { tot[k] = (tot[k] || 0) + days[day][k]; }); });
        return tot;
      };
      var conds = ["baseline", "filler", "mismatch", "staged_replayed", "staged_own"];
      var friction = rp.available ? rp.friction_by_agent : {};
      return h("div", null,
        h("div", { className: "flagbar" }, "FINAL day-3 export: " + d.export_label + ". Built " + d.built_at),
        h("div", { className: "keepnote strong" }, "D1: " + d.d1_wording + "."),
        h("section", { className: "card" }, h("h3", null, "Prediction scorecard (registered before any data; right, wrong or undecidable, whatever the direction)"),
          h(Table, { head: ["id", "prediction", "outcome", "reason", "numbers"], rows: d.scorecard.map(function (s) {
            return { cls: "out-" + String(s.outcome).replace(/ /g, "-"), cells: [s.id, s.prediction, h("b", null, s.outcome), s.reason, Object.keys(s.numbers).map(function (k) { return k + " = " + f2(s.numbers[k]); }).join("; ")] };
          }) }), h(Path, { path: "docs/phase9_results_export_day3.md and .json" })),
        h("section", { className: "card" }, h("h3", null, "Efficiency tiles (day-3 checkpoint, unique calls with replays removed)"),
          h("div", { className: "tiles" },
            h(Tile, { k: "E1 calls, baseline", v: T.baseline.E1_unique, sub: "raw " + T.baseline.E1_raw }), h(Tile, { k: "E1 calls, staged", v: T.staged.E1_unique, sub: "raw " + T.staged.E1_raw }),
            h(Tile, { k: "E2 tokens per scoring call, baseline", v: f2(T.baseline.E2_mean_tokens_in) }), h(Tile, { k: "E2 tokens per scoring call, staged", v: f2(T.staged.E2_mean_tokens_in) }),
            h(Tile, { k: "E3 consolidated fraction, baseline", v: f2(T.baseline.E3_consolidated_fraction), sub: "0 by construction" }), h(Tile, { k: "E3 consolidated fraction, staged", v: f2(T.staged.E3_consolidated_fraction) })),
          h("div", { className: "small" }, "E1 was registered as staged more calls than baseline by under 10 percent. Periodic reflection is off in the staged arm (D1), so no efficiency claim is made for the stages.")),
        h("section", { className: "card" }, h("h3", null, "Recall: mean checklist score by distance (baseline / staged)"),
          h(GroupedBars, { groups: R.by_distance.map(function (g) { return { label: g.group, a: g.baseline_mean, b: g.staged_mean, n: g.n }; }), max: 1 }), h(Legend2),
          h("div", { className: "small" }, "Distance in days between the event and the question; theme count = the three repeated-theme questions. Excluded: " + (R.excluded.join(", ") || "none") + ". Grader item agreement " + f2(R.grader.item_agreement) + " on " + R.grader.items_checked + " hand-labelled items (developer-authored). Bootstrap of staged minus baseline: mean " + f2(R.bootstrap.mean) + ", interval " + f2(R.bootstrap.ci95[0]) + " to " + f2(R.bootstrap.ci95[1]) + " (descriptive, " + R.bootstrap.agents + " agents).")),
        h("section", { className: "card" }, h("h3", null, "Recall: per question"),
          h(Table, { head: ["question", "agent", "type", "event", "distance", "baseline score", "baseline strict", "staged score", "staged strict", "note"], rows: R.rows.map(function (r) {
            var diff = r.baseline && r.staged && r.baseline.score !== r.staged.score;
            return { cls: diff ? "diffrow" : "", cells: [r.question_id, r.agent, r.type, r.event_id || "", r.distance_days == null ? "theme" : r.distance_days, r.baseline ? f2(r.baseline.score) : "n/a", r.baseline ? String(r.baseline.strict) : "n/a",
              r.staged ? f2(r.staged.score) : "n/a", r.staged ? String(r.staged.strict) : "n/a", r.excluded ? "excluded (injection failed in an arm)" : (diff ? "arms differ" : "")] };
          }) }), h("div", { className: "small" }, R.retrieval_note)),
        h("section", { className: "card" }, h("h3", null, "Calls by class per arm (whole run, unique calls, rule-based classes from the prompts)"),
          h(StackedByClass, { rows: [{ label: "baseline", counts: sumByArm("baseline") }, { label: "staged", counts: sumByArm("staged") }] }), h(ClassLegend),
          h("div", { className: "small" }, "The router's keyword tag is not used: its dialogue tag has 73 to 78 percent false matches (audit). Periodic reflection = focal points and insights; post-conversation memo = planning thought and memo after a conversation (both arms)."),
          h(Path, { path: "devmem/eval/phase9/purpose_classes.py, docs/phase9_purpose_tag_audit.json" })),
        h("section", { className: "card" }, h("h3", null, "Replay controls: mean importance of the social-friction events per agent, by condition"),
          !rp.available ? h("div", { className: "empty" }, "replay controls not available") : h("div", null,
            h(Table, { head: ["agent"].concat(conds.map(function (c) { return c === "staged_replayed" ? "staged_replayed (registered)" : (c === "staged_own" ? "staged_own (recorded in-run, sensitivity)" : c); })), rows: Object.keys(friction).map(function (a) {
              return { cells: [a].concat(conds.map(function (c) { var x = friction[a][c]; if (!x) { return c === "staged_replayed" ? "being re-run" : "n/a"; } return f2(x.mean) + " (n = " + x.n + ")"; })) };
            }) }),
            h("h4", null, "Whole sample (" + rp.n_injected + " injected + " + rp.n_natural + " natural events)"),
            h(Table, { head: ["condition", "n", "mean importance"], rows: conds.map(function (c) { var x = rp.whole_sample_means[c]; return { cells: [c, x ? x.n : "n/a", x ? f2(x.mean) : (c === "staged_replayed" ? "being re-run" : "n/a")] }; }) }),
            h("div", { className: "small" }, "Seed 20261008. The staged condition replays the staged scorer prompt (priors block plus the identity context recorded for each event); the recorded in-run scores are kept as a labelled sensitivity line. These are scoring results only; they say nothing about behaviour."))),
        h("section", { className: "card" }, h("h3", null, "M2 coherence: day-1 against day-3 answers, judged"),
          !m2 || !m2.available ? h("div", { className: "empty" }, "not available") : h("div", null,
            h("div", null, "Judge calibration on 20 developer-authored pairs: accuracy " + f2(m2.calibration_accuracy) + ", interpretable (at least 0.8): " + String(m2.coherence_interpretable) + ", parse failures " + m2.calibration_parse_failures),
            h("h4", null, "Confusion matrix (true label by judged label)"),
            h(Table, { head: ["true \\ judged", "consistent", "contradictory", "unrelated", "parse failure"], rows: Object.keys(m2.confusion_matrix_true_by_judged).map(function (t) { var x = m2.confusion_matrix_true_by_judged[t]; return { cells: [t, x.consistent, x.contradictory, x.unrelated, x.parse_failure] }; }) }),
            h(Table, { head: ["arm", "pairs", "contradiction rate", "per agent (consistent / contradictory / unrelated)"], rows: ["baseline", "staged"].map(function (a) {
              var x = m2.arms[a]; return { cells: [a, x.pairs, f2(x.contradiction_rate), Object.keys(x.per_agent).map(function (n) { var y = x.per_agent[n]; return n + ": " + y.consistent + " / " + y.contradictory + " / " + y.unrelated; }).join("; ")] };
            }) }), h("div", { className: "small" }, "No directional prediction was registered for coherence. 18 pairs per arm: a difference of one or two pairs is not a finding."))),
        h("section", { className: "card" }, h("h3", null, "D-1 trait provenance"),
          h("div", null, d.nights.provenance_flagged + " of " + d.nights.provenance_n + " Stage 4 traits are closer (cached-embedding cosine) to the agent's priors text than to their best source. Registered prediction: at least one third; scored wrong.")));
    } });
  }

  /* ---------------------------------------------------------------- Where it differs and why */
  function Entry(p) {
    return h("div", { className: "entry" }, h("div", null, h("span", { className: "lab" }, "WHAT "), p.what), h("div", null, h("span", { className: "lab" }, "WHERE "), p.where),
      h("div", null, h("span", { className: "lab" }, "WHY "), p.why), h("div", null, h("span", { className: "lab" }, "EVIDENCE "), h("code", null, p.evidence)));
  }
  function Differs() {
    return h(Wrap, { render: function (d) {
      var R = d.recall, byId = {}; R.rows.forEach(function (r) { byId[r.question_id] = r; });
      var N = d.nights, SC = d.scoring_card, V = d.divergence;
      var ex = N.nights.filter(function (n) { return n.summaries.length >= 3; })[0] || N.nights.filter(function (n) { return n.summaries.length; })[0];
      var tr = N.traits.filter(function (t) { return t.event_sources.length || t.semantic_sources.length; })[0];
      return h("div", null,
        h("section", { className: "card" }, h("h3", null, "1. Recall questions where the arms differ (" + R.differing_question_ids.join(", ") + ")"),
          R.differing_question_ids.map(function (id) {
            var r = byId[id];
            return h("div", { key: id, className: "pair" },
              h(Entry, { what: id + " (" + r.agent + ", " + r.type + (r.event_id ? ", event " + r.event_id : "") + "): baseline score " + f2(r.baseline.score) + ", staged score " + f2(r.staged.score) + ".", where: "the day-3 checkpoint copy of each arm; the question: " + r.question,
                why: "Rule fired: the key-fact checklist score differs (" + (r.checklist || []).join(", ") + "). Retrieved memory items: not logged (the harness logged only how many).", evidence: "devmem/storage/phase9_eval/{baseline,staged}/evaluation.json" }),
              h("div", { className: "two" },
                h("div", { className: "pbox base" }, h("b", null, "baseline answer"), h("pre", null, r.baseline_answer || "n/a"), h("div", { className: "small" }, "items matched: " + JSON.stringify(r.baseline_items))),
                h("div", { className: "pbox stag" }, h("b", null, "staged answer"), h("pre", null, r.staged_answer || "n/a"), h("div", { className: "small" }, "items matched: " + JSON.stringify(r.staged_items)))));
          }), h("div", { className: "small" }, R.retrieval_note)),
        h("section", { className: "card" }, h("h3", null, "2. Scoring of the " + SC.rows.length + " perceived injected events, baseline against staged"),
          h(Table, { head: ["event", "agent", "type", "step", "event text", "baseline importance", "staged importance", "staged minus baseline", "identity context in the staged prompt"], rows: SC.rows.map(function (r) {
            return { cells: [r.id, r.agent, r.type, r.step, r.text, r.baseline_importance, r.staged_importance, r.staged_importance - r.baseline_importance, r.identity_context_in_staged_prompt ? "yes (see below)" : "none yet"] };
          }) }), h("div", { className: "small" }, SC.note),
          Object.keys(SC.priors_block_by_agent).map(function (a) { return h("div", { key: a, className: "pbox stag" }, h("b", null, "priors block appended to the staged scoring prompt: " + a), h("pre", { className: "hlblock" }, SC.priors_block_by_agent[a])); }),
          SC.rows.filter(function (r) { return r.identity_context_in_staged_prompt; }).slice(0, 2).map(function (r) { return h("div", { key: r.id, className: "ctxbox" }, h("b", null, "identity context in the staged prompt for " + r.id + " (" + r.agent + ")"), h("pre", null, r.identity_context_in_staged_prompt)); }),
          h(Path, { path: "devmem/storage/p7_*/injection_log.jsonl; devmem/storage/p7_staged/memory.db (event_scoring_context)" })),
        h("section", { className: "card" }, h("h3", null, "3. One real consolidation night and one real trait"),
          !ex ? h("div", { className: "empty" }, "none") : h("div", null,
            h(Entry, { what: ex.agent + ", night " + ex.night + ": " + ex.entries_considered + " entries considered, cluster sizes " + JSON.stringify(ex.cluster_size_histogram) + ", " + ex.summaries_written + " summaries written, " + ex.summaries_reinforced + " reinforced.",
              where: "staged arm, sweep at sim " + ex.sim_time + " (average linkage, threshold " + ex.threshold + ")", why: "Rule fired: entries with importance at least 3 and no 'idle' text, clustered at mean pairwise cosine 0.82; each cluster of 3 or more becomes one summary (at most 6 a night).", evidence: "devmem/storage/p7_staged/consolidation_log.jsonl; memory.db" }),
            ex.summaries.map(function (s, i) { return h("div", { key: i, className: "item" }, h("b", null, s.action + ": "), s.summary, h("ul", null, s.sources.slice(0, 6).map(function (x, j) { return h("li", { key: j, className: "small" }, (x.time || "") + "  [" + x.importance + "]  " + x.text); }), s.sources.length > 6 ? h("li", { className: "small" }, "... " + (s.sources.length - 6) + " more sources") : null)); })),
          tr ? h("div", { className: "pair" + (tr.closer_to_priors_than_to_best_source ? " flag" : "") },
            h(Entry, { what: "Trait " + tr.trait_id + " (night " + tr.night + ", path " + tr.path + "): " + tr.text, where: "staged arm, created at sim " + tr.sim_time, why: "Rule fired: path " + tr.path + " graduates a theme counted on 3 distinct nights or 4 events in one night, or an event scored at least 9. Provenance cosine to the priors text " + f2(tr.provenance_cosine_to_priors) + ", to the best source " + f2(tr.provenance_best_source_cosine) + (tr.closer_to_priors_than_to_best_source ? " (flagged: closer to the priors)." : "."), evidence: "devmem/storage/p7_staged/memory.db (identity_traits)" }),
            h("ul", null, tr.semantic_sources.map(function (s, i) { return h("li", { key: "s" + i, className: "small" }, "summary source: " + s.summary); }), tr.event_sources.map(function (s, i) { return h("li", { key: "e" + i, className: "small" }, "event source: " + (s.time || "") + "  " + s.text); }))) : null),
        h("section", { className: "card" }, h("h3", null, "4. First behavioural divergence of the two full runs, per agent"),
          h("div", { className: "small" }, "Rule: " + V.rule), h("div", { className: "small" }, V.retrieval_note),
          Object.keys(V.agents).map(function (a) {
            var x = V.agents[a];
            return x ? h("div", { key: a, className: "pair" }, h(Entry, { what: a + ": the recorded action text first differs.", where: "step " + x.step + ", " + x.clock, why: "Rule fired: the cleaned action strings are not identical. Left (staged): \"" + x.left_action + "\" | right (baseline): \"" + x.right_action + "\".", evidence: "movement recordings of p7_staged and p7_baseline" }))
              : h("div", { key: a, className: "empty" }, a + ": no difference in recorded action text over the common steps");
          }),
          h("div", { className: "keepnote strong" }, "A difference in action text is a recorded difference, not a verdict on either arm; the runs also differ by chance (model sampling) and by the staged memory.")));
    } });
  }

  /* ---------------------------------------------------------------- Edge cases */
  function EdgeCases() {
    return h(Wrap, { render: function (d) {
      return h("div", null, h("div", { className: "flagbar" }, "FULL-RUN INCIDENTS AND LIMITS, with claims-ledger ids"),
        d.incidents.map(function (e, i) {
          return h("section", { className: "card flag", key: i }, h("h3", null, e.title + "  [" + e.ledger + "]"), h("div", null, h("b", null, "what "), e.what), h("div", null, h("b", null, "numbers "), e.numbers), h(Path, { path: e.evidence }));
        }));
    } });
  }

  /* ---------------------------------------------------------------- Cost view by class */
  function CostByClass() {
    return h(Wrap, { render: function (d) {
      return h("div", null, h("h3", null, "Calls by class per simulated day (unique calls; rule-based classes from the prompts)"),
        ["staged", "baseline"].map(function (a) {
          var c = d.calls_by_class[a], days = c.unique_by_day_class || {};
          var rows = Object.keys(days).sort().map(function (k) { return { label: "day " + k, counts: days[k] }; });
          return h("section", { className: "card", key: a }, h("h4", { style: { color: ARM_COLOR[a] } }, (a === "staged" ? "left: p7_staged" : "right: p7_baseline") + " (" + c.unique_total + " unique calls, " + c.raw_total + " raw)"),
            h(StackedByClass, { rows: rows }),
            h(Table, { head: ["class"].concat(rows.map(function (r) { return r.label; })).concat(["total"]), rows: CLASS_ORDER.map(function (k) { var tot = 0; var cells = rows.map(function (r) { var v = r.counts[k] || 0; tot += v; return v; }); return { cells: [k.replace(/_/g, " ")].concat(cells).concat([tot]) }; }) }),
            h("div", { className: "small" }, "unclassified: " + f2(c.other_share_of_unique) + " of unique calls; ledger and delivered-reply log paired by position (" + c.pairing.positions_disagreeing + " disagreements of " + c.pairing.paired + ")."));
        }), h(ClassLegend),
        h("div", { className: "keepnote strong" }, "Periodic reflection (focal points and insights) is off in the staged arm; the post-conversation memo calls run in both arms. No efficiency claim is made for the stages."));
    } });
  }

  /* ---------------------------------------------------------------- per-night memory view (Memory inspector tab) */
  function NightsView(p) {
    var f = useData();
    var _a = useState("Isabella Rodriguez"), agent = _a[0], setAgent = _a[1];
    if (!f.d) { return f.err ? h("div", { className: "err" }, f.err) : h("div", { className: "empty" }, "loading..."); }
    var d = f.d, names = ["Isabella Rodriguez", "Klaus Mueller", "Maria Lopez"];
    var picker = h("div", { className: "agents" }, names.map(function (n) { return h("button", { key: n, className: agent === n ? "on" : "", onClick: function () { setAgent(n); } }, n); }));
    if (p.run === "p7_baseline") {
      var B = d.baseline_reflections[agent];
      return h("div", { className: "view" }, h("div", { className: "keepnote" }, STANDING), picker,
        h("section", { className: "card" }, h("h3", null, "Baseline counterpart: node stream and thoughts (" + agent + ")"),
          h("div", null, B.stream_nodes + " nodes in the saved stream, " + B.thought_nodes + " of them thought nodes (periodic reflections: insights built on evidence nodes; and " + B.post_conversation_planning_thoughts + " post-conversation planning thoughts)."),
          h("div", { className: "small" }, "Periodic reflection (focal-point and insight generation) is on in the baseline and off in the staged arm."),
          h("ul", null, B.thoughts.slice(0, 40).map(function (x, i) { return h("li", { key: i, className: "small" }, x.created + "  [" + x.evidence_nodes + " evidence nodes]  " + x.text); }))));
    }
    var ns = d.nights.nights.filter(function (n) { return n.agent === agent; }), tr = d.nights.traits.filter(function (t) { return t.agent === agent; });
    return h("div", { className: "view" }, h("div", { className: "keepnote" }, STANDING), picker,
      h("section", { className: "card" }, h("h3", null, "Stage 3: each sweep of " + agent),
        ns.map(function (n) {
          return h("div", { key: n.night, className: "pair" },
            h(Entry, { what: "Night " + n.night + " at sim " + n.sim_time + ": " + n.entries_considered + " entries considered; cluster sizes " + JSON.stringify(n.cluster_size_histogram) + "; " + n.summaries_written + " summaries written, " + n.summaries_reinforced + " reinforced; " + n.entries_flagged + " entries flagged consolidated.",
              where: "staged arm, status " + n.status + ", threshold " + n.threshold + ", " + n.linkage + " linkage", why: "Entries with importance at least 3 and no idle text are clustered; clusters of 3 or more are summarised (at most 6 a night, 12 sources each).", evidence: "devmem/storage/p7_staged/consolidation_log.jsonl" }),
            n.summaries.map(function (s, i) { return h("div", { key: i, className: "item" }, h("b", null, s.action + (s.match_similarity ? " (match " + f2(s.match_similarity) + ")" : "") + ": "), s.summary, h("details", null, h("summary", null, s.sources.length + " source memories"), h("ul", null, s.sources.map(function (x, j) { return h("li", { key: j, className: "small" }, (x.time || "") + "  [" + x.importance + "]  " + x.text); })))); }),
            n.identity_step && n.identity_step.traits_created.length ? h("div", { className: "small" }, "Stage 4 step of this night created: " + n.identity_step.traits_created.join(", ")) : null);
        })),
      h("section", { className: "card" }, h("h3", null, "Stage 4: traits of " + agent + " with their sources and the D-1 provenance cosine"),
        tr.map(function (t) {
          return h("div", { key: t.trait_id, className: "pair" + (t.closer_to_priors_than_to_best_source ? " flag" : "") },
            h("div", null, h("b", null, t.trait_id + " (night " + t.night + ", path " + t.path + (t.active ? "" : ", evicted") + "): "), t.text),
            h("div", { className: "small" }, "cosine to the priors text " + f2(t.provenance_cosine_to_priors) + ", to the best source " + f2(t.provenance_best_source_cosine) + (t.closer_to_priors_than_to_best_source ? "   FLAGGED: closer to the priors than to its sources" : "")),
            h("details", null, h("summary", null, "sources (" + (t.semantic_sources.length + t.event_sources.length) + ")"), h("ul", null,
              t.semantic_sources.map(function (s, i) { return h("li", { key: "s" + i, className: "small" }, "summary: " + s.summary); }), t.event_sources.map(function (s, i) { return h("li", { key: "e" + i, className: "small" }, "event: " + s.text); }))));
        }),
        h("h4", null, "identity_context text as fed into the scoring prompt (active traits at the end of the run)"), h("pre", { className: "ctxbox" }, d.nights.identity_context_final_active_traits[agent] || "none")));
  }

  /* ---------------------------------------------------------------- town tools: day buttons, injected-event jumps, night markers */
  function toMinute(s) { return DM.toMin(s); }
  function TownTools(p) {
    var f = useData();
    if (!f.d) { return null; }
    var inj = f.d.injections, nights = f.d.nights.nights.filter(function (n) { return n.night > 0; });
    var days = [1, 2, 3].map(function (n) { return { n: n, t: toMinute("2023-02-" + (12 + n) + " 06:00:00") }; });
    var lo = p.range[0], hi = p.range[1], span = Math.max(1, hi - lo), W = 1000, x = function (m) { return ((m - lo) / span) * W; };
    var seen = {};
    return h("div", { className: "towntools" },
      h("div", { className: "bar" },
        days.map(function (d) { return h("button", { key: d.n, onClick: function () { p.onSeek(d.t); } }, "Day " + d.n); }),
        h("span", { className: "kv" }, "jump to an injected event "),
        h("select", { onChange: function (e) { var v = e.target.value; if (v) { p.onSeek(toMinute((inj.filter(function (i) { return i.id === v; })[0].staged || inj.filter(function (i) { return i.id === v; })[0].baseline).clock)); } }, value: "" },
          h("option", { value: "" }, "choose one of the 27"),
          inj.map(function (i) { var s = i.staged || i.baseline; return h("option", { key: i.id, value: i.id }, i.id + "  " + i.agent + "  step " + s.step + (i.both_perceived ? "" : "  (not perceived in both arms)")); }))),
      h("svg", { className: "track markers", viewBox: "0 0 " + W + " 34", preserveAspectRatio: "none" },
        nights.map(function (n, i) { var key = n.sim_time; var el = seen[key] ? null : h("g", { key: "n" + i }, h("line", { x1: x(toMinute(n.sim_time)), x2: x(toMinute(n.sim_time)), y1: 2, y2: 16, stroke: "#E0B84F", strokeWidth: 3 }, h("title", null, "Stage 3 sweep, night " + n.night + ", " + n.sim_time))); seen[key] = 1; return el; }),
        inj.map(function (i, k) { var s = i.staged || i.baseline; return h("line", { key: "i" + k, x1: x(toMinute(s.clock)), x2: x(toMinute(s.clock)), y1: 20, y2: 32, stroke: i.both_perceived ? "#3FD0C1" : "#E07A5F", strokeWidth: 2 }, h("title", null, i.id + " " + i.agent + " step " + s.step)); }),
        h("line", { x1: x(p.t), x2: x(p.t), y1: 0, y2: 34, stroke: "var(--gold-hi, #fff)", strokeWidth: 2 })),
      h("div", { className: "hint" }, "Gold ticks: the Stage 3 night sweeps (staged arm, nights 1 to 3; each agent sweeps when it falls asleep). Teal ticks: the 27 injected events (red = not perceived in both arms). Day buttons jump to 06:00."));
  }

  window.Full = { Findings: Findings, Differs: Differs, EdgeCases: EdgeCases, CostByClass: CostByClass, NightsView: NightsView, TownTools: TownTools };
})();
