/* DevMem memory inspector: shared helpers and the memory components (Stage 1 to 4 columns). Read-only: GET requests only.
   No CDN, no JSX, no compiler: React.createElement through the helper `h`. Exposed as window.DM for town.js, cost.js and app.js. */
(function () {
  "use strict";
  var h = function (type, props) { return React.createElement.apply(null, [type, props].concat([].slice.call(arguments, 2))); };

  var STAGE = {
    0: { name: "infrastructure (sleep windows, ledger windows)", color: "var(--s0)" },
    1: { name: "Stage 1 priors", color: "var(--s1)" },
    2: { name: "Stage 2 episodic", color: "var(--s2)" },
    3: { name: "Stage 3 semantic", color: "var(--s3)" },
    4: { name: "Stage 4 identity", color: "var(--s4)" }
  };

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

  var TAIL_RE = /\s*\(duration in minutes:\s*\d+,\s*minutes left:\s*\d+\)/g;
  function cleanText(t) { return String(t == null ? "" : t).replace(TAIL_RE, ""); }   /* display only: hides the raw duration annotation */

  function LabelBar(p) {
    var labels = (p.labels || []).filter(Boolean);
    var _o = React.useState(false), open = _o[0], setOpen = _o[1];
    var kv = function (k, v) { return h("span", { className: "kv" }, k + " ", h("b", null, v == null ? "unknown" : String(v))); };
    var pilot = labels.some(function (l) { return /PILOT/i.test(String(l.mode || "")) || /PILOT/i.test(String(l.note || "")); });
    var summary = labels.map(function (l) { return l.run; }).join(" | ");
    return h("div", null,
      h("div", { className: "labelbar" + (open ? " open" : "") },
        h("span", { className: "title" }, "DevMem Memory Inspector"),
        h("span", { className: "badge" + (pilot ? " pilot" : "") }, pilot ? "PILOT, not a result" : (labels[0] ? String(labels[0].mode || "recorded").slice(0, 40) : "recorded")),
        h("span", { className: "kv" }, summary),
        open ? labels.map(function (l, i) {
          return h("span", { className: "labelgroup", key: i },
            labels.length > 1 ? h("span", { className: "side" }, i === 0 ? "left" : "right") : null,
            kv("run", l.run), kv("recorded or live", l.mode), kv("scripted or natural", l.origin), kv("model", l.model),
            kv("normalizer", l.normalizer), kv("stages", l.stages));
        }) : null,
        h("button", { className: "expand", onClick: function () { setOpen(!open); } }, open ? "collapse label" : "expand label"),
        h("span", { className: "ro" }, "read only")),
      h("div", { className: "nonclaim" }, "single run per arm; differences can be model noise; PILOT is not a result. This view displays what was recorded in the run and makes no claim about recall, coherence or efficiency. Label source: " +
        labels.map(function (l) { return l.label_source || "none"; }).join(" | ") + (labels[0] && labels[0].note ? ". " + labels[0].note : "")));
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
    var st = p.state.stage2_episodic, hide = p.hideIdle, uid = p.uid || "";
    var list = st.entries.filter(function (e) { return !(hide && e.is_idle_text); }).slice().reverse();
    var shown = list.slice(0, 400);
    var toggle = h("div", { className: "toggle" },
      h("input", { type: "checkbox", id: "hide-idle" + uid, checked: hide, onChange: function (e) { p.onHideIdle(e.target.checked); } }),
      h("label", { htmlFor: "hide-idle" + uid }, "hide entries whose text contains \"idle\" (" + st.idle_text_entries + " up to this time)"));
    return h(Col, { title: "Stage 2: episodic", color: STAGE[2].color, extra: toggle,
      sub: st.entries_total_up_to_t + " entries up to this time, newest first" + (list.length > shown.length ? ", showing 400 of " + list.length : "") },
      shown.length === 0 ? h("div", { className: "empty" }, "nothing recorded yet at this time") :
        shown.map(function (e) {
          var cls = "item" + (p.hl[e.entry_id] ? " hl" : "") + (e.is_idle_text ? " dim" : "");
          var sc = e.scoring.status === "not recorded" ? "scoring context: not recorded" :
            "scored " + e.scoring.status + (e.scoring.trait_ids_in_prompt && e.scoring.trait_ids_in_prompt.length ? " with " + e.scoring.trait_ids_in_prompt.length + " trait(s) in the prompt" : "");
          return h("div", { className: cls, key: e.entry_id, id: "ep-" + uid + e.entry_id },
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
    var st = p.state.stage4_identity, ctx = p.state.identity_context_at_t, uid = p.uid || "";
    var traits = (st.traits || []).slice().reverse();
    var toggle = h("div", { className: "toggle" },
      h("input", { type: "checkbox", id: "diag" + uid, checked: p.diag, onChange: function (e) { p.onDiag(e.target.checked); } }),
      h("label", { htmlFor: "diag" + uid }, "provenance diagnostic (cached embeddings only, no network)"));
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

  /* selection highlight sets: which episodic entries and summaries a selected summary or trait points to */
  function highlightSets(state, sel) {
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
    return { hl: hl, hlSummary: hlSummary };
  }

  window.DM = { h: h, STAGE: STAGE, api: api, toMin: toMin, fromMin: fromMin, pretty: pretty, LabelBar: LabelBar, Col: Col, Priors: Priors,
    Episodic: Episodic, Semantic: Semantic, Identity: Identity, highlightSets: highlightSets, cleanText: cleanText };
})();
