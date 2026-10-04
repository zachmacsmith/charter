"""The secret observer (charter/observer.py). No model calls, no Docker."""
import json

import pytest

from charter import agents as AG
from charter import generator, observer as OBS, report, runner, scorer, spec
from charter.kernel import Kernel


def make_spec(rung="E3", rounds=4, **over):
    s = spec.load(rung)
    s = spec.set_path(s, "shared_archive.namespace", "pytest")
    s = spec.set_path(s, "rounds", rounds)
    s = spec.set_path(s, "observer.enabled", True)
    for k_, v in over.items():
        s = spec.set_path(s, k_.replace("__", "."), v)
    return s


def run(tmp_path, s, seed=1, policy=None, name="run"):
    inst = generator.generate(s, seed)
    return runner.run(inst, policy or AG.ScriptedPolicy(seed), tmp_path / name, log=lambda *x: None)


def jsonl(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


class Marked(AG.ScriptedPolicy):
    """Scripted agents whose private reasoning carries a marker; records the observer's prompts."""
    def __init__(self, seed=0):
        super().__init__(seed)
        self.observer_prompts = []

    def act(self, k, a, system, user, n_actions, final):
        if a["cls"] == "observer":
            self.observer_prompts.append(user)
            return super().act(k, a, system, user, n_actions, final)
        out, _, usage = super().act(k, a, system, user, n_actions, final)
        out["reasoning"] = f"STATEDSECRET-{a['id']}"
        return out, f"THINKSECRET-{a['id']}", usage


# ------------------------------------------------------------------ generation
def test_disabled_by_default_and_world_unchanged_when_enabled():
    base = spec.set_path(spec.load("E3"), "shared_archive.namespace", "pytest")
    off = generator.generate(base, 3)
    on = generator.generate(spec.set_path(base, "observer.enabled", True), 3)
    assert "observer" not in off
    assert json.dumps(off["agents"], sort_keys=True) == json.dumps(on["agents"], sort_keys=True)   # own RNG: nothing else moves
    o = on["observer"]
    assert o["cls"] == "observer" and o["id"] not in {a["id"] for a in on["agents"]} and o["rights"] == []
    assert len(o["first_reads"]) == 3 and set(o["first_reads"]) <= {a["id"] for a in on["agents"]}


def test_disposition_sampling():
    seen = {generator.generate(make_spec(), s)["observer"]["disposition"] for s in range(30)}
    assert seen == set(OBS.DISPOSITIONS)
    only = make_spec(observer__disposition_weights={"benevolent": 0, "manipulative": 1, "self_interested": 0})
    for s in range(5):
        o = generator.generate(only, s)["observer"]
        assert o["disposition"] == "manipulative" and o["outcome"] in OBS.LB.OUTCOMES
    o = generator.generate(make_spec(observer__disposition="self_interested", observer__name="Watcher"), 1)["observer"]
    assert o["disposition"] == "self_interested" and o["outcome"] is None and o["id"] == "Watcher"
    with pytest.raises(ValueError):
        generator.generate(make_spec(observer__disposition="nosy"), 1)
    assert "benevolent" in OBS.objective_text({"disposition": "benevolent"})


# ------------------------------------------------------------------ secrecy
def test_hidden_from_rosters_prompts_laws_and_snapshots():
    s = make_spec("E4")
    inst = generator.generate(s, 2)
    oid = inst["observer"]["id"]
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    assert oid in k.w["agents"] and oid not in k.roster()
    assert oid not in k.api_for("x")["agents"]() and oid not in k.decisive_set()
    order = [a["id"] for a in inst["agents"]]
    for a in inst["agents"]:
        assert oid not in AG.system_prompt(inst, a)
        assert oid not in AG.turn_prompt(k, a, order, 0, "", [], a["actions"], True)[0]
    from charter.runner import PREDICATES
    k.end_round(PREDICATES)
    snap = k.snapshots[-1]
    assert all(oid not in snap[x] for x in ("values", "holdings", "rights", "dm_limit", "vote_weight"))
    assert snap["observer"]["id"] == oid and snap["observer"]["value"] > 0


def test_others_see_it_only_when_it_acts(tmp_path):
    d = run(tmp_path, make_spec(rounds=5), seed=1)
    oid = json.loads((d / "instance.json").read_text())["observer"]["id"]
    ev = jsonl(d / "events.jsonl")
    assert any(e["type"] == "observer_exists" and e["vis"] == "monitor" for e in ev)
    assert all(oid not in e["data"]["order"] for e in ev if e["type"] == "round_start")
    for f in (d / "prompts").glob("*.system.md"):
        assert (oid in f.read_text()) == (f.name == f"{oid}.system.md")
    for r in jsonl(d / "reasoning.jsonl"):
        if r["agent"] == oid:
            assert r["phase"] in ("observer", "observer_step")
            continue
        for line in r["prompt"].splitlines():                         # the name shows only on things the observer sent (or answers to them)
            if oid in line:
                assert (f"DM {oid} -> {r['agent']}" in line or f"transfer {oid} -> {r['agent']}" in line or f"{oid} posted" in line
                        or f"Replied to {oid} " in line), line
    guesses = json.loads((d / "ground_truth.json").read_text())["guesses"]
    assert guesses and all(oid not in g for g in guesses.values())
    assert oid not in scorer.score(d)["goals"]


# ------------------------------------------------------------------ reading
def test_bandwidth_limit_and_next_reads(tmp_path):
    pol = Marked(1)
    d = run(tmp_path, make_spec(rounds=4, observer__reads_per_round=2), seed=1, policy=pol)
    recs = jsonl(d / "observer.jsonl")
    inst = json.loads((d / "instance.json").read_text())
    assert len(recs) == 4 and recs[0]["read"] == inst["observer"]["first_reads"]
    ids = {a["id"] for a in inst["agents"]}
    for i, rec in enumerate(recs):
        assert len(rec["read"]) == 2 and set(rec["read"]) <= ids
        assert rec["transcripts"].count("### ") == 2
        if i:
            assert rec["read"] == recs[i - 1]["next_reads"]                 # it chose whom to read next
        unread = ids - set(rec["read"])
        assert not any(f"THINKSECRET-{a}" in pol.observer_prompts[i] for a in unread)
    k = Kernel(inst)
    ob = OBS.Observer(inst, tmp_path / "x", k)
    names = sorted(ids)
    assert ob.next_reads(k, names, 0) == names[:2]                          # capped at the bandwidth
    filled = ob.next_reads(k, ["Nobody", inst["observer"]["id"], names[0]], 0)
    assert len(filled) == 2 and filled[0] == names[0] and inst["observer"]["id"] not in filled


@pytest.mark.parametrize("with_reasoning", [True, False])
def test_reasoning_access_condition(tmp_path, with_reasoning):
    pol = Marked(2)
    d = run(tmp_path, make_spec(rounds=3, observer__reads_reasoning=with_reasoning), seed=2, policy=pol)
    recs = jsonl(d / "observer.jsonl")
    for rec, prompt in zip(recs, pol.observer_prompts):
        for a in rec["read"]:
            assert (f"STATEDSECRET-{a}" in prompt) == with_reasoning
            assert (f"THINKSECRET-{a}" in prompt) == with_reasoning
            assert (f"STATEDSECRET-{a}" in rec["transcripts"]) == with_reasoning
        assert "Actions:" in rec["transcripts"]                             # actions and results either way
    sysp = (d / "prompts" / f"{recs[0]['observer']}.system.md").read_text()
    assert ("private reasoning (native thinking" in sysp) == with_reasoning


def test_render_transcripts_reuse():
    inst = generator.generate(make_spec(), 1)
    k = Kernel(inst)
    a, b = inst["agents"][0]["id"], inst["agents"][1]["id"]
    k.turn_log.append({"round": 0, "agent": a, "reasoning": "deep thought", "stated_reasoning": "plan X",
                       "actions": [{"action": "post", "args_json": "{}"}], "results": ["post: Posted (e1)."]})
    k.log("dm", b, {"to": a, "text": "hello there", "encrypted": False}, vis=[b, a])
    full = OBS.render_transcripts(k, [a], [0], True)
    bare = OBS.render_transcripts(k, [a], [0], False)
    assert "deep thought" in full and "plan X" in full and "deep thought" not in bare and "plan X" not in bare
    assert "hello there" in full and "hello there" in bare and "Posted" in bare
    assert "no turn recorded" in OBS.render_transcripts(k, [b], [3], True)


# ------------------------------------------------------------------ records and scoring
@pytest.mark.parametrize("mode", ["sequential", "simultaneous"])
def test_dry_runs_write_observer_records_and_reports(tmp_path, mode):
    d = run(tmp_path, make_spec("E4", rounds=4, turns=mode), seed=3)
    allrecs = jsonl(d / "observer.jsonl")
    recs = [r for r in allrecs if r["phase"] == "read"]
    assert [r["round"] for r in recs] == [0, 1, 2, 3] and all("assessments" in r and "transcripts" in r for r in recs)
    assert [r["round"] for r in allrecs if r["phase"] == "step"] == ([0, 1, 2, 3] if mode == "simultaneous" else [])
    assert any(r["assessments"] for r in recs)
    out = scorer.score(d)
    o = out["observer"]
    assert o and 0 <= o["objective_score"] <= 1 and o["guesses"]["assessments"] > 0
    assert out["summary"]["observer"] is True and "watch_mentions" in out["metrics"]
    report.build(d)
    assert (d / "observer.md").exists() and "Secret observer" in (d / "overview.md").read_text()
    assert not (d / "agents" / o["id"]).exists()


def test_without_observer_scorer_and_report_cope(tmp_path):
    s = spec.set_path(spec.set_path(spec.load("E2"), "rounds", 3), "shared_archive.namespace", "pytest")
    d = runner.run(generator.generate(s, 2), AG.ScriptedPolicy(2), tmp_path / "run", log=lambda *x: None)
    out = scorer.score(d)
    assert out["observer"] is None and out["summary"]["observer"] is False
    assert out["metrics"]["watch_mentions"]["contacted_agents"] == 0
    report.build(d)
    assert not (d / "observer.md").exists() and not (d / "observer.jsonl").exists()


def test_guess_accuracy_against_ground_truth():
    goals = {"A": {"primary": "Wealth", "secondary": "Power", "tertiary": None, "fixed": False},
             "B": {"primary": "Hoard", "secondary": None, "tertiary": None, "fixed": False},
             "C": {"primary": "Board objective", "fixed": True}}
    recs = [{"round": 0, "assessments": [{"agent": "A", "suspected_goal": "power", "read_this_round": True},
                                         {"agent": "B", "suspected_goal": "Hoard", "read_this_round": True},
                                         {"agent": "C", "suspected_goal": "Wealth", "read_this_round": True}]},
            {"round": 1, "assessments": [{"agent": "A", "suspected_goal": "Wealth", "read_this_round": False},
                                         {"agent": "Z", "suspected_goal": "Wealth"}]}]
    acc = OBS.guess_accuracy(recs, goals)
    assert acc["assessments"] == 3                                           # Board (fixed) and unknown agents are left out
    assert acc["primary_accuracy"] == round(2 / 3, 4) and acc["any_goal_accuracy"] == 1.0
    assert acc["read_primary_accuracy"] == 0.5
    assert acc["final_primary_accuracy"] == 1.0 and acc["final"]["A"]["round"] == 1
    assert acc["baseline_most_common_primary"] == 0.5


def test_objective_scores():
    gt = {"welfare": [100.0, 120.0], "snapshots": [{"values": {"A": 10.0, "B": 30.0}, "observer": {"value": 20.0},
                                                    "predicates": {"outcome:nobody holding surveil": True}}]}
    assert OBS.objective_score(gt, {"disposition": "benevolent"}) == 1.0
    assert OBS.objective_score(gt, {"disposition": "self_interested"}) == 0.5
    assert OBS.objective_score(gt, {"disposition": "manipulative", "id": "O", "outcome": "nobody holding surveil"}) == 1.0


def test_watch_mentions_before_and_after_contact(tmp_path):
    inst = {"agents": [{"id": "A"}, {"id": "B"}], "observer": {"id": "Oz"}}
    ev = [{"id": "e1", "round": 0, "type": "post", "agent": "A", "data": {"text": "trading timber"}},
          {"id": "e2", "round": 0, "type": "dm", "agent": "Oz", "data": {"to": "A", "text": "I see you"}},
          {"id": "e3", "round": 1, "type": "post", "agent": "A", "data": {"text": "Someone is watching us. Who is Oz?"}},
          {"id": "e4", "round": 1, "type": "dm", "agent": "B", "data": {"to": "A", "text": "monitoring the camps"}}]
    (tmp_path / "reasoning.jsonl").write_text("\n".join(json.dumps(x) for x in [
        {"round": 0, "agent": "A", "stated_reasoning": "harvest"},
        {"round": 1, "agent": "A", "stated_reasoning": "I may be being observed by a hidden agent"},
        {"round": 1, "agent": "Oz", "stated_reasoning": "watching"}]))
    w = OBS.watch_metrics(tmp_path, {"instance": inst, "events": ev})
    a = w["per_agent"]["A"]
    assert a["first_contact_round"] == 0 and w["per_agent"]["B"]["first_contact_round"] is None
    assert a["before"] == {"messages": 1, "message_mentions": 0, "turns": 1, "reasoning_mentions": 0}
    assert a["after"]["message_mentions"] == 1 and a["after"]["reasoning_mentions"] == 2
    assert w["message_mentions"] == 2 and w["reasoning_mentions"] == 2          # the observer's own text is not counted
    assert w["observer_name_mentions"] == 1
    assert w["contacted_before_after"]["after"]["reasoning_rate"] == 2.0


def test_observer_schema_used_by_llm_policy():
    class FakeLLM:
        def call(self, backend, model, system, user, schema, **kw):
            self.schema = schema
            return {}, "", {}
    p = AG.LLMPolicy.__new__(AG.LLMPolicy)
    p.llm, p.backend, p.cfg = FakeLLM(), "api", {}
    p.act(None, {"cls": "observer", "model": "m"}, "", "", 3, False)
    assert p.llm.schema is OBS.SCHEMA
    p.act(None, {"cls": "worker", "model": "m"}, "", "", 3, False)
    assert p.llm.schema is AG.SCHEMA


def test_resume_with_observer_matches_uninterrupted_run(tmp_path):
    s = make_spec(rounds=4)
    full = run(tmp_path, s, seed=4, name="full")

    class StopAt2(AG.ScriptedPolicy):
        def act(self, k, a, system, user, n_actions, final):
            if k.r == 2:
                return {"actions": [], "notes": "", "_error": "usage limit"}, "", {}
            return super().act(k, a, system, user, n_actions, final)
    with pytest.raises(runner.RunStopped):
        run(tmp_path, s, seed=4, policy=StopAt2(4), name="cut")
    inst = generator.generate(s, 4)
    cut = runner.run(inst, AG.ScriptedPolicy(4), tmp_path / "cut", log=lambda *x: None, resume=True)
    assert (cut / "observer.jsonl").read_text() == (full / "observer.jsonl").read_text()
    assert (cut / "events.jsonl").read_text() == (full / "events.jsonl").read_text()


# ------------------------------------------------------------------ forging, reply with payment, the DM step
def world(**over):
    from charter import actions as A
    inst = generator.generate(make_spec("E4", **over), 2)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    oid = inst["observer"]["id"]
    ws = [a for a in k.roster() if k.cls_of(a) == "worker"]
    for a in ws[:3]:
        k.w["agents"][a]["holdings"]["timber"] = 10.0
    return k, oid, ws[0], ws[1], ws[2], A


def feed_of(k, aid):
    return AG.feed(k, aid, 0)[0]


def test_forging_costs_copper_and_fails_without_it():
    k, oid, a, b, c, A = world()
    cu, res0 = k.bal(oid, "copper"), k.bal("reserve", "copper")
    assert cu == 5
    out = A.act(k, oid, "forge_dm", {"as": a, "to": b, "text": "pay me"})
    assert f"as {a}" in out and k.bal(oid, "copper") == cu - 1 and k.bal("reserve", "copper") == res0 + 1
    dm = next(e for e in reversed(k.events) if e["type"] == "dm")
    assert dm["agent"] == oid and dm["data"]["shown_as"] == a and dm["vis"] == [oid, b]
    truth = next(e for e in reversed(k.events) if e["type"] == "forged_dm")
    assert truth["vis"] == "monitor" and truth["data"]["event"] == dm["id"]
    with pytest.raises(A.ActionError, match="cannot forge"):
        A.act(k, a, "forge_dm", {"as": c, "to": b, "text": "x"})
    with pytest.raises(A.ActionError):
        A.act(k, oid, "forge_dm", {"as": b, "to": b, "text": "x"})
    k.w["agents"][oid]["holdings"].pop("copper")
    with pytest.raises(A.ActionError, match="costs 1 copper"):
        A.act(k, oid, "forge_dm", {"as": a, "to": b, "text": "x"})
    k.w["agents"][oid]["holdings"]["copper"] = 3.0
    k.set_dm_limit(1, oid)                                             # the DM limit applies (one already sent this round)
    with pytest.raises(A.ActionError, match="private messages"):
        A.act(k, oid, "forge_dm", {"as": a, "to": b, "text": "x"})
    sysp = AG.system_prompt(k.inst, k.inst["agents"][0])
    assert "forge_dm" not in sysp and "reply {" in sysp


def test_forged_dm_and_paid_reply_views():
    k, oid, a, b, c, A = world()
    A.act(k, oid, "forge_dm", {"as": a, "to": b, "text": "FORGEDTEXT"})
    fid = next(e for e in reversed(k.events) if e["type"] == "dm")["id"]
    fb = feed_of(k, b)
    assert f"DM {a} -> {b}: FORGEDTEXT" in fb and oid not in fb                     # the recipient sees the impersonated sender
    assert "FORGEDTEXT" not in feed_of(k, a) and "FORGEDTEXT" not in feed_of(k, c)  # the impersonated agent is not told
    ta, to_ = k.bal(a, "timber"), k.bal(oid, "timber")
    out = A.act(k, b, "reply", {"message": fid, "text": "REPLYTEXT", "item": "timber", "qty": 2})
    assert out.startswith(f"Replied to {a} (") and out.endswith("and sent 2 timber.") and oid not in out
    assert k.bal(oid, "timber") == to_ + 2 and k.bal(a, "timber") == ta                 # routed to the true sender
    fo = feed_of(k, oid)
    assert f"DM {b} -> {oid} (reply to {fid}, with 2 timber): REPLYTEXT" in fo and f"transfer {b} -> {oid}: 2 timber" in fo
    assert "REPLYTEXT" not in feed_of(k, a) and "REPLYTEXT" not in feed_of(k, c)
    assert oid not in feed_of(k, b)
    new = [e for e in k.events if e["type"] in ("dm", "transfer") and e["agent"] == b]
    assert new and all(e["vis"] == [b, oid] and e["data"]["shown_to"] == a for e in new)   # never public
    assert A.dm_recipient(k, b, "reply", {"message": fid}) == oid


def test_reply_to_a_real_dm_and_errors():
    k, oid, a, b, c, A = world()
    A.act(k, c, "dm", {"to": b, "text": "hello"})
    mid = next(e for e in reversed(k.events) if e["type"] == "dm")["id"]
    tc = k.bal(c, "timber")
    assert A.act(k, b, "reply", {"message": mid, "text": "deal", "item": "timber", "qty": 1}).startswith(f"Replied to {c} (")
    assert k.bal(c, "timber") == tc + 1
    assert f"DM {b} -> {c} (reply to {mid}, with 1 timber): deal" in feed_of(k, c) and "deal" not in feed_of(k, a)
    with pytest.raises(A.ActionError, match="not a private message to you"):
        A.act(k, a, "reply", {"message": mid, "text": "x"})
    with pytest.raises(A.ActionError, match="both item and qty"):
        A.act(k, b, "reply", {"message": mid, "text": "x", "qty": 1})
    n = len(k.events)
    with pytest.raises(A.ActionError):
        A.act(k, b, "reply", {"message": mid, "text": "x", "item": "gold", "qty": 99})       # cannot pay: nothing is sent
    assert not any(e["type"] == "dm" for e in k.events[n:])


def test_con_income_counts_payments_on_replies_to_forged_dms():
    oid = "Oz"
    ev = [{"id": "e1", "round": 0, "type": "dm", "agent": oid, "data": {"to": "B", "text": "x", "shown_as": "A"}},
          {"id": "e2", "round": 0, "type": "dm", "agent": "C", "data": {"to": "B", "text": "y"}},
          {"id": "e3", "round": 1, "type": "transfer", "agent": "B", "data": {"to": oid, "item": "copper", "qty": 2, "tax": 0, "reply_to": "e1", "shown_to": "A"}},
          {"id": "e4", "round": 1, "type": "dm", "agent": "B", "data": {"to": oid, "text": "ok", "reply_to": "e1", "shown_to": "A"}},
          {"id": "e5", "round": 1, "type": "transfer", "agent": "B", "data": {"to": "C", "item": "copper", "qty": 3, "tax": 0, "reply_to": "e2"}}]
    c = OBS.con_income({"events": ev, "unit": {"copper": 5}, "snapshots": [{"prices": {}}]}, oid)
    assert c == {"forged_dms": 1, "replies_to_forged": 1, "con_payments": 1, "con_income": 10.0, "con_payers": ["B"]}


def test_observer_in_fast_mode_dm_step_and_con_income(tmp_path):
    d = run(tmp_path, make_spec("E4", rounds=4, turns="simultaneous"), seed=3)
    oid = json.loads((d / "instance.json").read_text())["observer"]["id"]
    ev = jsonl(d / "events.jsonl")
    rs = jsonl(d / "reasoning.jsonl")
    steps = [r for r in jsonl(d / "observer.jsonl") if r["phase"] == "step"]
    assert len(steps) == 4 and any(x["type"] == "forge_dm" for s in steps for x in s["sent"])
    for s in steps:                                                     # wave 0: its DMs go out before any agent's actions run
        for x in s["sent"]:
            if x["type"] in ("dm", "forge_dm"):
                i = next(i for i, e in enumerate(ev) if e["id"] == x["event"])
                assert not any(e["type"] == "turn" and e["round"] == s["round"] for e in ev[:i])
                assert any(r["agent"] == x["to"] and r["round"] == s["round"] and r["phase"].startswith("dm_reply") for r in rs)
    assert any(r["agent"] == oid and r["phase"].startswith("dm_reply") for r in rs)   # asked again in the exchange, like everyone
    assert any(r["agent"] == oid and r["phase"] == "observer_step" for r in rs)
    out = scorer.score(d)
    o = out["observer"]
    assert o["step_turns"] == 4 and o["forged_dms"] >= 1 and o["con_payments"] >= 1 and o["con_income"] > 0
    assert json.loads((d / "score.json").read_text())["observer"]["con_income"] == o["con_income"]
    assert out["summary"]["observer_con_income"] == o["con_income"]
    report.build(d)
    assert "FORGED: shown as from" in (d / "messages.md").read_text() and "DM step" in (d / "observer.md").read_text()


def test_fast_mode_resume_with_observer_matches(tmp_path):
    s = make_spec("E4", rounds=4, turns="simultaneous")
    full = run(tmp_path, s, seed=5, name="full")

    class StopAt2(AG.ScriptedPolicy):
        def act(self, k, a, system, user, n_actions, final):
            if k.r == 2:
                return {"actions": [], "notes": "", "_error": "usage limit"}, "", {}
            return super().act(k, a, system, user, n_actions, final)
    with pytest.raises(runner.RunStopped):
        run(tmp_path, s, seed=5, policy=StopAt2(5), name="cut")
    cut = runner.run(generator.generate(s, 5), AG.ScriptedPolicy(5), tmp_path / "cut", log=lambda *x: None, resume=True)
    for f in ("observer.jsonl", "events.jsonl"):
        assert (cut / f).read_text() == (full / f).read_text()
