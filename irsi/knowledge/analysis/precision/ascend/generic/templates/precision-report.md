# <Model / Feature> Numerical Validation Report

> Include the command, source commit, and environment for each measurement.
> Declare the baseline. Mark unavailable measurements [not measured] and
> unavailable internal criteria [pending validation]. Acceptance and the final
> pass/fail decision belong to `hf-model-precision-validation`.

| Field | Value |
|---|---|
| Model / feature | [FILL] |
| Tested axis | [FILL: the single difference between candidate and baseline] |
| Candidate | [FILL: implementation/device, commit, configuration, environment] |
| Baseline | [FILL: implementation/device, commit, configuration, environment] |
| Node | [FILL: same-node, back-to-back A/B] |

## 1. Conclusion

- **Validation outcome (owned by `hf-model-precision-validation`)**: [not measured unless supplied by that layer].
- **First divergence**: [FILL: module/operator/source line and execution order, or no failing comparison].

## 2. Capture

- **Tool and configuration**: msprobe, level=[FILL], step=[FILL].
- **Command**: `python irsi/knowledge/analysis/precision/ascend/generic/scripts/collect_dump.py ...`,
  launched separately for candidate and baseline.
- **Dump paths**: candidate [FILL], baseline [FILL].
- **Internal instrumentation differences, if any**: [pending validation].

## 3. Comparison

- **Command**: `python irsi/knowledge/analysis/precision/ascend/generic/scripts/diff_dump.py --candidate <d1> --baseline <d2>`.
- **First failing item**: [FILL: name, execution order, cosine, maximum relative error].
- **Per-tensor criterion**: bitwise by default; any explicit cosine or
  relative-error tolerance and its justification [FILL].
- **BF16 ties**: tie count [FILL], worst reference-score gap [FILL].
  Apply the below-one-ULP boundary only to qualifying tied selections.

## 4. Validation handoff

State the actual comparison window [FILL]. Acceptance is owned by
`hf-model-precision-validation`; fill this section only when that validation
skill supplies its criteria. Its trajectory criteria are separate from
per-tensor comparison.

| Check | Result | Criterion |
|---|---|---|
| Mean absolute loss error | [not measured] | At most 0.02 |
| Mean relative loss error | [not measured] | At most 2% |
| Gradient-norm trajectory | [not measured] | Same declared error band |
| First step | [not measured] | Close agreement |
| Determinism with the same seed | [not measured] | Same trajectory |
| Checkpoint resume | [not measured] | Continuous trajectory |

## 5. Proposed fix

- **Root-cause assessment**: [FILL: based on the first divergence].
- **Proposed correction**: [FILL].
- **Regression method**: [FILL: repeat identical inputs and verify recovery].

## 6. Evidence index

- Commands, commits, and environments: [FILL].
- Comparison tables, dumps, and logs: [FILL].
