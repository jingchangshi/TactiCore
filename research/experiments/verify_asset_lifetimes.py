#!/usr/bin/env python3
"""将 version-controlled universe 生命周期与 RQAlpha bundle metadata 有界交叉核验。"""

import pickle
from pathlib import Path

import pandas as pd

from tacticore.data.universe import load_universe

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = Path.home() / ".rqalpha/bundle/instruments.pk"


def main() -> None:
    universe = load_universe(ROOT / "config/universe.csv")
    entries = pickle.loads(BUNDLE.read_bytes())
    upstream = {entry["order_book_id"]: entry for entry in entries}
    rows = []
    for symbol, item in universe.iterrows():
        entry = upstream.get(item.rqalpha_symbol)
        listed = pd.Timestamp(entry["listed_date"]) if entry else pd.NaT
        local = pd.Timestamp(item.start_date)
        rows.append(
            {
                "symbol": symbol,
                "local_start_date": local.date().isoformat(),
                "rqalpha_listed_date": listed.date().isoformat() if pd.notna(listed) else "MISSING",
                "match": bool(pd.notna(listed) and local == listed),
            }
        )
    report = pd.DataFrame(rows)
    report.to_csv(ROOT / "research/results/asset_lifetime_audit_v1.csv", index=False)
    if not report["match"].all():
        raise SystemExit("asset lifetime metadata 与 RQAlpha 不一致；未自动覆写 universe.csv")
    print(report.to_csv(index=False))


if __name__ == "__main__":
    main()
