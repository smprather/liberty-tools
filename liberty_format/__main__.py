"""``liberty_format`` CLI — strict, functionally-transparent Liberty formatter.

Run: ``uv run liberty_format FILE`` (or, after ``uv tool install .``,
``liberty_format FILE``).
"""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

import rich_click as click

from liberty_format import TransparencyError, format_text

click.rich_click.USE_RICH_MARKUP = True
click.rich_click.SHOW_ARGUMENTS = True
click.rich_click.STYLE_OPTION_DEFAULT = "dim cyan"


def _read(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read()
    return path.read_text(encoding="utf-8")


@click.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "-o", "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write formatted output here (default: stdout).",
)
@click.option(
    "-i", "--in-place",
    is_flag=True,
    help="Rewrite the input file in place.",
)
@click.option(
    "--check",
    is_flag=True,
    help="Don't write; exit non-zero if the file is not already formatted.",
)
@click.option(
    "--indent",
    type=int,
    default=2,
    show_default=True,
    help="Spaces per brace-nesting level.",
)
def main(
    file: Path, output: Path | None, in_place: bool, check: bool, indent: int
) -> None:
    """Reindent a **Liberty** (`.lib` / `.lib.gz`) file by brace depth.

    Strictly applies one indent level per `{ }` nesting, trims trailing
    whitespace, and collapses blank-line runs. The result is **guaranteed
    functionally transparent**: it is accepted only if it lexes to the exact
    same token stream as the input (otherwise the file is left untouched).
    """
    text = _read(file)
    try:
        formatted = format_text(text, indent=" " * indent)
    except TransparencyError as exc:
        raise click.ClickException(f"{file}: {exc}") from exc

    if check:
        if formatted == text:
            click.secho(f"{file}: already formatted", fg="green")
            return
        click.secho(f"{file}: would reformat", fg="yellow")
        sys.exit(1)

    if in_place:
        if file.suffix == ".gz":
            raise click.ClickException("--in-place not supported for .gz; use -o")
        if formatted == text:
            click.secho(f"{file}: unchanged", fg="green")
        else:
            file.write_text(formatted, encoding="utf-8")
            click.secho(f"{file}: formatted", fg="cyan")
    elif output:
        output.write_text(formatted, encoding="utf-8")
        click.secho(f"wrote {output}", fg="cyan")
    else:
        click.echo(formatted, nl=False)


if __name__ == "__main__":
    main()
