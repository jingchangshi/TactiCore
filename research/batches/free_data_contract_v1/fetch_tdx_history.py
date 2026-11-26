#!/usr/bin/env python3
"""FREE_DATA_CONTRACT_V1：最小通达信（TDX）直连历史下载脚本。

只做协议第 3 节规定的事：按 `config/universe.csv` 的 12 只 ETF 拉取 TDX 日线原始 OHLC 与
除权除息事件（xdxr），按预注册公式生成后复权收盘价，写出快照与 manifest。

- 只用标准库 socket/zlib/struct（外加 pandas 写 CSV），不新增依赖；
- 报文格式对齐 FinanceMCP `src/ashare/providers/tdxClient.ts`；
- 缺失保持缺失；上市日后出现扩缩股（category 11/12）时 fail closed，不猜因子；
- 不调度、不写 repository 冻结域；输出目录已存在即拒绝。
"""

from __future__ import annotations

import hashlib
import json
import socket
import struct
import zlib
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
UNIVERSE_PATH = ROOT / "config/universe.csv"
SOURCE = "TDX (通达信) public quote servers, TCP 7709"
ADJUSTMENT = (
    "后复权：首个有效交易日因子 1.0；xdxr category 1 除权日因子 × prev_close / ref，"
    "ref = (prev_close × 10 − fenhong + peigu × peigujia) / (10 + songzhuangu + peigu)"
)
DEFAULT_HOSTS = (
    "180.153.18.170",
    "115.238.56.198",
    "218.75.126.9",
    "124.71.187.122",
    "110.41.147.114",
    "180.153.18.171",
)
PORT = 7709
HELLO1 = bytes.fromhex("0c0218930001030003000d0001")
HELLO2 = bytes.fromhex("0c0218940001030003000d0002")
DAILY_CATEGORY = 9
PAGE = 800
TIMEOUT_SECONDS = 10.0


class TdxSession:
    def __init__(self, host: str, port: int = PORT) -> None:
        self.host = host
        self.sock = socket.create_connection((host, port), timeout=TIMEOUT_SECONDS)
        self.request(HELLO1)
        self.request(HELLO2)

    def close(self) -> None:
        self.sock.close()

    def _read_exact(self, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise ConnectionError(f"TDX socket closed ({self.host})")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def request(self, packet: bytes) -> bytes:
        self.sock.sendall(packet)
        header = self._read_exact(16)
        zipsize, unzipsize = struct.unpack_from("<HH", header, 12)
        body = self._read_exact(zipsize)
        return body if zipsize == unzipsize else zlib.decompress(body)

    def daily_bars(self, market: int, code: str, start: int, count: int) -> list[dict[str, Any]]:
        packet = bytearray(38)
        struct.pack_into("<HIHHHH", packet, 0, 0x10C, 0x01016408, 0x1C, 0x1C, 0x052D, market)
        packet[14:20] = code.encode("ascii")
        struct.pack_into("<HHHH", packet, 20, DAILY_CATEGORY, 1, start, count)
        return parse_bars(self.request(bytes(packet)))

    def xdxr(self, market: int, code: str) -> list[dict[str, Any]]:
        packet = bytearray(21)
        packet[0:14] = bytes.fromhex("0c1f187600010b000b000f000100")
        packet[14] = market
        packet[15:21] = code.encode("ascii")
        return parse_xdxr(self.request(bytes(packet)))


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    byte = buf[pos]
    negative = bool(byte & 0x40)
    value = byte & 0x3F
    shift = 6
    while byte & 0x80:
        pos += 1
        byte = buf[pos]
        value += (byte & 0x7F) << shift
        shift += 7
    return (-value if negative else value), pos + 1


def _ymd(raw: int) -> str:
    return f"{raw // 10000:04d}-{(raw % 10000) // 100:02d}-{raw % 100:02d}"


def _tdx_float(raw: int) -> float:
    """TDX 成交量编码（与 FinanceMCP decodeTdxVolume 同式）；只用于识别零成交。"""
    if raw == 0:
        return 0.0
    logpoint, hleax, lheax, lleax = (
        (raw >> 24) & 0xFF,
        (raw >> 16) & 0xFF,
        (raw >> 8) & 0xFF,
        raw & 0xFF,
    )
    ecx, edx, esi, eax = (
        logpoint * 2 - 0x7F,
        logpoint * 2 - 0x86,
        logpoint * 2 - 0x8E,
        logpoint * 2 - 0x96,
    )
    xmm6 = 2.0**ecx
    xmm4 = (
        (2.0**edx) * 128 + (hleax & 0x7F) * 2.0 ** (edx + 1) if hleax > 0x80 else (2.0**edx) * hleax
    )
    xmm3 = (2.0**esi) * lheax
    xmm1 = (2.0**eax) * lleax
    if hleax & 0x80:
        xmm3 *= 2
        xmm1 *= 2
    return xmm6 + xmm4 + xmm3 + xmm1


def parse_bars(buf: bytes) -> list[dict[str, Any]]:
    if len(buf) < 2:
        return []
    (count,) = struct.unpack_from("<H", buf, 0)
    pos = 2
    previous_close = 0
    bars: list[dict[str, Any]] = []
    for _ in range(count):
        (zipday,) = struct.unpack_from("<I", buf, pos)
        pos += 4
        open_diff, pos = _varint(buf, pos)
        close_diff, pos = _varint(buf, pos)
        high_diff, pos = _varint(buf, pos)
        low_diff, pos = _varint(buf, pos)
        vol_raw, _amount_raw = struct.unpack_from("<II", buf, pos)
        pos += 8
        open_base = open_diff + previous_close
        close_base = open_base + close_diff
        previous_close = close_base
        bars.append(
            {
                "date": _ymd(zipday),
                "open": open_base / 1000,
                "high": (open_base + high_diff) / 1000,
                "low": (open_base + low_diff) / 1000,
                "close": close_base / 1000,
                "volume": _tdx_float(vol_raw),
            }
        )
    return bars


def parse_xdxr(buf: bytes) -> list[dict[str, Any]]:
    if len(buf) < 11:
        return []
    (count,) = struct.unpack_from("<H", buf, 9)
    pos = 11
    events: list[dict[str, Any]] = []
    for _ in range(count):
        pos += 8
        (zipday,) = struct.unpack_from("<I", buf, pos)
        pos += 4
        category = buf[pos]
        pos += 1
        a, b, c, d = struct.unpack_from("<ffff", buf, pos)
        pos += 16
        event: dict[str, Any] = {"date": _ymd(zipday), "category": int(category)}
        if category == 1:
            event.update(fenhong=a, peigujia=b, songzhuangu=c, peigu=d)
        elif category in (11, 12):
            event.update(suogu=c)
        events.append(event)
    return events


def market_of(symbol: str) -> int:
    suffix = symbol.rsplit(".", 1)[1]
    if suffix == "SS":
        return 1
    if suffix == "SZ":
        return 0
    raise ValueError(f"未知交易所后缀: {symbol}")


def fetch_symbol(
    session: TdxSession, symbol: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    market = market_of(symbol)
    code = symbol[:6]
    by_date: dict[str, dict[str, Any]] = {}
    start = 0
    while True:
        page = session.daily_bars(market, code, start, PAGE)
        for bar in page:
            by_date.setdefault(bar["date"], bar)
        if len(page) < PAGE:
            break
        start += PAGE
    if not by_date:
        raise RuntimeError(f"{symbol} 未返回日线")
    return [by_date[key] for key in sorted(by_date)], session.xdxr(market, code)


def back_adjust(
    symbol: str, bars: list[dict[str, Any]], events: list[dict[str, Any]], list_date: str
) -> tuple[pd.Series, list[dict[str, Any]]]:
    """按协议第 3 节生成后复权收盘价；返回序列与实际应用的因子事件。"""
    traded = [
        bar for bar in bars if bar["date"] >= list_date and bar["volume"] > 0 and bar["close"] > 0
    ]
    if not traded:
        raise ValueError(f"{symbol} 上市后没有有效成交")
    for event in events:
        if event["category"] in (11, 12) and event["date"] > list_date:
            raise ValueError(f"{symbol} 上市后存在扩缩股事件 {event}；协议要求 fail closed")
    dividends = {event["date"]: event for event in events if event["category"] == 1}
    factor = 1.0
    previous_close: float | None = None
    applied: list[dict[str, Any]] = []
    values: dict[str, float] = {}
    pending = sorted(date for date in dividends if date > traded[0]["date"])
    for bar in traded:
        while pending and pending[0] <= bar["date"]:
            event = dividends[pending.pop(0)]
            if previous_close is None:
                raise ValueError(f"{symbol} 除权事件 {event['date']} 缺少前收")
            ref = (previous_close * 10 - event["fenhong"] + event["peigu"] * event["peigujia"]) / (
                10 + event["songzhuangu"] + event["peigu"]
            )
            if not ref > 0:
                raise ValueError(f"{symbol} 除权参考价非正: {event}")
            ratio = previous_close / ref
            factor *= ratio
            applied.append(
                {
                    **event,
                    "effective_bar": bar["date"],
                    "prev_close": previous_close,
                    "ratio": ratio,
                }
            )
        values[bar["date"]] = bar["close"] * factor
        previous_close = bar["close"]
    series = pd.Series(values, dtype=float)
    series.index = pd.DatetimeIndex(series.index, name="date")
    return series.rename(symbol), applied


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/free_v1")
    args = parser.parse_args()

    universe = pd.read_csv(UNIVERSE_PATH, dtype=str)
    downloaded_at = datetime.now(timezone.utc).replace(microsecond=0)
    destination = args.output_root / f"tdx_{downloaded_at.strftime('%Y%m%dT%H%M%SZ')}"
    if destination.exists():
        raise SystemExit(f"输出目录已存在，拒绝覆盖: {destination}")

    errors: list[str] = []
    session: TdxSession | None = None
    for host in DEFAULT_HOSTS:
        try:
            session = TdxSession(host)
            session.daily_bars(1, "510300", 0, 1)
            break
        except OSError as error:
            errors.append(f"{host}: {error}")
            session = None
    if session is None:
        raise SystemExit(f"全部 TDX 主站失败: {errors}")

    series: list[pd.Series] = []
    raw_rows: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    try:
        for row in universe.itertuples(index=False):
            symbol, list_date = str(row.symbol), str(row.start_date)
            bars, events = fetch_symbol(session, symbol)
            adjusted, applied = back_adjust(symbol, bars, events, list_date)
            series.append(adjusted)
            raw_rows.extend({"symbol": symbol, **bar} for bar in bars)
            zero_volume = [
                bar["date"] for bar in bars if bar["date"] >= list_date and bar["volume"] <= 0
            ]
            records.append(
                {
                    "symbol": symbol,
                    "tdx_market": market_of(symbol),
                    "tdx_code": symbol[:6],
                    "list_date": list_date,
                    "raw_bars": len(bars),
                    "raw_first_date": bars[0]["date"],
                    "adjusted_rows": int(adjusted.size),
                    "first_observation": adjusted.index.min().date().isoformat(),
                    "last_observation": adjusted.index.max().date().isoformat(),
                    "dropped_pre_listing_bars": sum(1 for bar in bars if bar["date"] < list_date),
                    "dropped_zero_volume_bars": zero_volume,
                    "xdxr_events": events,
                    "applied_factor_events": applied,
                }
            )
    finally:
        session.close()

    prices = pd.concat(series, axis=1).sort_index()
    prices.index.name = "date"
    destination.mkdir(parents=True)
    prices_path = destination / "etf_adjusted_close.csv"
    raw_path = destination / "tdx_raw_daily.csv"
    prices.to_csv(
        prices_path, date_format="%Y-%m-%d", float_format="%.8f", na_rep="", lineterminator="\n"
    )
    pd.DataFrame(raw_rows).to_csv(raw_path, index=False, float_format="%.6f", lineterminator="\n")
    manifest = {
        "contract": "FREE_DATA_CONTRACT_V1",
        "protocol": "research/batches/free_data_contract_v1/PROTOCOL_V1.md",
        "source": SOURCE,
        "host": session.host,
        "request": {"category": DAILY_CATEGORY, "page_size": PAGE, "xdxr": "get_xdxr_info"},
        "download_timestamp": downloaded_at.isoformat(),
        "universe": {"path": "config/universe.csv", "sha256": sha256(UNIVERSE_PATH)},
        "adjustment": ADJUSTMENT,
        "availability": (
            "trade_date 收盘价只在该日 15:00 Asia/Shanghai 后可用；xdxr 按除权日生效；"
            "历史为下载时刻的供应商当前视图，修订历史未知"
        ),
        "missing_values": "缺失保持缺失，不前向填充、插值、置零或猜测；零成交 bar 不产生价格行",
        "symbols": records,
        "files": {
            prices_path.name: {"sha256": sha256(prices_path), "rows": int(len(prices))},
            raw_path.name: {"sha256": sha256(raw_path), "rows": len(raw_rows)},
        },
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(destination)


if __name__ == "__main__":
    main()
