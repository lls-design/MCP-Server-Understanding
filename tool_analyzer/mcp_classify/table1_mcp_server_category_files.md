# Table I MCP Server Category Files

This file lists the repository files most directly related to the paper-style
table:

`TABLE I: Distribution of MCP server categories`

The counts in the screenshot match the `server_totals` stored in:

- `picture/auth_type_to_server_type_alluvial.audit.json`

Specifically, this file contains:

- `matched_projects = 4049`
- `total_flow = 4049`
- `server_totals`
  - `Data and Public Content Access = 1607`
  - `Infrastructure and Gateway Services = 692`
  - `Source Control and Collaboration = 589`
  - `Task and Schedule Management = 431`
  - `Local Execution and Automation = 375`
  - `Financial and Blockchain Services = 143`
  - `Analytics and Peripheral Tools = 130`
  - `Security, Access Control, and Scanning = 82`

## Most Important Files

- `picture/auth_type_to_server_type_alluvial.audit.json`
  - Direct repository-backed source for the exact 4049-project category counts
    shown in the table.
- `draw/plot_auth_category_to_server_type.py`
  - Script that reads the filtered project list, authorization labels, and
    paper-8 server assignments, then writes the alluvial outputs and audit file.
- `tool_analyzer/final_success_projects.txt`
  - The exact 4049-project population used for the table counts.
- `tool_analyzer/paper8_new_servers_classification/merged_server_assignments.jsonl`
  - Per-project paper-8 category assignments used to derive the 8 category
    totals for the 4049 final-success projects.
- `tool_analyzer/final_success_authorization_classified.json`
  - Authorization labels used by the same alluvial/audit pipeline.

## Direct Output Files From The Same Count Source

- `picture/auth_type_to_server_type_alluvial.audit.json`
- `picture/auth_type_to_server_type_alluvial.csv`
- `picture/auth_type_to_server_type_alluvial.png`
- `picture/auth_type_to_server_type_alluvial.pdf`

These outputs come from the same script and the same filtered 4049-project
population. Even if the screenshot table itself was formatted separately, these
files are the closest in-repo artifacts tied to the exact same counts.

## Taxonomy Definition Files

- `tool_analyzer/taxonomy_paper8.json`
  - The 8-category taxonomy definition.
- `tool_analyzer/taxonomy_paper8_codebook.json`
  - Machine-readable paper-8 codebook.
- `tool_analyzer/taxonomy_paper8_codebook.md`
  - Human-readable paper-8 category codebook.

These define the category names used in the table.

## Upstream Paper-8 Classification Outputs

- `tool_analyzer/paper8_new_servers_classification/merged_server_assignments.jsonl`
  - Current merged paper-8 assignments over the larger corpus; the table uses
    this file after filtering to `final_success_projects.txt`.
- `tool_analyzer/paper8_new_servers_classification/merged_type_count_summary.json`
  - Full merged corpus category totals before the 4049-project filter.
- `tool_analyzer/paper8_new_servers_classification/run_summary.json`
  - Run metadata for the merged assignments.

## Scripts That Produced The Underlying Paper-8 Assignments

- `scripts/classify_new_paper8_servers.py`
  - Produces `paper8_new_servers_classification/merged_server_assignments.jsonl`.
- `scripts/classify_servers_paper8_llm.py`
  - Paper-8 LLM reclassification script.
- `scripts/merge_paper8_llm_classification.py`
  - Merges paper-8 classification shards.
- `scripts/server_category_pipeline.py`
  - Evidence-preparation and batch pipeline for the 8-way category workflow.

## Practical Interpretation

If your goal is only this table, the essential file set is:

- `picture/auth_type_to_server_type_alluvial.audit.json`
- `draw/plot_auth_category_to_server_type.py`
- `tool_analyzer/final_success_projects.txt`
- `tool_analyzer/paper8_new_servers_classification/merged_server_assignments.jsonl`
- `tool_analyzer/taxonomy_paper8.json`

Everything else is supporting context or upstream provenance.
