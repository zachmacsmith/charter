"""Legal-system bug fixes (docs/ARCHITECTURE.md P1.4; docs/review/09_law_composition.md F1; decision D-3): a law calling repeal is
structural and cannot repeal a law of a stricter class; set_official_editor only appoints members; ban_forging(on=...); the media2
archive split and start_laws respect which modules are on."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from charter import archive
from charter import generator
from charter import lawapi as LA
from charter import lawlang as L
from charter import library as LB
from charter import media as MD
from charter import regimes as RG
from charter import spec as S
from charter.kernel import Kernel

sys.path.insert(0, str(Path(__file__).parent))


def code(title, body):
    return f'title = "{title}"\nintent = "test"\n\n{body}\n'


def _world(preset="E4", extra=()):
    inst = generator.generate(S.apply_overrides(S.load(preset), ["rounds=3", "shared_archive.enabled=false", *extra]), 1)
    k = Kernel(inst)
    const = k.new_law(inst["constitution_code"], "constitution")
    k.enact(const)
    k.start_round()
    return inst, k, const


# ------------------------------------------------------------------ F1: repeal is structural; no repeal of a stricter law
REPEAL_AND_GAZETTE = code("Sweep", 'def on_enact():\n    gazette("out with the old")\n    repeal("Constitution: Assembly")')


def test_a_law_calling_repeal_and_anything_else_is_structural():
    assert L.classify(L.check(REPEAL_AND_GAZETTE)) == "structural"
    assert "repeal" in L.STRUCTURAL_CALLS and LA.LAWFNS["repeal"].cls == "structural"
    assert L.is_repeal(L.check(REPEAL_AND_GAZETTE)) is None              # not a pure repeal: it does not take the target's class


def test_a_pure_repeal_law_still_takes_its_targets_class():
    _, k, _ = _world()
    target = k.new_law(code("Small Rule", 'def on_round_end(r):\n    gazette("hi")'), "constitution")
    k.enact(target)
    assert k.w["laws"][target]["cls"] == "ordinary"
    from charter import actions as A
    proposer = next(a for a in k.roster() if k.has(a, "propose"))
    A.act(k, proposer, "propose", {"code": code("Undo", 'repeal("Small Rule")')})
    rep = max(k.w["laws"], key=lambda x: int(x[1:]))
    assert k.w["laws"][rep]["repeal_target"] == "Small Rule" and k.w["laws"][rep]["cls"] == "ordinary"


def test_an_ordinary_or_structural_law_cannot_repeal_a_procedural_constitution():
    _, k, const = _world()
    assert k.w["laws"][const]["cls"] == "procedural"
    sweep = k.new_law(REPEAL_AND_GAZETTE, "constitution")
    assert k.w["laws"][sweep]["cls"] == "structural"
    k.enact(sweep)
    assert k.w["laws"][const]["status"] == "active"                    # refused: the constitution outranks the sweep
    assert not any(e["type"] == "repeal" and e["data"]["law"] == const for e in k.events)
    k.w["laws"][sweep]["cls"] = "ordinary"                             # a law classified ordinary before the fix: refused too
    assert k.repeal(const, by_law=sweep) is False and k.w["laws"][const]["status"] == "active"


def test_a_law_may_repeal_a_law_of_its_own_or_a_weaker_class():
    _, k, const = _world()
    small = k.new_law(code("Small Rule", 'def on_round_end(r):\n    gazette("hi")'), "constitution")
    k.enact(small)
    sweep = k.new_law(code("Sweep", 'def on_enact():\n    gazette("bye")\n    state["ok"] = repeal("Small Rule")'), "constitution")
    k.enact(sweep)
    assert k.w["laws"][small]["status"] == "repealed" and k.w["laws"][sweep]["state"]["ok"] is True
    assert k.repeal(const) is True                                      # not law-caused (the Board, a test): no class check


def test_no_library_law_or_regime_calls_repeal_so_no_class_changes():
    for name, law in LB.LIB.items():
        assert "repeal" not in L.calls(L.check(law["code"])), name
    for name, src in {**LB.CONSTITUTIONS, **RG.CONSTITUTIONS}.items():
        assert "repeal" not in L.calls(L.check(src)), name


# ------------------------------------------------------------------ D-3: set_official_editor appoints only members
def test_a_jurisdictions_law_cannot_appoint_a_non_member_as_its_editor():
    from test_charter_jurisdictions import citizens, declared, world
    _, k = world(extra=("media2.enabled=true",))
    cs = citizens(k)
    jid = declared(k, cs[0], cs[1])
    outsider = next(a for a in cs if a not in (cs[0], cs[1]))

    def appoint(agent):
        lid = k.new_law(code("Editor " + agent, f'def on_enact():\n    state["r"] = set_official_editor("{agent}", "{jid}")'), cs[0])
        k.w["laws"][lid]["jurisdiction"] = jid
        k.enact(lid)
        return k.w["laws"][lid]["state"]["r"]

    assert appoint(outsider) is False
    assert k.w["media"]["official"][jid]["editor"] is None
    assert any(e["type"] == "jur_out_of_scope" and e["data"].get("fn") == "set_official_editor" for e in k.events)
    assert appoint(cs[1]) is True and k.w["media"]["official"][jid]["editor"] == cs[1]
    assert LA.AGENT_ARGS["set_official_editor"] == ((0, "agent"),) and LA.REFUSED["set_official_editor"] is False


# ------------------------------------------------------------------ ban_forging(on=...)
def test_ban_forging_accepts_on_and_on_():
    from charter import conflict as CF
    _, k, _ = _world("society", ("conflict.enabled=true", "jurisdictions.enabled=false"))
    lid = k.new_law(code("Ban", 'def on_enact():\n    ban_forging(on=False)'), "constitution")
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active" and k.w["conflict"]["forge_ban"][lid] is False
    api = CF.law_api(k, lid)
    api["ban_forging"](on=True)
    assert k.w["conflict"]["forge_ban"][lid] is True
    api["ban_forging"](on_=False)
    assert k.w["conflict"]["forge_ban"][lid] is False
    api["ban_forging"](True)
    assert k.w["conflict"]["forge_ban"][lid] is True


# ------------------------------------------------------------------ media2 archive split: only categories whose module is on
def _gated_library_docs(cat):
    return {"library/" + archive._slug(n) for n, v in LB.LIB.items() if v["category"] == cat}


@pytest.mark.parametrize("on", [(), ("life",), ("conflict",), ("life", "conflict")])
def test_archive_split_hands_out_only_categories_whose_module_is_on(on):
    sp = S.apply_overrides(S.load("media2_pilot"), [f"{m}.enabled={'true' if m in on else 'false'}" for m in ("life", "conflict")])
    scis = [{"id": f"S{i}"} for i in range(4)]
    MD.archive_split(sp, 1, scis)
    got = set().union(*(set(a.get("archive_docs") or []) for a in scis))
    for cat, mod in LB.GATED_CATEGORIES.items():
        docs = _gated_library_docs(cat)
        if mod == "media2" or mod in on:
            assert docs <= got, cat
        else:
            assert not (docs & got), cat


# ------------------------------------------------------------------ start_laws gated by module
@pytest.mark.parametrize("name,mod", [("Arms Control", "conflict"), ("Two Child Limit", "life"), ("Open Board", "media2")])
def test_start_laws_of_a_module_that_is_off_are_rejected(name, mod):
    sp = S.apply_overrides(S.load("E4"), ["rounds=3", "shared_archive.enabled=false", f"start_laws=[{name!r}]".replace("'", '"')])
    with pytest.raises(ValueError, match=f"{name}.*{mod}"):
        generator.generate(sp, 1)


def test_start_laws_of_a_module_that_is_on_are_accepted():
    sp = S.apply_overrides(S.load("society"), ["rounds=3", "shared_archive.enabled=false", "conflict.enabled=true",
                                               "jurisdictions.enabled=false", 'start_laws=["Arms Control"]'])
    inst = generator.generate(sp, 1)
    assert inst["spec"]["start_laws"] == ["Arms Control"]
