from langchain_ollama import ChatOllama

from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt import tools_condition


from solvers_server import classic_planner, numeric_planner, validate_pddl_syntax


def get_llm():

    model = "llama3.1"

    return ChatOllama(model=model, temperature=0.0)


def ollama_with_tools(prompt, sys_msg, tools):
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools, tool_choice="any")

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
    builder.add_conditional_edges(
        "assistant",
        # If the latest message (result) from assistant is a tool call -> tools_condition routes to tools
        # If the latest message (result) from assistant is a not a tool call -> tools_condition routes to END
        tools_condition,
    )
    builder.add_edge("tools", "assistant")

    react_graph = builder.compile()

    # Show
    # graph = react_graph.get_graph(xray=True)
    # png_bytes = graph.draw_mermaid_png()
    # with open("output.png", "wb") as f:
    #     f.write(png_bytes)

    messages = [HumanMessage(content=prompt)]
    result = react_graph.invoke({"messages": [messages[0]]})

    tool_name = result["messages"][-2].name  # tool name
    tool_output = result["messages"][-2].content  # tool result
    tool_reason = result["messages"][-1].content  # why

    print(
        f"Tool used: {tool_name}"
        f"\nTool result: {tool_output}"
        f"\nReasoning: {tool_reason}"
    )

    return tool_name, tool_output, tool_reason


def ollama_request(prompt):
    tools = [classic_planner, numeric_planner, validate_pddl_syntax]

    sys_msg = SystemMessage(
        content=(
            "You are a PDDL planner operating within a tool-based planning system.\n"
            "Your task is to compute a plan for a given planning problem using one of the available solver tools.\n"
            "Never respond with free-form text. Tool use is mandatory.\n"
            "Always rely on tool outputs — do not generate a plan or runtime yourself.\n"
            "Always rely on tool outputs — do not generate a plan or runtime yourself.\n"
            "Don't use any tool that is not listed in the available tools.\n"
            "Select the appropriate tool based on the structure and features of the problem.\n"
            "If the selected tool returns empty list, treat the problem as unsolvable and return an empty plan.\n"
            "Conclude by explaining the reasoning behind the tool selection."
        )
    )

    return ollama_with_tools(prompt, sys_msg, tools)
