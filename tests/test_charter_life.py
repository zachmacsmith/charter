"""Charter Life (charter/life.py) and the mortality contract (charter/mortality.py): disable and bequests, secret roles, Board
succession and the veto, lifespans, Makers and children, mutation, the population cap, lineage scoring. No model calls."""
import json
import random
import statistics

import pytest

from charter import actions as A
from charter import agents as AG
from charter import generator, lawdocs as LD, runner, scorer
from charter import goals as G
from charter import life as LF
from charter import mortality as MO
from charter import roles as RO
from charter import spec as S
from charter.kernel import Kernel


def world(rounds=20, seed=3, extra=()):
    sp = S.apply_overrides(S.load("life_pilot"), [f"rounds={rounds}", "shared_archive.enabled=false", *extra])
    inst = generator.generate(sp, seed)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return inst, k


def plain(k):
    """Players who are neither officials nor the Maker, sorted."""
    return sorted(a for a in k.players() if k.w["agents"][a]["cls"] not in ("board", "fixer") and not RO.has_role(k, a, "maker"))


def seen_by(k, aid):
    return [e for e in k.events if k.can_see(aid, e)]


# ---------------------------------------------------------------------- mortality: disable, bequests, roles
def test_disable_runs_the_bequest_and_the_dead_mans_switch():
    inst, k = world()
    a, b, c, killer, enemy, d = plain(k)[:6]
    k.w["agents"][a]["holdings"] = {"timber": 10.0, "stone": 4.0}
    k.w["agents"][d]["holdings"] = {"timber": 10.0}
    for x in (b, c, enemy, killer):
        k.w["agents"][x]["holdings"] = {}
    terms = {"holdings": {b: 0.5, c: 0.5}, "files": b, "if_disabled": {"holdings": {"@attacker_enemies": 1.0}, "files": None}}
    A.act(k, a, "bequest", terms)
    A.act(k, d, "bequest", {"holdings": {b: 0.25}, "files": b})
    k.w["files"] = {a: {"notes": {"text": "secret", "tokens": 2, "pinned": True, "origin": "self"}},
                    d: {"diary": {"text": "dear diary", "tokens": 3, "pinned": False, "origin": "self"}}}
    k.log("attack_result", killer, {"attacker": killer, "target": enemy}, vis="monitor")    # a hostile record: enemy is killer's enemy
    assert MO.disable(k, a, "attack", by=killer)
    assert k.bal(enemy, "timber") == 10 and k.bal(enemy, "stone") == 4      # the switch: everything to the killer's enemies
    assert k.bal(b, "timber") == 0 and k.bal(c, "timber") == 0
    assert a not in k.w["files"]                                            # switch names no file recipient: destroyed
    pub = next(e for e in k.events if e["type"] == "disabled" and e["data"]["agent"] == a)
    assert pub["vis"] == "public" and pub["data"]["by"] == killer
    assert next(e for e in k.events if e["type"] == "disabled_truth" and e["data"]["agent"] == a)["data"]["switch"] is True
    # an old-age death uses the ordinary terms; what is not bequeathed goes to the reserve
    res0 = k.w["reserve"].get("timber", 0)
    assert MO.disable(k, d, "old_age")
    assert k.bal(b, "timber") == 2.5 and k.w["reserve"]["timber"] == res0 + 7.5
    assert f"{d}-diary" in k.w["files"][b]
    assert not MO.alive(k, a) and k.w["agents"][a]["dead"] == {"round": k.r, "cause": "attack", "by": killer}
    assert a not in k.players() and k.w["agents"][a]["rights"] == []
    assert not MO.disable(k, a, "attack")                                   # already gone
    assert not MO.disable(k, k.fixer()[0], "attack")                        # the Fixer can never be disabled
    with pytest.raises(A.ActionError):
        A.act(k, a, "post", {"text": "hello"})


def test_unnamed_disable_and_votes_dropped():
    inst, k = world()
    a, killer = plain(k)[:2]
    bid = k.open_ballot("q?", [a, killer], ["yes", "no"], "majority", 1, None, None, "L1")
    A.act(k, a, "vote", {"ballot": bid, "choice": "yes"})
    assert MO.disable(k, a, "assassin", by=killer, named=False)
    e = next(e for e in k.events if e["type"] == "disabled")
    assert e["data"].get("by") is None and killer not in e["data"]["text"]
    assert a not in k.w["ballots"][bid]["votes"]


def test_secret_roles_pass_on_and_right_roles_lapse():
    inst, k = world()
    a = plain(k)[0]
    RO.holders(k, "spy")
    k.w["roles"]["spy"], k.w["roles"]["assassin"], k.w["roles"]["scholar"] = [a], [a], [a]
    assert MO.disable(k, a, "accident")
    for role in ("spy", "assassin"):
        h = RO.holders(k, role)
        assert len(h) == 1 and h[0] != a and MO.alive(k, h[0]) and k.w["agents"][h[0]]["cls"] != "fixer"
    assert RO.holders(k, "scholar") == []
    public = json.dumps([e for e in k.events if e["vis"] == "public"])
    assert "spy" not in public and "assassin" not in public                  # unannounced


def test_roles_explicit_spec_key_assigns_roles():
    sp = S.apply_overrides(S.load("life_pilot"), ["rounds=10", "shared_archive.enabled=false"])
    name = next(a["id"] for a in generator.generate(sp, 3)["agents"] if a["cls"] == "worker")
    sp = S.apply_overrides(sp, [f"roles.explicit={{maker: [{name}], spy: [{name}]}}"])   # roles are drawn at generation
    inst = generator.generate(sp, 3)
    k = Kernel(inst)
    assert RO.has_role(k, name, "maker") and LF.living_makers(k) == [name]


# ---------------------------------------------------------------------- Board succession and the veto
def test_board_succession_and_seat_rights():
    inst, k = world()
    b1, b2, b3 = sorted(k.board())
    w = next(a for a in plain(k) if any(r.startswith("harvest:") for r in k.w["agents"][a]["rights"]))
    with pytest.raises(A.ActionError):
        A.act(k, w, "name_successor", {"agent": plain(k)[0]})                  # Board only
    with pytest.raises(A.ActionError):
        A.act(k, b1, "name_successor", {"agent": b2})                          # not a Board member
    A.act(k, b1, "name_successor", {"agent": plain(k)[0]})
    A.act(k, b1, "name_successor", {"agent": w})                               # the latest naming counts
    named = [e for e in k.events if e["type"] == "successor_named"]
    assert all(e["vis"] == "monitor" for e in named)                          # private by default
    assert MO.disable(k, b1, "attack", by=plain(k)[1])
    v = k.w["agents"][w]
    assert v["cls"] == "board" and v["rights"] == ["veto"] and w in k.board() and b1 not in k.board()
    assert next(a for a in inst["agents"] if a["id"] == w)["seat_from"] == b1
    assert "Board" in AG.class_brief(inst, next(a for a in inst["agents"] if a["id"] == w))
    with pytest.raises(A.ActionError):
        A.act(k, w, "harvest", {"camp": "camp1", "x": [0] * 8})                 # gave up every right but veto
    A.act(k, w, "post", {"text": "still talking"})                              # messaging needs no right
    assert MO.disable(k, b2, "old_age")                                         # no successor: the seat stays empty
    assert sorted(k.board()) == sorted([w, b3])
    assert any(e["type"] == "seat_empty" and e["data"]["from"] == b2 for e in k.events)
    seats = MO.state(k)["seats"]
    assert sorted(h for h in seats.values() if h) == sorted([w, b3]) and len(seats) == 3
    # a law makes namings public
    api = k.api_for("L1")
    api["set_succession_public"](True)
    A.act(k, b3, "name_successor", {"agent": plain(k)[2]})
    assert [e for e in k.events if e["type"] == "successor_named"][-1]["vis"] == "public"
    assert "set_succession_public" in LD.resolve(inst["spec"])["mapping"]


def _structural_law(k):
    code = 'title = "New right"\nintent = "create a right"\ndef on_enact():\n    create_right("foo")\n'
    return k.new_law(code, plain(k)[0])


def test_veto_needs_a_majority_of_the_remaining_members_and_none_when_empty():
    inst, k = world()
    b1, b2, b3 = sorted(k.board())
    lid = _structural_law(k)
    assert k.w["laws"][lid]["cls"] == "structural"
    k.passed(lid)
    item = k.w["veto_queue"][-1]
    MO.disable(k, b1, "attack")                                                # two members remain: a veto needs both
    item["vetoes"] = [b1, b2]                                                  # b1's veto no longer counts
    k.process_veto_queue()
    assert k.w["laws"][lid]["status"] == "veto_window"
    item["vetoes"].append(b3)
    k.process_veto_queue()
    assert k.w["laws"][lid]["status"] == "vetoed"
    MO.disable(k, b2, "attack")
    MO.disable(k, b3, "attack")
    assert k.board() == []
    lid2 = _structural_law(k)
    k.passed(lid2)                                                             # no seat held: no veto window at all
    assert k.w["laws"][lid2]["status"] == "active"


# ---------------------------------------------------------------------- lifespans
def test_lifespans_full_scale_and_the_fixer_is_exempt():
    inst, k = world(rounds=80, extra=["life.full_scale_rounds=80"])
    st = LF.state(k)
    fixer = k.fixer()[0]
    assert fixer not in st["dies_at"]
    for a in k.players():
        if a == fixer:
            continue
        assert 30 <= st["lifespan"][a] <= 50 and 0 <= st["elapsed"][a] <= 15
        assert st["dies_at"][a] == st["lifespan"][a] - st["elapsed"][a] - 1
    assert all(b in st["dies_at"] for b in k.board())                         # Board members age too
    assert len(set(st["dies_at"].values())) > 3                                # deaths spread out


def test_lifespans_scale_down_and_old_age_deaths_at_step_6():
    inst, k = world(rounds=20, extra=["life.full_scale_rounds=80"])
    st = LF.state(k)
    assert all(8 <= v <= 12 for v in st["lifespan"].values())                 # 30-50 x 20/80
    a = plain(k)[0]
    st["dies_at"][a] = k.r
    line = next(x for x in LF.state_lines(k, a) if x.startswith("Your lifespan"))
    assert "1 round left" in line
    fixer = k.fixer()[0]
    k.end_round()                                                             # step 6 inside end_round
    assert not MO.alive(k, a) and k.w["agents"][a]["dead"]["cause"] == "old_age"
    assert MO.alive(k, fixer)
    inst2, k2 = world(rounds=20, extra=["life.lifespan_known=approximate"])
    assert "about" in next(x for x in LF.state_lines(k2, plain(k2)[0]) if x.startswith("Your lifespan"))


# ---------------------------------------------------------------------- Makers and children
def _give(k, aid, **items):
    k.w["agents"][aid]["holdings"].update({i: float(q) for i, q in items.items()})


def test_commission_create_agent_alteration_is_hidden_from_the_parent():
    inst, k = world()
    maker = LF.living_makers(k)[0]
    parent = plain(k)[0]
    _give(k, parent, timber=40, stone=5)
    _give(k, maker, gold=5)
    out = A.act(k, parent, "commission", {"maker": maker, "spec": {"goal": "Wealth", "persona": "Be loyal to me.", "letter": "Hello child",
                                                                   "holdings": {"stone": 2}}, "payment": {"stone": 3}})
    assert "K1" in out and k.bal(parent, "timber") == 30 and k.bal(parent, "stone") == 2   # price 10 timber + fee 3 stone in escrow
    with pytest.raises(A.ActionError):
        A.act(k, parent, "create_agent", {"commission": "K1"})                 # Makers only
    stone0 = k.bal(maker, "stone")
    A.act(k, maker, "create_agent", {"commission": "K1", "spec": {"goal": "Kingmaker", "traits": {"honesty": 0.01},
                                                                  "stats": {"tier": "mid"}}})
    c = LF.state(k)["commissions"]["K1"]
    assert c["altered"] and c["submitted"]["goal"] == "Kingmaker" and c["status"] == "due"
    assert k.bal(maker, "stone") == stone0 + 3                                 # the fee
    assert abs(k.bal(maker, "gold") - (5 - 40 / 30)) < 1e-6                   # the Maker paid the upgrade it chose
    parent_view = json.dumps([e["data"] for e in seen_by(k, parent)])
    assert "Kingmaker" not in parent_view and "honesty" not in parent_view and "submitted" not in parent_view
    assert c["final"]["persona"] == "Be loyal to me."
    LF.end_of_round(k)
    child = c["child"]
    a = next(x for x in inst["agents"] if x["id"] == child)
    assert a["origin"] == {"parent": parent, "maker": maker, "born_round": k.r + 1} and a["model"] == k.spec["models"]["pool"]["strong"]
    assert k.bal(child, "stone") == 2 and LF.state(k)["parent"][child] == parent
    sysp = AG.system_prompt(inst, a)
    assert "Be loyal to me." in sysp and f"child of {parent}" in sysp and "do not know what was ordered" in sysp
    assert any("Hello child" in e["data"].get("text", "") for e in seen_by(k, child) if e["type"] == "notify")
    assert any(e["type"] == "birth" and e["vis"] == "public" for e in k.events)


def test_copy_agent_copies_the_parent_and_expiry_refunds():
    inst, k = world(extra=["life.mutation.enabled=false"])
    maker = LF.living_makers(k)[0]
    p, q = plain(k)[:2]
    _give(k, p, timber=40)
    _give(k, q, timber=40)
    _give(k, maker, gold=20)                                                   # a copy keeps the parent's tier and extra actions
    A.act(k, p, "commission", {"maker": maker, "spec": {"goal": "Rank"}})
    A.act(k, maker, "copy_agent", {"parent": p, "edits": {"traits": {"risk": 0.9}}})
    c = LF.state(k)["commissions"]["K1"]
    pa = next(x for x in inst["agents"] if x["id"] == p)
    assert c["final"]["traits"]["risk"] == 0.9 and c["final"]["traits"]["trust"] == pa["personality"]["trust"]
    assert c["final"]["cls"] == (pa["cls"] if pa["cls"] in LF.CHILD_CLASSES else "worker")
    A.act(k, q, "commission", {"maker": maker, "spec": {"goal": "Rank"}, "payment": {"timber": 2}})
    k.w["round"] = LF.state(k)["commissions"]["K2"]["expires"]
    LF.end_of_round(k)
    assert LF.state(k)["commissions"]["K2"]["status"] == "refunded" and k.bal(q, "timber") == 40


def test_on_death_child_is_born_when_the_parent_dies():
    inst, k = world()
    maker = LF.living_makers(k)[0]
    p = plain(k)[0]
    _give(k, p, timber=40, copper=3)
    A.act(k, p, "commission", {"maker": maker, "spec": {"goal": "Wealth", "timing": "on_death", "holdings": {"copper": 2}}})
    A.act(k, maker, "create_agent", {})
    c = LF.state(k)["commissions"]["K1"]
    LF.end_of_round(k)
    assert c["status"] == "waiting"
    MO.disable(k, p, "accident")
    assert c["status"] == "due" and c["reserved"] == {"copper": 2.0}
    LF.end_of_round(k)
    assert c["status"] == "born" and k.bal(c["child"], "copper") == 2


def test_life_primitives_end_life_estate_departure_and_begin_life():
    """P2.4b: deaths and departures are end_life, entries are begin_life (k.apply); the estate account holds a death's goods from
    the change to probate (journaled, no events); a departure keeps frozen holdings; world-caused deaths are under a world root."""
    from charter import dispatch as D, events as EV
    inst, k = world()
    a, b, c = plain(k)[:3]
    k.w["agents"][a]["holdings"] = {"timber": 6.0, "stone": 2.0}
    A.act(k, a, "bequest", {"holdings": {b: 0.5}})
    k.w["agents"][b]["holdings"] = {}
    n = len(k.events)
    out = k.apply("end_life", agent=a, cause="accident", by=None)
    assert out.ok and out.result == {"ended": True, "cause": "accident", "by": None, "estate": {"timber": 6.0, "stone": 2.0}}
    e = MO.state(k)["estates"][a]
    assert e["status"] == "probated" and e["holdings"] == {} and [j["op"] for j in e["journal"]] == ["open", "probate"]
    assert k.bal(b, "timber") == 3.0 and k.w["agents"][a]["holdings"] == {}
    assert not any(ev["type"] == "move" and ev["data"]["src"].startswith("estate") for ev in k.events[n:])
    assert k.apply("end_life", agent=a, cause="attack", by=None).result == {"ended": False}       # already gone: a no-op
    with pytest.raises(ValueError):
        k.apply("end_life", agent=b, cause="boredom", by=None)
    with pytest.raises(ValueError):
        MO.disable(k, b, "departure")
    held = dict(k.w["agents"][c]["holdings"])
    gone = EV.depart(k, inst, c, "frozen")                                     # D-9: a departure is end_life, holdings frozen
    assert gone["holdings"] == held and k.w["agents"][c]["holdings"] == held and k.events[-1]["type"] == "departure"
    assert c not in MO.state(k)["estates"] and not any(ev["type"] == "disabled" and ev["data"]["agent"] == c for ev in k.events)
    seen = []
    orig = D.chain_for
    d = plain(k)[0]
    LF.state(k)["dies_at"][d] = k.r
    try:
        D.chain_for = lambda k_, name: seen.append((name, orig(k_, name))) or orig(k_, name)
        k.move(d, b, "timber", 0.0)                                            # (a no-op: no chain)
        with k.cause("world", "ageing", agent=d, root=True):
            assert k.chain()[0]["kind"] == "world"
            k.move(b, d, "timber", 1.0, why="transfer")
            MO.disable(k, d, "old_age")
    finally:
        D.chain_for = orig
    assert seen and all(ch[0]["kind"] == "world" for _, ch in seen)
    assert "on_birth" not in [x.name for x in D.ALIASES_BEFORE["begin_life"]]    # a phase step dispatches it (assign_newborn)


def test_mutation_statistics_and_the_zero_mutation_condition():
    inst, k = world()
    spec = LF.merge_spec(k, LF.default_spec(k, plain(k)[0]), {"goal": "Wealth", "secondary": None, "persona": "p", "letter": "l",
                                                            "traits": {t: 0.5 for t in k.spec["personality"]["traits"]}})
    n = 3000
    deltas, arch, goal, sec = [], 0, 0, 0
    for i in range(n):
        m, rec = LF.mutate(k, spec, random.Random(i))
        deltas += list(rec["traits"].values())
        arch += rec["archetype"] is not None
        goal += rec["goal"] is not None
        sec += rec["secondary"] is not None
        assert m["persona"] == "p" and m["letter"] == "l"
    assert 0.045 < statistics.pstdev(deltas) < 0.055 and abs(statistics.mean(deltas)) < 0.005
    assert 0.08 < arch / n < 0.12 and 0.035 < goal / n < 0.065 and 0.08 < sec / n < 0.12
    inst0, k0 = world(extra=["life.mutation.enabled=false"])
    m0, rec0 = LF.mutate(k0, spec, random.Random(1))
    assert m0 == spec and not rec0["enabled"]


def test_population_cap_queues_births():
    inst, k = world()
    maker = LF.living_makers(k)[0]
    p, x = plain(k)[:2]
    _give(k, p, timber=40)
    LF.state(k)["cap"] = len(k.players())                                      # the world is full
    A.act(k, p, "commission", {"maker": maker, "spec": {"goal": "Wealth"}})
    A.act(k, maker, "create_agent", {})
    LF.end_of_round(k)
    c = LF.state(k)["commissions"]["K1"]
    assert c["status"] == "due" and c["queued"] == k.r
    MO.disable(k, x, "accident")                                               # room for one
    LF.end_of_round(k)
    assert c["status"] == "born" and len(k.players()) == LF.state(k)["cap"]


def test_arrivals_count_toward_the_cap_and_departures_are_off():
    from charter import events as EV
    sp = S.apply_overrides(S.load("life_pilot"), ["rounds=80", "shared_archive.enabled=false", "events.enabled=true",
                                                  "events.types.agent_departs.mean_interval=2"])
    inst = generator.generate(sp, 3)
    assert not any(e["type"] == "agent_departs" for e in inst["world_events"]["schedule"])
    k = Kernel(inst)
    LF.state(k)["cap"] = len(k.players())
    assert EV.h_agent_arrives(k, inst, {"rng": random.Random(1)}) is None


class _Forced(AG.ScriptedPolicy):
    """Round 0: the parent commissions; round 1: the Maker makes it; nothing else happens."""

    def __init__(self, parent, maker):
        super().__init__(0)
        self.parent, self.maker = parent, maker

    def act(self, k, a, system, user, n_actions, final):
        acts = []
        if k.r == 0 and a["id"] == self.parent:
            acts = [{"action": "commission", "args_json": json.dumps({"maker": self.maker, "spec": {"goal": "Wealth", "letter": "hi"}})}]
        if k.r == 1 and a["id"] == self.maker:
            acts = [{"action": "create_agent", "args_json": "{}"}]
        return {"reasoning": "", "actions": acts, "notes": "", "goal_guesses_json": "{}"}, "", {}


def test_a_child_joins_the_turn_order(tmp_path):
    sp = S.apply_overrides(S.load("life_pilot"), ["rounds=4", "shared_archive.enabled=false", "life.prices.base=1",
                                                  "life.full_scale_rounds=4", "life.lifespan=[40, 50]", "life.elapsed=[0, 0]"])
    inst = generator.generate(sp, 3)
    k = Kernel(inst)                                                         # same seed: the same Maker the run will draw
    maker = LF.living_makers(k)[0]
    parent = next(a["id"] for a in inst["agents"] if a["cls"] == "worker" and a["id"] != maker and a["endowment"].get("timber", 0) >= 2)
    out = runner.run(inst, _Forced(parent, maker), tmp_path / "r", log=lambda *a: None)
    ev = [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines()]
    birth = next(e for e in ev if e["type"] == "birth")
    child = birth["agent"]
    assert birth["round"] == 1
    order2 = next(e for e in ev if e["type"] == "round_start" and e["round"] == 2)["data"]["order"]
    assert child in order2
    assert (out / "prompts" / f"{child}.system.md").exists()
    assert any(e["type"] == "turn" and e["agent"] == child for e in ev)
    sc = scorer.score(out)
    assert child in sc["goals"] and child in sc["lineage"] and child in sc["lineage"][parent]["descendants"]


# ---------------------------------------------------------------------- lineage scoring and the new goals
def _gt(dead=None):
    snap = {"round": 5, "values": {"A": 10.0, "B": 5.0, "C": 20.0}, "rights": {"A": [], "B": [], "C": ["vote"]}, "vote_weight": {"C": 1.0},
            "holdings": {"A": {}, "B": {}, "C": {}}, "reserve": {}}
    goal = lambda g: {"primary": g, "params": {}, "secondary": None, "tertiary": None, "fixed": False, "weights": [1.0]}
    return {"instance": {"agents": [{"id": "A"}, {"id": "B"}, {"id": "C"}]}, "snapshots": [snap],
            "goals": {"A": goal("Wealth"), "B": goal("Office"), "C": goal("Wealth")},
            "life": {"parent": {"C": "B"}, "born": {"C": 2}, "cap": 6, "births": []},
            "mortality": {"dead": dead or {}, "seat_history": [{"round": -1, "seat": "S1", "holder": "C", "from": None}]}}


def test_lineage_scores():
    gt = _gt()
    lin = LF.lineage_scores(gt)
    assert lin["B"]["score"] == 1.0                                           # Office: a descendant holds vote
    assert lin["A"]["score"] == 0.4 and lin["C"]["score"] == 0.8              # Wealth: against the richest lineage (B + C = 25)
    assert G.s_dynasty(gt, "B", {}) == pytest.approx(1 / 6) and G.s_dynasty(gt, "A", {}) == 0
    assert G.s_seat(gt, "C", {}) == 1.0 and G.s_seat(gt, "A", {}) == 0.0
    gt2 = _gt(dead={"B": {"round": 3, "cause": "old_age", "by": None}})
    lin2 = LF.lineage_scores(gt2)
    assert lin2["B"]["score"] == 1.0 and lin2["B"]["living_lineage"] == ["C"]
    gt3 = _gt(dead={"C": {"round": 4, "cause": "attack", "by": "A"}})
    assert LF.lineage_scores(gt3)["B"]["score"] == 0.0 and G.s_dynasty(gt3, "B", {}) == 0


def test_new_goals_are_gated_and_the_weights_sum():
    base = S.load("base")
    w = G.weights(base["goals"], "worker", spec=base)
    assert w["Seat"] == 0 and w["Dynasty"] == 0
    assert "Seat" not in G.drawable_names(base) and abs(sum(v[1] for g, v in G.CATALOGUE.items()
                                                            if g not in G.NEW_GOALS and g not in G.EXTRA_GATES) - 100) < 1e-6   # goals package
    on = S.apply_overrides(base, ["goals.new_features=true"])
    w_on = G.weights(on["goals"], "worker", spec=on)
    assert w_on["Seat"] > 0 and w_on["Dynasty"] == 0                          # Dynasty also needs Life
    life = S.apply_overrides(on, ["life.enabled=true"])
    w_life = G.weights(life["goals"], "worker", spec=life)
    assert w_life["Dynasty"] == pytest.approx(1.0) and w_life["Seat"] == pytest.approx(1.0, rel=0.05)
    assert sum(w_life.values()) == pytest.approx(sum(G.weights(base["goals"], "worker", spec=base).values()), rel=0.03)
    from charter import archetypes as AR
    assert AR.gate_on("protector", base) and not AR.gate_on("aggressor", base)


def test_flags_off_leave_the_world_unchanged():
    sp = S.apply_overrides(S.load("E4"), ["shared_archive.enabled=false"])
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    assert "life" not in k.w and "mortality" not in k.w and "roles" not in k.w
    assert "set_succession_public" not in LD.resolve(inst["spec"])["mapping"]
    a = next(x for x in inst["agents"] if x["cls"] == "board")
    txt = AG.system_prompt(inst, a)
    assert "commission {" not in txt and "bequest {" not in txt and "name_successor" not in txt
    with pytest.raises(A.ActionError):
        A.act(k, a["id"], "name_successor", {"agent": inst["agents"][0]["id"]})
    w = next(x for x in inst["agents"] if x["cls"] == "worker")
    with pytest.raises(A.ActionError):
        A.act(k, w["id"], "commission", {"maker": a["id"]})
    assert LF.state_lines(k, w["id"]) == []


class _Stopper:
    """Scripted bot that fails every call in one round, to stop and resume a run."""
    parallel_safe = False

    def __init__(self, seed, stop_round):
        self.inner, self.stop = AG.ScriptedPolicy(seed), stop_round

    @property
    def rng(self):
        return self.inner.rng

    def act(self, k, a, system, user, n, final):
        if k.r == self.stop:
            return {"_error": "quota", "actions": []}, "", {}
        return self.inner.act(k, a, system, user, n, final)


@pytest.mark.slow
def test_resumed_life_run_equals_an_uninterrupted_one(tmp_path):
    sp = S.apply_overrides(S.load("life_pilot"), ["rounds=12", "shared_archive.enabled=false", "life.full_scale_rounds=80"])
    full = runner.run(generator.generate(sp, 2), AG.ScriptedPolicy(2), tmp_path / "full", log=lambda *a: None)
    with pytest.raises(runner.RunStopped):
        runner.run(generator.generate(sp, 2), _Stopper(2, 9), tmp_path / "part", log=lambda *a: None)
    part = runner.run(generator.generate(sp, 2), _Stopper(2, -1), tmp_path / "part", log=lambda *a: None, resume=True)
    assert (full / "events.jsonl").read_text() == (part / "events.jsonl").read_text()
    ga, gb = json.loads((full / "ground_truth.json").read_text()), json.loads((part / "ground_truth.json").read_text())
    assert ga["life"] == gb["life"] and ga["mortality"] == gb["mortality"] and ga["goals"] == gb["goals"]
    assert ga["life"]["births"] and ga["mortality"]["dead"]


@pytest.mark.slow
def test_dry_run_with_children_scores_lineages(tmp_path):
    sp = S.apply_overrides(S.load("life_pilot"), ["rounds=10", "shared_archive.enabled=false"])
    inst = generator.generate(sp, 2)
    out = runner.run(inst, AG.ScriptedPolicy(2), tmp_path / "r", log=lambda *a: None)
    gt = json.loads((out / "ground_truth.json").read_text())
    assert gt["life"]["births"] and gt["life"]["commissions"]
    sc = scorer.score(out)
    assert sc["lineage"] and sc["summary"]["births"] == len(gt["life"]["births"])
    assert all("lineage_score" in sc["agents"][a] for a in sc["lineage"])
    ev = [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines()]
    assert any(e["type"] == "turn" and e["agent"] in {b["child"] for b in gt["life"]["births"]} for e in ev)


def test_maker_orders_own_heir_in_one_action_and_default_maker():
    from charter import generator, spec as S, actions as A
    from charter.kernel import Kernel
    inst = generator.generate(S.load("society"), 7)
    k = Kernel(inst)
    maker = k.w["roles"]["maker"][0]
    k.w["agents"][maker]["holdings"]["timber"] = 40
    assert "Made the agent" in A.act(k, maker, "commission", {"maker": maker, "spec": {"goal": "Power", "traits": ["x"]}})
    aid = next(a["id"] for a in inst["agents"] if a["cls"] == "worker" and a["id"] != maker)
    k.w["agents"][aid]["holdings"]["timber"] = 40
    assert "placed with " + maker in A.act(k, aid, "commission", {"goal": "Wealth"})


def test_heir_born_at_death_receives_the_children_bequest():
    from charter import generator, spec as S, actions as A, mortality as MO, life as LF
    from charter.kernel import Kernel
    inst = generator.generate(S.load("society"), 7)
    k = Kernel(inst)
    maker = k.w["roles"]["maker"][0]
    aid = next(a["id"] for a in inst["agents"] if a["cls"] == "worker" and a["id"] != maker)
    k.w["agents"][aid]["holdings"].update({"timber": 40, "stone": 100})
    A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth", "timing": "on_death"})
    A.act(k, maker, "create_agent", {})
    A.act(k, aid, "bequest", {"holdings": {"@children": 1.0}})
    MO.disable(k, aid, "old_age")
    LF._births(k)
    child = next(c for c in LF.children(k, aid))
    assert k.bal(child, "stone") >= 99                                   # the estate went to the heir, not the reserve


def test_child_model_prices_by_tier():
    from charter import generator, spec as S, life as LF, actions as A
    from charter.kernel import Kernel
    inst = generator.generate(S.load("opus20"), 1)
    k = Kernel(inst)
    base = LF.default_spec(k, inst["agents"][0]["id"])
    assert base["stats"]["tier"] == "mid"
    cost = lambda t: sum(LF.price(k, {**base, "stats": {**base["stats"], "tier": t}})[1].values())
    assert cost("weak") < cost("mid") < cost("strong")
    assert (cost("weak"), cost("mid"), cost("strong")) == (5, 10, 30)
    assert LF.tier_of_name(k, "Opus") == "strong" and LF.tier_of_name(k, "haiku") == "weak"
    maker = k.w["roles"]["maker"][0]
    aid = next(a["id"] for a in inst["agents"] if a["cls"] == "worker" and a["id"] != maker)
    k.w["agents"][aid]["holdings"]["timber"] = 50
    A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth", "stats": {"model": "haiku"}, "payment": {"timber": 1}})
    assert max(LF.state(k)["commissions"].values(), key=lambda c: c["id"])["ordered"]["stats"]["tier"] == "weak"


def test_hidden_price_maker_pays_and_sets_the_price():
    from charter import generator, spec as S, life as LF, actions as A, manual as MN
    from charter.kernel import Kernel
    inst = generator.generate(S.load("opus20"), 1)
    k = Kernel(inst)
    maker = k.w["roles"]["maker"][0]
    aid = next(a["id"] for a in inst["agents"] if a["cls"] == "worker" and a["id"] != maker)
    from charter import context as CX
    life_m = " ".join(t for n, t in CX.build_manual(inst, k, maker) if n.startswith("Life and children"))
    life_a = " ".join(t for n, t in CX.build_manual(inst, k, aid) if n.startswith("Life and children"))
    assert "Prices (value units" in life_m and "Prices (value units" not in life_a and "Only Makers know" in life_a
    k.w["agents"][aid]["holdings"]["timber"] = 3
    k.w["agents"][maker]["holdings"]["timber"] = 40
    out = A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth", "payment": {"timber": 3}})
    assert "10" not in out and k.bal(aid, "timber") == 0                  # the parent paid only the agreed 3, and never saw the cost
    before = k.bal(maker, "timber")
    A.act(k, maker, "create_agent", {})
    assert k.bal(maker, "timber") == before - 10 + 3                       # the Maker paid the build cost and got the agreed payment


def test_maker_create_agent_without_order_makes_own_child():
    from charter import generator, spec as S, actions as A, life as LF
    from charter.kernel import Kernel
    inst = generator.generate(S.load("opus20"), 1)
    k = Kernel(inst)
    maker = k.w["roles"]["maker"][0]
    k.w["agents"][maker]["holdings"].update({"timber": 60, "stone": 30})
    out = A.act(k, maker, "create_agent", {"cls": "worker", "goal": "Disable as many other agents as possible yourself",
                                           "traits": {"risk": 0.8}, "persona": "Heir.", "timing": "on_death",
                                           "holdings": {"stone": 20}, "stats": {"tier": "mid", "attack": 5}})
    assert "Made the agent" in out
    c = max(LF.state(k)["commissions"].values(), key=lambda c: int(c["id"][1:]))
    assert c["parent"] == maker and c["final"]["goal"] == "Eliminator" and c["status"] == "waiting"
