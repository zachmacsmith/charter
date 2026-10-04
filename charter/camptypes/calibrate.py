"""Calibration of camp types: value per action relative to the tutorial, for scripted strategies (no models).

    .venv/bin/python -m charter.camptypes.calibrate [--rounds 40] [--seeds 3] [--stock full|dynamic] [--types tutorial,landscape,cartel,minority]

Strategies (each type's calibration_input):
  random   inputs drawn uniformly (an agent that has learned nothing)
  learned  the best input from the hidden truth: the landscape's optimum under this round's conditions, the tutorial's optimum, the
           cartel's joint-optimum quota kept by everyone (coordination works); the minority game has nothing to learn (random)
  nash     cartel only: everyone plays the n-extractor textbook equilibrium (each alone gains nothing by changing)
  fail     coordination fails: every cartel extractor grabs the maximum; every minority player picks the same side
With --stock full every camp is refilled before each round (the type's own payout rule, no commons dynamics); dynamic lets stocks run.

Spec targets (docs/new_features_update.md): solo science 1.5x once learned; coordination 2-3x when coordination works and 0.5x when it
fails; social games about 1x with high variance. Tune camps.typed.targets / value_per_action and the per-type parameters
(camps.typed.types.<type>) until this table matches, then check with models: run a pilot (specs/camps_pilot.yaml) with real models
over 3+ seeds and read score.json -> metrics.camps.yield_by_type (relative_to_tutorial) and metrics.camps.cartel (mean_coordination,
total_vs_optimum). Models learn more slowly than the `learned` strategy and coordinate worse than it, so expect the model ratios to
sit between `random` and `learned` (cartel: between `fail` and `learned`); if solo science stays below 1x after 20 rounds, lower the
landscape's ruggedness K or raise its target.
"""
from __future__ import annotations

import argparse
import random
import statistics

from charter.camptypes import framework as CT
from charter.camptypes import harness as HN

STRATEGIES = ("random", "learned", "nash", "fail")


def run(types=("tutorial", "landscape", "cartel", "minority"), strategy="learned", rounds=40, seed=1, stock="full",
        workers=4, others=4) -> dict:
    """{type: value per action} for one strategy and seed."""
    k = HN.world(list(types), workers=workers, others=others, seed=seed)
    rng = random.Random(f"calibrate|{seed}|{strategy}")
    players = sorted(a for a in k.players() if k.w["agents"][a]["cls"] not in CT.NO_CAMPS)
    acc = {cid: [0.0, 0] for cid in CT.typed_camps(k)}
    for _ in range(rounds):
        if stock == "full":
            for cid in CT.typed_camps(k):
                k.w["camps"][cid]["S"] = k.w["camps"][cid]["K"]
        inputs = {}
        for cid in CT.typed_camps(k):
            c = k.w["camps"][cid]
            if c.get("open"):
                fn = c["fn"]
                n = round(CT.get(c["type"]).expected_players(fn)) if hasattr(CT.get(c["type"]), "expected_players") else len(players)
                who = players[:max(1, n)]
            else:
                who = [a for a in players if k.has(a, f"harvest:{cid}")]
            k._calib_players = len(who)
            t = CT.view(k, cid, fresh=False)
            inputs[cid] = {a: t.calibration_input(k, a, strategy, rng) for a in who}
        out = HN.play(k, inputs)
        for cid, ins in inputs.items():
            v = k.w["unit"][k.w["camps"][cid]["resource"]]
            acc[cid][0] += sum(out.get(cid, {}).values()) * v
            acc[cid][1] += len(ins)
    by_type = {}
    for cid, (val, n) in acc.items():
        t = k.w["camps"][cid]["type"]
        b = by_type.setdefault(t, [0.0, 0])
        b[0] += val
        b[1] += n
    return {t: (val / n if n else None) for t, (val, n) in by_type.items()}


def table(types=("tutorial", "landscape", "cartel", "minority"), rounds=40, seeds=3, stock="full") -> dict:
    """{strategy: {type: mean value per action / the tutorial's under `learned`}} averaged over seeds."""
    raw = {s: [run(types, s, rounds, seed, stock) for seed in range(1, seeds + 1)] for s in STRATEGIES}
    ref = statistics.mean(x["tutorial"] for x in raw["learned"]) if "tutorial" in types else 1.0
    out = {}
    for s, xs in raw.items():
        out[s] = {t: round(statistics.mean(x[t] for x in xs) / ref, 3) for t in xs[0] if all(x[t] is not None for x in xs)}
    out["_tutorial_value_per_action"] = round(ref, 3)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rounds", type=int, default=40)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--stock", choices=("full", "dynamic"), default="full")
    ap.add_argument("--types", default="tutorial,landscape,cartel,minority")
    a = ap.parse_args(argv)
    types = tuple(a.types.split(","))
    t = table(types, a.rounds, a.seeds, a.stock)
    ref = t.pop("_tutorial_value_per_action")
    print(f"value per action relative to the tutorial under `learned` ({ref} value per action); stock {a.stock}, {a.rounds} rounds, {a.seeds} seeds")
    print("strategy  " + "".join(f"{x:>12}" for x in types))
    for s in STRATEGIES:
        print(f"{s:<10}" + "".join(f"{t[s].get(x, float('nan')):>12.3f}" for x in types))


if __name__ == "__main__":
    main()
