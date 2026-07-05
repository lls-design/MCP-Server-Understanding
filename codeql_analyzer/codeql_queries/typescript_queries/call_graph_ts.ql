/**
 * This is an automatically generated file
 * @name call graph builder typescript
 * @kind path-problem
 * @id typescript_queries/call_graph_ts.ql
*/

import javascript
import DataFlow
import typescriptAnalyzer.Entry_identification

predicate isContained(ExprOrStmt source, ExprOrStmt sink) {
    source.getAChild() = sink 
    or exists(ExprOrStmt expr | source.getAChild() = expr and isContained(expr, sink))
}



module TsCallGraph{
    class SourceStmt extends ExprOrStmt {
        SourceStmt() {
            this instanceof ToolFunction
        }

        // or exists(CaseStmt caseStmt, ToolFunction toolFunction | source = caseStmt.getAChildExpr().flow() | caseStmt.getChild(0) = toolFunction)
    }

    class SinkStmt extends ExprOrStmt {
        SinkStmt() {
            exists(CallNode cn| cn.asExpr() = this)
        }
    }

    
}

private query predicate edges(ExprOrStmt from_n, ExprOrStmt to_n) {
    exists(CallNode cn | cn.getEnclosingFunction() = from_n | to_n = cn.asExpr())
    or
    exists(CallNode cn | cn.asExpr() = from_n | cn.getACallee() = to_n )
    or
    exists(CallNode cn, Case caseStmt | caseStmt = from_n and isContained(from_n, cn.asExpr()) | to_n = cn.asExpr())
}


from TsCallGraph::SourceStmt source, TsCallGraph::SinkStmt sink
where edges+(source, sink)
select sink, source, sink, "Tool function Call Graph"


// from CaseStmt caseStmt, CallNode cn
// where caseStmt.getAChildExpr().(StringLiteral).getValue() = "create_relations" 
// select caseStmt.getChild(0).getAChildExpr()