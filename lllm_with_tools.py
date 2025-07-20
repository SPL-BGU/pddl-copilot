from langchain_ollama import ChatOllama

from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode


from solvers_server import classic_planner, numeric_planner


def call_ollama(prompt):
    tools = [classic_planner, numeric_planner]
    llm = ChatOllama(model="llama3.1", temperature=0.0)
    llm_with_tools = llm.bind_tools(tools, tool_choice="any")

    # System message
    sys_msg = SystemMessage(
        content=(
            "You are a PDDL planner operating within a tool-based planning system.\n"
            "Your task is to compute a plan for a given planning problem using one of the available solver tools.\n"
            "Never respond with free-form text. Tool use is mandatory.\n"
            "Always rely on tool outputs — do not generate a plan or runtime yourself.\n"
            "Select the appropriate tool based on the structure of the problem.\n"
            "If the selected tool returns no solution, treat the problem as unsolvable and return an empty plan.\n"
            "Conclude by explaining the reasoning behind the tool selection."
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
