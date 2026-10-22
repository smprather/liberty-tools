# Review Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two follow-ups the final review filed, and correct one
inaccurate sentence in the committed review spec.

**Architecture:** The repo is a maturin/PyO3 hybrid: all parsing and data
storage lives in Rust (`src/lib.rs`); `liberty_tools/__init__.py` is a thin
wrapper over the `#[pyclass]` types in `_native`; `liberty_tools/comparison.py`
is pure Python over the public API. Nothing here changes the writer's
*surgical* design or the flat-value layout.

**Tech Stack:** Rust (pyo3 0.28), Python 3.14, pytest, polars, ruff, `ty`.

**Spec:** `docs/superpowers/specs/2026-10-21-writer-compare-review.md` — the
original code review this branch grew out of. The final whole-branch review of
that work filed the two follow-ups; one sentence of the spec itself was
disproved during execution and is corrected here.

## Global Constraints

- The writer is SURGICAL: `Document::to_string`/`write` re-read the original
  source and rewrite only the attributes changed through `Cell::set_attribute` /
  `Pin::set_attribute`; everything else stays byte for byte.
- A table the compare helper cannot compare soundly must be REPORTED, never
  diffed with guessed numbers.
- `Comparison.has_differences` covers every category the helper reports —
  including the ones that are malformed input rather than a real difference
  (today: `duplicate_arcs`).
- The Python wrapper stays thin; the `.pyi` stub must match the runtime exactly.
- TDD: write the failing test first, watch it fail for the expected reason,
  then implement. Record the RED and GREEN output in the task report.
- Commands, from the repo root `/home/mylesp/liberty-tools`:
  `uv run pytest -q`, `uv run ruff check .`, `uv run ty check` (11 pre-existing
  diagnostics are expected; the count must not grow). No Rust change is
  expected, so no `maturin` rebuild.
- One commit per task.

## Review Focus

- A document with two cell groups of the same name → the comparison must say so
  instead of silently covering only the first group. (Task 1)
- After editing a pin in one container, the live model of the OTHER container's
  same-named pin must still hold its old value. (Task 2)
- The committed spec must not claim a symptom that was disproved during
  execution. (Task 3)

---

### Task 1: compare() reports cell names that occur more than once

**Files:**
- Modify: `liberty_tools/comparison.py` — `class Comparison`, `compare()`,
  `summary()`, `has_differences`
- Modify: `docs/AI_API.md`, `README.md` — the compare section
- Test: `tests/test_compare.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `Comparison.duplicate_cells: list[str]` — the cell names that occur more
    than once in either document, sorted, each name once.
  - `summary()["duplicate_cells"]` — how many there are.
  - `has_differences` is `True` when there is at least one (same rule as
    `duplicate_arcs`: a malformed input is reported, not silently accepted).
  - `LibertyDocument.cells()` lists a name once per cell group, so a name that
    occurs more than once means the document has several groups with that name.

- [ ] **Step 1: Write the failing test**

In `tests/test_compare.py`, add a fixture with two `cell (u1)` groups (the
malformed shape the parser accepts) and assert:

- `compare(doc, doc).duplicate_cells == ["u1"]`;
- `summary()["duplicate_cells"] == 1`;
- `has_differences is True`;
- the comparison still produces the entries of the FIRST group (the behaviour
  does not change, only the reporting).

Also assert a document with unique cell names reports `duplicate_cells == []`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest -q tests/test_compare.py -k duplicate_cell`
Expected: FAIL — `Comparison` has no `duplicate_cells`.

- [ ] **Step 3: Implement**

Detect the names from `a.cells()` and `b.cells()` (a name listed twice means
two groups), report the union, sorted and deduplicated. Add the field to
`Comparison`, the count to `summary()` and the category to `has_differences`.
Document in `docs/AI_API.md` and `README.md`: a document with two cell groups
of the same name is compared using the first group only, and the duplicate is
reported in `duplicate_cells`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest -q tests/test_compare.py`
Expected: PASS, and the existing comparison tests still pass.

- [ ] **Step 5: Run the full suite and the linters**

Run: `uv run pytest -q && uv run ruff check . && uv run ty check`
Expected: all pass; `ty` still reports 11 diagnostics.

- [ ] **Step 6: Commit**

```bash
git add liberty_tools/comparison.py docs/AI_API.md README.md tests/test_compare.py
git commit -m "fix(compare): report cell names that occur more than once"
```

---

### Task 2: the live model keeps the other container's pin unchanged

**Files:**
- Modify: `tests/test_writer.py` — `test_duplicate_pin_names_in_different_buses_patch_the_addressed_one`

**Interfaces:**
- Consumes: nothing new.
- Produces: no API change. The test pins that after editing `bus (B)`'s `pin
  (P)`, the in-memory model of `bus (A)`'s `pin (P)` still holds its old
  value, and the edited pin holds the new one.

- [ ] **Step 1: Write the failing test**

In the existing test, after the edit, assert on the LIVE model of the
original document (not only on the written file):

```python
assert doc.cell("u1").bus("A").pin("P").get("capacitance") == "0.001"
assert doc.cell("u1").bus("B").pin("P").get("capacitance") == "9.0"
```

`get()` is the raw attribute accessor; the typed `capacitance` getter is not
mirrored for edited pins and is not what this pins.

- [ ] **Step 2: Run the test to verify it passes (or reveals a defect)**

Run: `uv run pytest -q tests/test_writer.py -k duplicate_pin`
Expected: PASS if the container-aware edit application works. If it FAILS, that
is a real defect in the live model — report it with the failing output instead
of adjusting the expectation (production code is out of scope for this task).

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_writer.py
git commit -m "test: pin the live model of an unedited same-named pin"
```

---

### Task 3: correct the disproved claim in the review spec

**Files:**
- Modify: `docs/superpowers/specs/2026-10-21-writer-compare-review.md` — the
  I2 paragraph

**Interfaces:**
- Consumes: nothing new.
- Produces: the committed spec says what was actually verified.

- [ ] **Step 1: Correct the sentence**

The I2 paragraph ends with a claim that a `Comparison` constructor call with
an empty entries list (valid at runtime) is rejected by `ty`. That symptom was
disproved during execution: the old stub
already declared `Comparison.__init__(entries: ...)`, so the call type-checked.
The real defect — and the one that was fixed — is the two distinct nominal
`Comparison` types (and two `compare` signatures) between the package stub and
the module.

Rewrite the sentence to state only what was verified: the stub declared the
compare types a second time, so type checkers saw two distinct nominal
`Comparison` types and two `compare` signatures. Drop the rejected-constructor
claim. Do not change anything else in the file.

- [ ] **Step 2: Check the correction**

Run: `grep -n "entries=\[\]" docs/superpowers/specs/2026-10-21-writer-compare-review.md`
— it must return nothing. Scope the check to the spec: the plan and report files
under `docs/superpowers/` may quote the old sentence as history.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-10-21-writer-compare-review.md
git commit -m "docs: correct the disproved symptom in the review spec"
```
