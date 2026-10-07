"""The rights registry (charter/rights.py) and the bugs it fixes: the secret Spy hidden from the law API, manual docs for role
rights, and one Maker check for the prompt and the execution. No model calls."""
from __future__ import annotations

import pytest

from charter import action_registry as AR
from charter import actions as A
from charter import generator, roles as R
from charter import kernel as KN
from charter import lawlang as L
from charter import life as LF
from charter import manual as M
from charter import rights as RT
from charter import spec as S
from charter.kernel import Kernel

AG28 = "agents={worker: 12, scientist: 6, legislator: 5, media: 1, board: 3, fixer: 1}"


def _gen(seed, *sets, preset="E6"):
    return generator.generate(S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", *sets]), seed)


def _roles_world(seed=7, *sets):
    inst = _gen(seed, AG28, "roles.enabled=true", *sets)
    assert inst["roles"]["mode"] == "member"
    return inst, Kernel(inst)


# ------------------------------------------------------------------ the secret Spy and the law API
def test_law_api_does_not_expose_the_member_spy():
    inst, k = _roles_world()
    spy = R.holders(k, "spy")[0]
    assert k.has(spy, "impersonate")                                           # the kernel itself still knows
    api = k.api_for("L1")
    assert api["holders"]("impersonate") == []
    assert api["holders"]("Impersonate") == []
    assert api["holders"]("forge") == []                                       # the old name, too
    assert "impersonate" not in api["rights_of"](spy)
    assert not api["has"](spy, "impersonate")
    assert not api["has"](spy, "forge")
    assert all(r in api["rights_of"](spy) for r in k.w["agents"][spy]["rights"] if r != "impersonate")
    other = next(a for a in k.players() if k.has(a, "vote"))
    assert other in api["holders"]("vote") and api["has"](other, "vote")       # ordinary rights are still visible


def test_laws_cannot_grant_revoke_suspend_or_create_role_rights():
    inst, k = _roles_world()
    spy = R.holders(k, "spy")[0]
    other = next(a for a in k.players() if a != spy and k.cls_of(a) not in ("board", "fixer"))
    api = k.api_for("L1")
    n0 = len(k.events)
    for who in (spy, other):                                                   # refused whoever holds it: the answer leaks nothing
        assert api["grant"](who, "impersonate") is False
        assert api["revoke"](who, "impersonate") is False
        assert api["suspend"](who, "impersonate", 3) is False
        assert api["grant"](who, "forge") is False
    assert k.has(spy, "impersonate") and not k.has(other, "impersonate")
    assert not [e for e in k.events[n0:] if e["vis"] != "monitor"]             # no public rights or sanction event
    for name in ("impersonate", "forge", "maker", "scholar"):
        with pytest.raises(L.LawError):
            api["create_right"](name)
    with pytest.raises(L.LawError):                                            # a secret right is as good as absent
        api["define_action"]("impersonate", "spy_tool", lambda a: None)
    assert api["create_right"]("treasurer") == "treasurer"                     # laws still create rights
    assert api["grant"](other, "treasurer") and api["has"](other, "treasurer") and other in api["holders"]("treasurer")


def test_secret_harvest_rights_are_hidden_from_laws():
    inst, k = _roles_world()
    a = next(x for x in k.players() if k.cls_of(x) == "worker")
    k.w["camps"]["mere-x"] = {**next(iter(k.w["camps"].values())), "secret": True}
    k.w["rights"] = sorted(k.w["rights"] + ["harvest:mere-x"])
    k.w["agents"][a]["rights"].append("harvest:mere-x")
    api = k.api_for("L1")
    assert api["holders"]("harvest:mere-x") == [] and not api["has"](a, "harvest:mere-x")
    assert "harvest:mere-x" not in api["rights_of"](a)
    public = next(r for r in k.w["rights"] if r.startswith("harvest:") and r != "harvest:mere-x")
    assert RT.is_secret(k, "harvest:mere-x") and not RT.is_secret(k, public)


def test_the_spy_still_forges_and_reads():
    inst, k = _roles_world()
    spy = R.holders(k, "spy")[0]
    a, b = [x for x in k.players() if x != spy][:2]
    k.w["agents"][spy]["holdings"]["copper"] = 3.0
    assert "Message sent" in A.act(k, spy, "forge_dm", {"as": a, "to": b, "text": "hello"})
    assert "forge_dm" in [x.name for x in AR.available(inst, k, k.w["agents"][spy])]
    k.w["round"] = 1
    assert "What you saw" in R.turn_section(k, spy, "")


# ------------------------------------------------------------------ the manual
def test_manual_documents_role_rights():
    inst, k = _roles_world()
    for role, right in (("spy", "impersonate"), ("maker", "maker"), ("scholar", "scholar")):
        aid = R.holders(k, role)[0]
        text = dict(M.sections(inst, k, aid))["Your rights"]
        line = next(x for x in text.splitlines() if x.startswith(f"- {right}:"))
        assert "created by law" not in line and line == f"- {right}: {RT.RIGHT_DOC[right]}"
        text0 = dict(M.sections(inst, None, aid))["Your rights"]               # from the instance alone (the first system prompt)
        assert f"- {right}: {RT.RIGHT_DOC[right]}" in text0


def test_manual_spy_right_only_in_the_spys_manual():
    inst, k = _roles_world()
    spy = R.holders(k, "spy")[0]
    for a in k.players():
        assert ("- impersonate:" in dict(M.sections(inst, k, a))["Your rights"]) == (a == spy)


def test_manual_rights_created_by_law_and_unknown_rights():
    inst, k = _roles_world()
    a = next(x for x in k.players() if k.cls_of(x) == "legislator")
    api = k.api_for("L1")
    api["create_right"]("treasurer")
    api["grant"](a, "treasurer")
    assert "- treasurer: a right created by law" in dict(M.sections(inst, k, a))["Your rights"]
    k.w["agents"][a]["rights"].append("nonsense")                              # written past the kernel: fails loudly
    with pytest.raises(RT.UnknownRight):
        M.sections(inst, k, a)


# ------------------------------------------------------------------ the registry
def test_registry_derives_the_old_constants():
    assert KN.KERNEL_RIGHTS == {"vote", "propose", "sandbox", "ledger_read", "surveil", "encrypt", "veto", "patch", "judge", "archive",
                                "press", "see_hidden", "anon", "dm_rules"}
    assert KN.ENTRENCHED == {"veto", "patch", "archive"}
    assert KN.NEVER == {"board": None, "fixer": {"vote", "propose", "veto"}}
    assert Kernel.SECRET_RIGHTS == ("impersonate",)
    assert KN.RENAMED_RIGHTS == {"forge": "impersonate"}
    assert R.RIGHTS == {"scholar": "scholar", "maker": "maker", "media": "press"}
    assert RT.RIGHT_OF_ROLE["spy"] == "impersonate" and RT.ROLE_RIGHTS == {"scholar", "maker", "impersonate"}
    assert set(M.RIGHT_DOC) >= KN.KERNEL_RIGHTS | RT.ROLE_RIGHTS
    assert set(RT.RIGHT_OF_ROLE) <= set(R.ROLES)


def test_registry_lookups_fail_on_unknown_names():
    assert RT.get("forge").name == "impersonate" and RT.get("harvest:camp3").kind == "property"
    assert RT.doc("harvest:camp3") == "harvest at camp3"
    with pytest.raises(RT.UnknownRight):
        RT.get("treasurer")
    with pytest.raises(RT.UnknownRight):
        RT.lookup("treasurer", ["vote"])
    assert RT.lookup("treasurer", ["treasurer"]).origin == "law" and RT.doc("treasurer", ["treasurer"]) == "a right created by law"
    assert RT.get("decree").origin == "law" and "decree" not in KN.KERNEL_RIGHTS


def test_action_registry_rights_are_registered():
    for act in AR.REG.values():
        for r in act.edge_rights + act.edge:
            assert RT.is_registered(r) or r == RT.HARVEST, (act.name, r)


# ------------------------------------------------------------------ the Maker: one check
def _can_make(inst, k, aid):
    return {"create_agent", "copy_agent"} <= {x.name for x in AR.available(inst, k, k.w["agents"][aid])}


def _life_world(*sets):
    sp = S.apply_overrides(S.load("life_pilot"), ["rounds=10", "shared_archive.enabled=false", *sets])
    inst = generator.generate(sp, 3)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return inst, k


@pytest.mark.parametrize("sets", [(), ("roles.enabled=true",)])
def test_maker_prompt_and_execution_agree(sets):
    inst, k = _life_world(*sets)
    maker = LF.living_makers(k)[0]
    other = next(a for a in k.players() if a != maker and k.cls_of(a) not in ("board", "fixer"))
    for a in (maker, other):                                                   # ensure_maker (roles off) or the draw (roles on)
        assert _can_make(inst, k, a) == LF.is_maker(k, a) == (a == maker)
    api = k.api_for("L1")
    if "maker" in k.w["rights"]:
        assert api["grant"](other, "maker") is False and api["revoke"](maker, "maker") is False
        assert api["suspend"](maker, "maker", 5) is False
    for a in (maker, other):
        assert _can_make(inst, k, a) == LF.is_maker(k, a) == (a == maker) == k.has(a, "maker")
    with pytest.raises(L.LawError):
        LF.create_agent(k, other)


def test_ensured_maker_gets_its_right_and_the_manual_says_so():
    inst, k = _life_world()
    assert not inst.get("roles")
    maker = LF.living_makers(k)[0]
    assert "maker" in k.w["agents"][maker]["rights"]
    assert f"- maker: {RT.RIGHT_DOC['maker']}" in dict(M.sections(inst, k, maker))["Your rights"]


def test_law_holders_never_name_the_secret_observer():
    inst = _gen(7, "observer.enabled=true")
    k = Kernel(inst)
    obs = next(a for a, v in k.w["agents"].items() if v["cls"] == "observer")
    k.w["agents"][obs]["rights"].append("vote")                                # however it came to hold one
    assert obs in k.holders("vote")                                            # the kernel knows
    assert obs not in k.api_for("L1")["holders"]("vote")                       # laws do not


def test_regimes_take_entrenched_and_fixer_rights_from_the_registry():
    from charter import regimes as RG
    assert RG.ENTRENCHED == RT.ENTRENCHED and RG.FIXER_NEVER == RT.NEVER["fixer"]
