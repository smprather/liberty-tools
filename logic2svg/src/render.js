// Render a laid-out gate tree to an SVG string. IEEE distinctive-shape gates;
// inverted inputs/outputs drawn as bubbles. Wires are straight horizontals
// (the gate body spans its inputs' rows, so input pins sit at the child rows).

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function render(L) {
  const { nodes, W, H } = L;
  const out = [];
  const wire = (x1, y1, x2, y2) => `<path class="wire" d="M${x1},${y1} L${x2},${y2}"/>`;
  const pin = (x, y) => (L.dots ? `<circle class="pin" cx="${x}" cy="${y}" r="2.2"/>` : "");
  const childOutX = (nd) => (nd.kind === "gate" ? nd.x + nd.gw : nd.x);

  // Wires first (drawn under gate bodies).
  for (const ref of nodes) {
    const nd = ref.node;
    if (nd.kind !== "gate") continue;
    for (const c of nd.inputs) {
      const cy = c.node.y;
      let startx = childOutX(c.node);
      let endx = nd.x;
      if (c.inverted && c.node.kind === "gate") {
        const br = c.node.bubR || 4;
        out.push(`<circle class="bub" cx="${startx + br}" cy="${cy}" r="${br}"/>`);
        startx += br * 2;
      } else if (c.inverted) {
        const br = nd.bubR || 4;
        out.push(`<circle class="bub" cx="${nd.x - br}" cy="${cy}" r="${br}"/>`);
        endx = nd.x - br * 2;
      }
      out.push(wire(startx, cy, endx, cy));
    }
  }

  // Gates and leaves.
  for (const ref of nodes) {
    const nd = ref.node;
    if (nd.kind === "in") {
      out.push(pin(nd.x, nd.y));
      out.push(`<text class="lbl" x="${nd.x - 7}" y="${nd.y + 4}" text-anchor="end">${esc(nd.name)}</text>`);
    } else if (nd.kind === "const") {
      out.push(pin(nd.x, nd.y));
      out.push(`<text class="lbl" x="${nd.x - 7}" y="${nd.y + 4}" text-anchor="end">${nd.val}</text>`);
    } else {
      out.push(gateGlyph(nd.type, nd.x, nd.gtop, nd.gw, nd.gh));
      // Leaf inversion has no source gate, so it stays as an input bubble.
      for (const c of nd.inputs) out.push(pin(c.inverted && c.node.kind !== "gate" ? nd.x - (nd.bubR || 4) * 2 : nd.x, c.node.y));
      if (nd !== L.root.node) {
        const outx = ref.inverted ? nd.x + nd.gw + (nd.bubR || 4) * 2 : nd.x + nd.gw;
        out.push(pin(outx, nd.y));
      }
    }
  }

  // Output stub (+ bubble if the whole function is inverted).
  const r = L.root;
  const ry = r.node.y;
  const rx = childOutX(r.node);
  let ox = rx;
  const br = r.node.bubR || 4;
  if (r.inverted) {
    out.push(`<circle class="bub" cx="${rx + br}" cy="${ry}" r="${br}"/>`);
    ox = rx + br * 2;
  }
  out.push(pin(ox, ry)); // output dot on the bubble's outer edge when inverted
  out.push(wire(ox, ry, ox + 34, ry));
  out.push(`<text class="lbl out" x="${ox + 40}" y="${ry + 4}">Y</text>`);

  return `<svg viewBox="0 ${L.y0 || 0} ${W} ${H}" style="font-size:${L.fontUser}px" xmlns="http://www.w3.org/2000/svg" font-family="ui-monospace, monospace">${out.join("")}</svg>`;
}

function gateGlyph(type, L, T, w, h) {
  const r = h / 2;
  const mid = T + h / 2;
  const b = T + h;
  if (type === "buf") return `<path class="gate" d="M${L},${T} L${L + w},${mid} L${L},${b} Z"/>`;
  if (type === "and") {
    const m = L + w - r;
    return `<path class="gate" d="M${L},${T} L${m},${T} A${r},${r} 0 0 1 ${m},${b} L${L},${b} Z"/>`;
  }
  // or / xor — concave back, curved sides meeting at a point on the right.
  const back = L + w * 0.22;
  const straight = L + w / 3;
  const tip = L + w;
  const shoulder = L + w * 0.72;
  const orPath = `M${L},${T} L${straight},${T} Q${shoulder},${T} ${tip},${mid} Q${shoulder},${b} ${straight},${b} L${L},${b} Q${back},${mid} ${L},${T} Z`;
  if (type === "xor") {
    const arc = `<path class="gate2" d="M${L - 6},${T} Q${back - 6},${mid} ${L - 6},${b}"/>`;
    return arc + `<path class="gate" d="${orPath}"/>`;
  }
  return `<path class="gate" d="${orPath}"/>`;
}
