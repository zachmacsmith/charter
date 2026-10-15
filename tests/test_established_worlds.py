"""Established starting worlds (docs/review/27 §0, §6, §7): the three bugs, agents.names, the start block, the Offices Act, per-office
control of institution resources, and the Millbrook preset."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from charter import generator as GN
from charter import schema as SC
from charter import spec as S


def nature_child(tmp_path, body: dict) -> dict:
    p = tmp_path / "child.yaml"
    p.write_text(yaml.safe_dump({"extends": ["nature_subsistence"], **body}))
    return S.load(str(p))


# ---------------------------------------------------------------------- bug 1: food templates in a regime
def test_food_templates_pass_the_schema_in_a_regime_and_start_laws():
    sp = S.load("nature_subsistence")
    sp["regime"] = {"base": None, "name": "village", "constitution": "assembly",
                    "laws": [{"template": "Relief Act", "params": {"STORE": "S1", "BUDGET": 4}},
                             {"template": "Food Levy", "params": {"STORE": "S1"}}]}
    assert not [e for e in SC.validate(sp) if "regime" in e]
    sp["regime"]["laws"][0]["params"]["NOPE"] = 1
    assert any("Relief Act has no constant NOPE" in e for e in SC.validate(sp))
    sp2 = S.load("nature_subsistence")
    sp2["start_laws"] = ["Relief Act"]
    assert not [e for e in SC.validate(sp2) if "start_laws" in e]


def test_food_template_regime_law_is_enacted(tmp_path):
    sp = nature_child(tmp_path, {"regime": {"base": None, "name": "village", "constitution": "assembly",
                                            "laws": [{"template": "Relief Act", "params": {"BUDGET": 4}}]},
                                 "jurisdictions": {"start": "j0"}})
    inst = GN.generate(sp, 1)
    names = [s["name"] for s in inst["regime"]["statutes"]]
    assert "Relief Act" in names and "BUDGET = 4" in next(s["code"] for s in inst["regime"]["statutes"] if s["name"] == "Relief Act")


# ---------------------------------------------------------------------- bug 2: an inline regime is set whole
def test_child_inline_regime_replaces_the_inherited_one(tmp_path):
    sp = nature_child(tmp_path, {"regime": {"name": "village", "constitution": "assembly"}})
    assert sp["regime"] == {"name": "village", "constitution": "assembly"}        # no inherited base: state_of_nature
    sp = nature_child(tmp_path, {"regime": {"laws": [{"template": "Relief Act"}]}})
    assert any("needs a constitution" in e for e in SC.validate(sp))                # not silently voided: an error


def test_empty_mapping_clears_inherited_placements(tmp_path):
    sp = S.load("haiku100")
    assert sp["goals"]["explicit"] == {} and sp["models"]["overrides"] == {}


# ---------------------------------------------------------------------- bug 3: names fixed per seed; orphaned placements are errors
def small(names=None, **extra):
    sp = S.load("E0")
    sp["agents"] = {"worker": 3, "legislator": 2, "scientist": 0, "media": 0, "board": 0, "fixer": 0, **({"names": names} if names else {})}
    for k, v in extra.items():
        sp = S.set_path(sp, k, v)
    return sp


def test_names_fixed_are_seed_stable_and_bound_to_classes():
    sp = small({"worker": ["Wat", "Wynn", "Wren"], "legislator": ["Lyle", "Lark"]})
    for seed in (1, 2, 3):
        inst = GN.generate(copy.deepcopy(sp), seed)
        by = {a["id"]: a["cls"] for a in inst["agents"]}
        assert by == {"Wat": "worker", "Wynn": "worker", "Wren": "worker", "Lyle": "legislator", "Lark": "legislator"}
    inst = GN.generate(small("fixed"), 4)
    assert sorted(a["id"] for a in inst["agents"]) == sorted(GN.NAMES[:5])


def test_fixed_names_keep_every_other_draw():
    a = GN.generate(small(), 7)
    # the same world with the drawn names given explicitly, per class in roster order of first appearance
    names = {}
    for x in a["agents"]:
        names.setdefault(x["cls"], []).append(x["id"])
    b = GN.generate(small(names), 7)
    assert [x["cls"] for x in a["agents"]] == [x["cls"] for x in b["agents"]]
    assert [x["endowment"] for x in a["agents"]] == [x["endowment"] for x in b["agents"]]
    assert [x["rights"] for x in a["agents"]] == [x["rights"] for x in b["agents"]]


def test_grand35_names_are_seed_35s():
    sp = S.load("grand35")
    for seed in (1, 35):
        inst = GN.generate(copy.deepcopy(sp), seed)
        assert inst["agents"] and {a["id"]: a["goal"]["primary"] for a in inst["agents"]}["Clara"] == "Bloodline Eliminator"


def test_orphaned_placement_is_an_error():
    sp = small(**{"goals.explicit": {"Nobody": "Wealth"}})
    with pytest.raises(ValueError, match="match no agent.*goals.explicit: Nobody.*agents.names"):
        GN.generate(sp, 1)
    sp = small({"worker": ["Wat", "Wynn", "Wren"], "legislator": ["Lyle", "Lark"]}, **{"models.overrides": {"Wat": "x", "Ghost": "y"}})
    with pytest.raises(ValueError, match="models.overrides: Ghost"):
        GN.generate(sp, 1)


def test_bad_names():
    with pytest.raises(ValueError, match="2 names for 3 agents"):
        GN.generate(small({"worker": ["A", "B"], "legislator": ["C", "D"]}), 1)
    with pytest.raises(ValueError, match="distinct"):
        GN.generate(small(["A", "A", "B", "C", "D"]), 1)
    assert any("agents.names" in e for e in SC.validate(small(7)))
