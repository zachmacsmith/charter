"""W7e: wave-6 follow-ups under law.v2 (and contracts): a law's validity window shown to agents and reviewers, an after-hook's
refusal told to the acting agent, law helpers is_number / is_text, court-rule follow-ups (appellate rule, a cap on rulings), stage
plans for contracts' own procedures and in the jurisdiction probes, history() filtered by agents named in event data, an
association's law reading its members-only record, context's lookup error path, breach victims, and the enforcement seams of review
11 §4 (case source, law_can_see). Offline: no model calls."""
from __future__ import annotations

import copy
import re

import pytest

from charter import actions as A
from charter import agents as AG
from charter import context as CX
from charter import dispatch as D
from charter import generator
from charter import lawpreview as LP
from charter import spec as S
from charter.kernel import Kernel

_INST: dict = {}


def world(v2=True, sets=(), preset="E4"):
    key = (v2, preset, tuple(sets))
    if key not in _INST:
        sp = S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", *(["law.v2=true"] if v2 else []), *sets])
        _INST[key] = generator.generate(sp, 1)
    inst = copy.deepcopy(_INST[key])
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return k


def enact(k, code):
    lid = k.new_law(code, "constitution")
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active", k.w["laws"][lid]
    return lid


def law(title, body):
    return f'title = "{title}"\nintent = "test"\n' + body


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def agents(k, n=3):
    return [a for a in k.roster() if k.cls_of(a) not in ("board", "fixer")][:n]


# ====================================================================== 2. W6a: windows shown; after-hook refusals told
WINDOWED = law("Sunset", "in_force_from = 2\nin_force_until = 5\ndef on_round_end(r):\n    pass\n")


def test_the_draft_carries_the_window_under_v2_only():
    k = world()
    lid = k.new_law(WINDOWED, "a")
    d = D.draft(k, lid)
    assert (d["in_force_from"], d["in_force_until"]) == (2, 5)
    plain = k.new_law(law("Plain", "x = 1\n"), "a")
    assert (D.draft(k, plain)["in_force_from"], D.draft(k, plain)["in_force_until"]) == (None, None)
    k1 = world(v2=False)
    assert "in_force_from" not in D.draft(k1, k1.new_law(WINDOWED, "a"))


def test_agents_see_the_window_in_the_law_list_and_read_law():
    k = world()
    lid = enact(k, WINDOWED)
    a = agents(k)[0]
    note = D.window_note(k, lid)
    assert note == " [in force while round() is 2-5; out of force now]" and k.r < 2
    assert f"'Sunset' (" in AG.state_view(k, a) and note in AG.state_view(k, a)
    assert note in CX.read_law(k, a, lid)
    k.w["round"] = 3
    assert D.window_note(k, lid) == " [in force while round() is 2-5]"
    assert D.window_note(k, k.active_laws()[0]["id"]) == ""                 # no window: no note
    k1 = world(v2=False)
    l1 = enact(k1, WINDOWED)
    assert D.window_note(k1, l1) == "" and "in force while" not in CX.read_law(k1, a, l1)


def test_the_preview_shows_the_window():
    k = world()
    a = agents(k)[0]
    rep = LP.preview_law(k, a, WINDOWED)
    assert rep["static"]["in_force"] == [2, 5]
    assert "in force while round() is 2-5" in LP.render(rep)
    rep = LP.preview_law(k, a, law("Open", "in_force_until = 4\nx = 1\n"))
    assert rep["static"]["in_force"] == [None, 4] and "round() <= 4" in LP.render(rep)


def test_a_refusal_in_an_after_hook_is_told_to_the_acting_agent():
    k = world()
    a, b, _ = agents(k)
    lid = enact(k, law("Undo", "def after_move(p, chain):\n    if p['why'] == 'transfer':\n        state['n'] = 1\n"
                               "        refuse('no gifts on Sunday')\n"))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert events(k, "transfer") and k.w["laws"][lid]["state"] == {}
    e = events(k, "law_refused")[-1]
    assert e["vis"] == [a] and e["data"] == {"law": lid, "hook": "after_move", "primitive": "move", "reason": "no gifts on Sunday"}
    txt = AG.render_event(k, e, a)
    assert "refused after your move" in txt and "no gifts on Sunday" in txt and "your action stands" in txt
    assert events(k, "hook_aborted")[-1]["data"]["kind"] == "refused"      # the monitor's record as before


def test_a_refusal_without_an_acting_agent_tells_nobody():
    k = world()
    a, b, _ = agents(k)
    enact(k, law("Undo", "def after_move(p, chain):\n    refuse('no')\n"))
    with k.cause("kernel", "test", root=True):
        k.apply("move", src=a, dst=b, item="timber", qty=1, why="kernel")
    assert events(k, "hook_aborted") and not events(k, "law_refused")


# ====================================================================== 3. W6b: is_number / is_text; appellate office; ruling cap
def workers(k, n=5):
    return [a for a in k.roster() if k.cls_of(a) == "worker"][:n]


def give(k, aid, *rights):
    for r in rights:
        if r not in k.w["rights"]:
            k.w["rights"].append(r)
        k.w["agents"][aid]["rights"].append(r)


TYPED_PENALTY = law("Theft Act", '''
def penalty(accused, accuser, remedy):
    if is_number(remedy):
        move(accused, accuser, "timber", remedy)
        state["kind"] = "damages"
    elif is_text(remedy):
        state["kind"] = "named:" + remedy
    else:
        state["kind"] = "none"

def on_enact():
    clause("theft", "no theft", penalty)
''')


def court(sets=()):
    k = world(sets=sets)
    a, b, j, j2, j3 = workers(k)
    for x in (a, b):
        k._add(x, "timber", 20.0)
    lid = enact(k, TYPED_PENALTY)
    give(k, j, "judge")
    return k, lid, a, b, j, j2, j3


def accuse(k, a, b, lid):
    A.act(k, a, "accuse", {"agent": b, "law": lid, "clause": "theft", "evidence": []})
    return f"C{k.w['case_seq']}"


def test_is_number_and_is_text():
    assert [D.is_number(x) for x in (1, 2.5, True, "3", None)] == [True, True, False, False, False]
    assert [D.is_text(x) for x in ("a", 1, None)] == [True, False, False]
    k = world()
    api = k.api_for(k.active_laws()[0]["id"])
    assert api["is_number"] is D.is_number and api["is_text"] is D.is_text
    assert "is_number" not in world(v2=False).api_for("_")


@pytest.mark.parametrize("remedy,kind", [(4, "damages"), ("apology", "named:apology"), (None, "none")])
def test_a_penalty_tells_damages_from_a_named_remedy(remedy, kind):
    k, lid, a, b, j, _, _ = court()
    cid = accuse(k, a, b, lid)
    ab = k.bal(a, "timber")
    A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r", **({"remedy": remedy} if remedy is not None else {})})
    assert k.w["laws"][lid]["state"]["kind"] == kind
    assert k.bal(a, "timber") == ab + (4 if kind == "damages" else 0)


APPEAL_OFFICE = law("Court of Appeal", '''
def on_enact():
    set_court_rule("appeal_judges", "justice")
    set_court_rule("appeal_window", 2)
''')


def test_an_appellate_office_sees_rule_and_rules_on_appeals_only_without_judge():
    from charter import action_registry as AR
    k, lid, a, b, j, j2, _ = court()
    give(k, j2, "justice")                                              # the office, without judge
    names = lambda x: [r.name for r in AR.available(k.inst, k, k.w["agents"][x])]
    assert "rule" not in names(j2)                                      # no appeal bench yet
    enact(k, APPEAL_OFFICE)
    assert "rule" in names(j2) and "rule" in names(j)
    cid = accuse(k, a, b, lid)
    with pytest.raises(A.ActionError, match="judge"):                   # first instance: judges only
        A.act(k, j2, "rule", {"case": cid, "verdict": "guilty", "reason": "r"})
    A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r", "remedy": 3})
    A.act(k, b, "appeal", {"case": cid, "reason": "no"})
    c = k.w["cases"][cid]
    assert c["judges"] == [j2]
    A.act(k, j2, "rule", {"case": cid, "verdict": "not guilty", "reason": "alibi"})
    assert c["verdict"] == "not guilty" and c["penalty"] == "vacated"
    k1 = world(v2=False)
    w = workers(k1)[2]
    give(k1, w, "justice")
    assert "rule" not in [r.name for r in AR.available(k1.inst, k1, k1.w["agents"][w])]


def test_rulings_per_round_is_a_court_rule():
    from charter import courts as CO
    from charter import lawlang as L
    k, lid, a, b, j, _, _ = court()
    cases = [accuse(k, a, b, lid) for _ in range(3)]
    assert k.api_for(lid)["court_rules"]()["rulings_per_round"] == 3
    enact(k, law("Busy Bench", "def on_enact():\n    set_court_rule('rulings_per_round', 2)\n"))
    for cid in cases[:2]:
        A.act(k, j, "rule", {"case": cid, "verdict": "not guilty", "reason": "r"})
    with pytest.raises(A.ActionError, match="at most 2 cases per round"):
        A.act(k, j, "rule", {"case": cases[2], "verdict": "not guilty", "reason": "r"})
    with pytest.raises(L.LawError, match="1 to 20"):
        CO.check_rule(k, "rulings_per_round", 0)


# ====================================================================== 4. W6c: contracts' stage plans; probes; the vote doc
def contracts_world():
    sp = S.apply_overrides(S.load("E2"), ["rounds=8", "shared_archive.enabled=false", "turns=sequential", "law.v2=true",
                                          "contracts.enabled=true", "contracts.scripted=false"])
    k = Kernel(generator.generate(sp, 1))
    k.enact(k.new_law(k.inst["constitution_code"], "constitution"))
    k.start_round()
    return k


def people(k):
    return [a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer")]


STAGED_CONTRACT = '''
def proc(p):
    m = members()
    return {"stages": [{"name": "board", "electorate": m[:1], "rule": "majority", "closes_in": 0},
                       {"name": "members", "electorate": m + ["nobody"], "rule": "majority", "closes_in": 0}]}
def on_enact():
    set_procedure("ordinary", proc)
'''


def staged_contract():
    k = contracts_world()
    a, b, c, out = people(k)[:4]
    res = A.act(k, a, "create_contract", {"name": "Firm", "code": law("Rules", STAGED_CONTRACT)})
    cid = re.search(r"A\d+", res).group()
    for x in (b, c):
        A.act(k, x, "join_contract", {"contract": cid})
    res = A.act(k, b, "propose_contract_change", {"contract": cid, "code": law("More", "def on_round_end(r):\n    state['n'] = 1\n")})
    rec = k.w["contracts"]["assoc"][cid]
    pr = list(rec["proposals"].values())[-1]
    return k, cid, rec, pr, (a, b, c, out), res


def open_ballot(k, lid):
    return next(b for b in k.w["ballots"].values() if b["proposal"] == lid and b["status"] == "open")


def close(k):
    k.w["round"] = max(k.r, max(b["closes"] for b in k.w["ballots"].values() if b["status"] == "open"))
    k.close_ballots()


def test_a_contract_procedure_may_answer_with_a_stage_plan():
    k, cid, rec, pr, (a, b, c, out), res = staged_contract()
    lid = pr["law"]
    assert pr["status"] == "stage" and "stages" in res and k.w["laws"][lid]["status"] == "stage"
    b1 = open_ballot(k, lid)
    assert b1["electorate"] == [a] and b1["jurisdiction"] == cid
    opened = [e for e in k.events if e["type"] == "proposal_stage_open"][-1]
    assert opened["vis"] != "public" and set(opened["vis"]) >= {a, b, c} and out not in opened["vis"]   # members only
    A.act(k, a, "vote", {"ballot": b1["id"], "choice": "yes"})
    close(k)
    b2 = open_ballot(k, lid)
    assert b2["electorate"] == [a, b, c]                                 # cut to the members
    for x in (a, b):
        A.act(k, x, "vote", {"ballot": b2["id"], "choice": "yes"})
    close(k)
    assert pr["status"] == "adopted" and lid in rec["laws"] and k.w["laws"][lid]["status"] == "active"
    assert events(k, "contract_changed")[-1]["data"]["law"] == lid
    assert not [e for e in k.events if e["type"] == "proposal_failed" and e["data"]["law"] == lid]
    assert "Procedure (" in CX.read_law(k, b, lid)


def test_a_contract_stage_plan_voted_down_fails_through_the_contract():
    k, cid, rec, pr, (a, b, c, out), _ = staged_contract()
    lid = pr["law"]
    A.act(k, a, "vote", {"ballot": open_ballot(k, lid)["id"], "choice": "no"})
    close(k)
    assert pr["status"] == "failed" and k.w["laws"][lid]["status"] == "failed" and lid not in rec["laws"]
    e = events(k, "contract_change_failed")[-1]
    assert e["data"]["law"] == lid and "voted down at board" in e["data"]["why"]
    assert not [e for e in k.events if e["type"] == "proposal_failed" and e["data"]["law"] == lid]
    k.end_round()                                                        # nothing left for the contract's round end
    assert pr["status"] == "failed"


def test_jurisdiction_probes_read_a_stage_plan(monkeypatch):
    from charter import jurisdictions as J
    k = world()
    mem = agents(k, 5)
    plan = {"stages": [{"electorate": mem[:3], "rule": "majority"}, {"electorate": mem[2:], "rule": "two_thirds"}],
            "assent": [mem[0]]}
    monkeypatch.setattr(J, "members", lambda k, jid: list(mem))
    monkeypatch.setattr(J, "_procedure_spec", lambda k, jid, cls, a: plan)
    ds = J.decisive_set(k, "J1")
    assert ds == mem[:4]                                                 # 2 of 3, then 2 of 3 (two thirds), then the assent
    assert set(J.vote_weights(k, "J1")) == set(mem[:3])                  # the first stage's weights
    monkeypatch.setattr(J, "_procedure_spec", lambda k, jid, cls, a: {"electorate": mem, "rule": "majority"})
    assert J.decisive_set(k, "J1") == mem[:3]                            # one ballot: as before


def test_the_vote_doc_mentions_ranked_lists_only_under_v2():
    from charter import facts as FX
    for v2, has in ((True, True), (False, False)):
        k = world(v2=v2)
        a = k.w["agents"][agents(k)[0]]
        assert ("ranked list" in AG.action_doc("vote", k.inst, a, FX.facts(k.inst))) is has


# ====================================================================== 5. W6f: history(about=); an association reads its record
def test_history_about_matches_agents_named_in_event_data():
    from charter import evidence as EV
    k, lid, a, b, j, c, _ = court()
    accuse(k, a, b, lid)                                                 # public: agent a, data accused b, accuser a
    accuse(k, b, c, lid)
    A.act(k, c, "post", {"text": "hello"})
    api = k.api_for(enact(k, law("Reader", "x = 1\n")))
    by = lambda **kw: [(e["type"], e["agent"]) for e in api["history"](type=["accuse", "post"], **kw)]
    assert by(agent=b) == [("accuse", b)]                                # the actor only, as before
    assert by(about=b) == [("accuse", a), ("accuse", b)]                 # also named as the accused
    assert by(about=c) == [("accuse", b), ("post", c)]
    assert by(agent=a, about=c) == []
    assert EV.names({"agent": None, "data": {"parties": [a, b]}}, b) and not EV.names({"data": {"deep": {"to": b}}}, b)


CONTRACT_RECORD = '''
def on_round_start(r):
    breach(members()[-1], "late", "1 timber")

def on_round_end(r):
    public["seen"] = [[e["type"], e["data"]["clause"]] for e in history(type="contract_breach")]
    public["about"] = len(history(type="contract_breach", about=members()[-1]))
'''


def test_an_association_s_law_reads_its_members_only_record_end_to_end():
    k = contracts_world()
    a, b = people(k)[:2]
    res = A.act(k, a, "create_contract", {"name": "Club", "code": law("Record", CONTRACT_RECORD)})
    cid = re.search(r"A\d+", res).group()
    A.act(k, b, "join_contract", {"contract": cid})
    k.end_round()
    k.start_round()
    k.end_round()
    lid = k.w["contracts"]["assoc"][cid]["laws"][0]
    e = events(k, "contract_breach")[-1]
    assert e["vis"] != "public" and set(e["vis"]) == {a, b}              # members-only
    assert k.w["laws"][lid]["public"]["seen"] == [["contract_breach", "late"]] and k.w["laws"][lid]["public"]["about"] == 1
    polity = enact(k, law("Outsider", "x = 1\n"))                        # a polity's law never reads it
    assert k.api_for(polity)["history"](type="contract_breach") == []


def test_the_lookup_error_lists_the_lookups():
    k = world(sets=["context.enabled=true"])
    with pytest.raises(A.ActionError, match="no lookup 'nope'; lookups: manual, manual_search") as ei:
        CX.lookup(k, agents(k)[0], "nope", {})
    assert "preview_law" in str(ei.value) and "legal_position" not in str(ei.value)
    assert CX.lookup_names(k)[0] == "manual" and CX._lookups is not CX.lookup_names


# ====================================================================== 6. W6e: breach victims; the Act pays them
def victim_world(victim_expr):
    from charter import library as LB
    k = contracts_world()
    k.spec["contracts"]["enforcement"] = "escrow_court"
    a, b, c, judge = people(k)[:4]
    body = f"def on_round_start(r):\n    if r == 1:\n        breach({b!r}, 'delivery', 'late', {victim_expr})\n"
    res = A.act(k, a, "create_contract", {"name": "Supply", "code": law("Supply", body)})
    cid = re.search(r"A\d+", res).group()
    A.act(k, b, "join_contract", {"contract": cid})
    act = enact(k, LB.LIB["Contract Enforcement Act"]["code"].replace('MODE = "court"', 'MODE = "auto"'))
    k._add(b, "grain", 10.0 - k.bal(b, "grain"))
    return k, (a, b, c), cid, act


@pytest.mark.parametrize("who", ["member", "outsider", "none"])
def test_a_breach_names_its_victim_and_the_act_pays_the_fine_to_it(who):
    k0 = contracts_world()
    a, b, c = people(k0)[:3]
    victim = {"member": a, "outsider": c, "none": None}[who]
    k, (a, b, c), cid, act = victim_world(repr(victim))
    before = {x: k.bal(x, "grain") for x in (a, c, "reserve")}
    k.end_round()
    k.start_round()
    k.end_round()                                                        # round 1: recorded, then sanctioned (auto)
    rec = k.w["contracts"]["assoc"][cid]
    br = rec["breaches"][-1]
    assert (br.get("victim"), "victim" in br) == (victim, victim is not None)
    assert events(k, "contract_breach")[-1]["data"].get("victim") == victim
    assert k.bal(b, "grain") == 8.0                                      # FINE 2, once
    if victim is None:
        assert k.bal("reserve", "grain") == before["reserve"] + 2
    else:
        assert k.bal(victim, "grain") == before[victim] + 2 and k.bal("reserve", "grain") == before["reserve"]


def test_a_breach_victim_must_be_another_agent():
    from charter import lawlang as L
    k = contracts_world()
    a, b = people(k)[:2]
    res = A.act(k, a, "create_contract", {"name": "Supply", "code": law("Supply", "def go(m, v):\n    return breach(m, 'x', '', v)\n")})
    cid = re.search(r"A\d+", res).group()
    lid = k.w["contracts"]["assoc"][cid]["laws"][0]
    for bad in (a, "nobody"):
        with pytest.raises(L.LawError, match="victim"):
            k.call(lid, k.ns[lid]["go"], a, bad)
