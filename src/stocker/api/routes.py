"""FastAPI routes: /chat/stream flows through Supervisor MainGraph with real-time SSE dispatch logs."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# In-memory trade history (persists for session lifetime)
_trade_history: list[dict] = []


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    ticker: str


class TradeRequest(BaseModel):
    ticker: str
    action: str
    quantity: int
    price: float | None = None


class PortfolioRequest(BaseModel):
    action: str
    ticker: str = ""
    quantity: int = 0
    avg_cost: float = 0.0


class ChatRequest(BaseModel):
    message: str


class BacktestRequest(BaseModel):
    symbols: list[str]
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_cash: float = 100_000.0
    commission_rate: float = 0.001
    slippage_pct: float = 0.001
    data_source: str = "yfinance"
    data_path: str = ""
    run_mode: str = "rule"
    bar_frequency: str = "daily"
    benchmark: str = ""


# ---------------------------------------------------------------------------
# Conversation memory (in-memory, single-session)
# ---------------------------------------------------------------------------

_conversation_history: list = []


def _extract_ai_response(result: dict) -> str:
    """Extract the final AI text response from graph invoke result."""
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            return msg.content
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    return "Supervisor 未返回有效响应。"


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_router(
    service: Any = None,
    graph: Any = None,
    runtime: Any = None,
    broker: Any = None,
    watchlist_store: Any = None,
    swing_store: Any = None,
    trade_store: Any = None,
    position_store: Any = None,
) -> APIRouter:
    router = APIRouter()

    def _get_execution_mode() -> str:
        """Get current execution mode from service or shared runtime state."""
        if service is not None and hasattr(service, "config"):
            return service.config.get("execution_mode", "observe")
        from stocker.engine.runtime_state import get_execution_mode
        return get_execution_mode()

    def _set_execution_mode(mode: str) -> None:
        """Set execution mode on service and shared runtime state."""
        from stocker.engine.runtime_state import set_execution_mode
        set_execution_mode(mode)
        if service is not None and hasattr(service, "config"):
            service.config["execution_mode"] = mode

    # ----- Status -----

    @router.get("/status")
    async def get_status():
        positions = position_store.list_all() if position_store else []

        status = {
            "status": "running",
            "service": "stocker",
            "supervisor": "ready" if graph else "no_llm",
            "teams": {
                "intelligence": "idle",
                "risk_assessment": "idle",
                "execution": "ready" if broker else "idle",
            },
            "scheduler": "running",
            "broker": broker.broker_name if broker and hasattr(broker, "broker_name") else "futu",
            "positions_count": len(positions),
            "execution_mode": _get_execution_mode(),
        }

        if runtime is not None and hasattr(runtime, "get_runtime_status"):
            status["futu_runtime"] = runtime.get_runtime_status()

        return status

    # ----- Analyze -----

    @router.post("/analyze")
    async def analyze(req: AnalyzeRequest):
        if graph:
            try:
                result = await asyncio.to_thread(
                    graph.invoke,
                    {"messages": [HumanMessage(content=f"分析 {req.ticker.upper()}")]}
                )
                return {"ticker": req.ticker, "response": _extract_ai_response(result)}
            except Exception as e:
                logger.error("Analyze failed: %s", e)
                return {"ticker": req.ticker, "response": f"分析失败: {e}"}
        return {"ticker": req.ticker, "response": "Supervisor LLM 未就绪。"}

    # ----- Trade (connected to real broker) -----

    @router.post("/trade")
    async def trade(req: TradeRequest):
        from stocker.broker.models import Order, OrderSide

        exec_mode = _get_execution_mode()

        if exec_mode != "active":
            return {
                "ticker": req.ticker, "action": req.action, "quantity": req.quantity,
                "status": "rejected",
                "response": f"当前为 {exec_mode} 模式，不允许执行交易。请切换到 active 模式。",
            }

        active_broker = broker
        if active_broker is None:
            return {
                "ticker": req.ticker, "action": req.action, "quantity": req.quantity,
                "status": "rejected",
                "response": "Broker 未就绪，无法执行交易。",
            }

        try:
            # Price validation: reject trades with no price
            if not req.price or req.price <= 0:
                return {
                    "ticker": req.ticker, "action": req.action, "quantity": req.quantity,
                    "status": "rejected",
                    "response": f"交易被拒绝：缺少有效价格。请确保股票代码正确（如 AAPL 而非 APPL），且能获取到实时报价。",
                }

            order = Order(
                ticker=req.ticker.upper(),
                side=OrderSide(req.action.lower()),
                quantity=req.quantity,
                price=req.price,
            )
            result = await active_broker.place_order(order)

            # Record trade history
            _trade_history.append({
                "trade_id": result.order_id,
                "ticker": result.ticker,
                "side": result.side.value,
                "quantity": result.quantity,
                "price": result.filled_price,
                "status": result.status.value,
                "timestamp": result.timestamp.isoformat(),
                "broker": result.broker,
                "error": result.error,
            })

            # --- Auto swing trade lifecycle ---
            swing_trade = None
            if result.status.value == "filled" and swing_store:
                ticker_upper = result.ticker.upper()
                if result.side.value == "buy":
                    # Buy → open a new swing trade
                    swing_trade = swing_store.open_trade(
                        ticker=ticker_upper,
                        entry_price=result.filled_price,
                        quantity=result.quantity,
                        signal_source=f"broker:{result.broker}",
                        notes=f"Auto-created from order {result.order_id}",
                    )
                    logger.info("Auto-opened swing trade %s for %s", swing_trade.trade_id, ticker_upper)
                elif result.side.value == "sell":
                    # Sell → close the oldest open swing trade for this ticker
                    open_trades = swing_store.list_all(status="open", ticker=ticker_upper)
                    if open_trades:
                        closed = swing_store.close_trade(
                            trade_id=open_trades[0].trade_id,
                            exit_price=result.filled_price,
                            notes=f"Auto-closed from order {result.order_id}",
                        )
                        if closed:
                            swing_trade = closed
                            logger.info("Auto-closed swing trade %s for %s, P&L=%.2f",
                                        closed.trade_id, ticker_upper, closed.pnl)

            # --- Auto update position store ---
            if result.status.value == "filled" and position_store:
                ticker_upper = result.ticker.upper()
                if result.side.value == "buy":
                    position_store.add(ticker_upper, result.quantity, result.filled_price)
                elif result.side.value == "sell":
                    pos = position_store.get(ticker_upper)
                    if pos and pos.quantity <= result.quantity:
                        position_store.remove(ticker_upper)
                    elif pos:
                        pos.quantity -= result.quantity
                        position_store._save()

            resp = {
                "ticker": req.ticker, "action": req.action, "quantity": req.quantity,
                "status": result.status.value,
                "order_id": result.order_id,
                "filled_price": result.filled_price,
                "response": f"交易{'成功' if result.status.value == 'filled' else '失败'}: "
                            f"{req.action.upper()} {req.ticker} x{req.quantity}"
                            + (f" @ ${result.filled_price:.2f}" if result.filled_price else "")
                            + (f" (错误: {result.error})" if result.error else ""),
            }
            if swing_trade:
                resp["swing_trade_id"] = swing_trade.trade_id
            return resp

        except Exception as e:
            logger.error("Trade execution failed: %s", e)
            return {
                "ticker": req.ticker, "action": req.action, "quantity": req.quantity,
                "status": "error",
                "response": f"交易执行异常: {e}",
            }

    # ----- Trade History -----

    @router.get("/trades")
    async def get_trade_history():
        """Get trade history (most recent first)."""
        return {"trades": list(reversed(_trade_history[-100:]))}

    # ----- Broker Account Info -----

    @router.get("/account")
    async def get_account_info():
        """Get broker account information."""
        if broker is None:
            return {
                "account": {
                    "account_id": "N/A", "total_value": 0, "cash": 0,
                    "buying_power": 0, "broker": "none",
                },
                "connected": False,
            }
        try:
            info = await broker.get_account_info()
            return {"account": info.model_dump(mode="json"), "connected": True}
        except Exception as e:
            logger.error("Account info failed: %s", e)
            return {"account": {}, "connected": False, "error": str(e)}

    # ----- Logs -----

    @router.get("/logs")
    async def get_logs(lines: int = 100):
        """Get recent log entries from today's log file."""
        import os
        log_dir = Path("data/logs")
        today = datetime.now().strftime("%Y%m%d")
        log_file = log_dir / f"stocker_{today}.log"

        if not log_file.exists():
            return {"logs": [], "file": str(log_file), "message": "今日日志文件不存在"}

        try:
            with open(log_file, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
            recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
            entries = []
            for line in recent:
                line = line.strip()
                if not line:
                    continue
                entries.append(line)
            return {"logs": entries, "file": str(log_file), "total": len(all_lines)}
        except Exception as e:
            return {"logs": [], "error": str(e)}

    # ----- Reports (analysis cache) -----

    @router.get("/reports")
    async def get_reports():
        """Get cached analysis reports."""
        report_dir = Path("data")
        reports = []

        # Read from analysis_cache.json if it exists
        cache_file = report_dir / "analysis_cache.json"
        if cache_file.exists():
            try:
                import json as json_mod
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json_mod.load(f)
                if isinstance(cached, list):
                    reports.extend(cached)
                elif isinstance(cached, dict):
                    for ticker, data in cached.items():
                        if isinstance(data, dict):
                            data["ticker"] = ticker
                            reports.append(data)
            except Exception as e:
                logger.warning("Failed to read analysis cache: %s", e)

        # Also check for individual report files
        for f in sorted(report_dir.glob("report_*.json"), reverse=True):
            try:
                import json as json_mod
                with open(f, "r", encoding="utf-8") as fh:
                    r = json_mod.load(fh)
                    if isinstance(r, dict):
                        reports.append(r)
            except Exception:
                pass

        return {"reports": reports[:50]}

    # ----- Broker Config (read/switch) -----

    @router.get("/broker/config")
    async def get_broker_config():
        """Get current broker configuration."""
        from stocker.config import load_config
        config = load_config()
        return {
            "broker_type": config.get("broker_type", "futu"),
            "execution_mode": _get_execution_mode(),
            "futu_host": config.get("futu_host", "127.0.0.1"),
            "futu_port": config.get("futu_port", 11111),
            "futu_trd_env": config.get("futu_trd_env", "simulate"),
            "futu_market": config.get("futu_market", "HK"),
            "futu_quote_enabled": config.get("futu_quote_enabled", "true"),
            "connected": broker is not None and hasattr(broker, "broker_name"),
            "broker_name": broker.broker_name if broker and hasattr(broker, "broker_name") else "none",
        }

    @router.post("/execution-mode")
    async def set_execution_mode(body: dict):
        """Switch execution mode (observe/active). Runtime-only, no .env write."""
        mode = body.get("mode", "observe")
        if mode not in ("observe", "active"):
            return {"error": "Invalid mode. Must be 'observe' or 'active'."}

        _set_execution_mode(mode)

        # Inject a system notification into conversation history so Supervisor
        # is aware of the mode change even when relying on prior context.
        from langchain_core.messages import SystemMessage
        _conversation_history.append(
            SystemMessage(content=f"[系统通知] 执行模式已切换为 {mode.upper()}。")
        )

        return {"execution_mode": mode, "message": f"已切换到 {mode} 模式"}

    # ----- Auto-Pilot -----

    @router.get("/auto-pilot")
    async def get_auto_pilot_status():
        """Get auto-pilot status."""
        from stocker.engine.runtime_state import get_auto_pilot, get_auto_pilot_interval
        return {
            "enabled": get_auto_pilot(),
            "interval_minutes": get_auto_pilot_interval(),
        }

    @router.post("/auto-pilot")
    async def set_auto_pilot(body: dict):
        """Toggle auto-pilot on/off. Optional: set interval_minutes."""
        from stocker.engine.runtime_state import (
            get_auto_pilot, set_auto_pilot as _set_ap,
            set_auto_pilot_interval,
        )
        if "enabled" in body:
            enabled = bool(body["enabled"])
            _set_ap(enabled)
            logger.info("[AutoPilot] %s via API", "ENABLED" if enabled else "DISABLED")

        if "interval_minutes" in body:
            minutes = int(body["interval_minutes"])
            set_auto_pilot_interval(minutes)

        return {
            "enabled": get_auto_pilot(),
            "message": f"AutoPilot {'已开启' if get_auto_pilot() else '已关闭'}",
        }

    # ----- Portfolio -----

    @router.post("/portfolio")
    async def manage_portfolio(req: PortfolioRequest):
        if not position_store:
            return {"error": "Position store not initialized"}
        if req.action == "list":
            return {"positions": [p.model_dump(mode="json") for p in position_store.list_all()]}
        elif req.action == "add":
            pos = position_store.add(req.ticker, req.quantity, req.avg_cost)
            return {"added": pos.model_dump(mode="json")}
        elif req.action == "remove":
            ok = position_store.remove(req.ticker)
            return {"removed": req.ticker, "success": ok}
        return {"action": req.action, "message": "Wire to Supervisor."}

    # ----- Chat (non-streaming fallback) -----

    @router.post("/chat")
    async def chat(req: ChatRequest):
        global _conversation_history
        user_msg = req.message.strip()
        if not user_msg:
            return {"message": "", "response": "请输入消息。"}

        if graph:
            try:
                _conversation_history.append(HumanMessage(content=user_msg))
                result = await asyncio.to_thread(
                    graph.invoke,
                    {"messages": list(_conversation_history)}
                )
                _conversation_history = result.get("messages", _conversation_history)
                return {"message": user_msg, "response": _extract_ai_response(result)}
            except Exception as e:
                logger.error("Chat failed: %s", e)
                if _conversation_history and isinstance(_conversation_history[-1], HumanMessage):
                    _conversation_history.pop()
                return {"message": user_msg, "response": f"Supervisor 调用失败: {e}"}

        return {"message": user_msg, "response": "Supervisor LLM 未就绪。"}

    # ----- Chat Stream (SSE with real-time dispatch logs) -----

    @router.post("/chat/stream")
    async def chat_stream(req: ChatRequest):
        """Stream Supervisor execution via SSE.

        Events emitted:
          - event: log     {source, action, message, detail}  — dispatch step
          - event: done    {response}                          — final AI response
          - event: error   {message}                           — error
        """
        global _conversation_history
        user_msg = req.message.strip()
        if not user_msg:
            return StreamingResponse(_sse_single("error", {"message": "空消息"}),
                                     media_type="text/event-stream")

        if not graph:
            return StreamingResponse(_sse_single("error", {"message": "Supervisor LLM 未就绪。"}),
                                     media_type="text/event-stream")

        event_queue: asyncio.Queue = asyncio.Queue()

        def on_event(source: str, action: str, message: str, detail: dict | None = None):
            """Callback invoked by MainGraph nodes to push dispatch events."""
            # Log to file (persisted)
            logger.info("[dispatch] %s.%s: %s %s", source, action, message,
                        json.dumps(detail, ensure_ascii=False) if detail else "")
            # Push to SSE queue
            event_queue.put_nowait({
                "source": source,
                "action": action,
                "message": message,
                "detail": detail or {},
                "time": datetime.now().strftime("%H:%M:%S"),
            })

        async def generate():
            global _conversation_history

            _conversation_history.append(HumanMessage(content=user_msg))

            # Send initial event
            yield _sse_event("log", {
                "source": "system", "action": "start",
                "message": "开始处理请求...",
                "time": datetime.now().strftime("%H:%M:%S"),
            })

            # Run graph in background thread
            loop = asyncio.get_event_loop()

            async def run_graph():
                return await asyncio.to_thread(
                    graph.invoke,
                    {
                        "messages": list(_conversation_history),
                        "_on_event": on_event,
                    }
                )

            graph_task = asyncio.create_task(run_graph())

            # Stream events as they arrive
            while not graph_task.done():
                try:
                    evt = await asyncio.wait_for(event_queue.get(), timeout=0.3)
                    yield _sse_event("log", evt)
                except asyncio.TimeoutError:
                    pass

            # Drain remaining events
            while not event_queue.empty():
                evt = event_queue.get_nowait()
                yield _sse_event("log", evt)

            # Get result
            try:
                result = graph_task.result()
                _conversation_history = result.get("messages", _conversation_history)
                response_text = _extract_ai_response(result)
                yield _sse_event("done", {"response": response_text})
            except Exception as e:
                logger.error("Graph stream failed: %s", e)
                if _conversation_history and isinstance(_conversation_history[-1], HumanMessage):
                    _conversation_history.pop()
                yield _sse_event("error", {"message": str(e)})

        return StreamingResponse(generate(), media_type="text/event-stream",
                                  headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ----- Reset -----

    @router.post("/chat/reset")
    async def reset_chat():
        global _conversation_history
        _conversation_history = []
        return {"message": "对话已重置"}

    # ----- Skills -----

    @router.get("/skills")
    async def list_skills():
        from stocker.skills.registry import SkillRegistry
        registry = SkillRegistry.get_instance()
        registry.discover_and_register()
        return {"skills": [m.model_dump() for m in registry.list_manifests()]}

    # ----- Strategy Management -----

    @router.get("/strategy")
    async def get_strategy():
        """Get the current active strategy configuration."""
        from stocker.strategy.manager import StrategyManager
        mgr = StrategyManager()
        config = mgr.get()
        warnings = mgr.get_warnings()
        return {
            "strategy": config.model_dump(mode="json"),
            "warnings": warnings,
        }

    @router.put("/strategy")
    async def update_strategy(body: dict):
        """Update the active strategy with partial config.

        Body can contain any subset of strategy fields, e.g.:
        {"technical": {"rsi_window": 21}, "risk": {"stop_loss_min_pct": 3.0}}
        """
        from pydantic import ValidationError
        from stocker.strategy.manager import StrategyManager
        mgr = StrategyManager()
        try:
            updated = mgr.update(body)
            warnings = mgr.get_warnings()
            return {
                "strategy": updated.model_dump(mode="json"),
                "warnings": warnings,
                "message": "策略已更新",
            }
        except (ValueError, ValidationError) as e:
            return {"error": str(e), "message": "策略验证失败"}

    @router.get("/strategy/presets")
    async def list_strategy_presets():
        """List all available strategy presets."""
        from stocker.strategy.manager import StrategyManager
        mgr = StrategyManager()
        presets = mgr.list_presets()
        return {
            "presets": {
                name: {"name": p["name"], "description": p["description"]}
                for name, p in presets.items()
            },
            "current": mgr.get().name,
        }

    @router.post("/strategy/preset/{name}")
    async def switch_strategy_preset(name: str):
        """Switch to a built-in preset strategy."""
        from stocker.strategy.manager import StrategyManager
        mgr = StrategyManager()
        try:
            config = mgr.switch_preset(name)
            return {
                "strategy": config.model_dump(mode="json"),
                "message": f"已切换到 {name} 预设",
            }
        except KeyError as e:
            return {"error": str(e), "message": "预设不存在"}

    @router.post("/strategy/reset")
    async def reset_strategy():
        """Reset strategy to default (balanced)."""
        from stocker.strategy.manager import StrategyManager
        mgr = StrategyManager()
        config = mgr.reset()
        return {
            "strategy": config.model_dump(mode="json"),
            "message": "策略已重置为默认（均衡型）",
        }

    # ------------------------------------------------------------------
    # Backtest endpoint
    # ------------------------------------------------------------------

    @router.post("/api/v1/backtest")
    async def run_backtest(req: BacktestRequest):
        """Run a historical backtest and return the report."""
        from stocker.backtest import BacktestConfig, BacktestRuntime

        config = BacktestConfig(
            symbols=req.symbols,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_cash=req.initial_cash,
            commission_rate=req.commission_rate,
            slippage_pct=req.slippage_pct,
            data_source=req.data_source,
            data_path=req.data_path,
            run_mode=req.run_mode,
            bar_frequency=req.bar_frequency,
            benchmark=req.benchmark,
        )

        # Run backtest in a thread pool to avoid blocking the event loop
        import asyncio

        loop = asyncio.get_event_loop()
        runtime = BacktestRuntime(config)
        report = await loop.run_in_executor(None, runtime.run)
        return report.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Real-time quote (via westock-data)
    # ------------------------------------------------------------------

    def _ticker_to_westock_code(ticker: str) -> str:
        """Convert a generic ticker to westock-data code format.

        Examples: AAPL → usAAPL, 0700.HK → hk00700, 600519.SS → sh600519
        """
        t = ticker.strip().upper()

        # Already in westock format
        if t.startswith(("SH", "SZ", "BJ", "HK", "US")):
            return t.lower() if t[:2] in ("SH", "SZ", "BJ") else t[:2].lower() + t[2:]

        # Yahoo Finance HK format: 0700.HK → hk00700
        if t.endswith(".HK"):
            num = t.replace(".HK", "").zfill(5)
            return f"hk{num}"

        # Yahoo Finance CN format: 600519.SS → sh600519, 000001.SZ → sz000001
        if t.endswith(".SS"):
            return f"sh{t.replace('.SS', '')}"
        if t.endswith(".SZ"):
            return f"sz{t.replace('.SZ', '')}"

        # Pure digits → guess CN market
        if t.isdigit():
            if t.startswith("6") or t.startswith("9"):
                return f"sh{t}"
            return f"sz{t}"

        # Default: treat as US stock
        return f"us{t}"

    def _get_realtime_price(ticker: str) -> dict:
        """Get real-time price via westock-data CLI.

        westock-data quote returns either JSON or pipe-separated table text.
        We handle both formats.
        """
        from stocker.skills.westock_data import _run_westock

        code = _ticker_to_westock_code(ticker)
        raw = _run_westock(["quote", code], timeout=15)

        if not raw:
            return {"ticker": ticker, "code": code, "price": 0, "error": "no data"}

        # --- Try JSON first ---
        try:
            data = json.loads(raw)
            if "data" in data and isinstance(data["data"], list) and data["data"]:
                item = data["data"][0]
            elif "data" in data and isinstance(data["data"], dict):
                item = data["data"]
            else:
                item = data

            price = float(item.get("last", 0) or item.get("price", 0) or item.get("close", 0) or 0)
            change_pct = float(item.get("changePercent", 0) or item.get("changePct", 0) or item.get("change_percent", 0) or 0)
            name = item.get("name", "") or item.get("stockName", "")

            if price > 0:
                return {
                    "ticker": ticker, "code": code, "price": price,
                    "change_pct": change_pct, "name": name,
                }
        except (json.JSONDecodeError, TypeError):
            pass  # Not JSON, try table format

        # --- Parse pipe-separated table (| col1 | col2 | ...) ---
        try:
            lines = [l.strip() for l in raw.strip().split("\n") if l.strip() and "|" in l]
            if len(lines) >= 2:
                # First line with content = headers, skip separator lines (|---|---|)
                header_line = None
                data_line = None
                for l in lines:
                    # Skip separator lines
                    if all(c in "-| " for c in l):
                        continue
                    if header_line is None:
                        header_line = l
                    else:
                        data_line = l
                        break

                if header_line and data_line:
                    headers = [h.strip().lower() for h in header_line.split("|") if h.strip()]
                    values = [v.strip() for v in data_line.split("|") if v.strip()]

                    row = dict(zip(headers, values))

                    # Try various column names for price
                    price = 0.0
                    for key in ("price", "last", "close", "prev_close"):
                        val = row.get(key, "")
                        try:
                            p = float(val)
                            if p > 0:
                                price = p
                                break
                        except (ValueError, TypeError):
                            continue

                    change_pct = 0.0
                    for key in ("change_percent", "changepercent", "change_pct"):
                        val = row.get(key, "").replace("%", "")
                        try:
                            change_pct = float(val)
                            break
                        except (ValueError, TypeError):
                            continue

                    name = row.get("name", "") or row.get("symbol", "")

                    return {
                        "ticker": ticker, "code": code, "price": price,
                        "change_pct": change_pct, "name": name,
                    }
        except Exception as e:
            logger.debug("Table parse failed for %s: %s", ticker, e)

        logger.warning("Could not parse westock quote for %s (raw=%s)", ticker, raw[:300])
        return {"ticker": ticker, "code": code, "price": 0, "error": "parse failed", "raw_preview": raw[:300]}

    @router.get("/quote/{ticker}")
    async def get_quote(ticker: str):
        """Get real-time stock quote via westock-data."""
        import asyncio
        result = await asyncio.to_thread(_get_realtime_price, ticker)
        return result

    @router.post("/quotes")
    async def get_batch_quotes(body: dict):
        """Get real-time quotes for multiple tickers at once.
        body: {"tickers": ["AAPL", "TSLA", "0700.HK"]}"""
        import asyncio
        tickers = body.get("tickers", [])
        if not tickers:
            return {"quotes": {}}

        # Batch via westock: convert all tickers to codes, join with comma
        from stocker.skills.westock_data import _run_westock
        codes = []
        ticker_code_map = {}
        for t in tickers[:30]:  # limit batch
            code = _ticker_to_westock_code(t)
            codes.append(code)
            ticker_code_map[code] = t

        def _fetch_batch():
            raw = _run_westock(["quote", ",".join(codes)], timeout=20)
            return raw

        raw = await asyncio.to_thread(_fetch_batch)
        quotes = {}

        if not raw:
            return {"quotes": quotes}

        # Try JSON (BatchResult)
        try:
            data = json.loads(raw)
            items = data.get("data", []) if isinstance(data.get("data"), list) else [data]
            for item in items:
                code = item.get("code", "") or item.get("symbol", "")
                price = float(item.get("last", 0) or item.get("price", 0) or item.get("close", 0) or 0)
                change_pct = float(item.get("changePercent", 0) or item.get("changePct", 0) or 0)
                name = item.get("name", "")
                # Find original ticker
                orig = ticker_code_map.get(code, code)
                if price > 0:
                    quotes[orig] = {"price": price, "change_pct": change_pct, "name": name}
            if quotes:
                return {"quotes": quotes}
        except (json.JSONDecodeError, TypeError):
            pass

        # Try table format: parse all data rows
        try:
            lines = [l.strip() for l in raw.strip().split("\n") if l.strip() and "|" in l]
            headers = None
            for l in lines:
                if all(c in "-| " for c in l):
                    continue
                cells = [c.strip() for c in l.split("|") if c.strip()]
                if headers is None:
                    headers = [h.lower() for h in cells]
                    continue
                row = dict(zip(headers, cells))
                code = row.get("code", "") or row.get("symbol", "")
                price = 0.0
                for key in ("price", "last", "close", "prev_close"):
                    try:
                        p = float(row.get(key, ""))
                        if p > 0:
                            price = p
                            break
                    except (ValueError, TypeError):
                        continue
                change_pct = 0.0
                for key in ("change_percent", "changepercent"):
                    try:
                        change_pct = float(row.get(key, "").replace("%", ""))
                        break
                    except (ValueError, TypeError):
                        continue
                name = row.get("name", "")
                # Match back to original ticker
                for c, t in ticker_code_map.items():
                    if c.lower() in code.lower() or code.lower() in c.lower():
                        if price > 0:
                            quotes[t] = {"price": price, "change_pct": change_pct, "name": name}
                        break
        except Exception as e:
            logger.debug("Batch quote table parse failed: %s", e)

        return {"quotes": quotes}

    # ------------------------------------------------------------------
    # Watchlist endpoints
    # ------------------------------------------------------------------

    @router.get("/watchlist")
    async def list_watchlist():
        if not watchlist_store:
            return {"items": []}
        items = watchlist_store.list_all()
        return {"items": [wi.model_dump(mode="json") for wi in items]}

    @router.post("/watchlist")
    async def add_to_watchlist(body: dict):
        if not watchlist_store:
            return {"error": "Watchlist store not initialized"}
        ticker = body.get("ticker", "").strip()
        if not ticker:
            return {"error": "ticker is required"}
        wi = watchlist_store.add(
            ticker=ticker,
            name=body.get("name", ""),
            market=body.get("market", ""),
            tags=body.get("tags"),
        )
        return {"item": wi.model_dump(mode="json")}

    @router.delete("/watchlist/{ticker}")
    async def remove_from_watchlist(ticker: str):
        if not watchlist_store:
            return {"error": "Watchlist store not initialized"}
        ok = watchlist_store.remove(ticker)
        return {"removed": ticker, "success": ok}

    @router.post("/watchlist/scan")
    async def scan_watchlist(body: dict):
        """Scan all watchlist items for swing signals."""
        if not watchlist_store:
            return {"results": []}
        min_strength = body.get("min_strength", 20)
        results = []
        try:
            from stocker.analysis.swing_signals import SwingSignalEngine
            from stocker.utils.data_helpers import fetch_ohlcv_yfinance
            engine = SwingSignalEngine()
            for wi in watchlist_store.list_all():
                try:
                    df = fetch_ohlcv_yfinance(wi.ticker)
                    if df is None or df.empty:
                        continue
                    signal = engine.analyze(wi.ticker, df)
                    if signal and signal.strength >= min_strength:
                        sig_dict = signal.model_dump(mode="json")
                        sig_dict["ticker"] = wi.ticker
                        results.append(sig_dict)
                        # Update store
                        watchlist_store.update_signal(wi.ticker, signal)
                except Exception as e:
                    logger.warning("Scan failed for %s: %s", wi.ticker, e)
        except Exception as e:
            logger.error("Watchlist scan failed: %s", e)
        return {"results": results}

    # ------------------------------------------------------------------
    # Swing Trades endpoints
    # ------------------------------------------------------------------

    @router.get("/swing-trades")
    async def list_swing_trades(status: str = ""):
        if not swing_store:
            return {"trades": []}
        trades = swing_store.list_all(status=status if status else None)
        return {"trades": [t.model_dump(mode="json") for t in trades]}

    @router.get("/swing-trades/stats")
    async def get_swing_stats():
        if not swing_store:
            return {"stats": {}}
        stats = swing_store.get_stats()
        return {"stats": stats.model_dump(mode="json")}

    @router.post("/swing-trades/open")
    async def open_swing_trade(body: dict):
        if not swing_store:
            return {"error": "Swing store not initialized"}
        ticker = body.get("ticker", "").strip().upper()
        if not ticker:
            return {"error": "ticker is required"}
        entry_price = body.get("entry_price", 0)
        if not entry_price or entry_price <= 0:
            return {"error": "valid entry_price is required"}
        trade = swing_store.open_trade(
            ticker=ticker,
            entry_price=entry_price,
            quantity=body.get("quantity", 0),
            notes=body.get("notes", ""),
        )
        return {"trade": trade.model_dump(mode="json")}

    @router.post("/swing-trades/close")
    async def close_swing_trade(body: dict):
        if not swing_store:
            return {"error": "Swing store not initialized"}
        trade_id = body.get("trade_id", "")
        exit_price = body.get("exit_price", 0)
        if not trade_id:
            return {"error": "trade_id is required"}
        if not exit_price or exit_price <= 0:
            return {"error": "valid exit_price is required"}
        trade = swing_store.close_trade(
            trade_id=trade_id,
            exit_price=exit_price,
            notes=body.get("notes", ""),
        )
        if not trade:
            return {"error": f"Trade {trade_id} not found"}
        return {"trade": trade.model_dump(mode="json")}

    return router


async def _sse_single(event: str, data: dict):
    """Yield a single SSE event then close."""
    yield _sse_event(event, data)
