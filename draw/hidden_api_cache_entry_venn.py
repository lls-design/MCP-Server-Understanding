#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draw a Venn-style comparison of DeepSeek and Qwen hidden external API cache entries."""

from __future__ import annotations

import csv
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, PathPatch
from matplotlib.path import Path as MplPath


ROOT = Path("/home/lls/MCP_Analyze")
CACHE_FILE = ROOT / "tool_analyzer" / "api_cache.json"
DEEPSEEK_HIDDEN_TABLE = ROOT / "tool_analyzer" / "permission_transparency_hidden_table.csv"
QWEN_HIDDEN_TABLE = ROOT / "tool_analyzer" / "permission_transparency_qwen_hidden_table.csv"

OUTPUT_DIR = ROOT / "picture"
OUTPUT_PNG = OUTPUT_DIR / "deepseek_qwen_hidden_api_cache_entry_venn.png"
OUTPUT_PDF = OUTPUT_DIR / "deepseek_qwen_hidden_api_cache_entry_venn.pdf"

STATS_JSON = ROOT / "tool_analyzer" / "deepseek_qwen_hidden_api_cache_entry_venn_stats.json"
INTERSECTION_CSV = ROOT / "tool_analyzer" / "deepseek_qwen_hidden_api_cache_entry_intersection.csv"


plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 8,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def split_apis(text: str) -> list[str]:
    return [item.strip() for item in (text or "").split(";") if item.strip()]


def build_cache_index() -> dict[str, list[dict]]:
    cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    index: dict[str, list[dict]] = defaultdict(list)

    for language, entries in cache.items():
        for api_name, metadata in entries.items():
            projects = set(metadata.get("project") or [])
            index[api_name].append({
                "language": language,
                "api_name": api_name,
                "projects": projects,
                "category": metadata.get("category") or "",
                "external_api": metadata.get("external_api"),
            })

    return index


def select_cache_entries(project: str, api_name: str, cache_index: dict[str, list[dict]]) -> list[dict]:
    candidates = cache_index.get(api_name, [])
    project_matches = [entry for entry in candidates if project in entry["projects"]]
    return project_matches or candidates


def load_hidden_cache_entries(path: Path, cache_index: dict[str, list[dict]]) -> tuple[set[str], dict]:
    entries: set[str] = set()
    entry_details: dict[str, dict] = {}
    ref_counts: Counter[str] = Counter()
    permission_counts: dict[str, Counter] = defaultdict(Counter)
    unresolved_refs = []
    skipped_non_external_refs = []
    multi_entry_refs = 0
    raw_api_refs = 0
    raw_api_names = set()

    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            project = row.get("project") or ""
            permission = row.get("permission") or ""
            for api_name in split_apis(row.get("apis", "")):
                raw_api_refs += 1
                raw_api_names.add(api_name)
                selected = select_cache_entries(project, api_name, cache_index)
                if not selected:
                    unresolved_refs.append({
                        "project": project,
                        "tool": row.get("tool") or "",
                        "permission": permission,
                        "api_name": api_name,
                    })
                    continue

                external_selected = [entry for entry in selected if entry.get("external_api") is True]
                if len(external_selected) > 1:
                    multi_entry_refs += 1
                if len(skipped_non_external_refs) < 20:
                    for entry in selected:
                        if entry.get("external_api") is not True:
                            skipped_non_external_refs.append({
                                "project": project,
                                "tool": row.get("tool") or "",
                                "permission": permission,
                                "api_name": api_name,
                                "cache_entry_id": f"{entry['language']}::{api_name}",
                                "external_api": entry.get("external_api"),
                            })
                            if len(skipped_non_external_refs) >= 20:
                                break

                for entry in external_selected:
                    cache_entry_id = f"{entry['language']}::{api_name}"
                    entries.add(cache_entry_id)
                    ref_counts[cache_entry_id] += 1
                    permission_counts[cache_entry_id][permission] += 1
                    entry_details.setdefault(cache_entry_id, {
                        "cache_entry_id": cache_entry_id,
                        "language": entry["language"],
                        "api_name": api_name,
                        "category": entry.get("category") or "",
                    })

    metadata = {
        "source": str(path),
        "raw_api_refs": raw_api_refs,
        "raw_unique_api_name_strings": len(raw_api_names),
        "external_api_cache_entry_refs": sum(ref_counts.values()),
        "unique_external_api_cache_entries": len(entries),
        "multi_cache_entry_api_refs": multi_entry_refs,
        "unresolved_api_refs": len(unresolved_refs),
        "unresolved_examples": unresolved_refs[:20],
        "skipped_non_external_api_ref_examples": skipped_non_external_refs,
        "ref_counts": dict(ref_counts),
        "permission_counts": {key: dict(value) for key, value in permission_counts.items()},
        "entry_details": entry_details,
    }
    return entries, metadata


def write_intersection_csv(shared: set[str], deepseek_meta: dict, qwen_meta: dict) -> None:
    fields = [
        "cache_entry_id",
        "language",
        "api_name",
        "category",
        "deepseek_refs",
        "qwen_refs",
        "deepseek_permissions",
        "qwen_permissions",
    ]

    rows = []
    for cache_entry_id in sorted(shared):
        detail = qwen_meta["entry_details"].get(cache_entry_id) or deepseek_meta["entry_details"][cache_entry_id]
        deepseek_permissions = deepseek_meta["permission_counts"].get(cache_entry_id, {})
        qwen_permissions = qwen_meta["permission_counts"].get(cache_entry_id, {})
        rows.append({
            "cache_entry_id": cache_entry_id,
            "language": detail["language"],
            "api_name": detail["api_name"],
            "category": detail.get("category", ""),
            "deepseek_refs": deepseek_meta["ref_counts"].get(cache_entry_id, 0),
            "qwen_refs": qwen_meta["ref_counts"].get(cache_entry_id, 0),
            "deepseek_permissions": "; ".join(sorted(deepseek_permissions)),
            "qwen_permissions": "; ".join(sorted(qwen_permissions)),
        })

    with INTERSECTION_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def circle_intersection_area(r1: float, r2: float, distance: float) -> float:
    if distance >= r1 + r2:
        return 0.0
    if distance <= abs(r1 - r2):
        return math.pi * min(r1, r2) ** 2

    alpha = math.acos((distance**2 + r1**2 - r2**2) / (2 * distance * r1))
    beta = math.acos((distance**2 + r2**2 - r1**2) / (2 * distance * r2))
    lens = 0.5 * math.sqrt(
        max(
            0.0,
            (-distance + r1 + r2)
            * (distance + r1 - r2)
            * (distance - r1 + r2)
            * (distance + r1 + r2),
        )
    )
    return r1**2 * alpha + r2**2 * beta - lens


def solve_distance_for_overlap(r1: float, r2: float, target_area: float) -> float:
    low = abs(r1 - r2)
    high = r1 + r2
    max_overlap = math.pi * min(r1, r2) ** 2
    if target_area >= max_overlap:
        return low
    if target_area <= 0:
        return high

    for _ in range(80):
        mid = (low + high) / 2
        area = circle_intersection_area(r1, r2, mid)
        if area > target_area:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def lens_boundaries(c1: tuple[float, float], r1: float, c2: tuple[float, float], r2: float) -> tuple[float, float, float, float]:
    x1, y1 = c1
    x2, y2 = c2
    distance = math.hypot(x2 - x1, y2 - y1)
    a = (r1**2 - r2**2 + distance**2) / (2 * distance)
    h = math.sqrt(max(0.0, r1**2 - a**2))
    xm = x1 + a * (x2 - x1) / distance
    ym = y1 + a * (y2 - y1) / distance
    rx = -(y2 - y1) * (h / distance)
    ry = (x2 - x1) * (h / distance)
    p_top = (xm + rx, ym + ry)
    p_bottom = (xm - rx, ym - ry)
    return p_top[0], p_top[1], p_bottom[0], p_bottom[1]


def arc_points(center: tuple[float, float], radius: float, start: float, end: float, steps: int = 160) -> list[tuple[float, float]]:
    if end < start:
        end += 2 * math.pi
    return [
        (center[0] + radius * math.cos(theta), center[1] + radius * math.sin(theta))
        for theta in [start + (end - start) * i / (steps - 1) for i in range(steps)]
    ]


def polygon_patch(points: list[tuple[float, float]], **kwargs) -> PathPatch:
    vertices = points + [points[0]]
    codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(points) - 1) + [MplPath.CLOSEPOLY]
    return PathPatch(MplPath(vertices, codes), **kwargs)


def add_colored_venn_regions(
    ax,
    deepseek_center: tuple[float, float],
    deepseek_radius: float,
    qwen_center: tuple[float, float],
    qwen_radius: float,
) -> None:
    top_x, top_y, bottom_x, bottom_y = lens_boundaries(
        deepseek_center,
        deepseek_radius,
        qwen_center,
        qwen_radius,
    )
    top = (top_x, top_y)
    bottom = (bottom_x, bottom_y)

    left_top_angle = math.atan2(top_y - deepseek_center[1], top_x - deepseek_center[0])
    left_bottom_angle = math.atan2(bottom_y - deepseek_center[1], bottom_x - deepseek_center[0])
    right_top_angle = math.atan2(top_y - qwen_center[1], top_x - qwen_center[0])
    right_bottom_angle = math.atan2(bottom_y - qwen_center[1], bottom_x - qwen_center[0])

    left_outer = arc_points(deepseek_center, deepseek_radius, left_top_angle, left_bottom_angle)
    right_inner = arc_points(qwen_center, qwen_radius, right_bottom_angle, right_top_angle)
    deepseek_only = left_outer + right_inner

    right_outer = arc_points(qwen_center, qwen_radius, right_bottom_angle, right_top_angle)
    left_inner = arc_points(deepseek_center, deepseek_radius, left_top_angle, left_bottom_angle)
    qwen_only = right_outer + left_inner

    left_lens = arc_points(deepseek_center, deepseek_radius, left_bottom_angle, left_top_angle)
    right_lens = arc_points(qwen_center, qwen_radius, right_top_angle, right_bottom_angle)
    shared = left_lens + right_lens

    ax.add_patch(Circle(deepseek_center, deepseek_radius, facecolor="#BFE7EE", edgecolor="none", alpha=0.95))
    ax.add_patch(Circle(qwen_center, qwen_radius, facecolor="#F7C98E", edgecolor="none", alpha=0.95))
    ax.add_patch(polygon_patch(shared, facecolor="#8EA5FF", edgecolor="none", alpha=0.98))


def draw_venn(deepseek_count: int, qwen_count: int, shared_count: int) -> None:
    deepseek_only = deepseek_count - shared_count
    qwen_only = qwen_count - shared_count

    fig, ax = plt.subplots(figsize=(3.1, 3.55))
    fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02)

    deepseek_radius = 1.0
    qwen_radius = math.sqrt(qwen_count / deepseek_count) * deepseek_radius
    target_overlap_area = shared_count / deepseek_count * math.pi * deepseek_radius**2
    center_distance = solve_distance_for_overlap(deepseek_radius, qwen_radius, target_overlap_area)

    deepseek_center = (0.0, center_distance / 2)
    qwen_center = (0.0, -center_distance / 2)

    edge_color = "#D4DCF7"
    text_color = "#111936"

    add_colored_venn_regions(ax, deepseek_center, deepseek_radius, qwen_center, qwen_radius)
    ax.add_patch(
        Circle(deepseek_center, deepseek_radius, facecolor="none", edgecolor=edge_color, linewidth=0.55)
    )
    ax.add_patch(
        Circle(qwen_center, qwen_radius, facecolor="none", edgecolor=edge_color, linewidth=0.55)
    )

    shared_y = (
        max(deepseek_center[1] - deepseek_radius, qwen_center[1] - qwen_radius)
        + min(deepseek_center[1] + deepseek_radius, qwen_center[1] + qwen_radius)
    ) / 2

    ax.text(
        0.0,
        deepseek_center[1] + deepseek_radius + 0.62,
        "DeepSeek-V4-Pro",
        ha="center",
        va="center",
        fontsize=9.8,
        color=text_color,
    )
    ax.text(
        0.0,
        deepseek_center[1] + deepseek_radius + 0.32,
        f"Total: {deepseek_count:,}",
        ha="center",
        va="center",
        fontsize=9.8,
        color=text_color,
    )
    ax.text(
        0.0,
        deepseek_center[1] + deepseek_radius * 0.58,
        f"{deepseek_only:,}",
        ha="center",
        va="center",
        fontsize=11.8,
        color=text_color,
    )
    ax.text(
        0.0,
        shared_y,
        f"Shared\n{shared_count:,}",
        ha="center",
        va="center",
        fontsize=10.8,
        linespacing=1.18,
        color=text_color,
    )
    ax.text(
        0.0,
        qwen_center[1] - qwen_radius * 0.55,
        f"{qwen_only:,}",
        ha="center",
        va="center",
        fontsize=11.8,
        color=text_color,
    )
    ax.text(
        0.0,
        qwen_center[1] - qwen_radius - 0.29,
        "Qwen3.7-Plus",
        ha="center",
        va="center",
        fontsize=9.8,
        color=text_color,
    )
    ax.text(
        0.0,
        qwen_center[1] - qwen_radius - 0.56,
        f"Total: {qwen_count:,}",
        ha="center",
        va="center",
        fontsize=9.8,
        color=text_color,
    )

    max_radius = max(deepseek_radius, qwen_radius)
    ax.set_xlim(-max_radius - 0.12, max_radius + 0.12)
    ax.set_ylim(qwen_center[1] - qwen_radius - 0.94, deepseek_center[1] + deepseek_radius + 0.96)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PNG, dpi=600, bbox_inches="tight", pad_inches=0.03)
    fig.savefig(OUTPUT_PDF, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


def main() -> None:
    cache_index = build_cache_index()
    deepseek_entries, deepseek_meta = load_hidden_cache_entries(DEEPSEEK_HIDDEN_TABLE, cache_index)
    qwen_entries, qwen_meta = load_hidden_cache_entries(QWEN_HIDDEN_TABLE, cache_index)

    shared = deepseek_entries & qwen_entries
    stats = {
        "unique_definition": (
            "A unique external API is one concrete api_cache.json entry with external_api=true, "
            "identified as language::api_name. The same API name in different language sections is counted as different."
        ),
        "filter": "Only api_cache.json entries with external_api=true are counted.",
        "cache_file": str(CACHE_FILE),
        "deepseek_hidden_table": str(DEEPSEEK_HIDDEN_TABLE),
        "qwen_hidden_table": str(QWEN_HIDDEN_TABLE),
        "deepseek_unique_external_api_cache_entries": len(deepseek_entries),
        "qwen_unique_external_api_cache_entries": len(qwen_entries),
        "intersection_unique_external_api_cache_entries": len(shared),
        "deepseek_only_unique_external_api_cache_entries": len(deepseek_entries - qwen_entries),
        "qwen_only_unique_external_api_cache_entries": len(qwen_entries - deepseek_entries),
        "deepseek": {key: value for key, value in deepseek_meta.items() if key not in {"ref_counts", "permission_counts", "entry_details"}},
        "qwen": {key: value for key, value in qwen_meta.items() if key not in {"ref_counts", "permission_counts", "entry_details"}},
        "intersection_csv": str(INTERSECTION_CSV),
        "output_png": str(OUTPUT_PNG),
        "output_pdf": str(OUTPUT_PDF),
    }

    write_intersection_csv(shared, deepseek_meta, qwen_meta)
    STATS_JSON.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    draw_venn(len(deepseek_entries), len(qwen_entries), len(shared))

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"[DONE] saved {OUTPUT_PNG}")
    print(f"[DONE] saved {OUTPUT_PDF}")
    print(f"[DONE] saved {INTERSECTION_CSV}")
    print(f"[DONE] saved {STATS_JSON}")


if __name__ == "__main__":
    main()
