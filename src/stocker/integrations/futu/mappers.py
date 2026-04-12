"""Mappers: convert between Futu SDK types and Stocker broker models.

All mapping functions are pure – they never call the Futu SDK themselves.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from stocker.broker.models import (
    AccountInfo,
    Order,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
    PositionSource,
    TradeRecord,
)

logger = logging.getLogger(__name__)

# ======================================================================
# Ticker conversion
# ======================================================================


def convert_ticker_to_futu(ticker: str, default_market: str = "US") -> str:
    """Convert a generic ticker to Futu code format.

    Examples:
        AAPL           -> US.AAPL
        0700.HK        -> HK.00700
        600519.SS      -> SH.600519
        000001.SZ      -> SZ.000001
        HK.00700       -> HK.00700  (already Futu format)
    """
    t = ticker.strip()

    # Already in Futu format (XX.XXXXX)
    if "." in t:
        parts = t.split(".", 1)
        prefix = parts[0].upper()
        if prefix in ("HK", "US", "SH", "SZ", "SG", "JP", "AU"):
            return t.upper()

        suffix = parts[1].upper()
        if suffix == "HK":
            return f"HK.{parts[0].zfill(5)}"
        if suffix in ("SS", "SH"):
            return f"SH.{parts[0]}"
        if suffix == "SZ":
            return f"SZ.{parts[0]}"

    # Pure alphabetic -> default market (US)
    if t.isalpha():
        return f"{default_market.upper()}.{t.upper()}"

    return f"{default_market.upper()}.{t.upper()}"


def convert_futu_to_ticker(futu_code: str) -> str:
    """Convert Futu code back to conventional ticker.

    Examples:
        US.AAPL  -> AAPL
        HK.00700 -> 0700.HK
        SH.600519 -> 600519.SS
    """
    if "." not in futu_code:
        return futu_code

    market, symbol = futu_code.split(".", 1)
    market = market.upper()

    if market == "US":
        return symbol
    if market == "HK":
        return f"{symbol.lstrip('0') or '0'}.HK"
    if market == "SH":
        return f"{symbol}.SS"
    if market == "SZ":
        return f"{symbol}.SZ"

    return futu_code


# ======================================================================
# Order side / type mapping
# ======================================================================


def map_order_side_to_futu(side: OrderSide):
    """Map ``OrderSide`` -> ``futu.TrdSide``."""
    from futu import TrdSide

    return TrdSide.BUY if side == OrderSide.BUY else TrdSide.SELL


def map_order_type_to_futu(order_type: str):
    """Map stocker order_type string -> ``futu.OrderType``.

    Supports: market, limit, enhanced_limit, auction, auction_limit.
    Uses getattr to stay resilient across SDK versions where some
    OrderType members may not exist.
    """
    from futu import OrderType

    otype = order_type.lower().strip()

    if otype == "market":
        return OrderType.MARKET
    if otype == "limit":
        return OrderType.NORMAL
    if otype == "enhanced_limit":
        return getattr(OrderType, "ENHANCED_LIMIT",
                       getattr(OrderType, "SPECIAL_LIMIT", OrderType.NORMAL))
    if otype == "auction":
        return getattr(OrderType, "AUCTION", OrderType.MARKET)
    if otype == "auction_limit":
        return getattr(OrderType, "AUCTION_LIMIT", OrderType.NORMAL)

    # Default fallback
    return OrderType.MARKET


def map_futu_order_status(futu_status) -> OrderStatus:
    """Map ``futu.OrderStatus`` enum -> ``stocker.OrderStatus``.

    Uses string comparison to stay resilient across SDK versions.
    """
    s = str(futu_status).upper()

    if "FILLED_ALL" in s or "FILLED_PART" in s and "CANCELLED" in s:
        return OrderStatus.PARTIALLY_FILLED
    if "FILLED" in s:
        return OrderStatus.FILLED
    if "CANCEL" in s or "DELETED" in s:
        return OrderStatus.CANCELLED
    if "REJECT" in s or "FAILED" in s:
        return OrderStatus.REJECTED
    if "SUBMIT" in s or "WAITING" in s or "SUBMITTING" in s:
        return OrderStatus.PENDING

    return OrderStatus.PENDING


# ======================================================================
# DataFrame -> broker model mappers
# ======================================================================


def map_order_result(row: dict | pd.Series, broker: str = "futu") -> OrderResult:
    """Map a single row from order_list_query / place_order result to ``OrderResult``."""
    return OrderResult(
        order_id=str(row.get("order_id", "")),
        ticker=convert_futu_to_ticker(str(row.get("code", ""))),
        side=OrderSide.BUY if "BUY" in str(row.get("trd_side", "")).upper() else OrderSide.SELL,
        quantity=int(row.get("qty", 0) or row.get("order_qty", 0)),
        filled_price=float(row.get("dealt_avg_price", 0) or 0),
        status=map_futu_order_status(row.get("order_status", "")),
        timestamp=_parse_ts(row.get("create_time") or row.get("updated_time")),
        broker=broker,
        error=str(row.get("remark", "")) or None,
    )


def map_positions(df: pd.DataFrame, broker: str = "futu") -> list[Position]:
    """Map position_list_query DataFrame to list of ``Position``."""
    positions: list[Position] = []
    if df is None or df.empty:
        return positions

    for _, row in df.iterrows():
        futu_code = str(row.get("code", ""))
        market = futu_code.split(".")[0] if "." in futu_code else ""
        market_type_map = {"HK": "hk", "US": "us", "SH": "cn", "SZ": "cn"}

        positions.append(
            Position(
                ticker=convert_futu_to_ticker(futu_code),
                name=str(row.get("stock_name", "") or ""),
                quantity=int(row.get("qty", 0)),
                avg_cost=float(row.get("cost_price", 0) or 0),
                current_price=float(row.get("market_val", 0) or 0) / max(int(row.get("qty", 1)), 1),
                unrealized_pnl=float(row.get("pl_val", 0) or 0),
                source=PositionSource.BROKER_SYNCED,
                broker_account=str(row.get("acc_id", "")),
                market_type=market_type_map.get(market, ""),
                last_synced_at=datetime.now(),
            )
        )
    return positions


def map_account_info(row: dict | pd.Series, broker: str = "futu") -> AccountInfo:
    """Map accinfo_query row to ``AccountInfo``."""
    return AccountInfo(
        account_id=str(row.get("acc_id", "")),
        total_value=float(row.get("total_assets", 0) or 0),
        cash=float(row.get("cash", 0) or 0),
        buying_power=float(row.get("power", 0) or row.get("buying_power", 0) or 0),
        broker=broker,
    )


def map_trade_record(row: dict | pd.Series, broker: str = "futu") -> TradeRecord:
    """Map deal_list_query row to ``TradeRecord``."""
    return TradeRecord(
        trade_id=str(row.get("deal_id", "")),
        ticker=convert_futu_to_ticker(str(row.get("code", ""))),
        side="buy" if "BUY" in str(row.get("trd_side", "")).upper() else "sell",
        quantity=int(row.get("qty", 0)),
        price=float(row.get("price", 0) or 0),
        timestamp=_parse_ts(row.get("create_time")),
        broker=broker,
    )


# ======================================================================
# Helpers
# ======================================================================


def _parse_ts(raw: Any) -> datetime:
    """Best-effort parse a timestamp string from Futu."""
    if isinstance(raw, datetime):
        return raw
    if raw:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(raw), fmt)
            except ValueError:
                continue
    return datetime.now()
