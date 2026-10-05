"""Charter world events (charter/events.py): schedule, visibility modes, rumour truth, goal changes, arrivals and departures.
No model calls, no Docker."""
import json

import pytest

from charter import actions as A
from charter import agents as AG
from charter import events as EV
from charter import generator, runner, scorer, report, spec
from charter.kernel import Kernel


def ev_spec(rung="E3", **over):
    s = spec.load(rung)
    s = spec.set_path(s, "shared_archive.namespace", "pytest")
    s = spec.set_path(s, "events.enabled", True)
    for k_, v in over.items():
        s = spec.set_path(s, k_.replace("__", "."), v)
    return s


def make(seed=1, **over):
    inst = generator.generate(ev_spec(**over), seed)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    return inst, k


def rs_for(inst):
    agents = {a["id"]: a for a in inst["agents"]}
    return {"agents": agents, "sysp": {a: "" for a in agents}, "cursors": {}, "start_values": {a: 0.0 for a in agents}, "out": None}


def fire(k, inst, typ, vis=None, seed=7, **cfg):
    """Fire one event of `typ` now, with the given visibility and parameters."""
    for key, v in {**({"visibility": vis} if vis else {}), **cfg}.items():
        inst["spec"]["events"].setdefault("types", {}).setdefault(typ, {})[key] = v
    return EV.fire(k, inst, {"id": f"T{len(EV.state(k)['fired']) + 1}", "round": k.r, "type": typ, "seed": seed})


def world_events(k, eid):
    return [e for e in k.events if e["type"] == "world_event" and e["data"]["event"] == eid]


def truth_of(k, eid):
    return next(e for e in k.events if e["type"] == "world_event_truth" and e["data"]["event"] == eid)


# ------------------------------------------------------------------ schedule
def test_disabled_events_leave_the_world_unchanged():
    s = spec.set_path(spec.load("E3"), "shared_archive.namespace", "pytest")
    a = generator.generate(s, 3)
    b = generator.generate(spec.set_path(s, "events.enabled", True), 3)
    assert "world_events" not in a and "world_events" in b
    b.pop("world_events")
    a["spec"].pop("events", None), b["spec"].pop("events", None)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def test_schedule_is_reproducible_poisson_and_per_type():
    s = ev_spec(rounds=400)
    x, y = generator.generate(s, 5)["world_events"], generator.generate(s, 5)["world_events"]
    assert x == y
    assert x != generator.generate(s, 6)["world_events"]
    counts = {}
    for e in x["schedule"]:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
        assert 1 <= e["round"] < 400
    assert 25 <= counts["rumor"] <= 60                      # mean interval 10 over ~400 rounds
    assert counts.get("camp_destroyed", 0) < counts["rumor"]
    # changing one type's rate leaves the other types' schedules alone (each type has its own RNG)
    z = generator.generate(spec.set_path(s, "events.types.rumor.mean_interval", 3), 5)["world_events"]
    strip = lambda w: [(e["round"], e["type"], e["seed"]) for e in w["schedule"] if e["type"] != "rumor"]
    assert strip(z) == strip(x)
    off = generator.generate(spec.set_path(s, "events.types.rumor.mean_interval", None), 5)["world_events"]
    assert not any(e["type"] == "rumor" for e in off["schedule"])


def test_goal_change_schedule_count_in_range():
    for seed in range(6):
        inst = generator.generate(ev_spec(), seed)
        gcs = inst["world_events"]["goal_changes"]
        assert 3 <= len(gcs) <= 5
        assert len({g["agent"] for g in gcs}) == len(gcs)
        fixed = {a["id"] for a in inst["agents"] if a["goal"].get("fixed")}
        assert not fixed & {g["agent"] for g in gcs}
        assert all(int(0.2 * inst["rounds"]) <= g["round"] <= int(0.8 * inst["rounds"]) for g in gcs)


def test_registry_takes_a_new_type_with_one_entry():
    calls = []

    def h(k, inst, ctx):
        calls.append(ctx["round"])
        return {"text": "A comet passes overhead.", "truth": "a comet", "true": True}
    before = generator.generate(ev_spec(rounds=60), 1)["world_events"]
    EV.register("comet", h, mean_interval=5, visibility="public")
    try:
        inst, k = make(rounds=60)
        assert any(e["type"] == "comet" for e in inst["world_events"]["schedule"])
        old = lambda w: [(e["round"], e["type"], e["seed"]) for e in w["schedule"] if e["type"] != "comet"]
        assert old(inst["world_events"]) == old(before)                                  # other types' draws unchanged
        fire(k, inst, "comet")
        assert calls and world_events(k, "T1")[0]["vis"] == "public"
    finally:
        EV.REGISTRY.pop("comet")


# ------------------------------------------------------------------ visibility modes
def test_public_event_reaches_everyone():
    inst, k = make()
    fire(k, inst, "camp_blight", "public")
    (e,) = world_events(k, "T1")
    assert e["vis"] == "public" and "Blight" in e["data"]["text"]
    blighted = [c for c in k.w["camps"].values() if c.get("blight")]
    assert len(blighted) == 1 and blighted[0]["max_yield"] == pytest.approx(0.2 * inst["spec"]["camps"]["max_yield"])
    cid = blighted[0]["id"]
    inst["world_events"]["schedule"] = []                     # only this blight
    for _ in range(10):
        k.end_round()
        k.start_round()
        EV.round_start(k, inst, rs_for(inst))
    c = k.w["camps"][cid]                                    # k.w is deep-copied by dry runs: look it up again
    assert c.get("blight") is None and c["max_yield"] == inst["spec"]["camps"]["max_yield"]


def test_discoverer_alone_learns_of_a_new_camp():
    inst, k = make()
    rec = fire(k, inst, "camp_discovered", "discoverer")
    (e,) = world_events(k, "T1")
    first = rec["draws"]["first"]
    assert e["vis"] == [first]
    cid = rec["details"]["camp"]
    assert k.w["camps"][cid]["known_by"] == [first]
    assert f"harvest:{cid}" in k.w["rights"]
    holder = rec["details"]["holder"]
    assert holder == (first if k.w["agents"][first]["cls"] == "worker" else None)
    other = next(a for a in k.w["agents"] if a != first)
    assert cid in AG.state_view(k, first) and cid not in AG.state_view(k, other)
    assert cid not in k.round_summary()
    assert [x for x in AG.feed(k, other, 0)[0].splitlines() if "new camp" in x] == []


def test_subset_reaches_some_agents():
    inst, k = make()
    rec = fire(k, inst, "camp_destroyed", "subset")
    es = world_events(k, "T1")
    told = [e["vis"][0] for e in es]
    assert 1 <= len(told) < len(k.w["agents"]) and sorted(told) == sorted(rec["recipients"])
    cid = rec["details"]["camp"]
    assert k.w["camps"][cid]["destroyed"] == k.r and k.w["camps"][cid]["S"] == 0
    holder = next((a for a in k.w["agents"] if f"harvest:{cid}" in k.w["agents"][a]["rights"]), None)
    if holder:
        with pytest.raises(A.ActionError, match="destroyed"):
            A.act(k, holder, "harvest", {"camp": cid, "x": [0] * k.w["camps"][cid]["dials"]})
    k.end_round()
    assert cid not in k.snapshots[-1]["stocks"]


def test_delayed_public_reaches_one_agent_then_everyone():
    inst, k = make()
    rec = fire(k, inst, "camp_discovered", "delayed", delay=2)
    first = rec["draws"]["first"]
    cid = rec["details"]["camp"]
    assert [e["vis"] for e in world_events(k, "T1")] == [[first]]
    rs = rs_for(inst)
    for _ in range(2):
        k.end_round()
        k.start_round()
        EV.round_start(k, inst, rs)
    es = world_events(k, "T1")
    assert [e["vis"] for e in es] == [[first], "public"] and es[1]["round"] == rec["round"] + 2
    assert k.w["camps"][cid]["known_by"] is None
    other = next(a for a in k.w["agents"] if a != first)
    assert cid in AG.state_view(k, other)


def test_none_visibility_tells_nobody_but_records_truth():
    inst, k = make()
    old = {c: json.dumps(v["fn"]) for c, v in k.w["camps"].items()}
    rec = fire(k, inst, "camp_function_changes")
    assert rec["visibility"] == "none" and world_events(k, "T1") == []
    t = truth_of(k, "T1")
    assert t["vis"] == "monitor" and "redrawn" in t["data"]["truth"]
    assert json.dumps(k.w["camps"][rec["details"]["camp"]]["fn"]) != old[rec["details"]["camp"]] or rec["details"]["old_fn"]["family"]


@pytest.mark.parametrize("p_false", [0.0, 1.0])
def test_rumours_reach_a_subset_and_their_truth_is_monitor_only(p_false):
    inst, k = make()
    rec = fire(k, inst, "rumor", p_false=p_false, kinds=["holdings"])
    es = world_events(k, "T1")
    assert 1 <= len(es) < len(k.w["agents"])
    assert all(e["data"]["text"].startswith("You hear a rumour:") for e in es)
    t = truth_of(k, "T1")
    assert t["vis"] == "monitor" and t["data"]["rumor"] is True and t["data"]["true"] is (p_false == 0.0)
    assert t["data"]["truth"].startswith("true" if p_false == 0.0 else "false")
    told = es[0]["vis"][0]
    seen = AG.feed(k, told, 0)[0]
    assert "You hear a rumour" in seen and "truth" not in seen and "false:" not in seen
    assert rec["true"] is (p_false == 0.0)


def test_false_rumours_are_plausible():
    inst, k = make()
    for i, kind in enumerate(["blight", "arrival", "camp", "deal", "departure"]):
        rec = fire(k, inst, "rumor", seed=100 + i, p_false=1.0, kinds=[kind])
        assert rec.get("true") is False, kind
        assert "false" in rec["truth"]
    texts = [e["data"]["text"] for e in k.events if e["type"] == "world_event"]
    assert any("blight" in t for t in texts) and any("newcomer" in t for t in texts) and any("new camp" in t for t in texts)


def test_misreported_event_through_a_rumour():
    inst, k = make()
    rec = fire(k, inst, "camp_blight", "rumor", p_false=1.0)
    real = rec["details"]["camp"]
    assert rec["true"] is False and real not in rec["text"] and "misreported" in rec["truth"]


# ------------------------------------------------------------------ agents
def test_add_agent_and_departure_in_the_kernel():
    inst, k = make()
    n = len(k.w["agents"])
    a = EV.add_agent(k, inst, cls="worker", rng=__import__("random").Random(3))
    assert len(k.w["agents"]) == n + 1 and a in inst["agents"] and a["id"] in k.w["agents"]
    assert a["goal"]["text"] and a["model"] and a["actions"] >= inst["spec"]["actions_per_turn"]
    assert any(r.startswith("harvest:") for r in a["rights"])
    assert EV.add_agent(k, inst, cls="board") is None and EV.add_agent(k, inst, cls="fixer") is None
    w = next(x for x in k.w["agents"] if k.w["agents"][x]["cls"] == "worker" and x != a["id"])
    k._add(a["id"], "timber", 5)
    EV.depart(k, inst, w, "frozen")
    assert not k.has(w, "vote") and k.w["agents"][w]["rights"] == []
    with pytest.raises(A.ActionError, match="left the world"):
        A.act(k, a["id"], "transfer", {"to": w, "item": "timber", "qty": 1})
    with pytest.raises(A.ActionError, match="left the world"):
        A.act(k, w, "post", {"text": "hi"})
    assert w not in k.api_for("x")["agents"]()
    v = next(x for x in k.w["agents"] if k.w["agents"][x]["cls"] == "legislator")
    held = dict(k.w["agents"][v]["holdings"])
    EV.depart(k, inst, v, "reserve")
    assert k.w["agents"][v]["holdings"] == {} and all(k.w["reserve"].get(i, 0) >= q for i, q in held.items())


def test_spawn_requests_go_through_add_agent():
    inst, k = make()
    sponsor = next(iter(k.w["agents"]))
    k.w["spawn_requests"] = [{"by": sponsor, "cls": "scientist"}]
    rs = rs_for(inst)
    EV.round_start(k, inst, rs)
    st = EV.state(k)
    new = st["spawned"][0]["agent"]
    assert new in k.w["agents"] and new in rs["agents"] and rs["sysp"][new] and k.w["spawn_requests"] == []
    assert k.w["agents"][new]["cls"] == "scientist" and next(a for a in inst["agents"] if a["id"] == new)["sponsor"] == sponsor
    assert any(e["type"] == "notify" and e["vis"] == [sponsor] for e in k.events)


def test_goal_change_only_the_agent_is_told():
    inst, k = make()
    gc = inst["world_events"]["goal_changes"][0]
    aid = gc["agent"]
    a = next(x for x in inst["agents"] if x["id"] == aid)
    old_text = a["goal"]["text"]
    rs = rs_for(inst)
    EV.change_goal(k, inst, {**gc, "round": k.r})
    EV.sync(k, inst, rs)
    assert a["goal"]["text"] != old_text and a["goal"]["text"] in rs["sysp"][aid]
    assert len(a["goal"].get("weights")) == len([s for s in ("primary", "secondary", "tertiary") if a["goal"].get(s)])
    notes = [e for e in k.events if e["type"] == "notify" and "goal has changed" in e["data"]["text"]]
    assert len(notes) == 1 and notes[0]["vis"] == [aid]
    for other in k.w["agents"]:
        if other != aid:
            assert "goal has changed" not in AG.feed(k, other, 0)[0]
    assert "goal has changed" in AG.feed(k, aid, 0)[0]
    b = EV.state(k)["boundaries"][0]
    assert b["old"]["text"] == old_text and b["new"]["text"] == a["goal"]["text"]


# ------------------------------------------------------------------ end to end
def _run(tmp_path, mode, name, seed=2, rounds=16, policy=None, resume=False):
    s = ev_spec(rounds=rounds, turns=mode, events__types__agent_arrives__mean_interval=4,
                events__types__agent_departs__mean_interval=6, events__types__rumor__mean_interval=3)
    inst = generator.generate(s, seed)
    out = runner.run(inst, policy or AG.ScriptedPolicy(seed), tmp_path / name, log=lambda *x: None, resume=resume)
    return inst, out


@pytest.mark.parametrize("mode", ["sequential", "simultaneous"])
def test_arrivals_and_departures_end_to_end(tmp_path, mode):
    inst, out = _run(tmp_path, mode, mode)
    gt = json.loads((out / "ground_truth.json").read_text())
    we = gt["world_events"]
    assert we["arrivals"] and we["departures"] and gt["arrived_agents"]
    rs = [json.loads(l) for l in (out / "reasoning.jsonl").read_text().splitlines()]
    for aid, r0 in we["arrivals"].items():
        turns = {r["round"] for r in rs if r["agent"] == aid and r.get("phase", "decide") == "decide"}
        end = we["departures"].get(aid, gt["rounds_played"])
        assert turns == set(range(r0, end)), aid
        assert (out / "prompts" / f"{aid}.system.md").exists()
        assert aid in gt["goals"] and aid in gt["start_values"]
    for aid, r1 in we["departures"].items():
        assert not any(r["agent"] == aid and r["round"] >= r1 for r in rs)
    res = scorer.score(out)
    for aid in list(we["arrivals"]) + [b["agent"] for b in we["goal_boundaries"]]:
        g = res["goals"][aid]
        assert "segments" in g and (g["score"] is None or 0 <= g["score"] <= 1)
    for aid in set(we["departures"]) - set(we["arrivals"]) - {b["agent"] for b in we["goal_boundaries"]}:
        g = res["goals"][aid]                                            # goals.score_at_end: scored on the whole run, not cut at leaving
        assert "segments" not in g and (g["score"] is None or 0 <= g["score"] <= 1)
    assert 3 <= len(we["goal_boundaries"]) + len(we["goal_changes_skipped"]) <= 5
    report.build(out)
    msgs = (out / "messages.md").read_text()
    assert "World event" in msgs and ("RUMOUR, TRUE" in msgs or "RUMOUR, FALSE" in msgs)
    ov = (out / "overview.md").read_text()
    assert "**World event**" in ov and "Goal change" in ov
    so = (out / "spec_outline.md").read_text()
    assert "## World events (hidden from agents)" in so and "### Arrived agents" in so and "### Fired events" in so
    for aid in we["arrivals"]:
        assert (out / "agents" / aid / "transcript.md").exists()


def test_goal_segments_are_scored_over_their_own_rounds(tmp_path):
    inst, out = _run(tmp_path, "sequential", "seg", rounds=16)
    gt = scorer.load(out)
    b = gt["world_events"]["goal_boundaries"][0]
    segs = EV.segments(gt, b["agent"])
    assert segs[0][1] == b["round"] - 1 and segs[1][0] == b["round"]
    assert segs[0][2]["primary"] == b["old"]["primary"] and segs[-1][2]["primary"] == gt["goals"][b["agent"]]["primary"]
    res = scorer.goal_scores(gt)[b["agent"]]
    parts = [p for p in res["segments"] if p["score"] is not None]
    if parts:
        tot = sum(p["rounds"] for p in parts)
        assert res["score"] == pytest.approx(sum(p["score"] * p["rounds"] for p in parts) / tot, abs=1e-4)


class Stopper:
    """Scripted bot that fails every call in one round (once), to stop and resume a run."""
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


def test_resumed_run_with_events_equals_an_uninterrupted_one(tmp_path):
    _, full = _run(tmp_path, "sequential", "full", rounds=12)
    with pytest.raises(runner.RunStopped):
        _run(tmp_path, "sequential", "part", rounds=12, policy=Stopper(2, 8))
    pol = Stopper(2, -1)
    _, part = _run(tmp_path, "sequential", "part", rounds=12, policy=pol, resume=True)
    a = (full / "events.jsonl").read_text()
    b = (part / "events.jsonl").read_text()
    assert a == b
    ga, gb = json.loads((full / "ground_truth.json").read_text()), json.loads((part / "ground_truth.json").read_text())
    assert ga["world_events"] == gb["world_events"] and ga["goals"] == gb["goals"]
