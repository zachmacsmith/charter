"""History mode (review 20 §4; spec `context.history`, on by default wherever the context module is on).

Each agent's prompt is a conversation that restarts every `chunk` rounds (C, default 3), at rounds staggered across agents by a
stable per-agent offset. A conversation's first user message carries the agent's past on a gradient:

  Long memories      salient items from any time (deaths of close contacts, attacks, kin, open deals, laws), one line each
  beyond             "You no longer remember rounds 1-K in detail; use recall {"round": N}"
  summary band       B rounds (summary_rounds, default 12) as one line each: who it exchanged messages with and about what, what it
                     did, what happened to it
  full band          F rounds (F = the agent's own memory_turns draw, 2-5) in full: what it saw (its feed), every private message
                     of the round in order per counterpart (context.round_exchange), the lookups it made, what it did and the results

then the round itself and the ending (state, scratchpad, what to do now). Every later call in the chunk is appended: the agent's
replies stay in place, a DM reply is a short delta (agents.DMDelta), and the next round's message brings the results of the last
round's actions, the round's whole private exchange and what happened since. So the full band runs F, F+1, F+2 within a chunk
(F .. F+C-1) and drops back to F at the next restart.

Records: after each round the runner writes one row per agent that had a turn to <run>/memory.jsonl (provenance.APPEND_ONLY, cut
back with the other logs on resume): the texts the agent was shown (feed, exchange, lookups, actions, results) and the summary
line and notable items computed then, so nothing is re-rendered later from a changed world. `recall {"round": N}` returns a row's
full rendering (never the agent's reasoning: it is not recorded here).

The system prompt is frozen for the chunk (a byte change would invalidate the conversation's cache); actions gained or lost since
the conversation started are listed in "What to do now". A resume or fork starts every agent's conversation afresh at its first
round (run.json `history_restarts`).

Transport (agents.LLMPolicy): the API backend sends the messages with cache breakpoints on the previous turn's last block and the
new message; the CLI backend keeps one `claude -p` session per chunk (llm.Sessions: --session-id, then --resume with only the new
message) when llm.sessions_available(), and otherwise sends the whole conversation as one prompt (flattened, uncached; logged once
per run). Each call records which (usage["history"]: cached-session, api-messages, flattened).
"""
from __future__ import annotations

import json
import zlib
from pathlib import Path

from charter import context as CX

FILE = "memory.jsonl"
HISTORY_HEADER = "# Your memory"


# ------------------------------------------------------------------ settings and facts
def hcfg(x) -> dict:
    """context.history merged over its defaults (a spec may set a part of it, or true/false)."""
    d = CX.DEFAULTS["history"]
    got = CX.cfg(x).get("history")
    got = {"enabled": got} if isinstance(got, bool) else dict(got or {})
    out = {**d, **got}
    out["salience"] = {**d["salience"], **(got.get("salience") or {})}
    return out


def on(x) -> bool:
    """History mode is on: the context module is on and context.history.enabled (x: a kernel, an instance or a spec)."""
    return x is not None and CX.enabled(x) and bool(hcfg(x)["enabled"])


def _inst(x) -> dict:
    return x.inst if hasattr(x, "inst") else x


def _draw(inst, aid, what, n) -> int:
    """A stable per-agent number in 0..n-1 (no RNG stream: instances and runs are unchanged by it)."""
    return zlib.crc32(f"{inst.get('seed')}|history|{what}|{aid}".encode()) % max(1, int(n))


def summary_rounds(inst, aid) -> int:
    h = hcfg(inst)
    spread = max(0, int(h["summary_spread"]))
    return max(0, int(h["summary_rounds"]) + (_draw(inst, aid, "summary", 2 * spread + 1) - spread if spread else 0))


def facts(x, aid) -> dict:
    """The numbers the renderer and the agent-facing text both use: full (F, the agent's memory_turns), full_max (F + C - 1),
    summary (B), chunk (C), offset (its stagger)."""
    inst = _inst(x)
    h = hcfg(inst)
    rec = next((a for a in inst.get("agents", []) if a.get("id") == aid), {})
    f = int(rec.get("memory_turns") or CX.cfg(inst)["recent_turns"])
    c = max(1, int(h["chunk"]))
    return {"full": f, "full_max": f + c - 1, "summary": summary_rounds(inst, aid), "chunk": c,
            "offset": _draw(inst, aid, "chunk", c) if h["stagger"] else 0}


# ------------------------------------------------------------------ the store (rows of memory.jsonl, on the kernel)
class Store:
    """Per-agent round records, the frozen system prompts and the round's pending rows. Lives on the kernel (k._history), not in
    k.w, so checkpoints stay small: memory.jsonl is the durable copy (loaded back on resume)."""

    def __init__(self, out=None, segment_start: int = 0):
        self.out = Path(out) if out is not None else None
        self.segment_start = int(segment_start)
        self.rows: dict = {}                                            # aid -> {round: row}
        self.pending: dict = {}                                         # aid -> the current round's row, filled during the round
        self.first: dict = {}                                           # aid -> its first round with a history turn (this segment)
        self.frozen: dict = {}                                          # aid -> {"chunk", "system", "actions"}
        self.built: dict = {}                                           # aid -> round its round message was built
        self._f = None
        if self.out is not None and (self.out / FILE).exists():
            for ln in (self.out / FILE).read_text().splitlines():
                if ln.strip():
                    row = json.loads(ln)
                    self.rows.setdefault(row["agent"], {})[int(row["round"])] = row

    def write(self, row: dict) -> None:
        self.rows.setdefault(row["agent"], {})[int(row["round"])] = row
        if self.out is not None:
            if self._f is None:
                self._f = open(self.out / FILE, "a")
            self._f.write(json.dumps(row, sort_keys=True) + "\n")

    def flush(self) -> None:
        if self._f is not None:
            self._f.flush()

    def close(self) -> None:
        if self._f is not None:
            self._f.close()
            self._f = None


def store(k) -> Store:
    st = k.__dict__.get("_history")
    if st is None:
        st = k.__dict__["_history"] = Store()
    return st


def attach(k, out, first_round: int) -> Store:
    """runner: the run's store (memory.jsonl, already cut back to the checkpoint on a resume); first_round > 0: a resume or a fork,
    where every agent's conversation starts afresh."""
    st = Store(out, first_round)
    k.__dict__["_history"] = st
    return st


# ------------------------------------------------------------------ the chunk schedule
def chunk_start(k, aid, r=None) -> int:
    """The round the agent's current conversation started: the latest of its last scheduled restart ((round + offset) % C == 0),
    the segment's first round (a resume or fork restarts every conversation) and the agent's first turn."""
    r = k.r if r is None else r
    f = facts(k, aid)
    st = store(k)
    s = r - ((r + f["offset"]) % f["chunk"])
    return max(s, st.segment_start, st.first.get(aid, r))


def next_start(k, aid, after: int) -> int:
    """The first scheduled restart after round `after`."""
    f = facts(k, aid)
    b = after + 1
    while (b + f["offset"]) % f["chunk"]:
        b += 1
    return b


def bands(k, aid, s) -> dict:
    """Round ranges (0-based, half-open) for a conversation starting at round s: full [s-F, s), summary [s-F-B, s-F), beyond [0, s-F-B)."""
    f = facts(k, aid)
    full0 = max(0, s - f["full"])
    sum0 = max(0, full0 - f["summary"])
    return {"full": (full0, s), "summary": (sum0, full0), "beyond": (0, sum0)}


# ------------------------------------------------------------------ rendering a recorded round
def render_round(row: dict, budget: int | None = None) -> str:
    """A round as it is shown in the full band and by recall: what the agent saw, its private messages, its lookups, what it did
    and the results. Never its reasoning."""
    n = int(row["round"]) + 1
    parts = [f"### Round {n}", "What you saw at the start of the round:\n" + (row.get("saw") or "(nothing new)")]
    if row.get("exchange"):
        parts.append("Your private messages this round (every message you received and sent, in order):\n" + row["exchange"])
    if row.get("lookups"):
        parts.append("Lookups answered before you acted:\n" + "\n".join(row["lookups"]))
    acts = row.get("actions") or []
    parts.append("What you did: " + ("; ".join(acts) if acts else "(no actions)"))
    res = row.get("results") or []
    parts.append("Results:\n" + ("\n".join("  " + str(x) for x in res) if res else "  (none)"))
    text = "\n".join(parts)
    if budget:
        text = CX.clip(text, int(budget), f'...(cut: recall {{"round": {n}}} shows this round alone)')[0]
    return text


def recall(k, aid, args) -> str:
    """The recall lookup: round N (1-based, as the agent sees rounds) in full, as its full band showed it."""
    if not on(k) or not hcfg(k)["recall"]:
        raise CX._error("unknown lookup 'recall'")
    args = args if isinstance(args, dict) else {}
    v = args.get("round", args.get("r", next((x for x in args.values() if isinstance(x, (int, str))), None)))
    try:
        n = int(str(v).strip().lstrip("rR"))
    except (TypeError, ValueError):
        raise CX._error('give a round number: recall {"round": N}') from None
    if n < 1 or n > k.r:
        raise CX._error(f"round {n} is not a past round (this is round {k.r + 1})")
    row = store(k).rows.get(aid, {}).get(n - 1)
    if row is None:
        return f"Round {n}: you had no turn in that round."
    return "Recalled:\n" + render_round(row)


# ------------------------------------------------------------------ the record of a round (written at its end)
def note_saw(k, aid, feed: str) -> None:
    store(k).pending.setdefault(aid, {"round": k.r, "agent": aid, "lookups": []})["saw"] = feed


def note_lookup(k, aid, text: str) -> None:
    """A lookup answered in the DM step (context.dm_step_lookup): part of what the agent saw this round."""
    if on(k):
        store(k).pending.setdefault(aid, {"round": k.r, "agent": aid, "lookups": []})["lookups"].append(str(text))


def note_turn(k, aid, acts: list, results: list) -> None:
    """runner.execute: what the agent did this round and the results, in full."""
    if not on(k):
        return
    row = store(k).pending.setdefault(aid, {"round": k.r, "agent": aid, "lookups": []})
    row["actions"] = [f"{x.get('action')} {x.get('args_json', '')}" for x in acts]
    row["results"] = [str(x) for x in results]


def end_round(k) -> None:
    """runner, after the round's last event: complete each pending row (the round's private exchange, the summary line, the
    notable items) and write it."""
    if not on(k):
        return
    st = store(k)
    for aid in sorted(st.pending):
        row = st.pending[aid]
        r = int(row["round"])
        row.setdefault("saw", "(nothing new)")
        row.setdefault("actions", [])
        row.setdefault("results", [])
        row["exchange"] = CX.round_exchange(k, aid, r)
        row["partners"] = _partners(k, aid, r)
        row["notable"] = _notable(k, aid, r)
        row["line"] = summary_line(row)
        st.write(row)
    st.pending.clear()
    st.flush()


def _partners(k, aid, r) -> dict:
    """{counterpart: [messages exchanged, what the first one said]} for round r (the names the agent saw)."""
    out: dict = {}
    for e in CX.exchange_events(k, aid, r):
        d = e["data"] or {}
        who = (d.get("shown_to") or d.get("to")) if e["agent"] == aid else (d.get("shown_as") or e["agent"])
        if who not in out:
            from charter import agents as AG
            s = AG.render_event(k, e, aid) or ""
            said = s.split(": ", 1)[1] if ": " in s else ""
            words = said.split()
            out[who] = [0, " ".join(words[:8]) + ("..." if len(words) > 8 else "")]
        out[who][0] += 1
    return out


def _names(d) -> set:
    out = set()
    for v in (d or {}).values():
        if isinstance(v, str):
            out.add(v)
        elif isinstance(v, (list, tuple)):
            out |= {x for x in v if isinstance(x, str)}
    return out


DEALS = ("transfer", "loan_offer", "loan_active", "loan_repaid", "loan_defaulted", "loan_forgiven", "contract_joined",
         "contract_admitted", "contract_expelled", "contract_breach", "contract_dissolved")
LAWS = ("enact", "repeal", "jur_declared")


def _notable(k, aid, r) -> list:
    """Round r's events that may outlive the summary band (§4.3): {kind, who, text}. Kinds: death, attack, kin, deal, law."""
    import bisect
    from charter import agents as AG
    ev = k.events
    i = bisect.bisect_left(ev, r, key=lambda e: e.get("round") if e.get("round") is not None else -1)
    out = []
    for e in ev[i:]:
        if e.get("round") != r:
            break
        t, d = e["type"], e["data"] or {}
        kind = who = None
        if t == "disabled":
            who = d.get("agent")
            kind = "attack" if d.get("by") == aid else "death" if who != aid else None
        elif t == "attack_failed" and aid in (d.get("attacker"), d.get("target")):
            kind, who = "attack", d.get("target") if d.get("attacker") == aid else d.get("attacker")
        elif t == "birth" and aid in _names(d) | {e["agent"]}:
            kind, who = "kin", d.get("agent") or d.get("child")
        elif t in DEALS and e["agent"] != aid and aid in _names(d):
            kind, who = "deal", e["agent"]
        elif t in LAWS:
            kind = "law"
        if kind is None or not k.can_see(aid, e):
            continue
        s = AG.render_event(k, e, aid)
        if s:
            s = s.split("] ", 1)[1] if s.startswith("[") and "] " in s else s
            out.append({"kind": kind, "who": who, "text": CX.clip(s.replace("\n", " "), 40, "...")[0]})
    return out


def _act_brief(a: str) -> str:
    name, _, args = a.partition(" ")
    try:
        d = json.loads(args) if args.strip() else {}
    except json.JSONDecodeError:
        d = {}
    key = next((d[x] for x in ("camp", "to", "target", "law", "ballot", "channel", "name", "query", "section", "round", "item")
                if isinstance(d, dict) and isinstance(d.get(x), (str, int))), None)
    return f"{name} {key}" if key is not None else name


def summary_line(row: dict) -> str:
    """One line for a round: what it did, who it exchanged messages with and about what, what happened to it."""
    acts = [_act_brief(a) for a in row.get("actions") or []]
    seen, did = {}, []
    for a in acts:
        seen[a] = seen.get(a, 0) + 1
    did = [a + (f" x{n}" if n > 1 else "") for a, n in seen.items()]
    failed = sum(1 for x in row.get("results") or [] if ": ERROR" in str(x).split("\n", 1)[0])
    parts = ["you did " + (", ".join(did) if did else "nothing") + (f" ({failed} failed)" if failed else "")]
    p = row.get("partners") or {}
    if p:
        parts.append("messages with " + "; ".join(f"{who} ({n}" + (f', "{about}"' if about else "") + ")"
                                                for who, (n, about) in p.items()))
    nb = row.get("notable") or []
    if nb:
        parts.append("seen: " + "; ".join(x["text"] for x in nb[:3]) + (f" (+{len(nb) - 3} more)" if len(nb) > 3 else ""))
    return f"Round {int(row['round']) + 1}: " + "; ".join(parts) + "."


# ------------------------------------------------------------------ the history block (a conversation's opening)
def long_memories(k, aid, s) -> list:
    """Lines kept beyond the summary band, by salience (§4.3): each kind's rounds past the band (null: for good); a death is kept
    for good when the agent exchanged close_messages or more messages with the dead."""
    h = hcfg(k)
    sal = h["salience"]
    rows = store(k).rows.get(aid, {})
    b0 = bands(k, aid, s)["beyond"][1]
    talk: dict = {}
    for q, row in rows.items():
        if q < s:
            for who, (n, _) in (row.get("partners") or {}).items():
                talk[who] = talk.get(who, 0) + int(n)
    out = []
    for q in sorted(x for x in rows if x < b0):
        for it in rows[q].get("notable") or []:
            kind = it["kind"]
            if kind == "death" and talk.get(it.get("who"), 0) >= int(sal["close_messages"] or 0) and talk.get(it.get("who"), 0):
                kind = "death_close"
            ttl = sal.get(kind)
            if ttl is not None and b0 - 1 - q >= int(ttl):               # left the summary band ttl or more rounds ago
                continue
            extra = f" You exchanged {talk[it['who']]} messages with them." if kind == "death_close" else ""
            out.append(f"- r{q + 1}: {it['text']}{extra}")
    cap = int(h["long_items"])
    return out[-cap:] if cap > 0 else []


def history_block(k, aid, s) -> tuple[str, dict]:
    """The past as of round s (the conversation's start): (text, record of the band sizes)."""
    h = hcfg(k)
    rows = store(k).rows.get(aid, {})
    bd = bands(k, aid, s)
    full = [rows[q] for q in range(*bd["full"]) if q in rows]
    summ = [rows[q] for q in range(*bd["summary"]) if q in rows]
    beyond = bd["beyond"][1]
    longm = long_memories(k, aid, s)
    parts = [f"{HISTORY_HEADER} (as of round {s + 1}; older rounds come first)"]
    if longm:
        parts.append("## Long memories\n" + "\n".join(longm))
    if beyond > 0:
        parts.append(f"You no longer remember rounds 1-{beyond} in detail; use recall {{\"round\": N}} to see what you saw and did "
                     "in round N.")
    if summ:
        parts.append(f"## Rounds {int(summ[0]['round']) + 1}-{int(summ[-1]['round']) + 1}, one line each\n"
                     + "\n".join(r["line"] for r in summ))
    if full:
        parts.append(f"## Rounds {int(full[0]['round']) + 1}-{int(full[-1]['round']) + 1} in full\n"
                     + "\n\n".join(render_round(r, h["round_budget"]) for r in full))
    if len(parts) == 1:
        parts.append("(nothing yet: this is your first round)")
    rec = {"chunk_start": s + 1, "full": len(full), "summary": len(summ), "beyond": beyond, "long": len(longm)}
    return "\n\n".join(parts), rec


def counts(k, aid, s, r) -> dict:
    """Band sizes at round r of a conversation that started at s: full = the rounds in full (the opening's plus those appended
    since), summary = one-line rounds, beyond = rounds left to recall, long = long-memory lines."""
    rows = store(k).rows.get(aid, {})
    bd = bands(k, aid, s)
    return {"chunk_start": s + 1, "full": sum(1 for q in range(bd["full"][0], r) if q in rows),
            "summary": sum(1 for q in range(*bd["summary"]) if q in rows), "beyond": bd["beyond"][1],
            "long": len(long_memories(k, aid, s))}


# ------------------------------------------------------------------ the round message
class HistoryTurn(str):
    """A history-mode user message. The string is the new message (what the scripted bots and the recorder see); chunk: the
    conversation's id (agent, first round); starts: it opens the conversation (the string then holds the whole opening);
    restart: a self-contained message for this round (history block + round), sent when the policy has no conversation to
    continue."""

    def __new__(cls, text, chunk, starts, restart=None):
        s = super().__new__(cls, text)
        s.chunk, s.starts = tuple(chunk), bool(starts)
        s.restart = str(text) if starts or restart is None else str(restart)
        return s

    def extend(self, extra: str) -> "HistoryTurn":
        """The same message with text added at the end (roles: the Spy's private section)."""
        return HistoryTurn(str(self) + extra, self.chunk, self.starts, None if self.starts else self.restart + extra)


def system(k, a, core: str) -> str:
    """runner.prepare: the system prompt, frozen for the agent's conversation (rebuilt when one starts)."""
    aid = a["id"]
    st = store(k)
    s = _begin(k, aid)
    fz = st.frozen.get(aid)
    if fz is None or fz["chunk"] != s:
        rights = k.w["agents"][aid]["rights"] if aid in k.w["agents"] else a.get("rights", [])
        st.frozen[aid] = fz = {"chunk": s, "system": core, "actions": CX.allowed_actions(k.inst, a, rights, k)}
    return fz["system"]


def _begin(k, aid) -> int:
    st = store(k)
    st.first.setdefault(aid, k.r)
    return chunk_start(k, aid)


def _new_since(k, a) -> str:
    """Actions gained or lost since the conversation's system prompt was frozen."""
    fz = store(k).frozen.get(a["id"])
    if not fz:
        return ""
    rights = k.w["agents"][a["id"]]["rights"] if a["id"] in k.w["agents"] else a.get("rights", [])
    now = CX.allowed_actions(k.inst, a, rights, k)
    gained = [x for x in now if x not in fz["actions"]]
    lost = [x for x in fz["actions"] if x not in now]
    if not gained and not lost:
        return ""
    return ("New since this conversation started: " + "; ".join(x for x in (
        ("you may now use " + ", ".join(gained)) if gained else "", ("you can no longer use " + ", ".join(lost)) if lost else "") if x)
        + " (the manual has the details; your rules are refreshed when your memory is next updated).")


def reminder(k, aid) -> str:
    """The ending's memory line: when this round shrinks to one line and when it is gone, from the same schedule the renderer uses."""
    f = facts(k, aid)
    t = k.r
    s1 = next_start(k, aid, t)
    while s1 - f["full"] <= t:
        s1 = next_start(k, aid, s1)
    s2 = s1
    while s2 - f["full"] - f["summary"] <= t:
        s2 = next_start(k, aid, s2)
    return (f"Memory: in {s1 - t} rounds this round shrinks to one line, and in {s2 - t} rounds it is gone but for your long "
            "memories. recall can bring back what you saw, never what you thought. Before you finish, put your plan and your "
            "reasoning in your scratchpad: your strategy, what you promised and were promised, whom you trust and why.")


def what_to_do(k, a, n_actions, final) -> str:
    """"## What to do now": "Your situation" and "Before you act" merged, without the lines State already has."""
    from charter import agents as AG
    aid = a["id"]
    lim = k.dm_limit(aid)
    lines = [f"This turn: {n_actions} actions and {max(0, lim - k.w.get('dm_sent', {}).get(aid, 0))} private messages (of {lim} this "
             f"round{AG.dm_source(k, aid)})."]
    lines += [x for x in CX.situation_lines(k, a, n_actions)[1:] if not x.startswith(("Your lifespan", "You hold"))]
    new = _new_since(k, a)
    if new:
        lines.append(new)
    lines.append(f"Your goal: {CX._short_goal(a, True)}")
    lines.append(f"Use this turn for it. Any of your {n_actions} actions you do not use are wasted, and so are unused messages. Think "
                 "strategically: what would move your score most from here? If you have no plan, make one and write it down. If you "
                 "don't know what to do, explore: actions you have not tried (your edge first), your manual, the world and other "
                 "agents (Scientists hold knowledge), better routes to your goal; coordinate, bargain and trade.")
    lines.append(reminder(k, aid))
    if final:
        lines.append("This is the final round: whatever you leave undone now will not count.")
    return "## What to do now\n" + "\n".join(lines)


def turn(k, a: dict, order: list, since: int, n_actions: int, final: bool, simultaneous: bool = False) -> tuple:
    """The history-mode turn message: (HistoryTurn, cursor). Also stores the layer record for reasoning.jsonl."""
    aid, c = a["id"], CX.cfg(k)
    b = c["budgets"]
    CX.init_agent(k, aid)
    st, cx = store(k), CX._st(k, aid)
    s = _begin(k, aid)
    fetched = cx["fetched"].get(aid)
    if st.built.get(aid) == k.r and fetched is not None:                 # the lookup phase's second call: a continuation
        got = [f"{x['name']} {json.dumps(x['args'])}:\n{x['text']}" for x in fetched]
        text = (CX.FETCHED_HEADER + "\n" + "\n\n".join(got) + "\n\nYour free lookups for this turn are used: reply with your actions "
                "now (\"lookups\" is ignored; a further lookup costs an action: put it in \"actions\").")
        st.pending.setdefault(aid, {"round": k.r, "agent": aid, "lookups": []})["lookups"] += got
        rec = dict(cx["layers"].get(aid) or {})
        rec["history"] = {**rec.get("history", {}), "message": "lookups"}
        cx["layers"][aid] = rec
        return HistoryTurn(text, (aid, s), False, text), len(k.events)
    starts = s == k.r
    rec = {}
    state, rec["state"] = CX.state_layer(k, a, order, n_actions, simultaneous, int(b["state"]))
    shown = {e["id"] for e in CX.exchange_events(k, aid, k.r - 1)} if k.r > 0 else set()
    feed, cursor, rec["feed"] = CX.feed_layer(k, aid, since, int(b["feed"]), shown)
    note_saw(k, aid, feed)
    st.built[aid] = k.r
    last = st.rows.get(aid, {}).get(k.r - 1)
    middle = []                                                          # continuing: last round's results and private messages
    if last is not None:
        middle.append(f"## Results of your round {k.r} actions\nWhat you did: " + ("; ".join(last.get("actions") or []) or "(no actions)")
                      + "\n" + ("\n".join("  " + str(x) for x in last.get("results") or []) or "  (no results)"))
        if last.get("exchange"):
            middle.append(f"## Your private messages in round {k.r} (every message you received and sent, in order)\n" + last["exchange"])
    now = [f"## What happened since your last turn\n{feed}"]
    if final:
        now.append("This is the final round. In goal_guesses_json, map each other agent to the goal name from the list that best fits "
                   "what they did.")
    pad, cut = CX.clip(k.w["scratchpad"][aid], CX.scratchpad_size(k, aid))
    rec["scratchpad"] = {"tokens": CX.tokens(pad), "budget": CX.scratchpad_size(k, aid), "trimmed": cut}
    end = [f"## State (round {k.r + 1})\n" + state,
           f"## Your scratchpad ({CX.tokens(pad)} of {CX.scratchpad_size(k, aid)} tokens)\n" + (pad or "(empty)")]
    from charter import media
    eds = list(media.editions_for(k, aid) or [])[:int(c["media_outlets"])]
    med = [CX.clip(x, int(b["media"]) + CX.tokens(x.split("\n", 1)[0]))[0] for x in eds]
    if med:
        end.append("## Media (written by other agents)\n" + "\n\n".join(med))
    pins = [(n, f) for n, f in sorted(k.w["files"][aid].items()) if f["pinned"]][:CX.pin_limit(k, aid)]
    pinned = [f"File {n} ({f['origin']}):\n" + CX.clip(f["text"], int(b["pinned"]))[0] for n, f in pins]
    if pinned:
        end.append("## Pinned files\n" + "\n\n".join(pinned))
    from charter import directories as DR
    dirs = DR.turn_section(k, aid) if DR.enabled(k) else ""
    if dirs:
        end.append("## Your directories\n" + dirs)
    if c["lookup_phase"] and int(c["free_lookups"]) > 0 and not c["lookups_in_dm_step"]:
        end.append(f"Act now, or first list up to {c['free_lookups']} free lookups in \"lookups\" (with \"actions\" empty) to be asked "
                   "again with their results.")
    if c.get("closing", True):
        end.append(what_to_do(k, a, n_actions, final))
    block, hrec = history_block(k, aid, k.r)                             # the opening as if the conversation started now
    head = f"# Round {k.r + 1} (now)"
    restart = "\n\n".join([block, head] + now + end)
    if starts:
        text = restart
    else:
        text = "\n\n".join([f"# Round {k.r + 1}"] + middle + now + end)
        hrec = counts(k, aid, s, k.r)
    hrec.update(message="start" if starts else "continue", tokens=CX.tokens(text), restart_tokens=CX.tokens(restart),
                round_in_chunk=k.r - s + 1)
    rec["history"] = hrec
    core = cx["core"].get(aid) or {}
    rec["core"] = core
    rec["total_tokens"] = CX.tokens(text) + int(core.get("tokens", 0))
    cx["layers"][aid] = rec
    return HistoryTurn(text, (aid, s), starts, restart), cursor


# ------------------------------------------------------------------ agent-facing text (review 20 §6.2)
def recall_cost(mode: str) -> str:
    if mode == "dm_step":
        return ("as a pre-action (in \"lookups\") it is answered this round, before you act, and uses one of your private-message "
                "slots; as an action it uses an action and is answered next turn")
    if mode == "free":
        return "as a free lookup it is answered before you act; as an action it uses an action and is answered next turn"
    return "it uses an action and is answered next turn"


def core_text(inst, f: dict) -> str:
    """The core prompt's Memory section in history mode (memory_text v2). F, C, B, S and the recall cost come from charter.facts,
    the numbers the renderer uses (memory.facts)."""
    full, top, summ, s = int(f["memory_turns"]), int(f["memory_turns"]) + int(f["history_chunk"]) - 1, int(f["history_summary"]), f["scratchpad"]
    roster = cfg_roster(inst)
    rec = hcfg(inst)["recall"]
    return ("Memory: each turn you see your history in order, in less detail the further back it is.\n"
            f"- The last {full} to {top} rounds in full: everything you saw (messages, posts, events), every private message you "
            "received and sent, and what you did, with the results.\n"
            f"- The {summ} rounds before that as one line each: who you exchanged messages with and about what, what you did, what "
            "happened to you. The text of messages and results is not kept.\n"
            "- Older rounds: only a short list of things you would not forget, such as the death of someone you dealt with, an attack "
            "on you, or a deal." + (" The People line in your state always says who is alive and who is gone." if roster else "") + "\n"
            + (f"recall {{\"round\": N}} shows what you saw and did in round N, in full: {recall_cost(f['lookup_mode'])}.\n" if rec else "")
            + "\nWhat no summary keeps is your thinking: why you acted, what you planned next, what you suspect. That lives only in your "
            f"scratchpad ({s} tokens, shown at the end of every turn). Use it as a notebook for thinking, not a log: your strategy and "
            "the reasons for it, your plan for the next rounds, what was promised to you and by you, who you trust or distrust and "
            "why, what you have learned. Rewrite it whenever your thinking changes."
            + ((" recall brings back what you saw, never what you thought.") if rec else "") + CX._free_write(inst))


def cfg_roster(inst) -> bool:
    return bool(CX.cfg(inst).get("roster"))


def turn_text(f: dict) -> str:
    """The manual's "How your turn works" first paragraph in history mode."""
    full, top, summ = int(f["memory_turns"]), int(f["memory_turns"]) + int(f["history_chunk"]) - 1, int(f["history_summary"])
    return (f"Your turns form a conversation that restarts every {f['history_chunk']} rounds. It opens with your memory: long "
            f"memories, then the older rounds as one line each ({summ} of them), then the last {full} rounds in full; each round "
            "after that is added as it happens (what happened, your private messages, the results of your actions), so the newest "
            f"{full} to {top} rounds are always in full. Every turn ends with your state, your scratchpad ({f['scratchpad']} tokens) "
            "and what to do now. recall {\"round\": N} brings back any past round in full; search_dms finds an old message.\n")


# ------------------------------------------------------------------ run records
def run_info(inst) -> dict:
    """run.json `history`: the settings in force (null when off)."""
    if not on(inst):
        return None
    h = hcfg(inst)
    return {"chunk": int(h["chunk"]), "stagger": bool(h["stagger"]), "summary_rounds": int(h["summary_rounds"]),
            "summary_spread": int(h["summary_spread"]), "recall": bool(h["recall"]), "full": "memory_turns"}
