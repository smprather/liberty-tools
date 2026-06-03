"""Data-access layer for the Liberty viewer.

Wraps a parsed ``LibertyDocument`` and exposes exactly what the HTTP API needs:
a lazily-built per-cell tree (metadata only, no table values) plus resolution of
a single table leaf to its axes/values. Keeping value extraction per-leaf is what
makes the design tolerant of very large libraries — the browser only ever pulls
one table at a time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import liberty_tools as lt

# Physical quantity ("kind") of each template axis variable and of each table's
# value, so axes/values can be labelled "<name> (<unit>)".
_VAR_KIND = {
    "input_net_transition": "time",
    "constrained_pin_transition": "time",
    "related_pin_transition": "time",
    "input_transition_time": "time",
    "time": "time",
    "input_noise_width": "time",
    "total_output_net_capacitance": "cap",
    "output_net_capacitance": "cap",
    "input_voltage": "voltage",
    "output_voltage": "voltage",
    "normalized_voltage": "voltage",
    "input_noise_height": "voltage",
}
_VALUE_KIND = {
    "cell_rise": "time",
    "cell_fall": "time",
    "rise_transition": "time",
    "fall_transition": "time",
    "rise_constraint": "time",
    "fall_constraint": "time",
    "retaining_rise": "time",
    "retaining_fall": "time",
    "retain_rise_slew": "time",
    "retain_fall_slew": "time",
    "cell_degradation": "time",
    "output_current_rise": "current",
    "output_current_fall": "current",
    "rise_power": "energy",
    "fall_power": "energy",
    "receiver_capacitance1_rise": "cap",
    "receiver_capacitance1_fall": "cap",
    "receiver_capacitance2_rise": "cap",
    "receiver_capacitance2_fall": "cap",
}
_SI_PREFIX = {-18: "a", -15: "f", -12: "p", -9: "n", -6: "u", -3: "m", 0: ""}

# Short display aliases for axis variable names (labels only; raw names are kept
# in the parser/API).
_ALIAS = {
    "total_output_net_capacitance": "load",
    "input_net_transition": "slew",
}


# Liberty attributes whose value is a boolean expression — displayed in the
# canonical (minimized sum-of-products) format rather than verbatim.
_BOOL_ATTRS = frozenset(
    {
        "function",
        "three_state",
        "power_down_function",
        "when",
        "sdf_cond",
        "input_switching_condition",
        "output_switching_condition",
        "next_state",
        "clocked_on",
        "clocked_on_also",
        "clear",
        "preset",
        "enable",
        "data_in",
    }
)


def _fmt_bool(raw: str | None) -> str | None:
    """Render a Liberty boolean string in the canonical viewer format (minimized
    sum-of-products via :class:`liberty_tools.BooleanExpression`). Falls back to
    the verbatim text if it doesn't parse as a boolean expression."""
    if not raw:
        return raw
    try:
        return str(lt.BooleanExpression(raw))
    except ValueError:
        return raw


def _fmt_attr_rows(rows: list[tuple[str, str]]) -> list[list[str]]:
    """Format a raw ``(name, value)`` attribute list, canonicalizing the values
    of boolean-valued attributes (function, three_state, …)."""
    return [[k, _fmt_bool(v) if k in _BOOL_ATTRS else v] for k, v in rows]


def _propagate_src(node: dict[str, Any], parent_src: dict[str, str]) -> None:
    """Stamp every node with a source scope (cell/pin/bus/bundle group): nodes
    that don't define their own inherit the nearest named ancestor's."""
    src = node.get("src") or parent_src
    node["src"] = src
    for child in node.get("children", []):
        _propagate_src(child, src)


def _meta_attrs(meta: dict[str, Any]) -> list[list[str]]:
    """Turn a node's scalar meta dict into ordered ``[name, value]`` rows,
    dropping empty entries — for nodes (arc/power/bus/bundle) that have no raw
    Liberty attribute list of their own. Boolean-valued entries are rendered in
    the canonical format."""
    out: list[list[str]] = []
    for k, v in meta.items():
        if v in (None, ""):
            continue
        out.append([k, _fmt_bool(str(v)) if k in _BOOL_ATTRS else str(v)])
    return out


def _bare_unit(raw: str | None) -> str | None:
    """`"1ps"` -> `"ps"`, `"1mA"` -> `"mA"`; strip a leading numeric magnitude."""
    if not raw:
        return None
    i = 0
    while i < len(raw) and (raw[i].isdigit() or raw[i] in ".eE+-"):
        i += 1
    return raw[i:].strip() or None


def _ndim(index_1: list[float], index_2: list[float], index_3: list[float]) -> int:
    if index_3:
        return 3
    if index_2:
        return 2
    if index_1:
        return 1
    return 0


def _t_peak(time: list[float], values: list[float]) -> float | None:
    """Time at which ``abs(value)`` is largest — the scalar shown in each CCS
    grid cell."""
    if not values:
        return None
    ipk = max(range(len(values)), key=lambda k: abs(values[k]))
    return time[ipk] if ipk < len(time) else None


def _reshape(values: list[float], n1: int, n2: int, n3: int, ndim: int) -> Any:
    """Reshape the parser's row-major flat ``values`` into nested lists.

    Layout is row-major over (index_1 x index_2 x index_3); see CLAUDE.md.
    """
    if ndim <= 1:
        return list(values)
    if ndim == 2:
        return [values[i * n2 : (i + 1) * n2] for i in range(n1)]
    plane = n2 * n3
    return [
        [values[i * plane + j * n3 : i * plane + (j + 1) * n3] for j in range(n2)]
        for i in range(n1)
    ]


@dataclass
class LibertyData:
    path: str
    doc: lt.LibraryIndex
    templates: dict[str, list[str | None]] = field(default_factory=dict)
    unit_by_kind: dict[str, str | None] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "LibertyData":
        # LibraryIndex parses only the header up front and indexes cell byte
        # ranges; cells are parsed on demand (one at a time) when the tree/table
        # endpoints ask for them. This keeps open time ~seconds on multi-GB libs
        # instead of a full parse into RAM.
        doc = lt.LibraryIndex.open(path)
        energy = doc.energy_unit_joules()
        energy_unit = None
        if energy:
            energy_unit = _SI_PREFIX.get(round(math.log10(energy)), "") + "J"
        unit_by_kind = {
            "time": _bare_unit(doc.time_unit),
            "cap": doc.capacitive_load_unit,
            "current": _bare_unit(doc.current_unit),
            "voltage": _bare_unit(doc.voltage_unit),
            "energy": energy_unit,
        }
        return cls(path=path, doc=doc, templates=doc.templates(), unit_by_kind=unit_by_kind)

    def _with_unit(self, name: str, kind: str | None) -> str:
        unit = self.unit_by_kind.get(kind) if kind else None
        return f"{name} ({unit})" if unit else name

    def _axis_labels(self, template: str | None, table: str) -> dict[str, str]:
        """Per-axis ("<variable> (<unit>)") and value labels for a table."""
        vars_ = self.templates.get(template or "", [None, None, None])
        labels = {}
        for k, axis in enumerate(("index_1", "index_2", "index_3")):
            var = vars_[k] if k < len(vars_) else None
            labels[axis] = (
                self._with_unit(_ALIAS.get(var, var), _VAR_KIND.get(var or "")) if var else axis
            )
        labels["value"] = self._with_unit(table, _VALUE_KIND.get(table))
        return labels

    # -- library-level metadata ------------------------------------------------
    def meta(self) -> dict[str, Any]:
        return {
            "library_name": self.doc.library_name,
            "path": self.path,
            "voltage_unit": self.doc.voltage_unit,
            "current_unit": self.doc.current_unit,
            "time_unit": self.doc.time_unit,
            "energy_unit_joules": self.doc.energy_unit_joules(),
            "leakage_power_unit": next(
                (v for k, v in self.doc.attributes() if k == "leakage_power_unit"), None
            ),
            "num_cells": self.doc.num_cells(),
            "attributes": [[k, str(v)] for k, v in self.doc.attributes()],
            "driver_waveforms": self._driver_waveforms(),
        }

    def _driver_waveforms(self) -> list[dict[str, Any]]:
        """``normalized_driver_waveform`` tables for the library view.

        Each is a 2-D table: index_1 = input slew, index_2 = normalized voltage
        (0..1), values = time. Reshaped to ``time[slew][voltage]`` so the client
        can draw one voltage-vs-time curve per slew.
        """
        t = self.unit_by_kind.get("time")
        tu = f" ({t})" if t else ""
        out = []
        for i, w in enumerate(self.doc.driver_waveforms()):
            slew = list(w.index_1)
            volt = list(w.index_2)
            out.append(
                {
                    "name": w.name or f"waveform {i + 1}",
                    "slew": slew,
                    "voltage": volt,
                    "time": _reshape(list(w.values), len(slew), len(volt), 0, 2),
                    "labels": {
                        "slew": f"slew{tu}",
                        "voltage": "normalized voltage",
                        "time": f"time{tu}",
                    },
                }
            )
        return out

    def cell_names(
        self, filter_: str | None = None, offset: int = 0, limit: int = 500
    ) -> dict[str, Any]:
        names = self.doc.cell_names()
        if filter_:
            f = filter_.lower()
            names = [n for n in names if f in n.lower()]
        return {"total": len(names), "cells": names[offset : offset + limit]}

    # -- raw cell source (byte-slice from the in-memory buffer) ----------------
    def cell_source(self, cell_name: str) -> dict[str, Any]:
        """Raw Liberty text of one cell. Capped so the largest CCS cells can't
        bog down the browser; cost is O(cell size), not file size."""
        text = self.doc.cell_source(cell_name)
        limit = 1_000_000
        return {
            "cell": cell_name,
            "text": text[:limit],
            "length": len(text),
            "truncated": len(text) > limit,
        }

    # -- per-cell tree (metadata only, no values) ------------------------------
    def cell_tree(self, cell_name: str) -> dict[str, Any]:
        cell = self.doc.cell(cell_name)
        node: dict[str, Any] = {
            "id": f"cell:{cell_name}",
            "label": cell_name,
            "type": "cell",
            "meta": {"area": cell.area},
            "attributes": _fmt_attr_rows(cell.attributes()),
            "src": {"kind": "cell", "name": cell_name},
            "children": [],
        }
        for pin_name in cell.pins():
            node["children"].append(self._pin_node(cell.pin(pin_name), container=""))
        for bus_name in cell.buses():
            bus = cell.bus(bus_name)
            bnode: dict[str, Any] = {
                "id": f"bus:{bus_name}",
                "label": f"{bus_name} (bus)",
                "type": "bus",
                "meta": {"direction": bus.direction, "bus_type": bus.bus_type},
                "attributes": _meta_attrs({"direction": bus.direction, "bus_type": bus.bus_type}),
                "src": {"kind": "bus", "name": bus_name},
                "children": self._arc_nodes(list(bus.timing_arcs()), "bus", bus_name, ""),
            }
            for pin_name in bus.pins():
                bnode["children"].append(self._pin_node(bus.pin(pin_name), container=f"bus:{bus_name}"))
            node["children"].append(bnode)
        for bundle_name in cell.bundles():
            bundle = cell.bundle(bundle_name)
            unode: dict[str, Any] = {
                "id": f"bundle:{bundle_name}",
                "label": f"{bundle_name} (bundle)",
                "type": "bundle",
                "meta": {"direction": bundle.direction, "members": bundle.members},
                "attributes": _meta_attrs(
                    {"direction": bundle.direction, "members": ", ".join(bundle.members)}
                ),
                "src": {"kind": "bundle", "name": bundle_name},
                "children": self._arc_nodes(list(bundle.timing_arcs()), "bundle", bundle_name, ""),
            }
            for pin_name in bundle.pins():
                unode["children"].append(self._pin_node(bundle.pin(pin_name), container=f"bundle:{bundle_name}"))
            node["children"].append(unode)
        leak = self._leakage_node(cell, cell_name)
        if leak:
            node["children"].append(leak)
        node["children"].extend(self._ccsp_nodes(cell))
        # Each node carries the source scope (cell/pin/bus/bundle group) to show
        # in the bottom pane; descendants inherit their nearest named ancestor.
        _propagate_src(node, node["src"])
        return node

    def _leakage_node(self, cell: lt.Cell, cell_name: str) -> dict[str, Any] | None:
        """`leakage_power` as a single when-condition × power-rail table node.

        Rows are when-conditions (canonical form; the no-`when` default is
        `(default)`); columns are the `related_pg_pin` rails (or one `value`
        column when no rail is given). Cells are the leakage values."""
        lps = cell.leakage_powers()
        if not lps:
            return None
        has_pg = any(lp.related_pg_pin for lp in lps)
        cols = (
            sorted({lp.related_pg_pin for lp in lps if lp.related_pg_pin})
            if has_pg
            else ["value"]
        )
        rows: dict[str, dict[str, float | None]] = {}
        order: list[str] = []
        for lp in lps:
            key = _fmt_bool(lp.when) if lp.when else "(default)"
            if key not in rows:
                rows[key] = {}
                order.append(key)
            rows[key][lp.related_pg_pin if has_pg else "value"] = lp.value
        return {
            "id": f"cell:{cell_name}|leakage",
            "label": "leakage_power",
            "type": "leakage",
            "leakage": {
                "pg_pins": cols,
                "rows": [{"when": k, "values": rows[k]} for k in order],
            },
            "children": [],
        }

    def _ccsp_nodes(self, cell: lt.Cell) -> list[dict[str, Any]]:
        """CCS-power (`dynamic_current`) subtree: dynamic_current -> switching_group
        -> pg_current leaf (a slew x cap grid of current-vs-time waves)."""
        out: list[dict[str, Any]] = []
        for dci, dc in enumerate(cell.dynamic_currents()):
            io = " -> ".join(x for x in (dc.related_inputs, dc.related_outputs) if x)
            dnode: dict[str, Any] = {
                "id": f"ccsp:{dci}",
                "label": f"dynamic_current (CCSP){' [' + io + ']' if io else ''}",
                "type": "dynamic",
                "attributes": _meta_attrs(
                    {
                        "related_inputs": dc.related_inputs,
                        "related_outputs": dc.related_outputs,
                        "when": dc.when,
                    }
                ),
                "children": [],
            }
            for sgi, sg in enumerate(dc.switching_groups()):
                ic, oc = sg.input_switching_condition, sg.output_switching_condition
                snode: dict[str, Any] = {
                    "id": f"ccsp:{dci}:{sgi}",
                    "label": f"in {_fmt_bool(ic) or '?'} / out {_fmt_bool(oc) or '?'}",
                    "type": "switchgroup",
                    "attributes": _meta_attrs(
                        {
                            "input_switching_condition": ic,
                            "output_switching_condition": oc,
                        }
                    ),
                    "children": [],
                }
                for pgi, pg in enumerate(sg.pg_currents()):
                    pin = pg.pg_pin or f"pg{pgi}"
                    leaf = self._table_leaf("ccsp", pin, f"{dci}:{sgi}", pgi, pin)
                    leaf["label"] = f"pg_current {pin}"
                    snode["children"].append(leaf)
                dnode["children"].append(snode)
            out.append(dnode)
        return out

    def _wrap_when(
        self, when: str | None, node_id: str, children: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """If a ``when`` condition exists, nest ``children`` under an extra
        ``when`` tree level; otherwise return them unchanged."""
        if not when:
            return children
        return [
            {
                "id": f"{node_id}|when",
                "label": f"when: {_fmt_bool(when)}",
                "type": "when",
                "attributes": [["when", when]],
                "children": children,
            }
        ]

    def _pin_node(self, pin: lt.Pin, container: str) -> dict[str, Any]:
        children: list[dict[str, Any]] = []
        children.extend(self._arc_nodes(list(pin.timing_arcs()), "pin", pin.name, container))
        children.extend(self._power_nodes(pin, container))
        return {
            "id": f"{container}|pin:{pin.name}",
            "label": f"{pin.name}",
            "type": "pin",
            "meta": {"direction": pin.direction, "function": _fmt_bool(pin.function)},
            "attributes": _fmt_attr_rows(pin.attributes()),
            "src": {"kind": "pin", "name": pin.name},
            "children": children,
        }

    def _power_nodes(self, pin: lt.Pin, container: str) -> list[dict[str, Any]]:
        """Build `internal_power` tree nodes. Groups that share the same
        (related_pin, when) but differ only by `related_pg_pin` collapse under
        one node with a pg-pin sub-level (so e.g. the VDD/VSS pair of one
        condition reads as one entry with two power rails)."""
        groups: dict[tuple[str, str], list[tuple[int, lt.InternalPower]]] = {}
        order: list[tuple[str, str]] = []
        for i, grp in enumerate(pin.internal_power()):
            key = (grp.related_pin or "", grp.when or "")
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append((i, grp))
        return [
            self._power_group_node(pin, container, groups[key]) for key in order
        ]

    def _power_group_node(
        self,
        pin: lt.Pin,
        container: str,
        members: list[tuple[int, lt.InternalPower]],
    ) -> dict[str, Any]:
        first = members[0][1]
        related_pin, when = first.related_pin, first.when

        def tables_for(idx: int, grp: lt.InternalPower) -> list[dict[str, Any]]:
            return [
                self._table_leaf(container, pin.name, "power", idx, t)
                for t in grp.tables()
            ]

        # Lone group: flat node with the pg pin in the label (unchanged layout).
        if len(members) == 1:
            idx, grp = members[0]
            arrow = f"{grp.related_pin}→{pin.name}" if grp.related_pin else pin.name
            label = f"internal_power {arrow}"
            if grp.related_pg_pin:
                label += f" pg={grp.related_pg_pin}"
            pid = f"{container}|pin:{pin.name}|power:{idx}"
            meta = {
                "related_pin": grp.related_pin,
                "related_pg_pin": grp.related_pg_pin,
                "when": grp.when,
            }
            return {
                "id": pid,
                "label": label,
                "type": "powergrp",
                "meta": meta,
                "attributes": _meta_attrs(meta),
                "children": self._wrap_when(grp.when, pid, tables_for(idx, grp)),
            }

        # Several groups differing only by pg pin: one parent, a pg-pin level
        # (nested under the `when` level when a condition is present).
        gid = f"{container}|pin:{pin.name}|powergrp:{related_pin or ''}:{when or ''}"
        pg_nodes = []
        for idx, grp in members:
            pg = grp.related_pg_pin or f"pg{idx}"
            pg_nodes.append(
                {
                    "id": f"{gid}|power:{idx}",
                    "label": f"pg={pg}",
                    "type": "pgpin",
                    "meta": {"related_pg_pin": grp.related_pg_pin},
                    "attributes": _meta_attrs({"related_pg_pin": grp.related_pg_pin}),
                    "children": tables_for(idx, grp),
                }
            )
        arrow = f"{related_pin}→{pin.name}" if related_pin else pin.name
        label = f"internal_power {arrow}"
        meta = {"related_pin": related_pin, "when": when}
        return {
            "id": gid,
            "label": label,
            "type": "powergrp",
            "meta": meta,
            "attributes": _meta_attrs(meta),
            "children": self._wrap_when(when, gid, pg_nodes),
        }

    def _arc_nodes(
        self, arcs: list[lt.TimingArc], scope: str, owner: str, container: str
    ) -> list[dict[str, Any]]:
        """Build timing-arc tree nodes, collapsing arcs that share the same
        identity (``related_pin`` + ``timing_type``) under one node with each
        ``when`` as a sub-level. Arcs that differ only by ``when`` are the same
        physical arc split by state, so they read better grouped together."""
        groups: dict[tuple[str, str], list[tuple[int, lt.TimingArc]]] = {}
        order: list[tuple[str, str]] = []
        for i, arc in enumerate(arcs):
            key = (arc.related_pin or "", arc.timing_type or "")
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append((i, arc))
        return [self._arc_group_node(groups[key], scope, owner, container) for key in order]

    def _arc_group_node(
        self,
        members: list[tuple[int, lt.TimingArc]],
        scope: str,
        owner: str,
        container: str,
    ) -> dict[str, Any]:
        first = members[0][1]
        # `timing <related>→<owner> <type>`, e.g. `timing a→y combinational`.
        arrow = f"{first.related_pin}→{owner}" if first.related_pin else owner
        parts = [arrow]
        if first.timing_type:
            parts.append(first.timing_type)
        label = "timing " + " ".join(parts)
        # For bus/bundle direct arcs, the "pin" used by /api/table is the owner name.
        base = container if scope == "pin" else f"{scope}:{owner}"

        def tables_for(idx: int, arc: lt.TimingArc) -> list[dict[str, Any]]:
            return [self._table_leaf(base, owner, "timing", idx, t) for t in arc.tables()]

        # Lone unconditional arc: tables hang straight off the arc node.
        if len(members) == 1 and not first.when:
            idx, arc = members[0]
            arc_id = f"{container}|{scope}:{owner}|timing:{idx}"
            return {
                "id": arc_id,
                "label": label,
                "type": "arc",
                "meta": {"related_pin": first.related_pin, "timing_type": first.timing_type},
                "attributes": _meta_attrs(
                    {"related_pin": first.related_pin, "timing_type": first.timing_type}
                ),
                "children": tables_for(idx, arc),
            }

        # Otherwise one arc node, each member's `when` a sub-level beneath it.
        group_id = f"{container}|{scope}:{owner}|timinggrp:{first.related_pin or ''}:{first.timing_type or ''}"
        when_children = []
        for idx, arc in members:
            arc_id = f"{container}|{scope}:{owner}|timing:{idx}"
            when_children.append(
                {
                    "id": f"{arc_id}|when",
                    "label": f"when: {_fmt_bool(arc.when)}" if arc.when else "when: (unconditional)",
                    "type": "when",
                    "attributes": _meta_attrs(
                        {
                            "when": arc.when,
                            "related_pin": arc.related_pin,
                            "timing_type": arc.timing_type,
                        }
                    ),
                    "children": tables_for(idx, arc),
                }
            )
        return {
            "id": group_id,
            "label": label,
            "type": "arc",
            "meta": {"related_pin": first.related_pin, "timing_type": first.timing_type},
            "attributes": _meta_attrs(
                {"related_pin": first.related_pin, "timing_type": first.timing_type}
            ),
            "children": when_children,
        }

    def _table_leaf(
        self, container: str, pin: str, group: str, arc_index: int, table: str
    ) -> dict[str, Any]:
        return {
            "id": f"{container}|pin:{pin}|{group}:{arc_index}|table:{table}",
            "label": table,
            "type": "table",
            "leaf": True,
            "ref": {
                "container": container,
                "pin": pin,
                "group": group,
                "arc_index": arc_index,
                "table": table,
            },
        }

    # -- resolve one table leaf to axes + values -------------------------------
    def table(
        self,
        cell: str,
        pin: str,
        group: str,
        arc_index: int,
        table: str,
        container: str = "",
    ) -> dict[str, Any]:
        cell_obj = self.doc.cell(cell)
        if container == "ccsp":
            # group encodes "<dynamic_current idx>:<switching_group idx>",
            # arc_index = pg_current idx, table/pin = pg pin name.
            dci, sgi = (int(x) for x in group.split(":"))
            pg = (
                cell_obj.dynamic_currents()[dci]
                .switching_groups()[sgi]
                .pg_currents()[arc_index]
            )
            return self._ccs_payload(table, pg.vectors())
        pin_obj = self._resolve_pin_owner(cell_obj, container, pin)
        if group == "timing":
            arcs = pin_obj.timing_arcs()
            tbl = arcs[arc_index].table(table)
        elif group == "power":
            grps = pin_obj.internal_power()
            tbl = grps[arc_index].table(table)
        else:
            raise ValueError(f"unknown group {group!r}")

        vectors = tbl.vectors()
        if vectors:
            return self._ccs_payload(table, vectors)

        i1, i2, i3 = tbl.index_1, tbl.index_2, tbl.index_3
        ndim = _ndim(i1, i2, i3)
        n1, n2, n3 = len(i1) or 1, len(i2) or 1, len(i3) or 1
        return {
            "table": table,
            "kind": "table",
            "ndim": ndim,
            "index_1": i1,
            "index_2": i2,
            "index_3": i3,
            "values": _reshape(tbl.values, n1, n2, n3, ndim),
            "scalar": tbl.values[0] if ndim == 0 and tbl.values else None,
            "labels": self._axis_labels(tbl.template, table),
        }

    def _ccs_payload(self, table: str, vectors: list) -> dict[str, Any]:
        """CCS group -> slew x cap grid of current-vs-time waves.

        Each `vector` is one point in (input slew, output cap) space holding a
        full current(time) wave. The grid cell summary is the 95%-decay time.
        """
        slews = sorted({v.index_1[0] for v in vectors if v.index_1})
        caps = sorted({v.index_2[0] for v in vectors if v.index_2})
        si = {s: i for i, s in enumerate(slews)}
        ci = {c: j for j, c in enumerate(caps)}
        grid: list[list[Any]] = [[None] * len(caps) for _ in slews]
        for v in vectors:
            if not (v.index_1 and v.index_2):
                continue
            time, current = v.index_3, v.values
            grid[si[v.index_1[0]]][ci[v.index_2[0]]] = {
                "time": time,
                "current": current,
                "reference_time": v.reference_time,
                "t_peak": _t_peak(time, current),
            }
        template = vectors[0].template if vectors else None
        vars_ = self.templates.get(template or "", [None, None, None])
        labels = {
            "index_1": self._with_unit(_ALIAS.get(vars_[0], vars_[0]), _VAR_KIND.get(vars_[0] or "")) if vars_[0] else "slew",
            "index_2": self._with_unit(_ALIAS.get(vars_[1], vars_[1]), _VAR_KIND.get(vars_[1] or "")) if len(vars_) > 1 and vars_[1] else "load",
            "time": self._with_unit(vars_[2] if len(vars_) > 2 and vars_[2] else "time", "time"),
            "current": self._with_unit("current", "current"),
        }
        return {
            "table": table,
            "kind": "ccs",
            "index_1": slews,
            "index_2": caps,
            "grid": grid,
            "labels": labels,
        }

    def _resolve_pin_owner(self, cell_obj: lt.Cell, container: str, pin: str):
        """Return the object whose timing_arcs/internal_power we read.

        ``container`` is ""/"bus:NAME"/"bundle:NAME". For a bus/bundle *direct*
        arc the leaf encodes container="bus:NAME" and pin=NAME, so we return the
        bus/bundle itself (it exposes timing_arcs)."""
        if not container:
            return cell_obj.pin(pin)
        kind, name = container.split(":", 1)
        owner = cell_obj.bus(name) if kind == "bus" else cell_obj.bundle(name)
        if pin == name:
            return owner  # direct bus/bundle arc
        return owner.pin(pin)
