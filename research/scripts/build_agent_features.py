"""Compute agent-level features from exported research CSVs."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from research_common import as_float, ensure_dir, mean, read_csv, stddev, write_csv


INITIAL_CAPITAL = 100000.0


def max_drawdown(values: list[float]) -> float:
    peak = None
    drawdown = 0.0
    for value in values:
        peak = value if peak is None else max(peak, value)
        if peak and peak > 0:
            drawdown = max(drawdown, (peak - value) / peak)
    return drawdown


def build_features(input_dir: str, output_dir: str) -> str:
    agents = read_csv(f"{input_dir}/agents.csv")
    signals = read_csv(f"{input_dir}/signals.csv")
    replies = read_csv(f"{input_dir}/signal_replies.csv")
    subscriptions = read_csv(f"{input_dir}/subscriptions.csv")
    trades = read_csv(f"{input_dir}/trades.csv")
    history = read_csv(f"{input_dir}/profit_history.csv")

    signals_by_agent = defaultdict(list)
    for row in signals:
        signals_by_agent[row.get("agent_hash") or row.get("agent_id")].append(row)

    replies_by_agent = Counter(row.get("agent_hash") or row.get("agent_id") for row in replies)
    replies_received = Counter(row.get("parent_agent_hash") or row.get("parent_agent_id") for row in replies)
    accepted_by_agent = Counter((row.get("agent_hash") or row.get("agent_id")) for row in replies if str(row.get("accepted")) in {"1", "true", "True"})
    followers = Counter(row.get("leader_hash") or row.get("leader_id") for row in subscriptions if row.get("status") == "active")
    following = Counter(row.get("follower_hash") or row.get("follower_id") for row in subscriptions if row.get("status") == "active")
    trades_by_agent = Counter(row.get("agent_hash") or row.get("agent_id") for row in trades)
    history_by_agent = defaultdict(list)
    for row in history:
        key = row.get("agent_hash") or row.get("agent_id")
        history_by_agent[key].append((row.get("recorded_at"), as_float(row.get("total_value"), INITIAL_CAPITAL)))

    rows = []
    for agent in agents:
        key = agent.get("agent_hash") or agent.get("agent_id")
        agent_signals = signals_by_agent.get(key, [])
        markets = Counter(row.get("market") for row in agent_signals if row.get("market"))
        values = [value for _recorded_at, value in sorted(history_by_agent.get(key, []))]
        profit = values[-1] - INITIAL_CAPITAL if values else as_float(agent.get("cash"), INITIAL_CAPITAL) - INITIAL_CAPITAL
        returns = [((values[i] - values[i - 1]) / values[i - 1]) for i in range(1, len(values)) if values[i - 1]]
        active_days = len({(row.get("created_at") or "")[:10] for row in agent_signals if row.get("created_at")})
        rows.append({
            "agent_id": agent.get("agent_id"),
            "agent_hash": agent.get("agent_hash"),
            "registered_at": agent.get("created_at"),
            "active_days": active_days,
            "post_count": len(agent_signals),
            "reply_count": replies_by_agent.get(key, 0),
            "replies_received_count": replies_received.get(key, 0),
            "accepted_reply_count": accepted_by_agent.get(key, 0),
            "follower_count": followers.get(key, 0),
            "following_count": following.get(key, 0),
            "trade_count": trades_by_agent.get(key, 0),
            "primary_market": markets.most_common(1)[0][0] if markets else "",
            "profit": round(profit, 6),
            "max_drawdown": round(max_drawdown(values), 6),
            "volatility": round(stddev(returns), 6),
            "risk_adjusted_return": round((mean(returns) / stddev(returns)) if stddev(returns) else 0.0, 6),
        })

    output_path = ensure_dir(output_dir) / "agent_features.csv"
    write_csv(output_path, rows, [
        "agent_id", "agent_hash", "registered_at", "active_days", "post_count",
        "reply_count", "replies_received_count", "accepted_reply_count",
        "follower_count", "following_count", "trade_count", "primary_market",
        "profit", "max_drawdown", "volatility", "risk_adjusted_return",
    ])
    return str(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default="research/exports")
    parser.add_argument("--output-dir", default="research/exports/tables")
    args = parser.parse_args()
    print(f"wrote {build_features(args.input_dir, args.output_dir)}")


if __name__ == "__main__":
    main()
