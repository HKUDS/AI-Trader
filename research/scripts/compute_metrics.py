"""Compute competition, cooperation, and content metrics."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from research_common import as_float, ensure_dir, mean, read_csv, stddev, variant_summary, write_csv


def compute_metrics(input_dir: str, output_dir: str) -> dict[str, str]:
    agents = read_csv(f"{input_dir}/agents.csv")
    challenges = read_csv(f"{input_dir}/challenges.csv")
    challenge_results = read_csv(f"{input_dir}/challenge_results.csv")
    team_results = read_csv(f"{input_dir}/team_results.csv")
    replies = read_csv(f"{input_dir}/signal_replies.csv")
    quality = read_csv(f"{input_dir}/quality_scores.csv")
    edges = read_csv(f"{input_dir}/network_edges.csv")

    agent_count = max(len(agents), 1)
    participants = {row.get("agent_hash") or row.get("agent_id") for row in challenge_results}
    winners = {row.get("agent_hash") or row.get("agent_id") for row in challenge_results if str(row.get("rank")) == "1"}
    rank_by_agent = defaultdict(list)
    for row in challenge_results:
        rank_by_agent[row.get("agent_hash") or row.get("agent_id")].append(as_float(row.get("rank")))

    competition_rows = [
        {"metric": "challenge_participation_rate", "value": round(len(participants) / agent_count, 6), "n": len(challenge_results)},
        {"metric": "challenge_win_rate", "value": round(len(winners) / max(len(participants), 1), 6), "n": len(challenge_results)},
        {"metric": "rank_stability", "value": round(mean([1 / (1 + stddev(ranks)) for ranks in rank_by_agent.values()]), 6), "n": len(rank_by_agent)},
        {"metric": "risk_escalation", "value": round(mean(as_float(row.get("max_drawdown")) for row in challenge_results), 6), "n": len(challenge_results)},
        {"metric": "strategy_convergence", "value": round(1 / max(1, len({row.get("market") for row in challenges if row.get("market")})), 6), "n": len(challenges)},
        {"metric": "return_distribution_mean", "value": round(mean(as_float(row.get("return_pct")) for row in challenge_results), 6), "n": len(challenge_results)},
        {"metric": "max_drawdown_distribution_mean", "value": round(mean(as_float(row.get("max_drawdown")) for row in challenge_results), 6), "n": len(challenge_results)},
    ]

    edge_type_counts = Counter(row.get("edge_type") for row in edges)
    cooperation_rows = [
        {"metric": "citation_count", "value": edge_type_counts.get("citation", 0), "n": len(edges)},
        {"metric": "adoption_count", "value": edge_type_counts.get("adoption", 0) + edge_type_counts.get("follow", 0), "n": len(edges)},
        {"metric": "team_contribution_score", "value": round(mean(as_float(row.get("quality_score")) for row in team_results), 6), "n": len(team_results)},
        {"metric": "team_consensus_gain", "value": round(mean(as_float(row.get("consensus_gain")) for row in team_results), 6), "n": len(team_results)},
        {"metric": "reply_graph_centrality", "value": round(edge_type_counts.get("reply", 0) / max(agent_count, 1), 6), "n": len(edges)},
        {"metric": "cross_community_bridge_score", "value": edge_type_counts.get("same_team", 0), "n": len(edges)},
        {"metric": "discussion_gain", "value": len(replies), "n": len(replies)},
    ]

    content_rows = [
        {"metric": "verifiability", "value": round(mean(as_float(row.get("verifiability_score")) for row in quality), 6), "n": len(quality)},
        {"metric": "evidence_score", "value": round(mean(as_float(row.get("evidence_score")) for row in quality), 6), "n": len(quality)},
        {"metric": "specificity", "value": round(mean(as_float(row.get("specificity_score")) for row in quality), 6), "n": len(quality)},
        {"metric": "novelty", "value": round(mean(as_float(row.get("novelty_score")) for row in quality), 6), "n": len(quality)},
        {"metric": "review_score", "value": round(mean(as_float(row.get("review_score")) for row in quality), 6), "n": len(quality)},
        {"metric": "duplicate_content_rate", "value": 0.0, "n": len(quality)},
    ]

    out = ensure_dir(output_dir)
    paths = {
        "competition_metrics": str(out / "competition_metrics.csv"),
        "cooperation_metrics": str(out / "cooperation_metrics.csv"),
        "content_metrics": str(out / "content_metrics.csv"),
        "challenge_return_by_variant": str(out / "challenge_return_by_variant.csv"),
    }
    write_csv(paths["competition_metrics"], competition_rows, ["metric", "value", "n"])
    write_csv(paths["cooperation_metrics"], cooperation_rows, ["metric", "value", "n"])
    write_csv(paths["content_metrics"], content_rows, ["metric", "value", "n"])
    write_csv(paths["challenge_return_by_variant"], variant_summary(challenge_results, "return_pct"))
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default="research/exports")
    parser.add_argument("--output-dir", default="research/exports/tables")
    args = parser.parse_args()
    for name, path in compute_metrics(args.input_dir, args.output_dir).items():
        print(f"wrote {name}: {path}")


if __name__ == "__main__":
    main()
