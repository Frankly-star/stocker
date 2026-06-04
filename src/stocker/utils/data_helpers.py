"""Data helpers for the fixed Stocker market-data route.

K-line/OHLCV data used by watchlist and signal scans comes from westock-data
only. No automatic fallback is performed; callers receive ``None`` when the
fixed source is unavailable or cannot be parsed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

from stocker.agents.intelligence.data_fetcher import _convert_to_westock_code

logger = logging.getLogger(__name__)


_PRICE_KEYS = {
    "open": "Open",
    "o": "Open",
    "high": "High",
    "h": "High",
    "low": "Low",
    "l": "Low",
    "close": "Close",
    "c": "Close",
    "price": "Close",
    "volume": "Volume",
    "vol": "Volume",
    "v": "Volume",
}
_DATE_KEYS = ("date", "time", "datetime", "day")


def fetch_ohlcv_westock(ticker: str, count: int = 120, min_bars: int = 30) -> pd.DataFrame | None:
    """Fetch daily OHLCV data via westock-data only."""
    try:
        from stocker.skills.westock_data import _run_westock

        code = _convert_to_westock_code(ticker)
        raw = _run_westock(["kline", code, "day", str(count), "qfq"], timeout=30)
        df = parse_westock_kline(raw)
        if df is not None and len(df) >= min_bars:
            return df.tail(count)
        logger.warning("westock kline unavailable for %s: insufficient parsed bars", ticker)
    except Exception as e:
        logger.warning("westock kline fetch for %s failed: %s", ticker, e)
    return None


def fetch_quote_westock(ticker: str, timeout: int = 15) -> dict[str, Any]:
    """Fetch and parse a realtime quote via westock-data only."""
    from stocker.skills.westock_data import _run_westock

    code = _convert_to_westock_code(ticker)
    raw = _run_westock(["quote", code], timeout=timeout)
    quote = parse_westock_quote(raw)
    quote["ticker"] = ticker.upper()
    quote["code"] = code
    return quote


def parse_westock_quote(raw: str | None) -> dict[str, Any]:
    """Parse common westock-data quote JSON/table outputs."""
    if not raw:
        return {"price": 0.0, "error": "no data"}
    text = str(raw).strip()
    if not text:
        return {"price": 0.0, "error": "empty response"}
    if "error" in text.lower()[:120] or "timeout" in text.lower()[:120]:
        return {"price": 0.0, "error": text[:200]}

    try:
        payload = json.loads(text)
        item: Any = payload
        if isinstance(payload, dict) and "data" in payload:
            item = payload["data"]
        if isinstance(item, list) and item:
            item = item[0]
        if isinstance(item, dict):
            price = _first_float(item, ("last", "price", "close", "current", "now"))
            change_pct = _first_float(item, ("changePercent", "changePct", "change_percent"), default=0.0)
            name = item.get("name", "") or item.get("stockName", "") or item.get("symbol", "")
            if price > 0:
                return {"price": price, "change_pct": change_pct, "name": name, "raw": item}
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    records = _extract_table_records(text)
    if records:
        row = records[0]
        price = _first_float(row, ("price", "last", "close", "prev_close", "current", "now"))
        change_pct = _first_float(row, ("change_percent", "changepercent", "change_pct"), default=0.0)
        name = row.get("name", "") or row.get("symbol", "")
        if price > 0:
            return {"price": price, "change_pct": change_pct, "name": name, "raw": row}

    return {"price": 0.0, "error": "parse failed", "raw_preview": text[:300]}


def parse_westock_kline(raw: str | None) -> pd.DataFrame | None:
    """Parse common westock-data K-line JSON/table outputs into OHLCV columns."""
    if not raw:
        return None
    text = str(raw).strip()
    if not text or "error" in text.lower()[:120] or "timeout" in text.lower()[:120]:
        return None

    records = _extract_json_records(text)
    if not records:
        records = _extract_table_records(text)
    if not records:
        return None

    rows: list[dict[str, Any]] = []
    for rec in records:
        row: dict[str, Any] = {}
        for key, value in rec.items():
            lk = str(key).strip().lower()
            if lk in _DATE_KEYS:
                row["Date"] = value
            elif lk in _PRICE_KEYS:
                row[_PRICE_KEYS[lk]] = value
        if {"Open", "High", "Low", "Close"}.issubset(row):
            rows.append(row)

    if not rows:
        return None

    df = pd.DataFrame(rows)
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "Volume" not in df.columns:
        df["Volume"] = 0
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if "Date" in df.columns:
        df = df.sort_values("Date")
        df.index = pd.to_datetime(df["Date"], errors="coerce")
    return df[["Open", "High", "Low", "Close", "Volume"]] if not df.empty else None


def _first_float(item: dict[str, Any], keys: tuple[str, ...], default: float = 0.0) -> float:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        try:
            return float(str(value).replace("%", ""))
        except (TypeError, ValueError):
            continue
    return default


def _extract_json_records(text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []

    candidates: Any = payload
    if isinstance(payload, dict):
        for key in ("data", "items", "klines", "kline", "rows"):
            value = payload.get(key)
            if value:
                candidates = value
                break
    if isinstance(candidates, dict):
        for key in ("items", "klines", "rows"):
            value = candidates.get(key)
            if isinstance(value, list):
                candidates = value
                break
    if not isinstance(candidates, list):
        return []

    records = []
    for item in candidates:
        if isinstance(item, dict):
            records.append(item)
        elif isinstance(item, list) and len(item) >= 5:
            records.append({
                "date": item[0],
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5] if len(item) > 5 else 0,
            })
    return records


def _extract_table_records(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip() and "|" in line]
    headers: list[str] | None = None
    records: list[dict[str, Any]] = []
    for line in lines:
        if all(ch in "-| " for ch in line):
            continue
        cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        if not cells:
            continue
        if headers is None:
            headers = [cell.lower() for cell in cells]
            continue
        if len(cells) >= len(headers):
            records.append(dict(zip(headers, cells)))
    return records
