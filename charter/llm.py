"""One structured model call per agent turn, through LLM_BACKEND (agnet/.env): "api" (ANTHROPIC_API_KEY) or "claude_code"
(headless `claude -p` billed to the subscription via CLAUDE_CODE_OAUTH_TOKEN, with every tool disabled, so nothing runs on the host).
Returns (parsed JSON dict, reasoning text, usage dict). Reasoning: API Sonnet/Opus give summarised thinking; through Claude Code only
models with a fixed thinking budget (Haiku 4.5) return thinking text (Sonnet/Opus 5.5 come back with the text omitted).
"""
from __future__ import annotations

import json
import os
import re
import subprocess

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


def call(backend_name, model, system, user, schema, thinking_budget=0, max_tokens=6000, retries=1):
    last = None
    for _ in range(retries + 1):
        try:
            if backend_name == "claude_code":
                return _claude_code(model, system, user, schema, thinking_budget)
            return _api(model, system, user, schema, thinking_budget, max_tokens)
        except Exception as e:                                   # one retry, then an empty turn with the error recorded
            last = e
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
    return parse_json(text), reasoning, {"input": u.input_tokens, "output": u.output_tokens,
                                          "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                                          "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}


def _claude_code(model, system, user, schema, thinking_budget):
    cmd = ["claude", "-p", user, "--output-format", "stream-json", "--verbose", "--model", model, "--system-prompt", system,
           "--tools", "", "--json-schema", json.dumps(schema), "--no-session-persistence", "--disable-slash-commands"]
    env = {**os.environ, "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
    env.pop("ANTHROPIC_API_KEY", None)                           # bill the subscription, not the API key
    if thinking_budget:
        env["MAX_THINKING_TOKENS"] = str(thinking_budget)
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=900, cwd="/tmp")
    reasoning, result = [], None
    for ln in p.stdout.splitlines():
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if e.get("type") == "assistant":
            reasoning += [b.get("thinking", "") for b in e["message"].get("content", []) if b.get("type") == "thinking" and b.get("thinking")]
        if e.get("type") == "result":
            result = e
    if not result:
        raise RuntimeError(f"claude -p produced no result: {(p.stderr or p.stdout)[-300:]}")
    if result.get("is_error"):
        raise RuntimeError(f"claude -p error: {str(result.get('result'))[:300]}")
    out = result.get("structured_output") or parse_json(str(result.get("result", "")))
    u = result.get("usage") or {}
    return out, "\n\n".join(reasoning), {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
                                         "cache_read": u.get("cache_read_input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
                                         "cc_equiv_usd": result.get("total_cost_usd")}
