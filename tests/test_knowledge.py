"""HP skill catalog, resolver, and prompt integration."""

from __future__ import annotations

from pathlib import Path

from irsi.contract import load_contract
from irsi.knowledge import HPKnowledgeProvider, SkillCatalog, SkillResolver
from irsi.prompting import PROMPTS, PromptBuilder, StageContext

SKILL_ROOT = Path(__file__).resolve().parents[1] / "knowledge/skills"
TASK_PATH = Path(__file__).resolve().parents[1] / "examples/specs/hyperparallel-recompute.yaml"
TASK = load_contract(TASK_PATH)


def test_catalog_loads_hp_skills():
    catalog = SkillCatalog.from_root(SKILL_ROOT)
    expected = [
        "hp/engaged-evidence",
        "hp/measurement",
        "hp/memory-budget",
        "hp/mfu-perf",
        "hp/numeric-fingerprint",
        "hp/recompute-layerwise",
        "hp/recompute-modes",
    ]
    assert catalog.names() == expected


def test_get_skill_and_render_view():
    catalog = SkillCatalog.from_root(SKILL_ROOT)
    skill = catalog.get("hp/recompute-modes")
    assert skill.manifest.version == 1
    assert skill.manifest.kind == "domain"
    view = skill.to_view()
    assert view.id == "hp/recompute-modes"
    assert view.title == "HyperParallel activation recompute modes"
    assert "activation_checkpoint.mode" in view.excerpt
    assert view.manifest["framework"] == "hyperparallel"


def test_list_by_stage_and_surface():
    catalog = SkillCatalog.from_root(SKILL_ROOT)
    decision = catalog.list(framework="hyperparallel", stage="decision", surface="recompute")
    assert [skill.manifest.id for skill in decision] == [
        "hp/recompute-layerwise",
        "hp/recompute-modes",
    ]

    development = catalog.list(framework="hyperparallel", stage="development")
    assert [skill.manifest.id for skill in development] == [
        "hp/memory-budget",
        "hp/numeric-fingerprint",
        "hp/recompute-layerwise",
        "hp/recompute-modes",
    ]


def test_skill_resolver_selects_per_stage():
    catalog = SkillCatalog.from_root(SKILL_ROOT)
    resolver = SkillResolver(catalog)

    expected = {
        "decision": [
            "hp/mfu-perf",
            "hp/recompute-layerwise",
            "hp/recompute-modes",
        ],
        "development": [
            "hp/memory-budget",
            "hp/numeric-fingerprint",
            "hp/recompute-layerwise",
            "hp/recompute-modes",
        ],
        "observation": [
            "hp/engaged-evidence",
            "hp/measurement",
            "hp/memory-budget",
            "hp/mfu-perf",
        ],
        "execution": ["hp/engaged-evidence", "hp/measurement"],
        "judgment": [
            "hp/engaged-evidence",
            "hp/measurement",
            "hp/memory-budget",
            "hp/mfu-perf",
            "hp/numeric-fingerprint",
            "hp/recompute-layerwise",
            "hp/recompute-modes",
        ],
        "archive_report": [
            "hp/engaged-evidence",
            "hp/measurement",
            "hp/memory-budget",
            "hp/mfu-perf",
            "hp/numeric-fingerprint",
            "hp/recompute-layerwise",
        ],
    }

    for stage, ids in expected.items():
        views = resolver.resolve(stage, TASK)
        assert [view.id for view in views] == ids


def test_hp_provider_reads_skill_packages():
    provider = HPKnowledgeProvider(SKILL_ROOT)
    skill = provider.get_skill("hp/measurement", 1)
    assert skill.manifest.id == "hp/measurement"
    assert "tokens_per_second" in skill.body

    execution = provider.list_skills({"stage": "execution"})
    assert [skill.manifest.id for skill in execution] == [
        "hp/engaged-evidence",
        "hp/measurement",
    ]


def test_prompt_builder_uses_resolved_skills():
    catalog = SkillCatalog.from_root(SKILL_ROOT)
    resolver = SkillResolver(catalog)
    skills = resolver.resolve("decision", TASK)
    spec = PROMPTS.get("decision")
    context = StageContext(task=TASK, stage="decision", baseline_metric=100.0)
    rendered = PromptBuilder().render(spec, context, skills)

    assert "hp/recompute-modes" in rendered.text
    assert "hp/recompute-layerwise" in rendered.text
    assert "hp/mfu-perf" in rendered.text
    assert rendered.skill_ids == tuple(view.id for view in skills)
