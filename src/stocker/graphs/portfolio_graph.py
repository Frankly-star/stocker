"""PortfolioSubgraph: CRUD + sync + scan operations on positions."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from stocker.graphs.state import PortfolioState
from stocker.portfolio.store import PositionStore


def build_portfolio_graph(store: PositionStore, broker: Any = None) -> StateGraph:
    """Build the Portfolio Management Subgraph."""

    def route_action(state: dict) -> str:
        return state.get("action", "list")

    def list_positions(state: dict) -> dict:
        positions = store.list_all()
        return {"result": {
            "action": "list",
            "positions": [p.model_dump(mode="json") for p in positions],
            "summary": store.get_summary(),
        }}

    def add_position(state: dict) -> dict:
        params = state.get("params", {})
        pos = store.add(
            ticker=params.get("ticker", ""),
            quantity=params.get("quantity", 0),
            avg_cost=params.get("avg_cost", 0),
        )
        return {"result": {"action": "add", "position": pos.model_dump(mode="json")}}

    def remove_position(state: dict) -> dict:
        ticker = state.get("ticker", "")
        success = store.remove(ticker)
        return {"result": {"action": "remove", "ticker": ticker, "success": success}}

    def sync_positions(state: dict) -> dict:
        if broker is None:
            return {"result": {"action": "sync", "message": "No broker configured for sync"}}

        import asyncio

        try:
            # broker.sync_positions is async — run it in the current or new event loop
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    positions = loop.run_in_executor(pool, asyncio.run, broker.sync_positions())
            except RuntimeError:
                positions = asyncio.run(broker.sync_positions())

            if positions:
                result = store.sync_from_broker(positions)
                return {"result": {"action": "sync", "message": "Broker sync complete", "detail": result}}
            return {"result": {"action": "sync", "message": "Broker sync: no positions returned"}}
        except Exception as e:
            return {"result": {"action": "sync", "message": f"Broker sync failed: {e}"}}

    def scan_positions(state: dict) -> dict:
        # Will be wired to PortfolioScanner
        return {"result": {"action": "scan", "message": "Portfolio scan triggered"}}

    graph = StateGraph(PortfolioState)

    graph.add_node("list", list_positions)
    graph.add_node("add", add_position)
    graph.add_node("remove", remove_position)
    graph.add_node("sync", sync_positions)
    graph.add_node("scan", scan_positions)

    graph.set_conditional_entry_point(
        route_action,
        {"list": "list", "add": "add", "remove": "remove", "sync": "sync", "scan": "scan"},
    )

    for node in ["list", "add", "remove", "sync", "scan"]:
        graph.add_edge(node, END)

    return graph.compile()
