"""Strategy configuration models with Pydantic v2 validation.

All trading strategy parameters that were previously hardcoded across the codebase
are centralized here as structured, validated configuration models.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Technical Analysis Config
# ---------------------------------------------------------------------------

class TechnicalConfig(BaseModel):
    """Technical indicator parameters."""

    rsi_window: int = Field(14, ge=2, le=100, description="RSI 计算窗口")

    macd_fast: int = Field(12, ge=2, le=50, description="MACD 快线周期")
    macd_slow: int = Field(26, ge=10, le=100, description="MACD 慢线周期")
    macd_signal: int = Field(9, ge=2, le=50, description="MACD 信号线周期")

    bb_window: int = Field(20, ge=5, le=100, description="布林带窗口")
    bb_std: float = Field(2.0, ge=0.5, le=4.0, description="布林带标准差倍数")

    atr_window: int = Field(14, ge=2, le=100, description="ATR 计算窗口")

    sma_short: int = Field(50, ge=5, le=200, description="短期均线周期")
    sma_long: int = Field(200, ge=50, le=500, description="长期均线周期")

    sr_window: int = Field(20, ge=5, le=100, description="支撑阻力检测窗口")
    sr_num_levels: int = Field(3, ge=1, le=10, description="支撑/阻力级别数")
    sr_tolerance_pct: float = Field(1.5, ge=0.1, le=5.0, description="支撑阻力聚类容差%")

    @model_validator(mode="after")
    def check_macd_periods(self) -> "TechnicalConfig":
        if self.macd_fast >= self.macd_slow:
            raise ValueError(
                f"MACD 快线周期({self.macd_fast})必须小于慢线周期({self.macd_slow})"
            )
        return self

    @model_validator(mode="after")
    def check_sma_periods(self) -> "TechnicalConfig":
        if self.sma_short >= self.sma_long:
            raise ValueError(
                f"短期均线({self.sma_short})必须小于长期均线({self.sma_long})"
            )
        return self


# ---------------------------------------------------------------------------
# Risk / Trading Config
# ---------------------------------------------------------------------------

class RiskConfig(BaseModel):
    """Trading risk management parameters."""

    stop_loss_min_pct: float = Field(2.0, ge=0.5, le=20.0, description="止损最小百分比（低波动股）")
    stop_loss_max_pct: float = Field(10.0, ge=1.0, le=30.0, description="止损最大百分比（高波动股）")

    take_profit_min_ratio: float = Field(1.5, ge=1.0, le=10.0, description="最低风险回报比")

    position_size_min_pct: float = Field(2.0, ge=0.5, le=20.0, description="单笔最小仓位%")
    position_size_max_pct: float = Field(10.0, ge=1.0, le=50.0, description="单笔最大仓位%")

    confidence_threshold: float = Field(0.7, ge=0.1, le=1.0, description="交易置信度阈值")

    price_validation_min_pct: float = Field(1.0, ge=0.1, le=5.0, description="止损距当前价最小距离%")

    @model_validator(mode="after")
    def check_stop_loss_range(self) -> "RiskConfig":
        if self.stop_loss_min_pct >= self.stop_loss_max_pct:
            raise ValueError(
                f"止损最小值({self.stop_loss_min_pct}%)必须小于最大值({self.stop_loss_max_pct}%)"
            )
        return self

    @model_validator(mode="after")
    def check_position_range(self) -> "RiskConfig":
        if self.position_size_min_pct >= self.position_size_max_pct:
            raise ValueError(
                f"仓位最小值({self.position_size_min_pct}%)必须小于最大值({self.position_size_max_pct}%)"
            )
        return self


# ---------------------------------------------------------------------------
# Data Fetching Config
# ---------------------------------------------------------------------------

class DataConfig(BaseModel):
    """Data acquisition parameters."""

    kline_count: int = Field(120, ge=30, le=500, description="K 线获取数量")
    news_ticker_limit: int = Field(10, ge=1, le=50, description="个股新闻条数")
    news_global_limit: int = Field(8, ge=1, le=30, description="全球新闻条数")
    lookback_days: int = Field(30, ge=7, le=365, description="数据回看天数")
    rss_timeout: int = Field(10, ge=3, le=60, description="RSS 抓取超时(秒)")
    subprocess_timeout: int = Field(15, ge=5, le=120, description="子进程超时(秒)")


# ---------------------------------------------------------------------------
# Market Environment Detection Config
# ---------------------------------------------------------------------------

class MarketDetectionConfig(BaseModel):
    """Market environment detection thresholds."""

    bb_squeeze_threshold: float = Field(0.04, ge=0.01, le=0.20, description="布林带挤压阈值")
    atr_trend_threshold: float = Field(1.5, ge=1.0, le=5.0, description="ATR 趋势阈值(倍数)")
    zone_threshold_pct: float = Field(2.0, ge=0.5, le=10.0, description="区域判定阈值%")
    min_bars_required: int = Field(50, ge=20, le=200, description="最少 K 线数量")


# ---------------------------------------------------------------------------
# Top-level Strategy Config
# ---------------------------------------------------------------------------

class StrategyConfig(BaseModel):
    """Top-level strategy configuration — the single source of truth."""

    name: str = Field("balanced", description="策略名称")
    description: str = Field("均衡型策略", description="策略描述")

    technical: TechnicalConfig = Field(default_factory=TechnicalConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    market: MarketDetectionConfig = Field(default_factory=MarketDetectionConfig)

    version: str = Field("1.0", description="策略版本")
    updated_at: str = Field(default="", description="最后更新时间")

    def with_timestamp(self) -> "StrategyConfig":
        """Return a copy with updated_at set to now."""
        return self.model_copy(update={"updated_at": datetime.now().isoformat()})
