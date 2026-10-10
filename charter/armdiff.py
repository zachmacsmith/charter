"""Pre-run gate for review 24's arms: two specs (or more) must generate worlds that differ only in their agents' goals.

  python -m charter armdiff SPEC_A SPEC_B [SPEC_C ...] [--seed 1 --seed 2] [--set k=v] [--allow PATH ...]

For each seed, every spec is resolved (presets, --set) and generated (generator.generate); the resolved specs and the generated
instances are compared leaf by leaf, ignoring the goal fields:
  spec    goals.* (the arm's goal structure), life.reproduction.child_goals.* (children's goals), chronicle.namespace
  instance agents[*].goal, spec (compared above), settings (the code defaults, the same for every spec of one checkout)
--allow adds a path prefix to ignore (e.g. actions.unlisted for the salience arm, which differs in its prompt on purpose).
It also fails when either world schedules random world events or unannounced goal changes (events.enabled; --allow-events).
Exit 0 when the only differences are goals and no random events are scheduled, 1 otherwise (each other difference printed with both values).
"""
from __future__ import annotations

import json
import sys

SPEC_IGNORE = ("goals", "life.reproduction.child_goals", "chronicle.namespace")
INST_IGNORE = ("spec", "settings")


def leaves(x, path=""):
    """{dotted path: leaf value}; lists are indexed ([i]); agents are keyed by id so a reordering shows as such."""
    out = {}
    if isinstance(x, dict):
        for k, v in x.items():
            out.update(leaves(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            key = v.get("id") if isinstance(v, dict) and isinstance(v.get("id"), str) else i
            out.update(leaves(v, f"{path}[{key}]"))
    else:
        out[path] = x
    return out


def _ignored(path: str, prefixes) -> bool:
    return any(path == p or path.startswith(p + ".") or path.startswith(p + "[") for p in prefixes)


def _goal_path(path: str) -> bool:
    """agents[<id>].goal..."""
    return path.startswith("agents[") and (".goal." in path or path.endswith(".goal"))


def diff(a: dict, b: dict, ignore=(), goal_filter=None) -> list:
    """[(path, value in a, value in b)] for every leaf that differs, outside the ignored prefixes."""
    la, lb = leaves(a), leaves(b)
    out = []
    for p in sorted(set(la) | set(lb)):
        if _ignored(p, ignore) or (goal_filter and goal_filter(p)):
            continue
        va, vb = la.get(p, "<missing>"), lb.get(p, "<missing>")
        if json.dumps(va, sort_keys=True, default=str) != json.dumps(vb, sort_keys=True, default=str):
            out.append((p, va, vb))
    return out


def random_events(inst: dict) -> list:
    """What would change the world or an agent's goal unannounced: scheduled world events and random goal changes
    (instance["world_events"], drawn when events.enabled). Review 24's worlds must have none (doc 25: nature_pairs inherits
    events.enabled and 3-5 goal changes a run)."""
    we = inst.get("world_events") or {}
    return ([f"goal change: {g['agent']} at round {g['round'] + 1}" for g in we.get("goal_changes") or []]
            + [f"world event: {e['type']} at round {e['round'] + 1}" for e in we.get("schedule") or []])


def compare(spec_a: dict, spec_b: dict, seed: int, allow=()) -> dict:
    """{"spec": [...], "instance": [...]}: the non-goal differences between two resolved specs and their generated worlds."""
    from charter import generator
    ia, ib = generator.generate(spec_a, seed), generator.generate(spec_b, seed)
    return {"random_events": random_events(ia) + random_events(ib),
            "spec": diff(spec_a, spec_b, SPEC_IGNORE + tuple(allow)),
            "instance": diff(ia, ib, INST_IGNORE + tuple(allow) + tuple("spec_source." + p for p in SPEC_IGNORE + tuple(allow)),
                             _goal_path),
            "goals_differ": sum(1 for x, y in zip(ia["agents"], ib["agents"]) if x.get("goal") != y.get("goal"))}


def add_arguments(p) -> None:
    p.add_argument("specs", nargs="+")
    p.add_argument("--seed", type=int, action="append", default=[])
    p.add_argument("--set", action="append", default=[])
    p.add_argument("--allow", action="append", default=[], help="a path prefix to ignore as well (spec and instance)")
    p.add_argument("--allow-events", action="store_true", help="do not fail on scheduled world events or random goal changes")


def cmd(a) -> int:
    from charter import spec as S
    if len(a.specs) < 2:
        print("armdiff: give at least two specs")
        return 2
    specs = [S.apply_overrides(S.load(n), a.set) for n in a.specs]
    bad = 0
    for seed in a.seed or [1]:
        for name, sp in zip(a.specs[1:], specs[1:]):
            r = compare(specs[0], sp, seed, a.allow)
            n = len(r["spec"]) + len(r["instance"])
            ev = [] if a.allow_events else r["random_events"]
            print(f"seed {seed}: {a.specs[0]} vs {name}: {r['goals_differ']} agents' goals differ; "
                  f"{n} other difference{'s' if n != 1 else ''}; {len(ev)} random world events or goal changes")
            for x in ev[:20]:
                print(f"  random: {x} (set events.enabled: false and events.goal_changes.enabled: false)")
            n += len(ev)
            for where in ("spec", "instance"):
                for p, x, y in r[where][:40]:
                    print(f"  {where} {p}: {x!r} != {y!r}")
            bad += n
    return 1 if bad else 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    add_arguments(ap)
    sys.exit(cmd(ap.parse_args()))
