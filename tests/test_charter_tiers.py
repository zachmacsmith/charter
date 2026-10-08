"""Review 12 WP0 (W8a): the tier classification as data (charter/tiers.py, primitives.Primitive.tier).

Every primitive row has a tier consistent with its routing and blockability; the hard-coded rules registry has one row per item of
review 12's inventory (the ids parsed from docs/review/12_hardcoded_inventory.md), its counts are the review's (§2.15), and every
file:function reference and spec key in it resolves (a module-level def, class, method or assigned name; schema.keys())."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from charter import primitives as PR
from charter import schema as S
from charter import tiers as T

ROOT = Path(__file__).resolve().parent.parent / "charter"
REVIEW = Path(__file__).resolve().parent.parent / "docs" / "review" / "12_hardcoded_inventory.md"


# ---------------------------------------------------------------------- primitives
@pytest.mark.parametrize("p", list(PR.PRIMITIVES.values()), ids=lambda p: p.name)
def test_every_primitive_row_has_a_tier(p):
    assert p.tier in T.PRIMITIVE_TIERS, (p.name, p.tier)
    if p.tier == "L-route":
        assert not p.routed, "an L-route primitive is one the kernel does not route yet: routing it makes it L"
    if p.tier == "L":
        assert p.routed, "an L primitive is routed (a law may hook it)"
    if p.tier == "P":
        assert not p.blockable, "laws cannot block physics (review 12 §1)"
    if p.tier in ("E", "X"):
        assert not p.routed, "epistemic and experimental changes are not hookable"


def test_the_unrouted_primitives_are_review_12_s_list():
    """§2.14: 38 unrouted primitives: 31 L-route, 1 P, 2 E, 4 X. W8b (WP1) routed the 31 L-route rows: 7 remain."""
    unrouted = [p for p in PR.PRIMITIVES.values() if not p.routed]
    by = {t: sorted(p.name for p in unrouted if p.tier == t) for t in T.PRIMITIVE_TIERS}
    assert len(unrouted) == 7 and {t: len(v) for t, v in by.items() if v} == {"P": 1, "E": 2, "X": 4}
    assert not PR.TIER_OF["L-route"]
    assert by["P"] == ["demand_tribute"] and by["E"] == ["use_power", "write_note"]
    assert by["X"] == ["request_fix", "set_goal", "set_role", "suspend_law"]


def test_tier_table_names_real_primitives_once():
    seen = [n for names in PR.TIER_OF.values() for n in names]
    assert len(seen) == len(set(seen)) and set(seen) == set(PR.PRIMITIVES)
    assert set(PR.TIER_OF) <= set(T.PRIMITIVE_TIERS)


# ---------------------------------------------------------------------- the hard-coded rules registry
def test_rules_are_review_12_s_inventory():
    ids = [r.id for r in T.RULES]
    assert len(ids) == len(set(ids)) == 112
    text = REVIEW.read_text().split("## 2. Inventory", 1)[1].split("## 3.", 1)[0]
    doc = re.findall(r"^\| (?:\*\*)?([A-Z]-?\d+)(?:\*\*)? \|", text, re.M)
    assert ids == doc                                                    # same rows, same order


def test_rule_counts_are_review_12_s():
    """§2.15: P 16, E 13, X 25, L 58 (11 already law; of the 47 to move, 5 L-route and 42 L-rule). W8b (WP1) routed the 5 L-route
    rows: C2, D6, I6 and R6 are law now (L), N1's world rule (declare cost, minimum members) remains (L-rule)."""
    n = {t: sum(1 for r in T.RULES if r.tier == t) for t in T.TIERS}
    assert (n["P"], n["E"], n["X"]) == (16, 13, 25)
    assert n["L"] + n["L-route"] + n["L-rule"] == 58 and n["L"] == 15 and n["L-route"] == 0 and n["L-rule"] == 43
    assert sorted(r.id for r in T.RULES if r.note == "L-route until W8b") == ["C2", "D6", "I6", "R6"]
    assert T.RULE["N1"].tier == "L-rule"


_DEFS: dict = {}


def _defs(module: str) -> set:
    """Qualified names a module defines: defs and classes (nested: Kernel.api_for.title), and module-level assigned names."""
    if module not in _DEFS:
        path = ROOT / (module.replace(".", "/") + ".py")
        out: set = set()
        stack: list = []

        class V(ast.NodeVisitor):
            def visit_FunctionDef(self, n):
                stack.append(n.name)
                out.add(".".join(stack))
                self.generic_visit(n)
                stack.pop()

            visit_ClassDef = visit_AsyncFunctionDef = visit_FunctionDef

        tree = ast.parse(path.read_text()) if path.exists() else ast.Module(body=[], type_ignores=[])
        V().visit(tree)
        for n in tree.body:
            targets = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, ast.AnnAssign) else []
            out.update(t.id for t in targets if isinstance(t, ast.Name))
        _DEFS[module] = out if path.exists() else None
    return _DEFS[module]


@pytest.mark.parametrize("r", T.RULES, ids=lambda r: r.id)
def test_rule_row_is_well_formed_and_resolves(r):
    assert r.tier in T.TIERS and r.rule and r.today
    assert r.where or r.spec or r.today == "missing", "a rule is made somewhere: code or spec (or it is missing)"
    for ref in r.where:
        module, _, qual = ref.partition(":")
        defs = _defs(module)
        assert defs is not None, f"{r.id}: no module charter/{module.replace('.', '/')}.py"
        assert qual in defs, f"{r.id}: {ref} is not defined"
    keys = S.keys()
    for key in r.spec:
        assert key in keys, f"{r.id}: unknown spec key {key}"
