"""Goal registry (P1.5): one row per goal, the old tables derived from it, every rule written, every example passing, and the
generated text/rule listing (docs/goal_rules.md) current. No runs, no model calls."""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from charter import goal_registry as GR
from charter import goals as G
from charter import history as HI
from charter import life as LF
from charter import roles as RO

DOC = Path(__file__).resolve().parents[1] / "docs" / "goal_rules.md"


def test_registry_covers_the_catalogue():
    assert set(GR.GOALS) == set(G.CATALOGUE) == set(G.SCORERS)
    assert list(GR.GOALS) == list(G.CATALOGUE)                       # draw order is the catalogue order
    for name, g in GR.GOALS.items():
        assert G.CATALOGUE[name] == (g.category, g.weight, g.min_level, g.text)
        assert GR.get(name) is g


VERSIONS = {"Leaker": 2,                                             # P7.2: common text rendered from the sections
            "Lawmaker": 2}                                            # W9: only laws that took effect count


@pytest.mark.parametrize("name", list(GR.GOALS) + list(GR.FIXED))
def test_every_goal_has_a_rule_and_a_version(name):
    g = GR.get(name)
    assert isinstance(g.rule, str) and len(g.rule.strip()) > 20, name
    assert g.version == VERSIONS.get(name, 1) and g.text and callable(g.score) and callable(g.params)
    assert g.needs, name


def test_every_example_passes():
    assert GR.check_examples() == []
    assert [n for n, g in GR.GOALS.items() if not g.examples] == []     # every goal has an executable example (P6.1)


def test_a_wrong_example_is_reported():
    bad = GR.replace(GR.GOALS["Wealth"], examples=(GR.ex("A", {}, 0.25, final={"values": {"A": 5.0, "B": 10.0}}),))
    old = GR.GOALS["Wealth"]
    GR.GOALS["Wealth"] = bad
    try:
        assert GR.check_examples(["Wealth"]) == ["Wealth example 0: expected 0.25, got 0.5"]
    finally:
        GR.GOALS["Wealth"] = old


def test_score_is_the_native_scorer():
    h = GR.EXAMPLES["Gifts"][0][0]()
    for name in GR.GOALS:
        g = GR.GOALS[name]
        assert g.score.native is G.HSCORERS[name] and g.score.legacy is G.SCORERS[name]
    for name in ("Gifts", "Safety", "Benefactor", "Wealth"):
        g = GR.GOALS[name]
        assert g.score(h, "A", {}, HI.Ctx(h)) == G.SCORERS[name](h.gt, "A", {}) == HI.score_goal(h, name, "A", {})
    for name, legacy in (("Board objective", G.board_score), ("Fixer objective", G.fixer_score)):
        assert GR.FIXED[name].score(h, "A") == legacy(h.gt, "A") and GR.FIXED[name].score.legacy is legacy


def test_examples_agree_with_the_legacy_scorers():
    """Every example's expected value is also what the version-1 legacy scorer gives on the same fixture (a port, not a change)."""
    for name, g in GR.GOALS.items():
        for fx, agent, params, expected in g.examples:
            h = fx()
            assert GR._close(G.SCORERS[name](h.gt, agent, params), expected), name


def test_native_scorers_equal_legacy_on_every_window_of_every_example():
    """On each example's fixture, the native scorer equals the version-1 legacy scorer on the whole history and on every window
    (r0, r1), for every agent: the examples exercise branches the golden runs never reach (loans, leaks, deaths, lineage, ...)."""
    def outcome(fn, *a):
        try:
            return ("ok", fn(*a))
        except Exception:                                            # both must fail alike (e.g. an agent missing from a table)
            return ("error", None)

    n = 0
    for name, g in GR.GOALS.items():
        for fx, agent, params, _ in g.examples:
            h = fx()
            rs = h.rounds
            for v in [h] + [h.window(r0, r1) for i, r0 in enumerate(rs) for r1 in rs[i:]]:
                for a in sorted(set(v.final["values"]) | set(v.start_values)):
                    assert outcome(G.HSCORERS[name], v, a, params, HI.Ctx(v)) == outcome(G.SCORERS[name], v.gt, a, params), \
                        (name, a, params, v)
                    n += 1
    assert n > 1000


def test_old_names_are_derived_from_the_rows():
    rows = GR.GOALS.values()
    assert set(G.NEW_GOALS) == {g.name for g in rows if g.gate == "update"} == {"Eliminator", "Seat", "Dynasty"}
    assert set(G.EXTRA_GATES) == {g.name for g in rows if g.gate == "package"}
    assert all(G.EXTRA_GATES[n] == GR.GOALS[n].requires for n in G.EXTRA_GATES)
    assert set(G.HAVOC) == {g.name for g in rows if g.category == "Havoc"}
    assert set(G.DIRECT_SHARE) == {g.name for g in rows if g.share == "direct"}
    assert {n for n, s in G.SLOTS.items() if s == G.NOT_PRIMARY} == G._SECONDARY_ONLY
    assert set(G.PASSIVE) == {"Safety", "Bodyguard", "Block", "Concealment"}
    assert list(G.COUNTER_GOALS) == ["Block", "Bodyguard", "Concealment"]
    assert RO.HAVOC_REFUSAL == ("Eliminator",) + G.HAVOC and "Framer" not in RO.HAVOC_REFUSAL
    assert LF.HISTORY == {g.name for g in rows if g.lineage == "record"} and LF.SUMMED == {"Wealth", "Power", "Hoard"}
    assert "Dynasty" not in LF.HISTORY | LF.SUMMED and GR.GOALS["Dynasty"].lineage == "own"
    assert LF.LINEAGE_OVERRIDE == {"Wealth", "Rank", "Hoard", "Diversifier", "Currency Magnate", "Power", "Office", "Sovereign",
                                   "Seat", "Title", "Spymaster"}


def test_samplers_and_text():
    world = {"resources": ["timber"], "camps": ["c1"], "hardest_camp": "c1", "library": [], "agents": [("A", "worker", []),
             ("B", "worker", ["vote"])], "compute": {}, "channels_dm": True, "has_media": False, "has_scientists": False}
    for name in GR.GOALS:
        r1, r2 = random.Random(name), random.Random(name)
        assert G.sample_params(name, r1, world, "A") == GR.GOALS[name].params(r2, world, "A")
        assert r1.random() == r2.random()                              # same RNG consumption
    assert G.sample_params("Board objective", random.Random(1), world, "A") == {}
    assert G.describe("Kingmaker", {"target": "B"}).startswith("get B into the top 3")
    assert G.describe("Kingmaker", {}).startswith("get  into the top 3")    # a missing parameter renders as "" (as before)
    g = {"primary": "Wealth", "params": {}, "secondary": "Rival", "secondary_params": {"target": "B"}}
    assert GR.slot_text(g, [0.7, 0.3]) == (f"Primary goal (70% of your score): {G.describe('Wealth', {})}. "
                                           f"Secondary goal (30%): {G.describe('Rival', {'target': 'B'})}.")
    assert GR.slot_text(g, [1.0]) == G.describe("Wealth", {})


def test_probes_are_declared_for_predicate_goals():
    for name in ("Enact", "Enact as author", "Block", "Durable", "Outcome"):
        assert GR.GOALS[name].probes and "predicates" in GR.GOALS[name].needs


def test_goal_rules_doc_is_current():
    md = GR.rules_markdown()
    assert DOC.read_text() == md, "regenerate docs/goal_rules.md from goal_registry.rules_markdown()"
    for name, g in GR.GOALS.items():
        assert f"| {name} |" in md
    for name in ("Rank", "Board objective", "Kingmaker", "Title"):
        assert GR.TEXT_VS_SCORER[name][0] == "yes"
