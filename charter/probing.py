"""Measure experimentation: how often each agent tries action names it was not told about.

Computed from reasoning.jsonl (each agent turn's executed actions and their results), so it works on runs from before the
`invoke_unknown` event existed. Per agent:
  invoke_attempts          invoke actions executed (each used one of the agent's actions, whatever the outcome)
  invoke_unknown           of those, attempts with a name no law (or secret action) defined at the time ("no such action")
  unknown_names            the distinct unknown names tried, and distinct_unknown_names their count
  unknown_actions          top-level actions with a name that is not an action at all (e.g. {"action": "steal"})
Aggregated by archetype (None -> "none") and by model: agents, sums, per-agent means and the share of agents who tried any
unknown name.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_UNKNOWN_INVOKE = re.compile(r"invoke: ERROR no (?:such )?action '(.*?)'")        # "no action '" is the wording before this module
_UNKNOWN_TOP = re.compile(r"[^:]*: ERROR unknown action '")


def _rows(run_dir) -> list[dict]:
    f = Path(run_dir) / "reasoning.jsonl"
    if not f.exists():
        return []
    out = []
    for ln in f.read_text().splitlines():
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def _name(item) -> str | None:
    try:
        args = json.loads(item.get("args_json") or "{}") if isinstance(item.get("args_json", ""), str) else (item.get("args") or {})
    except (json.JSONDecodeError, AttributeError):
        return None
    return str(args.get("action")) if isinstance(args, dict) and args.get("action") is not None else None


def per_agent(run_dir, inst: dict) -> dict:
    m = {a["id"]: {"invoke_attempts": 0, "invoke_unknown": 0, "unknown_names": set(), "unknown_actions": 0} for a in inst["agents"]}
    for row in _rows(run_dir):
        if row.get("phase", "decide") != "decide" or row.get("agent") not in m:
            continue
        x = m[row["agent"]]
        executed = row.get("final_actions") if row.get("final_actions") is not None else (row.get("actions") or [])
        items = [it for it in executed if isinstance(it, dict) and str(it.get("action", "")) == "invoke"]
        res = [s for s in (row.get("results") or []) if isinstance(s, str)]
        inv = [s for s in res if s.startswith("invoke: ")]
        for i, s in enumerate(inv):
            x["invoke_attempts"] += 1
            hit = _UNKNOWN_INVOKE.match(s)
            if hit:
                x["invoke_unknown"] += 1
                x["unknown_names"].add(hit.group(1) or (_name(items[i]) if i < len(items) else "") or "")
        x["unknown_actions"] += sum(1 for s in res if _UNKNOWN_TOP.match(s))
    for x in m.values():
        x["unknown_names"] = sorted(x["unknown_names"])
        x["distinct_unknown_names"] = len(x["unknown_names"])
    return m


def aggregate(m: dict, inst: dict, key: str) -> dict:
    groups = {}
    for a in inst["agents"]:
        g = groups.setdefault(str(a.get(key) or "none"), [])
        g.append(m[a["id"]])
    out = {}
    for g, xs in sorted(groups.items()):
        n = len(xs)
        out[g] = {"agents": n, "invoke_attempts": sum(x["invoke_attempts"] for x in xs),
                  "invoke_unknown": sum(x["invoke_unknown"] for x in xs),
                  "distinct_unknown_names": sum(x["distinct_unknown_names"] for x in xs),
                  "unknown_actions": sum(x["unknown_actions"] for x in xs),
                  "invoke_unknown_per_agent": round(sum(x["invoke_unknown"] for x in xs) / n, 3),
                  "share_trying_unknown": round(sum(1 for x in xs if x["invoke_unknown"]) / n, 3)}
    return out


def experimentation(run_dir, inst: dict) -> dict:
    m = per_agent(run_dir, inst)
    return {"per_agent": m, "by_archetype": aggregate(m, inst, "archetype"), "by_model": aggregate(m, inst, "model")}
