"""The power table (charter/powers.py, P4.2): every law function's power exists, J0 holds every power it uses, a declared
jurisdiction lacks the J0-only ones, and the kernel's branches it replaced read it."""
from __future__ import annotations

import re

import pytest

from charter import actions as A
from charter import generator
from charter import jurisdictions as J
from charter import lawapi as LA
from charter import lawlang as LL
from charter import powers as P
from charter import spec as S
from charter.kernel import Kernel


def _world(preset="jurisdictions_pilot", extra=()):
    sp = S.apply_overrides(S.load(preset), ["rounds=4", "shared_archive.enabled=false", "hidden.enabled=false", "turns=sequential",
                                            *extra])
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    return inst, k


def _declare(k, founder):
    jid = re.search(r"J\d+", A.act(k, founder, "found", {"name": "Free Camp"})).group()
    A.act(k, founder, "declare", {"jurisdiction": jid})
    k.end_round()
    k.start_round()
    return jid


def _citizens(k):
    return [a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer")]


def test_every_law_function_power_exists_and_the_reverse_index_agrees():
    for f in LA.LAWFNS.values():
        assert f.power is None or f.power in P.POWERS, f
    for n, p in P.POWERS.items():
        assert set(p.lawfns) == {f.name for f in LA.LAWFNS.values() if f.power == n}, n
        assert p.refusal or not p.lawfns, n                              # a power gating functions says how it refuses
    assert LA.LEGACY_ONLY == set(P.POWERS["legacy_reserve"].lawfns)
    assert LA.POWER_OF == {f.name: f.power for f in LA.LAWFNS.values() if f.power}
    assert all(f.legacy_only == (f.power == "legacy_reserve") for f in LA.LAWFNS.values())


def test_level_presets_are_the_law_levels():
    assert {n: set(v["classes"]) for n, v in P.LEVEL_PRESETS.items()} == LL.LEVEL_CLASSES
    assert [n for n, v in P.LEVEL_PRESETS.items() if v["define_action"]] == ["L4"]
    assert {f.min_level for f in LA.LAWFNS.values() if f.name in LL.L4_CALLS} == {"L4"}


def test_j0_holds_every_power_it_uses_today_with_jurisdictions_off():
    inst, k = _world("E4")
    assert "jurisdictions" not in k.w
    ps = P.power_set(k, "J0")
    assert ps.pop("law_levels") == inst["law_level"]
    assert all(v is True for v in ps.values()), ps


def test_j0_and_a_declared_jurisdiction():
    inst, k = _world()
    j0 = P.power_set(k, "J0")
    assert j0.pop("law_levels") == inst["law_level"] and all(v is True for v in j0.values()), j0
    jid = _declare(k, _citizens(k)[0])
    j1 = P.power_set(k, jid)
    lacks = {n for n, v in j1.items() if not v}
    assert lacks == set(P.J0_ONLY) | {"board_veto"}                   # board_scope founding: the Board reviews J0 only
    assert set(P.J0_ONLY) == {"legacy_reserve", "propose_right"}
    assert j1["law_levels"] == inst["law_level"]
    assert J.board_reviews(k, "J0") and not J.board_reviews(k, jid)
    for name in P.POWERS["legacy_reserve"].lawfns:                    # scope_api refuses them, with the old message
        k.w["laws"]["Lx"] = {"jurisdiction": jid}
        api = J.scope_api(k, "Lx", {**k.api_for("Lx"), name: lambda *a, **kw: "ran"})
        with pytest.raises(LL.LawError, match=f"{name} works only in the founding jurisdiction J0"):
            api[name]()
        del k.w["laws"]["Lx"]


@pytest.mark.parametrize("scope", ["founding", "all", "none"])
def test_board_veto_follows_board_scope(scope):
    inst, k = _world(extra=[f"jurisdictions.board_scope={scope}"])
    jid = _declare(k, _citizens(k)[0])
    assert P.has_power(k, "J0", "board_veto") == (scope != "none")
    assert P.has_power(k, jid, "board_veto") == (scope == "all")
    assert P.has_power(k, None, "board_veto") == (scope == "all")    # as J.board_reviews(k, None) always was


def test_state_of_nature_founding_polity_has_the_board_but_not_j0s_reserve():
    inst, k = _world(extra=["jurisdictions.start=nature"])
    assert not P.has_power(k, "J0", "legacy_reserve") and not P.has_power(k, "J0", "propose_right")
    jid = _declare(k, _citizens(k)[0])
    assert k.w["jur"]["founding"] == jid
    assert P.has_power(k, jid, "board_veto") and not P.has_power(k, jid, "legacy_reserve")


def test_overrides_and_entrenchment():
    inst, k = _world()
    jid = _declare(k, _citizens(k)[0])
    k.w["jurisdictions"][jid]["powers"] = {"camp_rules": False, "legacy_reserve": True}
    assert not P.has_power(k, jid, "camp_rules") and P.has_power(k, jid, "legacy_reserve")
    k.w["jurisdictions"]["J0"]["powers"] = {"board_veto": False, "fixer_patch": False}
    assert P.has_power(k, "J0", "board_veto") and P.has_power(k, "J0", "fixer_patch")   # entrenched: an override cannot remove them
    with pytest.raises(KeyError):
        P.has_power(k, "J0", "no_such_power")


def test_remaining_branches_are_documented():
    assert P.REMAINING and all(isinstance(v, str) and v for v in P.REMAINING.values())
    for p in P.POWERS.values():
        for site in p.consulted:
            f, fn = site.split(":")
            src = open(f"{P.__file__.rsplit('/', 1)[0]}/{f}").read()
            assert fn.split(".")[-1] in src, site
