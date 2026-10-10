"""The law surface over subsistence and reproduction (review 15 S6, §3.4, §4.7; review 19 §7; D-42): the law reads (minors,
gestations, food_totals, forest, hunger), the hooks the templates rely on (before_conceive for both parents, after_begin_life with
both parents, before_withdraw, before_hunt, before_harvest, before_cast_vote, on_round_end before the ration), store scoping for
polity laws, and every food and family template of the library (charter/library.py FOOD_TEMPLATES) enacted in a scripted world
with its effect checked. No model calls."""
from __future__ import annotations

import pytest

from charter import accounts as AC
from charter import actions as A
from charter import contracts as KC
from charter import generator
from charter import library as LB
from charter import life as LF
from charter import mortality as MO
from charter import pairs as PR
from charter import spec as S
from charter import subsistence as SB
from charter.kernel import Kernel

SMALL = "agents={worker: 8, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 1}"
SOC = ["subsistence.enabled=true", "law.v2=true", "contracts.enabled=true"]
PAIRS = SOC + ["life.reproduction.mode=pairs"]
STILL = ["subsistence.ration=0", "subsistence.spoil=0", "subsistence.store_spoil=0"]   # no eating, no spoilage: exact balances


def world(extra=(), seed=3, rounds=20, preset="society"):
    sp = S.apply_overrides(S.load(preset), [f"rounds={rounds}", "shared_archive.enabled=false", SMALL, *extra])
    inst = generator.generate(sp, seed)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return inst, k


def end_round(k):
    k.begin_round_cause(k.r, "round_start")
    k.start_round()
    k.phase("end_of_round")
    k.end_round()
    k.end_round_cause()


def start(k):
    k.begin_round_cause(k.r, "round_start")
    k.start_round()


def finish(k):
    k.phase("end_of_round")
    k.end_round()
    k.end_round_cause()


def set_food(k, aid, q):
    h = k.w["agents"][aid]["holdings"]
    h.pop("food", None)
    if q:
        h["food"] = float(q)


def eaters(k):
    return SB.eaters(k)


def enact(k, name, **params):
    lid = k.new_law(LB.instantiate(name, params), "tester")
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active", k.w["laws"][lid]
    return lid


def found(k, founder, name, **params):
    before = set(AC.assocs(k))
    A.act(k, founder, "create_contract", {"name": name, "code": LB.instantiate(name, params)})
    return next(iter(set(AC.assocs(k)) - before))


def builder(k, aid):
    k._add(aid, "timber", 10)
    k._add(aid, "stone", 6)


def forest(k):
    return SB.forest_camps(k)[0]


def conceive(k, a, b):
    A.act(k, a, "conceive", {"partner": b})
    return A.act(k, b, "conceive", {"partner": a})


def born_child(k, gid="G1"):
    for _ in range(4):
        g = PR.state(k)["gestations"][gid]
        if g["status"] == "born":
            return g["child"]
        end_round(k)
    raise AssertionError("not born")


def family(extra=()):
    """A pairs world with one child born to the first two eaters (food plentiful)."""
    inst, k = world(PAIRS + list(extra))
    a, b = eaters(k)[:2]
    for x in eaters(k):
        set_food(k, x, 30)
    conceive(k, a, b)
    c = born_child(k)
    return inst, k, a, b, c


# ---------------------------------------------------------------------- the library entries and where they are listed
def test_every_template_checks_and_is_listed_only_where_its_needs_hold():
    names = set(LB.FOOD_TEMPLATES)
    assert {"Relief Act", "Granary Charter", "Household", "Child Support", "Guardianship", "Cooperative", "Day Labour", "Food Levy",
            "One-Child Law", "Birth Licence", "Hunger Disenfranchisement", "Hunting Season", "Hunting Quota", "Forest Territory",
            "Common-pool Management"} == names
    assert not names & (set(LB.TOOLKIT) | set(LB.CONTRACT_TEMPLATES) | set(LB.LIB))
    for e in LB.FOOD_TEMPLATES.values():
        if e["kind"] == "contract":
            KC.check_code(e["code"])
        assert LB.code(e["name"]) == e["code"] and LB.info2(e["name"])["params"] == LB.params(e["name"])
        assert "intent" in e["code"] and e["doc"]
    from charter import actions as AA
    plain = S.apply_overrides(S.load("society"), ["law.v2=true", "contracts.enabled=true", "shared_archive.enabled=false"])
    assert LB.food_templates(plain) == []
    sub = S.apply_overrides(plain, ["subsistence.enabled=true"])
    got = {e["name"] for e in LB.food_templates(sub)}
    assert "Relief Act" in got and "Granary Charter" in got and "Child Support" not in got and "Birth Licence" not in got
    pairs = S.apply_overrides(sub, ["life.reproduction.mode=pairs"])
    assert {"Child Support", "Guardianship", "Birth Licence", "One-Child Law"} <= {e["name"] for e in LB.food_templates(pairs)}
    inst, k = world(SOC)
    assert "Relief Act" in AA.library_index(inst) and "Child Support" not in AA.library_index(inst)
    inst2 = generator.generate(plain, 3)
    assert not set(AA.library_index(inst2)) & names
    tk = S.apply_overrides(plain, ["law.library.edition=2", "law.library.access=catalogue", "law.library.toolkit=all"])
    assert "Food and family templates" not in LB.catalogue_text(tk)
    assert "Food and family templates" in LB.catalogue_text(S.apply_overrides(tk, ["subsistence.enabled=true"]))


def test_a_template_instantiates_with_new_constants():
    src = LB.instantiate("Relief Act", {"BUDGET": 9, "STAGES": ["starving"]})
    assert "BUDGET = 9" in src and "STAGES = ['starving']" in src
    from charter import regimes as RG
    assert "BUDGET = 9" in RG.template_code("Relief Act", {"BUDGET": 9})


# ---------------------------------------------------------------------- reads and hooks
def test_reads_minors_gestations_and_food_totals():
    inst, k = world(PAIRS + STILL)
    a, b = eaters(k)[:2]
    for x in eaters(k):
        set_food(k, x, 20)
    lid = enact(k, "One-Child Law", MAX_CHILDREN=3)
    api = k.api_for(lid)
    assert api["gestations"]() == [] and api["minors"]() == []
    conceive(k, a, b)
    assert api["gestations"]() == [{"id": "G1", "parents": [a, b], "due": k.r + 2, "polity": None}]
    c = born_child(k)
    m = api["minors"]()
    assert [x["agent"] for x in m] == [c] and m[0]["parents"] == [a, b] and m[0]["adult_at"] > k.r
    assert api["gestations"]() == [] and sorted(api["parents_of"](c)) == sorted([a, b]) and api["children_of"](a) == [c]
    tot = api["food_totals"]()
    assert tot["agents"] == pytest.approx(sum(k.bal(x, "food") for x in eaters(k)))
    assert tot["total"] == pytest.approx(tot["agents"] + tot["stores"] + tot["other"])
    assert api["hunger"](a) == "fed" and api["forest"](forest(k))["game"] in ("plentiful", "fair", "scarce", "very scarce")


BIRTH_WATCH = '''title = "Birth Register"
intent = "Records both parents of every child born."
def after_begin_life(p, chain):
    if p["how"] == "born":
        public.setdefault("born", {})[p["agent"]] = sorted(parents_of(p["agent"]))
'''


def test_a_law_sees_a_birth_with_both_parents():
    inst, k = world(PAIRS)
    a, b = eaters(k)[:2]
    for x in (a, b):
        set_food(k, x, 20)
    lid = k.new_law(BIRTH_WATCH, "tester")
    k.enact(lid)
    conceive(k, a, b)
    c = born_child(k)
    assert k.w["laws"][lid]["public"]["born"][c] == sorted([a, b])


NO_KIDS_FOR_B = '''title = "No"
intent = "Refuses every conception."
def before_conceive(p, chain):
    return {"block": True, "reason": "no"}
'''


def test_before_conceive_binds_the_accepting_parents_laws_too(monkeypatch):
    from charter import jurisdictions as J
    inst, k = world(PAIRS)
    a, b = eaters(k)[:2]
    for x in (a, b):
        set_food(k, x, 20)
    lid = k.new_law(NO_KIDS_FOR_B, "tester")
    k.enact(lid)
    real = J.binds
    monkeypatch.setattr(J, "binds", lambda k_, l, x: (x == b) if l == lid else real(k_, l, x))   # the law binds only b
    A.act(k, a, "conceive", {"partner": b})                                # a's offer: no change, nothing to refuse
    with pytest.raises(A.ActionError, match="blocked by law|refuses this conception"):
        A.act(k, b, "conceive", {"partner": a})                            # b accepts: a is the subject, b's law still sees it


def test_a_polity_law_reaches_a_members_store_and_its_own():
    inst, k = world(SOC + STILL)
    a = eaters(k)[0]
    builder(k, a)
    A.act(k, a, "build", {"kind": "store"})
    k._add("store:S1", "food", 4)
    lid = enact(k, "Relief Act")
    api = k.api_for(lid)
    assert api["move"]("store:S1", "reserve", "food", 1) is True          # a member's store: the polity binds its owner
    assert k.bal("store:S1", "food") == pytest.approx(3)


# ---------------------------------------------------------------------- relief, levies, the franchise
def test_relief_act_feeds_the_starving_first_up_to_its_budget():
    inst, k = world(SOC)
    enact(k, "Relief Act", BUDGET=2)
    k._add("reserve", "food", 50)
    x, y, z = eaters(k)[:3]
    for v in eaters(k):
        set_food(k, v, 5)
    for v, st in ((x, -2), (y, 0), (z, -1)):
        set_food(k, v, 0)
        SB.state(k)["stage"][v], SB.state(k)["missed"][v] = st, -st
    end_round(k)
    assert SB.stage(k, x) == -1 and SB.stage(k, z) == 0                    # relieved, then ate (one stage up)
    assert SB.stage(k, y) == -1                                            # the budget ran out before the fed
    assert k.bal("reserve", "food") == pytest.approx(48 * 0.85)            # (the treasury's food spoils too)
    rows = k.w["laws"][[l for l in k.w["law_order"] if k.w["laws"][l]["title"] == "Relief Act"][0]]["public"]["relief"]
    assert [p["agent"] for p in rows[-1]["paid"]] == [x, z]


def test_relief_act_draws_on_the_polity_store_first():
    inst, k = world(SOC)
    a, b = eaters(k)[:2]
    builder(k, a)
    A.act(k, a, "build", {"kind": "store", "owner": "J0"})
    k._add("store:S1", "food", 5)
    enact(k, "Relief Act", STORE="S1")
    set_food(k, b, 0)
    end_round(k)
    assert SB.stage(k, b) == 0 and k.bal("store:S1", "food") < 5


def test_food_levy_confiscates_from_holdings_and_stores_and_rations_withdrawals():
    inst, k = world(SOC + STILL)
    a, b, c = eaters(k)[:3]
    for v in eaters(k):
        set_food(k, v, 0)
    set_food(k, a, 12)
    set_food(k, b, 2)
    builder(k, c)
    A.act(k, c, "build", {"kind": "store"})
    k._add("store:S1", "food", 10)
    t0 = k.bal("reserve", "food")
    enact(k, "Food Levy", RATE=0.5, WITHDRAW_CAP=1)
    end_round(k)
    assert k.bal(a, "food") == pytest.approx(7) and k.bal(b, "food") == pytest.approx(2)   # half of what is above KEEP 2
    assert k.bal("store:S1", "food") == pytest.approx(5)                                   # half of the member's store
    assert k.bal("reserve", "food") - t0 == pytest.approx(10)
    assert A.act(k, c, "withdraw", {"store": "S1", "qty": 1}).startswith("Took 1 food")
    with pytest.raises(A.ActionError, match="rations stores"):
        A.act(k, c, "withdraw", {"store": "S1", "qty": 1})
    end_round(k)
    assert A.act(k, c, "withdraw", {"store": "S1", "qty": 1}).startswith("Took 1 food")    # a new round, a new ration


BALLOT = '''title = "Ballot"
intent = "A test ballot."
def on_enact():
    pass
'''


def test_the_starving_vote_unless_a_law_disenfranchises_them():
    inst, k = world(SOC)
    a, b = eaters(k)[:2]
    lid = k.new_law(BALLOT, "tester")
    k.enact(lid)
    SB.state(k)["stage"][a] = -2
    bid = k.api_for(lid)["open_ballot"]("q", [a, b], ["yes", "no"])
    assert A.act(k, a, "vote", {"ballot": bid, "choice": "yes"}).startswith("Voted")   # physics: the starving vote
    dis = enact(k, "Hunger Disenfranchisement")
    bid = k.api_for(lid)["open_ballot"]("q2", [a, b], ["yes", "no"])
    with pytest.raises(A.ActionError, match="may not vote"):
        A.act(k, a, "vote", {"ballot": bid, "choice": "yes"})
    assert A.act(k, b, "vote", {"ballot": bid, "choice": "yes"}).startswith("Voted")


# ---------------------------------------------------------------------- children
def test_child_support_takes_from_the_parents_and_the_treasury_feeds_orphans():
    inst, k, a, b, c = family(["life.reproduction.household=false"])
    end_round(k)
    set_food(k, c, 0)
    set_food(k, a, 5)
    set_food(k, b, 9)
    end_round(k)
    assert SB.stage(k, c) == -1                                            # no household draw, no law: the child hungers
    enact(k, "Child Support", SUPPORT=1.5)
    set_food(k, c, 0)
    end_round(k)
    assert SB.stage(k, c) == 0 and k.bal(c, "food") == pytest.approx(0.5 * 0.85)   # 1.5 from b (the richer), ate 1
    row = k.w["laws"][k.w["law_order"][-1]]["public"]["support"][-1]["rows"][0]
    assert row["child"] == c and row["parents"] == pytest.approx(1.5) and row["treasury"] == 0
    for p in (a, b):
        assert MO.disable(k, p, "accident")
    k._add("reserve", "food", 10)
    set_food(k, c, 0)
    end_round(k)
    assert SB.stage(k, c) == 0                                             # an orphan, fed from the treasury


def test_guardianship_assigns_the_richest_fed_member_and_passes_on_the_duty():
    inst, k, a, b, c = family(["life.reproduction.household=false"])
    lid = enact(k, "Guardianship", FAIL_LIMIT=1)
    for p in (a, b):
        assert MO.disable(k, p, "accident")
    others = [x for x in eaters(k) if x not in (a, b, c)]
    for x in others:
        set_food(k, x, 3)
    rich, second = others[0], others[1]
    set_food(k, rich, 20)
    set_food(k, second, 10)
    set_food(k, c, 0)
    end_round(k)
    book = k.w["laws"][lid]["public"]["guardians"]
    assert book == {c: rich} and SB.stage(k, c) == 0
    assert any(e["type"] in ("notify", "notice") or rich in str(e.get("data")) for e in k.events)
    set_food(k, rich, 0)                                                    # the guardian cannot feed its ward: replaced
    set_food(k, c, 0)
    end_round(k)
    assert k.w["laws"][lid]["public"]["guardians"][c] == second


def test_one_child_law_caps_children_through_birth_rules():
    inst, k = world(PAIRS)
    a, b, c = eaters(k)[:3]
    for x in (a, b, c):
        set_food(k, x, 30)
    lid = enact(k, "One-Child Law")
    assert LF.state(k)["rules"][lid]["max_children"] == 1
    conceive(k, a, b)
    born_child(k)
    for x in (a, c):
        set_food(k, x, 30)
    A.act(k, c, "conceive", {"partner": a})
    with pytest.raises(A.ActionError, match="forbids"):
        A.act(k, a, "conceive", {"partner": c})
    k.api_for(lid)["set_birth_rules"]()                                     # lifting it (what on_repeal does)
    assert lid not in (LF.state(k).get("rules") or {})


def test_birth_licence_gates_conception_and_is_used_up():
    inst, k = world(PAIRS)
    a, b = eaters(k)[:2]
    for x in (a, b):
        set_food(k, x, 30)
    enact(k, "Birth Licence", FEE=2)
    A.act(k, a, "conceive", {"partner": b})
    with pytest.raises(A.ActionError, match="blocked by law|refuses this conception"):
        A.act(k, b, "conceive", {"partner": a})
    t0 = k.bal("reserve", "food")
    for x in (a, b):
        assert "issued" in A.act(k, x, "invoke", {"action": "apply_birth_licence", "args": []})
    assert k.bal("reserve", "food") - t0 == pytest.approx(4)
    conceive(k, a, b)
    assert PR.gestation_of(k, a) is not None
    assert "birth_licence" not in k.w["agents"][a]["rights"] and "birth_licence" not in k.w["agents"][b]["rights"]


# ---------------------------------------------------------------------- associations
def test_granary_charter_duties_arrears_and_withdrawal_rules():
    inst, k = world(SOC)
    a, b, c, d = eaters(k)[:4]
    cid = found(k, a, "Granary Charter", GRACE=1, DRAW=1, FEED=False)
    for x in (b, c):
        A.act(k, x, "join_contract", {"contract": cid})
    builder(k, a)
    A.act(k, a, "build", {"kind": "store", "owner": cid})
    for x in (a, b, c, d):
        set_food(k, x, 10)
    for x in (a, b):
        A.act(k, x, "transfer", {"to": "store:S1", "item": "food", "qty": 2})   # duty paid in
    end_round(k)
    assert law_of(k, cid)["state"]["arrears"] == {a: 0, b: 0, c: 1}
    assert [x["member"] for x in KC.recs(k)[cid]["breaches"]] == [c]
    assert A.act(k, b, "withdraw", {"store": "S1", "qty": 1}).startswith("Took 1 food")
    with pytest.raises(A.ActionError, match="at most 1 food a round"):
        A.act(k, b, "withdraw", {"store": "S1", "qty": 1})
    with pytest.raises(A.ActionError, match="good standing"):
        A.act(k, c, "withdraw", {"store": "S1", "qty": 1})                 # in arrears
    with pytest.raises(A.ActionError, match="good standing"):
        A.act(k, d, "withdraw", {"store": "S1", "qty": 1})                 # not a member


def J_of(k, lid):
    from charter import jurisdictions as J
    return J.law_jur(k, lid)


def law_of(k, cid):
    return k.w["laws"][[l for l in k.w["law_order"] if J_of(k, l) == cid][0]]


def test_granary_charter_takes_duty_by_allowance_and_feeds_members_short_of_a_meal():
    inst, k = world(SOC)
    a, b = eaters(k)[:2]
    cid = found(k, a, "Granary Charter")
    A.act(k, b, "join_contract", {"contract": cid})
    builder(k, a)
    A.act(k, a, "build", {"kind": "store", "owner": cid})
    set_food(k, a, 10)
    A.act(k, a, "set_allowance", {"contract": cid, "item": "food", "qty": 1})
    k._add("store:S1", "food", 5)
    set_food(k, b, 0)
    end_round(k)
    assert law_of(k, cid)["state"]["arrears"][a] == 0 and law_of(k, cid)["state"]["arrears"][b] == 1
    assert SB.stage(k, b) == 0                                             # one arrear < GRACE 2: still fed from the granary


def test_household_pools_surplus_and_feeds_members_and_their_children():
    inst, k, a, b, c = family(["life.reproduction.household=false"])
    d = [x for x in eaters(k) if x not in (a, b, c)][0]
    cid = found(k, d, "Household", KEEP=2)
    A.act(k, a, "join_contract", {"contract": cid})
    for x in (d, a):
        A.act(k, x, "set_allowance", {"contract": cid, "item": "food", "qty": 20})
    set_food(k, d, 10)
    set_food(k, a, 0)
    set_food(k, b, 0)
    set_food(k, c, 0)
    end_round(k)
    assert SB.stage(k, a) == 0 and SB.stage(k, c) == 0                     # a member and a member's minor child
    assert SB.stage(k, b) == -1                                            # not a member, not a child of one: not fed
    A.act(k, d, "leave_contract", {"contract": cid})                        # (applied at the end of the round)
    n = len(k.events)
    end_round(k)
    back = [e for e in k.events[n:] if e["type"] == "move" and e["data"].get("src") == KC.treasury_key(cid)
            and e["data"].get("dst") == d]
    meals, exit_ = [e["data"]["qty"] for e in back[:-1]], back[-1]["data"]["qty"]
    left = k.bal(KC.treasury_key(cid), "food")                              # half its net contribution (8 put in, less its meal),
    assert exit_ > 1 and (exit_ == pytest.approx(0.5 * (8 - sum(meals))) or left == pytest.approx(0))   # or all the pot holds


def test_cooperative_shares_and_pro_rata_payout():
    inst, k = world(SOC + STILL)
    a, b = eaters(k)[:2]
    cid = found(k, a, "Cooperative", PERIOD=1, PAYOUT=1.0)
    A.act(k, b, "join_contract", {"contract": cid})
    set_food(k, a, 6)
    set_food(k, b, 2)
    A.act(k, a, "set_allowance", {"contract": cid, "item": "food", "qty": 3})
    A.act(k, b, "set_allowance", {"contract": cid, "item": "food", "qty": 1})
    end_round(k)
    sh = law_of(k, cid)["public"]["shares"]
    assert sh == {a: 3.0, b: 1.0}
    assert k.bal(a, "food") == pytest.approx(3 + 3) and k.bal(b, "food") == pytest.approx(1 + 1)   # 4 paid back 3:1


def test_day_labour_pays_food_wages_for_harvests_and_takes_the_output():
    inst, k = world(SOC + STILL)
    a, b, c = eaters(k)[:3]
    cid = found(k, a, "Day Labour", WAGE=1)
    for x in (b, c):
        A.act(k, x, "join_contract", {"contract": cid})
    set_food(k, a, 10)
    A.act(k, a, "deposit_escrow", {"contract": cid, "item": "food", "qty": 5})
    A.act(k, b, "set_allowance", {"contract": cid, "item": "food", "qty": 20})
    for x in (b, c):
        set_food(k, x, 0)
    f = forest(k)
    A.act(k, b, "harvest", {"camp": f})
    A.act(k, c, "harvest", {"camp": f})
    got_c = k.bal(c, "food")
    end_round(k)
    pay = law_of(k, cid)["public"]["payroll"]
    assert pay["paid"] == {b: 1} and pay["unpaid"] == []
    assert k.bal(b, "food") == pytest.approx(1)                            # its forage went to the employer, the wage stays
    assert k.bal(c, "food") == pytest.approx(got_c)                        # withheld its output: kept it, no wage, a breach
    assert k.bal(a, "food") > 5


# ---------------------------------------------------------------------- forests (review 19 §7)
def test_hunting_season_closes_the_hunt_not_the_forage():
    inst, k = world(SOC)
    a = eaters(k)[0]
    f = forest(k)
    enact(k, "Hunting Season", CLOSED_ROUNDS=[k.r], CLOSE_WHEN=["very scarce"])
    with pytest.raises(A.ActionError, match="closed season"):
        A.act(k, a, "hunt", {"camp": f})
    assert A.act(k, a, "harvest", {"camp": f}).startswith("Foraged")
    end_round(k)
    start(k)
    assert A.act(k, a, "hunt", {"camp": f}).startswith("You hunt")
    g = k.w["camps"][f]["game"]
    g["G"] = 0.05 * g["K"]
    b = eaters(k)[1]
    with pytest.raises(A.ActionError, match="very scarce"):
        A.act(k, b, "hunt", {"camp": f})


def test_hunting_quota_caps_entries_and_game_per_period_and_seizes_the_excess():
    inst, k = world(SOC)
    a = eaters(k)[0]
    f = forest(k)
    lid = enact(k, "Hunting Quota", MAX_HUNTS=1, MAX_GAME=10, PERIOD=5, SEIZE_EXCESS=True)
    assert A.act(k, a, "hunt", {"camp": f}).startswith("You hunt")
    with pytest.raises(A.ActionError, match="at most 1 hunt"):
        A.act(k, a, "hunt", {"camp": f})
    b = eaters(k)[1]
    t0 = k.bal("reserve", "food")
    with k.cause("world", "hunt", root=True):                              # the hunt's payout at the round's end
        k.apply("harvest", agent=b, camp=f, x=[], item="food", qty=12, via="typed")
    assert k.bal("reserve", "food") - t0 == pytest.approx(2)
    with pytest.raises(A.ActionError, match="your 10 food of game"):
        A.act(k, b, "hunt", {"camp": f})
    A.act(k, b, "harvest", {"camp": f})                                    # foraging is not game
    assert k.w["laws"][lid]["state"]["game"]["by"][b] == pytest.approx(12)


def test_forest_territory_binds_members_only():
    inst, k = world(SOC)
    a, b = eaters(k)[:2]
    f = forest(k)
    enact(k, "Forest Territory", FOREIGN=[f])
    with pytest.raises(A.ActionError, match="another polity's forest"):
        A.act(k, a, "hunt", {"camp": f})
    with pytest.raises(A.ActionError, match="another polity"):
        A.act(k, a, "harvest", {"camp": f})
    assert k.w["camps"][f]["harvested_this_round"] == 0 and a not in SB.state(k)["forage"]   # refused: nothing taken or counted
    from charter import jurisdictions as J
    k.w["jur"]["member"].pop(b)                                             # b belongs to no polity: the law cannot reach it
    assert J.member_of(k, b) is None
    assert A.act(k, b, "hunt", {"camp": f}).startswith("You hunt")
    assert A.act(k, b, "harvest", {"camp": f}).startswith("Foraged")


def test_common_pool_management_ties_the_quota_to_the_stock():
    inst, k = world(SOC)
    f = forest(k)
    lid = enact(k, "Common-pool Management", PER_MEMBER=1.3, TARGET=0.6, FLOOR_SHARE=0.3)
    n = len([a for a in eaters(k)])
    start(k)
    full = k.w["laws"][lid]["public"]["quotas"][f]
    finish(k)
    c = k.w["camps"][f]
    c["S"] = 0.12 * c["K"]
    start(k)
    low = k.w["laws"][lid]["public"]["quotas"][f]
    assert low < full and low == max(1, int(1.3 * n * 0.3 + 0.5)) and c["quota"] == low
    users = eaters(k)
    c["game"]["G"] = 0.05 * c["game"]["K"]
    with pytest.raises(A.ActionError, match="very scarce"):
        A.act(k, users[0], "hunt", {"camp": f})
    for x in users[:low]:
        A.act(k, x, "harvest", {"camp": f})
    with pytest.raises(A.ActionError, match="quota"):
        A.act(k, users[low], "harvest", {"camp": f})


def test_a_forest_counts_its_polity_quota_per_jurisdiction(monkeypatch):
    from charter import jurisdictions as J
    inst, k = world(SOC)
    a = eaters(k)[0]
    f = forest(k)
    monkeypatch.setattr(J, "camp_rules", lambda k_, aid, camp: {"quota": 0, "harvest_limit": None, "fee": None,
                                                                 "qkey": f"J9|{camp}", "reserve": "reserve:J9"})
    with pytest.raises(A.ActionError, match="quota"):
        A.act(k, a, "harvest", {"camp": f})
