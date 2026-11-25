"""Pure transformations for FREE_DATA_CONTRACT_V2. No I/O or strategy logic."""

from __future__ import annotations

from bisect import bisect_left
from datetime import date
from decimal import Decimal
from math import isfinite

import numpy as np
import pandas as pd

CUTOFF = "2026-08-31"


def day(value):
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError(f"invalid date: {value}")
    return value


def decimal(value):
    return Decimal(str(value))


def adjust(symbol, bars, events, start, cutoff=CUTOFF):
    """Assign an in-window event only to its unique next valid close."""
    valid = {}
    for bar in bars:
        t = day(bar["date"])
        if start <= t <= cutoff and all(
            isfinite(bar[k]) and bar[k] > 0 for k in ("volume", "close")
        ):
            if t in valid:
                raise ValueError(f"{symbol} {t}: duplicate bar")
            valid[t] = decimal(bar["close"])
    dates = sorted(valid)
    if not dates:
        raise ValueError(f"{symbol}: no valid in-window price")
    multipliers, audit = {}, []
    for event in sorted(events, key=lambda e: e["date"]):
        t = day(event["date"])
        if not start <= t <= cutoff:
            continue
        label = f"{symbol} {t}"
        i = bisect_left(dates, t)
        if i == 0 or i == len(dates):
            raise ValueError(f"{label}: missing in-window pre/post")
        pre, post = dates[i - 1 : i + 1]
        if post in multipliers:
            raise ValueError(f"{label}: multiple events on effective bar {post}")
        a, b = valid[pre], valid[post]
        detail = dict(event, pre=pre, post=post)
        if event["category"] in (11, 12):
            k = decimal(event["suogu"])
            if not k.is_finite() or k <= 0:
                raise ValueError(f"{label}: invalid split")
            detail.update(s=str(k), r=str(b / a), deviation=str(abs(b * k - a) / a))
            if abs(b * k - a) > Decimal("0.05") * a:
                # Full check including dates, ratio and deviation goes only to the private log.
                print(detail)
                raise ValueError(f"{label}: split direction check exceeds 5%")
        elif event["category"] == 1:
            cash, subprice, stock, sub = (
                decimal(event[key]) for key in ("fenhong", "peigujia", "songzhuangu", "peigu")
            )
            if (
                not all(n.is_finite() for n in (cash, subprice, stock, sub))
                or 10 + stock + sub <= 0
            ):
                raise ValueError(f"{label}: invalid dividend terms/denominator")
            ref = (a * 10 - cash + sub * subprice) / (10 + stock + sub)
            if not ref.is_finite() or ref <= 0:
                raise ValueError(f"{label}: invalid dividend reference")
            k = a / ref
        else:
            raise ValueError(f"{label}: unknown category {event['category']}")
        multipliers[post] = k
        audit.append(dict(detail, multiplier=str(k)))
    values = {}
    factor = Decimal(1)
    for t in dates:
        factor *= multipliers.get(t, 1)
        val = float(valid[t] * factor)
        if not isfinite(float(factor)) or not isfinite(val) or factor <= 0 or val <= 0:
            raise ValueError(f"{symbol} {t}: invalid adjusted price/factor")
        values[t] = val
    series = pd.Series(values, name=symbol)
    series.index = pd.DatetimeIndex(series.index, name="date")
    return series, audit


def iso(t):
    return pd.Timestamp(t).date().isoformat()


def compare(candidate, ref, got):
    """Make the exact axis decision BEFORE intersecting axes for diagnostics."""
    erc = candidate == "S4C_R1"
    tol = 1e-4 if erc else 1e-8
    checks = {
        "date_order": ref.index.equals(got.index),
        "column_order": ref.columns.equals(got.columns),
        "row_count": len(ref) == len(got) == (161 if erc else 103),
        "inception": len(got) > 0 and iso(got.index[0]) == "2013-04-01",
    }
    if erc:
        checks["last_date"] = len(got) > 0 and iso(got.index[-1]) == "2026-08-03"
    missing = list(map(iso, ref.index.difference(got.index)))
    extra = list(map(iso, got.index.difference(ref.index)))
    result = dict(
        missing_dates=missing,
        extra_dates=extra,
        expected_columns=list(ref.columns),
        observed_columns=list(got.columns),
        rows=len(got),
        checks=checks,
        first_difference=None,
        largest_common_weight_difference=None,
    )
    issues = []
    for dates, reason in [(missing, "missing_date"), (extra, "extra_date")]:
        if dates:
            issues.append(dict(date=dates[0], asset=None, reason=reason))
    if not missing and not extra and not checks["date_order"]:
        for a, b in zip(ref.index, got.index, strict=False):
            if a != b:
                issues.append(dict(date=iso(b), asset=None, reason="date_order"))
                break
    if not checks["column_order"] and len(got):
        from itertools import zip_longest

        a, b = next((a, b) for a, b in zip_longest(ref.columns, got.columns) if a != b)
        issues.append(dict(date=iso(got.index[0]), asset=b or a, reason="column_order"))
    unique = all(axis.is_unique for f in (ref, got) for axis in (f.index, f.columns))
    checks["unique_axes"] = unique
    if unique:
        days = ref.index.intersection(got.index, sort=False)
        cols = ref.columns.intersection(got.columns, sort=False)
        a, b = ref.loc[days, cols], got.loc[days, cols]
        delta = (a - b).abs()
        finite = np.isfinite(delta)
        checks["weights"] = bool(delta.le(tol).all().all() and finite.all().all())
        if finite.any().any():
            row, col = np.unravel_index(
                np.argmax(delta.where(finite, -np.inf).to_numpy()), delta.shape
            )
            result["largest_common_weight_difference"] = dict(
                date=iso(days[row]), asset=cols[col], abs_delta=float(delta.iat[row, col])
            )
        for row, col in list(zip(*np.where((~finite | delta.gt(tol)).to_numpy()), strict=False))[
            :1
        ]:
            issues.append(dict(date=iso(days[row]), asset=cols[col], reason="weight"))
        if erc:
            bad_sum = got.sum(axis=1, skipna=False).round(12).ne(1)
            checks["row_sum"] = not bool(bad_sum.any())
            if bad_sum.any():
                issues.append(dict(date=iso(bad_sum.idxmax()), asset=None, reason="row_sum"))
            support = a.gt(0).ne(b.gt(0))
            checks["positive_support"] = not bool(support.any().any()) and checks["column_order"]
            for row, col in list(zip(*np.where(support.to_numpy()), strict=False))[:1]:
                issues.append(dict(date=iso(days[row]), asset=cols[col], reason="support"))
            maxima = (
                ref.loc[days].idxmax(axis=1).ne(got.loc[days].idxmax(axis=1))
                if len(days) and len(got.columns)
                else pd.Series(dtype=bool)
            )
            checks["max_asset"] = not bool(maxima.any())
            if maxima.any():
                t = maxima.idxmax()
                issues.append(dict(date=iso(t), asset=got.loc[t].idxmax(), reason="maximum"))
    result["first_difference"] = min(issues, key=lambda i: i["date"]) if issues else None
    result["passed"] = all(checks.values())
    return result
