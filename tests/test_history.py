"""History mode (review 20 §4, charter/memory.py; context.history, on by default wherever the context module is on): one
conversation per agent, restarted every 3 rounds (staggered), the past on a gradient (full band F..F+2 = the agent's memory_turns
plus the chunk's rounds, one-line summaries, long memories, recall), DM replies appended, the system prompt frozen per chunk.
No model is ever called: scripted bots, a fake anthropic client, a fake `claude` process."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from charter import actions as A
from charter import agents as AG
from charter import context as CX
from charter import generator, llm, runner
from charter import memory as HM
from charter import spec as S

import charter_golden_cases as GC

OFF = ["context.history.enabled=false"]
OFF_PROMPTS = Path(__file__).parent / "fixtures" / "history_off_prompts.json"   # every call's prompts before history mode
# A small society: 7 agents, no deaths in 6 rounds, every agent sees 3 rounds in full (F = 3), room for a 4-message exchange.
WORLD = ["rounds=6", "agents={worker: 4, scientist: 1, legislator: 1, media: 0, board: 0, fixer: 1}", "context.memory_turns=3",
         "dm_step.exchanges=3", "dm_step.dms_per_round=6", "shared_archive.enabled=false", "conflict.enabled=false"]


def _inst(sets=(), preset="society", seed=5):
    return generator.generate(S.apply_overrides(S.load(preset), list(WORLD) + list(sets)), seed)


def _rows(out, name="reasoning.jsonl"):
    return [json.loads(x) for x in (out / name).read_text().splitlines() if x.strip()]


# ------------------------------------------------------------------ off: exactly the prompts from before
OFF_CASES = {"society_small_4": ("society", 5, GC.SOCIETY_SMALL), "subsistence_small": GC.CASES["subsistence_small"]}


def _call_prompts(name, sets, tmp):
    preset, seed, base = OFF_CASES[name]
    inst = generator.generate(S.apply_overrides(S.load(preset), base + ["shared_archive.enabled=false"] + sets), seed)
    out = runner.run(inst, AG.ScriptedPolicy(seed), Path(tmp) / name, log=lambda *a: None)
    return {r.get("key") or r["call"]: [r["system_sha"], r["user_sha"]] for r in _rows(out, "calls.jsonl")}


@pytest.mark.parametrize("name", sorted(OFF_CASES))
def test_history_off_reproduces_every_prompt_from_before(name, tmp_path, monkeypatch):
    """context.history.enabled false: every call's system and user prompt is byte-identical to the recording made before history
    mode existed (both scripted runs), and the renderer is never called."""
    monkeypatch.setattr(HM, "turn", lambda *a, **kw: pytest.fail("history renderer called with history off"))
    monkeypatch.setitem(__import__("charter.goals").goals.SCORING_DEFAULTS, "fixes", False)   # engine 10 rewords Dynasty's text
    assert _call_prompts(name, OFF, tmp_path) == json.loads(OFF_PROMPTS.read_text())[name]


def test_defaults_and_settings():
    from charter import schema
    assert CX.DEFAULTS["history"]["enabled"] is True and CX.DEFAULTS["history"]["chunk"] == 3
    assert CX.DEFAULTS["history"]["summary_rounds"] == 12 and CX.DEFAULTS["history"]["summary_spread"] == 0
    sp = S.load("society")
    assert HM.on(sp) and not HM.on(S.load("E4"))                        # the context module is off in E4
    assert not HM.on(S.apply_overrides(sp, OFF))
    assert HM.hcfg(S.apply_overrides(sp, ["context.history.chunk=5"]))["summary_rounds"] == 12   # partial blocks merge
    assert schema.validate(S.apply_overrides(sp, ["context.history.chunk=4", "context.history.summary_spread=2",
                                                  "context.history.salience.death=null"])) == []
    assert any("chunck" in e for e in schema.validate(S.apply_overrides(sp, ["context.history.chunck=4"])))


# ------------------------------------------------------------------ bands and the chunk schedule (scripted runs)
@pytest.fixture(scope="module")
def scripted_run():
    with tempfile.TemporaryDirectory() as t:
        inst = _inst(["rounds=9"])
        out = runner.run(inst, AG.ScriptedPolicy(5), Path(t) / "run", log=lambda *a: None)
        yield inst, _rows(out), _rows(out, HM.FILE), json.loads((out / "run.json").read_text())


def test_full_band_is_a_sawtooth_staggered_across_agents(scripted_run):
    """F = 3, chunk 3: within each conversation the full band runs 3, 4, 5 (rounds appended), back to 3 at the next start; the
    starts are staggered by a stable per-agent offset."""
    inst, rows, _, run_json = scripted_run
    assert run_json["history"]["chunk"] == 3 and run_json["history_restarts"] == []
    starts = {}
    for aid in sorted({r["agent"] for r in rows if r["phase"] == "decide"}):   # founders and children born in the run
        dec = sorted((r["round"], r["context"]["history"]) for r in rows if r["agent"] == aid and r["phase"] == "decide")
        off, born = HM.facts(inst, aid)["offset"], dec[0][0]
        for r, h in dec:
            first = r == born or (r + off) % 3 == 0
            assert h["message"] == ("start" if first else "continue"), (aid, r, h)
            s = h["chunk_start"] - 1
            assert s == max(born, r - (r + off) % 3)
            assert h["full"] == min(s - born, 3) + (r - s), (aid, r, h)   # 3 at a start (fewer early on), then 4, 5
        starts[aid] = [r for r, h in dec if h["message"] == "start"]
    seq = [h["full"] for r, h in sorted((r["round"], r["context"]["history"]) for r in rows
                                        if r["agent"] == inst["agents"][0]["id"] and r["phase"] == "decide") if r >= 3]
    assert set(seq) == {3, 4, 5} and len({tuple(v[1:]) for v in starts.values()}) > 1   # a sawtooth; not every agent restarts together


def test_the_memory_text_states_the_renderers_numbers():
    """F, F+2, B and the recall cost in the core prompt come from the facts the renderer uses; summary_spread draws B per agent."""
    from charter.kernel import Kernel
    inst = _inst(["context.memory_turns={weights: {2: 1, 4: 1}}", "context.history.summary_spread=2"])
    k = Kernel(inst)
    seen = set()
    for a in inst["agents"]:
        f = HM.facts(inst, a["id"])
        core = CX.core_prompt(inst, a, k)
        assert f"The last {f['full']} to {f['full'] + 2} rounds in full" in core, a["id"]
        assert f"The {f['summary']} rounds before that as one line each" in core, a["id"]
        assert "uses one of your private-message slots" in core and "notebook for thinking" in core
        assert "recall brings back what you saw, never what you thought" in core
        turn = dict(CX.build_manual(inst, k, a["id"]))["How your turn works"]
        assert f"restarts every 3 rounds" in turn and f"({f['summary']} of them)" in turn and f"the last {f['full']} rounds in full" in turn
        assert 10 <= f["summary"] <= 14
        seen.add((f["full"], f["summary"]))
    assert len(seen) > 2


def test_the_reminder_matches_the_bands(scripted_run):
    """"in n1 rounds this round shrinks to one line, and in n2 rounds it is gone": at round t + n1 the round is in the summary
    band of a conversation starting then, and at t + n2 beyond it."""
    inst, rows, _, _ = scripted_run
    for r in rows:
        if r["phase"] != "decide" or r["round"] > 3:
            continue
        m = re.search(r"Memory: in (\d+) rounds this round shrinks to one line, and in (\d+) rounds", r["prompt"])
        n1, n2 = int(m.group(1)), int(m.group(2))
        t, aid = r["round"], r["agent"]
        k = SimpleNamespace(inst=inst, r=t)
        k.__dict__["_history"] = HM.Store()
        assert HM.next_start(k, aid, t + n1 - 1) == t + n1
        b1, b2 = HM.bands(k, aid, t + n1), HM.bands(k, aid, t + n2)
        assert b1["summary"][0] <= t < b1["summary"][1] and t < b2["beyond"][1]
        assert t >= HM.bands(k, aid, t + n1 - 3)["full"][0] if t + n1 - 3 > t else True


def test_records_are_what_the_agent_saw_never_its_reasoning(scripted_run):
    inst, rows, mem, _ = scripted_run
    assert mem and all(set(m) == {"round", "agent", "saw", "lookups", "actions", "results", "exchange", "partners", "notable", "line"}
                       for m in mem)
    for m in mem:
        assert "scripted bot: no reasoning" not in json.dumps(m)
        assert m["line"].startswith(f"Round {m['round'] + 1}: you did ")
        dec = next(r for r in rows if r["agent"] == m["agent"] and r["round"] == m["round"] and r["phase"] == "decide")
        assert m["results"] == dec["results"]


def test_a_round_with_summaries_and_beyond(tmp_path):
    """Round 17+ of a long run shows the beyond line, 12 one-line rounds and F full rounds; the opening is ordered oldest first."""
    inst = _inst(["rounds=19", "agents={worker: 3, scientist: 0, legislator: 1, media: 0, board: 0, fixer: 1}"])
    out = runner.run(inst, AG.ScriptedPolicy(5), tmp_path / "run", log=lambda *a: None)
    founders = {r["agent"] for r in _rows(out) if r["round"] == 0}
    rows = [r for r in _rows(out) if r["phase"] == "decide" and r["round"] >= 16 and r["context"]["history"]["message"] == "start"
            and r["agent"] in founders]
    assert rows
    for r in rows:
        h, p = r["context"]["history"], r["prompt"]
        s = h["chunk_start"] - 1
        assert h["summary"] == 12 and h["full"] == 3 and h["beyond"] == s - 15
        assert f"You no longer remember rounds 1-{s - 15} in detail; use recall" in p
        i_sum, i_full, i_now = p.index("one line each\nRound "), p.index(" in full\n### Round"), p.index("(now)")
        assert i_sum < i_full < i_now


# ------------------------------------------------------------------ salience (unit)
def test_long_memories_by_salience():
    """A close contact's death stays for good; a stranger's leaves 30 rounds past the summary band; an attack never leaves; a
    deal leaves after 10; the cap keeps the newest."""
    inst = {"seed": 1, "agents": [{"id": "me", "memory_turns": 3}], "spec": {"context": {"enabled": True}}}
    k = SimpleNamespace(inst=inst, spec=inst["spec"], r=0)
    st = k.__dict__["_history"] = HM.Store()
    note = lambda kind, who, text: {"kind": kind, "who": who, "text": text}
    st.rows["me"] = {0: {"partners": {"Saga": [7, "hi"]}, "notable": [note("death", "Saga", "Saga died"), note("death", "Ulf", "Ulf died"),
                                                                       note("attack", "Zed", "Zed attacked you"), note("deal", "Bo", "a loan")]}}
    for q in range(1, 120):
        st.rows["me"][q] = {"partners": {}, "notable": []}
    text = lambda s: "\n".join(HM.long_memories(k, "me", s))
    # the summary band ends at s - 3 - 12; round 0 is beyond it from s = 16
    assert "Saga died" in text(16) and "You exchanged 7 messages" in text(16) and "Ulf died" in text(16) and "a loan" in text(16)
    assert "a loan" in text(16 + 9) and "a loan" not in text(16 + 10)    # 10 rounds past the band
    assert "Ulf died" in text(16 + 29) and "Ulf died" not in text(16 + 30)
    assert "Saga died" in text(119) and "Zed attacked you" in text(119)


# ------------------------------------------------------------------ recall
class _Asker:
    """Scripted bots, but one agent asks for recall {"round": 1} at round 3: as a pre-action (lookups) or as an action."""

    def __init__(self, who, as_action):
        self.inner, self.who, self.as_action, self.prompts = AG.ScriptedPolicy(5), who, as_action, []

    def act(self, k, a, system, user, n_actions, final):
        self.prompts.append((k.r, a["id"], str(user)))
        out, reasoning, usage = self.inner.act(k, a, system, user, n_actions, final)
        if a["id"] == self.who and k.r == 2 and "private messages have arrived" not in user:
            q = {"lookup": "recall", "args_json": json.dumps({"round": 1})}
            if self.as_action:
                out = {**out, "actions": [{"action": "recall", "args_json": q["args_json"]}], "lookups": []}
            else:
                out = {**out, "lookups": [q], "actions": []}
        elif a["id"] == self.who and k.r == 2:
            out = {**out, "lookups": [], "actions": []}
        return out, reasoning, usage


def test_recall_as_a_pre_action_is_answered_before_acting_and_uses_a_dm_slot(tmp_path):
    inst = _inst()
    who = inst["agents"][0]["id"]
    pol = _Asker(who, as_action=False)
    out = runner.run(inst, pol, tmp_path / "run", log=lambda *a: None)
    mem = {m["round"]: m for m in _rows(out, HM.FILE) if m["agent"] == who}
    delta = next(u for r, x, u in pol.prompts if r == 2 and x == who and "private messages have arrived" in u)
    assert "Lookup recall {\"round\": 1}:\nRecalled:\n" + HM.render_round(mem[0]) in delta     # exactly round 1 as recorded
    lim = int(re.search(r"of your (\d+) messages left", delta).group(1))
    assert f"You have {lim - 1} of your {lim} messages left" in delta                          # one slot used
    ev = [e for e in _rows(out, "events.jsonl") if e["type"] == "lookup" and e["agent"] == who and e["round"] == 2]
    assert ev and ev[0]["data"]["name"] == "recall" and ev[0]["data"]["via"] == "dm_step"
    assert "Lookup recall" in "\n".join(mem[2]["lookups"])                 # part of what it saw in round 3


def test_recall_as_an_action_is_answered_next_turn(tmp_path):
    inst = _inst()
    who = inst["agents"][0]["id"]
    pol = _Asker(who, as_action=True)
    out = runner.run(inst, pol, tmp_path / "run", log=lambda *a: None)
    mem = {m["round"]: m for m in _rows(out, HM.FILE) if m["agent"] == who}
    assert mem[2]["results"][0].startswith("recall: Recalled:\n### Round 1")
    nxt = next(u for r, x, u in pol.prompts if r == 3 and x == who and "private messages have arrived" not in u)
    assert "recall: Recalled:\n### Round 1" in nxt                       # in the next turn's results (or its opening's full band)


def test_recall_exists_only_in_history_mode():
    from charter.kernel import Kernel
    inst = _inst(OFF)
    k = Kernel(inst)
    aid = inst["agents"][0]["id"]
    with pytest.raises(A.ActionError, match="unknown action 'recall'"):
        A.act(k, aid, "recall", {"round": 1})
    assert "recall" not in CX.allowed_actions(inst, inst["agents"][0], k.w["agents"][aid]["rights"], k)
    assert "recall" not in CX.core_prompt(inst, inst["agents"][0], k)
    on = _inst()
    k2 = Kernel(on)
    assert "recall" in CX.allowed_actions(on, on["agents"][0], k2.w["agents"][aid]["rights"], k2)
    with pytest.raises(A.ActionError, match="not a past round"):
        A.act(k2, aid, "recall", {"round": 1})


# ------------------------------------------------------------------ transports: one conversation, three ways to send it
class _Brain:
    """Deterministic replies: in round 2, A messages B; B replies (exchange 1); A answers (exchange 2); B replies (exchange 3).
    Everyone else does nothing."""
    TEXTS = ["m1: shall we share the camp?", "r1: only if you give me grain.", "m2: yes, from round 3 on.", "r2: agreed, see you then."]

    def __init__(self, a, b):
        self.a, self.b, self.n = a, b, {}

    def reply(self, system, last):
        who = re.search(r"^You are (\w+)\.", system, re.M).group(1)
        rnd = int(re.findall(r"(?:^# Round |^Round )(\d+)", last, re.M)[-1])
        step = "private messages have arrived" in last
        dm = lambda to, text: {"action": "dm", "args_json": json.dumps({"to": to, "text": text})}
        acts = []
        if rnd == 2 and who == self.a:
            acts = [dm(self.b, self.TEXTS[0] if not step else self.TEXTS[2])]
        elif rnd == 2 and who == self.b and step:
            i = self.n[(who, rnd)] = self.n.get((who, rnd), 0) + 1
            acts = [dm(self.a, self.TEXTS[1] if i == 1 else self.TEXTS[3])]
        return {"reasoning": f"{who} r{rnd}", "lookups": [], "actions": acts, "goal_guesses_json": "{}"}


def _last_message(text):
    """The newest message of a flattened conversation."""
    return text.rsplit(llm.NEXT_MARK + "\n", 1)[-1]


def _api_run(tmp_path, monkeypatch, inst, brain):
    seen = []

    class Msgs:
        def create(self, **kw):
            msgs = kw["messages"]
            texts = [m["content"] if isinstance(m["content"], str) else m["content"][0]["text"] for m in msgs]
            sys_ = kw["system"][0]["text"]
            seen.append((sys_, texts, msgs))
            raw = json.dumps(brain.reply(sys_, texts[-1]))
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=raw)],
                                   usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0,
                                                         cache_creation_input_tokens=0))
    monkeypatch.setitem(sys.modules, "anthropic", types.ModuleType("anthropic"))
    monkeypatch.setattr(llm, "_client", SimpleNamespace(messages=Msgs()))
    pol = AG.LLMPolicy("api", {})
    pol.parallel_safe = False
    out = runner.run(inst, pol, tmp_path / "api", log=lambda *a: None)
    return out, seen


def _cli_run(tmp_path, monkeypatch, inst, brain, sessions):
    seen, conv = [], {}
    real = llm.subprocess.run

    def run(cmd, **kw):
        if cmd[0] != "claude":
            return real(cmd, **kw)
        p, sys_ = cmd[cmd.index("-p") + 1], cmd[cmd.index("--system-prompt") + 1]
        if "--resume" in cmd:
            sid = cmd[cmd.index("--resume") + 1]
            conv[sid] += [p]
        elif "--session-id" in cmd:
            sid = cmd[cmd.index("--session-id") + 1]
            conv[sid] = [p]
        else:
            sid = None
        texts = conv[sid] if sid else [p]
        seen.append((sys_, llm.flatten(texts) if sid else p, cmd))
        raw = json.dumps(brain.reply(sys_, _last_message(texts[-1])))
        if sid:
            conv[sid].append(raw)
        res = {"type": "result", "result": raw, "structured_output": json.loads(raw), "usage": {}, "session_id": sid}
        return SimpleNamespace(stdout=json.dumps(res) + "\n", stderr="", returncode=0)
    monkeypatch.setattr(llm.subprocess, "run", run)
    monkeypatch.setattr(llm, "sessions_available", lambda: sessions)
    pol = AG.LLMPolicy("claude_code", {})
    pol.parallel_safe = False
    out = runner.run(inst, pol, tmp_path / ("sessions" if sessions else "flat"), log=lambda *a: None)
    return out, seen


@pytest.fixture(scope="module")
def three_ways(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("transports")
    inst = _inst()
    a, b = inst["agents"][0]["id"], inst["agents"][1]["id"]
    try:
        got = {"api": _api_run(tmp, mp, _inst(), _Brain(a, b))}
        got["flat"] = _cli_run(tmp, mp, _inst(), _Brain(a, b), sessions=False)
        got["sessions"] = _cli_run(tmp, mp, _inst(), _Brain(a, b), sessions=True)
    finally:
        mp.undo()
    yield (a, b), got


def test_flattened_sessions_and_api_send_the_same_conversation(three_ways):
    """The whole text the model sees at each call is the same under the three transports: the API's messages, a claude -p
    session (the opening with --session-id, then each new message with --resume), and the conversation flattened into one
    prompt (no sessions). Each call records which it was."""
    _, got = three_ways
    api = [(s, llm.flatten(t)) for s, t, _ in got["api"][1]]
    flat = [(s, p) for s, p, _ in got["flat"][1]]
    sess = [(s, p) for s, p, _ in got["sessions"][1]]
    assert len(api) == len(flat) == len(sess) > 50
    assert api == flat == sess
    for name, mode in (("api", "api-messages"), ("flat", "flattened"), ("sessions", "cached-session")):
        rows = [r for r in _rows(got[name][0]) if r["phase"] in ("decide", "lookup") or r["phase"].startswith("dm_reply")]
        assert rows and {r["usage"].get("history") for r in rows} == {mode}, name
    cmds = [c for _, _, c in got["sessions"][1]]
    assert sum("--session-id" in c for c in cmds) < sum("--resume" in c for c in cmds)       # mostly appends
    assert all("--no-session-persistence" in c for _, _, c in got["flat"][1])


def test_round_2s_exchange_is_visible_in_full_in_rounds_3_to_5(three_ways):
    (a, b), got = three_ways
    n = 0
    for s, text, _ in [(s, llm.flatten(t), m) for s, t, m in got["api"][1] if not isinstance(m[-1]["content"], str)]:
        who = re.search(r"^You are (\w+)\.", s, re.M).group(1)
        rnd = int(re.findall(r"(?:^# Round |^Round )(\d+)", _last_message(text), re.M)[-1])
        if who not in (a, b) or rnd not in (3, 4, 5):
            continue
        pos = [text.find(t) for t in _Brain.TEXTS]
        assert all(p >= 0 for p in pos) and pos == sorted(pos), (who, rnd, pos)
        n += 1
    assert n >= 6                                                     # both agents, rounds 3-5, with their DM replies


def test_api_calls_append_within_a_chunk_with_breakpoints(three_ways):
    """Within a conversation each call's messages extend the previous call's unchanged (the cached prefix); the previous turn's
    last block and the new message carry cache breakpoints."""
    _, got = three_ways
    last = {}
    for s, texts, msgs in got["api"][1]:
        if isinstance(msgs[-1]["content"], str):
            continue                                                  # an editorial turn: outside the conversation
        who = re.search(r"^You are (\w+)\.", s, re.M).group(1)
        prev = last.get(who)
        if len(texts) > 1:
            assert prev is not None and prev[0] == s and texts[:len(prev[1])] == prev[1] and len(texts) == len(prev[1]) + 2
            assert msgs[-2]["role"] == "assistant" and msgs[-2]["content"][0]["cache_control"] == {"type": "ephemeral"}
        assert msgs[-1]["content"][0]["cache_control"] == {"type": "ephemeral"}
        assert sum(isinstance(m["content"], list) for m in msgs) <= 2
        last[who] = (s, texts)


def test_the_system_prompt_is_frozen_within_a_chunk(three_ways):
    _, got = three_ways
    sys_by_chunk = {}
    for s, texts, msgs in got["api"][1]:
        if isinstance(msgs[-1]["content"], str):
            continue
        who = re.search(r"^You are (\w+)\.", s, re.M).group(1)
        if len(texts) > 1:
            assert sys_by_chunk[who] == s
        sys_by_chunk[who] = s


def test_uncached_history_is_logged_once(tmp_path, monkeypatch, caplog):
    import logging
    inst = _inst(["rounds=2"])
    with caplog.at_level(logging.WARNING, logger="charter.llm"):
        _cli_run(tmp_path, monkeypatch, inst, _Brain("x", "y"), sessions=False)
    assert sum("history mode is uncached" in r.getMessage() for r in caplog.records) == 1


def test_sessions_gate_is_one_function(monkeypatch, tmp_path):
    """Stage 0: the CLI logs in with a fresh config directory and no OAuth variable, so sessions are on; the one gate turns them
    off, and GIVE_UP failed starts turn them off for a run."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert llm.sessions_available() is True and llm.Sessions(tmp_path).usable is True
    monkeypatch.setattr(llm, "sessions_available", lambda: False)
    assert llm.Sessions(tmp_path).usable is False
    monkeypatch.setattr(llm, "sessions_available", lambda: True)
    s = llm.Sessions(tmp_path)
    s.failures = llm.Sessions.GIVE_UP
    assert s.usable is False


# ------------------------------------------------------------------ claude -p sessions (stage-0 findings)
def _fake_cli(monkeypatch, costs=None):
    calls = []
    total = {}

    def run(cmd, **kw):
        sid = cmd[cmd.index("--session-id") + 1] if "--session-id" in cmd else cmd[cmd.index("--resume") + 1] if "--resume" in cmd else None
        total[sid] = total.get(sid, 0.0) + 0.01 * (len(calls) + 1)
        calls.append((cmd, kw))
        reply = {"reasoning": "", "lookups": [], "actions": [], "goal_guesses_json": "{}"}
        res = {"type": "result", "result": json.dumps(reply), "structured_output": reply, "session_id": sid,
               "total_cost_usd": round(total[sid], 6),
               "usage": {"input_tokens": 3, "output_tokens": 5, "cache_read_input_tokens": 12000, "cache_creation_input_tokens": 300,
                         "cache_creation": {"ephemeral_1h_input_tokens": 300, "ephemeral_5m_input_tokens": 0}}}
        return SimpleNamespace(stdout=json.dumps(res) + "\n", stderr="", returncode=0)
    monkeypatch.setattr(llm.subprocess, "run", run)
    return calls


def _hk(r=0):
    return SimpleNamespace(inst={"spec": {"context": {"enabled": True}}}, spec={}, r=r)


def _flag(cmd, f):
    return cmd[cmd.index(f) + 1] if f in cmd else None


def test_resumes_keep_tools_and_schema_and_a_new_system_prompt_starts_a_new_session(monkeypatch, tmp_path):
    """--tools "" and --json-schema are the same on every call of a session (they lead the cached prefix); the CLI ignores
    --system-prompt on resume, so a conversation whose system prompt changed is never resumed: a new session starts."""
    calls = _fake_cli(monkeypatch)
    pol = AG.LLMPolicy("claude_code", {})
    pol.use_run_dir(tmp_path)
    a = {"id": "a1", "cls": "worker", "model": "m"}
    pol.act_recorded(_hk(0), a, "SYS A", HM.HistoryTurn("OPEN", ("a1", 0), True), 3, False)
    pol.act_recorded(_hk(0), a, "SYS A", AG.DMDelta("DELTA", "FULL"), 3, False)
    pol.act_recorded(_hk(1), a, "SYS A", HM.HistoryTurn("NEXT", ("a1", 0), False, "RESTART"), 3, False)
    pol.act_recorded(_hk(2), a, "SYS B", HM.HistoryTurn("NEXT 2", ("a1", 0), False, "RESTART 2"), 3, False)
    cmds = [c for c, _ in calls]
    sid = _flag(cmds[0], "--session-id")
    assert [_flag(c, "--resume") for c in cmds[1:3]] == [sid, sid]
    assert {_flag(c, "--json-schema") for c in cmds[:3]} == {_flag(cmds[0], "--json-schema")}
    assert all(_flag(c, "--tools") == "" for c in cmds)
    assert "--resume" not in cmds[3] and _flag(cmds[3], "--session-id") not in (None, sid)
    assert _flag(cmds[3], "-p") == "RESTART 2" and _flag(cmds[3], "--system-prompt") == "SYS B"
    assert all(kw["cwd"] == str(tmp_path / llm.Sessions.DIRNAME / "cwd") for _, kw in calls)   # the run's own cwd


def test_a_resume_after_55_minutes_starts_a_new_session(monkeypatch, tmp_path):
    calls = _fake_cli(monkeypatch)
    pol = AG.LLMPolicy("claude_code", {})
    pol.use_run_dir(tmp_path)
    a = {"id": "a1", "cls": "worker", "model": "m"}
    pol.act_recorded(_hk(0), a, "SYS", HM.HistoryTurn("OPEN", ("a1", 0), True), 3, False)
    pol._conv["a1"]["t"] -= llm.SESSION_MAX_IDLE + 1                    # the session's cache is about to expire
    _, _, usage, _ = pol.act_recorded(_hk(1), a, "SYS", HM.HistoryTurn("NEXT", ("a1", 0), False, "RESTART"), 3, False)
    assert "--resume" not in calls[1][0] and _flag(calls[1][0], "-p") == "RESTART" and usage["history_restart"] is True


def test_session_cost_is_per_call_and_cache_writes_are_logged(monkeypatch, tmp_path):
    """total_cost_usd is cumulative over a session on resume: cc_equiv_usd is this call's share; the 1h/5m cache writes and the
    cache read are in the call's usage (calls.jsonl)."""
    _fake_cli(monkeypatch)
    pol = AG.LLMPolicy("claude_code", {})
    pol.use_run_dir(tmp_path)
    a = {"id": "a1", "cls": "worker", "model": "m"}
    u = [pol.act_recorded(_hk(0), a, "SYS", HM.HistoryTurn("OPEN", ("a1", 0), True), 3, False)[2]]
    u.append(pol.act_recorded(_hk(1), a, "SYS", HM.HistoryTurn("NEXT", ("a1", 0), False, "R"), 3, False)[2])
    u.append(pol.act_recorded(_hk(2), a, "SYS", HM.HistoryTurn("NEXT 2", ("a1", 0), False, "R2"), 3, False)[2])
    assert [x["cc_equiv_usd"] for x in u] == pytest.approx([0.01, 0.02, 0.03])        # session totals 0.01, 0.03, 0.06
    assert [x["cc_session_usd"] for x in u] == pytest.approx([0.01, 0.03, 0.06])
    assert all(x["cache_write_1h"] == 300 and x["cache_write_5m"] == 0 and x["cache_read"] == 12000 for x in u)


def test_transcripts_move_into_the_run_folder_at_the_end(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    s = llm.Sessions(tmp_path / "run")
    home = s.transcript_dirs()[1]
    home.mkdir(parents=True)
    (home / "abc.jsonl").write_text("{}")
    info = s.collect()
    assert info["moved"] == 1 and (tmp_path / "run" / llm.Sessions.DIRNAME / "transcripts" / "abc.jsonl").exists()
    assert not home.exists() and info["from"] == str(home)


def test_a_lost_conversation_restarts_with_the_full_memory(monkeypatch):
    """A failed call drops the agent's conversation; the next call sends the turn's self-contained restart text."""
    sent = []
    calls = {"n": 0}

    def fake_call(backend, model, system, user, schema, **kw):
        sent.append(str(user))
        calls["n"] += 1
        att = kw["attempts"]
        if calls["n"] == 2:
            att.append({"ok": False, "raw": None})
            return {"actions": [], "_error": "boom"}, "", {}
        raw = json.dumps({"reasoning": "", "lookups": [], "actions": [], "goal_guesses_json": "{}"})
        att.append({"ok": True, "raw": raw})
        return json.loads(raw), "", {}
    pol = AG.LLMPolicy("api", {})
    monkeypatch.setattr(pol, "llm", SimpleNamespace(**{n: getattr(llm, n) for n in ("Turn", "flatten", "Sessions", "_warn_once", "SESSION_MAX_IDLE")},
                                                    call=fake_call))
    k = SimpleNamespace(inst={"spec": {"context": {"enabled": True}}}, spec={}, r=0)
    a = {"id": "a1", "cls": "worker", "model": "m"}
    pol.act_recorded(k, a, "SYS", HM.HistoryTurn("OPEN r1", ("a1", 0), True), 3, False)
    k.r = 1
    pol.act_recorded(k, a, "SYS", HM.HistoryTurn("NEXT r2", ("a1", 0), False, "RESTART r2"), 3, False)   # fails
    k.r = 2
    _, _, usage, _ = pol.act_recorded(k, a, "SYS", HM.HistoryTurn("NEXT r3", ("a1", 0), False, "RESTART r3"), 3, False)
    assert sent[0] == "OPEN r1" and sent[2] == "RESTART r3" and usage["history_restart"] is True


# ------------------------------------------------------------------ resume, determinism, export
def test_runs_are_deterministic_and_a_resume_restarts_conversations(tmp_path):
    inst = _inst()
    a = runner.run(inst, AG.ScriptedPolicy(5), tmp_path / "a", log=lambda *x: None)
    b = runner.run(_inst(), AG.ScriptedPolicy(5), tmp_path / "b", log=lambda *x: None)
    assert (a / HM.FILE).read_text() == (b / HM.FILE).read_text()
    assert [r["user_sha"] for r in _rows(a, "calls.jsonl")] == [r["user_sha"] for r in _rows(b, "calls.jsonl")]
    c = tmp_path / "c"
    runner.run(_inst(), AG.ScriptedPolicy(5), c, log=lambda *x: None, until=3)
    runner.run(json.loads((c / "instance.json").read_text()), AG.ScriptedPolicy(5), c, log=lambda *x: None, resume=True)
    rj = json.loads((c / "run.json").read_text())
    assert rj["history_restarts"] == [3]
    mem_a, mem_c = _rows(a, HM.FILE), _rows(c, HM.FILE)
    assert [(m["round"], m["agent"]) for m in mem_c] == [(m["round"], m["agent"]) for m in mem_a]
    assert [m for m in mem_c if m["round"] < 3] == [m for m in mem_a if m["round"] < 3]   # cut back and kept
    r3 = [r for r in _rows(c) if r["round"] == 3 and r["phase"] == "decide"]
    assert r3 and all(r["context"]["history"]["message"] == "start" for r in r3)


def test_the_export_carries_history_columns(three_ways, tmp_path):
    from charter import export as X
    _, got = three_ways
    X.export([got["api"][0]], tmp_path / "ds", fmt="csv")
    data = X.load(tmp_path / "ds")
    assert data["runs"][0]["history_chunk"] == 3
    dec = [t for t in data["turns"] if t["phase"] == "decide"]
    assert {t["history_message"] for t in dec} == {"start", "continue"}
    assert {t["history_transport"] for t in dec} == {"api-messages"}
    assert all(isinstance(t["history_full"], int) and t["history_chunk_start"] >= 1 for t in dec)

