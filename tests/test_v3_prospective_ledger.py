"""V3 前瞻台账的合成测试。

全部使用 `tmp_path`、合成 brief、合成 SQLite 账户库与合成交易日历；不读取任何真实
2026-11 之后的市场/账户数据，不写生产 DB，不产生真实观测。
"""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from research.experiments import v3_prospective_ledger as ledger

AS_OF = "20261126"
NEXT_DAY = "20261127"
GENERATED_AT = "2026-11-26T12:00:00Z"
NOW = datetime(2026, 11, 26, 13, 0, tzinfo=timezone.utc)  # 21:00 Asia/Shanghai
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


def _action(code: str = "P3-SUPER-ETF-REBALANCE", rank: int = 1, executable: bool = True) -> dict:
    return {
        "priority": "P3",
        "code": code,
        "kind": "ROTATE",
        "rank": rank,
        "title": "合成动作",
        "reasons": ["合成理由"],
        "counter_evidence": ["合成反证"],
        "legs": [
            {
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
                "executable": executable,
                "reason": "P3_SYNTHETIC",
            }
        ],
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
            "raw_regime": "DEFENSIVE",
            "style": "VALUE_LEADING",
            "target_equity_bps": 1500,
            "pct_above_ma60": 0.1,
            "amount_vs_ma20": 1.0,
        },
        "router": {
            "effective_regime": "DEFENSIVE",
            "circuit_breaker_status": "NORMAL",
            "sub_strategies": {"s_stock_swing": "STOP_ONLY"},
        },
        "deconcentration": {
            "plan_present": True,
            "ts_code": "159558.SZ",
            "recommended_sell_shares": 0,
            "recommended_buy_shares": 0,
            "tranches": [{"tranche_no": 1, "status": "PENDING"}],
        },
        "reconciliation_reminder": {"lag_trade_days": 1, "needs_reminder": False},
        "actions_summary": [],
    }


def _holding() -> dict:
    return {
        "ts_code": "511010.SH",
        "name": "国债ETF",
        "quantity": 1000,
        "weight": 0.15,
        "market_value_cents": 100_000,
        "price_milli": 100_000,
        "price_source": "server_cache_close",
        "latest_bar_date": AS_OF,
        "bar_quality": "READY",
        "stance": "HOLD",
        "diluted_cost_per_share": 1.0,
        "diluted_total_cost_cents": 100_000,
        "cost_basis": "broker_diluted",
    }


def make_brief(
    *,
    as_of: str = AS_OF,
    generated_at: str = GENERATED_AT,
    status: str = "ACTIONABLE",
    actions: list[dict] | None = None,
    cockpit: dict | None | str = "default",
    holdings: list[dict] | None = None,
    concentration: dict | None | str = "default",
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
            "observation_triggers": ["合成观察触发"],
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


def ingest(tmp_path: Path, brief: dict, *, name: str = "brief.json") -> dict:
    return ledger.ingest_brief(write_json(tmp_path / name, brief), root=tmp_path / "ledger")


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


def make_calendar_db(tmp_path: Path, days: list[str]) -> Path:
    path = tmp_path / "ashare.sqlite"
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
        connection.commit()
    finally:
        connection.close()
    return path


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
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
    # recommendation 永远不会自动生成成交
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
    assert signal["content"]["decision"]["no_action_reason"]
    assert signal["content"]["decision"]["evidence_complete"] is True


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
    changed = make_brief(as_of=NEXT_DAY, generated_at="2026-11-27T12:00:00Z")
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


# --------------------------------------------------------------------------------------
# Anti-backfill and temporal rules
# --------------------------------------------------------------------------------------


def test_brief_before_earliest_eligible_day_is_rejected(tmp_path: Path) -> None:
    root = init(tmp_path)
    before = snapshot_bytes(root)
    brief = make_brief(as_of="20261125", generated_at="2026-11-25T12:00:00Z")
    brief["expected_next_trade_date"] = AS_OF
    with pytest.raises(ledger.LedgerRefusal, match="最早合格日"):
        ingest(tmp_path, brief)
    assert snapshot_bytes(root) == before


def test_brief_must_be_ingested_on_its_own_shanghai_day() -> None:
    brief = make_brief()
    with pytest.raises(ledger.LedgerRefusal, match="当天追加"):
        ledger._validate_brief(
            brief, account_id="real-main", now=datetime(2026, 11, 27, 13, tzinfo=timezone.utc)
        )


def test_brief_generated_in_the_future_is_rejected() -> None:
    brief = make_brief()
    with pytest.raises(ledger.LedgerRefusal, match="尚未生成"):
        ledger._validate_brief(
            brief, account_id="real-main", now=datetime(2026, 11, 26, 11, tzinfo=timezone.utc)
        )


def test_brief_generated_on_a_different_shanghai_day_is_rejected() -> None:
    brief = make_brief(generated_at="2026-11-25T12:00:00Z")
    with pytest.raises(ledger.LedgerRefusal, match="上海日历日"):
        ledger._validate_brief(brief, account_id="real-main", now=NOW)


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


def test_actionable_brief_without_executable_quantity_is_rejected() -> None:
    brief = make_brief()
    brief["execution_plan"]["actions"][0]["legs"][0]["quantity"] = 0
    brief["first_section"]["actions"][0]["legs"][0]["quantity"] = 0
    with pytest.raises(ledger.LedgerRefusal, match="数量必须为正"):
        ledger._validate_brief(brief, account_id="real-main", now=NOW)


def test_brief_with_fill_fields_inside_recommendation_is_rejected() -> None:
    brief = make_brief()
    brief["execution_plan"]["actions"][0]["realized_weights"] = {"511010.SH": 1.0}
    brief["first_section"]["actions"][0]["realized_weights"] = {"511010.SH": 1.0}
    with pytest.raises(ledger.LedgerRefusal, match="成交字段"):
        ledger._validate_brief(brief, account_id="real-main", now=NOW)


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


def test_fill_import_requires_a_verified_real_account(tmp_path: Path) -> None:
    root = init(tmp_path)
    db = make_account_db(tmp_path)
    connection = sqlite3.connect(db)
    try:
        connection.execute("DELETE FROM account_meta")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ledger.LedgerRefusal, match="real_account_verified"):
        ledger.ingest_confirmed_fills(portfolio_db=db, root=root)


def test_fill_reversed_after_import_blocks_further_ingest(
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
        connection.execute(
            "UPDATE account_event SET reversed_by = 'rev-9' WHERE event_id = 'fill-1'"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ledger.LedgerRefusal, match="SOURCE_REVERSED_AFTER_IMPORT"):
        ledger.ingest_confirmed_fills(portfolio_db=db, root=root)


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


def test_status_matches_confirmed_fills_but_does_not_call_them_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    db = make_account_db(tmp_path)
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    report = ledger.status_report(root)
    review = report["recommendation_review"][0]
    assert review["match_status"] == "MATCHED"
    assert review["matched_fill_event_ids"]
    assert report["unresolved_recommendation_event_ids"] == []


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
    assert review["matched_fill_event_ids"] == []
    assert report["unmatched_fill_event_ids"]


def test_status_reports_partial_when_only_one_leg_has_a_fill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    action = _action()
    action["legs"].append(
        {
            "side": "SELL",
            "ts_code": "159558.SZ",
            "quantity": 100,
            "price_milli": 100_000,
            "executable": True,
        }
    )
    ingest(tmp_path, make_brief(actions=[action]))
    db = make_account_db(tmp_path)
    monkeypatch.setattr(
        ledger, "utc_now", lambda: datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
    )
    ledger.ingest_confirmed_fills(portfolio_db=db, root=root)
    report = ledger.status_report(root)
    review = report["recommendation_review"][0]
    assert review["match_status"] == "PARTIAL"
    assert review["matched_leg_indices"] == [0]
    assert review["executable_leg_indices"] == [0, 1]
    assert report["unresolved_recommendation_event_ids"]


def test_status_derives_missed_days_from_the_read_only_calendar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = init(tmp_path)
    ingest(tmp_path, make_brief())
    calendar = make_calendar_db(
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
    report = ledger.status_report(root, calendar_db=calendar)
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


def test_status_flags_signal_action_without_recommendation(tmp_path: Path) -> None:
    root = init(tmp_path)
    brief = make_brief()
    brief["v3_cockpit"]["deconcentration"]["recommended_sell_shares"] = 1000
    ingest(tmp_path, brief)
    report = ledger.status_report(root)
    assert any(
        warning.startswith("SIGNAL_ACTION_WITHOUT_RECOMMENDATION") for warning in report["warnings"]
    )


def test_cli_end_to_end_ingest_verify_and_status(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "ledger"
    assert ledger.main(["--ledger-root", str(root), "init"]) == 0
    capsys.readouterr()
    brief_path = write_json(tmp_path / "brief.json", make_brief())
    assert (
        ledger.main(["--ledger-root", str(root), "ingest-brief", "--brief", str(brief_path)]) == 0
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


def test_cli_refusal_returns_json_and_exit_code_two(tmp_path: Path, capsys) -> None:
    root = init(tmp_path)
    brief = make_brief(as_of="20261125", generated_at="2026-11-25T12:00:00Z")
    brief["expected_next_trade_date"] = AS_OF
    path = write_json(tmp_path / "old.json", brief)
    exit_code = ledger.main(["--ledger-root", str(root), "ingest-brief", "--brief", str(path)])
    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "REFUSED"
    assert "最早合格日" in payload["error"]
