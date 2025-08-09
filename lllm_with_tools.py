from langchain_ollama import ChatOllama

from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt import tools_condition

from langgraph.checkpoint.memory import MemorySaver

from solvers_server import (
    classic_planner,
    numeric_planner,
    validate_pddl_syntax,
    save_plan,
    get_state_transition,
)


def get_llm():

    model = "qwen3:4b"

    return ChatOllama(model=model, temperature=0.0, base_url="http://127.0.0.1:1234")


def ollama_with_tools(prompt, sys_msg, tools):
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools, tool_choice="any")

    # Node
    def assistant(state: MessagesState):
        return {
            "messages": [
                llm_with_tools.invoke([sys_msg] + state["messages"], think=False)
            ]
        }

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

    config = {"configurable": {"thread_id": "1"}}
    memory = MemorySaver()

    react_graph = builder.compile(checkpointer=memory)

    # Show
    # graph = react_graph.get_graph(xray=True)
    # png_bytes = graph.draw_mermaid_png()
    # with open("output.png", "wb") as f:
    #     f.write(png_bytes)

    messages = [HumanMessage(content=prompt)]
    result = react_graph.invoke({"messages": messages}, config)

    tool_name = result["messages"][-2].name  # tool name
    tool_output = result["messages"][-2].content  # tool result
    tool_reason = result["messages"][-1].content  # why

    print(
        f"Tool used: {tool_name}"
        f"\nTool result: {tool_output}"
        f"\nReasoning: {tool_reason}"
    )

    return tool_name, tool_output, tool_reason


def ollama_request(prompt, chat_focus=False):
    tools = [
        classic_planner,
        numeric_planner,
        validate_pddl_syntax,
        save_plan,
        get_state_transition,
    ]

    if chat_focus:
        content = (
            "You are a PDDL planner operating within a tool-based planning system.\n"
            "Your primary task is to compute a plan for a given planning problem using one of the available solver tools.\n"
            "If the query clearly requires solving a planning problem, you must select the appropriate tool from the available list and use it.\n"
            "If the query can be fully answered without solving a planning problem (e.g., it is a factual question, a clarification request, or an explanation about planning concepts), you may answer directly without using any tool.\n"
            "Do not use any tool that is not listed in the available tools.\n"
            "When using a tool:\n"
            "  - Select the appropriate tool based on the structure and features of the problem.\n"
            "  - Always rely on tool outputs — do not generate a plan or runtime yourself.\n"
            "  - If the selected tool returns an empty list, treat the problem as unsolvable and return an empty plan.\n"
            "When not using a tool:\n"
            "  - Provide a clear and concise answer directly.\n"
            "Always conclude by explaining your reasoning for either using a tool or answering directly."
        )
    else:
        content = (
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

    sys_msg = SystemMessage(content=content)
    return ollama_with_tools(prompt, sys_msg, tools)
