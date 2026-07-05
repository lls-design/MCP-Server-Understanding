#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
import unicodedata
from collections import Counter
import json
from pathlib import Path
from typing import cast

import matplotlib.pyplot as plt
from matplotlib.axes import Axes


FIGURE_FONT_SIZE = 8

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "font.size": FIGURE_FONT_SIZE,
        "axes.labelsize": FIGURE_FONT_SIZE,
        "xtick.labelsize": FIGURE_FONT_SIZE,
        "ytick.labelsize": FIGURE_FONT_SIZE,
        "legend.fontsize": FIGURE_FONT_SIZE,
        "legend.title_fontsize": FIGURE_FONT_SIZE,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


ROOT = Path("/home/lls/MCP_Analyze")
RESULTS_DIR = ROOT / "results"
PROJECT_LIST_FILE = ROOT / "tool_analyzer" / "final_success_projects.txt"
OUT_DIR = ROOT / "picture"
OUT_PATH = OUT_DIR / "Distribution of Authorization Approaches.png"
OUT_PDF = OUT_DIR / "Distribution of Authorization Approaches.pdf"
OUT_AUDIT = OUT_DIR / "Distribution of Authorization Approaches.audit.json"


TYPE_NAME_MAP = {
    "T0": "No Authorization",
    "T1": "Static Token / API Key",
    "T2": "Static Username / Password",
    "T3": "Runtime Credential Injection",
    "T4": "Delegated Role-Scoped Token",
    "T5": "OAuth 2.0 / OIDC Flow Orchestration",
    "T6": "Multi-Credential / Per-Tool Scoped Authorization",
    "T7": "Capability Artifact Authorization",
    "T8": "Other",
}
ORDER = ["T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]

RE_CATEGORY = re.compile(r'"category"\s*:\s*"(T[0-8])"')
RE_PRIMARY = re.compile(r'"primary_type"\s*:\s*"(T[0-8])"')


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def load_project_list(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [x.strip() for x in lines if x.strip()]


def build_results_dir_map(results_dir: Path) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for d in results_dir.iterdir():
        if not d.is_dir():
            continue
        key = normalize_name(d.name)
        mapping.setdefault(key, d)
    return mapping


def extract_type_from_authorization_json(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = RE_CATEGORY.search(text)
    if m:
        return m.group(1)
    m = RE_PRIMARY.search(text)
    if m:
        return m.group(1)
    return None


def plot_bar(counter: Counter[str], out_path: Path) -> None:
    items = [(t, counter.get(t, 0)) for t in ORDER if counter.get(t, 0) > 0]
    if not items:
        raise RuntimeError("No T0-T8 data to plot.")

    total = sum(v for _, v in items)
    items.sort(key=lambda x: x[1], reverse=True)

    display_labels = {
        t: chr(ord("A") + idx)
        for idx, (t, _) in enumerate(items)
    }
    short_labels = [display_labels[t] for t, _ in items]
    long_labels = [f"{display_labels[t]}: {TYPE_NAME_MAP[t]}" for t, _ in items]
    values = [v for _, v in items]

    palette_map = {
        "T0": "#F4A6A6",
        "T1": "#FFD59A",
        "T2": "#FFE8A3",
        "T3": "#E2F0CB",
        "T4": "#BFE3E8",
        "T5": "#C7CEEA",
        "T6": "#D4A5E5",
        "T7": "#F7C5A8",
        "T8": "#C2E7D9",
    }
    colors = [palette_map[t] for t, _ in items]

    fig_h = max(3.2, 0.34 * len(items) + 0.45)
    fig, ax = plt.subplots(figsize=(4.85, fig_h))
    ax = cast(Axes, ax)
    fig.subplots_adjust(left=0.085, right=0.985, bottom=0.15, top=0.97)

    bars = ax.barh(
        short_labels,
        values,
        color=colors,
        edgecolor="white",
        linewidth=0.6,
        height=0.64,
    )

    max_v = max(values)
    ax.set_xlim(0, max_v * 1.45)

    for bar, value in zip(bars, values):
        pct = value / total * 100
        ax.text(
            value + max_v * 0.015,
            bar.get_y() + bar.get_height() / 2,
            f"{value} ({pct:.1f}%)",
            va="center",
            ha="left",
            fontsize=FIGURE_FONT_SIZE,
        )

    ax.set_xlabel("Number of MCP Servers", fontsize=FIGURE_FONT_SIZE)
    ax.set_ylabel("")
    ax.tick_params(axis="both", labelsize=FIGURE_FONT_SIZE)
    ax.invert_yaxis()
    ax.grid(axis="x", linestyle="--", alpha=0.30, linewidth=0.5)
    ax.set_axisbelow(True)

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)

    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color=palette_map[t]) for t, _ in items
    ]
    ax.legend(
        legend_handles,
        long_labels,
        title="Authorization Types",
        loc="lower right",
        bbox_to_anchor=(0.995, 0.055),
        fontsize=FIGURE_FONT_SIZE,
        title_fontsize=FIGURE_FONT_SIZE,
        frameon=True,
        framealpha=0.70,
        facecolor="white",
        edgecolor="none",
        borderpad=0.25,
        labelspacing=0.20,
        handlelength=0.8,
        handletextpad=0.35,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=600, bbox_inches="tight", pad_inches=0.02)
    plt.savefig(OUT_PDF, bbox_inches="tight", pad_inches=0.02)
    plt.close()


def write_audit(
    *,
    projects: list[str],
    counter: Counter[str],
    missing_auth: list[str],
    missing_type: list[str],
) -> None:
    counted = sum(counter.values())
    audit = {
        "project_list_file": str(PROJECT_LIST_FILE),
        "projects_in_list": len(projects),
        "counted_projects": counted,
        "missing_authorization_json": len(missing_auth),
        "missing_category_or_primary_type": len(missing_type),
        "counts": {t: counter.get(t, 0) for t in ORDER},
        "shares": {
            t: (counter.get(t, 0) / counted if counted else 0)
            for t in ORDER
        },
    }
    OUT_AUDIT.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    projects = load_project_list(PROJECT_LIST_FILE)
    results_map = build_results_dir_map(RESULTS_DIR)

    counter: Counter[str] = Counter()
    missing_auth = []
    missing_type = []

    for p in projects:
        real_dir = results_map.get(normalize_name(p))
        if real_dir is None:
            missing_auth.append(p)
            continue

        auth_file = real_dir / "authorization.json"
        if not auth_file.exists():
            missing_auth.append(p)
            continue

        t = extract_type_from_authorization_json(auth_file)
        if t is None:
            missing_type.append(real_dir.name)
            continue

        counter[t] += 1
    counted = sum(counter.values())
    print(f"[INFO] projects in list: {len(projects)}")
    print(f"[INFO] counted projects: {counted}")
    print(f"[WARN] missing authorization.json: {len(missing_auth)}")
    if missing_auth:
        print(f"  examples: {', '.join(missing_auth[:10])}")

    print(f"[WARN] missing category/primary_type: {len(missing_type)}")
    if missing_type:
        print(f"  examples: {', '.join(missing_type[:10])}")

    for t in ORDER:
        if counter.get(t, 0):
            print(f"[INFO] {t}: {counter[t]}")

    write_audit(
        projects=projects,
        counter=counter,
        missing_auth=missing_auth,
        missing_type=missing_type,
    )
    plot_bar(counter, OUT_PATH)
    print(f"[DONE] saved: {OUT_PATH}")
    print(f"[DONE] audit: {OUT_AUDIT}")


if __name__ == "__main__":
    main()
