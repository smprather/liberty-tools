"""Table lookup, flat value ordering and axis roles (issues #2 and #6)."""

from pathlib import Path

import pytest

import liberty_tools as lt

LIBRARY = """
library (lookup_test) {
  time_unit : "1ns";
  capacitive_load_unit (1, pf);
  lu_table_template (delay_template) {
    variable_1 : input_net_transition;
    variable_2 : total_output_net_capacitance;
  }
  lu_table_template (load_template) {
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
          index_1 ("1, 2");
          index_2 ("10, 20, 30");
          values ("1, 2, 3, 4, 5, 6");
        }
        cell_fall (load_template) {
          index_1 ("10, 20, 30");
          index_2 ("1, 2");
          values ("1, 2, 3, 4, 5, 6");
        }
      }
    }
  }
}
"""


@pytest.fixture()
def doc(tmp_path: Path) -> lt.LibertyDocument:
    liberty = tmp_path / "lookup.lib"
    liberty.write_text(LIBRARY, encoding="utf-8")
    return lt.parse_file(liberty)


def _table(doc: lt.LibertyDocument, name: str) -> lt.TimingTable:
    arc = doc.cell("u1").pin("z").timing_arcs()[0]
    return arc.table(name)


def test_flat_values_are_row_major_with_index_1_slowest(doc):
    table = _table(doc, "cell_rise")

    # index_1 has 2 points, index_2 has 3: values run along index_2 first.
    assert table.values == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert table.value_at(0, 0) == 1.0
    assert table.value_at(0, 2) == 3.0
    assert table.value_at(1, 0) == 4.0
    assert table.value_at(1, 2) == 6.0


def test_value_at_rejects_out_of_range_positions(doc):
    table = _table(doc, "cell_rise")

    with pytest.raises(IndexError):
        table.value_at(2, 0)
    with pytest.raises(IndexError):
        table.value_at(0, 3)


def test_value_at_rejects_negative_positions(doc):
    table = _table(doc, "cell_rise")

    with pytest.raises(IndexError):
        table.value_at(-1, 0)
    with pytest.raises(IndexError):
        table.value_at(0, -1)
    with pytest.raises(IndexError):
        table.value_at(0, 0, -1)


def test_lookup_by_index_value(doc):
    table = _table(doc, "cell_rise")

    assert table.lookup(index_1=1.0, index_2=20.0) == 2.0
    assert table.lookup(index_1=2.0, index_2=30.0) == 6.0


def test_lookup_returns_none_for_points_off_the_grid(doc):
    table = _table(doc, "cell_rise")

    assert table.lookup(index_1=1.5, index_2=20.0) is None
    assert table.lookup(index_1=1.0, index_2=25.0) is None


def test_lookup_requires_a_coordinate_for_every_axis(doc):
    table = _table(doc, "cell_rise")

    with pytest.raises(ValueError):
        table.lookup(index_1=1.0)


def test_axis_roles_come_from_the_table_template(doc):
    table = _table(doc, "cell_rise")

    assert table.axis_roles() == [
        "input_net_transition",
        "total_output_net_capacitance",
    ]
    assert table.axis_role(1) == "input_net_transition"
    assert table.axis_role(2) == "total_output_net_capacitance"
    assert table.index_1_variable == "input_net_transition"
    assert table.index_2_variable == "total_output_net_capacitance"


def test_axis_roles_follow_the_table_not_the_template(doc):
    # The same library stores the load on index_1 in this table.
    table = _table(doc, "cell_fall")

    assert table.axis_roles() == [
        "total_output_net_capacitance",
        "input_net_transition",
    ]
    assert table.index_1_variable == "total_output_net_capacitance"


def test_a_three_dimensional_table_is_looked_up_by_position_and_by_value(
    tmp_path: Path,
):
    liberty = tmp_path / "three_d.lib"
    liberty.write_text(
        """
library (three_d) {
  lu_table_template (t3) {
    variable_1 : input_net_transition;
    variable_2 : total_output_net_capacitance;
    variable_3 : time;
  }
  cell (u1) {
    pin (z) {
      direction : output;
      timing () {
        related_pin : "a";
        cell_rise (t3) {
          index_1 ("1, 2");
          index_2 ("10, 20");
          index_3 ("0, 1");
          values ("1, 2, 3, 4, 5, 6, 7, 8");
        }
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    doc = lt.parse_file(liberty)
    table = doc.cell("u1").pin("z").timing_arcs()[0].table("cell_rise")

    assert table.axis_roles() == [
        "input_net_transition",
        "total_output_net_capacitance",
        "time",
    ]

    # index_3 varies fastest, then index_2, then index_1.
    assert table.values == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]

    # By grid position: row indexes index_1, col indexes index_2 and depth
    # indexes index_3.
    assert table.value_at(0, 0, 0) == 1.0
    assert table.value_at(0, 0, 1) == 2.0
    assert table.value_at(0, 1, 0) == 3.0
    assert table.value_at(0, 1, 1) == 4.0
    assert table.value_at(1, 0, 0) == 5.0
    assert table.value_at(1, 1, 1) == 8.0

    # By the value of each axis.
    assert table.lookup(index_1=1.0, index_2=10.0, index_3=0.0) == 1.0
    assert table.lookup(index_1=1.0, index_2=20.0, index_3=1.0) == 4.0
    assert table.lookup(index_1=2.0, index_2=20.0, index_3=1.0) == 8.0

    # By the role the template gives the axis.
    assert table.lookup(
        input_net_transition=1.0,
        total_output_net_capacitance=10.0,
        time=0.0,
    ) == 1.0
    assert table.lookup(transition=2.0, load=20.0, time=1.0) == 8.0

    # A position outside the table is an error.
    with pytest.raises(IndexError):
        table.value_at(0, 0, 2)


def test_a_template_declared_after_the_cell_that_uses_it_still_names_the_axes(
    tmp_path: Path,
):
    liberty = tmp_path / "late_template.lib"
    liberty.write_text(
        """
library (late_template) {
  cell (u1) {
    pin (z) {
      direction : output;
      timing () {
        related_pin : "a";
        cell_rise (delay_template) {
          index_1 ("1, 2");
          index_2 ("10, 20");
          values ("1, 2, 3, 4");
        }
      }
    }
  }
  lu_table_template (delay_template) {
    variable_1 : input_net_transition;
    variable_2 : total_output_net_capacitance;
  }
}
""",
        encoding="utf-8",
    )
    doc = lt.parse_file(liberty)
    table = doc.cell("u1").pin("z").timing_arcs()[0].table("cell_rise")

    # The template is resolved once the whole library body has been parsed,
    # so a template declared after the cell that uses it still names its
    # axes.
    assert table.axis_roles() == [
        "input_net_transition",
        "total_output_net_capacitance",
    ]
    assert table.lookup(transition=1.0, load=10.0) == 1.0
    assert table.lookup(load=20.0, transition=2.0) == 4.0


def test_lookup_by_axis_role(doc):
    table = _table(doc, "cell_rise")

    assert table.lookup(load=20.0, transition=1.0) == 2.0
    assert table.lookup(
        total_output_net_capacitance=30.0, input_net_transition=2.0
    ) == 6.0


def test_lookup_by_role_accepts_the_common_template_names(tmp_path: Path):
    liberty = tmp_path / "synonyms.lib"
    liberty.write_text(
        """
library (synonyms) {
  lu_table_template (t) {
    variable_1 : input_net_transition;
    variable_2 : output_capacitance;
  }
  cell (u1) {
    pin (z) {
      direction : output;
      timing () {
        related_pin : "a";
        cell_rise (t) {
          index_1 ("1, 2");
          index_2 ("10, 20");
          values ("1, 2, 3, 4");
        }
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    doc = lt.parse_file(liberty)
    table = doc.cell("u1").pin("z").timing_arcs()[0].table("cell_rise")

    assert table.axis_roles() == ["input_net_transition", "output_capacitance"]
    assert table.lookup(load=20.0, transition=1.0) == 2.0
    assert table.lookup(capacitance=20.0, slew=1.0) == 2.0


def test_lookup_by_role_rejects_unknown_axis(doc):
    table = _table(doc, "cell_rise")

    with pytest.raises(ValueError):
        table.lookup(voltage=1.0)


def test_tables_without_a_template_have_no_axis_roles(tmp_path: Path):
    liberty = tmp_path / "no_template.lib"
    liberty.write_text(
        """
library (no_template) {
  cell (u1) {
    pin (z) {
      direction : output;
      timing () {
        related_pin : "a";
        cell_rise () {
          index_1 ("1, 2");
          values ("3, 4");
        }
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    doc = lt.parse_file(liberty)
    table = doc.cell("u1").pin("z").timing_arcs()[0].table("cell_rise")

    # One axis, one (unknown) role.
    assert table.axis_roles() == [None]
    assert table.template is None
    # Lookup by index still works without a template.
    assert table.lookup(index_1=2.0) == 4.0


def test_a_table_without_a_grid_has_no_value_to_look_up(tmp_path: Path):
    liberty = tmp_path / "no_grid.lib"
    liberty.write_text(
        """
library (no_grid) {
  cell (u1) {
    pin (z) {
      direction : output;
      timing () {
        related_pin : "a";
        output_current_rise (ccs_template) {
          vector ("1") {
            index_1 ("1");
            index_3 ("0.1");
            values ("2");
          }
        }
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    doc = lt.parse_file(liberty)
    table = doc.cell("u1").pin("z").timing_arcs()[0].table("output_current_rise")

    assert table.index_1 == []
    assert table.values == []
    assert table.lookup() is None
    assert table.lookup(index_1=1.0) is None
