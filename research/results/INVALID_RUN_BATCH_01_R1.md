# Batch 01 R1 invalid-run disclosure

The first Batch 01 execution, committed as `9549261`, is **INVALID_RUN** for S27A and its batch summary. After observation, audit found that the read-only S2 V2B comparator was submitted monthly instead of using S2's frozen `SIGNAL_CHANGE_ONLY` policy. That is an incorrect primary comparator, not a performance judgement.

No configuration, strategy signal, data, or decision gate changed. Before any replacement results, the runner is corrected, its comparator submission policy is explicitly frozen in Protocol V2, and the full five-strategy batch is re-executed. Earlier S3C/S4A/S8A/S30 outputs are retained only as the recorded first-run context; the replacement batch summary is authoritative.
