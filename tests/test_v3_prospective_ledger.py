"""V3 前瞻台账的合成测试（对齐 AMENDMENT_2 的修正实现）。

全部使用 `tmp_path`、合成 brief、合成 SQLite 账户库、合成交易日历与合成 I/O 故障；
不读取任何真实 2026-11 之后的市场/账户数据，不写生产 DB，不产生真实观测。
"""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from research.experiments import v3_prospective_ledger as ledger

AS_OF = "20261126"
NEXT_DAY = "20261127"
GENERATED_AT = "2026-11-26T20:00:00+08:00"  # 上海 20:00，收盘后
NOW = datetime(2026, 11, 26, 13, 0, tzinfo=timezone.utc)  # UTC 13:00 = 上海 21:00 当日
POLICY_HASH = "a" * 64
REPORT_ID = "b" * 64

ACCOUNT_EVENT_DDL = """
CREATE TABLE account_event (
  event_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  occurred_on TEXT NOT NULL,
  settled_on TEXT,
  ts_code TEXT,
  quantity INTEGER,
  price_milli INTEGER,
  gross_cents INTEGER,
  fee_cents INTEGER NOT NULL DEFAULT 0,
  tax_cents INTEGER NOT NULL DEFAULT 0,
  cash_delta_cents INTEGER NOT NULL,
  ratio_num INTEGER,
  ratio_den INTEGER,
  reverses_event_id TEXT,
  reversed_by TEXT,
  note TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);
CREATE TABLE account_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _leg(**overrides) -> dict:
    leg = {
        "side": "BUY",
        "ts_code": "511010.SH",
        "name": "国债ETF",
        "quantity": 100,
        "lot_size": 100,
        "lots": 1,
        "price_milli": 100000,
        "gross_cents": 100000,
        "fees_cents": 5,
        "net_cents": 100005,
        "quote_trade_date": AS_OF,
        "executable": True,
        "reason": "P3_SYNTHETIC",
    }
    leg.update(overrides)
    return leg


def _action(code: str = "P3-SUPER-ETF-REBALANCE", rank: int = 1, executable: bool = True) -> dict:
    return {
        "priority": "P3",
        "code": code,
        "kind": "ROTATE",
        "rank": rank,
        "title": "合成动作",
        "reasons": ["合成理由"],
        "counter_evidence": ["合成反证"],
        "legs": [_leg(executable=executable)],
        "illustrative": None if executable else {"executable": False},
        "fees_cents": 5,
        "fees_assumed": True,
        "triggers": ["合成触发"],
        "invalidation_conditions": ["合成失效"],
        "risk_impact": ["合成风险"],
        "fact_meta": {"as_of": AS_OF, "source": "fixture", "quality": "OK", "claim_status": "FACT"},
    }


def _cockpit() -> dict:
    return {
        "schema": "v3-offensive-cockpit/1.0",
        "as_of_trade_date": AS_OF,
        "policy_release": {
            "strategy_id": "V3_OFFENSIVE_LOW_FREQ_SYSTEM",
            "version": "v3.2.0",
            "content_hash": POLICY_HASH,
            "production_admission": "APPROVED_FOR_ACCOUNT",
            "bp1_pullback_enabled": True,
            "bp2_breakout_enabled": False,
        },
        "principal": {
            "initial_principal_cents": 10_000_000,
            "current_nav_cents": 6_800_000,
            "to_principal_gap_cents": 3_200_000,
            "to_principal_return_needed_pct": 47.06,
            "loss_from_principal_pct": 32.0,
        },
        "market_regime": {
            "regime": "DEFENSIVE",
            "regime_label_zh": "防御",
            "raw_regime": "DEFENSIVE",
            "hysteresis_held": False,
            "crash_override": False,
            "style": "VALUE_LEADING",
            "target_equity_bps": 1500,
            "defensive_cash_bps": 8500,
            "pct_above_ma60": 0.1,
            "amount_vs_ma20": 1.0,
            "limit_down": 3,
            "hs300_above_ma60": False,
        },
        "router": {
            "effective_regime": "DEFENSIVE",
            "circuit_breaker_status": "NORMAL",
            "deconcentration_preemptive_active": False,
            "policy_version": "v3.2.0",
            "hwm_nav_cents": 10_000_000,
            "hwm_drawdown_pct": 32.0,
            "sub_strategies": {"s_stock_swing": "STOP_ONLY"},
            "sub_strategies_zh": {"s_stock_swing": "仅止损"},
        },
        "deconcentration": {
            "plan_present": True,
            "ts_code": "159558.SZ",
            "plan_status": "ACTIVE",
            "plan_mode": "BOTTOM_GRIND_25",
            "recommended_sell_shares": 0,
            "recommended_buy_shares": 0,
            "tranches": [{"tranche_no": 1, "status": "PENDING"}],
            "grind_guards": {"reload_target_cny": 1.23},
            "status_summary_zh": "合成状态",
        },
        "reconciliation_reminder": {"lag_trade_days": 1, "needs_reminder": False},
        "actions_summary": [],
    }


def _holding(**overrides) -> dict:
    holding = {
        "ts_code": "511010.SH",
        "name": "国债ETF",
        "quantity": 1000,
        "weight": 0.15,
        "market_value_cents": 100_000,
        "price_milli": 100_000,
        "price_source": "server_cache_close",
        "latest_bar_date": AS_OF,
        "bar_quality": "READY",
        "stance": "REDUCE",
        "reasons": ["合成理由不应进入 VALUATION"],
        "counter_evidence": ["合成反证"],
        "research": {"conditions": [{"stage": "WATCH"}]},
        "diluted_cost_per_share": 1.0,
        "diluted_total_cost_cents": 100_000,
        "cost_basis": "broker_diluted",
    }
    holding.update(overrides)
    return holding


def make_brief(
    *,
    as_of: str = AS_OF,
    generated_at: str = GENERATED_AT,
    status: str = "ACTIONABLE",
    actions: list[dict] | None = None,
    cockpit: dict | None | str = "default",
    holdings: list[dict] | None = None,
    concentration: dict | None | str = "default",
    triggers: list[str] | None = None,
) -> dict:
    if actions is None:
        actions = [_action()] if status in {"ACTIONABLE", "ILLUSTRATIVE"} else []
    if cockpit == "default":
        cockpit = _cockpit()
    if status == "ILLUSTRATIVE":
        for action in actions:
            for leg in action["legs"]:
                leg["executable"] = False
    if concentration == "default":
        concentration = {
            "hhi": 0.2,
            "effective_positions": 4.0,
            "top_position": {"ts_code": "159558.SZ", "weight": 0.4},
            "equity_weight": 0.7,
            "cash_ratio": 0.3,
        }
    no_action_reason = None
    if status == "NO_ACTION":
        no_action_reason = "没有可复核的证据支持下一交易日的交易动作"
    elif status == "DATA_INSUFFICIENT":
        no_action_reason = "DATA_INSUFFICIENT：核心行情缺失"
    if triggers is None:
        # 上游自由文本触发条件：可夹带份数与目标价，绝不能进 SIGNAL。
        triggers = [
            "159558.SZ 磨底降本机动槽（300 份）止盈线：+7.5% 目标价 1.234 元",
            "跨境 ETF 买入红线：最新净值折溢价高于 +2.5% 或净值滞后超 3 个交易日一律拦截禁买",
        ]
    return {
        "schema": ledger.BRIEF_SCHEMA,
        "brief_source": "generated",
        "report_id": REPORT_ID,
        "as_of_trade_date": as_of,
        "expected_next_trade_date": NEXT_DAY if as_of == AS_OF else None,
        "status": status,
        "actionable": status == "ACTIONABLE",
        "generated_at": generated_at,
        "account_id": "real-main",
        "account_id_source": "explicit",
        "account_status": "REAL_ACCOUNT_VERIFIED",
        "first_section": {
            "heading": "合成",
            "count": len(actions),
            "actions": copy.deepcopy(actions),
            "no_action_reason": no_action_reason,
            "observation_triggers": triggers,
        },
        "execution_plan": {"count": len(actions), "actions": copy.deepcopy(actions)},
        "v3_cockpit": copy.deepcopy(cockpit) if cockpit is not None else None,
        "holdings": copy.deepcopy(holdings if holdings is not None else [_holding()]),
        "concentration": copy.deepcopy(concentration) if concentration is not None else None,
        "data_quality": {"status": "OK", "summary_status": "OK", "missing_fields": []},
    }


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def init(tmp_path: Path) -> Path:
    root = tmp_path / "ledger"
    ledger.init_ledger(root)
    return root


def calendar(tmp_path: Path, days: list[str] | None = None) -> Path:
    return make_calendar_db(tmp_path, days if days is not None else [AS_OF, NEXT_DAY])


def ingest(
    tmp_path: Path,
    brief: dict,
    *,
    name: str = "brief.json",
    calendar_db: Path | None = None,
) -> dict:
    resolved_calendar = calendar_db if calendar_db is not None else calendar(tmp_path)
    return ledger.ingest_brief(
        write_json(tmp_path / name, brief),
        root=tmp_path / "ledger",
        calendar_db=resolved_calendar,
    )


def counts(root: Path) -> dict[str, int]:
    return {
        record_type: len(ledger.read_events(root, record_type))
        for record_type in ledger.RECORD_FILES
    }


def snapshot_bytes(root: Path) -> dict[str, bytes]:
    snapshot = {name: (root / name).read_bytes() for name in ledger.RECORD_FILES.values()} | {
        "manifest.json": (root / "manifest.json").read_bytes()
    }
    baseline = root / ledger.POLICY_BASELINE_FILENAME
    if baseline.is_file():
        snapshot[ledger.POLICY_BASELINE_FILENAME] = baseline.read_bytes()
    return snapshot


def make_account_db(tmp_path: Path) -> Path:
    path = tmp_path / "portfolio.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(ACCOUNT_EVENT_DDL)
        connection.execute(
            "INSERT INTO account_meta (key, value) VALUES (?, ?)",
            ("real_account_verified:real-main", "1"),
        )
        connection.executemany(
            "INSERT INTO account_event ("
            + ", ".join(ledger.ACCOUNT_EVENT_COLUMNS)
            + ") VALUES ("
            + ", ".join("?" for _ in ledger.ACCOUNT_EVENT_COLUMNS)
            + ")",
            [
                (
                    "fill-1",
                    "real-main",
                    "TRADE_BUY",
                    NEXT_DAY,
                    None,
                    "511010.SH",
                    100,
                    100_000,
                    10_000_000,
                    5,
                    0,
                    -10_000_005,
                    None,
                    None,
                    None,
                    None,
                    "合成券商成交",
                    "broker_statement",
                    "2026-11-27T01:00:00Z",
                ),
                (
                    "fill-synth",
                    "real-main",
                    "TRADE_SELL",
                    NEXT_DAY,
                    NEXT_DAY,
                    "511010.SH",
                    100,
                    100_000,
                    10_000_000,
                    0,
                    0,
                    9_999_990,
                    None,
                    None,
                    None,
                    None,
                    "合成测试成交",
                    "synthetic",
                    "2026-11-27T01:00:00Z",
                ),
                (
                    "fill-old",
                    "real-main",
                    "TRADE_BUY",
                    "20261125",
                    None,
                    "511010.SH",
                    100,
                    100_000,
                    10_000_000,
                    5,
                    0,
                    -10_000_005,
                    None,
                    None,
                    None,
                    None,
                    "窗口前成交",
                    "broker_statement",
                    "2026-11-25T01:00:00Z",
                ),
                (
                    "fill-reversed",
                    "real-main",
                    "TRADE_BUY",
                    NEXT_DAY,
                    None,
                    "511010.SH",
                    100,
                    100_000,
                    10_000_000,
                    5,
                    0,
                    -10_000_005,
                    None,
                    None,
                    None,
                    "rev-1",
                    "已撤销成交",
                    "broker_statement",
                    "2026-11-27T01:00:00Z",
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return path


_CALENDAR_SEQ = {"n": 0}


def make_calendar_db(tmp_path: Path, days: list[str], *, closed: list[str] | None = None) -> Path:
    _CALENDAR_SEQ["n"] += 1
    path = tmp_path / f"ashare-{_CALENDAR_SEQ['n']}.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE trade_cal ("
            "cal_date TEXT PRIMARY KEY, is_open INTEGER, pretrade_date TEXT)"
        )
        connection.executemany(
            "INSERT INTO trade_cal (cal_date, is_open, pretrade_date) VALUES (?, 1, NULL)",
            [(day,) for day in days],
        )
        connection.executemany(
            "INSERT INTO trade_cal (cal_date, is_open, pretrade_date) VALUES (?, 0, NULL)",
            [(day,) for day in (closed or [])],
        )
        connection.commit()
    finally:
        connection.close()
    return path


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TACTICORE_V3_LEDGER_CALENDAR_DB", raising=False)
    monkeypatch.setattr(ledger, "utc_now", lambda: NOW)


# --------------------------------------------------------------------------------------
# Init and manifest
# --------------------------------------------------------------------------------------


def test_init_creates_manifest_and_empty_evidence_files(tmp_path: Path) -> None:
    root = init(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ledger_version"] == ledger.LEDGER_VERSION
    assert manifest["protocol_commit"] == ledger.PROTOCOL_COMMIT
    assert manifest["earliest_eligible_day"] == "20261126"
    assert manifest["account_id"] == "real-main"
    assert counts(root) == {name: 0 for name in ledger.RECORD_FILES}
    assert oct((root / "manifest.json").stat().st_mode & 0o777) == "0o600"


def test_init_refuses_to_overwrite_existing_manifest(tmp_path: Path) -> None:
    root = init(tmp_path)
    with pytest.raises(ledger.LedgerRefusal, match="已初始化"):
        ledger.init_ledger(root)


def test_manifest_tampering_is_detected(tmp_path: Path) -> None:
    root = init(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["earliest_eligible_day"] = "20261125"
    write_json(root / "manifest.json", manifest)
    with pytest.raises(ledger.LedgerCorruption, match="manifest.earliest_eligible_day"):
        ledger.load_manifest(root)


# --------------------------------------------------------------------------------------
# AMENDMENT_2 #3: close window and trusted calendar
# --------------------------------------------------------------------------------------


def test_close_window_accepts_after_1500_on_an_open_day(tmp_path: Path) -> None:
    root = init(tmp_path)
    brief = make_brief(generated_at="2026-11-26T15:00:00+08:00")
    result = ingest(tmp_path, brief)
    assert result["status"] == "INGESTED"
    assert counts(root)["SIGNAL"] == 1


def test_brief_generated_at_1459_is_rejected(tmp_path: Path) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    brief = make_brief(generated_at="2026-11-26T14:59:59+08:00")
    with pytest.raises(ledger.LedgerRefusal, match="15:00:00"):
        ingest(tmp_path, brief)
    assert snapshot_bytes(root) == before


def test_brief_generated_1459_imported_1501_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    brief = make_brief(generated_at="2026-11-26T14:59:00+08:00")
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 26, 7, 1, tzinfo=timezone.utc)
    )  # 上海 15:01，仍在当日窗口内
    with pytest.raises(ledger.LedgerRefusal, match="15:00:00"):
        ingest(tmp_path, brief)
    assert snapshot_bytes(root) == before


def test_locked_clock_recheck_uses_the_clock_after_acquiring_the_flock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B 反例 1/7：真实 flock 竞争下，拿到锁后必须以新时钟重校窗口。

    预检时钟 23:59:59 合法；持锁线程在锁内把时钟推到次日 00:00 后释放 →
    等待线程拿到锁再校验即拒绝，零写入。
    """
    import threading
    import time as time_module

    root = init(tmp_path)
    calendar_db = calendar(tmp_path)
    brief_path = write_json(tmp_path / "brief.json", make_brief())
    clock = {"now": datetime(2026, 11, 26, 15, 59, 59, tzinfo=timezone.utc)}  # 上海 23:59:59
    monkeypatch.setattr(ledger, "utc_now", lambda: clock["now"])
    order: list[str] = []
    errors: list[BaseException] = []
    results: list[dict] = []

    def holder() -> None:
        with ledger._writer_lock(root):
            order.append("holder-in")
            clock["now"] = datetime(2026, 11, 26, 16, 0, 0, tzinfo=timezone.utc)  # 次日 00:00
            time_module.sleep(0.2)
            order.append("holder-out")

    def waiter() -> None:
        try:
            result = ledger.ingest_brief(
                brief_path, root=root, calendar_db=calendar_db
            )
            results.append(result)
        except BaseException as error:  # noqa: BLE001 - 线程异常留作断言
            errors.append(error)

    holder_thread = threading.Thread(target=holder)
    holder_thread.start()
    time_module.sleep(0.05)
    waiter_thread = threading.Thread(target=waiter)
    waiter_thread.start()
    holder_thread.join(timeout=10)
    waiter_thread.join(timeout=10)
    assert order == ["holder-in", "holder-out"]
    assert results == []
    assert len(errors) == 1
    assert isinstance(errors[0], ledger.LedgerRefusal)
    assert "跨午夜" in str(errors[0])
    assert ledger.read_events(root, "SIGNAL") == []
    assert ledger.verify_ledger(root)["total_events"] == 0


def test_source_byte_change_is_a_conflict_not_idempotent_noop(tmp_path: Path) -> None:
    """B 反例 2：同一 brief 仅多一个换行 → 源 SHA 变 → 冲突，不得 NOOP。"""
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    before = snapshot_bytes(root)
    path = tmp_path / "brief.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ledger.LedgerConflict, match="append-only"):
        ledger.ingest_brief(path, root=root, calendar_db=calendar(tmp_path, [AS_OF, NEXT_DAY]))
    assert snapshot_bytes(root) == before


def test_reformat_identical_semantics_with_new_bytes_is_a_conflict(tmp_path: Path) -> None:
    """B 反例 2：语义相同但重新序列化（缩进不同）也会改源 SHA → 冲突。"""
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    before = snapshot_bytes(root)
    path = tmp_path / "brief.json"
    path.write_text(
        json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(ledger.LedgerConflict, match="append-only"):
        ledger.ingest_brief(path, root=root, calendar_db=calendar(tmp_path, [AS_OF, NEXT_DAY]))
    assert snapshot_bytes(root) == before


def test_broken_policy_baseline_blocks_every_later_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B 反例 8：baseline 与 SIGNAL 不一致时，任何 append 前必须先做完整 verify。"""
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    baseline = json.loads((root / ledger.POLICY_BASELINE_FILENAME).read_text(encoding="utf-8"))
    baseline["content_hash"] = "d" * 64  # 合法格式，但与 SIGNAL 不一致
    write_json(root / ledger.POLICY_BASELINE_FILENAME, baseline)
    with pytest.raises(ledger.LedgerCorruption, match="policy_baseline"):
        ledger.verify_ledger(root)
    before = snapshot_bytes(root)
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    db = make_account_db(tmp_path)
    with pytest.raises(ledger.LedgerCorruption, match="policy_baseline"):
        ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    assert snapshot_bytes(root) == before


def test_unexecuted_reason_cannot_be_derived_from_matching_fills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B 反例 4：未执行原因只能由人类显式输入；同日同码同向成交不产生也不清空。"""
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    db = make_account_db(tmp_path)
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    assert ledger.read_events(root, "UNEXECUTED_REASON") == []
    report = ledger.status_report(root)
    recommendation_id = report["recommendation_review"][0]["recommendation_event_id"]
    assert recommendation_id in report["unresolved_recommendation_event_ids"]
    assert (
        report["recommendation_review"][0]["unexecuted_reason_event_id"] is None
    )


def test_brief_imported_after_midnight_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    # 日报在 D 23:59 生成；台账直到 D+1 00:01（上海）才导入 → 拒绝，不补写。
    brief = make_brief(generated_at="2026-11-26T23:59:00+08:00")
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 26, 16, 1, tzinfo=timezone.utc)
    )  # 上海 2026-11-27 00:01
    with pytest.raises(ledger.LedgerRefusal, match="跨午夜"):
        ingest(tmp_path, brief)
    assert snapshot_bytes(root) == before


def test_brief_imported_before_generation_is_rejected(tmp_path: Path) -> None:
    brief = make_brief(generated_at="2026-11-26T20:00:00+08:00")
    with pytest.raises(ledger.LedgerRefusal, match="不在"):
        ledger._validate_brief(
            brief,
            account_id="real-main",
            now=datetime(2026, 11, 26, 11, 0, tzinfo=timezone.utc),  # 上海 19:00
            calendar_db=calendar(tmp_path),
        )


def test_closed_day_brief_is_rejected(tmp_path: Path) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    # 2026-11-28 是周六；日历明确标记休市。
    weekend_day = "20261128"
    closed_calendar = make_calendar_db(tmp_path, [AS_OF, NEXT_DAY], closed=[weekend_day])
    brief = make_brief(as_of=weekend_day, generated_at="2026-11-28T20:00:00+08:00")
    brief["expected_next_trade_date"] = "20261130"
    with pytest.raises(ledger.LedgerRefusal, match="开市日"):
        ingest(tmp_path, brief, calendar_db=closed_calendar)
    assert snapshot_bytes(root) == before


def test_unknown_calendar_day_is_rejected(tmp_path: Path) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    brief = make_brief(as_of="20261130", generated_at="2026-11-30T20:00:00+08:00")
    brief["expected_next_trade_date"] = "20261201"
    with pytest.raises(ledger.LedgerRefusal, match="开市日"):
        ingest(tmp_path, brief, calendar_db=calendar(tmp_path, [AS_OF, NEXT_DAY]))
    assert snapshot_bytes(root) == before


def test_missing_calendar_refuses_the_whole_run(tmp_path: Path) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    with pytest.raises(ledger.LedgerRefusal, match="交易日历未知"):
        ledger.ingest_brief(
            write_json(tmp_path / "brief.json", make_brief()), root=root, calendar_db=None
        )
    assert snapshot_bytes(root) == before


def test_explicitly_reversed_calendar_row_is_rejected(tmp_path: Path) -> None:
    brief = make_brief()
    closed = make_calendar_db(tmp_path, [NEXT_DAY], closed=[AS_OF])
    with pytest.raises(ledger.LedgerRefusal, match="开市日"):
        ledger._validate_brief(
            brief, account_id="real-main", now=NOW, calendar_db=closed
        )


# --------------------------------------------------------------------------------------
# AMENDMENT_2 #4: SIGNAL / VALUATION / RECOMMENDATION projections
# --------------------------------------------------------------------------------------


def test_signal_does_not_carry_observation_trigger_text(tmp_path: Path) -> None:
    root = init(tmp_path)
    brief = make_brief()
    brief["first_section"]["observation_triggers"] = [
        "合成观察触发：300 份止盈线 1.234 元，目标价 1.250",
    ]
    ingest(tmp_path, brief)
    signal = ledger.read_events(root, "SIGNAL")[0]
    assert "decision" in signal["content"]
    assert "observation_triggers" not in signal["content"]["decision"]
    assert "trigger_codes" not in signal["content"]["decision"]
    assert ledger.OBSERVATION_TRIGGERS_UNPROJECTED in signal["missing_fields"]
    serialized = json.dumps(signal, ensure_ascii=False)
    assert "300 份" not in serialized
    assert "1.234" not in serialized
    assert "目标价" not in serialized


def test_signal_rejects_leg_quantity_price_and_fill_fields(tmp_path: Path) -> None:
    root = init(tmp_path)
    brief = make_brief()
    brief["v3_cockpit"]["deconcentration"]["recommended_sell_shares"] = 0
    brief["v3_cockpit"]["deconcentration"]["legs"] = [
        {"side": "SELL", "ts_code": "511010.SH", "quantity": 100, "price_milli": 1}
    ]
    # 上游额外键被白名单投影掉：SIGNAL 持久化内容不得携带腿/份数/价格或成交字段。
    ingest(tmp_path, brief)
    signal = ledger.read_events(root, "SIGNAL")[0]
    deconcentration = signal["content"]["deconcentration_state"]
    assert set(deconcentration) <= ledger.SIGNAL_DECONCENTRATION_KEYS
    for forbidden in ("legs", "recommended_sell_shares", "recommended_buy_shares", "quantity",
                      "price_milli", "fees_cents", "executable"):
        assert forbidden not in json.dumps(signal["content"], ensure_ascii=False)
    # 已落盘的 SIGNAL content 若被篡改为携带成交字段，verify 必须拒绝。
    forged = copy.deepcopy(signal["content"])
    forged["deconcentration_state"]["quantity"] = 100
    with pytest.raises(ledger.LedgerCorruption):
        ledger._validate_signal_content(forged, tuple(signal["missing_fields"]))


def test_signal_only_projects_whitelisted_deconcentration_keys() -> None:
    cockpit = _cockpit()
    projected = ledger._project_typed_block(
        cockpit["deconcentration"],
        label="v3_cockpit.deconcentration",
        types=ledger.SIGNAL_DECONCENTRATION_TYPES,
    )
    assert projected is not None
    assert "recommended_sell_shares" not in projected
    assert "recommended_buy_shares" not in projected
    assert "ts_code" not in projected
    assert "tranches" not in projected
    assert "grind_guards" not in projected
    assert "status_summary_zh" not in projected
    assert projected["plan_mode"] == "BOTTOM_GRIND_25"


def test_signal_accepts_structured_trigger_codes_from_upstream(tmp_path: Path) -> None:
    root = init(tmp_path)
    brief = make_brief()
    brief["first_section"]["trigger_codes"] = ["ACCOUNT_LIFELINE", "CROSS_BORDER_PREMIUM"]
    ingest(tmp_path, brief)
    signal = ledger.read_events(root, "SIGNAL")[0]
    assert signal["content"]["decision"]["trigger_codes"] == [
        "ACCOUNT_LIFELINE",
        "CROSS_BORDER_PREMIUM",
    ]
    assert ledger.OBSERVATION_TRIGGERS_UNPROJECTED not in signal["missing_fields"]


def test_unknown_trigger_code_is_rejected(tmp_path: Path) -> None:
    brief = make_brief()
    brief["first_section"]["trigger_codes"] = ["NOT_A_REAL_CODE"]
    with pytest.raises(ledger.LedgerRefusal, match="封闭枚举"):
        ledger._validate_brief(
            brief,
            account_id="real-main",
            now=NOW,
            calendar_db=make_calendar_db(tmp_path, [AS_OF]),
        )


def test_valuation_holding_drops_stance_and_recommendation_semantics(tmp_path: Path) -> None:
    root = init(tmp_path)
    assert _holding()["stance"] == "REDUCE"
    ingest(tmp_path, make_brief())
    valuation = ledger.read_events(root, "VALUATION")[0]
    holding = valuation["content"]["holdings"][0]
    assert "stance" not in holding
    for stripped in ("reasons", "counter_evidence", "research"):
        assert stripped not in holding
    assert set(holding) <= ledger.VALUATION_HOLDING_KEYS
    assert "REDUCE" not in json.dumps(valuation, ensure_ascii=False)


def test_data_quality_free_text_is_not_projected_into_signal(tmp_path: Path) -> None:
    """A2:35 不得用 data_quality/detail 作份数/价格自由文本后门。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["data_quality"] = {
        "status": "OK",
        "summary_status": "OK",
        "missing_fields": [],
        "quotes": {
            "ready": ["511010.SH"],
            "stale": [],
            "not_ready": [],
            "missing": [],
            "detail": "行情：300 份 目标价 1.234 元",
        },
        "market_report": {
            "available": True,
            "report_id": "f" * 64,
            "as_of_trade_date": AS_OF,
            "freshness": "same_day",
            "detail": "市场日报 500 份 参考价 9.99 元",
        },
        "screening": {"status": "READY", "missing_tables": []},
        "tiers": {
            "market_data": {"status": "READY", "as_of": AS_OF, "detail": "目标价 1.234"},
        },
        "notes": ["目标价 1.234 元，300 份"],
    }
    ingest(tmp_path, brief)
    signal = ledger.read_events(root, "SIGNAL")[0]
    serialized = json.dumps(signal["content"], ensure_ascii=False)
    for leaked in ("300 份", "目标价", "1.234", "参考价", "9.99"):
        assert leaked not in serialized
    # B 反例 3：SIGNAL 的 data_quality 只允许状态/摘要/缺失字段三个标量。
    assert set(signal["content"]["data_quality"]) == {
        "status",
        "summary_status",
        "missing_fields",
    }
    for dropped in ("quotes", "market_report", "screening", "tiers", "notes", "detail"):
        assert dropped not in signal["content"]["data_quality"]
    assert "511010.SH" not in serialized


def test_nested_order_semantics_never_reach_signal(tmp_path: Path) -> None:
    """B 反例 3：嵌套 recommended_sell_shares / notes 等不得进入 SIGNAL。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["v3_cockpit"]["deconcentration"]["recommended_sell_shares"] = 1000
    brief["v3_cockpit"]["deconcentration"]["notes"] = "卖出 1000 份 目标价 1.234 元"
    brief["data_quality"]["notes"] = ["卖出 500 份"]
    brief["data_quality"]["quotes"] = {"ready": ["511010.SH"], "detail": "目标价 9.99"}
    ingest(tmp_path, brief)
    signal = ledger.read_events(root, "SIGNAL")[0]
    serialized = json.dumps(signal["content"], ensure_ascii=False)
    for leaked in (
        "recommended_sell_shares",
        "notes",
        "500 份",
        "1000 份",
        "目标价",
        "1.234",
        "9.99",
        "quotes",
    ):
        assert leaked not in serialized
    deconcentration = signal["content"]["deconcentration_state"]
    assert "recommended_sell_shares" not in deconcentration


def test_concentration_rejects_nested_sell_hints_and_legs(tmp_path: Path) -> None:
    """B 反例 3：concentration 只允许数值/权重；卖出提示/腿不得进入 VALUATION。"""
    root = init(tmp_path)
    concentration = {
        "hhi": 0.2,
        "effective_positions": 4.0,
        "top_position": {
            "ts_code": "159558.SZ",
            "weight": 0.4,
            "suggested_action": "SELL 500 份",
            "legs": [{"side": "SELL", "quantity": 500}],
        },
        "sell_note": "建议卖出超额 1000 份",
        "recommended_sell_shares": 1000,
    }
    ingest(tmp_path, make_brief(concentration=concentration))
    valuation = ledger.read_events(root, "VALUATION")[0]
    stored = valuation["content"]["concentration"]
    assert stored == {
        "hhi": 0.2,
        "effective_positions": 4.0,
        "top_position": {"ts_code": "159558.SZ", "weight": 0.4},
    }
    serialized = json.dumps(valuation["content"], ensure_ascii=False)
    for leaked in ("suggested_action", "sell_note", "recommended_sell_shares", "500 份", "legs"):
        assert leaked not in serialized
    # 已落盘内容若被篡改为带卖出提示，verify 必须拒绝。
    forged = copy.deepcopy(valuation["content"])
    forged["concentration"]["sell_note"] = "卖出 500 份"
    with pytest.raises(ledger.LedgerCorruption):
        ledger._validate_valuation_content(
            forged, tuple(valuation["missing_fields"])
        )


def test_no_action_reason_with_order_semantics_is_not_projected(tmp_path: Path) -> None:
    """B 建议：no_action_reason 自由文本不落盘，SIGNAL 只留封闭原因码与 present 标志。"""
    root = init(tmp_path)
    brief = make_brief(status="NO_ACTION", actions=[])
    brief["first_section"]["no_action_reason"] = (
        "没有可复核的证据支持下一交易日的交易动作：300 份目标价 1.234 元未达门槛"
    )
    ingest(tmp_path, brief)
    signal = ledger.read_events(root, "SIGNAL")[0]
    decision = signal["content"]["decision"]
    assert "no_action_reason" not in decision
    assert decision["no_action_reason_code"] == "NO_ACTION_REASON_RECORDED_IN_BRIEF"
    assert decision["no_action_reason_present"] is True
    serialized = json.dumps(signal["content"], ensure_ascii=False)
    assert "300 份" not in serialized
    assert "1.234" not in serialized
    assert "目标价" not in serialized


def test_valid_financemcp_upstream_fields_are_projected_not_rejected(tmp_path: Path) -> None:
    """B-d-review：真实 ActionPlan/Holding 的已知展示字段必须可识别并投影，不能整份拒绝。"""
    root = init(tmp_path)
    brief = make_brief()  # _action() 已带 illustrative/fact_meta/腿的 name/lots/fees_cents 等
    holdings = [_holding()]  # 已带 stance/reasons/counter_evidence/research
    brief["holdings"] = holdings
    result = ingest(tmp_path, brief)
    assert result["status"] == "INGESTED"
    recommendation = ledger.read_events(root, "RECOMMENDATION")[0]
    action = recommendation["content"]["action"]
    assert set(action) <= ledger.ACTION_ALLOWED_KEYS
    leg = action["legs"][0]
    assert set(leg) == ledger.LEG_ALLOWED_KEYS
    assert "name" not in leg and "lot_size" not in leg and "fees_cents" not in leg
    valuation = ledger.read_events(root, "VALUATION")[0]
    assert "stance" not in valuation["content"]["holdings"][0]


def test_real_upstream_data_quality_shape_is_accepted_but_trimmed(tmp_path: Path) -> None:
    """真实 brief 的 data_quality（quotes/tiers/screening）是可接受输入，但深层一律不落盘。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["data_quality"] = {
        "status": "OK",
        "summary_status": "OK",
        "missing_fields": [],
        "quotes": {"ready": ["511010.SH"], "stale": [], "not_ready": [], "missing": []},
        "market_report": {
            "available": True,
            "report_id": "f" * 64,
            "as_of_trade_date": AS_OF,
            "freshness": "same_day",
        },
        "screening": {"status": "READY", "missing_tables": []},
        "tiers": {
            "etf_price": {"status": "READY", "ready": ["511010.SH"], "not_ready": []}
        },
        "notes": ["合成质量说明"],
    }
    result = ingest(tmp_path, brief)
    assert result["status"] == "INGESTED"
    assert ledger.read_events(root, "SIGNAL")[0]["content"]["data_quality"] == {
        "status": "OK",
        "summary_status": "OK",
        "missing_fields": [],
    }
    # team-lead 终判：VALUATION 的 data_quality 同样只允许三个状态键，深层结构不落盘。
    valuation_quality = ledger.read_events(root, "VALUATION")[0]["content"]["data_quality"]
    assert valuation_quality == {
        "status": "OK",
        "summary_status": "OK",
        "missing_fields": [],
    }


def test_unknown_persisted_signal_state_key_is_refused(tmp_path: Path) -> None:
    """已落盘的 SIGNAL 状态块出现未批准键（例如数量/价格语义）必须 CORRUPT。"""
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    signal = ledger.read_events(root, "SIGNAL")[0]
    forged = copy.deepcopy(signal["content"])
    forged["deconcentration_state"]["order_quantity"] = 300
    with pytest.raises(ledger.LedgerCorruption, match="未批准字段"):
        ledger._validate_signal_content(forged, tuple(signal["missing_fields"]))
    forged_quality = copy.deepcopy(signal["content"])
    forged_quality["data_quality"]["notes"] = "目标价 1.234"
    with pytest.raises(ledger.LedgerCorruption, match="未批准字段"):
        ledger._validate_signal_content(forged_quality, tuple(signal["missing_fields"]))


def test_recommendation_projects_whitelisted_action_keys_only(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    recommendation = ledger.read_events(root, "RECOMMENDATION")[0]
    action = recommendation["content"]["action"]
    assert set(action) == ledger.ACTION_ALLOWED_KEYS
    for stripped in ("illustrative", "fact_meta"):
        assert stripped not in action
    leg = action["legs"][0]
    assert set(leg) == ledger.LEG_ALLOWED_KEYS
    assert leg["executable"] is True
    assert leg["quantity"] == 100


def test_recommendation_rejects_unknown_action_key(tmp_path: Path) -> None:
    brief = make_brief()
    brief["execution_plan"]["actions"][0]["unknown_broker_field"] = "x"
    brief["first_section"]["actions"][0]["unknown_broker_field"] = "x"
    with pytest.raises(ledger.LedgerRefusal, match="未批准字段"):
        ledger._validate_brief(
            brief,
            account_id="real-main",
            now=NOW,
            calendar_db=make_calendar_db(tmp_path, [AS_OF]),
        )


def test_recommendation_rejects_unknown_leg_key(tmp_path: Path) -> None:
    brief = make_brief()
    brief["execution_plan"]["actions"][0]["legs"][0]["order_id"] = "x"
    brief["first_section"]["actions"][0]["legs"][0]["order_id"] = "x"
    with pytest.raises(ledger.LedgerRefusal, match="未批准字段"):
        ledger._validate_brief(
            brief,
            account_id="real-main",
            now=NOW,
            calendar_db=make_calendar_db(tmp_path, [AS_OF]),
        )


def test_recommendation_rejects_fill_fields(tmp_path: Path) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    brief = make_brief()
    brief["execution_plan"]["actions"][0]["realized_weights"] = {"511010.SH": 1.0}
    brief["first_section"]["actions"][0]["realized_weights"] = {"511010.SH": 1.0}
    with pytest.raises(ledger.LedgerRefusal, match="成交字段"):
        ingest(tmp_path, brief)
    assert snapshot_bytes(root) == before


def test_recommendation_with_illustrative_legs_never_creates_a_fill(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief(status="ILLUSTRATIVE"))
    recommendation = ledger.read_events(root, "RECOMMENDATION")[0]
    assert all(leg["executable"] is False for leg in recommendation["content"]["action"]["legs"])
    assert ledger.read_events(root, "CONFIRMED_FILL") == []


# --------------------------------------------------------------------------------------
# Brief split into five classes
# --------------------------------------------------------------------------------------


def test_brief_ingest_splits_signal_recommendation_and_valuation(tmp_path: Path) -> None:
    root = init(tmp_path)
    result = ingest(tmp_path, make_brief())
    assert result["status"] == "INGESTED"
    assert counts(root) == {
        "SIGNAL": 1,
        "RECOMMENDATION": 1,
        "CONFIRMED_FILL": 0,
        "UNEXECUTED_REASON": 0,
        "VALUATION": 1,
    }
    signal = ledger.read_events(root, "SIGNAL")[0]
    recommendation = ledger.read_events(root, "RECOMMENDATION")[0]
    valuation = ledger.read_events(root, "VALUATION")[0]
    raw = (tmp_path / "brief.json").read_bytes()
    assert signal["source"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert signal["policy"]["content_hash"] == POLICY_HASH
    assert recommendation["content"]["action"]["legs"][0]["quantity"] == 100
    assert "fills" not in recommendation["content"]["action"]
    assert valuation["content"]["principal"]["current_nav_cents"] == 6_800_000
    assert valuation["content"]["holdings"][0]["ts_code"] == "511010.SH"
    assert ledger.read_events(root, "CONFIRMED_FILL") == []


def test_reingest_same_brief_is_idempotent_and_does_not_change_bytes(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    before = snapshot_bytes(root)
    result = ingest(tmp_path, make_brief())
    assert result["status"] == "IDEMPOTENT_NOOP"
    assert snapshot_bytes(root) == before


def test_same_day_different_brief_is_a_conflict_without_byte_changes(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    before = snapshot_bytes(root)
    changed = make_brief()
    changed["report_id"] = "c" * 64
    changed["execution_plan"]["actions"][0]["title"] = "另一个动作"
    changed["first_section"]["actions"][0]["title"] = "另一个动作"
    with pytest.raises(ledger.LedgerConflict, match="append-only"):
        ingest(tmp_path, changed, name="changed.json")
    assert snapshot_bytes(root) == before


def test_no_action_brief_has_signal_and_valuation_but_no_recommendation(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief(status="NO_ACTION", actions=[]))
    assert counts(root) == {
        "SIGNAL": 1,
        "RECOMMENDATION": 0,
        "CONFIRMED_FILL": 0,
        "UNEXECUTED_REASON": 0,
        "VALUATION": 1,
    }
    signal = ledger.read_events(root, "SIGNAL")[0]
    decision = signal["content"]["decision"]
    assert decision["no_action_reason_code"] == "NO_ACTION_REASON_RECORDED_IN_BRIEF"
    assert decision["no_action_reason_present"] is True
    assert decision["evidence_complete"] is True


def test_data_insufficient_brief_records_signal_only_with_explicit_missing(tmp_path: Path) -> None:
    root = init(tmp_path)
    brief = make_brief(status="DATA_INSUFFICIENT", actions=[], cockpit=None)
    result = ingest(tmp_path, brief)
    assert counts(root) == {
        "SIGNAL": 1,
        "RECOMMENDATION": 0,
        "CONFIRMED_FILL": 0,
        "UNEXECUTED_REASON": 0,
        "VALUATION": 0,
    }
    signal = ledger.read_events(root, "SIGNAL")[0]
    assert signal["content"]["decision"]["evidence_complete"] is False
    assert "v3_cockpit" in signal["missing_fields"]
    assert "source_data_insufficient" in signal["missing_fields"]
    assert signal["policy"] is None
    assert result["missing_fields"]["SIGNAL"]


def test_illustrative_brief_records_non_executable_recommendations(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief(status="ILLUSTRATIVE"))
    recommendation = ledger.read_events(root, "RECOMMENDATION")[0]
    assert all(leg["executable"] is False for leg in recommendation["content"]["action"]["legs"])
    assert recommendation["content"]["status"] == "ILLUSTRATIVE"


def test_first_brief_pins_the_policy_baseline(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    baseline = ledger.load_policy_baseline(root)
    assert baseline is not None
    assert baseline["strategy_id"] == "V3_OFFENSIVE_LOW_FREQ_SYSTEM"
    assert baseline["version"] == "v3.2.0"
    assert baseline["content_hash"] == POLICY_HASH
    assert baseline["first_as_of_trade_date"] == AS_OF
    assert oct((root / ledger.POLICY_BASELINE_FILENAME).stat().st_mode & 0o777) == "0o600"


def test_policy_change_on_a_later_day_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    before = snapshot_bytes(root)
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 13, 0, tzinfo=timezone.utc)
    )
    changed = make_brief(as_of=NEXT_DAY, generated_at="2026-11-27T20:00:00+08:00")
    changed["report_id"] = "e" * 64
    changed["v3_cockpit"]["policy_release"]["content_hash"] = "f" * 64
    with pytest.raises(ledger.LedgerRefusal, match="POLICY_RELEASE_CHANGED"):
        ingest(tmp_path, changed, name="changed-policy.json")
    assert snapshot_bytes(root) == before


def test_verify_detects_a_tampered_policy_baseline(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    baseline = json.loads((root / ledger.POLICY_BASELINE_FILENAME).read_text(encoding="utf-8"))
    baseline["content_hash"] = "not-a-hash"
    write_json(root / ledger.POLICY_BASELINE_FILENAME, baseline)
    with pytest.raises(ledger.LedgerCorruption, match="content_hash"):
        ledger.verify_ledger(root)


def test_verify_cross_checks_baseline_against_signal_policy(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    baseline = json.loads((root / ledger.POLICY_BASELINE_FILENAME).read_text(encoding="utf-8"))
    baseline["content_hash"] = "d" * 64
    write_json(root / ledger.POLICY_BASELINE_FILENAME, baseline)
    with pytest.raises(ledger.LedgerCorruption, match="policy_baseline"):
        ledger.verify_ledger(root)


def test_missing_baseline_with_existing_signals_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    (root / ledger.POLICY_BASELINE_FILENAME).unlink()
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 13, 0, tzinfo=timezone.utc)
    )
    second = make_brief(as_of=NEXT_DAY, generated_at="2026-11-27T20:00:00+08:00")
    second["report_id"] = "e" * 64
    with pytest.raises(ledger.LedgerRefusal, match="POLICY_BASELINE_MISSING_WITH_EVIDENCE"):
        ingest(tmp_path, second, name="second.json")


def test_data_insufficient_first_day_does_not_block_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief(status="DATA_INSUFFICIENT", actions=[], cockpit=None))
    assert ledger.load_policy_baseline(root) is None
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 13, 0, tzinfo=timezone.utc)
    )
    second = make_brief(as_of=NEXT_DAY, generated_at="2026-11-27T20:00:00+08:00")
    second["report_id"] = "e" * 64
    ingest(tmp_path, second, name="second.json")
    assert ledger.load_policy_baseline(root)["first_as_of_trade_date"] == NEXT_DAY


def test_data_insufficient_day_with_cockpit_does_not_bind_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """补遗 1 §1：不足日即使 cockpit 带 policy_release 也不得提前钉住 baseline。"""
    root = init(tmp_path)
    brief = make_brief(status="DATA_INSUFFICIENT", actions=[])
    assert brief["v3_cockpit"]["policy_release"]["content_hash"] == POLICY_HASH
    ingest(tmp_path, brief)
    assert ledger.load_policy_baseline(root) is None
    signal = ledger.read_events(root, "SIGNAL")[0]
    assert signal["policy"] is None
    assert "v3_cockpit.policy_release" in signal["missing_fields"]
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 13, 0, tzinfo=timezone.utc)
    )
    second = make_brief(as_of=NEXT_DAY, generated_at="2026-11-27T20:00:00+08:00")
    second["report_id"] = "e" * 64
    ingest(tmp_path, second, name="second.json")
    baseline = ledger.load_policy_baseline(root)
    assert baseline is not None
    assert baseline["first_as_of_trade_date"] == NEXT_DAY


# --------------------------------------------------------------------------------------
# Anti-backfill and temporal rules
# --------------------------------------------------------------------------------------


def test_brief_before_earliest_eligible_day_is_rejected(tmp_path: Path) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    brief = make_brief(as_of="20261125", generated_at="2026-11-25T20:00:00+08:00")
    brief["expected_next_trade_date"] = AS_OF
    with pytest.raises(ledger.LedgerRefusal, match="最早合格日"):
        ingest(tmp_path, brief, calendar_db=calendar(tmp_path, ["20261125", AS_OF]))
    assert snapshot_bytes(root) == before


def test_recommendation_explicitly_records_missing_expected_execution_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 13, 0, tzinfo=timezone.utc)
    )
    second = make_brief(as_of=NEXT_DAY, generated_at="2026-11-27T20:00:00+08:00")
    second["report_id"] = "e" * 64
    ingest(tmp_path, second, name="second.json")
    recommendations = [
        event
        for event in ledger.read_events(root, "RECOMMENDATION")
        if event["as_of_trade_date"] == NEXT_DAY
    ]
    assert recommendations
    for event in recommendations:
        assert "expected_execution_date" in event["missing_fields"]
        assert event["content"]["expected_execution_date"] is None


# --------------------------------------------------------------------------------------
# Explicit missing
# --------------------------------------------------------------------------------------


def test_required_missing_field_refuses_without_writing(tmp_path: Path) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    brief = make_brief()
    del brief["holdings"]
    with pytest.raises(ledger.LedgerRefusal, match="holdings"):
        ingest(tmp_path, brief)
    assert snapshot_bytes(root) == before


def test_optional_missing_fields_are_explicit_in_valuation(tmp_path: Path) -> None:
    root = init(tmp_path)
    holding = _holding()
    del holding["price_source"]
    brief = make_brief(holdings=[holding], concentration=None)
    ingest(tmp_path, brief)
    valuation = ledger.read_events(root, "VALUATION")[0]
    assert "holdings[0].price_source" in valuation["missing_fields"]
    assert "concentration" in valuation["missing_fields"]
    assert valuation["content"]["holdings"][0]["price_source"] is None
    assert valuation["content"]["concentration"] is None


def test_actionable_brief_without_executable_quantity_is_rejected(tmp_path: Path) -> None:
    brief = make_brief()
    brief["execution_plan"]["actions"][0]["legs"][0]["quantity"] = 0
    brief["first_section"]["actions"][0]["legs"][0]["quantity"] = 0
    with pytest.raises(ledger.LedgerRefusal, match="数量必须为正"):
        ledger._validate_brief(
            brief,
            account_id="real-main",
            now=NOW,
            calendar_db=make_calendar_db(tmp_path, [AS_OF]),
        )


# --------------------------------------------------------------------------------------
# Confirmed fills
# --------------------------------------------------------------------------------------


def test_fills_import_only_broker_confirmed_non_reversed_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    result = ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    fills = ledger.read_events(root, "CONFIRMED_FILL")
    assert [event["content"]["event_id"] for event in fills] == ["fill-1"]
    assert result["skipped_rows"] == {
        "before_earliest": 1,
        "after_now": 0,
        "not_broker_statement": 1,
        "reversed": 1,
        "other_account": 0,
    }
    assert fills[0]["content"]["source"] == "broker_statement"
    assert fills[0]["content"]["quantity"] == 100
    assert fills[0]["source"]["schema_fingerprint"]


def test_fill_import_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    before = snapshot_bytes(root)
    result = ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    assert result["status"] == "IDEMPOTENT_NOOP"
    assert snapshot_bytes(root) == before


def test_fill_import_never_writes_to_the_source_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_fill_import_reads_only_account_event_table(tmp_path: Path) -> None:
    """P:40–41 只读边界：成交库无需（也不读）account_meta 表。"""
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    connection = sqlite3.connect(db)
    try:
        connection.execute("DROP TABLE account_meta")
        connection.commit()
    finally:
        connection.close()
    result = ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    assert result["status"] in {"INGESTED", "NO_NEW_FILLS"}

    statements: list[str] = []
    real_connect = sqlite3.connect

    def tracing_connect(*args, **kwargs):
        traced = real_connect(*args, **kwargs)
        traced.set_trace_callback(statements.append)
        return traced

    sqlite3.connect = tracing_connect
    try:
        ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    finally:
        sqlite3.connect = real_connect
    assert statements
    assert all("account_meta" not in statement for statement in statements)


@pytest.mark.parametrize("reversed_value", ["rev-9", ""])
def test_fill_reversed_after_import_blocks_further_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reversed_value: str
) -> None:
    """撤销复核只针对已导入 fill；源行 `reversed_by` 非 NULL（含空串）即触发
    SOURCE_REVERSED_AFTER_IMPORT，停止追加。"""
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    before = snapshot_bytes(root)
    connection = sqlite3.connect(db)
    try:
        connection.execute(
            "UPDATE account_event SET reversed_by = ? WHERE event_id = 'fill-1'",
            (reversed_value,),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ledger.LedgerRefusal, match="SOURCE_REVERSED_AFTER_IMPORT"):
        ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    assert snapshot_bytes(root) == before


def test_only_imported_fills_are_reverse_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """从未导入的已撤销行不触发报警，也不阻断整批。"""
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)  # 仅导入 fill-1
    connection = sqlite3.connect(db)
    try:
        # 未导入的 fill-old 被撤销：不属于已导入集合，不应报警。
        connection.execute(
            "UPDATE account_event SET reversed_by = 'rev-2' WHERE event_id = 'fill-old'"
        )
        connection.commit()
    finally:
        connection.close()
    result = ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    assert result["status"] == "IDEMPOTENT_NOOP"


def test_empty_string_reversed_by_row_is_not_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """协议 §4：只有 `reversed_by IS NULL` 才导入；空串行按正常筛选排除，
    不导入、不报 CORRUPT、不阻断同批其它行。"""
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    connection = sqlite3.connect(db)
    try:
        connection.execute("UPDATE account_event SET reversed_by = '' WHERE event_id = 'fill-1'")
        connection.commit()
    finally:
        connection.close()
    result = ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    assert result["status"] == "NO_NEW_FILLS"
    assert result["skipped_rows"]["reversed"] == 2  # fill-1（空串）+ fill-reversed（rev-1）
    assert ledger.read_events(root, "CONFIRMED_FILL") == []


def test_empty_string_reversed_by_row_does_not_block_the_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """空串行被排除属正常筛选：同批 NULL 行仍正常导入，不是 CORRUPT。"""
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    connection = sqlite3.connect(db)
    try:
        connection.execute("UPDATE account_event SET reversed_by = '' WHERE event_id = 'fill-old'")
        connection.commit()
    finally:
        connection.close()
    result = ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    assert result["status"] == "INGESTED"
    assert result["skipped_rows"]["reversed"] == 2  # fill-old（空串）+ fill-reversed（rev-1）
    imported = [
        event["content"]["event_id"] for event in ledger.read_events(root, "CONFIRMED_FILL")
    ]
    assert imported == ["fill-1"]


def test_fill_source_sha_covers_only_the_native_sql_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """源行 SHA 只哈希 account_event 原生 19 列，不掺入合成 schema 键。"""
    import hashlib

    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    fill = ledger.read_events(root, "CONFIRMED_FILL")[0]
    native = {
        column: fill["content"][column] for column in ledger.ACCOUNT_EVENT_COLUMNS
    }
    expected = hashlib.sha256(
        ledger.canonical_json(native).encode("utf-8")
    ).hexdigest()
    assert fill["source"]["sha256"] == expected
    assert "schema" not in native
    assert fill["content"]["schema"] == "financemcp.account_event/1.0"


def test_fill_missing_after_import_blocks_further_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    connection = sqlite3.connect(db)
    try:
        connection.execute("DELETE FROM account_event WHERE event_id = 'fill-1'")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ledger.LedgerRefusal, match="SOURCE_FILL_MISSING_AFTER_IMPORT"):
        ledger.ingest_confirmed_fills(portfolio_db=db, root=root)


def test_recommendation_never_becomes_a_fill_even_without_broker_rows(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    db = tmp_path / "empty-portfolio.sqlite"
    connection = sqlite3.connect(db)
    try:
        connection.executescript(ACCOUNT_EVENT_DDL)
        connection.execute(
            "INSERT INTO account_meta (key, value) VALUES (?, ?)",
            ("real_account_verified:real-main", "1"),
        )
        connection.commit()
    finally:
        connection.close()
    result = ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    assert result["status"] == "NO_NEW_FILLS"
    assert ledger.read_events(root, "CONFIRMED_FILL") == []


# --------------------------------------------------------------------------------------
# Explicit unexecuted reasons
# --------------------------------------------------------------------------------------


def _reason_input(
    recommendation_event_id: str,
    *,
    reason_code: str = "PRICE_INVALIDATED",
    note: str = "次日高开超过 +2%，按失效条件未执行",
    decided_on: str = NEXT_DAY,
) -> dict:
    return {
        "schema": ledger.REASON_SCHEMA,
        "recommendation_event_id": recommendation_event_id,
        "reason_code": reason_code,
        "scope": "FULL",
        "reason_note": note,
        "decided_on": decided_on,
    }


def test_unexecuted_reason_requires_an_existing_recommendation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    with pytest.raises(ledger.LedgerRefusal, match="唯一存在的 recommendation"):
        ledger.ingest_unexecuted_reason(
            write_json(tmp_path / "reason.json", _reason_input("V3L-" + "0" * 21)), root=root
        )


def test_unexecuted_reason_is_appended_once_and_cannot_be_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    recommendation_id = ledger.read_events(root, "RECOMMENDATION")[0]["event_id"]
    input_path = write_json(tmp_path / "reason.json", _reason_input(recommendation_id))
    first = ledger.ingest_unexecuted_reason(input_path, root=root)
    assert first["status"] == "INGESTED"
    second = ledger.ingest_unexecuted_reason(input_path, root=root)
    assert second["status"] == "IDEMPOTENT_NOOP"
    before = snapshot_bytes(root)
    changed = _reason_input(recommendation_id, note="另一个原因")
    with pytest.raises(ledger.LedgerConflict, match="append-only"):
        ledger.ingest_unexecuted_reason(write_json(tmp_path / "reason2.json", changed), root=root)
    assert snapshot_bytes(root) == before


@pytest.mark.parametrize("reason_code", ["PRICE_INVALIDATED", "USER_DEFERRED", "OTHER_EXPLICIT"])
def test_closed_reason_enum_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason_code: str
) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    recommendation_id = ledger.read_events(root, "RECOMMENDATION")[0]["event_id"]
    path = write_json(
        tmp_path / "reason.json", _reason_input(recommendation_id, reason_code=reason_code)
    )
    ledger.ingest_unexecuted_reason(path, root=root)
    assert ledger.read_events(root, "UNEXECUTED_REASON")[0]["content"]["reason_code"] == reason_code


def test_blank_reason_is_rejected(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    recommendation_id = ledger.read_events(root, "RECOMMENDATION")[0]["event_id"]
    path = write_json(tmp_path / "reason.json", _reason_input(recommendation_id, note="   "))
    with pytest.raises(ledger.LedgerRefusal, match="不得为空白"):
        ledger.ingest_unexecuted_reason(path, root=root)


# --------------------------------------------------------------------------------------
# AMENDMENT_2 #5: write integrity, batches, crash handling, replay rejection
# --------------------------------------------------------------------------------------


def test_append_batch_ordinals_are_one_based_and_contiguous(tmp_path: Path) -> None:
    root = init(tmp_path)
    result = ingest(tmp_path, make_brief())
    assert result["batch_event_count"] == 3
    ordinals: list[int] = []
    for record_type in ledger.RECORD_FILES:
        for event in ledger.read_events(root, record_type):
            assert event["ingest_batch"]["count"] == 3
            ordinals.append(event["ingest_batch"]["ordinal"])
    assert sorted(ordinals) == [1, 2, 3]


def test_fill_a_then_a_plus_b_only_appends_b_and_keeps_a_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    first_row = (root / "confirmed_fills.jsonl").read_text(encoding="utf-8")
    first_event = ledger.read_events(root, "CONFIRMED_FILL")[0]

    connection = sqlite3.connect(db)
    try:
        connection.execute(
            "INSERT INTO account_event ("
            + ", ".join(ledger.ACCOUNT_EVENT_COLUMNS)
            + ") VALUES ("
            + ", ".join("?" for _ in ledger.ACCOUNT_EVENT_COLUMNS)
            + ")",
            (
                "fill-2",
                "real-main",
                "TRADE_SELL",
                NEXT_DAY,
                None,
                "511010.SH",
                100,
                100_000,
                10_000_000,
                5,
                0,
                9_999_990,
                None,
                None,
                None,
                None,
                "第二笔合成成交",
                "broker_statement",
                "2026-11-27T03:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    # 不同时钟、不同批次成员：A 的内容身份不得改变，只有 B 追加。
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 5, 0, tzinfo=timezone.utc)
    )
    result = ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    assert result["appended"]["CONFIRMED_FILL"] == 1
    assert result["skipped_idempotent"]["CONFIRMED_FILL"] == 1
    rows = [json.loads(line) for line in (root / "confirmed_fills.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()]
    assert len(rows) == 2
    assert rows[0] == json.loads(first_row.splitlines()[0])  # A 原行逐字节等价
    assert rows[0]["content_hash"] == first_event["content_hash"]
    assert rows[0]["event_id"] == first_event["event_id"]
    assert rows[0]["ingest_batch"] == {
        "id": first_event["ingest_batch"]["id"],
        "ordinal": 1,
        "count": 1,
    }
    assert rows[1]["content"]["event_id"] == "fill-2"
    assert ledger.verify_ledger(root)["status"] == "OK"


def test_partial_batch_after_io_failure_blocks_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    real_append = ledger._append_line

    def failing_append(path: Path, payload: dict) -> None:
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(ledger, "_append_line", failing_append)
    with pytest.raises(ledger.LedgerRefusal, match="1/3"):
        ingest(tmp_path, make_brief())
    assert snapshot_bytes(root) == before  # 第 1 行即失败：无新字节

    # 第二行故障：SIGNAL 已落盘，留下不完整批 1/3。
    counter = {"n": 0}

    def fail_on_second(path: Path, payload: dict) -> None:
        counter["n"] += 1
        if counter["n"] == 2:
            raise OSError("synthetic mid-batch failure")
        real_append(path, payload)

    monkeypatch.setattr(ledger, "_append_line", fail_on_second)
    with pytest.raises(ledger.LedgerRefusal, match="2/3"):
        ingest(tmp_path, make_brief())
    partial = snapshot_bytes(root)
    assert partial["signals.jsonl"] != before["signals.jsonl"]  # 已有不完整新尾
    assert partial["recommendations.jsonl"] == before["recommendations.jsonl"]
    monkeypatch.setattr(ledger, "_append_line", real_append)
    with pytest.raises(ledger.LedgerCorruption, match="不完整"):
        ledger.verify_ledger(root)
    with pytest.raises(ledger.LedgerCorruption, match="不完整"):
        ingest(tmp_path, make_brief())
    assert snapshot_bytes(root) == partial  # 拒绝重放，不截断、不补行
    with pytest.raises(ledger.LedgerCorruption, match="不完整"):
        ledger.status_report(root)


def test_half_line_tail_is_reported_and_blocks_further_writes(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    path = root / "signals.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"half":')  # 崩溃留下的半行
    with pytest.raises(ledger.LedgerCorruption, match="半行"):
        ledger.verify_ledger(root)
    # 既有字节保持不变，拒绝继续追加。
    before = path.read_bytes()
    second = make_brief(triggers=["其他"])
    second["report_id"] = "c" * 64
    with pytest.raises(ledger.LedgerCorruption, match="半行"):
        ingest(tmp_path, second, name="second.json")
    assert path.read_bytes() == before


def test_cross_day_append_keeps_existing_prefix_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    action_a = _action(code="P3-A", rank=1)
    action_b = _action(code="P3-B", rank=2)
    ingest(tmp_path, make_brief(actions=[action_a]))
    before_b = snapshot_bytes(root)
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 13, 0, tzinfo=timezone.utc)
    )
    second = make_brief(
        as_of=NEXT_DAY,
        generated_at="2026-11-27T20:00:00+08:00",
        actions=[action_a, action_b],
    )
    second["report_id"] = "e" * 64
    result = ledger.ingest_brief(
        write_json(tmp_path / "second.json", second),
        root=root,
        calendar_db=make_calendar_db(tmp_path, [AS_OF, NEXT_DAY]),
    )
    assert result["appended"]["RECOMMENDATION"] == 2
    after_b = snapshot_bytes(root)
    for name, payload in before_b.items():
        if name in {"manifest.json", ledger.POLICY_BASELINE_FILENAME}:
            assert after_b[name] == payload
        else:
            assert after_b[name].startswith(payload)  # 旧前缀逐字节不变


def test_changed_source_sha_rejects_the_whole_batch(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    before = snapshot_bytes(root)
    changed = make_brief()
    changed["report_id"] = "c" * 64
    changed["execution_plan"]["actions"][0]["title"] = "重生成后的动作"
    changed["first_section"]["actions"][0]["title"] = "重生成后的动作"
    with pytest.raises(ledger.LedgerConflict, match="append-only"):
        ingest(tmp_path, changed, name="changed.json")
    assert snapshot_bytes(root) == before


def test_duplicate_natural_key_inside_one_batch_is_refused(tmp_path: Path) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    duplicate = _action(code="P3-DUP", rank=1)
    brief = make_brief(actions=[duplicate, copy.deepcopy(duplicate)])
    with pytest.raises(ledger.LedgerConflict, match="重复 natural_key"):
        ingest(tmp_path, brief)
    assert counts(root)["RECOMMENDATION"] == 0
    for name, payload in before.items():
        if name != "manifest.json" and name != ledger.POLICY_BASELINE_FILENAME:
            assert (root / name).read_bytes() == payload


def test_verify_detects_a_batch_count_mismatch(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    path = root / "signals.jsonl"
    line = json.loads(path.read_text(encoding="utf-8"))
    line["ingest_batch"]["count"] = 99
    material = {key: value for key, value in line.items() if key != "event_hash"}
    line["event_hash"] = hashlib.sha256(
        ledger.canonical_json(material).encode("utf-8")
    ).hexdigest()
    path.write_text(ledger.canonical_json(line) + "\n", encoding="utf-8")
    with pytest.raises(ledger.LedgerCorruption, match="不完整|count"):
        ledger.verify_ledger(root)


def test_verify_detects_duplicate_natural_keys_across_files(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    events = ledger.read_events(root, "VALUATION")
    # 复制一行 VALUATION 到 recommendations.jsonl；record_type 不符，读取即拒绝。
    forged = dict(events[0])
    forged["natural_key"] = "RECOMMENDATION:forged:1"
    path = root / "recommendations.jsonl"
    path.write_text(ledger.canonical_json(forged) + "\n", encoding="utf-8")
    with pytest.raises(ledger.LedgerCorruption):
        ledger.verify_ledger(root)


def test_two_concurrent_writers_of_the_same_batch_end_with_one_row_each(tmp_path: Path) -> None:
    root = init(tmp_path)
    calendar_db = calendar(tmp_path)
    brief_path = write_json(tmp_path / "brief.json", make_brief())
    results: list[str] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            result = ledger.ingest_brief(brief_path, root=root, calendar_db=calendar_db)
            results.append(result["status"])
        except BaseException as error:  # noqa: BLE001 - 记录线程内异常供断言
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    assert sorted(results) == ["IDEMPOTENT_NOOP", "INGESTED"]
    assert counts(root) == {
        "SIGNAL": 1,
        "RECOMMENDATION": 1,
        "CONFIRMED_FILL": 0,
        "UNEXECUTED_REASON": 0,
        "VALUATION": 1,
    }


def test_writer_lock_serializes_two_writers(tmp_path: Path) -> None:
    root = init(tmp_path)
    order: list[str] = []

    def writer(name: str) -> None:
        with ledger._writer_lock(root):
            order.append(f"enter:{name}")
            order.append(f"exit:{name}")

    threads = [threading.Thread(target=writer, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert order == ["enter:a", "exit:a", "enter:b", "exit:b"] or order == [
        "enter:b",
        "exit:b",
        "enter:a",
        "exit:a",
    ]


def test_non_finite_numbers_are_rejected_by_canonical_json() -> None:
    with pytest.raises(ledger.LedgerRefusal, match="非有限"):
        ledger.canonical_json({"value": float("nan")})
    with pytest.raises(ledger.LedgerRefusal, match="非有限"):
        ledger.canonical_json({"nested": [float("inf")]})


def test_golden_hash_vector_for_a_signal_content() -> None:
    content = {
        "brief_schema": "ashare-daily-brief/1.0",
        "report_id": "b" * 64,
        "status": "ACTIONABLE",
        "actionable": True,
        "generated_at": "2026-11-26T20:00:00+08:00",
        "expected_next_trade_date": "20261127",
        "account_id_source": "explicit",
        "account_status": "REAL_ACCOUNT_VERIFIED",
        "decision": {
            "evidence_complete": True,
            "no_action_reason": None,
            "suppressed_recommendation_count": 0,
            "trigger_codes": ["ACCOUNT_LIFELINE"],
        },
        "market_regime": {"regime": "DEFENSIVE"},
        "router": {"effective_regime": "DEFENSIVE", "circuit_breaker_status": "NORMAL"},
        "deconcentration_state": {"plan_present": False},
        "data_quality": {"status": "OK", "summary_status": "OK", "missing_fields": []},
    }
    digest = ledger.content_hash("SIGNAL", content, "c" * 64)
    assert digest == "fec60ddb7c2aeccf021a444de765e8c0dc917168732da01ab82a5d05b7741ecf"
    assert ledger.event_id_for(digest) == "V3L-fec60ddb7c2aeccf021a444d"


# --------------------------------------------------------------------------------------
# Integrity
# --------------------------------------------------------------------------------------


def test_verify_accepts_a_well_formed_ledger(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    result = ledger.verify_ledger(root)
    assert result["status"] == "OK"
    assert result["total_events"] == 3
    assert len(result["batches"]) == 1


def test_verify_detects_tampered_content(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    path = root / "recommendations.jsonl"
    line = json.loads(path.read_text(encoding="utf-8"))
    line["content"]["action"]["title"] = "被篡改"
    path.write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ledger.LedgerCorruption, match="content_hash"):
        ledger.verify_ledger(root)


def test_verify_detects_a_broken_hash_chain(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    path = root / "signals.jsonl"
    line = json.loads(path.read_text(encoding="utf-8"))
    line["prev_event_hash"] = "1" * 64
    path.write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ledger.LedgerCorruption):
        ledger.verify_ledger(root)


# --------------------------------------------------------------------------------------
# Status and pause advice
# --------------------------------------------------------------------------------------


def test_status_reports_unresolved_recommendations_without_inventing_reasons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    actions = [_action(code=f"P3-TEST-{index}", rank=index) for index in (1, 2, 3)]
    ingest(tmp_path, make_brief(actions=actions))
    monkeypatch.setattr(ledger, "utc_now", lambda: datetime(2026, 12, 1, 2, 0, tzinfo=timezone.utc))
    report = ledger.status_report(root)
    assert report["counts"]["UNEXECUTED_REASON"] == 0
    assert len(report["unresolved_recommendation_event_ids"]) == 3
    assert report["pause"]["recommended"] is True
    assert report["pause"]["no_automatic_actions"] is True


def test_status_never_auto_attributes_a_coincident_fill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """补遗 2 §2 / A2:65：同日同码同向只能报候选重合，不得自动 MATCHED 或解除 UNRESOLVED。"""
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    db = make_account_db(tmp_path)
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    report = ledger.status_report(root)
    review = report["recommendation_review"][0]
    assert review["match_status"] == "COINCIDENT_FILLS_UNATTRIBUTED"
    assert review["attribution"] == "NOT_ATTRIBUTED"
    assert review["coincident_fill_event_ids"]
    assert review["unexecuted_reason_event_id"] is None
    assert report["unresolved_recommendation_event_ids"] == [review["recommendation_event_id"]]


def test_illustrative_recommendations_do_not_absorb_confirmed_fills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief(status="ILLUSTRATIVE"))
    db = make_account_db(tmp_path)
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    report = ledger.status_report(root)
    review = report["recommendation_review"][0]
    assert review["match_status"] == "NOT_EXECUTABLE"
    assert review["coincident_fill_event_ids"] == []
    assert report["unattributed_fill_event_ids"]


def test_status_reports_partial_leg_coincidence_without_attribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    action = _action()
    action["legs"].append(
        _leg(side="SELL", ts_code="159558.SZ", quantity=100, executable=True)
    )
    ingest(tmp_path, make_brief(actions=[action]))
    db = make_account_db(tmp_path)
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    report = ledger.status_report(root)
    review = report["recommendation_review"][0]
    assert review["match_status"] == "COINCIDENT_FILLS_UNATTRIBUTED"
    assert review["coincident_leg_indices"] == [0]
    assert review["executable_leg_indices"] == [0, 1]
    assert review["attribution"] == "NOT_ATTRIBUTED"
    assert report["unresolved_recommendation_event_ids"]


def test_status_derives_missed_days_from_the_read_only_calendar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    calendar_db = make_calendar_db(
        tmp_path,
        [
            "20261126",
            "20261127",
            "20261130",
            "20261201",
            "20261202",
            "20261203",
            "20261204",
            "20261205",
        ],
    )
    monkeypatch.setattr(ledger, "utc_now", lambda: datetime(2026, 12, 8, 2, 0, tzinfo=timezone.utc))
    report = ledger.status_report(root, calendar_db=calendar_db)
    assert report["days"]["missed"] == [
        "20261127",
        "20261130",
        "20261201",
        "20261202",
        "20261203",
        "20261204",
        "20261205",
    ]
    assert any(
        reason.startswith("CONSECUTIVE_MISSED_DAYS") for reason in report["pause"]["reasons"]
    )


def test_status_does_not_mark_today_as_missed_before_the_day_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """补遗 2 §1：当天截止前不得判 MISSED，MISSED 只对已过去的开市日派生。"""
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    calendar_db = make_calendar_db(tmp_path, [AS_OF, NEXT_DAY])
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)
    )  # 上海 2026-11-28 02:00；11-27 已过去但日报可能尚未生成
    report = ledger.status_report(root, calendar_db=calendar_db)
    assert "20261127" in report["days"]["missed"]
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )  # 上海 2026-11-27 10:00，当天未截止
    report_same_day = ledger.status_report(root, calendar_db=calendar_db)
    assert "20261127" not in (report_same_day["days"]["missed"] or [])


def test_status_flags_actionable_signal_without_recommendation(tmp_path: Path) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    report = ledger.status_report(root)
    assert not any(
        warning.startswith("ACTIONABLE_SIGNAL_WITHOUT_RECOMMENDATION")
        for warning in report["warnings"]
    )
    # 直接追加一条未来 ACTIONABLE SIGNAL（无 recommendation）以验证派生告警。
    day = "20261130"
    source_signal = ledger.read_events(root, "SIGNAL")[0]
    content = dict(source_signal["content"])
    content["expected_next_trade_date"] = "20261201"
    content["generated_at"] = "2026-11-30T20:00:00+08:00"
    draft = ledger.Draft(
        record_type="SIGNAL",
        natural_key=f"SIGNAL:daily_brief:real-main:{day}",
        as_of_trade_date=day,
        content=content,
        source=source_signal["source"],
        policy=source_signal["policy"],
        missing_fields=tuple(source_signal["missing_fields"]),
    )
    monkeypatch_day = datetime(2026, 11, 30, 13, 0, tzinfo=timezone.utc)
    original_now = ledger.utc_now
    ledger.utc_now = lambda: monkeypatch_day
    try:
        ledger._append_drafts(
            root, [draft], batch_kind="synthetic_signal_only", batch_source_sha="0" * 64
        )
    finally:
        ledger.utc_now = original_now
    flagged = ledger.status_report(root)
    assert any(
        warning.startswith("ACTIONABLE_SIGNAL_WITHOUT_RECOMMENDATION:20261130")
        for warning in flagged["warnings"]
    )


def test_cli_end_to_end_ingest_verify_and_status(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "ledger"
    calendar_db = make_calendar_db(tmp_path, [AS_OF, NEXT_DAY])
    assert ledger.main(["--ledger-root", str(root), "init"]) == 0
    capsys.readouterr()
    brief_path = write_json(tmp_path / "brief.json", make_brief())
    assert (
        ledger.main(
            [
                "--ledger-root",
                str(root),
                "ingest-brief",
                "--brief",
                str(brief_path),
                "--calendar-db",
                str(calendar_db),
            ]
        )
        == 0
    )
    ingest_output = json.loads(capsys.readouterr().out)
    assert ingest_output["status"] == "INGESTED"
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    assert (
        ledger.main(
            [
                "--ledger-root",
                str(root),
                "ingest-fills",
                "--portfolio-db",
                str(make_account_db(tmp_path)),
            ]
        )
        == 0
    )
    fills_output = json.loads(capsys.readouterr().out)
    assert fills_output["status"] == "INGESTED"
    assert fills_output["appended"]["CONFIRMED_FILL"] == 1
    assert ledger.main(["--ledger-root", str(root), "verify"]) == 0
    verify_output = json.loads(capsys.readouterr().out)
    assert verify_output["status"] == "OK"
    assert ledger.main(["--ledger-root", str(root), "status"]) == 0
    status_output = json.loads(capsys.readouterr().out)
    assert status_output["status"] == "OK"
    assert status_output["counts"]["SIGNAL"] == 1
    assert status_output["counts"]["CONFIRMED_FILL"] == 1


def test_cli_ingest_brief_without_calendar_is_refused(
    tmp_path: Path, capsys
) -> None:
    root = init(tmp_path)
    path = write_json(tmp_path / "brief.json", make_brief())
    exit_code = ledger.main(["--ledger-root", str(root), "ingest-brief", "--brief", str(path)])
    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "REFUSED"
    assert "交易日历未知" in payload["error"]


def test_cli_refusal_returns_json_and_exit_code_two(tmp_path: Path, capsys) -> None:
    root = init(tmp_path)
    calendar_db = make_calendar_db(tmp_path, ["20261125", AS_OF])
    brief = make_brief(as_of="20261125", generated_at="2026-11-25T20:00:00+08:00")
    brief["expected_next_trade_date"] = AS_OF
    path = write_json(tmp_path / "old.json", brief)
    exit_code = ledger.main(
        [
            "--ledger-root",
            str(root),
            "ingest-brief",
            "--brief",
            str(path),
            "--calendar-db",
            str(calendar_db),
        ]
    )
    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "REFUSED"
    assert "最早合格日" in payload["error"]


def test_valuation_data_quality_nested_legs_is_dropped(tmp_path: Path) -> None:
    """B 反例 3：VALUATION 深层 data_quality 的 notes/legs 不落盘（显式投影剔除）。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["data_quality"] = {
        "status": "OK",
        "summary_status": "OK",
        "missing_fields": [],
        "notes": [{"legs": [{"side": "SELL", "quantity": 100}]}],
    }
    ingest(tmp_path, brief)
    valuation = ledger.read_events(root, "VALUATION")[0]
    quality = valuation["content"]["data_quality"]
    assert "notes" not in quality
    assert set(quality) <= {"status", "summary_status", "missing_fields"}
    serialized = json.dumps(valuation["content"], ensure_ascii=False)
    assert "legs" not in serialized
    assert "SELL" not in serialized


# --------------------------------------------------------------------------------------
# B terminal review (a6b945f): four residual counterexamples
# --------------------------------------------------------------------------------------


def test_router_sub_strategies_nested_price_key_never_reaches_signal(tmp_path: Path) -> None:
    """B 终判 #1：`router.sub_strategies.*` 未知键/价格键不得进入 SIGNAL（键白名单优先）。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["v3_cockpit"]["router"]["sub_strategies"]["unexpected"] = {"reference_price": 1.234}
    with pytest.raises(ledger.LedgerRefusal, match="未批准子策略键"):
        ingest(tmp_path, brief)
    assert ledger.read_events(root, "SIGNAL") == []


def test_english_order_text_in_state_block_never_reaches_signal(tmp_path: Path) -> None:
    """B 终判 #1：`SELL 777 shares @ 1.234` 这类英文自由文本不得进入 SIGNAL。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["v3_cockpit"]["router"]["sub_strategies"]["s_stock_swing"] = (
        "SELL 777 shares @ 1.234"
    )
    with pytest.raises(ledger.LedgerRefusal, match="封闭枚举"):
        ingest(tmp_path, brief)
    assert ledger.read_events(root, "SIGNAL") == []
    serialized = json.dumps(ledger.read_events(root, "SIGNAL"), ensure_ascii=False)
    assert "777" not in serialized and "1.234" not in serialized


def test_concentration_recommended_action_never_reaches_valuation(tmp_path: Path) -> None:
    """B 终判 #1：`concentration.recommended_action` 不得进入 VALUATION。"""
    root = init(tmp_path)
    concentration = {
        "hhi": 0.2,
        "equity_weight": 0.7,
        "cash_ratio": 0.3,
        "recommended_action": "SELL 777 shares @ 1.234",
    }
    ingest(tmp_path, make_brief(concentration=concentration))
    stored = ledger.read_events(root, "VALUATION")[0]["content"]["concentration"]
    assert stored == {"hhi": 0.2, "equity_weight": 0.7, "cash_ratio": 0.3}
    serialized = json.dumps(stored, ensure_ascii=False)
    assert "recommended_action" not in serialized
    assert "777" not in serialized
    assert "1.234" not in serialized


def test_trailing_newline_change_is_a_conflict_not_idempotent_noop(tmp_path: Path) -> None:
    """B 终判 #2：同一 brief 末尾加一个 LF → 源 SHA 变 → CONFLICT，不得 NOOP。"""
    root = init(tmp_path)
    brief = make_brief(status="NO_ACTION", actions=[])
    path = write_json(tmp_path / "brief.json", brief)
    calendar_db = calendar(tmp_path)
    ledger.ingest_brief(path, root=root, calendar_db=calendar_db)
    before = snapshot_bytes(root)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ledger.LedgerConflict, match="append-only"):
        ledger.ingest_brief(path, root=root, calendar_db=calendar_db)
    assert snapshot_bytes(root) == before


def test_broken_baseline_blocks_confirmed_fill_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B 终判 #3：verify 报 baseline↔SIGNAL 不符后，`ingest-fills` 必须零写入。"""
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    baseline = json.loads((root / ledger.POLICY_BASELINE_FILENAME).read_text(encoding="utf-8"))
    baseline["content_hash"] = "d" * 64
    write_json(root / ledger.POLICY_BASELINE_FILENAME, baseline)
    with pytest.raises(ledger.LedgerCorruption, match="policy_baseline"):
        ledger.verify_ledger(root)
    before = snapshot_bytes(root)
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    with pytest.raises(ledger.LedgerCorruption, match="policy_baseline"):
        ledger.ingest_confirmed_fills(portfolio_db=make_account_db(tmp_path), root=root)
    assert snapshot_bytes(root) == before
    assert ledger.read_events(root, "CONFIRMED_FILL") == []


def test_overflowing_json_number_in_unprojected_field_is_rejected(tmp_path: Path) -> None:
    """B 终判 #4：`1e999` 解析为 +Inf；未投影字段也必须拒绝整份输入。"""
    root = init(tmp_path)
    brief = make_brief()
    raw = json.dumps(brief, ensure_ascii=False)[:-1] + ', "spare": 1e999}'
    path = tmp_path / "brief.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ledger.LedgerRefusal, match="非有限"):
        ledger.ingest_brief(path, root=root, calendar_db=calendar(tmp_path))
    assert counts(root) == {record_type: 0 for record_type in ledger.RECORD_FILES}


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
def test_non_finite_json_literals_are_rejected(tmp_path: Path, literal: str) -> None:
    root = init(tmp_path)
    brief = make_brief()
    raw = json.dumps(brief, ensure_ascii=False)[:-1] + f', "spare": {literal}}}'
    path = tmp_path / "brief.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ledger.LedgerRefusal):
        ledger.ingest_brief(path, root=root, calendar_db=calendar(tmp_path))
    assert ledger.read_events(root, "SIGNAL") == []


# --------------------------------------------------------------------------------------
# Team-lead final: whitelist-first projection over every nested layer
# --------------------------------------------------------------------------------------


def test_chinese_free_text_in_router_sub_strategies_is_refused(tmp_path: Path) -> None:
    """终判 #4-a：`router.sub_strategies={'foo': '减仓三百股，限价一元二角'}` 必须拒绝。

    正则无法识别中文自由文本；这里靠键白名单 + 封闭枚举，而不是坏词匹配。
    """
    root = init(tmp_path)
    brief = make_brief()
    brief["v3_cockpit"]["router"]["sub_strategies"] = {
        "foo": "减仓三百股，限价一元二角"
    }
    with pytest.raises(ledger.LedgerRefusal):
        ingest(tmp_path, brief)
    assert ledger.read_events(root, "SIGNAL") == []
    assert counts(root) == {record_type: 0 for record_type in ledger.RECORD_FILES}


def test_chinese_free_text_as_known_sub_strategy_status_is_refused(tmp_path: Path) -> None:
    """终判 #4-a：即便键名合法（s_stock_swing），中文自由文本也不是枚举值。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["v3_cockpit"]["router"]["sub_strategies"]["s_stock_swing"] = (
        "减仓三百股，限价一元二角"
    )
    with pytest.raises(ledger.LedgerRefusal, match="封闭枚举"):
        ingest(tmp_path, brief)
    assert ledger.read_events(root, "SIGNAL") == []


def test_valuation_data_quality_trade_plan_executability_never_reaches_valuation(
    tmp_path: Path,
) -> None:
    """终判 #4-b：`data_quality.tiers.trade_plan_executability` 原样落盘 → 必须不落盘。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["data_quality"] = {
        "status": "OK",
        "summary_status": "OK",
        "missing_fields": [],
        "tiers": {
            "trade_plan_executability": {
                "status": "READY",
                "detail": "按计划可执行",
                "side": "SELL",
                "quantity": 300,
                "price_milli": 1234,
                "trade_plan": {"legs": [{"side": "SELL", "quantity": 300}]},
            }
        },
    }
    result = ingest(tmp_path, brief)
    assert result["status"] == "INGESTED"
    valuation = ledger.read_events(root, "VALUATION")[0]
    assert valuation["content"]["data_quality"] == {
        "status": "OK",
        "summary_status": "OK",
        "missing_fields": [],
    }
    serialized = json.dumps(valuation["content"]["data_quality"], ensure_ascii=False)
    for leaked in ("trade_plan_executability", "quantity", "price_milli", "legs", "SELL"):
        assert leaked not in serialized
    assert ledger.verify_ledger(root)["status"] == "OK"


def test_principal_proposed_exit_never_reaches_valuation(tmp_path: Path) -> None:
    """终判 #4-c：`principal.proposed_exit` 不得落盘（principal 只允许协议数值列）。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["v3_cockpit"]["principal"]["proposed_exit"] = {
        "side": "SELL",
        "quantity": 300,
        "price_milli": 1234,
    }
    with pytest.raises(ledger.LedgerRefusal, match="未批准字段"):
        ingest(tmp_path, brief)
    assert counts(root) == {record_type: 0 for record_type in ledger.RECORD_FILES}


def test_persisted_principal_with_unknown_key_is_corrupt() -> None:
    """已落盘 principal 出现 proposed_exit 等未知键 → verify 必须判 CORRUPT。"""
    content = {
        "brief_schema": ledger.BRIEF_SCHEMA,
        "report_id": "a" * 64,
        "status": "NO_ACTION",
        "generated_at": "2026-11-26T20:00:00+08:00",
        "principal": {
            "initial_principal_cents": 10_000_000,
            "current_nav_cents": 6_800_000,
            "to_principal_gap_cents": 3_200_000,
            "to_principal_return_needed_pct": 47.06,
            "loss_from_principal_pct": 32.0,
            "proposed_exit": {"quantity": 300},
        },
        "holdings": [],
        "concentration": None,
        "reconciliation_reminder": None,
        "data_quality": {"status": "OK", "summary_status": "OK", "missing_fields": []},
    }
    with pytest.raises(ledger.LedgerCorruption, match="未批准字段"):
        ledger._validate_valuation_content(
            content,
            tuple(
                sorted(
                    {
                        "concentration",
                        "v3_cockpit.reconciliation_reminder",
                        "holdings[0].name",
                    }
                )
            ),
        )


def test_unknown_state_block_key_is_dropped_not_persisted(tmp_path: Path) -> None:
    """状态块未知键（例如 `status_summary_zh`）剔除；持久化后再出现未知键 → CORRUPT。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["v3_cockpit"]["market_regime"]["free_text_zh"] = "减仓三百股"
    brief["v3_cockpit"]["router"]["free_text_zh"] = "限价一元二角"
    result = ingest(tmp_path, brief)
    assert result["status"] == "INGESTED"
    signal = ledger.read_events(root, "SIGNAL")[0]
    serialized = json.dumps(signal["content"], ensure_ascii=False)
    assert "减仓三百股" not in serialized
    assert "限价一元二角" not in serialized
    forged = copy.deepcopy(signal["content"])
    forged["router"]["free_text_zh"] = "限价一元二角"
    with pytest.raises(ledger.LedgerCorruption, match="未批准字段"):
        ledger._validate_signal_content(forged, tuple(signal["missing_fields"]))


def test_principal_cannot_borrow_holding_column_names(tmp_path: Path) -> None:
    """holdings 白名单只对 holdings[] 生效：`quantity`/`price_milli` 在 principal 里不豁免。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["v3_cockpit"]["principal"]["quantity"] = 300
    with pytest.raises(ledger.LedgerRefusal, match="未批准字段"):
        ingest(tmp_path, brief)
    assert counts(root) == {record_type: 0 for record_type in ledger.RECORD_FILES}


def test_holding_label_with_order_text_is_nulled_not_persisted(tmp_path: Path) -> None:
    """holdings[] 的 `name` 是唯一允许的展示标签；夹带动作/份数即置空并记缺失。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["holdings"] = [_holding(name="减仓三百股，限价一元二角")]
    result = ingest(tmp_path, brief)
    assert result["status"] == "INGESTED"
    valuation = ledger.read_events(root, "VALUATION")[0]
    assert valuation["content"]["holdings"][0]["name"] is None
    assert "holdings[0].name" in valuation["missing_fields"]
    serialized = json.dumps(valuation["content"], ensure_ascii=False)
    assert "减仓三百股" not in serialized
    assert ledger.verify_ledger(root)["status"] == "OK"


def test_holding_wrongly_typed_optional_field_is_nulled(tmp_path: Path) -> None:
    """holdings[] 可选字段类型不符（如 name 是对象）→ 置空并记缺失，不原样落盘。"""
    root = init(tmp_path)
    brief = make_brief()
    brief["holdings"] = [_holding(name={"nested": "SELL 777 shares @ 1.234"})]
    result = ingest(tmp_path, brief)
    assert result["status"] == "INGESTED"
    valuation = ledger.read_events(root, "VALUATION")[0]
    assert valuation["content"]["holdings"][0]["name"] is None
    assert ledger.verify_ledger(root)["status"] == "OK"


def test_persisted_holding_with_nested_label_is_corrupt() -> None:
    """已落盘 holding 的 label 字段不是字符串 → verify 判 CORRUPT。"""
    holding = {
        "ts_code": "a" * 32,
        "name": {"nested": "SELL"},
        "quantity": 1000,
        "weight": 0.15,
        "market_value_cents": 100_000,
        "price_milli": 100_000,
        "price_source": "server_cache_close",
        "latest_bar_date": AS_OF,
        "bar_quality": "READY",
        "diluted_cost_per_share": 1.0,
        "diluted_total_cost_cents": 100_000,
        "cost_basis": "broker_diluted",
    }
    content = {
        "brief_schema": ledger.BRIEF_SCHEMA,
        "report_id": "a" * 64,
        "status": "NO_ACTION",
        "generated_at": "2026-11-26T20:00:00+08:00",
        "principal": {
            "initial_principal_cents": 10_000_000,
            "current_nav_cents": 6_800_000,
            "to_principal_gap_cents": 3_200_000,
            "to_principal_return_needed_pct": 47.06,
            "loss_from_principal_pct": 32.0,
        },
        "holdings": [holding],
        "concentration": None,
        "reconciliation_reminder": None,
        "data_quality": {"status": "OK", "summary_status": "OK", "missing_fields": []},
    }
    with pytest.raises(ledger.LedgerCorruption):
        ledger._validate_valuation_content(
            content,
            tuple(sorted({"concentration", "v3_cockpit.reconciliation_reminder"})),
        )
