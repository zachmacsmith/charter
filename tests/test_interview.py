"""Interviews (charter/interview.py; docs/interview.md): an agent's context at a round is rebuilt by replaying the run with its
recorded replies, and equals what the model was sent in the run (history mode, per-round conversations, self-contained prompts;
after a resume; without checkpoints); the run directory is never changed; repeated sampling, reply schemas, the scoring helper,
usage stop, the CLI and the export table. No model is ever called: a fake anthropic client and scripted bots."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from charter import __main__ as M
from charter import agents as AG
from charter import export as X
from charter import generator, llm, runner
from charter import interview as IW
from charter import provenance as PV
from charter import spec as S

QUIET = lambda *a: None
# A small society in history mode (as tests/test_history.py): 7 agents, 6 rounds, chunks of 3 staggered, F = 3.
WORLD = ["rounds=6", "agents={worker: 4, scientist: 1, legislator: 1, media: 0, board: 0, fixer: 1}", "context.memory_turns=3",
         "dm_step.exchanges=3", "dm_step.dms_per_round=6", "shared_archive.enabled=false", "conflict.enabled=false"]
E4 = ["rounds=3", "turns=simultaneous", "shared_archive.enabled=false", "context.dm_delta=false"]


def _inst(preset, sets, seed=5):
    return generator.generate(S.apply_overrides(S.load(preset), list(sets)), seed)


def _who(system):
    return re.search(r"^You are (\w+)\.", system, re.M).group(1)


def _round_of(text):
    """The round (1-based) a message is for: its "# Round N" heading (history mode), else its first line "Round N ..."."""
    m = re.search(r"^# Round (\d+)", text, re.M) or re.match(r"Round (\d+)", text)
    return int(m.group(1)) if m else None


class _Brain:
    """Deterministic replies: everyone posts; in round 2 the first agent messages the second, who replies. Interview calls (a
    schema with "answer") alternate yes and no."""

    def __init__(self, a, b):
        self.a, self.b, self.n = a, b, 0

    def reply(self, system, last, schema):
        if "answer" in (schema.get("properties") or {}):
            self.n += 1
            return {"answer": "yes" if self.n % 2 else "no", "confidence": 0.5 + 0.1 * (self.n % 3), "reason": f"r{self.n}"}
        who, rnd = _who(system), _round_of(last) or 0
        step = "private messages have arrived" in last
        dm = lambda to, text: {"action": "dm", "args_json": json.dumps({"to": to, "text": text})}
        acts = [] if step else [{"action": "post", "args_json": json.dumps({"text": f"{who} says hello in round {rnd}"})}]
        if rnd == 2 and who == self.a and not step:
            acts.append(dm(self.b, "shall we share the camp?"))
        elif rnd == 2 and who == self.b and step:
            acts = [dm(self.a, "only if you give me grain.")]
        return {"reasoning": f"{who} r{rnd}", "lookups": [], "actions": acts, "notes": f"{who} notes r{rnd}", "goal_guesses_json": "{}"}


def _fake_api(mp, brain):
    """A fake anthropic client: every request is kept as (system, [message texts], reply text, schema)."""
    seen = []

    class Msgs:
        def create(self, **kw):
            texts = [m["content"] if isinstance(m["content"], str) else m["content"][0]["text"] for m in kw["messages"]]
            sys_, schema = kw["system"][0]["text"], kw["output_config"]["format"]["schema"]
            raw = json.dumps(brain.reply(sys_, texts[-1], schema))
            seen.append(SimpleNamespace(system=sys_, texts=texts, raw=raw, schema=schema))
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=raw)],
                                   usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                                         cache_creation_input_tokens=0))
    mp.setitem(sys.modules, "anthropic", types.ModuleType("anthropic"))
    mp.setattr(llm, "_client", SimpleNamespace(messages=Msgs()))
    return seen


def _api_run(tmp, preset, sets, name):
    mp = pytest.MonkeyPatch()
    try:
        inst = _inst(preset, sets)
        a, b = inst["agents"][0]["id"], inst["agents"][1]["id"]
        seen = _fake_api(mp, _Brain(a, b))
        pol = AG.LLMPolicy("api", inst["spec"]["llm"])
        pol.parallel_safe = False
        out = runner.run(inst, pol, tmp / name, log=QUIET)
    finally:
        mp.undo()
    return out, list(seen)


@pytest.fixture(scope="module")
def hist(tmp_path_factory):
    return _api_run(tmp_path_factory.mktemp("iv_hist"), "society", WORLD, "hist")


@pytest.fixture(scope="module")
def single(tmp_path_factory):
    return _api_run(tmp_path_factory.mktemp("iv_single"), "E4", E4, "single")


def _tree(d: Path) -> dict:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*")) if p.is_file()}


def _turn_calls(seen, aid, rnd):
    """The agent's turn calls of round rnd (1-based in the text), in order (decide, then DM replies)."""
    return [s for s in seen if "answer" not in (s.schema.get("properties") or {}) and _who(s.system) == aid
            and _round_of(s.texts[-1]) == rnd]


def _no_model(monkeypatch):
    monkeypatch.setattr(llm, "_api", lambda *a, **k: pytest.fail("the reconstruction called a model"))
    monkeypatch.setattr(llm, "_claude_code", lambda *a, **k: pytest.fail("the reconstruction called a model"))


# ------------------------------------------------------------------ the context is what the model was sent
@pytest.mark.parametrize("rnd", [2, 3])
def test_history_mode_start_context_is_the_recorded_call(hist, rnd, monkeypatch):
    """at="start": the system prompt, the conversation and the pending turn message are exactly what the model received for the
    agent's decide call of that round (the API request's messages)."""
    out, seen = hist
    _no_model(monkeypatch)
    ctxs = IW.contexts(out, rnd, at="start")
    assert len(ctxs) == 7
    for aid, c in ctxs.items():
        first = _turn_calls(seen, aid, rnd + 1)[0]
        assert c.system == first.system and c.messages + [c.pending] == first.texts, aid
        assert c.exact and c.mode == "history" and c.model


@pytest.mark.parametrize("rnd", [1, 2, 3, 5])
def test_history_mode_end_context_is_what_the_next_call_continues(hist, rnd, monkeypatch):
    """at="end": the conversation through the agent's last call of the round and its reply; when the agent's next call (its
    decide call of the next round) continues the same conversation, that call's history is exactly this context."""
    out, seen = hist
    _no_model(monkeypatch)
    ctxs = IW.contexts(out, rnd, at="end")
    continued = 0
    for aid, c in ctxs.items():
        calls = _turn_calls(seen, aid, rnd + 1)
        assert c.messages == calls[-1].texts + [calls[-1].raw] and c.system == calls[-1].system
        nxt = _turn_calls(seen, aid, rnd + 2)
        if nxt and len(nxt[0].texts) > 1:                               # the same chunk goes on
            assert nxt[0].texts[:-1] == c.messages and nxt[0].system == c.system
            continued += 1
        assert c.exact
    assert continued >= (3 if rnd < 5 else 0)


def test_self_contained_prompts_start_and_end(single, monkeypatch):
    """Without conversations (context off, dm_delta off): start = the decide prompt alone; end = the round's last prompt (the DM
    step's) and the reply to it."""
    out, seen = single
    _no_model(monkeypatch)
    for rnd in (0, 1, 2):
        s, e = IW.contexts(out, rnd, at="start"), IW.contexts(out, rnd, at="end")
        assert set(s) == set(e) and len(s) >= 4
        for aid in s:
            calls = _turn_calls(seen, aid, rnd + 1)
            assert s[aid].messages == [] and s[aid].pending == calls[0].texts[-1] and s[aid].system == calls[0].system
            assert e[aid].messages == [calls[-1].texts[-1], calls[-1].raw] and e[aid].pending is None
            assert s[aid].exact and e[aid].exact and s[aid].mode == e[aid].mode == "single"


def test_after_a_resume_the_conversations_start_where_the_run_restarted_them(tmp_path):
    """A run resumed at round 3 restarted every conversation there (run.json history_restarts): the replay starts from the
    checkpoint after round 3, so round 4's conversations are the run's own (every prompt hash matches)."""
    d = tmp_path / "res"
    runner.run(_inst("society", WORLD), AG.ScriptedPolicy(5), d, log=QUIET, until=3)
    runner.run(json.loads((d / "instance.json").read_text()), AG.ScriptedPolicy(5), d, log=QUIET, resume=True)
    assert PV.read(d)["history_restarts"] == [3]
    calls = {r["key"]: r for r in map(json.loads, (d / "calls.jsonl").read_text().splitlines())}
    for at in ("start", "end"):
        ctxs = IW.contexts(d, 4, at=at)
        for aid, c in ctxs.items():
            assert c.exact and c.base_checkpoint == 3 and all(int(k.split(":")[0][1:]) >= 3 for k in c.calls), (aid, c.calls)
            if at == "start":
                row = calls[f"r4:decide:0:{aid}:0"]
                assert PV.sha(c.pending) == row["user_sha"] and PV.sha(c.system) == row["system_sha"]


def test_without_checkpoints_the_replay_starts_at_round_one(hist, tmp_path):
    out, seen = hist
    d = shutil.copytree(out, tmp_path / "nockpt")
    shutil.rmtree(d / "checkpoints")
    (d / "checkpoint.pkl").unlink()
    a = IW.contexts(d, 3, at="end")
    b = IW.contexts(out, 3, at="end")
    assert {x: (c.system, c.messages) for x, c in a.items()} == {x: (c.system, c.messages) for x, c in b.items()}
    assert all(c.exact and c.base_checkpoint is None and "replayed from round 1" in c.notes for c in a.values())


# ------------------------------------------------------------------ asking: no writeback, sampling, schemas
def test_interview_sends_the_context_plus_the_question_and_never_changes_the_run(hist, tmp_path, monkeypatch):
    out, _ = hist
    run = shutil.copytree(out, tmp_path / "run")
    before = _tree(run)
    inst = _inst("society", WORLD)
    seen = _fake_api(monkeypatch, _Brain(inst["agents"][0]["id"], inst["agents"][1]["id"]))
    agents = [inst["agents"][2]["id"], inst["agents"][3]["id"]]
    res = IW.interview(run, 2, agents=agents, questions=["Do you support the regime?", {"id": "plan", "text": "What is your plan?"}],
                       n=3, response_schema="yes_no_conf", backend="api", out=tmp_path / "store", log=QUIET, parallel=1)
    assert _tree(run) == before                                         # --out elsewhere: the run directory is byte-identical
    rows = res["rows"]
    assert len(rows) == 2 * 2 * 3 == len(seen) and res["meta"]["asked"] == 12
    assert sorted({(r["agent"], r["question_id"]) for r in rows}) == sorted((a, q) for a in agents for q in ("plan", "q1"))
    assert sorted(r["sample"] for r in rows if r["agent"] == agents[0] and r["question_id"] == "q1") == [0, 1, 2]
    assert {r["answer"] for r in rows} == {"yes", "no"} and all(r["valid"] for r in rows)
    ctxs = IW.contexts(run, 2, agents)
    prompts = {p["prompt_sha"]: p for p in map(json.loads, (tmp_path / "store" / f"{res['id']}.prompts.jsonl").read_text().splitlines())}
    for r, s in zip(rows, seen):
        c = ctxs[r["agent"]]
        assert s.system == c.system and s.texts[:-1] == c.messages     # the agent's own conversation, then the interview
        assert s.texts[-1].startswith(IW.FRAMINGS["private"]) and r["question"] in s.texts[-1]
        assert s.schema == IW.json_schema("yes_no_conf") and r["model"] == c.model and r["context_exact"]
        p = prompts[r["prompt_sha"]]
        assert PV.sha(IW.prompt_text(p["system"], p["messages"], p["message"])) == r["prompt_sha"] and p["message"] == s.texts[-1]
        assert r["usage"]["input"] == 10 and r["cost_usd"] is not None
    meta = json.loads((tmp_path / "store" / f"{res['id']}.json").read_text())
    assert meta["contexts"][agents[0]]["exact"] and meta["n"] == 3 and meta["valid"] == 12
    # the default store is a new subdirectory: nothing that existed changes
    IW.interview(run, 2, agents=agents[:1], questions=["Do you support the regime?"], backend="api", log=QUIET)
    after = _tree(run)
    assert {x: v for x, v in after.items() if not x.startswith("interviews/")} == before
    assert any(x.startswith("interviews/") for x in after)


def test_start_interview_appends_the_question_to_the_pending_turn(hist, tmp_path):
    out, _ = hist
    res = IW.interview(out, 3, questions=["What will you do this round?"], at="start", dry=True, out=tmp_path, log=QUIET)
    p = [json.loads(x) for x in (tmp_path / f"{res['id']}.prompts.jsonl").read_text().splitlines()]
    ctxs = IW.contexts(out, 3, at="start")
    for x in p:
        c = next(c for c in ctxs.values() if PV.sha(c.system) == x["system_sha"] and c.messages == x["messages"])
        assert x["message"].startswith(c.pending + "\n\n---\n\n") and IW.START_NOTE in x["message"]


def test_dry_answers_are_scripted_and_repeatable(hist, tmp_path):
    out, _ = hist
    a = IW.interview(out, 1, questions=["Do you trust your neighbours?"], n=2, response_schema="yes_no_conf", dry=True,
                     out=tmp_path / "a", log=QUIET)
    b = IW.interview(out, 1, questions=["Do you trust your neighbours?"], n=2, response_schema="yes_no_conf", dry=True,
                     out=tmp_path / "b", log=QUIET)
    pick = lambda res: [(r["agent"], r["sample"], r["parsed"]) for r in res["rows"]]
    assert pick(a) == pick(b) and all(r["valid"] and r["backend"] == "dry" and r["usage"] == {} for r in a["rows"])
    assert len(a["rows"]) == 2 * len(IW.alive_at(out, 1))


def test_reply_schemas():
    assert IW.json_schema(None) == IW.json_schema("free") == {"type": "object", "properties": {"answer": {"type": "string"}},
                                                             "required": ["answer"], "additionalProperties": False}
    s = IW.json_schema({"answer": "yes|no", "confidence": "0..1", "reason": "str"})
    assert s == IW.json_schema("yes_no_conf") == IW.json_schema(json.dumps({"answer": "yes|no", "confidence": "0..1", "reason": "str"}))
    assert s["properties"]["answer"] == {"type": "string", "enum": ["yes", "no"]}
    assert s["properties"]["confidence"] == {"type": "number", "minimum": 0.0, "maximum": 1.0}
    assert IW.json_schema({"score": "1..7"})["properties"]["score"] == {"type": "integer", "minimum": 1, "maximum": 7}
    full = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    assert IW.json_schema(full) is full
    with pytest.raises(ValueError):
        IW.json_schema("nonsense")
    assert IW.validate({"answer": "Yes", "confidence": "0.8", "reason": "r"}, s) == ({"answer": "yes", "confidence": 0.8, "reason": "r"}, True, [])
    clean, ok, bad = IW.validate({"answer": "maybe", "confidence": 2}, s)
    assert not ok and len(bad) == 3 and clean["answer"] == "maybe"
    assert IW.validate({"actions": [], "_error": "boom"}, s)[1] is False
    assert "yes" in IW.describe_schema(s) and "from 0.0 to 1.0" in IW.describe_schema(s)


def test_interview_share_reads_stored_answers(hist, tmp_path):
    out, _ = hist
    run = shutil.copytree(out, tmp_path / "run")
    q = "Do you privately pledge allegiance to the regime?"
    assert IW.interview_share(run, 2, q) is None                        # nothing stored, and asking was not allowed
    got = IW.interview_share(run, 2, q, ask=True, n=3, dry=True, log=QUIET)
    rows = [r for r in IW.load(run) if r["question"] == q]
    yes = sum(r["answer"] == "yes" for r in rows)
    assert got["samples"] == len(rows) == 3 * 7 and got["satisfied"] == yes and got["share"] == yes / len(rows)
    assert got["samples_per_agent"] == {a: 3 for a in IW.alive_at(run, 2)} and len(got["interviews"]) == 1
    again = IW.interview_share(run, 2, q)                               # stored now: read back, not asked again
    assert again == got and len(list((run / "interviews").glob("*.json"))) == 1
    some = IW.interview_share(run, 2, q, agents=list(got["by_agent"])[:2], predicate=lambda p: p["confidence"] > 0.5)
    assert some["agents"] == 2 and some["samples"] == 6


def test_usage_stop_is_respected(hist, tmp_path, monkeypatch):
    out, _ = hist
    monkeypatch.delenv("CHARTER_USAGE_STOP", raising=False)
    monkeypatch.setattr(llm, "_api", lambda *a, **k: pytest.fail("asked past the usage stop"))
    ctxs = IW.contexts(out, 1, [IW.alive_at(out, 1)[0]])
    monkeypatch.setattr(llm, "USAGE", {"windows": {"five_hour": 0.97}, "status": "allowed"})
    res = IW.interview(out, 1, questions=["Anything?"], backend="api", out=tmp_path, ctxs=ctxs, log=QUIET)
    assert res["rows"] == [] and "subscription usage" in res["meta"]["stopped"] and res["meta"]["planned"] == 1


def test_errors_are_clear(hist):
    out, _ = hist
    with pytest.raises(ValueError, match="complete rounds"):
        IW.contexts(out, 6)
    with pytest.raises(ValueError, match="unknown agent"):
        IW.contexts(out, 1, ["Nobody"])
    with pytest.raises(ValueError, match="no question"):
        IW.interview(out, 1, questions=[], dry=True)


# ------------------------------------------------------------------ command line and export
def test_cli_dry_and_estimate(hist, tmp_path, monkeypatch, capsys):
    out, _ = hist
    run = shutil.copytree(out, tmp_path / "run")
    monkeypatch.setattr(M, "load_env", lambda: None)
    a, b = IW.alive_at(run, 1)[:2]
    qf = tmp_path / "q.yaml"
    qf.write_text("- What do you believe happened to the granary food?\n- id: ally\n  text: Who is your closest ally?\n")
    M.main(["interview", str(run), "--round", "1", "--agents", f"{a},{b}", "--estimate", "--question", "Hi?"])
    est = json.loads(capsys.readouterr().out)
    assert est["calls"] == 2 and est["input_tokens"] > 1000 and est["usd"] > 0
    M.main(["interview", str(run), "--round", "1", "--agents", f"{a},{b}", "--question", "Do you support the regime?",
            "--questions", str(qf), "--n", "2", "--schema", "yes_no_conf", "--dry", "--id", "t1"])
    text = capsys.readouterr().out
    assert "estimated $0 (dry" in text and "-> " in text
    rows = IW.load(run)
    assert len(rows) == 2 * 3 * 2 and {r["question_id"] for r in rows} == {"q1", "q2", "ally"} and all(r["valid"] for r in rows)
    assert (run / "interviews" / "t1.json").exists() and (run / "interviews" / "t1.prompts.jsonl").exists()


def test_the_export_carries_interviews(hist, tmp_path):
    out, _ = hist
    run = shutil.copytree(out, tmp_path / "run")
    res = IW.interview(run, 1, questions=["Do you support the regime?"], n=2, response_schema="yes_no_conf", dry=True, log=QUIET)
    man = X.export([run], tmp_path / "ds", fmt="csv", with_prompts=True)
    assert man["schema_minor"] == X.SCHEMA_MINOR >= 6 and man["tables"]["interviews"]["rows"] == len(res["rows"])
    data = X.load(tmp_path / "ds", ["interviews", "blobs"])
    iv = data["interviews"]
    assert {r["interview_id"] for r in iv} == {res["id"]} and {r["round"] for r in iv} == {1}
    assert all(r["answer"] in ("yes", "no") and r["valid"] is True and r["dry"] is True and r["context_exact"] is True for r in iv)
    blobs = {r["blob_sha"]: r for r in data["blobs"] if r["kind"] == "interview_prompt"}
    assert {r["prompt_sha"] for r in iv} <= set(blobs)
    plain = X.export([out], tmp_path / "ds2", fmt="csv")              # a run without interviews: an empty table
    assert plain["tables"]["interviews"]["rows"] == 0
