"""LibraryIndex (lazy cell-offset parser) must agree with a full parse_file."""

import gzip

import liberty_tools as lt

FIXTURE = """
library (idx_lib) {
  time_unit : "1ps";
  voltage_unit : "1V";
  current_unit : "1mA";
  capacitive_load_unit (1, ff);
  lu_table_template (d7) {
    variable_1 : input_net_transition;
    variable_2 : total_output_net_capacitance;
    index_1 ("1, 2"); index_2 ("3, 4");
  }
  cell (INV) {
    area : 1.0;
    pin (Y) {
      direction : output;
      function : "!A";
      timing () {
        related_pin : "A";
        cell_rise (d7) { index_1 ("1, 2"); index_2 ("3, 4"); values ("0.1, 0.2", "0.3, 0.4"); }
      }
    }
  }
  cell (BUF) {
    area : 2.0;
    dynamic_current () {
      related_inputs : "A"; related_outputs : "Y";
      switching_group () {
        input_switching_condition (rise);
        output_switching_condition (rise);
        pg_current (VDD) {
          vector (d7) { index_1 ("5"); index_2 ("1.5"); index_3 ("10, 20"); values ("0.1, 0.2"); }
        }
      }
    }
    pin (Y) { direction : output; function : "A"; }
  }
}
"""


def _write(tmp_path, gz=False):
    if gz:
        p = tmp_path / "idx.lib.gz"
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.write(FIXTURE)
        return p
    p = tmp_path / "idx.lib"
    p.write_text(FIXTURE, encoding="utf-8")
    return p


def test_index_matches_full_parse(tmp_path):
    path = _write(tmp_path)
    idx = lt.LibraryIndex.open(path)
    doc = lt.parse_file(path)

    assert idx.library_name == doc.library_name
    assert idx.cell_names() == doc.cells()
    assert idx.num_cells() == len(doc.cells())
    assert (idx.voltage_unit, idx.time_unit, idx.current_unit) == (
        doc.voltage_unit,
        doc.time_unit,
        doc.current_unit,
    )
    assert idx.capacitive_load_unit == doc.capacitive_load_unit
    assert idx.templates() == doc.templates()
    assert idx.energy_unit_joules() == doc.energy_unit_joules()


def test_index_lazy_cell_equals_full(tmp_path):
    path = _write(tmp_path)
    idx = lt.LibraryIndex.open(path)
    doc = lt.parse_file(path)

    # INV: timing table values match
    a_idx = idx.cell("INV").pin("Y").timing_arcs()[0].table("cell_rise")
    a_doc = doc.cell("INV").pin("Y").timing_arcs()[0].table("cell_rise")
    assert list(a_idx.values) == list(a_doc.values)
    assert idx.cell("INV").pin("Y").function == "!A"

    # BUF: CCSP survives the lazy parse
    dc = idx.cell("BUF").dynamic_currents()
    assert len(dc) == 1
    pg = dc[0].switching_groups()[0].pg_currents()[0]
    assert pg.pg_pin == "VDD"
    assert list(pg.vectors()[0].values) == [0.1, 0.2]


def test_index_gzip_input(tmp_path):
    path = _write(tmp_path, gz=True)
    idx = lt.LibraryIndex.open(path)
    assert idx.cell_names() == ["INV", "BUF"]
    assert idx.cell("BUF").area == 2.0


def test_index_unknown_cell_raises(tmp_path):
    idx = lt.LibraryIndex.open(_write(tmp_path))
    try:
        idx.cell("NOPE")
    except KeyError:
        return
    raise AssertionError("expected KeyError for unknown cell")
