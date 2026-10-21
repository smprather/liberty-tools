"""Type-level guard for the frozen ``MinPulseWidth`` stub.

``MinPulseWidth`` is a frozen dataclass at runtime
(``liberty_tools/__init__.py``), so the stub
(``liberty_tools/__init__.pyi``) declares it as one. A type checker must
reject an assignment to one of its fields.

The assignment below carries a ``ty: ignore`` directive: it type-checks
cleanly only while the field is read-only. If the stub ever loses its
``frozen=True``, the directive becomes unused and ``ty check`` reports it.

This file is never executed by pytest — it is a static check.
"""

import liberty_tools as lt


def reassign(width: lt.MinPulseWidth) -> None:
    width.high = 0.0  # ty: ignore[invalid-assignment]
