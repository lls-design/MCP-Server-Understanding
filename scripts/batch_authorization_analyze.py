import os
import argparse
import random
import subprocess
import sys
import time
import json
import concurrent.futures
from pathlib import Path
from typing import List, Dict


def get_static_analyzed_projects(results_dir: str) -> List[str]:
    """
    Determine whether static analysis is complete: results/<project>/call_graph.json exists.
    """
    p = Path(results_dir)
    if not p.exists():
        return []
    projects = []
    for item in p.iterdir():
        if not item.is_dir() or item.name.startswith("."):
            continue
        if (item / "call_graph.json").exists():
            projects.append(item.name)
    projects.sort()
    return projects


def read_project_list(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return [line.strip() for line in f if line.strip()]


def ensure_parent_dir(path: str):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def run_one(
    python_exe: str,
    authorization_script: str,
    project: str,
    servers_dir: str,
    results_dir: str,
    copilot_cmd: str,
    copilot_prompt_arg: str,
    timeout_sec: int,
) -> Dict:
    # Pass copilot_cmd via an environment variable to avoid argparse splitting.
    env = os.environ.copy()
    env["MCP_ANALYZE_COPILOT_CMD"] = copilot_cmd

    # Pass values that start with "-" using equals syntax to avoid argparse misparsing.
    copilot_arg_kv = f"--copilot_prompt_arg={copilot_prompt_arg}"

    cmd = [
        python_exe,
        authorization_script,
        "--project", project,
        "--servers_dir", servers_dir,
        "--results_dir", results_dir,
        copilot_arg_kv,
        "--timeout_sec", str(timeout_sec),
    ]

    p = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        env=env,
    )

    auth_path = os.path.join(results_dir, project, "authorization.json")
    analysis = ""
    if os.path.exists(auth_path):
        try:
            with open(auth_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            analysis = (data.get("analysis") or "").strip()
        except Exception:
            analysis = ""

    return {
        "project": project,
        "analysis": analysis,
        "authorization_json": auth_path if os.path.exists(auth_path) else None,
        "returncode": p.returncode,
        "stderr": p.stderr,
        "updated_at": int(time.time()),
    }


def load_fixed_summary(path: str) -> Dict:
    if not os.path.exists(path):
        return {"summary": {}, "items": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
            return data
    except Exception:
        pass
    return {"summary": {}, "items": []}


def save_fixed_summary(path: str, data: Dict):
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def upsert_item(items: List[Dict], new_item: Dict):
    project = new_item.get("project")
    for i, it in enumerate(items):
        if it.get("project") == project:
            items[i] = new_item
            return
    items.append(new_item)


def main():
    parser = argparse.ArgumentParser(description="Batch authorization analysis: find statically analyzed projects under results, call authorization_analyze.py, and write a fixed JSON summary")
    parser.add_argument("--results_dir", type=str, default="results")
    parser.add_argument("--servers_dir", type=str, default="Servers")
    parser.add_argument("--authorization_script", type=str, default="scripts/authorization_analyze.py")
    parser.add_argument("--python", type=str, default=sys.executable)

    # Fixed output file (standard JSON: summary + items list).
    parser.add_argument("--summary_file", type=str, default="tool_analyzer/authorization_summary.json",
                        help="Fixed summary file path (JSON). Default: tool_analyzer/authorization_summary.json")

    # Single-project mode.
    parser.add_argument("--project", type=str, default=None, help="Analyze only the specified project")
    parser.add_argument("--projects_file", type=str, default=None, help="Read project list from a file")
    parser.add_argument("--skip_existing_auth", action="store_true", help="Skip projects that already have authorization.json")

    # Selection strategy.
    parser.add_argument("--sample", type=int, default=None, help="Randomly sample N projects for analysis")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible sampling")
    parser.add_argument("--start_index", type=int, default=None, help="Start from project N (1-based)")
    parser.add_argument("--max_projects", type=int, default=None, help="Maximum number of projects to process")

    # Concurrency.
    parser.add_argument("--jobs", type=int, default=1, help="Number of projects to run concurrently")

    # Parameters passed to authorization_analyze.py.
    parser.add_argument("--copilot_cmd", type=str,
                        default="codex -c model_reasoning_effort=\"low\" -a never exec -m gpt-5.4-mini -s read-only --skip-git-repo-check --ephemeral --ignore-rules",
                        help="LLM command passed to authorization_analyze.py via MCP_ANALYZE_COPILOT_CMD")
    parser.add_argument("--copilot_prompt_arg", type=str, default="--prompt",
                        help="--copilot_prompt_arg passed to authorization_analyze.py")
    parser.add_argument("--timeout_sec", type=int, default=900,
                        help="--timeout_sec passed to authorization_analyze.py")

    args = parser.parse_args()

    if args.project:
        projects = [args.project]
    elif args.projects_file:
        projects = read_project_list(args.projects_file)
    else:
        projects = get_static_analyzed_projects(args.results_dir)
        if not projects:
            print("No statically analyzed projects found (requires results/<project>/call_graph.json)")
            return

        # start_index (1-based)
        if args.start_index is not None and args.start_index > 0:
            start0 = args.start_index - 1
            projects = projects[start0:] if start0 < len(projects) else []

        if args.max_projects is not None and args.max_projects > 0:
            projects = projects[:args.max_projects]

        if not projects:
            print("No projects to process after filtering")
            return

        # sample
        if args.sample is not None:
            if args.seed is not None:
                random.seed(args.seed)
            if args.sample < len(projects):
                projects = random.sample(projects, args.sample)

    if args.skip_existing_auth:
        projects = [
            project
            for project in projects
            if not (Path(args.results_dir) / project / "authorization.json").exists()
        ]

    total = len(projects)
    ok = 0
    fail = 0

    summary = load_fixed_summary(args.summary_file)

    print(f"Processing {total} projects; fixed summary will be written to: {args.summary_file}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        future_map = {
            executor.submit(
                run_one,
                args.python,
                args.authorization_script,
                prj,
                args.servers_dir,
                args.results_dir,
                args.copilot_cmd,
                args.copilot_prompt_arg,
                args.timeout_sec,
            ): prj
            for prj in projects
        }

        for idx, future in enumerate(concurrent.futures.as_completed(future_map), 1):
            prj = future_map[future]
            print(f"[{idx}/{total}] {prj}")

            res = future.result()

            if res["returncode"] == 0 and res["analysis"]:
                ok += 1
                upsert_item(summary["items"], {
                    "project": prj,
                    "analysis": res.get("analysis", "")
                })
            else:
                fail += 1
            if "analysis" not in res:
                print(f"!!! analysis not found for {prj}: {res}")
                exit(1)

    summary["summary"] = {
        "total": len(summary["items"]),
        "success": sum(1 for it in summary["items"] if (it.get("analysis") or "").strip()),
        "fail": sum(1 for it in summary["items"] if not (it.get("analysis") or "").strip()),
        "updated_at": int(time.time())
    }

    save_fixed_summary(args.summary_file, summary)

    print(f"done. success={ok}, fail={fail}, total={total}")


if __name__ == "__main__":
    main()
