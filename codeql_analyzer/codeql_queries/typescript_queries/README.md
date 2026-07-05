# MCP Tool Entry Points Identification

This directory contains CodeQL queries for identifying Model Context Protocol (MCP) tool entry points in TypeScript/JavaScript codebases.

## Query Files

### 1. `entry_identification_ts.ql`
Basic query for identifying `registerTool` method calls.

### 2. `mcp_tool_search.ql`
Comprehensive search covering both MCP tool patterns:
- `registerTool` method calls
- `setRequestHandler` with `ListToolsRequestSchema`
- `setRequestHandler` with `CallToolRequestSchema`
- Tool names in tools arrays
- Switch case labels for tool names

### 3. `register_tool_pattern.ql`
Detailed analysis of `registerTool` method calls:
- Tool names
- Configuration objects
- Implementation functions
- Complete tool information

### 4. `McpToolClass.ql`
Library file defining reusable classes for MCP tool patterns (for future use).

## MCP Tool Patterns

### Pattern 1: registerTool Method
```typescript
mcpServer.registerTool(
  'tool_name',           // Tool name
  {                      // Configuration object
    title: 'Tool Title',
    description: 'Tool description',
    inputSchema: inputSchema,
    outputSchema: outputSchema,
    annotations: { /* ... */ }
  },
  async (args) => {      // Implementation function
    // Tool logic
  }
);
```

### Pattern 2: setRequestHandler Method
```typescript
// Tool declaration
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "tool_name",
        description: "Tool description",
        inputSchema: inputSchema
      }
    ]
  };
});

// Tool implementation
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  switch (request.params.name) {
    case "tool_name": {
      // Tool implementation
    }
  }
});
```

## Usage

1. **Run the queries** on your TypeScript/JavaScript codebase
2. **Review results** to identify MCP tool entry points
3. **Analyze patterns** to understand tool registration methods
4. **Extract tool information** for documentation or analysis

## Expected Results

The queries will identify:
- Tool registration calls
- Tool names and configurations
- Implementation functions
- Request handler patterns
- Switch case structures for tool routing

## Benefits

- **Automated Discovery**: Find all MCP tools in a codebase
- **Pattern Analysis**: Understand different registration approaches
- **Documentation**: Generate tool catalogs automatically
- **Maintenance**: Track tool changes and dependencies 