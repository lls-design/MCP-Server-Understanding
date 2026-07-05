/**
 * @name MCP registerTool Pattern Analysis using Class
 * @kind problem
 * @problem.severity warning
 * @id typescript/mcp-register-tool-class-analysis
 * @description Analysis of MCP tools using the RegisterToolDefinedTool class
 */


import javascript

import typescriptAnalyzer.Entry_identification

import DataFlow

from CallExpr callExpr, ToolMethodDefinedTool toolFunction
// where param.getTypeBinding().hasQualifiedName("McpServer")
where callExpr.getCalleeName() = "withSecurityValidation" and 
toolFunction.getAnArgument()  = callExpr
select callExpr, callExpr.getArgument(0).(Function)
// exists(CallExpr callExpr | callExpr.getArgument(0) instanceof Function and this.getArgument(0) instanceof Function | result = this.getArgument(0))