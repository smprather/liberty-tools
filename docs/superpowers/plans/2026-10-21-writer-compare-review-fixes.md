# Writer / Compare Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every Critical and Important defect found in the code review of the
Liberty writer, table lookup, uniform accessors and compare helper
(`73af358..4630a3b`), so the feature is safe to ship.

**Architecture:** The repo is a maturin/PyO3 hybrid: all parsing and data storage
lives in `src/lib.rs`; `liberty_tools/__init__.py` is a thin wrapper over the
`#[pyclass]` types in `_native`; `liberty_tools/compare.py` is pure Python over
the public API. The writer is *surgical*: it re-reads the original source bytes
and patches only the attributes that were edited through
`Cell::set_attribute`/`Pin::set_attribute`. Every fix keeps that design: no
task may re-serialize the parsed model, and no task may change the row-major
flat-value layout.

**Tech Stack:** Rust (pyo3 0.28, flate2), Python 3.14, pytest, polars, ruff, `ty`,
maturin.

**Spec:** `docs/superpowers/specs/2026-10-21-writer-compare-review.md` — the code
review that lists every finding (C1, I1-I13, minors) with reproductions. The
spec is the authority; this plan is its argument. A conflict between the two
resolves against the spec.

## Global Constraints

These bind every task. Copy them verbatim into any review dispatch.

- **Surgical writer:** `Document::to_string`/`write` re-read the original source
  and rewrite only the attributes changed through `Cell::set_attribute` /
  `Pin::set_attribute`; everything else stays byte for byte. Never re-emit a
  document from the parsed model (the model is lossy).
- **Detached edits are refused:** `set_attribute` on a cell/pin that is not
  attached to a document raises `RuntimeError`.
- **Flat table values are row-major with `index_1` slowest:**
  `values[i*len(index_2)+j]` (2-D), `values[i*len(index_2)*len(index_3)+j*len(index_3)+k]`
  (3-D). `table_position()` and `flat_index()` must stay consistent; the
  documented public read path is `TimingTable.lookup` / `TimingTable.value_at`.
- **Axis order is per-table, not fixed.** Which axis is the load and which is
  the transition comes from the table's `lu_table_template`;
  `resolve_axis_vars` fills `TimingTableData::axis_vars` *after* the whole
  library body is parsed (templates may be declared after the cells that use
  them).
- **GIL released for heavy work** (`py.detach(...)`), with `PyErr` conversion
  *outside* the closure.
- **The Python wrapper stays thin.** Every public Rust entry point that is
  exposed must have a matching `liberty_tools/__init__.pyi` declaration whose
  signature matches the runtime exactly, and a doc mention in
  `docs/AI_API.md` / `README.md` when it is new public API.
- **No new public API without a test, a `.pyi` entry and a doc mention.**
- **TDD:** write the failing test first, watch it fail for the expected reason,
  then implement. Record the RED and GREEN output in the task report.
- **Build/test commands** (run from the repo root `/home/mylesp/open-eda-file-tools`):
  - Rust change → `uv run maturin develop --release` (mandatory: Python tests
    import the built extension) → `cargo fmt --check` → `cargo check`
  - Python change → `uv run pytest -q` (full suite before committing)
  - Lint/type: `uv run ruff check .` and `uv run ty check`
  - Focused: `uv run pytest -q tests/test_writer.py` etc.
- **Commits:** one commit per task, message `fix(<area>): <what changed>`.
- **Do not touch the `viewer/` frontend, `logic2svg/`, `liberty_format/` or
  `docs/CLI.md`'s viewer sections** — out of scope for this plan.

## Review Focus

The five input classes most likely to bite a user, each pinned by a test in the
task named beside it:

1. **The same attribute edited twice on a cell that also has another edited
   attribute** → the last value wins, the other attribute keeps its value, and
   the written file still parses. (Task 1)
2. **A pin whose name contains `[...]`** (bus/bundle pins, `A[0]`) → the edit
   lands on that pin, not on a same-named pin elsewhere. (Task 2)
3. **Two cells with the same name, or two pins with the same name in different
   containers** → the edit touches only the entity the caller addressed, or
   fails loudly. (Task 2)
4. **Two libraries whose unit declarations differ** → the comparison reports the
   unit mismatch instead of a false delta or a false "identical". (Task 5)
5. **A timing arc identified only by `timing_sense`** → the arc is compared, not
   silently dropped. (Task 6)

---

## Context for every task

**Repo:** `/home/mylesp/open-eda-file-tools`, branch `fix/review-fixes-2026-10-21`
(created from `main` at `4630a3b`). Work in that checkout; do not create a
worktree.

**Key Rust symbols** (`src/lib.rs`, line numbers as of `4630a3b`):

| symbol | line | role |
| --- | --- | --- |
| `struct AttrEdit` | 60 | one pending attribute edit: cell, pin, key, value |
| `Document::liberty_to_string` | 1026 | applies pending edits to the source text |
| `Document::write` | 1086 | writes `to_string()` (gzip when the path ends `.gz`) |
| `TimingTable::value_at` | 1909 | grid-position read (`row`, `col`, `depth`) |
| `index_cells` | 2985 | byte ranges of the cells of a library file |
| `open_library_index` | 3160 | `LibraryIndex` entry point |
| `Document::read_source_text` | 4767 | re-reads + hash-checks the source file |
| `Cell::set_attribute_text` | 4807 | records a cell edit |
| `Pin::set_attribute_text` | 4852 | records a pin edit |
| `struct SourceGroup` | 4908 | a group header found in a cell's source text |
| `scan_source_groups` | 4927 | lexes a cell's text into groups + attributes |
| `render_attribute_value` | 5036 | quotes a value when it needs quoting |
| `patch_cell_text` | 5059 | applies one cell's edits to its source text |

**Key Python symbols:**

| symbol | location | role |
| --- | --- | --- |
| `from .compare import ArcKey, CompareEntry, Comparison, compare` | `liberty_tools/__init__.py:8` | package re-export (shadows the submodule) |
| `class ArcKey` | `liberty_tools/compare.py:33` | arc identity |
| `class Comparison` | `liberty_tools/compare.py:119` | result object |
| `def compare` | `liberty_tools/compare.py:197` | entry point |
| `_collect_arcs` | `liberty_tools/compare.py:327` | arcs → `dict[ArcKey, TimingArc]` |
| `_compare_table` | `liberty_tools/compare.py:473` | one table's grid diff |
| `_axis_order` | `liberty_tools/compare.py:581` | role-based axis mapping |
| `_same_axis` | `liberty_tools/compare.py:608` | role synonym matching |
| `_interpolate` | `liberty_tools/compare.py:806` | bilinear interpolation |
| `_requested_points` | `liberty_tools/compare.py:753` | `grid=` resolution |
| compare stubs | `liberty_tools/__init__.pyi:435-508` | redeclared types (to be re-exported) |

**Unit accessors already available on `LibertyDocument`:**
`voltage_unit` (`str | None`), `current_unit`, `time_unit`,
`capacitive_load_unit` (e.g. `"pf"`), `capacitive_load_multiplier` (`float`).

---

### Task 1: Writer keeps the last edit of an attribute (Critical, spec C1)

**Files:**
- Modify: `src/lib.rs` — `Document::liberty_to_string` (de-duplication block at
  `:1037-1051`)
- Test: `tests/test_writer.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: the pending-edit log keeps, for every `(cell, pin, key)`, the
  **last** edit only, and the surviving edits stay in the order they were made.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_writer.py` a parametrized test that writes a cell with three
attributes (`area : 1.0;`, `dont_touch : false;`, `keep_me : 7;`), applies a
sequence of `set_attribute` calls, writes the document, re-parses it, and
asserts the *re-parsed* values:

```python
@pytest.mark.parametrize(
    "sequence,expected",
    [
        (["area", "dont_touch"], {"area": "111111", "dont_touch": "true", "keep_me": "7"}),
        (["area", "dont_touch", "area"], {"area": "222222", "dont_touch": "true", "keep_me": "7"}),
        (["area", "dont_touch", "area", "keep_me"], {"area": "222222", "dont_touch": "true", "keep_me": "8"}),
        (["area", "dont_touch", "area", "dont_touch"], {"area": "222222", "dont_touch": "true", "keep_me": "7"}),
        (["area", "dont_touch", "area", "keep_me", "dont_touch"], {"area": "222222", "dont_touch": "true", "keep_me": "8"}),
        (["area", "dont_touch", "area", "dont_touch", "keep_me"], {"area": "222222", "dont_touch": "true", "keep_me": "8"}),
    ],
)
def test_the_last_edit_of_an_attribute_wins(sequence, expected, liberty):
    ...
```

The values used per key, in the order the sequence names them:
`area` → `"111111"` then `"222222"`, `dont_touch` → `"true"`, `keep_me` → `"8"`.
The test must also assert that the written text still contains `keep_me : 7;`
(or `keep_me : 8;`) as its own attribute — i.e. no attribute value swallowed the
text of the following attribute — and that the written file re-parses without
error.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest -q tests/test_writer.py -k last_edit`
Expected: FAIL for the sequences that re-edit a key — the re-parsed `area` is
`"1.0"` and `dont_touch` is `"true keep_me : 7"` (the following attribute was
swallowed). The first three sequences must already pass.

- [ ] **Step 3: Implement last-wins selection**

In `Document::liberty_to_string`, replace the `keys` / `chosen` / `slots`
bookkeeping with a last-wins selection over the edit log: iterate `edits` in
reverse, keep the first occurrence of each key `(cell, pin, key)`, then reverse
the kept list so the survivors stay in the order the edits were made. The rest
of the function (the per-cell span loop, `patch_cell_text`) is unchanged.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest -q tests/test_writer.py -k last_edit`
Expected: PASS (all six cases).

- [ ] **Step 5: Run the full suite and the Rust checks**

Run: `uv run maturin develop --release && cargo fmt --check && cargo check && uv run pytest -q`
Expected: all tests pass; no new warnings.

- [ ] **Step 6: Commit**

```bash
git add src/lib.rs tests/test_writer.py
git commit -m "fix(writer): keep the last edit of an attribute"
```

---

### Task 2: The writer patches the entity the caller addressed (spec I7, I8, I9)

**Files:**
- Modify: `src/lib.rs` — `struct AttrEdit` (`:60`), `struct SourceGroup`
  (`:4908`), `scan_source_groups` (`:4927`), `patch_cell_text` (`:5059`),
  `Document::liberty_to_string` (`:1067-1072` cell-span selection),
  `Pin::set_attribute_text` (`:4852`), and the `Pin` pyclass' constructor /
  `Bus::pin()` / `Bundle::pin()` accessors
- Test: `tests/test_writer.py`

**Interfaces:**
- Consumes: Task 1 (the de-duplicated edit log).
- Produces:
  - `AttrEdit` gains `container: Option<(ContainerKind, String)>` — the bus or
    bundle that owns the pin, `None` for a cell-level pin. `ContainerKind` is a
    new Rust enum with the variants `Bus` and `Bundle`.
  - `SourceGroup` gains `start: usize` — the byte offset of the group's header,
    so a group's span is `start..close` and nesting is derivable by
    containment.
  - The writer resolves a pin target as: the pin group inside the named
    container when the edit carries one, otherwise the unique pin group in the
    cell with that name; if the name matches more than one group and the edit
    carries no container, the write fails with a `ValueError` naming the
    ambiguity — it never patches an arbitrary match.

- [ ] **Step 1: Write the failing tests**

Three tests in `tests/test_writer.py`, each writing the document, re-parsing it
and asserting the *file text* (so a wrong target is visible):

1. **Bracketed pin name.** A cell with `bus (A) { bus_type : B; pin (A[0]) {
   direction : input; capacitance : 0.001; } }`. Edit
   `doc.cell("u1").bus("A").pin("A[0]").set_attribute("capacitance", "0.5")`.
   Assert the written text contains `pin (A[0])` with `capacitance : 0.5` and
   that the file re-parses with that value.
2. **Duplicate cell names.** A library with two `cell (u1)` groups (areas 1.0
   and 2.0). Edit `doc.cell("u1").set_attribute("area", "9.0")`. Assert the
   written text contains `area : 9.0` exactly once and `area : 2.0` exactly
   once, i.e. only the first cell was changed.
3. **Duplicate pin names in different containers.** A cell with
   `bus (A) { pin (P) { capacitance : 0.001; } }` and
   `bus (B) { pin (P) { capacitance : 0.002; } }`. Edit
   `doc.cell("u1").bus("B").pin("P").set_attribute("capacitance", "9.0")`.
   Assert the written text still has `0.001` under bus A and `9.0` under bus B.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_writer.py -k "bracket or duplicate"`
Expected: FAIL — (1) `ValueError: cell "u1" has no pin "A[0]" to edit`;
(2) both cells rewritten to `area : 9.0`; (3) bus A's pin rewritten to `9.0`
and bus B's left at `0.002`.

- [ ] **Step 3: Implement the target resolution**

- `SourceGroup` gains `start`; `scan_source_groups` records it, and the group
  argument is reconstructed exactly like `Parser::read_value` does: a `Word`
  followed by `[`, `Word`, `]` yields `name[index]`. Prefer reusing the
  parser's own helper over a second copy — if the parser's reconstruction is
  not reachable as a function, extract one and call it from both places.
- `AttrEdit` gains the owning container (bus/bundle name and kind). The `Pin`
  pyclass carries that container when the pin is obtained through
  `Bus::pin()` / `Bundle::pin()`; cell-level pins carry none.
- `patch_cell_text` resolves the target pin group with the container when the
  edit has one (the pin group contained in the container group's span), and
  otherwise requires the name to match exactly one pin group in the cell —
  more than one match is an error naming the cell, the pin and the candidates.
- `Document::liberty_to_string` patches only the cell span that
  `Document::cell(name)` resolves to (the first match), instead of every span
  with that name.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_writer.py -k "bracket or duplicate"`
Expected: PASS (all three).

- [ ] **Step 5: Run the full suite and the Rust checks**

Run: `uv run maturin develop --release && cargo fmt --check && cargo check && uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/lib.rs tests/test_writer.py
git commit -m "fix(writer): patch the cell and pin the caller addressed"
```

---

### Task 3: Attribute write contract — typed pin fields, escaping, negative index (spec I10, I13, minor)

**Files:**
- Modify: `src/lib.rs` — `Pin::set_attribute_text` (`:4852`),
  `render_attribute_value` (`:5036`), `render_complex_attribute_value`,
  `TimingTable::value_at` (`:1909`)
- Test: `tests/test_writer.py`, `tests/test_table_lookup.py`

**Interfaces:**
- Consumes: nothing new from earlier tasks.
- Produces:
  - `Pin.set_attribute` mirrors the typed fields `direction`, `function`,
    `three_state`, `power_down_function` (the way `Cell` mirrors `area`), so
    the getters and `function_expr()` reflect the edit immediately.
  - A written attribute value re-parses to the exact value that was set:
    `"` and `\` are escaped inside a quoted value, and a value is quoted when
    it contains whitespace, `"`, `\`, `;`, `#`, `,`, `(` or `)`.
  - `TimingTable.value_at` raises `IndexError` (not `OverflowError`) for a
    negative row, col or depth.

- [ ] **Step 1: Write the failing tests**

1. `tests/test_writer.py`: a pin with `direction : input;` and
   `function : "A";`. After `pin.set_attribute("direction", "output")` assert
   `pin.direction == "output"`; after `pin.set_attribute("function", "A & !B")`
   assert `pin.function == "A & !B"` and that `pin.function_expr()` evaluates
   the new expression (e.g. `pin.function_expr().eval({"A": True, "B": False})`
   is `True` and `…eval({"A": True, "B": True})` is `False`).
2. `tests/test_writer.py`: `pin.set_attribute("function", 'A "B" C')` → the
   written file re-parses to exactly `A "B" C`; a second case with the value
   `a;b` re-parses to exactly `a;b`.
3. `tests/test_table_lookup.py`: `table.value_at(-1, 0)` raises `IndexError`
   (today it raises `OverflowError`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_writer.py tests/test_table_lookup.py -k "direction or quote or negative"`
Expected: FAIL — the typed field still reports the old value, the quoted value
re-parses as `A  B" C"`, and the negative position raises `OverflowError`.

- [ ] **Step 3: Implement**

- `Pin::set_attribute_text` mirrors the four typed fields after
  `set_attribute_in` updates the attribute vector.
- `render_attribute_value` quotes when the value is empty or contains any of
  whitespace, `"`, `\`, `;`, `#`, `,`, `(`, `)`; inside the quotes, `\` becomes
  `\\` and `"` becomes `\"` (the lexer's `read_quoted` already unescapes both).
  `render_complex_attribute_value` quotes each part with the same rule.
- `TimingTable::value_at` takes signed positions and raises `IndexError` for a
  negative one (keep the same message style as the existing out-of-range
  error).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_writer.py tests/test_table_lookup.py`
Expected: PASS.

- [ ] **Step 5: Run the full suite and the Rust checks**

Run: `uv run maturin develop --release && cargo fmt --check && cargo check && uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/lib.rs tests/test_writer.py tests/test_table_lookup.py
git commit -m "fix(writer): keep pin attributes and quoted values consistent"
```

---

### Task 4: Library-level Rust behavior — GIL release and `LibraryIndex` resolution (spec I11, GIL minor)

**Files:**
- Modify: `src/lib.rs` — `Document::liberty_to_string` (`:1026`),
  `Document::write` (`:1086`), `open_library_index` (`:3160`),
  `index_cells` (`:2985`)
- Test: `tests/test_attributes.py` (or a new `tests/test_library_index.py`)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `to_string()`/`write()` release the GIL while reading, hashing and lexing
    the source; `PyErr` conversion stays outside the detached closure.
  - `LibraryIndex.open(path).cell(name)` resolves units and templates that the
    library declares *after* the first cell, exactly like `parse_file` does.

- [ ] **Step 1: Write the failing tests**

1. A library whose `capacitive_load_unit (1, pf);` and
   `lu_table_template (t) { variable_1 : input_net_transition; variable_2 :
   total_output_net_capacitance; }` are declared **after** the cell that uses
   them. Assert `lt.LibraryIndex.open(path).cell("u1").pin("a").capacitance_farads`
   equals the expected farads and that the cell's timing table reports
   `axis_roles() == ["input_net_transition", "total_output_net_capacitance"]`
   (today both are `None` / `[None, None]`).
2. A concurrency smoke test: one thread calls `doc.to_string()` in a loop while
   another thread parses another file in a loop; both must finish (no
   deadlock) and the produced text must equal the untouched source.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_attributes.py tests/test_library_index.py -k "index or concurrent"`
Expected: the `LibraryIndex` test FAILS (`None` / `[None, None]`); the
concurrency test passes (it guards the refactor).

- [ ] **Step 3: Implement**

- `LibraryIndex` builds its header from the preamble **and** the top-level
  non-cell items that follow the first cell, so units and templates declared
  later are visible. Reuse the same parsing the full parser uses for those
  items; do not re-implement unit parsing.
- `to_string()`/`write()` move the pure-Rust work (read the file, hash it, scan
  the edited cells) into a helper that takes no Python token, and call it
  through `py.detach(...)`; convert errors to `PyErr` outside the closure. The
  returned text must be identical to today's.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_attributes.py tests/test_library_index.py`
Expected: PASS.

- [ ] **Step 5: Run the full suite and the Rust checks**

Run: `uv run maturin develop --release && cargo fmt --check && cargo check && uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/lib.rs tests/test_attributes.py tests/test_library_index.py
git commit -m "fix(library): release the GIL and resolve late library items"
```

---

### Task 5: `compare()` reports unit mismatches instead of diffing raw numbers (spec I3)

**Files:**
- Modify: `liberty_tools/compare.py` — `compare` (`:197`), `_compare_table`
  (`:473`), `class Comparison` (`:119`)
- Modify: `liberty_tools/__init__.py` — re-export the new dataclass
- Modify: `liberty_tools/__init__.pyi` — re-export the new dataclass
- Test: `tests/test_compare.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `class UnitMismatch` (frozen dataclass) with fields
    `cell: str`, `pin: str`, `table: str`, `dimension: str`,
    `unit_a: str | None`, `unit_b: str | None`; exported from
    `liberty_tools.compare` and from the package.
  - `Comparison.unit_mismatches: list[UnitMismatch]`.
  - Unit dimensions: `time` (`time_unit`), `capacitive_load`
    (`capacitive_load_unit` + `capacitive_load_multiplier`), `voltage`
    (`voltage_unit`). The unit strings are compared verbatim after stripping
    whitespace; the multiplier is compared numerically.
  - A table is *affected* by a dimension when one of its axis roles names that
    dimension (a role containing `transition` or `time` → time; containing
    `capacitance` → capacitive load; containing `voltage` → voltage), or when
    the table's value carries it (table names `cell_rise`, `cell_fall`,
    `rise_transition`, `fall_transition`, `rise_constraint`, `fall_constraint`
    carry time).
  - When a table is affected by a dimension whose declaration differs between
    the two documents, that table is **not** compared numerically; one
    `UnitMismatch` per affected table and dimension is recorded instead.

- [ ] **Step 1: Write the failing test**

In `tests/test_compare.py`, add a pair of libraries: identical except that one
declares `time_unit : "1ns";` and the other `time_unit : "1ps";` (the table
values are the same numbers). Assert:

- `compare(a, b).unit_mismatches` is non-empty and its first entry has
  `dimension == "time"`, `unit_a == "1ns"`, `unit_b == "1ps"`;
- no entry of that comparison has a numeric delta (the table was not diffed);
- `summary()["unit_mismatches"]` counts them.

Add the same for a capacitive-load difference (`pf` vs `ff`, with the load axis
scaled accordingly) and assert the `capacitive_load` dimension is reported.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest -q tests/test_compare.py -k unit`
Expected: FAIL — `unit_mismatches` does not exist / is empty, and the
comparison reports four matched points with delta 0.0 (a false "identical").

- [ ] **Step 3: Implement**

Add the `UnitMismatch` dataclass, the `Comparison.unit_mismatches` field, the
dimension/role helpers and the skip logic in `compare()` / `_compare_table()`.
Do not change the numeric comparison for libraries that declare the same units.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest -q tests/test_compare.py`
Expected: PASS, and the existing comparison tests (role swap, missing points,
missing arcs) still pass unchanged.

- [ ] **Step 5: Run the full suite and the linters**

Run: `uv run pytest -q && uv run ruff check . && uv run ty check`
Expected: all pass; `ty` reports no new diagnostics.

- [ ] **Step 6: Commit**

```bash
git add liberty_tools/compare.py liberty_tools/__init__.py liberty_tools/__init__.pyi tests/test_compare.py
git commit -m "fix(compare): report unit mismatches instead of diffing raw numbers"
```

---

### Task 6: `compare()` identifies arcs completely (spec I4, timing_type minor)

**Files:**
- Modify: `liberty_tools/compare.py` — `class ArcKey` (`:33`),
  `_collect_arcs` (`:327`), `_arc_group` (`:408`), `class Comparison` (`:119`)
- Modify: `liberty_tools/__init__.py`, `liberty_tools/__init__.pyi`
- Test: `tests/test_compare.py`

**Interfaces:**
- Consumes: Task 5's `Comparison` field pattern.
- Produces:
  - `ArcKey` gains `timing_sense: str | None = None` (last field, defaulted,
    so existing positional construction keeps working) and includes it in
    `__str__` when set.
  - `ArcKey.timing_type` is normalized: an absent `timing_type` attribute
    becomes `"combinational"` (Liberty's default), so a library that omits it
    matches one that writes it explicitly.
  - `Comparison.duplicate_arcs: list[ArcKey]` — arcs whose identity still
    collides after normalization. A collision is **reported**, never resolved
    by overwriting: the colliding arc is recorded and its values are not
    compared.

- [ ] **Step 1: Write the failing tests**

In `tests/test_compare.py`:

1. A cell whose output pin has two `timing ()` groups on the same related pin
   that differ only in `timing_sense` (`positive_unate` / `negative_unate`).
   Compare that document **with itself**: assert the number of compared points
   doubles (both arcs are compared) and that `only_in_a` / `only_in_b` are
   empty.
2. Two libraries, one with `timing_type : combinational;` and one without it.
   Assert the arcs match: no entry in `only_in_a` / `only_in_b`, and the
   tables are compared.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_compare.py -k "sense or timing_type"`
Expected: FAIL — today the two `timing_sense` arcs collapse into one (half the
points), and the omitted-vs-explicit `timing_type` produces one arc in
`only_in_a` and one in `only_in_b`.

- [ ] **Step 3: Implement**

Extend `ArcKey`, build it with the arc's `timing_sense` and the normalized
`timing_type`, and make `_collect_arcs` detect a residual key collision
instead of overwriting the previous arc. `CompareEntry` carries the same
identity fields so an entry can be traced back to its arc.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest -q tests/test_compare.py`
Expected: PASS.

- [ ] **Step 5: Run the full suite and the linters**

Run: `uv run pytest -q && uv run ruff check . && uv run ty check`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add liberty_tools/compare.py liberty_tools/__init__.py liberty_tools/__init__.pyi tests/test_compare.py
git commit -m "fix(compare): identify arcs by timing sense and default timing type"
```

---

### Task 7: `compare()` never guesses when the axis roles disagree (spec I5, I12)

**Files:**
- Modify: `liberty_tools/compare.py` — `_axis_order` (`:581`),
  `_compare_table` (`:473`), `class Comparison` (`:119`), `summary` (`:157`)
- Modify: `liberty_tools/__init__.py`, `liberty_tools/__init__.pyi`
- Test: `tests/test_compare.py`

**Interfaces:**
- Consumes: Tasks 5 and 6.
- Produces:
  - `class AxisRoleMismatch` (frozen dataclass) with fields
    `cell: str`, `pin: str`, `table: str`,
    `roles_a: tuple[str | None, ...]`, `roles_b: tuple[str | None, ...]`.
  - `Comparison.axis_role_mismatches: list[AxisRoleMismatch]`.
  - `_axis_order` returns "no mapping" when a role that is known on **both**
    sides has no counterpart. The positional fallback applies only when the
    roles are unknown (either side).
  - A table with unmatched roles is not compared numerically; the mismatch is
    recorded.
  - `Comparison.summary()` gains the keys `unmatched`, `only_in_a_tables`,
    `only_in_b_tables`, `unit_mismatches`, `axis_role_mismatches`,
    `duplicate_arcs` and `has_differences`.
  - `Comparison.has_differences` (property) is `True` when any of the
    difference categories is non-empty: mismatched entries, unmatched entries,
    arcs or tables only on one side, shape mismatches, unit mismatches, axis
    role mismatches, duplicate arcs. (Task 8 extends both with malformed
    tables.)

- [ ] **Step 1: Write the failing tests**

In `tests/test_compare.py`:

1. Library A's template names `[total_output_net_capacitance,
   input_net_transition]`, library B's names `[related_pin_transition,
   constrained_pin_transition]`, with the same numeric axes. Assert
   `compare(a, b).axis_role_mismatches` has one entry naming the table, that no
   entry of the comparison has a numeric delta, and that
   `summary()["axis_role_mismatches"] == 1`.
2. A library with a table `cell_fall` that the other library lacks. Assert
   `summary()["only_in_a_tables"] == 1` and `summary()["has_differences"] is
   True` (today `summary()["mismatched"] == 0`, which reads as "identical").
3. Assert `has_differences is False` for two libraries that are equal.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_compare.py -k "role or has_differences or only_in"`
Expected: FAIL — the role mismatch is not reported (the tables are compared
positionally and reported as identical), and `summary()` has no such keys.

- [ ] **Step 3: Implement**

- `_axis_order` returns `None` (or an explicit "unmapped" marker) when a role
  known on both sides has no counterpart; `_compare_table` records an
  `AxisRoleMismatch` and skips the numeric comparison for that table.
- Add the `AxisRoleMismatch` dataclass, the `Comparison` fields, the extended
  `summary()` and the `has_differences` property.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest -q tests/test_compare.py`
Expected: PASS.

- [ ] **Step 5: Run the full suite and the linters**

Run: `uv run pytest -q && uv run ruff check . && uv run ty check`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add liberty_tools/compare.py liberty_tools/__init__.py liberty_tools/__init__.pyi tests/test_compare.py
git commit -m "fix(compare): report axis role mismatches and complete the summary"
```

---

### Task 8: `compare()` never invents values (spec I6, malformed-value minors)

**Files:**
- Modify: `liberty_tools/compare.py` — `_interpolate` (`:806`),
  `_compare_table` (`:473`), `_requested_points` (`:753`), `_same_axis`
  (`:608`), `Comparison.to_polars` (`:169`)
- Modify: `liberty_tools/__init__.py`, `liberty_tools/__init__.pyi`
- Test: `tests/test_compare.py`

**Interfaces:**
- Consumes: Tasks 5-7.
- Produces:
  - `class MalformedTable` (frozen dataclass) with fields `cell: str`,
    `pin: str`, `table: str`, `expected_values: int`, `actual_values: int`.
  - `Comparison.malformed_tables: list[MalformedTable]`.
  - A table whose `values` length differs from the product of its axis lengths
    is recorded as malformed and is not compared numerically.
  - `Comparison.summary()` gains the key `malformed_tables`, and
    `Comparison.has_differences` is `True` when a malformed table was found.
  - `_interpolate` returns `None` unless **every** corner of the interpolation
    box has a value; a non-finite value (NaN/inf) counts as missing, not data.
  - `Comparison.to_polars()` on an empty comparison returns a frame with the
    documented columns and zero rows.
  - `grid=` accepts the same shorthands `lookup()` accepts: `load`, `slew` and
    `transition` resolve for the roles they belong to.

- [ ] **Step 1: Write the failing tests**

In `tests/test_compare.py`:

1. A table with a 2×2 grid but only two values (`values ("10, 30")`).
   Compare it with a complete table: assert
   `compare(a, b).malformed_tables` has one entry with `expected_values == 4`
   and `actual_values == 2`, and that no entry of the comparison reports a
   numeric delta for that table.
2. The same pair compared with `interpolate=True`: assert the missing points
   have `value_b is None` (today they get `0.0` and a delta of 30.0/40.0).
3. A table whose values contain `nan`: assert the entry is not treated as
   matched data (today `matched` is `True` and the delta is `nan`).
4. `compare(a, b).to_polars()` on a comparison with no entries: assert the
   frame has the documented columns and `len(frame) == 0`.
5. `compare(a, b, interpolate=True, grid={"load": [1.0], "transition": [0.1]})`
   does not raise (today `load` is rejected with a `ValueError`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_compare.py -k "malformed or interpolate or nan or empty or grid"`
Expected: FAIL — no `malformed_tables`, the interpolated points get `0.0`, the
NaN entry is "matched", the empty frame has no columns, and `grid={"load": …}`
raises `ValueError`.

- [ ] **Step 3: Implement**

- Validate `len(values)` against the product of the axis lengths (axes the
  table actually has) before comparing a table; record `MalformedTable` and
  skip it.
- `_interpolate` tracks whether every corner contributed a finite value and
  returns `None` otherwise.
- `to_polars()` builds the frame from an explicit column list so an empty
  comparison still has the documented schema.
- `_requested_points` resolves a `grid=` key with the same synonym direction
  `lookup()` uses.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest -q tests/test_compare.py`
Expected: PASS.

- [ ] **Step 5: Run the full suite and the linters**

Run: `uv run pytest -q && uv run ruff check . && uv run ty check`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add liberty_tools/compare.py liberty_tools/__init__.py liberty_tools/__init__.pyi tests/test_compare.py
git commit -m "fix(compare): report malformed tables and never invent values"
```

---

### Task 9: `liberty_tools.compare` is a module again; the stubs re-export (spec I1, I2)

**Files:**
- Move: `liberty_tools/compare.py` → `liberty_tools/comparison.py`
- Modify: `liberty_tools/__init__.py` (`:8`, `:1253`), `liberty_tools/__init__.pyi`
  (`:435-508`)
- Modify: `tests/test_compare.py` (imports), `docs/AI_API.md`, `README.md`
  (module references only — prose fixes are Task 10)
- Test: `tests/test_compare.py`

**Interfaces:**
- Consumes: Tasks 5-8 (the compare API is final by now).
- Produces:
  - `liberty_tools.comparison` is the module; `liberty_tools.compare` is the
    function. `import liberty_tools.comparison as cmp` gives the module;
    `liberty_tools.comparison.Comparison` is the class;
    `liberty_tools.compare` is callable and is the same object as
    `liberty_tools.comparison.compare`.
  - `liberty_tools/__init__.pyi` re-exports the compare types with the PEP 484
    `as` form instead of redeclaring them:
    `from .comparison import ArcKey as ArcKey, CompareEntry as CompareEntry, Comparison as Comparison, compare as compare`
    (plus the dataclasses added in Tasks 5-8).

- [ ] **Step 1: Write the failing test**

In `tests/test_compare.py` (or a new `tests/test_package_api.py`):

```python
def test_the_compare_module_is_not_shadowed_by_the_function():
    import liberty_tools.comparison as comparison
    assert comparison.Comparison is lt.Comparison
    assert callable(lt.compare)
    assert lt.compare is comparison.compare
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest -q tests/test_compare.py -k shadow`
Expected: FAIL — `import liberty_tools.comparison` does not exist yet (or the
module attribute is the function).

- [ ] **Step 3: Implement**

- `git mv liberty_tools/compare.py liberty_tools/comparison.py`; update the
  import in `liberty_tools/__init__.py` and every reference in the tests and
  the docs.
- Replace the redeclared stub block in `liberty_tools/__init__.pyi` with the
  `as`-form re-export of every public name of the module.
- Verify with `uv run ty check` that `lt.Comparison` and
  `liberty_tools.comparison.Comparison` are the same type (a snippet that
  assigns one to the other must type-check).

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest -q tests/test_compare.py && uv run ty check`
Expected: PASS, and `ty` reports no new diagnostics.

- [ ] **Step 5: Run the full suite and the linters**

Run: `uv run pytest -q && uv run ruff check . && uv run ty check`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add -A liberty_tools tests docs README.md
git commit -m "refactor(api): keep the compare module importable"
```

---

### Task 10: Documentation and stub accuracy (spec minors)

**Files:**
- Modify: `docs/AI_API.md`, `README.md`, `docs/CLI.md`,
  `liberty_tools/__init__.py` (docstrings), `liberty_tools/__init__.pyi`
- Test: `tests/test_writer.py` only if a doc statement is turned into a test

**Interfaces:**
- Consumes: Tasks 1-9 (the final API).
- Produces:
  - `docs/AI_API.md:208` describes `lookup()` as matching axis **values**
    (`index_1`/`index_2`/`index_3` or a role), not grid positions.
  - `docs/AI_API.md:221` states that `value_at()` raises `IndexError` for a
    position outside the table — now true for negative positions as well
    (Task 3).
  - "Every group exposes its attributes as `(name, value)` string pairs" is
    reworded to the document, the cell and the pin; `bus_type.attributes()`
    stays the documented `dict[str, str]` exception.
  - `docs/CLI.md:192` runs the viewer in the background (`&`) so the following
    steps of the "Typical Agent Workflow" can run.
  - `cell_leakage_power`'s docstring says the value uses `leakage_power_unit`
    (voltage × current only when the library declares no leakage unit).
  - `liberty_tools/__init__.pyi` declares `MinPulseWidth` as a frozen
    dataclass, matching the runtime.
  - `docs/AI_API.md` and `README.md` document the new compare API:
    `UnitMismatch`, `AxisRoleMismatch`, `MalformedTable`,
    `Comparison.unit_mismatches`, `Comparison.axis_role_mismatches`,
    `Comparison.malformed_tables`, `Comparison.duplicate_arcs`,
    `Comparison.has_differences`, and the unit-mismatch policy (tables whose
    unit dimension differs are reported, not diffed).
  - `CLAUDE.md` gains the new invariants: the writer keeps the last edit per
    attribute; the writer patches the cell/pin the caller addressed; `compare`
    reports unit and axis-role mismatches instead of guessing; the compare
    module is `liberty_tools/comparison.py`.

- [ ] **Step 1: Collect the corrections**

List every statement above against the current files and note the file:line of
each. Nothing is implemented in this step.

- [ ] **Step 2: Apply the corrections**

Edit the docs and docstrings as listed. Keep the existing voice and structure of
each document; change only what is wrong.

- [ ] **Step 3: Verify the examples still run**

Run every code example in the changed doc sections (copy each into a script
under `/tmp` and run it with `uv run python`); fix any example that no longer
matches the API. Report the examples you ran and their output.

- [ ] **Step 4: Run the linters and the suite**

Run: `uv run pytest -q && uv run ruff check . && uv run ty check`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add docs README.md CLAUDE.md liberty_tools
git commit -m "docs: correct the writer, lookup and compare documentation"
```

---

### Task 11: Close the coverage gaps (spec test-gap minor)

**Files:**
- Modify: `tests/test_writer.py`, `tests/test_table_lookup.py`,
  `tests/test_compare.py`

**Interfaces:**
- Consumes: Tasks 1-9.
- Produces: tests that pin behaviour the suite could not detect before —
  these are the regressions a future change would slip through:
  1. A writer test that edits **two different cells** in one document (one
     value longer than the original, one shorter) and asserts both cells
     re-parse with the new values and the rest of the file is unchanged.
  2. A 3-D lookup test: a table with three axes asserting
     `value_at(row, col, depth)`, `lookup(index_1=…, index_2=…, index_3=…)`,
     a role-based `lookup(..., time=…)`, and an out-of-range `depth` raising
     `IndexError`.
  3. A test whose `lu_table_template` is declared **after** the cell that uses
     it, asserting `axis_roles()` and a role-based `lookup()` still work.
  4. A compare test that exercises `tolerance=`: two libraries whose axis
     values differ by a relative amount inside the tolerance match, and one
     outside it does not.

- [ ] **Step 1: Write the tests**

Write the four tests listed above. They must fail only if the behaviour is
broken — check each against the current code and confirm the expected result
holds (these are coverage, not new behaviour: if a test fails on current code,
report it as a finding instead of changing production code in this task).

- [ ] **Step 2: Run them**

Run: `uv run pytest -q tests/test_writer.py tests/test_table_lookup.py tests/test_compare.py`
Expected: PASS. If any of the four fails, that is a real defect — report it
with the failing output instead of adjusting the expectation.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests
git commit -m "test: cover multi-cell writes, 3-D lookup and late templates"
```

---

## Out of scope (deferred)

These were Minor in the review and are **not** fixed by this plan; they are
recorded here so the final review can triage them:

- `compare.py` re-derives the row-major flat index and axis count that Rust
  already owns (`src/lib.rs:4666`, `:1763`) — a second implementation of an
  invariant.
- The `docs/AI_API.md` / `README.md` claim that `lookup()` and `value_at()`
  accept "either by index or by the axis's physical variable" — the wording is
  corrected in Task 10, but no API change follows.
- `min_pulse_width_high` / `_low` fall back to the misspelled vendor spelling
  `min_capulse_width_*` — deliberate vendor alias, unchanged.
- `axis_role(n)` is not truncated to the axes a table actually has.
- CCS wave vectors are compared pairwise by list position.
- `compare` does not normalize *equivalent* unit spellings (`1ns` vs `0.001ns`);
  only identical declarations are treated as the same unit.
