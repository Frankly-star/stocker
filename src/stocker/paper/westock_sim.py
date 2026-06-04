"""Westock-data driven paper trading simulation.

This module deliberately does not call broker/Futu APIs. Prices come from the
fixed westock-data route unless an explicit test/control price is provided.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from stocker.broker.models import Position, PositionSource


def get_westock_paper_status(
    *,
    position_store,
    trade_store,
    initial_cash: float = 100_000.0,
    refresh_prices: bool = True,
) -> dict:
    positions = position_store.list_all() if position_store is not None else []
    if refresh_prices and position_store is not None:
        positions = _refresh_position_prices(position_store, positions)

    cash = _compute_cash(initial_cash, trade_store)
    positions_value = sum(float(p.current_price or 0.0) * int(p.quantity or 0) for p in positions)
    return {
        "ready": position_store is not None and trade_store is not None,
        "broker": "westock-paper",
        "account": {
            "account_id": "WESTOCK-PAPER",
            "total_value": cash + positions_value,
            "cash": cash,
            "buying_power": cash,
            "broker": "westock-paper",
        },
        "positions": [p.model_dump(mode="json") for p in positions],
    }


def place_westock_paper_order(
    *,
    ticker: str,
    action: str,
    quantity: int,
    position_store,
    trade_store,
    initial_cash: float = 100_000.0,
    price: float | None = None,
) -> dict:
    if position_store is None or trade_store is None:
        return {"status": "rejected", "error": "position_store or trade_store unavailable"}
    action = action.lower().strip()
    ticker = ticker.upper().strip()
    if action not in ("buy", "sell"):
        return {"status": "rejected", "error": "action must be buy or sell"}
    if quantity <= 0:
        return {"status": "rejected", "error": "quantity must be positive"}

    quote = _resolve_quote(ticker, price)
    resolved_price = float(quote.get("price") or 0.0)
    if resolved_price <= 0:
        return {"status": "rejected", "error": quote.get("error") or "westock quote unavailable", "quote": quote}

    cash_before = _compute_cash(initial_cash, trade_store)
    total = resolved_price * quantity
    if action == "buy" and total > cash_before:
        return {"status": "rejected", "error": "insufficient paper cash", "cash": cash_before, "quote": quote}
    if action == "sell":
        existing = position_store.get(ticker)
        if existing is None or existing.quantity < quantity:
            return {"status": "rejected", "error": "insufficient paper shares", "quote": quote}

    trade_id = f"WP-{uuid4().hex[:8]}"
    if action == "buy":
        position = position_store.add(
            ticker=ticker,
            quantity=quantity,
            avg_cost=resolved_price,
            source=PositionSource.MANUAL_IMPORT,
        )
        position.current_price = resolved_price
        position.update_price(resolved_price)
        position.broker_account = "westock-paper"
        position.last_synced_at = datetime.now()
        position_store._save()
    else:
        position = position_store.get(ticker)
        position.quantity -= quantity
        if position.quantity <= 0:
            position_store.remove(ticker)
        else:
            position.current_price = resolved_price
            position.update_price(resolved_price)
            position.last_synced_at = datetime.now()
            position_store._save()

    trade_record = {
        "trade_id": trade_id,
        "ticker": ticker,
        "side": action,
        "quantity": quantity,
        "price": resolved_price,
        "timestamp": datetime.now().isoformat(),
        "broker": "westock-paper",
        "notes": "westock_paper; source=westock-data" + ("; price=explicit" if price else ""),
    }
    trade_store.add(trade_record)

    status = get_westock_paper_status(
        position_store=position_store,
        trade_store=trade_store,
        initial_cash=initial_cash,
        refresh_prices=False,
    )
    return {
        "status": "filled",
        "trade_id": trade_id,
        "ticker": ticker,
        "side": action,
        "quantity": quantity,
        "filled_price": resolved_price,
        "broker": "westock-paper",
        "quote": quote,
        "account_after": status["account"],
        "positions_after": status["positions"],
    }


def _resolve_quote(ticker: str, explicit_price: float | None = None) -> dict:
    if explicit_price and explicit_price > 0:
        return {"ticker": ticker, "price": float(explicit_price), "source": "explicit"}
    try:
        from stocker.utils.data_helpers import fetch_quote_westock
        quote = fetch_quote_westock(ticker)
        quote["source"] = "westock-data"
        return quote
    except Exception as e:
        return {"ticker": ticker, "price": 0.0, "error": str(e), "source": "westock-data"}


def _refresh_position_prices(position_store, positions: list[Position]) -> list[Position]:
    changed = False
    for position in positions:
        quote = _resolve_quote(position.ticker)
        price = float(quote.get("price") or 0.0)
        if price > 0:
            position.update_price(price)
            position.last_synced_at = datetime.now()
            changed = True
    if changed:
        position_store._save()
    return position_store.list_all()


def _compute_cash(initial_cash: float, trade_store) -> float:
    cash = float(initial_cash)
    if trade_store is None:
        return cash
    for trade in trade_store.list_all():
        if getattr(trade, "broker", "") != "westock-paper":
            continue
        value = float(trade.price or 0.0) * int(trade.quantity or 0)
        if str(trade.side).lower() == "buy":
            cash -= value
        elif str(trade.side).lower() == "sell":
            cash += value
    return cash
