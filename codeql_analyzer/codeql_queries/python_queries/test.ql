/**
 * @name MCP registerTool Pattern Analysis using Class
 * @kind problem
 * @problem.severity warning
 * @id typescript/mcp-register-tool-class-analysis
 * @description Analysis of MCP tools using the RegisterToolDefinedTool class
 */


import python
// import semmle.python.pointsto.CallGraph
import semmle.python.objects.ObjectInternal
import semmle.python.dataflow.new.DataFlow
import semmle.python.ApiGraphs
import pythonAnalyzer.Entry_identification
// from FunctionInvocation fi, Function f 
// where fi.getFunction().getName() = "process"
// select fi, fi.getCall().getLocation()

from ToolFunction tf, DataFlow::Node node
where node.asCfgNode().(FunctionObject).getFunction() = tf
select node.getLocation()

