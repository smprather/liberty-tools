from __future__ import annotations

from pathlib import Path
from typing import Any

from . import _native


class LibertyDocument:
    def __init__(self, native: _native.Document):
        self._native = native

    @property
    def library_name(self) -> str:
        return self._native.library_name

    def cells(self) -> list[str]:
        return self._native.cells()

    def cell(self, name: str) -> Cell:
        return Cell(self._native.cell(name))

    def timing_tables(self, **filters: Any) -> list[dict[str, Any]]:
        return self._native.timing_tables(**filters)

    def to_polars(self, kind: str = "timing", **filters: Any):
        if kind != "timing":
            raise ValueError("only kind='timing' is supported")
        import polars as pl

        return pl.DataFrame(self.timing_tables(**filters))


class Cell:
    def __init__(self, native: _native.Cell):
        self._native = native

    @property
    def name(self) -> str:
        return self._native.name

    @property
    def area(self) -> float | None:
        return self._native.area

    def pins(self) -> list[str]:
        return self._native.pins()

    def pin(self, name: str) -> Pin:
        return Pin(self._native.pin(name))


class Pin:
    def __init__(self, native: _native.Pin):
        self._native = native

    @property
    def name(self) -> str:
        return self._native.name

    @property
    def direction(self) -> str | None:
        return self._native.direction

    @property
    def function(self) -> str | None:
        return self._native.function

    def timing_arcs(
        self,
        *,
        related_pin: str | None = None,
        timing_type: str | None = None,
        when: str | None = None,
    ) -> list[TimingArc]:
        return [
            TimingArc(arc)
            for arc in self._native.timing_arcs(
                related_pin=related_pin,
                timing_type=timing_type,
                when=when,
            )
        ]


class TimingArc:
    def __init__(self, native: _native.TimingArc):
        self._native = native

    @property
    def related_pin(self) -> str | None:
        return self._native.related_pin

    @property
    def timing_type(self) -> str | None:
        return self._native.timing_type

    @property
    def when(self) -> str | None:
        return self._native.when

    def tables(self) -> list[str]:
        return self._native.tables()

    def table(self, name: str) -> TimingTable:
        return TimingTable(self._native.table(name))


class TimingTable:
    def __init__(self, native: _native.TimingTable):
        self._native = native

    @property
    def name(self) -> str:
        return self._native.name

    @property
    def index_1(self) -> list[float]:
        return self._native.index_1

    @property
    def index_2(self) -> list[float]:
        return self._native.index_2

    @property
    def values(self) -> list[float]:
        return self._native.values

    def to_polars(self):
        import polars as pl

        return pl.DataFrame(self._native.rows())


def parse_file(path: str | Path, **filters: Any) -> LibertyDocument:
    return LibertyDocument(_native.parse_file(str(path), **filters))


__all__ = [
    "Cell",
    "LibertyDocument",
    "Pin",
    "TimingArc",
    "TimingTable",
    "parse_file",
]
