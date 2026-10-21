"""Type-level guard for the compare API (checked by ``uv run ty check``).

The comparison API lives in the module ``liberty_tools.comparison``; the
package re-exports it, so ``liberty_tools.compare`` is the *function* and the
module stays importable under its own name. The stub
(``liberty_tools/__init__.pyi``) must re-export the same names instead of
redeclaring them, otherwise a type checker sees two nominal ``Comparison``
types and rejects perfectly valid code.

This file is never executed by pytest — it is a static check. Every
assignment below must type-check.
"""

from typing import Callable

import liberty_tools as lt
import liberty_tools.comparison as comparison

# The class exported by the package and the class of the module are one and
# the same type, in both directions.
package_class: type[lt.Comparison] = lt.Comparison
module_class: type[comparison.Comparison] = comparison.Comparison
package_class = comparison.Comparison
module_class = lt.Comparison

# The function exported by the package is the function of the module.
package_function: Callable[..., comparison.Comparison] = lt.compare
module_function: Callable[..., lt.Comparison] = comparison.compare

# The exported class can be built with the keyword arguments of the runtime.
empty: lt.Comparison = lt.Comparison(entries=[])
also_empty: comparison.Comparison = comparison.Comparison(entries=[])
