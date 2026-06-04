"""FastAPI application: REST control panel for Stocker."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from stocker.api.routes import create_router

logger = logging.getLogger(__name__)

# Paths
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
_STATIC_DIR = _WEB_DIR / "static"
_TEMPLATE_DIR = _WEB_DIR / "templates"
_LOG_DIR = Path("data/logs")


# ---------------------------------------------------------------------------
# Logging setup (console + file)
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    """Configure root logger to write to both console and daily log file."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_file = _LOG_DIR / f"stocker_{datetime.now().strftime('%Y%m%d')}.log"

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler (append)
    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    root = logging.getLogger()
    # Avoid duplicate handlers on reload
    if not any(isinstance(h, logging.FileHandler) and "stocker_" in str(getattr(h, 'baseFilename', '')) for h in root.handlers):
        root.addHandler(fh)
    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stdout for h in root.handlers):
        root.addHandler(ch)
    root.setLevel(logging.DEBUG)

    logger.info("Logging initialized → %s", log_file)


# ---------------------------------------------------------------------------
# Build subgraphs + Supervisor
# ---------------------------------------------------------------------------

def _build_supervisor_graph(service: Any = None) -> tuple:
    """Build the full Supervisor MainGraph with Intelligence + Risk + Execution subgraphs.

    Returns:
        (graph, runtime, broker, watchlist_store, swing_store, position_store)
    """
    runtime = None
    broker = None

    try:
        from stocker.config import create_llm, load_config
        from stocker.agents.supervisor import create_supervisor_tools
        from stocker.graphs.main_graph import build_main_graph
        from stocker.memory.bm25_memory import BM25Memory

        config = load_config()
        llm = create_llm(config, "deep")

        from stocker.portfolio.store import create_position_store
        store = create_position_store(config.get("broker_type", "futu"))

        # --- Build Watchlist & Swing stores ---
        watchlist_store = None
        swing_store = None
        try:
            from stocker.watchlist.store import create_watchlist_store
            from stocker.swing.store import create_swing_store
            watchlist_store = create_watchlist_store(config.get("broker_type", "futu"))
            swing_store = create_swing_store(config.get("broker_type", "futu"))
        except Exception as e:
            logger.warning("Failed to create watchlist/swing stores: %s", e)

        # --- Build Futu Runtime (only when broker_type is futu) ---
        broker_type = config.get("broker_type", "futu").lower()
        if broker_type == "futu":
            try:
                from stocker.integrations.futu.config import FutuConfig
                from stocker.engine.runtime import FutuRuntime

                futu_config = FutuConfig.from_stocker_config(config)
                runtime = FutuRuntime(futu_config)
                runtime.start()
                logger.info("FutuRuntime started (trd_env=%s)", futu_config.trd_env)
            except Exception as e:
                logger.warning("Failed to start FutuRuntime: %s — continuing without it", e)
                runtime = None

        # --- Create Broker ---
        try:
            from stocker.broker.factory import create_broker

            broker = create_broker(config, runtime=runtime)
        except Exception as e:
            logger.warning("Failed to create broker: %s", e)

        # --- Build Execution subgraph ---
        execution_graph = None
        if broker is not None:
            try:
                from stocker.graphs.execution_graph import build_execution_graph

                execution_graph = build_execution_graph(broker)
                logger.info("Execution subgraph built (broker=%s)", broker.broker_name)
            except Exception as e:
                logger.warning("Failed to build Execution subgraph: %s", e)

        # --- Build Intelligence subgraph ---
        intelligence_graph = None
        try:
            from stocker.graphs.intelligence_graph import build_intelligence_graph

            intelligence_graph = build_intelligence_graph(llm)
            logger.info("Intelligence subgraph built successfully with DataFetcher fixed-source route")
        except Exception as e:
            logger.warning("Failed to build Intelligence subgraph: %s", e)

        # --- Build Risk subgraph ---
        risk_graph = None
        try:
            from stocker.graphs.risk_graph import build_risk_graph

            max_debate = config.get("max_debate_rounds", 1)
            max_risk = config.get("max_risk_discuss_rounds", 1)
            risk_graph = build_risk_graph(
                llm,
                bull_memory=BM25Memory("bull"),
                bear_memory=BM25Memory("bear"),
                trader_memory=BM25Memory("trader"),
                manager_memory=BM25Memory("manager"),
                pm_memory=BM25Memory("portfolio_manager"),
                max_debate_rounds=max_debate,
                max_risk_rounds=max_risk,
            )
            logger.info("Risk subgraph built successfully")
        except Exception as e:
            logger.warning("Failed to build Risk subgraph: %s", e)

        # --- Supervisor tools (wired to real subgraphs + execution) ---
        tools = create_supervisor_tools(
            intelligence_graph=intelligence_graph,
            risk_graph=risk_graph,
            execution_graph=execution_graph,
            portfolio_store=store,
            watchlist_store=watchlist_store,
            service=service,
        )
        graph = build_main_graph(llm, tools)

        wired = []
        if intelligence_graph:
            wired.append("Intelligence")
        if risk_graph:
            wired.append("Risk")
        if execution_graph:
            wired.append("Execution")
        logger.info("Supervisor MainGraph initialized — wired teams: %s",
                     ", ".join(wired) if wired else "none (LLM-only)")
        return graph, runtime, broker, watchlist_store, swing_store, store

    except Exception as e:
        logger.error("Failed to initialize Supervisor MainGraph: %s", e, exc_info=True)
        return None, runtime, broker, None, None, None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(service: Any = None) -> FastAPI:
    """Create the FastAPI application instance."""
    _setup_logging()

    # Initialize shared runtime state from .env / service config
    from stocker.engine.runtime_state import set_execution_mode as _init_mode
    if service is not None and hasattr(service, "config"):
        _init_mode(service.config.get("execution_mode", "observe"))
    else:
        from stocker.config import load_config
        _cfg = load_config()
        _init_mode(_cfg.get("execution_mode", "observe"))

    app = FastAPI(
        title="Stocker API",
        description="Multi-Agent automated range/swing trading system",
        version="0.1.0",
    )

    # Build Supervisor graph (LLM + subgraphs + execution)
    graph, runtime, broker, watchlist_store, swing_store, position_store = _build_supervisor_graph(service=service)

    # Store runtime/broker on app.state for routes to access
    app.state.futu_runtime = runtime
    app.state.broker = broker

    # Persistent stores
    from stocker.alerts.store import create_alert_store
    from stocker.broker.trade_store import create_trade_store
    from stocker.config import load_config as _load_trade_cfg
    from stocker.trade_plan.store import create_trade_plan_store
    _trade_cfg = _load_trade_cfg()
    broker_type_for_stores = _trade_cfg.get("broker_type", "futu")
    trade_store = create_trade_store(broker_type_for_stores)
    alert_store = create_alert_store(broker_type_for_stores)
    trade_plan_store = create_trade_plan_store(broker_type_for_stores)

    # API routes
    router = create_router(
        service=service, graph=graph, runtime=runtime, broker=broker,
        watchlist_store=watchlist_store, swing_store=swing_store, trade_store=trade_store,
        position_store=position_store, alert_store=alert_store, trade_plan_store=trade_plan_store,
    )
    app.include_router(router, prefix="/api/v1")

    # Static files
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Initial broker sync on startup
    @app.on_event("startup")
    async def startup_broker_sync():
        if broker is not None:
            try:
                positions = await broker.sync_positions()
                if positions:
                    from stocker.portfolio.store import create_position_store
                    from stocker.config import load_config as _load_cfg
                    _cfg_sync = _load_cfg()
                    store = create_position_store(_cfg_sync.get("broker_type", "futu"))
                    result = store.sync_from_broker(positions)
                    logger.info("Startup broker sync: %s (%d positions)", result, len(positions))
                else:
                    logger.info("Startup broker sync: no positions returned from broker")
            except Exception as e:
                logger.warning("Startup broker sync failed: %s", e)

    # --- Monitoring + Auto-Pilot background tasks ---
    _monitoring_task = None
    _auto_pilot_task = None


    async def _auto_pilot_loop():
        """Background loop: when auto_pilot is ON, periodically invoke Supervisor
        with an autonomous research prompt to discover stocks, scan signals, and trade."""
        import asyncio
        from stocker.engine.runtime_state import get_auto_pilot, get_auto_pilot_interval

        logger.info("[AutoPilot] Background loop started")
        _was_on = False  # track state changes to run immediately on enable

        while True:
            try:
                is_on = get_auto_pilot()

                if not is_on:
                    _was_on = False
                    await asyncio.sleep(10)  # check every 10s when OFF
                    continue

                # Just turned ON → run immediately; otherwise wait interval
                if _was_on:
                    interval = get_auto_pilot_interval()
                    logger.info("[AutoPilot] Next cycle in %d minutes", interval)
                    await asyncio.sleep(interval * 60)
                    # Re-check in case it was turned off during wait
                    if not get_auto_pilot():
                        _was_on = False
                        continue
                else:
                    logger.info("[AutoPilot] Just enabled — running first cycle immediately")

                _was_on = True

                if not graph:
                    logger.warning("[AutoPilot] Supervisor graph not available, skipping cycle")
                    continue

                logger.info("[AutoPilot] Starting autonomous research cycle...")

                # Invoke Supervisor with autonomous research prompt
                from langchain_core.messages import HumanMessage
                prompt = (
                    "scheduled: 自主投研周期任务。请按以下步骤执行完整投研流程：\n"
                    "1. 调用 discover_market_opportunities 获取当前热门板块、热搜股票、资金流向等真实市场数据\n"
                    "2. 从市场数据中筛选出最有潜力的 2 个候选标的（资金流入大、板块领涨、热度高的优先）\n"
                    "3. **重要：逐个串行分析**，不要同时分析多只股票（LLM 并发有限制）：\n"
                    "   - 先对第 1 个候选调用 run_intelligence，等结果返回后再调用 run_risk_assessment\n"
                    "   - 然后对第 2 个候选重复同样流程\n"
                    "4. 将风险评估为 BUY/OVERWEIGHT 的标的加入观察列表（manage_watchlist add），注意 ticker 要用标准格式如 600519.SS 或 0700.HK\n"
                    "5. 对整个股票池运行 scan_watchlist_signals 扫描波段信号\n"
                    "6. 如果当前为 ACTIVE 模式：对有入场信号(strength>=60)且评级为BUY的股票执行建仓(run_execution buy)；对持仓中有出场信号的执行平仓(run_execution sell)\n"
                    "7. 简要汇报本轮操作：发现了什么机会、分析了哪些股票、做了什么交易决策"
                )
                try:
                    result = await asyncio.to_thread(
                        graph.invoke,
                        {"messages": [HumanMessage(content=prompt)]}
                    )
                    # Extract response for logging
                    from langchain_core.messages import AIMessage
                    messages = result.get("messages", [])
                    for msg in reversed(messages):
                        if isinstance(msg, AIMessage) and msg.content:
                            logger.info("[AutoPilot] Cycle complete. Response: %s",
                                        msg.content[:500])
                            break
                except Exception as e:
                    logger.error("[AutoPilot] Supervisor invocation failed: %s", e)

            except asyncio.CancelledError:
                logger.info("[AutoPilot] Background loop cancelled")
                break
            except Exception as e:
                logger.error("[AutoPilot] Unexpected error: %s", e)
                await asyncio.sleep(60)  # back off on error

    @app.on_event("startup")
    async def startup_monitoring():
        """Start the continuous monitoring loop."""
        import asyncio
        from stocker.config import load_config as _load_cfg_monitoring
        from stocker.engine.runtime_state import (
            set_monitoring_enabled,
            set_monitoring_interval_seconds,
        )
        from stocker.monitoring.loop import monitoring_loop

        _cfg_monitoring = _load_cfg_monitoring()
        monitoring_enabled = _cfg_monitoring.get("monitoring_enabled", "true").lower() == "true"
        monitoring_interval = int(_cfg_monitoring.get("monitoring_interval_seconds", 300))
        set_monitoring_enabled(monitoring_enabled)
        set_monitoring_interval_seconds(monitoring_interval)

        nonlocal _monitoring_task
        _monitoring_task = asyncio.create_task(
            monitoring_loop(
                broker=broker,
                position_store=position_store,
                watchlist_store=watchlist_store,
                alert_store=alert_store,
            )
        )
        app.state.monitoring_task = _monitoring_task
        logger.info(
            "[Monitoring] Initialized (enabled=%s, interval=%ss)",
            monitoring_enabled,
            monitoring_interval,
        )

    @app.on_event("startup")
    async def startup_auto_pilot():
        """Start the auto-pilot background loop."""
        import asyncio
        from stocker.engine.runtime_state import set_auto_pilot, set_auto_pilot_interval
        from stocker.config import load_config as _load_cfg2
        _cfg2 = _load_cfg2()
        # Initialize from .env
        auto_enabled = _cfg2.get("auto_trading_enabled", "false").lower() == "true"
        set_auto_pilot(auto_enabled)
        set_auto_pilot_interval(int(_cfg2.get("auto_pilot_interval_minutes", 60)))

        nonlocal _auto_pilot_task
        _auto_pilot_task = asyncio.create_task(_auto_pilot_loop())
        app.state.auto_pilot_task = _auto_pilot_task
        logger.info("[AutoPilot] Initialized (enabled=%s)", auto_enabled)

    # Store task references on app for route access
    app.state.monitoring_task = None
    app.state.auto_pilot_task = None


    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "stocker"}

    # Shutdown: clean up background tasks and runtime
    @app.on_event("shutdown")
    async def shutdown():
        import asyncio

        for task_name, task in (
            ("Monitoring", _monitoring_task),
            ("AutoPilot", _auto_pilot_task),
        ):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info("[%s] Background task stopped on app shutdown", task_name)
                except Exception as e:
                    logger.warning("[%s] Error stopping background task: %s", task_name, e)

        if runtime is not None:
            try:
                runtime.stop()
                logger.info("FutuRuntime stopped on app shutdown")
            except Exception as e:
                logger.warning("Error stopping FutuRuntime: %s", e)


    # Frontend SPA
    @app.get("/", response_class=HTMLResponse)
    async def index():
        index_path = _TEMPLATE_DIR / "index.html"
        return index_path.read_text(encoding="utf-8")

    @app.get("/{path:path}", response_class=HTMLResponse)
    async def catch_all(path: str):
        if path.startswith(("api/", "static/", "health")):
            return None
        index_path = _TEMPLATE_DIR / "index.html"
        if index_path.exists():
            return index_path.read_text(encoding="utf-8")
        return HTMLResponse("<h1>Stocker</h1><p>Frontend not found.</p>", status_code=404)

    return app
