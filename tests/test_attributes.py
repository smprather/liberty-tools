"""Uniform attribute access, typed scalar accessors and min pulse width
(issues #3 and #5)."""

from pathlib import Path

import pytest

import liberty_tools as lt

LIBRARY = """
library (attr_test) {
  voltage_unit : "1V";
  current_unit : "1mA";
  time_unit : "1ns";
  leakage_power_unit : "1pW";
  capacitive_load_unit (1, pf);
  default_max_transition : 1.5;
  default_fanout_load : 2;
  nom_voltage : 0.9;
  nom_temperature : 25;
  operating_conditions (default) {
    process : 1;
    temperature : 25;
    voltage : 0.9;
  }
  cell (u1) {
    area : 3.5;
    cell_leakage_power : 250.0;
    cell_footprint : "u1_fp";
    dont_touch : "true";
    dont_use : "false";
    pin (a) {
      direction : input;
      capacitance : 0.0044679094777018286;
      rise_capacitance : 0.005;
      fall_capacitance : 0.006;
      max_transition : 2.0;
      min_pulse_width_high : 0.09117187499999997;
      min_pulse_width_low : 0.7999999999999999;
    }
    pin (clk) {
      direction : input;
      timing () {
        related_pin : "clk";
        timing_type : min_pulse_width;
        rise_constraint (mpw_constraint) {
          index_1 ("1, 2");
          values ("0.05, 0.06");
        }
        fall_constraint (mpw_constraint) {
          index_1 ("1, 2");
          values ("0.07, 0.08");
        }
      }
    }
  }
}
"""


@pytest.fixture()
def doc(tmp_path: Path) -> lt.LibertyDocument:
    liberty = tmp_path / "attr.lib"
    liberty.write_text(LIBRARY, encoding="utf-8")
    return lt.parse_file(liberty)


def test_uniform_get_on_document_cell_and_pin(doc):
    assert doc.get("time_unit") == "1ns"
    assert doc.get("default_max_transition") == "1.5"
    assert doc.get("nope") is None

    cell = doc.cell("u1")
    assert cell.get("area") == "3.5"
    assert cell.get("cell_leakage_power") == "250.0"
    assert cell.get("nope") is None

    pin = cell.pin("a")
    assert pin.get("capacitance") == "0.0044679094777018286"
    assert pin.get("nope") is None


def test_typed_document_accessors(doc):
    assert doc.default_max_transition == 1.5
    assert doc.default_fanout_load == 2.0
    assert doc.nom_voltage == 0.9
    assert doc.nom_temperature == 25.0
    assert doc.capacitive_load_multiplier == 1.0
    assert doc.leakage_power_unit == "1pW"


def test_typed_cell_accessors(doc):
    cell = doc.cell("u1")
    assert cell.cell_leakage_power == 250.0
    # 250 in units of 1pW is 250e-12 W.
    assert cell.cell_leakage_power_watts == pytest.approx(250e-12)
    assert cell.cell_footprint == "u1_fp"
    assert cell.dont_touch == "true"
    assert cell.dont_use == "false"


def test_typed_pin_accessors_use_the_library_units(doc):
    pin = doc.cell("u1").pin("a")
    assert pin.capacitance == 0.0044679094777018286
    # The library declares picofarads.
    assert pin.capacitance_farads == pytest.approx(0.0044679094777018286e-12)
    assert pin.rise_capacitance == 0.005
    assert pin.rise_capacitance_farads == pytest.approx(5e-15)
    assert pin.fall_capacitance == 0.006
    assert pin.fall_capacitance_farads == pytest.approx(6e-15)
    # The library declares nanoseconds.
    assert pin.max_transition == 2.0
    assert pin.max_transition_seconds == pytest.approx(2e-9)


def test_nom_values_fall_back_to_the_operating_condition(tmp_path: Path):
    liberty = tmp_path / "oc.lib"
    liberty.write_text(
        """
library (oc) {
  voltage_unit : "1V";
  operating_conditions (default) {
    process : 1;
    voltage : 0.9;
    temperature : 25;
  }
  cell (u1) {
    area : 1.0;
  }
}
""",
        encoding="utf-8",
    )
    doc = lt.parse_file(liberty)

    assert doc.nom_voltage == 0.9
    assert doc.nom_temperature == 25.0


def test_the_named_default_operating_condition_wins(tmp_path: Path):
    liberty = tmp_path / "oc2.lib"
    liberty.write_text(
        """
library (oc2) {
  voltage_unit : "1V";
  default_operating_conditions : fast;
  operating_conditions (slow) {
    process : 1;
    voltage : 0.9;
    temperature : 125;
  }
  operating_conditions (fast) {
    process : 1;
    voltage : 1.1;
    temperature : -40;
  }
  cell (u1) {
    area : 1.0;
  }
}
""",
        encoding="utf-8",
    )
    doc = lt.parse_file(liberty)

    assert doc.get("default_operating_conditions") == "fast"
    assert doc.nom_voltage == 1.1
    assert doc.nom_temperature == -40.0


def test_operating_conditions_are_exposed(doc):
    assert doc.operating_conditions() == [
        (
            "default",
            [("process", "1"), ("temperature", "25"), ("voltage", "0.9")],
        )
    ]
    assert doc.operating_condition("default")[2] == ("voltage", "0.9")
    with pytest.raises(KeyError):
        doc.operating_condition("nope")


def test_min_pulse_width_from_pin_attributes(doc):
    pin = doc.cell("u1").pin("a")
    assert pin.min_pulse_width_high == 0.09117187499999997
    assert pin.min_pulse_width_low == 0.7999999999999999
    assert pin.min_pulse_width_high_seconds == pytest.approx(0.09117187499999997e-9)

    width = pin.min_pulse_width()
    assert width is not None
    assert width.high == 0.09117187499999997
    assert width.low == 0.7999999999999999
    assert width.source == "attribute"
    high, low = width
    assert (high, low) == (0.09117187499999997, 0.7999999999999999)


def test_min_pulse_width_from_the_timing_group(doc):
    pin = doc.cell("u1").pin("clk")
    assert pin.min_pulse_width_high is None
    assert pin.min_pulse_width_low is None

    width = pin.min_pulse_width()
    assert width is not None
    # The constraint tables are indexed by clock transition; the tightest
    # limit is the largest value in the table.
    assert width.high == 0.06
    assert width.low == 0.08
    assert width.source == "timing_group"


def test_min_pulse_width_is_none_when_the_file_has_neither_form(tmp_path: Path):
    liberty = tmp_path / "no_mpw.lib"
    liberty.write_text(
        """
library (no_mpw) {
  cell (u1) {
    pin (clk) {
      direction : input;
    }
  }
}
""",
        encoding="utf-8",
    )
    doc = lt.parse_file(liberty)
    assert doc.cell("u1").pin("clk").min_pulse_width() is None


def test_attribute_form_wins_over_the_timing_group(tmp_path: Path):
    liberty = tmp_path / "both_mpw.lib"
    liberty.write_text(
        """
library (both_mpw) {
  cell (u1) {
    pin (clk) {
      direction : input;
      min_pulse_width_high : 0.5;
      min_pulse_width_low : 0.6;
      timing () {
        related_pin : "clk";
        timing_type : min_pulse_width;
        rise_constraint (t) {
          index_1 ("1");
          values ("0.1");
        }
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    doc = lt.parse_file(liberty)
    width = doc.cell("u1").pin("clk").min_pulse_width()
    assert width is not None
    assert width.source == "attribute"
    assert width.high == 0.5
    assert width.low == 0.6
