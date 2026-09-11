# Batch 02 protocol V2 — S10A aligned-return correction

This is a successor freeze for the S10A track only.  It supersedes the S10A implementation identity in [PROTOCOL.md](PROTOCOL.md) after the invalid R1 run documented in [INVALID_RUN_BATCH_02_R1](../../results/INVALID_RUN_BATCH_02_R1.md).  S27A's frozen protocol and its completed historical result are unchanged; S4B remains `BLOCK_S4B_UPSTREAM_DEPENDENCY`.

The sole correction is mechanical: before selecting the trailing 20 observations, S10A constructs base-portfolio returns with `DataFrame.pct_change(fill_method=None).dropna(how="any")`.  Thus a missing source price cannot be forward-filled into an apparent valid aligned return.  The new regression test inserts an internal missing price and verifies the reported realized volatility uses that exact unfilled return series.

Everything else remains exactly as frozen in Protocol V1: the 25/25/25/25 base, 20 valid aligned daily returns, 10% target, [0,1] scale, bond residual, monthly signal/next-observation execution, 10/5 bps costs, static monthly primary comparator, annual S30 context, diagnostics, degeneration filters, and all economic gates.  The invalid R1 files will be overwritten by the sole V2 S10A rerun after this commit.

No historical performance is reported here.  Commit V2 must pass the standard sync, test, lint, format, type, and S2 R1 integrity checks before that rerun.
