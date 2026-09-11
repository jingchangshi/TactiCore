# Batch 02 External Evidence Gate

Evidence snapshot date: 2026-09-11. This review precedes any Batch 02 historical performance run.

## S27A robustness — `VOL_SCALED_TREND`

- Canonical mapping: time-series trend plus volatility-based active sizing.
- Tier/action: `E3_MIXED_CONDITIONAL` / `LOCAL_ADJUDICATION`.
- Mature portion: MOP (2012, `10.1016/j.jfineco.2011.11.003`) documents multi-asset futures TSMOM; Hurst/Ooi/Pedersen extend long-history trend evidence.
- Conditional portion: Kim/Tse/Wald (2016, `10.1016/j.finmar.2016.05.003`) finds futures TSMOM alpha can be driven by volatility scaling. Inverse-vol sizing is an allocation method, not alpha.
- Local gap: whether the frozen long-only ETF transfer's 200/60 result survives predeclared parameter, period and cost stability checks. Batch 01 added only this local transfer evidence.

## S4B ERC — `ERC_RISK_PARITY`

- Canonical mapping: vanilla equal-risk-contribution/risk parity.
- Tier/action: `E2_ESTABLISHED_METHOD` / `UPSTREAM_COMPARE`; Maillard/Roncalli/Teiletche is canonical (`10.3905/JPM.2010.36.4.060`).
- Upstream result: current Riskfolio-Lib 7.3.0 officially supports Python ≥3.10, but its `scipy>=1.16.1` dependency cannot resolve across TactiCore's supported Python `>=3.10,<3.13`; `uv sync --extra research` fails for Python 3.10 compatibility.
- Decision before implementation: `BLOCK_S4B_UPSTREAM_DEPENDENCY`. No local solver, older-version substitution, or dependency-range narrowing is authorized by this Goal.

## S10A volatility targeting — `VOL_TARGETING`

- Canonical mapping: volatility targeting / volatility-managed portfolios.
- Tier/action: `E3_MIXED_CONDITIONAL` / `LOCAL_ADJUDICATION`.
- Supporting evidence: Moreira/Muir (2017, `10.1111/jofi.12513`) studies managed factor and carry portfolios.
- Contradiction: Cederburg/O'Doherty/Wang/Yan (2020, `10.1016/j.jfineco.2020.04.015`) finds no systematic direct real-time outperformance across 103 equity strategies.
- Domain mismatch: the literature includes factor portfolios, leverage and normalizations unlike an unlevered long-only China/global ETF implementation. Local gap is the frozen 10%/20-day no-leverage S30 transfer against a monthly static control.
