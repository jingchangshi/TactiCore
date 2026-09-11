# Batch 01 protocol revision V2

This is a correctness revision of [Protocol V1](PROTOCOL.md), made after the invalid R1 output was observed and disclosed in [INVALID_RUN_BATCH_01_R1](../../results/INVALID_RUN_BATCH_01_R1.md).

## Reason and scope

The S27A primary comparator was incorrectly constructed with monthly target submissions. Its required comparator is frozen S2 V2B, whose submission policy is `SIGNAL_CHANGE_ONLY`. The correction changes only the comparator's execution-weight construction to `build_signal_change_execution_weights(prices, s2_targets(prices, s2))`.

No data, strategy signal, configuration, S27A allocation, gate, other comparator, or hypothesis changes. The full five-strategy batch must be rerun together; the R1 S27A and Batch summary results are invalid.

## V2 frozen identities

- `research/experiments/run_s27_trend_inverse_vol_baseline.py`: `2052e4ec23ca7edb9b2e40cb2d26e9b68ac9443476993b73d3467c98a75723f0`
- `tacticore/strategies/multi_asset_trend.py`: `2a11156f2f44f2cda9774b7c035bed9cb9757a83900b17028f6fd8c65eb7d1a6`
- `config/strategy.toml`: `9935dbdb54f3ea369574f2edfcdba2103c97d539697ff119c7ac9d084931c2ce`

All V1 dataset hashes, parameters, gates, prohibited searches, evaluation-start rules and non-S27 semantics remain unchanged. The V2 protocol-freeze SHA is recorded after its dedicated validated commit.
