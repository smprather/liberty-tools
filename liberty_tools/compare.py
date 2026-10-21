"""Cross-library comparison: match timing arcs, align their grids, diff the values.

Comparing a generated Liberty against a reference one is a normal part of a PDK
flow. Doing it by hand means writing, for every pair of cells, an arc matcher,
a grid intersector, an axis-role normalizer and a differ — and the last two
fail silently: a table whose axes are swapped produces plausible but wrong
deltas.

:func:`compare` does all four, using the same axis-role information the
extraction API exposes, so a mismatch is reported rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, Sequence

if TYPE_CHECKING:
    from . import BooleanExpression, LibertyDocument, TimingArc, TimingTable

__all__ = [
    "ArcKey",
    "CompareEntry",
    "Comparison",
    "compare",
]

#: Relative tolerance used when matching axis values of two tables.
DEFAULT_TOLERANCE = 1e-9


@dataclass(frozen=True)
class ArcKey:
    """Identifies a timing arc inside a document."""

    cell: str
    pin: str
    related_pin: str | None
    timing_type: str | None
    when: str | None

    def __str__(self) -> str:
        parts = [f"{self.cell}/{self.pin}"]
        if self.related_pin:
            parts.append(f"from {self.related_pin}")
        if self.timing_type:
            parts.append(f"({self.timing_type})")
        if self.when:
            parts.append(f"when {self.when}")
        return " ".join(parts)


@dataclass
class CompareEntry:
    """One compared grid point of one table of one arc."""

    cell: str
    pin: str
    related_pin: str | None
    timing_type: str | None
    when: str | None
    table: str
    index_1: float | None
    index_2: float | None
    index_3: float | None
    #: The physical variable of each axis (``None`` when the table has no
    #: template).
    axis_1: str | None
    axis_2: str | None
    axis_3: str | None
    value_a: float | None
    value_b: float | None

    @property
    def arc(self) -> str:
        """A readable label of the arc this point belongs to."""
        key = ArcKey(
            self.cell,
            self.pin,
            self.related_pin,
            self.timing_type,
            self.when,
        )
        return str(key)

    @property
    def arc_key(self) -> ArcKey:
        """The structured identity of the arc this point belongs to."""
        return ArcKey(
            self.cell,
            self.pin,
            self.related_pin,
            self.timing_type,
            self.when,
        )

    @property
    def delta(self) -> float | None:
        """``value_a - value_b``, or ``None`` when only one side has the point."""
        if self.value_a is None or self.value_b is None:
            return None
        return self.value_a - self.value_b

    @property
    def relative_delta(self) -> float | None:
        """``delta`` relative to ``value_b`` (the reference), or ``None``."""
        delta = self.delta
        if delta is None or not self.value_b:
            return None
        return delta / self.value_b

    @property
    def matched(self) -> bool:
        """True when both documents have a value at this point."""
        return self.value_a is not None and self.value_b is not None


@dataclass
class Comparison:
    """The result of :func:`compare`."""

    #: One entry per compared grid point.
    entries: list[CompareEntry] = field(default_factory=list)
    #: Arcs that exist only in the first document.
    only_in_a: list[ArcKey] = field(default_factory=list)
    #: Arcs that exist only in the second document.
    only_in_b: list[ArcKey] = field(default_factory=list)
    #: Tables that exist only in the first document (per matched arc).
    only_in_a_tables: list[tuple[ArcKey, str]] = field(default_factory=list)
    #: Tables that exist only in the second document (per matched arc).
    only_in_b_tables: list[tuple[ArcKey, str]] = field(default_factory=list)
    #: Tables whose grids have a different number of axes:
    #: ``(arc, table, axes in the first document, axes in the second)``.
    shape_mismatches: list[tuple[ArcKey, str, int, int]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    @property
    def matched(self) -> list[CompareEntry]:
        """The entries where both documents have a value."""
        return [entry for entry in self.entries if entry.matched]

    @property
    def mismatched(self) -> list[CompareEntry]:
        """The matched entries whose values differ."""
        return [entry for entry in self.matched if entry.delta not in (0.0, -0.0)]

    def max_abs_delta(self) -> float | None:
        """The largest absolute delta over the matched entries."""
        deltas = [abs(entry.delta) for entry in self.matched if entry.delta is not None]
        return max(deltas) if deltas else None

    def summary(self) -> dict[str, Any]:
        """Counts and the worst delta, for a quick report."""
        return {
            "entries": len(self.entries),
            "matched": len(self.matched),
            "mismatched": len(self.mismatched),
            "only_in_a_arcs": len(self.only_in_a),
            "only_in_b_arcs": len(self.only_in_b),
            "shape_mismatches": len(self.shape_mismatches),
            "max_abs_delta": self.max_abs_delta(),
        }

    def to_polars(self):
        """The compared points as a :class:`polars.DataFrame`."""
        import polars as pl

        rows = [
            {
                "cell": entry.cell,
                "pin": entry.pin,
                "related_pin": entry.related_pin,
                "timing_type": entry.timing_type,
                "when": entry.when,
                "table": entry.table,
                "axis_1": entry.axis_1,
                "axis_2": entry.axis_2,
                "axis_3": entry.axis_3,
                "index_1": entry.index_1,
                "index_2": entry.index_2,
                "index_3": entry.index_3,
                "value_a": entry.value_a,
                "value_b": entry.value_b,
                "delta": entry.delta,
                "relative_delta": entry.relative_delta,
            }
            for entry in self.entries
        ]
        return pl.DataFrame(rows, infer_schema_length=None)


def compare(
    a: LibertyDocument,
    b: LibertyDocument,
    *,
    cells: Sequence[str] | None = None,
    cell: str | None = None,
    pin: str | None = None,
    table: str | None = None,
    interpolate: bool = False,
    grid: dict[str, Sequence[float]] | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> Comparison:
    """Compare two Liberty documents.

    Arcs are matched by pin, related pin and timing type; within such a group
    the ``when`` conditions are matched by logical equivalence, so ``"A & B"``
    in one library matches ``"B & A"`` in the other. A condition that is only
    *implied* by the other describes a different arc, so those arcs are
    reported as existing in only one of the documents rather than compared.

    The tables of matched arcs are matched by name, and their grids are aligned
    by *axis role* rather than by position: the load axis of one library is
    matched against the load axis of the other even when the two files store
    them in a different order. When the roles are unknown the axes are matched
    by position.

    By default only the points that exist in both grids are reported. With
    ``interpolate=True`` the second document is interpolated onto the first
    document's grid (or onto ``grid``), so that every point of the first grid
    gets a value. Points that exist in only one grid are always reported, with
    the missing side left as ``None``.

    Args:
        a: The first document (the one being validated).
        b: The second document (the reference).
        cells: Cell names to compare. Defaults to every cell of ``a``.
        cell: A single cell name to compare (a shorthand for ``cells=[cell]``).
        pin: Only compare arcs of this pin.
        table: Only compare tables with this name.
        interpolate: Interpolate ``b`` onto ``a``'s grid instead of comparing
            only the points the grids share.
        grid: The requested grid for ``interpolate=True``, as a mapping from
            an axis role (or ``"index_1"`` … ``"index_3"``) to the values to
            compare at. Defaults to the grid of ``a``.
        tolerance: Relative tolerance when matching axis values.

    Returns:
        A :class:`Comparison` with the compared points and the arcs and tables
        that exist in only one of the two documents.
    """
    names = list(cells) if cells is not None else None
    if cell is not None:
        names = [cell] if names is None else [*names, cell]
    if names is None:
        names = a.cells()

    arcs_a = _collect_arcs(a, names, pin)
    arcs_b = _collect_arcs(b, names, pin)

    result = Comparison()
    matched_pairs, only_in_a, only_in_b = _match_arcs(arcs_a, arcs_b)
    result.only_in_a = only_in_a
    result.only_in_b = only_in_b
    for key_a, key_b in matched_pairs:
        arc_a = arcs_a[key_a]
        arc_b = arcs_b[key_b]
        names_a = set(arc_a.tables())
        names_b = set(arc_b.tables())
        for name in sorted(names_a - names_b):
            if table is not None and name != table:
                continue
            result.only_in_a_tables.append((key_a, name))
        for name in sorted(names_b - names_a):
            if table is not None and name != table:
                continue
            result.only_in_b_tables.append((key_b, name))
        for table_name in sorted(names_a & names_b):
            if table is not None and table_name != table:
                continue
            table_a = arc_a.table(table_name)
            table_b = arc_b.table(table_name)
            axes_a = _axes(table_a)
            axes_b = _axes(table_b)
            if axes_a and axes_b and len(axes_a) != len(axes_b):
                # The two tables have a different number of axes: there is no
                # grid to intersect, and interpolating one onto the other
                # would invent values. Report the mismatch instead.
                result.shape_mismatches.append(
                    (key_a, table_name, len(axes_a), len(axes_b))
                )
                continue
            if not axes_a and not axes_b:
                # A CCS wave container (`output_current_*`): the data lives in
                # the nested `vector` tables, not in a grid of its own.
                vectors_a = table_a.vectors()
                vectors_b = table_b.vectors()
                if len(vectors_a) != len(vectors_b):
                    result.only_in_a_tables.append(
                        (key_a, f"{table_name} ({len(vectors_a)} waves)")
                    )
                    result.only_in_b_tables.append(
                        (key_b, f"{table_name} ({len(vectors_b)} waves)")
                    )
                for index in range(min(len(vectors_a), len(vectors_b))):
                    result.entries.extend(
                        _compare_table(
                            key_a,
                            f"{table_name}[{index}]",
                            vectors_a[index],
                            vectors_b[index],
                            interpolate=interpolate,
                            grid=grid,
                            tolerance=tolerance,
                        )
                    )
                continue
            result.entries.extend(
                _compare_table(
                    key_a,
                    table_name,
                    table_a,
                    table_b,
                    interpolate=interpolate,
                    grid=grid,
                    tolerance=tolerance,
                )
            )
    return result


def _collect_arcs(
    document: LibertyDocument,
    cells: Iterable[str],
    pin: str | None,
) -> dict[ArcKey, TimingArc]:
    """Every timing arc of the given cells, keyed by its identity."""
    arcs: dict[ArcKey, TimingArc] = {}
    for cell_name in cells:
        try:
            cell = document.cell(cell_name)
        except KeyError:
            continue
        for pin_name, arc_list in _cell_arcs(cell).items():
            if pin is not None and pin_name != pin:
                continue
            for arc in arc_list:
                key = ArcKey(
                    cell_name,
                    pin_name,
                    arc.related_pin,
                    arc.timing_type,
                    arc.when,
                )
                arcs[key] = arc
    return arcs


def _cell_arcs(cell: Any) -> dict[str, list[TimingArc]]:
    """Timing arcs of a cell, including the pins of its buses and bundles."""
    arcs: dict[str, list[TimingArc]] = {}
    for pin_name in cell.pins():
        arcs[pin_name] = list(cell.pin(pin_name).timing_arcs())
    for bus_name in cell.buses():
        bus = cell.bus(bus_name)
        arcs.setdefault(bus_name, []).extend(bus.timing_arcs())
        for pin_name in bus.pins():
            pin_obj = bus.pin(pin_name)
            arcs.setdefault(pin_name, []).extend(pin_obj.timing_arcs())
    for bundle_name in cell.bundles():
        bundle = cell.bundle(bundle_name)
        arcs.setdefault(bundle_name, []).extend(bundle.timing_arcs())
        for pin_name in bundle.pins():
            pin_obj = bundle.pin(pin_name)
            arcs.setdefault(pin_name, []).extend(pin_obj.timing_arcs())
    return arcs


def _match_arcs(
    arcs_a: dict[ArcKey, TimingArc],
    arcs_b: dict[ArcKey, TimingArc],
) -> tuple[list[tuple[ArcKey, ArcKey]], list[ArcKey], list[ArcKey]]:
    """Pair up the arcs of two documents.

    Returns the matched pairs and the arcs that exist in only one document.
    """
    pairs: list[tuple[ArcKey, ArcKey]] = []
    matched_a: set[ArcKey] = set()
    matched_b: set[ArcKey] = set()

    groups_a: dict[tuple, list[ArcKey]] = {}
    for key in arcs_a:
        groups_a.setdefault(_arc_group(key), []).append(key)
    groups_b: dict[tuple, list[ArcKey]] = {}
    for key in arcs_b:
        groups_b.setdefault(_arc_group(key), []).append(key)

    for group, keys_a in groups_a.items():
        keys_b = groups_b.get(group, [])
        if not keys_b:
            continue
        group_pairs = _match_when_conditions(keys_a, keys_b)
        for key_a, key_b in group_pairs:
            pairs.append((key_a, key_b))
            matched_a.add(key_a)
            matched_b.add(key_b)

    only_in_a = [key for key in arcs_a if key not in matched_a]
    only_in_b = [key for key in arcs_b if key not in matched_b]
    return pairs, only_in_a, only_in_b


def _arc_group(key: ArcKey) -> tuple:
    """The part of an arc's identity that does not depend on ``when``."""
    return (key.cell, key.pin, key.related_pin, key.timing_type)


def _match_when_conditions(
    keys_a: list[ArcKey],
    keys_b: list[ArcKey],
) -> list[tuple[ArcKey, ArcKey]]:
    """Pair arcs of one group by their ``when`` condition.

    Only *logically equivalent* conditions are paired. A condition that merely
    implies the other describes a different arc — comparing their values
    would report a delta between two things that do not correspond — so those
    arcs are reported as existing in only one of the documents instead.
    """
    pairs: list[tuple[ArcKey, ArcKey]] = []
    used_b: set[ArcKey] = set()

    # 1. Logically equivalent conditions.
    for key_a in keys_a:
        expr_a = _condition_expr(key_a.when)
        if expr_a is None:
            continue
        for key_b in keys_b:
            if key_b in used_b:
                continue
            expr_b = _condition_expr(key_b.when)
            if expr_b is None:
                continue
            if expr_a == expr_b:
                pairs.append((key_a, key_b))
                used_b.add(key_b)
                break

    # 2. Conditions that could not be parsed match on their exact text.
    for key_a in keys_a:
        if any(pair[0] == key_a for pair in pairs):
            continue
        if _condition_expr(key_a.when) is not None:
            continue
        for key_b in keys_b:
            if key_b in used_b:
                continue
            if _condition_expr(key_b.when) is not None:
                continue
            if key_a.when == key_b.when:
                pairs.append((key_a, key_b))
                used_b.add(key_b)
                break
    return pairs


def _condition_expr(when: str | None) -> BooleanExpression | None:
    """Parse a ``when`` condition, or None when it cannot be parsed."""
    if when is None:
        return None
    from . import BooleanExpression

    try:
        return BooleanExpression(when)
    except ValueError:
        return None


def _compare_table(
    key: ArcKey,
    table_name: str,
    table_a: TimingTable,
    table_b: TimingTable,
    *,
    interpolate: bool,
    grid: dict[str, Sequence[float]] | None,
    tolerance: float,
) -> list[CompareEntry]:
    """Compare one pair of tables."""
    roles_a = table_a.axis_roles()
    roles_b = table_b.axis_roles()
    axes_a = _axes(table_a)
    axes_b = _axes(table_b)

    # Map b's axes onto a's axes, by role when the roles are known. The
    # values are permuted with the axes: the flat list is row-major over the
    # table's own axis order.
    order_b = _axis_order(roles_a, roles_b, len(axes_a), len(axes_b))
    axes_b_ordered = [axes_b[index] for index in order_b]
    values_b = _permute_values(axes_b, order_b, table_b.values)

    entries: list[CompareEntry] = []
    if interpolate:
        points = _requested_points(table_a, grid)
        for point in points:
            entries.append(
                CompareEntry(
                    cell=key.cell,
                    pin=key.pin,
                    related_pin=key.related_pin,
                    timing_type=key.timing_type,
                    when=key.when,
                    table=table_name,
                    index_1=point[0] if len(point) > 0 else None,
                    index_2=point[1] if len(point) > 1 else None,
                    index_3=point[2] if len(point) > 2 else None,
                    axis_1=roles_a[0] if len(roles_a) > 0 else None,
                    axis_2=roles_a[1] if len(roles_a) > 1 else None,
                    axis_3=roles_a[2] if len(roles_a) > 2 else None,
                    value_a=_interpolate(axes_a, table_a.values, point),
                    value_b=_interpolate(axes_b_ordered, values_b, point),
                )
            )
        return entries

    # Points both grids have, and points only one of them has.
    for indices_a, indices_b in _grid_points(axes_a, axes_b_ordered, tolerance):
        point = tuple(axes_a[axis][index] for axis, index in enumerate(indices_a))
        value_a = _flat_value(axes_a, table_a.values, indices_a)
        value_b = (
            None
            if indices_b is None
            else _flat_value(axes_b_ordered, values_b, indices_b)
        )
        entries.append(_entry(key, table_name, roles_a, point, value_a, value_b))
    for indices_b in _points_only_in(axes_b_ordered, axes_a, tolerance):
        point = tuple(axes_b_ordered[axis][index] for axis, index in enumerate(indices_b))
        entries.append(
            _entry(
                key,
                table_name,
                roles_a,
                point,
                None,
                _flat_value(axes_b_ordered, values_b, indices_b),
            )
        )
    return entries


def _entry(
    key: ArcKey,
    table_name: str,
    roles: Sequence[str | None],
    point: Sequence[float],
    value_a: float | None,
    value_b: float | None,
) -> CompareEntry:
    """Build one comparison entry."""
    return CompareEntry(
        cell=key.cell,
        pin=key.pin,
        related_pin=key.related_pin,
        timing_type=key.timing_type,
        when=key.when,
        table=table_name,
        index_1=point[0] if len(point) > 0 else None,
        index_2=point[1] if len(point) > 1 else None,
        index_3=point[2] if len(point) > 2 else None,
        axis_1=roles[0] if len(roles) > 0 else None,
        axis_2=roles[1] if len(roles) > 1 else None,
        axis_3=roles[2] if len(roles) > 2 else None,
        value_a=value_a,
        value_b=value_b,
    )


def _axes(table: TimingTable) -> list[list[float]]:
    """The non-empty index axes of a table, in index order."""
    axes = []
    for values in (table.index_1, table.index_2, table.index_3):
        if values:
            axes.append(list(values))
    return axes


def _axis_order(
    roles_a: Sequence[str | None],
    roles_b: Sequence[str | None],
    count_a: int,
    count_b: int,
) -> list[int]:
    """Map b's axes onto a's axes, by role when the roles are known.

    Returns the indices of b's axes, in a's axis order.
    """
    if count_a != count_b:
        return list(range(count_b))
    if all(role is not None for role in roles_a[:count_a]) and all(
        role is not None for role in roles_b[:count_b]
    ):
        order: list[int] = []
        for role_a in roles_a[:count_a]:
            for index, role_b in enumerate(roles_b[:count_b]):
                if _same_axis(role_a, role_b) and index not in order:
                    order.append(index)
                    break
            else:
                return list(range(count_b))
        return order
    return list(range(count_b))


def _same_axis(role_a: str | None, role_b: str | None) -> bool:
    """Do two axis variable names mean the same physical quantity?

    Uses the same synonym table as ``TimingTable.lookup``, so that a load axis
    named ``output_capacitance`` matches one named
    ``total_output_net_capacitance``.
    """
    if role_a is None or role_b is None:
        return False
    if role_a == role_b:
        return True
    from . import _axis_role_matches

    return _axis_role_matches(role_b, role_a)


def _match_value(values: Sequence[float], target: float, tolerance: float) -> int | None:
    """Index of the value matching ``target`` within the tolerance."""
    for index, value in enumerate(values):
        if abs(value - target) <= tolerance * max(abs(value), abs(target), 1.0):
            return index
    return None


def _grid_points(
    axes_a: Sequence[Sequence[float]],
    axes_b: Sequence[Sequence[float]],
    tolerance: float,
) -> list[tuple[tuple[int, ...], tuple[int, ...] | None]]:
    """Every point of a's grid, with b's position when b has that point."""
    if len(axes_a) != len(axes_b):
        return []
    per_axis: list[list[tuple[int, int | None]]] = []
    for axis_a, axis_b in zip(axes_a, axes_b):
        per_axis.append(
            [
                (index_a, _match_value(axis_b, value_a, tolerance))
                for index_a, value_a in enumerate(axis_a)
            ]
        )
    out: list[tuple[tuple[int, ...], tuple[int, ...] | None]] = []
    _cartesian_indices(per_axis, 0, [], [], out)
    return out


def _points_only_in(
    axes: Sequence[Sequence[float]],
    other: Sequence[Sequence[float]],
    tolerance: float,
) -> list[tuple[int, ...]]:
    """The positions of the grid points only ``axes`` has."""
    if len(axes) != len(other):
        return []
    per_axis: list[list[tuple[int, int | None]]] = []
    for axis, other_axis in zip(axes, other):
        per_axis.append(
            [
                (index, _match_value(other_axis, value, tolerance))
                for index, value in enumerate(axis)
            ]
        )
    out: list[tuple[tuple[int, ...], tuple[int, ...] | None]] = []
    _cartesian_indices(per_axis, 0, [], [], out)
    return [indices for indices, other_indices in out if other_indices is None]


def _cartesian_indices(
    per_axis: Sequence[Sequence[tuple[int, int | None]]],
    depth: int,
    current: list[int],
    other: list[int],
    out: list[tuple[tuple[int, ...], tuple[int, ...] | None]],
    matched: bool = True,
) -> None:
    """Every combination of the per-axis positions.

    ``other`` collects the matching positions in the other grid. As soon as an
    axis has no match the whole point is marked as absent from the other grid.
    """
    if depth == len(per_axis):
        out.append((tuple(current), tuple(other) if matched else None))
        return
    for index, other_index in per_axis[depth]:
        current.append(index)
        if other_index is None:
            _cartesian_indices(per_axis, depth + 1, current, other, out, False)
        else:
            other.append(other_index)
            _cartesian_indices(per_axis, depth + 1, current, other, out, matched)
            other.pop()
        current.pop()


def _permute_values(
    axes: Sequence[Sequence[float]],
    order: Sequence[int],
    values: Sequence[float],
) -> list[float]:
    """Reorder a table's flat values to a new axis order.

    The flat list is row-major over the table's own axis order, so permuting
    the axes permutes the values with them.
    """
    if list(order) == list(range(len(axes))):
        return list(values)
    out: list[float] = []
    original_indices = [0] * len(axes)
    for new_indices in _all_index_combinations(
        [len(axes[axis]) for axis in order]
    ):
        for position, axis_index in enumerate(order):
            original_indices[axis_index] = new_indices[position]
        flat = 0
        for position in range(len(axes)):
            flat = flat * len(axes[position]) + original_indices[position]
        out.append(values[flat] if flat < len(values) else float("nan"))
    return out


def _all_index_combinations(sizes: Sequence[int]) -> list[tuple[int, ...]]:
    """Every combination of index positions for the given axis sizes."""
    combinations: list[tuple[int, ...]] = [()]
    for size in sizes:
        combinations = [
            combination + (index,)
            for combination in combinations
            for index in range(size)
        ]
    return combinations


def _flat_value(
    axes: Sequence[Sequence[float]],
    values: Sequence[float],
    indices: Sequence[int],
) -> float | None:
    """The table value at a grid position."""
    flat = 0
    for axis, index in zip(axes, indices):
        flat = flat * len(axis) + index
    if flat >= len(values):
        return None
    return values[flat]


def _requested_points(
    table: TimingTable,
    grid: dict[str, Sequence[float]] | None,
) -> list[tuple[float, ...]]:
    """The grid points to compare at, in a's axis order."""
    axes = _axes(table)
    roles = table.axis_roles()
    if not grid:
        points: list[tuple[float, ...]] = []
        _cartesian_values(axes, 0, [], points)
        return points
    per_axis: list[list[float]] = []
    used: set[str] = set()
    for index, axis in enumerate(axes):
        requested = None
        for key, values in grid.items():
            if key == f"index_{index + 1}":
                requested = values
                used.add(key)
                break
            role = roles[index] if index < len(roles) else None
            if role is not None and _same_axis(role, key):
                requested = values
                used.add(key)
                break
        per_axis.append([float(value) for value in (requested if requested is not None else axis)])
    unknown = [key for key in grid if key not in used]
    if unknown:
        raise ValueError(
            f"the requested grid has no axis named {unknown[0]!r}; "
            f"the table's axes are {roles[: len(axes)]}"
        )
    points = []
    _cartesian_values(per_axis, 0, [], points)
    return points


def _cartesian_values(
    per_axis: Sequence[Sequence[float]],
    depth: int,
    current: list[float],
    out: list[tuple[float, ...]],
) -> None:
    """Every combination of the per-axis values."""
    if depth == len(per_axis):
        out.append(tuple(current))
        return
    for value in per_axis[depth]:
        current.append(value)
        _cartesian_values(per_axis, depth + 1, current, out)
        current.pop()


def _interpolate(
    axes: Sequence[Sequence[float]],
    values: Sequence[float],
    point: Sequence[float],
) -> float | None:
    """Interpolate the table at a point, or None when it is outside the grid."""
    if not axes:
        return values[0] if values else None
    if len(axes) != len(point):
        # The point has a different number of coordinates than the table has
        # axes: interpolating would silently drop a dimension.
        return None
    brackets: list[tuple[int, int, float]] = []
    for axis, coordinate in zip(axes, point):
        bracket = _bracket(axis, coordinate)
        if bracket is None:
            return None
        brackets.append(bracket)
    total = 0.0
    for corner in _corners(brackets):
        flat = 0
        weight = 1.0
        for axis, (low, high, ratio), position in zip(axes, brackets, corner):
            flat = flat * len(axis) + position
            if low == high:
                factor = 1.0
            elif position == low:
                factor = 1.0 - ratio
            else:
                factor = ratio
            weight *= factor
        if flat < len(values):
            total += values[flat] * weight
    return total


def _bracket(axis: Sequence[float], coordinate: float) -> tuple[int, int, float] | None:
    """The bracketing positions of a coordinate and the interpolation ratio."""
    if len(axis) == 1:
        return (0, 0, 0.0) if abs(axis[0] - coordinate) < 1e-12 else None
    for index in range(len(axis) - 1):
        low = axis[index]
        high = axis[index + 1]
        if coordinate >= low and coordinate <= high:
            span = high - low
            ratio = 0.0 if span == 0.0 else (coordinate - low) / span
            return (index, index + 1, ratio)
    return None


def _corners(brackets: Sequence[tuple[int, int, float]]) -> list[tuple[int, ...]]:
    """Every corner of the interpolation box."""
    corners: list[tuple[int, ...]] = [()]
    for low, high, _ in brackets:
        choices = (low,) if low == high else (low, high)
        corners = [corner + (choice,) for corner in corners for choice in choices]
    return corners
