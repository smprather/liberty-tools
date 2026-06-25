// Tree layout. x = column by depth (output on the right, leaves on the left);
// y = leaf row order, each gate centred on its inputs. Because it's a tree
// (leaves duplicated per use), wires never cross — no routing needed.
//
// opt.minWidthRatio caps gate aspect: each gate's width >= ratio * its height
// (so tall many-input gates don't render as thin slivers).

export function layout(root, opt = {}) {
  const dxMin = opt.dx ?? 0;
  const dy = opt.dy ?? 42;
  const gateW = opt.gateW ?? 46;
  const bubbleR = opt.bubbleR ?? 4;
  const pad = 9;
  const inputStub = opt.inputStub ?? 32;
  const termGapRows = opt.termGapRows ?? 0.35;
  const ratio = opt.minWidthRatio ?? 0;

  let row = 0;
  const nodes = [];
  function place(ref, depth) {
    const nd = ref.node;
    nd.depth = depth;
    if (nd.kind === "gate") {
      nd.inputs.forEach((c, i) => {
        place(c, depth + 1);
        const next = nd.inputs[i + 1];
        if (next && c.node.kind === "gate" && next.node.kind === "gate") row += termGapRows;
      });
      const ys = nd.inputs.map((c) => c.node.row);
      nd.row = (Math.min(...ys) + Math.max(...ys)) / 2;
    } else {
      nd.row = row++;
    }
    nodes.push(ref);
  }
  place(root, 0);

  let maxDepth = 0;
  nodes.forEach((r) => {
    if (r.node.kind === "gate") maxDepth = Math.max(maxDepth, r.node.depth);
  });
  nodes.forEach((r) => (r.node.y = 16 + r.node.row * dy));

  // Per-gate geometry: body spans its input rows. Keep the outer input pins at
  // least half an input-spacing away from the top/bottom edge, so inversion
  // bubbles remain readable.
  let maxW = gateW;
  let maxChildW = gateW;
  nodes.forEach((r) => {
    const nd = r.node;
    if (nd.kind !== "gate") return;
    const inputYs = nd.inputs.map((c) => c.node.y).sort((a, b) => a - b);
    const ys = inputYs.concat(nd.y);
    let minGap = 0;
    for (let i = 1; i < inputYs.length; i++) {
      const gap = inputYs[i] - inputYs[i - 1];
      if (gap > 0) minGap = minGap ? Math.min(minGap, gap) : gap;
    }
    const edgePad = Math.max(pad, minGap ? minGap / 2 : pad);
    nd.bubR = bubbleR;
    nd.gtop = Math.min(...ys) - edgePad;
    nd.gh = Math.max(...ys) + edgePad - nd.gtop;
    nd.gw = Math.max(gateW, nd.gh * ratio, nd.type === "and" ? nd.gh : 0);
    if (nd.gw > maxW) maxW = nd.gw;
    if (nd.depth > 0 && nd.gw > maxChildW) maxChildW = nd.gw;
  });

  // Vertical extent from gate bodies + pins (gates can overhang their rows).
  let yTop = 16, yBot = 16;
  nodes.forEach((r) => {
    const nd = r.node;
    const t = nd.kind === "gate" ? nd.gtop : nd.y;
    const b = nd.kind === "gate" ? nd.gtop + nd.gh : nd.y;
    yTop = Math.min(yTop, t);
    yBot = Math.max(yBot, b);
  });
  const y0 = yTop - pad;
  const H = yBot + pad - y0;

  // Label font (~12px on screen). opt.fitHeight=[min,max] enlarges the user-unit
  // font when the SVG is down-scaled to a capped pixel height (clipped to the
  // row gap). Left padding is sized for the longest input label at that font so
  // names aren't clipped at the left edge.
  let fontUser = 12;
  if (opt.fitHeight) {
    const hPx = Math.min(opt.fitHeight[1], Math.max(opt.fitHeight[0], H));
    const scale = hPx / H;
    fontUser = Math.max(3, Math.min(12, dy * scale - 2) / scale);
  }
  let maxName = 0;
  nodes.forEach((r) => { if (r.node.kind === "in") maxName = Math.max(maxName, String(r.node.name).length); });
  const padX = Math.max(30, maxName * fontUser * 0.62 + 12);

  const dx = Math.max(dxMin, maxChildW + 24);
  nodes.forEach((r) => {
    const nd = r.node;
    nd.x = nd.kind === "gate" ? padX + inputStub + (maxDepth - nd.depth) * dx : padX;
  });
  nodes.forEach((r) => {
    const nd = r.node;
    if (nd.kind !== "gate") return;
    nd.inputs.forEach((c) => {
      if (c.node.kind !== "gate") c.node.x = nd.x - inputStub;
    });
  });

  const W = padX + inputStub + maxDepth * dx + maxW + 90;
  return { root, nodes, W, H, y0, gateW, fontUser, dots: opt.dots ?? true };
}
