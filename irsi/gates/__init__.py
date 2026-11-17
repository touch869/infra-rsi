"""Gate plugins: pass/fail checks applied to one trial."""

from . import builtin, parallel  # noqa: F401  (registers receipt / bitwise / memory / parallel)

__all__ = ["builtin", "parallel"]
