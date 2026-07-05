import python


class ToolFunction extends Function {
    ToolFunction() {
        this.getADecorator().(Call).getFunc().(Attribute).getName().matches("tool")  
        or this.getADecorator().(Attribute).getName().matches("tool")
        or this.getADecorator().(Call).getFunc().(Attribute).getName().matches("call_tool")
    }
}
