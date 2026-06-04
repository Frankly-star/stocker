"""ExecutionSubgraph: order validation → risk check → broker execution → event publishing."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from stocker.broker.base import BaseBroker
from stocker.broker.models import Order, OrderSide
from stocker.graphs.state import ExecutionState

logger = logging.getLogger(__name__)


def _resolve_current_price(ticker: str) -> float | None:
    """Resolve current market price for a ticker.

    Priority: FutuRuntime snapshot → westock-data quote → None.
    Used to convert market orders to limit orders for HK simulate.
    """
    # 1. Try FutuRuntime (fastest, already connected)
    try:
        from stocker.engine.runtime import get_active_runtime
        from stocker.integrations.futu.mappers import convert_ticker_to_futu

        rt = get_active_runtime()
        if rt is not None and rt.started:
            futu_code = convert_ticker_to_futu(ticker, rt.config.market)
            snap = rt.get_snapshot(futu_code)
            if snap:
                # Try last_price, then nominal_price, then prev_close
                for key in ("last_price", "nominal_price", "prev_close_price"):
                    val = snap.get(key)
                    if val and float(val) > 0:
                        logger.info("Resolved price for %s via Futu snapshot: %.2f (%s)",
                                    ticker, float(val), key)
                        return float(val)
    except Exception as e:
        logger.debug("Futu price resolve failed for %s: %s", ticker, e)

    # 2. Try westock-data fixed quote route
    try:
        import json
        from stocker.agents.intelligence.data_fetcher import _convert_to_westock_code
        from stocker.skills.westock_data import _run_westock

        code = _convert_to_westock_code(ticker)
        raw = _run_westock(["quote", code], timeout=15)
        if raw and "error" not in raw.lower()[:120] and "timeout" not in raw.lower()[:120]:
            try:
                data = json.loads(raw)
                item = data.get("data", data) if isinstance(data, dict) else data
                if isinstance(item, list) and item:
                    item = item[0]
                if isinstance(item, dict):
                    price = item.get("last") or item.get("price") or item.get("close")
                    if price and float(price) > 0:
                        logger.info("Resolved price for %s via westock-data: %.2f", ticker, float(price))
                        return float(price)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

            lines = [line.strip() for line in raw.splitlines() if line.strip() and "|" in line]
            headers = None
            for line in lines:
                if all(ch in "-| " for ch in line):
                    continue
                cells = [cell.strip() for cell in line.split("|") if cell.strip()]
                if headers is None:
                    headers = [cell.lower() for cell in cells]
                    continue
                row = dict(zip(headers, cells))
                for key in ("price", "last", "close", "prev_close"):
                    try:
                        price = float(row.get(key, ""))
                        if price > 0:
                            logger.info("Resolved price for %s via westock-data: %.2f", ticker, price)
                            return price
                    except (ValueError, TypeError):
                        continue
    except Exception as e:
        logger.debug("westock-data price resolve failed for %s: %s", ticker, e)


    return None


def build_execution_graph(broker: BaseBroker) -> StateGraph:
    """Build the Execution Subgraph."""

    def validate_order(state: dict) -> dict:
        params = state.get("order_params", {})
        if not params:
            return {"execution_result": {"error": "No order params"}, "risk_check_passed": False}

        required = ["ticker", "side", "quantity"]
        missing = [f for f in required if f not in params]
        if missing:
            return {"execution_result": {"error": f"Missing fields: {missing}"}, "risk_check_passed": False}

        return {"risk_check_passed": True}

    def risk_check(state: dict) -> dict:
        if not state.get("risk_check_passed"):
            return state

        params = state.get("order_params", {})
        quantity = params.get("quantity", 0)

        # Basic risk checks
        if quantity <= 0:
            return {"execution_result": {"error": "Invalid quantity"}, "risk_check_passed": False}
        if quantity > 10000:
            return {"execution_result": {"error": "Quantity exceeds max limit (10000)"}, "risk_check_passed": False}

        return {"risk_check_passed": True}

    def should_execute(state: dict) -> str:
        return "execute" if state.get("risk_check_passed") else "reject"

    def execute_order(state: dict) -> dict:
        params = state.get("order_params", {})
        price = params.get("price") or 0.0
        order_type = params.get("order_type", "market")
        ticker = params["ticker"]

        # --- Smart price resolution ---
        # Futu HK simulate does not support true market orders (price=0).
        # When price is 0 or order_type is "market", fetch current price
        # and convert to a limit order automatically.
        if price <= 0 or order_type == "market":
            resolved_price = _resolve_current_price(ticker)
            if resolved_price and resolved_price > 0:
                # Add small buffer: +0.5% for buy, -0.5% for sell
                side = params.get("side", "buy").lower()
                if side == "buy":
                    price = round(resolved_price * 1.005, 2)
                else:
                    price = round(resolved_price * 0.995, 2)
                order_type = "limit"
                logger.info("Smart price: %s %s resolved %.2f -> limit @ %.2f",
                            side, ticker, resolved_price, price)
            else:
                logger.warning("Could not resolve price for %s, trying market order as-is", ticker)

        order = Order(
            ticker=ticker,
            side=OrderSide(params["side"]),
            quantity=params["quantity"],
            price=price if price > 0 else None,
            order_type=order_type,
        )
        try:
            # broker.place_order is async — bridge to sync context
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Already inside an async loop (e.g. FastAPI) — run in new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(asyncio.run, broker.place_order(order)).result()
            else:
                result = asyncio.run(broker.place_order(order))

            return {"execution_result": result.model_dump(mode="json")}
        except Exception as e:
            error_msg = str(e)
            if "not connected" in error_msg.lower():
                error_msg = f"Broker 连接已断开，请检查 OpenD 状态: {e}"
            elif "unlock" in error_msg.lower():
                error_msg = f"交易未解锁，请检查交易密码配置: {e}"
            elif "购买力" in error_msg:
                error_msg = f"账户购买力不足: {e}"
            return {"execution_result": {"error": error_msg}}

    def reject_order(state: dict) -> dict:
        logger.warning("Order rejected: %s", state.get("execution_result", {}).get("error"))
        return state

    graph = StateGraph(ExecutionState)

    graph.add_node("validate", validate_order)
    graph.add_node("risk_check", risk_check)
    graph.add_node("execute", execute_order)
    graph.add_node("reject", reject_order)

    graph.set_entry_point("validate")
    graph.add_edge("validate", "risk_check")
    graph.add_conditional_edges("risk_check", should_execute, {"execute": "execute", "reject": "reject"})
    graph.add_edge("execute", END)
    graph.add_edge("reject", END)

    return graph.compile()
