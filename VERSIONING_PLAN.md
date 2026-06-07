# Versioning Plan

This project uses two related version identifiers:

- Cargo/package version: SemVer in `Cargo.toml`.
- GitHub release tag: date-based release ID in `vYYYY.MM.DD.N` format.

## Cargo Version

`Cargo.toml` must remain valid SemVer because Cargo enforces SemVer syntax.

Release commits use stable SemVer:

```toml
version = "1.0.0"
```

After a release, `main` is bumped to the next patch development version:

```toml
version = "1.0.1-dev"
```

Patch, minor, and major changes follow SemVer:

- Patch: backward-compatible bug fixes.
- Minor: backward-compatible new functionality.
- Major: incompatible CLI, output, or behavior changes.

Default post-release bump is patch `-dev`. Bump minor only when the next cycle
has added backward-compatible functionality. Bump major only for breaking
changes.

## Release Tags

GitHub releases use date-based tags:

```text
vYYYY.MM.DD.N
```

Example:

```text
v2026.06.01.1
```

`N` starts at `1` for the first release on a given date and increments for
additional releases on the same date.

Release tags should point at commits where `Cargo.toml` contains a stable
SemVer version, not a `-dev` version.

## CLI Version Output

`liberty_format --version` prints the Cargo/package version:

```text
liberty_format 1.0.1-dev
```

On release-tagged commits, this should print the stable SemVer version for that
release.
