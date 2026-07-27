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


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
PROJECT_LIST_FILE = ROOT / "tool_analyzer" / "all_projects.txt"
AUTH_CLASSIFIED_FILE = (
    ROOT
    / "tool_analyzer"
    / "authorization_analyze"
    / "final_success_authorization_classified.json"
)
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
    projects = [x.strip() for x in lines if x.strip()]
    if len(projects) != len(set(projects)):
        raise ValueError(f"Duplicate projects in {path}")
    return projects


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_precomputed_authorization(
    path: Path,
    projects: list[str],
) -> Counter[str]:
    payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")

    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError(f"Expected an 'items' list in {path}")

    project_types: dict[str, str] = {}
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Item {index} in {path} is not an object")
        project = item.get("project")
        auth_type = item.get("type")
        if not isinstance(project, str) or not project.strip():
            raise ValueError(f"Item {index} in {path} has no valid project")
        if project in project_types:
            raise ValueError(f"Duplicate project {project!r} in {path}")
        if auth_type not in ORDER:
            raise ValueError(
                f"Project {project!r} has invalid authorization type {auth_type!r}"
            )
        project_types[project] = auth_type

    expected = set(projects)
    observed = set(project_types)
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing or extra:
        raise ValueError(
            f"Project coverage mismatch in {path}: "
            f"{len(missing)} missing and {len(extra)} extra"
            + (f"; missing examples: {', '.join(missing[:5])}" if missing else "")
            + (f"; extra examples: {', '.join(extra[:5])}" if extra else "")
        )

    counter = Counter(project_types[project] for project in projects)
    summary = payload.get("summary")
    if isinstance(summary, dict):
        summary_total = summary.get("total")
        if summary_total is not None and summary_total != len(projects):
            raise ValueError(
                f"summary.total in {path} is {summary_total}, "
                f"but the project list contains {len(projects)} projects"
            )
        summary_missing = summary.get("missing")
        if summary_missing not in (None, 0):
            raise ValueError(f"summary.missing in {path} is {summary_missing}, not 0")
        summary_counts = summary.get("counts_by_type")
        if isinstance(summary_counts, dict):
            expected_counts = {auth_type: counter.get(auth_type, 0) for auth_type in ORDER}
            observed_counts = {
                auth_type: summary_counts.get(auth_type, 0) for auth_type in ORDER
            }
            if observed_counts != expected_counts:
                raise ValueError(
                    f"summary.counts_by_type in {path} does not match its items"
                )
    return counter


def build_results_dir_map(results_dir: Path) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for d in results_dir.iterdir():
        if not d.is_dir():
            continue
        key = normalize_name(d.name)
        mapping.setdefault(key, d)
    return mapping


def load_authorization_from_results(
    projects: list[str],
) -> tuple[Counter[str], list[str], list[str]]:
    results_map = build_results_dir_map(RESULTS_DIR)
    counter: Counter[str] = Counter()
    missing_auth: list[str] = []
    missing_type: list[str] = []

    for project in projects:
        real_dir = results_map.get(normalize_name(project))
        if real_dir is None:
            missing_auth.append(project)
            continue

        auth_file = real_dir / "authorization.json"
        if not auth_file.exists():
            missing_auth.append(project)
            continue

        auth_type = extract_type_from_authorization_json(auth_file)
        if auth_type is None:
            missing_type.append(real_dir.name)
            continue

        counter[auth_type] += 1

    return counter, missing_auth, missing_type


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
    data_source: Path,
    source_mode: str,
) -> None:
    counted = sum(counter.values())
    audit = {
        "project_list_file": display_path(PROJECT_LIST_FILE),
        "data_source": display_path(data_source),
        "source_mode": source_mode,
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
    OUT_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    OUT_AUDIT.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    projects = load_project_list(PROJECT_LIST_FILE)
    if AUTH_CLASSIFIED_FILE.is_file():
        counter = load_precomputed_authorization(AUTH_CLASSIFIED_FILE, projects)
        missing_auth: list[str] = []
        missing_type: list[str] = []
        data_source = AUTH_CLASSIFIED_FILE
        source_mode = "precomputed_json"
    elif RESULTS_DIR.is_dir():
        counter, missing_auth, missing_type = load_authorization_from_results(projects)
        data_source = RESULTS_DIR
        source_mode = "per_project_results_fallback"
    else:
        raise FileNotFoundError(
            "No authorization data source is available. Expected the submitted "
            f"{display_path(AUTH_CLASSIFIED_FILE)} or fallback directory "
            f"{display_path(RESULTS_DIR)}."
        )

    counted = sum(counter.values())
    print(f"[INFO] data source: {display_path(data_source)} ({source_mode})")
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
        data_source=data_source,
        source_mode=source_mode,
    )
    plot_bar(counter, OUT_PATH)
    print(f"[DONE] saved: {OUT_PATH}")
    print(f"[DONE] audit: {OUT_AUDIT}")


if __name__ == "__main__":
    main()
