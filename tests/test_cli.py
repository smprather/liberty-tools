from importlib.metadata import version

from click.testing import CliRunner

from liberty_format.__main__ import main as format_main
from viewer.__main__ import main as view_main


def test_liberty_format_version_option():
    result = CliRunner().invoke(format_main, ["--version"])

    assert result.exit_code == 0
    assert result.output == f"liberty_format {version('liberty-tools')}\n"


def test_liberty_view_version_option():
    result = CliRunner().invoke(view_main, ["--version"])

    assert result.exit_code == 0
    assert result.output == f"liberty_view {version('liberty-tools')}\n"
