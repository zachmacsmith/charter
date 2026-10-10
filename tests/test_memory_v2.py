"""Review 20, decisions 6 and 7: context.memory_text (v2: the accurate memory text and the notebook scratchpad text, §6.1) and
context.dm_delta (DM replies continue the agent's decide conversation, §4.5). Both are on by default; v1 / false reproduce the
text and prompts of earlier runs. No model is ever called: scripted bots, a fake anthropic client and a fake `claude` process."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from charter import action_registry as AR
from charter import agents as AG
from charter import context as CX
from charter import generator, llm, manual, runner
from charter import spec as S
from charter.kernel import Kernel

import charter_golden_cases as GC
from test_charter_golden import _sha

V1 = ["context.memory_text=v1", "context.dm_delta=false"]
V1_PROMPTS = Path(__file__).parent / "fixtures" / "memory_v1_prompts.json"   # the prompt goldens from before review 20


def _world(preset="society", seed=5, sets=()):
    inst = generator.generate(S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", *sets]), seed)
    return inst, Kernel(inst)


# ------------------------------------------------------------------ memory_text
@pytest.mark.parametrize("name", ["prompts_society_5", "prompts_E4_1"])
def test_v1_reproduces_the_prompts_from_before(name):
    """memory_text v1: every agent's core prompt and manual are byte-identical to the goldens recorded before review 20."""
    preset, seed = GC.PROMPT_CASES[name]
    inst, k = _world(preset, seed, V1)
    got = {}
    for a in inst["agents"]:
        core = CX.core_prompt(inst, a, k) if CX.enabled(inst) else AG.system_prompt(inst, a)
        got[a["id"]] = {"core": _sha(core.encode()), "manual_base": _sha(manual.sections(inst, k, a["id"])),
                        "manual": _sha(CX.build_manual(inst, k, a["id"]))}
    assert got == json.loads(V1_PROMPTS.read_text())[name]


def test_defaults_are_v2_and_delta():
    assert CX.DEFAULTS["memory_text"] == "v2" and CX.DEFAULTS["dm_delta"] is True
    from charter import schema
    assert schema.validate(S.apply_overrides(S.load("society"), V1)) == []
    assert any("memory_text" in e for e in schema.validate(S.apply_overrides(S.load("society"), ["context.memory_text=v3"])))


def _turn(k, a, inst):
    return AG.turn_prompt(k, a, [x["id"] for x in inst["agents"]], 0, "", [], a["actions"], False, True)[0]


def test_v2_text_states_each_agents_own_memory_and_scratchpad():
    """N (memory_turns, drawn per agent) and S (scratchpad size, per agent) come from the same facts the renderer uses."""
    inst, k = _world()
    for i, a in enumerate(inst["agents"]):
        CX.init_agent(k, a["id"])
        k.w["context"]["scratchpad_size"][a["id"]] = 1000 + 37 * i      # a distinct size per agent
    ns = set()
    for a in inst["agents"]:
        aid = a["id"]
        n, s = CX.memory_turns(k, aid), CX.scratchpad_size(k, aid)
        ns.add(n)
        core, user = CX.core_prompt(inst, a, k), _turn(k, a, inst)
        turn = dict(CX.build_manual(inst, k, aid))["How your turn works"]
        assert f"Your own actions and their results are shown for your last {n} turns." in core, aid
        assert f"Your scratchpad ({s} tokens, shown every turn) is your only lasting memory" in core, aid
        assert "notebook for thinking, not a log" in core and "Anything older is gone" not in core
        assert f"your own last {n} turns with their results; your scratchpad ({s} tokens, every turn)" in turn, aid
        assert "Nothing else is remembered" not in turn
        assert f"after your next {n} turns you will not see what you did now" in user, aid
        assert "is forgotten within" not in user
        assert "who is alive" not in core                              # no roster line in this world, so not claimed
    assert len(ns) > 1                                                 # the draw really differs between agents
    assert "lasting notebook" in AG.action_doc("write_scratchpad", inst, inst["agents"][0])


def test_v2_names_who_is_alive_only_with_the_roster():
    inst, k = _world("society", 5, ["context.roster=true"])
    assert "laws, who is alive) is always current" in CX.core_prompt(inst, inst["agents"][0], k)


def test_v1_text_is_the_old_text():
    inst, k = _world("society", 5, V1)
    a = inst["agents"][0]
    n = CX.memory_turns(k, a["id"])
    assert f"your own last {n} turns, your\nscratchpad" in CX.core_prompt(inst, a, k)
    assert f"is forgotten within {n} rounds" in _turn(k, a, inst)
    assert AG.action_doc("write_scratchpad", inst, a) == AR.REG["write_scratchpad"].doc


def test_v2_goal_reminder_never_cuts_a_word():
    long = "Gather " + " ".join(f"profiles{i} of individuals" for i in range(40))
    out = CX._short_goal({"goal": {"text": long}}, whole_words=True)
    assert out.endswith("...") and out[:-3].split()[-1] in long.split() and len(out) <= 303
    assert CX._short_goal({"goal": {"text": long}}) == long[:300] + "."   # v1 unchanged


def _dm_args(k, a):
    return dict(first={"reasoning": "my plan"}, plan=[{"action": "harvest", "args_json": "{}"}], new_dms=["[e1] DM Bo -> me: hi"],
                sent=1, allow=5, n_actions=4, wave=1, waves=2, final=False)


def test_dm_prompt_drops_the_stale_notes_line_under_v2_only():
    for sets, has in (([], False), (V1, True)):
        inst, k = _world("society", 5, sets)
        a = inst["agents"][0]
        p = AG.dm_prompt(k, a, "TURN PROMPT", **_dm_args(k, a))
        assert ('"notes" in this reply replaces them' in p) is has
        assert p.endswith("TURN PROMPT")


def test_dm_delta_prompt_is_short_and_keeps_the_scripted_marker():
    inst, k = _world()
    a = inst["agents"][0]
    args = _dm_args(k, a)
    d = AG.dm_delta_prompt(k, a, args["new_dms"], 1, 5, 4, 1, 2, False)
    assert d.startswith("Round 1: private messages have arrived before anyone's actions") and "Since you acted you received:\n[e1]" in d
    assert "You have 4 of your 5 messages left" in d and "TURN" not in d and "notes" not in d and "my plan" not in d
    assert "Anyone you message now" in d
    assert "last exchange" in AG.dm_delta_prompt(k, a, args["new_dms"], 1, 5, 4, 2, 2, False)


# ------------------------------------------------------------------ dm_delta: the policy and the backends
REPLY = {"reasoning": "r", "lookups": [], "actions": [], "goal_guesses_json": "{}"}


def _k(r=0, sets=None):
    spec = {"context": sets or {}}
    return SimpleNamespace(inst={"spec": spec}, spec=spec, r=r)


A = {"id": "a1", "cls": "worker", "model": "m"}


def test_api_reply_continues_the_decide_conversation(monkeypatch):
    """API: the DM reply sends [decide prompt, decide reply, the delta], with a cache breakpoint on the system prompt and on the
    newest user message (the decide call's breakpoint is the cached prefix the reply reads)."""
    sent = []

    class Msgs:
        def create(self, **kw):
            sent.append(kw)
            raw = json.dumps({**REPLY, "reasoning": f"call {len(sent)}"})
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=raw)],
                                   usage=SimpleNamespace(input_tokens=1, output_tokens=2, cache_read_input_tokens=0,
                                                         cache_creation_input_tokens=0))
    monkeypatch.setitem(sys.modules, "anthropic", types.ModuleType("anthropic"))
    monkeypatch.setattr(llm, "_client", SimpleNamespace(messages=Msgs()))
    pol = AG.LLMPolicy("api", {})
    k = _k(3)
    pol.act_recorded(k, A, "SYS", "TURN PROMPT", 4, False)
    out, _, usage, _ = pol.act_recorded(k, A, "SYS", AG.DMDelta("DELTA 1", "FULL 1"), 4, False)
    assert usage["dm_mode"] == "delta" and usage["turn"] == "continued"
    m = sent[1]["messages"]
    assert [x["role"] for x in m] == ["user", "assistant", "user"]
    assert m[0]["content"] == "TURN PROMPT" and json.loads(m[1]["content"])["reasoning"] == "call 1"
    assert m[2]["content"] == [{"type": "text", "text": "DELTA 1", "cache_control": {"type": "ephemeral"}}]
    assert sent[0]["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}   # the decide prompt is written
    assert sent[1]["system"][0]["cache_control"] == {"type": "ephemeral"}
    pol.act_recorded(k, A, "SYS", AG.DMDelta("DELTA 2", "FULL 2"), 4, False)     # the second exchange appends again
    assert [x["content"] if isinstance(x["content"], str) else x["content"][0]["text"] for x in sent[2]["messages"]][::2] == \
        ["TURN PROMPT", "DELTA 1", "DELTA 2"]
    pol.act_recorded(_k(4), A, "SYS", AG.DMDelta("DELTA r5", "FULL r5"), 4, False)   # next round: nothing to continue
    assert sent[3]["messages"] == [{"role": "user", "content": "FULL r5"}]


def test_dm_delta_off_sends_plain_prompts(monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "_api", lambda model, system, user, *a: (seen.append(user), (json.dumps(REPLY), None, "", {}))[1])
    pol = AG.LLMPolicy("api", {})
    k = _k(0, {"dm_delta": False})
    pol.act_recorded(k, A, "SYS", "TURN", 4, False)
    _, _, usage, _ = pol.act_recorded(k, A, "SYS", "FULL DM", 4, False)
    assert seen == ["TURN", "FULL DM"] and all(type(u) is str for u in seen) and "dm_mode" not in usage


def _fake_cli(monkeypatch, fail_resume=False):
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw["env"]))
        if fail_resume and "--resume" in cmd:
            res = {"type": "result", "is_error": True, "subtype": "error_during_execution", "errors": ["No conversation found"]}
        else:
            sid = cmd[cmd.index("--session-id") + 1] if "--session-id" in cmd else (cmd[cmd.index("--resume") + 1] if "--resume" in cmd else None)
            res = {"type": "result", "result": json.dumps(REPLY), "structured_output": REPLY, "usage": {}, "session_id": sid}
        return SimpleNamespace(stdout=json.dumps(res) + "\n", stderr="", returncode=0)
    monkeypatch.setattr(llm.subprocess, "run", run)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-NOT-A-REAL-TOKEN")
    return calls


def test_cli_decide_starts_a_session_in_the_run_folder_and_the_reply_resumes_it(monkeypatch, tmp_path):
    calls = _fake_cli(monkeypatch)
    pol = AG.LLMPolicy("claude_code", {})
    pol.use_run_dir(tmp_path)
    k = _k(2)
    pol.act_recorded(k, A, "SYS", "TURN PROMPT", 4, False)
    _, _, usage, _ = pol.act_recorded(k, A, "SYS", AG.DMDelta("DELTA", "FULL"), 4, False)
    (c1, e1), (c2, e2) = calls
    sid = c1[c1.index("--session-id") + 1]
    assert len(sid) == 36 and "--no-session-persistence" not in c1 and c1[c1.index("-p") + 1] == "TURN PROMPT"
    assert c2[c2.index("--resume") + 1] == sid and c2[c2.index("-p") + 1] == "DELTA" and "--session-id" not in c2
    assert e1["CLAUDE_CONFIG_DIR"] == e2["CLAUDE_CONFIG_DIR"] == str(tmp_path / llm.Sessions.DIRNAME)
    assert (tmp_path / llm.Sessions.DIRNAME).is_dir() and "ANTHROPIC_API_KEY" not in e1
    assert usage["dm_mode"] == "delta" and usage["session"] == sid


def test_cli_without_sessions_keeps_todays_argv(monkeypatch, tmp_path):
    """dm_delta off, or no run folder: the argv is today's (--no-session-persistence, no CLAUDE_CONFIG_DIR)."""
    calls = _fake_cli(monkeypatch)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    AG.LLMPolicy("claude_code", {}).act_recorded(_k(0, {"dm_delta": False}), A, "SYS", "TURN", 4, False)
    pol = AG.LLMPolicy("claude_code", {})                                # on, but never given a run folder
    pol.act_recorded(_k(0), A, "SYS", "TURN", 4, False)
    _, _, usage, _ = pol.act_recorded(_k(0), A, "SYS", AG.DMDelta("DELTA", "FULL"), 4, False)
    for cmd, env in calls:
        assert "--no-session-persistence" in cmd and "CLAUDE_CONFIG_DIR" not in env
    assert calls[-1][0][calls[-1][0].index("-p") + 1] == "FULL" and usage["dm_mode"] == "full"


def test_cli_resume_failure_falls_back_to_the_full_prompt(monkeypatch, tmp_path):
    calls = _fake_cli(monkeypatch, fail_resume=True)
    pol = AG.LLMPolicy("claude_code", {})
    pol.use_run_dir(tmp_path)
    k = _k(1)
    pol.act_recorded(k, A, "SYS", "TURN", 4, False)
    out, _, usage, attempts = pol.act_recorded(k, A, "SYS", AG.DMDelta("DELTA", "FULL"), 4, False)
    assert not out.get("_error") and usage["dm_mode"] == "fallback"
    assert "--resume" in calls[1][0] and calls[2][0][calls[2][0].index("-p") + 1] == "FULL" and "--no-session-persistence" in calls[2][0]
    assert attempts[0]["ok"] is False and attempts[0]["turn"] == "continued" and attempts[-1]["ok"] is True
    _, _, usage2, _ = pol.act_recorded(k, A, "SYS", AG.DMDelta("DELTA 2", "FULL 2"), 4, False)   # the conversation is gone now
    assert usage2["dm_mode"] == "full" and calls[-1][0][calls[-1][0].index("-p") + 1] == "FULL 2"


def test_cli_failed_session_start_is_retried_without_a_session(monkeypatch, tmp_path):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if "--session-id" in cmd:
            return SimpleNamespace(stdout="", stderr="Invalid API key", returncode=1)
        return SimpleNamespace(stdout=json.dumps({"type": "result", "result": json.dumps(REPLY), "usage": {}}) + "\n", stderr="", returncode=0)
    monkeypatch.setattr(llm.subprocess, "run", run)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "x")
    pol = AG.LLMPolicy("claude_code", {})
    pol.use_run_dir(tmp_path)
    for r in range(llm.Sessions.GIVE_UP + 1):
        out, *_ = pol.act_recorded(_k(r), A, "SYS", "TURN", 4, False)
        assert not out.get("_error")
    assert sum("--session-id" in c for c in calls) == llm.Sessions.GIVE_UP   # then sessions are off for the run
    assert "--no-session-persistence" in calls[-1]


# ------------------------------------------------------------------ dm_delta in a run (scripted bots)
def _dry(tmp_path, sets):
    inst = generator.generate(S.apply_overrides(S.load("society"), ["rounds=2", "shared_archive.enabled=false", *sets]), 1)
    out = runner.run(inst, AG.ScriptedPolicy(1), tmp_path / "run", log=lambda *a: None)
    rows = [json.loads(x) for x in (out / "reasoning.jsonl").read_text().splitlines()]
    return out, [r for r in rows if str(r.get("phase", "")).startswith("dm_reply")]


def test_a_run_records_the_mode_of_each_dm_reply(tmp_path):
    out, dm = _dry(tmp_path / "on", [])
    assert dm and all(r["dm_mode"] == "delta" and "Since you acted you received" in r["prompt"] for r in dm)
    run_json = json.loads((out / "run.json").read_text())
    assert run_json["memory_text"] == "v2" and run_json["dm_delta"] is True
    out, dm = _dry(tmp_path / "off", V1)
    assert dm and all("dm_mode" not in r and "The turn prompt you saw at the start" in r["prompt"] for r in dm)
    run_json = json.loads((out / "run.json").read_text())
    assert run_json["memory_text"] == "v1" and run_json["dm_delta"] is False


class _Talkers:
    """Two agents talk across the DM step of round 1: A's decide DM m1 to B; B replies r1 (exchange 1); A answers m2 (exchange 2);
    B replies r2 (exchange 3). Everyone else does nothing. Every prompt is kept."""
    parallel_safe = False

    def __init__(self, a, b):
        self.a, self.b, self.prompts = a, b, []

    def act(self, k, ag, system, user, n_actions, final):
        self.prompts.append((k.r, ag["id"], str(user)))
        acts = []
        dm = lambda to, text: {"action": "dm", "args_json": json.dumps({"to": to, "text": text})}
        step = "private messages have arrived" in user
        if k.r == 0 and ag["id"] == self.a:
            acts = [dm(self.b, "m1: shall we share the camp?")] if not step else [dm(self.b, "m2: yes, from round 2 on.")]
        elif k.r == 0 and ag["id"] == self.b and step:
            n = sum(1 for r, x, u in self.prompts if r == 0 and x == self.b and "private messages have arrived" in u)
            acts = [dm(self.a, "r1: only if you give me grain.")] if n == 1 else [dm(self.a, "r2: agreed, see you then.")]
        return {"reasoning": "", "lookups": [], "actions": acts, "goal_guesses_json": "{}"}, "", {}


@pytest.mark.parametrize("sets", [[], V1])
def test_next_round_shows_last_rounds_whole_exchange_in_order(tmp_path, sets):
    """Today (dm_delta off) the agent's own DM-step replies vanish next round: "dm" is one of its own results (not in the feed)
    and "Your last turns" keeps only "Message sent to X (e..)". With dm_delta on, round 2's prompt has all four, in order."""
    inst = generator.generate(S.apply_overrides(S.load("society"), ["rounds=2", "shared_archive.enabled=false", "dm_step.exchanges=3",
                                                                    "dm_step.dms_per_round=6", *sets]), 1)
    a, b = inst["agents"][0]["id"], inst["agents"][1]["id"]
    pol = _Talkers(a, b)
    runner.run(inst, pol, tmp_path / "run", log=lambda *x: None)
    texts = ["m1: shall we share the camp?", "r1: only if you give me grain.", "m2: yes, from round 2 on.", "r2: agreed, see you then."]
    for who in (a, b):
        p = next(u for r, x, u in pol.prompts if r == 1 and x == who and "private messages have arrived" not in u)
        if sets:                                                      # v1 / off: the old prompt, the agent's own replies missing
            assert CX.EXCHANGE_HEADER not in p and sum(t in p for t in texts) == 2
            continue
        sec = p[p.index(CX.EXCHANGE_HEADER):]
        sec = sec[:sec.index("\n## ")]
        assert f"With {b if who == a else a}:" in sec
        pos = [sec.index(t) for t in texts]
        assert pos == sorted(pos), (who, sec)
        assert all(p.count(t) == 1 for t in texts)                    # not repeated in the feed


def test_the_export_tells_delta_and_full_dm_replies_apart(tmp_path):
    from charter import export as X
    on, _ = _dry(tmp_path / "on", [])
    off, _ = _dry(tmp_path / "off", V1)
    X.export([on, off], tmp_path / "ds", fmt="csv")
    data = X.load(tmp_path / "ds")
    runs = {r["run_id"]: r for r in data["runs"]}
    assert {(r["memory_text"], r["dm_delta"]) for r in runs.values()} == {("v2", True), ("v1", False)}
    modes = {}
    for t in data["turns"]:
        if str(t["phase"]).startswith("dm_reply"):
            modes.setdefault(runs[t["run_id"]]["memory_text"], set()).add(t["dm_mode"])
    assert modes == {"v2": {"delta"}, "v1": {None}}
