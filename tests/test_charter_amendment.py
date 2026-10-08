"""Amendment through the procedure and proposals by law (charter/amendment.py, P3.4; review 09 §7, D-16): the agent action amend,
the law functions propose_law / propose_amendment, the amendment's class over its dependents, the amend primitive via procedure."""
from __future__ import annotations

import pytest

from charter import action_registry as AR
from charter import actions as A
from charter import agents as AG
from charter import dispatch as D
from charter import generator
from charter import linker as LK
from charter import spec as S
from charter.kernel import Kernel


def code(title, body, intent="test"):
    return f'title = "{title}"\nintent = "{intent}"\n{body}\n'


# ordinary laws pass at once; structural and procedural ones go to a ballot of the voters
CONST = code("Constitution", '''rank = "constitution"
def fast(p):
    return True
def slow(p):
    return {"electorate": holders("vote"), "rule": "majority"}
def on_enact():
    set_procedure("ordinary", fast)
    set_procedure("structural", slow)
    set_procedure("procedural", slow)''')

TAX = code("Income Tax", '''exports = ["RATE", "tax_due"]
RATE = 0.10
def tax_due(qty):
    return round_to(qty * RATE, 3)
def on_round_end(r):
    public["rate"] = RATE
    state["n"] = state.get("n", 0) + 1''')


def budget(ref, title="Balanced Budget"):
    return code(title, f'''tax = use("{ref}")
def on_round_end(r):
    public["raised"] = public.get("raised", 0) + tax["tax_due"](100)
    for a in agents("worker"):
        move("reserve", a, "grain", 0)''')


def reader(ref, title="Rate Reader"):
    return code(title, f'tax = use("{ref}")\ndef on_round_end(r):\n    public["rate"] = tax["RATE"]')


def _world(v2=True, preset="E4", const=CONST, extra=()):
    inst = generator.generate(S.apply_overrides(S.load(preset), ["rounds=3", "shared_archive.enabled=false",
                                                                 *(["law.v2=true"] if v2 else []), *extra]), 1)
    k = Kernel(inst)
    c = k.new_law(const, "constitution")
    k.enact(c)
    k.start_round()
    return k


def _law(k, src, author="constitution"):
    lid = k.new_law(src, author)
    k.enact(lid)
    return lid


def _proposer(k):
    return next(a for a, v in k.w["agents"].items() if "propose" in v["rights"])


def _round_end(k):
    with k.cause("kernel", "test", root=True):
        return dict(k.hooks("on_round_end", k.r))


def _vote_through(k, lid, choice="yes"):
    b = next(b for b in k.w["ballots"].values() if b["proposal"] == lid and b["status"] == "open")
    for a in b["electorate"]:
        A.act(k, a, "vote", {"ballot": b["id"], "choice": choice})
    k.w["round"] = b["closes"]
    k.close_ballots()


def _last(k):
    return f"L{k.w['law_seq']}"


# ---------------------------------------------------------------------- the agent action
def test_amend_keeps_id_state_public_order_and_records_the_version():
    k = _world()
    l3 = _law(k, TAX)
    l7 = _law(k, reader(l3))
    _round_end(k)
    law = k.w["laws"][l3]
    v1, order = law["code_sha"], list(k.w["law_order"])
    state, public = law["state"], law["public"]
    assert state == {"n": 1} and public == {"rate": 0.1}
    new = TAX.replace("RATE = 0.10", "RATE = 0.15")
    predicted = LK.preview_amend(k, l3, new)
    out = A.act(k, _proposer(k), "amend", {"law": l3, "code": new, "reason": "a higher rate"})
    draft = _last(k)
    assert f"Proposed {draft}, an amendment of {l3}" in out
    rec = k.w["laws"][draft]
    assert rec["amends"] == l3 and rec["dependents"] == predicted and rec["status"] == "enacted_amendment"   # ordinary: at once
    law = k.w["laws"][l3]
    assert law["code"] == new and law["status"] == "active" and k.w["law_order"] == order and draft not in k.w["law_order"]
    assert law["state"] == {"n": 1} and law["public"] == {"rate": 0.1}       # the dry run worked on a copy; the values stay
    assert k.ns[l3]["state"] is law["state"] and k.ns[l3]["public"] is law["public"]
    assert [v["v"] for v in law["versions"]] == [1, 2] and law["versions"][0]["sha"] == v1
    assert law["versions"][1]["via"] == "procedure" and law["versions"][1]["by"] == _proposer(k)
    assert law["patches"][-1]["via"] == "procedure" and law["patches"][-1]["proposal"] == draft
    ev = [e for e in k.events if e["type"] == "amended"]
    assert ev and ev[-1]["data"]["law"] == l3 and ev[-1]["data"]["proposal"] == draft and ev[-1]["data"]["version"] == 2
    prop = next(e for e in k.events if e["type"] == "proposal" and e["data"]["law"] == draft)
    assert prop["data"]["amends"] == l3 and prop["data"]["reason"] == "a higher rate"
    assert "an amendment of" in AG.render_event(k, prop)
    # the dependent was relinked, as preview_amend predicted
    assert [r["outcome"] for r in predicted] == ["relinked"] and k.w["laws"][l7]["imports"][0]["sha"] == law["code_sha"]
    _round_end(k)
    assert k.w["laws"][l7]["public"]["rate"] == 0.15 and law["state"] == {"n": 2}


def test_amendment_dropping_an_export_auto_pins_the_follower_as_predicted():
    k = _world()
    l3 = _law(k, TAX)
    v1 = k.w["laws"][l3]["code_sha"]
    l7 = _law(k, reader(l3))
    renamed = TAX.replace('exports = ["RATE", "tax_due"]', 'exports = ["tax_due"]')
    A.act(k, _proposer(k), "amend", {"law": l3, "code": renamed, "reason": "hide the rate"})
    rec = k.w["laws"][_last(k)]
    assert [(r["law"], r["outcome"]) for r in rec["dependents"]] == [(l7, "auto_pinned")]
    assert rec["status"] == "enacted_amendment"
    imp = k.w["laws"][l7]["imports"][0]
    assert imp["mode"] == "pinned" and imp["auto"] and imp["sha"] == v1
    _round_end(k)
    assert k.w["laws"][l7]["public"]["rate"] == 0.1


def test_procedure_is_chosen_by_the_highest_class_over_dependents_and_the_board_window_applies():
    k = _world()
    l3 = _law(k, TAX)                                                 # ordinary
    l7 = _law(k, budget(l3))                                          # structural (move), follows L3
    assert k.w["laws"][l3]["cls"] == "ordinary" and k.w["laws"][l7]["cls"] == "structural"
    new = TAX.replace("RATE = 0.10", "RATE = 0.2")
    assert LK.amendment_class(k, l3, new) == "structural"
    A.act(k, _proposer(k), "amend", {"law": l3, "code": new, "reason": "r"})
    draft = _last(k)
    rec = k.w["laws"][draft]
    assert rec["cls"] == "structural" and rec["status"] == "ballot"   # the structural procedure (a ballot), not the ordinary one
    _vote_through(k, draft)
    assert k.w["laws"][draft]["status"] == "veto_window"              # E4's Board reviews non-ordinary laws, amendments too
    assert k.w["laws"][l3]["code"] == TAX
    k.w["round"] += k.spec["veto_window"]
    k.process_veto_queue()
    assert k.w["laws"][draft]["status"] == "enacted_amendment" and k.w["laws"][l3]["code"] == new


def test_board_veto_stops_an_amendment():
    k = _world()
    l3 = _law(k, TAX)
    _law(k, budget(l3))
    A.act(k, _proposer(k), "amend", {"law": l3, "code": TAX.replace("0.10", "0.3"), "reason": "r"})
    draft = _last(k)
    _vote_through(k, draft)
    for m in k.board():
        A.act(k, m, "veto", {"law": draft})
    k.process_veto_queue()
    assert k.w["laws"][draft]["status"] == "vetoed" and k.w["laws"][l3]["code"] == TAX


def test_rank_is_the_maximum_of_target_and_draft():
    k = _world()
    l3 = _law(k, TAX)
    A.act(k, _proposer(k), "amend", {"law": l3, "code": 'rank = "regulation"\n' + TAX.replace("0.10", "0.11"), "reason": "r"})
    assert k.w["laws"][_last(k)]["rank"] == "statute"
    A.act(k, _proposer(k), "amend", {"law": l3, "code": 'rank = "constitution"\n' + TAX.replace("0.10", "0.12"), "reason": "r"})
    draft = _last(k)
    assert k.w["laws"][draft]["rank"] == "constitution" and D.draft(k, draft)["rank"] == "constitution"
    d = D.draft(k, draft)
    assert d["amends"] == l3 and d["exports"] == ["RATE", "tax_due"] and d["imports"] == []


def test_cycle_inducing_amendment_is_refused_at_proposal():
    k = _world()
    l3 = _law(k, TAX)
    l7 = _law(k, code("Relay", f'exports = ["get"]\ntax = use("{l3}")\ndef get():\n    return tax["RATE"]'))
    cyc = TAX.replace('exports = ["RATE", "tax_due"]', f'exports = ["RATE", "tax_due"]\nrelay = use("{l7}")')
    n = k.w["law_seq"]
    with pytest.raises(A.ActionError, match="import cycle"):
        A.act(k, _proposer(k), "amend", {"law": l3, "code": cyc, "reason": "r"})
    assert k.w["law_seq"] == n                                        # refused before any draft was recorded


def test_amend_refusals():
    k = _world()
    l3 = _law(k, TAX)
    aid = _proposer(k)
    with pytest.raises(A.ActionError, match="no law L99 in force"):
        A.act(k, aid, "amend", {"law": "L99", "code": TAX, "reason": "r"})
    with pytest.raises(A.ActionError, match="current code"):
        A.act(k, aid, "amend", {"law": l3, "code": TAX, "reason": "r"})
    with pytest.raises(A.ActionError, match="complete new code"):
        A.act(k, aid, "amend", {"law": l3, "code": "", "reason": "r"})
    worker = next(a for a, v in k.w["agents"].items() if "propose" not in v["rights"] and v["cls"] == "worker")
    with pytest.raises(A.ActionError, match="'propose' right"):
        A.act(k, worker, "amend", {"law": l3, "code": TAX.replace("0.10", "0.2"), "reason": "r"})


def test_before_amend_strikes_an_amendment_down():
    k = _world()
    l3 = _law(k, TAX)
    _law(k, code("Entrench", f'def before_amend(p, chain):\n    if p["law"] == "{l3}":\n        return {{"block": True, "reason": "no"}}'))
    A.act(k, _proposer(k), "amend", {"law": l3, "code": TAX.replace("0.10", "0.2"), "reason": "r"})
    draft = _last(k)
    # the hooking law is procedural, so this ordinary amendment still passes at once; the before_amend block strikes it down
    assert k.w["laws"][draft]["status"] == "struck_down" and k.w["laws"][l3]["code"] == TAX
    assert any(e["type"] == "primitive_blocked" and e["data"]["primitive"] == "amend" for e in k.events)


# ---------------------------------------------------------------------- laws propose laws (D-16)
def test_law_proposes_an_amendment_and_the_procedure_decides_after_the_call():
    k = _world()
    l3 = _law(k, TAX)
    redraft = code("Redraft", f'''rank = "statute"
def on_round_end(r):
    if not state.get("done"):
        state["done"] = True
        state["out"] = propose_amendment("{l3}", NEW, "indexation")''').replace("NEW", repr(TAX.replace("0.10", "0.12")))
    lr = _law(k, redraft)
    assert k.w["laws"][lr]["cls"] == "procedural"                   # propose_amendment is procedural (from L3)
    _round_end(k)
    out = k.w["laws"][lr]["state"]["out"]
    assert out["ok"] is True and out["amends"] == l3
    draft = out["law"]
    rec = k.w["laws"][draft]
    assert rec["author"] == f"law:{lr}" and rec["amends"] == l3
    assert rec["status"] == "enacted_amendment" and "0.12" in k.w["laws"][l3]["code"]   # decided once the cascade drained
    prop = next(e for e in k.events if e["type"] == "proposal" and e["data"]["law"] == draft)
    assert prop["data"]["by_law"] == lr and prop["agent"] is None
    amended = next(e for e in k.events if e["type"] == "amended")
    assert {"law": lr, "hook": "on_round_end"} in amended["cause"]      # the procedure ran in the proposing call's context, after it
    assert k.w["laws"][l3]["versions"][-1]["by"] == f"law:{lr}"


def test_law_proposes_a_law_and_gets_refusals_as_data():
    k = _world()
    l3 = _law(k, code("Supreme", 'rank = "constitution"\nexports = ["X"]\nX = 1'))
    src = code("Proposer", f'''def on_round_end(r):
    state["a"] = propose_law(NEW)
    state["b"] = propose_law(NEW)
    state["c"] = propose_amendment("{l3}", NEW2, "r")
    state["d"] = propose_amendment("L99", NEW, "r")''').replace("NEW2", repr(code("Supreme", 'exports = ["X"]\nX = 2'))) \
        .replace("NEW", repr(code("Child", "x = 1")))
    lp = _law(k, src)
    _round_end(k)
    st = k.w["laws"][lp]["state"]
    assert st["a"]["ok"] and k.w["laws"][st["a"]["law"]]["status"] == "active"           # ordinary: passed at once
    assert k.w["laws"][st["a"]["law"]]["author"] == f"law:{lp}"
    assert not st["b"]["ok"] and "per round" in st["b"]["reason"]
    assert not st["c"]["ok"] and "cannot amend" in st["c"]["reason"]                     # lex superior: a statute, a constitution
    assert not st["d"]["ok"] and "no law L99" in st["d"]["reason"]
    assert k.w["laws"][lp]["status"] == "active"                       # refusals never suspend the proposing law


def test_law_proposals_need_level_l3():
    k = _world(preset="E2")                                            # law level L1
    lp = _law(k, code("Proposer", "def on_round_end(r):\n    state['a'] = propose_law(" + repr(code("Child", "x = 1")) + ")"))
    _round_end(k)
    out = k.w["laws"][lp]["state"]["a"]
    assert not out["ok"] and "L3" in out["reason"]


def test_a_blocked_law_proposal_comes_back_as_a_refusal():
    k = _world()
    _law(k, code("Gate", 'def before_propose(p, chain):\n    if p["draft"]["author"].startswith("law:"):\n'
                         '        return {"block": True, "reason": "laws may not legislate"}'))
    lp = _law(k, code("Proposer", "def on_round_end(r):\n    state['a'] = propose_law(" + repr(code("Child", "x = 1")) + ")"))
    _round_end(k)
    out = k.w["laws"][lp]["state"]["a"]
    assert not out["ok"] and "laws may not legislate" in out["reason"]
    assert k.w["laws"][out["law"]]["status"] == "blocked" and k.w["laws"][lp]["status"] == "active"


# ---------------------------------------------------------------------- law.v2 off: nothing exists
def test_v2_off_amend_is_unknown_and_absent_from_prompts():
    k = _world(v2=False, preset="E4")
    aid = _proposer(k)
    with pytest.raises(A.ActionError, match="unknown action 'amend'") as e:
        A.act(k, aid, "amend", {"law": "L1", "code": TAX, "reason": "r"})
    assert ", amend," not in str(e.value)
    a = next(x for x in k.inst["agents"] if x["id"] == aid)
    assert "amend" not in AG.legacy_actions(k.inst, a)
    assert "amend" not in [x.name for x in AR.available(k.inst, k, a)]
    assert not {"propose_law", "propose_amendment"} & set(k.api_for("L1"))
    kv = _world()
    a2 = next(x for x in kv.inst["agents"] if x["id"] == aid)
    assert "amend" in AG.legacy_actions(kv.inst, a2) and "amend" in [x.name for x in AR.available(kv.inst, kv, a2)]
    assert {"propose_law", "propose_amendment"} <= set(kv.api_for("L1"))
