"""Camp types (camps.model: types): the registry and interface, each type's payout rule, sealed inputs, every modifier,
participation, leasing, run composition, resources and upkeep, legacy unchanged, records and dry runs."""
from __future__ import annotations

import json
import math

import pytest

from charter import actions as A
from charter import camps as C
from charter import generator
from charter import lawlang as L
from charter import resources as RS
from charter import runner
from charter import spec as S
from charter import agents as AG
from charter.camptypes import TYPES, CampType, load_all
from charter.camptypes import framework as CT
from charter.camptypes import harness as HN
from charter.camptypes import modifiers as M
from charter.kernel import Kernel


def _quiet(k, cid):
    """No noise and a full stock: payouts are exact."""
    c = k.w["camps"][cid]
    c["sigma"], c["S"] = 0.0, c["K"]
    return c


def _events(k, typ, since=0):
    return [e for e in k.events[since:] if e["type"] == typ]


# ------------------------------------------------------------------ registry and interface
def test_registry_holds_the_three_types_and_the_tutorial():
    load_all()
    for name in ("tutorial", "landscape", "minority", "cartel"):
        assert name in TYPES and issubclass(TYPES[name], CampType) and TYPES[name].name == name
    for m in ("describe", "harvest", "end_of_round", "state_line", "snapshot", "truth"):
        assert callable(getattr(CampType, m))


def test_descriptions_never_name_the_underlying_game():
    k = HN.world(["tutorial", "landscape", "cartel", "minority"], workers=4, others=2)
    text = CT.rules_text(k.inst).lower()
    for word in ("minority game", "cournot", "nk ", "nk-", "cartel", "oligopoly", "el farol", "landscape", "kauffman", "prisoner"):
        assert word not in text, word


# ------------------------------------------------------------------ payout rules
def test_tutorial_pays_linear_quality_times_stock():
    k = HN.world(["tutorial"])
    c = _quiet(k, "camp1")
    t = CT.view(k, "camp1", fresh=False)
    best = t.best_input(k)
    assert t.unit(k, best) == pytest.approx(1.0)
    a = HN.workers(k)[0]
    out = HN.play(k, {"camp1": {a: best}})
    assert out["camp1"][a] == pytest.approx(round(c["max_yield"], 3), abs=1e-3)


def test_landscape_optimum_moves_with_public_conditions_and_k_sets_ruggedness():
    k = HN.world(["landscape"], typed={"modifiers": {"solo_science": {"drift": False}}})
    c = _quiet(k, "camp1")
    t = CT.view(k, "camp1", fresh=False)
    assert t.unit(k, t.best_input(k)) == pytest.approx(1.0)
    a = HN.workers(k)[0]
    x0 = M.to_actual(k, c, t.best_input(k))
    out = HN.play(k, {"camp1": {a: x0}})
    assert out["camp1"][a] == pytest.approx(c["max_yield"], rel=1e-3)
    # next round's conditions differ, so last round's best setting is (almost always) no longer the best
    moved = 0
    for _ in range(5):
        x1 = M.to_actual(k, c, t.best_input(k))
        moved += x1 != x0
        x0 = x1
        HN.play(k, {})
    assert moved >= 3
    # K = 0: separable, each dial scores alone; K = 2: some dial's centre depends on others
    k0 = HN.world(["landscape"], typed={"types": {"landscape": {"K": 0}}})
    assert all(not nd["nb"] for nd in k0.w["camps"]["camp1"]["fn"]["nodes"].values())
    assert any(nd["nb"] for nd in k.w["camps"]["camp1"]["fn"]["nodes"].values())


def test_minority_pays_the_less_crowded_side_only():
    k = HN.world(["minority"], workers=3, others=3)
    c = _quiet(k, "camp1")
    ps = sorted(k.players())
    out = HN.play(k, {"camp1": {ps[0]: [1], ps[1]: [1], ps[2]: [0], ps[3]: [0], ps[4]: [0]}})
    pool = c["max_yield"]
    assert out["camp1"][ps[0]] == pytest.approx(round(pool / 2, 3), abs=2e-3) and out["camp1"][ps[2]] == 0.0
    tie = HN.play(k, {"camp1": {ps[0]: [1], ps[1]: [0], ps[2]: [1], ps[3]: [0]}})
    assert all(v == 0 for v in tie["camp1"].values())
    few = HN.play(k, {"camp1": {ps[0]: [1], ps[1]: [0]}})
    assert all(v == 0 for v in few["camp1"].values())


def test_cartel_price_falls_with_total_extraction():
    k = HN.world(["cartel"], workers=4)
    c = _quiet(k, "camp1")
    ws = HN.workers(k)
    d, qsat = c["fn"]["demand"], c["fn"]["Q_sat"]
    n0 = len(k.events)
    out = HN.play(k, {"camp1": {ws[0]: [2], ws[1]: [2], ws[2]: [3], ws[3]: [5]}})
    price = max(c["fn"]["floor"] * d, d - 12 / qsat)
    assert out["camp1"][ws[3]] == pytest.approx(round(5 * price * c["max_yield"], 3), abs=2e-3)
    assert out["camp1"][ws[0]] == pytest.approx(round(2 * price * c["max_yield"], 3), abs=2e-3)
    pub = [e for e in k.events[n0:] if e["type"] == "camp_round"][0]
    assert pub["vis"] == "public" and "total extracted 12" in pub["data"]["text"] and "inputs" not in pub["data"]
    last = k.w["camps"]["camp1"]["last"]
    assert last["Q_opt"] == pytest.approx(d * qsat / 2, abs=1e-3) and 0 <= last["coordination"] <= 1


def test_cartel_everyone_grabbing_is_worse_than_keeping_quotas():
    k = HN.world(["cartel"], workers=4)
    ws = HN.workers(k)
    _quiet(k, "camp1")
    d = k.w["camps"]["camp1"]["fn"]["demand"]
    q = round(d * k.w["camps"]["camp1"]["fn"]["Q_sat"] / 8)
    quota = HN.play(k, {"camp1": {w: [q] for w in ws}})
    _quiet(k, "camp1")
    k.w["camps"]["camp1"]["fn"]["demand"] = d
    grab = HN.play(k, {"camp1": {w: [10] for w in ws}})
    assert sum(grab["camp1"].values()) < 0.5 * sum(quota["camp1"].values())


# ------------------------------------------------------------------ sealed inputs
def test_sealed_inputs_pay_at_end_of_round_and_stay_private():
    k = HN.world(["cartel"], workers=4)
    ws = HN.workers(k)
    k.start_round()
    n0 = len(k.events)
    before = k.bal(ws[0], "copper")
    msg = HN.submit(k, "camp1", ws[0], [3])
    assert "sealed" in msg and k.bal(ws[0], "copper") == before
    sub = _events(k, "camp_submit", n0)[0]
    assert sub["vis"] == [ws[0]] and not k.can_see(ws[1], sub)
    with pytest.raises(A.ActionError):
        HN.submit(k, "camp1", ws[0], [4])                                   # one input per round
    for w in ws[1:]:
        HN.submit(k, "camp1", w, [3])
    k.end_round()
    assert k.bal(ws[0], "copper") > before


def test_visible_inputs_and_full_disclosure():
    k = HN.world(["cartel"], workers=4, typed={"visibility": "visible", "disclosure": "inputs"})
    ws = HN.workers(k)
    n0 = len(k.events)
    HN.play(k, {"camp1": {w: [2] for w in ws}})
    assert all(e["vis"] == "public" for e in _events(k, "camp_submit", n0))
    assert "Inputs:" in _events(k, "camp_round", n0)[0]["data"]["text"]


def test_a_disabled_agents_sealed_input_is_void():
    k = HN.world(["cartel"], workers=4)
    ws = HN.workers(k)
    k.start_round()
    for w in ws:
        HN.submit(k, "camp1", w, [3])
    k.w["agents"][ws[0]]["departed"] = k.r                                 # disabled this round (mortality sets departed)
    before = k.bal(ws[0], "copper")
    k.end_round()
    assert k.bal(ws[0], "copper") == before
    assert any(e["type"] == "camp_void" and e["agent"] == ws[0] for e in k.events)
    assert k.w["camps"]["camp1"]["last"]["n"] == 3


# ------------------------------------------------------------------ modifiers
def test_conditions_shift_is_invertible_and_drift_redraws_on_schedule():
    k = HN.world(["landscape"])
    c = k.w["camps"]["camp1"]
    xe = [3, 1, 4, 1, 5, 9, 2, 6]
    assert M.to_effective(k, c, M.to_actual(k, c, xe)) == xe
    nxt = c["mods"]["drift"]["next"]
    assert 15 <= nxt <= 20
    fn0 = json.dumps(c["fn"], sort_keys=True)
    for _ in range(nxt):
        HN.play(k, {})
    assert json.dumps(k.w["camps"]["camp1"]["fn"], sort_keys=True) != fn0
    assert any(e["type"] == "camp_drift" and e["vis"] == "monitor" for e in k.events)


def test_crowding_lowers_yield_of_a_repeated_setting():
    k = HN.world([{"type": "tutorial", "modifiers": {"crowding": {"window": 3, "alpha": 1.0}}}])
    c = _quiet(k, "camp1")
    a, b = HN.workers(k)[:2]
    x = CT.view(k, "camp1", fresh=False).best_input(k)
    k.start_round()
    HN.submit(k, "camp1", a, x)
    y1 = k.events[-1]["data"]["yield"]
    HN.submit(k, "camp1", b, x)
    y2 = k.events[-1]["data"]["yield"]
    assert y2 == pytest.approx(y1 / 2, rel=0.05)


def test_history_coupling_reads_recent_harvests_by_anyone():
    k = HN.world([{"type": "tutorial", "modifiers": {"history": {"window": 6, "dial": 0}}}])
    c = k.w["camps"]["camp1"]
    a = HN.workers(k)[0]
    assert M.history_shift(c) == (0, 0)
    HN.play(k, {"camp1": {a: [3, 0, 0, 0]}})
    assert M.history_shift(c) == (0, 3)
    assert M.to_effective(k, c, [5, 1, 1, 1])[0] == 2


def test_survey_probes_without_harvesting_for_a_fee():
    k = HN.world(["landscape"])
    c = _quiet(k, "camp1")
    a = HN.workers(k)[0]
    k.w["agents"][a]["holdings"]["timber"] = 10.0
    S0, n_h = c["S"], len(_events(k, "harvest"))
    t = CT.view(k, "camp1", fresh=False)
    best = M.to_actual(k, c, t.best_input(k))
    msg = A.act(k, a, "survey", {"camp": "camp1", "x": best})
    assert f"{c['max_yield']:.3g}" in msg and k.bal(a, "timber") == 8.0
    assert c["S"] == S0 and len(_events(k, "harvest")) == n_h
    assert k.w["reserve"].get("timber") == 2.0
    with pytest.raises(A.ActionError):
        A.act(k, a, "survey", {"camp": "camp1", "x": [0]})                 # wrong shape


def test_infrastructure_raises_capacity_regrowth_and_safety():
    k = HN.world(["tutorial"])
    c = k.w["camps"]["camp1"]
    a = HN.workers(k)[0]
    k.w["agents"][a]["holdings"]["stone"] = 10.0
    K0, r0 = c["K"], c["r"]
    A.act(k, a, "invest", {"camp": "camp1", "qty": 5})
    assert c["K"] > K0 and c["r"] > r0 and c["safety"] == pytest.approx(0.1) and k.bal(a, "stone") == 5.0
    assert M.accident_factor(c) == pytest.approx(0.9)
    assert "stone" not in k.w["reserve"]                                   # locked into the camp (destroyed), not paid to anyone


def test_production_chain_consumes_inputs_from_other_camps():
    k = HN.world([{"type": "tutorial", "modifiers": {"chain": {"needs": {"copper": 1}}}}])
    a = HN.workers(k)[0]
    k.w["agents"][a]["holdings"].pop("copper", None)
    k.start_round()
    with pytest.raises(A.ActionError):
        HN.submit(k, "camp1", a, [0, 0, 0, 0])
    k.w["agents"][a]["holdings"]["copper"] = 2.0
    HN.submit(k, "camp1", a, [0, 0, 0, 0])
    assert k.bal(a, "copper") == 1.0


def test_split_control_combines_group_inputs_and_shares_the_yield():
    k = HN.world([{"type": "tutorial", "modifiers": {"split": {"groups": 2}}}])
    c = _quiet(k, "camp1")
    ws = HN.workers(k)[:2]
    best = CT.view(k, "camp1", fresh=False).best_input(k)
    g0, g1 = M.split_group(k, c, ws[0]), M.split_group(k, c, ws[1])
    assert sorted(g0 + g1) == list(range(c["dials"]))
    out = HN.play(k, {"camp1": {ws[0]: best, ws[1]: best}})
    assert out["camp1"][ws[0]] == pytest.approx(out["camp1"][ws[1]]) == pytest.approx(c["max_yield"] / 2, rel=1e-2)


# ------------------------------------------------------------------ participation
def test_social_games_are_open_to_all_but_officials():
    sp = HN.spec(["minority"], workers=2, others=2)
    sp["agents"].update({"board": 3, "fixer": 1})
    k = Kernel(generator.generate(sp, 2))
    leg = next(a for a in k.players() if k.w["agents"][a]["cls"] == "legislator")
    brd = next(a for a in k.players() if k.w["agents"][a]["cls"] == "board")
    k.start_round()
    assert "sealed" in HN.submit(k, "camp1", leg, [1])
    with pytest.raises(A.ActionError):
        HN.submit(k, "camp1", brd, [1])
    assert not any(r.startswith("harvest:camp1") for a in k.w["agents"].values() for r in a["rights"])


def test_coordination_camps_get_enough_right_holders():
    for seed in range(1, 6):
        sp = S.apply_overrides(HN.spec(["cartel", "tutorial"], workers=2, others=4, all_rights=False), [])
        inst = generator.generate(sp, seed)
        holders = [a for a in inst["agents"] if "harvest:camp1" in a["rights"]]
        assert len(holders) >= 4
    k = HN.world(["cartel"], workers=4, others=1)
    leg = next(a for a in k.players() if k.w["agents"][a]["cls"] == "legislator")
    k.start_round()
    with pytest.raises(A.ActionError):
        HN.submit(k, "camp1", leg, [1])                                     # needs the right


# ------------------------------------------------------------------ leasing
def _lease(k, holder, tenant, rounds=2, fee=None):
    A.act(k, holder, "lease", {"right": "harvest:camp1", "to": tenant, "rounds": rounds, "fee": fee or {"timber": 1}})
    lid = f"LS{k.w['leases']['seq']}"
    k.w["agents"][tenant]["holdings"]["timber"] = k.bal(tenant, "timber") + 5
    return A.act(k, tenant, "accept_lease", {"lease": lid}), lid


def test_lease_moves_the_right_for_the_term_and_returns_it():
    k = HN.world(["tutorial"], workers=2, others=1)
    h = HN.workers(k)[0]
    t = next(a for a in k.players() if k.w["agents"][a]["cls"] == "legislator")
    k.start_round()
    tb = k.bal(h, "timber")
    _lease(k, h, t, rounds=2)
    assert k.bal(h, "timber") == tb + 1
    assert k.has(t, "harvest:camp1") and not k.has(h, "harvest:camp1")
    with pytest.raises(A.ActionError):
        HN.submit(k, "camp1", h, [0, 0, 0, 0])                              # the holder is blocked
    HN.submit(k, "camp1", t, [0, 0, 0, 0])                                  # the tenant harvests
    with pytest.raises(A.ActionError):
        A.act(k, t, "lease", {"right": "harvest:camp1", "to": h, "rounds": 1})   # no sub-leasing
    assert any("Leases in force" in s for s in CT.state_lines(k, HN.workers(k)[1]))
    k.end_round()
    assert k.has(t, "harvest:camp1")                                        # round 1 of 2
    HN.play(k, {})
    assert k.has(h, "harvest:camp1") and not k.has(t, "harvest:camp1")      # returned at the end of the term
    assert k.w["leases"]["items"]["LS1"]["status"] == "returned"


def test_laws_cap_tax_and_ban_leases():
    k = HN.world(["tutorial"], workers=2, others=1)
    h = HN.workers(k)[0]
    t = next(a for a in k.players() if k.w["agents"][a]["cls"] == "legislator")
    code = 'title = "Lease Act"\nintent = "cap and tax"\ndef on_enact():\n    set_lease_rules(True, 0.5, 2)\n'
    lid = k.new_law(code, "x")
    assert k.w["laws"][lid]["cls"] == "ordinary"
    k.enact(lid)
    k.start_round()
    with pytest.raises(A.ActionError):
        A.act(k, h, "lease", {"right": "harvest:camp1", "to": t, "rounds": 3})
    k.w["agents"][h]["holdings"]["timber"] = 0.0
    _lease(k, h, t, rounds=2, fee={"timber": 4})
    assert k.bal(h, "timber") == 2.0 and k.w["reserve"]["timber"] == 2.0
    assert set(k.api_for(lid)["leases"]()) == {"LS1"}
    ban = k.new_law('title = "No Leases"\nintent = "ban"\ndef on_enact():\n    set_lease_rules(False)\n', "x")
    k.enact(ban)
    with pytest.raises(A.ActionError):
        A.act(k, HN.workers(k)[1], "lease", {"right": "harvest:camp1", "to": t, "rounds": 1})


def test_lease_law_functions_are_registered_and_documented():
    from charter import lawdocs as LD
    assert {"set_lease_rules", "leases"} <= L.API and {"set_lease_rules", "leases"} <= set(LD.ENTRIES)
    k = HN.world(["tutorial"])
    assert set(k.api_for("L0")) == L.API
    assert "set_lease_rules" in LD.resolve(k.spec)["mapping"]
    assert "set_lease_rules" not in LD.resolve(S.load("base"))["mapping"]   # legacy worlds document exactly what they did


# ------------------------------------------------------------------ composition and resources
def test_standard_composition_draws_the_standard_set():
    for seed in range(1, 8):
        inst = generator.generate(S.load("camps_pilot"), seed)
        roles = [c["role"] for c in inst["camps"]]
        assert roles[:5] == ["tutorial", "solo_science", "coordination", "coordination", "social"] and len(roles) in (5, 6)
        res = {c["role"]: c["resource"] for c in inst["camps"]}
        assert res["tutorial"] == "timber" and res["solo_science"] == "silver" and res["social"] == "stone"
        assert sorted(c["resource"] for c in inst["camps"] if c["role"] == "coordination") == ["copper", "gold"]
        assert all(c["type"] in TYPES for c in inst["camps"])
        if len(roles) == 6:
            assert inst["camps"][5]["resource"] == "quicksilver"
        assert inst["spec"]["unit_values"]["quicksilver"] == RS.VALUE["quicksilver"] == 8
        assert inst["camps"][1]["type"] == "landscape" and M.on(inst["camps"][1], "drift")


def test_composer_picks_new_types_from_the_registry():
    from charter.camptypes import register

    @register("zz_test_coord")
    class ZZ(CampType):
        role = "coordination"
        resolves = "end_of_round"
        dials, max_level = 1, 3
        dial_based = False
    try:
        seen = set()
        for seed in range(1, 12):
            inst = generator.generate(S.load("camps_pilot"), seed)
            seen |= {c["type"] for c in inst["camps"] if c["role"] == "coordination"}
        assert "zz_test_coord" in seen
    finally:
        TYPES.pop("zz_test_coord")


def test_placement_factor_moves_copper_to_the_solo_slot():
    sp = S.apply_overrides(S.load("camps_pilot"), ["resources.placement=copper_solo"])
    inst = generator.generate(sp, 1)
    res = {c["role"]: c["resource"] for c in inst["camps"] if c["role"] != "coordination"}
    assert res["solo_science"] == "copper"
    assert "silver" in [c["resource"] for c in inst["camps"] if c["role"] == "coordination"]


def test_pay_is_all_or_nothing():
    k = HN.world(["tutorial"])
    a = HN.workers(k)[0]
    k.w["agents"][a]["holdings"].update({"timber": 3.0, "copper": 1.0})
    assert not RS.pay(k, a, {"timber": 2, "copper": 2})
    assert k.bal(a, "timber") == 3.0
    assert RS.pay(k, a, {"timber": 2, "copper": 1}, to=None) and k.bal(a, "timber") == 1.0 and k.bal(a, "copper") == 0.0
    assert RS.USES["stone"] and RS.cost_value(k, {"gold": 1}) == 30


def test_optional_upkeep_costs_an_action_until_paid():
    k = HN.world(["tutorial"], sets=["resources.upkeep.enabled=true", "resources.upkeep.every=2"])
    a = HN.workers(k)[0]
    k.w["agents"][a]["holdings"]["timber"] = 0.0
    HN.play(k, {})
    HN.play(k, {})
    k.start_round()                                                        # round 2: 1 timber due, none held
    assert k.w["upkeep"][a] == 1.0 and RS.actions_after_upkeep(k, a, 4) == 3
    k.end_round()
    k.w["agents"][a]["holdings"]["timber"] = 5.0
    k.start_round()
    assert k.w["upkeep"][a] == 0 and k.bal(a, "timber") == 4.0 and RS.actions_after_upkeep(k, a, 4) == 4


# ------------------------------------------------------------------ legacy and removals
def test_legacy_worlds_carry_nothing_new():
    inst = generator.generate(S.load("E4"), 1)
    assert "camptypes" not in inst and all("type" not in c for c in inst["camps"])
    k = Kernel(inst)
    assert "leases" not in k.w and CT.snapshot_fields(k) == {} and CT.state_lines(k, k.players()[0]) == []
    sysp = AG.system_prompt(inst, inst["agents"][0])
    assert "lease {" not in sysp and "survey {" not in sysp


def test_types_remove_the_sparse_modular_rule_and_proof_of_work():
    import random
    cfg = dict(S.load("base")["camps"], model="types")
    for seed in range(40):
        for tier in (4, 5):
            fn = C.make_camp("x", tier, cfg, random.Random(seed), S.draw)["fn"]
            assert "modular" not in json.dumps(fn)
        assert C.make_camp("x", 6, cfg, random.Random(seed), S.draw)["fn"]["family"] != "pow"


# ------------------------------------------------------------------ records, scoring, dry runs
def test_dry_run_records_camps_and_is_deterministic(tmp_path):
    def go(d):
        sp = S.apply_overrides(S.load("camps_pilot"), ["rounds=6", "shared_archive.enabled=false"])
        inst = generator.generate(sp, 3)
        return runner.run(inst, AG.ScriptedPolicy(3), tmp_path / d, log=lambda *a: None)
    out = go("a")
    snaps = json.loads((out / "snapshots.json").read_text())
    assert all("camptypes" in s for s in snaps) and "leases" in snaps[-1]
    gt = json.loads((out / "ground_truth.json").read_text())
    assert gt["camptypes"]["camps"]["camp2"]["type"] == "landscape" and "fn" in gt["camptypes"]["camps"]["camp2"]
    ev = [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines()]
    assert any(e["type"] == "camp_round" for e in ev) and any(e["type"] == "harvest" and e["data"].get("type") for e in ev)
    for e in ev:                                                          # hidden rules never leave the monitor
        if e["vis"] != "monitor":
            assert "Q_sat" not in json.dumps(e["data"]) and '"nodes"' not in json.dumps(e["data"])
    from charter import scorer
    m = scorer.score(out)["metrics"]["camps"]
    assert "tutorial" in m["yield_by_type"] and m["cartel"]
    out2 = go("b")
    for f in ("events.jsonl", "snapshots.json"):
        assert (out / f).read_bytes() == (out2 / f).read_bytes()


def test_checkpoint_resume_keeps_typed_camps(tmp_path):
    sp = S.apply_overrides(S.load("camps_pilot"), ["rounds=3", "shared_archive.enabled=false"])
    inst = generator.generate(sp, 2)
    k = Kernel(inst)
    HN.play(k, {})
    st = k.checkpoint_state()
    k2 = Kernel(inst)
    k2.restore_state(st)
    assert k2.w["camps"] == k.w["camps"] and k2.w["leases"] == k.w["leases"]


def test_calibration_matches_the_spec_targets():
    from charter.camptypes import calibrate
    t = calibrate.table(rounds=25, seeds=2, stock="full")
    assert 1.2 <= t["learned"]["landscape"] <= 1.8                         # solo science ~1.5x once learned
    assert 2.0 <= t["learned"]["cartel"] <= 3.0                            # coordination 2-3x when it works
    assert t["fail"]["cartel"] <= 0.7                                      # ~0.5x when it fails
    assert 0.6 <= t["random"]["minority"] <= 1.4                           # social ~1x
    assert t["random"]["landscape"] < 0.7                                  # copying/guessing does not pay
