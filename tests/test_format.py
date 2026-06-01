import liberty_tools as lt
from liberty_tools import _native
from liberty_format import format_text, reindent

MESSY = """\
library(l){
  cell (a){
        area:1;
 pin(Y){direction:output;
function : "A";
}
   /* a block
      comment */
  comment : "line1 \\
line2";
}
}
"""


def _tok(s):
    return _native.tokenize_str(s)


def test_format_is_token_transparent_and_strict_indent():
    out = format_text(MESSY)
    # functional transparency: identical lexer token stream
    assert _tok(out) == _tok(MESSY)
    # strict brace indentation (2 spaces per level); intra-line spacing is left
    # exactly as-is (reindent only — never reflows tokens).
    lines = out.splitlines()
    assert lines[0] == "library(l){"  # depth 0, content untouched
    assert "  cell (a){" in out  # cell at depth 1
    assert "    area:1;" in out  # area at depth 2
    assert '      function : "A";' in out  # function at depth 3


def test_format_idempotent():
    once = format_text(MESSY)
    assert format_text(once) == once


def test_format_preserves_multiline_string_bytes():
    # the embedded backslash-continued string must survive untouched
    out = format_text(MESSY)
    assert "line1 \\" in out
    assert "line2" in out
    # and the parse agrees
    assert _tok(out) == _tok(MESSY)


def test_format_parses_to_same_document(tmp_path):
    src = tmp_path / "m.lib"
    src.write_text(MESSY, encoding="utf-8")
    out = tmp_path / "m.fmt.lib"
    out.write_text(format_text(MESSY), encoding="utf-8")
    a = lt.parse_file(src)
    b = lt.parse_file(out)
    assert a.cells() == b.cells()
    assert a.cell("a").pin("Y").direction == b.cell("a").pin("Y").direction


def test_reindent_alone_does_not_change_tokens():
    # reindent (no verification) must already be transparent on this input
    assert _tok(reindent(MESSY)) == _tok(MESSY)
