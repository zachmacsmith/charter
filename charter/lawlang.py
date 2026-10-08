"""The law language: a restricted Python subset, statically checked and classified, executed with step and depth limits.

A law module sets `title` and `intent`, may keep persistent data in `state` (a dict), and defines hooks:
on_enact, on_repeal, on_round_start(r), on_round_end(r), on_harvest(agent, camp, x, y) (return a deduction),
on_transfer(src, dst, item, qty) (return False to block, or a number to tax), on_proposal(p), on_vote(ballot, agent, choice),
on_post(agent, text) and the module hooks in charter/lawapi.py; with law.v2 also before_<p>(p, chain) and after_<p>(p, chain) for every
routed primitive p (V2_HOOKS, check_hooks: a check error without law.v2, R5; dispatch.py runs them). It calls the kernel API (see API_GROUPS, generated from the table in
charter/lawapi.py); nothing else is reachable: no imports, no I/O, no dunders, no global/nonlocal, no try, no classes.

Static class (by which API calls appear, so it cannot be misstated):
  procedural  any set_procedure
  structural  any rights, money, sanctions, governance (open_ballot), clause, project/tribute or repeal call (a law calling nothing
              but repeal(<constant>) takes its target's class instead: is_repeal)
  ordinary    only read, camp, names, text and output calls
"""
from __future__ import annotations

import ast

from charter import gas as G
from charter import lawapi as LA

# Version of the law API (API_GROUPS, hooks, their signatures and semantics) seen by law code. Bump it when an existing call or hook
# changes meaning or is removed (adding a call does not break old laws); run.json records it per run segment.
LAW_API_VERSION = 1

# The law API's classification, generated from the table in charter/lawapi.py (one row per function and hook): group -> names.
API_GROUPS = LA.api_groups()
API = set().union(*API_GROUPS.values())
STRUCTURAL_CALLS = LA.STRUCTURAL_CALLS                                 # rights, money, sanctions, projects, open_ballot, repeal
PROCEDURAL_CALLS = LA.PROCEDURAL_CALLS                                 # set_procedure
L4_CALLS = LA.L4_CALLS                                                 # define_action
CLASS_RANK = {"ordinary": 0, "structural": 1, "procedural": 2}         # strictness: a law may not repeal a stricter one (Kernel.repeal)
LEVEL_CLASSES = {"L0": set(), "L1": {"ordinary"}, "L2": {"ordinary", "structural"}, "L3": {"ordinary", "structural", "procedural"},
                 "L4": {"ordinary", "structural", "procedural"}}
from charter.primitives import LAW_HOOKS as HOOKS                     # noqa: E402  live hooks of primitives.HOOKS (lawapi.HOOKTABLE)
SAFE_BUILTINS = {"len": len, "range": range, "min": min, "max": max, "sum": sum, "abs": abs, "int": int, "float": float,
                 "round_to": round, "sorted": sorted, "list": list, "dict": dict, "set": set, "str": str, "bool": bool,
                 "enumerate": enumerate, "zip": zip, "any": any, "all": all, "True": True, "False": False, "None": None, "tuple": tuple}
SAFE_ATTRS = {"get", "items", "keys", "values", "append", "pop", "remove", "insert", "extend", "sort", "index", "setdefault", "update",
              "copy", "upper", "startswith", "endswith", "split", "strip", "join", "replace", "count",
              "author", "title", "intent", "cls", "id", "round", "add", "discard"}
ALLOWED_NODES = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Expr,
                 ast.If, ast.For, ast.While, ast.Break, ast.Continue, ast.Pass, ast.Compare, ast.BoolOp, ast.BinOp, ast.UnaryOp,
                 ast.Call, ast.keyword, ast.Name, ast.Load, ast.Store, ast.Del, ast.Delete, ast.Constant, ast.List, ast.Tuple,
                 ast.Dict, ast.Set, ast.Subscript, ast.Slice, ast.Attribute, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp,
                 ast.GeneratorExp, ast.comprehension, ast.IfExp, ast.JoinedStr, ast.FormattedValue, ast.Starred,
                 ast.operator, ast.unaryop, ast.cmpop, ast.boolop, ast.expr_context)
MAX_STEPS, MAX_DEPTH = G.MAX_STEPS, G.MAX_DEPTH
LawError, StepLimit = G.LawError, G.StepLimit                          # defined in charter/gas.py (the meter raises them)


def check(code: str) -> ast.Module:
    """Parse and validate against the whitelist. Raises LawError with a readable reason."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise LawError(f"syntax error on line {e.lineno}: {e.msg}")
    unpack_ok = {id(e) for a in ast.walk(tree) if isinstance(a, ast.Assign) for t in a.targets if isinstance(t, (ast.Tuple, ast.List))
                 for e in t.elts if isinstance(e, ast.Starred)}                # a, *rest = xs (metered by size); not in loops
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise LawError(f"not allowed in law code: {type(node).__name__} (line {getattr(node, 'lineno', '?')})")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise LawError(f"names may not start with '_': {node.id}")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr not in SAFE_ATTRS):
            raise LawError(f"attribute not allowed: .{node.attr} (line {node.lineno})")
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.name.startswith("_")):
            raise LawError(f"function {node.name}: decorators and leading underscores are not allowed")
        if isinstance(node, ast.arg) and node.arg.startswith("__"):    # a parameter could shadow the meter's names (gas.py)
            raise LawError(f"parameter names may not start with '__': {node.arg}")
        if isinstance(node, ast.Starred) and isinstance(node.ctx, ast.Store) and id(node) not in unpack_ok:
            raise LawError(f"starred targets are allowed only in plain assignments (line {node.lineno})")
    names = {n.targets[0].id: n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)}
    for req in ("title", "intent"):
        if req not in names or not isinstance(names[req].value, ast.Constant) or not isinstance(names[req].value.value, str):
            raise LawError(f"a law must set {req} = \"...\" as a plain string")
    return tree


def calls(tree: ast.AST) -> set[str]:
    return {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def moves_holdings_by_return(tree: ast.AST) -> bool:
    """on_harvest / on_transfer can move holdings by what they return (a deduction, a tax, or False to block a transfer).
    Any return other than a constant 0 / None makes the law structural, as the spec requires for taxes and deductions."""
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name in ("on_harvest", "on_transfer"):
            for r in ast.walk(fn):
                if not isinstance(r, ast.Return) or r.value is None:
                    continue
                v = r.value
                harmless = isinstance(v, ast.Constant) and (v.value is None or (type(v.value) in (int, float) and v.value == 0))
                if not harmless:
                    return True
    return False


def classify(tree: ast.AST) -> str:
    c = calls(tree)
    hc = hooks_class(tree)                                             # law.v2 hooks (none in any law without law.v2: R5)
    if c & PROCEDURAL_CALLS or hc == "procedural":
        return "procedural"
    if c & STRUCTURAL_CALLS or moves_holdings_by_return(tree) or hc == "structural":
        return "structural"
    return "ordinary"


# ---------------------------------------------------------------------- law.v2 hooks (P3.1; review 09 §4.2, §9.3 R5, §11)
from charter.primitives import HOOKS as _HOOKROWS, PRIMITIVES as _PRIMS   # noqa: E402
V2_HOOKS = tuple(n for n, h in _HOOKROWS.items() if h.kind in ("before", "after"))   # before_<p>/after_<p>, every declared phase


def new_style_hooks(tree: ast.Module) -> list:
    """Top-level functions named before_<p>/after_<p> for a declared primitive p (whatever the phase flags say), in source order:
    [(name, phase, primitive)]."""
    out = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            ph, _, prim = n.name.partition("_")
            if ph in ("before", "after") and prim in _PRIMS:
                out.append((n.name, ph, prim))
    return out


def check_hooks(tree: ast.Module, v2: bool, live=None) -> None:
    """R5: new-style hooks are a check error without law.v2. With it, each must hook a phase its primitive has (regrow cannot be
    hooked before: physics), a primitive routed through Kernel.apply (`live`: dispatch.ROUTED; others never fire yet), and take
    exactly (p, chain)."""
    for name, ph, prim in new_style_hooks(tree):
        if not v2:
            raise LawError(f"{name}: new-style hooks (before_<primitive>, after_<primitive>) need law.v2 in this world")
        if name not in _HOOKROWS:
            raise LawError(f"{name}: {prim} cannot be hooked {ph} it happens (physics)")
        if live is not None and prim not in live:
            raise LawError(f"{name}: the {prim} primitive is not routed through the kernel yet, so the hook would never run")
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        a = fn.args
        if len(a.args) != 2 or a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs or a.defaults:
            raise LawError(f"{name} must take exactly two arguments: (p, chain)")


def hooks_class(tree: ast.Module) -> str:
    """The class a law's new-style hooks give it (review 09 §11): any hook of a legal primitive is procedural; a before-hook that can
    block or charge (a return other than None, True or a constant 0) is structural; after-hooks add nothing of their own."""
    cls = "ordinary"
    for name, ph, prim in new_style_hooks(tree):
        if _PRIMS[prim].legal:
            return "procedural"
        if ph == "before":
            fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            for r in ast.walk(fn):
                if isinstance(r, ast.Return) and r.value is not None:
                    v = r.value
                    if not (isinstance(v, ast.Constant) and (v.value is None or v.value is True or
                                                             (type(v.value) in (int, float) and v.value == 0))):
                        cls = "structural"
    return cls


def is_repeal(tree: ast.Module) -> str | None:
    """A repeal law calls nothing but repeal(law) (besides title/intent). Returns the target or None."""
    c = calls(tree)
    if c != {"repeal"}:
        return None
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "repeal" and n.args and isinstance(n.args[0], ast.Constant):
            return str(n.args[0].value)
    return None


def uses_define_action(tree: ast.AST) -> bool:
    return bool(calls(tree) & L4_CALLS)


def header(code: str) -> tuple[str, str]:
    tree = check(code)
    ns = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("title", "intent"):
            ns[n.targets[0].id] = n.value.value
    return ns["title"], ns["intent"]


class Limited:
    """Run law code under a step budget and a recursion depth limit: a thin wrapper over the gas meter (charter/gas.py). Only code
    compiled by load_module is metered (it is instrumented). Each call opens a meter frame with its own per-call budget, so a law
    hook run from inside another law's call has its own budget, as with the old line tracer."""

    def __init__(self, max_steps=MAX_STEPS, max_depth=MAX_DEPTH):
        self.max_steps, self.max_depth = max_steps, max_depth
        self.meter = G.Meter()

    def __call__(self, fn, *args, **kw):
        try:
            return self.meter.run(fn, args, kw, per_call=self.max_steps, max_depth=self.max_depth)
        except LawError:
            raise
        except Exception as e:
            raise LawError(f"{type(e).__name__}: {e}") from e


def compile_law(code: str, law_id: str):
    """Check, instrument (gas.instrument) and compile a law module."""
    return compile(G.instrument(check(code)), f"<law:{law_id}>", "exec")


def load_module(code: str, law_id: str, api: dict, state: dict, limited: Limited) -> dict:
    """Exec a checked law module into a fresh namespace bound to `api` and `state` (and to `limited`'s meter)."""
    compiled = compile_law(code, law_id)
    ns = {"__builtins__": {}, **SAFE_BUILTINS, **limited.meter.builtins, **api, "state": state, **limited.meter.runtime}
    limited(exec, compiled, ns)
    return ns
