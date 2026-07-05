#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draw category distribution for DeepSeek-Qwen shared hidden API cache entries."""

from __future__ import annotations

import csv
import json
import math
import os
import textwrap
from collections import Counter
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt


ROOT = Path("/home/lls/MCP_Analyze")
INTERSECTION_CSV = ROOT / "tool_analyzer" / "deepseek_qwen_hidden_api_cache_entry_intersection.csv"

OUTPUT_DIR = ROOT / "picture"
OUTPUT_PNG = OUTPUT_DIR / "deepseek_qwen_shared_hidden_api_category_pie.png"
OUTPUT_PDF = OUTPUT_DIR / "deepseek_qwen_shared_hidden_api_category_pie.pdf"
OUTPUT_SVG = OUTPUT_DIR / "deepseek_qwen_shared_hidden_api_category_pie.svg"

STATS_JSON = ROOT / "tool_analyzer" / "deepseek_qwen_shared_hidden_api_category_stats.json"
STATS_CSV = ROOT / "tool_analyzer" / "deepseek_qwen_shared_hidden_api_category_stats.csv"


COLORS = [
    "#F7C98E",
    "#EE9C98",
    "#FBE6A3",
    "#C9D5EE",
    "#DCEED0",
    "#BFE7EE",
    "#D7A6E6",
    "#F6C5A6",
    "#CBEBDD",
    "#E6D8C8",
    "#CED7F1",
]

FIGURE_LABEL_FONT_SIZE = 8
FONT_SERIF_FAMILIES = ["Times New Roman", "Tinos", "Times", "DejaVu Serif"]
CALLOUT_CATEGORY_COUNT = 2

PLOT_ORDER = [
    "System Command Execution",
    "Database Management",
    "Project Management Services",
    "Browser Automation and Web Interaction",
    "Financial and Blockchain Services",
    "File System Operations",
    "Specialized Domain Data Services",
    "Cloud Infrastructure Management",
    "AI and Machine Learning Services",
    "Identity and Access Management",
]

VALID_CATEGORIES = set(PLOT_ORDER)

DISPLAY_LABELS = {
    "Project Management Services": "Project Manage Services",
    "Identity and Access Management": "Identity and Access Manage",
}

LABEL_LINE_BREAKS = {
    "Project Manage Services": "Project Manage\nServices",
    "Identity and Access Manage": "Identity and\nAccess Manage",
    "Browser Automation and Web Interaction": "Browser Automation\nand Web Interaction",
    "Financial and Blockchain Services": "Financial and\nBlockchain Services",
    "Cloud Infrastructure Management": "Cloud Infrastructure\nManagement",
    "AI and Machine Learning Services": "AI and Machine\nLearning Services",
}

LEGEND_LABELS = {
    "System Command Execution": "System Command Execution",
    "Database Management": "Database Management",
    "Browser Automation and Web Interaction": "Browser Automation/Web",
    "File System Operations": "File System Operations",
    "Specialized Domain Data Services": "Domain Data Services",
    "Cloud Infrastructure Management": "Cloud Infrastructure",
    "Project Management Services": "Project Management",
    "Financial and Blockchain Services": "Financial/Blockchain",
    "AI and Machine Learning Services": "AI/ML Services",
    "Identity and Access Management": "IAM",
}


plt.rcParams.update({
    "font.family": "serif",
    "font.serif": FONT_SERIF_FAMILIES,
    "font.size": FIGURE_LABEL_FONT_SIZE,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "svg.fonttype": "none",
})


def format_label(label: str) -> str:
    display_label = DISPLAY_LABELS.get(label, label)
    if display_label in LABEL_LINE_BREAKS:
        return LABEL_LINE_BREAKS[display_label]
    return textwrap.fill(display_label, width=18, break_long_words=False)


def format_minor_entry(label: str, value: int, percent: float) -> str:
    return f"{format_label(label)}\n{value:,} ({percent:.1f}%)"


def build_plot_rows(counts: Counter[str]) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    base_rows = counts.most_common()
    callout_rows = sorted(base_rows, key=lambda item: (item[1], item[0]))[:CALLOUT_CATEGORY_COUNT]
    by_category = dict(base_rows)
    plot_rows = [
        (category, by_category[category])
        for category in PLOT_ORDER
        if category in by_category
    ]
    plot_rows.extend(row for row in base_rows if row[0] not in PLOT_ORDER)
    return plot_rows, callout_rows


def load_shared_category_counts() -> tuple[Counter[str], dict]:
    counts: Counter[str] = Counter()
    seen_entries: set[str] = set()
    missing_category_records = []
    unexpected_category_records = []

    with INTERSECTION_CSV.open("r", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            cache_entry_id = row.get("cache_entry_id") or ""
            if not cache_entry_id or cache_entry_id in seen_entries:
                continue
            seen_entries.add(cache_entry_id)
            category = (row.get("category") or "").strip()
            if not category:
                missing_category_records.append({
                    "cache_entry_id": cache_entry_id,
                    "language": row.get("language") or "",
                    "api_name": row.get("api_name") or "",
                })
                continue
            if category not in VALID_CATEGORIES:
                unexpected_category_records.append({
                    "cache_entry_id": cache_entry_id,
                    "language": row.get("language") or "",
                    "api_name": row.get("api_name") or "",
                    "category": category,
                })
                continue
            counts[category] += 1

    if missing_category_records or unexpected_category_records:
        issue_payload = {
            "source_intersection_csv": str(INTERSECTION_CSV),
            "missing_category_entries": len(missing_category_records),
            "missing_category_examples": missing_category_records[:20],
            "unexpected_category_entries": len(unexpected_category_records),
            "unexpected_category_examples": unexpected_category_records[:20],
        }
        raise RuntimeError(
            "External API category plot requires every shared external API cache entry "
            f"to have one of the formal categories: {json.dumps(issue_payload, ensure_ascii=False)}"
        )

    metadata = {
        "source_intersection_csv": str(INTERSECTION_CSV),
        "unique_definition": (
            "A unique external API is one concrete api_cache.json entry with external_api=true, "
            "identified as language::api_name. The plotted set is the DeepSeek V4 Pro and Qwen "
            "3.7 Plus shared external-API set from the Venn diagram."
        ),
        "total_shared_cache_entries": len(seen_entries),
        "filter": "Only api_cache.json entries with external_api=true are counted.",
        "category_source": "api_cache.json category field; no permission fallback or pseudo-category is used.",
        "missing_api_category_entries": 0,
        "unexpected_api_category_entries": 0,
    }
    return counts, metadata


def write_stats(counts: Counter[str], metadata: dict) -> None:
    total = sum(counts.values())
    plot_rows, other_rows = build_plot_rows(counts)
    rows = [
        {
            "category": category,
            "shared_unique_api_cache_entries": count,
            "percent": count / total * 100 if total else 0.0,
        }
        for category, count in counts.most_common()
    ]

    payload = {
        **metadata,
        "total_shared_unique_api_cache_entries": total,
        "plot_policy": (
            "All plotted slices are shared hidden external APIs and use the formal api_cache.json "
            "category field directly."
        ),
        "plot_category_counts": [
            {
                "category": category,
                "shared_unique_api_cache_entries": count,
                "percent": count / total * 100 if total else 0.0,
            }
            for category, count in plot_rows
        ],
        "callout_categories": [
            {
                "category": category,
                "shared_unique_api_cache_entries": count,
                "percent": count / total * 100 if total else 0.0,
            }
            for category, count in other_rows
        ],
        "category_counts": rows,
    }

    STATS_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with STATS_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["category", "shared_unique_api_cache_entries", "percent"],
        )
        writer.writeheader()
        writer.writerows(rows)


def draw_pie(counts: Counter[str]) -> None:
    total = sum(counts.values())
    plot_rows, _ = build_plot_rows(counts)
    base_rows = counts.most_common()
    labels = [category for category, _ in plot_rows]
    values = [count for _, count in plot_rows]
    percents = [value / total * 100 if total else 0.0 for value in values]
    color_by_label = {
        category: COLORS[index % len(COLORS)]
        for index, (category, _) in enumerate(base_rows)
    }
    colors = [color_by_label[label] for label in labels]

    fig, ax = plt.subplots(figsize=(4.45, 3.0))
    fig.subplots_adjust(left=0.01, right=0.99, top=0.98, bottom=0.03)

    pie_center = (0.0, 0.0)
    pie_radius = 0.78
    wedges, _ = ax.pie(
        values,
        colors=colors,
        startangle=0,
        counterclock=True,
        radius=pie_radius,
        center=pie_center,
        wedgeprops={"linewidth": 0.9, "edgecolor": "white"},
    )

    for wedge, label, value, percent in zip(wedges, labels, values, percents):
        angle = math.radians((wedge.theta1 + wedge.theta2) / 2)
        if percent < 3.0:
            continue
        if percent >= 10.0:
            data_radius = pie_radius * 0.52
            data_fontsize = 7.4
            text = f"{value:,}\n{percent:.1f}%"
        elif percent >= 7.0:
            data_radius = pie_radius * 0.64
            data_fontsize = 6.8
            text = f"{value:,}\n{percent:.1f}%"
        else:
            data_radius = pie_radius * 0.73
            data_fontsize = 6.3
            text = f"{value:,}\n{percent:.1f}%"

        data_text = ax.text(
            pie_center[0] + math.cos(angle) * data_radius,
            pie_center[1] + math.sin(angle) * data_radius,
            text,
            ha="center",
            va="center",
            fontsize=data_fontsize,
            color="#000000",
            linespacing=0.88,
        )
        # Keep text as editable/vector text in PDF/SVG outputs.

    label_positions = {
        "System Command Execution": (0.54, 0.68, "left"),
        "Database Management": (-0.70, 0.43, "right"),
        "Project Management Services": (-0.82, -0.13, "right"),
        "Browser Automation and Web Interaction": (-0.66, -0.49, "right"),
        "Financial and Blockchain Services": (-0.54, -0.83, "center"),
        "File System Operations": (0.01, -0.85, "center"),
        "Specialized Domain Data Services": (0.40, -0.73, "left"),
        "Cloud Infrastructure Management": (0.68, -0.43, "left"),
        "AI and Machine Learning Services": (0.80, -0.12, "left"),
        "Identity and Access Management": (0.85, 0.16, "left"),
    }
    label_font = 8.2
    small_label_font = 7.4
    wedge_by_label = dict(zip(labels, wedges))
    value_by_label = dict(zip(labels, values))
    percent_by_label = dict(zip(labels, percents))

    for label in labels:
        if label not in label_positions:
            continue
        x, y, ha = label_positions[label]
        label_text = format_label(label)
        is_small_callout = percent_by_label[label] < 1.0
        number_text = None
        if is_small_callout:
            number_text = f"{value_by_label[label]:,} ({percent_by_label[label]:.1f}%)"
            if label != "Identity and Access Management":
                label_text = f"{label_text}\n{number_text}"

        if is_small_callout:
            wedge = wedge_by_label[label]
            angle = math.radians((wedge.theta1 + wedge.theta2) / 2)
            start_x = pie_center[0] + math.cos(angle) * pie_radius * 1.01
            start_y = pie_center[1] + math.sin(angle) * pie_radius * 1.01
            if label == "Identity and Access Management":
                end_x = x - 0.025
                end_y = y - 0.055
            else:
                end_x = x - 0.01 if ha == "left" else x + 0.01
                end_y = y - 0.01 if ha == "left" else y
            ax.plot(
                [start_x, end_x],
                [start_y, end_y],
                color="#000000",
                linewidth=0.38,
                solid_capstyle="round",
            )

        text_y = y + 0.028 if label == "Identity and Access Management" else y
        ax.text(
            x,
            text_y,
            label_text,
            ha=ha,
            va="center",
            fontsize=small_label_font if is_small_callout else label_font,
            color="#000000",
            linespacing=0.84,
            multialignment="left" if ha == "left" else "right" if ha == "right" else "center",
        )
        if label == "Identity and Access Management" and number_text:
            ax.text(
                x,
                y - 0.075,
                number_text,
                ha=ha,
                va="center",
                fontsize=small_label_font,
                color="#000000",
            )

    ax.set_aspect("equal")
    ax.set_xlim(-1.08, 1.18)
    ax.set_ylim(-1.00, 0.96)
    ax.axis("off")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PNG, dpi=600, bbox_inches="tight", pad_inches=0.03)
    fig.savefig(OUTPUT_PDF, bbox_inches="tight", pad_inches=0.03)
    fig.savefig(OUTPUT_SVG, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


def main() -> None:
    counts, metadata = load_shared_category_counts()
    write_stats(counts, metadata)
    draw_pie(counts)
    print(f"[INFO] shared unique API cache entries: {sum(counts.values())}")
    print(f"[INFO] source intersection CSV: {INTERSECTION_CSV}")
    print(f"[DONE] saved PNG: {OUTPUT_PNG}")
    print(f"[DONE] saved PDF: {OUTPUT_PDF}")
    print(f"[DONE] saved SVG: {OUTPUT_SVG}")
    print(f"[DONE] saved stats: {STATS_JSON}")
    print(f"[DONE] saved CSV: {STATS_CSV}")


if __name__ == "__main__":
    main()
