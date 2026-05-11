from pathlib import Path

import pytest

import liberty_tools as lt


def sample_liberty_file() -> Path:
    sample = Path(__file__).resolve().parents[1] / "generic80_ss_125c_1p116v_0p84v.lib"
    if not sample.exists():
        pytest.skip("local large Liberty sample is not checked into the repository")
    return sample


def test_parse_sample_inventory():
    doc = lt.parse_file(sample_liberty_file())

    assert doc.library_name == "generic80_ss_125c_1p116v_0p84v"
    assert len(doc.cells()) == 1308

    cell = doc.cell("and2d102srdh")
    assert cell.area == 2.08152
    assert cell.pins() == ["y", "a", "b"]

    pin = cell.pin("y")
    arcs = pin.timing_arcs()
    assert len(arcs) == 2
    assert "cell_rise" in arcs[0].tables()


def test_timing_tables_to_polars():
    doc = lt.parse_file(sample_liberty_file(), cells=["and2d102srdh"])

    frame = doc.to_polars(cell="and2d102srdh", table="cell_rise")
    assert frame.height > 0
    assert {"cell", "pin", "related_pin", "table", "index_1", "index_2", "value"} <= set(
        frame.columns
    )


def test_when_filter_matches_required_boolean_condition(tmp_path):
    liberty = tmp_path / "when.lib"
    liberty.write_text(
        """
library (when_test) {
  cell (u1) {
    area : 1.0;
    pin (z) {
      direction : output;
      timing () { related_pin : "i"; when : "A & B"; }
      timing () { related_pin : "i"; when : "A & !B"; }
      timing () { related_pin : "i"; when : "!A"; }
      timing () { related_pin : "i"; when : "A | B"; }
      timing () { related_pin : "i"; }
    }
  }
}
""",
        encoding="utf-8",
    )

    doc = lt.parse_file(liberty)
    pin = doc.cell("u1").pin("z")

    assert [arc.when for arc in pin.timing_arcs(when="A")] == ["A & B", "A & !B"]
    assert [arc.when for arc in pin.timing_arcs(when="!A")] == ["!A"]
    assert [arc.when for arc in pin.timing_arcs(when="A & B")] == ["A & B"]


def test_when_filter_applies_to_polars_rows(tmp_path):
    liberty = tmp_path / "when_tables.lib"
    liberty.write_text(
        """
library (when_test) {
  cell (u1) {
    pin (z) {
      direction : output;
      timing () {
        related_pin : "i";
        when : "A & B";
        cell_rise (delay_template) {
          index_1 ("1,2");
          values ("3,4");
        }
      }
      timing () {
        related_pin : "i";
        when : "!A";
        cell_rise (delay_template) {
          index_1 ("1,2");
          values ("5,6");
        }
      }
    }
  }
}
""",
        encoding="utf-8",
    )

    doc = lt.parse_file(liberty)
    frame = doc.to_polars(when="A", table="cell_rise")

    assert frame["when"].to_list() == ["A & B", "A & B"]
    assert frame["value"].to_list() == [3.0, 4.0]
