# MCP Privilege Analysis

This repository contains the artifact for our large-scale study of privilege
usage in Model Context Protocol (MCP) servers. The analysis combines CodeQL
static analysis with LLM-assisted classification to identify privilege-sensitive
APIs, authorization mechanisms, and permission transparency issues in MCP tools.

The repository includes the analysis scripts, the local MCP server corpus, the
per-project analysis results, and precomputed tables/figures used by the paper.

## Overview

MCP servers expose tool entry points to LLM clients. A single tool invocation can
reach local resources or remote services through SDK calls, HTTP clients,
filesystem operations, database clients, browser automation, shell commands, and
other APIs. This artifact follows the execution path from each MCP tool to the
downstream APIs it may invoke, then analyzes the privileges implied by those
APIs.

The analysis pipeline is:

1. **Build tool-level call graphs.** For each MCP server, identify MCP tool
   entry points and recover the functions reachable from each tool.
2. **Collect downstream API calls.** Use the recovered call graph to collect API
   calls reachable from MCP tools, including external service calls and local
   resource-access APIs.
3. **Identify and classify privilege-sensitive APIs.** Use LLM-assisted
   analysis and cached evidence to decide whether each API is privilege
   sensitive, then assign it to a functional permission category.
4. **Analyze authorization behavior.** Inspect how each server obtains, stores,
   and passes credentials or other authority when invoking external services.
5. **Analyze permission transparency.** Compare the permissions implied by the
   reachable APIs with the natural-language tool descriptions to find hidden or
   understated capabilities.

## Repository Structure

| Path | Description |
|---|---|
| `codeql_analyzer/` | This directory contains scripts to execute CodeQL queries. A CodeQL engine needs to be deployed in `codeql_analyzer/codeql-engine`. |
| `scripts/` | It stores automatic scripts for large-scale experiments, including corpus extraction, API collection, API classification, authorization analysis, permission transparency analysis, and batch execution. |
| `tool_analyzer/` | This directory contains precomputed analysis artifacts, caches, summaries, taxonomy files, and intermediate data used by the paper. |
| `draw/` | Plotting scripts that generate paper figures and tables from the precomputed artifacts. |
| `figures/` | Paper-facing figures, tables, and audit files. |
| `utils/` | It contains tool scripts and functions for LLM calling, figure drawing, etc. |
| `MCPs/` | Raw MCP metadata shards used to construct the corpus. |
| `Servers/` | It is used for saving source code and CodeQL database of each MCP server. |
| `results/` | It saves per-project analysis results, including entry points, call graphs, labeled call graphs, and authorization reports. |

## Current Artifact Snapshot

The current workspace contains:

| Item | Count / Location |
|---|---:|
| Successfully analyzed projects | `4049` in `tool_analyzer/final_success_projects.txt` |
| Per-project result directories | `4049` under `results/` |
| MCP tools in final successful projects | `35476` |
| External API call occurrences in final successful projects | `79874` |
| Unique external APIs in final successful projects | `27465` |
| Qwen/DeepSeek consensus hidden-permission tools | `2219` |

The checked-in JSON/CSV files under `tool_analyzer/` are the canonical
precomputed results for this snapshot.

## Environment Setup

This project uses `uv` and Python 3.12.

```bash
uv sync
```

The following environment variables are used by different parts of the
pipeline:

| Variable | Purpose |
|---|---|
| `CODEQL_PATH` | Path to the CodeQL engine used to build databases and run queries. |
| `GITHUB_TOKEN` | Optional GitHub token for repository metadata collection and rate-limit avoidance. |
| `QWEN_KEY` or `DASHSCOPE_API_KEY` | Qwen-compatible LLM calls. |
| `GEMINI_KEY` | Optional Gemini-backed LLM calls. |

Set these variables in a local `.env` file before running stages that require
CodeQL, GitHub API access, or LLM calls. The precomputed results can be
inspected without external credentials.

## Basic Usage

### 1. Build Call Graphs

To analyze one local MCP server project:

```bash
uv run python scripts/call_graph_analyze.py \
  --project_path Servers/0pstech_vuln-fs \
  --project_name 0pstech_vuln-fs \
  --result_dir results \
  --force_rebuild
```

To analyze a repository from GitHub:

```bash
uv run python scripts/call_graph_analyze.py \
  --url https://github.com/OWNER/REPO \
  --project_name OWNER_REPO \
  --result_dir results \
  --force_rebuild
```

For large-scale execution over a server metadata file:

```bash
uv run python scripts/graph_all_projects.py \
  -m MCPs/data1.json \
  --result_file results/0-results/call_graph_result.json
```

Typical per-project outputs are written to `results/<project>/`:

| File | Description |
|---|---|
| `entry_points.json` | MCP tool entry points. |
| `call_graph.json` | Recovered call graph. |
| `invoked_functions.json` | Functions reachable from MCP tools. |
| `call_graph_labeled.json` | Call graph labeled with external API and category information. |
| `authorization.json` | Authorization analysis report. |

### 2. Identify and Classify Privilege-Sensitive APIs

```bash
uv run python scripts/api_analyze.py \
  --project_path results/0pstech_vuln-fs \
  --cache tool_analyzer/api_analyze/api_cache.json
```

For batch classification of APIs that have already been detected:

```bash
uv run python scripts/batch_classify_all.py \
  --results_dir results \
  --cache tool_analyzer/api_analyze/api_cache.json \
  --output_file call_graph_labeled.json
```

To run `api_analyze.py` across many result directories, use:

```bash
uv run python scripts/batch_analyze.py \
  --results_dir results \
  --cache tool_analyzer/api_analyze/api_cache.json \
  --output_file call_graph_labeled.json
```

### 3. Analyze and Classify Authorization

```bash
uv run python scripts/authorization_analyze.py \
  --project 0pstech_vuln-fs \
  --servers_dir Servers \
  --results_dir results
```

For batch authorization analysis over all statically analyzed projects, use:

```bash
uv run python scripts/batch_authorization_analyze.py \
  --results_dir results \
  --servers_dir Servers \
  --summary_file tool_analyzer/authorization_analyze/authorization_summary.json
```

After project-level authorization reports are summarized, classify the
authorization approaches with:

```bash
uv run python scripts/authorization_classification.py \
  --input tool_analyzer/authorization_analyze/authorization_summary.json \
  --output tool_analyzer/authorization_analyze/authorization_classified.json \
  --results_dir results
```

Use `--project 0pstech_vuln-fs` to classify one project from the summary file.
The authorization summary and classified authorization results are available in
`tool_analyzer/authorization_analyze/`.

### 4. Analyze Permission Transparency

```bash
uv run python scripts/permission_transparency.py \
  --projects-file tool_analyzer/final_success_projects.txt \
  --all \
  --output-json tool_analyzer/permission_transparency/permission_transparency_qwen_tools.json \
  --summary-json tool_analyzer/permission_transparency/permission_transparency_qwen_summary.json \
  --hidden-cases-json tool_analyzer/permission_transparency/permission_transparency_qwen_hidden_permission_cases.json \
  --table-csv tool_analyzer/permission_transparency/permission_transparency_qwen_table.csv \
  --hidden-table-csv tool_analyzer/permission_transparency/permission_transparency_qwen_hidden_table.csv
```

The repository also includes DeepSeek results and Qwen/DeepSeek intersection
artifacts in `tool_analyzer/permission_transparency/`.

## Main Precomputed Results

The most important reusable result files are:

| File | Description |
|---|---|
| `tool_analyzer/api_analyze/category_statistics.json` | Classification results for privilege-sensitive API categories. |
| `tool_analyzer/api_analyze/api_cache.json` | Cached API evidence used by the API and permission-transparency analyses. |
| `tool_analyzer/authorization_analyze/authorization_summary.json` | Project-level authorization analysis results. |
| `tool_analyzer/authorization_analyze/authorization_classified.json` | Authorization results grouped into higher-level authorization approaches. |

Other precomputed artifacts are organized by analysis stage. `tool_analyzer/tools/`
contains MCP tool-count results, `tool_analyzer/api_calls/` contains external
API usage statistics, `tool_analyzer/permission_transparency/` contains
LLM-generated permission-transparency outputs, and
`tool_analyzer/mcp_classify/` contains MCP server taxonomy artifacts.

## Paper Figures and Tables

Paper-facing outputs are stored under `figures/`.

| Output | Generator |
|---|---|
| `Distribution of Authorization Approaches.png/pdf` | `draw/authorization_pie.py` |
| `auth_type_to_server_type_alluvial.png/pdf/csv` | `draw/plot_auth_category_to_server_type.py` |
| `Table 2 Categorization of Privilege-Sensitive APIs.csv/png` | `draw/category_priviledged_api.py` |
| `final_success_tool_count_violin.png/pdf` | `draw/final_success_tool_violin.py` |
| `final_success_external_api_count_violin.png/pdf` | `draw/final_success_external_api_violin.py` |
| `final_success_code_loc_violin.png/pdf` | `draw/final_success_code_loc_violin.py` |
| `deepseek_qwen_hidden_api_cache_entry_venn.png/pdf` | `draw/hidden_api_cache_entry_venn.py` |
| `deepseek_qwen_shared_hidden_api_category_pie.png/pdf/svg` | `draw/deepseek_qwen_shared_hidden_api_category_pie.py` |

## Quick Inspection Commands

```bash
wc -l tool_analyzer/final_success_projects.txt
uv run python -m json.tool tool_analyzer/api_analyze/api_cache.json | head -40
uv run python -m json.tool tool_analyzer/api_analyze/category_statistics.json | head -40
uv run python -m json.tool tool_analyzer/authorization_analyze/authorization_summary.json | head -40
uv run python -m json.tool tool_analyzer/authorization_analyze/authorization_classified.json | head -40
```

## Artifact Notes

- Full reproduction is computationally expensive because it clones thousands of
  repositories, builds CodeQL databases, and invokes LLM services.
- LLM-backed labels may vary across model versions. The checked-in artifacts are
  the snapshot used for the paper-facing results.
- Some MCP projects fail static analysis because of unsupported layouts, missing
  entry points, or build issues. The paper analyses use the fixed final-success
  project set listed in `tool_analyzer/final_success_projects.txt`.
- The `Servers/` directory contains third-party repositories. Respect upstream
  licenses and remove private credentials before distributing a public artifact.

## Citation

This repository accompanies an ICSE submission on privilege usage,
authorization, and permission transparency in MCP servers. A BibTeX entry can be
added after publication.
