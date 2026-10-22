# Versioning Plan

This project uses two related version identifiers:

- Cargo/package version: SemVer in `Cargo.toml`.
- GitHub release tag: month-based release ID in `vYYYY.M.N[-suffix]` format.

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

GitHub releases use month-based tags:

```text
vYYYY.M.N[-suffix]
```

Example:

```text
v2026.10.1
```

`N` starts at `1` for the first release of a month and increments for each
additional release in the same month.

The optional `[-suffix]` marks a tag that is not a release — for example
`v2026.10.1-dev` for a development snapshot. Release tags carry no suffix.

Release tags should point at commits where `Cargo.toml` contains a stable
SemVer version, not a `-dev` version.

Tags released before this scheme (for example `v2026.06.01.1`) use the older
date-based `vYYYY.MM.DD.N` form and are left as they are.

## CLI Version Output

`liberty-format --version` prints the Cargo/package version:

```text
liberty-format 1.0.1-dev
```

On release-tagged commits, this should print the stable SemVer version for that
release.
