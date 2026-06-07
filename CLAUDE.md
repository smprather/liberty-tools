# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
uv sync --dev
uv run maturin develop --release   # required after any Rust change

# Tests
uv run pytest -q                   # Python tests
cargo fmt --check                  # Rust format check
cargo check                        # Rust type check

# Single test
uv run pytest tests/test_extraction_api.py::test_1d_2d_and_3d_table_extraction -q

# Lint / type check
uv run ruff check .
uv run ty check
```

The large-file smoke tests need `generic80_ss_125c_1p116v_0p84v.lib` in the repo root; they skip otherwise.

## Architecture

This is a **maturin/PyO3 hybrid**: all parsing and data storage lives in Rust (`src/lib.rs`); Python is a thin wrapper.

```
src/lib.rs                 Rust: lexer, parser, boolean evaluator, PyO3 #[pyclass] types
liberty_tools/__init__.py  Python wrapper classes (LibertyDocument, Cell, Pin, …)
liberty_tools/__init__.pyi Type stubs
tests/                     Pytest integration tests (inline fixture strings, no large files)
```

### Rust layer (`src/lib.rs`)

Single file containing:
- **`Lexer`** — byte-level streaming tokenizer; handles `#`, `//`, `/* */` comments, quoted strings, backslash line continuation
- **`Parser`** — recursive descent; builds `*Data` structs (plain Rust) by consuming tokens
- **`BoolParser` / `BoolExpr` / `bool_implies`** — Liberty Boolean expression parser and implication checker for `when` filters; uses brute-force truth-table enumeration
- **`#[pyclass]` types** (`Document`, `Cell`, `Pin`, `Bus`, `Bundle`, `BusType`, `TimingArc`, `TimingTable`) — own `Vec<*Data>` and expose methods to Python; registered in `_native` module
- **`parse_file` `#[pyfunction]`** — entry point; opens `.lib` or `.lib.gz`, constructs parser with optional cell filter

There are two parallel type hierarchies: `*Data` (plain Rust structs, no PyO3 overhead) used during parse, and `#[pyclass]` types that wrap/clone them when returned to Python. This avoids PyO3 GIL overhead during bulk parse.

### Python layer (`liberty_tools/__init__.py`)

Each class wraps the corresponding native object via `self._native`. `LibertyDocument.to_polars()` calls `timing_tables()` and hands the result to `polars.DataFrame`. `parse_file` is the sole public entry point.

### Key behaviors to preserve

- **`when` filter uses implication, not equality**: `when="A"` matches `"A & B"` and `"A & !B"` but not `"A | B"`. Any changes to `bool_implies` must preserve this semantics.
- **Parse-time cell filter** (`cells=[...]` in `parse_file`) skips group bodies entirely via `skip_group_body()` — it is not a post-parse filter.
- **`timing_tables()` / `to_polars()` search pins inside buses and bundles** in addition to top-level cell pins (see the nested loops in `Document::timing_tables`).
- **3D table flattening**: values stored row-major across `(index_1 × index_2 × index_3)`; `table_position()` reconstructs `(i, j, k)`. The Polars column is `depth`, not `index_3_pos`.
- **`internal_power` is energy, not power**: the `rise_power`/`fall_power` table values are switching *energy* in joules. Scale = `voltage_unit × current_unit × time_unit` (`Document::energy_unit_joules`, exposed as `doc.energy_unit_joules()`); ASAP7 = `1e-15` (fJ). Extract via `internal_power_tables()` / `to_polars(kind="power")` (rows carry `related_pg_pin`; reuses `table_position`/`TimingTableData`). **Non-propagating energy** (input pin switches, no output switch) lives in input-pin `internal_power` groups with no `related_pin` and a 1-D table over input transition — these are included, with `related_pin` null.
- **One top-level group**: a valid library is a single `library` group. A second top-level group (typically a `cell` orphaned by a premature `library` close) is reported as an `unbalanced braces` error pointing at that group, not skipped — see the stray-`}` guard in `Parser::parse_document`. The ASAP7 SIMPLE-group libs ship with this exact defect (spurious `}` after `XOR2xp5r`, dropping `NAND5xp2R`).
- **CCSN noise data** lives *inside* `timing()` groups as `ccsn_first_stage` / `ccsn_last_stage`, parsed into `CcsnStageData`/`CcsnStage` (not the `tables` list) via `parse_ccsn_stage_body` — captures the scalars (`is_inverting`, `miller_cap_*`, `stage_type`, …), the 2-D `dc_current` IV surface, and `output_voltage_rise`/`_fall` vector sets (reuses `parse_timing_table_body`'s `.vectors`). `propagated_noise_*` is **deferred** (4-D, would need an `index_4` on the table primitive). Exposed as `arc.ccsn_stages()`.
- **GIL released during heavy work**: `parse_file`, `LibraryIndex::open`, `LibraryIndex::cell`, and `LibraryIndex::cell_source` run their pure-Rust parse/extract inside `py.detach(...)` (pyo3 0.28's renamed `allow_threads`) and convert `io::Error`/`ParseError` to `PyErr` **outside** the closure (error enums `ParseLoadError`/`CellLookupError`/`CellSourceError`). This lets many libraries parse concurrently; keep new heavy entry points GIL-free the same way.

## Liberty spec reference

The authoritative Liberty syntax/semantics reference is `Liberty_User_Guides_and_Reference_Manual_Suite_Version_2017.06.pdf` (1458 pages, gitignored — local only). When parser behavior is ambiguous, consult it instead of guessing.

The PDF's printed TOC uses chapter-relative page numbers (e.g. `2-3`), which the Read tool can't use. Two gitignored sidecars map topics to **absolute** PDF pages (`pypdf` is a dev dependency; regenerate if missing):

- `liberty_spec_toc.txt` — section title → absolute page, from the PDF outline. Grep this first for "where is the section on X". Regenerate: walk `PdfReader(pdf).outline`, use `get_destination_page_number(item)+1`.
- `liberty_spec.txt` — full text dump for exhaustive keyword sweeps. Pages are `\f`-separated, so awk record number = absolute page. Regenerate: `pdftotext -layout <pdf> liberty_spec.txt`.

```bash
grep -i bus_naming_style liberty_spec_toc.txt                                   # section → page
awk -v RS='\f' 'tolower($0) ~ /bus_naming_style/ {print "page " NR}' liberty_spec.txt  # every mention → page
```

Then `Read` the PDF at that page range (`pages: "N-M"`, ≤20 pages/request) to see tables/figures rendered.
