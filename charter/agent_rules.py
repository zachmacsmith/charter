"""Per-agent scenario rules (spec `agent_rules`, default empty: nothing changes). Today: a briefing for named agents.

    agent_rules:
      Siv: {briefing: "Your goals score only control of the existing Commonwealth (J0) ..."}

  briefing  a short text shown as "Your situation: ..." in the agent's system prompt (core layer: after its identity; legacy layer:
            the same), so it is in every model call. It informs; it restricts nothing (the agent may still do anything the world
            allows).
Names are checked when a world is built (Kernel construction) and keys by the schema: an unknown agent or key is an error with a
did-you-mean.
"""
from __future__ import annotations

import difflib

FIELDS = ("briefing",)


def rules(x) -> dict:
    """{agent: {briefing}} from a spec, an instance or a kernel ({} when unset)."""
    if hasattr(x, "spec") and not isinstance(x, dict):
        sp = x.spec
    elif isinstance(x, dict) and isinstance(x.get("spec"), dict):
        sp = x["spec"]
    else:
        sp = x
    return (sp or {}).get("agent_rules") or {}


def briefing(x, aid) -> str:
    return str((rules(x).get(aid) or {}).get("briefing") or "").strip()


def _close(v, pool) -> str:
    c = difflib.get_close_matches(str(v), list(pool), n=1)
    return f" (did you mean {c[0]!r}?)" if c else ""


def check_spec(path, v) -> list:
    """schema check for agent_rules.<name>: {briefing: str}."""
    if not isinstance(v, dict):
        return [f"{path}: expected {{briefing}}, got {v!r}"]
    errs = [f"{path}.{k}: unknown key{_close(k, FIELDS)}" for k in v if k not in FIELDS]
    if "briefing" in v and not isinstance(v["briefing"], str):
        errs.append(f"{path}.briefing: expected text")
    return errs


def install(k) -> None:
    """Kernel construction: every named agent exists (nothing to do when unset)."""
    r = rules(k)
    if not r:
        return
    ids = [a["id"] for a in k.inst["agents"]]
    bad = [n for n in r if n not in ids]
    if bad:
        raise ValueError(f"agent_rules: no agent {bad[0]!r}{_close(bad[0], ids)}")
    errs = [e for n, v in r.items() for e in check_spec(f"agent_rules.{n}", v)]
    if errs:
        raise ValueError("; ".join(errs))


def line(x, aid) -> str:
    b = briefing(x, aid)
    return f"\nYour situation: {b}" if b else ""
