/**
 * This is an automatically generated file
 * @name call graph builder typescript
 * @kind graph
 * @id typescript_queries/call_graph_ts_g.ql
*/

import javascript
import DataFlow
import typescriptAnalyzer.Entry_identification

predicate isContained(ExprOrStmt source, ExprOrStmt sink) {
    source.getAChild() = sink 
    or exists(ExprOrStmt expr | source.getAChild() = expr and isContained(expr, sink))
}


private query predicate nodes(TsCallGraph::CallGraphNode n, string attr, string val) {
    attr = "semmle.label" and
    val = n.getLabel()
}

private query predicate edges(TsCallGraph::CallGraphNode pred, TsCallGraph::CallGraphNode succ, string attr, string val) {
    (
        exists(CallNode cn | cn.getEnclosingFunction() = pred | succ = cn.asExpr())
        or
        exists(CallNode cn | cn.asExpr() = pred | cn.getACallee() = succ )
        or
        exists(CallNode cn, Case caseStmt | caseStmt = pred and isContained(pred, cn.asExpr()) | succ = cn.asExpr())
    )
    and 
    attr = "semmle.label" and
    (
        if pred instanceof TsCallGraph::SourceStmt
        then val = "edge from Source " + pred.getLabel()
        else val = "edge"
    )
}
    

module TsCallGraph{

    class CallGraphNode extends ExprOrStmt {
        CallGraphNode() {
            this instanceof SourceStmt or
            from_source(this)
        }

        string getLabel() {
            if this instanceof SourceStmt
            then result = this.(SourceStmt).getLabel()
            else (
                exists(CallNode cn | cn.getEnclosingFunction() = this | result = "FunctionDef " + cn.getEnclosingFunction().getName())
                or
                exists(CallNode cn | cn.asExpr() = this | result = "CallNode " + cn.asExpr().toString())
            )
        }
    }

    class SourceStmt extends ExprOrStmt {
        SourceStmt() {
            this instanceof ToolFunction
        }

        // or exists(CaseStmt caseStmt, ToolFunction toolFunction | source = caseStmt.getAChildExpr().flow() | caseStmt.getChild(0) = toolFunction)

        string getLabel() {
            result = "Source " + this.(ToolFunction).getName()
        }
    }

    class SinkStmt extends ExprOrStmt {
        SinkStmt() {
            exists(CallNode cn| cn.asExpr() = this)
        }
    }

    private predicate edges_pri(ExprOrStmt from_n, ExprOrStmt to_n) {
        exists(CallNode cn | cn.getEnclosingFunction() = from_n | to_n = cn.asExpr())
        or
        exists(CallNode cn | cn.asExpr() = from_n | cn.getACallee() = to_n )
        or
        exists(CallNode cn, Case caseStmt | caseStmt = from_n and isContained(from_n, cn.asExpr()) | to_n = cn.asExpr())
    }

    predicate from_source(ExprOrStmt n) {
        exists(SourceStmt source, ExprOrStmt intermediate | edges_pri(source, n) or from_source(intermediate) and edges_pri(intermediate, n)) 
    }
    

    
}


// from CaseStmt caseStmt, CallNode cn
// where caseStmt.getAChildExpr().(StringLiteral).getValue() = "create_relations" 
// select caseStmt.getChild(0).getAChildExpr()