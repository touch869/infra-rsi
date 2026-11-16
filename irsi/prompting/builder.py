"""Deterministic prompt assembly: fixed sections first, stage context last."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

from ..contract import InfraTaskSpec
from .context import StageContext
from .spec import ExpertPromptSpec, PromptBuildError, RenderedPrompt, SkillView

__all__ = ["PromptBuilder"]

_SECTION_ORDER = (
    "system",
    "output",
    "guardrails",
    "tools",
    "task",
    "context",
    "skills",
)


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6g}"


def _snippet(value: Any, limit: int) -> str:
    """Render a compact, deterministic JSON-ish view of an artifact."""
    if value is None:
        return "none"
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = repr(value)
    if len(text) > limit:
        return text[:limit].rstrip() + " ... (truncated)"
    return text


class PromptBuilder:
    """Render one expert prompt from a static spec plus dynamic context."""

    def __init__(
        self,
        *,
        max_context_chars: int = 4000,
        max_artifact_chars: int = 2000,
    ) -> None:
        if max_context_chars < 0 or max_artifact_chars < 0:
            raise ValueError("context/artifact limits must be >= 0")
        self.max_context_chars = max_context_chars
        self.max_artifact_chars = max_artifact_chars

    def render(
        self,
        spec: ExpertPromptSpec,
        context: StageContext,
        skills: Iterable[SkillView] = (),
    ) -> RenderedPrompt:
        skills = tuple(skills)
        sections = self.render_sections(spec, context, skills)
        text = "\n\n".join(
            f"=== {name.upper()} ===\n{body}" for name, body in sections.items()
        )
        return RenderedPrompt(
            role=spec.role,
            stage=spec.stage,
            text=text,
            prompt_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            sections=sections,
            skill_ids=tuple(skill.id for skill in self._selected_skills(spec, skills)),
            token_estimate=max(1, len(text) // 4),
        )

    def render_sections(
        self,
        spec: ExpertPromptSpec,
        context: StageContext,
        skills: Iterable[SkillView] = (),
    ) -> dict[str, str]:
        """Build named sections; useful for audit and tests."""
        self._validate(spec, context)
        sections = {
            "system": self._render_system(spec),
            "output": self._render_output(spec),
            "guardrails": self._render_guardrails(spec),
            "tools": self._render_tools(spec),
            "task": self._render_task(context.task),
            "context": self._render_context(context),
            "skills": self._render_skills(spec, skills),
        }
        if tuple(sections) != _SECTION_ORDER:  # pragma: no cover - defensive
            raise PromptBuildError("prompt section order is not stable")
        return sections

    def _validate(self, spec: ExpertPromptSpec, context: StageContext) -> None:
        if not isinstance(context.task, InfraTaskSpec):
            raise PromptBuildError("context.task is not an InfraTaskSpec")
        for name in spec.required_inputs:
            if getattr(context, name, None) is None:
                raise PromptBuildError(
                    f"required context field {name!r} is missing for {spec.role}"
                )

    def _render_system(self, spec: ExpertPromptSpec) -> str:
        return "\n".join(
            [
                f"role: {spec.role}",
                f"stage: {spec.stage}",
                f"objective: {spec.objective}",
                f"spec_version: {spec.version}",
                "",
                spec.system.strip(),
            ]
        )

    def _render_output(self, spec: ExpertPromptSpec) -> str:
        schema = json.dumps(
            dict(spec.output_schema),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        return (
            "Return exactly one JSON object matching this schema. "
            "Do not wrap it in markdown fences.\n"
            + schema
        )

    def _render_guardrails(self, spec: ExpertPromptSpec) -> str:
        if not spec.guardrails:
            return "No extra guardrails."
        return "\n".join(f"- {item}" for item in spec.guardrails)

    def _render_tools(self, spec: ExpertPromptSpec) -> str:
        if not spec.allowed_tools:
            return "No tools are allowed for this stage."
        return "\n".join(f"- {tool}" for tool in spec.allowed_tools)

    def _render_task(self, task: Any) -> str:
        lines = [
            f"name: {task.name}",
            f"repo_root: {task.repo_root}",
            f"base_config: {task.base_config}",
            f"domain: {task.domain}",
            f"writable_prefixes: {', '.join(task.writable_prefixes)}",
            f"read_only_keys: {', '.join(task.read_only_keys) or '<none>'}",
            (
                f"metric: {task.metric.key} "
                f"({task.metric.direction}, noise={task.metric.noise_fraction:.2%}, "
                f"warmup={task.metric.warmup_steps}, measured={task.metric.measured_steps})"
            ),
            f"gates: {', '.join(gate.name for gate in task.gates)}",
            (
                f"budget: max_trials={task.budget.max_trials}, "
                f"timeout_min={task.budget.timeout_min}"
            ),
            f"memory_budget_gib: {task.memory_budget_gib}",
            (
                f"workload: nproc={task.workload.nproc}, seed={task.workload.seed}, "
                f"determinism={task.workload.determinism}, "
                f"expect_steps={task.workload.expect_steps}"
            ),
        ]
        if task.domain_params:
            lines.append(
                "domain_params: "
                + json.dumps(dict(task.domain_params), ensure_ascii=False, sort_keys=True)
            )
        if task.base_overrides:
            lines.append(
                "base_overrides: "
                + json.dumps(dict(task.base_overrides), ensure_ascii=False, sort_keys=True)
            )
        return "\n".join(lines)

    def _render_context(self, context: StageContext) -> str:
        lines = [
            f"stage: {context.stage}",
            f"baseline_metric: {_number(context.baseline_metric)}",
            f"best_metric: {_number(context.best_metric)}",
        ]

        if context.recent_decisions:
            lines.append("recent_decisions:")
            for decision in context.recent_decisions[-5:]:
                lines.append(
                    f"- {decision.get('trial', '?')}: "
                    f"{decision.get('status', '?')} "
                    f"metric={decision.get('metric')} "
                    f"detail={decision.get('detail', '')}"
                )

        if context.records:
            lines.append("records:")
            for record in context.records[-5:]:
                lines.append(
                    f"- {record.get('trial', '?')}: "
                    f"status={record.get('status', '?')} "
                    f"metric={record.get('metric')}"
                )

        lines.append(
            "previous_artifact: "
            + _snippet(context.previous_artifact, self.max_artifact_chars)
        )
        lines.append(
            "candidate: " + _snippet(context.candidate, self.max_artifact_chars)
        )

        if context.notes:
            lines.append("notes:")
            lines.extend(f"- {note}" for note in context.notes)

        text = "\n".join(lines)
        if len(text) > self.max_context_chars:
            text = text[: self.max_context_chars].rstrip() + " ... (truncated)"
        return text

    def _selected_skills(self, spec: ExpertPromptSpec, skills: Iterable[SkillView]) -> list[SkillView]:
        selected = sorted(skills, key=lambda skill: (skill.id, skill.version))
        if len(selected) > spec.skill_policy.max_skills:
            raise PromptBuildError(
                f"{spec.role} allows at most {spec.skill_policy.max_skills} skills, "
                f"got {len(selected)}"
            )
        return selected

    def _render_skills(self, spec: ExpertPromptSpec, skills: Iterable[SkillView]) -> str:
        selected = self._selected_skills(spec, skills)
        if not selected:
            return "No skills selected."

        policy = spec.skill_policy
        lines: list[str] = []
        for skill in selected:
            excerpt = skill.excerpt.strip()
            if len(excerpt) > policy.max_excerpt_chars:
                excerpt = excerpt[: policy.max_excerpt_chars].rstrip() + " ..."

            lines.append(f"- {skill.id} v{skill.version}: {skill.title}")
            lines.append(f"  when_to_use: {skill.when_to_use}")
            lines.append(f"  excerpt: {excerpt}")

            if skill.manifest:
                manifest = json.dumps(
                    dict(skill.manifest), ensure_ascii=False, sort_keys=True
                )
                if len(manifest) > 500:
                    manifest = manifest[:500].rstrip() + " ..."
                lines.append(f"  manifest: {manifest}")

        return "\n".join(lines)
