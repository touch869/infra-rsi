"""Generic source-patch edit surface.

The contract declares candidates as id/description/overrides/patch pairs. The
orchestrator applies the patch to the task repo before execution, reverts it on
discard or crash, and commits the patch artifact only when the candidate is kept.
"""

from __future__ import annotations

from typing import Any, List, Mapping

from ..task_spec import InfraTaskSpec
from ...registry import SURFACES
from .base import Hypothesis

__all__ = ["source_patch_candidates"]


@SURFACES.register("source-patch")
def source_patch_candidates(spec: InfraTaskSpec) -> List[Hypothesis]:
    raw = spec.domain_params.get("candidates", ())
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("domain_params.candidates must be a non-empty list")

    hypotheses: List[Hypothesis] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("each source-patch candidate must be a mapping")
        patch = str(item.get("patch", ""))
        target_files = tuple(str(path) for path in item.get("patch_target_files", ()))
        if patch and not target_files:
            raise ValueError("a source-patch candidate must declare patch_target_files")
        hypotheses.append(
            Hypothesis(
                id=str(item["id"]),
                description=str(item.get("description", "")),
                overrides=dict(item.get("overrides", {})),
                expect_numeric_equal=bool(item.get("expect_numeric_equal", True)),
                patch=patch,
                patch_target_files=target_files,
            )
        )
    return hypotheses
