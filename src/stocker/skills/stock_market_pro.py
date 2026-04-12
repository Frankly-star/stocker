"""Skill adapter for stock-market-pro: yfinance-driven stock analysis."""

from __future__ import annotations

from langchain_core.tools import tool

from stocker.skills.base import SkillAdapter, SkillManifest


class StockMarketProSkill(SkillAdapter):

    @property
    def name(self) -> str:
        return "stock-market-pro"

    @property
    def description(self) -> str:
        return "Stock analysis: real-time quotes, technical indicators (RSI/MACD/BB/ATR), K-line charts, comprehensive reports"

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name=self.name,
            description=self.description,
            sub_capabilities=["price", "fundamentals", "chart", "report", "indicators"],
            version="1.2.12",
        )

    def load(self) -> dict:
        prompt = (
            "You now have access to the stock-market-pro skill.\n"
            "Use get_stock_price for real-time quotes.\n"
            "Use get_technical_indicators for RSI, MACD, BB, ATR values.\n"
            "Combine multiple indicators to form a technical analysis view."
        )

        @tool
        def get_stock_price(symbol: str) -> str:
            """Get current stock price and basic info via yfinance."""
            import yfinance as yf
            try:
                t = yf.Ticker(symbol.upper())
                info = t.info
                price = info.get("regularMarketPrice") or info.get("currentPrice", "N/A")
                prev = info.get("regularMarketPreviousClose", 0)
                change = float(price) - float(prev) if price != "N/A" and prev else 0
                return f"{symbol.upper()}: ${price} (change: {change:+.2f})"
            except Exception as e:
                return f"Error: {e}"

        @tool
        def get_technical_indicators(symbol: str, period: str = "3mo") -> str:
            """Calculate RSI, MACD, Bollinger Bands, ATR for a stock."""
            import yfinance as yf
            from stocker.analysis.indicators import calc_rsi, calc_macd, calc_bbands, calc_atr

            try:
                t = yf.Ticker(symbol.upper())
                df = t.history(period=period)
                if df.empty:
                    return f"No data for {symbol}"

                rsi = calc_rsi(df["Close"])
                macd_l, macd_s, macd_h = calc_macd(df["Close"])
                bb_u, bb_m, bb_l = calc_bbands(df["Close"])
                atr = calc_atr(df)

                latest = len(df) - 1
                return (
                    f"Technical Indicators for {symbol.upper()}:\n"
                    f"  RSI(14): {rsi.iloc[latest]:.1f}\n"
                    f"  MACD: {macd_l.iloc[latest]:.4f} / Signal: {macd_s.iloc[latest]:.4f} / Hist: {macd_h.iloc[latest]:.4f}\n"
                    f"  BB: Upper={bb_u.iloc[latest]:.2f} / Mid={bb_m.iloc[latest]:.2f} / Lower={bb_l.iloc[latest]:.2f}\n"
                    f"  ATR(14): {atr.iloc[latest]:.2f}"
                )
            except Exception as e:
                return f"Error: {e}"

        return {"prompt": prompt, "tools": [get_stock_price, get_technical_indicators]}
