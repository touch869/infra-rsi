# Tolerance-based numeric parity

## Why bitwise is not enough

Tensor parallel splits matrix multiplications and vocabulary output. The
floating-point summation order changes, so loss and grad_norm may differ from
the unsharded baseline even when the mathematical result is equivalent.

## Gate

`numeric-parity` compares selected per-step fields:

```text
| candidate - baseline | <= atol + rtol * |baseline|
```

- `fields` defaults to `("loss", "grad_norm")`, but parallel contracts may
  select `("loss",)` because TP/FSDP reduce and scale gradients differently;
  `grad_norm` is diagnostic, not a model-equivalence judgment.
- `rtol` and `atol` are declared in the contract before the run.
- A mismatch at any step is a FAIL, with the first divergent step recorded.
- If the fingerprints are identical, the gate passes immediately.

## What this does not prove

A tolerance gate proves numerical proximity under the declared tolerance, not
bitwise equivalence. The report must state the tolerance, the selected fields
and the observed maximum deviation. For recompute candidates, keep using the
`bitwise` gate.
