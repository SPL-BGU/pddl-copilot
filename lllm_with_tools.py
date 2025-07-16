from langchain_ollama import ChatOllama

from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode


from solvers_server import add, multiply, numeric_planner


def call_ollama(prompt):
    tools = [add, multiply, numeric_planner]
    llm = ChatOllama(model="llama3.1", temperature=0)
    llm_with_tools = llm.bind_tools(tools, tool_choice="any")

    # System message
    sys_msg = SystemMessage(
        content=(
            "You are a MAPF planner. "
            "Given a problem description, you must always call exactly one of the available solver tools. "
            "Then u need to explain why did u choose this tool over the others."
        )
    )

    # Node
    def assistant(state: MessagesState):
        return {"messages": [llm_with_tools.invoke([sys_msg] + state["messages"])]}

    # Graph
    builder = StateGraph(MessagesState)

    # Define nodes: these do the work
    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode(tools))

    # Define edges: these determine how the control flow moves
    builder.add_edge(START, "assistant")
    builder.add_edge("assistant", "tools")
    builder.add_node("assistant2", assistant)
    builder.add_edge("tools", "assistant2")
    react_graph = builder.compile()

    # Show
    # graph = react_graph.get_graph(xray=True)
    # png_bytes = graph.draw_mermaid_png()
    # with open("output.png", "wb") as f:
    #     f.write(png_bytes)

    messages = [HumanMessage(content=prompt)]
    result = react_graph.invoke({"messages": [messages[0]]})

    tool_name = result["messages"][-2].name  # tool name
    tool_result = result["messages"][-2].content  # tool result
    tool_reason = result["messages"][-1].content  # why

    print(
        f"Tool used: {tool_name}"
        f"\nTool result: {tool_result}"
        f"\nReasoning: {tool_reason}"
    )

    return tool_name, tool_result, tool_reason
