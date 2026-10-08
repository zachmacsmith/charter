"""Law sets (W6d; review 10 §5.4): a legal system is a set of laws, not a point in a dimension space. This module reads a set of law
codes statically (no kernel, no simulation) and answers three questions about it.

  check(laws, spec)         composability at generation: each law's static rules, its law level against the world's, its rank
                            (and the ranks its set_procedure calls reach), its import graph (a DAG of lib:* entries), whether it can
                            ever fire in this world (a law whose every hook hooks a change that cannot happen here never runs), and
                            the overlaps (laws hooking the same change, with their ranks). Returns errors, level drops and overlaps.
  dimensions(laws)          the regime's dimension vector derived from its laws: the procedures in force at round 0 (electorate
                            kind and rule per class and rank, weights, gates, decree), the amendment rule, the scorer's label
                            (anarchy / dictatorship / oligarchy / democracy), entrenchment, rights guards, review, courts,
                            offices, classes and ranks, and hooks per primitive family. Pure: the same codes give the same vector.
                            Dimensions are labels for sampling and analysis; the laws stay the source of truth.
  fingerprint(k) / of(laws) the legal fingerprint: the sha set of the laws in force, each law's rank, class and template
                            provenance, and the hook coverage matrix primitive x rank. distance(a, b) compares two.

A law here is a dict {"name", "code", "rank"?}: the code is authoritative (its declared rank is read from it; "rank" only names a
default for code that declares none). The order is enactment order: a later set_procedure for the same class and rank replaces an
earlier one, as in the kernel.
"""
from __future__ import annotations

import ast

from charter import lawlang as L
from charter import primitives as PR

LEVELS = ["L0", "L1", "L2", "L3", "L4"]
CLOCK = ("on_enact", "on_repeal", "on_round_start", "on_round_end")          # hooks that run whatever happens in the world
# a change happens in a world when one of these features is on (a feature not named here: the primitive's own; core: always)
FIRES_WITH = {"end_life": ("mortality", "conflict", "life", "events"), "begin_life": ("life", "events")}
FEATURE_ALIAS = {"camptypes": "camps", "media2": "media"}
CITIZENS = "citizens"
LABELS = ("anarchy", "dictatorship", "oligarchy", "democracy")


# ---------------------------------------------------------------------- static facts of one law
def _tree(code: str) -> ast.Module:
    return ast.parse(code)


def rank_of(code: str, default: str = "statute") -> str:
    return L.declared(_tree(code), "rank") or default


def hooks_of(code: str) -> list:
    """[(hook, primitive or None)]: the law's hooks and the change each one hooks (None: a clock or lifecycle hook)."""
    out = []
    for n in _tree(code).body:
        if isinstance(n, ast.FunctionDef) and n.name in PR.HOOKS:
            h = PR.HOOKS[n.name]
            out.append((n.name, getattr(h, "primitive", None) if h.kind not in ("lifecycle", "clock") else None))
    return out


def family(prim: str | None) -> str:
    """A hooked change's family: its primitive's effect (move, create, legal, status, speech, relation, life, ...); clock for none."""
    return PR.PRIMITIVES[prim].effect if prim in PR.PRIMITIVES else "clock"


def _feature_on(feature: str, spec: dict) -> bool:
    from charter import features as FT
    if feature == "core":
        return True
    try:
        return FT.on(FEATURE_ALIAS.get(feature, feature), spec)
    except KeyError:
        return True


def change_possible(prim: str, spec: dict) -> bool:
    feats = FIRES_WITH.get(prim) or (PR.PRIMITIVES[prim].feature,)
    return any(_feature_on(f, spec) for f in feats)


def can_fire(code: str, spec: dict) -> bool:
    """Whether a law can ever run in a world with this spec: it exports names (others call them), it calls something at its top
    level (run when it is loaded: a clause), it has a clock or lifecycle hook (on_enact defines offices and clauses, sets
    procedures), or one of its hooks hooks a change that can happen here."""
    tree = _tree(code)
    if L.exports_of(tree) or any(isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) for n in tree.body):
        return True                                                    # exports, or calls run when the law is loaded (clause(...))
    for _hook, prim in hooks_of(code):
        if prim is None or change_possible(prim, spec):
            return True
    return False


def _procedure_ranks(tree: ast.Module) -> set:
    """The constant ranks a law's set_procedure(..., rank=...) calls name (loop variables over constant lists included)."""
    consts = _consts(tree)
    loops = _loop_values(tree, consts)
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "set_procedure":
            for kw in n.keywords:
                if kw.arg == "rank":
                    out |= set(_values(kw.value, consts, loops))
    return {r for r in out if isinstance(r, str)}


# ---------------------------------------------------------------------- composability
def check(laws: list, spec: dict, level: str | None = None) -> dict:
    """Composability of a law set (in enactment order) in a world with this spec: {"errors": [...], "dropped": [names above the
    world's law level], "overlaps": [{"change", "laws": [{name, rank, hook}]}]}. Errors: a law that does not check, a rank its
    set_procedure calls cannot reach, an import that is not a library entry or a cyclic or too deep import graph, a law that can never
    fire here. A law above the world's law level is dropped (as a regime's statutes are), not an error."""
    from charter import dispatch as D
    from charter import library as LB
    from charter import linker as LK
    level = level or spec.get("law_level") or "L4"
    errors, dropped, by_change = [], [], {}
    for law in laws:
        name, code = law["name"], law["code"]
        try:
            tree = L.check(code, v2=True)
            L.check_hooks(tree, True, D.ROUTED)
        except L.LawError as e:
            errors.append(f"{name}: {e}")
            continue
        rank = L.declared(tree, "rank") or "statute"
        for r in _procedure_ranks(tree):
            if r not in L.RANKS or r == "charter" or L.RANKS[r] > L.RANKS[rank]:
                errors.append(f"{name}: a {rank} cannot set the procedure for {r} drafts (declare rank = \"{r}\" or higher)")

        def resolve(_key, ref):
            kind, ident, pin = LK.parse_ref(ref)
            if kind != "lib":
                raise L.LawError(f"use({ref!r}): a law of a starting law set may import library entries only (lib:<name>@<sha>)")
            sub, shas = LB.lib_code(ident, pin)
            if sub is None:
                raise L.LawError(f"use({ref!r}): no such library entry" + (f" version (it has {', '.join(shas)})" if shas else ""))
            return f"lib:{ident}@{LK.sha(sub)}", sub
        try:
            L.check_graph(name, code, resolve)
            need = LB.classify_code(code)["level"]
        except L.LawError as e:
            errors.append(f"{name}: {e}")
            continue
        if LEVELS.index(need) > LEVELS.index(level):
            dropped.append({"name": name, "level": need})
            continue
        if not can_fire(code, spec):
            hooked = sorted({p for _h, p in hooks_of(code) if p})
            errors.append(f"{name}: can never fire in this world (it hooks only {', '.join(hooked) or 'nothing'}, which cannot happen "
                          f"with the modules that are on)")
            continue
        for hook, prim in hooks_of(code):
            if prim is not None:
                by_change.setdefault(prim, []).append({"name": name, "rank": rank, "hook": hook})
    overlaps = [{"change": p, "laws": v} for p, v in sorted(by_change.items()) if len({x["name"] for x in v}) > 1]
    return {"errors": errors, "dropped": dropped, "overlaps": overlaps}


# ---------------------------------------------------------------------- derived dimensions
def _consts(tree: ast.Module) -> dict:
    out = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and L.const_expr(n.value):
            try:
                out[n.targets[0].id] = ast.literal_eval(n.value)
            except ValueError:
                pass
    return out


def _loop_values(tree, consts) -> dict:
    """Loop variables over constant lists: {name: [values]} (for c in CLASSES: set_procedure(c, ...))."""
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.For) and isinstance(n.target, ast.Name):
            vals = _values(n.iter, consts, {})
            if isinstance(vals, list) and vals and all(isinstance(v, list) for v in vals):
                out[n.target.id] = vals[0]
            elif isinstance(n.iter, (ast.List, ast.Tuple)):
                out[n.target.id] = [e.value for e in n.iter.elts if isinstance(e, ast.Constant)]
    return out


def _values(expr, consts, loops) -> list:
    """The constant values an expression can have: [value] for a constant or a constant name, the loop's list for a loop variable."""
    if isinstance(expr, ast.Constant):
        return [expr.value]
    if isinstance(expr, ast.Name):
        if expr.id in loops:
            return list(loops[expr.id])
        if expr.id in consts:
            return [consts[expr.id]]
    return []


def _defs(tree) -> dict:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _calls(node, name) -> list:
    return [c for c in ast.walk(node) if isinstance(c, ast.Call) and getattr(c.func, "id", None) == name]


def _locals(fn, name) -> list:
    """Every value assigned to a local name in a function, in source order (the first is its definition, later ones fallbacks)."""
    return [n.value for n in ast.walk(fn) if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id == name]


def _truth(test, consts):
    """A test on constants (ELECTORATE == "citizens", not REVIEW): True/False, or None when it depends on the world."""
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], (ast.Eq, ast.NotEq)):
        a, b = _values(test.left, consts, {}), _values(test.comparators[0], consts, {})
        if a and b:
            return (a[0] == b[0]) == isinstance(test.ops[0], ast.Eq)
    if isinstance(test, ast.Name) and test.id in consts:
        return bool(consts[test.id])
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        t = _truth(test.operand, consts)
        return None if t is None else not t
    return None


def _returns(body, consts) -> list:
    """The return statements a function body can reach, folding tests on constants."""
    out = []
    for st in body:
        if isinstance(st, ast.Return):
            out.append(st)
            return out
        if isinstance(st, ast.If):
            t = _truth(st.test, consts)
            if t is True:
                out += _returns(st.body, consts)
                if out and isinstance(st.body[-1], ast.Return):
                    return out
            elif t is False:
                out += _returns(st.orelse, consts)
            else:
                out += _returns(st.body, consts) + _returns(st.orelse, consts)
        elif isinstance(st, (ast.For, ast.While)):
            out += _returns(st.body, consts)
    return out


def _mentions(expr, fn, defs, word, seen=None) -> bool:
    """Does the expression (following local names and helper calls one step at a time) call `word`?"""
    seen = seen if seen is not None else set()
    for n in ast.walk(expr):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == word:
            return True
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and fn is not None and (fn.name, n.id) not in seen:
            seen.add((fn.name, n.id))
            if any(_mentions(v, fn, defs, word, seen) for v in _locals(fn, n.id)):
                return True
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) in defs and n.func.id not in seen:
            seen.add(n.func.id)
            if _mentions(defs[n.func.id], defs[n.func.id], defs, word, seen):
                return True
    return False


def _excludes_officials(expr) -> bool:
    return any(isinstance(c, ast.Constant) and c.value in ("board", "fixer") for c in ast.walk(expr))


def _electorate(expr, fn, defs, consts, depth=0) -> str:
    """The kind of an electorate expression: right:<name>, citizens, all, class:<name>, wealth, drawn, composite or unknown."""
    if depth > 6 or expr is None:
        return "unknown"
    if _mentions(expr, fn, defs, "holdings_value"):
        return "wealth"
    if isinstance(expr, ast.Call):
        f = getattr(expr.func, "id", None)
        if f == "holders" and expr.args:
            v = _values(expr.args[0], consts, {})
            return f"right:{v[0]}" if v else "right:?"
        if f == "agents":
            if expr.args:
                v = _values(expr.args[0], consts, {})
                return f"class:{v[0]}" if v else "class:?"
            return "all"
        if f == "list" and expr.args:
            return "composite"
        if f in defs:
            rets = [r.value for r in _returns(defs[f].body, consts) if r.value is not None]
            kinds = {_electorate(v, defs[f], defs, consts, depth + 1) for v in rets}
            return kinds.pop() if len(kinds) == 1 else "unknown"
    if isinstance(expr, (ast.ListComp, ast.GeneratorExp)):
        it = expr.generators[0].iter
        base = _electorate(it, fn, defs, consts, depth + 1)
        conds = [c for g in expr.generators for c in g.ifs]
        if base == "all" and conds and all(_excludes_officials(c) for c in conds):
            return CITIZENS
        if base in ("all", CITIZENS) and not conds:
            return base
        return base if base.startswith(("right:", "class:")) else "unknown"
    if isinstance(expr, ast.Name):
        vals = _locals(fn, expr.id) if fn is not None else []
        if vals:
            return _electorate(vals[0], fn, defs, consts, depth + 1)
        return "unknown"
    if isinstance(expr, ast.Subscript):
        if isinstance(expr.value, ast.Name) and expr.value.id == "state":
            return "drawn"
        return _electorate(expr.value, fn, defs, consts, depth + 1)
    if isinstance(expr, ast.BinOp):
        return "composite"
    return "unknown"


def _summary(fn, defs, consts) -> dict:
    """What a procedure function decides: {"electorate", "rule", "weighted", "gated", "decree"}."""
    out = {"electorate": None, "rule": None, "weighted": None, "gated": False, "decree": None}
    for r in _returns(fn.body, consts):
        v = r.value
        if isinstance(v, ast.Constant) and v.value is True:
            guard = [c for c in _calls(fn, "has") if len(c.args) == 2]
            if guard:
                vals = _values(guard[0].args[1], consts, {})
                out["decree"] = f"right:{vals[0]}" if vals else "right:?"
            else:
                out["electorate"], out["rule"] = "none", "pass"
        elif isinstance(v, ast.Call) and getattr(v.func, "id", None) == "has" and len(v.args) == 2:
            vals = _values(v.args[1], consts, {})
            out["decree"] = f"right:{vals[0]}" if vals else "right:?"
        elif isinstance(v, ast.Dict):
            d = {k.value: x for k, x in zip(v.keys, v.values) if isinstance(k, ast.Constant)}
            out["electorate"] = _electorate(d.get("electorate"), fn, defs, consts)
            rv = _values(d["rule"], consts, {}) if "rule" in d else ["majority"]
            out["rule"] = rv[0] if rv else "unknown"
            if "weights" in d:
                out["weighted"] = "wealth" if _mentions(d["weights"], fn, defs, "holdings_value") else "other"
            out["gated"] = out["gated"] or "gate" in d
    return out


def procedures(code: str) -> dict:
    """The procedures a law sets when it is enacted: {"<cls>" or "<rank>:<cls>": summary} (set_procedure calls in on_enact; a
    constitution that sets procedures only later, like anarchy's convention, sets none at round 0)."""
    tree = _tree(code)
    defs, consts = _defs(tree), _consts(tree)
    loops = _loop_values(tree, consts)
    out = {}
    if "on_enact" not in defs:
        return out
    for c in _calls(defs["on_enact"], "set_procedure"):
        if len(c.args) < 2:
            continue
        classes = _values(c.args[0], consts, loops)
        ranks = [None]
        for kw in c.keywords:
            if kw.arg == "rank":
                ranks = _values(kw.value, consts, loops) or ["?"]
        fn = defs.get(getattr(c.args[1], "id", None))
        summ = _summary(fn, defs, consts) if fn is not None else {"electorate": "unknown", "rule": "unknown", "weighted": None,
                                                                  "gated": False, "decree": None}
        for cls in classes:
            for r in ranks:
                out[f"{r}:{cls}" if r else cls] = summ
    return out


def _granted_in_loops(tree, consts) -> dict:
    """Rights a law grants to everyone, to citizens or to a class at enactment: {right: kind}."""
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.For):
            kind = _electorate(n.iter, None, {}, consts)
            ifs = [s.test for s in n.body if isinstance(s, ast.If)]
            if kind == "all" and ifs and all(_excludes_officials(t) for t in ifs):
                kind = CITIZENS
            for c in _calls(n, "grant"):
                if len(c.args) == 2:
                    for v in _values(c.args[1], consts, {}):
                        out[v] = kind
    return out


def _elected(laws) -> dict:
    """Rights filled by an election: {right: electorate kind} (an open_ballot whose result callback grants the right)."""
    granted, out = {}, {}
    for law in laws:
        tree = _tree(law["code"])
        granted.update(_granted_in_loops(tree, _consts(tree)))
    for law in laws:
        tree = _tree(law["code"])
        defs, consts = _defs(tree), _consts(tree)
        for fn in defs.values():
            for c in _calls(fn, "open_ballot"):
                args = list(c.args)
                cb = args[5] if len(args) > 5 else next((k.value for k in c.keywords if k.arg == "on_result"), None)
                if len(args) < 2 or not isinstance(cb, ast.Name) or cb.id not in defs:
                    continue
                kind = _electorate(args[1], fn, defs, consts)
                if kind.startswith("right:"):
                    kind = granted.get(kind[6:], kind)
                for g in _calls(defs[cb.id], "grant"):
                    if len(g.args) == 2:
                        for v in _values(g.args[1], consts, {}):
                            out[v] = kind
    return out


def _label(procs: dict, elected: dict) -> str:
    """The scorer's label of the starting order, from the procedures in force (the ordinary class decides most laws)."""
    if not procs:
        return "anarchy"
    if any(p["decree"] for p in procs.values()):
        return "dictatorship"
    main = procs.get("ordinary") or next(iter(procs.values()))
    kind = main["electorate"] or "unknown"
    if main["weighted"] == "wealth" or kind == "wealth":
        return "oligarchy"
    if kind in (CITIZENS, "all", "none"):
        return "democracy"
    if kind.startswith("right:") and elected.get(kind[6:]) in (CITIZENS, "all"):
        return "democracy"
    return "oligarchy"


TAX_HOOKS = ("on_harvest", "on_transfer", "before_harvest", "before_move")


def _charges(fn) -> bool:
    """Does a hook return a charge (a number, or a dict with a charge), rather than only blocks and abstentions?"""
    for r in ast.walk(fn):
        if isinstance(r, ast.Return) and r.value is not None:
            v = r.value
            if isinstance(v, ast.Dict):
                if any(isinstance(k, ast.Constant) and k.value == "charge" for k in v.keys):
                    return True
            elif isinstance(v, ast.Constant):
                if type(v.value) in (int, float) and v.value:
                    return True
            else:
                return True
    return False


def _lookup(procs, cls, rank):
    from charter import dispatch as D
    key = D.procedure_lookup({k: k for k in procs}, cls, rank)
    return procs.get(key) if key else None


def dimensions(laws: list) -> dict:
    """The dimension vector of a law set (constitution first, then statutes, in enactment order). Pure and static."""
    procs: dict = {}
    ranks, classes, hooks, coverage = {}, {}, {}, {}
    flags = {"entrenched": False, "rights_guard": False, "review": False, "courts": False, "offices": 0, "succession": False,
             "taxes": False, "registers": False}
    from charter import library as LB
    for law in laws:
        code = law["code"]
        tree = _tree(code)
        procs.update(procedures(code))
        rank = L.declared(tree, "rank") or law.get("rank") or "statute"
        ranks[rank] = ranks.get(rank, 0) + 1
        try:
            cls = LB.classify_code(code)["cls"]
        except L.LawError:
            cls = "unknown"
        classes[cls] = classes.get(cls, 0) + 1
        calls = L.calls(tree)
        names = [h for h, _p in hooks_of(code)]
        for hook, prim in hooks_of(code):
            fam = family(prim)
            hooks[fam] = hooks.get(fam, 0) + 1
            if prim:
                coverage.setdefault(prim, {}).setdefault(rank, 0)
                coverage[prim][rank] += 1
        flags["entrenched"] |= bool({"before_amend", "before_repeal"} & set(names))
        flags["rights_guard"] |= bool({"before_revoke_right", "before_suspend_right", "before_set_dm_limit"} & set(names))
        flags["review"] |= "before_propose" in names or ("repeal" in calls and "define_action" in calls)
        flags["courts"] |= "clause" in calls or bool({"on_ruling", "after_rule", "before_rule"} & set(names))
        flags["offices"] += int("define_action" in calls)
        flags["succession"] |= bool({"after_end_life", "before_end_life"} & set(names))
        flags["taxes"] |= any(_charges(f) for f in tree.body if isinstance(f, ast.FunctionDef) and f.name in TAX_HOOKS)
        flags["registers"] |= "public" in {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    elected = _elected(laws)
    amend = _lookup(procs, "procedural", "constitution")
    return {"label": _label(procs, elected),
            "procedures": {k: dict(v) for k, v in sorted(procs.items())},
            "amendment_rule": (amend or {}).get("rule") or ("decree" if (amend or {}).get("decree") else None),
            "elected": dict(sorted(elected.items())), **flags,
            "ranks": dict(sorted(ranks.items())), "classes": dict(sorted(classes.items())), "hooks": dict(sorted(hooks.items())),
            "coverage": {p: dict(sorted(v.items())) for p, v in sorted(coverage.items())}}


def key(dims: dict) -> tuple:
    """The part of a dimension vector that sampling holds fixed (no counts of laws or hooks: those vary with the law set)."""
    return (dims["label"], tuple((k, v["electorate"], v["rule"], v["weighted"], v["gated"], v["decree"])
                                 for k, v in dims["procedures"].items()),
            dims["amendment_rule"], dims["entrenched"], dims["rights_guard"], dims["review"], dims["courts"], dims["succession"],
            dims["taxes"])


# ---------------------------------------------------------------------- fingerprints and distance
def of(laws: list) -> dict:
    """The fingerprint of a law set given as code: [{"name", "code", "rank"?, "template"?}]."""
    from charter import linker as LK
    rows, coverage = [], {}
    for law in laws:
        rank = rank_of(law["code"], law.get("rank") or "statute")
        row = {"title": L.header(law["code"])[0], "sha": LK.sha(law["code"]), "rank": rank}
        if law.get("id"):
            row = {"id": law["id"], **row}
        if law.get("cls"):
            row["cls"] = law["cls"]
        if law.get("template"):
            row["template"] = law["template"]
        rows.append(row)
        for _h, prim in hooks_of(law["code"]):
            if prim:
                coverage.setdefault(prim, {}).setdefault(rank, 0)
                coverage[prim][rank] += 1
    return {"shas": sorted({r["sha"] for r in rows}), "laws": rows,
            "coverage": {p: dict(sorted(v.items())) for p, v in sorted(coverage.items())}}


def fingerprint(k) -> dict:
    """The legal fingerprint of a world now: every law in force (constitution and statutes), with its id, sha, rank, class and the
    template it was made from (regime law sets), and the coverage matrix."""
    from charter import dispatch as D
    laws = [{"id": x["id"], "name": x["title"], "code": x["code"], "rank": D.rank_of(k, x["id"]), "cls": x["cls"],
             "template": x.get("template")} for x in k.active_laws()]
    return of(laws)


def distance(a: dict, b: dict) -> dict:
    """How far apart two legal systems are (fingerprints): the laws only one has (by sha), Jaccard distance of the sha sets, and the
    coverage difference primitive x rank (b minus a) with its L1 norm."""
    sa, sb = set(a["shas"]), set(b["shas"])
    union = sa | sb
    diff = {}
    for p in sorted(set(a["coverage"]) | set(b["coverage"])):
        for r in sorted(set(a["coverage"].get(p, {})) | set(b["coverage"].get(p, {}))):
            d = b["coverage"].get(p, {}).get(r, 0) - a["coverage"].get(p, {}).get(r, 0)
            if d:
                diff.setdefault(p, {})[r] = d
    l1 = sum(abs(x) for v in diff.values() for x in v.values())
    return {"only_a": sorted(sa - sb), "only_b": sorted(sb - sa), "jaccard": (len(union - (sa & sb)) / len(union)) if union else 0.0,
            "coverage_diff": diff, "coverage_l1": l1}


# ---------------------------------------------------------------------- command line: python -m charter library list|show
def add_arguments(p) -> None:
    p.add_argument("what", choices=["list", "show"])
    p.add_argument("name", nargs="?", help="show: a toolkit template, library law or block")
    p.add_argument("--family", help="list: only this toolkit family")
    p.add_argument("--set", action="append", default=[], help="show: instantiate with CONSTANT=value (YAML value; repeatable)")


def cmd(a) -> int:
    import yaml
    from charter import library as LB
    if a.what == "list":
        print(f"{'template':34} {'family/topic':34} {'rank':12} {'class':10} level  main hook")
        for n, e in LB.TOOLKIT.items():
            if a.family and e["family"] != a.family:
                continue
            i = LB.classify_code(e["code"])
            print(f"{n:34} {e['family'] + '/' + e['topic']:34} {e['rank']:12} {i['cls']:10} {i['level']:6} {e['fires']}")
        pend = [e for e in LB.PENDING.values() if not a.family or e["family"] == a.family]
        if pend:
            print("\nTODO (waits on a roadmap item):")
            for e in pend:
                print(f"  {e['name']:32} {e['family'] + '/' + e['topic']:34} waits on {e['waits_on']}")
        if not a.family:
            print("\nBuilding blocks: " + ", ".join(f"{n} ({LB.ref(n)})" for n in LB.BLOCKS))
        return 0
    if not a.name:
        print("library show NAME [--set CONSTANT=value ...]")
        return 2
    name = a.name
    if name not in LB.TOOLKIT and name not in LB.LIB and name not in LB.BLOCKS:
        import difflib
        hit = difflib.get_close_matches(name, list(LB.TOOLKIT) + list(LB.LIB) + list(LB.BLOCKS), 1)
        print(f"no library entry {name!r}" + (f" (did you mean {hit[0]!r}?)" if hit else ""))
        return 2
    if name in LB.BLOCKS:
        print(f"{name}: block {LB.ref(name)}\n\n{LB.BLOCKS[name]['code']}")
        return 0
    params = {}
    for s in a.set:
        k, _, v = s.partition("=")
        params[k.strip()] = yaml.safe_load(v)
    src = LB.instantiate(name, params) if params else LB.code(name)
    i = LB.classify_code(src)
    e = LB.TOOLKIT.get(name)
    head = f"{name}: " + (f"{e['family']}/{e['topic']}, rank {rank_of(src)}, " if e else f"library law ({LB.LIB[name]['category']}), ")
    print(head + f"class {i['cls']}, level {i['level']}" + (f", main hook {e['fires']}" if e else ""))
    if e:
        print(e["doc"])
    print("parameters: " + (", ".join(f"{k}={v!r}" for k, v in LB.params(name).items()) or "none"))
    print("\n" + src)
    return 0
