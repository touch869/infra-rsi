# Bitwise numeric fingerprint gate

## What is checked

- For each step, compare `loss` and `grad_norm` with the baseline.
- The baseline fingerprint is frozen before any candidate runs.
- Recompute should be mathematically equivalent, so a correct candidate must be bitwise identical.
- A mismatch is a crash, even if the candidate is faster.
- The first divergent step should be recorded.

## Why it matters

Performance gain is meaningless if numerics change. The numeric gate is a binary PASS/FAIL check; it does not use the performance noise band.

## Constraints

- Do not compare only the final loss; compare every step's loss and grad_norm.
- Do not accept a candidate whose numeric hash differs from the baseline.
- If the baseline fingerprint is missing, do not proceed to candidate comparisons.
- `bitwise` is for recompute and other exact-equivalence changes. Tensor-parallel
  and FSDP candidates change floating-point reduction order, so use
  `numeric-parity` with a contract-declared tolerance; record the fields and
  maximum deviation.

## Archive use

The report should record the baseline numeric hash and the candidate's numeric verdict so the gain is traceable.
