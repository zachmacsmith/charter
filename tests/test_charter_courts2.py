"""Courts v2 (charter/courts.py; review 10 §6 item 5): law-readable cases, open_case/answer_case routed through Kernel.apply (hooks
fire on them), remedies reaching the clause's penalty, law-set court rules (deadline, panel, benches) and appeals with deferred
penalties; and worlds without law.v2 unchanged. Offline: scripted actions, no model calls."""
from __future__ import annotations

import pytest

from charter import action_registry as AR
from charter import actions as A
from charter import courts as CO
from charter import generator
from charter import lawlang as L
from charter import spec as S
from charter.kernel import Kernel


def world(v2=True, preset="E4"):
    sp = S.apply_overrides(S.load(preset), ["shared_archive.enabled=false"])
    if v2:
        sp["law"] = {"v2": True}
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return k


def law(title, body):
    return f'title = "{title}"\nintent = "test"\n' + body


def enact(k, code):
    lid = k.new_law(code, "constitution")
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active", k.w["laws"][lid]
    return lid


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def workers(k, n=5):
    return [a for a in k.roster() if k.cls_of(a) == "worker"][:n]


def give(k, aid, *rights):
    for r in rights:
        if r not in k.w["rights"]:
            k.w["rights"].append(r)
        k.w["agents"][aid]["rights"].append(r)


def next_round(k):
    """End the round's case step, then move to the next round (the counters a judge's rulings use reset)."""
    k._round_end_steps()["expire_cases"]()
    k.w["round"] += 1
    k.w["rulings_this_round"] = {}


PENALTY3 = '''
def penalty(accused, accuser, remedy):
    state["calls"] = state.get("calls", []) + [[accused, accuser, remedy]]
    if remedy:
        move(accused, accuser, "timber", remedy)

def on_enact():
    clause("theft", "no theft", penalty)
'''


def setup(k, body=PENALTY3, title="Theft Act"):
    a, b, j, j2, j3 = workers(k)
    for x in (a, b):
        k._add(x, "timber", 20.0)
    lid = enact(k, law(title, body))
    give(k, j, "judge")
    return lid, a, b, j, j2, j3


def accuse(k, a, b, lid, clause="theft"):
    A.act(k, a, "accuse", {"agent": b, "law": lid, "clause": clause, "evidence": []})
    return f"C{k.w['case_seq']}"


# ------------------------------------------------------------------ worlds without law.v2 are untouched
def test_v1_courts_are_unchanged():
    k = world(v2=False)
    lid, a, b, j, _, _ = setup(k, body='def pen(accused, accuser):\n    fine(accused, "timber", 1)\n'
                                       'def on_enact():\n    clause("theft", "no theft", pen)\n')
    api = k.api_for(lid)
    assert not {"cases", "case", "court_rules", "set_court_rule"} & set(api)
    cid = accuse(k, a, b, lid)
    c = k.w["cases"][cid]
    assert set(c) == {"id", "accuser", "accused", "clause", "evidence", "counter", "status", "filed", "deadline", "judges"}
    assert c["deadline"] == k.r + 3
    with pytest.raises(A.ActionError, match="unexpected keyword argument 'remedy'"):
        A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r", "remedy": 3})
    with pytest.raises(A.ActionError, match="unknown action 'appeal'"):
        A.act(k, b, "appeal", {"case": cid})
    before = k.bal(b, "timber")
    A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "seen"})
    assert k.bal(b, "timber") == before - 1 and k.w["cases"][cid]["status"] == "decided"
    assert set(k.w["cases"][cid]) == {"id", "accuser", "accused", "clause", "evidence", "counter", "status", "filed", "deadline",
                                      "judges", "verdict", "reason", "judge"}
    assert set(events(k, "ruling")[-1]["data"]) == {"case", "verdict", "reason"}
    assert "court_rules" not in k.w and "appeal" not in [x.name for x in AR.available(k.inst, k, k.w["agents"][b])]
    with pytest.raises(L.LawError, match="need law.v2"):                # no hooking a filing without law.v2
        k.new_law(law("Standing", "def before_open_case(p, chain):\n    return False\n"), "a")


def test_v1_dismissal_is_unchanged():
    k = world(v2=False)
    lid, a, b, j, _, _ = setup(k, body='def pen(accused, accuser):\n    return None\n'
                                       'def on_enact():\n    clause("theft", "no theft", pen)\n')
    cid = accuse(k, a, b, lid)
    for _ in range(3):
        next_round(k)
    assert k.w["cases"][cid]["status"] == "open"
    next_round(k)                                                       # the end of the third round after filing
    assert k.w["cases"][cid]["status"] == "dismissed"
    assert events(k, "case_dismissed")[-1]["data"] == {"case": cid, "why": "no ruling within 3 rounds"}


# ------------------------------------------------------------------ 1. law-readable cases
def test_laws_read_cases_of_their_own_polity():
    k = world()
    lid, a, b, j, _, _ = setup(k)
    cid = accuse(k, a, b, lid)
    api = k.api_for(lid)
    [c] = api["cases"]()
    assert c["id"] == cid and c["accuser"] == a and c["accused"] == b and c["status"] == "open" and c["law"] == lid
    assert c["stage"] == 1 and c["verdict"] is None and c["final"] is False
    assert api["cases"]("decided") == [] and api["case"](cid) == c and api["case"]("C99") is None
    with pytest.raises(L.LawError, match="status"):
        api["cases"]("pending")
    c["accused"] = "someone"                                            # a copy: the case is not changed through the read
    assert k.w["cases"][cid]["accused"] == b
    other = enact(k, law("Elsewhere", "def noop():\n    return None\n"))
    k.w["laws"][other]["jurisdiction"] = "J7"                          # a law of another account sees none of them
    assert k.api_for(other)["cases"]() == [] and k.api_for(other)["case"](cid) is None


def test_a_statute_of_limitations_reads_cases_before_filing():
    """Double jeopardy: before_open_case refuses a second case against the same agent under the same clause."""
    k = world()
    lid, a, b, j, j2, _ = setup(k)
    enact(k, law("No Double Jeopardy", '''
def before_open_case(p, chain):
    for c in cases():
        if c["accused"] == p["accused"] and c["clause"] == p["clause"]:
            return {"block": True, "reason": "already tried"}
    return None
'''))
    accuse(k, a, b, lid)
    n = k.w["case_seq"]
    with pytest.raises(A.ActionError, match="already tried"):
        accuse(k, j2, b, lid)
    assert k.w["case_seq"] == n                                         # a refused filing files nothing


# ------------------------------------------------------------------ 2. routed filings: standing and a filing fee
def test_standing_rule_and_filing_fee_fire_on_open_case():
    k = world()
    lid, a, b, j, j2, _ = setup(k)
    give(k, a, "standing")
    enact(k, law("Court Fees", '''
def before_open_case(p, chain):
    if not has(p["accuser"], "standing"):
        return {"block": True, "reason": "no standing"}
    return None

def after_open_case(p, chain):
    fine(p["accuser"], "timber", 2)

def after_answer_case(p, chain):
    state["answers"] = state.get("answers", 0) + 1
'''))
    with pytest.raises(A.ActionError, match="no standing"):
        accuse(k, b, a, lid)
    assert k.w["cases"] == {}
    before = k.bal(a, "timber")
    cid = accuse(k, a, b, lid)
    assert k.bal(a, "timber") == before - 2                              # the filing fee
    A.act(k, b, "respond", {"case": cid, "evidence": []})
    fees = next(l for l in k.w["laws"].values() if l["title"] == "Court Fees")
    assert fees["state"]["answers"] == 1
    assert events(k, "accuse")[-1]["data"]["case"] == cid and events(k, "respond")[-1]["data"]["case"] == cid


# ------------------------------------------------------------------ 3. remedies
def test_remedy_reaches_a_three_argument_penalty():
    k = world()
    lid, a, b, j, _, _ = setup(k)
    cid = accuse(k, a, b, lid)
    with pytest.raises(A.ActionError, match="damages"):
        A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r", "remedy": -1})
    ab, bb = k.bal(a, "timber"), k.bal(b, "timber")
    A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "took it", "remedy": "4"})
    assert k.bal(a, "timber") == ab + 4 and k.bal(b, "timber") == bb - 4
    assert k.w["laws"][lid]["state"]["calls"] == [[b, a, 4.0]]
    ev = events(k, "ruling")[-1]["data"]
    assert ev["remedy"] == 4.0 and k.w["cases"][cid]["remedy"] == 4.0
    assert k.api_for(lid)["case"](cid)["remedy"] == 4.0
    cid2 = accuse(k, a, b, lid)                                         # a named remedy; an acquittal carries none
    A.act(k, j, "rule", {"case": cid2, "verdict": "not guilty", "reason": "no", "remedy": "apology"})
    assert "remedy" not in k.w["cases"][cid2]


@pytest.mark.parametrize("sig,args", [("accused", "[accused]"), ("accused, accuser", "[accused, accuser]"),
                                      ("*xs", "list(xs)")])
def test_old_penalties_keep_working(sig, args):
    k = world()
    body = f'def pen({sig}):\n    {"accused = xs[0]" if sig == "*xs" else "pass"}\n    state["got"] = {args}\n' \
           'def on_enact():\n    clause("theft", "no theft", pen)\n'
    lid, a, b, j, _, _ = setup(k, body=body)
    cid = accuse(k, a, b, lid)
    A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r", "remedy": 2})
    want = {"accused": [b], "accused, accuser": [b, a], "*xs": [b, a, 2.0]}[sig]
    assert k.w["laws"][lid]["state"]["got"] == want and k.w["laws"][lid]["status"] == "active"


def test_before_rule_sees_the_remedy_and_can_cap_it():
    k = world()
    lid, a, b, j, _, _ = setup(k)
    enact(k, law("Damages Cap", '''
def before_rule(p, chain):
    if p["remedy"] != None and p["remedy"] != "apology" and p["remedy"] > 5:
        return {"block": True, "reason": "damages above 5"}
    return None
'''))
    cid = accuse(k, a, b, lid)
    with pytest.raises(A.ActionError, match="damages above 5"):
        A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r", "remedy": 9})
    assert k.w["cases"][cid]["status"] == "open"


# ------------------------------------------------------------------ 4. court rules
RULES = '''
def on_enact():
    set_court_rule("deadline", DEADLINE)
    set_court_rule("panel", PANEL)
'''


def test_court_rules_set_deadline_and_hold_while_their_law_is_in_force():
    k = world()
    lid, a, b, j, _, _ = setup(k)
    rl = enact(k, law("Court Rules", "DEADLINE = 5\nPANEL = 1\n" + RULES))
    assert k.w["laws"][rl]["cls"] == "procedural"
    assert k.api_for(lid)["court_rules"]()["deadline"] == 5 and events(k, "court_rule")[0]["data"]["key"] == "deadline"
    cid = accuse(k, a, b, lid)
    assert k.w["cases"][cid]["deadline"] == k.r + 5
    for _ in range(5):
        next_round(k)
    assert k.w["cases"][cid]["status"] == "open"
    next_round(k)
    assert k.w["cases"][cid]["status"] == "dismissed"
    assert events(k, "case_dismissed")[-1]["data"]["why"] == "no ruling within 5 rounds"
    k.repeal(rl, by_law=None)
    assert CO.rules(k, "J0")["deadline"] == 3                          # the rule lapses with its law
    api = k.api_for(lid)
    with pytest.raises(L.LawError, match="no court rule"):
        api["set_court_rule"]("speed", 2)
    with pytest.raises(L.LawError, match="whole number"):
        api["set_court_rule"]("panel", 0)
    with pytest.raises(L.LawError, match="no such right"):
        api["set_court_rule"]("judges", "magistracy")


def test_a_panel_decides_by_majority_with_the_median_remedy():
    k = world()
    lid, a, b, j, j2, j3 = setup(k)
    give(k, j2, "judge")
    give(k, j3, "judge")
    enact(k, law("Court Rules", "DEADLINE = 3\nPANEL = 3\n" + RULES))
    enact(k, law("Ruling Log", "def on_ruling(case, verdict, accuser, accused):\n    state['n'] = state.get('n', 0) + 1\n"))
    log = next(l for l in k.w["laws"].values() if l["title"] == "Ruling Log")
    cid = accuse(k, a, b, lid)
    bb = k.bal(b, "timber")
    out = A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r1", "remedy": 6})
    assert "1 of a panel of 3" in out and k.w["cases"][cid]["status"] == "open" and k.bal(b, "timber") == bb
    assert events(k, "panel_vote")[-1]["data"]["needed"] == 2 and "n" not in log["state"]
    with pytest.raises(A.ActionError, match="already ruled"):
        A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "again"})
    A.act(k, j2, "rule", {"case": cid, "verdict": "not guilty", "reason": "r2"})
    assert k.w["cases"][cid]["status"] == "open"
    A.act(k, j3, "rule", {"case": cid, "verdict": "guilty", "reason": "r3", "remedy": 2})
    c = k.w["cases"][cid]
    assert c["status"] == "decided" and c["verdict"] == "guilty" and c["remedy"] == 2.0      # lower median of 6 and 2
    assert k.bal(b, "timber") == bb - 2 and log["state"]["n"] == 1
    assert k.api_for(lid)["case"](cid)["votes"] == {j: "guilty", j2: "not guilty", j3: "guilty"}


def test_who_may_judge_is_a_court_rule():
    k = world()
    lid, a, b, j, j2, _ = setup(k)
    give(k, j2, "judge", "magistrate")
    enact(k, law("Magistrates", 'def on_enact():\n    set_court_rule("judges", "magistrate")\n'))
    cid = accuse(k, a, b, lid)
    assert k.w["cases"][cid]["judges"] == [j2]
    with pytest.raises(A.ActionError, match="only judges holding 'magistrate'"):
        A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r"})
    A.act(k, j2, "rule", {"case": cid, "verdict": "guilty", "reason": "r"})
    assert k.w["cases"][cid]["status"] == "decided"


# ------------------------------------------------------------------ 5. appeals
APPEALS = '''
def on_enact():
    set_court_rule("appeal_judges", "justice")
    set_court_rule("appeal_window", 2)
'''


def appeal_world():
    k = world()
    lid, a, b, j, j2, j3 = setup(k)
    give(k, j2, "judge", "justice")
    enact(k, law("Court of Appeal", APPEALS))
    return k, lid, a, b, j, j2, j3


def test_a_guilty_penalty_waits_for_the_appeal_window_then_runs():
    k, lid, a, b, j, _, _ = appeal_world()
    cid = accuse(k, a, b, lid)
    bb = k.bal(b, "timber")
    A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r", "remedy": 3})
    c = k.w["cases"][cid]
    assert c["penalty"] == "pending" and c["appealable_until"] == k.r + 2 and k.bal(b, "timber") == bb
    assert events(k, "ruling")[-1]["data"]["penalty"] == "deferred"
    assert "appeal" in [x.name for x in AR.available(k.inst, k, k.w["agents"][b])]
    next_round(k)
    next_round(k)
    assert k.bal(b, "timber") == bb and c["penalty"] == "pending"      # appealable to the end of the second round after the ruling
    next_round(k)
    assert k.bal(b, "timber") == bb - 3 and c["penalty"] == "run" and "appealable_until" not in c
    assert events(k, "case_final")[-1]["data"]["why"] == "no appeal"
    with pytest.raises(A.ActionError, match="final"):
        A.act(k, b, "appeal", {"case": cid, "reason": "late"})


def test_an_appeal_reopens_the_case_before_the_higher_office_and_can_acquit():
    k, lid, a, b, j, j2, j3 = appeal_world()
    cid = accuse(k, a, b, lid)
    bb = k.bal(b, "timber")
    A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r", "remedy": 3})
    with pytest.raises(A.ActionError, match="not a party"):
        A.act(k, j3, "appeal", {"case": cid})
    A.act(k, b, "appeal", {"case": cid, "reason": "I was elsewhere"})
    c = k.w["cases"][cid]
    assert c["status"] == "open" and c["stage"] == 2 and c["judges"] == [j2] and c["first"]["verdict"] == "guilty"
    assert "verdict" not in c and events(k, "appeal")[-1]["data"]["first"] == "guilty"
    view = k.api_for(lid)["case"](cid)
    assert view["stage"] == 2 and view["appeal"]["by"] == b and view["first"]["remedy"] == 3.0
    with pytest.raises(A.ActionError, match="justice"):
        A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "mine"})
    A.act(k, b, "respond", {"case": cid, "evidence": []})               # the accused may answer on appeal
    A.act(k, j2, "rule", {"case": cid, "verdict": "not guilty", "reason": "alibi"})
    assert c["status"] == "decided" and c["verdict"] == "not guilty" and c["penalty"] == "vacated"
    assert k.bal(b, "timber") == bb and "appealable_until" not in c
    with pytest.raises(A.ActionError, match="already appealed"):
        A.act(k, a, "appeal", {"case": cid})
    next_round(k)
    next_round(k)
    assert k.bal(b, "timber") == bb                                     # an acquittal on appeal is final


def test_an_appeal_not_decided_in_time_lapses_and_the_first_ruling_stands():
    k, lid, a, b, j, j2, _ = appeal_world()
    cid = accuse(k, a, b, lid)
    bb = k.bal(b, "timber")
    A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r", "remedy": 1})
    A.act(k, b, "appeal", {"case": cid})
    for _ in range(4):
        next_round(k)
    c = k.w["cases"][cid]
    assert c["status"] == "decided" and c["verdict"] == "guilty" and c["appeal"]["outcome"] == "lapsed"
    assert k.bal(b, "timber") == bb - 1 and c["penalty"] == "run"
    assert "first ruling stands" in events(k, "case_final")[-1]["data"]["why"]


def test_before_appeal_can_refuse_an_appeal():
    k, lid, a, b, j, _, _ = appeal_world()
    enact(k, law("Leave To Appeal", 'def before_appeal(p, chain):\n    return {"block": True, "reason": "no leave"}\n'))
    cid = accuse(k, a, b, lid)
    A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r"})
    with pytest.raises(A.ActionError, match="no leave"):
        A.act(k, b, "appeal", {"case": cid})
    assert k.w["cases"][cid].get("stage", 1) == 1 and k.w["cases"][cid]["status"] == "decided"


def test_without_an_appeal_bench_nothing_is_deferred():
    k = world()
    lid, a, b, j, _, _ = setup(k)
    cid = accuse(k, a, b, lid)
    bb = k.bal(b, "timber")
    A.act(k, j, "rule", {"case": cid, "verdict": "guilty", "reason": "r", "remedy": 1})
    assert k.bal(b, "timber") == bb - 1 and "appealable_until" not in k.w["cases"][cid]
    with pytest.raises(A.ActionError, match="final"):
        A.act(k, b, "appeal", {"case": cid})


# ------------------------------------------------------------------ helpers
def test_arity_and_remedies():
    assert CO.arity(lambda a: 0) == 1 and CO.arity(lambda a, b: 0) == 2 and CO.arity(lambda a, b, c, d: 0) == 3
    assert CO.arity(lambda *a: 0) == 3
    assert CO.remedy_of(None) is None and CO.remedy_of(2) == 2.0 and CO.remedy_of("2.5") == 2.5 and CO.remedy_of("apology") == "apology"
    for bad in (True, -1, float("nan"), [1]):
        with pytest.raises(ValueError):
            CO.remedy_of(bad)
