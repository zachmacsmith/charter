"""Credit and fragility (charter/credit.py): interest, partial repayment, default consequences, credit records, refinancing,
par currencies, fractional reserves, bank runs, suspensions, bailouts, and a scripted run with the new laws in force."""
import json

import pytest

from charter import actions as A
from charter import agents as AG
from charter import credit as CR
from charter import generator, lawlang as L, library as LB, spec
from charter.kernel import Kernel


def make(rung="E3", seed=1, **over):
    s = spec.load(rung)
    s = spec.set_path(s, "shared_archive.namespace", "pytest")
    for k_, v in over.items():
        s = spec.set_path(s, k_.replace("__", "."), v)
    k = Kernel(generator.generate(s, seed))
    k.enact(k.new_law(k.inst["constitution_code"], "constitution"))
    k.start_round()
    return k


def workers(k, n=3):
    ws = [a for a, v in k.w["agents"].items() if v["cls"] == "worker"][:n]
    for w in ws:
        k.agent(w)["holdings"] = {"timber": 20.0, "stone": 10.0}
    return ws


def law(k, code, author="constitution"):
    lid = k.new_law(code, author)
    k.enact(lid)
    return lid


def lib(k, name):
    return law(k, LB.LIB[name]["code"])


def nxt(k):
    k.end_round(None)
    k.start_round()


# ------------------------------------------------------------------ loans
def test_simple_and_compound_interest_accrue_each_round():
    k = make()
    a, b, c = workers(k)
    lib(k, "Loan Registry")
    A.act(k, a, "lend", {"to": b, "item": "timber", "qty": 10, "due_in": 3, "rate": 0.1})
    A.act(k, a, "lend", {"to": c, "item": "timber", "qty": 10, "due_in": 3, "rate": 0.1, "compound": True})
    A.act(k, b, "accept_loan", {"loan": "N1"})
    A.act(k, c, "accept_loan", {"loan": "N2"})
    nxt(k)
    nxt(k)
    s, cp = k.w["loans"]["N1"], k.w["loans"]["N2"]
    assert s["repay_qty"] == pytest.approx(12.0) and cp["repay_qty"] == pytest.approx(12.1)
    assert s["interest"] == pytest.approx(2.0)


def test_partial_repayment_and_repaid_in_full():
    k = make()
    a, b, _ = workers(k)
    lib(k, "Loan Registry")
    A.act(k, a, "lend", {"to": b, "item": "timber", "qty": 5, "repay_qty": 6, "due_in": 4})
    A.act(k, b, "accept_loan", {"loan": "N1"})
    out = A.act(k, b, "repay_loan", {"loan": "N1", "qty": 2})
    assert "4 still owed" in out and k.w["loans"]["N1"]["status"] == "active"
    A.act(k, b, "repay_loan", {"loan": "N1"})
    assert k.w["loans"]["N1"]["status"] == "repaid" and k.bal(a, "timber") == pytest.approx(21)
    assert CR.record(k, a)["interest_received"] == pytest.approx(1) and CR.record(k, b)["interest_paid"] == pytest.approx(1)


@pytest.mark.parametrize("kind", ["seize", "sanction", "seize_sanction", "none"])
def test_default_under_each_consequence(kind):
    k = make()
    a, b, c = workers(k)
    lib(k, "Loan Registry")
    law(k, f'title="Default rule"\nintent="i"\ndef on_enact():\n    set_default_consequence("{kind}")\n')
    A.act(k, a, "lend", {"to": b, "item": "stone", "qty": 4, "repay_qty": 30, "due_in": 1})
    A.act(k, b, "accept_loan", {"loan": "N1"})
    nxt(k)
    ln = k.w["loans"]["N1"]
    assert ln["status"] == "defaulted" and ln["defaulted_round"] == k.r
    seized = kind in ("seize", "seize_sanction")
    assert k.bal(b, "stone") == (0 if seized else 14) and ln["repaid"] == (14 if seized else 0)
    sanctioned = kind in ("sanction", "seize_sanction")
    assert (k.agent(b)["limit"] is not None) == sanctioned
    assert any(e["type"] == "sanction" and e["data"]["agent"] == b for e in k.events) == sanctioned
    A.act(k, c, "lend", {"to": b, "item": "timber", "qty": 1, "due_in": 2})
    if sanctioned:
        with pytest.raises(A.ActionError, match="default"):
            A.act(k, b, "accept_loan", {"loan": "N2"})                 # barred from borrowing while in default
    else:
        A.act(k, b, "accept_loan", {"loan": "N2"})
    # repaying after default clears it (counted as late)
    k.agent(b)["holdings"]["stone"] = 100.0
    A.act(k, b, "repay_loan", {"loan": "N1"})
    assert ln["status"] == "repaid" and ln["late"] and CR.record(k, b)["defaults"] == 1 and CR.record(k, b)["repaid_late"] == 1


def test_handshake_loans_still_mean_no_seizure_and_registry_still_seizes():
    k = make()
    a, b, _ = workers(k)
    lib(k, "Handshake Loans")
    assert CR.consequence(k) == "none"
    lib(k, "Loan Registry")
    assert CR.consequence(k) == "seize"
    lid = lib(k, "Debtor Sanctions")
    assert CR.consequence(k) == "sanction"
    k.repeal(lid)                                                     # the rule lapses with its law (and so do loans it enabled)
    assert not k.loans_enabled()


def test_credit_records_are_public_and_readable_by_law():
    k = make()
    a, b, c = workers(k)
    lib(k, "Handshake Loans")
    A.act(k, a, "lend", {"to": b, "item": "timber", "qty": 3, "repay_qty": 50, "due_in": 1})
    A.act(k, b, "accept_loan", {"loan": "N1"})
    nxt(k)
    view = AG.state_view(k, c)                                       # a third party sees b's record
    assert "Credit records (public)" in view and f"{b}: owes 50" in view and "IN DEFAULT" in view
    assert "Loans: enabled; on default: none" in view
    assert f"N1 you owe {a}" in AG.state_view(k, b)
    law(k, 'title="Shame"\nintent="i"\ndef on_round_end(r):\n    for a in agents():\n        if credit_record(a)["defaults"] > 0:\n'
           '            gazette("defaulter " + a)\n')
    nxt(k)
    assert any(e["type"] == "gazette" and e["data"]["text"] == f"defaulter {b}" for e in k.events)
    assert any(e["type"] == "loan_defaulted" and e["vis"] == "public" for e in k.events)


def test_rollover_refinancing_and_lending_coins():
    k = make()
    a, b, c = workers(k)
    lib(k, "Loan Registry")
    lib(k, "Crown Currency")
    A.act(k, c, "deposit", {"currency": "crown", "item": "stone", "qty": 5})          # c holds 10 crowns
    A.act(k, a, "lend", {"to": b, "item": "timber", "qty": 6, "repay_qty": 8, "due_in": 1})
    A.act(k, b, "accept_loan", {"loan": "N1"})
    A.act(k, a, "extend_loan", {"loan": "N1", "rounds": 2})
    assert k.w["loans"]["N1"]["due"] == k.r + 3
    with pytest.raises(A.ActionError, match="raise"):
        A.act(k, a, "extend_loan", {"loan": "N1", "rounds": 1, "rate": 0.5})
    # c refinances: lends timber that first pays a off
    A.act(k, c, "lend", {"to": b, "item": "timber", "qty": 10, "repay_qty": 11, "due_in": 5, "refinance": "N1"})
    a0, b0 = k.bal(a, "timber"), k.bal(b, "timber")
    A.act(k, b, "accept_loan", {"loan": "N2"})
    assert k.w["loans"]["N1"]["status"] == "refinanced" and k.bal(a, "timber") == a0 + 8 and k.bal(b, "timber") == b0 + 2
    # coins can be lent like resources
    A.act(k, c, "lend", {"to": a, "item": "crown", "qty": 4, "repay_qty": 5, "due_in": 2})
    A.act(k, a, "accept_loan", {"loan": "N3"})
    assert k.bal(a, "crown") == pytest.approx(4)


def test_usury_law_caps_interest_and_jubilee_forgives():
    k = make()
    a, b, _ = workers(k)
    lib(k, "Loan Registry")
    A.act(k, a, "lend", {"to": b, "item": "timber", "qty": 10, "due_in": 5, "rate": 0.2})
    A.act(k, b, "accept_loan", {"loan": "N1"})
    lib(k, "Usury Law")
    assert LB.PREDICATES["Usury Law"](k, {})
    with pytest.raises(A.ActionError, match="interest cap"):
        A.act(k, a, "lend", {"to": b, "item": "timber", "qty": 10, "repay_qty": 14, "due_in": 2})   # 20% per round premium
    A.act(k, a, "lend", {"to": b, "item": "timber", "qty": 10, "repay_qty": 11, "due_in": 2})       # 5% per round: allowed
    nxt(k)
    assert k.w["loans"]["N1"]["rate"] == 0.05 and k.w["loans"]["N1"]["repay_qty"] == pytest.approx(10.5)   # existing loan capped
    lib(k, "Debt Jubilee")
    assert k.w["loans"]["N1"]["status"] == "forgiven"


# ------------------------------------------------------------------ par, fractional reserve, runs
def par_world():
    k = make()
    a, b, c = workers(k)
    lib(k, "Crown Currency")
    law(k, 'title="Par"\nintent="i"\ndef on_enact():\n    set_par("crown", "stone", 1)\n')
    return k, a, b, c


def test_par_redemption_and_minting_beyond_the_reserve():
    k, a, b, c = par_world()
    A.act(k, a, "deposit", {"currency": "crown", "item": "stone", "qty": 10})
    assert k.bal(a, "crown") == pytest.approx(10) and k.price("crown") == pytest.approx(2.0)   # 1 crown = 1 stone (value 2)
    law(k, 'title="Print"\nintent="i"\ndef on_enact():\n    mint("crown", 10, "' + b + '")\n')
    assert CR.reserve_ratio(k, "crown") == pytest.approx(0.5)
    assert k.price("crown") == pytest.approx(2.0)                     # at par while redemption is open: no dilution
    assert "par 1 crown = 1 stone, reserve ratio 0.5, redemption OPEN" in AG.state_view(k, c)
    out = A.act(k, b, "redeem", {"currency": "crown", "item": "stone", "coins": 4})
    assert "at par" in out and k.bal(b, "stone") == pytest.approx(14)
    with pytest.raises(A.ActionError, match="only to stone"):
        A.act(k, b, "redeem", {"currency": "crown", "item": "timber", "coins": 1})


def test_bank_run_suspends_redemption_and_the_coin_falls():
    k, a, b, c = par_world()
    A.act(k, a, "deposit", {"currency": "crown", "item": "stone", "qty": 10})
    law(k, 'title="Print"\nintent="i"\ndef on_enact():\n    mint("crown", 10, "' + b + '")\n    mint("crown", 10, "' + c + '")\n')
    nxt(k)                                                           # reserve 10 stone, 30 crowns: ratio 1/3
    A.act(k, b, "redeem", {"currency": "crown", "item": "stone", "coins": 10})
    out = A.act(k, c, "redeem", {"currency": "crown", "item": "stone", "coins": 10})   # c is too late: nothing is left
    assert "suspended" in out and k.bal(c, "crown") == pytest.approx(10)
    assert not CR.redemption_open(k, "crown")
    with pytest.raises(A.ActionError, match="suspended"):
        A.act(k, a, "redeem", {"currency": "crown", "item": "stone", "coins": 1})
    with pytest.raises(A.ActionError, match="closed"):
        A.act(k, a, "deposit", {"currency": "crown", "item": "stone", "qty": 1})
    assert k.price("crown") == pytest.approx(0.0)                     # nothing backs the 20 crowns left
    assert "SUSPENDED" in AG.state_view(k, a)
    k.end_round(None)
    run = next(e for e in k.events if e["type"] == "bank_run")
    assert run["data"]["demand"] == pytest.approx(42) and run["data"]["backing"] == pytest.approx(20)
    assert k.snapshots[-1]["redemption"]["crown"] == "suspended"
    k.start_round()
    assert not CR.redemption_open(k, "crown")                         # suspended this round and the next (run_suspend_rounds 1)
    nxt(k)
    assert CR.redemption_open(k, "crown") and any(e["type"] == "redemption_resumed" for e in k.events)


def test_law_suspends_and_resumes_redemption_and_a_partial_payout():
    k, a, b, c = par_world()
    A.act(k, a, "deposit", {"currency": "crown", "item": "stone", "qty": 6})
    law(k, 'title="Print"\nintent="i"\ndef on_enact():\n    mint("crown", 4, "' + a + '")\n')
    law(k, 'title="Holiday"\nintent="i"\ndef on_enact():\n    suspend_redemption("crown", 3)\n')
    with pytest.raises(A.ActionError, match="suspended"):
        A.act(k, a, "redeem", {"currency": "crown", "item": "stone", "coins": 1})
    assert k.price("crown") == pytest.approx(2 * 6 / 10)               # backing per coin, below par
    law(k, 'title="Reopen"\nintent="i"\ndef on_enact():\n    suspend_redemption("crown", 0)\n')
    out = A.act(k, a, "redeem", {"currency": "crown", "item": "stone", "coins": 8})   # 6 stone left: 6 paid, 2 of 8 unredeemed
    assert "ran out" in out and k.bal(a, "crown") == pytest.approx(4) and k.bal(a, "stone") == pytest.approx(10)


def test_value_par_pays_in_any_reserve_resource():
    k, a, b, c = par_world()
    law(k, 'title="Value par"\nintent="i"\ndef on_enact():\n    set_par("crown", "value", 1)\n')
    A.act(k, a, "deposit", {"currency": "crown", "item": "timber", "qty": 4})
    A.act(k, b, "deposit", {"currency": "crown", "item": "stone", "qty": 3})
    assert k.price("crown") == 1.0 and k.bal(b, "crown") == pytest.approx(6)
    A.act(k, b, "redeem", {"currency": "crown", "item": "timber", "coins": 6})       # 4 timber (value 4), then 1 stone (value 2)
    assert k.bal("reserve", "timber") == 0 and k.bal("reserve", "stone") == pytest.approx(2)


def test_reserve_bank_act_lends_and_bailout_act_buys_defaulted_loans():
    k = make()
    a, b, c = workers(k)
    lib(k, "Reserve Bank Act")
    assert LB.PREDICATES["Reserve Bank Act"](k, {}) and L.classify(L.check(LB.LIB["Reserve Bank Act"]["code"])) == "structural"
    A.act(k, a, "deposit", {"currency": "crown", "item": "stone", "qty": 10})       # 20 crowns, backing 20
    nxt(k)
    offers = [ln for ln in k.w["loans"].values() if ln["lender"] == "reserve" and ln["status"] == "offered"]
    assert offers                                                      # credit expansion: new crowns lent from the reserve
    w = offers[0]["borrower"]
    before = k.bal(w, "crown")
    A.act(k, w, "accept_loan", {"loan": offers[0]["id"]})
    assert k.bal(w, "crown") == pytest.approx(before + 10) and CR.reserve_ratio(k, "crown") < 1
    # a private loan defaults; the Bailout Act pays its lender from the reserve
    A.act(k, a, "lend", {"to": b, "item": "timber", "qty": 1, "repay_qty": 50, "due_in": 1})
    A.act(k, b, "accept_loan", {"loan": next(i for i, ln in k.w["loans"].items() if ln["lender"] == a)})
    k.w["reserve"]["timber"] = 200.0
    lib(k, "Bailout Act")
    nxt(k)
    nxt(k)
    bought = [e for e in k.events if e["type"] == "loan_bought"]
    assert bought and bought[0]["data"]["from"] == a
    ln = k.w["loans"][bought[0]["data"]["loan"]]
    assert ln["lender"] == "reserve" and ln["sale"]["lender"] == a
    # lender of last resort: the defaulter is offered a reserve loan
    assert any(x["lender"] == "reserve" and x["borrower"] == b for x in k.w["loans"].values())
    from charter import scorer
    gt = {"snapshots": k.snapshots, "events": k.events, "unit": k.w["unit"]}
    m = CR.metrics(gt)
    assert any(x["kind"] == "loan_bought" for x in m["bailouts"]) and m["defaults"] >= 1 and m["debt_max"] > 0
    assert len(m["reserve_ratio_series"]["crown"]) == len(k.snapshots)
    from charter import goals as G
    assert G.s_creditor(gt, a, {}) == 1.0                              # a got its 50 stone (49 interest) through the bailout
    assert scorer is not None


def test_new_laws_are_structural_and_dry_run():
    k = make()
    for name in ("Reserve Bank Act", "Usury Law", "Debtor Sanctions", "Bailout Act", "Debt Jubilee"):
        assert L.classify(L.check(LB.LIB[name]["code"])) == "structural", name
        assert isinstance(k.dry_run(k.new_law(LB.LIB[name]["code"], "x")), list)
    for call in ("set_par", "suspend_redemption", "set_interest_cap", "set_default_consequence", "restructure_loan",
                 "lend_from_reserve", "buy_loan"):
        assert call in L.STRUCTURAL_CALLS


def test_restructure_loan_by_law():
    k = make()
    a, b, _ = workers(k)
    lib(k, "Handshake Loans")
    A.act(k, a, "lend", {"to": b, "item": "timber", "qty": 1, "repay_qty": 40, "due_in": 1})
    A.act(k, b, "accept_loan", {"loan": "N1"})
    nxt(k)
    assert k.w["loans"]["N1"]["status"] == "defaulted"
    law(k, 'title="Haircut"\nintent="i"\ndef on_enact():\n    for i in loans():\n        restructure_loan(i, 2, 5, 0)\n')
    ln = k.w["loans"]["N1"]
    assert ln["status"] == "active" and ln["repay_qty"] == pytest.approx(2) and ln["due"] == k.r + 5


def test_scripted_run_with_credit_laws_in_force(tmp_path):
    from charter import agents, runner, scorer
    sp = spec.load("E6")
    for key, v in (("rounds", 12), ("shared_archive.namespace", "pytest"), ("turns", "simultaneous"),
                   ("start_laws", ["Reserve Bank Act", "Usury Law", "Bailout Act", "Debtor Sanctions"])):
        sp = spec.set_path(sp, key, v)
    inst = generator.generate(sp, 3)
    out = runner.run(inst, agents.ScriptedPolicy(3), tmp_path / "r", log=lambda *x: None)
    res = scorer.score(out)
    cm = res["metrics"]["credit"]
    assert len(cm["debt_series"]) == 12 and "crown" in cm["reserve_ratio_series"]
    assert cm["loans_accepted"] > 0
    assert {"debt_max", "default_rate", "bank_runs", "bailouts"} <= set(res["summary"])
    ev = [json.loads(x) for x in (out / "events.jsonl").read_text().splitlines()]
    assert any(e["type"] == "par_set" for e in ev) and any(e["type"] == "loan_active" for e in ev)
