/**
 * This is an automatically generated file
 * @name call graph python
 * @kind problem
 * @problem.severity warning
 * @id codeql_queries/entry_identification_py.ql
 */

import python
import semmle.python.objects.ObjectInternal
import semmle.python.pointsto.CallGraph
import pythonAnalyzer.Entry_identification
// from Function f
// where f.getName() = "extract_content"
// // where f.getADecorator().(Call).getFunc().(Attribute).getName().matches("tool") 
// select f.getName(), f.getADecorator().(Attribute).getName()


from ToolFunction tf
select tf.getName(), tf.getLocation().getFile(), tf.getLocation().getStartLine(), tf.getLocation().getEndLine()
