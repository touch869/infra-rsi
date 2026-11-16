"""Prompt spec, context, and deterministic assembly tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from irsi.contract import load_contract
from irsi.prompting import (
    ExpertPromptSpec,
    PromptBuildError,
    PromptBuilder,
    SkillPolicy,
    SkillView,
    StageContext,
)

TASK_PATH = Path(__file__).resolve().parents[1] / "examples/specs/hyperparallel-recompute.yaml"
TASK = load_contract(TASK_PATH)

SPEC = ExpertPromptSpec(
    role="development",
    stage="development",
    objective="Turn one hypothesis into a contract-approved candidate.",
    system="You are DevelopmentExpert. You do not execute trials or judge results.",
    required_inputs=("task",),
    allowed_tools=("validate_overrides", "list_candidates"),
    output_schema={
        "artifact_type": "CandidateSpec",
        "overrides": {"type": "object"},
        "rationale": {"type": "string"},
    },
    guardrails=(
        "Only keys under writable_prefixes may change.",
        "Never touch read-only keys.",
    ),
    skill_policy=SkillPolicy(max_skills=2, max_excerpt_chars=120),
)

SKILL = SkillView(
    id="hp/recompute-layerwise",
    version=1,
    title="Layerwise recompute",
    when_to_use="When per-layer checkpointing is available.",
    excerpt="Use activation_checkpoint.selection.layer_count to choose a layer ladder.",
    manifest={"framework": "hyperparallel", "surface": "recompute"},
)


def _context() -> StageContext:
    return StageContext(
        task=TASK,
        stage="development",
        baseline_metric=100.0,
        best_metric=110.0,
        recent_decisions=(
            {
                "trial": "h01-layerwise",
                "status": "keep",
                "metric": 110.0,
                "detail": "beat baseline beyond noise",
            },
        ),
        previous_artifact={
            "artifact_type": "HypothesisSet",
            "hypotheses": [
                {
                    "id": "layerwise",
                    "overrides": {"activation_checkpoint.mode": "selective"},
                }
            ],
        },
        candidate={"artifact_type": "CandidateSpec", "overrides": {}},
        notes=("baseline is frozen",),
    )


def test_fixed_sections_precede_variable_context():
    rendered = PromptBuilder().render(SPEC, _context(), [SKILL])
    text = rendered.text

    assert "=== SYSTEM ===" in text
    assert "=== OUTPUT ===" in text
    assert "=== GUARDRAILS ===" in text
    assert "=== TOOLS ===" in text
    assert "=== TASK ===" in text
    assert "=== CONTEXT ===" in text
    assert "=== SKILLS ===" in text

    assert text.index("=== OUTPUT ===") < text.index("=== TASK ===")
    assert text.index("=== TASK ===") < text.index("=== CONTEXT ===")
    assert text.index("=== CONTEXT ===") < text.index("=== SKILLS ===")
    assert text.index("=== TOOLS ===") < text.index("=== CONTEXT ===")


def test_render_includes_contract_constraints_and_artifact_schema():
    rendered = PromptBuilder().render(SPEC, _context(), [SKILL])
    text = rendered.text

    assert "activation_checkpoint." in text
    assert "training.seed" in text
    assert "performance/tokens_per_second" in text
    assert "recompute-layerwise" in text
    assert "artifact_type" in text
    assert "validate_overrides" in text
    assert rendered.skill_ids == ("hp/recompute-layerwise",)


def test_prompt_hash_is_deterministic():
    first = PromptBuilder().render(SPEC, _context(), [SKILL])
    second = PromptBuilder().render(SPEC, _context(), [SKILL])
    assert first.prompt_hash == second.prompt_hash
    assert first.text == second.text


def test_required_context_field_is_enforced():
    spec = ExpertPromptSpec(
        role="decision",
        stage="decision",
        objective="Produce hypotheses.",
        system="You are DecisionExpert.",
        required_inputs=("baseline_metric",),
        output_schema={"artifact_type": "HypothesisSet"},
    )
    context = StageContext(task=TASK, stage="decision", baseline_metric=None)
    with pytest.raises(PromptBuildError, match="baseline_metric"):
        PromptBuilder().render(spec, context)


def test_skill_policy_limit_is_enforced():
    spec = ExpertPromptSpec(
        role="decision",
        stage="decision",
        objective="Produce hypotheses.",
        system="You are DecisionExpert.",
        skill_policy=SkillPolicy(max_skills=1),
    )
    context = StageContext(task=TASK, stage="decision", baseline_metric=100.0)
    second = SkillView(
        id="hp/memory-budget",
        version=1,
        title="Memory budget",
        when_to_use="When memory is a gate.",
        excerpt="Check peak device memory.",
    )
    with pytest.raises(PromptBuildError, match="at most 1 skills"):
        PromptBuilder().render(spec, context, [SKILL, second])


def test_no_skills_is_allowed():
    spec = ExpertPromptSpec(
        role="decision",
        stage="decision",
        objective="Produce hypotheses.",
        system="You are DecisionExpert.",
    )
    context = StageContext(task=TASK, stage="decision", baseline_metric=100.0)
    rendered = PromptBuilder().render(spec, context)
    assert "No skills selected." in rendered.text
    assert rendered.skill_ids == ()
