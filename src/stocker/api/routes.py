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

def create_router(service: Any = None, graph: Any = None, runtime: Any = None, broker: Any = None) -> APIRouter:
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
        from stocker.portfolio.store import PositionStore
        store = PositionStore()
        positions = store.list_all()

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
            order = Order(
                ticker=req.ticker.upper(),
                side=OrderSide(req.action.lower()),
                quantity=req.quantity,
                price=req.price,
            )
            result = await active_broker.place_order(order)

            # Record trade
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

            return {
                "ticker": req.ticker, "action": req.action, "quantity": req.quantity,
                "status": result.status.value,
                "order_id": result.order_id,
                "filled_price": result.filled_price,
                "response": f"交易{'成功' if result.status.value == 'filled' else '失败'}: "
                            f"{req.action.upper()} {req.ticker} x{req.quantity}"
                            + (f" @ ${result.filled_price:.2f}" if result.filled_price else "")
                            + (f" (错误: {result.error})" if result.error else ""),
            }
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

    # ----- Portfolio -----

    @router.post("/portfolio")
    async def manage_portfolio(req: PortfolioRequest):
        from stocker.portfolio.store import PositionStore
        store = PositionStore()
        if req.action == "list":
            return {"positions": [p.model_dump(mode="json") for p in store.list_all()]}
        elif req.action == "add":
            pos = store.add(req.ticker, req.quantity, req.avg_cost)
            return {"added": pos.model_dump(mode="json")}
        elif req.action == "remove":
            ok = store.remove(req.ticker)
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

    return router


async def _sse_single(event: str, data: dict):
    """Yield a single SSE event then close."""
    yield _sse_event(event, data)
