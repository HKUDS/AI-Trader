"""Generate paper figures from exported research CSVs."""

from __future__ import annotations

import argparse
import html
import math
from collections import Counter
from pathlib import Path

from research_common import as_float, ensure_dir, read_csv


COLORS = ["#2563eb", "#16a34a", "#dc2626", "#7c3aed", "#ea580c", "#0891b2", "#4b5563", "#be123c"]


def svg_text(x: int, y: int, text: str, size: int = 18, weight: int = 400) -> str:
    return f'<text x="{x}" y="{y}" font-size="{size}" font-family="Arial" font-weight="{weight}" fill="#0f172a">{html.escape(text)}</text>'


def bar_chart(values: list[tuple[str, float]], *, x: int = 60, y: int = 120, width: int = 460, height: int = 340) -> str:
    if not values:
        values = [("none", 0.0)]
    max_value = max([value for _label, value in values] + [1.0])
    bar_gap = 12
    bar_width = max(18, (width - bar_gap * (len(values) - 1)) / max(len(values), 1))
    parts = []
    for idx, (label, value) in enumerate(values):
        bar_height = 0 if max_value == 0 else (value / max_value) * height
        bx = x + idx * (bar_width + bar_gap)
        by = y + height - bar_height
        parts.append(f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" fill="{COLORS[idx % len(COLORS)]}"/>')
        parts.append(svg_text(int(bx), y + height + 28, str(label)[:16], 13))
        parts.append(svg_text(int(bx), int(by) - 8, f"{value:.2f}", 12))
    parts.append(f'<line x1="{x}" y1="{y + height}" x2="{x + width}" y2="{y + height}" stroke="#94a3b8"/>')
    return "\n".join(parts)


def line_chart(values: list[float], *, x: int = 620, y: int = 120, width: int = 500, height: int = 340) -> str:
    if not values:
        values = [0.0]
    min_value = min(values)
    max_value = max(values)
    span = max(max_value - min_value, 1.0)
    points = []
    for idx, value in enumerate(values):
        px = x + (idx / max(len(values) - 1, 1)) * width
        py = y + height - ((value - min_value) / span) * height
        points.append(f"{px:.2f},{py:.2f}")
    circles = "".join(f'<circle cx="{point.split(",")[0]}" cy="{point.split(",")[1]}" r="4" fill="#2563eb"/>' for point in points)
    return (
        f'<polyline points="{" ".join(points)}" fill="none" stroke="#2563eb" stroke-width="3"/>'
        f"{circles}"
        f'<line x1="{x}" y1="{y + height}" x2="{x + width}" y2="{y + height}" stroke="#94a3b8"/>'
        f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y + height}" stroke="#94a3b8"/>'
    )


def network_chart(edges: list[dict], *, x: int = 80, y: int = 120, width: int = 980, height: int = 440) -> str:
    nodes = sorted({row.get("source_agent_hash") or row.get("source_agent_id") for row in edges} | {row.get("target_agent_hash") or row.get("target_agent_id") for row in edges})
    nodes = [node for node in nodes if node][:16]
    if not nodes:
        nodes = ["agent_a", "agent_b"]
    radius = min(width, height) / 2 - 40
    cx = x + width / 2
    cy = y + height / 2
    positions = {}
    for idx, node in enumerate(nodes):
        angle = 2 * math.pi * idx / len(nodes)
        positions[node] = (cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)
    parts = []
    for row in edges[:80]:
        source = row.get("source_agent_hash") or row.get("source_agent_id")
        target = row.get("target_agent_hash") or row.get("target_agent_id")
        if source in positions and target in positions:
            sx, sy = positions[source]
            tx, ty = positions[target]
            parts.append(f'<line x1="{sx:.2f}" y1="{sy:.2f}" x2="{tx:.2f}" y2="{ty:.2f}" stroke="#94a3b8" stroke-opacity="0.55"/>')
    for idx, node in enumerate(nodes):
        nx, ny = positions[node]
        parts.append(f'<circle cx="{nx:.2f}" cy="{ny:.2f}" r="13" fill="{COLORS[idx % len(COLORS)]}"/>')
        parts.append(svg_text(int(nx + 16), int(ny + 4), str(node)[7:17] if str(node).startswith("sha256:") else str(node)[:10], 12))
    return "\n".join(parts)


def write_figure(path: Path, title: str, chart: str, notes: list[str]) -> None:
    note_body = "".join(svg_text(60, 590 + idx * 24, note, 15) for idx, note in enumerate(notes[:4]))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720">
<rect width="1200" height="720" fill="#f8fafc"/>
<text x="40" y="52" font-size="30" font-family="Arial" font-weight="700" fill="#0f172a">{html.escape(title)}</text>
{chart}
{note_body}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def generate(input_dir: str, tables_dir: str, output_dir: str) -> dict[str, str]:
    out = ensure_dir(output_dir)
    agents = read_csv(f"{input_dir}/agents.csv")
    signals = read_csv(f"{input_dir}/signals.csv")
    challenges = read_csv(f"{input_dir}/challenges.csv")
    challenge_results = read_csv(f"{input_dir}/challenge_results.csv")
    quality_scores = read_csv(f"{input_dir}/quality_scores.csv")
    edges = read_csv(f"{input_dir}/network_edges.csv")
    team_results = read_csv(f"{input_dir}/team_results.csv")
    rq = read_csv(f"{tables_dir}/rq_hypothesis_metrics.csv")

    market_counts = Counter(row.get("market") or "unknown" for row in signals)
    edge_counts = Counter(row.get("edge_type") or "unknown" for row in edges)
    post_counts = Counter(row.get("agent_hash") or row.get("agent_id") or "unknown" for row in signals)
    variants = Counter(row.get("variant_key") or "unassigned" for row in rq)
    returns = [as_float(row.get("return_pct")) for row in challenge_results]
    drawdowns = [as_float(row.get("max_drawdown")) for row in challenge_results]
    quality_by_metric = [
        ("verify", sum(as_float(r.get("verifiability_score")) for r in quality_scores) / max(len(quality_scores), 1)),
        ("evidence", sum(as_float(r.get("evidence_score")) for r in quality_scores) / max(len(quality_scores), 1)),
        ("specific", sum(as_float(r.get("specificity_score")) for r in quality_scores) / max(len(quality_scores), 1)),
        ("novelty", sum(as_float(r.get("novelty_score")) for r in quality_scores) / max(len(quality_scores), 1)),
        ("review", sum(as_float(r.get("review_score")) for r in quality_scores) / max(len(quality_scores), 1)),
    ]
    team_scores = [(row.get("team_key") or str(idx + 1), as_float(row.get("final_score"))) for idx, row in enumerate(team_results[:12])]
    consensus = [as_float(row.get("consensus_gain")) for row in team_results]
    best_agent = [as_float(row.get("final_score")) for row in challenge_results]
    figures = {
        "figure_01_competition_cooperation_loop.svg": ("Figure 1: Platform Competition/Cooperation Loop", bar_chart([
            ("agents", len(agents)), ("signals", len(signals)), ("challenges", len(challenges)), ("edges", len(edges))
        ]), [
            f"agents: {len(agents)}",
            f"signals: {len(signals)}",
            f"challenges: {len(challenges)}",
            f"network edges: {len(edges)}",
        ]),
        "figure_02_agent_behavior_long_tail.svg": ("Figure 2: Agent Behavior Long Tail", bar_chart([(label, count) for label, count in post_counts.most_common(12)]), [
            f"top markets: {dict(market_counts.most_common(6))}",
            f"agent count: {len(agents)}",
        ]),
        "figure_03_experiment_groups_timeline.svg": ("Figure 3: Experiment Groups and Timeline", bar_chart([(label, count) for label, count in variants.most_common(10)]), [
            f"analysis rows: {len(rq)}",
            f"challenge windows: {len(challenges)}",
        ]),
        "figure_04_competition_return_drawdown.svg": ("Figure 4: Competition Effects", line_chart(returns) + line_chart(drawdowns, x=620, y=120), [
            f"mean return pct: {sum(as_float(r.get('return_pct')) for r in challenge_results) / max(len(challenge_results), 1):.4f}",
            f"mean drawdown: {sum(as_float(r.get('max_drawdown')) for r in challenge_results) / max(len(challenge_results), 1):.4f}",
        ]),
        "figure_05_cooperation_content_quality.svg": ("Figure 5: Cooperation and Content Quality", bar_chart(quality_by_metric), [
            f"quality scored signals: {len(quality_scores)}",
            f"mean quality: {sum(as_float(r.get('overall_score')) for r in quality_scores) / max(len(quality_scores), 1):.4f}",
        ]),
        "figure_06_agent_interaction_graph.svg": ("Figure 6: Agent Interaction Graph", network_chart(edges), [
            f"edge types: {dict(edge_counts.most_common(8))}",
        ]),
        "figure_07_team_diversity_performance.svg": ("Figure 7: Team Diversity and Performance", bar_chart(team_scores), [
            f"team results: {len(team_results)}",
            f"mean final score: {sum(as_float(r.get('final_score')) for r in team_results) / max(len(team_results), 1):.4f}",
        ]),
        "figure_08_consensus_vs_best_agent.svg": ("Figure 8: Group Consensus vs Best Agent", line_chart(consensus) + line_chart(best_agent, x=620, y=120), [
            f"mean consensus gain: {sum(as_float(r.get('consensus_gain')) for r in team_results) / max(len(team_results), 1):.4f}",
            f"best challenge score: {max([as_float(r.get('final_score')) for r in challenge_results] or [0]):.4f}",
        ]),
    }
    written = {}
    for filename, (title, chart, lines) in figures.items():
        path = out / filename
        write_figure(path, title, chart, lines)
        written[filename] = str(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default="research/exports")
    parser.add_argument("--tables-dir", default="research/exports/tables")
    parser.add_argument("--output-dir", default="research/exports/figures")
    args = parser.parse_args()
    for name, path in generate(args.input_dir, args.tables_dir, args.output_dir).items():
        print(f"wrote {name}: {path}")


if __name__ == "__main__":
    main()
