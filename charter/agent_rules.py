"""Per-agent scenario rules (spec `agent_rules`, default empty: nothing changes): a briefing and denied actions for named agents.

    agent_rules:
      Siv: {briefing: "You cannot found a new jurisdiction ...", deny: [found, join, leave, declare, set_charter]}

  briefing  a short text shown every turn as "Your situation: ..." in the agent's system prompt (core layer: after its identity;
            legacy layer: the same), so it is in every model call
  deny      actions the kernel refuses for that agent (actions.act raises "<action> is not open to you in this world"), and which
            are left out of its action list (action_registry.available). An experimental-contract rule (review 12 tier X): a
            restriction the scenario imposes on one agent, not physics and not law; no law can lift it.
Names are checked when a world is built (Kernel construction): an unknown agent or action is an error with a did-you-mean.
"""
from __future__ import annotations

import difflib

FIELDS = ("briefing", "deny")


def rules(x) -> dict:
    """{agent: {briefing, deny}} from a spec, an instance or a kernel ({} when unset)."""
    sp = x.spec if hasattr(x, "spec") and not isinstance(x, dict) else (x.get("spec") if isinstance(x, dict) and isinstance(x.get("spec"), dict) else x)
    return (sp or {}).get("agent_rules") or {}


def briefing(x, aid) -> str:
    return str((rules(x).get(aid) or {}).get("briefing") or "").strip()


def denied(x, aid) -> frozenset:
    return frozenset((rules(x).get(aid) or {}).get("deny") or ())


def _close(v, pool) -> str:
    c = difflib.get_close_matches(str(v), list(pool), n=1)
    return f" (did you mean {c[0]!r}?)" if c else ""


def check_spec(path, v) -> list:
    """schema check for agent_rules.<name>: {briefing: str, deny: [action names]}."""
    from charter import action_registry as AR
    if not isinstance(v, dict):
        return [f"{path}: expected {{briefing, deny}}, got {v!r}"]
    errs = [f"{path}.{k}: unknown key{_close(k, FIELDS)}" for k in v if k not in FIELDS]
    if "briefing" in v and not isinstance(v["briefing"], str):
        errs.append(f"{path}.briefing: expected text")
    deny = v.get("deny") or []
    if not isinstance(deny, list):
        errs.append(f"{path}.deny: expected a list of action names")
    else:
        errs += [f"{path}.deny: unknown action {a!r}{_close(a, AR.REG)}" for a in deny if a not in AR.REG]
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
