"""Plugin registries.

Every extension point in the harness is a named factory in one of three
registries. Adding a backend, a gate or an edit-surface plugin never requires
editing the engine.
"""

from __future__ import annotations

from typing import Callable, Dict, Generic, TypeVar

T = TypeVar("T")

__all__ = ["Registry", "BACKENDS", "GATES", "SURFACES"]


class Registry(Generic[T]):
    """A named set of factories for one plugin kind."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._factories: Dict[str, Callable[..., T]] = {}

    def register(self, name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """Register ``factory`` under ``name``; duplicate names are refused."""

        def decorator(factory: Callable[..., T]) -> Callable[..., T]:
            if name in self._factories:
                raise ValueError(f"duplicate {self.kind} plugin: {name}")
            self._factories[name] = factory
            return factory

        return decorator

    def create(self, name: str, /, **kwargs: object) -> T:
        """Instantiate the plugin registered under ``name``."""
        try:
            factory = self._factories[name]
        except KeyError as exc:
            known = ", ".join(sorted(self._factories)) or "<none>"
            raise KeyError(f"unknown {self.kind}: {name!r} (known: {known})") from exc
        return factory(**kwargs)

    def names(self) -> list[str]:
        """Registered plugin names, sorted."""
        return sorted(self._factories)


BACKENDS: Registry[object] = Registry("backend")
GATES: Registry[object] = Registry("gate")
SURFACES: Registry[object] = Registry("surface")
