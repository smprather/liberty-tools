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


def test_bus_bundle_and_bus_type_api(tmp_path):
    liberty = tmp_path / "ram.lib"
    liberty.write_text(
        """
library (ram_lib) {
  type (addr_bus_t) {
    base_type : array;
    data_type : bit;
    bit_width : 4;
    bit_from : 3;
    bit_to : 0;
    downto : true;
  }
  cell (sram32x8) {
    bus (A) {
      bus_type : addr_bus_t;
      direction : input;
      pin (A[0]) {
        direction : input;
      }
      pin (A[1]) {
        direction : input;
      }
    }
    bundle (control) {
      members ("CS WE OE");
      direction : input;
      pin (CS) {
        direction : input;
      }
      pin (WE) {
        direction : input;
      }
    }
    pin (Q) {
      direction : output;
      timing () {
        related_pin : "A[0]";
        when : "CS & !WE";
        cell_rise (delay_template) {
          index_1 ("1,2");
          values ("3,4");
        }
      }
    }
  }
}
""",
        encoding="utf-8",
    )

    doc = lt.parse_file(liberty)
    assert doc.bus_types() == ["addr_bus_t"]
    assert doc.bus_type("addr_bus_t").get("bit_width") == "4"

    cell = doc.cell("sram32x8")
    assert cell.buses() == ["A"]
    assert cell.bus("A").bus_type == "addr_bus_t"
    assert cell.bus("A").pins() == ["A[0]", "A[1]"]
    assert cell.bus("A").pin("A[0]").direction == "input"

    assert cell.bundles() == ["control"]
    assert cell.bundle("control").members == ["CS", "WE", "OE"]
    assert cell.bundle("control").pins() == ["CS", "WE"]

    frame = doc.to_polars(cell="sram32x8", pin="Q", related_pin="A[0]", when="CS")
    assert frame["value"].to_list() == [3.0, 4.0]
