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

def _build_supervisor_graph(service: Any = None) -> tuple[Any | None, Any | None, Any | None]:
    """Build the full Supervisor MainGraph with Intelligence + Risk + Execution subgraphs.

    Returns:
        (graph, runtime, broker) — runtime/broker may be None if not futu.
    """
    runtime = None
    broker = None

    try:
        from stocker.config import create_llm, load_config
        from stocker.agents.supervisor import create_supervisor_tools
        from stocker.graphs.main_graph import build_main_graph
        from stocker.portfolio.store import PositionStore
        from stocker.memory.bm25_memory import BM25Memory

        config = load_config()
        llm = create_llm(config, "deep")
        store = PositionStore()

        # --- Build Futu Runtime (default broker) ---
        if config.get("broker_type", "futu") != "simulated":
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
            from stocker.dataflows.router import create_default_router
            from stocker.dataflows.tools import create_dataflow_tools
            from stocker.graphs.intelligence_graph import build_intelligence_graph

            data_router = create_default_router()
            dataflow_tools = create_dataflow_tools(data_router)
            # News tools are the subset with get_news / get_global_news
            news_tools = [t for t in dataflow_tools if "news" in t.name]
            intelligence_graph = build_intelligence_graph(llm, dataflow_tools, news_tools)
            logger.info("Intelligence subgraph built successfully")
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
        return graph, runtime, broker

    except Exception as e:
        logger.error("Failed to initialize Supervisor MainGraph: %s", e, exc_info=True)
        return None, runtime, broker


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
    graph, runtime, broker = _build_supervisor_graph(service=service)

    # Store runtime/broker on app.state for routes to access
    app.state.futu_runtime = runtime
    app.state.broker = broker

    # API routes
    router = create_router(service=service, graph=graph, runtime=runtime, broker=broker)
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
                    from stocker.portfolio.store import PositionStore
                    store = PositionStore()
                    result = store.sync_from_broker(positions)
                    logger.info("Startup broker sync: %s (%d positions)", result, len(positions))
                else:
                    logger.info("Startup broker sync: no positions returned from broker")
            except Exception as e:
                logger.warning("Startup broker sync failed: %s", e)

    # Health check
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "stocker"}

    # Shutdown: clean up runtime
    @app.on_event("shutdown")
    async def shutdown():
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
