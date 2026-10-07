"""One structured model call per agent turn, through LLM_BACKEND (.env at the repository root): "api" (ANTHROPIC_API_KEY) or "claude_code"
(headless `claude -p` billed to the subscription via CLAUDE_CODE_OAUTH_TOKEN, with every tool disabled, so nothing runs on the host).
Returns (parsed JSON dict, reasoning text, usage dict); pass `attempts=[]` to also get every attempt's raw text and error. Reasoning: API Sonnet/Opus give summarised thinking; through Claude Code only
models with a fixed thinking budget (Haiku 4.5) return thinking text (Sonnet/Opus 5.5 come back with the text omitted).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time

_client = None


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
    last = None
    for i in range(retries + 1):
        rec = {"attempt": i, "backend": backend_name, "model": model, "ts": round(time.time(), 3)}
        t0 = time.monotonic()
        raw = None
        try:
            if backend_name == "claude_code":
                raw, parsed, reasoning, usage = _claude_code(model, system, user, schema, thinking_budget)
            else:
                raw, parsed, reasoning, usage = _api(model, system, user, schema, thinking_budget, max_tokens)
            out = parsed if parsed is not None else parse_json(raw)
            rec.update(latency_s=round(time.monotonic() - t0, 3), ok=True, raw=raw)
            if attempts is not None:
                attempts.append(rec)
            return out, reasoning, usage
        except Exception as e:                                   # one retry, then an empty turn with the error recorded
            last = e
            rec.update(latency_s=round(time.monotonic() - t0, 3), ok=False, raw=raw if raw is not None else getattr(e, "raw", None),
                       error=f"{type(e).__name__}: {e}")
            if attempts is not None:
                attempts.append(rec)
    return {"actions": [], "notes": "", "goal_guesses_json": "{}", "_error": f"{type(last).__name__}: {last}"}, "", {}


def _api(model, system, user, schema, thinking_budget, max_tokens):
    global _client
    import anthropic
    _client = _client or anthropic.Anthropic()
    kw = dict(model=model, max_tokens=max_tokens + (thinking_budget or 0),
              system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
              messages=[{"role": "user", "content": user}],
              output_config={"format": {"type": "json_schema", "schema": schema}})
    if "haiku" in model:                                         # Haiku 4.5: fixed budget only (no adaptive thinking)
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


def _claude_code(model, system, user, schema, thinking_budget):
    cmd = ["claude", "-p", user, "--output-format", "stream-json", "--verbose", "--model", model, "--system-prompt", system,
           "--tools", "", "--json-schema", json.dumps(schema), "--no-session-persistence", "--disable-slash-commands",
           "--settings", json.dumps({"showThinkingSummaries": True})]     # without it the CLI returns thinking blocks with no text
    env = {**os.environ, "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
    env.pop("ANTHROPIC_API_KEY", None)                           # bill the subscription, not the API key
    if thinking_budget:
        env["MAX_THINKING_TOKENS"] = str(thinking_budget)
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
    return str(raw), out, "\n\n".join(reasoning), {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
                                         "cache_read": u.get("cache_read_input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
                                         "cc_equiv_usd": result.get("total_cost_usd"), "thinking_withheld": withheld}
