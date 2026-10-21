# Code review findings — writer, table lookup, accessors, compare helper

**Reviewed range:** `73af358..4630a3b` (feature commit `04fe843` + doc fix `4630a3b`)

**Verdict at review time:** Not ready to merge. One Critical data-corruption bug in
the writer's core path, plus Important defects where the new API silently reports
the wrong thing.

**Baseline at review time:** `cargo fmt --check` clean, `cargo check` clean,
`uv run pytest -q` → 116 passed / 2 skipped (the two skips need the gitignored
`generic80_ss_125c_1p116v_0p84v.lib`). The installed native extension was built
from the reviewed `src/lib.rs`.

**What was verified to work** (so it is not re-litigated):

- The writer is byte-exact: an untouched document re-emits identical bytes
  (synthetic fixture and the real 427 KB `dev.lib`); an edited real library
  changed only the two edited attributes; comments, CRLF and unknown groups
  survive; `.lib.gz` round-trips; a source file changed on disk is detected by
  hash and refused.
- `value_at` ≡ `lookup` ≡ `values[i*n2*n3 + j*n3 + k]` over every position of a
  rotated 2-D and a 3-D table; role lookup works on a real library.
- `compare()` aligns grids by axis role, not position: axis-swapped and 3-D
  cyclic-permuted libraries produce all points matched with delta 0.
- 51 malformed/mutated `.lib` inputs produced 0 panics — every failure was a
  `ValueError` with line/column.

This document is the authority for the fix plan
(`docs/superpowers/plans/2026-10-21-writer-compare-review-fixes.md`).

---

## Critical

### C1. Writer edit de-duplication corrupts the output file

`src/lib.rs:1037-1051` (`Document::liberty_to_string`).

`slots` stores indices into `keys`/`chosen`, but `keys.remove(slot)` and
`chosen.remove(slot)` shift the later elements without renumbering `slots`. The
next removal therefore uses a stale index, removes the wrong pending edit and
leaves a duplicate key behind. Both duplicates patch the same source span, so
`replace_range` is applied twice to that span and eats the following `;`/newline.

Reproduction (two attributes on one cell, each edited twice):

```python
c = doc.cell("u1")
c.set_attribute("area", "111111")
c.set_attribute("dont_touch", "true")
c.set_attribute("area", "222222")
c.set_attribute("dont_touch", "true")
doc.to_string()
```

Observed: `area` keeps its old value, `dont_touch` swallows the text of the
following attribute, and the following attribute disappears. The file may still
re-parse — silently wrong data — or fail to parse, depending on lengths.

Measured trigger matrix (all on one cell):

| edit sequence | result before fix |
| --- | --- |
| `A,B` | correct |
| `A,B,A` | correct |
| `A,B,A,C` | correct |
| `A,B,A,B` | **corrupt** |
| `A,B,A,C,B` | **corrupt** |
| `A,B,A,B,C` | **corrupt** |

---

## Important

### I1. `liberty_tools.compare` submodule is shadowed by the re-exported function

`liberty_tools/__init__.py:8` (`from .compare import … compare`) and
`liberty_tools/__init__.py:1253`.

`import liberty_tools.compare as cmp` yields the **function**;
`liberty_tools.compare.Comparison` raises `AttributeError`. `from
liberty_tools.compare import Comparison` still works, so the module is
half-importable.

### I2. `.pyi` redeclares the compare types instead of re-exporting them

`liberty_tools/__init__.pyi:435-508`.

Type checkers see two distinct nominal `Comparison` types and two `compare`
signatures; `lt.Comparison(entries=[])` (valid at runtime) is rejected by `ty`.

### I3. `compare()` ignores library units

`liberty_tools/compare.py:484-528`.

Values and axis coordinates are diffed raw. The same table in `ns/pf` versus
`ps/ff` gives four matched entries with delta 0.0 (physically 10³/10¹² apart),
and the inverse gives zero matched points — `summary()` then reports
`mismatched: 0`, which reads as "identical".

### I4. `ArcKey` omits `timing_sense`; colliding arcs overwrite each other

`liberty_tools/compare.py:29-45`, `:341-350` (`arcs[key] = arc`).

Two timing groups on the same related pin that differ only in `timing_sense`
collapse into one. A library compared **against itself** yields half the grid
points and reports no differences.

### I5. Incompatible known axis roles silently fall back to positional matching

`liberty_tools/compare.py:581-605` (`_axis_order` returns
`list(range(count_b))`).

The docstring and `docs/AI_API.md:470-472` promise the positional fallback only
when the roles are *unknown*. A=`[total_output_net_capacitance,
input_net_transition]`, B=`[related_pin_transition, constrained_pin_transition]`
→ four matched points, zero mismatches, b's axes labelled with a's roles.

### I6. `interpolate=True` fabricates `0.0` for points with no data

`liberty_tools/compare.py:824-839`.

Missing corners are skipped and the accumulator stays `0.0`, which is then
reported as a value (deltas 30.0/40.0 instead of "missing").

### I7. Pins whose name contains `[...]` cannot be edited

`src/lib.rs:4979-4982` (`SourceGroup.arg` only accepts a `Word` token; the
parser reassembles `A[0]` in `Parser::read_value`).

`bus("A").pin("A[0]").set_attribute("capacitance", 2.0)` fails at write time
with `ValueError: cell "u1" has no pin "A[0]" to edit`. Bus/bundle pins are
conventionally `name[index]`.

### I8. Duplicate cell names → every same-named cell is rewritten

`src/lib.rs:1067-1072`. `Document::cell()` takes the first match; the writer
patches **all** spans with that name. Editing one `cell (u1)` changed both.

### I9. Duplicate pin names → the wrong pin is patched

`src/lib.rs:5075-5083`. `AttrEdit` records only cell + pin name, so the writer
hits the first matching `pin` group in the cell. Editing `bus("B").pin("P")`
rewrote `bus(A)`'s `P` and left B untouched — the file contradicts the model.

### I10. `Pin.set_attribute` leaves the typed pin fields stale

`src/lib.rs:4836-4845`. `direction`, `function`, `three_state` and
`power_down_function` are first-class getters but are not mirrored (unlike
`Cell.area` at `:4797-4819`): after `pin.set_attribute("direction","output")`,
`pin.direction` is still `input` while the file says `output`.

### I11. `LibraryIndex` cells miss units/templates declared after the first cell

`src/lib.rs:3137-3143`, `:3043`. `parse_file` resolves them after the whole
body; `LibraryIndex` stops the header at the first cell, so `axis_roles()` is
`[None, None]` and `capacitance_farads` is `None`.

### I12. `Comparison.summary()` hides unmatched points and missing tables

`liberty_tools/compare.py:157-167`. `only_in_a_tables`, `only_in_b_tables` and
unmatched entries are absent, so gating on `summary()["mismatched"] == 0`
reports "identical" when a table exists on one side only.

### I13. Attribute values containing `"` or `\` are not escaped

`src/lib.rs:5036-5041`. `set_attribute("function", 'A "B" C')` writes
`function : "A "B" C";` and re-parses as `'A  B" C"'`.

---

## Minor

- Writer holds the GIL while reading/hashing the whole source
  (`src/lib.rs:1026-1035`) — blocks every thread on multi-GB libraries;
  `py.detach` is the project rule for heavy entry points.
- `value_at(-1, 0)` raises `OverflowError`, but `docs/AI_API.md:221` says
  `IndexError` (non-negative out-of-range does raise `IndexError`).
- `compare.to_polars()` on an empty result returns a 0-column frame.
- `grid={"load": …}` / `{"slew": …}` are rejected although `lookup(load=…)`
  accepts them (inverted synonym matching, `compare.py:608-621`).
- `compare.py:572-578`, `:701-751` re-derive the row-major flat index and axis
  count that Rust already owns (`src/lib.rs:4666`, `:1763`).
- `cell_leakage_power` docstring says "voltage × current" but the value uses
  `leakage_power_unit` when declared (`liberty_tools/__init__.py:351`).
- The stub declares `MinPulseWidth` mutable; the runtime class is
  `@dataclass(frozen=True)`.
- `docs/AI_API.md:208` labels `lookup()` "by grid position" (it matches axis
  *values*; positions silently return `None`).
- "Every group exposes its attributes" is false for bus/bundle
  (`docs/AI_API.md:350-351`, `README.md:233-235`).
- `docs/CLI.md:192` runs the viewer in the foreground, so the following steps of
  the "Typical Agent Workflow" never run.
- `compare` `timing_type` is compared raw, so an omitted `timing_type` does not
  match an explicit `combinational` (Liberty's default).
- Test gaps: no two-cell writer edit, no 3-D lookup, no template declared after
  the cell that uses it, `tolerance=` never exercised, no unit-difference or
  duplicate-`timing_sense` fixture.
