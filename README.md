# liberty-tools

`liberty-tools` is a fast Python library for parsing and querying Synopsys
Liberty `.lib` timing models. It streams Liberty files through a Rust backend
and exposes a Python API for cells, pins, timing arcs, timing tables, and Polars
dataframe extraction.

The current implementation focuses on standard-cell timing, power, and CCS data:

- streaming parse from `.lib` and `.lib.gz` paths
- low-memory Rust-backed indexing with on-demand cell parsing (`LibraryIndex`)
- cell, pin, and timing arc lookup
- bus, bundle, and Liberty `type(...)` bus definition lookup
- 1D, 2D, and 3D timing table extraction to Python rows or Polars
- `internal_power` extraction (switching energy in joules)
- CCS data: `output_current_*` waves, CCSP dynamic current, and CCS-noise
  (CCSN) stage data (`dc_current`, `output_voltage_*`)
- Boolean-aware `when` filtering
- the GIL is released during parsing, so many libraries can be opened in
  parallel threads

For LLM/agent-oriented API usage, see [docs/AI_API.md](docs/AI_API.md).
The package also ships `py.typed` and `.pyi` stubs for coding tools.

## Project Status

This is an early implementation. The parser is already useful for large timing
libraries, but the public API should still be treated as pre-1.0.

On the local 96.8 MB reference Liberty file, the release extension parses the
whole library into an in-memory document in about 1.5 seconds (~150 MB peak
RSS). The lazy `LibraryIndex` used by the viewer opens the same file in about
0.15 seconds and parses individual cells on demand.

## Install From GitHub

Until wheels are published, install directly from the repository:

```bash
python -m pip install "git+https://github.com/smprather/liberty-tools.git"
```

For projects managed by `uv`:

```bash
uv add "liberty-tools @ git+https://github.com/smprather/liberty-tools.git"
```

This package contains a Rust extension, so source installs need:

- Python 3.14 or newer
- Rust toolchain with `cargo`
- a working compiler toolchain for your platform

## Develop Locally

Clone and build the editable extension:

```bash
git clone https://github.com/smprather/liberty-tools.git
cd liberty-tools
uv sync --dev
uv run maturin develop --release
```

Run tests:

```bash
uv run pytest -q
cargo fmt --check
cargo check
```

The repository does not include large Liberty reference files. If you have a
local sample named `generic80_ss_125c_1p116v_0p84v.lib` in the repo root, the
large-file smoke tests will run; otherwise they are skipped.

## Basic Usage

```python
import liberty_tools as lt

doc = lt.parse_file("generic80_ss_125c_1p116v_0p84v.lib")

print(doc.library_name)
print(doc.cells()[:10])

cell = doc.cell("and2d102srdh")
print(cell.area)
print(cell.pins())

pin = cell.pin("y")
arcs = pin.timing_arcs(related_pin="a")

for arc in arcs:
    print(arc.related_pin, arc.timing_type, arc.when, arc.tables())
```

## Timing Tables

Get one timing table from an arc:

```python
arc = doc.cell("and2d102srdh").pin("y").timing_arcs(related_pin="a")[0]
table = arc.table("cell_rise")

print(table.index_1)
print(table.index_2)
print(table.values)
```

Extract timing table rows across the document:

```python
rows = doc.timing_tables(
    cell="and2d102srdh",
    pin="y",
    related_pin="a",
    table="cell_rise",
)
```

Convert directly to Polars:

```python
df = doc.to_polars(cell="and2d102srdh", table="cell_rise")
print(df)
```

The timing dataframe uses long-form rows with columns such as:

- `cell`
- `pin`
- `related_pin`
- `timing_type`
- `when`
- `table`
- `index_1`
- `index_2`
- `row`
- `col`
- `value`

## Boolean `when` Filtering

`when` filters are parsed as Boolean expressions, not string matches. A query
matches an arc when the arc condition implies the requested condition.

```python
pin.timing_arcs(when="A")
doc.to_polars(when="A", table="cell_rise")
```

For a cell with inputs `A`, `B`, and `C`, querying `when="A"` matches arcs whose
conditions require `A=1`, regardless of the other pins:

- `A & B` matches
- `A & !B` matches
- `!A` does not match
- `A | B` does not match, because it can be true when `A=0`

Supported operators include `!`, `~`, postfix `'`, `&`, `*`, `|`, `+`, `^`, and
parentheses.

## Selective Parsing

For large libraries, restrict indexing to selected cells:

```python
doc = lt.parse_file(
    "generic80_ss_125c_1p116v_0p84v.lib",
    cells=["and2d102srdh", "and2d12sr"],
)
```

The parser still streams through the input file, but it only materializes data
for the requested cells.

## Current API

```python
lt.parse_file(path, cells=None) -> LibertyDocument

doc.library_name
doc.cells()
doc.cell(name)
doc.timing_tables(...)
doc.internal_power_tables(...)
doc.to_polars(kind="timing", ...)   # or kind="power"

cell.name
cell.area
cell.pins()
cell.pin(name)
cell.buses()
cell.bus(name)
cell.bundles()
cell.bundle(name)

bus.name
bus.direction
bus.function
bus.bus_type
bus.pins()
bus.pin(name)

bundle.name
bundle.direction
bundle.function
bundle.members
bundle.pins()
bundle.pin(name)

doc.bus_types()
doc.bus_type(name)

pin.name
pin.direction
pin.function
pin.timing_arcs(related_pin=None, timing_type=None, when=None)
pin.internal_power()

arc.related_pin
arc.timing_type
arc.when
arc.tables()
arc.table(name)
arc.ccsn_stages()                   # CCS-noise stage data (CCSN libs)

table.name
table.index_1
table.index_2
table.index_3
table.values
table.to_polars()
```

## Notes

The Python package used for initial behavior comparison,
`liberty-parser`, is not part of the runtime dependency set. It remains useful
as a reference during development, but `liberty-tools` uses its own Rust parser.
