"""Cross-field business logic validators for strategy configuration.

Pydantic model_validator handles per-sub-model checks. This module provides
top-level validation across the entire StrategyConfig.
"""

from __future__ import annotations

from stocker.strategy.models import StrategyConfig


def validate_strategy(config: StrategyConfig) -> list[str]:
    """Validate a complete strategy config and return a list of warnings/errors.

    Returns an empty list if everything is valid.
    Pydantic field constraints and model_validators handle strict type/range checks;
    this function adds softer business-rule warnings.
    """
    warnings: list[str] = []

    t = config.technical
    r = config.risk
    d = config.data
    m = config.market

    # --- Technical cross-checks ---
    if t.bb_window > t.sma_short:
        warnings.append(
            f"布林带窗口({t.bb_window})大于短期均线({t.sma_short})，可能导致信号滞后"
        )

    if t.rsi_window > t.atr_window * 3:
        warnings.append(
            f"RSI窗口({t.rsi_window})远大于ATR窗口({t.atr_window})，指标周期差异过大"
        )

    # --- Risk cross-checks ---
    if r.stop_loss_min_pct < r.price_validation_min_pct:
        warnings.append(
            f"止损最小值({r.stop_loss_min_pct}%)小于价格校验最小距离({r.price_validation_min_pct}%)，"
            f"止损可能被校验规则拒绝"
        )

    effective_min_tp = r.stop_loss_min_pct * r.take_profit_min_ratio
    if effective_min_tp > 30:
        warnings.append(
            f"最低止盈距离({effective_min_tp:.1f}%)过大（止损{r.stop_loss_min_pct}% × "
            f"风险回报比{r.take_profit_min_ratio}），可能难以触达"
        )

    # --- Data checks ---
    if d.kline_count < m.min_bars_required:
        warnings.append(
            f"K线数量({d.kline_count})小于市场检测最少要求({m.min_bars_required})，"
            f"环境检测可能不准确"
        )

    if d.rss_timeout >= d.subprocess_timeout:
        warnings.append(
            f"RSS超时({d.rss_timeout}s) >= 子进程超时({d.subprocess_timeout}s)，"
            f"可能导致 RSS 永远超时"
        )

    return warnings
