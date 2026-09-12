# Batch 05 protocol V3 — INVALID_RUN artifact namespace correction

Protocol V2 的 successful in-memory S27/S10 replays wrote S27 native summary to the pre-existing Batch 04 filename `s27a_pit_corrected_summary_v1.csv`. Batch 04 artifact has been restored. This revision assigns unique Batch 05 names: S27 execution-review files use `s27a_rqalpha_execution_*_v2`, S10 uses `s10a_rqalpha_execution_*_v1`, while the required PIT-corrected frozen target artifacts retain their specified names.

No target, data, PIT rule, callback, comparator, parameter, gate, decision set, or prior result is changed. The V2 run is `INVALID_RUN`; V3 requires a complete rerun before any results are accepted.
