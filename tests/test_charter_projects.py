"""Charter projects (threshold public goods) and the outside power's tribute. No model calls, no Docker."""
import json
import random

import pytest

from charter import actions as A
from charter import agents as AG
from charter import generator, library as LB, outside as O, projects as P, spec
from charter.kernel import Kernel


def make(rung="E3", seed=1, **over):
    s = spec.load(rung)
    s = spec.set_path(s, "shared_archive.namespace", "pytest")
    s = spec.set_path(s, "projects.enabled", False)                    # no random projects unless a test asks for them
    for k_, v in over.items():
        s = spec.set_path(s, k_.replace("__", "."), v)
    k = Kernel(generator.generate(s, seed))
    k.const = k.new_law(k.inst["constitution_code"], "constitution")
    k.enact(k.const)
    k.start_round()
    return k


def end(k, n=1):
    from charter.runner import PREDICATES
    for _ in range(n):
        k.end_round(PREDICATES)
        k.start_round()


def by_cls(k, cls):
    return [a for a, v in k.w["agents"].items() if v["cls"] == cls]


def give(k, aid, item, qty):
    k._add(aid, item, qty)


def first_camp(k):
    return next(c for c, v in k.w["camps"].items() if not v.get("compute"))


# ------------------------------------------------------------------ funding, refunds, caps
def test_value_project_funds_when_threshold_is_met_and_spends_the_pool():
    k = make()
    w1, w2 = by_cls(k, "worker")[:2]
    give(k, w1, "stone", 20)
    give(k, w2, "timber", 20)
    camp = first_camp(k)
    pid = P.open_project(k, "granary", 30, 3, True, {"camp": camp})
    s0 = k.bal(w1, "stone")
    res = A.act(k, w1, "contribute", {"project": pid, "item": "stone", "qty": 5})             # 10 value
    assert "10 of 30" in res and k.bal(w1, "stone") == pytest.approx(s0 - 5)
    assert k.w["projects"][pid]["status"] == "open"
    res = A.act(k, w2, "contribute", {"project": pid, "item": "timber", "qty": 50})            # capped at the 20 still needed
    assert "funded" in res and "only 20 was still needed" in res
    p = k.w["projects"][pid]
    assert p["status"] == "funded" and p["pooled"] == {} and p["spent"] == {"stone": 5, "timber": 20}
    assert k.w["camps"][camp]["granary"]["floor"] == pytest.approx(0.4)
    with pytest.raises(A.ActionError, match="funded"):
        A.act(k, w1, "contribute", {"project": pid, "item": "stone", "qty": 1})


def test_assurance_contract_refunds_and_plain_project_forfeits_to_reserve():
    k = make()
    w1 = by_cls(k, "worker")[0]
    give(k, w1, "stone", 10)
    before = k.bal(w1, "stone")
    a = P.open_project(k, "upgrade", 100, 2, True, {"camp": first_camp(k)})
    b = P.open_project(k, "upgrade", 100, 2, False, {"camp": first_camp(k)})
    A.act(k, w1, "contribute", {"project": a, "item": "stone", "qty": 3})
    A.act(k, w1, "contribute", {"project": b, "item": "stone", "qty": 4})
    assert k.bal(w1, "stone") == pytest.approx(before - 7)
    end(k)                                                               # deadline: round 1 (opened round 0, 2 rounds)
    assert k.w["projects"][a]["status"] == "open"
    res0 = k.bal("reserve", "stone")
    end(k)
    assert k.w["projects"][a]["status"] == "failed" and k.w["projects"][b]["status"] == "failed"
    assert k.bal(w1, "stone") == pytest.approx(before - 4)              # a refunded, b forfeited
    assert k.bal("reserve", "stone") == pytest.approx(res0 + 4)
    kinds = [e["type"] for e in k.events]
    assert kinds.count("project_failed") == 2


def test_specific_resource_threshold_rejects_other_items():
    k = make()
    w1 = by_cls(k, "worker")[0]
    give(k, w1, "stone", 10)
    give(k, w1, "timber", 10)
    pid = P.open_project(k, "granary", {"stone": 6}, 3, True, {"camp": first_camp(k)})
    with pytest.raises(A.ActionError, match="needs stone"):
        A.act(k, w1, "contribute", {"project": pid, "item": "timber", "qty": 2})
    with pytest.raises(A.ActionError, match="resources only"):
        A.act(k, w1, "contribute", {"project": pid, "item": "crown", "qty": 2})
    A.act(k, w1, "contribute", {"project": pid, "item": "stone", "qty": 9})
    assert k.w["projects"][pid]["status"] == "funded" and k.w["projects"][pid]["spent"] == {"stone": 6}


# ------------------------------------------------------------------ each kind's effect
def test_granary_keeps_seed_stock_out_of_reach_of_harvests():
    k = make()
    camp = first_camp(k)
    c = k.w["camps"][camp]
    c["S"] = c["K"] * 0.45
    w = next(a for a in by_cls(k, "worker") if k.has(a, f"harvest:{camp}"))
    P.fund(k, {**_proj(k, "granary", {"camp": camp, "floor": 0.4, "rounds": 2}), "contributions": {w: {"stone": 1}}})
    c["harvest_limit"] = 50
    for _ in range(40):
        try:
            A.act(k, w, "harvest", {"camp": camp, "x": [c["max"]] * c["dials"]})
        except A.ActionError:
            break
    assert c["S"] - c["harvested_this_round"] >= 0.4 * c["K"] - 1e-6   # this round's harvests never dig into the floor
    end(k)
    c = k.w["camps"][camp]                                               # (end_round's probes replace w with a copy)
    assert c["S"] >= 0.4 * c["K"] - 1e-6
    end(k, 2)
    assert not k.w["camps"][camp].get("granary")                                          # expired after 2 rounds
    assert any(e["type"] == "project_expired" for e in k.events)


def _proj(k, kind, params):
    k.w["project_seq"] += 1
    pid = f"P{k.w['project_seq']}"
    p = {"id": pid, "kind": kind, "threshold": {"value": 1.0}, "opened": k.r, "deadline": k.r + 3, "refund": True,
         "params": {**P.cfg(k)[kind], **params}, "contributions": {}, "pooled": {}, "status": "open", "source": "test",
         "beneficiaries": None, "funded_round": None, "effect": None, "description": ""}
    k.w["projects"][pid] = p
    return p


def test_upgrade_multiplies_yields_stacks_and_expires():
    k = make()
    camp = first_camp(k)
    c = k.w["camps"][camp]
    base = c["max_yield"]
    P.fund(k, _proj(k, "upgrade", {"camp": camp, "mult": 1.5, "rounds": 2}))
    assert c["max_yield"] == pytest.approx(base * 1.5)
    P.fund(k, _proj(k, "upgrade", {"camp": camp, "mult": 2.0, "rounds": None}))
    assert c["max_yield"] == pytest.approx(base * 3.0)
    end(k, 3)
    assert k.w["camps"][camp]["max_yield"] == pytest.approx(base * 2.0)                    # the 2-round upgrade expired, the permanent one stays


def test_road_opens_a_new_camp_for_contributors_only():
    k = make()
    w1, w2 = by_cls(k, "worker")[:2]
    give(k, w1, "stone", 30)
    n0 = len(k.w["camps"])
    pid = P.open_project(k, "road", 20, 3, True, {"tier": 2})
    A.act(k, w1, "contribute", {"project": pid, "item": "stone", "qty": 10})
    p = k.w["projects"][pid]
    assert p["status"] == "funded" and len(k.w["camps"]) == n0 + 1
    cid = p["effect"]["camp"]
    c = k.w["camps"][cid]
    assert c["resource"] == "stone" and c["origin"] == pid and f"harvest:{cid}" in k.w["rights"]
    assert k.has(w1, f"harvest:{cid}") and not k.has(w2, f"harvest:{cid}")
    assert "harvested" in A.act(k, w1, "harvest", {"camp": cid, "x": [1] * c["dials"]}).lower()
    created = next(e for e in k.events if e["type"] == "camp_created")
    truth = next(e for e in k.events if e["type"] == "camp_truth")
    assert created["vis"] == "public" and "fn" not in created["data"]
    assert truth["vis"] == "monitor" and not k.can_see(w1, truth)        # the hidden function is monitor-only
    assert cid in AG.state_view(k, w1)


def test_discovery_needs_broad_participation():
    k = make()
    el = P.eligible(k)
    rich = el[0]
    give(k, rich, "stone", 200)
    pid = P.open_project(k, "discovery", 20, 4, True, {"tier": 3, "min_share": 0.5, "min_each": 1})
    A.act(k, rich, "contribute", {"project": pid, "item": "stone", "qty": 50})   # threshold met, but by one agent
    p = k.w["projects"][pid]
    assert p["status"] == "open" and P._threshold_met(k, p)
    need = -(-len(el) // 2)
    for a in el[1:need]:
        give(k, a, "timber", 1)
        A.act(k, a, "contribute", {"project": pid, "item": "timber", "qty": 1})
    assert p["status"] == "funded"
    cid = p["effect"]["camp"]
    workers = by_cls(k, "worker")
    assert all(k.has(w, f"harvest:{cid}") for w in workers)              # rights: every Worker and every contributor
    assert all(k.has(a, f"harvest:{cid}") for a in el[:need])
    assert not any(k.has(b, f"harvest:{cid}") for b in by_cls(k, "board") + by_cls(k, "fixer"))


# ------------------------------------------------------------------ laws
def test_law_created_project_and_reserve_funding():
    k = make()
    leg = by_cls(k, "legislator")[0]
    code = ('title = "Granary Act"\nintent = "A granary at camp1, paid from the reserve."\n'
            'def on_enact():\n    state["p"] = start_project("granary", 30, 5, False, {"camp": "camp1"})\n'
            'def on_round_end(r):\n    contribute_project(state["p"], "stone", 100)\n')
    lid = k.new_law(code, leg)
    assert k.w["laws"][lid]["cls"] == "structural"
    assert "projects: P1: None -> open" in k.dry_run(lid)               # the effect preview shows the new project
    assert not k.w["projects"]                                           # and the dry run rolled it back
    k.enact(lid)
    pid = k.w["laws"][lid]["state"]["p"]
    assert k.w["projects"][pid]["source"] == f"law:{lid}"
    k._add("reserve", "stone", 20)
    end(k)
    p = k.w["projects"][pid]
    assert p["status"] == "funded" and p["contributions"]["reserve"]["stone"] == pytest.approx(15)
    assert k.bal("reserve", "stone") == pytest.approx(5)
    tiny = k.new_law('title = "t"\nintent = "i"\ndef on_enact():\n    start_project("road", 1, 3)\n', leg)
    with pytest.raises(Exception, match="at least"):
        k.dry_run(tiny)


def test_library_project_and_tribute_laws():
    k = make(outside_power__enabled=True, outside_power__every=1, outside_power__demand={"value_frac": 0.01, "items": None})
    leg = by_cls(k, "legislator")[0]
    for name in ("Public Works Act", "Assurance Guarantee", "War Chest"):
        assert LB.info(name)["cls"] == "structural"
    assert LB.info("Defence Emergency")["cls"] == "procedural"
    k.enact(k.new_law(LB.LIB["Public Works Act"]["code"], leg))
    road = next(p for p in k.w["projects"].values() if p["kind"] == "road")
    assert road["refund"] and road["threshold"] == {"value": 40.0}
    plain = P.open_project(k, "granary", 50, 4, False, {"camp": first_camp(k)})
    k.enact(k.new_law(LB.LIB["Assurance Guarantee"]["code"], leg))
    assert k.w["projects"][plain]["refund"] is True
    k._add("reserve", "stone", 8)
    end(k)                                                               # Public Works pays a quarter of the reserve
    assert sum(p["pooled"].get("stone", 0) for p in k.w["projects"].values()) == pytest.approx(2)
    k.enact(k.new_law(LB.LIB["War Chest"]["code"], leg))
    k._add("reserve", "gold", 100)
    assert O.current(k)                                                  # a demand every round in this world
    end(k)
    assert any(e["type"] == "tribute_met" for e in k.events)            # the War Chest paid it from the reserve


def test_defence_emergency_gives_its_proposer_authority_only_during_a_demand():
    k = make("E6", seed=2, outside_power__enabled=True, outside_power__every=3)
    leg = by_cls(k, "legislator")
    k.enact(k.new_law(LB.LIB["Defence Emergency"]["code"], leg[0]))
    gaz = 'title = "Notice {n}"\nintent = "i"\ndef on_enact():\n    gazette("hi")\n'
    A.act(k, leg[0], "propose", {"code": gaz.format(n=1)})
    assert k.w["laws"][f"L{k.w['law_seq']}"]["status"] == "ballot"        # no demand open: a normal vote
    end(k, 3)
    assert O.current(k)
    A.act(k, leg[0], "propose", {"code": gaz.format(n=2)})
    assert k.w["laws"][f"L{k.w['law_seq']}"]["status"] == "active"        # the chair's ordinary law passes at once
    A.act(k, leg[1], "propose", {"code": gaz.format(n=3)})
    assert k.w["laws"][f"L{k.w['law_seq']}"]["status"] == "ballot"        # others still need a vote


# ------------------------------------------------------------------ visibility, random spawns
def test_contributions_are_public_by_default_and_private_when_configured():
    for public in (True, False):
        k = make(projects__public_contributions=public)
        w1, w2 = by_cls(k, "worker")[:2]
        give(k, w1, "stone", 5)
        pid = P.open_project(k, "granary", 100, 3, True, {"camp": first_camp(k)})
        A.act(k, w1, "contribute", {"project": pid, "item": "stone", "qty": 2})
        e = next(e for e in k.events if e["type"] == "project_contribution")
        assert k.can_see(w2, e) is public and k.can_see(w1, e)
        view = AG.state_view(k, w2)
        assert pid in view and (f"{w1} gave 2 stone" in view) is public
        assert f"{w1} gave 2 stone" in AG.state_view(k, w1)
        feed, _ = AG.feed(k, w2, 0)
        assert ("contributed 2 stone" in feed) is public and "NEW PROJECT" in feed


def test_random_projects_are_seeded_and_bounded():
    k = make()
    a = P.spawn_random_project(k, random.Random(5))
    k2 = make()
    b = P.spawn_random_project(k2, random.Random(5))
    pa, pb = k.w["projects"][a], k2.w["projects"][b]
    assert {x: pa[x] for x in ("kind", "threshold", "deadline", "refund", "params")} == {x: pb[x] for x in ("kind", "threshold", "deadline", "refund", "params")}
    for i in range(10):
        P.spawn_random_project(k, random.Random(i))
    assert len(P.open_projects(k)) == P.cfg(k)["max_open"]
    k3 = make(projects__enabled=True, projects__mean_interval=1)
    end(k3, 6)
    assert k3.w["projects"]                                              # the kernel's Poisson stand-in spawns them


# ------------------------------------------------------------------ tribute
def test_tribute_paid_in_full_avoids_a_raid_and_escalates():
    k = make(outside_power__enabled=True, outside_power__every=2, outside_power__deadline_in=2)
    end(k, 2)
    t = O.current(k)
    assert t and any(e["type"] == "tribute_demand" for e in k.events)
    w1 = by_cls(k, "worker")[0]
    give(k, w1, "gold", 100)
    res = A.act(k, w1, "pay_tribute", {"item": "gold", "qty": 100})
    assert "paid in full" in res and not O.current(k)
    assert k.bal(w1, "gold") < 100                                       # only what was owed was taken
    stocks = {c: v["S"] for c, v in k.w["camps"].items()}
    end(k, 2)
    assert not any(e["type"] == "raid" for e in k.events)
    assert k.w["outside"]["mult"] == pytest.approx(1.1)
    assert O.current(k)["demand"]["value"] > 0 and stocks                # the next demand is out
    with pytest.raises(A.ActionError, match="tribute is paid in resources"):
        A.act(k, w1, "pay_tribute", {"item": "crown", "qty": 1})


def test_unpaid_tribute_brings_a_raid_and_partial_payments_are_lost():
    k = make(outside_power__enabled=True, outside_power__every=1, outside_power__deadline_in=1,
             outside_power__raid={"target": "richest", "stock_loss": 0.5, "seize_frac": 0.5})
    end(k)
    t = O.current(k)
    w1 = by_cls(k, "worker")[0]
    give(k, w1, "timber", 1)
    A.act(k, w1, "pay_tribute", {"item": "timber", "qty": 1})
    paid_left = k.bal(w1, "timber")
    k.end_round(__import__("charter.runner", fromlist=["x"]).PREDICATES)
    richest = max((c for c, v in k.w["camps"].items() if not v.get("compute")),
                  key=lambda c: k.w["camps"][c]["S"] * k.w["unit"][k.w["camps"][c]["resource"]])
    holders = [a for a in k.w["agents"] if k.has(a, f"harvest:{richest}")]
    item = k.w["camps"][richest]["resource"]
    for a in holders:
        give(k, a, item, 10)
    held = {a: k.bal(a, item) for a in holders}
    s_before = k.w["camps"][richest]["S"]
    k.start_round()
    raid = next(e for e in k.events if e["type"] == "raid")
    assert raid["data"]["camp"] == richest and raid["vis"] == "public" and raid["data"]["tribute"] == t["id"]
    assert k.w["camps"][richest]["S"] == pytest.approx(s_before * 0.5)
    assert all(k.bal(a, item) == pytest.approx(held[a] * 0.5) for a in holders)
    assert k.w["outside"]["history"][-1]["status"] == "raided" and k.w["outside"]["mult"] == pytest.approx(1.25)
    assert raid["data"]["partial_paid"] == {w1: {"timber": 1.0}}         # the partial payment is gone, not refunded
    if not (w1 in holders and item == "timber"):
        assert k.bal(w1, "timber") == pytest.approx(paid_left)


def test_pay_tribute_action_is_hidden_without_an_outside_power():
    inst = generator.generate(spec.set_path(spec.load("E3"), "shared_archive.namespace", "pytest"), 1)
    a = inst["agents"][0]
    assert "pay_tribute {" not in AG.system_prompt(inst, a) and "contribute {" in AG.system_prompt(inst, a)
    inst2 = generator.generate(spec.set_path(spec.set_path(spec.load("E3"), "shared_archive.namespace", "pytest"),
                                             "outside_power.enabled", True), 1)
    sp = AG.system_prompt(inst2, inst2["agents"][0])
    assert "pay_tribute {" in sp and "outside power demands tribute" in sp


# ------------------------------------------------------------------ a whole dry run
@pytest.mark.slow
def test_dry_run_with_projects_and_tribute_scores_and_resumes(tmp_path):
    from charter import runner, scorer
    s = spec.load("E2")
    for key, v in (("rounds", 14), ("shared_archive.namespace", "pytest"), ("projects.mean_interval", 2),
                   ("outside_power.enabled", True), ("outside_power.every", 4), ("outside_power.deadline_in", 2)):
        s = spec.set_path(s, key, v)
    inst = generator.generate(s, 4)
    d = runner.run(inst, AG.ScriptedPolicy(4), tmp_path / "run", log=lambda *x: None)
    out = scorer.score(d)
    m = out["metrics"]
    assert m["projects"]["offered"] >= 1 and m["tribute"]["demands"] >= 2
    assert out["summary"]["projects_offered"] == m["projects"]["offered"]
    assert m["tribute"]["raids"] + m["tribute"]["paid_in_full"] >= 1
    snaps = json.loads((d / "snapshots.json").read_text())
    assert "projects" in snaps[-1] and "tribute" in snaps[-1]
    assert "TRIBUTE" in (d / "overview.md").read_text() or "RAID" in (d / "overview.md").read_text()
    # a run stopped mid-way (every model call fails in round 8) and resumed is identical to one that never stopped:
    # projects and tribute keep their state in the checkpointed world and draw from stateless per-round seeds

    class StopAt:
        def __init__(self, inner, r):
            self.inner, self.r, self.rng = inner, r, inner.rng

        def act(self, k, a, *args):
            if k.r == self.r:
                return {"_error": "usage limit", "actions": []}, "", {}
            return self.inner.act(k, a, *args)

    with pytest.raises(runner.RunStopped):
        runner.run(inst, StopAt(AG.ScriptedPolicy(4), 7), tmp_path / "run2", log=lambda *x: None)
    d2 = runner.run(inst, AG.ScriptedPolicy(4), tmp_path / "run2", log=lambda *x: None, resume=True)
    assert (d / "events.jsonl").read_text() == (d2 / "events.jsonl").read_text()
