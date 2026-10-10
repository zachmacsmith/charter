"""Review 14 package A, the design arm on today's code: no template names leak when templates are not offered, the core action
surface, outcome-only goal draws (every goal classified), the library visibility modes, the two arm presets differing only in the
design-arm flags, and the novelty metric on known template code against novel code (charter/novelty.py)."""
from __future__ import annotations

import json
import re

import pytest

from charter import action_registry as AR
from charter import actions as A
from charter import agents as AG
from charter import context as CX
from charter import contracts as CT
from charter import generator
from charter import goal_registry as GR
from charter import goals as G
from charter import library as LB
from charter import novelty as NV
from charter import preview as PV
from charter import schema
from charter import spec as S
from charter.kernel import Kernel

# Template names as offered (club, company, crowdfund, cartel, exchange; standing_order is also an action's name) and the
# institution goals' kinds. "company" and "exchange" also appear as ordinary words elsewhere (incorporation's company rules, a
# swap is "an exchange between two members' escrows"), so they are checked where a template would be offered: the contracts
# phrase, create_contract's purpose and doc, and the Contracts manual section's template list.
LEAK = re.compile(r"\b(clubs?|crowdfunds?|cartels?|insurers?|rackets?|templates?)\b", re.I)
FLAGS = {("contracts", "offer_templates"), ("law", "library", "visibility"), ("goals", "outcome_only"), ("actions", "core_only")}


def make(preset, extra=(), seed=1):
    inst = generator.generate(S.apply_overrides(S.load(preset), ["rounds=4", "turns=sequential", "contracts.scripted=false",
                                                                 *extra]), seed)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    return inst, k


def citizen(k):
    return next(a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer"))


def texts(inst, k, a):
    """Every text this agent's prompt layers show: the core prompt, every manual section, the legacy system prompt."""
    return [CX.core_prompt(inst, a, k)] + [f"{t}\n{x}" for t, x in CX.build_manual(inst, k, a["id"])] + [AG.system_prompt(inst, a)]


@pytest.fixture(scope="module")
def design():
    with PV.world("design_arm", 1, ["rounds=3"], rounds=0) as (inst, k):     # before any agent writes (bots copy templates)
        yield inst, k


@pytest.fixture(scope="module")
def scaffolded():
    with PV.world("scaffolded_arm", 1, ["rounds=3"], rounds=0) as (inst, k):
        yield inst, k


# ---------------------------------------------------------------------- 1. no template names
def test_no_template_names_leak_in_design_arm_prompts(design):
    inst, k = design
    assert not AR.templates_offered(inst["spec"])
    for a in inst["agents"]:
        for t in texts(inst, k, a):
            hits = [m.group() for m in LEAK.finditer(t)]
            assert not hits, (a["id"], hits, t[:300])
    doc = AG.action_doc("create_contract", inst, inst["agents"][0])
    assert "company" not in doc and "exchange" not in doc and '"code"' in doc
    assert AR.phrase("contracts", inst["spec"]).count("(") == 1 and "compan" not in AR.phrase("contracts", inst["spec"])


def test_scaffolded_arm_still_offers_the_templates(scaffolded):
    inst, k = scaffolded
    a = next(x for x in inst["agents"] if x["cls"] == "worker")
    core = CX.core_prompt(inst, a, k)
    assert "clubs, companies, crowdfunds, cartels, exchanges" in core
    assert "templates: club, company" in AG.action_doc("create_contract", inst, a)


def test_templates_false_no_longer_leaks_the_names():
    inst, k = make("E2", ["law.v2=true", "contracts.enabled=true", "contracts.templates=false"])
    a = inst["agents"][0]
    assert not LEAK.search(AG.action_doc("create_contract", inst, a))
    assert not LEAK.search(CT.rules_text(inst))
    assert not LEAK.search(AR.phrase("contracts", inst["spec"]))
    assert not LEAK.search(CX.action_sections([n.name for n in AR.REG.values() if n.module == "contracts"], [], None, (),
                                              inst["spec"]))


def test_create_contract_takes_code_only_and_errors_name_no_template():
    inst, k = make("E2", ["law.v2=true", "contracts.enabled=true", "contracts.offer_templates=false"])
    aid = citizen(k)
    with pytest.raises(A.ActionError) as e:
        A.act(k, aid, "create_contract", {"name": "X", "template": "club"})
    assert not LEAK.sub("", str(e.value)).count("club") and "company" not in str(e.value) and "cartel" not in str(e.value)
    out = A.act(k, aid, "create_contract", {"name": "Own", "code": CT.SCRIPTED_OWN_CODE})
    assert "own code" in out
    cid = re.search(r"A\d+", out).group()
    with pytest.raises(A.ActionError) as e:
        A.act(k, aid, "propose_contract_change", {"contract": cid, "template": "cartel"})
    assert "cartel (" not in str(e.value) and "templates:" not in str(e.value)


def test_flags_off_keep_the_template_path():
    inst, k = make("E2", ["law.v2=true", "contracts.enabled=true"])
    out = A.act(k, citizen(k), "create_contract", {"name": "C", "template": "club", "params": {"DUES": 1}})
    assert "(club;" in out
    assert AR.hidden(inst["spec"]) == {"read_library"} and not AR.core_only(inst["spec"])


# ---------------------------------------------------------------------- 2. the core action surface
def test_core_surface_is_small_and_registered():
    assert set(AR.CORE_SURFACE) <= set(AR.REG) and len(set(AR.CORE_SURFACE)) == len(AR.CORE_SURFACE)
    assert 25 <= len(AR.CORE_SURFACE) <= 37                             # review 15 S4: conceive (pairs worlds only); review 19: hunt
    for name in ("dm", "post", "transfer", "harvest", "propose", "vote", "create_contract", "join_contract", "leave_contract",
                 "read_law", "manual", "write_file", "invoke"):
        assert name in AR.CORE_SURFACE
    for name in ("guard", "contract", "lend", "found", "subscribe", "standing_order", "accuse", "survey", "lease"):
        assert name not in AR.CORE_SURFACE


def test_design_arm_agents_see_and_use_only_the_core(design):
    inst, k = design
    for a in inst["agents"]:
        allowed = CX.allowed_actions(inst, a, k.w["agents"][a["id"]]["rights"], k)
        core = set(AR.core_surface(inst["spec"]))                         # plus guard/join_attack where conflict is on, channel verbs
        assert set(allowed) <= core, set(allowed) - core
    a = next(x for x in inst["agents"] if x["cls"] == "worker")
    assert len(CX.allowed_actions(inst, a, k.w["agents"][a["id"]]["rights"], k)) <= 32   # guard, join_attack where conflict is on
    inst2, k2 = make("design_arm")
    with pytest.raises(A.ActionError, match="unknown action 'guard'") as e:
        A.act(k2, citizen(k2), "guard", {"agent": citizen(k2)})
    listed = str(e.value).split("Actions: ", 1)[1].split(", ")
    assert set(listed) <= set(AR.CORE_SURFACE)


def test_design_arm_has_only_citizens_and_the_fixer(design):
    inst, _ = design
    assert {a["cls"] for a in inst["agents"]} == {"worker", "fixer"}
    vote = [a["id"] for a in inst["agents"] if a["cls"] == "worker"]
    assert vote and all("propose" in a["rights"] for a in inst["agents"] if a["cls"] == "worker")


# ---------------------------------------------------------------------- 3. outcome-only goals
def test_every_goal_is_classified():
    every = set(GR.GOALS) | set(GR.INSTITUTION)
    assert set(GR.GOAL_CLASS) == every
    assert set(GR.GOAL_CLASS.values()) == {"outcome", "institution", "recipe", "relational"}
    assert set(GR.INSTITUTION) <= {g for g, c in GR.GOAL_CLASS.items() if c == "institution"}
    for g in ("Wealth", "Rank", "Safety", "Power", "Following", "Dynasty", "Lineage Wealth"):
        assert g in GR.OUTCOME_GOALS
    for g in ("Enact", "Lawmaker", "Revolutionary", "Creditor", "Company", "Eliminator", "Leaker", "Office", "Seat"):
        assert g not in GR.OUTCOME_GOALS


def test_outcome_only_weights_and_draws():
    sp = S.load("design_arm")
    w = G.weights(sp["goals"], "worker", spec=sp)
    assert {g for g, x in w.items() if x > 0} <= GR.OUTCOME_GOALS and sum(w.values()) > 0
    for seed in (1, 2, 3):
        inst = generator.generate(S.load("design_arm"), seed)
        for a in inst["agents"]:
            g = a["goal"]
            if g.get("fixed"):
                continue
            for slot in ("primary", "secondary", "tertiary"):
                assert g.get(slot) in (None, *GR.OUTCOME_GOALS), (seed, a["id"], slot, g.get(slot))
        assert not inst["counter_goals"]
    drawn = set()
    for seed in (1, 2, 3):
        inst = generator.generate(S.load("scaffolded_arm"), seed)
        drawn |= {a["goal"][s] for a in inst["agents"] for s in ("primary", "secondary", "tertiary") if a["goal"].get(s)}
    assert drawn - GR.OUTCOME_GOALS                                     # the scaffolded arm still draws the rest


# ---------------------------------------------------------------------- 4. library visibility
def _lib_section(inst, k, aid):
    return dict(CX.build_manual(inst, k, aid)).get("Law library")


def test_library_visibility_modes():
    inst, k = make("E2", ["law.v2=true"])
    aid = citizen(k)
    full = _lib_section(inst, k, aid)
    assert full and "Library" in full and "read_library" not in [x.name for x in AR.available(inst, k, k.w["agents"][aid])]
    with pytest.raises(A.ActionError, match="unknown action 'read_library'"):
        A.act(k, aid, "read_library", {})

    inst, k = make("E2", ["law.v2=true", "law.library.visibility=none"])
    aid = citizen(k)
    assert _lib_section(inst, k, aid) is None
    assert "read_library" not in CX.core_prompt(inst, inst["agents"][0], k)
    with pytest.raises(A.ActionError, match="unknown action"):
        A.act(k, aid, "read_library", {})

    inst, k = make("E2", ["law.v2=true", "law.library.visibility=on_request"])
    aid = citizen(k)
    a = next(x for x in inst["agents"] if x["id"] == aid)
    assert _lib_section(inst, k, aid) == AG.LIBRARY_ON_REQUEST
    core = CX.core_prompt(inst, a, k)
    assert "read_library" in core and "(pre-action)" not in core.split("read_library", 1)[1].split(";", 1)[0]
    assert not AR.REG["read_library"].pre                                # it uses an action
    idx = A.act(k, aid, "read_library", {})
    name = inst["library"][0]
    assert name in idx and "def " not in idx
    one = A.act(k, aid, "read_library", {"name": name})
    assert LB.code(name, inst).strip().splitlines()[0] in one
    assert any(e["type"] == "library_lookup" and e["agent"] == aid for e in k.events)


# ---------------------------------------------------------------------- 5. the presets
def _diff(a, b, path=()):
    if isinstance(a, dict) and isinstance(b, dict):
        out = set()
        for key in set(a) | set(b):
            out |= _diff(a.get(key), b.get(key), path + (key,))
        return out
    return set() if a == b else {path}


def test_arm_presets_differ_only_in_the_design_flags_and_classes():
    d, s = S.load("design_arm"), S.load("scaffolded_arm")
    diff = _diff(d, s)
    assert {p for p in diff if p[0] != "agents"} == FLAGS
    assert schema.validate(d) == [] and schema.validate(s) == []
    for sp in (d, s):
        assert sp["rounds"] == 25 and sum(sp["agents"].values()) == 30
        assert sp["models"]["mix"] == "all_weak" and set(sp["models"]["pool"].values()) == {"claude-haiku-5-5"}
        assert sp["law"]["v2"] and sp["law"]["publication"] and sp["law"]["digest"]
        assert sp["contracts"]["enabled"] and sp["code"]["enabled"] and sp["observer"]["enabled"]
        assert sp["shared_archive"]["enabled"] is False
    assert d["agents"]["board"] == d["agents"]["legislator"] == d["agents"]["scientist"] == d["agents"]["media"] == 0


# ---------------------------------------------------------------------- 6. novelty
def test_novelty_known_template_code_against_novel_code():
    club = CT.TEMPLATES["club"]["code"]
    near = NV.nearest(CT.instantiate(club, {}))
    assert near["copy"] and near["ref"] == "template:club" and NV.classify(near) == "copy"
    adapted = NV.nearest(CT.instantiate(club, {"DUES": 3, "ITEM": "timber"}))
    assert not adapted["copy"] and adapted["similarity"] >= 0.99 and NV.classify(adapted) == "adaptation"
    renamed = LB.code("Scrip").replace("scrip", "token").replace('"Scrip"', '"Token Act"')
    assert NV.nearest(renamed)["similarity"] >= 0.99
    own = NV.nearest(CT.SCRIPTED_OWN_CODE)
    assert own["similarity"] < NV.THRESHOLD and NV.classify(own) == "novel"
    assert NV.similarity(club, club) == 1.0 and NV.similarity(club, CT.SCRIPTED_OWN_CODE) < 0.5
    assert NV.tokens("def broken(:") == ()
    assert len(NV.clusters([club, CT.instantiate(club, {"DUES": 2}), CT.SCRIPTED_OWN_CODE])) == 2


def test_novelty_on_a_scripted_design_arm_run(tmp_path):
    from charter import runner
    inst = generator.generate(S.apply_overrides(S.load("design_arm"), ["rounds=4"]), 1)
    out = runner.run(inst, AG.ScriptedPolicy(1), tmp_path / "run", log=lambda *x: None, publish_archive=False)
    res = NV.analyse(out)
    s = res["summary"]
    assert s["institutions"] >= 4 and s["institutions_from_templates"] == 0     # code only: none founded by template name
    assert s["laws"] >= 4 and s["novel"] + s["no_effect"] >= 1 and s["adaptations"] >= 3
    assert s["novel_institutions"] >= 1 and s["novel_institution_share"] < 1
    assert s["distinct_institution_designs"] >= 4
    own = next(r for r in res["laws"] if r["title"] == "Mutual Watch")
    assert own["similarity"] < NV.THRESHOLD                             # novel code; enacted late in 4 rounds, it may do nothing yet
    assert own["class"] == ("novel" if own["effect"] else "no_effect")       # (W9: no_effect)
    assert {r["nearest"] for r in res["laws"] if r["class"] == "adaptation"} >= {"template:club", "template:cartel"}
    assert NV.cmd(type("a", (), {"runs": [str(out)], "threshold": 0.8, "json": None})()) == 0
    assert json.loads((out / "novelty.json").read_text())["summary"] == s
