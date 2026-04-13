"""Data models for the analysis pipeline and inter-team communication."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Execution mode: only controls whether trades are actually executed
# The Supervisor LLM decides what to do (analyze, assess, query status, etc.)
# based on conversation context — no need for granular mode selection.
# ---------------------------------------------------------------------------

class ExecutionMode(str, Enum):
    ACTIVE = "active"        # Full autonomy: Supervisor can execute trades
    OBSERVE = "observe"      # Observe-only: Supervisor analyzes but never executes trades


# ---------------------------------------------------------------------------
# Team 1 output: Data Intelligence
# ---------------------------------------------------------------------------

class TechnicalSignals(BaseModel):
    """Structured technical indicator values."""
    rsi: float = 50.0
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_position: float = 0.5  # 0-1, current price position within Bollinger Bands
    atr: float = 0.0
    vwap: float = 0.0
    sma_50: float = 0.0
    sma_200: float = 0.0
    trend: str = "sideways"  # "uptrend" / "downtrend" / "sideways"


class TechnicalAnalysisReport(BaseModel):
    """Output of MarketDataAgent."""
    ticker: str
    current_price: float
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    current_zone: str = "mid_range"  # "near_support" / "mid_range" / "near_resistance"
    range_width_pct: float = 0.0
    technical_signals: TechnicalSignals = Field(default_factory=TechnicalSignals)
    market_environment: str = "range_bound"  # "range_bound" / "trending_up" / "trending_down" / "volatile"
    summary: str = ""


class NewsSentimentReport(BaseModel):
    """Output of NewsAgent."""
    ticker: str
    sentiment_score: float = 0.0  # -1.0 ~ 1.0
    key_events: list[str] = Field(default_factory=list)
    overall_mood: str = "neutral"  # "bullish" / "bearish" / "neutral" / "mixed"
    news_count: int = 0
    summary: str = ""


class FundamentalsReport(BaseModel):
    """Output of FundamentalsAgent."""
    ticker: str
    valuation_status: str = "fair"  # "overvalued" / "fair" / "undervalued"
    key_metrics: dict = Field(default_factory=dict)  # PE, PB, EPS, etc.
    earnings_surprise: str = ""
    sector: str = ""
    industry: str = ""
    summary: str = ""


class SocialSentimentReport(BaseModel):
    """Output of SocialMediaAgent."""
    ticker: str
    retail_sentiment: float = 0.0  # -1.0 ~ 1.0
    buzz_level: str = "normal"  # "low" / "normal" / "high" / "viral"
    contrarian_signal: bool = False
    summary: str = ""


class MarketIntelligenceReport(BaseModel):
    """Unified output of the Data Intelligence Team. Input to Risk Assessment Team."""
    ticker: str
    timestamp: datetime = Field(default_factory=datetime.now)
    current_price: float = 0.0

    # Technical analysis
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    current_zone: str = "mid_range"
    range_width_pct: float = 0.0
    technical_signals: TechnicalSignals = Field(default_factory=TechnicalSignals)

    # News & sentiment
    sentiment_score: float = 0.0
    key_news_events: list[str] = Field(default_factory=list)

    # Fundamentals
    fundamental_valuation: str = "fair"
    fundamental_metrics: dict = Field(default_factory=dict)

    # Social
    social_sentiment: float = 0.0

    # Overall
    market_environment: str = "range_bound"

    # Raw text reports (for risk team's debate context)
    raw_reports: dict = Field(default_factory=dict)

    # Data quality tracking — CRITICAL for preventing fake-looking default reports
    data_quality: str = "unknown"  # "good" / "partial" / "poor" / "unknown"
    data_sources_used: list[str] = Field(default_factory=list)
    data_warnings: list[str] = Field(default_factory=list)

    def assess_data_quality(self) -> str:
        """Assess data quality based on what reports actually contain real data."""
        reports = self.raw_reports
        has_real_data = 0
        total = len(reports) if reports else 4
        warnings = []

        for name, text in reports.items():
            if text and len(text) > 50 and "error" not in text.lower()[:100] and "no data" not in text.lower()[:100] and "rate limit" not in text.lower()[:100]:
                has_real_data += 1
            else:
                warnings.append(f"{name}: no real data obtained")

        # Also check if price is clearly a default
        if self.current_price == 0.0:
            warnings.append("price: no real price data")

        self.data_warnings = warnings

        if has_real_data >= 3:
            self.data_quality = "good"
        elif has_real_data >= 1:
            self.data_quality = "partial"
        else:
            self.data_quality = "poor"

        return self.data_quality

    def to_situation_text(self) -> str:
        """Format as text for risk assessment team's debate context."""
        # Auto-assess quality if not done yet
        if self.data_quality == "unknown":
            self.assess_data_quality()

        lines = []

        # CRITICAL: Warn about data quality prominently
        if self.data_quality == "poor":
            lines.extend([
                f"## ⚠️ WARNING: DATA QUALITY IS POOR FOR {self.ticker}",
                "",
                "**Most data below is DEFAULT/PLACEHOLDER values, NOT real market data.**",
                "**DO NOT make trading decisions based on these numbers.**",
                "**The data sources (e.g. yfinance) were likely rate-limited or unavailable.**",
                "",
                "Data issues:",
                *[f"  - {w}" for w in self.data_warnings],
                "",
            ])
        elif self.data_quality == "partial":
            lines.extend([
                f"## ⚠️ PARTIAL DATA for {self.ticker}",
                "",
                "Some data sources failed. Analysis may be incomplete:",
                *[f"  - {w}" for w in self.data_warnings],
                "",
            ])

        lines.extend([
            f"## Market Intelligence Report for {self.ticker}",
            f"**Data Quality**: {self.data_quality.upper()}",
            f"**Price**: ${self.current_price:.2f}" if self.current_price > 0 else "**Price**: UNAVAILABLE",
            f"**Market Environment**: {self.market_environment}",
            f"**Current Zone**: {self.current_zone}",
            f"**Support Levels**: {self.support_levels}",
            f"**Resistance Levels**: {self.resistance_levels}",
            f"**Range Width**: {self.range_width_pct:.1f}%",
            "",
            f"**Technical Signals**:",
            f"  RSI: {self.technical_signals.rsi:.1f}",
            f"  MACD Histogram: {self.technical_signals.macd_histogram:.4f}",
            f"  BB Position: {self.technical_signals.bb_position:.2f}",
            f"  ATR: {self.technical_signals.atr:.2f}",
            f"  Trend: {self.technical_signals.trend}",
            "",
            f"**Sentiment Score**: {self.sentiment_score:.2f}",
            f"**Fundamental Valuation**: {self.fundamental_valuation}",
            f"**Social Sentiment**: {self.social_sentiment:.2f}",
        ])
        if self.key_news_events:
            lines.append(f"**Key Events**: {'; '.join(self.key_news_events[:5])}")
        if self.raw_reports:
            for name, text in self.raw_reports.items():
                lines.append(f"\n### {name}\n{text[:2000]}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Team 2 output: Risk Assessment
# ---------------------------------------------------------------------------

class RiskAssessmentResult(BaseModel):
    """Output of the Risk Assessment Team."""
    ticker: str = ""
    rating: str = "HOLD"  # BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL
    confidence: float = 0.5  # 0-1
    suggested_action: str = ""
    position_size_pct: float = 0.0  # recommended position size as portfolio %
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_level: str = "MEDIUM"  # LOW / MEDIUM / HIGH
    key_reasons: list[str] = Field(default_factory=list)
    investment_thesis: str = ""
    debate_summary: str = ""  # summary of bull/bear debate


# ---------------------------------------------------------------------------
# Swing signal models (used by SwingSignalEngine + WatchlistItem)
# ---------------------------------------------------------------------------

class SwingSignalType(str, Enum):
    ENTRY_LONG = "entry_long"
    EXIT_LONG = "exit_long"
    NEUTRAL = "neutral"


class SwingSignal(BaseModel):
    """Composite swing trading signal with strength score."""
    ticker: str = ""
    signal_type: SwingSignalType = SwingSignalType.NEUTRAL
    strength: float = 0.0  # 0-100
    suggested_price: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    reasons: list[str] = Field(default_factory=list)
    indicators: dict = Field(default_factory=dict)
    market_environment: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
