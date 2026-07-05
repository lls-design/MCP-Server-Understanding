import argparse
import logging
import json
import re
import time
import shutil
from urllib.parse import unquote

import requests
from openai import OpenAI
from google.genai import Client
import os
import dotenv
from utils.llm_call import generate_content_openai, get_gemini_client, generate_content_gemini, get_openai_client

dotenv.load_dotenv('.env')




logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("api_analyze")


prompt_template_api_name = """
You are a helpful assistant. I will provide you with a code snippet that invokes the API and its imported modules. Please return the API name. The code is written in Python or TypeScript. Since many APIs have the same name, please return the library name and API name together to identify the API uniquely. For example, the "get" API in the "requests" library should be returned as "requests.get". Please follow the import path of the API to return the API name.
The code snippet is:
"{}"
The imported modules are:
"{}"
Please return the response following the format {{"api_name": "api_name"}} without any other text.
"""

prompt_template_api_identify = """
You are a helpful assistant that can analyze the code and determine if the function is external api that related to privilege. I will provide you with a code snippet that invoke the api and the imported modules. The detailed step is as follows:
    1. Summarize the api name and related library name.
    2. **IMPORTANT: You MUST search the internet for the api name and related library name to find reference documents for the functionality of the api.** Use web search to find official documentation, API references, or relevant documentation pages. Please note that if the api is those normally used api, like concat, join, JSON.stringify, etc., you may skip searching and direct jump to the step 4 and output response with none summary and url.
    3. Based on the reference documents found from internet search, determine if the api is related to privilege.
    4. If the api is not related to the privilege, please output {{"api_name": "api_name", "external": "no", "summary": "none", "url": "https://example.com"}}. If it is related to privilege, output the response of analyze along with the summary of the api description and the url of the reference documents. as the following format: {{"api_name": "api_name", "external": "yes", "summary": "The api \"api_name\" is about...", "url": "https://example.com"}}.

Please note that only those APIs that invoke APIs of other services or utilize important system resources are considered as privilege external APIs. For example, a API that invoke database for query or manage cloud service is a privilege external API. Or a API that read system file or execute system command is a privilege external API. However, functions like concat, join, JSON.stringify are not considered as privilege APIs. Next, I will provide you a code snippet of a function invocation and the imported modules of the code. The code is of {}. 
The code snippet is:
"{}"
The imported modules are:
"{}"
Please output the response according to the json format above. Please note to generate escape characters like \" in the summary. Please only output the json string without any other text.
"""

prompt_api_classification = """
### Instruction
You are a helpful assistant specialized in API classification for permission analysis research. Your task is to classify APIs into one of the following 10 categories based on semantic analysis of their descriptions and the permission implications.

### Categories Reference

1. **Specialized Domain Data Services**
   Definition: Generic HTTP client APIs used to fetch or post data to various external endpoints, including axios.get, fetch, httpx, and custom fetcher functions. Requires network access and often authentication tokens. Security implications involve data exfiltration and unauthorized service access. Distinguished as the only permitted use of 'Specialized Domain Data Services' — strictly for HTTP client wrappers, not domain-specific services like healthcare or finance.

2. **Cloud Infrastructure Management**
   Definition: APIs that manage cloud computing and virtualization resources such as Kubernetes clusters, persistent volumes, virtual machines, object storage buckets, and cluster configurations. Includes providers like Azure VM services, Kubernetes Python client, Tencent Object Storage (TOS), Alibaba Cloud RDS, Bauplan (S3-based), and Files.com. These APIs require IAM roles, service account credentials, API keys, or OAuth tokens with administrative privileges to provision, modify, list, or delete infrastructure components. Security risks include resource exhaustion, privilege escalation, and unauthorized infrastructure modification. Differentiated from 'Database Management' by operating at the infrastructure provisioning layer (e.g., managing clusters, VMs, storage buckets) rather than the data access or query layer within databases.

3. **System Command Execution**
   Definition: APIs that spawn subprocesses, execute shell commands, or interact with low-level system interfaces such as Python's subprocess module, Frida's spawn, GDB register access, and AutoIt initialization. Requires high-privilege system access and can compromise host security. Distinguished from 'File System Operations' by ability to execute arbitrary code rather than just access file metadata.

4. **Project Management Services**
   Definition: APIs that manage tasks, issues, workflows, and collaboration artifacts within productivity and team coordination platforms such as Linear, Todoist, Azure DevOps, Jira, Monday.com, Notion, Trello, Slack, and GitHub Projects. These APIs require OAuth tokens or personal access tokens with read/write permissions to modify project timelines, task assignments, issue states, comments, or board configurations. Security implications include unauthorized workflow disruption, data loss, or exfiltration of internal team communications. Distinguished from 'Code Repository Services' by focusing on task and project tracking rather than source code version control, from 'Calendar Services' by managing discrete work items instead of time-based events, and from 'Social Media Management' by targeting internal enterprise tools rather than public-facing platforms.

5. **Identity and Access Management**
   Definition: APIs that initialize authentication middleware, manage credentials, or handle session tokens such as Microsoft Graph Client initialization with middleware and environment variable retrieval for API keys. Requires handling of secrets and tokens. Security implications involve credential leakage and unauthorized resource access. Distinguished from 'Social Media Management' by focus on authentication infrastructure rather than content APIs.

6. **Financial and Blockchain Services**
   Definition: APIs that interact with blockchain networks to transfer funds or manage accounts, such as Solana's SystemProgram.transfer and RecallNet's accountManager. Requires cryptographic key management and involves irreversible transactions. Security implications include permanent loss of funds if compromised. Distinguished from 'Financial Market Data Services' by direct blockchain interaction rather than traditional market data querying.

7. **Database Management**
   Definition: APIs that create, modify, query, or manage connections to database systems including Prisma ORM, DataStax Astra DB, PostgreSQL via psycopg2, and memcached clients. Requires database credentials and affects data persistence. Security implications include potential data leakage or corruption. Distinguished from 'File System Operations' by interaction with structured database engines rather than raw filesystem.

8. **AI and Machine Learning Services**
   Definition: APIs that interface with AI models or structured response parsers such as OpenAI's chat.completions.parse. Requires API keys and accesses cloud-hosted machine learning models. Security implications include prompt injection, data leakage to third-party models, and cost exposure. Distinguished from 'Specialized Domain Data Services' by direct interaction with AI inference endpoints rather than generic HTTP data fetching.

9. **Browser Automation and Web Interaction**
   Definition: This category includes APIs that automate browser interactions and execute JavaScript in page contexts, such as Puppeteer's evaluate method. These APIs require permissions to control browser instances and can access/manipulate web page content, cookies, and localStorage. They pose risks related to session hijacking and unauthorized web interactions. Distinguished from 'System Command Execution' by being confined to browser environments rather than full system access.

10. **File System Operations**
    Definition: APIs that interact with the local or remote file system to retrieve metadata, open files, or manage file resources. Includes Node.js fs.stat, LeanLSPClient.open_file, and similar functions. Requires filesystem read permissions and potentially exposes sensitive file metadata. Distinguished from 'Database Management' by direct interaction with OS file systems rather than structured database systems.

### Classification Guidelines

When classifying an API, you must:
1. Carefully analyze the semantic meaning of both the API name and its description
2. Compare the API's functionality and permission requirements against each category definition
3. Consider the security implications and permission scope from a research perspective on permission analysis
4. Match the API to the category that best describes its primary function and permission characteristics
5. Pay special attention to the distinctions between similar categories (e.g., Database Management vs File System Operations, Cloud Infrastructure Management vs Database Management)

### Input
The name of API is: "{}"
The summary of the api description is: "{}"

### Output
Please classify the API and output following the JSON format: {{"api_name": "api_name", "category": "category_name"}}. Please note to output the full category name (e.g., "Specialized Domain Data Services"), not a category ID or abbreviation. Please only output the JSON string without any other text.

"""


CATEGORY_ALIASES = {
    "Academic Research Data Services": "Specialized Domain Data Services",
    "Blockchain and Cryptocurrency Services": "Financial and Blockchain Services",
    "Calendar Services": "Project Management Services",
    "Cloud Services": "Cloud Infrastructure Management",
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
    category = str(category or "").strip()
    return CATEGORY_ALIASES.get(category, category)



def infer_privileged_from_snippet(source_code: str) -> tuple[str, str, str] | None:
    rules: list[tuple[re.Pattern[str], str, str, str]] = [
        (re.compile(r"\bpsycopg2\.connect\b"), "psycopg2.connect", "Connects to PostgreSQL database.", "https://www.psycopg.org/psycopg2/docs/module.html"),
        (re.compile(r"\bsqlite3\.connect\b"), "sqlite3.connect", "Connects to SQLite database.", "https://docs.python.org/3/library/sqlite3.html"),
        (re.compile(r"\bopen\s*\("), "builtins.open", "Opens a local file for read/write access.", "https://docs.python.org/3/library/functions.html#open"),
        (re.compile(r"\bfetch\s*\("), "fetch", "Performs HTTP fetch request.", "https://developer.mozilla.org/en-US/docs/Web/API/fetch"),
        (re.compile(r"\breadFile\s*\("), "fs.readFile", "Reads file contents from filesystem.", "https://nodejs.org/api/fs.html#fsreadfilepath-options-callback"),
        (re.compile(r"\bwriteFile\s*\("), "fs.writeFile", "Writes data to filesystem.", "https://nodejs.org/api/fs.html#fswritefilefile-data-options-callback"),
    ]
    for pattern, api_name, summary, url in rules:
        if pattern.search(source_code):
            return api_name, summary, url
    return None


def resolve_source_path(node_path: str, project_path: str) -> str:
    path = unquote(node_path.split(":")[0].lstrip("/"))
    project_name = os.path.basename(project_path.rstrip(os.sep))
    normalized = path.replace("\\", "/")
    marker = f"/Servers/{project_name}/"
    if marker in normalized:
        path = normalized.split(marker, 1)[1]
    elif f"{project_name}_codeql/" in normalized:
        path = normalized.split(f"{project_name}_codeql/", 1)[1]
        if "/Servers/" in path:
            path = path.split("/Servers/", 1)[1]
            if "/" in path:
                path = path.split("/", 1)[1]
    candidates = [
        os.path.join(project_path, path),
        os.path.join(project_path, os.path.basename(path)),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(
        f"Cannot resolve source path for node path {node_path!r} under {project_path}"
    )


def collect_imports(node, project_path):
    imports = []
    source_file = resolve_source_path(node["path"], project_path)
    with open(source_file, "r") as f:
        code = f.readlines()
    for line in code:
        if 'import ' in line:
            imports.append(line.strip())
    return '\n'.join(imports)


def extract_function_name(code_snippet):
    """
    Extract a function call name, excluding attribute calls and chained calls.
    
    Args:
        code_snippet (str): Code snippet containing a function call.
        
    Returns:
        str or None: Extracted function name, or None if not found.
    """
    # Fixed regular expression:
    # 1. Use negative lookbehind to ensure the function name is not preceded by a dot.
    # 2. Match function names that start with a letter or underscore, followed by letters, digits, or underscores.
    # 3. Require an opening parenthesis immediately after the name.
    pattern = r'(?<!\.)\b([a-zA-Z_][a-zA-Z0-9_]*)\('
    
    match = re.search(pattern, code_snippet)
    if match:
        return match.group(1)
    return None

def check_accessible(url: str):
    if url == "https://example.com":
        return False
    cache_path = "tool_analyzer/api_cache_url_check_results.json"
    if not os.path.exists(cache_path):
        api_url_cache = {}
    else:
        with open(cache_path, "r") as f:
            api_url_cache = json.load(f)
    if url in api_url_cache:
        return api_url_cache[url]['accessible']
    
    try:
        proxies = {
            "http": "http://127.0.0.1:10800",
            "https": "http://127.0.0.1:10800"
        }
        response = requests.get(url, timeout=4, proxies=proxies)
        accessible = response.status_code == 200
        api_url_cache[url] = {'accessible': accessible}
        with open("tool_analyzer/api_cache_url_check_results.json", "w") as f:
            json.dump(api_url_cache, f, indent=4, ensure_ascii=False)
        return accessible
    except:
        accessible = False
        api_url_cache[url] = {'accessible': accessible}
        with open("tool_analyzer/api_cache_url_check_results.json", "w") as f:
            json.dump(api_url_cache, f, indent=4, ensure_ascii=False)
        return accessible



def safe_save_json(data, path):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except KeyboardInterrupt as e:
        with open(path, "w") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        exit(0)


def resolve_server_path(project: str) -> str:
    return os.path.join("Servers", project)


def _iter_graph_nodes(call_graph: dict):
    for node_id, node in call_graph.items():
        if str(node_id).startswith("_"):
            continue
        if isinstance(node, dict):
            yield str(node_id), node


def is_usable_call_graph(call_graph: dict) -> bool:
    return any(True for _ in _iter_graph_nodes(call_graph))


def load_project_call_graph(res_path: str, output_file: str = "call_graph_labeled.json") -> tuple[dict, str]:
    base_path = os.path.join(res_path, "call_graph.json")
    labeled_path = os.path.join(res_path, output_file)
    for path, source in ((labeled_path, output_file), (base_path, "call_graph.json")):
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            call_graph = json.load(f)
        if is_usable_call_graph(call_graph):
            if path == base_path and labeled_path != base_path:
                safe_save_json(call_graph, labeled_path)
            return call_graph, source
    return {}, "missing"


def detect_project_type(call_graph: dict, res_path: str) -> str:
    root = call_graph.get("0")
    if isinstance(root, dict):
        path = root.get("path", "")
        if path:
            return "Python" if ".py:" in path else "TypeScript"
    for _, node in _iter_graph_nodes(call_graph):
        path = node.get("path", "")
        if ".py:" in path:
            return "Python"
        if any(ext in path for ext in (".ts:", ".js:", ".tsx:", ".jsx:")):
            return "TypeScript"
    entry_points_path = os.path.join(res_path, "entry_points.json")
    if os.path.exists(entry_points_path):
        with open(entry_points_path, "r", encoding="utf-8") as f:
            entry_points = json.load(f)
        for ep in entry_points.values():
            file_path = ep.get("file", "")
            if file_path.endswith(".py"):
                return "Python"
            if file_path.endswith((".ts", ".js", ".tsx", ".jsx")):
                return "TypeScript"
    return "Python"


def mark_call_graph_skipped(res_path: str, output_file: str, reason: str) -> dict:
    call_graph = {"_api_analyze_meta": {"status": "skipped", "reason": reason}}
    safe_save_json(call_graph, os.path.join(res_path, output_file))
    logger.warning(f"skip api_analyze: {reason}")
    return call_graph


def collect_call_nodes_to_analyze(invoked_functions: dict, call_graph: dict) -> tuple[list[str], str]:
    seen: set[str] = set()
    nodes: list[str] = []

    def add_callnode(node_id) -> None:
        node_id = str(node_id)
        if node_id in seen or node_id not in call_graph:
            return
        if not call_graph[node_id].get("des", "").startswith("CallNode"):
            return
        seen.add(node_id)
        nodes.append(node_id)

    for entry_info in invoked_functions.values():
        for node_id in entry_info.get("visited", []):
            add_callnode(node_id)
        for node_id in entry_info.get("leaf_nodes", []):
            add_callnode(node_id)

    if nodes:
        return nodes, "visited_and_leaf"
    for node_id in call_graph:
        if node_id.startswith("_"):
            continue
        add_callnode(node_id)
    if nodes:
        return nodes, "all_call_nodes_fallback"
    return nodes, "empty"


def should_skip_labeled_node(node_data: dict, force_rerun: bool) -> bool:
    if force_rerun:
        return node_data.get("external_api") is True and "api_name" in node_data
    return "external_api" in node_data and "api_name" in node_data


def analyze_a_project(project: str, client1: OpenAI | Client, client2: OpenAI | Client | None = None, force_rerun: bool = False, cache_path: str = "", output_file: str = "call_graph_labeled.json", no_search: bool = False):
    res_path = os.path.join("results", project)
    if cache_path != "" and os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            cached_apis = json.load(f)
    else:
        cached_apis = {
            "Python": {},
            "TypeScript": {}
        }
    
    if not os.path.exists(res_path):
        logger.error(f"!!! result path not found: {res_path}")
        return {}
    if not os.path.exists(os.path.join(res_path, "call_graph.json")):
        logger.error(f"!!! call graph not build: {os.path.join(res_path, 'call_graph.json')}")
        return {}
    
    output_path = os.path.join(res_path, output_file)
    call_graph, graph_source = load_project_call_graph(res_path, output_file)
    if not is_usable_call_graph(call_graph):
        return mark_call_graph_skipped(res_path, output_file, "call graph missing or empty; CodeQL rebuild required")
    if graph_source == "call_graph.json":
        logger.info(f"reload call graph from call_graph.json for {project}")

    project_type = detect_project_type(call_graph, res_path)
    cached_apis_language = cached_apis[project_type]
    server_path = resolve_server_path(project)

    invoked_path = os.path.join(res_path, "invoked_functions.json")
    if not os.path.exists(invoked_path):
        logger.warning(f"invoked_functions.json missing for {project}, using empty dict")
        invoked_functions = {}
    else:
        with open(invoked_path, "r", encoding="utf-8") as f:
            invoked_functions = json.load(f)

    call_nodes, collect_mode = collect_call_nodes_to_analyze(invoked_functions, call_graph)
    logger.info(f"Project {project} has {len(call_nodes)} CallNodes to analyze (strategy: {collect_mode})")

    if force_rerun:
        for node_id in call_nodes:
            for key in ("external_api", "api_name", "external_api_summary", "external_api_url", "category", "retry"):
                call_graph[node_id].pop(key, None)

    for node in call_nodes:
            if not call_graph[node].get("des", "").startswith("CallNode"):
                continue
            if should_skip_labeled_node(call_graph[node], force_rerun):
                api_name = call_graph[node]["api_name"]
                if api_name in cached_apis_language and cached_apis_language[api_name]["external_api"] == call_graph[node]["external_api"]:
                    projects = cached_apis_language[api_name].get("project", [])
                    if project not in projects:
                        cached_apis_language[api_name]["project"] = list(set(projects + [project]))
                        safe_save_json(cached_apis, cache_path)
                    logging.info(f"resolved node. Function {call_graph[node]['des']}'s api is {call_graph[node]['api_name']}, and is external api: {call_graph[node]['external_api']}")
                    continue
                else:
                    logger.info(f"update call graph node from cache. Function {call_graph[node]['des']}'s api is {call_graph[node]['api_name']}, and is external api: {call_graph[node]['external_api']}")

            imports = collect_imports(call_graph[node], server_path)

            #todo: temp code for repetion check
            repetion = False
            if 'api_name' in call_graph[node]:
                api_name = call_graph[node]['api_name']
                if api_name in cached_apis_language and len(cached_apis_language[api_name]['project']) > 4:
                    repetion = True
                elif api_name in cached_apis_language and check_accessible(cached_apis_language[api_name]['external_api_url']) == False:
                    logger.info(f"external api url is not accessible: {cached_apis_language[api_name]['external_api_url']}")
                    repetion = True

            
            if 'api_name' in call_graph[node] and not repetion:
                api_name = call_graph[node]['api_name']

            else:
                # api_name = extract_function_name(call_graph[node]['source_code'])
                api_name = None
                if api_name is None:
                    ## get api name
                    prompt = prompt_template_api_name.format(call_graph[node]['source_code'], imports)
                    res = generate_content_openai(client1, prompt, output_check={"api_name": "api_name"})
                    if res is None:
                        logger.error(f"Failed to generate api name for function {call_graph[node]['des']}")
                        continue
                    logger.info(f"function {call_graph[node]['des']} api name is: {res['api_name']}")
                    api_name = res['api_name']
                    call_graph[node]['retry'] = True
                else:
                    logger.info(f"directly extract function name, {call_graph[node]['des']} api name is: {api_name}")
            
            call_graph[node]['api_name'] = api_name
            safe_save_json(call_graph, output_path)
            if api_name in cached_apis_language and not force_rerun:
                logger.info(f"Cached result. Function {call_graph[node]['des']} is external api: {cached_apis_language[api_name]}")
                call_graph[node]['external_api'] = cached_apis_language[api_name]['external_api']
                call_graph[node]['external_api_summary'] = cached_apis_language[api_name]['external_api_summary']
                call_graph[node]['external_api_url'] = cached_apis_language[api_name]['external_api_url']
                cached_apis_language[api_name]["project"] = list(set(cached_apis_language[api_name]["project"] + [project]))
                safe_save_json(cached_apis, cache_path)
                safe_save_json(call_graph, output_path)
                continue
            if api_name in cached_apis_language and force_rerun and cached_apis_language[api_name]['external_api']:
                call_graph[node]['external_api'] = True
                call_graph[node]['external_api_summary'] = cached_apis_language[api_name]['external_api_summary']
                call_graph[node]['external_api_url'] = cached_apis_language[api_name]['external_api_url']
                cached_apis_language[api_name]["project"] = list(set(cached_apis_language[api_name]["project"] + [project]))
                safe_save_json(cached_apis, cache_path)
                safe_save_json(call_graph, output_path)
                continue


            # analyze privilege external api
            prompt = prompt_template_api_identify.format(project_type, call_graph[node]['source_code'], imports)
            res = generate_content_openai(
                client1, prompt,
                enable_search=not no_search,
                forced_search=not no_search,
                output_check={"api_name": "api_name", "external": "yes", "summary": "summary", "url": "url"},
            )
            if res is None:
                logger.error(f"Failed to generate api identify for function {call_graph[node]['des']}")
                safe_save_json(call_graph, output_path)
                continue
            # time.sleep(4)
            logger.info(f"function {call_graph[node]['des']}, {api_name} is external api: {res['external']}")
            # exit(0)
            if res['external']  == "yes":
                call_graph[node]['external_api'] = True
                call_graph[node]['external_api_summary'] = res['summary']
                call_graph[node]['external_api_url'] = res['url']
            else:
                override = infer_privileged_from_snippet(call_graph[node].get('source_code', ''))
                if override:
                    api_name_override, summary, url = override
                    logger.info(f"rule override for {call_graph[node]['des']}: {api_name_override}")
                    call_graph[node]['external_api'] = True
                    call_graph[node]['external_api_summary'] = summary
                    call_graph[node]['external_api_url'] = url
                    if not call_graph[node].get('api_name'):
                        call_graph[node]['api_name'] = api_name_override
                else:
                    call_graph[node]['external_api'] = False
                    call_graph[node]['external_api_summary'] = ''
                    call_graph[node]['external_api_url'] = res['url']
            cached_apis_language[api_name] = {
                "external_api": call_graph[node]['external_api'],
                "external_api_summary": call_graph[node]['external_api_summary'],
                "external_api_url": call_graph[node]['external_api_url'],
                "project": [project]
            }
            safe_save_json(cached_apis, cache_path)
            safe_save_json(call_graph, output_path)
    safe_save_json(call_graph, output_path)
    return call_graph


def classify_api_of_a_project(project: str, client: OpenAI | Client, cache_path: str = "", output_file: str = "call_graph_labeled.json", call_graph: dict | None = None):
    res_path = os.path.join("results", project)
    if not os.path.exists(res_path):
        logger.error(f"!!! result path not found: {res_path}")
        return {}
    if call_graph is None:
        call_graph, _ = load_project_call_graph(res_path, output_file)
    if not is_usable_call_graph(call_graph):
        return mark_call_graph_skipped(res_path, output_file, "call graph missing or empty; CodeQL rebuild required")
    api_category = {
        "Python": {},
        "TypeScript": {}
    }
    if cache_path != "" and os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            api_category = json.load(f)
        print(f"load api cache from {cache_path}, length: {len(api_category)}")

    project_type = detect_project_type(call_graph, res_path)
    cached_apis_language = api_category[project_type]
    
    cnt = 0
    for node in call_graph:
        if not call_graph[node].get("des", "").startswith("CallNode"):
            continue
        if 'external_api' not in call_graph[node] or not call_graph[node]['external_api']:
            continue
        
        # if 'category' in call_graph[node]:
        #     continue

        api_name = call_graph[node]['api_name']
        api_summary = call_graph[node]['external_api_summary']


        
        cached_category = None
        if api_name in cached_apis_language:
            cached_category = cached_apis_language[api_name].get("category")
        if cached_category is not None and str(cached_category).strip():
            call_graph[node]['category'] = cached_category
            logger.info(f"Cached classify result. Function {call_graph[node]['api_name']} is category: {cached_category}")
            continue

        prompt = prompt_api_classification.format(api_name, api_summary)
        res = generate_content_openai(client, prompt, output_check={"api_name": "api_name", "category": "category"})
        if res is None:
            logger.error(f"Failed to generate api classification for function {call_graph[node]['des']}")
            continue
        category = canonical_category(res['category'])
        call_graph[node]['category'] = category
        cached_apis_language.setdefault(api_name, {})
        cached_apis_language[api_name]['category'] = category
        
        cnt += 1
        if cnt == 10:
            safe_save_json(api_category, cache_path)
            safe_save_json(call_graph, os.path.join(res_path, output_file))
            cnt = 0
    safe_save_json(api_category, cache_path)
    safe_save_json(call_graph, os.path.join(res_path, output_file))

    
    
    return call_graph


def collect_apis_to_classify(project: str, cache_path: str = "", output_file: str = "call_graph_labeled.json") -> list:
    res_path = os.path.join("results", project)
    call_graph, _ = load_project_call_graph(res_path, output_file)
    if not is_usable_call_graph(call_graph):
        return []
    apis = []
    for node_id, node in _iter_graph_nodes(call_graph):
        if not node.get("des", "").startswith("CallNode"):
            continue
        if not node.get("external_api"):
            continue
        apis.append({
            "project": project,
            "node_id": node_id,
            "api_name": node.get("api_name", ""),
            "api_summary": node.get("external_api_summary", ""),
        })
    return apis


def apply_classification_results(project, classification_results, api_mapping, cache_path="", output_file="call_graph_labeled.json"):
    res_path = os.path.join("results", project)
    call_graph, _ = load_project_call_graph(res_path, output_file)
    if not is_usable_call_graph(call_graph):
        return
    api_category = {"Python": {}, "TypeScript": {}}
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            api_category = json.load(f)
    project_type = detect_project_type(call_graph, res_path)
    cached = api_category[project_type]
    indices = [i for i, item in enumerate(api_mapping) if item.get("project") == project]
    for idx in indices:
        if idx >= len(classification_results):
            continue
        item = api_mapping[idx]
        node_id = item["node_id"]
        result = classification_results[idx]
        if node_id not in call_graph:
            continue
        category = result.get("category")
        if not category:
            continue
        call_graph[node_id]["category"] = category
        api_name = call_graph[node_id].get("api_name")
        if api_name:
            cached.setdefault(api_name, {})
            cached[api_name]["category"] = category
    safe_save_json(api_category, cache_path)
    safe_save_json(call_graph, os.path.join(res_path, output_file))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project_path", "-p", type=str, required=True)
    parser.add_argument("--force_rerun", action="store_true")
    parser.add_argument("--cache", type=str, default="tool_analyzer/api_cache.json")
    parser.add_argument("--output_file", type=str, default="call_graph_labeled.json")
    parser.add_argument("--skip-classify", action="store_true", help="Skip category classification (run batch_classify_all later)")
    parser.add_argument("--no-search", action="store_true", help="Identify without web search (faster bulk labeling)")
    args = parser.parse_args()
    try:
        client2 = get_gemini_client()
    except Exception as e:
        logger.warning(f"Failed to initialize Gemini client: {e}; using only OpenAI/QWEN")
        client2 = None
    client1 = get_openai_client()

    project_name = os.path.basename(args.project_path.rstrip("/"))
    call_graph = analyze_a_project(
        project_name, client1, client2, args.force_rerun, args.cache, args.output_file, no_search=args.no_search
    )
    if call_graph and not args.skip_classify:
        call_graph = classify_api_of_a_project(
            project_name, client1, args.cache, args.output_file, call_graph=call_graph
        )
    with open(os.path.join(args.project_path, args.output_file), "w") as f:
        json.dump(call_graph, f, indent=4)
    
