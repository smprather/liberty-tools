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

    @property
    def voltage_unit(self) -> str | None:
        return self._native.voltage_unit

    @property
    def current_unit(self) -> str | None:
        return self._native.current_unit

    @property
    def time_unit(self) -> str | None:
        return self._native.time_unit

    @property
    def capacitive_load_unit(self) -> str | None:
        """Capacitance unit, e.g. ``"ff"`` from ``capacitive_load_unit (1, ff)``."""
        return self._native.capacitive_load_unit

    def templates(self) -> dict[str, list[str | None]]:
        """Lookup-table templates: name -> ``[variable_1, variable_2, variable_3]``."""
        return self._native.templates()

    def attributes(self) -> list[tuple[str, str]]:
        """Ordered ``(name, value)`` library-group simple/complex attributes."""
        return self._native.attributes()

    def driver_waveforms(self) -> list[TimingTable]:
        """``normalized_driver_waveform`` tables (input slew × normalized voltage
        → time). ``name`` holds the ``driver_waveform_name``."""
        return [TimingTable(w) for w in self._native.driver_waveforms()]

    def energy_unit_joules(self) -> float | None:
        """SI scale (joules) for ``internal_power`` energy values.

        ``internal_power`` is a Liberty misnomer: the table values are switching
        *energy*, not power. The scale is ``voltage_unit * current_unit *
        time_unit``; for ASAP7 (1V, 1mA, 1ps) that is ``1e-15`` (femtojoules).
        """
        return self._native.energy_unit_joules()

    def cells(self) -> list[str]:
        return self._native.cells()

    def cell(self, name: str) -> Cell:
        return Cell(self._native.cell(name))

    def bus_types(self) -> list[str]:
        return self._native.bus_types()

    def bus_type(self, name: str) -> BusType:
        return BusType(self._native.bus_type(name))

    def timing_tables(self, **filters: Any) -> list[dict[str, Any]]:
        return self._native.timing_tables(**filters)

    def internal_power_tables(self, **filters: Any) -> list[dict[str, Any]]:
        """Flattened ``internal_power`` (rise_power/fall_power) table rows.

        Values are switching energy in library units; multiply by
        :meth:`energy_unit_joules` for joules. Non-propagating energy on input
        pins (input switches, no output switch) appears here too, typically as
        groups with no ``related_pin`` and a 1-D table over input transition.
        """
        return self._native.internal_power_tables(**filters)

    def to_polars(self, kind: str = "timing", **filters: Any):
        if kind == "timing":
            rows = self.timing_tables(**filters)
        elif kind == "power":
            rows = self.internal_power_tables(**filters)
        else:
            raise ValueError("kind must be 'timing' or 'power'")
        import polars as pl

        # Scan all rows for schema: optional columns (when, related_pin, …) are
        # null in the first rows but become strings later, which trips Polars'
        # default 100-row inference.
        return pl.DataFrame(rows, infer_schema_length=None)


class BooleanExpression:
    """A parsed Liberty boolean expression.

    ``str(expr)`` is a minimized sum-of-products (compact, human-readable).
    ``==`` and ``hash`` compare the canonical sum-of-minterms over the support,
    so two expressions are equal exactly when they are logically equivalent
    (``BooleanExpression("A | B") == BooleanExpression("B | A")``,
    ``BooleanExpression("A & (B | !B)") == BooleanExpression("A")``).

    Construct one directly from any Liberty boolean string —
    ``BooleanExpression("CLK * D * !QN")`` — or obtain it from a parsed field via
    the ``*_expr`` accessors (``pin.function_expr()``, ``arc.when_expr()``, …).
    """

    def __init__(self, source: str | _native.BooleanExpression):
        if isinstance(source, str):
            self._native = _native.BooleanExpression(source)
        else:
            self._native = source

    @property
    def source(self) -> str:
        """The original (verbatim) expression text."""
        return self._native.source

    @property
    def raw(self) -> str:
        """Alias of :attr:`source`."""
        return self._native.raw

    @property
    def variables(self) -> list[str]:
        """Support variables (those the function depends on), sorted."""
        return self._native.variables

    def minterms(self) -> list[str]:
        """Canonical product terms (sum-of-minterms over the support)."""
        return self._native.minterms()

    def canonical(self) -> str:
        """The canonical sum-of-minterms string that backs equality/hashing."""
        return self._native.canonical()

    def minimized(self) -> str:
        """The minimized sum-of-products string (same as ``str(self)``)."""
        return self._native.minimized()

    def eval(self, mapping: dict[str, bool] | None = None, **kwargs: bool) -> bool:
        """Evaluate under a ``{var: bool}`` mapping and/or keyword args; unset
        variables default to false, unknown variables are ignored."""
        return self._native.eval(mapping, **kwargs)

    def implies(self, other: BooleanExpression) -> bool:
        """True if ``self`` logically implies ``other``."""
        return self._native.implies(other._native)

    def __str__(self) -> str:
        return self._native.__str__()

    def __repr__(self) -> str:
        return self._native.__repr__()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BooleanExpression):
            return NotImplemented
        return self._native == other._native

    def __hash__(self) -> int:
        return hash(self._native)


def _wrap_expr(native: _native.BooleanExpression | None) -> BooleanExpression | None:
    """Wrap an optional native ``BooleanExpression`` (None stays None)."""
    return BooleanExpression(native) if native is not None else None


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

    def buses(self) -> list[str]:
        return self._native.buses()

    def bus(self, name: str) -> Bus:
        return Bus(self._native.bus(name))

    def bundles(self) -> list[str]:
        return self._native.bundles()

    def bundle(self, name: str) -> Bundle:
        return Bundle(self._native.bundle(name))

    def attributes(self) -> list[tuple[str, str]]:
        """Ordered ``(name, value)`` cell-level simple/complex attributes."""
        return self._native.attributes()

    def dynamic_currents(self) -> list[DynamicCurrent]:
        """CCS power (``dynamic_current``) groups."""
        return [DynamicCurrent(dc) for dc in self._native.dynamic_currents()]

    def ff(self) -> Ff | None:
        """The flip-flop (``ff`` / ``ff_bank``) group, if the cell is sequential."""
        native = self._native.ff()
        return Ff(native) if native is not None else None

    def latch(self) -> Latch | None:
        """The latch (``latch`` / ``latch_bank``) group, if present."""
        native = self._native.latch()
        return Latch(native) if native is not None else None


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

    @property
    def three_state(self) -> str | None:
        return self._native.three_state

    @property
    def power_down_function(self) -> str | None:
        return self._native.power_down_function

    def function_expr(self) -> BooleanExpression | None:
        """The ``function`` as a parsed :class:`BooleanExpression` (None if absent)."""
        return _wrap_expr(self._native.function_expr())

    def three_state_expr(self) -> BooleanExpression | None:
        """The ``three_state`` condition as a :class:`BooleanExpression` (None if absent)."""
        return _wrap_expr(self._native.three_state_expr())

    def power_down_function_expr(self) -> BooleanExpression | None:
        """The ``power_down_function`` as a :class:`BooleanExpression` (None if absent)."""
        return _wrap_expr(self._native.power_down_function_expr())

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

    def internal_power(
        self,
        *,
        related_pin: str | None = None,
        related_pg_pin: str | None = None,
        when: str | None = None,
    ) -> list[InternalPower]:
        return [
            InternalPower(group)
            for group in self._native.internal_power(
                related_pin=related_pin,
                related_pg_pin=related_pg_pin,
                when=when,
            )
        ]

    def attributes(self) -> list[tuple[str, str]]:
        """Ordered ``(name, value)`` pin-level simple/complex attributes."""
        return self._native.attributes()


class Bus:
    def __init__(self, native: _native.Bus):
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

    def function_expr(self) -> BooleanExpression | None:
        """The bus ``function`` as a parsed :class:`BooleanExpression` (None if absent)."""
        return _wrap_expr(self._native.function_expr())

    @property
    def bus_type(self) -> str | None:
        return self._native.bus_type

    def pins(self) -> list[str]:
        return self._native.pins()

    def pin(self, name: str) -> Pin:
        return Pin(self._native.pin(name))

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


class Bundle:
    def __init__(self, native: _native.Bundle):
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

    def function_expr(self) -> BooleanExpression | None:
        """The bundle ``function`` as a parsed :class:`BooleanExpression` (None if absent)."""
        return _wrap_expr(self._native.function_expr())

    @property
    def members(self) -> list[str]:
        return self._native.members

    def pins(self) -> list[str]:
        return self._native.pins()

    def pin(self, name: str) -> Pin:
        return Pin(self._native.pin(name))

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


class BusType:
    def __init__(self, native: _native.BusType):
        self._native = native

    @property
    def name(self) -> str:
        return self._native.name

    def attributes(self) -> dict[str, str]:
        return self._native.attributes()

    def get(self, key: str) -> str | None:
        return self._native.get(key)


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

    @property
    def sdf_cond(self) -> str | None:
        return self._native.sdf_cond

    def when_expr(self) -> BooleanExpression | None:
        """The ``when`` condition as a parsed :class:`BooleanExpression` (None if absent)."""
        return _wrap_expr(self._native.when_expr())

    def sdf_cond_expr(self) -> BooleanExpression | None:
        """The ``sdf_cond`` as a parsed :class:`BooleanExpression` (None if absent)."""
        return _wrap_expr(self._native.sdf_cond_expr())

    def tables(self) -> list[str]:
        return self._native.tables()

    def table(self, name: str) -> TimingTable:
        return TimingTable(self._native.table(name))


class InternalPower:
    """An ``internal_power`` group (switching energy, not power)."""

    def __init__(self, native: _native.InternalPower):
        self._native = native

    @property
    def related_pin(self) -> str | None:
        return self._native.related_pin

    @property
    def related_pg_pin(self) -> str | None:
        return self._native.related_pg_pin

    @property
    def when(self) -> str | None:
        return self._native.when

    def when_expr(self) -> BooleanExpression | None:
        """The ``when`` condition as a parsed :class:`BooleanExpression` (None if absent)."""
        return _wrap_expr(self._native.when_expr())

    def tables(self) -> list[str]:
        return self._native.tables()

    def table(self, name: str) -> TimingTable:
        return TimingTable(self._native.table(name))


class DynamicCurrent:
    """A ``dynamic_current`` group (CCS power: per-condition PG current waves)."""

    def __init__(self, native: _native.DynamicCurrent):
        self._native = native

    @property
    def related_inputs(self) -> str | None:
        return self._native.related_inputs

    @property
    def related_outputs(self) -> str | None:
        return self._native.related_outputs

    @property
    def when(self) -> str | None:
        return self._native.when

    def when_expr(self) -> BooleanExpression | None:
        """The ``when`` condition as a parsed :class:`BooleanExpression` (None if absent)."""
        return _wrap_expr(self._native.when_expr())

    def switching_groups(self) -> list[SwitchingGroup]:
        return [SwitchingGroup(sg) for sg in self._native.switching_groups()]


class SwitchingGroup:
    def __init__(self, native: _native.SwitchingGroup):
        self._native = native

    @property
    def input_switching_condition(self) -> str | None:
        return self._native.input_switching_condition

    @property
    def output_switching_condition(self) -> str | None:
        return self._native.output_switching_condition

    def input_switching_expr(self) -> BooleanExpression | None:
        """``input_switching_condition`` as a :class:`BooleanExpression` (None if absent)."""
        return _wrap_expr(self._native.input_switching_expr())

    def output_switching_expr(self) -> BooleanExpression | None:
        """``output_switching_condition`` as a :class:`BooleanExpression` (None if absent)."""
        return _wrap_expr(self._native.output_switching_expr())

    def pg_currents(self) -> list[PgCurrent]:
        return [PgCurrent(pg) for pg in self._native.pg_currents()]


class PgCurrent:
    """A ``pg_current`` group: current-vs-time waves for one PG pin."""

    def __init__(self, native: _native.PgCurrent):
        self._native = native

    @property
    def pg_pin(self) -> str | None:
        return self._native.pg_pin

    def vectors(self) -> list[TimingTable]:
        return [TimingTable(v) for v in self._native.vectors()]


class Ff:
    """A flip-flop (``ff`` / ``ff_bank``) group. The boolean attributes are
    available raw (strings) and as parsed expressions via ``*_expr``."""

    def __init__(self, native: _native.Ff):
        self._native = native

    @property
    def variable1(self) -> str | None:
        return self._native.variable1

    @property
    def variable2(self) -> str | None:
        return self._native.variable2

    @property
    def next_state(self) -> str | None:
        return self._native.next_state

    @property
    def clocked_on(self) -> str | None:
        return self._native.clocked_on

    @property
    def clocked_on_also(self) -> str | None:
        return self._native.clocked_on_also

    @property
    def clear(self) -> str | None:
        return self._native.clear

    @property
    def preset(self) -> str | None:
        return self._native.preset

    @property
    def power_down_function(self) -> str | None:
        return self._native.power_down_function

    def next_state_expr(self) -> BooleanExpression | None:
        return _wrap_expr(self._native.next_state_expr())

    def clocked_on_expr(self) -> BooleanExpression | None:
        return _wrap_expr(self._native.clocked_on_expr())

    def clocked_on_also_expr(self) -> BooleanExpression | None:
        return _wrap_expr(self._native.clocked_on_also_expr())

    def clear_expr(self) -> BooleanExpression | None:
        return _wrap_expr(self._native.clear_expr())

    def preset_expr(self) -> BooleanExpression | None:
        return _wrap_expr(self._native.preset_expr())

    def power_down_function_expr(self) -> BooleanExpression | None:
        return _wrap_expr(self._native.power_down_function_expr())


class Latch:
    """A latch (``latch`` / ``latch_bank``) group."""

    def __init__(self, native: _native.Latch):
        self._native = native

    @property
    def variable1(self) -> str | None:
        return self._native.variable1

    @property
    def variable2(self) -> str | None:
        return self._native.variable2

    @property
    def enable(self) -> str | None:
        return self._native.enable

    @property
    def data_in(self) -> str | None:
        return self._native.data_in

    @property
    def clear(self) -> str | None:
        return self._native.clear

    @property
    def preset(self) -> str | None:
        return self._native.preset

    def enable_expr(self) -> BooleanExpression | None:
        return _wrap_expr(self._native.enable_expr())

    def data_in_expr(self) -> BooleanExpression | None:
        return _wrap_expr(self._native.data_in_expr())

    def clear_expr(self) -> BooleanExpression | None:
        return _wrap_expr(self._native.clear_expr())

    def preset_expr(self) -> BooleanExpression | None:
        return _wrap_expr(self._native.preset_expr())


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
    def index_3(self) -> list[float]:
        return self._native.index_3

    @property
    def values(self) -> list[float]:
        return self._native.values

    @property
    def template(self) -> str | None:
        """Lookup-table template name from the group header (axis variables)."""
        return self._native.template

    @property
    def reference_time(self) -> float | None:
        """CCS only: the ``reference_time`` of a ``vector`` group."""
        return self._native.reference_time

    def vectors(self) -> list[TimingTable]:
        """CCS only: nested ``vector`` sub-tables (current-vs-time waves).

        Empty for ordinary NLDM tables. Each vector has a single ``index_1``
        (input slew) and ``index_2`` (output cap), an ``index_3`` time axis, and
        ``values`` holding the output current samples.
        """
        return [TimingTable(v) for v in self._native.vectors()]

    def to_polars(self):
        import polars as pl

        return pl.DataFrame(self._native.rows())


class LibraryIndex:
    """Lazy, cell-indexed view of a Liberty file for fast open on large libs.

    Reads the (decompressed) file into memory once and records each cell's byte
    range; the library header (units/templates/attrs) is parsed up front, but
    individual cells are parsed only when :meth:`cell` is called. Use this
    instead of :func:`parse_file` when you need to list/inspect a few cells of a
    multi-GB library without paying for a full parse.
    """

    def __init__(self, native: _native.LibraryIndex):
        self._native = native

    @classmethod
    def open(cls, path: str | Path) -> LibraryIndex:
        return cls(_native.LibraryIndex.open(str(path)))

    @property
    def library_name(self) -> str:
        return self._native.library_name

    @property
    def voltage_unit(self) -> str | None:
        return self._native.voltage_unit

    @property
    def current_unit(self) -> str | None:
        return self._native.current_unit

    @property
    def time_unit(self) -> str | None:
        return self._native.time_unit

    @property
    def capacitive_load_unit(self) -> str | None:
        return self._native.capacitive_load_unit

    def energy_unit_joules(self) -> float | None:
        return self._native.energy_unit_joules()

    def templates(self) -> dict[str, list[str | None]]:
        return self._native.templates()

    def attributes(self) -> list[tuple[str, str]]:
        return self._native.attributes()

    def driver_waveforms(self) -> list[TimingTable]:
        return [TimingTable(w) for w in self._native.driver_waveforms()]

    def cell_names(self) -> list[str]:
        return self._native.cell_names()

    def num_cells(self) -> int:
        return self._native.num_cells()

    def cell(self, name: str) -> Cell:
        return Cell(self._native.cell(name))

    def cell_source(self, name: str) -> str:
        """Raw Liberty source text of one cell, sliced from the in-memory buffer
        (O(cell size), independent of total file size)."""
        return self._native.cell_source(name)


def parse_file(path: str | Path, **filters: Any) -> LibertyDocument:
    return LibertyDocument(_native.parse_file(str(path), **filters))


__all__ = [
    "BooleanExpression",
    "Cell",
    "Bus",
    "Bundle",
    "BusType",
    "DynamicCurrent",
    "Ff",
    "InternalPower",
    "Latch",
    "LibertyDocument",
    "LibraryIndex",
    "Pin",
    "PgCurrent",
    "SwitchingGroup",
    "TimingArc",
    "TimingTable",
    "parse_file",
]
