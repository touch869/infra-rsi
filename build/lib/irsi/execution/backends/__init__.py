"""Backend plugins: how one trial is executed."""

from . import hyperparallel  # noqa: F401  (registers the built-in backend)

__all__ = ["hyperparallel"]
