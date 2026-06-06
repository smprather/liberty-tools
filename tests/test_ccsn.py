import liberty_tools as lt


FIXTURE = """
library (ccsn_lib) {
  lu_table_template (dc_t) {
    variable_1 : input_voltage;
    variable_2 : output_voltage;
  }
  output_current_template (ov_t) {
    variable_1 : input_net_transition;
    variable_2 : total_output_net_capacitance;
    variable_3 : time;
  }
  cell (buf) {
    pin (A) {
      direction : input;
    }
    pin (Y) {
      direction : output;
      timing () {
        related_pin : "A";
        timing_type : combinational;
        cell_rise (dc_t) {
          index_1 ("0.01, 0.02");
          values ("0.1, 0.2");
        }
        ccsn_first_stage () {
          is_inverting : true;
          is_needed : true;
          is_pass_gate : false;
          stage_type : pull_up;
          miller_cap_rise : 0.12;
          miller_cap_fall : 0.34;
          when : "A";
          mode (active, functional);
          dc_current (dc_t) {
            index_1 ("0.0, 0.5");
            index_2 ("0.0, 1.0");
            values ("0.1, -0.2", "0.3, -0.4");
          }
          output_voltage_rise () {
            vector (ov_t) {
              reference_time : 0.1;
              index_1 ("0.01");
              index_2 ("0.02");
              index_3 ("0.0, 0.5, 1.0");
              values ("0.0, 0.6, 1.0");
            }
          }
          output_voltage_fall () {
            vector (ov_t) {
              reference_time : 0.2;
              index_1 ("0.03");
              index_2 ("0.04");
              index_3 ("0.0, 0.5, 1.0");
              values ("1.0, 0.4, 0.0");
            }
          }
        }
      }
    }
  }
}
"""


def test_ccsn_stage_scalars_tables_and_vectors(tmp_path):
    path = tmp_path / "ccsn.lib"
    path.write_text(FIXTURE, encoding="utf-8")
    doc = lt.parse_file(path)
    arc = doc.cell("buf").pin("Y").timing_arcs()[0]

    stages = arc.ccsn_stages()
    assert len(stages) == 1
    stage = stages[0]
    assert stage.name == "ccsn_first_stage"
    assert stage.is_inverting == "true"
    assert stage.miller_cap_rise == 0.12
    assert stage.stage_type == "pull_up"

    dc = stage.dc_current()
    assert dc is not None
    assert dc.index_1 == [0.0, 0.5]
    assert dc.index_2 == [0.0, 1.0]
    assert dc.values == [0.1, -0.2, 0.3, -0.4]

    rise = stage.output_voltage_rise()[0]
    assert rise.index_1 == [0.01]
    assert rise.index_2 == [0.02]
    assert rise.index_3 == [0.0, 0.5, 1.0]
    assert rise.values == [0.0, 0.6, 1.0]

    fall = stage.output_voltage_fall()[0]
    assert fall.index_1 == [0.03]
    assert fall.index_2 == [0.04]
    assert fall.index_3 == [0.0, 0.5, 1.0]
    assert fall.values == [1.0, 0.4, 0.0]

    assert "ccsn_first_stage" not in arc.tables()
