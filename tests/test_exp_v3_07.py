"""Synthetic tests for EXP-V3-07."""

import numpy as np
import pandas as pd

from research.batches.exp_v3_07_lowvol_risk_budget.run import compute_bucket_shares


def test_inv_vol_and_erc_allocate_highest_to_lowvol_bucket():
    rng = np.random.default_rng(7)
    ret = pd.DataFrame(
        {
            "VALUE": rng.normal(0.0, 0.015, 60),
            "GROWTH": rng.normal(0.0, 0.030, 60),
            "LOW_VOL": rng.normal(0.0, 0.008, 60),
        }
    )
    inv = compute_bucket_shares(ret, "inv_vol")
    erc = compute_bucket_shares(ret, "erc")
    assert abs(sum(inv.values()) - 1.0) < 1e-9
    assert abs(sum(erc.values()) - 1.0) < 1e-9
    assert inv["LOW_VOL"] > inv["VALUE"] > inv["GROWTH"]
    assert erc["LOW_VOL"] > erc["VALUE"] > erc["GROWTH"]
