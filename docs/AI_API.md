# liberty-tools AI API Guide

This guide is for AI agents writing code that consumes `liberty_tools`.
Prefer these APIs over manual Liberty parsing.

## First Choice

```python
import liberty_tools as lt

doc = lt.parse_file("library.lib", cells=["target_cell"])
df = doc.to_polars(table="cell_rise", when="A")
```

Use `parse_file(path, cells=...)` for large files. Do not read the Liberty file
into Python strings.

## Exact API

```python
lt.parse_file(path: str | Path, cells: list[str] | None = None) -> LibertyDocument

doc.library_name -> str
doc.cells() -> list[str]
doc.cell(name: str) -> Cell
doc.bus_types() -> list[str]
doc.bus_type(name: str) -> BusType
doc.timing_tables(...) -> list[dict[str, object]]
doc.to_polars(kind="timing", **filters) -> polars.DataFrame

cell.name -> str
cell.area -> float | None
cell.pins() -> list[str]
cell.pin(name: str) -> Pin
cell.buses() -> list[str]
cell.bus(name: str) -> Bus
cell.bundles() -> list[str]
cell.bundle(name: str) -> Bundle

pin.name -> str
pin.direction -> str | None
pin.function -> str | None
pin.timing_arcs(related_pin=None, timing_type=None, when=None) -> list[TimingArc]

bus.name -> str
bus.direction -> str | None
bus.function -> str | None
bus.bus_type -> str | None
bus.pins() -> list[str]
bus.pin(name: str) -> Pin
bus.timing_arcs(...) -> list[TimingArc]

bundle.name -> str
bundle.direction -> str | None
bundle.function -> str | None
bundle.members -> list[str]
bundle.pins() -> list[str]
bundle.pin(name: str) -> Pin
bundle.timing_arcs(...) -> list[TimingArc]

bus_type.name -> str
bus_type.attributes() -> dict[str, str]
bus_type.get(key: str) -> str | None

arc.related_pin -> str | None
arc.timing_type -> str | None
arc.when -> str | None
arc.tables() -> list[str]
arc.table(name: str) -> TimingTable

table.name -> str
table.index_1 -> list[float]
table.index_2 -> list[float]
table.values -> list[float]
table.to_polars() -> polars.DataFrame
```

## Timing DataFrame Schema

`doc.to_polars(kind="timing", **filters)` returns long-form timing table rows:

```text
cell: str
pin: str
related_pin: str | None
timing_type: str | None
when: str | None
table: str
index_1: float | None
index_2: float | None
row: int
col: int
value: float
```

Supported filters:

```python
doc.to_polars(
    cell="u_ram",
    pin="q",
    related_pin="clk",
    timing_type="rising_edge",
    when="CS & WE",
    table="cell_rise",
)
```

`cells=[...]` in `parse_file` is parse-time materialization filtering.
`cell=...` and `pin=...` in `to_polars` are query-time filters.

## Boolean `when` Semantics

`when` filters are Boolean implication checks, not string equality.

Querying `when="A"` means: return arcs whose stored condition requires `A=1`.

Examples:

```text
stored when     query when="A"     match
A & B           yes
A & !B          yes
!A              no
A | B           no
```

Supported operators:

```text
!  ~  postfix '  &  *  |  +  ^  parentheses
```

## Bus and Bundle Use

RAM Liberty files commonly describe buses and bundles. Use these accessors:

```python
cell = doc.cell("my_ram")

for bus_name in cell.buses():
    bus = cell.bus(bus_name)
    print(bus.name, bus.direction, bus.bus_type, bus.pins())

for bundle_name in cell.bundles():
    bundle = cell.bundle(bundle_name)
    print(bundle.name, bundle.members)

for type_name in doc.bus_types():
    bus_type = doc.bus_type(type_name)
    print(bus_type.attributes())
```

Nested bus or bundle pins are exposed through `bus.pins()` / `bundle.pins()`.
Timing tables attached to nested pins are included by `doc.to_polars(...)`.

## Do And Do Not

Do:

- Use `parse_file(path)` directly.
- Use `cells=[...]` for targeted extraction from large libraries.
- Use `to_polars(...)` for tabular timing extraction.
- Use Boolean `when` filters for state-dependent timing.
- Use `cell.buses()`, `cell.bundles()`, and `doc.bus_types()` for RAM ports.

Do not:

- Do not call `open(path).read()` before parsing.
- Do not string-match `when` conditions.
- Do not assume this is a full Liberty AST API.
- Do not expect all non-timing Liberty groups to be materialized yet.

## Errors

- Unknown cell, pin, bus, bundle, bus type, or table: `KeyError`.
- Invalid Boolean `when` expression: `ValueError`.
- Liberty syntax parse error: `ValueError` with line and column.
