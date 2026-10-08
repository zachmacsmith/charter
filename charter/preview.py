"""Prompt preview (docs/ARCHITECTURE.md P7.2, review 02 section 5 item 13): exactly what agents would see, rendered from the sections
registry (charter/sections.py), with token counts per section and per layer against the budgets. Replaces the hand-committed
prompt_preview.md snapshot.

    python -m charter preview society --seed 1 [--agent Ike | --class legislator] [--layer core|manual|legacy|observer|all]
        [--set key=value ...] [--rounds K] [--out DIR] [--json FILE] [--against GIT_REV]

The world is the one `run` would play: generated from the spec and seed, set up by the runner itself (constitution, statutes,
start laws, setup interventions), then K scripted rounds (--rounds K, default 0; the free scripted bots, never a model call). The
kernel is restored from the run's checkpoint after K rounds, exactly as a resume restores it, so the core prompt shown is the one
the agent gets in round K + 1 (the runner's prepare() renders it from the same state).

Layers (sections.LAYERS): core (context.core_prompt, fitted to budgets.core), manual (context.build_manual, each section at most
budgets.lookup), legacy (the context-off system prompt), observer (the secret observer's prompt, when the world has one). Default:
the layers this world's agents see (core and manual with the context module on, else legacy; plus observer when there is one).
Agents: --agent ID (repeatable), --class C (repeatable), default the first agent of each class.

Output: the texts and per-section token tables on stdout; with --out DIR, one file per agent and layer (DIR/<agent>.<layer>.md)
and DIR/summary.md (the tables), with only the summary printed. Tokens are context.tokens (len // 4).

--against REV renders the same preview on another git revision (a temporary worktree, charter/difftest.py's Revision; this file's
code runs against that tree's modules in a subprocess) and prints a unified diff per agent and layer; exit status 1 if any differ.

goals.common_texts (Leaker's common text, version 2) uses `seen_texts` here: what each agent's prompt layers show at run start.
"""
from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

LAYER_CHOICES = ("core", "manual", "legacy", "observer", "all")


# ---------------------------------------------------------------------------------------------------------------- the world

@contextmanager
def world(spec, seed: int, sets=(), rounds: int = 0):
    """(inst, k) as the runner has them before round `rounds` + 1: generated, set up by runner.run with the scripted policy for
    `rounds` rounds (no model calls, the shared archive never published), the kernel restored from that checkpoint. While the
    context is open the run's frozen shared archive is bound, so archive reads see what the run saw."""
    from charter import agents as AG
    from charter import archive
    from charter import events as EV
    from charter import generator, runner
    from charter import interventions as IV
    from charter import spec as S
    from charter.kernel import Kernel
    sp = S.apply_overrides(S.load(spec), list(sets))
    tmp = Path(tempfile.mkdtemp(prefix="charter_preview_"))
    try:
        inst = generator.generate(sp, seed)
        n = max(0, min(int(rounds), int(inst["rounds"])))
        inst["run_id"] = "preview"
        out = runner.run(inst, AG.ScriptedPolicy(seed), tmp / "run", log=lambda *x: None, until=n, keep_checkpoints="all",
                         publish_archive=False)
        ck = runner.load_checkpoint(out, out / runner.CKPT_DIR / runner.ckpt_name(n))
        inst = generator.generate(sp, seed)                             # a fresh copy restored the way a resume restores it
        inst["run_id"] = "preview"
        k = Kernel(inst, None)
        k.restore_state(ck["kernel"])
        EV.restore(k, inst, {a["id"]: a for a in inst["agents"]})
        IV.restore(k, inst)
        fz = archive.Frozen.open(out, inst["spec"], resume=True, publish=False)
        if fz is None:
            yield inst, k
        else:
            fz.rebuild()
            with fz.bind(inst["spec"]):
                yield inst, k
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def default_layers(inst) -> list:
    from charter import context as CX
    return (["core", "manual"] if CX.enabled(inst) else ["legacy"]) + (["observer"] if inst.get("observer") else [])


def pick_agents(inst, ids=(), classes=()) -> list:
    """--agent / --class selection (in roster order); neither: the first agent of each class."""
    if ids or classes:
        known = {a["id"] for a in inst["agents"]}
        bad = [x for x in ids if x not in known]
        if bad:
            raise SystemExit(f"unknown agent(s) {bad}; this world has {sorted(known)}")
        got = [a for a in inst["agents"] if a["id"] in ids or a["cls"] in classes]
        if not got:
            raise SystemExit(f"no agent of class {list(classes)}; classes here: {sorted({a['cls'] for a in inst['agents']})}")
        return got
    seen, out = set(), []
    for a in inst["agents"]:
        if a["cls"] not in seen:
            seen.add(a["cls"])
            out.append(a)
    return out


# ---------------------------------------------------------------------------------------------------------------- rendering

def _core(inst, k, a) -> dict:
    """The core prompt (context.core_prompt, verbatim) and its sections as `sections.fit` sizes them (clip rows cut to the room
    the others leave)."""
    from charter import composition as CP
    from charter import context as CX
    from charter import sections as SC
    text = CX.core_prompt(inst, a, k)
    aid, budget = a["id"], int(CX.cfg(inst)["budgets"]["core"])
    rights = k.w["agents"][aid]["rights"] if k is not None and aid in k.w["agents"] else a.get("rights", [])
    v = SC.view(inst, k, a, rights, "core")
    parts = [(key, t) for key, t in CP.apply(inst, a, SC.render("core", v), "core", default_after="goal") if t or key == "overview"]
    by = {s.key: s for s in SC.rows("core")}
    fixed = sum(CX.tokens(t.strip("\n")) for key, t in parts if not (key in by and by[key].cut == "clip"))
    secs, cut = [], 0
    for key, t in parts:
        s = by.get(key)
        if s is not None and s.cut == "clip":                          # as sections.fit: clip rows rendered into the room left
            room = max(200, budget - fixed - 10)
            t, n = CX.clip(s.render(v), min(room, s.budget) if s.budget else room, s.note)
            cut += n
        secs.append((key, t))
    return {"text": text, "tokens": CX.tokens(text), "budget": budget, "trimmed": cut,
            "sections": [[key, CX.tokens(t)] for key, t in secs]}


def _manual(inst, k, a) -> dict:
    from charter import context as CX
    secs = CX.build_manual(inst, k, a["id"])
    text = "\n\n".join(f"## {t}\n\n{x}" for t, x in secs)
    return {"text": text, "tokens": sum(CX.tokens(x) for _, x in secs), "budget": int(CX.cfg(inst)["budgets"]["lookup"]),
            "budget_per": "section", "sections": [[t, CX.tokens(x)] for t, x in secs]}


def _joined(inst, a, layer: str) -> dict:
    from charter import context as CX
    from charter import sections as SC
    if layer == "observer":
        v = SC.view(inst, None, inst["observer"], (), "observer")
    else:
        v = SC.view(inst, None, a, a.get("rights", []), "legacy")
    secs = SC.render(layer, v)
    text = SC.join(layer, secs)
    return {"text": text, "tokens": CX.tokens(text), "budget": None, "sections": [[key, CX.tokens(t)] for key, t in secs]}


def render(inst, k, a, layers) -> dict:
    """{layer: {"text", "tokens", "budget", "sections": [[key, tokens]], ...}} for one agent (observer: the world's observer)."""
    out = {}
    for layer in layers:
        if layer == "core":
            out[layer] = _core(inst, k, a)
        elif layer == "manual":
            out[layer] = _manual(inst, k, a)
        elif layer == "observer":
            if inst.get("observer"):
                out[layer] = _joined(inst, a, "observer")
        else:
            out[layer] = _joined(inst, a, layer)
    return out


def seen_texts(inst, a, k=None) -> list:
    """The texts this agent's prompt layers show (context on: the core prompt and every manual section; off: the legacy system
    prompt, which is what agents.system_prompt gives). goals.common_texts intersects them over the agents."""
    from charter import agents as AG
    from charter import context as CX
    if CX.enabled(inst):
        return [CX.core_prompt(inst, a, k)] + [x for _, x in CX.build_manual(inst, k, a["id"])]
    return [AG.system_prompt(inst, a)]


def collect(spec, seed, sets=(), rounds=0, agents=(), classes=(), layer=None) -> dict:
    """The whole preview as data (what --json writes and --against compares)."""
    with world(spec, seed, sets, rounds) as (inst, k):
        layers = default_layers(inst) if layer is None else \
            (["core", "manual", "legacy", "observer"] if layer == "all" else [layer])
        rows = []
        for a in pick_agents(inst, agents, classes):
            agent_layers = [x for x in layers if x != "observer"]
            if agent_layers:
                rows.append({"id": a["id"], "cls": a["cls"], "model": a.get("model"), "layers": render(inst, k, a, agent_layers)})
        if "observer" in layers and inst.get("observer"):
            o = inst["observer"]
            rows.append({"id": o.get("id", "observer"), "cls": "observer", "model": o.get("model"),
                         "layers": render(inst, k, o, ["observer"])})
        return {"spec": str(spec), "seed": seed, "sets": list(sets), "rounds": rounds, "layers": layers, "agents": rows}


# ---------------------------------------------------------------------------------------------------------------- text output

def _budget(L: dict) -> str:
    if L.get("budget") is None:
        return f"{L['tokens']} tokens (no budget)"
    if L.get("budget_per") == "section":
        big = max((n for _, n in L["sections"]), default=0)
        return f"{L['tokens']} tokens in {len(L['sections'])} sections; largest {big} of {L['budget']} per section (lookup budget)"
    over = " OVER BUDGET" if L["tokens"] > L["budget"] else ""
    trim = f", {L['trimmed']} trimmed from clip sections" if L.get("trimmed") else ""
    return f"{L['tokens']} / {L['budget']} tokens{trim}{over}"


def summary(data: dict) -> str:
    sets = " ".join(f"--set {x}" for x in data["sets"])
    lines = [f"# Prompt preview: {data['spec']} --seed {data['seed']}" + (f" {sets}" if sets else ""),
             "", f"Generated by `python -m charter preview`; what agents see before round {data['rounds'] + 1}"
             + (f" (after {data['rounds']} scripted rounds)" if data["rounds"] else "") + ". Tokens: len // 4."]
    for r in data["agents"]:
        lines += ["", f"## {r['id']} ({r['cls']}, {r['model']})"]
        for layer, L in r["layers"].items():
            lines += ["", f"### {layer}: {_budget(L)}", "", "| section | tokens |", "|---|---|"]
            lines += [f"| {key} | {n} |" for key, n in L["sections"]]
    return "\n".join(lines) + "\n"


def full(data: dict) -> str:
    out = [summary(data)]
    for r in data["agents"]:
        for layer, L in r["layers"].items():
            out.append(f"\n---\n\n# {r['id']}: {layer}\n\n```\n{L['text']}\n```\n")
    return "".join(out)


def write_dir(data: dict, d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.md").write_text(summary(data))
    for r in data["agents"]:
        for layer, L in r["layers"].items():
            (d / f"{r['id']}.{layer}.md").write_text(L["text"])


# ---------------------------------------------------------------------------------------------------------------- --against

WORKER = r'''
import json, sys, types
src_path, args, out = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
mod = types.ModuleType("charter_preview_ext")
mod.__file__ = src_path
sys.modules[mod.__name__] = mod
exec(compile(open(src_path).read(), src_path, "exec"), mod.__dict__)
data = mod.collect(**args)
open(out, "w").write(json.dumps(data, default=str))
'''


def collect_at(rev: str, args: dict, repo: Path | None = None) -> tuple[dict, str]:
    """collect(**args) on another git revision: its tree in a temporary worktree, this file's code run against its modules."""
    from charter import difftest as DT
    repo = Path(repo) if repo else DT.repo_root()
    tmp = Path(tempfile.mkdtemp(prefix="charter_preview_rev_"))
    rv = None
    try:
        rv = DT.Revision(repo, rev, tmp, "against")
        out = tmp / "preview.json"
        r = subprocess.run([sys.executable, "-c", WORKER, str(Path(__file__).resolve()), json.dumps(args), str(out)],
                           cwd=rv.root, env=DT._env(rv.root), capture_output=True, text=True)
        if r.returncode or not out.exists():
            raise SystemExit(f"preview on {rv.desc} failed:\n{(r.stderr or r.stdout).strip()[-3000:]}")
        return json.loads(out.read_text()), rv.desc
    finally:
        if rv is not None:
            rv.cleanup()
        shutil.rmtree(tmp, ignore_errors=True)


def diff(base: dict, head: dict, base_label="base", head_label="head") -> list:
    """[(agent, layer, unified diff lines)] for every agent and layer whose text differs (or is present on one side only)."""
    out = []
    ba = {r["id"]: r for r in base["agents"]}
    ha = {r["id"]: r for r in head["agents"]}
    for aid in list(ba) + [x for x in ha if x not in ba]:
        bl = (ba.get(aid) or {}).get("layers", {})
        hl = (ha.get(aid) or {}).get("layers", {})
        for layer in list(bl) + [x for x in hl if x not in bl]:
            a, b = (bl.get(layer) or {}).get("text"), (hl.get(layer) or {}).get("text")
            if a == b:
                continue
            lines = list(difflib.unified_diff((a or "").splitlines(), (b or "").splitlines(), f"{base_label}/{aid}.{layer}",
                                              f"{head_label}/{aid}.{layer}", lineterm=""))
            out.append((aid, layer, lines or [f"(present on {'head' if a is None else 'base'} only)"]))
    return out


# ---------------------------------------------------------------------------------------------------------------- CLI

def add_arguments(p: argparse.ArgumentParser):
    p.add_argument("spec", help="preset name (E0..E7, society, ...) or a YAML spec path")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--agent", action="append", default=[], help="agent id to show (repeatable)")
    p.add_argument("--class", dest="cls", action="append", default=[], help="show every agent of this class (repeatable)")
    p.add_argument("--layer", choices=LAYER_CHOICES, default=None,
                   help="default: the layers this world's agents see (core+manual with the context module on, else legacy; observer "
                        "if the world has one)")
    p.add_argument("--set", action="append", default=[], help="spec override, e.g. constitution=council (repeatable)")
    p.add_argument("--rounds", type=int, default=0, help="play K scripted rounds first (no model calls); default 0")
    p.add_argument("--out", help="write <agent>.<layer>.md files and summary.md here; print only the summary")
    p.add_argument("--json", help="also write the preview as JSON here")
    p.add_argument("--against", help="git revision to compare with: unified diff of the rendered texts (exit 1 if any differ)")


def cmd(a) -> int:
    args = {"spec": a.spec, "seed": a.seed, "sets": list(a.set), "rounds": a.rounds, "agents": list(a.agent),
            "classes": list(a.cls), "layer": a.layer}
    data = collect(**args)
    if a.json:
        Path(a.json).write_text(json.dumps(data, indent=1, default=str) + "\n")
    if a.against:
        other, desc = collect_at(a.against, args)
        ds = diff(other, data, a.against, "WORKTREE")
        print(f"preview diff: {desc} vs WORKTREE, {a.spec} --seed {a.seed}, "
              f"{len(data['agents'])} agent(s), layers {', '.join(data['layers'])}")
        if not ds:
            print("no differences")
            return 0
        for aid, layer, lines in ds:
            print(f"\n== {aid} {layer}")
            print("\n".join(lines))
        print(f"\n{len(ds)} text(s) differ")
        return 1
    if a.out:
        write_dir(data, Path(a.out))
        print(summary(data), end="")
        print(f"\nwritten to {a.out}")
    else:
        print(full(data), end="")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m charter preview", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(ap)
    raise SystemExit(cmd(ap.parse_args(argv)))


if __name__ == "__main__":
    main()
