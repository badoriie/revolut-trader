#!/usr/bin/env python3
"""
Revolut Trader Dashboard
Comprehensive web dashboard for backtesting, paper trading, and live trading
"""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Page config
st.set_page_config(
    page_title="Revolut Trader Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 5px solid #1f77b4;
    }
    .positive {
        color: #00b050;
    }
    .negative {
        color: #ff0000;
    }
</style>
""",
    unsafe_allow_html=True,
)


def load_backtest_results(file_path: Path) -> dict | None:
    """Load backtest results from JSON file."""
    try:
        with open(file_path) as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading {file_path}: {e}")
        return None


def load_all_backtests(results_dir: Path = Path("./results")) -> list[dict]:
    """Load all backtest JSON files from results directory."""
    if not results_dir.exists():
        return []

    results = []
    for json_file in results_dir.glob("*.json"):
        data = load_backtest_results(json_file)
        if data:
            data["filename"] = json_file.name
            results.append(data)

    return results


def create_equity_curve_chart(equity_curve: list[dict]) -> go.Figure:
    """Create equity curve chart."""
    if not equity_curve:
        return go.Figure()

    df = pd.DataFrame(equity_curve)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["equity"],
            mode="lines",
            name="Portfolio Value",
            line=dict(color="#1f77b4", width=2),
            fill="tozeroy",
            fillcolor="rgba(31, 119, 180, 0.1)",
        )
    )

    fig.update_layout(
        title="Equity Curve",
        xaxis_title="Time",
        yaxis_title="Portfolio Value ($)",
        hovermode="x unified",
        template="plotly_white",
        height=400,
    )

    return fig


def create_pnl_chart(trades: list[dict]) -> go.Figure:
    """Create cumulative P&L chart from trades."""
    if not trades:
        return go.Figure()

    df = pd.DataFrame(trades)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    df = df.sort_values("timestamp")
    df["cumulative_pnl"] = df["pnl"].cumsum()

    fig = go.Figure()

    # Cumulative P&L line
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["cumulative_pnl"],
            mode="lines+markers",
            name="Cumulative P&L",
            line=dict(color="#00b050", width=2),
            marker=dict(size=6),
        )
    )

    # Individual trade P&L bars
    colors = ["#00b050" if x > 0 else "#ff0000" for x in df["pnl"]]
    fig.add_trace(
        go.Bar(
            x=df["timestamp"],
            y=df["pnl"],
            name="Trade P&L",
            marker=dict(color=colors),
            opacity=0.6,
            yaxis="y2",
        )
    )

    fig.update_layout(
        title="Profit & Loss",
        xaxis_title="Time",
        yaxis_title="Cumulative P&L ($)",
        yaxis2=dict(title="Trade P&L ($)", overlaying="y", side="right"),
        hovermode="x unified",
        template="plotly_white",
        height=400,
    )

    return fig


def create_trades_table(trades: list[dict]) -> pd.DataFrame:
    """Create formatted trades dataframe."""
    if not trades:
        return pd.DataFrame()

    df = pd.DataFrame(trades)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601").dt.strftime(
        "%Y-%m-%d %H:%M"
    )

    # Format numeric columns
    df["price"] = df["price"].apply(lambda x: f"${x:,.2f}")
    df["quantity"] = df["quantity"].apply(lambda x: f"{x:.8f}")
    df["pnl"] = df["pnl"].apply(lambda x: f"${x:,.2f}")

    return df[["timestamp", "symbol", "side", "quantity", "price", "pnl"]]


def render_backtest_view():
    """Render backtest results view."""
    st.markdown('<div class="main-header">📊 Backtest Results</div>', unsafe_allow_html=True)

    # Load all backtest results
    results_list = load_all_backtests()

    if not results_list:
        st.warning("No backtest results found in ./results/ directory")
        st.info(
            "Run a backtest with --output flag to generate results:\n\n`python backtest.py --strategy momentum --output ./results/test.json`"
        )
        return

    # Sidebar: Select backtest
    st.sidebar.subheader("📁 Select Backtest")
    selected_file = st.sidebar.selectbox(
        "Choose a result file:",
        [r["filename"] for r in results_list],
        index=0,
    )

    # Find selected result
    result = next(r for r in results_list if r["filename"] == selected_file)

    # Display metadata
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Strategy", result["config"]["strategy"].replace("_", " ").title())
    with col2:
        st.metric("Risk Level", result["config"]["risk_level"].title())
    with col3:
        st.metric("Days Tested", result["config"]["days"])
    with col4:
        st.metric("Interval", f"{result['config']['interval']}min")

    st.divider()

    # Performance metrics
    st.subheader("📈 Performance Metrics")
    metrics = result["results"]

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        pnl = metrics["total_pnl"]
        pnl_color = "positive" if pnl > 0 else "negative"
        st.metric(
            "Total P&L",
            f"${pnl:,.2f}",
            delta=f"{metrics['return_pct']:.2f}%",
        )

    with col2:
        st.metric("Total Trades", metrics["total_trades"])

    with col3:
        win_rate = metrics["win_rate"]
        st.metric("Win Rate", f"{win_rate:.1f}%")

    with col4:
        pf = metrics["profit_factor"]
        st.metric("Profit Factor", f"{pf:.2f}")

    with col5:
        dd = metrics["max_drawdown"]
        st.metric("Max Drawdown", f"${dd:,.2f}")

    st.divider()

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        if result.get("equity_curve"):
            fig = create_equity_curve_chart(result["equity_curve"])
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No equity curve data available")

    with col2:
        if result.get("trades"):
            fig = create_pnl_chart(result["trades"])
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No trade data available")

    # Trade history
    st.subheader("📝 Trade History")
    if result.get("trades"):
        trades_df = create_trades_table(result["trades"])
        st.dataframe(trades_df, width="stretch", hide_index=True)
    else:
        st.info("No trades executed in this backtest")


def render_comparison_view():
    """Render strategy comparison view."""
    st.markdown('<div class="main-header">🔬 Strategy Comparison</div>', unsafe_allow_html=True)

    results_list = load_all_backtests()

    if len(results_list) < 2:
        st.warning("Need at least 2 backtest results for comparison")
        st.info("Run multiple backtests with different strategies or parameters")
        return

    # Create comparison dataframe
    comparison_data = []
    for result in results_list:
        comparison_data.append(
            {
                "File": result["filename"],
                "Strategy": result["config"]["strategy"],
                "Risk": result["config"]["risk_level"],
                "Days": result["config"]["days"],
                "Return %": f"{result['results']['return_pct']:.2f}%",
                "Total P&L": f"${result['results']['total_pnl']:.2f}",
                "Trades": result["results"]["total_trades"],
                "Win Rate": f"{result['results']['win_rate']:.1f}%",
                "Profit Factor": f"{result['results']['profit_factor']:.2f}",
                "Max DD": f"${result['results']['max_drawdown']:.2f}",
            }
        )

    df = pd.DataFrame(comparison_data)
    st.dataframe(df, width="stretch", hide_index=True)

    # Comparison charts
    st.subheader("📊 Performance Comparison")

    # Returns comparison
    fig = go.Figure()
    for result in results_list:
        label = f"{result['config']['strategy']} ({result['config']['risk_level']})"
        fig.add_trace(
            go.Bar(
                name=label,
                x=["Return %"],
                y=[result["results"]["return_pct"]],
            )
        )

    fig.update_layout(
        title="Strategy Returns Comparison",
        yaxis_title="Return %",
        template="plotly_white",
        height=400,
    )

    st.plotly_chart(fig, width="stretch")


def render_live_monitor():
    """Render live/paper trading monitor (placeholder)."""
    st.markdown('<div class="main-header">🔴 Live Trading Monitor</div>', unsafe_allow_html=True)

    st.info(
        """
    **Real-time monitoring feature coming soon!**

    This will show:
    - Current portfolio value
    - Open positions
    - Recent trades
    - Live P&L
    - Strategy performance

    For now, use the trading bot logs:
    ```
    tail -f logs/trading.log
    ```
    """
    )

    # Placeholder metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Portfolio Value", "$10,000.00", delta="0.00%")
    with col2:
        st.metric("Open Positions", "0")
    with col3:
        st.metric("Today's P&L", "$0.00", delta="0.00%")
    with col4:
        st.metric("Total Trades", "0")


def main():
    """Main dashboard entry point."""

    # Sidebar navigation
    st.sidebar.title("🚀 Revolut Trader")
    st.sidebar.markdown("---")

    page = st.sidebar.radio(
        "Navigation",
        ["📊 Backtest Results", "🔬 Strategy Comparison", "🔴 Live Monitor"],
        index=0,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📚 Quick Actions")

    if st.sidebar.button("🔄 Refresh Data"):
        st.rerun()

    st.sidebar.markdown(
        """
    ### 💡 Tip
    Run backtests with:
    ```bash
    python backtest.py \\
      --strategy momentum \\
      --output results/test.json
    ```
    """
    )

    # Render selected page
    if page == "📊 Backtest Results":
        render_backtest_view()
    elif page == "🔬 Strategy Comparison":
        render_comparison_view()
    elif page == "🔴 Live Monitor":
        render_live_monitor()


if __name__ == "__main__":
    main()
