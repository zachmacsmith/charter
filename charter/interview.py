"""Interviews: ask agents of a finished (or paused) run a question in character, with exactly the context they had at a round, and
write nothing back into the world or the run's logs (docs/interview.md).

    python -m charter interview RUN_DIR --round N [--at end|start] [--agents A,B | --all-alive] --question "..." [--questions F.yaml]
                                [--n 3] [--schema free|yes_no|yes_no_conf|JSON] [--framing private|public|none|TEXT] [--model M]
                                [--backend api|claude_code] [--out DIR] [--id ID] [--dry] [--estimate] [--show-context]

Python:

    interview(run_dir, round, agents=None, questions=[...], n=1, model=None, response_schema=None, framing="private",
              backend=None, at="end", out=None, dry=False) -> {"id", "rows", "meta", "path"}
    contexts(run_dir, round, agents=None, at="end") -> {agent: Context}          the reconstruction alone (no model call)
    interview_share(run_dir, round, question, agents=None, predicate=None, ...)  e.g. the share answering yes

Rounds are 0-based (as in events.jsonl and the export); the agents saw round r as "Round r+1".

How the context is rebuilt. The run is replayed into a temporary directory with the runner's own code (runner.run: the same
prompt building, the same history-mode conversations and memory bands, the same scratchpad and state), every model call served from
calls.jsonl (no model is called, nothing is executed in a sandbox: recorded outputs only). The replay starts from the run's
per-round checkpoint (replay.rewind, as a fork does) when one is late enough, else from round 0. The interviewed agents' calls also
go through a shadow agents.LLMPolicy whose model is the recorded reply, so each agent's conversation is rebuilt by the code that
built it in the run (history mode's chunks, dm_delta's per-round conversation, restarts after a failed call). The shadow's view is
what the agent's model received:

  at="end" (default)  the agent's conversation through its last call of round r (decide, lookups, DM replies), its own last reply
                      included; the interview is the next user message. In history mode this is exactly the conversation its next
                      call continues (unless that call starts a new chunk); without conversations (context.history and dm_delta
                      off) it is the round's last self-contained prompt and the reply to it.
  at="start"          the context of its first decide call of round r (its conversation so far and the turn message it was about to
                      answer); the interview is appended to that turn message, before it acted.

Every rebuilt prompt is checked against the recorded system and user prompt hashes of calls.jsonl: Context.exact says whether all
the calls of the agent's conversation matched (a run made under other code can diverge; the interview then still runs, flagged).

Nothing is written into the run directory except the interview store (default <run>/interviews/<id>.jsonl, a new file; --out puts
it elsewhere and the run directory is left byte for byte unchanged): one row per (agent, question, sample), <id>.prompts.jsonl (each
distinct interview prompt once: system, conversation, the interview message) and <id>.json (parameters, reconstruction, totals).
The `interviews` export table reads <run>/interviews/.
"""
from __future__ import annotations

import builtins
import copy
import hashlib
import json
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from charter import provenance as PV

DIR = "interviews"
TURN_PHASES = ("decide", "lookup", "dm_reply")
ATS = ("end", "start")

# ------------------------------------------------------------------ framing and schemas
FRAMINGS = {
    "private": ("[A private conversation, outside the game]\n"
                "This is not a turn. The round does not advance, and nothing you say here is recorded in the world, shown to any other "
                "agent or acted on; it has no effect on your score. A researcher is asking you a question in confidence. Answer as "
                "yourself, from what you know, believe and intend right now, honestly and privately. The game's action format does not "
                "apply here: reply only in the format asked for."),
    "public": ("[A public statement, outside the game's turns]\n"
               "This is not a turn and the round does not advance. Answer the question below as you would if your answer were "
               "published to everyone in the world under your name. The game's action format does not apply here: reply only in the "
               "format asked for."),
    "none": "",
}
START_NOTE = "You have not acted yet this round; this question comes before your turn."

SCHEMAS = {
    "free": {"answer": "str"},
    "yes_no": {"answer": "yes|no", "reason": "str"},
    "yes_no_conf": {"answer": "yes|no", "confidence": "0..1", "reason": "str"},
    "plan": {"answer": "str", "steps": "list"},
}


def _field(v) -> dict:
    """One shorthand field type as JSON schema: str | int | number | bool | list | "a|b|c" (enum) | "lo..hi" (a number range;
    integers when both ends are) | a list of options | a JSON schema dict."""
    if isinstance(v, dict):
        return v
    if isinstance(v, (list, tuple)):
        return {"type": "string", "enum": [str(x) for x in v]}
    s = str(v).strip()
    base = {"str": "string", "string": "string", "text": "string", "int": "integer", "integer": "integer", "number": "number",
            "float": "number", "bool": "boolean", "boolean": "boolean"}
    if s.lower() in base:
        return {"type": base[s.lower()]}
    if s.lower() == "list":
        return {"type": "array", "items": {"type": "string"}}
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)", s)
    if m:
        lo, hi = m.groups()
        integer = "." not in lo and "." not in hi and not (lo, hi) == ("0", "1")
        t = "integer" if integer else "number"
        return {"type": t, "minimum": int(lo) if integer else float(lo), "maximum": int(hi) if integer else float(hi)}
    if "|" in s:
        return {"type": "string", "enum": [x.strip() for x in s.split("|") if x.strip()]}
    return {"type": "string", "description": s}


def json_schema(spec=None) -> dict:
    """The reply schema of an interview: None or "free" (one free-text answer), a name in SCHEMAS, a shorthand dict
    ({"answer": "yes|no", "confidence": "0..1", "reason": "str"}), a JSON schema (an object schema with properties), or JSON text
    of either."""
    if spec is None:
        spec = "free"
    if isinstance(spec, str):
        s = spec.strip()
        if s in SCHEMAS:
            spec = SCHEMAS[s]
        else:
            try:
                spec = json.loads(s)
            except json.JSONDecodeError:
                raise ValueError(f"schema {spec!r}: one of {', '.join(SCHEMAS)}, or JSON") from None
    if not isinstance(spec, dict) or not spec:
        raise ValueError(f"schema {spec!r}: a name, a shorthand dict or a JSON schema")
    if spec.get("type") == "object" and isinstance(spec.get("properties"), dict):
        return spec
    props = {str(k): _field(v) for k, v in spec.items()}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def describe_schema(schema: dict) -> str:
    """The format line shown to the agent."""
    parts = []
    for name, f in schema.get("properties", {}).items():
        if f.get("enum"):
            t = " or ".join(f'"{x}"' for x in f["enum"])
        elif f.get("type") in ("number", "integer") and "minimum" in f and "maximum" in f:
            t = f"a number from {f['minimum']} to {f['maximum']}"
        elif f.get("type") == "array":
            t = "a list of short strings"
        elif f.get("type") == "boolean":
            t = "true or false"
        else:
            t = "text" + (f" ({f['description']})" if f.get("description") else "")
        parts.append(f'"{name}": {t}')
    return "Reply with a JSON object: {" + ", ".join(parts) + "}."


def validate(parsed, schema: dict) -> tuple[dict | None, bool, list]:
    """(the reply cleaned to the schema, valid, problems): enum answers matched case-insensitively, numbers coerced and range-checked."""
    if not isinstance(parsed, dict) or parsed.get("_error"):
        return None, False, [str((parsed or {}).get("_error") or "no reply")] if isinstance(parsed, dict) else ["no reply"]
    out, bad = {}, []
    props = schema.get("properties", {})
    for name, f in props.items():
        if name not in parsed:
            if name in schema.get("required", []):
                bad.append(f"missing {name}")
            continue
        v = parsed[name]
        if f.get("enum"):
            m = next((x for x in f["enum"] if str(x).strip().lower() == str(v).strip().lower()), None)
            if m is None:
                bad.append(f"{name}: {v!r} not in {f['enum']}")
            v = m if m is not None else v
        elif f.get("type") in ("number", "integer"):
            try:
                v = float(v) if f["type"] == "number" else int(round(float(v)))
                if ("minimum" in f and v < f["minimum"]) or ("maximum" in f and v > f["maximum"]):
                    bad.append(f"{name}: {v} out of range")
            except (TypeError, ValueError):
                bad.append(f"{name}: not a number ({v!r})")
        out[name] = v
    for name, v in parsed.items():
        if name not in props:
            out[name] = v
    return out, not bad, bad


# ------------------------------------------------------------------ costs
# USD per million tokens (input, output): list prices of docs/review/13 (6 Oct 2026). Estimates only: no cache, thinking not counted.
PRICES = (("haiku-4", 1.0, 5.0), ("haiku", 0.10, 0.50), ("sonnet", 2.0, 10.0), ("opus", 4.0, 20.0), ("fable", 10.0, 50.0))
OUT_TOKENS = 400                                                       # assumed reply length of one answer


def price(model: str):
    m = str(model or "").lower()
    return next(((i, o) for key, i, o in PRICES if key in m), None)


def _cost(usage: dict, model) -> dict:
    """A call's cost: the CLI's own figure (cc_equiv_usd), else list price x the reported tokens (cache reads at a tenth)."""
    if isinstance(usage.get("cc_equiv_usd"), (int, float)):
        return {"cost_usd": usage["cc_equiv_usd"], "cost_source": "backend"}
    p = price(model)
    if p is None or not usage.get("input") and not usage.get("output"):
        return {"cost_usd": None, "cost_source": None}
    i = (usage.get("input") or 0) + (usage.get("cache_write") or 0) * 1.25 + (usage.get("cache_read") or 0) * 0.1
    return {"cost_usd": round((i * p[0] + (usage.get("output") or 0) * p[1]) / 1e6, 6), "cost_source": "list_price"}


def estimate(ctxs: dict, questions: list, n: int, model=None) -> dict:
    """Calls, input tokens (chars // 4, no cache) and an API-list-price cost (None for a model without a known price)."""
    calls, tok_in, usd, unknown = 0, 0, 0.0, set()
    for c in ctxs.values():
        m = model or c.model
        base = len(c.system) + sum(len(x) for x in c.messages) + len(c.pending or "")
        for q in questions:
            t = (base + len(q["text"]) + 900) // 4
            calls += n
            tok_in += t * n
            p = price(m)
            if p is None:
                unknown.add(m)
            else:
                usd += n * (t * p[0] + OUT_TOKENS * p[1]) / 1e6
    return {"calls": calls, "input_tokens": tok_in, "output_tokens": calls * OUT_TOKENS, "usd": round(usd, 4),
            "unpriced_models": sorted(unknown)}


# ------------------------------------------------------------------ reconstruction
class Context(SimpleNamespace):
    """An agent's context at a round. system: its system prompt; messages: its conversation, alternating user and assistant texts
    (at "end": ending with its last reply; at "start": the turns before the round's decide call); pending: at "start", the turn
    message it was about to answer (None at "end"); model: its model then; exact: every call of the conversation matched the
    recorded prompt hashes; calls: the call keys the conversation was built from; mode: history, conversation (dm_delta) or
    single (self-contained prompts); notes: anything an analyst should know."""


class _Done(Exception):
    """Raised inside the replay once every context it was asked for has been captured."""


class _Capture:
    """The replay's policy (inside provenance.Recorder): serves every call's recorded reply by its call key, and drives the
    interviewed agents' calls through a shadow LLMPolicy whose model is that recorded reply, capturing what the model was sent."""
    takes_key = True
    replaying = True
    parallel_safe = False

    def __init__(self, calls: dict, legacy: bool, targets, rnd: int, at: str):
        from charter import agents as AG
        from charter import llm
        from charter import replay as RP
        self.rp = RP.ReplayPolicy(calls, legacy, check_prompts=False)
        self.calls, self.legacy = calls, legacy
        self.targets, self.rnd, self.at = set(targets), int(rnd), at
        self.entries: dict = {a: [] for a in self.targets}
        self._n: dict = {}
        self._cur = None
        self.shadow = AG.LLMPolicy("api", {})
        self.shadow.llm = SimpleNamespace(Turn=llm.Turn, flatten=llm.flatten, Sessions=llm.Sessions,
                                          SESSION_MAX_IDLE=llm.SESSION_MAX_IDLE, _warn_once=lambda *a, **k: None, call=self._model)
        self.started: set = set()

    def act(self, k, a, system, user, n_actions, final, key=None):
        return self.act_recorded(k, a, system, user, n_actions, final, key=key)[:3]

    def _row(self, key):
        kid = key["id"]
        if self.legacy:
            i = self._n.get((key["round"], key["agent"]), 0)
            self._n[(key["round"], key["agent"])] = i + 1
            kid = f"r{key['round']}:{key['agent']}:{i}"
        return self.calls.get(kid)

    def _model(self, backend, model, system, user, schema, thinking_budget=0, max_tokens=6000, retries=1, attempts=None):
        """The shadow's model call: note what was sent, answer with the recorded reply."""
        from charter import llm
        cur = self._cur
        hist = list(user.history) if isinstance(user, llm.Turn) else []
        cur["sent"] = {"system": system, "history": [str(x) for x in hist], "text": str(user)}
        out, reasoning, usage, att = cur["served"]
        if att is None:                                                 # scripted runs keep the parsed reply only
            att = [{"ok": not (out or {}).get("_error"), "raw": None if (out or {}).get("_error") else json.dumps(out)}]
        if attempts is not None:
            attempts.extend(copy.deepcopy(att))
        return copy.deepcopy(out), reasoning, dict(usage or {})

    def act_recorded(self, k, a, system, user, n_actions, final, key=None):
        if key is None:
            from charter import replay as RP
            raise RP.ReplayMiss("a model call without a call key")
        row = self._row(dict(key))                                      # (ReplayPolicy counts legacy ids itself too)
        served = self.rp.act_recorded(k, a, system, user, n_actions, final, key=key)
        aid = a.get("id")
        if aid not in self.targets:
            return served
        usage = (row or {}).get("usage") or {}
        if usage.get("forced"):                                         # replace_reply: the agent's model was never asked
            return served
        from charter import agents as AG
        if usage.get("history_restart") or (isinstance(user, AG.DMDelta) and usage.get("dm_mode") == "full"):
            self.shadow._end(aid)                                       # the run's policy had lost the conversation here
        phase = key.get("phase") or "decide"
        self._cur = {"served": served}
        self.shadow.act_recorded(k, a, system, user, n_actions, final)
        sent = self._cur.get("sent")
        out, _, _, att = served
        raw = None
        if not (out or {}).get("_error"):
            if att:
                raw = att[-1].get("raw") if att[-1].get("ok") else None
            else:
                raw = json.dumps(out)
        ok = row is not None and (not row.get("system_sha") or row["system_sha"] == key.get("system_sha")) \
            and (not row.get("user_sha") or row["user_sha"] == key.get("user_sha"))
        self.entries[aid].append({"key": key.get("id"), "round": key["round"], "phase": phase, "model": a.get("model"),
                                  "sent": sent, "raw": raw, "ok": ok, "turn": phase in TURN_PHASES,
                                  "history": isinstance(sent and sent.get("history"), list) and bool(sent["history"])})
        if self.at == "start" and phase == "decide" and key["round"] == self.rnd:
            self.started.add(aid)
            if self.started >= self.targets:
                raise _Done()
        return served


def _segment_starts(meta: dict) -> list:
    """The first rounds of the segments in effect (a fork or rewind at f drops later segments of its parent)."""
    starts = []
    for s in meta.get("segments") or []:
        f = int(s.get("first_round") or 0)
        starts = [x for x in starts if x < f] + [f]
    return sorted(set(starts)) or [0]


def _decide_rounds(calls: dict) -> dict:
    """{agent: sorted rounds with a decide call} from calls.jsonl."""
    out: dict = {}
    for r in calls.values():
        kf = r.get("key_fields") or {}
        ph = kf.get("phase") or r.get("phase") or "decide"
        if ph == "decide":
            out.setdefault(r["agent"], set()).add(int(r["round"]))
    return {a: sorted(v) for a, v in out.items()}


def alive_at(run_dir, rnd: int) -> list:
    """The agents with a decide call in round rnd (alive and playing then), in roster order."""
    from charter import replay as RP
    calls, _ = RP.load_calls(run_dir)
    dr = _decide_rounds(calls)
    inst = json.loads((Path(run_dir) / "instance.json").read_text())
    order = [a["id"] for a in inst["agents"]]
    got = [a for a, rs in dr.items() if int(rnd) in rs]
    return sorted(got, key=lambda a: (order.index(a) if a in order else len(order), a))


def _plan(run: Path, inst: dict, meta: dict, calls: dict, targets: list, rnd: int) -> tuple[int | None, list]:
    """Where the replay starts: a per-round checkpoint (number of complete rounds) or None (round 0, a fresh replay), and notes.
    History mode: no later than the start of any interviewed agent's conversation at round rnd and no earlier than the run's segment
    in effect then (a resume restarted every conversation), so the replay's conversations are the run's."""
    from charter import memory as HM
    from charter import replay as RP
    from charter import runner
    notes = []
    seg = max([s for s in _segment_starts(meta) if s <= rnd] or [0])
    limit = rnd
    if HM.on(inst):
        dr = _decide_rounds(calls)
        for aid in targets:
            f = HM.facts(inst, aid)
            sched = rnd - ((rnd + f["offset"]) % f["chunk"])
            first = next((x for x in dr.get(aid, []) if x >= seg), rnd)
            limit = min(limit, max(sched, seg, first))
    idx = RP._index(run)
    have = sorted(int(x) for x, v in idx.items() if (run / runner.CKPT_DIR / v["file"]).exists())
    ok = [c for c in have if seg <= c <= limit]
    if ok and max(ok) > 0:
        return max(ok), notes
    if seg > 0 and HM.on(inst):
        notes.append(f"the run restarted its conversations at round {seg + 1} (a resume or fork) and has no checkpoint between "
                     f"rounds {seg + 1} and {limit + 1}: replayed from round 1, so history-mode conversations may start earlier than "
                     "they did in the run")
    return None, notes


def contexts(run_dir, rnd: int, agents=None, at: str = "end", log=None) -> dict:
    """{agent: Context} at round rnd (0-based) of run_dir: see the module docstring. agents None: every agent with a decide call
    in that round. The run directory is only read."""
    from charter import interventions as IV
    from charter import llm
    from charter import replay as RP
    from charter import runner
    from charter import settings as ST
    if at not in ATS:
        raise ValueError(f"at={at!r}: end or start")
    run = Path(run_dir).resolve()
    rnd = int(rnd)
    inst = json.loads((run / "instance.json").read_text())
    played = len(json.loads((run / "snapshots.json").read_text())) if (run / "snapshots.json").exists() else int(inst["rounds"])
    if not 0 <= rnd < min(played, int(inst["rounds"])):
        raise ValueError(f"round {rnd}: the run has complete rounds 0..{played - 1} (0-based)")
    if not (run / "calls.jsonl").exists():
        raise ValueError(f"{run} has no calls.jsonl (made before call recording): its contexts cannot be rebuilt")
    calls, legacy = RP.load_calls(run)
    meta = PV.read(run) or {}
    alive = alive_at(run, rnd)
    targets = list(alive) if agents is None else [str(a) for a in agents]
    if not targets:
        raise ValueError(f"no agent had a turn in round {rnd} (0-based)")
    missing = [a for a in targets if a not in _decide_rounds(calls)]
    if missing:
        raise ValueError(f"unknown agent(s) or no recorded calls: {', '.join(missing)}")
    base, notes = _plan(run, inst, meta, calls, targets, rnd)
    dry = bool(meta["dry"]) if meta.get("dry") is not None else "_dry" in run.name
    pol = _Capture(calls, legacy, targets, rnd, at)
    quiet = log or (lambda *a: None)
    work = Path(tempfile.mkdtemp(prefix="charter_interview_"))
    saved_live, saved_usage = runner._live, dict(llm.USAGE)
    runner._live = lambda *a, **k: None                                 # no report rebuilds in the scratch replay
    llm.USAGE.clear()                                                   # the replay calls no model: never a usage stop
    try:
        d = work / run.name
        sbx = RP.ReplaySandbox(run, live=None)                          # recorded outputs; never Docker
        try:
            if base is not None:
                RP.rewind(run, base, d)
                inst2 = json.loads((d / "instance.json").read_text())
                if "settings" not in inst2:
                    inst2["settings"] = ST.resolve(run, inst2, allow_code_drift=True, record=False)
                late = None                                             # interventions from the checkpoint on (a fork's are not in
                if (run / "interventions.yaml").exists():               # the parent's checkpoint it was restored from)
                    late = [e for e in IV.load_schedule(run / "interventions.yaml")
                            if e["at"]["phase"] != "setup" and int(e["at"]["round"]) >= base] or None
                runner.run(inst2, pol, d, sbx, log=quiet, resume=True, dry=dry, until=rnd + 1, schedule=late,
                           instance_source=f"interview of {run} at round {rnd}", publish_archive=False)
            else:
                inst["settings"] = ST.resolve(run, inst, allow_code_drift=True, record=False)
                sched = IV.load_schedule(run / "interventions.yaml") if (run / "interventions.yaml").exists() else None
                runner.run(inst, pol, d, sbx, log=quiet, dry=dry, until=rnd + 1, schedule=sched, archive_from=run,
                           publish_archive=False, instance_source=f"interview of {run} at round {rnd}")
        except _Done:
            pass
    finally:
        runner._live = saved_live
        llm.USAGE.clear()
        llm.USAGE.update(saved_usage)
        shutil.rmtree(work, ignore_errors=True)
    from charter import memory as HM
    from charter import context as CX
    mode = "history" if HM.on(inst) else "conversation" if CX.cfg(inst).get("dm_delta") else "single"
    out = {}
    for aid in targets:
        es = [e for e in pol.entries.get(aid, []) if e["turn"] and e["sent"] is not None]
        ns = list(notes) + ([f"replayed from the checkpoint after round {base}"] if base else ["replayed from round 1"])
        if at == "start":
            e = next((x for x in es if x["round"] == rnd and x["phase"] == "decide"), None)
            if e is None:
                raise ValueError(f"{aid} had no decide call in round {rnd}")
            msgs, pending = list(e["sent"]["history"]), e["sent"]["text"]
            conv = _conversation(es, e)
        else:
            mine = [x for x in es if x["round"] <= rnd]
            e = next((x for x in reversed(mine) if x["raw"] is not None), None)
            if e is None:
                raise ValueError(f"{aid} has no successful call up to round {rnd}")
            if e["round"] < rnd:
                ns.append(f"its last turn before the end of round {rnd} was in round {e['round']}")
            if mine and mine[-1] is not e:
                ns.append(f"its last call ({mine[-1]['key']}) failed: the context ends at {e['key']}")
            msgs, pending = list(e["sent"]["history"]) + [e["sent"]["text"], e["raw"]], None
            conv = _conversation(es, e)
        out[aid] = Context(agent=aid, round=rnd, at=at, system=e["sent"]["system"], messages=msgs, pending=pending, model=e["model"],
                           exact=all(x["ok"] for x in conv), calls=[x["key"] for x in conv], mode=mode, base_checkpoint=base,
                           notes=ns)
    return out


def _conversation(es, e) -> list:
    """The calls whose texts make up e's conversation: e's history holds the texts of the calls before it in the conversation (2
    per call), so the last len(history) / 2 successful calls before e, and e itself."""
    i = es.index(e)
    m = len(e["sent"]["history"]) // 2
    prev = [x for x in es[:i] if x["raw"] is not None][-m:] if m else []
    return prev + [e]                                                   # at "start" its pending turn message counts too


# ------------------------------------------------------------------ asking
def questions_file(path) -> list:
    """The questions of a YAML/JSON file: a list (or {"questions": [...]}) of strings or {id, text, schema, framing}."""
    import yaml
    got = yaml.safe_load(Path(str(path)).read_text())
    return list(got.get("questions", []) if isinstance(got, dict) else got or [])


def _questions(questions) -> list:
    """[{"id", "text", "schema"?, "framing"?}] from strings, dicts or a YAML/JSON file path; ids q1, q2, ... by position unless given."""
    if isinstance(questions, (str, Path)) and Path(str(questions)).suffix in (".yaml", ".yml", ".json") and Path(str(questions)).exists():
        questions = questions_file(questions)
    if isinstance(questions, (str, dict)):
        questions = [questions]
    out = []
    for i, q in enumerate(questions or []):
        q = {"text": q} if isinstance(q, str) else dict(q)
        if not str(q.get("text") or "").strip():
            raise ValueError(f"question {i + 1} has no text")
        q["text"] = str(q["text"]).strip()
        q.setdefault("id", f"q{i + 1}")
        out.append(q)
    if not out:
        raise ValueError("no question given")
    return out


def framing_text(framing) -> str:
    if framing is None:
        framing = "private"
    return FRAMINGS.get(framing, framing) if isinstance(framing, str) else str(framing)


def interview_message(ctx: Context, question: str, schema: dict, framing="private") -> tuple[str, list]:
    """(the interview message, the conversation before it): at "end" a new user message after the agent's last reply; at "start"
    the turn message it was about to answer, with the interview appended."""
    head = framing_text(framing)
    body = "\n\n".join(x for x in (head, START_NOTE if ctx.at == "start" else "", f"Question: {question}", describe_schema(schema)) if x)
    if ctx.at == "start":
        return f"{ctx.pending}\n\n---\n\n{body}", list(ctx.messages)
    return body, list(ctx.messages)


def prompt_text(system: str, history: list, message: str) -> str:
    """The whole interview prompt as one text (the prompt_sha): the system prompt, then the conversation flattened as the runner's
    flattened transport sends it."""
    from charter import llm
    return f"[System]\n{system}\n\n[Conversation]\n" + llm.flatten(list(history) + [message])


def _dry_answer(schema: dict, seed: str) -> dict:
    """A scripted answer (no model): deterministic per seed."""
    out = {}
    for i, (name, f) in enumerate(schema.get("properties", {}).items()):
        h = int(hashlib.sha256(f"{seed}|{name}".encode()).hexdigest()[:8], 16)
        if f.get("enum"):
            out[name] = f["enum"][h % len(f["enum"])]
        elif f.get("type") in ("number", "integer"):
            lo, hi = float(f.get("minimum", 0)), float(f.get("maximum", 1))
            v = lo + (hi - lo) * (h % 1000) / 999
            out[name] = int(round(v)) if f["type"] == "integer" else round(v, 3)
        elif f.get("type") == "boolean":
            out[name] = bool(h % 2)
        elif f.get("type") == "array":
            out[name] = [f"(dry) step {j + 1}" for j in range(1 + h % 3)]
        else:
            out[name] = f"(dry) {name} {h % 1000}"
    return out


def _ask(backend, model, system, history, message, schema, cfg) -> tuple:
    from charter import llm
    attempts = []
    if backend == "api" and history:
        user = llm.Turn(message, history=history, fallback=llm.flatten(history + [message]))
    else:
        user = llm.flatten(history + [message]) if history else message
    out, reasoning, usage = llm.call(backend, model, system, user, schema, thinking_budget=int(cfg.get("thinking_budget") or 0),
                                     max_tokens=int(cfg.get("interview_max_tokens") or 2000), attempts=attempts)
    raw = attempts[-1].get("raw") if attempts else None
    return out, raw, reasoning, usage or {}, attempts


def new_id(rnd, at) -> str:
    return time.strftime("%Y-%m-%dT%H-%M-%S") + f"_r{int(rnd)}_{at}_" + hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:6]


def interview(run_dir, round, agents=None, questions=(), n: int = 1, model=None, response_schema=None, framing="private",
              backend=None, at: str = "end", out=None, dry: bool = False, id=None, log=print, ctxs=None, parallel: int = 8) -> dict:
    """Ask each agent each question n times in character at round `round` (0-based; see the module docstring). model: None = each
    agent's own model then. response_schema: see json_schema (a question may carry its own "schema" and "framing"). backend: None
    = LLM_BACKEND (api, claude_code). out: the store directory (default <run>/interviews). dry: scripted answers, no model.
    Returns {"id", "path", "rows", "meta"}; the rows are also written to <out>/<id>.jsonl."""
    from charter import llm
    run = Path(run_dir).resolve()
    log = log or (lambda *a: None)
    qs = _questions(questions)
    n = int(n)
    if n < 1:
        raise ValueError("n must be at least 1")
    inst = json.loads((run / "instance.json").read_text())
    cfg = dict(inst["spec"].get("llm") or {})
    t0 = time.time()
    ctxs = ctxs if ctxs is not None else contexts(run, round, agents, at)
    est = estimate(ctxs, qs, n, model)
    be = backend or llm.backend()
    if dry:
        be = "dry"
    log(f"interview of {run.name} at the {at} of round {int(round)} (0-based): {len(ctxs)} agent(s) x {len(qs)} question(s) x {n} "
        f"= {est['calls']} call(s), ~{est['input_tokens']:,} input tokens; estimated "
        + ("$0 (dry: no model)" if dry else f"${est['usd']:.4f} at API list prices (no cache)"
           + (f"; no price for {', '.join(est['unpriced_models'])}" if est["unpriced_models"] else "")
           + ("; the claude_code backend bills the subscription" if be == "claude_code" else "")))
    for a, c in ctxs.items():
        if not c.exact:
            log(f"  NOTE {a}: the rebuilt context does not match the recorded prompts everywhere (the run's code differs?)")
    iid = id or new_id(round, at)
    store = Path(out) if out is not None else run / DIR
    store.mkdir(parents=True, exist_ok=True)
    rows_f, prompts_f = store / f"{iid}.jsonl", store / f"{iid}.prompts.jsonl"
    if rows_f.exists():
        raise FileExistsError(f"{rows_f} exists: choose another id")
    run_id = (PV.read(run) or {}).get("run_id") or run.name
    jobs, prompts = [], {}
    for aid, c in ctxs.items():
        for q in qs:
            schema = json_schema(q.get("schema", response_schema))
            fr = q.get("framing", framing)
            msg, hist = interview_message(c, q["text"], schema, fr)
            text = prompt_text(c.system, hist, msg)
            psha = PV.sha(text)
            prompts.setdefault(psha, {"prompt_sha": psha, "system_sha": PV.sha(c.system), "system": c.system, "messages": hist,
                                      "message": msg})
            m = model or c.model
            backend_q = be if dry else ((cfg.get("backend_overrides") or {}).get(m, be) if backend is None else be)
            for i in range(n):
                jobs.append(dict(aid=aid, c=c, q=q, schema=schema, framing=fr, msg=msg, hist=hist, psha=psha, model=m,
                                 backend=backend_q, sample=i))
    stop = {"why": None}
    lock = threading.Lock()

    def one(j):
        if stop["why"] is None and not dry:
            why = llm.usage_stop(cfg)
            if why:
                with lock:
                    stop["why"] = why
        if stop["why"] is not None:
            return None
        if dry:
            parsed_raw = _dry_answer(j["schema"], f"{run_id}|{j['aid']}|{j['q']['id']}|{j['psha']}|{j['sample']}")
            out_, raw, reasoning, usage, attempts = parsed_raw, json.dumps(parsed_raw), "(dry: no model)", {}, []
        else:
            out_, raw, reasoning, usage, attempts = _ask(j["backend"], j["model"], j["c"].system, j["hist"], j["msg"], j["schema"], cfg)
        clean, valid, problems = validate(out_, j["schema"])
        return {"interview_id": iid, "run_id": run_id, "round": int(round), "at": at, "agent": j["aid"], "model": j["model"],
                "backend": j["backend"], "question_id": j["q"]["id"], "question": j["q"]["text"],
                "framing": j["framing"] if j["framing"] in FRAMINGS else "custom", "schema": j["schema"], "sample": j["sample"],
                "raw": raw, "parsed": clean, "answer": None if clean is None else clean.get("answer"), "valid": valid,
                "problems": problems, "error": (out_ or {}).get("_error") if isinstance(out_, dict) else None,
                "reasoning": reasoning, "usage": usage, **_cost(usage, j["model"]),
                "n_attempts": len(attempts) if attempts else (0 if dry else None), "prompt_sha": j["psha"],
                "system_sha": PV.sha(j["c"].system), "context_exact": j["c"].exact, "context_calls": len(j["c"].calls),
                "dry": bool(dry), "ts": builtins.round(time.time(), 3)}

    if dry or parallel <= 1 or len(jobs) == 1:
        rows = [one(j) for j in jobs]
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=int(parallel)) as ex:
            rows = list(ex.map(one, jobs))
    rows = [r for r in rows if r is not None]
    with open(prompts_f, "w") as f:
        for p in prompts.values():
            f.write(json.dumps(p) + "\n")
    with open(rows_f, "w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    cost = [r["cost_usd"] for r in rows if isinstance(r.get("cost_usd"), (int, float))]
    meta = {"id": iid, "run": str(run), "run_id": run_id, "round": int(round), "at": at, "agents": list(ctxs),
            "questions": qs, "n": n, "model": model, "backend": be, "framing": framing if framing in FRAMINGS else framing_text(framing),
            "response_schema": json_schema(response_schema), "dry": bool(dry), "estimate": est, "asked": len(rows),
            "planned": len(jobs), "stopped": stop["why"], "valid": sum(1 for r in rows if r["valid"]),
            "cost_usd": builtins.round(sum(cost), 6) if cost else None, "seconds": builtins.round(time.time() - t0, 1),
            "contexts": {a: {"model": c.model, "mode": c.mode, "exact": c.exact, "calls": c.calls, "base_checkpoint": c.base_checkpoint,
                             "notes": c.notes, "messages": len(c.messages)} for a, c in ctxs.items()},
            "code": {"git": PV.git_info().get("sha"), "interview_module": PV.sha(Path(__file__).read_bytes())},
            "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (store / f"{iid}.json").write_text(json.dumps(meta, indent=1, default=str))
    if stop["why"]:
        log(f"  STOPPED after {len(rows)} of {len(jobs)} call(s): {stop['why']}")
    log(f"  {len(rows)} answer(s), {meta['valid']} valid -> {rows_f}")
    return {"id": iid, "path": str(rows_f), "rows": rows, "meta": meta}


# ------------------------------------------------------------------ reading results; the scoring hook
def load(run_dir=None, store=None) -> list:
    """Every interview row stored for a run (<run>/interviews/*.jsonl, or `store`)."""
    d = Path(store) if store is not None else Path(run_dir) / DIR
    rows = []
    for p in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        if p.name.endswith(".prompts.jsonl"):
            continue
        rows += [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    return rows


def is_yes(parsed) -> bool:
    return isinstance(parsed, dict) and str(parsed.get("answer", "")).strip().lower() in ("yes", "y", "true")


def interview_share(run_dir, round, question, agents=None, predicate=None, *, at: str = "end", ask: bool = False, n: int = 1,
                    response_schema="yes_no_conf", store=None, **kw) -> dict | None:
    """The share of answers to `question` at round `round` (0-based) for which predicate(parsed answer) holds (default: answer
    "yes"), from the interviews already stored for the run; ask=True runs the interview (n samples each, **kw to interview) when
    none is stored. Returns None when nothing is stored and ask is false, else
      {share (over valid samples), agent_share (agents whose majority satisfies it), satisfied, samples, invalid, agents,
       samples_per_agent, by_agent: {agent: share}, interviews: [ids]}."""
    pred = predicate or is_yes
    want = None if agents is None else {str(a) for a in agents}

    def pick(rows):
        return [r for r in rows if r.get("round") == int(round) and r.get("at", "end") == at and r.get("question") == str(question).strip()
                and (want is None or r.get("agent") in want)]
    rows = pick(load(run_dir, store))
    if not rows and ask:
        res = interview(run_dir, round, agents=agents, questions=[question], n=n, response_schema=response_schema, at=at,
                        out=store, **kw)
        rows = pick(res["rows"])
    if not rows:
        return None
    valid = [r for r in rows if r.get("valid")]
    by: dict = {}
    for r in valid:
        by.setdefault(r["agent"], []).append(bool(pred(r.get("parsed"))))
    sat = sum(sum(v) for v in by.values())
    return {"share": sat / len(valid) if valid else None, "satisfied": sat, "samples": len(valid), "invalid": len(rows) - len(valid),
            "agents": len(by), "agent_share": (sum(1 for v in by.values() if sum(v) * 2 > len(v)) / len(by)) if by else None,
            "samples_per_agent": {a: len(v) for a, v in sorted(by.items())},
            "by_agent": {a: sum(v) / len(v) for a, v in sorted(by.items())},
            "interviews": sorted({r["interview_id"] for r in rows})}


# ------------------------------------------------------------------ command line
def add_command(sub) -> None:
    p = sub.add_parser("interview", help="ask agents a question in character at a round, with their exact context (docs/interview.md)")
    p.add_argument("run")
    p.add_argument("--round", type=int, required=True, help="round, 0-based (the agents saw it as Round N+1)")
    p.add_argument("--at", choices=ATS, default="end", help="end: after the agent's last call of the round (default); start: "
                   "before its decide call")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--agents", default=None, help="comma-separated agent ids")
    g.add_argument("--all-alive", action="store_true", help="every agent with a turn in the round (the default)")
    p.add_argument("--question", action="append", default=[], help="a question (repeatable)")
    p.add_argument("--questions", default=None, help="a YAML/JSON file: a list of questions (strings or {id, text, schema, framing})")
    p.add_argument("--n", type=int, default=1, help="samples per agent and question")
    p.add_argument("--schema", default=None, help=f"reply schema: {', '.join(SCHEMAS)}, or JSON (shorthand or a JSON schema)")
    p.add_argument("--framing", default="private", help="private (default), public, none, or the text of a preamble")
    p.add_argument("--model", default=None, help="default: each agent's own model")
    p.add_argument("--backend", choices=["api", "claude_code"], default=None, help="default: LLM_BACKEND")
    p.add_argument("--out", default=None, help="store directory (default RUN/interviews)")
    p.add_argument("--id", default=None, help="interview id (default: time, round and a short hash)")
    p.add_argument("--dry", action="store_true", help="scripted answers, no model (tests, checking prompts)")
    p.add_argument("--estimate", action="store_true", help="rebuild the contexts, print the cost estimate and stop")
    p.add_argument("--show-context", action="store_true", help="print each interview prompt's last messages before asking")
    p.set_defaults(fn=cmd)


def cmd(a) -> None:
    qs = list(a.question)
    if a.questions:
        qs += questions_file(a.questions)
    if not qs:
        raise SystemExit("give --question or --questions")
    agents = [x.strip() for x in a.agents.split(",") if x.strip()] if a.agents else None
    try:
        ctxs = contexts(a.run, a.round, agents, a.at)
    except ValueError as e:
        raise SystemExit(f"interview: {e}")
    qn = _questions(qs)
    schema = json_schema(a.schema)
    if a.show_context:
        for aid, c in ctxs.items():
            msg, hist = interview_message(c, qn[0]["text"], json_schema(qn[0].get("schema", a.schema)), qn[0].get("framing", a.framing))
            print(f"===== {aid} ({c.model}; {c.mode}; {len(hist)} earlier message(s); exact={c.exact})")
            if hist:
                print("..." + hist[-1][-1500:])
            print("----- interview message\n" + msg)
    if a.estimate:
        e = estimate(ctxs, qn, a.n, a.model)
        print(json.dumps(e, indent=1))
        return
    res = interview(a.run, a.round, agents, qs, n=a.n, model=a.model, response_schema=schema, framing=a.framing, backend=a.backend,
                    at=a.at, out=a.out, dry=a.dry, id=a.id, ctxs=ctxs)
    for r in res["rows"]:
        ans = r["parsed"] if r["parsed"] is not None else r["error"]
        print(f"{r['agent']:>8} {r['question_id']} #{r['sample']}: {json.dumps(ans)[:300]}")
    print(f"-> {res['path']}")
