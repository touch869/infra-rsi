"""Framework-neutral interfaces for the phase-1 plugin architecture."""

from __future__ import annotations

from typing import Any, Protocol


class SurfacePlugin(Protocol):
    """Framework-specific modification surface."""

    framework: str
    surface: str

    def validate(self, spec: Any) -> None:
        ...

    def candidates(self, spec: Any) -> list[Any]:
        ...


class Gate(Protocol):
    """A deterministic pass/fail gate."""

    name: str

    def check(self, context: Any) -> Any:
        ...


class TrialExecutor(Protocol):
    """Run one candidate trial and return raw execution evidence."""

    def execute(self, candidate: Any, spec: Any) -> Any:
        ...


class MetricExtractor(Protocol):
    """Parse raw execution evidence into trial metrics."""

    def extract(self, execution: Any, spec: Any) -> Any:
        ...


class KnowledgeProvider(Protocol):
    """Load framework or domain skills from a static skill source."""

    def list_skills(self, query: Any) -> list[Any]:
        ...

    def get_skill(self, skill_id: str, version: int) -> Any:
        ...


class Exporter(Protocol):
    """Export decisions, trials, or reports to a durable format."""

    def export(self, bundle: Any, path: str) -> None:
        ...


class ExpertRuntime(Protocol):
    """Run one expert with a stage prompt and deterministic runtime facade."""

    def run(self, expert: str, context: Any, facade: Any) -> Any:
        ...
