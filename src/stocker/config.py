"""Configuration management: loads from .env and provides typed access."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_config(env_path: str | None = None) -> dict:
    """Load configuration from .env file and environment variables."""
    if env_path:
        load_dotenv(env_path)
    else:
        # Search upward for .env
        for p in [Path(".env"), Path(__file__).parent.parent.parent / ".env"]:
            if p.exists():
                load_dotenv(p)
                break

    return {
        # LLM
        "openai_api_base": os.getenv("OPENAI_API_BASE", "http://192.168.192.70:3030/v1"),
        "openai_api_key": os.getenv("OPENAI_API_KEY", "sk-placeholder"),
        "deep_think_model": os.getenv("STOCKER_DEEP_THINK_MODEL", "gpt-5.3-codex"),
        "quick_think_model": os.getenv("STOCKER_QUICK_THINK_MODEL", "gpt-5.3-codex"),

        # Scheduler
        "scan_cron": os.getenv("STOCKER_SCAN_CRON", "0 9 * * 1-5"),
        "report_cron": os.getenv("STOCKER_REPORT_CRON", "0 16 * * 1-5"),
        "reflect_cron": os.getenv("STOCKER_REFLECT_CRON", "30 16 * * 1-5"),
        "sync_interval_minutes": int(os.getenv("STOCKER_SYNC_INTERVAL_MINUTES", "5")),

        # Service
        "api_host": os.getenv("STOCKER_API_HOST", "0.0.0.0"),
        "api_port": int(os.getenv("STOCKER_API_PORT", "8000")),
        "data_dir": os.getenv("STOCKER_DATA_DIR", "data"),

        # Trading
        "execution_mode": os.getenv("STOCKER_EXECUTION_MODE", "observe"),  # "active" or "observe"
        "confidence_threshold": float(os.getenv("STOCKER_CONFIDENCE_THRESHOLD", "0.7")),
        "auto_trading_enabled": os.getenv("STOCKER_AUTO_TRADING_ENABLED", "false"),
        "auto_pilot_interval_minutes": int(os.getenv("STOCKER_AUTO_PILOT_INTERVAL", "60")),

        # Broker (default: futu paper trading via OpenD)
        "broker_type": os.getenv("STOCKER_BROKER_TYPE", "futu"),

        # Futu Open API
        "futu_host": os.getenv("STOCKER_FUTU_HOST", "127.0.0.1"),
        "futu_port": int(os.getenv("STOCKER_FUTU_PORT", "11111")),
        "futu_trd_env": os.getenv("STOCKER_FUTU_TRD_ENV", "simulate"),  # "simulate" or "real"
        "futu_market": os.getenv("STOCKER_FUTU_MARKET", "HK"),  # HK / US / CN / ...
        "futu_trade_pwd": os.getenv("STOCKER_FUTU_TRADE_PWD", ""),
        "futu_quote_enabled": os.getenv("STOCKER_FUTU_QUOTE_ENABLED", "true"),
        "futu_subscribe_codes": os.getenv("STOCKER_FUTU_SUBSCRIBE_CODES", ""),  # comma-separated

        # Debate
        "max_debate_rounds": int(os.getenv("STOCKER_MAX_DEBATE_ROUNDS", "1")),
        "max_risk_discuss_rounds": int(os.getenv("STOCKER_MAX_RISK_DISCUSS_ROUNDS", "1")),

        # Backtest
        "backtest_symbols": os.getenv("STOCKER_BACKTEST_SYMBOLS", ""),  # comma-separated
        "backtest_start_date": os.getenv("STOCKER_BACKTEST_START_DATE", "2024-01-01"),
        "backtest_end_date": os.getenv("STOCKER_BACKTEST_END_DATE", "2024-12-31"),
        "backtest_initial_cash": float(os.getenv("STOCKER_BACKTEST_INITIAL_CASH", "100000")),
        "backtest_commission_rate": float(os.getenv("STOCKER_BACKTEST_COMMISSION_RATE", "0.001")),
        "backtest_slippage_pct": float(os.getenv("STOCKER_BACKTEST_SLIPPAGE_PCT", "0.001")),
        "backtest_data_source": os.getenv("STOCKER_BACKTEST_DATA_SOURCE", "yfinance"),
        "backtest_data_path": os.getenv("STOCKER_BACKTEST_DATA_PATH", ""),
        "backtest_run_mode": os.getenv("STOCKER_BACKTEST_RUN_MODE", "rule"),
        "backtest_bar_frequency": os.getenv("STOCKER_BACKTEST_BAR_FREQUENCY", "daily"),
        "backtest_benchmark": os.getenv("STOCKER_BACKTEST_BENCHMARK", ""),
    }


def create_llm(config: dict, model_type: str = "deep"):
    """Create a LangChain ChatOpenAI instance from config."""
    from langchain_openai import ChatOpenAI

    model = config["deep_think_model"] if model_type == "deep" else config["quick_think_model"]
    return ChatOpenAI(
        model=model,
        openai_api_base=config["openai_api_base"],
        openai_api_key=config["openai_api_key"],
        temperature=0.1,
    )
