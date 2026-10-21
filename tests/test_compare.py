"""Cross-library comparison (issue #4)."""

from pathlib import Path

import pytest

import liberty_tools as lt

# The two libraries below store the same physical axes in opposite order:
# `ours` puts the load on index_1, `theirs` puts the transition there.
OURS = """
library (ours) {
  time_unit : "1ns";
  capacitive_load_unit (1, pf);
  lu_table_template (delay_template) {
    variable_1 : total_output_net_capacitance;
    variable_2 : input_net_transition;
  }
  cell (u1) {
    area : 1.0;
    pin (z) {
      direction : output;
      timing () {
        related_pin : "a";
        cell_rise (delay_template) {
          index_1 ("0.1, 0.2");
          index_2 ("1, 2");
          values ("10, 20, 30, 40");
        }
      }
    }
    pin (a) {
      direction : input;
    }
  }
}
"""

THEIRS = """
library (theirs) {
  time_unit : "1ns";
  capacitive_load_unit (1, pf);
  lu_table_template (delay_template) {
    variable_1 : input_net_transition;
    variable_2 : total_output_net_capacitance;
  }
  cell (u1) {
    area : 1.0;
    pin (z) {
      direction : output;
      timing () {
        related_pin : "a";
        cell_rise (delay_template) {
          index_1 ("1, 2");
          index_2 ("0.1, 0.2");
          values ("10, 35, 20, 40");
        }
      }
    }
    pin (a) {
      direction : input;
    }
  }
}
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def docs(tmp_path: Path) -> tuple[lt.LibertyDocument, lt.LibertyDocument]:
    ours = lt.parse_file(_write(tmp_path, "ours.lib", OURS))
    theirs = lt.parse_file(_write(tmp_path, "theirs.lib", THEIRS))
    return ours, theirs


def test_matched_arcs_are_compared_point_by_point(docs):
    ours, theirs = docs

    diff = lt.compare(ours, theirs, cell="u1")

    assert len(diff.entries) == 4
    assert all(entry.matched for entry in diff.entries)
    assert diff.only_in_a == []
    assert diff.only_in_b == []


def test_grids_are_aligned_by_axis_role_not_by_position(docs):
    ours, theirs = docs

    diff = lt.compare(ours, theirs, cell="u1")
    by_point = {(entry.index_1, entry.index_2): entry for entry in diff.entries}

    # Load 0.1 / transition 1 is the same point in both libraries even though
    # it sits at a different grid position in each of them.
    entry = by_point[(0.1, 1.0)]
    assert entry.value_a == 10.0
    assert entry.value_b == 10.0
    assert entry.delta == 0.0

    entry = by_point[(0.2, 2.0)]
    assert entry.value_a == 40.0
    assert entry.value_b == 40.0

    # The values that really differ are reported.
    entry = by_point[(0.2, 1.0)]
    assert entry.value_a == 30.0
    assert entry.value_b == 35.0
    assert entry.delta == -5.0
    assert entry.relative_delta == pytest.approx(-1 / 7)


def test_entries_carry_the_arc_identity(docs):
    ours, theirs = docs

    entry = lt.compare(ours, theirs, cell="u1").entries[0]

    assert entry.cell == "u1"
    assert entry.pin == "z"
    assert entry.related_pin == "a"
    assert entry.table == "cell_rise"
    assert "u1/z" in entry.arc
    assert entry.arc_key.pin == "z"


def test_arcs_missing_from_one_document_are_reported(tmp_path: Path):
    ours = lt.parse_file(_write(tmp_path, "ours.lib", OURS))
    fewer = OURS.replace(
        """      timing () {
        related_pin : "a";
        cell_rise (delay_template) {
          index_1 ("0.1, 0.2");
          index_2 ("1, 2");
          values ("10, 20, 30, 40");
        }
      }
""",
        "",
    )
    theirs = lt.parse_file(_write(tmp_path, "theirs.lib", fewer))

    diff = lt.compare(ours, theirs, cell="u1")

    assert [str(key) for key in diff.only_in_b] == []
    assert len(diff.only_in_a) == 1
    assert diff.only_in_a[0].pin == "z"
    assert diff.only_in_a[0].related_pin == "a"


def test_points_missing_from_one_grid_are_reported(tmp_path: Path):
    ours = lt.parse_file(_write(tmp_path, "ours.lib", OURS))
    smaller = THEIRS.replace('index_2 ("0.1, 0.2");', 'index_2 ("0.1");').replace(
        'values ("10, 30, 20, 40");', 'values ("10, 30");'
    )
    theirs = lt.parse_file(_write(tmp_path, "theirs.lib", smaller))

    diff = lt.compare(ours, theirs, cell="u1")

    unmatched = [entry for entry in diff.entries if not entry.matched]
    assert len(unmatched) == 2
    # The load axis is the one that is missing points.
    assert {entry.index_1 for entry in unmatched} == {0.2}
    assert all(entry.value_b is None for entry in unmatched)
    assert all(entry.delta is None for entry in unmatched)


def test_interpolation_compares_on_the_first_documents_grid(docs):
    ours, theirs = docs

    diff = lt.compare(ours, theirs, cell="u1", interpolate=True)

    # Every point of our grid gets a value from both documents.
    assert len(diff.entries) == 4
    assert all(entry.matched for entry in diff.entries)
    by_point = {(entry.index_1, entry.index_2): entry for entry in diff.entries}
    assert by_point[(0.1, 1.0)].value_b == 10.0
    assert by_point[(0.2, 1.0)].value_b == 35.0


def test_interpolation_on_a_requested_grid(docs):
    ours, theirs = docs

    diff = lt.compare(
        ours,
        theirs,
        cell="u1",
        interpolate=True,
        grid={"total_output_net_capacitance": [0.1, 0.2], "input_net_transition": [1.5]},
    )

    assert len(diff.entries) == 2
    # Halfway between transition 1 and 2 on each load.
    by_load = {entry.index_1: entry for entry in diff.entries}
    assert by_load[0.1].value_a == pytest.approx(15.0)
    assert by_load[0.1].value_b == pytest.approx(15.0)
    assert by_load[0.2].value_a == pytest.approx(35.0)
    assert by_load[0.2].value_b == pytest.approx(37.5)


def test_an_unknown_grid_axis_is_rejected(docs):
    ours, theirs = docs

    with pytest.raises(ValueError):
        lt.compare(
            ours,
            theirs,
            cell="u1",
            interpolate=True,
            grid={"nonsense": [1.0]},
        )


def test_arcs_are_matched_by_logically_equal_when_conditions(tmp_path: Path):
    a = """
library (a) {
  cell (u1) {
    pin (z) {
      direction : output;
      timing () { related_pin : "a"; when : "A & B"; }
    }
  }
}
"""
    b = """
library (b) {
  cell (u1) {
    pin (z) {
      direction : output;
      timing () { related_pin : "a"; when : "B & A"; }
    }
  }
}
"""
    ours = lt.parse_file(_write(tmp_path, "a.lib", a))
    theirs = lt.parse_file(_write(tmp_path, "b.lib", b))

    diff = lt.compare(ours, theirs, cell="u1")

    assert diff.only_in_a == []
    assert diff.only_in_b == []


def test_comparing_a_library_with_itself_finds_no_differences(tmp_path: Path):
    path = _write(tmp_path, "ours.lib", OURS)
    ours = lt.parse_file(path)
    theirs = lt.parse_file(path)

    diff = lt.compare(ours, theirs, cell="u1")

    assert diff.entries
    assert all(entry.matched for entry in diff.entries)
    assert diff.mismatched == []
    assert diff.only_in_a == []
    assert diff.only_in_b == []
    assert diff.max_abs_delta() == 0.0


def test_the_table_filter_selects_one_table(docs):
    ours, theirs = docs

    diff = lt.compare(ours, theirs, cell="u1", table="cell_rise")
    assert {entry.table for entry in diff.entries} == {"cell_rise"}

    # A table that neither document has yields nothing at all.
    diff = lt.compare(ours, theirs, cell="u1", table="cell_fall")
    assert diff.entries == []
    assert diff.only_in_b_tables == []


def test_tables_with_a_different_number_of_axes_are_reported(tmp_path: Path):
    flat = OURS.replace(
        """        cell_rise (delay_template) {
          index_1 ("0.1, 0.2");
          index_2 ("1, 2");
          values ("10, 20, 30, 40");
        }""",
        """        cell_rise (delay_template) {
          index_1 ("0.1, 0.2");
          values ("10, 20");
        }""",
    )
    ours = lt.parse_file(_write(tmp_path, "ours.lib", OURS))
    theirs = lt.parse_file(_write(tmp_path, "theirs.lib", flat))

    diff = lt.compare(ours, theirs, cell="u1")

    # The grids cannot be intersected, so the mismatch is reported instead of
    # silently comparing unrelated points.
    assert diff.shape_mismatches
    assert diff.shape_mismatches[0][1] == "cell_rise"
    assert diff.shape_mismatches[0][2:] == (2, 1)
    assert diff.entries == []


def test_interpolation_does_not_invent_values_for_a_different_shape(tmp_path: Path):
    flat = OURS.replace(
        """        cell_rise (delay_template) {
          index_1 ("0.1, 0.2");
          index_2 ("1, 2");
          values ("10, 20, 30, 40");
        }""",
        """        cell_rise (delay_template) {
          index_1 ("0.1, 0.2");
          values ("10, 20");
        }""",
    )
    ours = lt.parse_file(_write(tmp_path, "ours.lib", OURS))
    theirs = lt.parse_file(_write(tmp_path, "theirs.lib", flat))

    diff = lt.compare(ours, theirs, cell="u1", interpolate=True)

    assert diff.entries == []
    assert diff.shape_mismatches


def test_arcs_with_different_conditions_are_not_compared(tmp_path: Path):
    a = """
library (a) {
  cell (u1) {
    pin (z) {
      direction : output;
      timing () { related_pin : "a"; when : "A"; }
    }
  }
}
"""
    b = """
library (b) {
  cell (u1) {
    pin (z) {
      direction : output;
      timing () { related_pin : "a"; when : "A & B"; }
    }
  }
}
"""
    ours = lt.parse_file(_write(tmp_path, "a.lib", a))
    theirs = lt.parse_file(_write(tmp_path, "b.lib", b))

    diff = lt.compare(ours, theirs, cell="u1")

    # "A" and "A & B" describe different arcs, so there is nothing to
    # compare — the difference is reported instead of a meaningless delta.
    assert diff.entries == []
    assert len(diff.only_in_a) == 1
    assert len(diff.only_in_b) == 1


def test_axes_named_differently_are_still_aligned(tmp_path: Path):
    renamed = THEIRS.replace(
        "variable_1 : input_net_transition;",
        "variable_1 : input_transition;",
    ).replace(
        "variable_2 : total_output_net_capacitance;",
        "variable_2 : output_capacitance;",
    )
    ours = lt.parse_file(_write(tmp_path, "ours.lib", OURS))
    theirs = lt.parse_file(_write(tmp_path, "theirs.lib", renamed))

    diff = lt.compare(ours, theirs, cell="u1")
    by_point = {(entry.index_1, entry.index_2): entry for entry in diff.entries}

    # The slew axis of one library is matched against the slew axis of the
    # other even though the two name it differently.
    entry = by_point[(0.1, 1.0)]
    assert entry.value_a == 10.0
    assert entry.value_b == 10.0
    assert entry.delta == 0.0


def test_summary_and_polars_output(docs):
    ours, theirs = docs

    diff = lt.compare(ours, theirs, cell="u1")
    summary = diff.summary()

    assert summary["entries"] == 4
    assert summary["matched"] == 4
    assert summary["mismatched"] == 1
    assert summary["max_abs_delta"] == 5.0

    frame = diff.to_polars()
    assert frame.height == 4
    assert {"cell", "pin", "table", "value_a", "value_b", "delta"} <= set(frame.columns)
