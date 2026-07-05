#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Draw a compact violin plot for all source-code LOC in final projects."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path("/home/lls/MCP_Analyze")
PROJECT_FILE = ROOT / "tool_analyzer" / "final_success_projects.txt"
SERVERS_DIR = ROOT / "Servers"
RESULTS_DIR = ROOT / "results"
OUTPUT_DIR = ROOT / "picture"
OUTPUT_PNG = OUTPUT_DIR / "final_success_code_loc_violin.png"
OUTPUT_PDF = OUTPUT_DIR / "final_success_code_loc_violin.pdf"
DETAILS_JSON = OUTPUT_DIR / "final_success_mcp_implementation_loc_details.json"

SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs",
    ".mts", ".cts",
    ".go", ".rs", ".java", ".kt", ".cs", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".swift", ".scala", ".sh",
}

IGNORE_DIRS = {
    ".git", "node_modules", "dist", "build", "coverage", ".next",
    ".venv", "venv", "myenv", "env", "__pycache__", ".idea", ".vscode", "target",
    ".documcp", ".pytest_cache", ".mypy_cache", "site-packages", ".smithery",
}
NON_IMPLEMENTATION_DIRS = {
    "doc", "docs", "documentation",
    "test", "tests", "__tests__", "spec", "specs",
    "example", "examples", "demo", "demos",
    "fixture", "fixtures", "mock", "mocks",
    "sample", "samples", "template", "templates",
    "benchmark", "benchmarks",
}
FRONTEND_DIRS = {
    "dashboard", "frontend", "web", "webapp", "ui",
    "public", "static", "assets",
}
VENDORED_DIRS = {
    "vendor", "vendors", "third_party", "third-party",
    "external", "fastmcp",
}
IGNORE_DIR_SUFFIXES = ("_codeql",)
IGNORE_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "composer.lock", "poetry.lock", "Cargo.lock",
}


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


def is_ignored_path(path: Path) -> bool:
    for part in path.parts:
        if part in IGNORE_DIRS:
            return True
        if part.endswith(IGNORE_DIR_SUFFIXES):
            return True
        if "node_modules" in part:
            return True
    return False


def is_non_implementation_path(path: Path) -> bool:
    for part in path.parts:
        normalized = part.lower().strip()
        if normalized in NON_IMPLEMENTATION_DIRS:
            return True
        if normalized.endswith((".test", ".spec")):
            return True
        if normalized.endswith(("-test", "_test", "-tests", "_tests")):
            return True
    name = path.name.lower()
    return (
        ".test." in name
        or ".spec." in name
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def is_project_excluded_path(project: str, server_dir: Path, path: Path) -> bool:
    rel_parts = path.relative_to(server_dir).parts
    lower_parts = [part.lower().strip() for part in rel_parts]
    project_lower = project.lower()

    if lower_parts:
        top = lower_parts[0]
        if top in VENDORED_DIRS and top not in project_lower:
            return True

    has_mcp_part = any("mcp" in part for part in lower_parts)
    if not has_mcp_part and any(part in FRONTEND_DIRS for part in lower_parts):
        return True

    return False


def is_source_file(path: Path) -> bool:
    if path.name in IGNORE_FILES:
        return False
    if is_ignored_path(path):
        return False
    if is_non_implementation_path(path):
        return False
    return path.suffix.lower() in SOURCE_EXTENSIONS


def is_project_source_file(project: str, server_dir: Path, path: Path) -> bool:
    if is_project_excluded_path(project, server_dir, path):
        return False
    return is_source_file(path)


def iter_call_graph_nodes(call_graph: Path) -> list[dict]:
    data = json.loads(call_graph.read_text(encoding="utf-8", errors="ignore"))
    if isinstance(data, list):
        return [node for node in data if isinstance(node, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("nodes"), list):
            return [node for node in data["nodes"] if isinstance(node, dict)]
        return [node for node in data.values() if isinstance(node, dict)]
    return []


def strip_location_suffix(raw_path: str) -> str:
    parts = raw_path.rsplit(":", 4)
    if len(parts) == 5 and all(part.isdigit() for part in parts[1:]):
        return parts[0]
    return raw_path


def resolve_graph_path(server_dir: Path, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    raw_file = strip_location_suffix(raw_path)
    candidate = Path(raw_file)
    if candidate.is_absolute() and candidate.exists():
        try:
            candidate.relative_to(server_dir)
        except ValueError:
            return None
        return candidate
    candidate = server_dir / raw_file.lstrip("/")
    if candidate.exists():
        return candidate
    return None


def iter_entry_point_files(entry_points: Path) -> list[str]:
    if not entry_points.exists():
        return []
    data = json.loads(entry_points.read_text(encoding="utf-8", errors="ignore"))
    items = data.values() if isinstance(data, dict) else data
    files = []
    for item in items:
        if isinstance(item, dict) and item.get("file"):
            files.append(str(item["file"]))
    return files


def implementation_root_for_file(server_dir: Path, path: Path) -> Path:
    rel = path.relative_to(server_dir)
    parts = rel.parts

    for i, part in enumerate(parts[:-1]):
        if part == "src":
            if i + 1 < len(parts) - 1:
                return server_dir.joinpath(*parts[: i + 2])
            return path

    for i, part in enumerate(parts[:-1]):
        if "mcp" in part.lower():
            return server_dir.joinpath(*parts[: i + 1])

    if len(parts) > 1:
        return server_dir / parts[0]
    return path


def collect_implementation_roots(project: str, server_dir: Path) -> list[Path]:
    roots: set[Path] = set()
    call_graph = RESULTS_DIR / project / "call_graph_labeled.json"
    entry_points = RESULTS_DIR / project / "entry_points.json"

    for raw_path in iter_entry_point_files(entry_points):
        path = resolve_graph_path(server_dir, raw_path)
        if path is not None and path.is_file() and is_project_source_file(project, server_dir, path):
            roots.add(implementation_root_for_file(server_dir, path))

    if call_graph.exists():
        for node in iter_call_graph_nodes(call_graph):
            path = resolve_graph_path(server_dir, str(node.get("path", "")))
            if path is not None and path.is_file() and is_project_source_file(project, server_dir, path):
                roots.add(implementation_root_for_file(server_dir, path))

    # Drop roots contained by a broader selected root.
    minimal_roots = []
    for root in sorted(roots, key=lambda p: (len(p.parts), str(p))):
        if not any(root.is_relative_to(existing) for existing in minimal_roots):
            minimal_roots.append(root)
    return minimal_roots


def collect_mcp_implementation_files(project: str, server_dir: Path) -> list[Path]:
    files: set[Path] = set()
    for root in collect_implementation_roots(project, server_dir):
        if root.is_file():
            candidates = [root]
        else:
            candidates = [path for path in root.rglob("*") if path.is_file()]
        for path in candidates:
            if is_project_source_file(project, server_dir, path):
                files.add(path)
    return sorted(files)


def count_project_loc(project: str, server_dir: Path) -> tuple[int, int]:
    total_lines = 0
    files = collect_mcp_implementation_files(project, server_dir)
    for path in files:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                total_lines += sum(1 for _ in f)
        except OSError:
            continue
    return total_lines, len(files)


def collect_loc_counts() -> tuple[np.ndarray, list[dict]]:
    projects = read_projects(PROJECT_FILE)
    project_set = set(projects)
    if len(projects) != len(project_set):
        raise ValueError(f"Duplicate projects in {PROJECT_FILE}")

    server_index = {p.name: p for p in SERVERS_DIR.iterdir() if p.is_dir()}
    missing = sorted(project_set - set(server_index))
    if missing:
        raise ValueError(f"Missing server dirs for {len(missing)} projects")

    details = []
    values = []
    for project in projects:
        loc, file_count = count_project_loc(project, server_index[project])
        roots = collect_implementation_roots(project, server_index[project])
        values.append(loc)
        details.append({
            "project": project,
            "mcp_implementation_loc": loc,
            "implementation_file_count": file_count,
            "implementation_roots": [
                str(root.relative_to(server_index[project])) if root != server_index[project] else "."
                for root in roots
            ],
        })

    return np.asarray(values, dtype=float), details


def format_tick(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.0f}M"
    if value >= 1000:
        return f"{value / 1000:.0f}k"
    return str(value)


def format_stat(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    if value >= 100:
        return f"{value / 1000:.1f}k"
    return f"{value:.0f}"


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
    color: str = "#2F4858",
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
    total_loc = int(np.sum(values))

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
        body.set_facecolor("#AFC1DE")
        body.set_edgecolor("#4F5F7A")
        body.set_alpha(0.96)
        body.set_linewidth(0.85)

    rng = np.random.default_rng(20260624)
    jitter = rng.normal(0, 0.055, size=len(log_values))
    jitter = np.clip(jitter, -0.16, 0.16)
    ax.scatter(
        1 + jitter,
        log_values,
        s=4.5,
        color="#23384F",
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
        color="#1D2633",
        edgecolor="white",
        linewidth=0.25,
        alpha=0.90,
        zorder=5,
    )

    tick_candidates = [10, 100, 1000, 10000, 100000, 500000, 1000000]
    upper_tick = next(
        tick for tick in tick_candidates if tick >= max(10, values.max() * 1.12)
    )
    tick_values = [tick for tick in tick_candidates if tick <= upper_tick]
    ax.set_yticks(np.log10(np.asarray(tick_values, dtype=float) + 1))
    ax.set_yticklabels([format_tick(v) for v in tick_values])
    ax.set_ylim(np.log10(10 + 1), np.log10(upper_tick + 1))

    ax.set_xlim(0.43, 1.60)
    ax.set_xticks([1])
    ax.set_xticklabels(["Lines of Code"], fontsize=11)
    ax.set_ylabel("MCP implementation LOC (log scale)", labelpad=2)
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
        f"{len(values):,} MCPs | {total_loc / 1_000_000:.1f}M LOC",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=9.6,
        color="#303030",
    )

    mark_stat(ax, 1.27, median, "s", format_stat(median), dy=0.000, size=24)
    mark_stat(
        ax,
        1.25,
        mean,
        "D",
        format_stat(mean),
        text_dy=-0.010,
        dy=-0.026,
        size=26,
    )
    mark_stat(ax, 1.20, p95, "^", format_stat(p95), text_dy=0.006, size=42)
    mark_stat(
        ax,
        1.06,
        float(values.max()),
        "P",
        format_stat(float(values.max())),
        line_len=0.040,
        text_gap=0.012,
        dy=-0.110,
        size=38,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PNG, dpi=600)
    fig.savefig(OUTPUT_PDF)
    plt.close(fig)


def main() -> None:
    values, details = collect_loc_counts()
    draw_violin(values)
    DETAILS_JSON.write_text(
        json.dumps(details, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"[INFO] projects: {len(values)}")
    print(f"[INFO] total MCP implementation LOC: {int(values.sum())}")
    print(
        "[INFO] min/median/mean/p95/max: "
        f"{values.min():.0f} / {np.median(values):.0f} / "
        f"{values.mean():.2f} / {np.percentile(values, 95):.0f} / {values.max():.0f}"
    )
    print(f"[DONE] saved details: {DETAILS_JSON}")
    print(f"[DONE] saved PNG: {OUTPUT_PNG}")
    print(f"[DONE] saved PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
