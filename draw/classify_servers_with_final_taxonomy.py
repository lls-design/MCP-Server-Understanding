#!/usr/bin/env python3
"""Classify MCP servers with tool_analyzer/taxonomy_final.json.

This classifier is deterministic and local. It uses extracted evidence from
server_category_accuracy/server_evidence.jsonl and applies the final taxonomy
codebook with noise filtering, weighted signal matching, and review flags.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tool_analyzer"
DEFAULT_TAXONOMY = TOOL / "taxonomy_final.json"
DEFAULT_EVIDENCE = TOOL / "server_category_accuracy" / "server_evidence.jsonl"
DEFAULT_OUT = TOOL / "final_taxonomy_stats"

INSTALL_SECTION_RE = re.compile(
    r"(?im)^#{1,5}\s*(installation|install|setup|quick start|configuration|configure|usage|running|development|debugging|contributing|license)\b"
)
CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
URL_RE = re.compile(r"https?://\S+")
COMMAND_RE = re.compile(
    r"\b(npm|pnpm|yarn|pip|uv|python|node|docker|cargo|go)\s+(install|run|add|build|start|test|mod|env)\b[^\n]*",
    re.I,
)


def normalize(text: Any) -> str:
    s = str(text or "").lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", normalize(text)))


def clean_readme(text: str) -> str:
    if not text:
        return ""
    stop = INSTALL_SECTION_RE.search(text)
    if stop and stop.start() > 300:
        text = text[: stop.start()]
    text = CODE_BLOCK_RE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    text = COMMAND_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()[:7000]


def compact(text: Any, limit: int = 3000) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def signal_hit(signal: str, text_norm: str, text_tokens: set[str]) -> bool:
    sig = normalize(signal)
    if not sig:
        return False
    if sig in text_norm:
        return True
    sig_tokens = tokens(sig)
    return len(sig_tokens) >= 2 and sig_tokens.issubset(text_tokens)


def evidence_fields(row: dict[str, Any]) -> dict[str, str]:
    tool_text = " ".join(row.get("tool_like_names") or [])
    analysis_text = " ".join(
        [
            str(row.get("analysis_summary") or ""),
            " ".join(map(str, row.get("analysis_capabilities") or [])),
            " ".join(map(str, row.get("analysis_use_cases") or [])),
            " ".join(map(str, row.get("analysis_candidate_types") or [])),
        ]
    )
    meta_bits = []
    for name, value in (row.get("meta_files") or {}).items():
        if name in {"package.json", "pyproject.toml", "Cargo.toml", "go.mod"}:
            meta_bits.append(str(value)[:2500])
        else:
            meta_bits.append(str(value)[:800])
    readme = clean_readme(str(row.get("readme_excerpt") or ""))
    name = str(row.get("server_name") or "")
    return {
        "tool": compact(tool_text, 3000),
        "analysis": compact(analysis_text, 3000),
        "readme": compact(readme, 7000),
        "meta": compact(" ".join(meta_bits), 3000),
        "name": name,
    }


def score_signals(signals: list[str], fields: dict[str, str], weight: float) -> tuple[float, list[str]]:
    matched: list[str] = []
    score = 0.0
    field_weights = {
        "tool": 4.0,
        "analysis": 3.0,
        "readme": 2.0,
        "meta": 1.2,
        "name": 1.0,
    }
    norm_cache = {k: normalize(v) for k, v in fields.items()}
    token_cache = {k: tokens(v) for k, v in norm_cache.items()}
    for sig in signals:
        sig_hit = False
        for field, fw in field_weights.items():
            if signal_hit(sig, norm_cache[field], token_cache[field]):
                score += weight * fw
                sig_hit = True
        if sig_hit:
            matched.append(sig)
    return score, matched


def score_criteria(criteria: list[str], fields: dict[str, str], weight: float) -> tuple[float, list[str]]:
    # Criteria are prose, so only use compact token overlap instead of exact phrase matches.
    text = normalize(" ".join(fields.values()))
    text_tokens = tokens(text)
    matched = []
    score = 0.0
    for crit in criteria:
        crit_tokens = {t for t in tokens(crit) if len(t) > 3}
        if not crit_tokens:
            continue
        overlap = len(crit_tokens & text_tokens)
        if overlap >= min(3, len(crit_tokens)):
            score += weight * min(overlap, 5)
            matched.append(crit)
    return score, matched


def classify_one(row: dict[str, Any], taxonomy: dict[str, Any]) -> dict[str, Any]:
    fields = evidence_fields(row)
    scored = []
    for cat in taxonomy["categories"]:
        pos_score, pos_hits = score_signals(cat.get("positive_signals", []), fields, 1.0)
        neg_score, neg_hits = score_signals(cat.get("negative_signals", []), fields, 0.8)
        inc_score, inc_hits = score_criteria(cat.get("include_criteria", []), fields, 0.35)
        exc_score, exc_hits = score_criteria(cat.get("exclude_criteria", []), fields, 0.35)

        # Category name/description provide a weak prior only.
        prior_text = f"{cat.get('name', '')} {cat.get('description', '')}"
        prior_score, prior_hits = score_signals([cat.get("name", ""), cat.get("description", "")], fields, 0.08)
        score = pos_score + inc_score + prior_score - neg_score - exc_score

        scored.append({
            "category_id": cat["id"],
            "category_name": cat["name"],
            "description": cat["description"],
            "score": round(score, 3),
            "positive_hits": pos_hits,
            "include_hits": inc_hits,
            "negative_hits": neg_hits,
            "exclude_hits": exc_hits,
            "prior_hits": prior_hits,
        })

    scored.sort(key=lambda x: (x["score"], x["category_id"]), reverse=True)
    best = scored[0]
    second = scored[1] if len(scored) > 1 else {"score": 0, "category_name": ""}
    margin = round(best["score"] - second["score"], 3)
    review_reasons = []
    if best["score"] < 6:
        review_reasons.append("low_score")
    if margin < 3:
        review_reasons.append("low_margin")
    if best["category_name"] == "Other Specialized Integrations":
        review_reasons.append("other_category")
    if best["category_name"] in {
        "Security and Access Control",
        "Financial and Blockchain Services",
        "Infrastructure and Operations",
    }:
        review_reasons.append("high_impact_category")
    if best["negative_hits"] or best["exclude_hits"]:
        review_reasons.append("conflicting_negative_evidence")

    return {
        "server_name": row.get("server_name"),
        "assigned_category_id": best["category_id"],
        "assigned_category_name": best["category_name"],
        "assigned_category_description": best["description"],
        "score": best["score"],
        "score_margin": margin,
        "review_reasons": review_reasons,
        "positive_hits": best["positive_hits"],
        "include_hits": best["include_hits"],
        "negative_hits": best["negative_hits"],
        "exclude_hits": best["exclude_hits"],
        "top2": scored[:2],
        "tool_like_names": row.get("tool_like_names") or [],
        "old_assignment": row.get("old_assignment"),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_outputs(out_dir: Path, taxonomy: dict[str, Any], assignments: list[dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "server_assignments.jsonl", assignments)

    counts = Counter(a["assigned_category_name"] for a in assignments)
    summary = {
        "total_servers": len(assignments),
        "taxonomy_file": str(DEFAULT_TAXONOMY),
        "items": [
            {
                "category_id": c["id"],
                "category_name": c["name"],
                "description": c["description"],
                "count": counts.get(c["name"], 0),
            }
            for c in taxonomy["categories"]
        ],
        "review_queue_count": sum(1 for a in assignments if a["review_reasons"]),
        "review_reason_counts": Counter(r for a in assignments for r in a["review_reasons"]),
    }
    (out_dir / "type_count_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=dict),
        encoding="utf-8",
    )

    with (out_dir / "type_count_summary.md").open("w", encoding="utf-8") as f:
        f.write("| Type Name | Description | Count |\n")
        f.write("|---|---|---:|\n")
        for item in summary["items"]:
            f.write(f"| {item['category_name']} | {item['description']} | {item['count']} |\n")
        f.write(f"| **Total** |  | **{len(assignments)}** |\n")

    with (out_dir / "type_count_summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Type Name", "Description", "Count"])
        for item in summary["items"]:
            writer.writerow([item["category_name"], item["description"], item["count"]])
        writer.writerow(["Total", "", len(assignments)])

    review_rows = [a for a in assignments if a["review_reasons"]]
    with (out_dir / "review_queue.csv").open("w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "server_name",
            "assigned_category_name",
            "score",
            "score_margin",
            "review_reasons",
            "top2",
            "positive_hits",
            "negative_hits",
            "tool_like_names",
            "old_assignment",
            "manual_category",
            "notes",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for a in review_rows:
            writer.writerow({
                "server_name": a["server_name"],
                "assigned_category_name": a["assigned_category_name"],
                "score": a["score"],
                "score_margin": a["score_margin"],
                "review_reasons": "; ".join(a["review_reasons"]),
                "top2": json.dumps(a["top2"], ensure_ascii=False),
                "positive_hits": "; ".join(a["positive_hits"]),
                "negative_hits": "; ".join(a["negative_hits"]),
                "tool_like_names": "; ".join(a["tool_like_names"])[:500],
                "old_assignment": json.dumps(a["old_assignment"], ensure_ascii=False),
                "manual_category": "",
                "notes": "",
            })

    audit = {
        "score_distribution": {
            "min": min(a["score"] for a in assignments),
            "max": max(a["score"] for a in assignments),
            "avg": round(sum(a["score"] for a in assignments) / len(assignments), 3),
        },
        "margin_distribution": {
            "min": min(a["score_margin"] for a in assignments),
            "max": max(a["score_margin"] for a in assignments),
            "avg": round(sum(a["score_margin"] for a in assignments) / len(assignments), 3),
        },
        "review_reason_counts": dict(Counter(r for a in assignments for r in a["review_reasons"])),
        "category_counts": dict(counts),
    }
    (out_dir / "classification_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    taxonomy = json.loads(args.taxonomy.read_text(encoding="utf-8"))
    rows = load_jsonl(args.evidence)
    if args.limit:
        rows = rows[: args.limit]

    assignments = [classify_one(row, taxonomy) for row in rows]
    write_outputs(args.out_dir, taxonomy, assignments)
    print(f"[INFO] total servers: {len(assignments)}")
    print(f"[INFO] assignments: {args.out_dir / 'server_assignments.jsonl'}")
    print(f"[INFO] summary: {args.out_dir / 'type_count_summary.md'}")
    print(f"[INFO] review queue: {args.out_dir / 'review_queue.csv'}")
    print()
    print((args.out_dir / "type_count_summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
