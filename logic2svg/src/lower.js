// Lower an AST to a gate tree. NOT is pushed onto edges as an `inverted` flag
// (rendered as a bubble), not a separate inverter box. Associative AND/OR/XOR
// chains are flattened into n-ary gates. Each leaf occurrence is its own input
// pin (the layout is a pure tree — no shared nets, no wire routing).
//
// Returns a "ref": { node, inverted } where node is one of:
//   {kind:'in', name, id}
//   {kind:'const', val, id}
//   {kind:'gate', type:'and'|'or'|'xor', inputs:[ref...], id}

export function lower(ast) {
  let id = 0;

  function go(n) {
    if (n.op === "not") {
      const r = go(n.a);
      return { node: r.node, inverted: !r.inverted };
    }
    if (n.op === "var") return { node: { kind: "in", name: n.name, id: id++ }, inverted: false };
    if (n.op === "const") return { node: { kind: "const", val: n.val, id: id++ }, inverted: false };

    // and / or / xor — flatten same-type children at the AST level first.
    const type = n.op;
    const inputs = [];
    const collect = (m) => {
      if (m.op === type) m.args.forEach(collect);
      else inputs.push(go(m));
    };
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

// De Morgan: an AND/OR gate with ALL inputs inverted becomes the other type
// with an inverted output (NOR/NAND). Bottom-up, so double bubbles on an edge
// collapse to none. Returns the (possibly re-rooted) ref.
export function demorgan(ref) {
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
