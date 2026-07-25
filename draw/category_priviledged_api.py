#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate an English category table for privileged/external APIs.

Input:
  tool_analyzer/api_cache.json

Output:
  picture/Table 2 Categorization of Privilege-Sensitive APIs.csv
  picture/Table 2 Categorization of Privilege-Sensitive APIs.png
"""

import json
import os
import textwrap
from pathlib import Path
from collections import defaultdict

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
API_CACHE = ROOT / "tool_analyzer" / "api_cache.json"
PROJECT_FILE = ROOT / "tool_analyzer" / "all_projects.txt"
OUT_DIR = ROOT / "picture"
OUT_CSV = OUT_DIR / "Table 2 Categorization of Privilege-Sensitive APIs.csv"
OUT_PNG = OUT_DIR / "Table 2 Categorization of Privilege-Sensitive APIs.png"
OUT_JSON = ROOT / "category_statistics.json"


# Category definitions from api_analyze.py (56-85), rewritten for the paper table
CATEGORY_DESC = {
    "Specialized Domain Data Services": "Access domain-specific external data.",
    "Cloud Infrastructure Management": "Provision or manage cloud resources.",
    "System Command Execution": "Run local commands or scripts.",
    "Project Management Services": "Manage issues, tasks, and repositories.",
    "Identity and Access Management": "Authenticate users and manage access.",
    "Financial and Blockchain Services": "Process financial or blockchain transactions.",
    "Database Management": "Query, modify, or administer databases.",
    "AI and Machine Learning Services": "Invoke AI/ML models or services.",
    "Browser Automation and Web Interaction": "Automate browsers and web pages.",
    "File System Operations": "Read, write, or transfer files.",
}


# Curated from APIs that appear in the current cache. These examples are chosen
# for reader recognizability rather than frequency, so the table illustrates the
# category boundary instead of incidental traversal order.
REPRESENTATIVE_EXAMPLES = {
    "Specialized Domain Data Services": [
        ("googlemaps.Client.geocode", "GoogleMaps.geocode"),
        ("youtube.videos.list", "YouTube.videos.list"),
    ],
    "Cloud Infrastructure Management": [
        ("boto3.client('ec2').describe_volumes", "EC2.describe_volumes"),
        ("CoreV1Api.list_namespaced_pod", "Kubernetes.list_pod"),
    ],
    "System Command Execution": [
        ("subprocess.run", "subprocess.run"),
        ("child_process.spawn", "child_process.spawn"),
    ],
    "Project Management Services": [
        ("jira.JIRA.create_issue", "JIRA.create_issue"),
        ("pulls.createPullRequest", "GitHub.createPullRequest"),
    ],
    "Identity and Access Management": [
        ("google_auth_oauthlib.flow.run_local_server", "OAuth.run_server"),
        ("google.oauth2.credentials.Credentials.refresh", "Credentials.refresh"),
    ],
    "Financial and Blockchain Services": [
        ("stripe.paymentIntents.create", "Stripe.paymentIntents.create"),
        ("viem.sendTransaction", "viem.sendTransaction"),
    ],
    "Database Management": [
        ("sqlite3.Cursor.execute", "SQLite.execute"),
        ("pg.Client.query", "PostgreSQL.query"),
    ],
    "AI and Machine Learning Services": [
        ("openai.chat.completions.create", "OpenAI.chat.create"),
        ("openai.embeddings.create", "OpenAI.embeddings"),
    ],
    "Browser Automation and Web Interaction": [
        ("puppeteer.Page.waitForSelector", "Puppeteer.waitForSelector"),
        ("playwright.Page.goto", "Playwright.goto"),
    ],
    "File System Operations": [
        ("os.remove", "os.remove"),
        ("fs.writeFile", "fs.writeFile"),
    ],
}

# Keep a stable row order (same as api_analyze.py)
CATEGORY_ORDER = [
    "Specialized Domain Data Services",
    "Cloud Infrastructure Management",
    "System Command Execution",
    "Project Management Services",
    "Identity and Access Management",
    "Financial and Blockchain Services",
    "Database Management",
    "AI and Machine Learning Services",
    "Browser Automation and Web Interaction",
    "File System Operations",
]


# Current cache may contain narrower labels from later review passes. The table in
# the paper uses the 10-category taxonomy above, so fold these labels back.
CATEGORY_ALIASES = {
    "Academic Research Data Services": "Specialized Domain Data Services",
    "Blockchain and Cryptocurrency Services": "Financial and Blockchain Services",
    "Calendar Services": "Project Management Services",
    "Code Repository Services": "Project Management Services",
    "Email Management Services": "Specialized Domain Data Services",
    "Email Services": "Specialized Domain Data Services",
    "Financial Market Data Services": "Specialized Domain Data Services",
    "Financial Trading Services": "Financial and Blockchain Services",
    "Healthcare Terminology Services": "Specialized Domain Data Services",
    "Network Access": "Specialized Domain Data Services",
    "Payment Processing": "Financial and Blockchain Services",
    "SMS and Telephony Services": "Specialized Domain Data Services",
    "Social Media Management": "Specialized Domain Data Services",
    "Weather and Climate Services": "Specialized Domain Data Services",
}


def canonical_category(category: str) -> str:
    category = (category or "Uncategorized").strip()
    return CATEGORY_ALIASES.get(category, category)


def load_project_set(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def entry_projects(info: dict) -> set[str]:
    value = info.get("project") or info.get("project_name") or info.get("repository")
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(v) for v in value if v}
    if value:
        return {str(value)}
    return set()


def load_external_api_records(path: Path, projects: set[str]):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    skipped_outside_projects = 0
    for lang in ("Python", "TypeScript"):
        bucket = data.get(lang, {})
        for api_name, info in bucket.items():
            if not isinstance(info, dict):
                continue
            if info.get("external_api") is True:
                projects_for_entry = entry_projects(info)
                if projects and not (projects_for_entry & projects):
                    skipped_outside_projects += 1
                    continue
                rows.append(
                    {
                        "api_name": api_name,
                        "category": canonical_category(info.get("category")),
                        "summary": info.get("external_api_summary", ""),
                        "lang": lang,
                    }
                )
    return rows, skipped_outside_projects


def format_api_example(name: str) -> str:
    name = str(name).strip()
    if not name or name == "-":
        return "-"
    if name.endswith(")"):
        return name
    return f"{name}()"


def example_key_and_label(example: str | tuple[str, str]) -> tuple[str, str]:
    if isinstance(example, tuple):
        return example
    return example, example


def summarize(rows):
    by_cat_count = defaultdict(int)
    by_cat_examples = defaultdict(list)
    by_cat_available = defaultdict(set)

    for r in rows:
        c = r["category"] if r["category"] in CATEGORY_DESC else "Uncategorized"
        by_cat_count[c] += 1
        by_cat_available[c].add(r["api_name"])

        # Keep a fallback in case curated examples are absent after future data refreshes.
        if len(by_cat_examples[c]) < 2:
            by_cat_examples[c].append(format_api_example(r["api_name"]))

    total = len(rows)

    table_rows = []
    for c in CATEGORY_ORDER + ["Uncategorized"]:
        n = by_cat_count.get(c, 0)
        if n == 0:
            continue
        pct = (n / total * 100.0) if total else 0.0
        desc = CATEGORY_DESC.get(c, "APIs without a valid category mapping.")
        curated = []
        for example in REPRESENTATIVE_EXAMPLES.get(c, []):
            api, label = example_key_and_label(example)
            if api in by_cat_available.get(c, set()):
                curated.append(format_api_example(label))
        examples = curated[:2] or by_cat_examples.get(c, [])[:2]
        ex = "\n".join(examples) if examples else "-"
        table_rows.append([c, n, desc, ex, f"{pct:.2f}%"])

    # sort by count desc while keeping Uncategorized at end (if any)
    unc = [r for r in table_rows if r[0] == "Uncategorized"]
    main = [r for r in table_rows if r[0] != "Uncategorized"]
    main.sort(key=lambda x: x[1], reverse=True)
    table_rows = main + unc

    return total, table_rows


def save_csv(path: Path, rows):
    header = ["Category", "Count", "Description", "Examples", "Share"]
    lines = [",".join(header)]
    for r in rows:
        esc = []
        for v in r:
            s = str(v).replace('"', '""')
            esc.append(f'"{s}"')
        lines.append(",".join(esc))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_json(path: Path, project_count, total, rows, skipped_outside_projects):
    result = {
        "source": str(API_CACHE),
        "project_file": str(PROJECT_FILE),
        "project_count": project_count,
        "total_external_apis": total,
        "skipped_outside_projects": skipped_outside_projects,
        "taxonomy": "10-category merged taxonomy",
        "category_aliases": CATEGORY_ALIASES,
        "categories": {
            r[0]: {
                "count": r[1],
                "share": r[4],
                "description": r[2],
                "examples": r[3].splitlines() if r[3] != "-" else [],
            }
            for r in rows
        },
    }
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_table_png(path: Path, total, rows):
    # Build figure
    fig_h = max(7, 0.7 * (len(rows) + 2))
    fig, ax = plt.subplots(figsize=(22, fig_h))
    ax.axis("off")

    col_labels = ["Category", "Count", "Description", "Examples", "Share"]
    cell_text = [
        [
            textwrap.fill(r[0], 28),
            str(r[1]),
            textwrap.fill(r[2], 42),
            r[3],
            r[4],
        ]
        for r in rows
    ]

    table = ax.table(
        cellText=cell_text,
        colLabels=col_labels,
        cellLoc="left",
        loc="center",
        colWidths=[0.25, 0.08, 0.34, 0.23, 0.10],
    )

    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2.2)

    # Header style + zebra stripes
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#D9E1F2")
        elif row % 2 == 0:
            cell.set_facecolor("#F7F7F7")

    ax.set_title(
        f"Table 2 Categorization of Privilege-Sensitive APIs (N={total})",
        fontsize=16,
        pad=20,
        weight="bold"
    )

    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    projects = load_project_set(PROJECT_FILE)
    rows, skipped_outside_projects = load_external_api_records(API_CACHE, projects)
    total, table_rows = summarize(rows)

    save_csv(OUT_CSV, table_rows)
    save_json(OUT_JSON, len(projects), total, table_rows, skipped_outside_projects)
    save_table_png(OUT_PNG, total, table_rows)

    print(f"[INFO] projects: {len(projects)}")
    print(f"[INFO] external_api=true total: {total}")
    if skipped_outside_projects:
        print(f"[WARN] skipped entries outside target projects: {skipped_outside_projects}")
    print(f"[DONE] JSON saved: {OUT_JSON}")
    print(f"[DONE] CSV saved: {OUT_CSV}")
    print(f"[DONE] PNG saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
