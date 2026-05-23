# Ollama MCP Bridge

A standalone CLI that connects local Ollama models to the MCP plugins in this marketplace. Lets open-source LLMs use the same planning tools as Claude Code.

This is an **example / reference integration**, not a maintained plugin. It is not exercised by CI and may lag behind plugin changes.

## Setup

From the repo root:

```bash
pip3 install -r examples/ollama-bridge/requirements.txt
```

## Usage

Interactive:

```bash
python3 examples/ollama-bridge/ollama_mcp_bridge.py
```

Non-interactive:

```bash
python3 examples/ollama-bridge/ollama_mcp_bridge.py --model qwen3:4b --plugins pddl-solver,pddl-validator,pddl-parser
```

The bridge discovers plugins by scanning `plugins/*/CLAUDE.md` + `plugins/*/.mcp.json` from the repo root, so it must be run from within a checkout of this repository.

## Requirements

- [Ollama](https://ollama.com) installed and running (`ollama serve`)
- A model with tool-calling support (e.g., `llama3.1`, `qwen3`, `mistral`)
- Python 3.10+
