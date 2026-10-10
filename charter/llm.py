"""One structured model call per agent turn, through LLM_BACKEND (.env at the repository root): "api" (ANTHROPIC_API_KEY) or "claude_code"
(headless `claude -p` billed to the subscription via CLAUDE_CODE_OAUTH_TOKEN, with every tool disabled, so nothing runs on the host).
Returns (parsed JSON dict, reasoning text, usage dict); pass `attempts=[]` to also get every attempt's raw text and error. Reasoning: API Sonnet/Opus give summarised thinking; through Claude Code only
models with a fixed thinking budget (Haiku 4.5) return thinking text (Sonnet/Opus 5.5 come back with the text omitted).
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

_client = None
log = logging.getLogger("charter.llm")


# ------------------------------------------------------------------ conversations (review 20 §4.5, §4.7)
def sessions_available() -> bool:
    """Whether `claude -p` sessions in a run-local config directory can authenticate: the one gate for every session user (the DM
    delta, history mode). Today: CLAUDE_CODE_OAUTH_TOKEN is set (a fresh CLAUDE_CONFIG_DIR holds no login). Change it here when the
    CLI is known to authenticate another way."""
    return bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))


REPLY_MARK = "[Your reply]"
NEXT_MARK = "[Next message]"


def flatten(texts) -> str:
    """A conversation as one prompt (history mode without sessions): the user and assistant texts in order, the agent's replies
    marked. One message is itself, so a conversation's first call is the same either way."""
    texts = [str(t) for t in texts]
    out = [texts[0]] if texts else []
    for i in range(1, len(texts)):
        out.append(f"{REPLY_MARK}\n{texts[i]}" if i % 2 else f"{NEXT_MARK}\n{texts[i]}")
    return "\n\n".join(out)


class Sessions:
    """Run-local `claude -p` sessions: CLAUDE_CONFIG_DIR points at a directory inside the run folder, so session files are kept
    there and never in the user's ~/.claude. A first call starts a session with `--session-id <uuid>`; a later call continues it
    with `--resume <uuid>` (a new user message, everything before it served from the session). Authentication must come from the
    environment (sessions_available: CLAUDE_CODE_OAUTH_TOKEN), since a fresh config directory holds no login; without it sessions
    are not used.
    Reusable by any conversation-shaped caller (the DM delta now, history mode later)."""
    DIRNAME = "claude_sessions"
    GIVE_UP = 3                                                       # session starts that failed while a plain retry worked

    def __init__(self, run_dir):
        self.root = Path(run_dir) / self.DIRNAME
        self.failures = 0
        self._lock = threading.Lock()

    @property
    def usable(self) -> bool:
        return sessions_available() and self.failures < self.GIVE_UP

    def env(self) -> dict:
        """Environment entries for a `claude -p` call that keeps or resumes a session here."""
        self.root.mkdir(parents=True, exist_ok=True)
        return {"CLAUDE_CONFIG_DIR": str(self.root)}

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def failed_start(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures == self.GIVE_UP:
                log.warning("claude -p sessions failed to start %d times while plain calls worked: sessions are off for this run "
                            "(DM replies use the full prompt)", self.GIVE_UP)

    def drop(self, sid) -> None:
        """Delete a finished session's files (best effort): a session only has to live until its conversation ends."""
        for p in self.root.glob(f"projects/*/{sid}.jsonl"):
            try:
                p.unlink()
            except OSError:
                pass


class Turn(str):
    """A user message in a conversation. The string is the new user message. history: the texts before it, alternating user and
    assistant ([] for the first message); fallback: the self-contained prompt to send instead when the conversation cannot be
    continued; sessions / session: the CLI's run-local sessions and this conversation's session id (resume when history is
    non-empty, start otherwise; None: no session). Being a str, it passes through every policy wrapper and mock backend as the new
    message itself, so records and replays stay deterministic."""

    def __new__(cls, text, history=(), fallback=None, sessions=None, session=None, mark_previous=False):
        s = super().__new__(cls, text)
        s.history, s.fallback, s.sessions, s.session = list(history), fallback, sessions, session
        s.mark_previous = mark_previous                          # API: a cache breakpoint on the previous turn's last block too
        return s

    @property
    def continues(self) -> bool:
        return bool(self.history)


_warned: set = set()


def _warn_once(what: str, msg: str) -> None:
    if what not in _warned:
        _warned.add(what)
        log.warning(msg)


def parse_json(text: str) -> dict:
    t = text.strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
        if m:
            t = m.group(1)
    i, j = t.find("{"), t.rfind("}")
    return json.loads(t[i:j + 1])


def backend() -> str:
    return (os.environ.get("LLM_BACKEND") or "api").strip().lower()


class CallError(RuntimeError):
    """A failed attempt that still got reply text back (kept in the attempt record)."""

    def __init__(self, msg, raw=None):
        super().__init__(msg)
        self.raw = raw


def call(backend_name, model, system, user, schema, thinking_budget=0, max_tokens=6000, retries=1, attempts=None):
    """attempts: an optional list that receives one record per attempt (backend, model, start time, latency, the raw reply text,
    the error of a failed attempt), so retries and failed attempts are not lost (provenance.Recorder writes them to calls.jsonl)."""
    """user: a str, or a Turn (a conversation): a Turn that continues one is tried once and, if that fails for any reason, the
    call is made again with its self-contained fallback prompt (usage["turn"]: "continued" or "fallback"); a Turn that starts one
    on the CLI keeps a session (usage["session"]), and a failed start is retried without one."""
    if isinstance(user, Turn) and user.continues:
        return _continue(backend_name, model, system, user, schema, thinking_budget, max_tokens, retries, attempts)
    last, session_failed = None, False
    for i in range(retries + 1):
        rec = {"attempt": i, "backend": backend_name, "model": model, "ts": round(time.time(), 3)}
        t0 = time.monotonic()
        raw = None
        if isinstance(user, Turn) and user.session and backend_name == "claude_code" and i > 0:
            session_failed = True                                # a session start failed: the retry keeps no session
            user = Turn(str(user), fallback=user.fallback, sessions=user.sessions)
        try:
            if backend_name == "claude_code":
                raw, parsed, reasoning, usage = _claude_code(model, system, user, schema, thinking_budget)
            else:
                raw, parsed, reasoning, usage = _api(model, system, user, schema, thinking_budget, max_tokens)
            out = parsed if parsed is not None else parse_json(raw)
            rec.update(latency_s=round(time.monotonic() - t0, 3), ok=True, raw=raw)
            if attempts is not None:
                attempts.append(rec)
            if session_failed and user.sessions is not None:
                user.sessions.failed_start()
            if isinstance(user, Turn):
                usage = {**(usage or {}), "turn": "start"}
            return out, reasoning, usage
        except Exception as e:                                   # one retry, then an empty turn with the error recorded
            last = e
            rec.update(latency_s=round(time.monotonic() - t0, 3), ok=False, raw=raw if raw is not None else getattr(e, "raw", None),
                       error=f"{type(e).__name__}: {e}")
            if attempts is not None:
                attempts.append(rec)
    return {"actions": [], "notes": "", "goal_guesses_json": "{}", "_error": f"{type(last).__name__}: {last}"}, "", {}


def _continue(backend_name, model, system, user, schema, thinking_budget, max_tokens, retries, attempts):
    """One attempt at continuing the conversation; on any failure, the self-contained fallback prompt (logged once per process)."""
    rec = {"attempt": 0, "backend": backend_name, "model": model, "ts": round(time.time(), 3), "turn": "continued"}
    t0 = time.monotonic()
    raw = None
    try:
        if backend_name == "claude_code" and not (user.sessions is not None and user.session):
            raise CallError("no claude -p session to resume")
        if backend_name == "claude_code":
            raw, parsed, reasoning, usage = _claude_code(model, system, user, schema, thinking_budget)
        else:
            raw, parsed, reasoning, usage = _api(model, system, user, schema, thinking_budget, max_tokens)
        out = parsed if parsed is not None else parse_json(raw)
        rec.update(latency_s=round(time.monotonic() - t0, 3), ok=True, raw=raw)
        if attempts is not None:
            attempts.append(rec)
        return out, reasoning, {**(usage or {}), "turn": "continued"}
    except Exception as e:
        rec.update(latency_s=round(time.monotonic() - t0, 3), ok=False, raw=raw if raw is not None else getattr(e, "raw", None),
                   error=f"{type(e).__name__}: {e}")
        if attempts is not None:
            attempts.append(rec)
        _warn_once("continue", f"a conversation could not be continued ({type(e).__name__}: {str(e)[:200]}); the full prompt is sent "
                               "instead (this warning is shown once)")
    out, reasoning, usage = call(backend_name, model, system, user.fallback, schema, thinking_budget, max_tokens, retries, attempts)
    return out, reasoning, {**(usage or {}), "turn": "fallback"}


def messages(user) -> list:
    """The API messages of a user message: one plain user message for a str; for a Turn, its history (alternating user and
    assistant) then the new message, with a cache breakpoint at the end of the new message so the next continuation reads all of
    it from the cache (automatic prefix matching finds this call's entry from the next call's breakpoint)."""
    if not isinstance(user, Turn):
        return [{"role": "user", "content": user}]
    out = [{"role": ("user", "assistant")[i % 2], "content": str(t)} for i, t in enumerate(user.history)]
    if user.mark_previous and out:                               # history mode: the previous call's end is read back whole
        out[-1] = {**out[-1], "content": [{"type": "text", "text": str(user.history[-1]), "cache_control": {"type": "ephemeral"}}]}
    return out + [{"role": "user", "content": [{"type": "text", "text": str(user), "cache_control": {"type": "ephemeral"}}]}]


def _api(model, system, user, schema, thinking_budget, max_tokens):
    global _client
    import anthropic
    _client = _client or anthropic.Anthropic()
    kw = dict(model=model, max_tokens=max_tokens + (thinking_budget or 0),
              system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
              messages=messages(user),
              output_config={"format": {"type": "json_schema", "schema": schema}})
    if "haiku-4" in model:                                       # Haiku 4.5: fixed budget only (no adaptive thinking); Haiku 5.5
                                                                 # takes adaptive like Sonnet/Opus 5.x (budget_tokens is a 400 there)
        if thinking_budget:
            kw["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
    else:                                                        # Sonnet/Opus 5.x: adaptive thinking with summarised text
        kw["thinking"] = {"type": "adaptive", "display": "summarized"}
        kw["max_tokens"] = max_tokens
    resp = _client.messages.create(**kw)
    reasoning = "\n\n".join(b.thinking for b in resp.content if b.type == "thinking" and getattr(b, "thinking", ""))
    text = next(b.text for b in resp.content if b.type == "text")
    u = resp.usage
    return text, None, reasoning, {"input": u.input_tokens, "output": u.output_tokens,
                                          "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                                          "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}


# Subscription usage (claude_code backend): every `claude -p` stream carries a rate_limit_event with the utilization (0..1) of the
# account's windows (five_hour, seven_day). The runner reads USAGE before each round and stops the run at llm.usage_stop.
USAGE: dict = {}


def note_usage(info: dict) -> None:
    import time as _t
    wins = {n: float(w["utilization"]) for n, w in (info.get("unifiedWindows") or {}).items()
            if isinstance(w, dict) and w.get("utilization") is not None}
    if wins:
        USAGE.clear()
        USAGE.update({"windows": wins, "status": info.get("status"), "at": _t.time()})


def usage_stop(llm_cfg: dict | None = None) -> str | None:
    """Why to stop (the subscription is at or over the stop level in some window), or None. Level: env CHARTER_USAGE_STOP, else
    spec llm.usage_stop, else 0.9 (stop with 10% left); null or >= 1 disables. Only the claude_code backend reports usage."""
    v = os.environ.get("CHARTER_USAGE_STOP")
    level = (llm_cfg or {}).get("usage_stop", 0.9) if v is None else (None if v.lower() in ("", "none", "null") else float(v))
    if level is None or level >= 1 or not USAGE.get("windows"):
        return None
    if USAGE.get("status") not in (None, "allowed", "allowed_warning"):
        return f"subscription usage limit reached ({USAGE.get('status')})"
    over = {n: u for n, u in USAGE["windows"].items() if u >= level}
    if not over:
        return None
    return "subscription usage " + ", ".join(f"{n} window {u:.0%} used" for n, u in sorted(over.items())) + f" (stop at {level:.0%})"


def cli_command(model, system, user, schema, thinking_budget=0) -> tuple[list, dict]:
    """The `claude -p` argv and environment of a call. A plain str: no session (--no-session-persistence). A Turn with a session:
    --session-id to start it, or --resume to add the new message to it (history non-empty), with CLAUDE_CONFIG_DIR set to the
    run-local session directory (Sessions)."""
    turn = isinstance(user, Turn) and user.session and user.sessions is not None
    if not turn:
        session = ["--no-session-persistence"]
    else:
        session = ["--resume", user.session] if user.continues else ["--session-id", user.session]
    cmd = ["claude", "-p", str(user), "--output-format", "stream-json", "--verbose", "--model", model, "--system-prompt", system,
           "--tools", "", "--json-schema", json.dumps(schema), *session, "--disable-slash-commands",
           "--settings", json.dumps({"showThinkingSummaries": True})]     # without it the CLI returns thinking blocks with no text
    env = {**os.environ, "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
    env.pop("ANTHROPIC_API_KEY", None)                           # bill the subscription, not the API key
    if thinking_budget:
        env["MAX_THINKING_TOKENS"] = str(thinking_budget)
    if turn:
        env.update(user.sessions.env())
    return cmd, env


def _claude_code(model, system, user, schema, thinking_budget):
    cmd, env = cli_command(model, system, user, schema, thinking_budget)
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=900, cwd="/tmp")
    reasoning, result, withheld = [], None, 0
    for ln in p.stdout.splitlines():
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if e.get("type") == "assistant":
            blocks = [b for b in e["message"].get("content", []) if b.get("type") in ("thinking", "redacted_thinking")]
            reasoning += [b["thinking"] for b in blocks if b.get("thinking")]
            withheld += sum(1 for b in blocks if not b.get("thinking"))   # the model thought, but the CLI gave no text
        if e.get("type") == "result":
            result = e
        if e.get("type") == "rate_limit_event":
            note_usage(e.get("rate_limit_info") or {})
    if not result:
        raise CallError(f"claude -p produced no result: {(p.stderr or p.stdout)[-300:]}", raw=p.stdout[-20000:] or None)
    if result.get("is_error"):                                   # say why: the result text is often empty (None)
        detail = {k: result.get(k) for k in ("subtype", "result", "errors", "stop_reason", "api_error_status") if result.get(k)}
        raise CallError(f"claude -p error (exit {p.returncode}): {json.dumps(detail, default=str)[:400]}"
                        + (f"; stderr: {p.stderr.strip()[-300:]}" if p.stderr.strip() else ""), raw=result.get("result"))
    raw = result.get("result")
    out = result.get("structured_output") or None                    # None: parsed from the raw text by call()
    if raw is None or raw == "":
        raw = json.dumps(out) if out is not None else ""
    u = result.get("usage") or {}
    usage = {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
             "cache_read": u.get("cache_read_input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
             "cc_equiv_usd": result.get("total_cost_usd"), "thinking_withheld": withheld}
    if "--no-session-persistence" not in cmd:                    # the session to resume next (the CLI's own id when it reports one)
        usage["session"] = result.get("session_id") or user.session
    return str(raw), out, "\n\n".join(reasoning), usage
