"""Charter command line (run from agnet/):

  python -m charter generate E3 --seed 4 [--set constitution=council ...]       print / save the drawn world
  python -m charter run E3 --seed 4 [--dry] [--set ...]                          generate, play, score, report -> charter/out/<spec>/E3_seed4_<hash>
  python -m charter resume RUN_DIR                                               continue a stopped or crashed run from its last complete round
  python -m charter score RUN_DIR                                                (re)score a run
  python -m charter show RUN_DIR                                                 summary + timeline of what happened
  python -m charter view RUN_DIR [--open]                                       story.html: the run as a group chat, inboxes, laws and wealth
  python -m charter report RUN_DIR                                               (re)build overview.md, spec_outline.md, agents/*
  python -m charter sweep E3 --seeds 3 --vary constitution=assembly,oligarchy --vary models.mix=all_weak,strong_legislators [--dry]
  python -m charter explore E3 --runs 8 --perturb "endowment_gini={uniform: [0.1, 0.7]}" --perturb "conditions.fixer={choice: [honest, hidden]}" [--dry]

SPEC is a preset name (E0..E7, base, example_E3) or a path to a YAML spec. --set applies explicit choices (they win over draws).
Model calls go through LLM_BACKEND in agnet/.env: api (default) or claude_code (your Claude Code subscription). --dry uses free
scripted bots instead of models.

Run directories are stable: <spec>_seed<N>[_dry]_<hash of the resolved spec>. Running the same command again skips a run that is
complete and resumes one that is not (from checkpoint.pkl, written after every round). A run stops by itself if half the model calls
in a round fail (llm.fail_stop_fraction; e.g. a usage limit): that round is dropped and STOPPED.md says why; run the same command
again (or `resume`) later.
--fresh starts a separate run in a new timestamped directory instead (e.g. to repeat a seed).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import random
import sys
import time
from pathlib import Path

from charter import agents as AG
from charter import generator, runner, scorer
from charter import spec as S

AGNET = Path(__file__).resolve().parents[1]
RUNS = Path(__file__).resolve().parent / "out"                 # charter/out/<spec>/<run>/ (git-ignored)


def load_env():
    f = AGNET / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ[k.strip()] = v.strip().strip("\"'")


def build_spec(name, overrides, fast=False):
    sp = S.apply_overrides(S.load(name), overrides)
    return S.set_path(sp, "turns", "simultaneous") if fast else sp


def new_dir(parent: Path, stem: str) -> Path:
    d = parent / stem
    n = 2
    while d.exists():
        d = parent / f"{stem}_{n}"
        n += 1
    d.mkdir(parents=True)
    return d


def run_stem(tag: str, sp: dict, seed: int, dry: bool) -> str:
    """Stable run directory name: the same spec (after overrides), seed and mode always give the same directory."""
    if sp.get("regime", 0) is None:                              # `regime: null` (the default) keeps pre-regime run directories
        sp = {k: v for k, v in sp.items() if k != "regime"}
    h = hashlib.sha256(json.dumps(sp, sort_keys=True, default=str).encode()).hexdigest()[:8]
    return f"{tag}_seed{seed}" + ("_dry" if dry else "") + f"_{h}"


def _same_instance(out: Path, inst: dict) -> bool:
    f = out / "instance.json"
    return f.exists() and f.read_text() == json.dumps(inst, indent=1, default=str)


def policy_for(sp, dry, seed):
    if dry:
        return AG.ScriptedPolicy(seed)
    from charter import llm
    return AG.LLMPolicy(llm.backend(), sp["llm"])


def sandbox_for(dry, mode):
    if dry or mode == "off":
        return None
    from charter.sandbox import DockerSandbox
    return DockerSandbox()


def run_one(spec_name, sp, seed, dry, sandbox_mode, parent=None, quiet=False, fresh=False):
    inst = generator.generate(sp, seed)
    tag = Path(spec_name).stem
    parent = parent or RUNS / tag
    resume = False
    if fresh:
        out = new_dir(parent, time.strftime("%Y-%m-%dT%H-%M-%S") + f"_seed{seed}" + ("_dry" if dry else ""))
    else:
        out = parent / run_stem(tag, sp, seed, dry)
        gt = out / "ground_truth.json"
        if gt.exists() and json.loads(gt.read_text()).get("complete"):
            print(f"[{out.name}] already complete; skipping (use --fresh for a separate run)")
            res = json.loads((out / "score.json").read_text()) if (out / "score.json").exists() else scorer.score(out)
            return out, res["summary"]
        out.mkdir(parents=True, exist_ok=True)
        if (out / "checkpoint.pkl").exists():
            inst["run_id"] = out.name
            if not _same_instance(out, inst):
                raise SystemExit(f"[{out.name}] has a checkpoint but the world it would generate now differs from instance.json "
                                 f"(spec or code changed). Use --fresh for a new run.")
            resume = True
    inst["run_id"] = out.name
    backend = "scripted" if dry else os.environ.get("LLM_BACKEND", "api")
    print(f"[{out.name}] {len(inst['agents'])} agents x {inst['rounds']} rounds, constitution {inst['constitution']}, "
          + (f"regime {inst['regime']['name']}, " if inst.get("regime") else "") +
          f"law level {inst['law_level']}, backend {backend}" + (" (resuming)" if resume else ""))
    _play(inst, out, dry, seed, sandbox_mode, quiet, resume)
    res = scorer.score(out)
    from charter import report
    report.build(out)
    return out, res["summary"]


def _play(inst, out, dry, seed, sandbox_mode, quiet, resume):
    try:
        runner.run(inst, policy_for(inst["spec"], dry, seed), out, sandbox_for(dry, sandbox_mode),
                   log=(lambda *a: None) if quiet else print, resume=resume)
    except runner.RunStopped as e:
        print(f"[{out.name}] stopped: {e}\nContinue later with the same command, or: python -m charter resume {out}")
        raise SystemExit(2)


def cmd_resume(a):
    out = Path(a.run)
    if not (out / "checkpoint.pkl").exists():
        raise SystemExit(f"{out} has no checkpoint.pkl (runs from before checkpoints existed cannot be resumed)")
    saved = json.loads((out / "instance.json").read_text())
    inst = generator.generate(saved["spec"], saved["seed"])
    inst["run_id"] = saved.get("run_id", out.name)
    if not _same_instance(out, inst):
        raise SystemExit(f"{out}: the world generated now differs from instance.json (spec or code changed); cannot resume")
    dry = "_dry" in out.name
    _play(inst, out, dry, saved["seed"], a.sandbox, False, resume=True)
    res = scorer.score(out)
    from charter import report
    report.build(out)
    print(json.dumps(res["summary"], indent=1))
    print(f"run dir: {out}")


def interest(s: dict) -> float:
    """How much happened in a run (for ranking exploration results): institutions formed, changed, or were captured."""
    return (2 * s["regime_changes"] + s["laws_enacted"] + 2 * s["currency_adopted"] + s["vetoes"] + s["corruption_candidates"]
            + s["knowledge_transfers"] + (3 if s["regime_final"] == "dictatorship" else 0))


def write_table(d: Path, rows: list[dict], extra_cols=()):
    if not rows:
        return
    cols = list(extra_cols) + [c for c in rows[0] if c not in extra_cols]
    with open(d / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    show = list(extra_cols) + ["seed", "constitution", "regime", "regime_start", "regime_final", "regime_changes", "laws_enacted", "currency_adopted", "vetoes",
                               "corruption_candidates", "knowledge_transfers", "welfare_change", "holdings_gini_end", "mean_goal_score", "interest"]
    show = list(dict.fromkeys(show))                             # e.g. --vary regime=... already lists regime
    lines = ["| " + " | ".join(show) + " |", "|" + "---|" * len(show)]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in show) + " |")
    (d / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def cmd_generate(a):
    sp = build_spec(a.spec, a.set, getattr(a, 'fast', False))
    inst = generator.generate(sp, a.seed)
    if a.out:
        Path(a.out).write_text(json.dumps(inst, indent=1, default=str))
    reg = inst.get("regime")
    print(json.dumps({"constitution": inst["constitution"], "law_level": inst["law_level"], "rounds": inst["rounds"],
                      **({"regime": {"name": reg["name"], "statutes": [s["name"] for s in reg["statutes"]], "offices": reg["offices"]}} if reg else {}),
                      "agents": [{k: x[k] for k in ("id", "cls", "model", "actions")} | {"goal": x["goal"]["primary"]} for x in inst["agents"]],
                      "camps": [(c["id"], c["resource"], c["fn"]["family"]) for c in inst["camps"]], "library": len(inst["library"]),
                      "library_access": inst["library_access"], "repairs": inst["repairs"], "unreachable_goals": inst["unreachable_goals"]}, indent=1))


def cmd_run(a):
    sp = build_spec(a.spec, a.set, getattr(a, 'fast', False))
    out, s = run_one(a.spec, sp, a.seed, a.dry, a.sandbox, fresh=a.fresh)
    print(json.dumps(s, indent=1))
    print(f"run dir: {out}")


def cmd_sweep(a):
    base = build_spec(a.spec, a.set, getattr(a, 'fast', False))
    grid = [(k, [S.yaml.safe_load(x) for x in v.split(",")]) for k, _, v in (x.partition("=") for x in a.vary)]
    sweep = new_dir(RUNS / "sweeps", time.strftime("%Y-%m-%dT%H-%M-%S") + "_" + Path(a.spec).stem)
    rows = []
    combos = list(itertools.product(*[vals for _, vals in grid])) or [()]
    for combo in combos:
        sp = base
        label = {}
        for (k, _), v in zip(grid, combo):
            sp = S.set_path(sp, k, v)
            label[k] = v
        for seed in range(a.seed, a.seed + a.seeds):
            out, s = run_one(a.spec, sp, seed, a.dry, a.sandbox, parent=sweep, quiet=True, fresh=a.fresh)
            rows.append({**{k: json.dumps(v) for k, v in label.items()}, **s, "interest": interest(s)})
            write_table(sweep, rows, extra_cols=tuple(label))
    print(f"sweep dir: {sweep}")


def cmd_explore(a):
    """Random exploration: each run draws every --perturb parameter from its distribution (and a fresh seed), then runs are ranked
    by how much happened. Use it to find the regions of parameter space worth a proper sweep."""
    base = build_spec(a.spec, a.set, getattr(a, 'fast', False))
    pert = [(k, S.yaml.safe_load(v)) for k, _, v in (x.partition("=") for x in a.perturb)]
    rng = random.Random(a.seed)
    exp = new_dir(RUNS / "explore", time.strftime("%Y-%m-%dT%H-%M-%S") + "_" + Path(a.spec).stem)
    rows = []
    for i in range(a.runs):
        sp, label = base, {}
        for k, dist in pert:
            v = S.draw(dist, rng)
            sp = S.set_path(sp, k, v)
            label[k] = round(v, 3) if isinstance(v, float) else v
        seed = rng.randrange(10**6)
        out, s = run_one(a.spec, sp, seed, a.dry, a.sandbox, parent=exp, quiet=True, fresh=a.fresh)
        rows.append({**{k: json.dumps(v) for k, v in label.items()}, **s, "interest": interest(s)})
        rows.sort(key=lambda r: -r["interest"])
        write_table(exp, rows, extra_cols=tuple(label))
    print(f"explore dir: {exp}")


def cmd_score(a):
    print(json.dumps(scorer.score(a.run)["summary"], indent=1))


def cmd_show(a):
    d = Path(a.run)
    res = json.loads((d / "score.json").read_text()) if (d / "score.json").exists() else scorer.score(d)
    print(json.dumps(res["summary"], indent=1))
    ev = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines()]
    keep = {"enact", "repeal", "vetoed", "law_error", "patched", "ruling", "rename", "story", "proposal_failed"}
    print("\nTimeline:")
    for e in ev:
        if e["type"] in keep:
            print(f"  r{e['round'] + 1} {e['type']}: " + json.dumps({k: v for k, v in e["data"].items() if k not in ("code", "diff")})[:200])
    print("\nGoal scores:")
    for aid, g in res["goals"].items():
        print(f"  {aid}: {g['goal']} -> {g['score']}")


def cmd_view(a):
    """The story page: a group-chat replay of the run with message inboxes and the world panel."""
    from charter import viewer
    out = viewer.build(a.run, a.out)
    print(f"story: {out}")
    if a.open:
        import webbrowser
        webbrowser.open(out.resolve().as_uri())


def main(argv=None):
    load_env()
    ap = argparse.ArgumentParser(prog="python -m charter", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, seeds=False):
        p.add_argument("spec")
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--set", action="append", default=[], help="explicit choice, e.g. constitution=council (repeatable)")
        p.add_argument("--dry", action="store_true", help="scripted bots, no model calls")
        p.add_argument("--sandbox", choices=["docker", "off"], default="docker")
        p.add_argument("--fast", action="store_true", help="simultaneous turns: everyone decides from the same view, model calls in parallel")
        p.add_argument("--fresh", action="store_true", help="a separate run in a new timestamped directory (default: stable directory; "
                                                             "skip if complete, resume if not)")

    p = sub.add_parser("generate"); common(p); p.add_argument("--out"); p.set_defaults(fn=cmd_generate)
    p = sub.add_parser("run"); common(p); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("sweep"); common(p); p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--vary", action="append", default=[], help="key=v1,v2 (repeatable; grid over all)"); p.set_defaults(fn=cmd_sweep)
    p = sub.add_parser("explore"); common(p); p.add_argument("--runs", type=int, default=8)
    p.add_argument("--perturb", action="append", default=[], help="key=<distribution YAML> (repeatable)"); p.set_defaults(fn=cmd_explore)
    p = sub.add_parser("resume"); p.add_argument("run"); p.add_argument("--sandbox", choices=["docker", "off"], default="docker")
    p.set_defaults(fn=cmd_resume)
    p = sub.add_parser("score"); p.add_argument("run"); p.set_defaults(fn=cmd_score)
    p = sub.add_parser("show"); p.add_argument("run"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("report"); p.add_argument("run"); p.set_defaults(fn=lambda a: print(__import__("charter.report", fromlist=["build"]).build(a.run)))
    p = sub.add_parser("view"); p.add_argument("run"); p.add_argument("--out"); p.add_argument("--open", action="store_true")
    p.set_defaults(fn=cmd_view)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
