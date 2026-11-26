"""Synthetic tests for EXP-V3-10."""

import numpy as np

from research.batches.exp_v3_10_pioneer_alpha.run import lookup_exact_circ_and_dv


def test_exact_circ_and_dv_lookup_no_ffill():
    table = {
        "601088.SH": (
            np.array([20261117, 20261126], dtype=np.int64),
            np.array([2_000_000.0, 2_010_000.0]),
            np.array([5.4, np.nan]),
        )
    }
    cmv, dv = lookup_exact_circ_and_dv(table, "601088.SH", 20261117)
    assert cmv == 2_000_000.0 and dv == 5.4
    # No forward fill onto null date 20261126
    cmv2, dv2 = lookup_exact_circ_and_dv(table, "601088.SH", 20261126)
    assert cmv2 == 2_010_000.0 and dv2 is None
