"""The law language: a restricted Python subset, statically checked and classified, executed with step and depth limits.

A law module sets `title` and `intent`, may keep persistent data in `state` (a dict), and defines hooks:
on_enact, on_repeal, on_round_start(r), on_round_end(r), on_harvest(agent, camp, x, y) (return a deduction),
on_transfer(src, dst, item, qty) (return False to block, or a number to tax), on_proposal(p), on_vote(ballot, agent, choice),
on_post(agent, text). It calls the kernel API (see API_GROUPS); nothing else is reachable: no imports, no I/O, no dunders,
no global/nonlocal, no try, no classes.

Static class (by which API calls appear, so it cannot be misstated):
  procedural  any set_procedure
  structural  any rights, money, sanctions, governance (open_ballot), clause or project/tribute call
  ordinary    only read, camp, names, text and output calls
"""
from __future__ import annotations

import ast
import sys

# Version of the law API (API_GROUPS, hooks, their signatures and semantics) seen by law code. Bump it when an existing call or hook
# changes meaning or is removed (adding a call does not break old laws); run.json records it per run segment.
LAW_API_VERSION = 1

API_GROUPS = {
    "read": {"agents", "holders", "has", "balance", "reserve", "price", "stock", "round", "laws", "proposer", "value", "supply",
             "camps", "class_of", "holdings_value", "currencies", "rights_of", "rng", "bounty_number",
             "channels", "posts", "current_post", "hidden_posts", "dm_limit", "loans",
             "credit_record", "reserve_ratio", "redemption_open", "par", "interest_cap", "circulation"},
    "rights": {"create_right", "grant", "revoke", "define_action"},
    "money": {"create_currency", "mint", "burn", "move", "set_convertible", "enable_loans", "forgive_loan",
              "set_par", "suspend_redemption", "set_interest_cap", "set_default_consequence", "restructure_loan",
              "lend_from_reserve", "buy_loan"},
    "camps": {"set_quota", "set_harvest_limit", "set_fee"},
    "governance": {"set_procedure", "open_ballot"},
    "output": {"gazette", "notify", "unhide_post"},
    "names": {"rename", "name", "title"},
    "sanctions": {"fine", "suspend", "limit_actions", "censure", "clause", "hide_post", "set_dm_limit"},
    "text": {"contains", "count", "starts_with", "lower"},
    "meta": {"repeal"},
    "projects": {"start_project", "contribute_project", "set_refund", "pay_tribute"},   # structural: new camps/rights, reserve outflows
    "projects_read": {"projects", "tribute_status"},
}
API_GROUPS["read"] = API_GROUPS["read"] | {"capability_holders"}                           # hidden powers (hidden.py)
API_GROUPS["rights"] = API_GROUPS["rights"] | {"revoke_capability", "disclose_capability_use"}  # structural, like rights
API_GROUPS["read"] = API_GROUPS["read"] | {"leases"}                                       # camps: leasing harvest rights
API_GROUPS["camps"] = API_GROUPS["camps"] | {"set_lease_rules"}                            # camps: ordinary, like set_fee
API_GROUPS["rights"] = API_GROUPS["rights"] | {"set_succession_public"}                        # life: Board succession (mortality.py)
API_GROUPS["read"] = API_GROUPS["read"] | {"forts", "weapons_of", "defense_of", "guards", "attacks", "disabled_agents"}   # conflict
API_GROUPS["sanctions"] = API_GROUPS["sanctions"] | {"ban_forging", "oblige_guard", "clear_obligations"}  # conflict: structural
API_GROUPS["read"] = API_GROUPS["read"] | {"jurisdiction", "members"}                     # jurisdictions (jurisdictions.py)
API_GROUPS["rights"] = API_GROUPS["rights"] | {"admit", "expel"}
API_GROUPS["sanctions"] = API_GROUPS["sanctions"] | {"lawful_attack"}
# media2 (media.py): reads; which official statistics are public (ordinary output); outlet rules and sanctions (structural)
API_GROUPS["read"] = API_GROUPS["read"] | {"outlets", "public_stats", "submissions"}
API_GROUPS["output"] = API_GROUPS["output"] | {"publish_stat"}
API_GROUPS["rights"] = API_GROUPS["rights"] | {"set_official_editor", "set_open_board", "set_press_freedom", "official_stream"}
API_GROUPS["sanctions"] = API_GROUPS["sanctions"] | {"suspend_outlet", "require_sponsor_label", "compel_subscription"}
# life (life.py): who makes children and what is made; birth rules are structural, publishing commissions and births ordinary output
API_GROUPS["read"] = API_GROUPS["read"] | {"makers", "commissions", "births", "children_of", "lifespan_left"}
API_GROUPS["output"] = API_GROUPS["output"] | {"publish_commissions", "publish_births"}
API_GROUPS["rights"] = API_GROUPS["rights"] | {"set_birth_rules"}
API = set().union(*API_GROUPS.values())
STRUCTURAL_CALLS = API_GROUPS["rights"] | API_GROUPS["money"] | API_GROUPS["sanctions"] | {"open_ballot"} | API_GROUPS["projects"]
LEVEL_CLASSES = {"L0": set(), "L1": {"ordinary"}, "L2": {"ordinary", "structural"}, "L3": {"ordinary", "structural", "procedural"},
                 "L4": {"ordinary", "structural", "procedural"}}
HOOKS = ("on_enact", "on_repeal", "on_round_start", "on_round_end", "on_harvest", "on_transfer", "on_proposal", "on_vote", "on_post",
         "on_ruling", "on_dm",
         "on_admission", "on_exit", "on_birth",                        # jurisdictions
         "on_commission")                                              # life: return False to refuse an order
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
MAX_STEPS, MAX_DEPTH = 10_000, 20


class LawError(Exception):
    """A law failed the static check or raised at runtime (message is shown to the proposer / the Fixer)."""


class StepLimit(LawError):
    pass


def check(code: str) -> ast.Module:
    """Parse and validate against the whitelist. Raises LawError with a readable reason."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise LawError(f"syntax error on line {e.lineno}: {e.msg}")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise LawError(f"not allowed in law code: {type(node).__name__} (line {getattr(node, 'lineno', '?')})")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise LawError(f"names may not start with '_': {node.id}")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr not in SAFE_ATTRS):
            raise LawError(f"attribute not allowed: .{node.attr} (line {node.lineno})")
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.name.startswith("_")):
            raise LawError(f"function {node.name}: decorators and leading underscores are not allowed")
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
    if "set_procedure" in c:
        return "procedural"
    if c & STRUCTURAL_CALLS or moves_holdings_by_return(tree):
        return "structural"
    return "ordinary"


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
    return "define_action" in calls(tree)


def header(code: str) -> tuple[str, str]:
    tree = check(code)
    ns = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("title", "intent"):
            ns[n.targets[0].id] = n.value.value
    return ns["title"], ns["intent"]


class Limited:
    """Run law code under a step budget and a recursion depth limit (only frames compiled from law code count)."""

    def __init__(self, max_steps=MAX_STEPS, max_depth=MAX_DEPTH):
        self.max_steps, self.max_depth = max_steps, max_depth

    def __call__(self, fn, *args, **kw):
        steps, depth = [0], [0]

        def local(frame, event, arg):
            if event == "line":
                steps[0] += 1
                if steps[0] > self.max_steps:
                    raise StepLimit(f"law exceeded {self.max_steps} steps")
            elif event == "return":
                depth[0] -= 1
            return local

        def glob(frame, event, arg):
            if event == "call" and frame.f_code.co_filename.startswith("<law:"):
                depth[0] += 1
                if depth[0] > self.max_depth:
                    raise LawError(f"law exceeded recursion depth {self.max_depth}")
                return local
            return None

        old = sys.gettrace()
        sys.settrace(glob)
        try:
            return fn(*args, **kw)
        except LawError:
            raise
        except Exception as e:
            raise LawError(f"{type(e).__name__}: {e}") from e
        finally:
            sys.settrace(old)


def load_module(code: str, law_id: str, api: dict, state: dict, limited: Limited) -> dict:
    """Exec a checked law module into a fresh namespace bound to `api` and `state`."""
    tree = check(code)
    ns = {"__builtins__": {}, **SAFE_BUILTINS, **api, "state": state}
    compiled = compile(tree, f"<law:{law_id}>", "exec")
    limited(exec, compiled, ns)
    return ns
