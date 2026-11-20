"""Agent-authored contracts are summarized, confirmed and hash-locked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from irsi.cli import main
from irsi.contract import (
    ContractLockError,
    check_overrides_allowed,
    confirm_contract,
    contract_hash,
    create_contract_draft,
    load_contract,
    load_contract_lock,
    verify_contract_lock,
)


def _base_config(tmp_path: Path) -> Path:
    path = tmp_path / "workspace" / "configs" / "train_tiny.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "training": {
                    "train_iters": 12,
                    "seed": 7,
                    "enable_full_determinism": False,
                    "backend": "hccl",
                },
                "fsdp_config": {"dp_shard_size": 2},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _draft(tmp_path: Path):
    return create_contract_draft(
        objective="优化重计算策略，提高吞吐并保持数值一致",
        out=tmp_path / "contracts" / "generated.yaml",
        base_config=_base_config(tmp_path),
        repo_root=tmp_path,
        warmup_steps=4,
        measured_steps=4,
    )


def test_draft_infers_config_and_writes_review_artifacts(tmp_path):
    draft = _draft(tmp_path)
    spec = load_contract(draft.path)
    assert spec.workload.nproc == 2
    assert spec.workload.seed == 7
    assert spec.workload.determinism is False
    assert spec.workload.expect_steps == 12
    assert spec.metric.warmup_steps == 4
    assert spec.metric.measured_steps == 4
    assert spec.writable_prefixes == ("activation_checkpoint.",)
    assert "activation_checkpoint.allow_cache_entry_mutation" in spec.read_only_keys
    with pytest.raises(ValueError, match="read-only"):
        check_overrides_allowed(
            spec, {"activation_checkpoint.allow_cache_entry_mutation": True}
        )

    summary_path = draft.path.with_suffix(draft.path.suffix + ".summary.md")
    assert draft.path.is_file()
    assert draft.manifest_path.is_file()
    assert summary_path.is_file()
    assert "优化重计算策略" in summary_path.read_text(encoding="utf-8")
    manifest = json.loads(draft.manifest_path.read_text(encoding="utf-8"))
    assert manifest["contract_hash"] == contract_hash(spec)
    assert manifest["confirmation_code"] == draft.confirmation_code
    assert load_contract_lock(draft.path) is None


def test_confirm_requires_code_statement_and_matching_draft(tmp_path):
    draft = _draft(tmp_path)
    with pytest.raises(ContractLockError, match="expected"):
        confirm_contract(
            draft.path,
            confirmation_code="not-the-code",
            statement="确认冻结",
        )
    with pytest.raises(ContractLockError, match="statement"):
        confirm_contract(
            draft.path,
            confirmation_code=draft.confirmation_code,
            statement="   ",
        )

    lock = confirm_contract(
        draft.path,
        confirmation_code=draft.confirmation_code,
        statement="确认上述评估边界，baseline 后不再修改。",
        confirmed_by="user",
    )
    assert lock["contract_hash"] == draft.contract_hash
    assert load_contract_lock(draft.path)["statement"].startswith("确认上述")
    assert verify_contract_lock(draft.path, load_contract(draft.path)) == lock


def test_contract_change_after_confirmation_invalidates_lock(tmp_path):
    draft = _draft(tmp_path)
    confirm_contract(
        draft.path,
        confirmation_code=draft.confirmation_code,
        statement="确认冻结该评估边界。",
    )
    raw = yaml.safe_load(draft.path.read_text(encoding="utf-8"))
    raw["workload"]["nproc"] = 4
    draft.path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    changed = load_contract(draft.path)

    with pytest.raises(ContractLockError, match="changed after confirmation"):
        verify_contract_lock(draft.path, changed, require=True)


def test_cli_draft_show_confirm_flow(tmp_path, capsys):
    contract = tmp_path / "contracts" / "generated.yaml"
    assert main(
        [
            "contract",
            "draft",
            "--objective",
            "提高吞吐，保持 loss 完全一致",
            "--base-config",
            str(_base_config(tmp_path)),
            "--repo-root",
            str(tmp_path),
            "--out",
            str(contract),
            "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "draft"
    assert load_contract_lock(contract) is None

    assert main(["contract", "show", "--contract", str(contract)]) == 0
    shown = capsys.readouterr().out
    assert "status: unconfirmed" in shown
    assert "确认码" in shown

    assert main(
        [
            "contract",
            "confirm",
            "--contract",
            str(contract),
            "--code",
            "wrong-code",
            "--statement",
            "确认冻结。",
        ]
    ) == 1
    assert "IRSI_CONTRACT_ERROR" in capsys.readouterr().err
    assert load_contract_lock(contract) is None

    assert main(
        [
            "contract",
            "confirm",
            "--contract",
            str(contract),
            "--code",
            payload["confirmation_code"],
            "--statement",
            "确认上述评估边界，开始跑 baseline。",
            "--confirmed-by",
            "user",
            "--json",
        ]
    ) == 0
    lock = json.loads(capsys.readouterr().out)
    assert lock["contract_hash"] == payload["contract_hash"]

    assert main(["contract", "show", "--contract", str(contract), "--json"]) == 0
    shown_json = json.loads(capsys.readouterr().out)
    assert shown_json["status"] == "confirmed"
