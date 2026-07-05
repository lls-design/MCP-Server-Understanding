/**
 * @name MCP Tool Entry Points - registerTool Pattern
 * @kind problem
 * @problem.severity warning
 * @id typescript/mcp-register-tool-pattern
 * @description Identifies MCP tool entry points using registerTool method pattern
 */

import javascript
import typescriptAnalyzer.Entry_identification

from ToolFunction toolFunction
select toolFunction.getName(), toolFunction.getLocation().getFile(), toolFunction.getLocation().getStartLine().toString(), toolFunction.getLocation().getEndLine() 

