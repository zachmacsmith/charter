"""Prompts are efficient and deliberately unequal: each agent gets what it needs to act, not to understand everything.

Checked on a world with every New Features module on (specs/society.yaml):
- the core prompt fits its budget and always carries who the agent is, its goal, its actions and the reply format;
- an agent sees only the actions it can use (editors', Scholars' and the Maker's tools, veto, patch and name_successor only for them);
- camps are described by their interface only: how they pay is never stated (that is in a Scientist-only archive document);
- knowledge is uneven on purpose: required archive documents are held by at least one Scientist and by nobody else;
- secret roles appear only in their holder's prompt.
"""
from __future__ import annotations

import re

import pytest

from charter import context as CX
from charter import generator, manual as MN, media as MD
from charter import spec as S
from charter.camptypes import framework as CT
from charter.kernel import Kernel

MECHANICS = ("lowest", "fewer agents", "less crowded", "sha-256", "hash", "least squares", "faulty", "weights", "dot product",
             "times its weight", "falls as the total", "both share", "the taker", "fraction of the average", "redrawn", "crowd")


@pytest.fixture(scope="module")
def world():
    inst = generator.generate(S.load("society"), 5)
    return inst, Kernel(inst)


def _actions_line(p: str) -> str:
    return next(l for l in p.splitlines() if l.startswith("Actions ("))


def test_core_prompts_fit_and_carry_the_agent(world):
    inst, k = world
    budget = int(CX.cfg(inst)["budgets"]["core"])
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k)
        assert CX.tokens(p) <= budget, (a["id"], CX.tokens(p))
        assert f"You are {a['id']}" in p and "Your private goal" in p and "Reply with a JSON object" in p
        assert re.search(r"\bpost\b", _actions_line(p)) and re.search(r"\bdm\b", _actions_line(p))


def test_agents_see_only_actions_they_can_use(world):
    inst, k = world
    for a in inst["agents"]:
        acts = set(re.findall(r"[a-z_]+", _actions_line(CX.core_prompt(inst, a, k)).split(":", 1)[1]))
        rights = k.w["agents"][a["id"]]["rights"]
        if not MD.inst_editor(inst, a):
            assert not acts & set(MD.EDITOR_ACTIONS), a["id"]
        if not MD.inst_scholar(inst, a):
            assert not acts & set(MD.SCHOLAR_ACTIONS), a["id"]
        if "maker" not in rights:
            assert not acts & {"create_agent", "copy_agent"}, a["id"]
        if a["cls"] != "board":
            assert not acts & {"veto", "name_successor"}, a["id"]
        if a["cls"] != "fixer":
            assert "patch" not in acts, a["id"]


def test_camps_are_described_by_their_interface_only(world):
    inst, k = world
    texts = [CX.overview(inst), CT.rules_text(inst)] + [CT.view(k, c, fresh=False).describe(inst) for c in k.w["camps"]
                                                         if k.w["camps"][c].get("type")]
    for t in texts:
        low = t.lower()
        for word in MECHANICS:
            assert word not in low, (word, t[:200])


def test_required_documents_reach_a_scientist_and_nobody_else(world):
    inst, k = world
    req = inst["spec"]["archive_split"]["required"]
    scis = [a for a in inst["agents"] if a["cls"] == "scientist"]
    for doc in req:
        assert any(doc in (a.get("archive_docs") or []) for a in scis), doc
    for a in inst["agents"]:
        if a["cls"] == "scientist":
            continue
        assert not set(req) & set(a.get("archive_docs") or [])
        text = " ".join(t for _, t in MN.sections(inst, k, a["id"])).lower()
        assert "sha-256" not in text and "least squares" not in text, a["id"]       # camp mechanics stay with the Scientists


def test_required_document_is_guaranteed_across_seeds():
    for seed in range(1, 8):
        inst = generator.generate(S.load("society"), seed)
        holders = [a["id"] for a in inst["agents"] if "math/camp-mechanics" in (a.get("archive_docs") or [])]
        assert holders and all(next(x for x in inst["agents"] if x["id"] == h)["cls"] == "scientist" for h in holders)


def test_manuals_differ_by_role(world):
    inst, k = world
    titles = {a["id"]: [t for t, _ in MN.sections(inst, k, a["id"])] for a in inst["agents"]}
    for a in inst["agents"]:
        has_archive = "Your archive" in titles[a["id"]]
        assert has_archive == (a["cls"] == "scientist"), a["id"]
    assert len({tuple(t) for t in titles.values()}) > 3                     # not one manual for everyone


def test_secret_roles_only_in_their_holders_prompt(world):
    inst, k = world
    secret = {r: hs for r, hs in (k.w.get("roles") or {}).items() if r in ("assassin", "seer")}
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k).lower()
        for role, hs in secret.items():
            if a["id"] not in hs:
                assert f"secretly hold the {role}" not in p and f"you are the {role}" not in p, (a["id"], role)


def test_every_non_rare_document_reaches_some_scientist(world):
    from charter import archive as A
    inst, _ = world
    held = {d for a in inst["agents"] if a["cls"] == "scientist" for d in a.get("archive_docs") or []}
    assert not {d for d in A.docs(None) if not d.startswith("rare/")} - held     # only rare records may go unheld


def test_prompts_do_not_contradict_the_rules(world):
    inst, k = world
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k)
        assert "cannot harvest" not in p                                # Scientists can harvest at open camps or with a granted right
        assert "each read or search uses an action" not in p          # reading a held document is free
        assert "posting needs a licence" not in p                       # everyone starts licensed
        if a["cls"] == "scientist":
            assert "secrets and strategy" in p


def test_every_prompt_states_its_leverage_per_class_and_role(world):
    inst, k = world
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k)
        line = next(l for l in p.splitlines() if l.startswith("Your leverage: "))
        assert CX.LEVERAGE_CLASS[a["cls"]] in line, a["id"]
        for r in CX.own_roles(k, a["id"]):
            assert CX.LEVERAGE_ROLE[r] in line, (a["id"], r)
        for r in set(CX.LEVERAGE_ROLE) - set(CX.own_roles(k, a["id"])):
            assert CX.LEVERAGE_ROLE[r] not in p, (a["id"], r)               # nobody is told another's (secret) edge


def test_actions_and_camp_args_match_what_each_agent_can_do(world):
    inst, k = world
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k)
        acts = set(re.findall(r"[a-z_]+", _actions_line(p).split(":", 1)[1]))
        if "sandbox" not in k.w["agents"][a["id"]]["rights"]:
            assert "run_python" not in acts, a["id"]
        if a["cls"] in ("board", "fixer"):
            assert "harvest" not in acts, a["id"]
        assert "camp5 stone (open to all but the Board and Fixer; choose 0 or 1, sealed; harvest args x: 0..1)" in p
        assert "harvest args factor" in p                                   # the vault takes only a factor


def test_everyone_is_told_why_children_matter_and_how_to_make_them(world):
    inst, k = world
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k)
        assert "scored at the end of the game whether or not" in p and "Anyone can pay a Maker to make a new agent" in p, a["id"]


def test_heir_reminder_in_the_last_rounds(world):
    from charter import life as LF
    inst, k = world
    aid = next(a["id"] for a in inst["agents"] if a["cls"] == "worker")
    st = LF.state(k)
    keep = st["dies_at"][aid]
    try:
        st["dies_at"][aid] = k.r + 5
        assert not any(l.startswith("Reminder: you leave") for l in LF.state_lines(k, aid))
        st["dies_at"][aid] = k.r + 2
        lines = [l for l in LF.state_lines(k, aid) if l.startswith("Reminder: you leave")]
        assert lines and "You have no heir yet" in lines[0]
    finally:
        st["dies_at"][aid] = keep


def test_life_rules_are_in_everyones_manual(world):
    inst, k = world
    for a in inst["agents"]:
        secs = dict(MN.sections(inst, k, a["id"]))
        assert "Life and children" in secs and "commission a new agent" in secs["Life and children"], a["id"]


def test_camp_line_names_harvest_inputs():
    inst = generator.generate(S.load("society"), 37)
    k = Kernel(inst)
    p = CX.core_prompt(inst, inst["agents"][0], k)
    assert "each harvest uses 1 copper" in p
