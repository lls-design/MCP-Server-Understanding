#!/usr/bin/env python3
import argparse
import csv
import json
import os
import random
import re
import time
from pathlib import Path
from urllib import error, request


DEFAULT_ROOT = Path("/home/lls/MCP_Analyze")
DEFAULT_QWEN_MODEL = "qwen3.7-plus"
DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_PROJECTS_FILE = Path("tool_analyzer/final_success_projects.txt")

PERMISSION_CATEGORIES = [
    "File System Operations",
    "System Command Execution",
    "Network Access",
    "Database Access",
    "Database Management",
    "Browser Automation",
    "Process/Environment Access",
    "Authentication/Secrets Access",
    "Cloud/API Service Access",
    "Cloud Infrastructure Management",
    "Code Execution",
    "Specialized Domain Data Services",
    "Project Management Services",
    "Other",
    "None",
]

PERMISSION_COMPATIBILITY = {
    "Network Access": {
        "Network Access",
        "Cloud/API Service Access",
        "Specialized Domain Data Services",
        "Cloud Infrastructure Management",
    },
    "Cloud/API Service Access": {
        "Network Access",
        "Cloud/API Service Access",
        "Specialized Domain Data Services",
        "Cloud Infrastructure Management",
    },
    "Specialized Domain Data Services": {
        "Network Access",
        "Cloud/API Service Access",
        "Specialized Domain Data Services",
    },
    "Cloud Infrastructure Management": {
        "Network Access",
        "Cloud/API Service Access",
        "Cloud Infrastructure Management",
    },
    "Database Management": {"Database Management", "Database Access"},
    "Database Access": {"Database Management", "Database Access"},
}

SENSITIVE_PERMISSION_CATEGORIES = {
    "File System Operations",
    "System Command Execution",
    "Network Access",
    "Database Access",
    "Database Management",
    "Browser Automation",
    "Process/Environment Access",
    "Authentication/Secrets Access",
    "Cloud/API Service Access",
    "Cloud Infrastructure Management",
    "Code Execution",
    "Specialized Domain Data Services",
    "Project Management Services",
}

EXPLICIT_PERMISSION_DISCLOSURE_TERMS = {
    "file": ["file", "filesystem", "path", "directory", "readfile", "writefile"],
    "command": ["command", "shell", "exec", "spawn", "terminal", "run script"],
    "network": ["network", "http", "https", "api", "endpoint", "request", "websocket", "url", "interface"],
    "database": ["database", "db", "sql", "query", "table", "record"],
    "auth": ["auth", "token", "key", "secret", "credential", "oauth"],
    "cloud": ["aws", "s3", "gcp", "azure", "cloud", "kubernetes"],
    "browser": ["browser", "page", "dom", "webpage"],
}

BUSINESS_WRITE_TERMS = {
    "create", "update", "set", "delete", "save", "add", "remove", "modify",
    "write", "complete", "status", "sync",
}

# Terms whose descriptions already strongly imply a sensitive behavior,
# even if they are not listed in EXPLICIT_PERMISSION_DISCLOSURE_TERMS.
IMPLIED_NETWORK_BEHAVIOR_TERMS = {
    "subscribe", "real-time", "realtime", "websocket", "stream", "streaming",
    "fetch", "download", "upload", "market data", "trading pair", "exchange",
}

IMPLIED_EXTERNAL_SERVICE_TERMS = {
    "approve", "sync", "import", "export", "integrate", "connect",
}


def categories_compatible(predicted_category, actual_category):
    if predicted_category == actual_category:
        return True

    return predicted_category in PERMISSION_COMPATIBILITY.get(
        actual_category, {actual_category}
    )


def load_json(path: Path):
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return json.load(f)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_dotenv(path: Path):
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_under_root(root: Path, path_value):
    path = Path(path_value)
    if path.is_absolute():
        return path
    return root / path


def load_successful_projects(root: Path, projects_file=DEFAULT_PROJECTS_FILE):
    success_file = resolve_under_root(root, projects_file)
    projects = [
        line.strip()
        for line in success_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    inventory_path = root / "tool_analyzer" / "tool_number_static_inventory_details.json"
    inventory = {}
    if inventory_path.exists():
        for row in load_json(inventory_path):
            inventory[row.get("project")] = row

    rows = []
    for project in projects:
        result_dir = root / "results" / project
        server_dir = root / "Servers" / project
        call_graph = result_dir / "call_graph_labeled.json"

        if not call_graph.exists():
            continue

        inv = inventory.get(project, {})
        rows.append({
            "project": project,
            "result_dir": str(result_dir),
            "server_dir": str(inv.get("server_dir", server_dir)),
            "accepted_tools": inv.get("accepted_tools", []),
        })

    return rows


def collect_nodes_for_tool(call_graph, source_node):
    visited = set()
    stack = list(source_node.get("successors", []))
    nodes = []

    while stack:
        node_id = str(stack.pop())
        if node_id in visited:
            continue
        visited.add(node_id)

        node = call_graph.get(node_id)
        if not node:
            continue

        nodes.append(node)
        stack.extend(node.get("successors", []))

    return nodes


def normalize_external_call(call):
    normalized = dict(call)
    api_name = normalized.get("api_name") or ""

    if api_name == "ws.on" or api_name.endswith(".ws.on"):
        normalized["category"] = "Network Access"
        normalized["summary"] = (
            'The api "ws.on" registers WebSocket event handlers for events such as '
            "open, message, error, close, and pong. It is part of real-time network "
            "communication rather than a local file system or cloud infrastructure "
            "management operation."
        )
        normalized["url"] = "https://github.com/websockets/ws/blob/master/doc/ws.md"

    return normalized


def parse_source_tool_name(des):
    if not isinstance(des, str):
        return ""

    text = des.strip()
    if text.startswith("Source "):
        return text.removeprefix("Source ").strip()
    if text.startswith("Source:"):
        return text.removeprefix("Source:").strip()

    return ""


def extract_actual_permissions(call_graph):
    tools = {}

    for node in call_graph.values():
        tool_name = parse_source_tool_name(node.get("des", ""))
        if not tool_name:
            continue

        called_nodes = collect_nodes_for_tool(call_graph, node)

        calls = []
        for child in called_nodes:
            if child.get("external_api") is True:
                calls.append(normalize_external_call({
                    "api_name": child.get("api_name"),
                    "category": child.get("category") or "Other",
                    "source_code": child.get("source_code"),
                    "path": child.get("path"),
                    "summary": child.get("external_api_summary"),
                    "url": child.get("external_api_url"),
                }))

        seen = set()
        deduped = []
        for call in calls:
            key = (
                call.get("api_name"),
                call.get("category"),
                call.get("source_code"),
                call.get("path"),
            )
            if key not in seen:
                seen.add(key)
                deduped.append(call)

        categories = sorted({
            call["category"]
            for call in deduped
            if call.get("category")
        })

        tools[tool_name] = {
            "source_node": node,
            "external_calls": deduped,
            "actual_categories": categories,
        }

    return tools


def normalize_text(s):
    return re.sub(r"\s+", " ", s or "").strip()


def extract_string_after_key(text, key):
    patterns = [
        rf"{key}\s*:\s*(['\"])(.*?)\1",
        rf"{key}\s*=\s*(['\"])(.*?)\1",
        rf"{key}\s*:\s*`(.*?)`",
        rf"{key}\s*=\s*`(.*?)`",
    ]

    for pat in patterns:
        m = re.search(pat, text, flags=re.DOTALL)
        if m:
            return normalize_text(m.group(2) if len(m.groups()) >= 2 else m.group(1))

    return ""


def extract_balanced_object_around(text, idx):
    start = text.rfind("{", 0, idx)
    if start == -1:
        start = max(0, idx - 1200)

    depth = 0
    in_str = None
    escaped = False

    for i in range(start, min(len(text), idx + 4000)):
        ch = text[i]

        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth <= 0 and i > idx:
                return text[start:i + 1]

    return text[max(0, idx - 1000): min(len(text), idx + 2500)]


def extract_parenthesized_call_around(text, idx):
    call_start = text.rfind(".tool", 0, idx)
    if call_start == -1:
        return ""

    paren_start = text.find("(", call_start, idx + 1)
    if paren_start == -1:
        return ""

    depth = 0
    in_str = None
    escaped = False

    for i in range(paren_start, min(len(text), paren_start + 8000)):
        ch = text[i]

        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[call_start:i + 1]

    return text[call_start:min(len(text), call_start + 3500)]


def extract_positional_tool_description(call_text, tool_name):
    pattern = re.compile(
        rf"\.tool\s*\(\s*(['\"`]){re.escape(tool_name)}\1\s*,\s*(['\"`])(?P<description>.*?)(?<!\\)\2",
        flags=re.DOTALL,
    )
    m = pattern.search(call_text)
    if not m:
        return ""

    return normalize_text(m.group("description"))


def omit_implementation_from_schema_context(schema_context):
    text = normalize_text(schema_context)
    if not text:
        return ""

    handler_markers = [
        ", withErrorHandling",
        " withErrorHandling(",
        "}, async ",
        ", async ",
        "=> {",
        ", function ",
    ]
    cut_positions = [text.find(marker) for marker in handler_markers if text.find(marker) != -1]
    if not cut_positions:
        return text[:2500]

    return text[:min(cut_positions)].rstrip(" ,") + " [implementation omitted]"


def build_model_visible_context(description_contexts):
    visible = []

    for ctx in description_contexts:
        visible.append({
            "source_file": ctx.get("source_file"),
            "tool_name_evidence": ctx.get("tool_name_evidence"),
            "description": ctx.get("description", ""),
            "input_schema_context": omit_implementation_from_schema_context(
                ctx.get("input_schema_context", "")
            ),
        })

    return dedupe_visible_contexts(visible)


def dedupe_visible_contexts(contexts):
    if not contexts:
        return []

    best_by_key = {}
    for ctx in contexts:
        key = (
            ctx.get("source_file"),
            ctx.get("tool_name_evidence"),
        )
        current = best_by_key.get(key)
        if current is None or context_quality(ctx) > context_quality(current):
            best_by_key[key] = ctx

    ranked = sorted(best_by_key.values(), key=context_quality, reverse=True)
    non_empty = [ctx for ctx in ranked if context_quality(ctx) > 0]
    return non_empty or ranked[:1]


def context_quality(ctx):
    description = normalize_text(ctx.get("description", ""))
    schema = normalize_text(ctx.get("input_schema_context", ""))
    score = 0
    if description:
        score += 10 + min(len(description), 200)
    if schema:
        score += 5 + min(len(schema), 200)
    return score


def primary_visible_descriptions(visible_contexts):
    descriptions = []
    for ctx in visible_contexts:
        description = normalize_text(ctx.get("description", ""))
        if description:
            descriptions.append(description)
    return descriptions


def has_implied_network_behavior(visible_contexts):
    text = visible_context_text(visible_contexts)
    return any(term in text for term in IMPLIED_NETWORK_BEHAVIOR_TERMS)


def has_implied_external_service_behavior(visible_contexts):
    text = visible_context_text(visible_contexts)
    return any(term in text for term in IMPLIED_EXTERNAL_SERVICE_TERMS)


def is_taxonomy_granularity_risk(visible_contexts, actual_categories, missing_sensitive):
    actual = {
        category for category in actual_categories
        if category in SENSITIVE_PERMISSION_CATEGORIES
    }
    if not actual:
        return False

    text = visible_context_text(visible_contexts)
    business_write = any(term in text for term in BUSINESS_WRITE_TERMS)
    db_categories = {"Database Access", "Database Management"}
    missing = set(missing_sensitive)

    # If the description has write semantics like create/update/set/save/delete,
    # but the ground truth only contains DB behavior, this is usually a
    # "business description vs. persistence implementation" taxonomy issue,
    # not permission hiding in the description.
    if business_write and actual <= db_categories:
        return True

    # If the model captured the business permission but only missed DB, this is
    # usually a label-granularity issue rather than invisible permissions.
    if business_write and missing and missing <= db_categories:
        return True

    return False


def build_thesis_claim_text(tool_name, predicted_categories, actual_sensitive, hidden_calls):
    predicted_text = predicted_categories or ["None"]
    actual_text = sorted(actual_sensitive)
    api_examples = ", ".join(
        f"`{call.get('api_name')}`" for call in hidden_calls[:3] if call.get("api_name")
    )
    api_clause = f" (for example, {api_examples})" if api_examples else ""

    return (
        f"The MCP description/schema of tool `{tool_name}` only expresses its functional purpose; "
        f"before invocation, the model can only infer permissions as {predicted_text}, "
        f"but the static call graph shows that it actually triggers {actual_text} permission behavior{api_clause}. "
        f"This shows that an LLM cannot reliably perceive underlying API and permission semantics from the description before selecting the tool."
    )


def build_interface_opacity_text(tool_name, predicted_categories, actual_sensitive, hidden_calls):
    api_examples = ", ".join(
        f"`{call.get('api_name')}`" for call in hidden_calls[:3] if call.get("api_name")
    )
    api_clause = f" (for example, {api_examples})" if api_examples else ""

    return (
        f"The description/schema of tool `{tool_name}` is sufficient for the model to infer permission categories "
        f"{predicted_categories or ['None']}, which match the actual categories {sorted(actual_sensitive)}; "
        f"however, the model still cannot see the concrete underlying APIs{api_clause}. "
        f"Therefore, this case is interface-level opacity and is not counted as a hidden-permission thesis case."
    )


def extract_python_function_docstring(text, tool_name):
    pattern = re.compile(
        rf"(?:async\s+def|def)\s+{re.escape(tool_name)}\s*\((?P<params>[^)]*)\)"
        rf"\s*(?:->[^\n:]*)?\s*:\s*"
        rf"(?:\"\"\"(?P<doc3>.*?)\"\"\"|'''(?P<doc1>.*?)''')?",
        flags=re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None

    doc = normalize_text(match.group("doc3") or match.group("doc1") or "")
    params = normalize_text(match.group("params") or "")
    schema_excerpt = ""
    if params:
        schema_excerpt = f"def {tool_name}({params})"

    args_match = re.search(r"Args:\s*(.*?)(?:\n\s*(?:Returns|Raises):|\Z)", doc, flags=re.DOTALL)
    if args_match:
        schema_excerpt = normalize_text(args_match.group(1))
        if params:
            schema_excerpt = f"{schema_excerpt}\nSignature: def {tool_name}({params})"

    return {
        "description": doc,
        "input_schema_context": schema_excerpt,
    }


def description_context_is_useful(context):
    return bool(
        normalize_text(context.get("description", ""))
        or normalize_text(context.get("input_schema_context", ""))
    )


def get_entry_point_file(project_meta, tool_name):
    result_dir = Path(project_meta.get("result_dir", ""))
    entry_points_path = result_dir / "entry_points.json"
    if not entry_points_path.exists():
        return None

    entry_points = load_json(entry_points_path)
    entry = entry_points.get(tool_name)
    if not entry:
        return None

    file_path = entry.get("file")
    if file_path:
        return Path(file_path)

    return None


def collect_description_search_files(project_meta, tool_name):
    files = []

    entry_point = get_entry_point_file(project_meta, tool_name)
    if entry_point:
        files.append(entry_point)

    for tool in project_meta.get("accepted_tools", []):
        if tool.get("canonical_name") != tool_name and tool.get("display_name") != tool_name:
            continue
        for file_path in tool.get("files", []):
            files.append(Path(file_path))

    server_dir = Path(project_meta.get("server_dir", ""))
    if server_dir.exists():
        files.extend(server_dir.rglob("*.ts"))
        files.extend(server_dir.rglob("*.js"))
        files.extend(server_dir.rglob("*.py"))

    deduped = []
    seen = set()
    for file_path in files:
        resolved = str(file_path.resolve()) if file_path.exists() else str(file_path)
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(file_path)

    return deduped[:400]


def extract_description_context_from_file(file_path: Path, tool_name: str):
    if not file_path or not file_path.exists() or not file_path.is_file():
        return []

    text = file_path.read_text(encoding="utf-8", errors="replace")
    contexts = []

    quoted_names = [
        f'"{tool_name}"',
        f"'{tool_name}'",
        f"`{tool_name}`",
    ]

    for q in quoted_names:
        start = 0
        while True:
            idx = text.find(q, start)
            if idx == -1:
                break

            call_text = extract_parenthesized_call_around(text, idx)
            positional_desc = extract_positional_tool_description(call_text, tool_name)
            if positional_desc:
                contexts.append({
                    "source_file": str(file_path),
                    "tool_name_evidence": q,
                    "description": positional_desc,
                    "raw_registration_context": normalize_text(call_text[:3500]),
                    "input_schema_context": normalize_text(call_text[:2500]),
                })
                start = idx + len(q)
                continue

            obj = extract_balanced_object_around(text, idx)
            desc = extract_string_after_key(obj, "description")

            input_schema = ""
            for schema_key in ["inputSchema", "schema", "parameters", "argsSchema"]:
                if schema_key in obj:
                    input_schema = obj[:2500]
                    break

            if desc or "description" in obj:
                contexts.append({
                    "source_file": str(file_path),
                    "tool_name_evidence": q,
                    "description": desc,
                    "raw_registration_context": normalize_text(obj[:3500]),
                    "input_schema_context": normalize_text(input_schema),
                })

            start = idx + len(q)

    python_doc = extract_python_function_docstring(text, tool_name)
    if python_doc and (python_doc.get("description") or python_doc.get("input_schema_context")):
        contexts.append({
            "source_file": str(file_path),
            "tool_name_evidence": f"def {tool_name}",
            "description": python_doc.get("description", ""),
            "raw_registration_context": python_doc.get("description", ""),
            "input_schema_context": python_doc.get("input_schema_context", ""),
        })

    return [ctx for ctx in contexts if description_context_is_useful(ctx)][:5]


def get_description_context(project_meta, tool_name):
    contexts = []

    for file_path in collect_description_search_files(project_meta, tool_name):
        found = extract_description_context_from_file(file_path, tool_name)
        if not found:
            continue

        contexts.extend(found)
        if any(description_context_is_useful(ctx) for ctx in found):
            break

    return contexts[:5]


def compatible_chat(api_key, base_url, model, messages, timeout=120, retries=3):
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "enable_thinking": False,
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            req = request.Request(url, data=data, headers=headers, method="POST")
            with request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return body["choices"][0]["message"]["content"]
        except error.HTTPError as e:
            response_body = e.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {e.code}: {response_body}"
            if attempt < retries:
                time.sleep(2 * attempt)
        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(2 * attempt)

    raise RuntimeError(f"LLM request failed: {last_error}")


def parse_json_object(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def compact_visible_context(description_contexts):
    descriptions = []
    schemas = []

    for ctx in description_contexts:
        description = normalize_text(ctx.get("description", ""))
        schema = normalize_text(ctx.get("input_schema_context", ""))

        if description and description not in descriptions:
            descriptions.append(description)
        if schema and schema not in schemas:
            schemas.append(schema[:1200])

    return {
        "descriptions": descriptions,
        "schema_excerpt": schemas[:2],
    }


def extract_actual_apis(actual):
    apis = []
    seen = set()

    for call in actual.get("external_calls", []):
        api_name = call.get("api_name") or "unknown"
        permission = call.get("category") or "Other"
        key = (permission, api_family(api_name))
        if key in seen:
            continue
        seen.add(key)

        apis.append({
            "api": api_name,
            "permission": permission,
        })

    return sorted(apis, key=lambda row: (row["permission"], row["api"]))


def group_apis_by_permission(actual_apis):
    grouped = {}

    for row in actual_apis:
        permission = row.get("permission") or "Other"
        api = row.get("api")
        if not api:
            continue
        grouped.setdefault(permission, [])
        if api not in grouped[permission]:
            grouped[permission].append(api)

    for permission in grouped:
        grouped[permission].sort()

    return grouped


def build_actual_permissions_with_apis(actual_apis, actual_permissions):
    grouped = group_apis_by_permission(actual_apis)

    return [
        {
            "permission": permission,
            "apis": grouped.get(permission, []),
        }
        for permission in actual_permissions
    ]


def empty_disclosure_judgment(tool_name):
    return {
        "tool": tool_name,
        "permissions": [],
    }


def judge_disclosure_from_description(
    tool_name,
    visible_context,
    actual_permissions,
    actual_apis,
    model_args,
):
    permission_behavior = build_actual_permissions_with_apis(actual_apis, actual_permissions)

    prompt = f"""
You evaluate MCP tool permission transparency using a severity-comparison test.

An LLM agent only sees the tool name, description, and input schema before calling a tool.
It cannot inspect the implementation.

We extracted actual permission categories and representative API behaviors from a static call graph.
Your job is NOT to judge whether specific API names are inferable.
Your job IS to decide whether each actual permission category is a HIGHER-IMPACT capability than the
tool description/schema reasonably implies, and therefore should have been disclosed but was not.

Tool name:
{tool_name}

Visible description/schema:
{json.dumps(visible_context, ensure_ascii=False, indent=2)}

Actual permission categories with representative APIs (ground truth, for behavior understanding only):
{json.dumps(permission_behavior, ensure_ascii=False, indent=2)}

Procedure:

Step 1 — Infer the baseline capability implied by the description/schema.
Estimate the highest user-visible effect a reasonable reader would expect, using this rough ordering
(from lower to higher impact):
  L0 supporting plumbing: authentication, authorization, token/session validation, identity checks
  L1 read/query/list/search/get/view/find/fetch/subscribe(stream)/receive
  L2 create/write/update/modify/persist/store/save/upsert/sync changes
  L3 delete/destructive/remove/send/post/execute/run/command

Step 2 — For EACH actual permission category, compare its real behavior (use representative APIs as hints)
against the baseline from Step 1.

Decision rules:

Mark inferable=true when ANY of the following holds:
  - The permission matches the baseline level or a clearly stated effect in the description
    (example: description says "delete note" and APIs include delete -> inferable=true).
  - The permission is L0 plumbing that is lower impact than the described main action and does not expand scope
    (example: description says "find/search notes" -> Identity/Authentication checks are inferable=true even if not
    explicitly mentioned, because they are expected gatekeeping before the described read).
  - The description explicitly names a mutating/destructive effect that matches the permission
    (save/create/update/delete/write/remove/send/execute/run/store/persist).
  - Read-oriented network/domain-data access when the tool purpose is fetch/get/list/search/subscribe/market-data
    and representative APIs show no extra mutation beyond that purpose.

Mark inferable=false ONLY when BOTH are true:
  (a) Elevated impact: this permission reflects a STRICTLY HIGHER impact level than the baseline implied by
      the description/schema (not merely missing implementation detail).
  (b) Material risk if unexpected: an agent could be surprised and harmed because the hidden capability exceeds
      what the description led them to expect.

Strong inferable=false patterns:
  - Read baseline but mutating/destructive side effect:
    description implies get/read/list/view/find, but APIs include update/insert/upsert/delete/sync/send/execute.
    Example: "Get the next task" + db.update -> inferable=false.
    Example: "Read email" + delete/send APIs -> inferable=false.
  - Business-language baseline but hidden persistence:
    description uses approve/begin/plan/set status/complete/mark without save/store/persist/write/database/file,
    but APIs show database/file mutation -> inferable=false.
    Examples: "Approve user stories" + db.insert; "Begin planning" + upsertProject; "Set status" + db.update.

Do NOT mark inferable=false for:
  - Authentication/Secrets Access or Identity and Access Management that only gates the described operation
    when the main described action is already at L1 or above (missing auth mention is NOT a disclosure failure).
  - Permissions at the same or lower impact level than the baseline (including supporting reads before writes
    when update/delete is already described).
  - Missing vendor/API names when the capability level itself is already implied.
  - Network/domain-data read access that matches a fetch/subscribe/search tool with no hidden mutation.

Important:
  - Missing lower-impact plumbing does NOT count as hidden permission failure.
  - Only elevated-impact capabilities count: the hidden behavior must be MORE dangerous than what the description led the agent to expect.
  - Use representative APIs to detect upgrade from read->write, write->delete, view->send, etc.; do not require API names in the description.

Classify every listed permission category exactly once.
Keep each reason to one concise English sentence explaining the severity comparison.

Return only valid JSON:
{{
  "tool": "{tool_name}",
  "permissions": [
    {{
      "permission": "Permission Category",
      "inferable": true,
      "reason": "one concise sentence"
    }}
  ]
}}

Use English only. No Markdown.
""".strip()

    raw = compatible_chat(
        api_key=model_args["api_key"],
        base_url=model_args["base_url"],
        model=model_args["model"],
        messages=[
            {
                "role": "system",
                "content": (
                    "Return concise valid JSON only. "
                    "Mark inferable=false only when an actual permission is strictly higher-impact than "
                    "the capability baseline implied by the visible description/schema. "
                    "Never mark inferable=false for authentication/identity plumbing alone."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        timeout=model_args["timeout"],
        retries=model_args["retries"],
    )
    return parse_json_object(raw)


def normalize_disclosure(actual_permissions, actual_apis, judgment):
    permission_rows = {
        row.get("permission"): row
        for row in judgment.get("permissions", [])
        if row.get("permission")
    }
    apis_by_permission = group_apis_by_permission(actual_apis)

    inferable_permissions = []
    not_inferable_permissions = []

    for permission in actual_permissions:
        row = permission_rows.get(permission, {})
        item = {
            "permission": permission,
            "apis": apis_by_permission.get(permission, []),
            "reason": row.get("reason", "Not classified by the model."),
        }
        if row.get("inferable") is True:
            inferable_permissions.append(item)
        else:
            not_inferable_permissions.append(item)

    return {
        "inferable_from_description": {
            "permissions": inferable_permissions,
        },
        "not_inferable_from_description": {
            "permissions": not_inferable_permissions,
        },
    }


def build_tool_result(project, tool_name, visible_context, actual_apis, actual_permissions, disclosure):
    not_inferable = disclosure["not_inferable_from_description"]
    has_hidden = bool(not_inferable["permissions"])

    return {
        "project": project,
        "tool": tool_name,
        "description": visible_context.get("descriptions", [""])[0] if visible_context.get("descriptions") else "",
        "actual_permissions": build_actual_permissions_with_apis(actual_apis, actual_permissions),
        "inferable_from_description": disclosure["inferable_from_description"],
        "not_inferable_from_description": not_inferable,
        "has_hidden_behavior": has_hidden,
    }


def predict_permissions_from_description(tool_name, description_contexts, model_args):
    prompt = f"""
You are an MCP tool permission-transparency evaluation assistant.

The research question is:
To what extent do MCP tool descriptions accurately reflect the underlying permission behaviors?
In particular, can large language models reliably interpret permission scopes based solely on these descriptions?

Important: you may only judge the permission scope from the tool name, tool description, input schema, or registration context.
You cannot see the real implementation code and must not assume implementation details.

Tool name:
{tool_name}

Visible tool description / schema / registration context:
{json.dumps(description_contexts, ensure_ascii=False, indent=2)}

Permission categories must be selected only from the following list:
{json.dumps(PERMISSION_CATEGORIES, ensure_ascii=False)}

Output JSON only, in this format:
{{
  "tool": "{tool_name}",
  "predicted_permissions": [
    {{
      "category": "File System Operations",
      "confidence": "high",
      "reason": "The description indicates that this tool needs to read or write files."
    }}
  ],
  "description_clarity": "clear | ambiguous | misleading | insufficient",
  "description_only_summary": "Brief judgment of the tool's capability scope based only on the description."
}}

If no sensitive permission is visible from the description, return category "None".
Do not output Markdown.
""".strip()

    raw = compatible_chat(
        api_key=model_args["api_key"],
        base_url=model_args["base_url"],
        model=model_args["model"],
        messages=[
            {"role": "system", "content": "You are a strict JSON generator. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        timeout=model_args["timeout"],
        retries=model_args["retries"],
    )
    return parse_json_object(raw)


def compare_permissions(prediction, actual_categories):
    predicted = {
        item.get("category")
        for item in prediction.get("predicted_permissions", [])
        if item.get("category") and item.get("category") != "None"
    }
    actual = {
        c for c in actual_categories
        if c and c != "None"
    }

    matched = sorted({
        actual_category
        for actual_category in actual
        if any(
            categories_compatible(predicted_category, actual_category)
            for predicted_category in predicted
        )
    })
    missing = sorted(actual - set(matched))
    extra = sorted({
        predicted_category
        for predicted_category in predicted
        if not any(
            categories_compatible(predicted_category, actual_category)
            for actual_category in actual
        )
    })

    if missing and extra:
        label = "mismatched"
    elif missing:
        label = "under_disclosed"
    elif extra:
        label = "over_disclosed"
    else:
        label = "matched"

    compatible_union_size = len(actual) + len(extra)
    return {
        "label": label,
        "predicted_categories": sorted(predicted),
        "actual_categories": sorted(actual),
        "matched_permissions": matched,
        "missing_permissions": missing,
        "extra_predicted_permissions": extra,
        "jaccard": len(matched) / compatible_union_size if compatible_union_size else 1.0,
        "precision": len(matched) / len(predicted) if predicted else (1.0 if not actual else 0.0),
        "recall": len(matched) / len(actual) if actual else 1.0,
    }


def api_family(api_name):
    name = (api_name or "").lower()

    if "findmany" in name or "findfirst" in name or "select" in name or ".query." in name:
        return "database.query"
    if "update" in name:
        return "database.update"
    if "insert" in name:
        return "database.insert"
    if "delete" in name:
        return "database.delete"
    if name == "ws.on" or name.endswith(".ws.on"):
        return "websocket.event_handler"

    return name


def visible_context_text(description_contexts):
    parts = []
    for ctx in description_contexts:
        parts.append(ctx.get("description", ""))
        parts.append(ctx.get("input_schema_context", ""))
    return normalize_text(" ".join(parts)).lower()


def disclosed_permission_terms(description_contexts):
    text = visible_context_text(description_contexts)
    matches = []

    for term_group, terms in EXPLICIT_PERMISSION_DISCLOSURE_TERMS.items():
        if any(term in text for term in terms):
            matches.append(term_group)

    return sorted(matches)


def has_business_write_signal(description_contexts):
    text = visible_context_text(description_contexts)
    return any(term in text for term in BUSINESS_WRITE_TERMS)


def concise_call_evidence(call):
    return {
        "api_name": call.get("api_name"),
        "api_family": api_family(call.get("api_name")),
        "permission": call.get("category"),
        "path": call.get("path"),
        "source_code": call.get("source_code"),
        "external_api_summary": call.get("summary"),
        "external_api_url": call.get("url"),
    }


def build_hidden_permission_case(tool_name, visible_contexts, prediction, actual, comparison):
    """
    Determine whether the case supports the paper thesis:
    before invoking an MCP tool, an LLM can only see the description/schema and
    cannot reliably perceive the underlying permission semantics.

    Hard requirements for entering the thesis case pool:
    1) The call graph contains sensitive permission behavior.
    2) The model misses at least one actual sensitive permission category.
    3) The visible description does not disclose permission-related technical terms and does not strongly imply that behavior.
    4) The case is not a false positive caused by taxonomy granularity, such as "business description vs. DB implementation".
    """
    actual_calls = [
        call for call in actual.get("external_calls", [])
        if call.get("category") in SENSITIVE_PERMISSION_CATEGORIES
    ]
    if not actual_calls:
        return _hidden_case_result(
            tool_name=tool_name,
            case_type="no_sensitive_external_behavior",
            rejection_reason="No clear sensitive permission behavior appears in the call graph.",
        )

    predicted_categories = comparison.get("predicted_categories", [])
    missing_permissions = set(comparison.get("missing_permissions", []))
    actual_categories = set(comparison.get("actual_categories", []))
    actual_sensitive = sorted(actual_categories & SENSITIVE_PERMISSION_CATEGORIES)
    missing_sensitive = sorted(missing_permissions & SENSITIVE_PERMISSION_CATEGORIES)

    disclosed_terms = disclosed_permission_terms(visible_contexts)
    descriptions = primary_visible_descriptions(visible_contexts)
    explicit_permission_disclosed = bool(disclosed_terms)
    predicted_none = not predicted_categories
    has_missing_sensitive = bool(missing_sensitive)
    label_matched = comparison.get("label") == "matched"
    taxonomy_granularity_risk = is_taxonomy_granularity_risk(
        visible_contexts, actual_categories, missing_sensitive
    )
    implied_network = has_implied_network_behavior(visible_contexts)
    implied_external_service = has_implied_external_service_behavior(visible_contexts)

    hidden_calls = []
    seen = set()
    for call in actual_calls:
        key = (call.get("category"), api_family(call.get("api_name")))
        if key in seen:
            continue
        seen.add(key)
        hidden_calls.append(concise_call_evidence(call))

    rejection_reasons = []
    if not descriptions:
        rejection_reasons.append("The visible description is empty, so it cannot prove that an ordinary business description masks permission behavior.")
    if label_matched or not has_missing_sensitive:
        rejection_reasons.append(
            "The model already covers the actual sensitive permission categories in the call graph; this is only interface-level opacity and does not support the claim that permission semantics are imperceptible."
        )
    if explicit_permission_disclosed:
        rejection_reasons.append(
            f"The description/schema directly contains permission-related terms: {disclosed_terms}."
        )
    if taxonomy_granularity_risk:
        rejection_reasons.append(
            "The description has clear business semantics such as write/approval/sync, while the ground truth is database implementation; this is a taxonomy-granularity risk."
        )
    if implied_network and actual_sensitive == ["Network Access"]:
        rejection_reasons.append(
            "The description already strongly implies network or real-time subscription behavior, so it cannot be counted as hidden network permission."
        )

    supports_thesis = not rejection_reasons
    notes = []

    if predicted_none:
        notes.append("The model did not identify any sensitive permission category from the description/schema alone.")
    elif has_missing_sensitive:
        notes.append(
            f"The model missed actual sensitive permissions: {missing_sensitive}."
        )

    if supports_thesis:
        if predicted_none:
            strength = "strong"
            suitability_score = 5
        else:
            strength = "strong"
            suitability_score = 4
        case_type = "genuine_hidden_permission_behavior"
        notes.append("Meets the paper-thesis filter: ordinary description, missed actual permission categories, and clear sensitive behavior in the call graph.")
    else:
        strength = "not_candidate"
        suitability_score = 0
        if taxonomy_granularity_risk:
            case_type = "taxonomy_granularity_risk"
        elif label_matched:
            case_type = "interface_opacity_only"
        elif explicit_permission_disclosed or implied_network:
            case_type = "permission_behavior_disclosed_or_implied"
        else:
            case_type = "does_not_support_thesis"

    description_summary = prediction.get("description_only_summary", "")
    is_interface_opacity = case_type == "interface_opacity_only"

    return {
        "supports_thesis": supports_thesis,
        "is_candidate": supports_thesis,
        "is_interface_opacity": is_interface_opacity,
        "strength": strength,
        "suitability_score": suitability_score,
        "case_type": case_type,
        "rejection_reasons": rejection_reasons,
        "visible_descriptions": descriptions,
        "visible_description_ordinary": (
            bool(descriptions) and not explicit_permission_disclosed
        ),
        "explicit_permission_disclosure_terms": disclosed_terms,
        "implied_network_behavior_in_description": implied_network,
        "implied_external_service_in_description": implied_external_service,
        "taxonomy_granularity_risk": taxonomy_granularity_risk,
        "comparison_label": comparison.get("label"),
        "actual_sensitive_permissions": actual_sensitive,
        "predicted_permissions_from_description": predicted_categories,
        "missing_sensitive_permissions": missing_sensitive,
        "hidden_interfaces": hidden_calls,
        "why_it_supports_claim": (
            build_thesis_claim_text(
                tool_name=tool_name,
                predicted_categories=predicted_categories,
                actual_sensitive=actual_sensitive,
                hidden_calls=hidden_calls,
            )
            if supports_thesis else ""
        ),
        "why_interface_opacity_matters": (
            build_interface_opacity_text(
                tool_name=tool_name,
                predicted_categories=predicted_categories,
                actual_sensitive=actual_sensitive,
                hidden_calls=hidden_calls,
            )
            if is_interface_opacity else ""
        ),
        "notes": notes + rejection_reasons,
        "description_only_summary": description_summary,
    }


def _hidden_case_result(tool_name, case_type, rejection_reason):
    return {
        "supports_thesis": False,
        "is_candidate": False,
        "is_interface_opacity": False,
        "strength": "not_candidate",
        "suitability_score": 0,
        "case_type": case_type,
        "rejection_reasons": [rejection_reason],
        "visible_descriptions": [],
        "visible_description_ordinary": False,
        "explicit_permission_disclosure_terms": [],
        "implied_network_behavior_in_description": False,
        "implied_external_service_in_description": False,
        "taxonomy_granularity_risk": False,
        "comparison_label": "",
        "actual_sensitive_permissions": [],
        "predicted_permissions_from_description": [],
        "missing_sensitive_permissions": [],
        "hidden_interfaces": [],
        "why_it_supports_claim": "",
        "why_interface_opacity_matters": "",
        "notes": [rejection_reason],
        "description_only_summary": "",
    }


def build_out_of_scope_report(tool_name, prediction, actual, comparison):
    missing_permissions = set(comparison.get("missing_permissions", []))
    predicted_categories = comparison.get("predicted_categories", [])
    actual_categories = comparison.get("actual_categories", [])
    description_summary = prediction.get("description_only_summary", "")

    out_of_scope_calls = []
    seen_call_families = set()

    for call in actual.get("external_calls", []):
        category = call.get("category")
        if category not in missing_permissions:
            continue

        api_name = call.get("api_name")
        family = api_family(api_name)
        dedupe_key = (category, family)
        if dedupe_key in seen_call_families:
            continue
        seen_call_families.add(dedupe_key)

        out_of_scope_calls.append({
            "api_name": api_name,
            "api_family": family,
            "permission": category,
            "is_out_of_scope": True,
            "why_out_of_scope": (
                f"This API call belongs to the `{category}` permission category, but DeepSeek inferred only "
                f"{predicted_categories or ['None']} from the tool description/schema. "
                f"In other words, the tool description did not let the model identify this actual `{category}` permission. "
                f"Therefore, `{api_name}` is an API call not sufficiently disclosed by the description and is outside the visible permission scope of the tool description."
            ),
            "description_based_inference": {
                "predicted_permissions": predicted_categories,
                "description_summary": description_summary,
            },
            "actual_behavior_evidence": {
                "actual_permissions": actual_categories,
                "path": call.get("path"),
                "source_code": call.get("source_code"),
                "external_api_summary": call.get("summary"),
                "external_api_url": call.get("url"),
            },
        })

    has_out_of_scope = bool(out_of_scope_calls)

    return {
        "has_out_of_scope_calls": has_out_of_scope,
        "out_of_scope_status": (
            "has_out_of_scope_calls" if has_out_of_scope else "no_out_of_scope_calls"
        ),
        "out_of_scope_summary": (
            f"This tool has {len(out_of_scope_calls)} API calls outside the description scope."
            if has_out_of_scope
            else "No actual API calls outside the tool-description scope were found."
        ),
        "out_of_scope_calls": out_of_scope_calls,
    }


def summarize(rows):
    tool_rows = []

    for project in rows:
        for tool in project.get("tools", []):
            if "actual_permissions" in tool:
                tool_rows.append(tool)

    total = len(tool_rows)
    with_hidden = sum(1 for row in tool_rows if row.get("has_hidden_behavior"))
    hidden_permission_count = sum(
        len(row.get("not_inferable_from_description", {}).get("permissions", []))
        for row in tool_rows
    )

    return {
        "projects_analyzed": len(rows),
        "tools_analyzed": total,
        "tools_with_hidden_behavior": with_hidden,
        "not_inferable_permission_count": hidden_permission_count,
    }


def analyze_project(project_meta, model_args):
    project = project_meta["project"]
    call_graph_path = Path(project_meta["result_dir"]) / "call_graph_labeled.json"
    call_graph = load_json(call_graph_path)
    actual_by_tool = extract_actual_permissions(call_graph)

    result = {
        "project": project,
        "result_dir": project_meta["result_dir"],
        "server_dir": project_meta["server_dir"],
        "call_graph": str(call_graph_path),
        "tools": [],
    }

    for tool_name, actual in actual_by_tool.items():
        desc_context = get_description_context(project_meta, tool_name)
        model_visible_context = build_model_visible_context(desc_context)
        visible_context = compact_visible_context(model_visible_context)
        actual_apis = extract_actual_apis(actual)
        actual_permissions = sorted({
            call.get("category")
            for call in actual.get("external_calls", [])
            if call.get("category") and call.get("category") != "None"
        })

        try:
            if actual_permissions:
                judgment = judge_disclosure_from_description(
                    tool_name=tool_name,
                    visible_context=visible_context,
                    actual_permissions=actual_permissions,
                    actual_apis=actual_apis,
                    model_args=model_args,
                )
                disclosure = normalize_disclosure(
                    actual_permissions=actual_permissions,
                    actual_apis=actual_apis,
                    judgment=judgment,
                )
            else:
                disclosure = {
                    "inferable_from_description": {"permissions": []},
                    "not_inferable_from_description": {"permissions": []},
                }

            tool_result = build_tool_result(
                project=project,
                tool_name=tool_name,
                visible_context=visible_context,
                actual_apis=actual_apis,
                actual_permissions=actual_permissions,
                disclosure=disclosure,
            )

        except Exception as e:
            tool_result = {
                "project": project,
                "tool": tool_name,
                "description": visible_context.get("descriptions", [""])[0] if visible_context.get("descriptions") else "",
                "actual_permissions": build_actual_permissions_with_apis(actual_apis, actual_permissions),
                "error": str(e),
            }

        result["tools"].append(tool_result)

    return result


def flatten_tool_results(project_results):
    tool_results = []

    for project in project_results:
        if "tools" not in project:
            if "tool" in project or "error" in project:
                tool_results.append(project)
            continue

        for tool in project.get("tools", []):
            tool_results.append(tool)

    return tool_results


DISCLOSURE_TABLE_FIELDS = [
    "project",
    "tool",
    "description",
    "permission",
    "apis",
    "inferable_from_description",
    "reason",
]


def normalize_tool_result_output(tool):
    actual_permissions = tool.get("actual_permissions", [])
    actual_apis = tool.get("actual_apis", [])

    if actual_permissions and isinstance(actual_permissions[0], str):
        tool["actual_permissions"] = build_actual_permissions_with_apis(
            actual_apis,
            actual_permissions,
        )
        tool.pop("actual_apis", None)
        actual_permissions = tool["actual_permissions"]

    apis_by_permission = {
        row.get("permission"): row.get("apis", [])
        for row in actual_permissions
        if isinstance(row, dict) and row.get("permission")
    }

    for bucket_key in ("inferable_from_description", "not_inferable_from_description"):
        bucket = tool.get(bucket_key, {})
        for item in bucket.get("permissions", []):
            if "apis" not in item:
                item["apis"] = apis_by_permission.get(item.get("permission"), [])

    not_inferable = tool.get("not_inferable_from_description", {}).get("permissions", [])
    tool["has_hidden_behavior"] = bool(not_inferable)
    return tool


def build_disclosure_table_rows(tool_results, hidden_only=False):
    rows = []

    for tool in tool_results:
        tool = normalize_tool_result_output(dict(tool))
        if tool.get("error"):
            continue

        project = tool.get("project", "")
        tool_name = tool.get("tool", "")
        description = tool.get("description", "")

        buckets = [
            (tool.get("inferable_from_description", {}), "yes"),
            (tool.get("not_inferable_from_description", {}), "no"),
        ]

        for bucket, inferable_flag in buckets:
            if hidden_only and inferable_flag == "yes":
                continue

            for item in bucket.get("permissions", []):
                rows.append({
                    "project": project,
                    "tool": tool_name,
                    "description": description,
                    "permission": item.get("permission", ""),
                    "apis": "; ".join(item.get("apis", [])),
                    "inferable_from_description": inferable_flag,
                    "reason": item.get("reason", ""),
                })

    return rows


def write_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def persist_permission_transparency_outputs(
    all_results,
    output_json,
    summary_json,
    hidden_cases_json,
    table_csv,
    hidden_table_csv,
    sampled,
    args,
    projects,
):
    tool_results = flatten_tool_results(all_results)
    hidden_cases = extract_hidden_permission_cases(tool_results)
    table_rows = build_disclosure_table_rows(tool_results, hidden_only=False)
    hidden_table_rows = build_disclosure_table_rows(tool_results, hidden_only=True)
    summary = summarize(all_results)
    summary["sample_size"] = len(sampled)
    summary["all_projects"] = bool(args.all)
    if args.all:
        summary["seed"] = None
    else:
        summary["seed"] = args.seed
    summary["model"] = args.model
    summary["population"] = args.projects_file
    summary["population_size_loaded"] = len(projects)
    summary["tool_results_file"] = str(output_json)
    summary["hidden_permission_cases_file"] = str(hidden_cases_json)
    summary["hidden_permission_cases"] = len(hidden_cases)
    summary["table_csv_file"] = str(table_csv)
    summary["table_rows"] = len(table_rows)
    summary["hidden_table_csv_file"] = str(hidden_table_csv)
    summary["hidden_table_rows"] = len(hidden_table_rows)
    summary["analysis_scope"] = "permission_categories_elevated_impact_only"
    summary["num_shards"] = args.num_shards
    summary["shard_index"] = args.shard_index

    write_json(output_json, tool_results)
    write_json(hidden_cases_json, hidden_cases)
    write_csv(table_csv, table_rows, DISCLOSURE_TABLE_FIELDS)
    write_csv(hidden_table_csv, hidden_table_rows, DISCLOSURE_TABLE_FIELDS)
    write_json(summary_json, summary)
    return summary


def apply_project_shard(projects, num_shards, shard_index):
    if num_shards <= 1:
        return list(projects)

    return [
        project
        for idx, project in enumerate(projects)
        if idx % num_shards == shard_index
    ]


def select_projects(projects, project_map, args):
    if args.project:
        sampled = []
        for name in args.project:
            if name not in project_map:
                raise SystemExit(f"Project not found in successful analyzed set: {name}")
            sampled.append(project_map[name])
        return apply_project_shard(sampled, args.num_shards, args.shard_index)

    if args.all:
        return apply_project_shard(projects, args.num_shards, args.shard_index)

    random.seed(args.seed)
    sampled = random.sample(projects, min(args.sample_size, len(projects)))
    return apply_project_shard(sampled, args.num_shards, args.shard_index)


def add_path_suffix(path: Path, suffix: str):
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


def maybe_add_shard_suffix(path: Path, args):
    if args.num_shards <= 1:
        return path

    suffix = f"_shard{args.shard_index}of{args.num_shards}"
    return add_path_suffix(path, suffix)


def extract_hidden_permission_cases(tool_results):
    cases = []

    for row in tool_results:
        row = normalize_tool_result_output(dict(row))
        not_inferable = row.get("not_inferable_from_description", {})
        if not not_inferable.get("permissions"):
            continue

        cases.append({
            "project": row.get("project"),
            "tool": row.get("tool"),
            "description": row.get("description", ""),
            "actual_permissions": row.get("actual_permissions", []),
            "inferable_from_description": row.get("inferable_from_description", {}),
            "not_inferable_from_description": not_inferable,
        })

    return sorted(
        cases,
        key=lambda row: (
            row.get("project") or "",
            row.get("tool") or "",
        ),
    )


def main():
    load_dotenv(DEFAULT_ROOT / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument(
        "--projects-file",
        default=str(DEFAULT_PROJECTS_FILE),
        help="Project list to analyze. Default is the 3858-project final success list.",
    )
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-shards", type=int, default=1, help="Split selected projects across N workers.")
    parser.add_argument("--shard-index", type=int, default=0, help="Zero-based shard index for this worker.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Analyze every project in --projects-file that has call_graph_labeled.json.",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=0,
        help="Write intermediate outputs every N projects (default: 1 when --all, otherwise disabled).",
    )
    parser.add_argument("--project", action="append", help="Specify projects; may be repeated. If specified, random sampling is disabled.")
    parser.add_argument("--output-json", default="tool_analyzer/permission_transparency_qwen_tools.json")
    parser.add_argument("--summary-json", default="tool_analyzer/permission_transparency_qwen_summary.json")
    parser.add_argument(
        "--hidden-cases-json",
        default="tool_analyzer/permission_transparency_qwen_hidden_permission_cases.json",
        help="Tools whose materially consequential permissions are not inferable from the description.",
    )
    parser.add_argument(
        "--table-csv",
        default="tool_analyzer/permission_transparency_qwen_table.csv",
        help="CSV table of permission disclosure judgments with mapped APIs.",
    )
    parser.add_argument(
        "--hidden-table-csv",
        default="tool_analyzer/permission_transparency_qwen_hidden_table.csv",
        help="CSV table containing only not-inferable permissions/APIs.",
    )
    parser.add_argument("--model", default=os.getenv("QWEN_MODEL", DEFAULT_QWEN_MODEL))
    parser.add_argument("--base-url", default=os.getenv("QWEN_BASE_URL", DEFAULT_QWEN_BASE_URL))
    parser.add_argument("--api-key", default=os.getenv("QWEN_KEY") or os.getenv("DASHSCOPE_API_KEY"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    if args.num_shards < 1:
        raise SystemExit("--num-shards must be >= 1")
    if args.shard_index < 0 or args.shard_index >= args.num_shards:
        raise SystemExit("--shard-index must satisfy 0 <= shard_index < num_shards")

    if not args.api_key:
        raise SystemExit("Missing QWEN_KEY or DASHSCOPE_API_KEY")

    root = Path(args.root)
    output_json = maybe_add_shard_suffix(Path(args.output_json), args)
    summary_json = maybe_add_shard_suffix(Path(args.summary_json), args)
    hidden_cases_json = maybe_add_shard_suffix(Path(args.hidden_cases_json), args)
    table_csv = maybe_add_shard_suffix(Path(args.table_csv), args)
    hidden_table_csv = maybe_add_shard_suffix(Path(args.hidden_table_csv), args)

    projects = load_successful_projects(root, args.projects_file)
    project_map = {p["project"]: p for p in projects}
    sampled = select_projects(projects, project_map, args)
    checkpoint_every = args.checkpoint_every
    if checkpoint_every <= 0 and args.all:
        checkpoint_every = 1

    model_args = {
        "api_key": args.api_key,
        "base_url": args.base_url,
        "model": args.model,
        "timeout": args.timeout,
        "retries": args.retries,
    }

    all_results = []

    for idx, project_meta in enumerate(sampled, start=1):
        print(f"[{idx}/{len(sampled)}] {project_meta['project']}", flush=True)
        try:
            row = analyze_project(
                project_meta=project_meta,
                model_args=model_args,
            )
        except Exception as e:
            row = {
                "project": project_meta["project"],
                "error": str(e),
            }

        all_results.append(row)

        if checkpoint_every and idx % checkpoint_every == 0:
            persist_permission_transparency_outputs(
                all_results=all_results,
                output_json=output_json,
                summary_json=summary_json,
                hidden_cases_json=hidden_cases_json,
                table_csv=table_csv,
                hidden_table_csv=hidden_table_csv,
                sampled=sampled,
                args=args,
                projects=projects,
            )

    summary = persist_permission_transparency_outputs(
        all_results=all_results,
        output_json=output_json,
        summary_json=summary_json,
        hidden_cases_json=hidden_cases_json,
        table_csv=table_csv,
        hidden_table_csv=hidden_table_csv,
        sampled=sampled,
        args=args,
        projects=projects,
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"tool-level results: {output_json}")
    print(f"hidden permission cases: {hidden_cases_json}")
    print(f"table csv: {table_csv}")
    print(f"hidden table csv: {hidden_table_csv}")
    print(f"summary: {summary_json}")


if __name__ == "__main__":
    main()
