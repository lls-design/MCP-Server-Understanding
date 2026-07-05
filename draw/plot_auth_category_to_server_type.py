#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Rectangle

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Tinos", "Times", "DejaVu Serif"],
        "font.size": 8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)

ROOT = Path("/home/lls/MCP_Analyze")
OUT_DIR = ROOT / "picture"

AUTH_CLASSIFIED_PATH = ROOT / "tool_analyzer" / "final_success_authorization_classified.json"
FINAL_PROJECTS_PATH = ROOT / "tool_analyzer" / "final_success_projects.txt"
SERVER_ASSIGNMENTS_PATH = ROOT / "tool_analyzer" / "paper8_new_servers_classification" / "merged_server_assignments.jsonl"
OUT_AUDIT_PATH = OUT_DIR / "auth_type_to_server_type_alluvial.audit.json"

FONT_FAMILY = "serif"

# Paper-style compact alluvial chart.
FIG_W_INCHES = 5.6
FIG_H_INCHES = 5.8
LEFT_LABEL_FONT_SIZE = 6.5
RIGHT_LABEL_FONT_SIZE = 6.5
BOTTOM_LABEL_FONT_SIZE = 7.5

GRAPH_TOP = 0.972
GRAPH_BOTTOM = 0.145
NODE_MIN_GAP = 0.008
# Vertical offset for the two bottom column titles below the chart area, in axis units; larger values move titles farther from the bars.
BOTTOM_TITLE_GAP_BELOW_CHART = 0.033
SAVE_PAD_INCHES = 0.012

AUTH_TYPE_LABELS = {
    "T0": "No Authorization",
    "T1": "Static Token or API Key",
    "T2": "Static Username or Password",
    "T3": "Runtime Injection",
    "T4": "Delegated Role-Scoped Token",
    "T5": "OAuth 2.0 or OIDC Flow",
    "T6": "Multi-Credential",
    "T7": "Capability Artifact",
    "T8": "Other",
}

AUTH_TYPE_ORDER = ["T1", "T0", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]

SERVER_TYPE_ORDER = [
    "Data and Public Content Access",
    "Infrastructure and Gateway Services",
    "Source Control and Collaboration",
    "Local Execution and Automation",
    "Task and Schedule Management",
    "Financial and Blockchain Services",
    "Analytics and Peripheral Tools",
    "Security, Access Control, and Scanning",
]

AUTH_COLORS = {
    "No Authorization": "#c7c7c7",
    "Static Token or API Key": "#9ecae1",
    "Static Username or Password": "#fdd0a2",
    "Runtime Injection": "#fdae6b",
    "Delegated Role-Scoped Token": "#a1d99b",
    "OAuth 2.0 or OIDC Flow": "#bcbddc",
    "Multi-Credential": "#9edae5",
    "Capability Artifact": "#fbb4ae",
    "Other": "#d9d9d9",
}

SERVER_COLORS = {
    "Data and Public Content Access": "#9ecae1",
    "Infrastructure and Gateway Services": "#a1d99b",
    "Source Control and Collaboration": "#bcbddc",
    "Local Execution and Automation": "#fdae6b",
    "Task and Schedule Management": "#fdd0a2",
    "Financial and Blockchain Services": "#c7c7c7",
    "Analytics and Peripheral Tools": "#c6dbef",
    "Security, Access Control, and Scanning": "#fbb4ae",
}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_project_set(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip()
    }


def load_server_assignments(path: Path) -> dict[str, str]:
    mapping = {}
    valid_server_types = set(SERVER_TYPE_ORDER)

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            obj = json.loads(line)
            project = obj.get("server_name")
            server_type = obj.get("assigned_category_name")

            if project:
                project = project.strip()

            if not project or server_type not in valid_server_types:
                continue

            mapping[project] = server_type

    return mapping


def build_flow() -> tuple[Counter[tuple[str, str]], int, int]:
    auth_data = load_json(AUTH_CLASSIFIED_PATH)
    raw_auth_items = auth_data.get("items", {})
    final_projects = load_project_set(FINAL_PROJECTS_PATH)
    server_type_by_project = load_server_assignments(SERVER_ASSIGNMENTS_PATH)

    flow = Counter()
    matched = 0
    skipped = 0

    if isinstance(raw_auth_items, dict):
        auth_items = [
            {"project": project, **auth_obj}
            for project, auth_obj in raw_auth_items.items()
            if isinstance(auth_obj, dict)
        ]
    else:
        auth_items = raw_auth_items

    for auth_obj in auth_items:
        if not isinstance(auth_obj, dict):
            continue
        project = auth_obj.get("project", "")
        project = project.strip()
        if project not in final_projects:
            continue

        auth_type = auth_obj.get("type")
        server_type = server_type_by_project.get(project)

        if auth_type not in AUTH_TYPE_LABELS or not server_type:
            skipped += 1
            continue

        auth_label = AUTH_TYPE_LABELS[auth_type]
        flow[(auth_label, server_type)] += 1
        matched += 1

    return flow, matched, skipped


def save_flow_csv(path: Path, flow: Counter[tuple[str, str]]) -> None:
    rows = [
        {"source": src, "target": dst, "value": value}
        for (src, dst), value in flow.items()
    ]
    rows.sort(key=lambda x: (-x["value"], x["source"], x["target"]))

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["source", "target", "value"])
        writer.writeheader()
        writer.writerows(rows)


def save_audit(
    path: Path,
    flow: Counter[tuple[str, str]],
    auth_totals,
    server_totals,
    matched: int,
    skipped: int,
) -> None:
    total_flow = sum(flow.values())
    rows = [
        {"source": src, "target": dst, "value": value}
        for (src, dst), value in flow.items()
    ]
    rows.sort(key=lambda x: (-x["value"], x["source"], x["target"]))
    audit = {
        "authorization_classified_path": str(AUTH_CLASSIFIED_PATH),
        "final_projects_path": str(FINAL_PROJECTS_PATH),
        "server_assignments_path": str(SERVER_ASSIGNMENTS_PATH),
        "matched_projects": matched,
        "skipped_projects": skipped,
        "total_flow": total_flow,
        "auth_totals": {
            label: auth_totals.get(label, 0)
            for label in [AUTH_TYPE_LABELS[t] for t in AUTH_TYPE_ORDER]
        },
        "server_totals": {
            label: server_totals.get(label, 0)
            for label in SERVER_TYPE_ORDER
        },
        "links": rows,
    }
    path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def compute_node_layout(
    labels,
    totals,
    total_flow,
    top=None,
    bottom=None,
    min_height=0.024,
    min_gap=NODE_MIN_GAP,
):
    if top is None:
        top = GRAPH_TOP
    if bottom is None:
        bottom = GRAPH_BOTTOM

    available_total = top - bottom
    total_gap = min_gap * (len(labels) - 1)
    available_for_nodes = available_total - total_gap

    raw_heights = {label: totals[label] / total_flow for label in labels}

    fixed_height = 0.0
    flexible_total = 0.0

    for label in labels:
        raw_h = raw_heights[label]
        if raw_h < min_height:
            fixed_height += min_height
        else:
            flexible_total += raw_h

    available_for_flexible = available_for_nodes - fixed_height
    scale = available_for_flexible / flexible_total if flexible_total > 0 else 1.0

    heights = {}
    for label in labels:
        raw_h = raw_heights[label]
        if raw_h < min_height:
            heights[label] = min_height
        else:
            heights[label] = raw_h * scale

    layout = {}
    y = top

    for label in labels:
        height = heights[label]
        layout[label] = {
            "y_top": y,
            "y_bottom": y - height,
            "height": height,
        }
        y = y - height - min_gap

    return layout


def draw_ribbon(ax, x0, x1, left_top, left_bottom, right_top, right_bottom, color):
    c0 = x0 + (x1 - x0) * 0.45
    c1 = x0 + (x1 - x0) * 0.55

    verts = [
        (x0, left_top),
        (c0, left_top),
        (c1, right_top),
        (x1, right_top),
        (x1, right_bottom),
        (c1, right_bottom),
        (c0, left_bottom),
        (x0, left_bottom),
        (x0, left_top),
    ]

    codes = [
        MplPath.MOVETO,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.LINETO,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CURVE4,
        MplPath.CLOSEPOLY,
    ]

    ax.add_patch(
        PathPatch(
            MplPath(verts, codes),
            facecolor=color,
            edgecolor="none",
            alpha=0.38,
            zorder=1,
        )
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    flow, matched, skipped = build_flow()

    auth_totals = defaultdict(int)
    server_totals = defaultdict(int)

    for (auth_label, server_label), value in flow.items():
        auth_totals[auth_label] += value
        server_totals[server_label] += value

    used_auth = [
        AUTH_TYPE_LABELS[t]
        for t in AUTH_TYPE_ORDER
        if AUTH_TYPE_LABELS[t] in auth_totals
    ]

    used_server = [
        label
        for label in SERVER_TYPE_ORDER
        if label in server_totals
    ]

    total_flow = sum(flow.values())

    left_layout = compute_node_layout(used_auth, auth_totals, total_flow)
    right_layout = compute_node_layout(used_server, server_totals, total_flow)

    auth_strings_order = [AUTH_TYPE_LABELS[t] for t in AUTH_TYPE_ORDER]
    auth_rank = {s: i for i, s in enumerate(auth_strings_order)}
    server_rank = {s: i for i, s in enumerate(SERVER_TYPE_ORDER)}

    x_left0 = 0.050
    x_left1 = 0.069
    x_right0 = 0.912
    x_right1 = 0.931

    chart_bottom_edge = min(
        min(left_layout[l]["y_bottom"] for l in used_auth),
        min(right_layout[l]["y_bottom"] for l in used_server),
    )
    bottom_title_y = max(0.015, chart_bottom_edge - BOTTOM_TITLE_GAP_BELOW_CHART)

    fig_w, fig_h = FIG_W_INCHES, FIG_H_INCHES
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    links = []
    for auth_label in used_auth:
        for server_label in used_server:
            value = flow.get((auth_label, server_label), 0)
            if value <= 0:
                continue
            links.append((auth_label, server_label, value))

    left_bands = {}
    for auth_label in used_auth:
        node = left_layout[auth_label]
        outs = [
            (s, flow[(auth_label, s)])
            for s in used_server
            if flow.get((auth_label, s), 0) > 0
        ]
        outs.sort(key=lambda x: server_rank[x[0]])
        cur_y = node["y_top"]
        denom = auth_totals[auth_label]
        for s, v in outs:
            frac = v / denom
            band_h = frac * node["height"]
            top = cur_y
            bottom = cur_y - band_h
            cur_y = bottom
            left_bands[(auth_label, s)] = (top, bottom)

    right_bands = {}
    for server_label in used_server:
        node = right_layout[server_label]
        ins = [
            (a, flow[(a, server_label)])
            for a in used_auth
            if flow.get((a, server_label), 0) > 0
        ]
        ins.sort(key=lambda x: auth_rank[x[0]])
        cur_y = node["y_top"]
        denom = server_totals[server_label]
        for a, v in ins:
            frac = v / denom
            band_h = frac * node["height"]
            top = cur_y
            bottom = cur_y - band_h
            cur_y = bottom
            right_bands[(a, server_label)] = (top, bottom)

    for auth_label, server_label, value in links:
        left_top, left_bottom = left_bands[(auth_label, server_label)]
        right_top, right_bottom = right_bands[(auth_label, server_label)]

        draw_ribbon(
            ax,
            x_left1,
            x_right0,
            left_top,
            left_bottom,
            right_top,
            right_bottom,
            AUTH_COLORS[auth_label],
        )

    for label in used_auth:
        node = left_layout[label]
        y0 = node["y_bottom"]
        h = node["height"]

        ax.add_patch(
            Rectangle(
                (x_left0, y0),
                x_left1 - x_left0,
                h,
                facecolor=AUTH_COLORS[label],
                edgecolor="white",
                linewidth=0.7,
                zorder=3,
            )
        )

        ax.text(
            x_left1 + 0.008,
            y0 + h / 2,
            f"{label}: {auth_totals[label]}",
            ha="left",
            va="center",
            fontsize=LEFT_LABEL_FONT_SIZE,
            family=FONT_FAMILY,
            fontweight="normal",
            zorder=4,
        )

    for label in used_server:
        node = right_layout[label]
        y0 = node["y_bottom"]
        h = node["height"]

        ax.add_patch(
            Rectangle(
                (x_right0, y0),
                x_right1 - x_right0,
                h,
                facecolor=SERVER_COLORS[label],
                edgecolor="white",
                linewidth=0.7,
                zorder=3,
            )
        )

        ax.text(
            x_right0 - 0.008,
            y0 + h / 2,
            f"{label}: {server_totals[label]}",
            ha="right",
            va="center",
            fontsize=RIGHT_LABEL_FONT_SIZE,
            family=FONT_FAMILY,
            fontweight="normal",
            zorder=4,
        )

    ax.text(
        x_left0,
        bottom_title_y,
        "Authorization Types",
        ha="left",
        va="bottom",
        fontsize=BOTTOM_LABEL_FONT_SIZE,
        family=FONT_FAMILY,
        fontweight="normal",
    )

    ax.text(
        x_right1,
        bottom_title_y,
        "Server Types",
        ha="right",
        va="bottom",
        fontsize=BOTTOM_LABEL_FONT_SIZE,
        family=FONT_FAMILY,
        fontweight="normal",
    )

    out_stem = "auth_type_to_server_type_alluvial"
    csv_path = OUT_DIR / f"{out_stem}.csv"
    png_path = OUT_DIR / f"{out_stem}.png"
    pdf_path = OUT_DIR / f"{out_stem}.pdf"

    save_flow_csv(csv_path, flow)
    save_audit(OUT_AUDIT_PATH, flow, auth_totals, server_totals, matched, skipped)
    fig.savefig(png_path, dpi=300, bbox_inches="tight", pad_inches=SAVE_PAD_INCHES)
    fig.savefig(pdf_path, format="pdf", bbox_inches="tight", pad_inches=SAVE_PAD_INCHES)
    plt.close(fig)

    print(f"[INFO] matched projects: {matched}")
    print(f"[INFO] skipped projects: {skipped}")
    print(f"[INFO] displayed links: {len(links)}")
    print(f"[INFO] total flow value: {total_flow}")
    print(f"[SAVED] {csv_path}")
    print(f"[SAVED] {png_path}")
    print(f"[SAVED] {pdf_path}")
    print(f"[SAVED] {OUT_AUDIT_PATH}")


if __name__ == "__main__":
    main()
