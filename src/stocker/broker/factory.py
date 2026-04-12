"""Broker factory: creates the appropriate broker based on configuration.

Default is FutuBroker with paper trading (TrdEnv.SIMULATE).
SimulatedBroker is only used as an explicit fallback when futu-api is unavailable.

Usage:
    from stocker.broker.factory import create_broker
    broker = create_broker(config, runtime=runtime)
"""

from __future__ import annotations

import logging
from typing import Any

from stocker.broker.base import BaseBroker

logger = logging.getLogger(__name__)


def create_broker(config: dict, runtime: Any | None = None) -> BaseBroker:
    """Create a broker instance based on ``config["broker_type"]``.

    Args:
        config: Main stocker configuration dict.
        runtime: An optional ``FutuRuntime`` instance (required for futu broker).

    Returns:
        A concrete ``BaseBroker`` implementation.

    Default behaviour (broker_type == "futu"):
        Creates ``FutuBroker`` connected to OpenD paper-trading environment.
        Falls back to ``SimulatedBroker`` only if futu-api is not installed
        or no runtime is provided.

    Explicit ``broker_type == "simulated"``:
        Creates the in-memory ``SimulatedBroker`` directly.
    """
    broker_type = config.get("broker_type", "futu").lower()

    # --- Backtest ---
    if broker_type == "backtest":
        logger.info("broker_type=backtest — BacktestBroker will be created by BacktestRuntime")
        # BacktestBroker requires clock + data_store, so it is created inside
        # BacktestRuntime.run().  Return a SimulatedBroker as placeholder for
        # any pre-run code that needs a broker reference.
        from stocker.broker.simulated import SimulatedBroker

        return SimulatedBroker()

    # --- Explicit simulated ---
    if broker_type == "simulated":
        from stocker.broker.simulated import SimulatedBroker

        logger.info("Creating SimulatedBroker (explicitly configured)")
        return SimulatedBroker()

    # --- Default: futu ---
    try:
        from stocker.broker.futu import FutuBroker

        if runtime is None:
            logger.warning(
                "broker_type=futu but no FutuRuntime provided — "
                "falling back to SimulatedBroker (start OpenD first)"
            )
        elif not getattr(runtime, "started", False):
            logger.warning(
                "broker_type=futu but FutuRuntime did not start successfully "
                "(OpenD not logged in?) — falling back to SimulatedBroker"
            )
        else:
            exec_mode = config.get("execution_mode", "observe")
            trd_env = runtime.config.trd_env.lower()

            # Log the safety-critical environment combination
            if exec_mode == "active" and trd_env == "real":
                logger.warning(
                    "!! LIVE TRADING ENABLED !! execution_mode=active + trd_env=real — "
                    "orders WILL be sent to the real market"
                )
            elif exec_mode == "active" and trd_env == "simulate":
                logger.info(
                    "Creating FutuBroker: active + simulate (paper trading)"
                )
            elif exec_mode == "observe":
                logger.info(
                    "Creating FutuBroker: observe mode — broker connected but "
                    "place_order will be blocked at runtime"
                )

            return FutuBroker(runtime=runtime, config=config)
    except ImportError:
        logger.warning(
            "broker_type=futu but futu-api is not installed — "
            "install with: pip install 'stocker[brokers]'  — falling back to SimulatedBroker"
        )

    # Fallback: SimulatedBroker
    from stocker.broker.simulated import SimulatedBroker

    logger.info("Creating SimulatedBroker (fallback)")
    return SimulatedBroker()
