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
import re

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
# P3.2 (law.v2; review 09 §8.1): a law's rank, declared as a top-level constant `rank = "statute"` (default statute). charter is
# reserved (kernel-seeded: no draft may declare it, no procedure exists for it). CONFLICT_RULES: the named conflict rules (§8.3) a
# constitution-rank law may declare with `conflict_rule = "superior"` or set with set_conflict_rule(name_or_fn).
RANKS = {"charter": 4, "constitution": 3, "statute": 2, "regulation": 1, "bylaw": 0}
CONFLICT_RULES = ("any_block", "superior", "posterior", "specialis")  # W6a: specialis (the most specific verdict within the top rank)
# W6a (review 10 §4, roadmap #2): a law's declared temporal validity, top-level constants `in_force_from = 3` / `in_force_until = 9`
# (round numbers, both inclusive; checked by check_window under law.v2). Outside its window the dispatcher skips the law's change and
# clock hooks (dispatch.in_force); at the end of round in_force_until the kernel repeals it with via "expired" (dispatch.expire_laws).
WINDOW = ("in_force_from", "in_force_until")
LEVEL_CLASSES = {"L0": set(), "L1": {"ordinary"}, "L2": {"ordinary", "structural"}, "L3": {"ordinary", "structural", "procedural"},
                 "L4": {"ordinary", "structural", "procedural"}}
from charter.primitives import LAW_HOOKS as HOOKS                     # noqa: E402  live hooks of primitives.HOOKS (lawapi.HOOKTABLE)
SAFE_BUILTINS = {"len": len, "range": range, "min": min, "max": max, "sum": sum, "abs": abs, "int": int, "float": float,
                 "round_to": round, "sorted": sorted, "list": list, "dict": dict, "set": set, "str": str, "bool": bool,
                 "enumerate": enumerate, "zip": zip, "any": any, "all": all, "True": True, "False": False, "None": None, "tuple": tuple}
SAFE_ATTRS = {"get", "items", "keys", "values", "append", "pop", "remove", "insert", "extend", "sort", "index", "setdefault", "update",
              "copy", "upper", "startswith", "endswith", "split", "strip", "join", "replace", "count",
              "author", "title", "intent", "cls", "id", "round", "add", "discard",
              "rank"}                                                  # P3.2: a procedure's p.rank ("statute" unless law.v2)
ALLOWED_NODES = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Expr,
                 ast.If, ast.For, ast.While, ast.Break, ast.Continue, ast.Pass, ast.Compare, ast.BoolOp, ast.BinOp, ast.UnaryOp,
                 ast.Call, ast.keyword, ast.Name, ast.Load, ast.Store, ast.Del, ast.Delete, ast.Constant, ast.List, ast.Tuple,
                 ast.Dict, ast.Set, ast.Subscript, ast.Slice, ast.Attribute, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp,
                 ast.GeneratorExp, ast.comprehension, ast.IfExp, ast.JoinedStr, ast.FormattedValue, ast.Starred,
                 ast.operator, ast.unaryop, ast.cmpop, ast.boolop, ast.expr_context)
MAX_STEPS, MAX_DEPTH = G.MAX_STEPS, G.MAX_DEPTH
LawError, StepLimit = G.LawError, G.StepLimit                          # defined in charter/gas.py (the meter raises them)


def check(code: str, v2: bool = False) -> ast.Module:
    """Parse and validate against the whitelist. Raises LawError with a readable reason. v2 (spec law.v2): also the linker's static
    rules (check_v2: exports, use, public)."""
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
    if v2:
        check_v2(tree, code)
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


def classify(tree: ast.AST, imported=()) -> str:
    """The law's class from its calls and hooks, and (law.v2, transitive) from the exported closures it imports (`imported`: the
    closures as AST modules, linker.import_closures): importing a function that calls fine() makes the importer structural."""
    out = _classify_one(tree)
    for t in imported:
        out = max(out, _classify_one(t), key=CLASS_RANK.get)
    return out


def _classify_one(tree: ast.AST) -> str:
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


# ====================================================================== law.v2: exports, use, public (P3.3; review 09 §6.1)
# Static rules, checked by check(code, v2=True) for every law in a law.v2 world (off: none of this runs and nothing changes):
#  * use(ref) appears only as a top-level `alias = use("<ref>")` with a constant ref: "L3" (follow the current version), "L3@<8-16 hex>"
#    (pinned to a code version) or "lib:<name>@<8-16 hex>" (a library entry by hash). `use` is never passed around or called elsewhere,
#    so the kernel knows every dependency before proposal and linking happens only when a module is loaded.
#  * `exports = [...]` is one top-level assignment of a constant list of strings; each name is a top-level def or a top-level
#    assignment of a constant expression (literals and arithmetic on literals).
#  * a law with exports has a declarative top level: only constant assignments, defs, use(...) assignments, title, intent, rank and
#    exports, so linking it runs no API call.
#  * exported functions, and every function they reach in their module, never name `state` or `public` (an exporter's data is
#    reachable only through public_of(lid)); `public` is never rebound.
#  * one module is at most MAX_LINKED_BYTES; the import graph (check_graph, run by the linker with the kernel's resolver) is a DAG at
#    most MAX_IMPORT_DEPTH deep whose linked code is at most MAX_LINKED_BYTES in all.
REF_RE = re.compile(r"^(?:(L\d+)(?:@([0-9a-f]{8,16}))?|lib:([a-z0-9_]+)@([0-9a-f]{8,16}))$")
MAX_IMPORT_DEPTH = 6
MAX_LINKED_BYTES = 64 * 1024
NOT_EXPORTABLE = {"title", "intent", "rank", "conflict_rule", "exports", "state", "public", "use", *WINDOW}   # W6a: the window


def _single(n) -> str | None:
    """The name a top-level `name = value` statement assigns, else None."""
    if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
        return n.targets[0].id
    return None


def _is_use(v) -> bool:
    return isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "use"


def use_refs(tree: ast.Module) -> dict:
    """alias -> ref of every top-level `alias = use("<ref>")` (check_v2 guarantees there are no other uses)."""
    return {_single(n): n.value.args[0].value for n in tree.body if _single(n) and _is_use(n.value) and n.value.args
            and isinstance(n.value.args[0], ast.Constant)}


def exports_of(tree: ast.Module) -> list | None:
    """The names in `exports = [...]`, or None when the law exports nothing."""
    for n in tree.body:
        if _single(n) == "exports" and isinstance(n.value, (ast.List, ast.Tuple)):
            return [e.value for e in n.value.elts if isinstance(e, ast.Constant)]
    return None


def const_expr(v) -> bool:
    """Literals and arithmetic on literals (no names, no calls)."""
    if isinstance(v, ast.Constant):
        return True
    if isinstance(v, ast.UnaryOp):
        return const_expr(v.operand)
    if isinstance(v, ast.BinOp):
        return const_expr(v.left) and const_expr(v.right)
    if isinstance(v, (ast.List, ast.Tuple, ast.Set)):
        return all(const_expr(e) for e in v.elts)
    if isinstance(v, ast.Dict):
        return all(k is not None and const_expr(k) for k in v.keys) and all(const_expr(x) for x in v.values)
    return False


def used_exports(tree: ast.Module) -> dict:
    """alias -> the export names the law reads from it (`tax["tax_due"]`, `tax.get("RATE")`), or None when it uses the alias any
    other way (passes it around, iterates it, indexes it with a variable): then it depends on every name it was linked with."""
    aliases = set(use_refs(tree))
    out: dict = {a: set() for a in aliases}
    ok = {id(n.targets[0]) for n in tree.body if _single(n) in aliases and _is_use(n.value)}
    for n in ast.walk(tree):
        base = key = None
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id in aliases:
            base, key = n.value, n.slice
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
                and n.func.value.id in aliases and n.func.attr == "get":
            base, key = n.func.value, (n.args[0] if n.args else None)
        if base is None:
            continue
        ok.add(id(base))
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and out[base.id] is not None:
            out[base.id].add(key.value)
        else:
            out[base.id] = None
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in aliases and id(n) not in ok:
            out[n.id] = None
    return {a: (None if v is None else sorted(v)) for a, v in out.items()}


def export_closure(tree: ast.Module, names=None) -> tuple:
    """The top-level defs the exports `names` (default: all exports) reach through name references, as one module (for classify),
    and the use-aliases those defs name (their own imports, which the linker classifies transitively)."""
    defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    aliases = set(use_refs(tree))
    todo = [x for x in ((exports_of(tree) or []) if names is None else names) if x in defs]
    seen, used = set(), set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        for x in ast.walk(defs[name]):
            if isinstance(x, ast.Name):
                if x.id in defs and x.id not in seen:
                    todo.append(x.id)
                elif x.id in aliases:
                    used.add(x.id)
    return ast.Module(body=[defs[n] for n in defs if n in seen], type_ignores=[]), used


def declared(tree: ast.Module, name: str):
    """The constant a module assigns to `name` at the top level (rank, conflict_rule, fail_closed), else None."""
    v = next((n.value for n in tree.body if _single(n) == name), None)
    return v.value if isinstance(v, ast.Constant) else None


def check_rank(tree: ast.Module) -> None:
    """P3.2 static rules (law.v2): `rank` and `conflict_rule`, when a module sets them at the top level, are set once to a known
    constant string; only a constitution-rank (or charter) law may declare a conflict rule. Raises LawError."""
    for nm, known in (("rank", tuple(RANKS)), ("conflict_rule", CONFLICT_RULES)):
        top = [n for n in tree.body if _single(n) == nm or (isinstance(n, (ast.AugAssign, ast.AnnAssign)) and
                                                             isinstance(n.target, ast.Name) and n.target.id == nm)]
        if len(top) > 1:
            raise LawError(f"{nm} is set once, at the top level")
        if top and not (_single(top[0]) == nm and isinstance(top[0].value, ast.Constant) and top[0].value.value in known):
            raise LawError(f"{nm} must be one of {', '.join(known)} as a constant string (line {top[0].lineno})")
    if declared(tree, "conflict_rule") is not None and RANKS[declared(tree, "rank") or "statute"] < RANKS["constitution"]:
        raise LawError('only a constitution-rank law may declare conflict_rule (rank = "constitution")')
    check_window(tree)


def check_window(tree: ast.Module) -> None:
    """W6a static rules (law.v2), run with the rank rules: `in_force_from` and `in_force_until`, when a module names them, are
    assigned once, at the top level, a constant whole round number >= 0, and the window is not empty (from <= until)."""
    for nm in WINDOW:
        uses = [n for n in ast.walk(tree) if (isinstance(n, ast.Name) and n.id == nm and isinstance(n.ctx, (ast.Store, ast.Del)))
                or (isinstance(n, ast.arg) and n.arg == nm)]
        top = [n for n in tree.body if _single(n) == nm]
        if len(uses) > 1 or len(uses) != len(top):
            raise LawError(f"{nm} is set once, at the top level: {nm} = 5")
        v = declared(tree, nm)
        if top and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
            raise LawError(f"{nm} must be a constant round number (a whole number >= 0), e.g. {nm} = 5 (line {top[0].lineno})")
    lo, hi = window(tree)
    if lo is not None and hi is not None and hi < lo:
        raise LawError(f"in_force_until ({hi}) is before in_force_from ({lo})")


def window(tree: ast.Module) -> tuple:
    """W6a: (in_force_from, in_force_until) as a module declares them; None where it declares none (or not a round number)."""
    out = []
    for nm in WINDOW:
        v = declared(tree, nm)
        out.append(v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None)
    return tuple(out)


def check_v2(tree: ast.Module, code: str) -> None:
    """The linker's per-module static rules (see above), and the rank rules (check_rank). Raises LawError."""
    if len(code.encode()) > MAX_LINKED_BYTES:
        raise LawError(f"a law may be at most {MAX_LINKED_BYTES // 1024} KB")
    check_rank(tree)
    use_stmts = [n for n in tree.body if _single(n) and _is_use(n.value)]
    use_calls = {id(n.value) for n in use_stmts}
    use_funcs = {id(n.value.func) for n in use_stmts}
    seen_alias: set = set()
    for n in use_stmts:
        c = n.value
        if len(c.args) != 1 or c.keywords or not isinstance(c.args[0], ast.Constant) or not isinstance(c.args[0].value, str):
            raise LawError(f"use(...) takes one constant string (line {n.lineno})")
        if not REF_RE.match(c.args[0].value):
            raise LawError(f"use({c.args[0].value!r}): a reference is \"L3\", \"L3@<8-16 hex digits>\" or \"lib:<name>@<8-16 hex digits>\"")
        alias = _single(n)
        if alias in seen_alias or alias in NOT_EXPORTABLE or alias in API:
            raise LawError(f"use(...) alias {alias!r} is reserved or assigned twice (line {n.lineno})")
        seen_alias.add(alias)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_use(node) and id(node) not in use_calls:
            raise LawError(f"use(...) is allowed only as a top-level assignment: name = use(\"L3\") (line {node.lineno})")
        if isinstance(node, ast.Name) and node.id == "use" and id(node) not in use_funcs:
            raise LawError(f"use may only be called, as name = use(\"L3\") at the top level (line {node.lineno})")
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)) and node.id == "public":
            raise LawError(f"public is the law's public dict: change its keys, never rebind it (line {node.lineno})")
        if isinstance(node, ast.arg) and node.arg in ("public", "use"):
            raise LawError(f"a parameter may not be called {node.arg}")
    top_ex = [n for n in tree.body if _single(n) == "exports"]
    all_ex = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "exports" and isinstance(n.ctx, (ast.Store, ast.Del))]
    if len(top_ex) > 1 or len(all_ex) != len(top_ex):
        raise LawError("exports is set once, at the top level: exports = [\"name\", ...]")
    if not top_ex:
        return
    v = top_ex[0].value
    if not isinstance(v, (ast.List, ast.Tuple)) or not all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in v.elts):
        raise LawError("exports must be a constant list of names: exports = [\"RATE\", \"tax_due\"]")
    names = [e.value for e in v.elts]
    if len(set(names)) != len(names):
        raise LawError("exports names a name twice")
    defs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    consts: dict = {}
    for n in tree.body:                                            # declarative top level
        nm = _single(n)
        if isinstance(n, ast.FunctionDef) or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)):
            continue
        if nm in ("title", "intent", "rank", "conflict_rule", *WINDOW) and isinstance(n.value, ast.Constant):   # W6a: the window
            continue
        if nm == "exports" or (nm and _is_use(n.value)):
            continue
        if nm and const_expr(n.value):
            consts[nm] = consts.get(nm, 0) + 1
            continue
        raise LawError(f"a law with exports has a declarative top level (constants, defs, use, title, intent, rank): line {n.lineno}")
    for x in names:
        if x in NOT_EXPORTABLE:
            raise LawError(f"{x} cannot be exported")
        if (defs.count(x), consts.get(x, 0)) not in ((1, 0), (0, 1)):
            raise LawError(f"export {x!r} must be one top-level def or one top-level constant assignment")
    closure, _ = export_closure(tree, names)
    for fn in closure.body:
        for x in ast.walk(fn):
            if isinstance(x, ast.Name) and x.id in ("state", "public"):
                raise LawError(f"exported function {fn.name} (or a function it calls) uses {x.id}: exported code reads other laws' "
                               f"data only through public_of(id) (line {x.lineno})")


def check_graph(root: str, code: str, resolve) -> list:
    """The import graph from one module: a DAG at most MAX_IMPORT_DEPTH deep whose distinct linked code (the root's included) is at
    most MAX_LINKED_BYTES. resolve(declarer_key, ref) -> (key, code) names and returns each import's code (raising LawError when it
    cannot). Every imported module must pass check_v2 and export something. Returns the keys of the modules reached, in DFS order."""
    sizes = {root: len(code.encode())}
    order: list = []

    def walk(key, src, stack):
        for ref in use_refs(check(src, v2=True)).values():
            sub, sub_code = resolve(key, ref)
            path = " -> ".join(stack + [key, sub])
            if sub in stack or sub == key:
                raise LawError(f"import cycle: {path}")
            if len(stack) + 1 >= MAX_IMPORT_DEPTH:
                raise LawError(f"imports nest deeper than {MAX_IMPORT_DEPTH}: {path}")
            if not exports_of(check(sub_code, v2=True)):
                raise LawError(f"{ref} exports nothing")
            if sub not in sizes:
                sizes[sub] = len(sub_code.encode())
                order.append(sub)
                if sum(sizes.values()) > MAX_LINKED_BYTES:
                    raise LawError(f"the code a law links (its own and its imports) may be at most {MAX_LINKED_BYTES // 1024} KB")
            walk(sub, sub_code, stack + [key])

    walk(root, code, [])
    return order


def static_info(tree: ast.Module) -> dict:
    """Static facts of a checked module (I-9): API calls, hooks, constant rights granted/revoked/suspended, imports, exports, rank,
    title, intent."""
    from charter import primitives as PR
    rights: dict = {"grant": set(), "revoke": set(), "suspend": set()}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in rights and len(n.args) >= 2 \
                and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
            rights[n.func.id].add(n.args[1].value)
    consts = {_single(n): n.value.value for n in tree.body if _single(n) in ("title", "intent", "rank") and isinstance(n.value, ast.Constant)}
    return {"calls": sorted(calls(tree) & API),
            "hooks": sorted(n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in PR.HOOKS),
            "rights": {x: sorted(v) for x, v in rights.items()}, "imports": [{"alias": a, "ref": r} for a, r in use_refs(tree).items()],
            "exports": exports_of(tree) or [], "rank": consts.get("rank"), "title": consts.get("title"), "intent": consts.get("intent")}
