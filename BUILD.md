# Building

The **Rust** dependencies are vendored so the native extension builds without
hitting the crates.io registry. Python dependencies are **not** vendored —
install them normally with `uv` or `pip`.

## Vendored Rust crates

`vendor/cargo/` holds every crate the extension needs (pyo3, flate2/zlib-rs, and
their transitive deps). `.cargo/config.toml` redirects crates.io to that
directory, so `cargo` / `maturin` never reach the network for crates.

Regenerate after changing `Cargo.toml`:

```bash
cargo vendor vendor/cargo
```

## Frontend

The viewer loads `viewer/static/plotly.min.js` locally (not from a CDN), so it
works without internet. Refresh it with:

```bash
curl -o viewer/static/plotly.min.js https://cdn.plot.ly/plotly-2.35.2.min.js
```

## Prerequisites

- **Rust toolchain** (`rustc` + `cargo`), edition 2021.
- **CPython 3.14** with `venv`.

## Build

```bash
# Python deps (online — uv or pip):
uv sync --dev
#   or:  python3.14 -m venv .venv && . .venv/bin/activate
#        pip install fastapi polars 'uvicorn[standard]' click rich-click maturin pytest ruff ty

# Native extension (Rust crates come from vendor/cargo via .cargo/config.toml):
uv run maturin develop --release
#   build a wheel instead:  uv run maturin build --release
```

`.cargo/config.toml` points cargo at the vendored crates unconditionally, so the
crate side is already offline. Set `CARGO_NET_OFFLINE=true` to make any stray
crate fetch fail loudly.

## Run / test

```bash
uv run liberty_view dev.lib          # browser viewer (Plotly served locally)
uv run liberty_format dev.lib        # transparency-checked formatter
uv run pytest -q                     # tests
uv run ruff check . && cargo fmt --check
```
