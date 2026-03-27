#!/usr/bin/env python3
"""
Reproduce experiments from:
  "Toward PDDL Planning Copilot" (Benyamin et al., 2025)
  https://arxiv.org/abs/2509.12987

Evaluates Ollama LLMs with and without MCP planning tools on 5 PDDL tasks:
  1. solve           — find a plan for a domain+problem
  2. validate_domain — check domain PDDL syntax
  3. validate_problem— check problem PDDL syntax
  4. validate_plan   — verify a plan is correct
  5. simulate        — produce a state-transition trace

Usage:
  pip3 install -r requirements.txt
  python3 run_experiment.py --models qwen3:0.5b qwen3:4b
  python3 run_experiment.py --models qwen3:4b --tasks solve validate_plan --chains
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
from collections import defaultdict
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass, field
from pathlib import Path

import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PLUGIN_DIR = REPO_ROOT / "plugins" / "pddl-solver"
DOMAINS_DIR = SCRIPT_DIR / "domains"
RESULTS_DIR = SCRIPT_DIR / "results"

# ---------------------------------------------------------------------------
# Defaults (from the paper)
# ---------------------------------------------------------------------------

DEFAULT_MODELS = ["qwen3:0.5b", "qwen3:4b"]
TEMPERATURE = 0.0
MAX_TOOL_LOOPS = 10
TASKS = ["solve", "validate_domain", "validate_problem", "validate_plan", "simulate"]

# ---------------------------------------------------------------------------
# System prompts (Section 4 of the paper)
# ---------------------------------------------------------------------------

WITH_TOOLS_SYSTEM = (
    "You are a PDDL planning assistant with access to planning tools. "
    "Your ONLY way to get information or solve problems is by calling the "
    "provided tools ONE AT A TIME — never guess or create plan details yourself."
)

WITHOUT_TOOLS_SYSTEM = (
    "You are a PDDL planning assistant. You must analyze PDDL problems, "
    "validate syntax, create plans, and simulate state transitions all on "
    "your own, without any external tools."
)

# ---------------------------------------------------------------------------
# Prompt templates — 5 variants per task (robustness, Section 4.1)
# ---------------------------------------------------------------------------

PROMPT_TEMPLATES: dict[str, list[str]] = {
    "solve": [
        "Solve the following PDDL planning problem.\n\nDomain:\n{domain}\n\nProblem:\n{problem}",
        "Find a valid plan for this PDDL problem.\n\nDomain definition:\n{domain}\n\nProblem definition:\n{problem}",
        "Generate a plan that solves the following planning problem.\n\nDomain:\n{domain}\n\nProblem:\n{problem}",
        "Given the PDDL domain and problem below, compute a solution plan.\n\nDomain:\n{domain}\n\nProblem:\n{problem}",
        "Please solve this automated planning task and return the plan.\n\n{domain}\n\n{problem}",
    ],
    "validate_domain": [
        "Check if this PDDL domain definition has valid syntax:\n\n{domain}",
        "Validate the following PDDL domain for syntactic correctness:\n\n{domain}",
        "Is this PDDL domain syntactically correct? Please check.\n\n{domain}",
        "Analyze this domain definition and tell me if the PDDL syntax is valid:\n\n{domain}",
        "Please verify the syntax of the following PDDL domain:\n\n{domain}",
    ],
    "validate_problem": [
        "Check if this PDDL problem has valid syntax given the domain.\n\nDomain:\n{domain}\n\nProblem:\n{problem}",
        "Validate the syntax of this PDDL problem against its domain:\n\nDomain:\n{domain}\n\nProblem:\n{problem}",
        "Is this PDDL problem file syntactically correct for the given domain?\n\nDomain:\n{domain}\n\nProblem:\n{problem}",
        "Verify the syntax of the following PDDL problem.\n\nDomain:\n{domain}\n\nProblem:\n{problem}",
        "Check the following PDDL problem for syntax errors.\n\nDomain:\n{domain}\n\nProblem:\n{problem}",
    ],
    "validate_plan": [
        "Validate whether this plan is correct for the given domain and problem.\n\nDomain:\n{domain}\n\nProblem:\n{problem}\n\nPlan:\n{plan}",
        "Check if the following plan solves the PDDL problem.\n\nDomain:\n{domain}\n\nProblem:\n{problem}\n\nPlan:\n{plan}",
        "Is this plan valid for the given planning problem?\n\nDomain:\n{domain}\n\nProblem:\n{problem}\n\nPlan:\n{plan}",
        "Verify the correctness of this plan.\n\nDomain:\n{domain}\n\nProblem:\n{problem}\n\nPlan:\n{plan}",
        "Does this plan achieve the goal? Validate it.\n\nDomain:\n{domain}\n\nProblem:\n{problem}\n\nPlan:\n{plan}",
    ],
    "simulate": [
        "Simulate the execution of this plan and show the state transitions.\n\nDomain:\n{domain}\n\nProblem:\n{problem}\n\nPlan:\n{plan}",
        "Trace the state changes when executing this plan step by step.\n\nDomain:\n{domain}\n\nProblem:\n{problem}\n\nPlan:\n{plan}",
        "Show me the state after each action in this plan.\n\nDomain:\n{domain}\n\nProblem:\n{problem}\n\nPlan:\n{plan}",
        "Execute this plan and provide the state transition trace.\n\nDomain:\n{domain}\n\nProblem:\n{problem}\n\nPlan:\n{plan}",
        "Walk through this plan action by action and show each intermediate state.\n\nDomain:\n{domain}\n\nProblem:\n{problem}\n\nPlan:\n{plan}",
    ],
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TaskResult:
    model: str
    task: str
    domain_name: str
    problem_name: str
    prompt_variant: int
    with_tools: bool
    success: bool
    response: str
    tool_calls: list = field(default_factory=list)
    duration_s: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# MCP connection (mirrors ollama_mcp_bridge.py patterns)
# ---------------------------------------------------------------------------


class MCPPlanner:
    """Manages a stdio connection to the PDDL planning MCP server."""

    def __init__(self):
        self.stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.tools: list[dict] = []

    async def connect(self):
        launch_script = PLUGIN_DIR / "scripts" / "launch-server.sh"
        if not launch_script.exists():
            sys.exit(f"Launch script not found: {launch_script}")

        server_params = StdioServerParameters(
            command="bash",
            args=[str(launch_script)],
            env={**os.environ, "HOST_PWD": os.getcwd()},
        )
        read_stream, write_stream = await self.stack.enter_async_context(
            stdio_client(server_params)
        )
        self.session = await self.stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self.session.initialize()

        tools_result = await self.session.list_tools()
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                },
            }
            for t in tools_result.tools
        ]
        names = [t["function"]["name"] for t in self.tools]
        print(f"  MCP connected — tools: {names}")

    async def call_tool(self, name: str, arguments: dict) -> str:
        result = await self.session.call_tool(name, arguments=arguments)
        return result.content[0].text if result.content else ""

    async def close(self):
        await self.stack.aclose()


# ---------------------------------------------------------------------------
# Ollama chat helpers
# ---------------------------------------------------------------------------


async def chat_with_tools(
    model: str,
    messages: list[dict],
    mcp: MCPPlanner,
    max_loops: int = MAX_TOOL_LOOPS,
    temperature: float = TEMPERATURE,
) -> tuple[str, list[dict]]:
    """Send messages to Ollama, handle tool-call loops. Returns (text, tool_calls_log)."""
    tool_calls_log: list[dict] = []

    for _ in range(max_loops):
        resp = ollama.chat(
            model=model,
            messages=messages,
            tools=mcp.tools,
            options={"temperature": temperature},
        )
        msg = resp["message"]
        messages.append(msg)

        if not msg.get("tool_calls"):
            return msg.get("content", ""), tool_calls_log

        for tc in msg["tool_calls"]:
            fn = tc["function"]
            tool_name = fn["name"]
            tool_args = fn.get("arguments", {})
            tool_calls_log.append({"name": tool_name, "arguments": tool_args})

            try:
                result_text = await mcp.call_tool(tool_name, tool_args)
            except Exception as exc:
                result_text = f"Tool error: {exc}"

            messages.append({"role": "tool", "content": result_text})

    # Exhausted loops — return last content
    last = messages[-1]
    return last.get("content", "") if isinstance(last, dict) else "", tool_calls_log


def chat_without_tools(
    model: str,
    messages: list[dict],
    temperature: float = TEMPERATURE,
) -> str:
    resp = ollama.chat(
        model=model,
        messages=messages,
        options={"temperature": temperature},
    )
    return resp["message"].get("content", "")


# ---------------------------------------------------------------------------
# Domain / problem loading
# ---------------------------------------------------------------------------


def load_domains(domains_dir: Path) -> dict:
    """
    Load PDDL domains from:
        domains/{classical,numeric}/<name>/domain.pddl
        domains/{classical,numeric}/<name>/p*.pddl

    Returns {name: {"type": str, "domain": str, "problems": {pname: str}}}.
    """
    domains: dict = {}
    for dtype in ("classical", "numeric"):
        type_dir = domains_dir / dtype
        if not type_dir.is_dir():
            continue
        for ddir in sorted(type_dir.iterdir()):
            if not ddir.is_dir():
                continue
            domain_file = ddir / "domain.pddl"
            if not domain_file.exists():
                continue
            problems = {
                pf.stem: pf.read_text()
                for pf in sorted(ddir.glob("p*.pddl"))
            }
            if problems:
                domains[ddir.name] = {
                    "type": dtype,
                    "domain": domain_file.read_text(),
                    "problems": problems,
                }
    return domains


# ---------------------------------------------------------------------------
# Ground-truth oracle (use MCP tools as reference, Section 4.2)
# ---------------------------------------------------------------------------


async def generate_ground_truth(mcp: MCPPlanner, domains: dict) -> dict:
    """For each domain/problem, solve and validate using the MCP tools as oracle."""
    gt: dict = {}
    for dname, dinfo in domains.items():
        gt[dname] = {}
        planner = "classic_planner" if dinfo["type"] == "classical" else "numeric_planner"
        for pname, ppddl in dinfo["problems"].items():
            entry: dict = {
                "domain_valid": True,
                "problem_valid": True,
                "solvable": False,
                "plan": None,
                "trace": None,
            }

            # Validate domain
            try:
                raw = await mcp.call_tool("validate_pddl_syntax", {"domain": dinfo["domain"]})
                entry["domain_validation_raw"] = raw
            except Exception as exc:
                entry["domain_validation_raw"] = str(exc)

            # Validate problem
            try:
                raw = await mcp.call_tool(
                    "validate_pddl_syntax",
                    {"domain": dinfo["domain"], "problem": ppddl},
                )
                entry["problem_validation_raw"] = raw
            except Exception as exc:
                entry["problem_validation_raw"] = str(exc)

            # Solve
            try:
                raw = await mcp.call_tool(planner, {"domain": dinfo["domain"], "problem": ppddl})
                data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(data, dict) and "plan" in data:
                    entry["plan"] = data["plan"]
                    entry["solvable"] = True
            except Exception:
                pass

            # State trace
            if entry["plan"]:
                try:
                    plan_str = "\n".join(entry["plan"]) if isinstance(entry["plan"], list) else entry["plan"]
                    entry["trace"] = await mcp.call_tool(
                        "get_state_transition",
                        {"domain": dinfo["domain"], "problem": ppddl, "plan": plan_str},
                    )
                except Exception:
                    pass

            gt[dname][pname] = entry
            tag = "solvable" if entry["solvable"] else "unsolvable"
            print(f"    {dname}/{pname}: {tag}")
    return gt


# ---------------------------------------------------------------------------
# Success checking (Section 4.3 — evaluation criteria)
# ---------------------------------------------------------------------------


def _used_tool(tool_calls: list[dict], name: str) -> bool:
    return any(tc["name"] == name for tc in tool_calls)


def check_success(task: str, response: str, tool_calls: list[dict], gt: dict) -> bool:
    """Decide whether a model response counts as task success."""
    resp = (response or "").lower()

    if task == "solve":
        if tool_calls:
            return _used_tool(tool_calls, "classic_planner") or _used_tool(tool_calls, "numeric_planner")
        # Without tools: check if the response contains actions from the ground-truth plan
        if gt.get("plan"):
            actions = [a.lower().strip("() ").split()[0] for a in gt["plan"] if a.strip()]
            return sum(1 for a in actions if a in resp) >= len(actions) // 2
        return False

    if task == "validate_domain":
        if tool_calls:
            return _used_tool(tool_calls, "validate_pddl_syntax")
        return "valid" in resp and "invalid" not in resp

    if task == "validate_problem":
        if tool_calls:
            return _used_tool(tool_calls, "validate_pddl_syntax")
        return "valid" in resp and "invalid" not in resp

    if task == "validate_plan":
        if tool_calls:
            return _used_tool(tool_calls, "validate_pddl_syntax")
        return "valid" in resp

    if task == "simulate":
        if tool_calls:
            return _used_tool(tool_calls, "get_state_transition")
        return "state" in resp and ("after" in resp or "step" in resp)

    return False


# ---------------------------------------------------------------------------
# Single-task evaluation
# ---------------------------------------------------------------------------


async def evaluate_one(
    model: str,
    task: str,
    domain_name: str,
    domain_pddl: str,
    problem_name: str,
    problem_pddl: str,
    prompt_variant: int,
    with_tools: bool,
    mcp: MCPPlanner,
    gt: dict,
) -> TaskResult:
    template = PROMPT_TEMPLATES[task][prompt_variant % len(PROMPT_TEMPLATES[task])]

    plan_str = ""
    if task in ("validate_plan", "simulate") and gt.get("plan"):
        plan_str = "\n".join(gt["plan"]) if isinstance(gt["plan"], list) else gt["plan"]

    prompt = template.format(domain=domain_pddl, problem=problem_pddl, plan=plan_str)
    system = WITH_TOOLS_SYSTEM if with_tools else WITHOUT_TOOLS_SYSTEM
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    t0 = time.time()
    tool_calls: list[dict] = []
    error = ""
    response_text = ""

    try:
        if with_tools:
            response_text, tool_calls = await chat_with_tools(model, messages, mcp)
        else:
            response_text = chat_without_tools(model, messages)
    except Exception as exc:
        error = str(exc)

    duration = time.time() - t0
    success = check_success(task, response_text, tool_calls, gt) if not error else False

    return TaskResult(
        model=model,
        task=task,
        domain_name=domain_name,
        problem_name=problem_name,
        prompt_variant=prompt_variant,
        with_tools=with_tools,
        success=success,
        response=response_text[:500],
        tool_calls=tool_calls,
        duration_s=round(duration, 2),
        error=error,
    )


async def run_single_task_experiment(
    models: list[str],
    tasks: list[str],
    domains: dict,
    ground_truth: dict,
    mcp: MCPPlanner,
    num_variants: int = 5,
) -> list[TaskResult]:
    results: list[TaskResult] = []
    total = (
        len(models) * 2 * len(tasks)
        * sum(len(d["problems"]) for d in domains.values())
        * num_variants
    )
    done = 0

    for model in models:
        for with_tools in (True, False):
            cond = "tools" if with_tools else "no-tools"
            for task in tasks:
                for dname, dinfo in domains.items():
                    for pname, ppddl in dinfo["problems"].items():
                        gt = ground_truth.get(dname, {}).get(pname, {})
                        # Skip plan/simulate tasks when problem is unsolvable
                        if task in ("validate_plan", "simulate") and not gt.get("plan"):
                            done += num_variants
                            continue
                        for pv in range(num_variants):
                            done += 1
                            label = f"[{done}/{total}] {model}|{cond}|{task}|{dname}/{pname} v{pv}"
                            print(f"  {label}", end="", flush=True)

                            r = await evaluate_one(
                                model, task, dname, dinfo["domain"],
                                pname, ppddl, pv, with_tools, mcp, gt,
                            )
                            results.append(r)
                            mark = "OK" if r.success else "FAIL"
                            print(f" -> {mark} ({r.duration_s}s)")
    return results


# ---------------------------------------------------------------------------
# Multi-task chain evaluation (Section 4.4)
# ---------------------------------------------------------------------------


async def run_chain_experiment(
    models: list[str],
    domains: dict,
    ground_truth: dict,
    mcp: MCPPlanner,
    chain_lengths: list[int] = [2, 3, 4, 5],
    samples: int = 20,
) -> list[dict]:
    results: list[dict] = []
    domain_items = list(domains.items())

    for model in models:
        for n in chain_lengths:
            successes = 0
            for i in range(samples):
                dname, dinfo = random.choice(domain_items)
                pname = random.choice(list(dinfo["problems"].keys()))
                ppddl = dinfo["problems"][pname]
                gt = ground_truth.get(dname, {}).get(pname, {})

                chain_tasks = random.choices(TASKS, k=n)
                messages: list[dict] = [{"role": "system", "content": WITH_TOOLS_SYSTEM}]
                chain_ok = True

                for task in chain_tasks:
                    template = random.choice(PROMPT_TEMPLATES[task])
                    plan_str = ""
                    if task in ("validate_plan", "simulate") and gt.get("plan"):
                        plan_str = (
                            "\n".join(gt["plan"]) if isinstance(gt["plan"], list) else gt["plan"]
                        )
                    prompt = template.format(
                        domain=dinfo["domain"], problem=ppddl, plan=plan_str,
                    )
                    messages.append({"role": "user", "content": prompt})

                    try:
                        resp_text, tc = await chat_with_tools(model, messages, mcp)
                        if not check_success(task, resp_text, tc, gt):
                            chain_ok = False
                            break
                    except Exception:
                        chain_ok = False
                        break

                if chain_ok:
                    successes += 1
                mark = "OK" if chain_ok else "FAIL"
                print(f"  {model} chain={n} [{i+1}/{samples}] {mark}")

            results.append({
                "model": model,
                "chain_length": n,
                "samples": samples,
                "successes": successes,
                "success_rate": round(successes / samples, 2),
            })
    return results


# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------


def print_single_task_table(results: list[TaskResult]):
    """Reproduce Table 1 from the paper."""
    agg: dict = defaultdict(lambda: {"total": 0, "success": 0})
    for r in results:
        cond = "tools" if r.with_tools else "no-tools"
        key = (r.model, cond, r.task)
        agg[key]["total"] += 1
        if r.success:
            agg[key]["success"] += 1

    models = sorted(set(r.model for r in results))
    tasks_present = [t for t in TASKS if any(r.task == t for r in results)]

    col_w = max(len(t) for t in tasks_present) + 2
    row_fmt = "{:<28} {:<10}" + " {:<" + str(col_w) + "}" * len(tasks_present)

    print("\n" + "=" * (42 + col_w * len(tasks_present)))
    print("SINGLE-TASK SUCCESS RATES (Table 1 reproduction)")
    print("=" * (42 + col_w * len(tasks_present)))
    print(row_fmt.format("Model", "Condition", *tasks_present))
    print("-" * (42 + col_w * len(tasks_present)))

    for model in models:
        for cond in ("tools", "no-tools"):
            rates = []
            for task in tasks_present:
                d = agg[(model, cond, task)]
                rate = d["success"] / d["total"] if d["total"] > 0 else 0.0
                rates.append(f"{rate:.2f}")
            print(row_fmt.format(model, cond, *rates))

    print("=" * (42 + col_w * len(tasks_present)))


def print_chain_table(chain_results: list[dict]):
    if not chain_results:
        return
    models = sorted(set(r["model"] for r in chain_results))
    lengths = sorted(set(r["chain_length"] for r in chain_results))

    print("\n" + "=" * 60)
    print("MULTI-TASK CHAIN SUCCESS RATES")
    print("=" * 60)
    header = f"{'Model':<28}" + "".join(f" {'n='+str(n):<10}" for n in lengths)
    print(header)
    print("-" * len(header))
    for model in models:
        row = f"{model:<28}"
        for n in lengths:
            match = [r for r in chain_results if r["model"] == model and r["chain_length"] == n]
            row += f" {match[0]['success_rate']:<10.2f}" if match else f" {'--':<10}"
        print(row)
    print("=" * 60)


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def save_results(
    single: list[TaskResult],
    chains: list[dict],
    output_dir: Path,
):
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    p1 = output_dir / f"single_task_{ts}.json"
    p1.write_text(json.dumps([asdict(r) for r in single], indent=2))
    print(f"\nSaved single-task results -> {p1}")

    if chains:
        p2 = output_dir / f"chain_{ts}.json"
        p2.write_text(json.dumps(chains, indent=2))
        print(f"Saved chain results       -> {p2}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def async_main(args):
    print("=" * 60)
    print("PDDL Planning Copilot — Experiment Runner")
    print("Reproducing: Benyamin et al., 2025 (arXiv:2509.12987)")
    print("=" * 60)
    print(f"  Models:     {args.models}")
    print(f"  Tasks:      {args.tasks}")
    print(f"  Domains:    {args.domains_dir}")
    print(f"  Variants:   {args.num_variants}")
    print(f"  Temperature:{args.temperature}")

    # Load domains
    domains = load_domains(Path(args.domains_dir))
    if not domains:
        sys.exit(f"No domains found in {args.domains_dir}")
    n_problems = sum(len(d["problems"]) for d in domains.values())
    print(f"\n  Loaded {len(domains)} domains, {n_problems} problems total")
    for dname, dinfo in domains.items():
        print(f"    {dname} ({dinfo['type']}): {len(dinfo['problems'])} problems")

    # Connect MCP
    print("\nConnecting to MCP planning server...")
    mcp = MCPPlanner()
    await mcp.connect()

    try:
        # Ground truth
        print("\nGenerating ground truth (solving all problems with planners)...")
        ground_truth = await generate_ground_truth(mcp, domains)

        # Single-task
        print("\n--- Single-Task Evaluation ---")
        single_results = await run_single_task_experiment(
            models=args.models,
            tasks=args.tasks,
            domains=domains,
            ground_truth=ground_truth,
            mcp=mcp,
            num_variants=args.num_variants,
        )
        print_single_task_table(single_results)

        # Multi-task chains
        chain_results: list[dict] = []
        if args.chains:
            print("\n--- Multi-Task Chain Evaluation ---")
            chain_results = await run_chain_experiment(
                models=args.models,
                domains=domains,
                ground_truth=ground_truth,
                mcp=mcp,
                chain_lengths=[2, 3, 4, 5],
                samples=args.chain_samples,
            )
            print_chain_table(chain_results)

        # Save
        save_results(single_results, chain_results, Path(args.output_dir))

    finally:
        await mcp.close()


def main():
    p = argparse.ArgumentParser(
        description="Reproduce PDDL Planning Copilot experiments (arXiv:2509.12987)",
    )
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS,
                   help="Ollama model names to evaluate")
    p.add_argument("--tasks", nargs="+", default=TASKS, choices=TASKS,
                   help="Tasks to evaluate")
    p.add_argument("--domains-dir", default=str(DOMAINS_DIR),
                   help="Path to domains directory")
    p.add_argument("--output-dir", default=str(RESULTS_DIR),
                   help="Path to save result JSON files")
    p.add_argument("--num-variants", type=int, default=5,
                   help="Prompt variants per task (paper uses 5)")
    p.add_argument("--temperature", type=float, default=TEMPERATURE,
                   help="LLM sampling temperature (paper uses 0)")
    p.add_argument("--chains", action="store_true",
                   help="Also run multi-task chain evaluation")
    p.add_argument("--chain-samples", type=int, default=20,
                   help="Samples per chain length")
    p.add_argument("--seed", type=int, default=42,
                   help="Random seed for chain sampling")
    args = p.parse_args()

    random.seed(args.seed)
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
