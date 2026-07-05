# mcp_server_taxonomy_final_v2

Revised final candidate taxonomy for classifying MCP servers by dominant user-facing functionality. Version 2 restores source-control/software-collaboration as a recurring category after review found that GitHub/GitLab/Bitbucket servers were being scattered across unrelated categories.

## Categories

| ID | Category | Description |
|---|---|---|
| F01 | Data and Knowledge Access | Retrieval, querying, search, summarization, or exposure of structured data, documents, knowledge bases, web content, and public or SaaS records. |
| F02 | Agent and AI Tooling | Prompting, memory, RAG, embeddings, model routing, AI generation, and agent-oriented tooling for AI assistants. |
| F03 | Infrastructure and Operations | Cloud resources, containers, deployments, observability, gateways, proxies, and service operations. |
| F04 | Productivity and Communication | Tasks, calendars, messaging, email, meetings, tickets, project boards, and workflow coordination. |
| F05 | Financial and Blockchain Services | Financial data, trading, payments, ecommerce, crypto, wallets, smart contracts, and on-chain analysis. |
| F06 | Analytics and Creative Tools | Computation, analytics, visualization, media generation, design, and peripheral utilities. |
| F07 | Local Execution and Automation | Local command execution, filesystem operations, browser automation, and workspace control. |
| F08 | Security and Access Control | Vulnerability scanning, security auditing, identity, secrets, permissions, policy, and compliance. |
| F09 | Source Control and Software Collaboration | Source-code repository operations, including Git hosting APIs, commits, branches, pull/merge requests, code review, releases, and repository-file workflows. |
| F10 | Other Specialized Integrations | Long-tail domain-specific MCP servers that do not fall into the major recurring categories. |

## Assignment Policy

### label_cardinality

single-label

### primary_rule

Assign each MCP server to the category that best captures its dominant user-facing capability, not its installation method, framework, or generic MCP protocol implementation.

### evidence_priority

- tool/resource/prompt names and descriptions
- README feature or capability sections
- package metadata description and keywords
- API/service dependencies and configuration variables
- repository name only when other evidence is sparse

### noise_to_ignore

- generic MCP/Claude/Desktop setup text
- installation commands such as npm install, pip install, docker run, uv run
- generic build/test/lint/deploy instructions unless they are the exposed server capability
- authentication setup unless identity/security is the core function

### tie_breakers

- Prefer domain-specific categories over generic data access when the server performs domain actions such as trading, payments, vulnerability scanning, or infrastructure control.
- Prefer Infrastructure and Operations over Local Execution and Automation when the server manages cloud/container/service lifecycle rather than merely executing local commands.
- Prefer Local Execution and Automation when the exposed capability is shell/filesystem/browser control even if the README mentions data retrieval.
- Prefer Source Control and Software Collaboration when the server exposes repository, commit, branch, pull/merge request, release, issue, or code-review operations.
- Prefer Agent and AI Tooling only when prompts, memory, RAG, embeddings, model routing, or agent orchestration are first-class server functions rather than marketing context.
- Use Other Specialized Integrations only when evidence is sparse or the integration belongs to a long-tail domain not represented by the major categories.
- Use Other Specialized Integrations only when evidence is sparse or the integration belongs to a long-tail domain not represented by the recurring categories.

