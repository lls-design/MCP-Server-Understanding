# Paper-8 MCP Server Taxonomy Codebook

This codebook is for classifying MCP servers into the eight paper categories. `Agent and AI Tooling` and `Other` are not top-level categories. Agent-oriented or ambiguous servers should be assigned to the closest dominant functional category.

## Global Rules

- Assign exactly one category.
- Classify by dominant exposed capability, not by implementation language, installation method, framework, or generic MCP protocol integration.
- Prefer tool/resource/prompt names over README marketing text.
- Ignore generic MCP/Claude/Desktop setup, install commands, badges, GitHub URLs, Dockerfiles, and auth setup unless they describe exposed functionality.
- Do not assign Source Control solely because a package has a GitHub repository URL.
- Do not assign Infrastructure solely because installation uses Docker.
- Do not assign Security solely because an API key, OAuth token, or secure connection is required.
- If evidence is sparse, choose the closest of the eight paper categories; do not create an Other category.

## Categories

| ID | Category | Definition |
|---|---|---|
| P01 | Data and Public Content Access | Retrieval, querying, search, summarization, or exposure of structured data, documents, knowledge bases, web content, public content, or SaaS records. |
| P02 | Infrastructure and Gateway Services | Administration of infrastructure, cloud resources, containers, deployments, observability, gateways, proxies, or service orchestration. |
| P03 | Source Control and Collaboration | Git/source-hosting repository operations, commits, branches, PR/MR workflows, code review, releases, and repository-file workflows. |
| P04 | Local Execution and Automation | Local command execution, scripts, filesystem/workspace operations, browser/UI automation, screenshots, scraping, and desktop automation. |
| P05 | Task and Schedule Management | Tasks, todos, tickets, calendars, meetings, reminders, email, chat, team communication, and workflow coordination. |
| P06 | Financial and Blockchain Services | Financial data, trading, payments, ecommerce, accounting, banking, crypto, wallets, smart contracts, and on-chain analysis. |
| P07 | Analytics and Peripheral Tools | Computation, analysis, statistics, visualization, reporting, media/creative tools, transcription, QR, hardware, camera, sensors, and peripheral utilities. |
| P08 | Security, Access Control, and Scanning | Vulnerability scanning, security auditing, pentesting, CVE/threat intelligence, IAM, secrets, permissions, policy, compliance, and access control. |

## Boundary Rules

- RAG, embeddings, semantic search, memory, and knowledge retrieval go to `Data and Public Content Access` when they retrieve knowledge/context.
- AI generation, media generation, computation, transformation, and model wrappers go to `Analytics and Peripheral Tools` when generated/analytical output is dominant.
- GitHub/GitLab/Bitbucket/Azure DevOps repository operations go to `Source Control and Collaboration`; generic GitHub URLs do not.
- Jira/Linear/Trello/task/calendar/email/chat workflows go to `Task and Schedule Management` unless repository PR/commit operations dominate.
- Docker/Kubernetes/cloud/deployment/gateway/monitoring operations go to `Infrastructure and Gateway Services`; Docker installation instructions do not.
- Shell/filesystem/browser/desktop automation goes to `Local Execution and Automation` unless the operation is clearly cloud infrastructure, source control, or security scanning.
- Payment, trading, ecommerce, wallet, smart-contract, token, NFT, and on-chain operations go to `Financial and Blockchain Services`.
- Vulnerability, CVE, pentest, IAM, secrets, policy, permission, compliance, and security audit operations go to `Security, Access Control, and Scanning`.

## LLM Output Schema

```json
{
  "server_name": "string",
  "category": "one of the eight category names",
  "confidence": "high | medium | low",
  "secondary_category": "one of the eight category names or null",
  "decision_basis": "short explanation grounded in evidence",
  "evidence": ["tool names or short evidence snippets"],
  "ambiguity_notes": "short note if evidence is sparse or categories are close"
}
```
