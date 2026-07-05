import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECTS_FILE = Path("/home/lls/MCP_Analyze/projects_by_stars.txt")
SERVERS_DIR = Path("/home/lls/MCP_Analyze/Servers")
OUTPUT_JSONL = Path("/home/lls/MCP_Analyze/copilot_sensitive_api_scan.jsonl")

EXTRACT_PROMPT_TEMPLATE = r"""
You are working inside the root directory of a single project. Treat the current working directory as the entire project and analyze the whole codebase, not just the README or a single file.

Task: Stage 1 only — extract externally sensitive privilege-related interfaces used in this project.

Selection rules:
1. Include externally sensitive interfaces actually used by this project.
2. Exclude ordinary non-sensitive APIs.
3. Prioritize:
   - external HTTP / REST / GraphQL / RPC / SDK calls
   - cloud, storage, database, messaging, email, payment, blockchain
   - browser automation, system command execution, high-impact filesystem operations
   - authentication, tokens, API keys, OAuth, sessions, credential injection flows
4. For each interface include concrete usage evidence.
5. Return as many as possible for this project. <<LIMIT_RULE>>

Output STRICT JSON only:
{
  "interfaces": [
    {
      "api_name": "interface name",
      "why_sensitive": "short explanation",
      "code_evidence": [
        {
          "file": "relative/path",
          "symbol": "symbol name",
          "summary": "how this location uses the interface"
        }
      ]
    }
  ],
  "notes": ["optional note"]
}
""".strip()

VERIFY_PROMPT_TEMPLATE = r"""
You are validating ONE interface candidate from a project.

Candidate interface JSON:
<<CANDIDATE_JSON>>

Task: Search official documentation and decide whether there is explicit responsibility language.

Count as strong hit only if documentation clearly attributes security/safe usage responsibility to:
- developer / caller / integrator / application / user
AND the responsibility is tied to authorization, permission scope, access control, or resource protection in this interface context.

Do NOT count as strong hit:
- coding guidelines / secure coding tips (e.g., parameterized queries, SQL injection prevention best practices)
- generic input validation best practices
- generic token/API key management advice without explicit authorization responsibility assignment
- only says auth/token is required
- only says "use with caution" / "read security considerations"
- pricing / rate limit / quota notes

Output STRICT JSON only:
{
  "strong_hit": true,
  "matched_interface": {
    "api_name": "interface name",
    "why_sensitive": "why this is sensitive",
    "code_evidence": [
      {
        "file": "relative/path",
        "symbol": "symbol name",
        "summary": "how used"
      }
    ],
    "doc_url": "official documentation URL",
    "doc_quote": "exact quote or near-exact quote",
    "responsibility_type": "developer_responsible | caller_responsible | integrator_responsible | application_must_enforce | user_must_ensure",
    "reason": "why this quote is explicit responsibility language"
  },
  "checked_interface": {
    "api_name": "interface name",
    "why_sensitive": "short explanation",
    "doc_url": "URL or empty string",
    "result": "strong_hit | weak_hint | no_hit"
  }
}
""".strip()


def read_projects(file_path: Path) -> list[str]:
    projects: list[str] = []
    with file_path.open("r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            if idx == 0 and line.lower().startswith("project"):
                continue
            parts = line.split("\t")
            if not parts:
                continue
            project = parts[0].strip()
            if project:
                projects.append(project)
    return projects


def load_scanned_projects(path: Path) -> set[str]:
    scanned: set[str] = set()
    if not path.exists():
        return scanned
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            project = str(obj.get("project") or "").strip()
            if project:
                scanned.add(project)
    return scanned


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}

    try:
         return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return {}


def run_copilot_prompt(
    project_dir: Path,
    copilot_cmd: str,
    copilot_prompt_arg: str,
    timeout_sec: int,
    prompt: str,
) -> dict[str, Any]:
    cmd = shlex.split(copilot_cmd) + [copilot_prompt_arg, prompt]
    started = time.time()

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(project_dir),
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        elapsed = time.time() - started
        parsed = extract_json(proc.stdout)

        return {
            "project_dir": str(project_dir),
            "returncode": proc.returncode,
            "elapsed_sec": round(elapsed, 2),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "parsed": parsed,
            "error": None,
        }
    except subprocess.TimeoutExpired:
        elapsed = time.time() - started
        return {
            "project_dir": str(project_dir),
            "returncode": 124,
            "elapsed_sec": round(elapsed, 2),
            "stdout": "",
            "stderr": "copilot timeout",
            "parsed": {},
            "error": "timeout",
        }
    except FileNotFoundError as e:
        return {
            "project_dir": str(project_dir),
            "returncode": 127,
            "elapsed_sec": 0,
            "stdout": "",
            "stderr": str(e),
            "parsed": {},
            "error": "copilot_not_found",
        }


def _normalize_interface_candidates(parsed: dict[str, Any], max_apis: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not isinstance(parsed, dict):
        return candidates

    raw = parsed.get("interfaces")
    if not isinstance(raw, list):
        raw = parsed.get("checked_interfaces")
    if not isinstance(raw, list):
        raw = parsed.get("matched_interfaces")
    if not isinstance(raw, list):
        return candidates

    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        api_name = str(item.get("api_name") or "").strip()
        if not api_name:
            continue
        key = api_name.lower()
        if key in seen:
            continue
        seen.add(key)
        candidate = {
            "api_name": api_name,
            "why_sensitive": str(item.get("why_sensitive") or "").strip(),
            "code_evidence": item.get("code_evidence") if isinstance(item.get("code_evidence"), list) else [],
        }
        candidates.append(candidate)

    if max_apis > 0:
        return candidates[:max_apis]
    return candidates


def run_copilot(
    project: str,
    project_dir: Path,
    copilot_cmd: str,
    copilot_prompt_arg: str,
    timeout_sec: int,
    max_apis: int,
) -> dict[str, Any]:
    limit_rule = (
        f"Return at most {max_apis} interfaces." if max_apis > 0 else "No fixed upper limit."
    )
    extract_prompt = EXTRACT_PROMPT_TEMPLATE.replace("<<LIMIT_RULE>>", limit_rule)
    stage1 = run_copilot_prompt(
        project_dir=project_dir,
        copilot_cmd=copilot_cmd,
        copilot_prompt_arg=copilot_prompt_arg,
        timeout_sec=timeout_sec,
        prompt=extract_prompt,
    )
    stage1_parsed = stage1.get("parsed") or {}
    interfaces = _normalize_interface_candidates(stage1_parsed, max_apis=max_apis)

    matched_interfaces: list[dict[str, Any]] = []
    checked_interfaces: list[dict[str, Any]] = []
    notes: list[str] = []
    if not interfaces:
        notes.append("No interface candidates extracted in Stage 1.")

    for candidate in interfaces:
        verify_prompt = VERIFY_PROMPT_TEMPLATE.replace(
            "<<CANDIDATE_JSON>>",
            json.dumps(candidate, ensure_ascii=False),
        )
        stage2 = run_copilot_prompt(
            project_dir=project_dir,
            copilot_cmd=copilot_cmd,
            copilot_prompt_arg=copilot_prompt_arg,
            timeout_sec=timeout_sec,
            prompt=verify_prompt,
        )
        parsed = stage2.get("parsed") or {}
        if not isinstance(parsed, dict):
            parsed = {}

        checked = parsed.get("checked_interface")
        if isinstance(checked, dict):
            checked_interfaces.append(
                {
                    "api_name": str(checked.get("api_name") or candidate.get("api_name") or "").strip(),
                    "why_sensitive": str(checked.get("why_sensitive") or candidate.get("why_sensitive") or "").strip(),
                    "doc_url": str(checked.get("doc_url") or "").strip(),
                    "result": str(checked.get("result") or "").strip() or "no_hit",
                }
            )
        else:
            checked_interfaces.append(
                {
                    "api_name": str(candidate.get("api_name") or "").strip(),
                    "why_sensitive": str(candidate.get("why_sensitive") or "").strip(),
                    "doc_url": "",
                    "result": "no_hit",
                }
            )

        if parsed.get("strong_hit") is True:
            matched = parsed.get("matched_interface")
            if isinstance(matched, dict):
                if not matched.get("api_name"):
                    matched["api_name"] = candidate.get("api_name")
                if not matched.get("why_sensitive"):
                    matched["why_sensitive"] = candidate.get("why_sensitive")
                if not isinstance(matched.get("code_evidence"), list):
                    matched["code_evidence"] = candidate.get("code_evidence") or []
                matched_interfaces.append(matched)

    elapsed = round(float(stage1.get("elapsed_sec") or 0), 2)
    parsed_project = {
        "hit": len(matched_interfaces) > 0,
        "hit_count": len(matched_interfaces),
        "matched_interfaces": matched_interfaces,
        "checked_interfaces": checked_interfaces,
        "notes": notes,
        "extracted_interface_count": len(interfaces),
    }
    return {
        "project": project,
        "project_dir": str(project_dir),
        "returncode": stage1.get("returncode", 0),
        "elapsed_sec": elapsed,
        "stdout": "",
        "stderr": stage1.get("stderr", ""),
        "parsed": parsed_project,
        "extracted_interfaces": interfaces,
        "error": stage1.get("error"),
    }


def _is_valid_matched_interface(item: Any) -> bool:
    if not isinstance(item, dict):
        return False

    api_name = str(item.get("api_name") or "").strip()
    doc_url = str(item.get("doc_url") or "").strip()
    doc_quote = str(item.get("doc_quote") or "").strip()
    # Accept both keys for compatibility with different prompt versions.
    judgment = str(
        item.get("responsibility_type")
        or item.get("responsibility_judgment")
        or ""
    ).strip()

    reason = str(item.get("reason") or "").strip()
    if not api_name or not doc_url or not doc_quote:
        return False

    if judgment not in {
        "developer_responsible",
        "caller_responsible",
        "integrator_responsible",
        "user_must_ensure",
        "application_must_enforce",
    }:
        return False

    combined = f"{api_name}\n{doc_quote}\n{reason}".lower()
    noise_patterns = (
        "parameterized quer",
        "sql injection",
        "never use `%`",
        "never use % or +",
        "coding guideline",
        "best practice",
        "input validation",
        "sanitize input",
        "keep your token secret",
        "token storage",
        "protect your api key",
    )
    if any(p in combined for p in noise_patterns):
        return False

    authz_keywords = (
        "authorization",
        "access control",
        "permission",
        "scope",
        "claims",
        "role",
        "resource access",
        "application must enforce",
        "caller must ensure",
        "developer is responsible",
    )
    return any(k in combined for k in authz_keywords)


def get_valid_matched_interfaces(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(parsed, dict):
        return []

    matched_many = parsed.get("matched_interfaces")
    if isinstance(matched_many, list):
        return [item for item in matched_many if _is_valid_matched_interface(item)]

    matched_one = parsed.get("matched_interface")
    if isinstance(matched_one, dict) and _is_valid_matched_interface(matched_one):
        return [matched_one]

    return []


def is_strong_hit(parsed: dict[str, Any]) -> bool:
    if not isinstance(parsed, dict):
        return False
    if parsed.get("hit") is not True:
        return False

    return bool(get_valid_matched_interfaces(parsed))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Call Copilot project by project to audit externally sensitive interface documentation; stop on the first hit."
    )
    parser.add_argument("--projects-file", default=str(PROJECTS_FILE))
    parser.add_argument("--servers-dir", default=str(SERVERS_DIR))
    parser.add_argument("--output", default=str(OUTPUT_JSONL))
    parser.add_argument(
        "--copilot-cmd",
        default="copilot --model gpt-5-mini --allow-all-tools --allow-all-paths -s",
        help="Copilot CLI command",
    )
    parser.add_argument(
        "--copilot-prompt-arg",
        default="-p",
        help="Copilot prompt argument, commonly -p or --prompt",
    )
    parser.add_argument("--start", type=int, default=1, help="Start from project number N, 1-based")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of projects to scan; 0 means unlimited")
    parser.add_argument("--project", type=str, default="", help="Scan only the specified project; takes precedence over --start/--limit")
    parser.add_argument("--timeout", type=int, default=1200, help="Timeout in seconds for a single project")
    parser.add_argument("--max-apis", type=int, default=0, help="Maximum number of key interfaces to check per project; 0 means unlimited")
    parser.add_argument("--resume", action="store_true", help="Skip projects already scanned in output")
    parser.add_argument("--debug-candidates", action="store_true", help="Print candidate interfaces extracted in Stage 1")
    parser.add_argument("--debug-project", type=str, default="", help="Print debug candidate interfaces only for the specified project")
    args = parser.parse_args()

    projects = read_projects(Path(args.projects_file))
    if not projects:
        print("No project list was read.", file=sys.stderr)
        sys.exit(1)

    if args.project.strip():
        selected = [args.project.strip()]
        start_idx = 0
    else:
        start_idx = max(args.start - 1, 0)
        selected = projects[start_idx:]
        if args.limit > 0:
            selected = selected[:args.limit]

    scanned = load_scanned_projects(Path(args.output)) if args.resume else set()

    print(f"Total projects: {len(projects)}")
    print(f"Candidate projects in this run: {len(selected)}")
    if scanned:
        print(f"Already scanned projects: {len(scanned)}")

    selected_total = len(selected)
    for idx, project in enumerate(selected, start=1):
        if project in scanned:
            print(f"[{idx}/{selected_total}] Skipping already scanned project: {project}")
            continue

        project_dir = Path(args.servers_dir) / project
        if not project_dir.is_dir():
            record = {
                "project": project,
                "hit": False,
                "error": f"project dir not found: {project_dir}",
                "timestamp": int(time.time()),
            }
            append_jsonl(Path(args.output), record)
            print(f"[{idx}/{selected_total}] Directory does not exist: {project}")
            continue

        print(f"\n[{idx}/{selected_total}] Starting scan: {project}")
        result = run_copilot(
            project=project,
            project_dir=project_dir,
            copilot_cmd=args.copilot_cmd,
            copilot_prompt_arg=args.copilot_prompt_arg,
            timeout_sec=args.timeout,
            max_apis=args.max_apis,
        )

        parsed = result.get("parsed") or {}
        extracted_interfaces = result.get("extracted_interfaces") or []
        record = {
            "project": project,
            "timestamp": int(time.time()),
            "project_dir": str(project_dir),
            "returncode": result["returncode"],
            "elapsed_sec": result["elapsed_sec"],
            "error": result["error"],
            "stderr": result["stderr"],
            "parsed": parsed,
        }
        append_jsonl(Path(args.output), record)

        should_debug = args.debug_candidates and (
            not args.debug_project or args.debug_project == project
        )
        if should_debug:
            print(f"[debug] Stage1 extracted_interface_count: {len(extracted_interfaces)}")
            for i, item in enumerate(extracted_interfaces, start=1):
                print(f"[S1-{i}] api_name: {item.get('api_name')}")
                print(f"       why_sensitive: {item.get('why_sensitive')}")
            checked = parsed.get("checked_interfaces")
            if isinstance(checked, list):
                print(f"[debug] Stage2 checked_interface_count: {len(checked)}")
                for i, item in enumerate(checked, start=1):
                    print(f"[S2-{i}] api_name: {item.get('api_name')} | result: {item.get('result')}")

        if is_strong_hit(parsed):
            matched_many = get_valid_matched_interfaces(parsed)

            print("\n[hit] Current project analysis completed and a matching interface was found; stopping subsequent scans.")
            print(f"project: {project}")
            print(f"hit_count: {len(matched_many)}")
            for i, matched in enumerate(matched_many, start=1):
                print(f"[{i}] api_name: {matched.get('api_name')}")
                print(f"    doc_url: {matched.get('doc_url')}")
                print(f"    doc_quote: {matched.get('doc_quote')}")
                print(f"    reason: {matched.get('reason')}")
            return

        print(f"[continue] No hit: {project}")

    print("\n[done] No matching project found.")


if __name__ == "__main__":
    main()
