#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draw a compact violin plot for tool counts in final projects."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path("/home/lls/MCP_Analyze")
PROJECT_FILE = ROOT / "tool_analyzer" / "final_success_projects.txt"
DETAILS_FILE = ROOT / "tool_analyzer" / "final_success_tool_count_call_graph_source_details.json"
OUTPUT_DIR = ROOT / "picture"
OUTPUT_PNG = OUTPUT_DIR / "final_success_tool_count_violin.png"
OUTPUT_PDF = OUTPUT_DIR / "final_success_tool_count_violin.pdf"

VIOLIN_FILL = "#B9D9CF"
VIOLIN_EDGE = "#456E66"
POINT_COLOR = "#3E625C"
TOP_POINT_COLOR = "#294741"
STAT_COLOR = "#355A53"


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


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8", errors="ignore"))


def collect_tool_counts() -> np.ndarray:
    projects = read_projects(PROJECT_FILE)
    project_set = set(projects)
    if len(projects) != len(project_set):
        raise ValueError(f"Duplicate projects in {PROJECT_FILE}")

    details = read_json(DETAILS_FILE)
    counts_by_project = {
        row.get("project"): int(row.get("count") or 0)
        for row in details
        if isinstance(row, dict) and row.get("project") in project_set
    }

    missing = sorted(project_set - set(counts_by_project))
    if missing:
        raise ValueError(f"Missing tool-count rows for {len(missing)} projects")

    values = np.asarray([counts_by_project[p] for p in projects], dtype=float)
    if values.size == 0:
        raise ValueError("No tool-count values found")

    return values


def format_tool_tick(value: int) -> str:
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
    y_plot = np.log10(y_value) + dy
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
    log_values = np.log10(values)
    median = np.percentile(values, 50)
    p95 = np.percentile(values, 95)
    mean = float(np.mean(values))
    total_tools = int(np.sum(values))

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
        np.log10(top_values),
        s=14,
        color=TOP_POINT_COLOR,
        edgecolor="white",
        linewidth=0.25,
        alpha=0.90,
        zorder=5,
    )

    max_value = float(values.max())
    upper_limit = 250 if max_value <= 250 else max_value * 1.08
    tick_values = [1, 3, 10, 30, 100, 250]
    tick_values = [tick for tick in tick_values if tick <= upper_limit]
    if tick_values[-1] < max_value:
        tick_values.append(int(np.ceil(upper_limit)))
    ax.set_yticks(np.log10(tick_values))
    ax.set_yticklabels([format_tool_tick(v) for v in tick_values])
    ax.set_ylim(np.log10(1), np.log10(max(upper_limit, tick_values[-1])))

    ax.set_xlim(0.43, 1.60)
    ax.set_xticks([1])
    ax.set_xticklabels(["Tool Count"], fontsize=11)
    ax.set_ylabel("Tools per MCP (log scale)", labelpad=2)
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
        f"{len(values):,} MCPs | {total_tools:,} tools",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=9.6,
        color="#303030",
    )

    mark_stat(ax, 1.30, median, "s", f"{median:.0f}", dy=0.000, size=24)
    mark_stat(
        ax,
        1.25,
        mean,
        "D",
        f"{mean:.2f}",
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
        dy=-0.030,
        size=38,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PNG, dpi=600)
    fig.savefig(OUTPUT_PDF)
    plt.close(fig)


def main() -> None:
    values = collect_tool_counts()
    draw_violin(values)

    print(f"[INFO] projects: {len(values)}")
    print(f"[INFO] total tools: {int(values.sum())}")
    print(f"[INFO] min/median/mean/max: {values.min():.0f} / {np.median(values):.0f} / {values.mean():.2f} / {values.max():.0f}")
    print(f"[DONE] saved PNG: {OUTPUT_PNG}")
    print(f"[DONE] saved PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
