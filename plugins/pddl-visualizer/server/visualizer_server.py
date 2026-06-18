"""
visualizer_server.py — MCP server for rendering PDDL states and trajectories
to images.

Domain-independent: a state is rendered as a graph where objects are nodes,
unary predicates become node properties, binary predicates become labelled
edges, n-ary predicates become predicate-nodes wired to their arguments, and
numeric fluents become node/global annotations. No PDDL parsing or simulation
happens here — the input is the grounded predicate-string state that
pddl-parser / pddl-validator already emit, so this plugin stays a pure render
function with no planner/parser dependency.

Pure pip (Tier 1): networkx for graph layout, matplotlib (Agg) for rendering,
Pillow for GIF assembly. No system binaries (deliberately NOT graphviz/dot).
"""

import io
import json
import os
import re
import textwrap
import time
import uuid
from typing import Annotated, Literal, Optional, Union

import matplotlib
matplotlib.use("Agg")  # headless; must precede pyplot import
import matplotlib.pyplot as plt
from matplotlib.transforms import Bbox
import networkx as nx
from PIL import Image

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from pydantic import Field, ValidationError


# NOTE: this class is duplicated verbatim in pddl-solver, pddl-validator and
# pddl-parser. The marketplace plugin-isolation rule
# (.claude/rules/marketplace.md) forbids cross-plugin imports; each plugin must
# be installable standalone. Don't try to "DRY" this into a shared module — it
# would break isolation. Fix it in all places when changing the payload
# contract.
class _StructuredArgErrorFastMCP(FastMCP):
    """FastMCP subclass that converts pydantic arg-validation errors into a
    one-line structured payload so small models can parse and recover.

    FastMCP wraps every tool exception in ToolError("Error executing tool ...");
    when the inner cause is a pydantic ValidationError we emit a fixed 7-key
    payload (error/errcode/tool/missing/required/supplied/message) as
    isError=True content. Non-ValidationError ToolErrors are re-raised so the
    existing lowlevel error path is unchanged."""

    async def call_tool(self, name, arguments, *args, **kwargs):
        try:
            return await super().call_tool(name, arguments, *args, **kwargs)
        except ToolError as e:
            cause = getattr(e, "__cause__", None)
            if not isinstance(cause, ValidationError):
                raise
            tool = self._tool_manager.get_tool(name)
            if tool is None:
                raise
            required = [
                (fi.alias or fname)
                for fname, fi in tool.fn_metadata.arg_model.model_fields.items()
                if fi.is_required()
            ]
            supplied = list((arguments or {}).keys())
            errs = cause.errors()
            missing = [
                str(err["loc"][0])
                for err in errs
                if err.get("type") == "missing" and err.get("loc")
            ]
            if missing:
                errcode = "missing_required_arg"
                message = (
                    f"{name}: missing required argument {missing[0]!r}. "
                    f"Required args: {', '.join(required)}."
                )
            else:
                errcode = "arg_validation_failed"
                first = errs[0] if errs else {"msg": "invalid", "loc": ("?",)}
                bad_loc = first.get("loc") or ("?",)
                bad_arg = str(bad_loc[0])
                message = f"{name}: argument {bad_arg!r}: {first.get('msg', 'invalid')}."
            payload = {
                "error": True,
                "errcode": errcode,
                "tool": name,
                "missing": missing,
                "required": required,
                "supplied": supplied,
                "message": message,
            }
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text=json.dumps(payload))],
            )


mcp = _StructuredArgErrorFastMCP("pddl-visualizer")

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
DEFAULT_RENDER_DIR = os.path.expanduser(
    os.environ.get("PDDL_RENDER_DIR", "~/pddl-renders")
)

# Fixed pixel canvas for every frame. GIF frames MUST share dimensions, so we
# render at a constant figsize*dpi and never use bbox_inches="tight" for
# multi-frame output.
FIG_W, FIG_H, DPI = 8.0, 6.0, 100

# Palette
C_OBJECT = "#aed6f1"      # object node fill
C_PRED = "#f5cba7"        # n-ary predicate node fill
C_ADDED = "#abebc6"       # highlight: fact added since previous frame
C_ADDED_EDGE = "#27ae60"
C_EDGE = "#566573"

# ---------------------------------------------------------------------------
# State-string parsing (pure Python — no PDDL library)
# ---------------------------------------------------------------------------

# Heads that wrap a list of predicates rather than being a predicate themselves.
_WRAPPER_HEADS = (":init", ":state", ":goal")


def _toplevel_sexprs(s: str) -> list[str]:
    """Return every balanced top-level ``(...)`` group in ``s`` (ignores any
    text outside parentheses)."""
    out, depth, start = [], 0, None
    for i, ch in enumerate(s):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    out.append(s[start : i + 1])
                    start = None
    return out


def _sexpr_tokens(inner: str) -> list[str]:
    """Split the inside of one s-expression into top-level tokens. Atoms split
    on whitespace; nested ``(...)`` groups are kept intact as single tokens.
    e.g. ``"= (fuel truck) 5"`` -> ``["=", "(fuel truck)", "5"]``."""
    toks, depth, cur = [], 0, ""
    for ch in inner:
        if ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch.isspace() and depth == 0:
            if cur:
                toks.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        toks.append(cur)
    return toks


def extract_predicates(state: Union[str, list]) -> list[str]:
    """Normalise any accepted state form into a flat list of predicate
    s-expression strings.

    Accepts:
      - a list of predicate strings (already split),
      - a JSON array string ``'["(on a b)", ...]'``,
      - a PDDL state string, wrapped (``(:init (on a b) ...)`` /
        ``(:state ...)`` / ``(:goal ...)``) or a bare predicate sequence
        (``(on a b) (clear a)``).
    """
    if isinstance(state, list):
        return [str(p).strip() for p in state if str(p).strip()]

    s = (state or "").strip()
    if not s:
        return []
    if s.startswith("["):
        return [str(p).strip() for p in json.loads(s) if str(p).strip()]

    groups = _toplevel_sexprs(s)
    # A single wrapper group like (:init ...) -> unwrap and re-extract.
    if len(groups) == 1:
        inner = groups[0][1:-1].strip()
        toks = _sexpr_tokens(inner)
        if toks and toks[0].lower() in _WRAPPER_HEADS:
            return _toplevel_sexprs(inner[len(toks[0]):])
    return groups


def parse_predicate(sexpr: str) -> dict:
    """Classify one predicate s-expression.

    Returns a dict with ``kind`` in {flag, unary, binary, nary, numeric, malformed}
    plus the relevant fields:
      flag    -> {name}
      unary   -> {name, arg}
      binary  -> {name, a, b}
      nary    -> {name, args}
      numeric -> {func, args, value}     # (= (fuel t) 5) or (= (total-cost) 3)
    """
    inner = sexpr.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1].strip()
    toks = _sexpr_tokens(inner)
    if not toks:
        return {"kind": "malformed", "raw": sexpr}

    head = toks[0]
    if head in ("=", "assign") and len(toks) >= 3:
        fterm = toks[1]
        finner = fterm[1:-1].strip() if fterm.startswith("(") else fterm
        ftoks = _sexpr_tokens(finner)
        func = ftoks[0] if ftoks else fterm
        return {
            "kind": "numeric",
            "func": func,
            "args": ftoks[1:],
            "value": toks[-1],
        }

    args = toks[1:]
    if len(args) == 0:
        return {"kind": "flag", "name": head}
    if len(args) == 1:
        return {"kind": "unary", "name": head, "arg": args[0]}
    if len(args) == 2:
        return {"kind": "binary", "name": head, "a": args[0], "b": args[1]}
    return {"kind": "nary", "name": head, "args": args}


# ---------------------------------------------------------------------------
# Graph model
# ---------------------------------------------------------------------------

class StateModel:
    """The renderable interpretation of one state."""

    def __init__(self, predicates: list[str]):
        self.objects: list[str] = []          # preserves first-seen order
        self.node_props: dict[str, list[str]] = {}   # obj -> unary pred names
        self.node_numeric: dict[str, list[str]] = {} # obj -> ["fuel=5", ...]
        self.binary: list[tuple[str, str, str]] = [] # (a, b, name)
        self.nary: list[tuple[str, list[str]]] = []  # (name, args)
        self.flags: list[str] = []                   # 0-arity predicate names
        self.global_numeric: list[str] = []          # "(total-cost)=3"
        self.malformed: list[str] = []

        for sx in predicates:
            self._add(sx, parse_predicate(sx))

    def _see(self, obj: str) -> None:
        if obj not in self.node_props:
            self.node_props[obj] = []
            self.node_numeric[obj] = []
            self.objects.append(obj)

    def _add(self, raw: str, p: dict) -> None:
        kind = p["kind"]
        if kind == "flag":
            self.flags.append(p["name"])
        elif kind == "unary":
            self._see(p["arg"])
            self.node_props[p["arg"]].append(p["name"])
        elif kind == "binary":
            self._see(p["a"])
            self._see(p["b"])
            self.binary.append((p["a"], p["b"], p["name"]))
        elif kind == "nary":
            for a in p["args"]:
                self._see(a)
            self.nary.append((p["name"], p["args"]))
        elif kind == "numeric":
            label = f"{p['func']}={p['value']}"
            if p["args"]:
                tgt = p["args"][0]
                self._see(tgt)
                self.node_numeric[tgt].append(label)
            else:
                self.global_numeric.append(label)
        else:
            self.malformed.append(raw)

    def node_label(self, obj: str) -> str:
        lines = [obj]
        if self.node_props.get(obj):
            lines.append("[" + ", ".join(sorted(self.node_props[obj])) + "]")
        if self.node_numeric.get(obj):
            lines.append("\n".join(sorted(self.node_numeric[obj])))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Layout & rendering
# ---------------------------------------------------------------------------

def _layout(objects: list[str], binary: list[tuple], kind: str) -> dict:
    """Compute a {object: (x, y)} layout from object nodes + binary edges.
    spring_layout is seeded for determinism (stable frames across a
    trajectory)."""
    g = nx.DiGraph()
    g.add_nodes_from(objects)
    for a, b, _ in binary:
        g.add_edge(a, b)
    if g.number_of_nodes() == 0:
        return {}
    if kind == "circular":
        return nx.circular_layout(g)
    if kind == "shell":
        return nx.shell_layout(g)
    if kind == "kamada_kawai":
        try:
            return nx.kamada_kawai_layout(g)
        except Exception:
            pass  # needs scipy / connected graph; fall through to spring
    return nx.spring_layout(g, seed=42, k=1.2)


def _centroid(points: list[tuple]) -> tuple:
    if not points:
        return (0.0, 0.0)
    return (sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points))


def _draw_state(model: StateModel, pos: dict, ax, title: Optional[str],
                added: Optional[set]) -> list:
    """Draw one state onto a matplotlib axis. ``added`` is the set of raw
    predicate strings new vs. the previous frame (highlighted in green).

    Returns the artists (node markers + text labels) whose rendered extents
    must be fitted into the axis by ``_fitted_limits`` so nothing clips."""
    added = added or set()
    ax.axis("off")
    if title:
        # Wrap long titles (e.g. verbose grounded action names) so they don't
        # overrun the panel width and collide with neighbours in a filmstrip.
        ax.set_title(textwrap.fill(title, width=38), fontsize=11,
                     fontweight="bold")

    # Predicate-nodes for n-ary predicates, positioned at the centroid of their
    # arguments (deterministic; keeps the shared object layout stable).
    pred_nodes = {}
    g = nx.DiGraph()
    for o in model.objects:
        g.add_node(o)
    for i, (name, args) in enumerate(model.nary):
        pid = f"__pred{i}__{name}"
        pred_nodes[pid] = name
        pts = [pos[a] for a in args if a in pos]
        pos[pid] = _centroid(pts)
        g.add_node(pid)
        for a in args:
            if a in pos:
                g.add_edge(pid, a)

    # Binary edges, accumulating multi-labels per ordered pair.
    edge_labels: dict[tuple, list[str]] = {}
    for a, b, name in model.binary:
        g.add_edge(a, b)
        edge_labels.setdefault((a, b), []).append(name)
    added_edges = set()
    for raw in added:
        p = parse_predicate(raw)
        if p["kind"] == "binary":
            added_edges.add((p["a"], p["b"]))

    if g.number_of_nodes() == 0:
        ax.text(0.5, 0.5, "(empty state)", ha="center", va="center",
                fontsize=14, transform=ax.transAxes, color="#888")
        return []

    # Added object nodes (touched by any added predicate).
    added_objs = set()
    for raw in added:
        p = parse_predicate(raw)
        for key in ("arg", "a", "b"):
            if key in p:
                added_objs.add(p[key])
        if p["kind"] == "nary":
            added_objs.update(p["args"])

    extent_artists = []
    obj_colors = [C_ADDED if o in added_objs else C_OBJECT
                  for o in model.objects]
    extent_artists.append(nx.draw_networkx_nodes(
        g, pos, nodelist=model.objects, ax=ax, node_color=obj_colors,
        node_size=2200, edgecolors="#34495e", linewidths=1.2))
    if pred_nodes:
        extent_artists.append(nx.draw_networkx_nodes(
            g, pos, nodelist=list(pred_nodes), ax=ax, node_color=C_PRED,
            node_shape="s", node_size=1400, edgecolors="#b9770e",
            linewidths=1.0))

    # Edges: split into added vs normal for colouring.
    norm_edges = [(a, b) for (a, b) in g.edges() if (a, b) not in added_edges]
    hot_edges = [(a, b) for (a, b) in g.edges() if (a, b) in added_edges]
    nx.draw_networkx_edges(g, pos, edgelist=norm_edges, ax=ax,
                           edge_color=C_EDGE, arrows=True, arrowsize=16,
                           node_size=2200, width=1.3)
    if hot_edges:
        nx.draw_networkx_edges(g, pos, edgelist=hot_edges, ax=ax,
                               edge_color=C_ADDED_EDGE, arrows=True,
                               arrowsize=18, node_size=2200, width=2.4)

    # clip_on=False: keep full label extents so _fitted_limits can size the axis
    # around them (networkx clips labels to the axes by default, which both hides
    # text AND drops it from the extent calc → the clipping we are preventing).
    labels = {o: model.node_label(o) for o in model.objects}
    labels.update(pred_nodes)
    text_items = nx.draw_networkx_labels(g, pos, labels=labels, ax=ax,
                                         font_size=8, clip_on=False)
    extent_artists.extend(text_items.values())
    el_items = nx.draw_networkx_edge_labels(
        g, pos, ax=ax, font_size=7, font_color="#1b4f72", clip_on=False,
        edge_labels={k: "\n".join(v) for k, v in edge_labels.items()})
    extent_artists.extend(el_items.values())

    # Side panel (pinned to the axes corner in axes-fraction coords, so it is
    # NOT part of extent-fitting): 0-arity flags + global numerics + malformed.
    side = []
    if model.flags:
        side.append("flags: " + ", ".join(sorted(model.flags)))
    if model.global_numeric:
        side.append("numeric: " + ", ".join(sorted(model.global_numeric)))
    if model.malformed:
        side.append(f"(skipped {len(model.malformed)} unparsed)")
    if side:
        ax.text(0.01, 0.01, "\n".join(side), transform=ax.transAxes,
                fontsize=8, va="bottom", ha="left", color="#566573",
                bbox=dict(boxstyle="round", fc="#fdfefe", ec="#d5d8dc"))

    return extent_artists


# Limit-fitting: networkx sizes the axis tightly around node *centers*, so the
# (display-sized) node markers and the wide multi-line labels overflow and clip.
# After a draw pass we measure the true rendered extents and set the data limits
# to contain them. Trajectories share one unioned window across frames so node
# positions stay pixel-stable as the animation plays.

def _fitted_limits(ax, artists: list, renderer):
    """Return ((x0, x1), (y0, y1)) data limits enclosing ``artists`` (+ pad),
    or None if nothing measurable was drawn."""
    boxes = []
    for art in artists:
        try:
            bb = art.get_window_extent(renderer)
        except Exception:
            continue
        if bb is not None and bb.width > 0 and bb.height > 0:
            boxes.append(bb)
    if not boxes:
        return None
    u = Bbox.union(boxes)
    inv = ax.transData.inverted()
    (x0, y0), (x1, y1) = inv.transform([(u.x0, u.y0), (u.x1, u.y1)])
    xlo, xhi = sorted((x0, x1))
    ylo, yhi = sorted((y0, y1))
    pad_x = (xhi - xlo) * 0.13 or 0.15
    pad_y = (yhi - ylo) * 0.13 or 0.15
    return ((xlo - pad_x, xhi + pad_x), (ylo - pad_y, yhi + pad_y))


def _union_limits(a, b):
    if a is None:
        return b
    if b is None:
        return a
    (ax0, ax1), (ay0, ay1) = a
    (bx0, bx1), (by0, by1) = b
    return ((min(ax0, bx0), max(ax1, bx1)), (min(ay0, by0), max(ay1, by1)))


def _apply_limits(ax, lims) -> None:
    if lims is None:
        return
    (x0, x1), (y0, y1) = lims
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)


def _fig_to_image(fig) -> Image.Image:
    """Rasterise a figure to a fixed-size RGB PIL image (no tight bbox, so all
    GIF frames share dimensions)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _resolve_output(output_path: Optional[str], stem: str, ext: str) -> str:
    if output_path:
        path = os.path.expanduser(output_path.strip())
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return path
    os.makedirs(DEFAULT_RENDER_DIR, exist_ok=True)
    path = os.path.join(DEFAULT_RENDER_DIR, f"{stem}.{ext}")
    if os.path.exists(path):
        n = 1
        while os.path.exists(os.path.join(DEFAULT_RENDER_DIR, f"{stem}_{n}.{ext}")):
            n += 1
        path = os.path.join(DEFAULT_RENDER_DIR, f"{stem}_{n}.{ext}")
    return path


def _normalize_trajectory(trajectory: Union[str, list, dict]) -> list[dict]:
    """Return an ordered list of frames ``[{"state": [...preds], "action": str|None}]``.

    Accepts the dict returned by pddl-parser's get_trajectory
    ({"trajectory": {"1": {state, action}, ...}, "final_state": ...}), the bare
    inner step-mapping, or a plain list of state strings. The action attached to
    a frame is the one that LED to it (so the first frame's action is None and a
    terminal final_state frame is appended)."""
    if isinstance(trajectory, str):
        trajectory = json.loads(trajectory)

    if isinstance(trajectory, dict) and "trajectory" in trajectory:
        steps = trajectory["trajectory"]
        final = trajectory.get("final_state")
    elif isinstance(trajectory, dict):
        steps = trajectory
        final = None
    elif isinstance(trajectory, list):
        return [{"state": extract_predicates(s), "action": None}
                for s in trajectory]
    else:
        raise ValueError("trajectory must be a dict, list, or JSON string")

    ordered = sorted(steps.items(), key=lambda kv: int(kv[0]))
    frames: list[dict] = []
    prev_action = None
    for _, step in ordered:
        frames.append({"state": extract_predicates(step["state"]),
                       "action": prev_action})
        prev_action = step.get("action")
    if final:
        frames.append({"state": extract_predicates(final),
                       "action": prev_action})
    return frames


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": False})
def render_state(
    state: Annotated[Union[str, list[str]], Field(description="The state to draw, as the grounded predicate-string output pddl-parser / pddl-validator already emit. Accepts a PDDL state string (wrapped '(:init (on a b) (clear a) (handempty))' / '(:state ...)' / '(:goal ...)', or a bare predicate sequence '(on a b) (clear a)'), OR a JSON array of predicate strings ['(on a b)', '(clear a)']. This tool does NOT parse a domain/problem or simulate a plan — get the state from a sibling plugin first.")],
    output_path: Annotated[Optional[str], Field(description="Absolute file path to write the image to. Defaults to ~/pddl-renders/state.<fmt> (auto-created, numeric suffix on collision).")] = None,
    layout: Annotated[Literal["spring", "circular", "shell", "kamada_kawai"], Field(description="Graph layout algorithm. 'spring' (default) is a good general force-directed layout; 'circular'/'shell' arrange nodes on rings; 'kamada_kawai' minimises edge crossings (needs scipy, falls back to spring).")] = "spring",
    fmt: Annotated[Literal["png", "svg"], Field(description="Output image format.")] = "png",
    title: Annotated[Optional[str], Field(description="Optional title drawn at the top of the image.")] = None,
) -> dict:
    """Renders a single PDDL state to an image using a domain-independent
    predicate-graph: objects are nodes, unary predicates become node property
    labels, binary predicates become labelled directed edges, n-ary predicates
    become square predicate-nodes wired to their arguments, and numeric fluents
    ('(= (fuel t) 5)') annotate the relevant node (or a side panel when the
    function has no object argument). 0-arity predicates ('(handempty)') are
    listed in a side panel. No per-domain configuration is needed — this works
    on any domain. To draw a whole plan/trace, use render_trajectory.

    After calling this, Read the returned image_path to view it.

    Returns:
        Success: {"image_path": str, "format": str, "num_objects": int, "num_predicates": int}
        Error:   {"error": True, "message": str}"""
    try:
        preds = extract_predicates(state)
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": True, "message": f"Could not parse state: {e}"}

    try:
        model = StateModel(preds)
        pos = _layout(model.objects, model.binary, layout)
        fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
        try:
            artists = _draw_state(model, pos, ax, title, added=None)
            fig.canvas.draw()
            _apply_limits(ax, _fitted_limits(ax, artists, fig.canvas.get_renderer()))
            out = _resolve_output(output_path, "state", fmt)
            fig.savefig(out, format=fmt, dpi=DPI, bbox_inches="tight")
        finally:
            plt.close(fig)
    except Exception as e:
        return {"error": True, "message": f"{type(e).__name__}: {e}"}

    return {
        "image_path": out,
        "format": fmt,
        "num_objects": len(model.objects),
        "num_predicates": len(preds),
    }


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": False})
def render_trajectory(
    trajectory: Annotated[Union[str, list, dict], Field(description="The trace to draw. Accepts the dict pddl-parser's get_trajectory returns ({'trajectory': {'1': {'state','action'}, ...}, 'final_state': ...}), its bare inner step-mapping, OR a plain list of state strings. Each state uses the same forms as render_state. Pass the get_trajectory result through directly.")],
    output_path: Annotated[Optional[str], Field(description="Absolute file path for the output. Defaults to ~/pddl-renders/trajectory.<gif|png>.")] = None,
    fmt: Annotated[Literal["gif", "filmstrip"], Field(description="'gif' (default): animated GIF, one frame per state. 'filmstrip': a single PNG with all states as a grid of panels (diff-friendly, no animation).")] = "gif",
    layout: Annotated[Literal["spring", "circular", "shell", "kamada_kawai"], Field(description="Graph layout (computed once over the union of all objects so nodes stay put across frames).")] = "spring",
    highlight_changes: Annotated[bool, Field(description="Highlight predicates added relative to the previous state (green nodes/edges). Default True.")] = True,
    frame_seconds: Annotated[float, Field(description="GIF seconds per frame (ignored for filmstrip). Default 1.2.")] = 1.2,
) -> dict:
    """Renders a PDDL trajectory (a sequence of states produced by executing a
    plan) to either an animated GIF or a single filmstrip PNG, reusing the same
    domain-independent predicate-graph as render_state. Node positions are
    computed once over the union of all states so objects stay anchored across
    frames; each frame is titled with the action that produced it, and (by
    default) facts added since the previous state are highlighted in green.

    Feed it the dict from pddl-parser's get_trajectory directly. After calling
    this, Read the returned image_path to view it.

    Returns:
        Success: {"image_path": str, "format": str, "num_frames": int}
        Error:   {"error": True, "message": str}"""
    try:
        frames = _normalize_trajectory(trajectory)
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
        return {"error": True, "message": f"Could not parse trajectory: {e}"}

    if not frames:
        return {"error": True, "message": "Trajectory has no states to render."}

    try:
        models = [StateModel(f["state"]) for f in frames]
        # Shared layout over the union of all objects and binary edges.
        all_objs, seen = [], set()
        all_binary = []
        for m in models:
            for o in m.objects:
                if o not in seen:
                    seen.add(o)
                    all_objs.append(o)
            all_binary.extend(m.binary)
        base_pos = _layout(all_objs, all_binary, layout)

        # Per-frame "added" sets (raw predicate strings new vs. previous frame).
        added_sets = [None]
        for i in range(1, len(frames)):
            prev = set(frames[i - 1]["state"])
            added_sets.append(set(frames[i]["state"]) - prev
                              if highlight_changes else set())

        def _title(i: int) -> str:
            act = frames[i]["action"]
            return f"step {i}: {act}" if act else "initial state"

        n = len(frames)
        if fmt == "filmstrip":
            cols = min(4, n)
            rows = (n + cols - 1) // cols
            fig, axes = plt.subplots(rows, cols,
                                     figsize=(4.2 * cols, 3.4 * rows),
                                     constrained_layout=True)
            axes = [axes] if n == 1 else list(axes.flat)
            try:
                arts = [_draw_state(models[i], dict(base_pos), axes[i],
                                    _title(i), added_sets[i]) for i in range(n)]
                for j in range(n, len(axes)):
                    axes[j].axis("off")
                fig.canvas.draw()
                renderer = fig.canvas.get_renderer()
                union = None
                for i in range(n):
                    union = _union_limits(
                        union, _fitted_limits(axes[i], arts[i], renderer))
                for i in range(n):
                    _apply_limits(axes[i], union)
                out = _resolve_output(output_path, "trajectory", "png")
                fig.savefig(out, format="png", dpi=DPI)  # constrained_layout trims
            finally:
                plt.close(fig)
        else:  # gif
            # Two passes so node positions are pixel-identical across frames
            # (shared data window) while holding only ONE figure open at a time
            # — keeping every frame's figure open blows past matplotlib's
            # open-figure limit and wastes memory on long plans.
            def _render_frame(i: int, lims):
                fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
                try:
                    artists = _draw_state(models[i], dict(base_pos), ax,
                                          _title(i), added_sets[i])
                    fig.canvas.draw()
                    fit = _fitted_limits(ax, artists, fig.canvas.get_renderer())
                    if lims is not None:
                        _apply_limits(ax, lims)
                        return None, _fig_to_image(fig)
                    return fit, None
                finally:
                    plt.close(fig)

            # Pass 1: measure each frame's fitted window and union them.
            union = None
            for i in range(n):
                fit, _ = _render_frame(i, None)
                union = _union_limits(union, fit)
            # Pass 2: render each frame with the shared window applied.
            images = [_render_frame(i, union)[1] for i in range(n)]
            out = _resolve_output(output_path, "trajectory", "gif")
            images[0].save(
                out, save_all=True, append_images=images[1:],
                duration=int(frame_seconds * 1000), loop=0, disposal=2,
            )
    except Exception as e:
        return {"error": True, "message": f"{type(e).__name__}: {e}"}

    return {"image_path": out, "format": fmt, "num_frames": len(frames)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
