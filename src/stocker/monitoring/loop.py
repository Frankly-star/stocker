"""Continuous monitoring loop for RUN-001.

The loop is intentionally lightweight: it syncs broker positions and scans the
watchlist with the fixed westock-data route. It does not place orders.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


async def run_monitoring_cycle(
    *,
    broker: Any = None,
    position_store: Any = None,
    watchlist_store: Any = None,
    alert_store: Any = None,
    min_signal_strength: float = 20.0,
) -> dict:
    """Run one monitoring cycle and return a compact summary."""
    summary: dict[str, Any] = {
        "started_at": datetime.now().isoformat(),
        "broker_synced_positions": 0,
        "local_positions": 0,
        "watchlist_items": 0,
        "watchlist_signals": 0,
        "position_alerts": 0,
        "new_alerts": 0,
        "suppressed_alerts": 0,
        "warnings": [],
    }


    if broker is not None and position_store is not None:
        try:
            broker_positions = await broker.sync_positions()
            summary["broker_synced_positions"] = len(broker_positions or [])
            if broker_positions:
                position_store.sync_from_broker(broker_positions)
        except Exception as e:
            logger.warning("[Monitoring] broker position sync failed: %s", e)
            summary["warnings"].append(f"broker_sync: {e}")

    if position_store is not None:
        try:
            summary["local_positions"] = len(position_store.list_all())
            from stocker.alerts.position_alerts import generate_position_alerts

            alert_result = await asyncio.to_thread(
                generate_position_alerts,
                position_store,
                alert_store,
            )
            summary["position_alerts"] = alert_result.get("actionable_count", 0)
            summary["new_alerts"] = len(alert_result.get("new_alerts", []))
            summary["suppressed_alerts"] = alert_result.get("suppressed_duplicates", 0)
        except Exception as e:
            logger.warning("[Monitoring] position alert generation failed: %s", e)
            summary["warnings"].append(f"position_alerts: {e}")

    if watchlist_store is not None:
        try:
            items = watchlist_store.list_all()
            summary["watchlist_items"] = len(items)
            if items:
                from stocker.analysis.swing_signals import SwingSignalEngine
                from stocker.utils.data_helpers import fetch_ohlcv_westock

                engine = SwingSignalEngine()
                for item in items[:30]:
                    try:
                        df = await asyncio.to_thread(fetch_ohlcv_westock, item.ticker)
                        if df is None or df.empty:
                            continue
                        signal = engine.analyze(item.ticker, df)
                        if signal and signal.strength >= min_signal_strength:
                            watchlist_store.update_signal(item.ticker, signal.model_dump(mode="json"))
                            summary["watchlist_signals"] += 1
                    except Exception as e:
                        logger.debug("[Monitoring] watchlist scan failed for %s: %s", item.ticker, e)
        except Exception as e:
            logger.warning("[Monitoring] watchlist scan failed: %s", e)
            summary["warnings"].append(f"watchlist_scan: {e}")

    summary["finished_at"] = datetime.now().isoformat()
    return summary


async def monitoring_loop(
    *,
    broker: Any = None,
    position_store: Any = None,
    watchlist_store: Any = None,
    alert_store: Any = None,
) -> None:
    """Run the process-global monitoring loop until cancelled."""
    from stocker.engine.runtime_state import (
        get_monitoring_enabled,
        get_monitoring_interval_seconds,
        mark_monitoring_cycle_completed,
        mark_monitoring_cycle_failed,
        mark_monitoring_cycle_started,
        set_monitoring_running,
    )

    set_monitoring_running(True)
    logger.info("[Monitoring] Background loop started")

    try:
        while True:
            try:
                if not get_monitoring_enabled():
                    await asyncio.sleep(5)
                    continue

                mark_monitoring_cycle_started()
                summary = await run_monitoring_cycle(
                    broker=broker,
                    position_store=position_store,
                    watchlist_store=watchlist_store,
                    alert_store=alert_store,
                )
                mark_monitoring_cycle_completed(summary)
                logger.info("[Monitoring] Cycle complete: %s", summary)

                await asyncio.sleep(get_monitoring_interval_seconds())
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("[Monitoring] Cycle failed: %s", e)
                mark_monitoring_cycle_failed(str(e))
                await asyncio.sleep(min(get_monitoring_interval_seconds(), 60))
    except asyncio.CancelledError:
        logger.info("[Monitoring] Background loop cancelled")
    finally:
        set_monitoring_running(False)
