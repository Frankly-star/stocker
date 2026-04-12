"""Stocker CLI: control panel for the trading system."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(name="stocker", help="Multi-Agent automated range/swing trading system")
console = Console()


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="API host"),
    port: int = typer.Option(8000, help="API port"),
):
    """Start the stocker background service."""
    from stocker.config import load_config
    from stocker.engine.service import StockerService

    config = load_config()
    config["api_host"] = host
    config["api_port"] = port

    console.print("[bold green]Starting Stocker Service...[/bold green]")
    service = StockerService(config)
    service.start()


@app.command()
def analyze(ticker: str = typer.Argument(..., help="Stock ticker symbol")):
    """Run data analysis + risk assessment for a stock."""
    console.print(f"[bold]Analyzing {ticker.upper()}...[/bold]")

    from stocker.config import create_llm, load_config
    from stocker.agents.supervisor import SUPERVISOR_SYSTEM_PROMPT, create_supervisor_tools
    from stocker.graphs.main_graph import build_main_graph
    from langchain_core.messages import HumanMessage

    config = load_config()
    llm = create_llm(config, "deep")
    tools = create_supervisor_tools()
    graph = build_main_graph(llm, tools)

    result = graph.invoke({
        "messages": [HumanMessage(content=f"Analyze {ticker.upper()} and give me your assessment")],
    })

    # Print the last AI message
    for msg in reversed(result.get("messages", [])):
        if hasattr(msg, "content") and msg.content:
            console.print(f"\n{msg.content}")
            break


@app.command()
def status():
    """Show system status."""
    from stocker.config import load_config
    from stocker.portfolio.store import PositionStore

    config = load_config()
    store = PositionStore()
    summary = store.get_summary()

    console.print("[bold]System Status[/bold]")
    console.print(f"  Execution mode: {config.get('execution_mode', 'observe')}")
    console.print(f"  Broker type: {config.get('broker_type', 'futu')}")
    console.print(f"  Positions: {summary['count']}")
    console.print(f"  Total value: ${summary['total_value']:,.2f}")
    console.print(f"  Unrealized P&L: ${summary['total_unrealized_pnl']:,.2f}")
    if summary['tickers']:
        console.print(f"  Tickers: {', '.join(summary['tickers'])}")

    # Show Futu runtime status if available
    if config.get("broker_type") == "futu":
        try:
            from stocker.engine.runtime import get_active_runtime

            rt = get_active_runtime()
            if rt is not None:
                rs = rt.get_runtime_status()
                console.print("\n[bold]Futu Runtime[/bold]")
                console.print(f"  Quote connected: {rs.get('quote_connected', False)}")
                console.print(f"  Trade connected: {rs.get('trade_connected', False)}")
                console.print(f"  Trade unlocked: {rs.get('trade_unlocked', False)}")
                console.print(f"  Account ID: {rs.get('acc_id', 'N/A')}")
                console.print(f"  Trading env: {rs.get('trd_env', 'N/A')}")
                console.print(f"  Market: {rs.get('market', 'N/A')}")
                console.print(f"  Subscriptions: {rs.get('subscriptions_count', 0)}")
            else:
                console.print("\n[dim]Futu runtime not active (service not started?)[/dim]")
        except ImportError:
            console.print("\n[dim]futu-api not installed[/dim]")


@app.command()
def portfolio(
    action: str = typer.Argument("list", help="Action: list/add/remove"),
    ticker: str = typer.Option("", help="Ticker symbol"),
    quantity: int = typer.Option(0, help="Number of shares"),
    cost: float = typer.Option(0.0, help="Average cost per share"),
):
    """Manage portfolio positions."""
    from stocker.portfolio.store import PositionStore

    store = PositionStore()

    if action == "list":
        positions = store.list_all()
        if not positions:
            console.print("[dim]No positions[/dim]")
            return
        for p in positions:
            pnl = p.unrealized_pnl
            color = "green" if pnl >= 0 else "red"
            console.print(
                f"  {p.ticker}: {p.quantity} shares @ ${p.avg_cost:.2f} "
                f"[{color}]P&L: ${pnl:+,.2f}[/{color}] ({p.source.value})"
            )
    elif action == "add":
        if not ticker:
            console.print("[red]Ticker required for add[/red]")
            return
        pos = store.add(ticker.upper(), quantity, cost)
        console.print(f"[green]Added {pos.ticker}: {pos.quantity} @ ${pos.avg_cost:.2f}[/green]")
    elif action == "remove":
        if not ticker:
            console.print("[red]Ticker required for remove[/red]")
            return
        if store.remove(ticker.upper()):
            console.print(f"[green]Removed {ticker.upper()}[/green]")
        else:
            console.print(f"[red]{ticker.upper()} not found[/red]")


@app.command()
def chat():
    """Interactive chat with the Supervisor Agent."""
    console.print("[bold]Stocker Chat Mode[/bold] (type 'quit' to exit)\n")

    from stocker.config import create_llm, load_config
    from stocker.agents.supervisor import create_supervisor_tools
    from stocker.graphs.main_graph import build_main_graph
    from langchain_core.messages import HumanMessage

    config = load_config()
    llm = create_llm(config, "deep")
    tools = create_supervisor_tools()
    graph = build_main_graph(llm, tools)

    messages = []
    while True:
        try:
            user_input = console.input("[bold cyan]You>[/bold cyan] ")
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.strip().lower() in ("quit", "exit", "q"):
            break

        messages.append(HumanMessage(content=user_input))
        result = graph.invoke({"messages": messages})

        response_messages = result.get("messages", [])
        for msg in reversed(response_messages):
            if hasattr(msg, "content") and msg.content and not hasattr(msg, "tool_calls"):
                console.print(f"\n[bold green]Stocker>[/bold green] {msg.content}\n")
                messages = response_messages
                break


if __name__ == "__main__":
    app()
