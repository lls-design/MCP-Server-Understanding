/**
 * This is an automatically generated file
 * @name call graph builder python
 * @kind path-problem
 * @id codeql_queries/call_graph_py.ql
 */


import python
import semmle.python.pointsto.CallGraph
import semmle.python.objects.ObjectInternal
import semmle.python.dataflow.new.DataFlow
import semmle.python.ApiGraphs

/**
 * Returns true if there is a call graph edge from statement `from` to statement `to`.
 */
private query predicate edges(DataFlow::Node from_n, DataFlow::Node to_n) {
exists(FunctionInvocation fi, Function f |
    fi.getCall().getScope().(Function) = f and f.getLocation() = from_n.getLocation()| 
    to_n.getLocation() = fi.getCall().getLocation()) 
    or exists(FunctionInvocation fi, Function f |
    fi.getCall().getNode().getLocation() = from_n.getLocation() | 
    to_n.getLocation() = f.getLocation() and fi.getFunction().getFunction() = f )
    or exists(CallNode cn| cn.getScope().getLocation() = from_n.getLocation() and cn.getLocation() = to_n.getLocation())
    // Implement Durk Type Analysis
}

string getFuncOrAttribute(CallNode cn){
    // If the function is not an Attribute, return its string representation
    cn.getNode().getFunc().toString() = result and
    not cn.getNode().getFunc() instanceof Attribute
    or
    // If the function is an Attribute, return the attribute's name
    result = cn.getNode().getFunc().(Attribute).getName()
    // or
    
}

module PyCallGraph {
    class SourceNode extends DataFlow::Node {
        SourceNode() {
        exists(Function f |
            f.getADecorator().(Call).getFunc().(Attribute).getName().matches("tool") |
            this.getLocation() = f.getLocation())
        }
    }
    // predicate isSource(DataFlow::Node source) {
    //     exists(Function f |
    //         f.getADecorator().(Call).getFunc().(Attribute).getName().matches("tool") |
    //         source.getLocation() = f.getLocation())
    // }

    class SinkNode extends DataFlow::Node {
        SinkNode() {
            exists(CallNode cn| cn.getLocation() = this.getLocation())
        }
    }

    // predicate isSink(DataFlow::Node sink) {
    //     exists(CallNode cn| cn.getLocation() = sink.getLocation() 
    //     // | fi.getCall() = API::moduleImport(_).getMember(_).getACall().getNode() and fi.getFunction().getName() != "len" and fi.getFunction().getName() != "print" and fi.getFunction().getName() != "isinstance" and fi.getFunction().getName() != "eval"
    //     )
    // }
}



from PyCallGraph::SourceNode source, PyCallGraph::SinkNode sink, Function fsouce, CallNode cn
// where PyCallGraph::flow(source, sink)// and source.getLocation() = fsouce.getLocation() and sink.getLocation() = cn.getLocation()
where edges+(source, sink) and fsouce.getLocation() = source.getLocation() and cn.getLocation() = sink.getLocation()
select fsouce, source, sink, "Inoke Function " + getFuncOrAttribute(cn)

