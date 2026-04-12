"""Built-in strategy presets: conservative, balanced, aggressive."""

from __future__ import annotations

from stocker.strategy.models import (
    DataConfig,
    MarketDetectionConfig,
    RiskConfig,
    StrategyConfig,
    TechnicalConfig,
)

# ---------------------------------------------------------------------------
# Conservative — 保守型：更宽止损、更小仓位、更长周期均线
# ---------------------------------------------------------------------------

CONSERVATIVE = StrategyConfig(
    name="conservative",
    description="保守型策略：优先资金安全，宽止损、小仓位、长周期分析",
    technical=TechnicalConfig(
        rsi_window=21,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        bb_window=25,
        bb_std=2.5,
        atr_window=21,
        sma_short=50,
        sma_long=200,
        sr_window=30,
        sr_num_levels=3,
        sr_tolerance_pct=2.0,
    ),
    risk=RiskConfig(
        stop_loss_min_pct=3.0,
        stop_loss_max_pct=12.0,
        take_profit_min_ratio=2.0,
        position_size_min_pct=1.0,
        position_size_max_pct=5.0,
        confidence_threshold=0.8,
        price_validation_min_pct=1.5,
    ),
    data=DataConfig(
        kline_count=180,
        news_ticker_limit=15,
        news_global_limit=10,
        lookback_days=60,
        rss_timeout=15,
        subprocess_timeout=20,
    ),
    market=MarketDetectionConfig(
        bb_squeeze_threshold=0.03,
        atr_trend_threshold=1.8,
        zone_threshold_pct=3.0,
        min_bars_required=60,
    ),
)

# ---------------------------------------------------------------------------
# Balanced — 均衡型（= 默认值）
# ---------------------------------------------------------------------------

BALANCED = StrategyConfig(
    name="balanced",
    description="均衡型策略：平衡风险与收益，适合大多数市场环境",
)

# ---------------------------------------------------------------------------
# Aggressive — 激进型：更窄止损、更大仓位、更短周期
# ---------------------------------------------------------------------------

AGGRESSIVE = StrategyConfig(
    name="aggressive",
    description="激进型策略：追求高收益，窄止损、大仓位、短周期捕捉机会",
    technical=TechnicalConfig(
        rsi_window=9,
        macd_fast=8,
        macd_slow=17,
        macd_signal=6,
        bb_window=15,
        bb_std=1.5,
        atr_window=10,
        sma_short=20,
        sma_long=100,
        sr_window=15,
        sr_num_levels=4,
        sr_tolerance_pct=1.0,
    ),
    risk=RiskConfig(
        stop_loss_min_pct=1.5,
        stop_loss_max_pct=7.0,
        take_profit_min_ratio=1.2,
        position_size_min_pct=3.0,
        position_size_max_pct=15.0,
        confidence_threshold=0.6,
        price_validation_min_pct=0.8,
    ),
    data=DataConfig(
        kline_count=90,
        news_ticker_limit=8,
        news_global_limit=6,
        lookback_days=14,
        rss_timeout=8,
        subprocess_timeout=12,
    ),
    market=MarketDetectionConfig(
        bb_squeeze_threshold=0.05,
        atr_trend_threshold=1.3,
        zone_threshold_pct=1.5,
        min_bars_required=30,
    ),
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PRESETS: dict[str, StrategyConfig] = {
    "conservative": CONSERVATIVE,
    "balanced": BALANCED,
    "aggressive": AGGRESSIVE,
}


def get_preset(name: str) -> StrategyConfig | None:
    """Get a preset by name, or None if not found."""
    return PRESETS.get(name)


def list_preset_names() -> list[str]:
    """List available preset names."""
    return list(PRESETS.keys())
