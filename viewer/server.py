"""FastAPI backend for the Liberty viewer.

Run:
    LIBERTY_FILE=dev.lib uv run uvicorn viewer.server:app --reload

Endpoints are deliberately cell-scoped and leaf-scoped so the browser never
pulls more than one table at a time — the basis for tolerating multi-GB files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .data import LibertyData

STATIC_DIR = Path(__file__).parent / "static"
# Fixed, predictable path so "check the debug dump" always means this file.
DEBUG_DUMP = Path("/tmp/liberty_view_debug.json")


def _dev_enabled() -> bool:
    return os.environ.get("LIBERTY_DEV") == "1"

app = FastAPI(title="Liberty Viewer")
_data: LibertyData | None = None


@app.middleware("http")
async def no_store_api(request: Request, call_next):
    """Never let the browser cache API JSON — the tree/table payloads change
    whenever the lib is rebuilt, and a stale cached tree silently hides edits."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def get_data() -> LibertyData:
    global _data
    if _data is None:
        path = os.environ.get("LIBERTY_FILE", "dev.lib")
        if not Path(path).exists():
            raise HTTPException(500, f"LIBERTY_FILE not found: {path}")
        _data = LibertyData.load(path)
    return _data


@app.get("/api/meta")
def meta():
    return get_data().meta()


@app.get("/api/cells")
def cells(
    filter: str | None = None,
    offset: int = 0,
    limit: int = Query(500, le=5000),
):
    return get_data().cell_names(filter, offset, limit)


@app.get("/api/cells/{cell}")
def cell_tree(cell: str):
    try:
        return get_data().cell_tree(cell)
    except KeyError:
        raise HTTPException(404, f"unknown cell {cell!r}")


@app.get("/api/table")
def table(
    cell: str,
    pin: str,
    group: str,
    arc_index: int,
    table: str,
    container: str = "",
):
    try:
        return get_data().table(cell, pin, group, arc_index, table, container)
    except (KeyError, IndexError) as exc:
        raise HTTPException(404, f"table not found: {exc}")


@app.get("/api/config")
def config():
    """Client boot config. ``dev`` toggles the in-page Dump Debug button."""
    return {"dev": _dev_enabled()}


@app.post("/api/debug")
async def debug_dump(request: Request):
    """Persist the client's current state to ``/tmp/liberty_view_debug.json`` so
    it can be inspected out-of-band (overwriting any prior dump). Only enabled
    under ``--dev`` to keep a file-writing endpoint off by default."""
    if not _dev_enabled():
        raise HTTPException(404, "debug dump disabled (run with --dev)")
    state = await request.json()
    DEBUG_DUMP.write_text(json.dumps(state, indent=2))
    return {"ok": True, "path": str(DEBUG_DUMP)}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
