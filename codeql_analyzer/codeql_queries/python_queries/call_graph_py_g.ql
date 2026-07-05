/**
 * This is an automatically generated file
 * @name call graph builder python
 * @kind graph
 * @id python_queries/call_graph_py_g.ql
 */


import python
import semmle.python.pointsto.CallGraph
import semmle.python.objects.ObjectInternal
import semmle.python.dataflow.new.DataFlow
import semmle.python.ApiGraphs
import pythonAnalyzer.Entry_identification
/**
 * Returns true if there is a call graph edge from statement `from` to statement `to`.
 */
private query predicate edges(PyCallGraph::CallGraphNode pred, PyCallGraph::CallGraphNode succ, string attr, string val) {
        (exists(FunctionInvocation fi, Function f |
        fi.getCall().getScope().(Function) = f and f.getLocation() = pred.getLocation()| 
        succ.getLocation() = fi.getCall().getLocation()) 
        or exists(FunctionInvocation fi, Function f |
        fi.getCall().getNode().getLocation() = pred.getLocation() | 
        succ.getLocation() = f.getLocation() and fi.getFunction().getFunction() = f )
        or exists(CallNode cn| cn.getScope().getLocation() = pred.getLocation() and cn.getLocation() = succ.getLocation()))
        and
        attr = "semmle.label"
        and
        val = "edge"
    
    // Implement Durk Type Analysis
}

private query predicate nodes(PyCallGraph::CallGraphNode n, string attr, string val) {
    attr = "semmle.label" and
    val = n.getLabel()
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


    class CallGraphNode extends DataFlow::Node {
        CallGraphNode() {
            this instanceof SourceNode 
            or  from_source(this)
            // or 
            // exists(SourceNode source | source.getLocation() = this.getLocation())
        }

        string getLabel() {
            if this instanceof SourceNode
            then result = this.(SourceNode).getLabel()
            else(
            exists(Function f | f.getLocation() = this.getLocation() | result = "FunctionDef " + f.getName())
            or
            if this.asExpr().(Call).getFunc() instanceof Attribute 
            then result = "CallNode " + this.asExpr().(Call).getFunc().(Attribute).getName()
            else if this.asExpr() instanceof Call
            then result = "CallNode " + this.asExpr().toString()
            else result = "CallNode " + " Unknown Call"
            )

            // result = "CallNode " + this.asExpr().toString() + " : " + this.asExpr().getLocation().toString()
            // exists(CallNode cn| cn.getScope().getLocation() = this.getLocation() | result = "FunctionDef " +  cn.getScope().getName() + " : " + cn.getLocation().toString())
      
        }
    }
    
    class SourceNode extends DataFlow::Node {
        SourceNode() {
        // exists(Function f |
        //     f.getADecorator().(Call).getFunc().(Attribute).getName().matches("tool") |
        //     this.getLocation() = f.getLocation())
        exists(ToolFunction tf |
            // this.asCfgNode().(FunctionObject).getFunction() = tf)
            this.getLocation() = tf.getLocation())
        }
        
        
        string getLabel() {
            exists(Function f |
                f.getADecorator().(Call).getFunc().(Attribute).getName().matches("tool") |
                this.getLocation() = f.getLocation() and result = "Source: " + f.getName()) 
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




    private predicate edges_private(DataFlow::Node pred, DataFlow::Node succ) {
        (
            exists(FunctionInvocation fi, Function f |
            fi.getCall().getScope().(Function) = f and f.getLocation() = pred.getLocation()| 
            succ.getLocation() = fi.getCall().getLocation()) 
            or exists(FunctionInvocation fi, Function f |
            fi.getCall().getNode().getLocation() = pred.getLocation() | 
            succ.getLocation() = f.getLocation() and fi.getFunction().getFunction() = f )
            or exists(CallNode cn| cn.getScope().getLocation() = pred.getLocation() and cn.getLocation() = succ.getLocation())
        )
    }

    predicate from_source(DataFlow::Node n) {
        exists(SourceNode source, DataFlow::Node intermediate | edges_private(source, n) or from_source(intermediate) and edges_private(intermediate, n)) 
    }
    // predicate isSink(DataFlow::Node sink) {
    //     exists(CallNode cn| cn.getLocation() = sink.getLocation() 
    //     // | fi.getCall() = API::moduleImport(_).getMember(_).getACall().getNode() and fi.getFunction().getName() != "len" and fi.getFunction().getName() != "print" and fi.getFunction().getName() != "isinstance" and fi.getFunction().getName() != "eval"
    //     )
    // }
}
