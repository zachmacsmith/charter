"""History (charter/history.py): the run as one read-only object that every goal scorer receives.

Scoring through History must not change a single number: per-agent goal scores equal a frozen copy of the pre-History scorer and
the goal scores stored with the golden fingerprints (tests/fixtures/charter_golden.json), including agents scored per segment
(arrival, goal change) and Life runs (lineage override). The native ports (goals.HSCORERS) equal their legacy scorers on every
run and every window; window() restricts every table; History loaded from disk equals History built from the runner's memory;
scoring is not slower. Everything is offline (ScriptedPolicy, shared archive off), like the golden tests.
"""
from __future__ import annotations

import copy
import json
import time

import pytest

import test_charter_golden as golden                     # the golden case builders (tests/ is on sys.path under pytest)
from charter import agents as AG
from charter import events as EV
from charter import generator, runner, scorer
from charter import goals as G
from charter import history as HI
from charter import spec as S
from charter.history import History


# ------------------------------------------------------------------ the golden runs, built once (with their in-memory parts)
class _JsonSpy:
    """Stands in for runner's `json` module: records the last ground-truth dict the runner serialises (still in memory)."""

    def __init__(self, store):
        self._store = store

    def dumps(self, obj, *a, **kw):
        if isinstance(obj, dict) and "rounds_played" in obj and "goals" in obj:
            self._store["truth"] = copy.deepcopy(obj)
        return json.dumps(obj, *a, **kw)

    def __getattr__(self, name):
        return getattr(json, name)


def _build(name, tmp):
    preset, seed, sets = golden.CASES[name]
    sp = S.apply_overrides(S.load(preset), sets + ["shared_archive.enabled=false"])
    inst = generator.generate(sp, seed)
    inst["run_id"] = f"golden_{name}"
    mem = {}
    real_begin, real_truth = runner.PV.begin, runner._truth

    def begin(out, inst_, *a, **kw):                     # the instance as it is written to instance.json (before the run edits it)
        mem["instance"] = json.loads(json.dumps(inst_, default=str))
        return real_begin(out, inst_, *a, **kw)

    def truth(out, inst_, k, *a, **kw):
        mem["snapshots"], mem["events"] = copy.deepcopy(k.snapshots), copy.deepcopy(k.events)
        return real_truth(out, inst_, k, *a, **kw)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(runner.PV, "begin", begin)
        mp.setattr(runner, "_truth", truth)
        mp.setattr(runner, "json", _JsonSpy(mem))
        out = runner.run(inst, AG.ScriptedPolicy(seed), tmp / name, log=lambda *a: None)
    return out, mem


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("history_golden")
    return {name: _build(name, tmp) for name in sorted(golden.CASES)}


# ------------------------------------------------------------------ the scorer as it was before History (frozen reference)
def _legacy_segment_views(gt, aid):
    out = []
    for r0, r1, goal in EV.segments(gt, aid) or []:
        idx = [i for i, s in enumerate(gt["snapshots"]) if r0 <= s["round"] <= r1]
        if not idx:
            out.append((r0, r1, goal, 0, None))
            continue
        prev = [s for s in gt["snapshots"] if s["round"] == r0 - 1]
        start = prev[0]["values"].get(aid, gt["start_values"].get(aid, 0.0)) if prev else gt["start_values"].get(aid, 0.0)
        g = {x: goal.get(x) for x in ("primary", "params", "secondary", "secondary_params", "tertiary", "tertiary_params", "weights")}
        g["params"] = g["params"] or {}
        g["fixed"] = goal.get("fixed", False)
        view = {**EV.window(gt, r0, r1), "goals": {**gt["goals"], aid: g}, "start_values": {**gt["start_values"], aid: start}}
        out.append((r0, r1, goal, len(idx), view))
    return out


def legacy_goal_scores(gt, only=None):
    """scorer.goal_scores as of 014a913: every s_* on the gt dict, segments as dict views."""
    out = {}
    for a in gt["instance"]["agents"]:
        if only is not None and a["id"] != only:
            continue
        aid, g = a["id"], gt["goals"][a["id"]]
        if EV.segments(gt, aid):
            parts = []
            for r0, r1, goal, n, view in _legacy_segment_views(gt, aid):
                if view is None:
                    parts.append({"from_round": r0 + 1, "to_round": r1 + 1, "goal": goal.get("primary"), "rounds": 0, "score": None})
                    continue
                res = legacy_goal_scores(view, only=aid)[aid]
                parts.append({"from_round": r0 + 1, "to_round": r1 + 1, "goal": goal.get("primary"), "rounds": n, **res})
            out[aid] = {"goal": g["primary"], "params": g.get("params", {}), "score": EV.by_rounds(parts), "segments": parts,
                        "rule": "per segment of rounds (arrival / goal change / departure), weighted by rounds"}
            continue
        if g["fixed"]:
            sc = G.board_score(gt, aid) if a["cls"] == "board" else G.fixer_score(gt, aid)
            out[aid] = {"goal": g["primary"], "score": round(sc, 4)}
            continue
        p = G.SCORERS[g["primary"]](gt, aid, g["params"])
        sec = G.SCORERS[g["secondary"]](gt, aid, g["secondary_params"]) if g.get("secondary") else None
        ter = G.SCORERS[g["tertiary"]](gt, aid, g.get("tertiary_params", {})) if g.get("tertiary") else None
        ws = g.get("weights") or ([0.6, 0.3, 0.1] if g.get("tertiary") else [0.7, 0.3] if g.get("secondary") else [1.0])
        parts = [(x, w) for x, w in zip([p, sec, ter], ws) if x is not None]
        total = None if p is None else sum(x * w for x, w in parts) / sum(w for _, w in parts)
        out[aid] = {"goal": g["primary"], "params": g["params"], "primary": p, "secondary": g.get("secondary"), "secondary_score": sec,
                    "tertiary": g.get("tertiary"), "tertiary_score": ter, "weights": ws,
                    "score": None if total is None else round(total, 4)}
    return out


def _windows(h):
    """Every (r0, r1) window of a short run, plus every scoring segment's view."""
    rs = h.rounds
    out = [h.window(r0, r1) for i, r0 in enumerate(rs) for r1 in rs[i:]]
    for a in h.agents:
        out += [v for *_, v in h.segment_views(a) if v is not None]
    return out


# ------------------------------------------------------------------ identical scores
@pytest.mark.parametrize("name", sorted(golden.CASES))
def test_scores_through_history_equal_the_legacy_scorer(runs, name):
    out, _ = runs[name]
    assert scorer.goal_scores(History.load(out)) == legacy_goal_scores(scorer.load(out))
    assert scorer.goal_scores(scorer.load(out)) == legacy_goal_scores(scorer.load(out))   # a legacy dict is still accepted


@pytest.mark.parametrize("name", sorted(golden.CASES))
def test_score_json_goal_scores_equal_the_golden_fixture(runs, name):
    """The stored per-agent goal scores (after the Life lineage override) come out unchanged."""
    out, _ = runs[name]
    want = json.loads(golden.GOLDEN.read_text())[name]["score"]["goal_scores"]
    sc = scorer.score(out)
    assert {aid: g.get("score") for aid, g in sorted(sc["goals"].items())} == want


def test_golden_runs_cover_segments_and_life(runs):
    """The comparison above includes agents scored per segment (arrival or goal change) and a Life run with births and deaths."""
    seg = {name: [a for a in History.load(out).agents if History.load(out).segments(a)] for name, (out, _) in runs.items()}
    assert any(seg.values()), seg
    reasons = set()
    for name, (out, _) in runs.items():
        h = History.load(out)
        for a in seg[name]:
            reasons.add(h.life(a).how)
            if len(h.segments(a)) > 1:
                reasons.add("goal change")
    assert "goal change" in reasons, reasons
    life = History.load(runs["society_small_4"][0])
    assert life.gt.get("life") and life.deaths
    assert any(life.life(a).how == "birth" for a in life.ever())


def _param_sets(h):
    """Parameters to score every goal with on a run: those its agents drew (every slot, every segment) and one generic set that
    names a resource, a library law, an outcome, an entity, a camp, a target, a partner and a right of this world."""
    from charter import library as LB
    out = {}
    goals = list(h.goals.values()) + [b[k] for b in (h.gt.get("world_events") or {}).get("goal_boundaries") or [] for k in ("old", "new")]
    for g in goals:
        for slot, pk in (("primary", "params"), ("secondary", "secondary_params"), ("tertiary", "tertiary_params")):
            if g.get(slot):
                out.setdefault(g[slot], []).append(g.get(pk) or {})
    camps = sorted(h.camp_resource) or ["c1"]
    agents = h.agents
    generic = {"resource": h.camp_resource.get(camps[0], "timber"), "law": sorted(LB.PREDICATES)[0], "condition": sorted(LB.OUTCOMES)[0],
               "entity": "board", "name": "the Elders", "word": "Archon", "camp": camps[0], "target": agents[1], "partner": agents[2],
               "slot": "primary", "right": "vote", "classes": "worker"}
    return {name: out.get(name, []) + [generic] for name in G.SCORERS}


def _outcome(fn, *a):
    try:
        return ("ok", fn(*a))
    except Exception as e:                                       # e.g. Wealth for an agent not in the final values: both must fail
        return ("error", None)


@pytest.mark.parametrize("name", sorted(golden.CASES))
def test_native_scorers_equal_legacy_scorers_on_every_window(runs, name, monkeypatch):
    """Every goal's native scorer (goals.HSCORERS) returns exactly what its legacy s_* returns, for every agent, on the whole run,
    every window and every scoring segment's view, with the parameters drawn in the run and a generic set."""
    cache = {}
    common = G._common_shingles
    monkeypatch.setattr(G, "_common_shingles", lambda inst: cache[id(inst)] if id(inst) in cache else cache.setdefault(id(inst), common(inst)))
    h = History.load(runs[name][0])
    assert set(G.HSCORERS) == set(G.SCORERS) and len(G.HSCORERS) == 70
    params = _param_sets(h)
    n = 0
    for v in [h] + _windows(h):
        agents = sorted(set(v.final["values"]) | set(v.start_values))
        ctx = HI.Ctx(v)
        for goal, native in G.HSCORERS.items():
            for p in params[goal]:
                for a in agents:
                    want = _outcome(G.SCORERS[goal], v.gt, a, p)
                    got = _outcome(native, v, a, p, ctx)
                    assert got == want, (goal, a, p, v)
                    n += 1
        for a in agents:
            for fixed, legacy_fn in ((G.h_board, G.board_score), (G.h_fixer, G.fixer_score)):
                assert _outcome(fixed, v, a) == _outcome(legacy_fn, v.gt, a)
    assert n > 1000


def test_ctx_score_of_follows_ally_and_foil_chains():
    from charter import goal_registry as GR
    h = GR.fixture(goals={"B": "Wealth"}, final={"values": {"A": 1.0, "B": 5.0, "C": 10.0, "D": 0.0}})
    h.gt["goals"]["C"] = {**h.gt["goals"]["C"], "primary": "Ally", "params": {"target": "B"}}
    h.gt["goals"]["D"] = {**h.gt["goals"]["D"], "primary": "Foil", "params": {"target": "C"}}
    ctx = HI.Ctx(h)
    assert ctx.score_of("B") == 0.5 and ctx.score_of("C") == 0.5 and ctx.score_of("D") == 0.5
    assert G.h_ally(h, "A", {"target": "D"}, ctx) == 0.5 == G.s_ally(h.gt, "A", {"target": "D"})
    h.gt["goals"]["B"] = {**h.gt["goals"]["B"], "primary": "Ally", "params": {"target": "C"}}   # B -> C -> B: a cycle
    ctx = HI.Ctx(h)
    assert ctx.score_of("C") is None and G.h_foil(h, "A", {"target": "C"}, ctx) is None is G.s_foil(h.gt, "A", {"target": "C"})
    assert ctx.score_of("A", "secondary") is None and ctx.score_of(None) is None
    w = ctx.at((1, 2))
    assert w.history is h.window(1, 2) and w.span == (1, 2) and ctx.at(None) is ctx


def test_scorer_for_returns_the_native_scorer(runs):
    h = History.load(runs["E2_seq_6"][0])
    fn = HI.scorer_for("Rank")
    a = h.agents[0]
    assert fn is G.h_rank and fn(h, a, {}, HI.Ctx(h)) == G.s_rank(h.gt, a, {})
    assert HI.legacy(G.s_rank)(h, a, {}) == G.s_rank(h.gt, a, {}) and HI.legacy(G.s_rank).legacy is G.s_rank
    assert HI.scorer_for("Wealth") is G.h_wealth
    with pytest.raises(KeyError):
        HI.scorer_for("No such goal")


# ------------------------------------------------------------------ API
def test_disk_equals_memory(runs):
    for name in ("society_small_4", "E7_events_3", "E4_observer_hidden_4"):
        out, mem = runs[name]
        h = History.from_run(mem["instance"], mem["snapshots"], mem["events"], mem["truth"])
        assert h == History.load(out), name
        assert h.gt == scorer.load(out)


def test_states_events_and_tables(runs):
    h = History.load(runs["society_small_4"][0])
    assert h.rounds == [s["round"] for s in h.gt["snapshots"]] and h.final is h.gt["snapshots"][-1]
    assert all(h.state(r)["round"] == r for r in h.rounds)
    assert h.series("values", h.agents[0]) == [s["values"].get(h.agents[0]) for s in h.states]
    ev = h.gt["events"]
    assert list(h.events()) == ev
    for t in {e["type"] for e in ev}:
        assert list(h.events(t)) == [e for e in ev if e["type"] == t]
    a = h.agents[0]
    assert list(h.events(agent=a)) == [e for e in ev if e["agent"] == a]
    both = ("transfer", "post")
    assert list(h.events(both, agent=a)) == [e for e in ev if e["type"] in both and e["agent"] == a]
    assert list(h.events("transfer", rounds=(1, 2))) == [e for e in ev if e["type"] == "transfer" and 1 <= e["round"] <= 2]
    assert list(h.events(rounds=[0, 3])) == [e for e in ev if e["round"] in (0, 3)]
    assert dict(h.laws) == h.gt["laws"] and dict(h.cases) == h.gt["cases"]
    assert dict(h.loans) == h.final.get("loans", {})
    assert h.deaths == G._dead(h.gt)
    calls = []
    assert h.cached("k", lambda x: calls.append(1) or 7) == 7 and h.cached("k", lambda x: calls.append(1) or 8) == 7
    assert calls == [1]


def test_roster_life_lineage_and_goals(runs):
    h = History.load(runs["society_small_4"][0])
    final = h.final["round"]
    for a in h.ever():
        lf = h.life(a)
        d = h.deaths.get(a)
        assert lf.how in ("founder", "arrival", "birth")
        if d is not None:
            assert lf.left == int(d["round"]) and lf.cause == d.get("cause")
            assert not h.alive(a, final) and h.alive(a, lf.left - 1) == (lf.entered <= lf.left - 1)
        if lf.how == "birth":
            assert lf.entered == int(h.gt["life"]["born"][a]) and not h.alive(a, lf.entered - 1)
        assert h.descendants(a) == __import__("charter.life", fromlist=["x"]).gt_descendants(h.gt, a)
        assert h.lineage(a, living=False)[0] == a
        assert set(h.lineage(a)) <= set(h.living(final))
    for s in h.states:                                     # the derived roster matches who is in the snapshot
        for a in s["values"]:
            assert h.life(a).entered <= s["round"] + 1
    for name in ("E7_events_3", "society_small_4"):
        he = History.load(runs[name][0])
        for a in he.agents:
            sp = he.spans(a)
            assert sp and sp[0].r0 == he.life(a).entered and sp[-1].r1 == he.final["round"]
            assert all(x.r1 + 1 == y.r0 for x, y in zip(sp, sp[1:]))
            assert all(he.goal_of(a, r) is x.goal for x in sp for r in x.rounds)
            segs = he.segments(a)
            if segs:                                       # scoring segments are the goal-held spans (score_at_end: no departure cut)
                assert [(x.r0, x.r1) for x in sp] == [(r0, r1) for r0, r1, _ in segs]
    he = History.load(runs["E7_events_3"][0])
    arr = (he.gt.get("world_events") or {}).get("arrivals") or {}
    for a, r in arr.items():
        assert he.life(a).how == "arrival" and he.life(a).entered == r and not he.present(a, r - 1)


def test_window_restricts_every_table(runs):
    for name in ("society_small_4", "E7_events_3", "E2_seq_6"):
        h = History.load(runs[name][0])
        final = h.final["round"]
        for r0, r1 in [(1, 2), (0, 1), (2, final), (h.rounds[0], final)]:
            w = h.window(r0, r1)
            assert w is h.window(r0, r1)                      # cached
            assert w.gt == EV.window(h.gt, r0, r1)            # one implementation
            assert w.rounds == [r for r in h.rounds if r0 <= r <= r1]
            assert all(r0 <= e["round"] <= r1 for e in w.events())
            assert list(w.events()) == [e for e in h.events() if r0 <= e["round"] <= r1]
            assert list(w.events("transfer")) == list(h.events("transfer", rounds=(r0, r1)))
            assert len(w.welfare) == len(w.states)
            assert all(l.get("enacted_round") is None or r0 <= l["enacted_round"] <= r1 for l in w.laws.values())
            assert all(l.get("proposed_round") is None or l["proposed_round"] <= r1 for l in w.laws.values())
            assert all(c.get("filed", 0) <= r1 for c in w.cases.values())
            assert all(int(d["round"]) <= r1 for d in w.deaths.values())
            assert (dict(w.guesses) == dict(h.guesses)) if r1 >= final else not w.guesses
            assert dict(w.loans) == (w.final.get("loans") or {})
            if h.gt.get("life"):
                assert all(int(b) <= r1 for b in w.gt["life"]["born"].values())
                assert all(r0 <= p.get("round", 0) <= r1 for p in w.gt["life"]["population"])
                assert all(int(h.gt["life"]["born"].get(x, 0)) <= r1 for a in w.ever() for x in w.descendants(a))
            assert all(int(r) <= r1 for r in (w._roster.get("arrivals") or {}).values())
            assert all(w.life(a).entered <= r1 for a in w.agents if a in (w._roster.get("arrivals") or {}))
            assert w.segments(w.agents[0]) is None            # a window is never split again
            nested = w.window(r0, r0)
            assert nested.gt == EV.window(w.gt, r0, r0)


def test_sugar_matches_hand_written_loops(runs):
    h = History.load(runs["E2_seq_6"][0])
    assert HI.at_end(h, lambda s: s["round"]) == h.final["round"]
    assert HI.mean_over_rounds(h, lambda s: min(s["stocks"].values())) == G.s_steward(h.gt, None, {})
    assert HI.peak(h, lambda s: s["round"]) == h.final["round"]


# ------------------------------------------------------------------ performance
def test_scoring_through_history_is_not_slower(runs):
    out = runs["society_small_4"][0]
    gt = scorer.load(out)

    def best(fn, n=25):
        ts = []
        for _ in range(n):
            t0 = time.perf_counter()
            fn()
            ts.append(time.perf_counter() - t0)
        return min(ts)

    old = best(lambda: legacy_goal_scores(gt))
    new = best(lambda: scorer.goal_scores(History(gt)))
    print(f"society_small_4 goal scoring: legacy {old * 1e3:.2f} ms, History {new * 1e3:.2f} ms")
    assert new <= old * 1.10 + 0.0003, (old, new)
