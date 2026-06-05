// Tree layout. x = column by depth (output on the right, leaves on the left);
// y = leaf row order, each gate centred on its inputs. Because it's a tree
// (leaves duplicated per use), wires never cross — no routing needed.
//
// opt.minWidthRatio caps gate aspect: each gate's width >= ratio * its height
// (so tall many-input gates don't render as thin slivers).

export function layout(root, opt = {}) {
  const dx0 = opt.dx ?? 92;
  const dy = opt.dy ?? 42;
  const gateW = opt.gateW ?? 46;
  const pad = 9;
  const ratio = opt.minWidthRatio ?? 0;

  let row = 0;
  const nodes = [];
  function place(ref, depth) {
    const nd = ref.node;
    nd.depth = depth;
    if (nd.kind === "gate") {
      nd.inputs.forEach((c) => place(c, depth + 1));
      const ys = nd.inputs.map((c) => c.node.row);
      nd.row = (Math.min(...ys) + Math.max(...ys)) / 2;
    } else {
      nd.row = row++;
    }
    nodes.push(ref);
  }
  place(root, 0);

  let maxDepth = 0;
  nodes.forEach((r) => (maxDepth = Math.max(maxDepth, r.node.depth)));
  nodes.forEach((r) => (r.node.y = 16 + r.node.row * dy));
  const H = 16 + (row - 1) * dy + 16; // top + content span (not row count) + bottom

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

  // Per-gate geometry: body spans its input rows; widen to keep w >= ratio*h.
  let maxW = gateW;
  nodes.forEach((r) => {
    const nd = r.node;
    if (nd.kind !== "gate") return;
    const ys = nd.inputs.map((c) => c.node.y).concat(nd.y);
    nd.gtop = Math.min(...ys) - pad;
    nd.gh = Math.max(...ys) + pad - nd.gtop;
    nd.gw = Math.max(gateW, nd.gh * ratio);
    if (nd.gw > maxW) maxW = nd.gw;
  });

  const dx = Math.max(dx0, maxW + 40);
  nodes.forEach((r) => (r.node.x = padX + (maxDepth - r.node.depth) * dx));

  const W = padX + maxDepth * dx + maxW + 90;
  return { root, nodes, W, H, gateW, fontUser, dots: opt.dots ?? true };
}
