import os
import json
import argparse
import subprocess
import shlex
import time
import re
import tempfile
from typing import Optional

PROMPT = """This project implements an **MCP Server** that integrates multiple tools and allows an **LLM-driven agent** to invoke them.

Your task is to analyze **whether and how authorization exists at the MCP Server level** when its tools invoke **external APIs or execute local commands**.

The analysis focuses **only on egress authority**: what real-world authority the MCP Server explicitly holds or exercises over **external systems**, and how that authority is obtained.

---

## 1. Scope of Analysis (Strict Boundary)

Analyze **only** the execution path:

> **A tool invocation request is received by the MCP Server → the tool is executed**

Anything outside this path (e.g., OS behavior, network configuration, deployment environment, infrastructure security) must **not** be considered.

---

## 2. Core Authorization Attribution Rule (Must Follow)

**Authorization is attributed to the MCP Server if and only if the MCP Server code OR the README provides direct evidence that the MCP Server explicitly participates in obtaining or exercising authority over an external system (egress).**

Evidence of MCP Server–level egress authorization exists when **either** of the following is evidenced:

1. **Credential or capability material explicitly flows through MCP Server code**, or
2. **MCP Server code explicitly initiates, configures, or invokes authentication / authorization APIs or flows** to obtain or manage access.

Credential or capability material includes (but is not limited to):

* Passwords, API keys, tokens, secrets
* Certificates, connection strings
* Pre-signed URLs or other capability-bearing artifacts
* Equivalent authentication or access inputs

If neither (1) nor (2) is evidenced in code, you may rely on **explicit README evidence** (e.g., documented required credentials or auth flows) to determine whether egress authorization exists.

---

## 3. What Counts as MCP Server–Level Authorization (Non-Exhaustive)

Authorization-related behavior refers to **any explicit mechanism by which the MCP Server gains, assumes, or exercises authority to interact with an external system**, including but not limited to:

* Reading credentials from configuration files or environment variables
* Requiring credentials to be configured for server startup or operation
* Passing credentials or credential-derived configuration to SDKs, clients, or APIs
* Constructing authentication material (e.g., headers, signatures, client configs)
* Explicitly invoking authentication or authorization APIs or flows, such as OAuth/OIDC token flows, cloud SDK token acquisition/assume-role APIs, or custom login/token exchange endpoints
* Executing tools unconditionally once such authority is established

**Credential pass-through and SDK-mediated authentication both count as authorization**, even if the MCP Server performs no validation beyond existence checks or enforces no per-request restrictions.

---

## 4. External SDKs and Auth APIs (Clarified Attribution)

Attribute authorization to the MCP Server **if and only if** MCP Server code **explicitly triggers or configures** authentication behavior (even when details are handled inside an SDK).

Examples include (non-exhaustive):

* Constructing or selecting a credential provider
* Invoking SDK login/auth/credential APIs
* Initiating token acquisition, refresh, or role-assumption flows
* Passing auth-related providers, callbacks, or signer objects
* **Explicitly constructing/selecting a “default credential provider” in code** (counts as MCP Server involvement even if the provider later resolves credentials via a standard chain)

Do **not** attribute authorization if authentication is handled **entirely implicitly** (e.g., SDKs or binaries auto-resolving credentials without MCP Server involvement).

> **Execution success alone is not evidence of MCP Server–level authorization.**

---

## 5. Explicitly Disallowed Reasoning (Hard Boundary)

**Do NOT attribute authorization to the MCP Server based on any of the following alone:**

* Operating system permissions or process identity
* File system access rights
* Network reachability, topology, or firewall configuration
* Transport-layer security (TLS / mTLS) by itself
* External tools or SDKs resolving credentials without MCP Server involvement
* The fact that a tool or command executes successfully

---

## 6. Output Requirements (Rich, Keyword-Safe, Egress-Only)

Produce a concise but rigorous report using exactly these fields:

* **Field A — EgressAuthorization (Primary):** **Exists** / **Does not exist**

  * Provide concrete evidence from code and/or README.

* **Field B — AuthorizationMechanism (Description):**

  * Explain how authority is obtained/exercised (in your own words).
  * You may use example tags (non-exhaustive): credential-based, auth-API–based, delegated/pass-through, SDK-mediated, unconstrained.

* **Field C — InternalConstraints:** **Constrained** / **Unconstrained** / **Fully trusted by default**

  * Describe what (if anything) limits tool execution or privilege use inside the MCP Server.

* **Field D — AuthorizationCategory (Open Taxonomy):**

  * Provide 1–3 short labels that best describe the project’s egress authorization pattern.
  * Labels are **not limited** to any predefined list.
  * Examples (non-exhaustive): “Static API key”, “Env-based secret”, “Single global credential”, “OAuth token refresh”, “Cloud assume-role”, “Per-tool scoped credentials”, “SDK default provider (explicitly selected)”.

* **Field E — EvidenceSummary (2–5 bullets):**

  * List the strongest evidence points (file/function names, config keys, relevant call sites).
  * Include where credentials come from and where they are applied in outgoing requests.

* **Field F — TrustBoundaryNotes (2–5 bullets):**

  * State trust assumptions and notable gaps (e.g., shared global key, no per-request gating, no scoping, broad tool power).
  * Do not mention OS/network as authorization.

Then output a final single-line conclusion:

* **Final Conclusion:**

  * If **Field A = Exists**, output exactly: **“Authorization exists.”**
  * If **Field A = Does not exist**, output exactly: **“No authorization.”**

**Rule:** The **Final Conclusion must match Field A exactly** and must not introduce new qualifiers or contradictions.
"""

def trim_to_field_a(text: str) -> str:
    if not text:
        return text
    m = re.search(r'Field A\s*[—-]\s*EgressAuthorization', text)
    if not m:
        m = re.search(r'Field A\s*[—-]\s*', text)
    if m:
        return text[m.start():].strip()
    return text.strip()

def is_codex_command(cmd_parts: list[str]) -> bool:
    if not cmd_parts:
        return False
    executable = os.path.basename(cmd_parts[0])
    if executable == "codex":
        return True
    return len(cmd_parts) >= 2 and executable == "node" and "codex" in cmd_parts[1]


def run_llm_in_dir(
    prompt: str,
    cwd: str,
    llm_cmd: str,
    prompt_arg: str,
    timeout_sec: int,
) -> dict:
    cmd_parts = shlex.split(llm_cmd)
    output_path: Optional[str] = None
    abs_cwd = os.path.abspath(cwd)
    if is_codex_command(cmd_parts):
        fd, output_path = tempfile.mkstemp(prefix="mcp_auth_codex_", suffix=".txt")
        os.close(fd)
        full_cmd = cmd_parts + ["-C", abs_cwd, "--output-last-message", output_path, prompt]
        run_cwd = abs_cwd
    else:
        full_cmd = cmd_parts + [prompt_arg, prompt]
        run_cwd = abs_cwd

    started = time.time()
    try:
        p = subprocess.run(
            full_cmd,
            cwd=run_cwd,
            text=True,
            input="",
            capture_output=True,
            timeout=timeout_sec,
        )
        elapsed = time.time() - started
        final_output = p.stdout
        if output_path and os.path.exists(output_path):
            with open(output_path, "r", encoding="utf-8", errors="ignore") as f:
                final_output = f.read()
    finally:
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass

    return {
        "cmd": full_cmd,
        "cwd": run_cwd,
        "returncode": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
        "final_output": final_output,
        "elapsed_sec": elapsed,
    }


def save_result(results_dir: str, project: str, payload: dict) -> str:
    out_dir = os.path.join(results_dir, project)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "authorization.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Analyze authorization for one MCP Server project by launching Codex/Copilot CLI in the project directory")
    parser.add_argument("--project", type=str, required=True, help="Project name (directory name under Servers)")
    parser.add_argument("--servers_dir", type=str, default="Servers", help="Server project directory (default: Servers)")
    parser.add_argument("--results_dir", type=str, default="results", help="Results directory (default: results)")

    # Use the Codex CLI mini model by default; keep parameter names for compatibility with existing batch scripts.
    parser.add_argument("--copilot_cmd", type=str,
                        default="codex -c model_reasoning_effort=\"low\" -a never exec -m gpt-5.4-mini -s read-only --skip-git-repo-check --ephemeral --ignore-rules",
                        help="LLM CLI command (may include options). Defaults to the Codex mini model")
    parser.add_argument("--copilot_prompt_arg", type=str, default="-p",
                        help="Copilot CLI prompt argument (default: -p, equivalent to --prompt)")
    parser.add_argument("--timeout_sec", type=int, default=900, help="Timeout in seconds (default: 900)")

    args = parser.parse_args()

    # Environment variable takes precedence; batch scripts pass through this variable.
    args.copilot_cmd = os.getenv("MCP_ANALYZE_COPILOT_CMD", args.copilot_cmd)

    project_dir = os.path.join(args.servers_dir, args.project)
    if not os.path.isdir(project_dir):
        payload = {
            "project": args.project,
            "generated_at": int(time.time()),
            "error": f"project dir not found: {project_dir}",
        }
        out_path = save_result(args.results_dir, args.project, payload)
        print(f"✗ project not found, saved: {out_path}")
        return

    try:
        copilot = run_llm_in_dir(
            prompt=PROMPT,
            cwd=project_dir,
            llm_cmd=args.copilot_cmd,
            prompt_arg=args.copilot_prompt_arg,
            timeout_sec=args.timeout_sec,
        )
        
        raw = (copilot.get("final_output") or copilot.get("stdout") or "")
        cleaned = trim_to_field_a(raw)

        payload = {
            "project": args.project,
            "generated_at": int(time.time()),
            "servers_path": project_dir,
            "copilot": {
                "cmd": copilot["cmd"],
                "cwd": copilot["cwd"],
                "returncode": copilot["returncode"],
                "stderr": copilot["stderr"],
                "elapsed_sec": copilot["elapsed_sec"],
            },
            "analysis": cleaned,
        }

        out_path = save_result(args.results_dir, args.project, payload)
        if payload["analysis"]:
            print(f"✓ saved: {out_path}")
        else:
            print(f"✗ empty analysis, saved: {out_path}")

    except subprocess.TimeoutExpired:
        payload = {
            "project": args.project,
            "generated_at": int(time.time()),
            "servers_path": project_dir,
            "error": "copilot timeout",
            "timeout_sec": args.timeout_sec,
            "copilot_cmd": args.copilot_cmd,
        }
        out_path = save_result(args.results_dir, args.project, payload)
        print(f"✗ copilot timeout, saved: {out_path}")
    except FileNotFoundError as e:
        payload = {
            "project": args.project,
            "generated_at": int(time.time()),
            "servers_path": project_dir,
            "error": f"copilot command not found: {e}",
            "copilot_cmd": args.copilot_cmd,
        }
        out_path = save_result(args.results_dir, args.project, payload)
        print(f"✗ copilot not found, saved: {out_path}")


if __name__ == "__main__":
    main()
