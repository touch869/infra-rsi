"""Build the synthetic packed dataset used by the phase-1 contracts.

The run host stores the dataset at ``/root/irsi-workspace/data/tiny-packed``.
This script regenerates an equivalent dataset from a fixed seed so the flow is
reproducible from the repository alone; token values differ from the original
run, which does not matter because gates compare trials inside one run.

Layout matches what ``irsi_data.PackedTensorDataset`` expects:

- ``input_ids``: int32, ``seq_len`` tokens per record
- ``labels``: int64, next-token shifted, ``-100`` at the last position
- ``cu_seqlens``: int64, one document boundary per ``doc_len`` tokens
"""

from __future__ import annotations

import argparse

import numpy as np
from datasets import Dataset


def build(
    records: int,
    seq_len: int,
    doc_len: int,
    vocab_size: int,
    seed: int,
) -> Dataset:
    if seq_len % doc_len != 0:
        raise ValueError("seq_len must be a multiple of doc_len")
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for _ in range(records):
        tokens = rng.integers(0, vocab_size, size=seq_len, dtype=np.int64)
        labels = np.empty_like(tokens)
        labels[:-1] = tokens[1:]
        labels[-1] = -100
        rows.append(
            {
                "input_ids": tokens.astype(np.int32).tolist(),
                "labels": labels.tolist(),
                "cu_seqlens": list(range(0, seq_len + 1, doc_len)),
            }
        )
    return Dataset.from_list(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/tiny-packed")
    parser.add_argument("--records", type=int, default=64)
    parser.add_argument("--seq-len", type=int, default=2048)
    parser.add_argument("--doc-len", type=int, default=1024)
    parser.add_argument("--vocab-size", type=int, default=32000)
    parser.add_argument("--seed", type=int, default=20261112)
    args = parser.parse_args()

    dataset = build(
        records=args.records,
        seq_len=args.seq_len,
        doc_len=args.doc_len,
        vocab_size=args.vocab_size,
        seed=args.seed,
    )
    dataset.save_to_disk(args.out)
    print(f"wrote {len(dataset)} records to {args.out}")


if __name__ == "__main__":
    main()
