"""Writing a Liberty document back out (issue #1)."""

from pathlib import Path

import pytest

import liberty_tools as lt

LIBRARY = """/* A library with comments.
 */
library (write_test) {
  time_unit : "1ns";
  capacitive_load_unit (1, pf);

  cell (u1) {
    area : 1.0;
    cell_leakage_power : 12.5;
    dont_touch : "false";
    pin (a) {
      direction : input;
      capacitance : 0.5;
    }
    pin (z) {
      direction : output;
      timing () {
        related_pin : "a";
        cell_rise (delay_template) {
          index_1 ("1, 2");
          values ("3, 4");
        }
      }
    }
  }

  cell (u2) {
    area : 2.0;
  }
}
"""


@pytest.fixture()
def liberty(tmp_path: Path) -> Path:
    path = tmp_path / "write.lib"
    path.write_text(LIBRARY, encoding="utf-8")
    return path


def test_unchanged_document_round_trips_byte_for_byte(liberty):
    doc = lt.parse_file(liberty)

    assert doc.to_string() == LIBRARY


def test_writing_an_unchanged_document_copies_the_file(liberty, tmp_path: Path):
    doc = lt.parse_file(liberty)
    out = tmp_path / "copy.lib"
    doc.write(out)

    assert out.read_text(encoding="utf-8") == LIBRARY


def test_setting_the_area_changes_only_that_line(liberty):
    doc = lt.parse_file(liberty)
    doc.cell("u1").set_attribute("area", "59.8752")

    written = doc.to_string()
    assert "    area : 59.8752;" in written
    assert "    area : 1.0;" not in written
    # Everything else is untouched.
    assert written.count("cell (u2)") == 1
    assert "/* A library with comments." in written
    assert "    cell_leakage_power : 12.5;" in written
    assert "      capacitance : 0.5;" in written


def test_setting_an_area_updates_the_typed_attribute(liberty):
    doc = lt.parse_file(liberty)
    cell = doc.cell("u1")
    cell.set_area(59.8752)

    assert cell.area == 59.8752
    assert cell.get("area") == "59.8752"
    # A fresh handle sees the change too.
    assert doc.cell("u1").area == 59.8752


def test_a_new_attribute_is_added_to_the_cell(liberty, tmp_path: Path):
    doc = lt.parse_file(liberty)
    doc.cell("u1").set_attribute("dont_use", "true")

    written = doc.to_string()
    assert "dont_use : true;" in written
    assert written.count("dont_use") == 1
    # The written file parses back.
    out = tmp_path / "out.lib"
    doc.write(out)
    assert lt.parse_file(out).cell("u1").dont_use == "true"


def test_a_pin_attribute_can_be_changed(liberty):
    doc = lt.parse_file(liberty)
    doc.cell("u1").pin("a").set_attribute("capacitance", 0.25)

    written = doc.to_string()
    assert "      capacitance : 0.25;" in written
    assert "      capacitance : 0.5;" not in written


def test_written_document_parses_back_with_the_new_values(liberty, tmp_path: Path):
    doc = lt.parse_file(liberty)
    doc.cell("u1").set_attribute("area", "59.8752")
    doc.cell("u1").pin("a").set_attribute("capacitance", 0.25)
    out = tmp_path / "out.lib"
    doc.write(out)

    reparsed = lt.parse_file(out)
    assert reparsed.cell("u1").area == 59.8752
    assert reparsed.cell("u1").pin("a").capacitance == 0.25
    assert reparsed.cell("u2").area == 2.0
    # The tables survived the write.
    table = reparsed.cell("u1").pin("z").timing_arcs()[0].table("cell_rise")
    assert table.values == [3.0, 4.0]


def test_writing_to_a_gzipped_path(liberty, tmp_path: Path):
    doc = lt.parse_file(liberty)
    doc.cell("u1").set_attribute("area", "59.8752")
    out = tmp_path / "out.lib.gz"
    doc.write(out)

    assert out.read_bytes()[:2] == b"\x1f\x8b"
    reparsed = lt.parse_file(out)
    assert reparsed.cell("u1").area == 59.8752


def test_writing_refuses_a_source_file_that_changed(liberty, tmp_path: Path):
    doc = lt.parse_file(liberty)
    doc.cell("u1").set_attribute("area", "59.8752")

    liberty.write_text(LIBRARY + "\n/* edited behind our back */\n", encoding="utf-8")

    with pytest.raises(ValueError):
        doc.to_string()


def test_a_document_parsed_from_a_file_always_has_a_source(liberty):
    doc = lt.parse_file(liberty)
    assert doc.to_string() == LIBRARY


def test_unusual_formatting_survives_a_write(tmp_path: Path):
    source = (
        "library (odd) {\n"
        "\ttime_unit : \"1ns\";\n"
        "\t/* a comment */\n"
        "\tcell (c1) {\n"
        "\t\tarea:1.0;\n"
        "\t\tpin (a) { direction : input; }\n"
        "\t}\n"
        "}\n"
    )
    path = tmp_path / "odd.lib"
    path.write_text(source, encoding="utf-8")

    doc = lt.parse_file(path)
    assert doc.to_string() == source

    doc.cell("c1").set_attribute("area", "2.5")
    written = doc.to_string()

    # The comment, the tabs and the one-line pin group are untouched.
    assert "\t/* a comment */" in written
    assert "\t\tpin (a) { direction : input; }" in written
    assert "\t\tarea : 2.5;" in written


def test_a_complex_attribute_stays_complex(tmp_path: Path):
    source = (
        "library (complex) {\n"
        "  cell (u1) {\n"
        "    pin (a) {\n"
        "      rise_capacitance_range (0.25, 0.32);\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    path = tmp_path / "complex.lib"
    path.write_text(source, encoding="utf-8")

    doc = lt.parse_file(path)
    doc.cell("u1").pin("a").set_attribute("rise_capacitance_range", "0.1, 0.2")

    written = doc.to_string()
    assert "rise_capacitance_range (0.1, 0.2);" in written

    out = tmp_path / "out.lib"
    doc.write(out)
    assert lt.parse_file(out).cell("u1").pin("a").get("rise_capacitance_range") == (
        "0.1, 0.2"
    )


def test_replacing_and_adding_an_attribute_in_one_cell(liberty):
    doc = lt.parse_file(liberty)
    cell = doc.cell("u1")
    cell.set_attribute("area", "2.5")
    cell.set_attribute("dont_use", "true")

    written = doc.to_string()
    assert "    area : 2.5;" in written
    assert "    dont_use : true;" in written
    # The cell still has exactly one closing brace.
    assert written.count("cell (u1)") == 1


def test_adding_an_attribute_to_a_one_line_group(liberty):
    doc = lt.parse_file(liberty)
    doc.cell("u1").pin("a").set_attribute("capacitance", 0.25)

    written = doc.to_string()
    # The pin group is not duplicated.
    assert written.count("pin (a)") == 1
    assert "capacitance : 0.25;" in written


def test_new_attributes_keep_the_order_they_were_set_in(liberty):
    doc = lt.parse_file(liberty)
    cell = doc.cell("u1")
    cell.set_attribute("dont_use", "true")
    cell.set_attribute("cell_footprint", "foot")

    written = doc.to_string()
    assert written.index("dont_use : true;") < written.index("cell_footprint : foot;")


def test_a_boolean_attribute_is_written_as_true(liberty):
    doc = lt.parse_file(liberty)
    doc.cell("u1").set_attribute("dont_touch", True)

    written = doc.to_string()
    assert "dont_touch : true;" in written


def test_a_crlf_file_keeps_its_line_endings(tmp_path: Path):
    source = "library (crlf) {\r\n  cell (u1) {\r\n    area : 1.0;\r\n  }\r\n}\r\n"
    path = tmp_path / "crlf.lib"
    path.write_bytes(source.encode("utf-8"))

    doc = lt.parse_file(path)
    assert doc.to_string() == source

    doc.cell("u1").set_attribute("dont_use", "true")
    written = doc.to_string()

    assert "\r\n" in written
    assert "dont_use : true;\r\n" in written
    # No bare LF was introduced.
    assert written.replace("\r\n", "") .count("\n") == 0


def test_setting_the_same_attribute_twice_keeps_the_last_value(liberty):
    doc = lt.parse_file(liberty)
    cell = doc.cell("u1")
    cell.set_attribute("area", "22222222.0")
    cell.set_attribute("area", "3.0")

    written = doc.to_string()
    assert "    area : 3.0;" in written
    assert "22222222" not in written


@pytest.mark.parametrize(
    "sequence,expected",
    [
        (["area", "dont_touch"], {"area": "111111", "dont_touch": "true", "keep_me": "7"}),
        (
            ["area", "dont_touch", "area"],
            {"area": "222222", "dont_touch": "true", "keep_me": "7"},
        ),
        (
            ["area", "dont_touch", "area", "keep_me"],
            {"area": "222222", "dont_touch": "true", "keep_me": "8"},
        ),
        (
            ["area", "dont_touch", "area", "dont_touch"],
            {"area": "222222", "dont_touch": "true", "keep_me": "7"},
        ),
        (
            ["area", "dont_touch", "area", "keep_me", "dont_touch"],
            {"area": "222222", "dont_touch": "true", "keep_me": "8"},
        ),
        (
            ["area", "dont_touch", "area", "dont_touch", "keep_me"],
            {"area": "222222", "dont_touch": "true", "keep_me": "8"},
        ),
    ],
)
def test_the_last_edit_of_an_attribute_wins(sequence, expected, tmp_path: Path):
    source = (
        "library (dedup) {\n"
        "  cell (u1) {\n"
        "    area : 1.0;\n"
        "    dont_touch : false;\n"
        "    keep_me : 7;\n"
        "  }\n"
        "}\n"
    )
    path = tmp_path / "dedup.lib"
    path.write_text(source, encoding="utf-8")

    # The values used per key, in the order the sequence names them: "area"
    # goes to "111111" and then to "222222", "dont_touch" to "true" and
    # "keep_me" to "8".
    values = {"area": "111111", "dont_touch": "true", "keep_me": "8"}
    doc = lt.parse_file(path)
    cell = doc.cell("u1")
    seen_area = 0
    for key in sequence:
        if key == "area":
            seen_area += 1
            cell.set_attribute(key, "111111" if seen_area == 1 else "222222")
        else:
            cell.set_attribute(key, values[key])

    written = doc.to_string()
    out = tmp_path / "out.lib"
    doc.write(out)

    reparsed = lt.parse_file(out)
    for key, value in expected.items():
        assert reparsed.cell("u1").get(key) == value, key

    # No attribute swallowed the text of the following attribute.
    assert "keep_me : 7;" in written or "keep_me : 8;" in written
    assert written.count("keep_me") == 1
    # The written file re-parses without error (checked above) and the
    # untouched attributes survived.
    assert reparsed.cell("u1").get("dont_touch") == "true"


def test_editing_a_detached_cell_is_refused(liberty):
    # A cell from a LibraryIndex has no document to write back to, so the
    # edit would be lost. Refuse it instead of losing it silently.
    index = lt.LibraryIndex.open(liberty)
    cell = index.cell("u1")

    with pytest.raises(RuntimeError):
        cell.set_attribute("area", "59.8752")
