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

## Not done yet / ideas

- Factoring for readability (minimized SOP is wide, 2-level AND-OR).
- Shared nets / fan-out instead of duplicated leaves.
- Pattern recognition (MUX, adders) → nicer symbols.
- Buffer/constant handling polish; tidier OR/XOR glyph curves.
