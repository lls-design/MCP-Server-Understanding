import os
import json
import argparse
import time
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.llm_call import get_openai_client

dotenv.load_dotenv(".env")


PROMPT_TEMPLATE = """
You are given an MCP server egress-authorization analysis report with fields:

- Field A — EgressAuthorization: Exists / Does not exist
- Field B — AuthorizationMechanism
- Field C — InternalConstraints
- Field D — AuthorizationCategory (open labels)
- Field E — EvidenceSummary
- Field F — TrustBoundaryNotes

Task: Assign exactly one PrimaryType label (T0–T8) describing the server’s *egress authorization*.

Hard boundaries (must follow):
- Focus only on egress authorization (authority exercised over external systems).
- Ignore ingress authorization completely (do not mention caller authentication).
- Do not infer authorization from OS permissions, network reachability, TLS/mTLS, or “it works” unless explicitly evidenced in the provided fields.
- Use only evidence present in the provided fields; do not speculate.

PrimaryType labels (choose exactly one):
- T1: Static Token / API Key
- T2: Static Username / Password
- T3: Runtime Credential Injection (rare; evidence required)
- T4: Delegated Role-Scoped Token (issued/brokered/delegated + role/scope/claims)
- T5: OAuth 2.0 / OIDC Flow Orchestration
- T6: Multi-Credential / Per-Tool Scoped Authorization
- T7: Capability Artifact Authorization
- T8: Other (provide subtype)
- T0: No Authorization (EgressAuth: None)

Consistency / precedence rules:
- If Field A = Does not exist → PrimaryType must be T0.
- If Field A = Exists and there is explicit evidence of delegated/issued role- or scope-bearing tokens (e.g., token exchange/STS/assume-role/impersonation/acquire-token + role/scope/claims/audience) → PrimaryType must be T4.
- Choose T3 only when Field E/README explicitly shows credentials passed as tool-call inputs; otherwise prefer T1/T2/T4/T5/T6/T7/T8.

Here is the analysis report:
{analysis}

Output (STRICT JSON only; no markdown, no prose):
{{
  "type": "T#",
  "reason": "...",
  "subtype": "..." | null
}}

Output rules:
- "type" must be one of: "T1","T2","T3","T4","T5","T6","T7","T8","T0".
- "reason" must be one short paragraph (1–4 sentences) citing concrete evidence from Field E and/or README (file/function/config key mentions). Do not use OS/network reasoning.
- "subtype" must be null unless type == "T8". If type == "T8", subtype must be a short descriptive phrase (free text) naming the specific “Other” mechanism.

"""


# New classification type definitions (T0-T8).
PRIMARY_TYPES = ["T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]

# Type name mapping (label -> full name).
TYPE_NAME_MAP = {
    "T0": "No Authorization (EgressAuth: None)",
    "T1": "Static Token / API Key",
    "T2": "Static Username / Password",
    "T3": "Runtime Credential Injection (rare; evidence required)",
    "T4": "Delegated Role-Scoped Token (issued/brokered/delegated + role/scope/claims)",
    "T5": "OAuth 2.0 / OIDC Flow Orchestration",
    "T6": "Multi-Credential / Per-Tool Scoped Authorization",
    "T7": "Capability Artifact Authorization",
    "T8": "Other (provide subtype)",
    "Unknown": "Unknown Type"
}


def load_summary(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "items" in data:
        return data["items"]
    if isinstance(data, list):
        return data

    raise ValueError("Unsupported summary format. Expect {summary, items[]} or a list.")


def write_classification_to_authorization(results_dir: str, project: str, classification: Dict[str, Any]):
    """
    Write classification results back to authorization.json.
    """
    auth_path = os.path.join(results_dir, project, "authorization.json")
    if not os.path.exists(auth_path):
        return
    try:
        with open(auth_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    
    # Write new classification fields, including the full type name.
    data["primary_type"] = classification.get("type")
    data["primary_type_name"] = classification.get("type_name")
    data["classification_reason"] = classification.get("reason")
    data["classification_subtype"] = classification.get("subtype")
    
    # Keep the legacy category field for compatibility, using type as category.
    data["category"] = classification.get("type", "Unknown")
    
    with open(auth_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_json_from_response(response: str) -> Dict[str, Any]:
    """
    Extract a JSON object from an LLM response.
    Supports multiple formats: plain JSON, JSON in markdown code blocks, prefixed JSON, etc.
    """
    if not response:
        return {"type": "Unknown", "reason": "Empty response", "subtype": None}
    
    response = response.strip()
    
    # Try direct JSON parsing.
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # Try extracting from a markdown code block, including multiline content.
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to find a complete JSON object, supporting nesting from the first "{".
    brace_count = 0
    start_idx = -1
    for i, char in enumerate(response):
        if char == '{':
            if start_idx == -1:
                start_idx = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_idx != -1:
                json_str = response[start_idx:i+1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # Continue searching for the next JSON object.
                    start_idx = -1
                    brace_count = 0
    
    # If all parsing attempts fail, return a default value.
    return {
        "type": "Unknown",
        "reason": f"Failed to parse JSON from response: {response[:200]}",
        "subtype": None
    }


def validate_classification_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize classification results to ensure T0-T8 format.
    """
    valid_types = {"T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"}
    
    type_val = result.get("type", "").strip().upper()
    if type_val not in valid_types:
        return {
            "type": "Unknown",
            "type_name": TYPE_NAME_MAP.get("Unknown", "Unknown Type"),
            "reason": f"Invalid type: {type_val}. Expected one of {valid_types}",
            "subtype": None
        }
    
    reason = result.get("reason", "").strip()
    if not reason:
        reason = "No reason provided"
    
    subtype = result.get("subtype")
    if subtype is not None:
        subtype = str(subtype).strip()
        if not subtype:
            subtype = None
    
    # T8 must have a subtype; other types must have null subtype.
    if type_val == "T8" and subtype is None:
        subtype = "Unspecified other mechanism"
    elif type_val != "T8" and subtype is not None:
        subtype = None
    
    return {
        "type": type_val,
        "type_name": TYPE_NAME_MAP.get(type_val, f"{type_val}: Unknown"),
        "reason": reason,
        "subtype": subtype
    }


def generate_report(client, prompt: str, model: str) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        extra_body={"enable_thinking": False},
    )
    return (resp.choices[0].message.content or "").strip()


def load_fixed(path: str) -> Dict:
    if not os.path.exists(path):
        return {"summary": {}, "items": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "items" in data:
            return data
    except Exception:
        pass
    return {"summary": {}, "items": {}}


def save_fixed(path: str, data: Dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Classify authorization types from authorization summary results (qwen3-max-preview)")
    parser.add_argument("--input", "-i", type=str, required=True, help="Input summary JSON file path")
    parser.add_argument("--project", type=str, default=None, help="Classify only the specified project")
    parser.add_argument("--output", type=str, default="tool_analyzer/authorization_classified.json",
                        help="Fixed output file path (JSON)")
    parser.add_argument("--model", type=str, default="qwen3-max-preview", help="Model name (default: qwen3-max-preview)")
    parser.add_argument("--sleep", type=float, default=0.2, help="Seconds to sleep after each request to avoid rate limits")
    parser.add_argument("--results_dir", type=str, default="results", help="Results directory used to write back category")
    args = parser.parse_args()

    items = load_summary(args.input)
    if args.project:
        items = [it for it in items if (it.get("project") or "").strip() == args.project]

    total = len(items)
    done = 0
    print(f"total={total}")

    client = get_openai_client()

    store = load_fixed(args.output)
    if "items" not in store:
        store["items"] = {}

    for item in items:
        project = (item.get("project") or "").strip()
        analysis = (item.get("analysis") or "").strip()

        if not project or not analysis:
            continue

        done += 1
        print(f"[{done}/{total}] project={project}")

        prompt = PROMPT_TEMPLATE.format(analysis=analysis)
        report = generate_report(client, prompt, args.model)

        # Parse JSON-formatted classification results.
        raw_result = extract_json_from_response(report)
        classification = validate_classification_result(raw_result)

        # Overwrite the same project, saving type, type_name, reason, and subtype.
        store["items"][project] = {
            "project": project,
            "type": classification["type"],
            "type_name": classification["type_name"],
            "reason": classification["reason"],
            "subtype": classification["subtype"],
            "raw_response": report,
            "updated_at": int(time.time())
        }

        write_classification_to_authorization(args.results_dir, project, classification)

        time.sleep(args.sleep)

    # Summary counts by T0-T8 type.
    counts: Dict[str, int] = {}
    subtype_counts: Dict[str, Dict[str, int]] = {}  # Count subtypes by type.
    
    for _, item in store["items"].items():
        type_val = item.get("type", "Unknown")
        counts[type_val] = counts.get(type_val, 0) + 1
        
        # Count subtype values, meaningful only for T8.
        if type_val == "T8":
            subtype = item.get("subtype") or "Unspecified"
            if type_val not in subtype_counts:
                subtype_counts[type_val] = {}
            subtype_counts[type_val][subtype] = subtype_counts[type_val].get(subtype, 0) + 1

    store["summary"] = {
        "total": len(store["items"]),
        "model": args.model,
        "counts_by_type": counts,
        "subtype_counts": subtype_counts,
        "updated_at": int(time.time())
    }

    save_fixed(args.output, store)

    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
