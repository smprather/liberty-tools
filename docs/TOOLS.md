# Tools

`open-eda-file-tools` hosts open EDA data-file tooling. Each tool is its own
Python package and its own distribution; the repository is the shared home for
their source, tests and release history.

| Tool | Package | Commands | Status |
| --- | --- | --- | --- |
| Liberty `.lib` parser, writer, viewer and formatter | `liberty_tools` | `liberty-view`, `liberty-format` | shipped |
| VCD toggle-count profiler | `vcd_tools` (reserved) | — | on the way |
| DEF reader | `def_tools` (reserved) | — | on the way |

## Adding a tool

1. Create the tool's package at the repository root (`<name>_tools/`), with
   its own `pyproject.toml`, distribution name, version and tests.
2. Give it its own command-line entry points, kebab-case and prefixed with the
   file format it reads (`liberty-…`, `vcd-…`, `def-…`).
3. If it has a Rust backend, point its `[build-system]` at `maturin` and keep
   its native crate beside the package. A pure-Python tool uses a plain build
   backend.
4. Add the tool to the table above and to the repository layout section of the
   README.
5. Follow the release conventions in `VERSIONING_PLAN.md`. Tools ship from this
   repository but keep their own distribution and version.

## Shared conventions

- Tests live beside the tool they cover (`tests/` covers the Liberty tool
  today).
- `BUILD.md` covers the toolchain, `CLAUDE.md` covers the repository structure
  and the invariants a tool must preserve.
- There is one release history for the repository: tags in `vYYYY.M.N` form
  (`VERSIONING_PLAN.md`), pointing at commits whose package version is stable.
