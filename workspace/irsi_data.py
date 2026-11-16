"""Synthetic packed-text dataset for the Infra-RSI smoke harness.

Returns torch tensors: the trainer's TextPackingCollator concatenates samples
with ``torch.cat`` and expects tensors rather than numpy arrays.
"""

from __future__ import annotations

from typing import Any, Mapping

import torch
from datasets import load_from_disk
from torch.utils.data import Dataset


class PackedTensorDataset(Dataset):
    """Map-style dataset over a saved HF Dataset of packed token records."""

    def __init__(
        self,
        data_path: str,
        sequence_length: int | None = None,
        data_config: Mapping[str, Any] | None = None,
        **_: Any,
    ) -> None:
        self._records = load_from_disk(str(data_path))
        self.sequence_length = int(sequence_length or 2048)
        self.data_config = dict(data_config or {})

    def __len__(self) -> int:
        return len(self._records)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        record = self._records[int(index)]
        input_ids = torch.tensor(record["input_ids"], dtype=torch.long)
        labels = torch.tensor(record["labels"], dtype=torch.long)
        return {"input_ids": input_ids, "labels": labels}
