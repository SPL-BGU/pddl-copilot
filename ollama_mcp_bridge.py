#!/usr/bin/env python3
"""Ollama MCP Bridge — connects Ollama models to marketplace MCP plugins."""

import argparse
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack

import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
PLUGINS_DIR = os.path.join(REPO_ROOT, "plugins")


# ── Plugin discovery ────────────────────────────────────────────────────────


def _read_plugin_description(plugin_path):
    """Read first non-empty, non-heading line from CLAUDE.md as description."""
    claude_md = os.path.join(plugin_path, "CLAUDE.md")
    try:
        with open(claude_md) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except OSError:
        pass
    return None


def discover_plugins():
    """Scan plugins/ directory for .mcp.json and return list of plugin dicts."""
    plugins = []
    if not os.path.isdir(PLUGINS_DIR):
        return plugins

    for name in os.listdir(PLUGINS_DIR):
        abs_path = os.path.join(PLUGINS_DIR, name)
        mcp_json_path = os.path.join(abs_path, ".mcp.json")
        if os.path.isdir(abs_path) and os.path.isfile(mcp_json_path):
            description = _read_plugin_description(abs_path) or f"Local plugin ({name})"
            plugins.append({
                "name": name,
                "description": description,
                "source_abs": abs_path,
            })
    return sorted(plugins, key=lambda p: p["name"])


def load_plugin_mcp_config(plugin_path):
    """Read a plugin's .mcp.json and return dict of {server_name: StdioServerParameters}."""
    mcp_json_path = os.path.join(plugin_path, ".mcp.json")
    with open(mcp_json_path) as f:
        config = json.load(f)

    servers = {}
    for name, server_def in config.get("mcpServers", {}).items():
        command = server_def["command"]
        raw_args = server_def.get("args", [])
        resolved_args = [arg.replace("${CLAUDE_PLUGIN_ROOT}", plugin_path) for arg in raw_args]

        servers[name] = StdioServerParameters(
            command=command,
            args=resolved_args,
            env=dict(os.environ),
        )
    return servers


# ── MCP session management ──────────────────────────────────────────────────


async def connect_plugins(selected_plugins, exit_stack):
    """Launch MCP servers for selected plugins and return tools + routing map."""
    ollama_tools = []
    tool_to_session = {}

    for plugin in selected_plugins:
        server_configs = load_plugin_mcp_config(plugin["source_abs"])
        for server_name, params in server_configs.items():
            print(f"  Connecting to {server_name}...", end=" ", flush=True)
            try:
                transport = await exit_stack.enter_async_context(stdio_client(params))
                read_stream, write_stream = transport
                session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
                await session.initialize()

                tools_response = await session.list_tools()
                for tool in tools_response.tools:
                    ollama_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": tool.inputSchema,
                        },
                    })
                    tool_to_session[tool.name] = session

                print(f"OK ({len(tools_response.tools)} tools)")
            except Exception as e:
                print(f"FAILED: {e}")

    return ollama_tools, tool_to_session


# ── Tool execution ──────────────────────────────────────────────────────────


async def execute_tool_call(tool_name, arguments, tool_to_session):
    """Execute a tool call on the appropriate MCP session and return result text."""
    session = tool_to_session.get(tool_name)
    if not session:
        return f"Error: unknown tool '{tool_name}'"

    result = await session.call_tool(tool_name, arguments=arguments)

    parts = []
    for content in result.content:
        if hasattr(content, "text"):
            parts.append(content.text)
        else:
            parts.append(str(content))

    text = "\n".join(parts)
    if result.isError:
        return f"Error: {text}"
    return text


# ── Chat loop ───────────────────────────────────────────────────────────────


async def chat_loop(model, ollama_tools, tool_to_session):
    """Interactive chat loop: user → Ollama → tool calls → MCP → Ollama → response."""
    client = ollama.AsyncClient()
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant with access to specialized tools. "
                "Use them when the user's request requires their functionality. "
                "Always rely on tool outputs rather than generating answers yourself "
                "for tasks the tools handle."
            ),
        }
    ]

    print("\nChat started. Type 'quit' to exit, '/clear' to reset history.\n")

    while True:
        try:
            user_input = await asyncio.to_thread(input, "You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye.")
            break
        if user_input == "/clear":
            messages = messages[:1]  # keep system message
            print("History cleared.\n")
            continue

        messages.append({"role": "user", "content": user_input})

        try:
            response = await client.chat(model=model, messages=messages, tools=ollama_tools)
        except ollama.ResponseError as e:
            print(f"Ollama error: {e}")
            messages.pop()  # remove failed user message
            continue

        # Tool call loop — model may chain multiple rounds of tool calls
        while response.message.tool_calls:
            messages.append(response.message)

            for tc in response.message.tool_calls:
                fn_name = tc.function.name
                fn_args = tc.function.arguments
                print(f"  [Calling {fn_name}({json.dumps(fn_args, ensure_ascii=False)[:200]})]")

                result_text = await execute_tool_call(fn_name, fn_args, tool_to_session)
                print(f"  [Result: {result_text[:200]}{'...' if len(result_text) > 200 else ''}]")

                messages.append({"role": "tool", "content": result_text, "name": fn_name})

            response = await client.chat(model=model, messages=messages, tools=ollama_tools)

        # Final text response
        messages.append(response.message)
        print(f"\nAssistant: {response.message.content}\n")


# ── Interactive startup ─────────────────────────────────────────────────────


async def select_model():
    """List available Ollama models and let user pick one."""
    try:
        models_response = await ollama.AsyncClient().list()
    except Exception as e:
        print(f"Cannot connect to Ollama: {e}")
        print("Make sure Ollama is running (ollama serve).")
        sys.exit(1)

    models = [m.model for m in models_response.models]
    if not models:
        print("No Ollama models found. Pull one first: ollama pull llama3.1")
        sys.exit(1)

    print("Available models:")
    for i, name in enumerate(models, 1):
        print(f"  {i}. {name}")

    choice = await asyncio.to_thread(input, f"Select model [1]: ")
    choice = choice.strip()
    if not choice:
        idx = 0
    else:
        try:
            idx = int(choice) - 1
        except ValueError:
            idx = 0
    idx = max(0, min(idx, len(models) - 1))
    return models[idx]


def select_plugins(plugins):
    """Display available plugins and let user pick."""
    print("\nAvailable plugins:")
    for i, p in enumerate(plugins, 1):
        print(f"  {i}. {p['name']} — {p['description'][:80]}")

    choice = input("Select plugins (comma-separated) [1]: ").strip()
    if not choice:
        indices = [0]
    else:
        try:
            indices = [int(x.strip()) - 1 for x in choice.split(",")]
        except ValueError:
            indices = [0]

    selected = []
    for idx in indices:
        if 0 <= idx < len(plugins):
            selected.append(plugins[idx])
    return selected or [plugins[0]]


# ── Main ────────────────────────────────────────────────────────────────────


async def main():
    parser = argparse.ArgumentParser(description="Ollama MCP Bridge")
    parser.add_argument("--model", help="Ollama model name (skip interactive selection)")
    parser.add_argument("--plugins", help="Comma-separated plugin names (skip interactive selection)")
    args = parser.parse_args()

    print("Ollama MCP Bridge")
    print("=" * 40)

    # Select model
    if args.model:
        model = args.model
        print(f"Model: {model}")
    else:
        model = await select_model()
    print(f"Using model: {model}\n")

    # Discover plugins
    plugins = discover_plugins()
    if not plugins:
        print("No plugins found in plugins/ directory")
        sys.exit(1)

    # Select plugins
    if args.plugins:
        requested = [n.strip() for n in args.plugins.split(",")]
        selected = [p for p in plugins if p["name"] in requested]
        if not selected:
            print(f"No matching plugins found for: {args.plugins}")
            sys.exit(1)
    else:
        selected = select_plugins(plugins)

    print(f"\nConnecting to {len(selected)} plugin(s)...")

    async with AsyncExitStack() as exit_stack:
        ollama_tools, tool_to_session = await connect_plugins(selected, exit_stack)

        if not ollama_tools:
            print("No tools loaded. Check plugin configuration and Docker status.")
            sys.exit(1)

        print(f"\nTools available ({len(ollama_tools)}):")
        for t in ollama_tools:
            fn = t["function"]
            desc = fn['description'].split('\n')[0]
            print(f"  - {fn['name']}: {desc}")

        await chat_loop(model, ollama_tools, tool_to_session)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye.")
