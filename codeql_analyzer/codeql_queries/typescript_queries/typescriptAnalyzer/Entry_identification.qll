private import javascript
private import semmle.javascript.TypeScript as typescript
private import DataFlow

/**
 * A class representing MCP tools defined using the setRequestHandler method pattern.
 * These are functions that handle tool requests in a switch statement.
 */
class SetRequestHandlerTool extends SwitchCase {
  SetRequestHandlerTool() {
    // This function is passed as the second argument to a setRequestHandler method call
    exists(Function handlerFunction, SwitchStmt switchStmt, SwitchCase case, MethodCallExpr call |
      call.getMethodName() = "setRequestHandler" and
      handlerFunction = call.getArgument(1).(Function) and
      switchStmt = handlerFunction.getABodyStmt().getAChild*() and
      case = switchStmt.getACase()
    |
      this = case
    )
  }

  string getToolName() { result = this.getExpr().(StringLiteral).getValue() }

  Stmt getToolFunction() { result = this }
}

// datatrace for McpServer
private SourceNode mcpServer(TypeTracker t) {
  t.start() and
  (exists(NewExpr newServer | result.asExpr() = newServer |
    newServer.getCallee().toString() = "McpServer" //or exists(
    //     ClassDefinition classDef | classDef.getSuperClass().toString() = "McpServer" and newServer.getCallee().toString() = classDef.getName().toString())
  ) or 
  exists(Parameter param | param.getTypeBinding().toString() = "McpServer" | result.asExpr() = param)
  )
  or
  exists(TypeTracker t2 | result = mcpServer(t2).track(t2, t))
}

private SourceNode mcpServer() { result = mcpServer(TypeTracker::end()) }

SourceNode callTool(TypeTracker t) {
  t.start() and
  (
    result = mcpServer().getAMemberCall("tool") or
    result = mcpServer().getAMemberCall("registerTool")
  )
  or
  exists(TypeTracker t2 | result = callTool(t2).track(t2, t))
}

SourceNode callTool() { result = callTool(TypeTracker::end()) }

//Tool Name Trace DataFlow Analysis
private module FindToolName implements DataFlow::ConfigSig {
  predicate isSource(DataFlow::Node source) {
    source instanceof ValueNode and source.getStringValue() != ""
  }

  predicate isSink(DataFlow::Node sink) {
    exists(MethodCallNode toolCall |
      toolCall.getCalleeName() = "tool" or toolCall.getCalleeName() = "registerTool"
    |
      toolCall.getArgument(0) = sink
    )
  }
  // optional predicates:
}

private module FindToolNameFlow = DataFlow::Global<FindToolName>;

class ToolMethodDefinedTool extends MethodCallExpr {
  ToolMethodDefinedTool() {
    this = callTool().asExpr()
    or
    exists(ClassDefinition classDef |
      classDef.getSuperClass().toString() = "McpServer" and
      this.getReceiver().getTypeBinding().getAnUnderlyingClass().getName() = classDef.getName()
    |
      this.getCalleeName() = "tool" or this.getCalleeName() = "registerTool"
    )
  }

  string getToolName() {
    result = this.getArgument(0).(StringLiteral).getValue()
    or
    exists(DataFlow::Node source, DataFlow::Node sink | FindToolNameFlow::flow(source, sink) |
      result = source.getStringValue() and sink.asExpr() = this.getArgument(0)
    )
  }
  

  Function getToolFunction() {
    exists(Function toolFunction |
      result = toolFunction and toolFunction = this.getAnArgument().(Function)
    )
    or
    exists(MethodDeclaration toolMethod, MethodCallExpr methodCallExpr, ClassDefinition typeDef |
      methodCallExpr.getCalleeName() = "bind" and
      this.getAnArgument() = methodCallExpr and
      toolMethod.getName() = methodCallExpr.getReceiver().(PropAccess).getPropertyName() and
      typeDef =
        methodCallExpr.getReceiver().(PropAccess).getBase().getTypeBinding().getTypeDefinition() and
      (
        typeDef = toolMethod.getDeclaringType()
        or
        typeDef.getASuperTypeDeclaration() = toolMethod.getDeclaringType()
        or
        toolMethod.getDeclaringType().getName() =
          typeDef.getSuperClass().(ExpressionWithTypeArguments).getExpression().(VarAccess).getVariable().getName()
      )
    |
      result = toolMethod.getBody()
    )
    or(
      result = this.getAnArgument().(CallExpr).getArgument(0).(Function)
    )
  }
}


class FastMCPAddToolObject extends ObjectExpr {
    FastMCPAddToolObject() {
        this.getAProperty().getName() = "name"
        and this.getAProperty().getName() = "description"
        and exists(Property prop | prop = this.getAProperty() and prop.getName() = "execute" | prop.getInit() instanceof Function)
    }

    string getToolName() {
        result = this.getPropertyByName("name").getInit().(StringLiteral).getValue()
    }

    Function getToolFunction() {
        result = this.getPropertyByName("execute").getInit().(Function)
    }
}

class ToolFunction extends ExprOrStmt {
  ToolFunction() {
    exists(SetRequestHandlerTool setRequestHandler | setRequestHandler.getToolFunction() = this) or
    exists(ToolMethodDefinedTool toolMethodDefinedTool |
      toolMethodDefinedTool.getToolFunction() = this
    ) or
    exists(FastMCPAddToolObject fastMCPAddToolObject | fastMCPAddToolObject.getToolFunction() = this)
  }

  string getName() {
    exists(SetRequestHandlerTool setRequestHandler | setRequestHandler.getToolFunction() = this |
      result = setRequestHandler.getToolName()
    )
    or
    exists(ToolMethodDefinedTool toolMethodDefinedTool |
      toolMethodDefinedTool.getToolFunction() = this
    | result = toolMethodDefinedTool.getToolName())
    or
    exists(FastMCPAddToolObject fastMCPAddToolObject | fastMCPAddToolObject.getToolFunction() = this | result = fastMCPAddToolObject.getToolName())
  }
}
