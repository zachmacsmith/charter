"""The Standing Contract core and its presets (review 31: docs/review/31_institutions/03_money_labour.md §2, 08_integration.md §2.1;
charter/standing.py): start.contracts, start.allowances and start.escrow, J0 as an employer (start.wages employer J0: the Payroll
polity form), roster and bilateral forms, could-not vs would-not misses, bond, penalty, notice priced by an exit fee, the forums,
the terms line, and a 3-round zero-attention world where a Board feeds its subscribers and Payrolls pay their workers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charter import generator as GN
from charter import schema as SC
from charter import spec as S

NAMES = ["Ada", "Bo", "Cy", "Di", "Ed", "Fay"]


def world(rounds=3, **start_over):
    """A small established town: J0 with a keeper and a watch (paid by J0 out of its reserve: start.wages employer J0), a shop A1
    (Ada's) with a store S2, a Board open to its members, a Payroll and a Supply Contract; the granary S1 of J0."""
    sp = S.load("charter/specs/survival/base.yaml")
    sp = S.deep_merge(sp, {
        "agents": {"worker": 6, "names": list(NAMES)}, "rounds": rounds, "parallel_calls": 1,
        "institutions": {"unified": True, "grants": True, "succession": True, "office_control": True},
        "jurisdictions": {"enabled": False}, "contracts": {"scripted": False, "max_laws": 5, "max_own": 12},
        "goals": {"explicit": {"Ada": "Wealth"}},
        "life": {"age_structure": "elapsed", "elapsed": [20, 30]},     # nobody dies of old age in these few rounds
    })
    sp["regime"] = {"base": None, "name": "t", "constitution": "assembly"}
    start = {
        "rights": {n: ["vote", "propose"] for n in NAMES},
        "currencies": [{"name": "penny", "issuer": "J0"}],
        "institutions": [
            {"id": "J0", "offices": {
                "keeper": {"title": "Keeper", "holders": ["Cy"], "controls": ["store:S1"], "duties": "Keep the granary."},
                "watch": {"title": "Watch", "holders": ["Ed"], "duties": "Keep the peace."}},
             "treasury": {"penny": 100}},
            {"id": "A1", "name": "Provisions", "founder": "Ada", "members": ["Bo", "Di"], "procedure": "founder",
             "offices": {"head": {"title": "Head", "holders": ["Ada"], "controls": ["treasury", "store:S2"]}},
             "treasury": {"penny": 50}},
        ],
        "stores": [{"id": "S1", "owner": "J0", "food": 30, "capacity": 200},
                   {"id": "S2", "owner": "A1", "food": 40, "capacity": 200}],
        "holdings": {"Bo": {"penny": 20}, "Di": {"penny": 20}, "Fay": {"penny": 10}},
        "wages": [{"employer": "J0", "worker": "office:J0.watch", "item": "penny", "qty": 2},
                  {"employer": "J0", "worker": "Fay", "item": "penny", "qty": 1}],
        "contracts": [
            {"template": "Board", "in": "A1", "params": {"TERMS": {"store": "store:S2", "price": 2, "ration": 1}},
             "allowances": {"Bo": {"penny": 2}, "Di": {"penny": 2}}},
            {"template": "Payroll", "in": "A1", "roster": {"Bo": {"wage": 3}, "Di": {"wage": 2}},
             "params": {"OFFICE": "head"}},
        ],
    }
    start.update(start_over)
    sp["start"] = start
    return sp


class Idle:
    """Zero attention: every agent passes every turn."""

    def act(self, k, a, system, user, n_actions, final):
        return ({"reasoning": "", "actions": [], "notes": "", "goal_guesses_json": "{}"}, "", {})


def run(tmp_path, sp, policy=None, seed=1):
    from charter import agents as AG
    from charter import runner
    inst = GN.generate(sp, seed)
    out = runner.run(inst, policy or Idle(), tmp_path / "run", log=lambda *a: None)
    return inst, Path(out)


def events(run_dir):
    return [json.loads(x) for x in (run_dir / "events.jsonl").read_text().splitlines() if x.strip()]


def kernel_at(run_dir, n):
    from charter import start as STT
    return STT._kernel_at(run_dir, n)[1]


def law_of(k, iid, title):
    return next(l for l in k.w["laws"].values() if l["title"] == title and l.get("jurisdiction", "J0") == iid
                and l["status"] == "active")


def moves(evs, lid, **match):
    return [e["data"] for e in evs if e["type"] == "move" and e["data"].get("why") == f"law:{lid}"
            and all(e["data"].get(x) == v for x, v in match.items())]


def test_the_presets_are_contract_templates_that_check():
    from charter import contracts as KC
    from charter import library as LB
    from charter import standing as SD
    for name in SD.PRESETS:
        e = LB.ESTABLISHED[name]
        assert e["kind"] == "contract" and e["rank"] == "bylaw"
        KC.check_code(e["code"])                                        # an association may run it (no denied function)
        assert set(KC.constants(e["code"])) >= set(SD.BASE)


def test_spec_checks():
    sp = world()
    assert not [e for e in SC.validate(sp) if "start" in e]
    bad = world(contracts=[{"template": "Relief Act", "in": "A1"}, {"template": "Board"}],
                allowances=[{"agent": "Bo", "contract": "A1", "item": "penny"}])
    errs = SC.validate(bad)
    assert any("contracts[0].template" in e for e in errs) and any("contracts[1]" in e and "founder" in e for e in errs)
    assert any("allowances[0]: needs qty" in e for e in errs)
    with pytest.raises(ValueError, match="not a member of A1"):
        GN.generate(world(contracts=[{"template": "Payroll", "in": "A1", "roster": {"Fay": {"wage": 1}}}]), 1)
    with pytest.raises(ValueError, match="founder Ada must be one of its parties"):
        GN.generate(world(contracts=[{"template": "Retainer", "founder": "Ada", "parties": {"Bo": "client", "Cy": "counsel"}}]), 1)


def test_zero_attention_three_rounds_board_feeds_and_payrolls_pay(tmp_path):
    """Framework §11 check 2: 3 rounds with no agent action. The Board feeds its subscribers from the shop's store and charges them;
    the shop's Payroll pays its workers; J0 pays the watch (an office, whoever holds it) and Fay out of its reserve."""
    from charter import accounts as AC
    from charter import agents as AG
    inst, rd = run(tmp_path, world(rounds=3))
    recs = [json.loads(x) for x in (rd / "interventions.jsonl").read_text().splitlines()]
    assert not [r for r in recs if "error" in r], [r for r in recs if "error" in r]
    evs = events(rd)
    k0 = kernel_at(rd, 0)
    board, pay = law_of(k0, "A1", "Board")["id"], law_of(k0, "A1", "Payroll")["id"]
    civil = law_of(k0, "J0", "Payroll")["id"]
    for who in ("Bo", "Di"):
        food = moves(evs, board, dst=who, item="food")
        assert [round(m["qty"], 6) for m in food] == [1.0, 1.0, 1.0], who            # fed every round from S2
        assert all(m["src"] == "store:S2" for m in food)
    paid_in = [e["data"] for e in evs if e["type"] == "contract_pull" and e["data"]["law"] == board]
    assert len(paid_in) == 6 and all(m["qty"] == 2 and m["item"] == "penny" for m in paid_in)   # 2 penny per food, by allowance
    assert not moves(evs, board, dst="Ada")                                            # no allowance: not served, not charged
    assert [m["qty"] for m in moves(evs, pay, dst="Bo")] == [3, 3, 3]
    assert [m["qty"] for m in moves(evs, pay, dst="Di")] == [2, 2, 2]
    assert [m["qty"] for m in moves(evs, civil, dst="Ed")] == [2, 2, 2]               # the watch, by office
    assert [m["qty"] for m in moves(evs, civil, dst="Fay")] == [1, 1, 1]
    assert all(m["src"] == "reserve" for m in moves(evs, civil))
    k3 = kernel_at(rd, 3)
    assert k3.bal(AC.treasury_of(k3, "A1"), "penny") == 50 + 12 - 15
    assert k3.bal("reserve", "penny") == 100 - 9
    v = AG.state_view(k0, "Bo")                                                        # the terms line, from round 1 on
    assert "Board (L" in v and "F: you get 1 food from store S2" in v and "P: you give 2 penny for each food of F to A1's treasury" in v
    assert "Payroll (L" in v and "W: you get 3 penny from A1's treasury" in v and "harvest" not in v.split("Payroll (")[1]
    assert "Payroll (" in AG.state_view(k0, "Ed") and "you are worker" in AG.state_view(k0, "Ed")


# ---------------------------------------------------------------------- driving a kernel by hand from the round-0 world
def setup(tmp_path, sp):
    """The kernel right after the round-0 setup (a one-round idle run's checkpoint 0)."""
    sp["rounds"] = 1
    _, rd = run(tmp_path, sp)
    recs = [json.loads(x) for x in (rd / "interventions.jsonl").read_text().splitlines()]
    assert not [r for r in recs if "error" in r], [r.get("error") for r in recs if "error" in r]
    return kernel_at(rd, 0)


def step(k, n=1):
    for _ in range(n):
        k.end_round()
        k.end_round_cause()
        k.start_round()


def act(k, aid, name, **args):
    from charter import actions as A
    return A.act(k, aid, name, args)


def law(k, iid, title):
    return law_of(k, iid, title)["id"]


def since(k, n0, t=None):
    return [e for e in k.events[n0:] if t is None or e["type"] == t]


# ---------------------------------------------------------------------- Phase 0: paying institutions
def test_agents_and_offices_pay_into_institutions(tmp_path):
    from charter import accounts as AC
    from charter.actions import ActionError
    k = setup(tmp_path, world())
    a1 = AC.treasury_of(k, "A1")
    t0, r0, f0 = k.bal(a1, "penny"), k.bal("reserve", "penny"), k.bal("Fay", "penny")
    n0 = len(k.events)
    assert "into A1's treasury" in act(k, "Fay", "transfer", to="A1", item="penny", qty=3)
    act(k, "Fay", "transfer", to="J0", item="penny", qty=2)
    act(k, "Fay", "transfer", to="assoc:A1", item="penny", qty=1)
    assert k.bal(a1, "penny") == t0 + 4 and k.bal("reserve", "penny") == r0 + 2 and k.bal("Fay", "penny") == f0 - 6
    ev = since(k, n0, "transfer")
    assert [e["data"]["to"] for e in ev] == ["A1", "J0", "A1"] and "Ada" in ev[0]["vis"] and "Bo" in ev[0]["vis"]
    with pytest.raises(ActionError, match="you have only"):
        act(k, "Fay", "transfer", to="A1", item="penny", qty=99)
    out = act(k, "Ada", "transfer", to="J0", item="penny", qty=5, **{"as": "A1"})   # an office pays another institution
    assert "out of A1's" in out and k.bal("reserve", "penny") == r0 + 7 and k.bal(a1, "penny") == t0 - 1
    with pytest.raises(ActionError):
        act(k, "Bo", "transfer", to="J0", item="penny", qty=1, **{"as": "A1"})       # a plain member holds no office
    with pytest.raises(ActionError, match="own treasury"):
        act(k, "Ada", "transfer", to="A1", item="penny", qty=1, **{"as": "A1"})


def test_paying_institutions_is_off_with_the_flag(tmp_path):
    from charter.actions import ActionError
    sp = world()
    sp["contracts"]["pay_institutions"] = False
    k = setup(tmp_path, sp)
    with pytest.raises(ActionError, match="unknown recipient"):
        act(k, "Fay", "transfer", to="A1", item="penny", qty=1)


def test_a_levy_applies_to_payments_into_a_treasury(tmp_path):
    from charter import accounts as AC
    sp = world(laws=[{"template": "Payment Levy", "params": {"ITEM": "penny", "RATE": 0.1}}])
    k = setup(tmp_path, sp)
    t0, f0 = k.bal(AC.treasury_of(k, "A1"), "penny"), k.bal("Fay", "penny")
    act(k, "Fay", "transfer", to="A1", item="penny", qty=5)
    assert k.bal(AC.treasury_of(k, "A1"), "penny") == t0 + 5 and round(f0 - k.bal("Fay", "penny"), 6) == 5.5


def test_a_contract_law_pays_j0_a_grant(tmp_path):
    sp = world(contracts=[{"template": "Grant", "in": "A1", "params": {"TERMS": {"recipient": "J0", "qty": 2}}}])
    k = setup(tmp_path, sp)
    r0 = k.bal("reserve", "penny")
    step(k, 2)
    assert k.bal("reserve", "penny") - r0 == pytest.approx(4 - 2 * 3)  # J0's own payroll pays 3 a round out of it
    lid = law(k, "A1", "Grant")
    got = [e["data"] for e in k.events if e["type"] == "move" and e["data"]["why"] == f"law:{lid}"]
    assert [(m["src"], m["dst"], m["qty"]) for m in got] == [("assoc:A1", "reserve", 2.0)] * 2


# ---------------------------------------------------------------------- Payroll: hire, set_wage, fire; arrears
def test_payroll_office_actions_and_arrears(tmp_path):
    from charter import accounts as AC
    from charter.actions import ActionError
    k = setup(tmp_path, world())
    act(k, "Fay", "join_contract", contract="A1")                       # closed: an applicant
    assert "Applicants to A1: Fay" in __import__("charter.agents", fromlist=["x"]).state_view(k, "Ada")
    act(k, "Ada", "invoke", action="A1.hire", args=["Fay", 2])
    act(k, "Ada", "invoke", action="A1.set_wage", args=["Fay", 4])
    with pytest.raises(ActionError):
        act(k, "Bo", "invoke", action="A1.set_wage", args=["Bo", 9])     # not the head
    b0 = k.bal("Bo", "penny")
    act(k, "Ada", "invoke", action="A1.fire", args=["Bo", 1])           # severance 1; Bo leaves at the end of the round
    assert k.bal("Bo", "penny") == b0 + 1
    pay = law(k, "A1", "Payroll")
    n0 = len(k.events)
    step(k)
    got = {e["data"]["dst"]: e["data"]["qty"] for e in since(k, n0, "move") if e["data"]["why"] == f"law:{pay}"}
    assert got == {"Di": 2.0, "Fay": 4.0}
    assert "Bo" not in AC.assocs(k)["A1"]["members"]
    k.w["institutions"]["A1"]["reserve"]["penny"] = 1.0                 # an empty treasury: wages are owed, paid first later
    step(k)
    st = k.w["laws"][pay]["state"]                                      # 1 + Di's 2 for the Board: Di paid 2, Fay 1 of 4
    assert st["owed"] == {"Fay": {"penny": 3.0}} and "Owed to you: 3 penny" in st["terms_lines"]["Fay"]
    k.w["institutions"]["A1"]["reserve"]["penny"] = 20.0
    step(k)
    assert not k.w["laws"][pay]["state"].get("owed")
    assert "Owed to you" not in k.w["laws"][pay]["state"]["terms_lines"]["Fay"]


# ---------------------------------------------------------------------- Supply: could-not vs would-not, bond, penalty, notice
def supply_world(**extra):
    return world(holdings={"Bo": {"penny": 20, "food": 12}, "Di": {"penny": 20, "food": 2}, "Fay": {"penny": 10}},
                 contracts=[{"template": "Supply Contract", "in": "A1", "roster": {"Bo": {}, "Di": {"qty": 3}},
                             "params": {"TERMS": {"store": "store:S2", "price": 1.5}, "OFFICE": "head", **extra},
                             "allowances": {"Bo": {"food": 4}, "Di": {"food": 3}}, "escrow": {"Bo": {"penny": 5}}}])


def test_supply_delivers_into_the_store_and_pays_per_unit(tmp_path):
    from charter import subsistence as SB
    k = setup(tmp_path, supply_world())
    sup = law(k, "A1", "Supply Contract")
    s0, b0 = SB.state(k)["stores"]["S2"]["holdings"]["food"], k.bal("Bo", "penny")
    k.w["agents"]["Di"]["holdings"]["food"] = 1.0                        # Di keeps 1: it could not deliver (a miss, no breach)
    n0 = len(k.events)
    step(k)
    st = k.w["laws"][sup]["state"]
    assert st["moved"]["Bo"]["D"][1] == 4 and k.bal("Bo", "penny") == b0 + 6
    assert SB.state(k)["stores"]["S2"]["holdings"]["food"] >= s0 + 4 - 3     # (less the shop's own spoilage)
    assert st.get("could", {}).get("Di", {}).get("D") == 1 and not since(k, n0, "contract_breach")
    line = st["terms_lines"]["Bo"]
    assert "D: you give 4 food to store S2 (never below 1)" in line and "P: you get 1.5 penny for each food of D" in line


def test_withdrawn_allowance_is_a_breach_after_grace_with_the_penalty_from_the_bond(tmp_path):
    from charter import accounts as AC
    k = setup(tmp_path, supply_world())
    sup = law(k, "A1", "Supply Contract")
    act(k, "Bo", "set_allowance", contract="A1", item="food", qty=0)    # would not: a strike by allowance
    t0 = k.bal(AC.treasury_of(k, "A1"), "penny")
    n0 = len(k.events)
    step(k)
    assert not since(k, n0, "contract_breach") and k.w["laws"][sup]["state"]["missed"]["Bo"]["D"] == 1
    step(k)
    br = since(k, n0, "contract_breach")
    assert len(br) == 1 and br[0]["agent"] == "Bo" and "penalty 2 penny" in br[0]["data"]["remedy"]
    assert AC.assocs(k)["A1"]["escrow"]["Bo"]["penny"] == 3                  # 5 - PENALTY 2, to the shop's treasury
    assert k.bal(AC.treasury_of(k, "A1"), "penny") >= t0 + 2 - 5 - 5 * 2


def test_leaving_without_notice_costs_the_exit_fee_and_notice_ends_the_terms(tmp_path):
    from charter import accounts as AC
    k = setup(tmp_path, supply_world())
    sup = law(k, "A1", "Supply Contract")
    n0 = len(k.events)
    act(k, "Bo", "leave_contract", contract="A1")
    step(k)
    br = [e for e in since(k, n0, "contract_breach")]
    assert br and "without notice" in br[0]["data"]["clause"] and "exit fee 5 penny" in br[0]["data"]["remedy"]
    assert "Bo" not in AC.assocs(k)["A1"]["members"] and "Bo" not in k.w["laws"][sup]["state"]["roster"]
    k2 = setup(tmp_path / "b", supply_world())
    out = act(k2, "Bo", "invoke", action="A1.supply_notice")
    assert "end after round 3" in out                                    # NOTICE 2: round 1 + 2
    step(k2, 2)
    assert "Bo" in k2.w["laws"][sup]["state"]["roster"]                  # deliveries run through the notice
    step(k2)
    assert "Bo" not in k2.w["laws"][sup]["state"]["roster"] and k2.bal("Bo", "penny") >= 25   # bond refunded
    assert "Bo" in AC.assocs(k2)["A1"]["members"]                        # still a member of the shop: only the terms ended


def test_supply_price_by_the_officer(tmp_path):
    k = setup(tmp_path, supply_world())
    sup = law(k, "A1", "Supply Contract")
    act(k, "Ada", "invoke", action="A1.supply_price", args=["all", 2])
    b0 = k.bal("Bo", "penny")
    step(k)
    assert k.bal("Bo", "penny") == b0 + 8
    assert "set price for everyone from 1.5 to 2" in " ".join(e["data"].get("text", "") for e in k.events
                                                                 if e["type"] == "contract_notice")


# ---------------------------------------------------------------------- bilateral: its own association
def bilateral(**params):
    return world(contracts=[{"template": "Standing Contract", "founder": "Bo", "name": "Bo sells to Fay",
                             "parties": {"Bo": "seller", "Fay": "buyer", **params.pop("extra_parties", {})},
                             "params": params, "allowances": {"Bo": {"food": 4}, "Fay": {"penny": 6}},
                             "escrow": {"Bo": {"penny": 5}, "Fay": {"penny": 5}}}],
                 holdings={"Bo": {"penny": 20, "food": 12}, "Di": {"penny": 20}, "Fay": {"penny": 20}})


def test_bilateral_contract_runs_and_exit_without_notice_pays_the_other_party(tmp_path):
    from charter import accounts as AC
    from charter import agents as AG
    k = setup(tmp_path, bilateral())
    assert AC.assocs(k)["A2"]["members"] == ["Bo", "Fay"]
    lid = AC.assocs(k)["A2"]["laws"][0]
    v = AG.state_view(k, "Fay")
    assert "Standing Contract (" in v and "you are buyer" in v and "L1: you get 4 food" in v
    assert "A2 'Bo sells to Fay'" not in AG.state_view(k, "Di")          # a closed contract with named parties is not listed
    f0, b0 = k.bal("Fay", "food"), k.bal("Bo", "penny")
    step(k)
    st = k.w["laws"][lid]["state"]
    assert st["moved"]["*"]["L1"][1] == 4 and st["moved"]["*"]["L2"][1] == 6 and k.bal("Bo", "penny") == b0 + 6
    n0 = len(k.events)
    bo = k.bal("Bo", "penny")
    act(k, "Fay", "leave_contract", contract="A2")
    step(k)
    br = since(k, n0, "contract_breach")
    assert br and br[0]["agent"] == "Fay" and "without notice" in br[0]["data"]["clause"]
    assert k.bal("Bo", "penny") >= bo + 5 + 5                           # the exit fee, to the other party; Bo's bond back too
    step(k)
    assert AC.assocs(k)["A2"]["status"] == "dissolved"


def test_bilateral_notice_ends_it_and_refunds_bonds(tmp_path):
    from charter import accounts as AC
    k = setup(tmp_path, bilateral())
    act(k, "Fay", "invoke", action="A2.sc_notice")
    step(k)
    lid = AC.assocs(k)["A2"]["laws"][0] if AC.assocs(k)["A2"]["laws"] else None
    step(k)
    assert AC.assocs(k)["A2"]["status"] == "dissolved"
    assert not any(e["type"] == "contract_breach" for e in k.events)


def test_arbiter_forum_awards_from_the_bond(tmp_path):
    from charter import accounts as AC
    k = setup(tmp_path, bilateral(FORUM="arbiter:Cy", GRACE=0, extra_parties={"Cy": "arbiter"}))
    act(k, "Fay", "set_allowance", contract="A2", item="penny", qty=0)   # Fay holds the money but will not pay
    step(k)
    lid = AC.assocs(k)["A2"]["laws"][0]
    claims = k.w["laws"][lid]["state"]["claims"]
    assert claims and claims[0]["against"] == "Fay" and claims[0]["for"] == "Bo"
    b0 = k.bal("Bo", "penny")
    act(k, "Cy", "invoke", action="A2.sc_award", args=[1, 3])
    assert k.bal("Bo", "penny") == b0 + 3 and AC.assocs(k)["A2"]["escrow"]["Fay"]["penny"] == 2
    from charter.actions import ActionError
    with pytest.raises(ActionError):
        act(k, "Bo", "invoke", action="A2.sc_award", args=[1, 3])


def test_court_forum_names_the_victim_only_when_the_bond_falls_short(tmp_path):
    from charter import accounts as AC
    k = setup(tmp_path, bilateral(FORUM="court", GRACE=0, PENALTY={"item": "penny", "qty": 8}))
    act(k, "Fay", "set_allowance", contract="A2", item="penny", qty=0)
    step(k)
    br = [e for e in k.events if e["type"] == "contract_breach"]
    assert br and br[0]["data"].get("victim") == "Bo" and "3 for the court" in br[0]["data"]["remedy"]
    k2 = setup(tmp_path / "b", bilateral(FORUM="court", GRACE=0))
    act(k2, "Fay", "set_allowance", contract="A2", item="penny", qty=0)
    step(k2)
    br = [e for e in k2.events if e["type"] == "contract_breach"]
    assert br and "victim" not in br[0]["data"]


def test_parties_procedure_needs_every_party(tmp_path):
    from charter import accounts as AC
    k = setup(tmp_path, bilateral())
    rec = AC.assocs(k)["A2"]
    lid = rec["laws"][0]
    code = k.w["laws"][lid]["code"].replace("EXIT_FEE = 5", "EXIT_FEE = 1")
    out = act(k, "Bo", "propose_contract_change", contract="A2", code=code, replaces=lid)
    bid = rec["proposals"]["A2-P1"]["ballot"]
    act(k, "Bo", "vote", ballot=bid, choice="yes")
    step(k)
    assert rec["proposals"]["A2-P1"]["status"] == "failed"              # Fay did not vote yes


# ---------------------------------------------------------------------- Quota (J0, compulsory), Charge, start sections
def test_quota_takes_into_the_granary_and_pays(tmp_path):
    from charter import subsistence as SB
    sp = world(contracts=[{"template": "Quota", "in": "J0", "roster": {"Bo": {"quota": 3}, "Di": {}},
                           "params": {"TERMS": {"store": "store:S1"}, "FINE": 1}}],
               holdings={"Bo": {"penny": 20, "food": 12}, "Di": {"penny": 20}, "Fay": {"penny": 10}})
    k = setup(tmp_path, sp)
    q = law(k, "J0", "Quota")
    k.w["agents"]["Di"]["holdings"]["food"] = 2.0
    s0, b0, r0 = SB.state(k)["stores"]["S1"]["holdings"]["food"], k.bal("Bo", "penny"), k.bal("reserve", "penny")
    k.start_round()                                                      # the round's start: what each held (the FINE's test)
    step(k)
    st = k.w["laws"][q]["state"]
    assert st["moved"]["Bo"]["D"][1] == 3 and st["moved"]["Di"]["D"][1] == 1          # Di: only above its keep of 1
    assert k.bal("Bo", "penny") == b0 + 3
    assert "Quota (" in st["terms_lines"]["Bo"] and "you are producer" in st["terms_lines"]["Bo"]


def test_charge_drops_a_member_who_will_not_pay(tmp_path):
    sp = world(contracts=[{"template": "Charge", "in": "A1", "params": {"OPEN": False, "GRACE": 0},
                           "roster": {"Bo": {}, "Di": {}}, "allowances": {"Bo": {"penny": 1}}}])
    k = setup(tmp_path, sp)
    c = law(k, "A1", "Charge")
    step(k)
    ros = k.w["laws"][c]["state"]["roster"]
    assert "Bo" in ros and "Di" not in ros                               # Di would not pay: dropped (ON_BREACH drop)


def test_top_level_allowances_and_escrow(tmp_path):
    from charter import accounts as AC
    sp = world(allowances=[{"agent": "Bo", "contract": "A1", "item": "food", "qty": 2}],
               escrow=[{"agent": "Di", "contract": "A1", "item": "penny", "qty": 4}])
    k = setup(tmp_path, sp)
    rec = AC.assocs(k)["A1"]
    assert rec["allowances"]["Bo"]["food"] == 2 and rec["escrow"]["Di"]["penny"] == 4 and k.bal("Di", "penny") == 16
    with pytest.raises(ValueError, match="not an association founded in start"):
        GN.generate(world(escrow=[{"agent": "Di", "contract": "A7", "item": "penny", "qty": 4}]), 1)


# ---------------------------------------------------------------------- leg kinds: harvest (piece rate), duty, indexing; scale
def test_piece_rate_pays_per_unit_of_the_harvest_share(tmp_path):
    sp = world(camp_rights=[{"resource": "copper", "members": "A1", "exclusive": True}],
               contracts=[{"template": "Payroll", "in": "A1", "roster": {"Bo": {"wage": 2, "basis": "piece", "cut": 0.5}},
                           "params": {"OFFICE": "head"}}])
    k = setup(tmp_path, sp)
    pay = law(k, "A1", "Payroll")
    camp = next(c for c, v in k.w["camps"].items() if v.get("resource") == "copper" and f"harvest:{c}" in
                k.w["agents"]["Bo"]["rights"])
    c = k.w["camps"][camp]
    x = [1] * c["dials"] if c.get("dials") else [1]
    from charter import accounts as AC
    t0 = k.bal(AC.treasury_of(k, "A1"), "copper")
    act(k, "Bo", "harvest", camp=camp, x=x)                               # a sealed input: harvested at the end of the round
    b0 = k.bal("Bo", "penny")
    step(k)
    moved = k.w["laws"][pay]["state"]["moved"]["Bo"]
    took = moved["O"][1]
    assert took > 0 and k.bal(AC.treasury_of(k, "A1"), "copper") == pytest.approx(t0 + took)
    assert moved["R"][1] == pytest.approx(2 * took) and k.bal("Bo", "penny") == pytest.approx(b0 + 2 * took)
    assert "W" not in moved                                               # piece basis: no salary


def test_duty_leg_and_indexed_wage(tmp_path):
    sp = world(contracts=[{"template": "Standing Contract", "founder": "Bo", "parties": {"Bo": "crier", "Fay": "patron"},
                           "params": {"LEGS": [{"id": "D", "kind": "duty", "from": "crier", "to": "patron", "check": "act:post"},
                                               {"id": "F", "from": "patron", "to": "crier", "item": "penny", "qty": 1,
                                                "per": "D"}],
                                      "GRACE": 0, "BOND": {}, "PENALTY": {"item": "penny", "qty": 1}},
                           "allowances": {"Fay": {"penny": 1}}, "escrow": {"Bo": {"penny": 2}}}],
               holdings={"Bo": {"penny": 20}, "Di": {"penny": 20}, "Fay": {"penny": 20}})
    k = setup(tmp_path, sp)
    act(k, "Bo", "post", text="Hear ye: the market opens at dawn.")
    b0 = k.bal("Bo", "penny")
    step(k)
    assert k.bal("Bo", "penny") == b0 + 1                                 # the duty done: paid
    n0 = len(k.events)
    step(k)                                                               # no post: a would-not duty miss, a breach (grace 0)
    br = since(k, n0, "contract_breach")
    assert br and br[0]["agent"] == "Bo" and "D" in br[0]["data"]["clause"]


def test_scale_twenty_subscribers_and_workers_within_gas(tmp_path):
    names = [f"N{i:02d}" for i in range(22)]
    sp = world(rounds=1)
    sp["agents"] = {**sp["agents"], "worker": 22, "names": names}
    sp["goals"]["explicit"] = {}
    st = sp["start"]
    st["rights"] = {n: ["vote", "propose"] for n in names}
    st["institutions"][0]["offices"] = {"watch": {"title": "Watch", "holders": names[:3]}}
    st["institutions"][1].update({"founder": names[0], "members": names[1:], "offices": {"head": {"holders": [names[0]],
                                                                                               "controls": ["treasury", "store:S2"]}}})
    st["institutions"][1]["treasury"] = {"penny": 500}
    st["holdings"] = {n: {"penny": 20} for n in names}
    st["wages"] = [{"employer": "J0", "worker": "office:J0.watch", "item": "penny", "qty": 2}]
    st["contracts"] = [{"template": "Board", "in": "A1", "params": {"TERMS": {"store": "store:S2"}},
                        "allowances": {n: {"penny": 2} for n in names}},
                       {"template": "Payroll", "in": "A1", "roster": {n: {"wage": 3} for n in names}}]
    st["stores"][1]["food"] = 100
    _, rd = run(tmp_path, sp)
    recs = [json.loads(x) for x in (rd / "interventions.jsonl").read_text().splitlines()]
    assert not [r for r in recs if "error" in r]
    evs = events(rd)
    assert not [e for e in evs if e["type"] in ("contract_law_error", "law_error")], \
        [e["data"] for e in evs if e["type"] in ("contract_law_error", "law_error")][:2]
    k = kernel_at(rd, 1)
    board, pay = law(k, "A1", "Board"), law(k, "A1", "Payroll")
    assert len(moves(evs, board, item="food")) == 22 and len(moves(evs, pay)) == 22
    assert len(moves(evs, law(k, "J0", "Payroll"))) == 3


# ---------------------------------------------------------------------- the Licence template (one gate for camps, posts, forges)
def test_licence_gates_posting_by_right_roster_registrar_and_fee(tmp_path):
    from charter.actions import ActionError
    sp = world(channels=[{"id": "market", "owner": "J0", "by": "Cy", "purpose": "prices", "readers": {"all": True},
                          "writers": {"all": True}}],
               laws=[{"template": "Licence", "params": {"GATES": ["post"], "TARGETS": ["market"], "RIGHT": "trader",
                                                         "REGISTRAR": "J0.keeper", "HOLDERS_FROM": "roster:A1", "FEE": 2,
                                                         "TAG": "trade"}}])
    k = setup(tmp_path, sp)
    act(k, "Bo", "post", channel="market", text="SELL 2 food @ 2 penny")              # a member of A1: licensed by membership
    with pytest.raises(ActionError, match="needs a licence"):
        act(k, "Fay", "post", channel="market", text="SELL 1 food @ 1 penny")
    act(k, "Fay", "post", text="the square is free")                                   # other posts are not gated
    act(k, "Cy", "invoke", action="trade_issue", args=["Fay"])                        # the Registrar's licence
    act(k, "Fay", "post", channel="market", text="SELL 1 food @ 1 penny")
    with pytest.raises(ActionError):
        act(k, "Di", "invoke", action="trade_issue", args=["Ed"])                     # not the Registrar
    r0 = k.bal("reserve", "penny")
    k.w["agents"]["Ed"]["holdings"]["penny"] = 5.0
    act(k, "Ed", "invoke", action="trade_apply")                                     # bought for the fee
    assert k.bal("reserve", "penny") == r0 + 2 and k.has("Ed", "trader")
    act(k, "Cy", "invoke", action="trade_revoke", args=["Fay", "fraud"])
    with pytest.raises(ActionError, match="needs a licence"):
        act(k, "Fay", "post", channel="market", text="again")
    lid = law(k, "J0", "Licence")
    assert [r["event"].split(" ")[0] for r in k.w["laws"][lid]["public"]["register"]] == ["issued", "bought", "revoked"]
