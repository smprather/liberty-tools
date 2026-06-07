"use strict";
// Boolean function -> gate-symbol SVG, for the viewer's symbol panel. Self-
// contained port of ../../logic2svg/src/* (parse/lower/layout/render) exposing
// one global: functionToSvg(funcStr, outLabel). Keep in sync with logic2svg.
(function () {
  const OPS = "!~&*|+^'()";

  function parse(input) {
    const p = new P(input);
    const e = p.parseOr();
    p.ws();
    if (!p.eof()) throw new Error(`unexpected '${p.s[p.i]}' at ${p.i}`);
    return e;
  }
  class P {
    constructor(s) { this.s = s; this.i = 0; }
    ws() { while (this.i < this.s.length && /\s/.test(this.s[this.i])) this.i++; }
    peek() { return this.s[this.i]; }
    eof() { return this.i >= this.s.length; }
    eat(ch) { if (this.peek() === ch) { this.i++; return true; } return false; }
    parseOr() { let e = this.parseXor(); for (;;) { this.ws(); if (this.eat("|") || this.eat("+")) e = { op: "or", args: [e, this.parseXor()] }; else return e; } }
    parseXor() { let e = this.parseAnd(); for (;;) { this.ws(); if (this.eat("^")) e = { op: "xor", args: [e, this.parseAnd()] }; else return e; } }
    parseAnd() {
      let e = this.parseNot();
      for (;;) {
        this.ws();
        if (this.eat("&") || this.eat("*")) e = { op: "and", args: [e, this.parseNot()] };
        else if (this.atPrimary()) e = { op: "and", args: [e, this.parseNot()] };
        else return e;
      }
    }
    atPrimary() { let j = this.i; while (j < this.s.length && /\s/.test(this.s[j])) j++; const c = this.s[j]; return c !== undefined && !"|+^&*')".includes(c); }
    parseNot() { this.ws(); if (this.eat("!") || this.eat("~")) return { op: "not", a: this.parseNot() }; let e = this.parsePrimary(); for (;;) { this.ws(); if (this.eat("'")) e = { op: "not", a: e }; else return e; } }
    parsePrimary() {
      this.ws();
      if (this.eat("(")) { const e = this.parseOr(); this.ws(); if (!this.eat(")")) throw new Error(`expected ')' at ${this.i}`); return e; }
      const id = this.ident();
      if (id === "1" || id === "true" || id === "TRUE") return { op: "const", val: 1 };
      if (id === "0" || id === "false" || id === "FALSE") return { op: "const", val: 0 };
      return { op: "var", name: id };
    }
    ident() { this.ws(); const st = this.i; while (this.i < this.s.length) { const c = this.s[this.i]; if (/\s/.test(c) || OPS.includes(c)) break; this.i++; } if (this.i === st) throw new Error(`expected identifier at ${this.i}`); return this.s.slice(st, this.i); }
  }

  function lower(ast) {
    let id = 0;
    function go(n) {
      if (n.op === "not") { const r = go(n.a); return { node: r.node, inverted: !r.inverted }; }
      if (n.op === "var") return { node: { kind: "in", name: n.name, id: id++ }, inverted: false };
      if (n.op === "const") return { node: { kind: "const", val: n.val, id: id++ }, inverted: false };
      const type = n.op;
      const inputs = [];
      const collect = (m) => { if (m.op === type) m.args.forEach(collect); else inputs.push(go(m)); };
      n.args.forEach(collect);
      return { node: { kind: "gate", type, inputs, id: id++ }, inverted: false };
    }
    const r = go(ast);
    // Bare-variable output (y = a / y = !a) -> buffer / inverter triangle.
    if (r.node.kind === "in") {
      return { node: { kind: "gate", type: "buf", inputs: [{ node: r.node, inverted: false }], id: id++ }, inverted: r.inverted };
    }
    return r;
  }

  function layout(root, opt = {}) {
    const dx0 = opt.dx ?? 92, dy = opt.dy ?? 38, gateW = opt.gateW ?? 44, pad = 8;
    const ratio = opt.minWidthRatio ?? 0; // gate width >= ratio * height (aspect cap)
    let row = 0;
    const nodes = [];
    function place(ref, depth) {
      const nd = ref.node;
      nd.depth = depth;
      if (nd.kind === "gate") {
        nd.inputs.forEach((c) => place(c, depth + 1));
        const ys = nd.inputs.map((c) => c.node.row);
        nd.row = (Math.min(...ys) + Math.max(...ys)) / 2;
      } else nd.row = row++;
      nodes.push(ref);
    }
    place(root, 0);
    let maxDepth = 0;
    nodes.forEach((r) => (maxDepth = Math.max(maxDepth, r.node.depth)));
    nodes.forEach((r) => (r.node.y = 14 + r.node.row * dy));

    // Per-gate geometry: body spans its input rows; floor the height so a
    // single-row gate (buffer/inverter) doesn't render as a flat pancake, then
    // widen to keep w >= ratio*h. Recenter on the gate row when floored.
    const minGH = gateW * 0.82;
    let maxW = gateW;
    nodes.forEach((r) => {
      const nd = r.node;
      if (nd.kind !== "gate") return;
      const ys = nd.inputs.map((c) => c.node.y).concat(nd.y);
      nd.gtop = Math.min(...ys) - pad;
      nd.gh = Math.max(...ys) + pad - nd.gtop;
      if (nd.gh < minGH) { nd.gh = minGH; nd.gtop = nd.y - minGH / 2; }
      nd.gw = Math.max(gateW, nd.gh * ratio);
      if (nd.gw > maxW) maxW = nd.gw;
    });

    // Vertical extent from gate bodies + pins (gates can overhang their rows).
    let yTop = 14, yBot = 14;
    nodes.forEach((r) => {
      const nd = r.node;
      const t = nd.kind === "gate" ? nd.gtop : nd.y;
      const bb = nd.kind === "gate" ? nd.gtop + nd.gh : nd.y;
      yTop = Math.min(yTop, t);
      yBot = Math.max(yBot, bb);
    });
    const y0 = yTop - pad;
    const H = yBot + pad - y0;

    // Font: target ~12px on screen. If opt.fitHeight=[min,max] (the viewer caps
    // the SVG's pixel height), enlarge the user-unit font to compensate for the
    // down-scale, clipped to the row gap so labels don't collide. Standalone
    // (no fitHeight) renders near 1:1, so 12 user units is fine.
    let fontUser = 12;
    if (opt.fitHeight) {
      const hPx = Math.min(opt.fitHeight[1], Math.max(opt.fitHeight[0], H));
      const scale = hPx / H;
      fontUser = Math.max(3, Math.min(12, dy * scale - 2) / scale);
    }
    // Left padding sized for the longest input label at the chosen font, so a
    // (possibly enlarged) name isn't clipped at the SVG's left edge.
    let maxName = 0;
    nodes.forEach((r) => { if (r.node.kind === "in") maxName = Math.max(maxName, String(r.node.name).length); });
    const padX = Math.max(26, maxName * fontUser * 0.62 + 12);

    const dx = Math.max(dx0, maxW + 36); // keep columns clear of the widest gate
    nodes.forEach((r) => (r.node.x = padX + (maxDepth - r.node.depth) * dx));
    return { root, nodes, W: padX + maxDepth * dx + maxW + 80, H, y0, gateW, dy, fontUser, dots: opt.dots ?? true };
  }

  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  function render(L, outLabel) {
    const { nodes, W, H } = L;
    const o = [];
    const wire = (x1, y1, x2, y2) => `<path class="wire" d="M${x1},${y1} L${x2},${y2}"/>`;
    const pin = (x, y) => (L.dots ? `<circle class="pin" cx="${x}" cy="${y}" r="2.2"/>` : "");
    const childOutX = (nd) => (nd.kind === "gate" ? nd.x + nd.gw : nd.x);
    for (const ref of nodes) {
      const nd = ref.node;
      if (nd.kind !== "gate") continue;
      for (const c of nd.inputs) {
        const cy = c.node.y;
        let endx = nd.x;
        if (c.inverted) { o.push(`<circle class="bub" cx="${nd.x - 4}" cy="${cy}" r="4"/>`); endx = nd.x - 8; }
        o.push(wire(childOutX(c.node), cy, endx, cy));
      }
    }
    for (const ref of nodes) {
      const nd = ref.node;
      if (nd.kind === "in") {
        o.push(pin(nd.x, nd.y));
        o.push(`<text class="lbl" x="${nd.x - 7}" y="${nd.y + 4}" text-anchor="end">${esc(nd.name)}</text>`);
      } else if (nd.kind === "const") {
        o.push(pin(nd.x, nd.y));
        o.push(`<text class="lbl" x="${nd.x - 7}" y="${nd.y + 4}" text-anchor="end">${nd.val}</text>`);
      } else {
        o.push(gateGlyph(nd.type, nd.x, nd.gtop, nd.gw, nd.gh));
        // Inverted input: dot on the bubble's outer (wire) edge, not the gate.
        for (const c of nd.inputs) o.push(pin(c.inverted ? nd.x - 8 : nd.x, c.node.y));
        if (nd !== L.root.node) o.push(pin(nd.x + nd.gw, nd.y)); // root output dot drawn at the stub
      }
    }
    const r = L.root, ry = r.node.y, rx = childOutX(r.node);
    let ox = rx;
    if (r.inverted) { o.push(`<circle class="bub" cx="${rx + 4}" cy="${ry}" r="4"/>`); ox = rx + 8; }
    o.push(pin(ox, ry)); // output dot on the bubble's outer edge when inverted
    o.push(wire(ox, ry, ox + 30, ry));
    o.push(`<text class="lbl out" x="${ox + 36}" y="${ry + 4}">${esc(outLabel || "Y")}</text>`);
    // Trim trailing whitespace: the output label is the rightmost element, so the
    // viewBox width is its right edge (not the looser column-spacing W).
    const Wt = Math.ceil(ox + 36 + esc(outLabel || "Y").length * L.fontUser * 0.62 + 6);
    return `<svg viewBox="0 ${L.y0} ${Wt} ${H}" style="font-size:${L.fontUser}px" xmlns="http://www.w3.org/2000/svg" font-family="ui-monospace, monospace">${o.join("")}</svg>`;
  }

  function gateGlyph(type, L, T, w, h) {
    const r = h / 2, mid = T + h / 2, b = T + h;
    if (type === "buf") return `<path class="gate" d="M${L},${T} L${L + w},${mid} L${L},${b} Z"/>`;
    if (type === "and") { const m = L + w - r; return `<path class="gate" d="M${L},${T} L${m},${T} A${r},${r} 0 0 1 ${m},${b} L${L},${b} Z"/>`; }
    const back = L + w * 0.22, tip = L + w, shoulder = L + w * 0.55;
    const orPath = `M${L},${T} Q${back},${mid} ${L},${b} Q${shoulder},${b} ${tip},${mid} Q${shoulder},${T} ${L},${T} Z`;
    if (type === "xor") return `<path class="gate2" d="M${L - 6},${T} Q${back - 6},${mid} ${L - 6},${b}"/><path class="gate" d="${orPath}"/>`;
    return `<path class="gate" d="${orPath}"/>`;
  }

  // De Morgan: an AND/OR gate with ALL inputs inverted becomes the other type
  // with an inverted output (NOR/NAND). Applied bottom-up; toggling the output
  // inversion collapses any double bubble on that edge automatically.
  function demorgan(ref) {
    const nd = ref.node;
    if (nd.kind === "gate") {
      nd.inputs = nd.inputs.map(demorgan);
      if ((nd.type === "and" || nd.type === "or") && nd.inputs.length >= 2 && nd.inputs.every((c) => c.inverted)) {
        nd.type = nd.type === "and" ? "or" : "and";
        nd.inputs.forEach((c) => (c.inverted = false));
        return { node: nd, inverted: !ref.inverted };
      }
    }
    return ref;
  }

  // Sequential-element symbol (flip-flop / latch box). spec from data.py
  // _seq_spec: {kind, d, clock|enable:{name,inv}, q, qn, set, clr, scan:{si,se}}.
  function seqSymbol(spec, opt) {
    opt = opt || {};
    const o = [];
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    const ext = (x, y) => { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; };
    const wire = (a, b, c, d) => { ext(a, b); ext(c, d); return `<path class="wire" d="M${a},${b} L${c},${d}"/>`; };
    const bub = (x, y) => { ext(x - 4, y - 4); ext(x + 4, y + 4); return `<circle class="bub" cx="${x}" cy="${y}" r="4"/>`; };
    const txt = (x, y, t, anchor, cls) => {
      const w = String(t).length * 7.5;
      if (anchor === "end") ext(x - w, y); else if (anchor === "middle") { ext(x - w / 2, y); ext(x + w / 2, y); } else ext(x + w, y);
      ext(x, y - 7); ext(x, y + 7);
      return `<text class="lbl ${cls || ""}" x="${x}" y="${y + 4}"${anchor ? ` text-anchor="${anchor}"` : ""}>${esc(t)}</text>`;
    };

    const BW = 72, BH = 72, stub = 18, muxW = 26, muxGap = 18;
    const scan = spec.scan;
    const bx = 130 + (scan ? muxW + muxGap : 0);
    const by = 60;
    o.push(`<rect class="gate" x="${bx}" y="${by}" width="${BW}" height="${BH}" rx="3"/>`);
    ext(bx, by); ext(bx + BW, by + BH);
    const dY = by + BH * 0.3, ckY = by + BH * 0.74, qY = by + BH * 0.3, qnY = by + BH * 0.7;

    // D input, possibly via a 2:1 scan mux (D / SI selected by SE).
    if (scan) {
      const mx = bx - muxGap - muxW, half = 24, mTop = dY - half, mBot = dY + half;
      o.push(`<path class="gate" d="M${mx},${mTop} L${mx + muxW},${mTop + 9} L${mx + muxW},${mBot - 9} L${mx},${mBot} Z"/>`);
      ext(mx, mTop); ext(mx + muxW, mBot);
      const inA = mTop + 12, inB = mBot - 12, outY = (mTop + mBot) / 2, selX = mx + muxW * 0.5;
      o.push(wire(mx - stub, inA, mx, inA)); o.push(txt(mx - stub - 3, inA, spec.d || "D", "end"));
      o.push(wire(mx - stub, inB, mx, inB)); o.push(txt(mx - stub - 3, inB, scan.si, "end"));
      o.push(txt(mx + 4, inA, "0", "start", "hint")); o.push(txt(mx + 4, inB, "1", "start", "hint"));
      o.push(wire(selX, mTop - stub, selX, mTop + 9)); o.push(txt(selX, mTop - stub - 6, scan.se, "middle"));
      o.push(wire(mx + muxW, outY, bx, dY));
    } else {
      o.push(wire(bx - stub, dY, bx, dY)); o.push(txt(bx - stub - 3, dY, spec.d || "D", "end"));
    }

    // Clock (triangle notch) or latch enable.
    const clk = spec.clock || spec.enable;
    if (clk) {
      let endx = bx;
      if (clk.inv) { o.push(bub(bx - 4, ckY)); endx = bx - 8; }
      o.push(wire(bx - stub, ckY, endx, ckY));
      o.push(txt(bx - stub - 3, ckY, clk.name, "end"));
      if (spec.kind === "ff") o.push(`<path class="gate2" d="M${bx},${ckY - 6} L${bx + 10},${ckY} L${bx},${ckY + 6}"/>`);
    }

    // Outputs (labelled by pin name).
    if (spec.q) { o.push(wire(bx + BW, qY, bx + BW + stub, qY)); o.push(txt(bx + BW + stub + 3, qY, spec.q, "start", "out")); }
    if (spec.qn) { o.push(wire(bx + BW, qnY, bx + BW + stub, qnY)); o.push(txt(bx + BW + stub + 3, qnY, spec.qn, "start", "out")); }

    // Async set (top) / clear (bottom), bubble if active-low.
    const cx = bx + BW * 0.5;
    if (spec.set) { let ey = by; if (spec.set.inv) { o.push(bub(cx, by - 4)); ey = by - 8; } o.push(wire(cx, by - stub, cx, ey)); o.push(txt(cx, by - stub - 6, spec.set.name, "middle")); }
    if (spec.clr) { let ey = by + BH; if (spec.clr.inv) { o.push(bub(cx, by + BH + 4)); ey = by + BH + 8; } o.push(wire(cx, by + BH + stub, cx, ey)); o.push(txt(cx, by + BH + stub + 12, spec.clr.name, "middle")); }

    const pad = 8;
    const W = x1 - x0 + pad * 2, H = y1 - y0 + pad * 2;
    let fontUser = 12;
    if (opt.fitHeight) { const hPx = Math.min(opt.fitHeight[1], Math.max(opt.fitHeight[0], H)); const sc = hPx / H; fontUser = Math.max(3, Math.min(12, 16 * sc - 2) / sc); }
    return `<svg viewBox="${x0 - pad} ${y0 - pad} ${W} ${H}" style="font-size:${fontUser}px" xmlns="http://www.w3.org/2000/svg" font-family="ui-monospace, monospace">${o.join("")}</svg>`;
  }

  window.seqSymbolSvg = seqSymbol;

  window.functionToSvg = function (funcStr, outLabel, opt) {
    opt = opt || {};
    let root = lower(parse(funcStr));
    if (opt.demorgan) root = demorgan(root);
    return render(layout(root, opt), outLabel);
  };
})();
