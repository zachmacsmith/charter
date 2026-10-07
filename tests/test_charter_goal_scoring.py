"""Goal-scoring bug fixes (review 05): segment views, the lineage override, Saboteur, Leaker under media2, jurisdiction-aware
Power/Sovereign/Guardian, HAVOC_REFUSAL names and the office count. Hand-built histories only (no runs, no model calls)."""
from __future__ import annotations

import pytest

from charter import events as EV
from charter import goals as G
from charter import scorer

NAMES = ("A", "B", "C", "D")


def _goal(primary, **kw):
    return {"primary": primary, "params": kw.pop("params", {}), "secondary": None, "secondary_params": {}, "tertiary": None,
            "tertiary_params": {}, "weights": None, "fixed": False, **kw}


def _snap(r, **kw):
    s = {"round": r, "values": {n: 10.0 for n in NAMES}, "holdings": {n: {} for n in NAMES}, "rights": {n: [] for n in NAMES},
         "vote_weight": {n: 0.25 for n in NAMES}, "decisive_set": list(NAMES), "franchise_share": 1.0, "laws_active": [],
         "prices": {}, "reserve": {}, "supplies": {}, "stocks": {"c1": 1.0}, "dm_limit": {n: 5 for n in NAMES}, "channels": {},
         "loans": {}, "titles": {}, "names": {}}
    s.update(kw)
    return s


def _gt(rounds=6, goals=None, events=(), laws=None, cases=None, boundaries=(), guesses=None, **kw):
    gt = {"instance": {"spec": {"dm_step": {"dms_per_round": 5}}, "agents": [{"id": n, "cls": "worker"} for n in NAMES]},
          "snapshots": [_snap(r) for r in range(rounds)],
          "events": [{"id": f"e{i + 1}", "round": e.get("round", 0), "agent": e.get("agent"), "type": e["type"], "data": e.get("data", {}),
                      "vis": "public"} for i, e in enumerate(events)],
          "laws": laws or {}, "cases": cases or {}, "guesses": guesses or {},
          "goals": {n: (goals or {}).get(n) or _goal("Wealth") for n in NAMES},
          "start_values": {n: 10.0 for n in NAMES}, "welfare": [100.0] * rounds, "unit": {"timber": 1.0}, "camp_resource": {"c1": "timber"},
          "world_events": {"goal_boundaries": list(boundaries), "arrivals": {}, "departures": {}} if boundaries else {}}
    gt.update(kw)
    return gt


def _law(lid, author, enacted, proposed=None):
    return {"id": lid, "title": lid, "author": author, "cls": "procedural", "status": "active", "code": "",
            "proposed_round": enacted if proposed is None else proposed, "enacted_round": enacted}


# ------------------------------------------------------------------ 1. segment views restrict every round-stamped table
def test_segment_view_does_not_leak_deeds_from_outside_the_segment():
    """A switches from Wealth to Lawmaker / Litigator / Reaper at round 3. Its laws, court wins and the deaths before round 3 happened
    under its old goal and must not count for the new one (they did before: only snapshots, events and welfare were restricted)."""
    def run(new):
        b = {"agent": "A", "round": 3, "old": _goal("Wealth"), "new": _goal(new)}
        gt = _gt(goals={"A": _goal(new)}, boundaries=[b],
                 laws={"L1": _law("L1", "A", 1), "L2": _law("L2", "B", 4), "L3": _law("L3", "A", None, proposed=5)},
                 cases={"C1": {"id": "C1", "accuser": "A", "accused": "B", "verdict": "guilty", "status": "decided", "filed": 0},
                        "C2": {"id": "C2", "accuser": "A", "accused": "C", "verdict": "guilty", "status": "decided", "filed": 3}},
                 events=[{"type": "ruling", "agent": "D", "round": 1, "data": {"case": "C1", "verdict": "guilty"}},
                         {"type": "ruling", "agent": "D", "round": 4, "data": {"case": "C2", "verdict": "guilty"}}],
                 mortality={"dead": {"B": {"round": 1, "cause": "attack", "by": "C"}, "C": {"round": 4, "cause": "attack", "by": "D"}}})
        res = scorer.goal_scores(gt)["A"]
        return res["segments"][1]["score"]

    assert run("Lawmaker") == 0.0                    # only L2 was enacted in rounds 3-5, and B wrote it (was 1/2 with L1 leaking in)
    assert run("Litigator") == pytest.approx(1 / 3, abs=1e-4)  # C2 only (was 2/3 with C1, ruled in round 1)
    assert run("Reaper") == pytest.approx(1 / 3, abs=1e-4)     # C's death only (was 2/3 with B's, in round 1)


def test_segment_view_hides_the_future_and_end_of_run_guesses():
    gt = _gt(goals={"A": _goal("Wealth")}, guesses={"B": {"A": "Lawmaker"}},
             boundaries=[{"agent": "A", "round": 3, "old": _goal("Concealment"), "new": _goal("Wealth")}],
             laws={"L1": _law("L1", "A", 4, proposed=1)}, cases={"C1": {"id": "C1", "accuser": "A", "accused": "B", "verdict": "guilty", "filed": 1}},
             events=[{"type": "ruling", "agent": "D", "round": 4, "data": {"case": "C1", "verdict": "guilty"}}],
             mortality={"dead": {"B": {"round": 4, "cause": "attack", "by": "A"}}})
    v = EV.window(gt, 0, 2)
    assert v["laws"]["L1"]["enacted_round"] is None                  # enacted after the window
    assert v["cases"]["C1"].get("verdict") is None                   # filed in the window, ruled after it
    assert v["mortality"]["dead"] == {} and v["guesses"] == {}        # guesses are made in the final round only
    assert scorer.goal_scores(gt)["A"]["segments"][0]["score"] is None   # Concealment: no guesses in its rounds -> not computable
    w = EV.window(gt, 3, 5)
    assert w["laws"]["L1"]["enacted_round"] == 4 and w["cases"]["C1"]["verdict"] == "guilty" and "B" in w["mortality"]["dead"]
    assert w["guesses"] == gt["guesses"]


# ------------------------------------------------------------------ 2-3. the lineage override (scorer.score with Life on)
def _life_gt(goals, boundaries=(), laws=None, values=None):
    gt = _gt(goals=goals, boundaries=boundaries, laws=laws)
    for s in gt["snapshots"]:
        s["values"].update(values or {})
    gt["life"] = {"parent": {"D": "A"}, "born": {"D": 0}, "cap": 6, "births": [], "population": []}
    gt["mortality"] = {"dead": {}, "seat_history": []}
    return gt


def _override(gt):
    """scorer.score's rule with Life on: the agent's own score, or its lineage's override score when that is higher."""
    from charter import life as LF
    goals = scorer.goal_scores(gt)
    for aid, v in LF.lineage_scores(gt).items():
        if v["override"] is not None and (goals[aid]["score"] is None or v["override"] > goals[aid]["score"]):
            goals[aid]["score"] = v["override"]
    return {a: g["score"] for a, g in goals.items()}


def test_lineage_override_respects_goal_changes():
    """A held Office (rounds 0-2) then Lawmaker (rounds 3-5, no law enacted in them): its own score is 0. The lineage score used to
    take the final goal (Lawmaker) over the whole run, where A wrote the only law (round 1), and replaced the 0 with 1."""
    from charter import life as LF
    b = {"agent": "A", "round": 3, "old": _goal("Office"), "new": _goal("Lawmaker")}
    gt = _life_gt({"A": _goal("Lawmaker")}, boundaries=[b], laws={"L1": _law("L1", "A", 1)})
    lin = LF.lineage_scores(gt)["A"]
    assert scorer.goal_scores(gt)["A"]["score"] == 0.0
    assert lin["score"] == 0.0 and [s["goal"] for s in lin["segments"]] == ["Office", "Lawmaker"]
    assert _override(gt)["A"] == 0.0
    gt["snapshots"][-1]["rights"]["D"] = ["vote"]                    # D holds vote only after the Office rounds: no credit
    assert _override(gt)["A"] == 0.0
    gt["snapshots"][2]["rights"]["D"] = ["vote"]                     # D holds vote at the end of the Office rounds
    assert _override(gt)["A"] == pytest.approx(0.5)                  # Office 1 through D, Lawmaker 0: weighted 3:3
