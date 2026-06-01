"""FastAPI backend for the Liberty viewer.

Run:
    LIBERTY_FILE=dev.lib uv run uvicorn viewer.server:app --reload

Endpoints are deliberately cell-scoped and leaf-scoped so the browser never
pulls more than one table at a time — the basis for tolerating multi-GB files.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .data import LibertyData

STATIC_DIR = Path(__file__).parent / "static"

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


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
