# Invalid run — Batch 02 R1

The first post-freeze S10A historical execution is invalid and must not be used as evidence or a decision record.

`volatility_targeting.py` used pandas `DataFrame.pct_change()` with its default forward-fill behavior.  The frozen protocol requires 20 **valid aligned** daily base-portfolio returns; default filling could manufacture a return across a missing price.  The runner emitted pandas' deprecation warning, which exposed this mismatch.

Correction: use `pct_change(fill_method=None)` before dropping non-aligned return rows.  This does not alter the target volatility, lookback, no-leverage rule, weights, costs, timing, comparator, or decision gates.  It is a correctness correction only.

Protocol V2 must be frozen and committed before rerunning S10A.  S27A is unaffected because its volatility helper already uses explicit valid-return semantics; S4B remains blocked before implementation.
