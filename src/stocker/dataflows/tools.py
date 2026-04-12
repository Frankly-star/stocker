"""LangChain @tool definitions for the Data Intelligence Team agents."""

from __future__ import annotations

from langchain_core.tools import tool

from stocker.dataflows.router import DataRouter


def create_dataflow_tools(router: DataRouter) -> list:
    """Create LangChain tools backed by the DataRouter.

    Returns a list of tools that agents can bind_tools with.
    """

    @tool
    def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
        """Get OHLCV stock price data for a symbol within a date range (yyyy-mm-dd)."""
        return router.route("get_stock_data", symbol, start_date, end_date)

    @tool
    def get_fundamentals(ticker: str) -> str:
        """Get company fundamentals: PE, PB, EPS, revenue, margins, etc."""
        return router.route("get_fundamentals", ticker)

    @tool
    def get_news(ticker: str, start_date: str, end_date: str) -> str:
        """Get recent news articles for a stock ticker."""
        return router.route("get_news", ticker, start_date, end_date)

    @tool
    def get_global_news(curr_date: str) -> str:
        """Get global market and economic news."""
        return router.route("get_global_news", curr_date)

    @tool
    def get_balance_sheet(ticker: str) -> str:
        """Get quarterly balance sheet data."""
        return router.route("get_balance_sheet", ticker)

    @tool
    def get_income_statement(ticker: str) -> str:
        """Get quarterly income statement data."""
        return router.route("get_income_statement", ticker)

    @tool
    def get_insider_transactions(ticker: str) -> str:
        """Get insider trading transactions."""
        return router.route("get_insider_transactions", ticker)

    return [
        get_stock_data,
        get_fundamentals,
        get_news,
        get_global_news,
        get_balance_sheet,
        get_income_statement,
        get_insider_transactions,
    ]
