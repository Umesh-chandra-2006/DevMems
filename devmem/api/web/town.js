/* DevMem memory inspector: the town replay (Phase 8 Stop 2).
   Upstream's town (map, tilesets, character atlases, speech bubble) is read from /town-assets (served read-only from
   reverie/environment/frontend_server/static_dirs/assets; nothing is copied, no upstream file is edited) and drawn with the vendored
   Phaser 3.55.2, the version upstream's own pages reference. The scene follows upstream's replay (same tilesets, same layers, same atlas
   animations) but is driven by recorded movement frames (GET /runs/{run}/movement/frames) and a clock shared by both panes.
   Clicking an avatar opens that agent's memory panel at the current replay time. Read-only: GET requests only. */
(function () {
  "use strict";
  var DM = window.DM, h = DM.h;
  var useState = React.useState, useEffect = React.useEffect, useRef = React.useRef;
  var TILE = 32, ASSET = "/town-assets/", CHUNK = 1440;
  var MAP = "the_ville/visuals/map_assets/";
  var CUTE = MAP + "cute_rpg_word_VXAce/tilesets/";
  var IMAGES = [
    ["blocks_1", MAP + "blocks/blocks_1.png"], ["walls", MAP + "v1/Room_Builder_32x32.png"],
    ["interiors_pt1", MAP + "v1/interiors_pt1.png"], ["interiors_pt2", MAP + "v1/interiors_pt2.png"], ["interiors_pt3", MAP + "v1/interiors_pt3.png"],
    ["interiors_pt4", MAP + "v1/interiors_pt4.png"], ["interiors_pt5", MAP + "v1/interiors_pt5.png"],
    ["CuteRPG_Field_B", CUTE + "CuteRPG_Field_B.png"], ["CuteRPG_Field_C", CUTE + "CuteRPG_Field_C.png"], ["CuteRPG_Harbor_C", CUTE + "CuteRPG_Harbor_C.png"],
    ["CuteRPG_Village_B", CUTE + "CuteRPG_Village_B.png"], ["CuteRPG_Forest_B", CUTE + "CuteRPG_Forest_B.png"], ["CuteRPG_Desert_C", CUTE + "CuteRPG_Desert_C.png"],
    ["CuteRPG_Mountains_B", CUTE + "CuteRPG_Mountains_B.png"], ["CuteRPG_Desert_B", CUTE + "CuteRPG_Desert_B.png"], ["CuteRPG_Forest_C", CUTE + "CuteRPG_Forest_C.png"]
  ];
  var TILESET_NAMES = [["blocks", "blocks_1"], ["Room_Builder_32x32", "walls"], ["interiors_pt1", "interiors_pt1"], ["interiors_pt2", "interiors_pt2"],
    ["interiors_pt3", "interiors_pt3"], ["interiors_pt4", "interiors_pt4"], ["interiors_pt5", "interiors_pt5"], ["CuteRPG_Field_B", "CuteRPG_Field_B"],
    ["CuteRPG_Field_C", "CuteRPG_Field_C"], ["CuteRPG_Harbor_C", "CuteRPG_Harbor_C"], ["CuteRPG_Village_B", "CuteRPG_Village_B"], ["CuteRPG_Forest_B", "CuteRPG_Forest_B"],
    ["CuteRPG_Desert_C", "CuteRPG_Desert_C"], ["CuteRPG_Mountains_B", "CuteRPG_Mountains_B"], ["CuteRPG_Desert_B", "CuteRPG_Desert_B"], ["CuteRPG_Forest_C", "CuteRPG_Forest_C"]];
  var LAYERS = ["Bottom Ground", "Exterior Ground", "Exterior Decoration L1", "Exterior Decoration L2", "Interior Ground", "Wall",
    "Interior Furniture L1", "Interior Furniture L2 ", "Foreground L1", "Foreground L2"];

  window.TownDebug = { panes: {} };   /* handles for automated checks only (click an avatar, read its screen position) */

  function initials(name) { return name.split(" ").map(function (p) { return p[0]; }).join("").toUpperCase(); }

  function createTown(host, names, cb) {
    var ctrl = { sprites: {}, targets: {}, last: {}, dir: {}, labels: {}, bubbles: {}, emoji: {}, selected: null, snap: true, ready: false };
    function preload() {
      var s = this;
      IMAGES.forEach(function (t) { s.load.image(t[0], ASSET + t[1]); });
      s.load.tilemapTiledJSON("map", ASSET + "the_ville/visuals/the_ville_jan7.json");
      names.forEach(function (n) { var k = n.replace(" ", "_"); s.load.atlas(k, ASSET + "characters/" + k + ".png", ASSET + "characters/atlas.json"); });
      s.load.image("speech_bubble", ASSET + "speech_bubble/v3.png");
    }
    function create() {
      var s = this;
      ctrl.scene = s;
      var map = s.make.tilemap({ key: "map" });
      var ts = {};
      TILESET_NAMES.forEach(function (t) { ts[t[0]] = map.addTilesetImage(t[0], t[1]); });
      var group = [ts.CuteRPG_Field_B, ts.CuteRPG_Field_C, ts.CuteRPG_Harbor_C, ts.CuteRPG_Village_B, ts.CuteRPG_Forest_B, ts.CuteRPG_Desert_C,
        ts.CuteRPG_Mountains_B, ts.CuteRPG_Desert_B, ts.CuteRPG_Forest_C, ts.interiors_pt1, ts.interiors_pt2, ts.interiors_pt3, ts.interiors_pt4,
        ts.interiors_pt5, ts.Room_Builder_32x32];
      LAYERS.forEach(function (name) {
        var layer = map.createLayer(name, name === "Wall" ? [ts.CuteRPG_Field_C, ts.Room_Builder_32x32] : group, 0, 0);
        if (name.indexOf("Foreground") === 0) { layer.setDepth(2); }
      });
      var coll = map.createLayer("Collisions", ts.blocks, 0, 0);
      coll.setVisible(false).setDepth(-1);
      var cam = s.cameras.main;
      cam.setBounds(0, 0, map.widthInPixels, map.heightInPixels);
      cam.setZoom(0.7);
      ctrl.map = map;
      ctrl.ring = s.add.graphics().setDepth(0.5);
      names.forEach(function (n, i) {
        var k = n.replace(" ", "_");
        ["left", "right", "down", "up"].forEach(function (d) {
          s.anims.create({ key: k + "-" + d + "-walk", frameRate: 4, repeat: -1,
            frames: s.anims.generateFrameNames(k, { prefix: d + "-walk.", start: 0, end: 3, zeroPad: 3 }) });
        });
        var sp = s.add.sprite(2400 + i * 40, 600, k, "down").setDepth(1);   /* the atlas frames carry a centre pivot: the origin is the centre */
        sp.displayWidth = 40;
        sp.scaleY = sp.scaleX;
        sp.setInteractive({ useHandCursor: true });
        sp.on("pointerdown", function () { ctrl.clickedSprite = true; cb.onSelect(n); });
        ctrl.sprites[n] = sp;
        ctrl.bubbles[n] = s.add.image(0, 0, "speech_bubble").setDepth(3);
        ctrl.bubbles[n].displayWidth = 90;
        ctrl.bubbles[n].displayHeight = 40;
        ctrl.emoji[n] = s.add.text(0, 0, "", { font: "20px monospace", fill: "#000000" }).setDepth(3);
        ctrl.labels[n] = s.add.text(0, 0, initials(n), { font: "bold 11px monospace", fill: "#f0cf72", backgroundColor: "#090806" }).setDepth(3);
      });
      s.input.on("pointerup", function () { ctrl.clickedSprite = false; });
      s.input.on("pointermove", function (p) {
        if (p.isDown && !ctrl.clickedSprite) {
          cam.stopFollow();
          cam.scrollX -= (p.x - p.prevPosition.x) / cam.zoom;
          cam.scrollY -= (p.y - p.prevPosition.y) / cam.zoom;
        }
      });
      s.input.on("wheel", function (p, o, dx, dy) { cam.setZoom(Phaser.Math.Clamp(cam.zoom - dy * 0.001, 0.3, 1.6)); });
      var first = names[0] && ctrl.sprites[names[0]];
      if (first) { cam.centerOn(first.x, first.y); }
      ctrl.ready = true;
      if (ctrl.pending) { ctrl.setTargets(ctrl.pending, true); }
    }
    function update(time, delta) {
      if (!ctrl.ready) { return; }
      names.forEach(function (n) {
        var sp = ctrl.sprites[n], t = ctrl.targets[n], k = n.replace(" ", "_");
        if (!t) { return; }
        var dx = t.x - sp.x, dy = t.y - sp.y, dist = Math.sqrt(dx * dx + dy * dy);
        if (ctrl.snap || dist > 220) { sp.x = t.x; sp.y = t.y; dist = 0; } else if (dist > 0.5) { var f = Math.min(1, delta * 0.012); sp.x += dx * f; sp.y += dy * f; }
        if (dist > 1.5) {
          var d = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
          ctrl.dir[n] = d;
          sp.anims.play(k + "-" + d + "-walk", true);
        } else {
          sp.anims.stop();
          sp.setTexture(k, ctrl.dir[n] || "down");
        }
        ctrl.bubbles[n].x = sp.x + 55;
        ctrl.bubbles[n].y = sp.y - 52;
        ctrl.emoji[n].x = sp.x + 28;
        ctrl.emoji[n].y = sp.y - 68;
        ctrl.labels[n].x = sp.x - 10;
        ctrl.labels[n].y = sp.y + 12;
      });
      ctrl.ring.clear();
      if (ctrl.selected && ctrl.sprites[ctrl.selected]) {
        var s2 = ctrl.sprites[ctrl.selected];
        ctrl.ring.lineStyle(3, 0xf0cf72, 1).strokeEllipse(s2.x, s2.y + 18, 46, 16);
      }
    }
    ctrl.setTargets = function (frame, snap) {
      ctrl.snap = !!snap;
      if (!ctrl.ready) { ctrl.pending = frame; return; }
      names.forEach(function (n) {
        var p = frame[n];
        if (!p || p[0] == null) { return; }
        ctrl.targets[n] = { x: p[0] * TILE + TILE / 2, y: p[1] * TILE + TILE / 2 };
        ctrl.emoji[n].setText(p[2] || "");
      });
    };
    ctrl.select = function (name, follow) {
      ctrl.selected = name;
      if (follow !== false && ctrl.ready && ctrl.sprites[name]) { ctrl.scene.cameras.main.startFollow(ctrl.sprites[name], true, 0.12, 0.12); }
    };
    ctrl.screenPos = function (name) {
      var cam = ctrl.scene.cameras.main, sp = ctrl.sprites[name];
      var r = host.querySelector("canvas").getBoundingClientRect();
      return { x: r.left + (sp.x - cam.worldView.x) * cam.zoom, y: r.top + (sp.y - cam.worldView.y) * cam.zoom };
    };
    ctrl.destroy = function () { if (ctrl.game) { ctrl.game.destroy(true); ctrl.game = null; } };
    ctrl.game = new Phaser.Game({ type: Phaser.AUTO, parent: host, width: host.clientWidth || 640, height: host.clientHeight || 420,
      backgroundColor: "#090806", pixelArt: true, scene: { preload: preload, create: create, update: update } });
    /* Phaser caches the canvas position at creation; the page layout changes afterwards (labels, tabs), so refresh it before every pointer event */
    var refresh = function () { if (ctrl.game && ctrl.game.scale) { ctrl.game.scale.updateBounds(); } };
    ["pointermove", "pointerdown", "mousemove", "mousedown", "wheel"].forEach(function (ev) { host.addEventListener(ev, refresh, true); });
    return ctrl;
  }

  function TownPane(p) {
    var hostRef = useRef(null), ctrlRef = useRef(null), framesRef = useRef({}), pendingRef = useRef({});
    var _a = useState(null), meta = _a[0], setMeta = _a[1];
    var _b = useState(null), agent = _b[0], setAgent = _b[1];
    var _c = useState(null), state = _c[0], setState = _c[1];
    var _d = useState(null), thoughts = _d[0], setThoughts = _d[1];
    var _e = useState(null), sel = _e[0], setSel = _e[1];
    var _f = useState(true), hideIdle = _f[0], setHideIdle = _f[1];
    var _g = useState(false), diag = _g[0], setDiag = _g[1];
    var _h = useState(null), frameNow = _h[0], setFrameNow = _h[1];
    var _i = useState(null), error = _i[0], setError = _i[1];
    var _j = useState(0), loadTick = _j[0], setLoadTick = _j[1];
    var seq = useRef(0);
    var run = p.run;

    useEffect(function () {   /* meta and label for this pane's run; live (folder) runs are re-read while they grow */
      if (!run) { return; }
      var alive = true, timer = null;
      function load() {
        DM.api("/runs/" + encodeURIComponent(run) + "/movement/meta").then(function (m) {
          if (!alive) { return; }
          setMeta(m); p.onMeta(p.id, m);
          if (m.available && m.source === "folder") { timer = setTimeout(load, 15000); }
        }).catch(function (e) { if (alive) { setError(String(e)); } });
      }
      framesRef.current = {}; pendingRef.current = {};
      setMeta(null); setAgent(null); setState(null); setThoughts(null); setSel(null); setFrameNow(null); setError(null);
      load();
      DM.api("/runs/" + encodeURIComponent(run) + "/label").then(function (l) { if (alive) { p.onLabel(p.id, l); } }).catch(function () {});
      return function () { alive = false; if (timer) { clearTimeout(timer); } };
    }, [run]);

    useEffect(function () {   /* the Phaser scene for this run's personas */
      if (!meta || !meta.available || !hostRef.current) { return; }
      var ctrl = createTown(hostRef.current, meta.persona_names, { onSelect: function (n) { setAgent(n); setSel(null); } });
      ctrlRef.current = ctrl;
      window.TownDebug.panes[p.id] = ctrl;
      return function () { ctrl.destroy(); ctrlRef.current = null; delete window.TownDebug.panes[p.id]; };
    }, [meta && meta.available, run, meta && meta.persona_names && meta.persona_names.join()]);

    var stepNow = null;
    if (meta && meta.available) {
      var startMin = DM.toMin(meta.start_time);
      stepNow = Math.round(((p.t - startMin) * 60) / meta.sec_per_step);
    }
    var inRange = meta && meta.available && meta.first_step != null && stepNow >= meta.first_step && stepNow <= meta.last_step;

    useEffect(function () {   /* frames: load the chunk around the step, prefetch the next one, then point the avatars at the frame */
      if (!inRange || !ctrlRef.current) { return; }
      var cs = Math.floor(stepNow / CHUNK) * CHUNK;
      function ensure(c) {
        var key = String(c), now = Date.now(), pend = pendingRef.current[key];
        /* a complete chunk is fetched once; a partial chunk of a growing (folder) run is re-read at most every 10 seconds */
        if (pend && (!pend.partial || now - pend.at < 10000)) { return; }
        pendingRef.current[key] = { at: now, partial: false, busy: true };
        DM.api("/runs/" + encodeURIComponent(run) + "/movement/frames?from_step=" + c + "&to_step=" + (c + CHUNK - 1)).then(function (r) {
          var before = Object.keys(framesRef.current).length;
          r.frames.forEach(function (f) { framesRef.current[f.s] = f.p; });
          pendingRef.current[key] = { at: Date.now(), partial: r.frames.length < CHUNK && meta.source === "folder", busy: false };
          if (Object.keys(framesRef.current).length !== before) { setLoadTick(function (x) { return x + 1; }); }
        }).catch(function (e) { delete pendingRef.current[key]; setError(String(e)); });
      }
      ensure(cs);
      if (stepNow - cs > CHUNK - 120) { ensure(cs + CHUNK); }
      var fr = framesRef.current[stepNow];
      if (!fr) {   /* the nearest earlier loaded frame, never an invented position */
        for (var s = stepNow; s > stepNow - 400 && !fr; s -= 1) { fr = framesRef.current[s]; }
      }
      if (fr) {
        var obj = {};
        Object.keys(fr).forEach(function (n) { obj[n] = fr[n]; });
        ctrlRef.current.setTargets(obj, !p.playing);
        setFrameNow(fr);
      }
    }, [stepNow, inRange, loadTick, run, p.playing]);

    useEffect(function () { if (ctrlRef.current && agent) { ctrlRef.current.select(agent, true); } }, [agent, meta && meta.available]);

    useEffect(function () {   /* the memory panel of the clicked agent at the current replay time */
      if (!run || !agent || !inRange) { return; }
      var my = ++seq.current;
      var t = DM.fromMin(p.t);
      var timer = setTimeout(function () {
        var note = [];   /* the two requests are independent: a run without a memory database (the baseline arm writes none) still shows its thoughts */
        Promise.all([
          DM.api("/runs/" + encodeURIComponent(run) + "/agents/" + encodeURIComponent(agent) + "/state?t=" + encodeURIComponent(t) + (diag ? "&diagnostics=true" : ""))
            .catch(function (e) { note.push("memory database panel unavailable for this run (" + String(e).replace(/^Error: /, "") + "; the baseline arm writes no memory database)"); return null; }),
          DM.api("/runs/" + encodeURIComponent(run) + "/agents/" + encodeURIComponent(agent) + "/thoughts?t=" + encodeURIComponent(t))
            .catch(function (e) { note.push("thoughts unavailable (" + String(e) + ")"); return null; })
        ]).then(function (r) { if (my === seq.current) { setState(r[0]); setThoughts(r[1]); setError(note.length ? note.join("; ") : null); } })
          .catch(function (e) { if (my === seq.current) { setError(String(e)); } });
      }, p.playing ? 700 : 150);
      return function () { clearTimeout(timer); };
    }, [run, agent, Math.round(p.t / (p.playing ? 5 : 0.01)), diag, inRange]);

    var sets = DM.highlightSets(state, sel);
    function select(x) { setSel(sel && sel.type === x.type && sel.id === x.id ? null : x); }
    var pf = frameNow && agent ? frameNow[agent] : null;
    var action = pf && pf[3] ? DM.cleanText(String(pf[3]).split("@")[0]) : null, address = pf && pf[3] && String(pf[3]).indexOf("@") >= 0 ? String(pf[3]).split("@")[1] : null;
    var chat = pf && pf[4] ? pf[4] : null;

    return h("div", { className: "pane", id: "pane-" + p.id },
      h("div", { className: "panehead" },
        h("span", { className: "side" }, p.id === "left" ? "left pane" : "right pane"),
        h("select", { value: run || "", onChange: function (e) { p.onRun(p.id, e.target.value); } },
          p.runs.map(function (r) { return h("option", { key: r.run, value: r.run }, r.run); })),
        meta && meta.available ? h("span", { className: "kv" }, "recorded " + meta.t_min.slice(5, 16) + " to " + meta.t_max.slice(5, 16) + ", " + meta.frames + " frames, from " + meta.source) : null),
      meta && !meta.available ? h("div", { className: "nomove" }, "No movement is recorded for this run (" + meta.reason + "). The memory panels of the other tab still work.") : null,
      meta && meta.available && !inRange ? h("div", { className: "nomove" }, "No frame is recorded at this simulated time: this run covers " + meta.t_min + " to " + meta.t_max + ". The avatars stay where they were last recorded.") : null,
      h("div", { className: "townhost", ref: hostRef, style: { display: meta && meta.available ? "block" : "none" } }),
      error ? h("div", { className: "err" }, error) : null,
      agent && inRange ? h("div", { className: "agentcard" },
        h("div", { className: "who" }, agent, pf && pf[2] ? h("span", { className: "emoji" }, pf[2]) : null),
        h("div", { className: "line" }, h("b", null, "current action "), action || "none recorded at this step"),
        address ? h("div", { className: "line" }, h("b", null, "where "), address.trim()) : null,
        h("div", { className: "line" }, h("b", null, "dialogue "), chat ? chat.map(function (c, i) { return h("div", { key: i, className: "say" }, c[0] + ": " + c[1]); }) : "none at this moment"),
        h("div", { className: "line" }, h("b", null, "thoughts "), thoughts && thoughts.available ?
          (thoughts.thoughts.length ? thoughts.thoughts.map(function (x, i) { return h("div", { key: i, className: "say" }, x.created.slice(5, 16) + "  " + x.description); }) : "none recorded up to this time") :
          (thoughts ? thoughts.reason : "loading"),
          thoughts && thoughts.available ? h("div", { className: "meta" }, thoughts.up_to_t + " of " + thoughts.total_in_record + " thought nodes in the saved memory; " + thoughts.source) : null)) :
        (meta && meta.available ? h("div", { className: "hint" }, "Click an avatar to open its memory panel at this time. Drag the map to pan, scroll to zoom.") : null),
      agent && inRange && state ? h("div", { className: "townpanel" },
        h("div", { className: "cols town-cols" },
          h(DM.Priors, { state: state }),
          h(DM.Episodic, { state: state, hl: sets.hl, hideIdle: hideIdle, onHideIdle: setHideIdle, uid: p.id }),
          h(DM.Semantic, { state: state, sel: sel, hlSummary: sets.hlSummary, onSelect: select }),
          h(DM.Identity, { state: state, sel: sel, onSelect: select, diag: diag, onDiag: setDiag, uid: p.id }))) : null);
  }

  window.Town = { TownPane: TownPane };
})();
