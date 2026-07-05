#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


README_NAMES = [
    "README.md",
    "readme.md",
    "README.MD",
    "README.txt",
    "readme.txt",
    "README",
    "readme",
]

META_NAMES = [
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Dockerfile",
    ".env.example",
]


def read_text_safely(path: Path, max_chars: int = 8000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def normalize_text(text: Any) -> str:
    s = str(text or "").lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", normalize_text(text)))


def escape_md(text: Any) -> str:
    return str(text).replace("|", r"\|").replace("\n", " ").strip()


def load_taxonomy(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    types = data.get("types", [])
    if not isinstance(types, list) or len(types) != 8:
        raise ValueError(f"Invalid taxonomy file format: expected 8 categories, got {len(types)}")
    return types


def load_analysis_map(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            name = str(obj.get("server_name") or "").strip()
            if name:
                rows[name] = obj
    return rows


def discover_servers(servers_dir: Path) -> list[Path]:
    if not servers_dir.exists() or not servers_dir.is_dir():
        return []
    return sorted(
        [p for p in servers_dir.iterdir() if p.is_dir()],
        key=lambda p: p.name.lower(),
    )


def collect_fallback_row(server_dir: Path) -> dict[str, Any]:
    readme_text = ""
    for name in README_NAMES:
        p = server_dir / name
        if p.exists() and p.is_file():
            readme_text = read_text_safely(p, max_chars=8000)
            if readme_text:
                break

    meta_hits = []
    for name in META_NAMES:
        if (server_dir / name).exists():
            meta_hits.append(name)

    top_entries = []
    try:
        for child in sorted(server_dir.iterdir(), key=lambda p: p.name.lower())[:40]:
            top_entries.append(child.name)
    except Exception:
        pass

    summary_parts = []
    if readme_text:
        summary_parts.append(readme_text)
    if meta_hits:
        summary_parts.append("Meta files: " + ", ".join(meta_hits))
    if top_entries:
        summary_parts.append("Top-level entries: " + ", ".join(top_entries))

    return {
        "server_name": server_dir.name,
        "summary": "\n".join(summary_parts).strip(),
        "target_users": [],
        "use_cases": [],
        "capabilities": meta_hits + top_entries[:12],
        "candidate_types": [],
        "_source": "servers-fallback",
    }


def build_project_rows(
    servers_dir: Path,
    analysis_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    server_dirs = discover_servers(servers_dir)

    if server_dirs:
        rows = []
        for sd in server_dirs:
            if sd.name in analysis_map:
                row = dict(analysis_map[sd.name])
                row["_source"] = "analysis-jsonl"
            else:
                row = collect_fallback_row(sd)
            rows.append(row)
        return rows

    rows = []
    for row in analysis_map.values():
        obj = dict(row)
        obj["_source"] = "analysis-jsonl"
        rows.append(obj)
    return rows


def signal_hit(signal: str, text_norm: str, text_tokens: set[str]) -> bool:
    s = normalize_text(signal)
    if not s:
        return False

    if s in text_norm:
        return True

    sig_tokens = tokenize(s)
    if len(sig_tokens) >= 2 and sig_tokens.issubset(text_tokens):
        return True

    return False


def build_project_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append(str(row.get("summary") or ""))

    for key in ("target_users", "use_cases", "capabilities", "candidate_types"):
        value = row.get(key)
        if isinstance(value, list):
            parts.extend(str(x) for x in value if x)

    return normalize_text(" ".join(parts))


def score_type(row: dict[str, Any], t: dict[str, Any]) -> dict[str, Any]:
    text_norm = build_project_text(row)
    text_tokens = tokenize(text_norm)

    matched_keywords = []
    matched_include = []
    matched_exclude = []

    score = 0.0

    type_name = str(t.get("name") or "")
    type_def = str(t.get("definition") or "")
    keywords = t.get("keywords") if isinstance(t.get("keywords"), list) else []
    include_signals = t.get("include_signals") if isinstance(t.get("include_signals"), list) else []
    exclude_signals = t.get("exclude_signals") if isinstance(t.get("exclude_signals"), list) else []

    if signal_hit(type_name, text_norm, text_tokens):
        score += 2.0

    for kw in keywords:
        kw = str(kw)
        if signal_hit(kw, text_norm, text_tokens):
            matched_keywords.append(kw)
            score += 2.0

    for sig in include_signals:
        sig = str(sig)
        if signal_hit(sig, text_norm, text_tokens):
            matched_include.append(sig)
            score += 3.0

    for sig in exclude_signals:
        sig = str(sig)
        if signal_hit(sig, text_norm, text_tokens):
            matched_exclude.append(sig)
            score -= 2.5

    desc_tokens = tokenize(" ".join([type_name, type_def] + [str(x) for x in keywords]))
    overlap = len(text_tokens & desc_tokens)
    score += min(overlap, 8) * 0.35

    return {
        "type_id": t.get("id"),
        "type_name": type_name,
        "type_definition": type_def,
        "score": round(score, 3),
        "matched_keywords": matched_keywords,
        "matched_include_signals": matched_include,
        "matched_exclude_signals": matched_exclude,
    }


def classify_one(row: dict[str, Any], taxonomy: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [score_type(row, t) for t in taxonomy]
    scored.sort(key=lambda x: (x["score"], str(x["type_id"])), reverse=True)

    best = scored[0]
    second = scored[1] if len(scored) > 1 else None

    return {
        "server_name": row.get("server_name"),
        "source": row.get("_source", "unknown"),
        "assigned_type_id": best["type_id"],
        "assigned_type_name": best["type_name"],
        "assigned_type_definition": best["type_definition"],
        "score": best["score"],
        "score_margin": round(best["score"] - (second["score"] if second else 0.0), 3),
        "matched_keywords": best["matched_keywords"],
        "matched_include_signals": best["matched_include_signals"],
        "matched_exclude_signals": best["matched_exclude_signals"],
        "top2": scored[:2],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_markdown_table(taxonomy: list[dict[str, Any]], counts: Counter[str]) -> str:
    lines = [
        "| Type Name | Type Description | Count |",
        "|---|---|---:|",
    ]
    for t in taxonomy:
        lines.append(
            f"| {escape_md(t['name'])} | {escape_md(t['definition'])} | {counts.get(t['id'], 0)} |"
        )
    return "\n".join(lines)


def write_csv_table(path: Path, taxonomy: list[dict[str, Any]], counts: Counter[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Type Name", "Type Description", "Count"])
        for t in taxonomy:
            writer.writerow([t["name"], t["definition"], counts.get(t["id"], 0)])


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    parser = argparse.ArgumentParser(
        description="Classify and count projects in Servers according to taxonomy_k8.json"
    )
    parser.add_argument(
        "--servers-dir",
        default=str(repo_root / "Servers"),
        help="Path to the Servers directory",
    )
    parser.add_argument(
        "--analysis-jsonl",
        default=str(repo_root / "tool_analyzer" / "server_analysis.jsonl"),
        help="Existing service analysis results JSONL",
    )
    parser.add_argument(
        "--taxonomy",
        default=str(repo_root / "tool_analyzer" / "taxonomy_k8.json"),
        help="Path to the 8-category taxonomy file",
    )
    parser.add_argument(
        "--out-dir",
        default=str(repo_root / "picture" / "server_taxonomy_stats"),
        help="Output directory",
    )
    args = parser.parse_args()

    servers_dir = Path(args.servers_dir).resolve()
    analysis_jsonl = Path(args.analysis_jsonl).resolve()
    taxonomy_path = Path(args.taxonomy).resolve()
    out_dir = Path(args.out_dir).resolve()

    out_dir.mkdir(parents=True, exist_ok=True)

    taxonomy = load_taxonomy(taxonomy_path)
    analysis_map = load_analysis_map(analysis_jsonl)
    project_rows = build_project_rows(servers_dir, analysis_map)

    if not project_rows:
        raise RuntimeError("No projects to classify: Servers does not exist and the analysis JSONL is also empty.")

    assignments = [classify_one(row, taxonomy) for row in project_rows]
    counts = Counter(a["assigned_type_id"] for a in assignments)

    assignments_path = out_dir / "server_type_assignments.jsonl"
    summary_json_path = out_dir / "type_count_summary.json"
    summary_md_path = out_dir / "type_count_summary.md"
    summary_csv_path = out_dir / "type_count_summary.csv"

    write_jsonl(assignments_path, assignments)

    summary_json = {
        "total_projects": len(assignments),
        "taxonomy_file": str(taxonomy_path),
        "servers_dir": str(servers_dir),
        "analysis_jsonl": str(analysis_jsonl),
        "items": [
            {
                "type_id": t["id"],
                "type_name": t["name"],
                "type_definition": t["definition"],
                "count": counts.get(t["id"], 0),
            }
            for t in taxonomy
        ],
    }
    summary_json_path.write_text(
        json.dumps(summary_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_table = build_markdown_table(taxonomy, counts)
    summary_md_path.write_text(md_table + "\n", encoding="utf-8")
    write_csv_table(summary_csv_path, taxonomy, counts)

    print(f"[INFO] total projects: {len(assignments)}")
    print(f"[INFO] assignments: {assignments_path}")
    print(f"[INFO] summary json: {summary_json_path}")
    print(f"[INFO] summary md: {summary_md_path}")
    print(f"[INFO] summary csv: {summary_csv_path}")
    print()
    print(md_table)


if __name__ == "__main__":
    main()
