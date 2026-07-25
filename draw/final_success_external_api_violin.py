#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draw a compact violin plot for external API call counts in final projects."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PROJECT_FILE = ROOT / "tool_analyzer" / "all_projects.txt"
API_CACHE_FILE = ROOT / "tool_analyzer" / "api_cache.json"
RESULTS_DIR = ROOT / "results"
OUTPUT_DIR = ROOT / "picture"
OUTPUT_PNG = OUTPUT_DIR / "final_success_external_api_count_violin.png"
OUTPUT_PDF = OUTPUT_DIR / "final_success_external_api_count_violin.pdf"
STATS_JSON = ROOT / "tool_analyzer" / "final_success_external_api_stats.json"
PER_PROJECT_TSV = ROOT / "tool_analyzer" / "final_success_external_api_per_project.tsv"

VIOLIN_FILL = "#E7C6A5"
VIOLIN_EDGE = "#8A6546"
POINT_COLOR = "#7A5A3D"
TOP_POINT_COLOR = "#5A412D"
STAT_COLOR = "#6F5237"


plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 11,
    "axes.labelsize": 11,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "axes.linewidth": 0.75,
})


def read_projects(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip()
    ]


def project_type(call_graph: dict) -> str:
    return "TypeScript" if any(
        isinstance(node, dict)
        and str(node.get("path", "")).endswith((".ts", ".tsx", ".js", ".jsx"))
        for node in call_graph.values()
    ) else "Python"


def node_lang(node: dict, fallback: str) -> str:
    path = str(node.get("path", ""))
    if any(ext in path for ext in (".ts:", ".tsx:", ".js:", ".jsx:")) or path.endswith(
        (".ts", ".tsx", ".js", ".jsx")
    ):
        return "TypeScript"
    if ".py:" in path or path.endswith(".py"):
        return "Python"
    return fallback


def collect_external_api_counts() -> tuple[np.ndarray, dict]:
    projects = read_projects(PROJECT_FILE)
    project_set = set(projects)
    if len(projects) != len(project_set):
        raise ValueError(f"Duplicate projects in {PROJECT_FILE}")

    counts_by_project = dict.fromkeys(projects, 0)
    api_cache = json.loads(API_CACHE_FILE.read_text(encoding="utf-8", errors="ignore"))
    unique_names: set[str] = set()
    unique_lang_api: set[tuple[str, str]] = set()
    by_language = {"Python": 0, "TypeScript": 0}

    for project in projects:
        graph_path = RESULTS_DIR / project / "call_graph_labeled.json"
        call_graph = json.loads(graph_path.read_text(encoding="utf-8", errors="ignore"))
        fallback = project_type(call_graph)

        for node in call_graph.values():
            if not isinstance(node, dict):
                continue
            api_name = node.get("api_name")
            if not api_name:
                continue

            lang = node_lang(node, fallback)
            item = api_cache.get(lang, {}).get(api_name)
            if not isinstance(item, dict) or item.get("external_api") is not True:
                continue

            counts_by_project[project] += 1
            by_language[lang] = by_language.get(lang, 0) + 1
            unique_names.add(api_name)
            unique_lang_api.add((lang, api_name))

    values = np.asarray([counts_by_project[p] for p in projects], dtype=float)
    stats = {
        "project_file": str(PROJECT_FILE),
        "project_count": len(projects),
        "api_cache": str(API_CACHE_FILE),
        "results_dir": str(RESULTS_DIR),
        "counting_policy": (
            "call graph node occurrence where node (language, api_name) is external_api=true "
            "in current api_cache.json"
        ),
        "external_api_occurrences_in_projects": int(values.sum()),
        "unique_external_api_name_count_used": len(unique_names),
        "unique_external_api_count_lang_api_used": len(unique_lang_api),
        "projects_with_external_api_count": int(np.count_nonzero(values)),
        "projects_without_external_api_count": int(len(values) - np.count_nonzero(values)),
        "by_language_occurrences": by_language,
    }
    PER_PROJECT_TSV.write_text(
        "project\texternal_api_count\n"
        + "\n".join(f"{project}\t{counts_by_project[project]}" for project in projects)
        + "\n",
        encoding="utf-8",
    )
    STATS_JSON.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return values, stats


def format_tick(value: int) -> str:
    if value >= 1000:
        return f"{value / 1000:.0f}k"
    return str(value)


def mark_stat(
    ax: plt.Axes,
    x: float,
    y_value: float,
    marker: str,
    text: str,
    line_len: float = 0.042,
    text_gap: float = 0.014,
    text_dy: float = 0.0,
    dy: float = 0.0,
    color: str = STAT_COLOR,
    size: float = 30,
) -> None:
    y_plot = np.log10(y_value + 1) + dy
    ax.scatter(
        [x],
        [y_plot],
        s=size,
        marker=marker,
        color=color,
        edgecolor="white",
        linewidth=0.25,
        zorder=7,
    )
    ax.plot(
        [x + 0.018, x + 0.018 + line_len],
        [y_plot, y_plot],
        color="#555555",
        linewidth=0.55,
        solid_capstyle="round",
        zorder=7,
    )
    ax.text(
        x + 0.018 + line_len + text_gap,
        y_plot + text_dy,
        text,
        ha="left",
        va="center",
        fontsize=11,
        color="#2F2F2F",
        zorder=8,
    )


def draw_violin(values: np.ndarray) -> None:
    log_values = np.log10(values + 1)
    median = float(np.percentile(values, 50))
    p95 = float(np.percentile(values, 95))
    mean = float(np.mean(values))
    total_calls = int(np.sum(values))

    fig, ax = plt.subplots(figsize=(2.55, 4.15))
    fig.subplots_adjust(left=0.31, right=0.965, bottom=0.095, top=0.90)

    violin = ax.violinplot(
        [log_values],
        positions=[1],
        widths=0.68,
        showmeans=False,
        showmedians=False,
        showextrema=False,
        bw_method=0.22,
    )
    for body in violin["bodies"]:
        body.set_facecolor(VIOLIN_FILL)
        body.set_edgecolor(VIOLIN_EDGE)
        body.set_alpha(0.96)
        body.set_linewidth(0.85)

    rng = np.random.default_rng(20260624)
    jitter = rng.normal(0, 0.055, size=len(log_values))
    jitter = np.clip(jitter, -0.16, 0.16)
    ax.scatter(
        1 + jitter,
        log_values,
        s=4.5,
        color=POINT_COLOR,
        alpha=0.12,
        linewidths=0,
        zorder=2,
    )

    ax.boxplot(
        [log_values],
        positions=[1],
        widths=0.18,
        patch_artist=True,
        showfliers=False,
        boxprops={
            "facecolor": "white",
            "edgecolor": "#3F3F3F",
            "linewidth": 0.85,
        },
        medianprops={"color": "#2B2B2B", "linewidth": 1.0},
        whiskerprops={"color": "#3F3F3F", "linewidth": 0.75},
        capprops={"color": "#3F3F3F", "linewidth": 0.75},
        zorder=4,
    )

    top_values = np.sort(values)[-8:]
    top_x = 1 + rng.uniform(-0.045, 0.045, size=len(top_values))
    ax.scatter(
        top_x,
        np.log10(top_values + 1),
        s=14,
        color=TOP_POINT_COLOR,
        edgecolor="white",
        linewidth=0.25,
        alpha=0.90,
        zorder=5,
    )

    tick_values = [0, 2, 8, 32, 128, 512]
    ax.set_yticks(np.log10(np.asarray(tick_values, dtype=float) + 1))
    ax.set_yticklabels([format_tick(v) for v in tick_values])
    ax.set_ylim(np.log10(1), np.log10(values.max() * 1.15 + 1))

    ax.set_xlim(0.43, 1.68)
    ax.set_xticks([1])
    ax.set_xticklabels(["External API Calls"], fontsize=11)
    ax.set_ylabel("Calls per MCP (log scale)", labelpad=2)
    ax.set_xlabel("")

    ax.grid(axis="y", linestyle="--", linewidth=0.42, alpha=0.20)
    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", length=2.0, width=0.55, pad=2)

    for side in ["left", "right", "top", "bottom"]:
        ax.spines[side].set_visible(True)
        ax.spines[side].set_linewidth(0.75)
        ax.spines[side].set_color("#3D3D3D")

    ax.text(
        0.48,
        1.020,
        f"{len(values):,} MCPs | {total_calls:,} calls",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=9.6,
        color="#303030",
    )

    mark_stat(ax, 1.32, median, "s", f"{median:.0f}", dy=0.000, size=24)
    mark_stat(
        ax,
        1.18,
        mean,
        "D",
        f"{mean:.2f}",
        line_len=0.050,
        text_gap=0.050,
        text_dy=-0.010,
        dy=-0.026,
        size=26,
    )
    mark_stat(ax, 1.25, p95, "^", f"{p95:.0f}", text_dy=0.006, size=42)
    mark_stat(
        ax,
        1.12,
        float(values.max()),
        "P",
        f"{values.max():.0f}",
        line_len=0.040,
        text_gap=0.012,
        dy=-0.045,
        size=38,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PNG, dpi=600)
    fig.savefig(OUTPUT_PDF)
    plt.close(fig)


def main() -> None:
    values, stats = collect_external_api_counts()
    draw_violin(values)

    print(f"[INFO] projects: {len(values)}")
    print(f"[INFO] total external API calls: {int(values.sum())}")
    print(f"[INFO] unique external API names used: {stats['unique_external_api_name_count_used']}")
    print(
        "[INFO] min/median/mean/p95/max: "
        f"{values.min():.0f} / {np.median(values):.0f} / "
        f"{values.mean():.2f} / {np.percentile(values, 95):.0f} / {values.max():.0f}"
    )
    print(f"[DONE] saved PNG: {OUTPUT_PNG}")
    print(f"[DONE] saved PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
