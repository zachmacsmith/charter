"""docs/review/21_combat.md: the outcome table of the harm combat model, by seeded Monte Carlo through the real battle code
(conflict._resolve_harm), and the analytic odds next to it. Bases are 1 (the mean of the default draw), everyone fed.

    python docs/review/21_combat_table.py [trials]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from charter import conflict as CF                                    # noqa: E402
from charter import generator, spec as S                              # noqa: E402
from charter.kernel import Kernel                                      # noqa: E402

SCENARIOS = [  # name, attacker's weapon, ally's weapon (None: no ally), target's weapon, target on watch, target's fort
    ("unarmed vs unarmed", None, None, None, False, 0),
    ("club vs unwary", "crude", None, None, False, 0),
    ("blade vs unwary", "weapons", None, None, False, 0),
    ("blade vs wary (watch)", "weapons", None, None, True, 0),
    ("blade vs fort 5", "weapons", None, None, False, 5),
    ("two blades vs unwary", "weapons", "weapons", None, False, 0),
    ("two blades vs wary", "weapons", "weapons", None, True, 0),
    ("blade vs armed wary defender (blade)", "weapons", None, "weapons", True, 0),
]


def world():
    sp = S.apply_overrides(S.load("nature_subsistence"), [
        "shared_archive.enabled=false", "conflict.assassin.present_prob=0", "conflict.start={}", "conflict.grace=0",
        "conflict.timing=immediate", "rounds=10", "agents={worker: 6, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 1}"])
    k = Kernel(generator.generate(sp, 1))
    a, b, t = sorted(x for x in k.players() if k.w["agents"][x]["cls"] == "worker")[:3]
    for x in (a, b, t):
        k.w["conflict"]["bases"][x] = {"attack": 1.0, "defense": 1.0}
        for item in ("weapons", "crude"):
            k._add(x, item, -k.bal(x, item))
    return k, a, b, t


def run(trials=4000):
    k, a, b, t = world()
    base = k._snapshot()
    rows = []
    for name, aw, bw, tw, watch, fort in SCENARIOS:
        n = {"kill": 0, "wound": 0, "repelled": 0, "struck_first": 0, "att_wounded": 0, "att_killed": 0}
        P = D = None
        for i in range(trials):
            k._restore(base)
            k.w["conflict"]["seq"] = i
            for x, w in ((a, aw), (b, bw), (t, tw)):
                k._add(x, "food", 6.0 - k.bal(x, "food"))
                if w:
                    k._add(x, w, 1.0)
            k.w["conflict"]["forts"][t] = float(fort)
            if watch:
                k.w["conflict"]["watch"][t] = k.r
            if bw:
                k.apply("attack", attacker=a, target=t, units=0.0, covert=False, disguise=False, lawful=False, ally=b)
            r = CF.attack(k, a, t, 0)
            P, D = r["P"], r["D"]
            n[r["outcome"]] += 1
            blow = r.get("first_strike") if r["outcome"] == "struck_first" else r.get("counter")
            if blow and blow.get("landed"):
                n["att_killed" if blow["effect"] == "kill" else "att_wounded"] += 1
        o = CF.odds(CF.config(k.spec), P, D)
        rows.append((name, P, D, o, {x: v / trials for x, v in n.items()}))
    return rows


def markdown(rows, trials) -> str:
    out = [f"| scenario | P | D | p_kill (formula) | kill | wound | repelled | struck first | attacker wounded | attacker killed |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for name, P, D, o, s in rows:
        out.append(f"| {name} | {P:g} | {D:g} | {o['p_kill']:.2f} | {s['kill']:.2f} | {s['wound']:.2f} | {s['repelled']:.2f} | "
                   f"{s['struck_first']:.2f} | {s['att_wounded']:.2f} | {s['att_killed']:.3f} |")
    return "\n".join(out) + f"\n\n({trials} seeded trials per row.)"


def yields(run_dir) -> dict:
    """Mean yield per harvest (and per hunt action) by resource and camp type, from a run's events.jsonl."""
    import json
    import statistics as stt
    run_dir = Path(run_dir)
    camps = {c["id"]: c for c in json.loads((run_dir / "instance.json").read_text())["camps"]}
    per = {}
    for line in (run_dir / "events.jsonl").read_text().splitlines():
        e = json.loads(line)
        d = e.get("data") or {}
        if e["type"] == "harvest" and d.get("camp") in camps:
            c = camps[d["camp"]]
            per.setdefault((c.get("resource"), c.get("type")), []).append(float(d.get("yield") or 0))
        elif e["type"] == "hunt_result":
            per.setdefault(("food", "hunt"), []).append(float(d.get("share") or 0) / max(1e-9, float(d.get("effort") or 1)))
    return {key: (len(v), round(stt.mean(v), 2), round(stt.median(v), 2), round(max(v), 2)) for key, v in sorted(per.items())}


if __name__ == "__main__":
    if sys.argv[1:2] == ["--yields"]:
        for r in sys.argv[2:]:
            print(r)
            for (res, typ), (n, mean, med, mx) in yields(r).items():
                print(f"  {res:8s} {typ:12s} n={n:4d} mean={mean:6.2f} median={med:6.2f} max={mx:6.2f}")
    else:
        n = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
        print(markdown(run(n), n))
