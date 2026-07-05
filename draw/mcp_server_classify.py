#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Analyze all server functions in the Servers directory and use Copilot CLI + LLM to generate a final 10-category taxonomy.

Core flow:
1) Traverse all service directories under Servers and extract readable context such as README, config files, and directory structure.
2) Call Copilot CLI for each service and output structured analysis JSON with resumable execution.
3) Summarize all service analyses into candidate types by chunk.
4) Merge all candidate types into the final 10 categories and output taxonomy_k10.json.
"""

import argparse
import json
import os
import random
import re
import shlex
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any


# ---------------------------
# Basic utilities
# ---------------------------

def read_text_safely(path: Path, max_chars: int = 12000) -> str:
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
        return txt[:max_chars]
    except Exception:
        return ""


def try_parse_json(text: str) -> Any | None:
    if not text:
        return None

    cleaned = text.strip()
    cleaned = cleaned.replace("```json", "```")
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned[3:-3].strip()

    # Parse directly.
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Extract the first JSON object or array.
    obj_match = re.search(r"\{[\s\S]*\}", cleaned)
    arr_match = re.search(r"\[[\s\S]*\]", cleaned)
    candidates = []
    if obj_match:
        candidates.append(obj_match.group(0))
    if arr_match:
        candidates.append(arr_match.group(0))

    for c in candidates:
        try:
            return json.loads(c)
        except Exception:
            continue

    return None


def append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_jsonl_map(path: Path, key: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    if not path.exists():
        return result

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                k = obj.get(key)
                if isinstance(k, str) and k:
                    result[k] = obj
            except Exception:
                continue
    return result


def safe_int(v: Any) -> int | None:
    try:
        if isinstance(v, bool):
            return None
        return int(v)
    except Exception:
        return None


# ---------------------------
# Copilot invocation layer, following the authorization_analyze.py style.
# ---------------------------

class CopilotRunner:
    """
    Use the unified command form:
    copilot_cmd + copilot_prompt_arg + prompt
    Example:
    copilot --model gpt-5-mini --allow-all-tools --allow-all-paths -s  -p  "<prompt>"
    """

    def __init__(
        self,
        copilot_cmd: str,
        copilot_prompt_arg: str,
        timeout: int,
        retries: int,
        sleep_ms: int,
    ):
        self.copilot_cmd = copilot_cmd
        self.copilot_prompt_arg = copilot_prompt_arg
        self.timeout = timeout
        self.retries = retries
        self.sleep_ms = sleep_ms

    def run(self, prompt: str, cwd: str | None = None) -> str:
        last_err = ""
        cmd_parts = shlex.split(self.copilot_cmd)

        if not cmd_parts:
            raise RuntimeError("copilot_cmd is empty")

        full_cmd = cmd_parts + [self.copilot_prompt_arg, prompt]

        for i in range(self.retries):
            try:
                proc = subprocess.run(
                    full_cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )

                out = (proc.stdout or "").strip()
                err = (proc.stderr or "").strip()

                if proc.returncode == 0 and out:
                    return out

                last_err = f"rc={proc.returncode}, stdout={out[:240]}, stderr={err[:240]}"
            except subprocess.TimeoutExpired:
                last_err = f"timeout>{self.timeout}s"
            except Exception as e:
                last_err = str(e)

            time.sleep((self.sleep_ms / 1000.0) * (i + 1))

        raise RuntimeError(f"Copilot invocation failed: {last_err}")


# ---------------------------
# Data extraction
# ---------------------------

CANDIDATE_README = [
    "README.md", "readme.md", "README.MD",
    "README.txt", "readme.txt",
    "README", "readme",
]

CANDIDATE_META = [
    "package.json", "pyproject.toml", "requirements.txt",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
    "Dockerfile", ".env.example",
]


def collect_server_context(server_dir: Path, max_file_chars: int = 9000) -> dict:
    readme_text = ""
    for name in CANDIDATE_README:
        p = server_dir / name
        if p.exists() and p.is_file():
            readme_text = read_text_safely(p, max_chars=max_file_chars)
            if readme_text:
                break

    meta_texts: dict[str, str] = {}
    for name in CANDIDATE_META:
        p = server_dir / name
        if p.exists() and p.is_file():
            meta_texts[name] = read_text_safely(p, max_chars=3000)

    tree_items = []
    try:
        for root, dirs, files in os.walk(server_dir):
            rel_root = os.path.relpath(root, server_dir)
            depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
            if depth > 2:
                dirs[:] = []
                continue
            dirs[:] = sorted(dirs)[:30]
            files = sorted(files)[:50]
            tree_items.append(
                {
                    "root": rel_root,
                    "dirs": dirs,
                    "files": files,
                }
            )
            if len(tree_items) >= 80:
                break
    except Exception:
        pass

    return {
        "server_name": server_dir.name,
        "path": str(server_dir),
        "readme_excerpt": readme_text,
        "meta_files": meta_texts,
        "tree_excerpt": tree_items,
    }


def build_analysis_prompt(ctx: dict) -> str:
    return f"""
You are a senior technical architect. Analyze the server project below and output strict JSON only, with no Markdown and no extra explanation.

Requirements:
1) Identify the service's core functionality, target users, and typical scenarios.
2) Provide 3-8 capability tags as short phrases.
3) Provide 1-3 candidate type names for later clustering.
4) Set confidence as a floating-point value from 0 to 1.

Output JSON format:
{{
  "server_name": "...",
  "summary": "...",
  "target_users": ["..."],
  "use_cases": ["..."],
  "capabilities": ["..."],
  "candidate_types": ["..."],
  "confidence": 0.0
}}

Project information:
{json.dumps(ctx, ensure_ascii=False)}
""".strip()


def build_chunk_taxonomy_prompt(chunk_rows: list[dict], chunk_id: int) -> str:
    payload = []
    for r in chunk_rows:
        payload.append(
            {
                "server_name": r.get("server_name"),
                "summary": r.get("summary", ""),
                "capabilities": r.get("capabilities", []),
                "candidate_types": r.get("candidate_types", []),
            }
        )

    return f"""
You will receive a batch of server function analysis results. Summarize a candidate type system for this sample batch for later global merging.
Output strict JSON only.

Requirements:
- Output 12 to 20 candidate types.
- Each type must include: name, definition, keywords (3 to 8), and example_servers (<=8).
- Avoid synonymous duplicates as much as possible.
- Names should be concise and distinguishable.

Output format:
{{
  "chunk_id": {chunk_id},
  "candidate_types": [
    {{
      "name": "...",
      "definition": "...",
      "keywords": ["..."],
      "example_servers": ["..."]
    }}
  ]
}}

Data:
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def build_final_k10_prompt(all_candidates: list[dict], top_terms: list[str], total_servers: int) -> str:
    return f"""
You are a taxonomy design expert. Based on the candidate type collection, generate a final server-function taxonomy with exactly 10 categories.
Output strict JSON only, with no Markdown.

Constraints:
1) There must be exactly 10 categories, no more and no fewer.
2) Categories should be as mutually exclusive as possible and cover the corpus as completely as possible.
3) Names must be concise and definitions clear.
4) Each category must provide include_signals and exclude_signals for easier assignment.
5) Give each category an id: T01...T10.

Output format:
{{
  "total_servers": {total_servers},
  "types": [
    {{
      "id": "T01",
      "name": "...",
      "definition": "...",
      "keywords": ["..."],
      "include_signals": ["..."],
      "exclude_signals": ["..."]
    }}
  ]
}}

Full candidate type set:
{json.dumps(all_candidates, ensure_ascii=False)}

Global high-frequency terms for reference:
{json.dumps(top_terms, ensure_ascii=False)}
""".strip()


# ---------------------------
# Main flow
# ---------------------------

def discover_servers(servers_dir: Path) -> list[Path]:
    if not servers_dir.exists() or not servers_dir.is_dir():
        raise FileNotFoundError(f"Servers directory does not exist: {servers_dir}")
    dirs = [p for p in servers_dir.iterdir() if p.is_dir()]
    dirs.sort(key=lambda x: x.name.lower())
    return dirs


def collect_top_terms(analysis_rows: list[dict], topn: int = 120) -> list[str]:
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "are", "into",
        "server", "tool", "tools", "api", "mcp", "based", "using",
        "service", "system", "platform", "support", "used", "related",
    }
    cnt = Counter()
    for r in analysis_rows:
        text = " ".join(
            [
                str(r.get("summary", "")),
                " ".join(r.get("capabilities", []) if isinstance(r.get("capabilities"), list) else []),
                " ".join(r.get("candidate_types", []) if isinstance(r.get("candidate_types"), list) else []),
            ]
        ).lower()
        words = re.findall(r"[a-zA-Z\u4e00-\u9fff][a-zA-Z0-9_\-\u4e00-\u9fff]{1,30}", text)
        for w in words:
            if w in stop or len(w) <= 1:
                continue
            cnt[w] += 1
    return [w for w, _ in cnt.most_common(topn)]


def normalize_analysis(raw: Any, server_name: str) -> dict:
    if not isinstance(raw, dict):
        return {
            "server_name": server_name,
            "summary": "",
            "target_users": [],
            "use_cases": [],
            "capabilities": [],
            "candidate_types": [],
            "confidence": 0.0,
            "_parse_error": True,
        }

    return {
        "server_name": str(raw.get("server_name") or server_name),
        "summary": str(raw.get("summary") or ""),
        "target_users": raw.get("target_users") if isinstance(raw.get("target_users"), list) else [],
        "use_cases": raw.get("use_cases") if isinstance(raw.get("use_cases"), list) else [],
        "capabilities": raw.get("capabilities") if isinstance(raw.get("capabilities"), list) else [],
        "candidate_types": raw.get("candidate_types") if isinstance(raw.get("candidate_types"), list) else [],
        "confidence": float(raw.get("confidence") or 0.0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Servers and build k=10 taxonomy with Copilot CLI")
    parser.add_argument("--servers-dir", default="./Servers", help="Path to the Servers directory")
    parser.add_argument("--output-dir", default="./tool_analyzer", help="Output directory")

    # Reuse the invocation style from authorization_analyze.py.
    parser.add_argument(
        "--copilot-cmd",
        default="copilot --model gpt-5-mini --allow-all-tools --allow-all-paths -s",
        help="Copilot CLI command, optionally with flags",
    )
    parser.add_argument(
        "--copilot-prompt-arg",
        default="-p",
        help="Copilot prompt argument; default is -p",
    )

    parser.add_argument("--timeout", type=int, default=120, help="Timeout in seconds for one Copilot call")
    parser.add_argument("--retries", type=int, default=3, help="Number of retries after failure")
    parser.add_argument("--sleep-ms", type=int, default=300, help="Interval between calls in milliseconds")
    parser.add_argument("--chunk-size", type=int, default=350, help="Chunk size for candidate type generation")
    parser.add_argument("--sample-cap", type=int, default=0, help="Debug mode: process only the first N services; 0 means all")
    parser.add_argument("--shuffle", action="store_true", help="Whether to shuffle service order")
    args = parser.parse_args()

    # Support environment-variable override, consistent with authorization_analyze.py.
    args.copilot_cmd = os.getenv("MCP_ANALYZE_COPILOT_CMD", args.copilot_cmd)

    servers_dir = Path(args.servers_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    briefs_jsonl = output_dir / "server_briefs.jsonl"
    analysis_jsonl = output_dir / "server_analysis.jsonl"
    taxonomy_candidates_jsonl = output_dir / "taxonomy_candidates_chunks.jsonl"
    taxonomy_k10_json = output_dir / "taxonomy_k10.json"

    runner = CopilotRunner(
        copilot_cmd=args.copilot_cmd,
        copilot_prompt_arg=args.copilot_prompt_arg,
        timeout=args.timeout,
        retries=args.retries,
        sleep_ms=args.sleep_ms,
    )

    # Run a startup preflight check to avoid discovering CLI issues during a full run.
    try:
        smoke_prompt = 'Return only JSON: {"ok": true}'
        smoke_text = runner.run(smoke_prompt)
        smoke_obj = try_parse_json(smoke_text)
        if not isinstance(smoke_obj, dict):
            raise RuntimeError(f"Preflight returned non-JSON output: {smoke_text[:200]}")
        print("[INFO] Copilot CLI preflight passed")
    except Exception as e:
        raise RuntimeError(
            f"Copilot CLI preflight failed: {e}\n"
            f"Current copilot_cmd={args.copilot_cmd}\n"
            f"Please manually verify that the command is executable first."
        )

    # 1) Discover service directories.
    servers = discover_servers(servers_dir)
    if args.shuffle:
        random.shuffle(servers)
    if args.sample_cap and args.sample_cap > 0:
        servers = servers[:args.sample_cap]

    print(f"[INFO] discovered servers: {len(servers)}")

    # 2) Per-service analysis with resumability.
    done = load_jsonl_map(analysis_jsonl, "server_name")
    print(f"[INFO] already analyzed: {len(done)}")

    for idx, sd in enumerate(servers, start=1):
        name = sd.name
        if name in done:
            continue

        ctx = collect_server_context(sd)
        append_jsonl(briefs_jsonl, ctx)

        prompt = build_analysis_prompt(ctx)
        try:
            # Optionally run in the project directory, consistent with authorization_analyze.py.
            text = runner.run(prompt, cwd=str(sd))
            parsed = try_parse_json(text)
            row = normalize_analysis(parsed, name)
            if row.get("server_name") != name:
                row["server_name"] = name
            append_jsonl(analysis_jsonl, row)
            print(f"[OK] [{idx}/{len(servers)}] {name}")
        except Exception as e:
            err_row = {
                "server_name": name,
                "summary": "",
                "target_users": [],
                "use_cases": [],
                "capabilities": [],
                "candidate_types": [],
                "confidence": 0.0,
                "_error": str(e),
            }
            append_jsonl(analysis_jsonl, err_row)
            print(f"[ERR] [{idx}/{len(servers)}] {name}: {e}")

        time.sleep(args.sleep_ms / 1000.0)

    # 3) Read all analysis results.
    all_rows_map = load_jsonl_map(analysis_jsonl, "server_name")
    all_rows = list(all_rows_map.values())
    print(f"[INFO] total analysis rows: {len(all_rows)}")

    if not all_rows:
        raise RuntimeError("No usable analysis results are available; cannot generate taxonomy")

    # 4) Generate candidate types by chunk.
    existing_chunks = []
    if taxonomy_candidates_jsonl.exists():
        with taxonomy_candidates_jsonl.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    existing_chunks.append(json.loads(line))
                except Exception:
                    pass

    # Support both int and string forms such as "3".
    existing_chunk_ids = {
        cid
        for x in existing_chunks
        if isinstance(x, dict)
        for cid in [safe_int(x.get("chunk_id"))]
        if cid is not None
    }

    chunk_size = max(80, args.chunk_size)
    chunk_count = (len(all_rows) + chunk_size - 1) // chunk_size
    print(f"[INFO] taxonomy chunk count: {chunk_count}, chunk_size={chunk_size}")

    for cid in range(chunk_count):
        if cid in existing_chunk_ids:
            continue

        s = cid * chunk_size
        e = min((cid + 1) * chunk_size, len(all_rows))
        chunk_rows = all_rows[s:e]
        prompt = build_chunk_taxonomy_prompt(chunk_rows, cid)

        try:
            txt = runner.run(prompt)
            parsed = try_parse_json(txt)
            if not isinstance(parsed, dict):
                parsed = {
                    "chunk_id": cid,
                    "candidate_types": [],
                    "_parse_error": True,
                    "raw": txt[:2000],
                }
            parsed["chunk_id"] = cid
            append_jsonl(taxonomy_candidates_jsonl, parsed)
            print(f"[OK] chunk taxonomy {cid + 1}/{chunk_count}")
        except Exception as e:
            append_jsonl(
                taxonomy_candidates_jsonl,
                {
                    "chunk_id": cid,
                    "candidate_types": [],
                    "_error": str(e),
                },
            )
            print(f"[ERR] chunk taxonomy {cid + 1}/{chunk_count}: {e}")

        time.sleep(args.sleep_ms / 1000.0)

    # 5) Merge candidates into the final 10 categories.
    all_candidates = []
    with taxonomy_candidates_jsonl.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            arr = obj.get("candidate_types", [])
            if isinstance(arr, list):
                for item in arr:
                    if isinstance(item, dict) and item.get("name"):
                        all_candidates.append(item)

    top_terms = collect_top_terms(all_rows, topn=120)
    final_prompt = build_final_k10_prompt(
        all_candidates=all_candidates,
        top_terms=top_terms,
        total_servers=len(all_rows),
    )

    final_text = runner.run(final_prompt)
    final_json = try_parse_json(final_text)
    if not isinstance(final_json, dict):
        raise RuntimeError("Failed to parse the final 10-category JSON; check Copilot output format")

    types = final_json.get("types")
    if not isinstance(types, list):
        raise RuntimeError("Final result is missing the types array")
    if len(types) != 10:
        raise RuntimeError(f"Final type count is not 10; got {len(types)}. Rerun or increase retries.")

    taxonomy_k10_json.write_text(
        json.dumps(final_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[DONE] taxonomy saved: {taxonomy_k10_json}")


if __name__ == "__main__":
    main()
