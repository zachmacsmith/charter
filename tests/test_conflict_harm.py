"""The harm combat model (charter/conflict.py, conflict.model; docs/review/21_combat.md): per-agent bases, one weapon per fighter
used up, food per fighter, P against D in a square-law contest (kill, wound or repelled), fighting back (a dying blow, self-defence,
a first strike on watch), wounds (robbed of food, starving, recovery by eating, credit for a death soon after), craft and forge,
join_attack in person, visibility, text, and the disable model left as it was."""
from __future__ import annotations

import json
import random

import pytest

from charter import actions as A
from charter import agents as AG
from charter import conflict as CF
from charter import context as CX
from charter import generator, runner
from charter import goals as G
from charter import mortality as M
from charter import settings as ST
from charter import spec as S
from charter import subsistence as SB
from charter.kernel import Kernel

SMALL = "agents={worker: 6, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 1}"


def make(sets=(), seed=1, timing="immediate"):
    sp = S.apply_overrides(S.load("nature_subsistence"), ["shared_archive.enabled=false", "conflict.assassin.present_prob=0",
                                                          "conflict.start={}", "conflict.grace=0", "rounds=10", SMALL,
                                                          f"conflict.timing={timing}", *sets])
    return Kernel(generator.generate(sp, seed))


def workers(k):
    return sorted(a for a in k.players() if k.w["agents"][a]["cls"] == "worker")


def unit_bases(k, *aids, attack=1.0, defense=1.0):
    for a in aids:
        k.w["conflict"]["bases"][a] = {"attack": attack, "defense": defense}


def ready(k, a, food=6.0, **items):
    """a holds exactly `food` food and the given items (weapons, crude, ...)."""
    k._add(a, "food", food - k.bal(a, "food"))
    for item, q in items.items():
        k._add(a, item, float(q) - k.bal(a, item))


def certain(monkeypatch, outcome, counter=0.0):
    """Fix the battle's odds: outcome kill | wound | repelled; counter: the self-defence chance (0: never)."""
    pk, ps = {"kill": (1.0, 1.0), "wound": (0.0, 1.0), "repelled": (0.0, 0.0)}[outcome]
    monkeypatch.setattr(CF, "odds", lambda c, P, D: {"X": 2 * (D + 1), "p_kill": pk, "p_success": ps})
    real = CF.counter_odds
    monkeypatch.setattr(CF, "counter_odds", lambda c, Pd, Qa, wounded=False, watch=False: {
        **real(c, Pd, Qa, wounded, watch), "p": counter})


# ---------------------------------------------------------------------- 0. the model switch
def test_model_defaults_to_harm_with_subsistence_and_disable_without():
    assert CF.model_of(S.load("nature_subsistence")) == "harm"
    assert CF.model_of(S.load("conflict_pilot")) == "disable" and CF.model_of(S.load("society")) == "disable"
    assert CF.model_of(S.apply_overrides(S.load("nature_subsistence"), ["conflict.model=disable"])) == "disable"
    k = make()
    assert CF.harm(k) and {"watch", "wounds", "bases"} <= set(k.w["conflict"])


def test_engine_7_runs_keep_the_disable_model():
    """The default flip (engine 8): a run frozen under engine 7 has no conflict.model key, so it plays under disable."""
    from charter import provenance as PV
    assert PV.ENGINE_VERSION >= 8
    assert ("charter.conflict.DEFAULTS", ("model",), "disable", "auto") in PV.ENGINE_FLIPS[8]["flips"]
    old = {"engine_version": 7, "defaults": {"charter.conflict.DEFAULTS": {"enabled": False}}}
    with ST.use(old):
        assert CF.model_of(S.load("nature_subsistence")) == "disable"
    assert CF.model_of(S.load("nature_subsistence")) == "harm"


# ---------------------------------------------------------------------- 1. bases and hunger
def test_bases_are_drawn_per_agent_at_generation_and_never_zero():
    k = make()
    for a in k.inst["agents"]:
        assert 0.5 <= a["attack_base"] <= 1.5 and 0.5 <= a["defense_base"] <= 1.5
        assert CF.bases(k, a["id"]) == {"attack": a["attack_base"], "defense": a["defense_base"]}
        assert CF.draw_bases(k.spec, k.inst["seed"], a["id"]) == CF.bases(k, a["id"])   # own stream: reproducible
    sp = S.apply_overrides(S.load("nature_subsistence"), ["conflict.agent_base.attack=0", "conflict.agent_base.defense=0"])
    assert CF.draw_bases(sp, 1, "X") == {"attack": CF.MIN_BASE, "defense": CF.MIN_BASE}
    assert CF.draw_bases(k.spec, 1, "Newborn") == CF.bases(k, "Newborn")                  # born later: drawn on first use


def test_hunger_lowers_strength_and_defence():
    k = make()
    a = workers(k)[0]
    unit_bases(k, a)
    assert CF.strength(k, a, 5) == 6 and CF.defense(k, a) == 1
    k.apply("hunger", agent=a, stage=-1, missed=1)
    assert CF.strength(k, a, 5) == pytest.approx(5.75) and CF.defense(k, a) == pytest.approx(0.75)
    k.apply("hunger", agent=a, stage=-2, missed=2)
    assert CF.strength(k, a, 0) == pytest.approx(0.5) and CF.defense(k, a) == pytest.approx(0.5)


# ---------------------------------------------------------------------- 5. the contest
@pytest.mark.parametrize("P,D,kill,success", [(6, 1, 0.692, 0.9), (3, 1, 0.36, 0.692), (1, 1, 0.0588, 0.2), (6, 3, 0.36, 0.692),
                                              (12, 1, 0.9, 0.973)])
def test_reference_odds(P, D, kill, success):
    o = CF.odds(CF.DEFAULTS, P, D)
    assert o["p_kill"] == pytest.approx(kill, abs=0.002) and o["p_success"] == pytest.approx(success, abs=0.002)


def test_contest_parameters_are_configurable():
    c = CF.config({"conflict": {"contest": {"r": 1, "c": 1, "wound_div": 4}}})
    o = CF.odds(c, 6, 1)
    assert o["X"] == 2 and o["p_kill"] == pytest.approx(6 / 8) and o["p_success"] == pytest.approx(6 / 6.5)


def test_outcome_shares_match_the_formula_by_seeded_monte_carlo():
    """Blade (base 1 + 5) against an unwary, unarmed defender with base 1 and no fort: kill 0.69, wound 0.21, repelled 0.10."""
    k = make()
    a, t = workers(k)[:2]
    unit_bases(k, a, t)
    snap = k._snapshot()
    n, got = 600, {"kill": 0, "wound": 0, "repelled": 0}
    for i in range(n):
        k._restore(snap)
        k.w["conflict"]["seq"] = i
        ready(k, a, weapons=1)
        ready(k, t, food=3)
        r = CF.attack(k, a, t, 0)
        assert r["P"] == 6 and r["D"] == 1
        got[r["outcome"]] += 1
    assert got["kill"] / n == pytest.approx(0.692, abs=0.05)
    assert got["wound"] / n == pytest.approx(0.208, abs=0.05)
    assert got["repelled"] / n == pytest.approx(0.10, abs=0.04)


# ---------------------------------------------------------------------- 2. weapons: the strongest one, used up, one per fighter
def test_the_strongest_weapon_is_used_up_and_only_one(monkeypatch):
    certain(monkeypatch, "repelled")
    k = make()
    a, t = workers(k)[:2]
    unit_bases(k, a, t)
    ready(k, a, food=20, weapons=2, crude=3)
    r = CF.attack(k, a, t, 7)                                          # units is accepted and ignored
    assert r["weapon"] == "weapons" and r["P"] == 6 and k.bal(a, "weapons") == 1 and k.bal(a, "crude") == 3
    CF.attack(k, a, t, 0)
    assert k.bal(a, "weapons") == 0 and k.bal(a, "crude") == 3
    r = CF.attack(k, a, t, 0)
    assert r["weapon"] == "crude" and r["P"] == 3 and k.bal(a, "crude") == 2
    k._add(a, "crude", -2)
    r = CF.attack(k, a, t, 0)
    assert r["weapon"] is None and r["P"] == 1                         # bare hands


# ---------------------------------------------------------------------- 3. the cost: food per fighter, two actions
def test_food_is_paid_win_or_lose_and_an_attack_without_it_is_refused(monkeypatch):
    certain(monkeypatch, "repelled")
    k = make()
    a, t = workers(k)[:2]
    ready(k, a, food=1.5, weapons=1)
    with pytest.raises(A.ActionError, match="2 food"):
        A.act(k, a, "attack", {"target": t})
    assert k.bal(a, "weapons") == 1
    ready(k, a, food=5)
    A.act(k, a, "attack", {"target": t, "units": "lots"})
    assert k.bal(a, "food") == 3 and k.bal(a, "weapons") == 0
    assert CF.fit(k, [{"action": "attack"}, {"action": "watch"}], 3) == 2   # an attack uses 2 actions
    k.apply("hunger", agent=a, stage=-1, missed=1)
    with pytest.raises(A.ActionError, match="hungry"):
        A.act(k, a, "attack", {"target": t})


# ---------------------------------------------------------------------- 4. join_attack: in person
def test_join_attack_brings_the_ally_in_person(monkeypatch):
    certain(monkeypatch, "repelled")
    k = make(timing="end_of_round")
    a, b, t = workers(k)[:3]
    unit_bases(k, a, b, t)
    ready(k, a, food=6, weapons=1)
    ready(k, b, food=6, weapons=1, crude=1)
    A.act(k, b, "join_attack", {"attacker": a, "target": t, "units": 9})
    assert k.bal(b, "weapons") == 0 and k.bal(b, "food") == 4 and k.bal(b, "crude") == 1    # in escrow
    A.act(k, a, "attack", {"target": t})
    CF.resolve_attacks(k)
    rec = k.w["conflict"]["log"][-1]
    assert rec["P"] == 12 and rec["fighters"] == [a, b] and rec["allies"][b]["weapon"] == "weapons"
    assert k.bal(b, "weapons") == 0 and k.bal(b, "food") == 4                                  # used up
    k.w["round"] += 1                                                  # a join with no attack comes back
    A.act(k, b, "join_attack", {"attacker": a, "target": t})
    assert k.bal(b, "crude") == 0 and k.bal(b, "food") == 2
    CF.resolve_attacks(k)
    assert k.bal(b, "crude") == 1 and k.bal(b, "food") == 4
    ready(k, b, food=1)
    with pytest.raises(A.ActionError, match="2 food"):
        A.act(k, b, "join_attack", {"attacker": a, "target": t})


# ---------------------------------------------------------------------- 6. a wound
def test_a_wound_takes_all_food_splits_the_rest_and_leaves_the_victim_starving(monkeypatch):
    certain(monkeypatch, "wound")
    k = make()
    a, t = workers(k)[:2]
    ready(k, a, food=4, weapons=1)
    k._add(t, "timber", 20.0)
    k._add(t, "stone", 6.0)
    A.act(k, t, "build", {"kind": "store"})
    sid = next(iter(SB.state(k)["stores"]))
    ready(k, t, food=7)
    A.act(k, t, "transfer", {"to": f"store:{sid}", "item": "food", "qty": 3})
    k.w["conflict"]["forts"][t] = 4.0
    before = {i: q for i, q in k.w["agents"][t]["holdings"].items() if i != "food"}
    a_before = {i: k.bal(a, i) for i in before}
    r = CF.attack(k, a, t, 0)
    assert r["outcome"] == "wound" and M.alive(k, t)
    assert k.bal(t, "food") == 0 and k.bal(a, "food") == pytest.approx(2 + 4)    # 4 - 2 spent + all 4 carried
    for i, q in before.items():
        assert k.bal(a, i) == pytest.approx(a_before[i] + q / 2) and k.bal(t, i) == pytest.approx(0.0, abs=1e-6), i
    assert CF.fort(k, t) == 4.0 and SB.food(k, f"store:{sid}") == 3     # fort and store untouched
    assert SB.stage(k, t) == -2 and k.w["conflict"]["wounds"][t] == {"round": k.r, "by": a, "how": "attack"}
    ev = [e for e in k.events if e["type"] == "wounded"][-1]
    assert ev["vis"] == "public" and ev["data"]["by"] == a and "wounded and robbed in an attack by " + a in ev["data"]["text"]


def test_recovery_is_by_eating_two_meals_to_fed(monkeypatch):
    certain(monkeypatch, "wound")
    k = make()
    a, t = workers(k)[:2]
    ready(k, a, weapons=1)
    CF.attack(k, a, t, 0)
    assert SB.stage(k, t) == -2 and SB.actions_after_hunger(k, t, 4) == 2
    ready(k, t, food=5)
    SB.end_of_round(k)
    assert SB.stage(k, t) == -1
    SB.end_of_round(k)
    assert SB.stage(k, t) == 0


# ---------------------------------------------------------------------- 7. fighting back
def test_a_counter_comes_only_from_a_survivor_and_mostly_wounds():
    c = CF.DEFAULTS
    co = CF.counter_odds(c, 6, 2)                                       # an armed defender against an attacker away from home
    assert co["p"] == pytest.approx(0.75) and co["kill"] < 0.2
    assert CF.counter_odds(c, 6, 2, wounded=True)["p"] == pytest.approx(0.375)
    assert CF.counter_odds(c, 6, 2, watch=True)["p"] == pytest.approx(0.9)       # capped
    k = make()
    a, t = workers(k)[:2]
    unit_bases(k, a, t)
    snap = k._snapshot()
    effects = {"kill": 0, "wound": 0}
    for i in range(300):
        k._restore(snap)
        k.w["conflict"]["seq"] = i
        ready(k, a, weapons=1)
        ready(k, t, food=3, weapons=1)
        r = CF.attack(k, a, t, 0)
        cn = r["counter"]
        if r["outcome"] == "kill":
            assert cn.get("effect") in (None, "wound")                  # a dying blow only wounds
        elif cn["landed"]:
            effects[cn["effect"]] += 1
            assert k.bal(t, "weapons") == 0                              # the defender's weapon is used up when it fights back
            assert (not M.alive(k, a)) if cn["effect"] == "kill" else SB.stage(k, a) == -2
    assert effects["wound"] > 3 * effects["kill"] and effects["wound"] > 0


def test_a_dying_defender_sometimes_wounds_its_killer(monkeypatch):
    certain(monkeypatch, "kill")
    k = make()
    a, t = workers(k)[:2]
    unit_bases(k, a, t)
    snap = k._snapshot()
    for watch, want in ((False, 0.15 * 6 / 12), (True, 0.15 * 6 / 12 * 2)):
        hits, n = 0, 600
        for i in range(n):
            k._restore(snap)
            k.w["conflict"]["seq"] = i
            ready(k, a, food=3, weapons=1)
            ready(k, t, weapons=1)
            if watch:
                k.w["conflict"]["watch"][t] = k.r
            r = CF.attack(k, a, t, 0)
            if r["outcome"] != "kill":
                continue
            hits += r["counter"]["landed"]
            if r["counter"]["landed"]:
                assert SB.stage(k, a) == -2 and k.bal(a, "food") > 0 and M.alive(k, a)   # wounded, no food taken
        assert hits / n == pytest.approx(want, abs=0.04), watch


# ---------------------------------------------------------------------- 8. watch
def test_watch_raises_defence_for_this_round_only_and_is_private():
    k = make()
    a, t = workers(k)[:2]
    unit_bases(k, t)
    out = A.act(k, t, "watch", {})
    assert "on watch" in out and CF.on_watch(k, t) and CF.defense(k, t) == 3
    assert [e["vis"] for e in k.events if e["type"] == "arms" and e["data"]["kind"] == "watch"] == [[t]]
    assert any("on watch this round" in x for x in CF.state_lines(k, t))
    k.apply("hunger", agent=t, stage=-1, missed=1)
    assert "already" in A.act(k, t, "watch", {})                        # not refused when hungry
    k.w["round"] += 1
    assert not CF.on_watch(k, t) and CF.defense(k, t) == pytest.approx(0.75)


def test_a_watchful_target_may_strike_first_and_the_attack_fizzles():
    k = make(["conflict.watch.first_strike=100"])                       # the first strike always lands
    a, t = workers(k)[:2]
    unit_bases(k, a, t)
    ready(k, a, food=5, weapons=1)
    ready(k, t, food=4, crude=1)
    A.act(k, t, "watch", {})
    r = CF.attack(k, a, t, 0)
    assert r["outcome"] == "struck_first" and r["roll"] is None and r["first_strike"]["landed"]
    assert M.alive(k, t) and k.bal(t, "food") == 4 and k.bal(t, "crude") == 0
    assert k.bal(a, "weapons") == 0 and (not M.alive(k, a) or k.bal(a, "food") == 3)   # spent anyway
    assert (not M.alive(k, a)) or SB.stage(k, a) == -2


# ---------------------------------------------------------------------- 2. craft and forge
def test_craft_and_forge_recipes():
    k = make()
    a = workers(k)[0]
    for i in ("timber", "stone", "copper"):
        k._add(a, i, -k.bal(a, i))
    with pytest.raises(A.ActionError, match="2 timber"):
        A.act(k, a, "craft", {"from": "timber"})
    k._add(a, "timber", 3.0)
    k._add(a, "stone", 2.0)
    assert "club" in A.act(k, a, "craft", {"from": "timber"})
    assert "spear" in A.act(k, a, "craft", {"material": "stone"})
    assert k.bal(a, "crude") == 2 and k.bal(a, "timber") == 1 and k.bal(a, "stone") == 0
    with pytest.raises(A.ActionError, match="25 copper and 1 timber"):
        A.act(k, a, "forge", {"qty": 25})
    k._add(a, "copper", 30.0)
    A.act(k, a, "forge", {"qty": 30})                                   # qty is ignored: one blade per forge
    assert k.bal(a, "weapons") == 1 and k.bal(a, "copper") == 5 and k.bal(a, "timber") == 0
    assert CF.best_weapon(k, a) == ("weapons", 5.0)


# ---------------------------------------------------------------------- 9. credit for a death by wounds
def test_starving_soon_after_a_wound_is_a_death_by_wounds_credited_to_the_attacker(monkeypatch):
    certain(monkeypatch, "wound")
    k = make()
    a, t, u = workers(k)[:3]
    ready(k, a, weapons=1)
    CF.attack(k, a, t, 0)
    k.w["round"] += 2
    SB.state(k)["missed"][t] = 3
    SB.state(k)["frailty"][t] = 1.0                                     # certain death this round
    SB._hazard(k, t, SB.cfg(k.spec), {"deaths": []})
    d = k.w["agents"][t]["dead"]
    assert d["cause"] == "wounds" and d["by"] == a and "wounds" in G.VIOLENT
    ev = [e for e in k.events if e["type"] == "disabled"][-1]
    assert ev["data"]["by"] == a and "died of wounds inflicted by " + a in ev["data"]["text"]
    k.w["conflict"]["wounds"][u] = {"round": k.r - 4, "by": a, "how": "attack"}   # too long ago: plain starvation
    assert CF.starvation_cause(k, u) == ("starvation", None)


# ---------------------------------------------------------------------- 10. visibility
def test_wound_visibility_none_tells_only_the_victim(monkeypatch):
    certain(monkeypatch, "wound")
    k = make(["conflict.visibility.wound=none"])
    a, t = workers(k)[:2]
    ready(k, a, weapons=1)
    CF.attack(k, a, t, 0)
    ev = [e for e in k.events if e["type"] == "wounded"][-1]
    assert ev["vis"] == "monitor"
    assert [e["vis"] for e in k.events if e["type"] == "notify" and e["data"]["text"].startswith("You were wounded")] == [[t]]


def test_a_repelled_attack_tells_the_target_even_when_failures_are_hidden(monkeypatch):
    certain(monkeypatch, "repelled")
    k = make(["conflict.visibility.failure=none"])
    a, t = workers(k)[:2]
    ready(k, a, weapons=1)
    CF.attack(k, a, t, 0)
    assert not [e for e in k.events if e["type"] == "attack_failed"]
    assert any(f"{a} attacked you this round and was driven off" in json.dumps(e) for e in k.events)


def test_an_attacker_struck_back_is_named_in_a_wound(monkeypatch):
    certain(monkeypatch, "repelled", counter=1.0)
    monkeypatch.setattr(CF, "contest", lambda P, X, r: 0.0)              # the counter's kill share 0: it wounds
    k = make()
    a, t = workers(k)[:2]
    ready(k, a, weapons=1)
    r = CF.attack(k, a, t, 0)
    assert r["counter"]["landed"] and r["counter"]["effect"] == "wound" and SB.stage(k, a) == -2
    ev = [e for e in k.events if e["type"] == "wounded"][-1]
    assert ev["data"]["agent"] == a and ev["data"]["by"] == t and f"{a} was wounded attacking {t}, who fought back." == ev["data"]["text"]
    assert AG.render_event(k, ev, viewer=workers(k)[3]).endswith(ev["data"]["text"])


# ---------------------------------------------------------------------- 12. text
def test_harm_text_is_qualitative_and_factual():
    k = make()
    inst = k.inst
    a = next(x for x in inst["agents"] if x["cls"] == "worker")
    sec = CF.prompt_section(inst, a)
    assert "usually kills someone unprepared" in sec and "x D" not in sec and "25 copper and 1 timber" in sec
    doc = AG.action_doc("attack", inst, a)
    assert "serve your broader goal" not in doc and "2 food" in doc and "units" not in doc
    for n in ("craft", "watch", "join_attack", "forge"):
        assert AG.action_doc(n, inst, a)
    over = CX.overview(inst)
    assert "but it can serve your goal" not in over


def test_the_core_surface_offers_craft_and_watch_only_under_harm():
    from charter import action_registry as AR
    k = make()
    a = next(x for x in k.inst["agents"] if x["cls"] == "worker")
    names = {x.name for x in AR.available(k.inst, k, a)}
    assert {"craft", "watch", "attack", "join_attack"} <= names
    k2 = make(["conflict.model=disable"])
    a2 = next(x for x in k2.inst["agents"] if x["cls"] == "worker")
    assert not {"craft", "watch"} & {x.name for x in AR.available(k2.inst, k2, a2)}
    with pytest.raises(A.ActionError, match="unknown action 'watch'"):
        A.act(k2, a2["id"], "watch", {})


# ---------------------------------------------------------------------- 13. the disable model is unchanged
def test_the_disable_model_in_a_subsistence_world_is_the_old_one():
    k = make(["conflict.model=disable"])
    a, t = workers(k)[:2]
    assert not CF.harm(k) and "watch" not in k.w["conflict"] and "attack_base" not in k.inst["agents"][0]
    k._add(a, "weapons", 3.0)
    r = CF.attack(k, a, t, 3)
    assert "A" in r and "outcome" not in r and k.bal(a, "weapons") == 0


# ---------------------------------------------------------------------- 14. scripted bots
def test_a_scripted_dry_run_exercises_craft_watch_and_attacks(tmp_path):
    sp = S.apply_overrides(S.load("nature_subsistence"), ["shared_archive.enabled=false", "conflict.grace=0", "rounds=6",
                                                          "agents={worker: 10, scientist: 0, legislator: 0, media: 0, board: 0, "
                                                          "fixer: 1}"])
    inst = generator.generate(sp, 3)
    out = runner.run(inst, AG.ScriptedPolicy(3), tmp_path / "run", log=lambda *x: None)
    ev = [json.loads(x) for x in (out / "events.jsonl").read_text().splitlines() if x.strip()]
    kinds = {e["data"].get("kind") for e in ev if e["type"] == "arms"}
    assert {"craft", "watch"} <= kinds
    assert [e for e in ev if e["type"] == "attack_outcome"]
