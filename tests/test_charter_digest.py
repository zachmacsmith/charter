"""The per-agent legal digest (charter/digest.py; review 10 §7 "Comprehension and prompt budget"): the laws that bind an agent,
grouped by what they act on, from static facts only, within a budget; in the core prompt and the legal_position look-up, both only
under law.v2 with law.digest on. Offline: no model calls."""
from __future__ import annotations

import re

import pytest

from charter import actions as A
from charter import context as CX
from charter import digest as DG
from charter import generator
from charter import schema as SCH
from charter import spec as S
from charter.kernel import Kernel

import charter_law_v2_laws as V2

MEMBERS_ONLY = '''title = "Members Only"
intent = "Only guild members may receive transfers."
rank = "constitution"

def before_move(p, chain):
    if p["why"] == "transfer" and p["dst"] not in public.get("guild", []):
        return {"block": True, "reason": "not a guild member"}
'''
DEFINITIONS = '''title = "Definitions"
intent = "Shared definitions."
exports = ["RATE", "adult"]
RATE = 0.03

def adult(a):
    return True
'''
LEGACY = '''title = "Old Customs"
intent = "A tenth of a send is taxed, and loud posters are fined every round."

def on_transfer(src, dst, item, qty):
    return qty / 10

def on_round_end(r):
    for a in agents():
        if balance(a, "timber") > 100:
            fine(a, "timber", 1)
'''


def world(digest=True, v2=True, sets=(), preset="E4", seed=1):
    sp = S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", "context.enabled=true", *sets])
    if v2:
        sp.setdefault("law", {})["v2"] = True
    if digest:
        sp.setdefault("law", {})["digest"] = True
    k = Kernel(generator.generate(sp, seed))
    k.enact(k.new_law(k.inst["constitution_code"], "constitution"))
    return k


def enact(k, code):
    lid = k.new_law(code, "constitution")
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active"
    return lid


def someone(k):
    return next(a for a in k.players() if k.cls_of(a) not in ("board", "fixer"))


def rec(k, aid):
    return next(x for x in k.inst["agents"] if x["id"] == aid)


def seeded(k):
    ids = {n: enact(k, V2.V2_LAWS[n]) for n in ("Transfer Toll", "Harvest Tithe", "Fine Relief")}
    ids["Members Only"] = enact(k, MEMBERS_ONLY)
    ids["Definitions"] = enact(k, DEFINITIONS)
    return ids


def test_off_by_default_and_only_under_law_v2():
    for k in (world(digest=False), world(digest=False, v2=False)):
        a = someone(k)
        p = CX.core_prompt(k.inst, rec(k, a), k)
        assert "Laws that bind you" not in p and "legal_position" not in p
        with pytest.raises(A.ActionError, match="unknown action 'legal_position'"):
            A.act(k, a, "legal_position", {})
    sp = S.apply_overrides(S.load("E4"), ["law.digest=true"])
    assert any("law.digest" in e for e in SCH.validate(sp))           # the digest needs law.v2


def test_a_seeded_world_s_digest_groups_by_family():
    k = world()
    ids = seeded(k)
    text = DG.render(k, someone(k))
    lines = text.splitlines()
    assert lines[0].startswith("Laws that bind you: 6 in force")
    tr = next(l for l in lines if l.startswith("transfers:"))
    mo, tt, fr = ids["Members Only"], ids["Transfer Toll"], ids["Fine Relief"]
    assert tr.index(mo) < tr.index(tt)                                 # canonical order: rank first
    assert f"{mo} 'Members Only' [constitution] may block ('not a guild member') (before_move)" in tr
    assert f"{tt} 'Transfer Toll' may charge 2%" in tr and f"{fr} 'Fine Relief' reacts with move, notify (after_move)" in tr
    assert f"[{mo}, {tt} all gate each move; conflicting verdicts: any_block]" in tr
    assert any(l.startswith("harvests and camps:") and "may charge 5%" in l for l in lines)
    assert any(l.startswith("no hooks") and ids["Definitions"] in l for l in lines)
    assert f"{ids['Definitions']} exports RATE, adult" in text
    assert DG.render(k, someone(k)) == text                            # deterministic


def test_legacy_and_round_hooks():
    k = world()
    lid = enact(k, LEGACY)
    text = DG.render(k, someone(k))
    assert f"transfers: {lid} 'Old Customs' may charge 10% (on_transfer)" in text
    assert f"every round: {lid} 'Old Customs' (on_round_end: fine)" in text


def test_the_budget_holds_and_the_look_up_has_more_room():
    k = world(sets=())
    k.inst["spec"]["law"]["digest_tokens"] = 60
    for i in range(12):
        enact(k, MEMBERS_ONLY.replace("Members Only", f"Members Only {i}"))
    a = someone(k)
    short = DG.render(k, a)
    assert CX.tokens(short) <= 60 + 15 and "the legal_position look-up" in short
    long = A.act(k, a, "legal_position", {})
    assert long.startswith("Your legal position:") and CX.tokens(long) > CX.tokens(short)


def test_in_the_core_prompt_and_as_a_look_up():
    k = world()
    seeded(k)
    a = someone(k)
    p = CX.core_prompt(k.inst, rec(k, a), k)
    assert "Laws that bind you: 6 in force" in p and "legal_position" in p
    assert p.index("Laws that bind you") > p.index("Charter:")         # after the overview
    assert CX.lookup(k, a, "legal_position", {}).startswith("Your legal position:")


def _juris():
    sp = S.apply_overrides(S.load("jurisdictions_pilot"), ["rounds=6", "shared_archive.enabled=false", "hidden.enabled=false",
                                                           "turns=sequential", "jurisdictions.start=j0"])
    sp.setdefault("law", {}).update({"v2": True, "digest": True})
    k = Kernel(generator.generate(sp, 1))
    k.enact(k.new_law(k.inst["constitution_code"], "constitution"))
    k.start_round()
    return k


def test_hidden_jurisdictions_laws_are_not_shown_to_non_members():
    k = _juris()
    a, b, c = [x for x in k.roster() if k.w["agents"][x]["cls"] not in ("board", "fixer")][:3]
    jid = re.search(r"J\d+", A.act(k, a, "found", {"name": "Cabal"})).group()
    A.act(k, a, "invite", {"jurisdiction": jid, "agent": b})
    A.act(k, b, "join", {"jurisdiction": jid})
    lid = k.new_law(MEMBERS_ONLY.replace("Members Only", "Cabal Toll"), "constitution")
    k.w["laws"][lid]["jurisdiction"] = jid
    k.w["laws"][lid]["status"] = "active"                              # adversarial: even a law of it in force
    k.w["law_order"].append(lid)
    for x in (a, b):
        t = DG.render(k, x)
        assert "Cabal Toll" not in t and f"your hidden jurisdiction {jid} has 1 law(s)" in t
    t = DG.render(k, c)
    assert "Cabal Toll" not in t and jid not in t and lid not in t
    assert "Cabal" not in CX.core_prompt(k.inst, rec(k, c), k)


def test_static_facts():
    st = DG.static('title = "T"\nintent = "i"\n\ndef before_harvest(p, chain):\n    return p["qty"] / 20\n'
                   'def before_post(p, chain):\n    return False\n'
                   'def after_end_life(p, chain):\n    gazette("x")\n    move("reserve", "a", "grain", 1)\n')
    h = st["hooks"]
    assert h["before_harvest"]["charge"] == "may charge 5%" and h["before_post"]["block"] == "block"
    assert h["after_end_life"]["does"] == ["gazette", "move"] and h["after_end_life"]["phase"] == "after"
    assert DG.static("def broken(:\n") == {"hooks": {}, "exports": [], "imports": []}


def test_hooks_are_indexed_by_name():
    """dispatch.hooked: False only when every active law is loaded and none defines the hook (review 10 §7)."""
    from charter import dispatch as D
    k = world(digest=False)
    for lid in [l["id"] for l in k.active_laws()]:
        k.ns.get(lid) or k._load(lid)
    assert not D.hooked(k, "before_move") and not D.hooked(k, "after_post")
    lid = enact(k, V2.V2_LAWS["Transfer Toll"])
    k.ns.get(lid) or k._load(lid)
    assert D.hooked(k, "before_move") and not D.hooked(k, "after_post")
    k.repeal(lid)
    assert not D.hooked(k, "before_move")
