# logic2svg

Boolean logic function → gate-symbol **SVG**. Type a function, get a schematic of
AND/OR/XOR gates with inversion bubbles, live. Zero dependencies, zero build —
plain ES modules + SVG.

> First pass, living in the `liberty-tools` repo for now; will move to its own
> repo (and likely gain TS + Vite + GitHub Pages) later.

## Run

ES modules need to be served over HTTP (not `file://`):

```bash
cd logic2svg
python3 -m http.server 8000
# open http://localhost:8000
```

## Syntax

Liberty boolean grammar. Precedence low → high: OR < XOR < AND < NOT.

| | operators |
|---|---|
| NOT | `!x` `~x` `x'` |
| AND | `a & b` `a * b` `a b` (juxtaposition) |
| OR | `a + b` `a \| b` |
| XOR | `a ^ b` |
| group / const | `( )` `0` `1` |

## How it works (`src/`)

- `parse.js` — recursive-descent parser → AST (ports the liberty-tools Rust grammar).
- `lower.js` — AST → gate tree. NOT is pushed onto edges as a bubble (no inverter
  box); associative AND/OR/XOR flatten to n-ary gates. Pure tree: each leaf use
  is its own input pin, so there's no wire routing.
- `layout.js` — column by depth (output right, inputs left), row by leaf order,
  each gate centred on its inputs.
- `render.js` — IEEE distinctive-shape gates + bubbles → SVG string.
- `main.js` — live demo glue + SVG download.

`build(text)` (in `main.js`) returns the SVG string for embedding. The
liberty-tools viewer already does this: `viewer/static/symbol.js` is a
hand-synced port of `src/*` (`functionToSvg`) — keep the two in step when
either changes.

## Rendering Rules

Keep symbols conservative and easy to recognize:

- Inversion bubbles are fixed at radius `4` SVG units. Do not scale them from
  input row spacing or gate height.
- If an inverted signal comes from another gate, draw the bubble on that source
  gate's output. Draw an input bubble only when the inverted signal comes from a
  leaf/variable/constant with no source gate.
- Gate labels and viewer equation text are not part of the symbol geometry.
  Viewer equation labels must not affect total symbol width.
- AND/OR/XOR shapes should stay close to common distinctive logic-gate symbols;
  visual smoke screenshots are expected for renderer changes.

Run the focused regression test after renderer/layout edits:

```bash
uv run pytest -q tests/test_symbol_render.py
```

That test exercises both this ES-module implementation and the hand-synced
viewer copy.

## Not done yet / ideas

- Factoring for readability (minimized SOP is wide, 2-level AND-OR).
- Shared nets / fan-out instead of duplicated leaves.
- Pattern recognition (MUX, adders) → nicer symbols.
- Buffer/constant handling polish; tidier OR/XOR glyph curves.
