"""Differential test: run the same scripted worlds on two code revisions and report exactly where they diverge.

    python -m charter difftest --base main --head WORKTREE --presets E0,E1,E2,E3,E4,E5,E6,E7,society --seeds 1,2 --rounds 3
        [--set key=value ...] [--head-set key=value ...] [--ignore-field cause --ignore-field id] [--ignore-type new_event]
        [--rename old_key=new_key] [--rename-type old_type=new_type] [--ignore-code-acts] [--json report.json] [--keep DIR] [--jobs N]

Each revision runs from its own tree: a git revision is checked out into a temporary `git worktree` (removed afterwards); WORKTREE
means the current checkout, uncommitted changes included. Every preset/seed runs in its own subprocess whose cwd and PYTHONPATH are
that tree, so the two revisions' modules never mix. Runs are offline: the scripted policy (agents.ScriptedPolicy), the shared archive
off, API keys stripped from the subprocess environment and LLMPolicy disabled there.

Compared per case: instance.json, events.jsonl (first diverging event, side by side, and counts per event type), snapshots.json
(differing fields per round), ground_truth.json and score.json (goal scores per agent and goal component, summary, metrics).

Normalisation, applied to both sides before comparing:
  --ignore-field NAME   drop dict keys named NAME at any depth (e.g. `cause`, `ts`), or a dotted path from a record's root
                        (e.g. `data.cause` for events, `values.Alma` for snapshots)
  --ignore-type TYPE    drop events of this type (an intended new event type); event ids then shift, so add --ignore-field id
  --rename OLD=NEW      rename dict keys OLD -> NEW on the base side (a renamed field)
  --rename-type OLD=NEW rename event types OLD -> NEW on the base side
  --float-tol X         numbers within X compare equal (default 0: exact)
  --ignore-code-acts    the default code (charter/code, spec code.enabled): drop the monitor-only `code_act` records and renumber
                        the remaining events' ids (whole strings and ids inside text, in every file but instance.json, which is
                        written before any event), drop the Acts' law records
                        (ground_truth laws A1, A2, ...) and the instance's `code` record and spec `code` keys. Use it with
                        `--head-set code.enabled=true` (an override for the head side only: an older base rejects the key) to check
                        that `code: today` reproduces the code-off world.
Exit status: 0 when no case diverges, 1 otherwise.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

PKG = Path(__file__).resolve().parent
FILES = ("instance.json", "events.jsonl", "snapshots.json", "ground_truth.json", "score.json")
MAX_PATHS = 20                                    # differing paths listed per file/round (the count is always complete)

# The worker runs inside the revision's tree. It only uses APIs that predate this harness (spec.load/apply_overrides,
# generator.generate, runner.run, agents.ScriptedPolicy, scorer.score), so older revisions can be run too.
WORKER = r'''
import json, sys, time
from pathlib import Path
args = json.loads(sys.argv[1])
from charter import agents as AG, generator, runner, scorer, spec as S
def _no_llm(*a, **k):
    raise RuntimeError("difftest: LLMPolicy is disabled; runs must use the scripted policy")
AG.LLMPolicy = _no_llm
t0 = time.time()
sp = S.apply_overrides(S.load(args["preset"]), list(args["sets"]) + ["shared_archive.enabled=false"])
inst = generator.generate(sp, args["seed"])
inst["run_id"] = args["run_id"]
policy = AG.ScriptedPolicy(args["seed"])
assert type(policy).__name__ == "ScriptedPolicy"
out = runner.run(inst, policy, Path(args["out"]), log=lambda *a: None)
scorer.score(out)                                       # writes score.json
print("DIFFTEST_RESULT " + json.dumps({"policy": type(policy).__name__, "seconds": round(time.time() - t0, 2),
                                       "out": str(out), "file": str(Path(AG.__file__).resolve())}))
'''


# ---------------------------------------------------------------------------------------------------------------- revisions

def git(repo: Path, *args, check=True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def repo_root(start: Path = PKG) -> Path:
    return Path(git(start, "rev-parse", "--show-toplevel"))


class Revision:
    """A source tree for one side: the current checkout (WORKTREE) or a temporary git worktree of a revision."""

    def __init__(self, repo: Path, rev: str, tmp: Path, label: str):
        self.repo, self.rev, self.label = repo, rev, label
        self.temp = None
        if rev.upper() == "WORKTREE":
            self.root, self.desc = repo, "WORKTREE (" + git(repo, "rev-parse", "--short", "HEAD") + " + uncommitted changes)"
        else:
            sha = git(repo, "rev-parse", "--verify", rev + "^{commit}")
            self.root = self.temp = tmp / f"tree_{label}"
            git(repo, "worktree", "add", "--detach", str(self.temp), sha)
            self.desc = f"{rev} ({sha[:9]})"

    def cleanup(self):
        if self.temp is not None:
            git(self.repo, "worktree", "remove", "--force", "--force", str(self.temp), check=False)
            shutil.rmtree(self.temp, ignore_errors=True)
            self.temp = None


def _env(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not re.search(r"API_KEY|TOKEN|SECRET", k, re.I)}
    env.update(PYTHONPATH=str(root), LLM_BACKEND="disabled-by-difftest", PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1",
               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")    # runs are parallel; no nested threading
    return env


def run_case(root: Path, preset: str, seed: int, sets: list[str], out: Path, timeout=3600) -> dict:
    """One scripted run of preset/seed in a subprocess rooted at `root`. Returns the worker's result record."""
    args = {"preset": preset, "seed": seed, "sets": sets, "out": str(out), "run_id": f"difftest_{preset}_s{seed}"}
    r = subprocess.run([sys.executable, "-c", WORKER, json.dumps(args)], cwd=root, env=_env(root), capture_output=True,
                       text=True, timeout=timeout)
    line = next((l for l in r.stdout.splitlines() if l.startswith("DIFFTEST_RESULT ")), None)
    if r.returncode or line is None:
        return {"error": (r.stderr or r.stdout).strip()[-3000:], "returncode": r.returncode}
    res = json.loads(line.split(" ", 1)[1])
    if res.get("policy") != "ScriptedPolicy":
        return {"error": f"worker used {res.get('policy')}, not ScriptedPolicy"}
    if not Path(res["file"]).is_relative_to(root.resolve()):            # the revision's own modules were imported
        return {"error": f"worker imported charter from {res['file']}, outside {root}"}
    return res


# ---------------------------------------------------------------------------------------------------------------- normalising

class Norm:
    def __init__(self, ignore_fields=(), ignore_types=(), renames=None, type_renames=None, float_tol=0.0, code_acts=False):
        self.code_acts = bool(code_acts)                                # --ignore-code-acts (strip_code_acts)
        self.names = {f for f in ignore_fields if "." not in f}
        self.paths = {tuple(f.split(".")) for f in ignore_fields if "." in f}
        self.ignore_types = set(ignore_types)
        self.renames = dict(renames or {})
        self.type_renames = dict(type_renames or {})
        self.tol = float(float_tol or 0)

    def clean(self, x, base=False, path=()):
        if isinstance(x, dict):
            out = {}
            for k, v in x.items():
                k = self.renames.get(k, k) if base else k
                if k in self.names or path + (k,) in self.paths:
                    continue
                out[k] = self.clean(v, base, path + (k,))
            return out
        if isinstance(x, list):
            return [self.clean(v, base, path) for v in x]
        return x

    def events(self, evs, base=False):
        out = []
        for e in evs:
            if base and isinstance(e, dict) and e.get("type") in self.type_renames:
                e = {**e, "type": self.type_renames[e["type"]]}
            if isinstance(e, dict) and e.get("type") in self.ignore_types:
                continue
            out.append(self.clean(e, base))
        return out

    def eq(self, a, b) -> bool:
        if self.tol and isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) \
                and not isinstance(b, bool):
            return abs(a - b) <= self.tol
        return a == b


def deep_diff(a, b, norm: Norm, path="", out=None, limit=MAX_PATHS):
    """[(path, a, b)] for every differing leaf (only the first `limit` kept); returns (list, total count)."""
    out = [] if out is None else out
    total = 0
    if isinstance(a, dict) and isinstance(b, dict):
        for k in list(a) + [k for k in b if k not in a]:
            p = f"{path}.{k}" if path else str(k)
            if k not in a or k not in b:
                total += 1
                if len(out) < limit:
                    out.append((p, a.get(k, "<missing>"), b.get(k, "<missing>")))
            else:
                total += deep_diff(a[k], b[k], norm, p, out, limit)[1]
        return out, total
    if isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            p = f"{path}[{i}]"
            if i >= len(a) or i >= len(b):
                total += 1
                if len(out) < limit:
                    out.append((p, a[i] if i < len(a) else "<missing>", b[i] if i < len(b) else "<missing>"))
            else:
                total += deep_diff(a[i], b[i], norm, p, out, limit)[1]
        return out, total
    if not norm.eq(a, b):
        if len(out) < limit:
            out.append((path or "<root>", a, b))
        return out, 1
    return out, 0


def _paths(diffs):
    return [{"path": p, "base": a, "head": b} for p, a, b in diffs]


# ---------------------------------------------------------------------------------------------------------------- comparing

def _load(d: Path, name: str):
    f = d / name
    if not f.exists():
        return None
    text = f.read_text().replace(str(d.resolve()), "<RUN>").replace(str(d), "<RUN>")
    if name.endswith(".jsonl"):
        return [json.loads(l) for l in text.splitlines() if l.strip()]
    return json.loads(text)


def compare_events(a: list, b: list, norm: Norm) -> dict:
    na, nb = norm.events(a, base=True), norm.events(b)
    ca, cb = Counter(e.get("type") for e in na), Counter(e.get("type") for e in nb)
    counts = {t: {"base": ca.get(t, 0), "head": cb.get(t, 0)} for t in sorted(set(ca) | set(cb))}
    first = None
    for i in range(max(len(na), len(nb))):
        ea = na[i] if i < len(na) else None
        eb = nb[i] if i < len(nb) else None
        if ea is None or eb is None or deep_diff(ea, eb, norm, limit=0)[1]:
            ref = ea or eb
            first = {"index": i, "round": ref.get("round"), "type_base": (ea or {}).get("type"),
                     "type_head": (eb or {}).get("type"), "base": ea, "head": eb,
                     "fields": _paths(deep_diff(ea, eb, norm)[0]) if ea is not None and eb is not None else []}
            break
    n_diff = sum(1 for i in range(max(len(na), len(nb)))
                 if i >= len(na) or i >= len(nb) or deep_diff(na[i], nb[i], norm, limit=0)[1])
    return {"identical": first is None, "n_base": len(na), "n_head": len(nb), "n_differing": n_diff, "first": first,
            "counts": counts, "count_changes": {t: c for t, c in counts.items() if c["base"] != c["head"]}}


def compare_snapshots(a: list, b: list, norm: Norm) -> dict:
    na, nb = norm.clean(a, base=True), norm.clean(b)
    rounds = []
    for i in range(max(len(na), len(nb))):
        sa = na[i] if i < len(na) else None
        sb = nb[i] if i < len(nb) else None
        if sa is None or sb is None:
            rounds.append({"index": i, "round": (sa or sb).get("round"), "missing": "base" if sa is None else "head"})
            continue
        fields = {}
        for k in list(sa) + [k for k in sb if k not in sa]:
            if k not in sa or k not in sb:
                fields[k] = {"count": 1, "paths": _paths([(k, sa.get(k, "<missing>"), sb.get(k, "<missing>"))])}
                continue
            d, n = deep_diff(sa[k], sb[k], norm, k, limit=5)
            if n:
                fields[k] = {"count": n, "paths": _paths(d)}
        if fields:
            rounds.append({"index": i, "round": sa.get("round"), "fields": fields})
    return {"identical": not rounds, "n_base": len(na), "n_head": len(nb), "rounds": rounds}


def compare_score(a: dict, b: dict, norm: Norm) -> dict:
    na, nb = norm.clean(a, base=True), norm.clean(b)
    goals = {}
    ga, gb = na.get("goals", {}) or {}, nb.get("goals", {}) or {}
    for aid in sorted(set(ga) | set(gb)):
        x, y = ga.get(aid), gb.get(aid)
        if x is None or y is None:
            goals[aid] = {"missing": "base" if x is None else "head"}
            continue
        d, n = deep_diff(x, y, norm)
        if n:
            goals[aid] = {"goal": y.get("goal", x.get("goal")), "score": {"base": x.get("score"), "head": y.get("score")},
                          "paths": _paths(d)}
    rest = {}
    for k in sorted(set(na) | set(nb)):
        if k == "goals":
            continue
        d, n = deep_diff(na.get(k, "<missing>"), nb.get(k, "<missing>"), norm, k)
        if n:
            rest[k] = {"count": n, "paths": _paths(d)}
    return {"identical": not goals and not rest, "goals": goals, "other": rest}


def compare_plain(a, b, norm: Norm) -> dict:
    d, n = deep_diff(norm.clean(a, base=True), norm.clean(b), norm)
    return {"identical": n == 0, "count": n, "paths": _paths(d)}


CODE_EVENT = "code_act"
ACT_ID = re.compile(r"^A[1-9]\d*$")


EVENT_ID = re.compile(r"\be[1-9]\d*\b")


def _remap(x, m: dict):
    """Old event ids -> new ones in x: whole strings, and ids inside text (an action result's "Posted (e5)")."""
    if isinstance(x, str):
        return m[x] if x in m else EVENT_ID.sub(lambda g: m.get(g.group(0), g.group(0)), x) if "e" in x else x
    if isinstance(x, dict):
        return {m.get(k, k) if isinstance(k, str) else k: _remap(v, m) for k, v in x.items()}
    if isinstance(x, list):
        return [_remap(v, m) for v in x]
    return x


def strip_code_acts(files: dict) -> dict:
    """--ignore-code-acts on one side's loaded files ({name: data}): see the module docstring."""
    files = dict(files)
    evs = files.get("events.jsonl")
    if evs is not None:
        kept = [e for e in evs if not (isinstance(e, dict) and e.get("type") == CODE_EVENT)]
        m = {e["id"]: f"e{i}" for i, e in enumerate(kept, 1) if isinstance(e, dict) and e.get("id") not in (None, f"e{i}")}
        files["events.jsonl"] = kept
        if m:
            files = {n: (_remap(v, m) if v is not None and n != "instance.json" else v) for n, v in files.items()}   # the
            # instance is written before any event (its texts' "e12" are examples, not ids)
    inst = files.get("instance.json")
    if isinstance(inst, dict):
        inst = {k: v for k, v in inst.items() if k != "code"}
        for key in ("spec", "spec_source"):
            if isinstance(inst.get(key), dict):
                inst[key] = {k: v for k, v in inst[key].items() if k != "code"}
        files["instance.json"] = inst
    gt = files.get("ground_truth.json")
    if isinstance(gt, dict) and isinstance(gt.get("laws"), dict):
        files["ground_truth.json"] = {**gt, "laws": {k: v for k, v in gt["laws"].items() if not ACT_ID.match(k)}}
    return files


def compare_dirs(base: Path, head: Path, norm: Norm | None = None) -> dict:
    """Compare two run directories file by file."""
    norm = norm or Norm()
    base, head = Path(base), Path(head)
    side = {"base": {n: _load(base, n) for n in FILES}, "head": {n: _load(head, n) for n in FILES}}
    if norm.code_acts:
        side = {s: strip_code_acts(f) for s, f in side.items()}
    files = {}
    for name in FILES:
        a, b = side["base"][name], side["head"][name]
        if a is None or b is None:
            files[name] = {"identical": a is None and b is None, "missing": [s for s, x in (("base", a), ("head", b)) if x is None]}
        elif name == "events.jsonl":
            files[name] = compare_events(a, b, norm)
        elif name == "snapshots.json":
            files[name] = compare_snapshots(a, b, norm)
        elif name == "score.json":
            files[name] = compare_score(a, b, norm)
        else:
            files[name] = compare_plain(a, b, norm)
    return {"identical": all(f["identical"] for f in files.values()), "files": files}


# ---------------------------------------------------------------------------------------------------------------- driver

def difftest(base: str, head: str, presets, seeds, rounds=None, sets=(), norm: Norm | None = None, repo: Path | None = None,
             keep: Path | None = None, jobs: int = 0, log=print, head_sets=()) -> dict:
    repo = Path(repo) if repo else repo_root()
    norm = norm or Norm()
    sets = ([f"rounds={rounds}"] if rounds else []) + list(sets)
    tmp = Path(tempfile.mkdtemp(prefix="charter_difftest_"))
    work = Path(keep) if keep else tmp / "runs"
    revs = []
    t0 = time.time()
    try:
        revs = [Revision(repo, base, tmp, "base")]
        revs.append(Revision(repo, head, tmp, "head"))
        cases = [(p, s) for p in presets for s in seeds]
        jobs = jobs or min(8, os.cpu_count() or 2)
        log(f"difftest: base {revs[0].desc} vs head {revs[1].desc}; {len(cases)} case(s) x 2 runs, {jobs} at a time")
        futs = {}
        with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
            for p, s in cases:
                for rv in revs:
                    out = work / rv.label / f"{p}_s{s}"
                    if out.exists():
                        shutil.rmtree(out)
                    futs[(p, s, rv.label)] = ex.submit(run_case, rv.root, p, s,
                                                       sets + (list(head_sets) if rv.label == "head" else []), out)
            results = {k: f.result() for k, f in futs.items()}
        report = {"base": revs[0].desc, "head": revs[1].desc, "sets": sets, "head_sets": list(head_sets),
                  "normalise": {"ignore_fields": sorted(norm.names | {".".join(p) for p in norm.paths}),
                                "ignore_types": sorted(norm.ignore_types), "renames": norm.renames,
                                "type_renames": norm.type_renames, "float_tol": norm.tol, "code_acts": norm.code_acts},
                  "cases": []}
        for p, s in cases:
            ra, rb = results[(p, s, "base")], results[(p, s, "head")]
            case = {"preset": p, "seed": s, "seconds": {"base": ra.get("seconds"), "head": rb.get("seconds")}}
            if "error" in ra or "error" in rb:
                case.update(identical=False, error={k: r["error"] for k, r in (("base", ra), ("head", rb)) if "error" in r})
            else:
                case.update(compare_dirs(Path(ra["out"]), Path(rb["out"]), norm))
            report["cases"].append(case)
            log(f"  {p} seed {s}: " + ("identical" if case["identical"] else "ERROR" if "error" in case else "DIVERGES")
                + f" ({case['seconds']['base']}s / {case['seconds']['head']}s)")
        report["identical"] = all(c["identical"] for c in report["cases"])
        report["seconds"] = round(time.time() - t0, 1)
        if keep:
            report["runs"] = str(work)
        return report
    finally:
        for rv in revs:
            rv.cleanup()
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------------------------------------------- text report

def _short(x, n=160) -> str:
    s = json.dumps(x, sort_keys=True, default=str) if not isinstance(x, str) else x
    return s if len(s) <= n else s[:n - 3] + "..."


def text_report(rep: dict) -> str:
    L = [f"Charter difftest: base {rep['base']}  vs  head {rep['head']}", f"overrides: {' '.join(rep['sets']) or '(none)'}"]
    if rep.get("head_sets"):
        L.append(f"head-only overrides: {' '.join(rep['head_sets'])}")
    nm = rep["normalise"]
    if any(nm.get(k) for k in ("ignore_fields", "ignore_types", "renames", "type_renames", "float_tol", "code_acts")):
        L.append("normalised: " + "; ".join(f"{k}={v}" for k, v in nm.items() if v))
    n_div = sum(not c["identical"] for c in rep["cases"])
    verdict = "no divergence" if rep["identical"] else f"{n_div} of {len(rep['cases'])} case(s) diverge"
    L.append(f"RESULT: {verdict} ({rep.get('seconds', '?')}s)")
    for c in rep["cases"]:
        L.append("")
        L.append(f"== {c['preset']} seed {c['seed']}: {'identical' if c['identical'] else 'DIVERGES'}"
                 f"  [{c['seconds']['base']}s base, {c['seconds']['head']}s head]")
        if "error" in c:
            for side, err in c["error"].items():
                L.append(f"  {side} run failed:\n    " + "\n    ".join(err.splitlines()[-12:]))
            continue
        if c["identical"]:
            continue
        for name, f in c["files"].items():
            if f["identical"]:
                continue
            if "missing" in f:
                L.append(f"  {name}: missing on {', '.join(f['missing'])}")
            elif name == "events.jsonl":
                fe = f["first"]
                L.append(f"  events.jsonl: {f['n_base']} base / {f['n_head']} head events, {f['n_differing']} positions differ")
                L.append(f"    FIRST DIVERGENCE: event #{fe['index']}, round {fe['round']}, "
                         f"type {fe['type_base']}" + (f" -> {fe['type_head']}" if fe['type_head'] != fe['type_base'] else ""))
                L.append(f"      base: {_short(fe['base'], 400)}")
                L.append(f"      head: {_short(fe['head'], 400)}")
                for d in fe["fields"]:
                    L.append(f"      {d['path']}: {_short(d['base'], 70)}  ->  {_short(d['head'], 70)}")
                if f["count_changes"]:
                    L.append("    counts per type (base -> head), changed only:")
                    for t, n in f["count_changes"].items():
                        L.append(f"      {t}: {n['base']} -> {n['head']}")
            elif name == "snapshots.json":
                L.append(f"  snapshots.json: {len(f['rounds'])} of {max(f['n_base'], f['n_head'])} snapshots differ")
                for r in f["rounds"][:10]:
                    if "missing" in r:
                        L.append(f"    round {r['round']}: missing on {r['missing']}")
                        continue
                    L.append(f"    round {r['round']}: " + ", ".join(f"{k} ({v['count']})" for k, v in r["fields"].items()))
                    for k, v in list(r["fields"].items())[:6]:
                        for d in v["paths"][:2]:
                            L.append(f"      {d['path']}: {_short(d['base'], 60)}  ->  {_short(d['head'], 60)}")
            elif name == "score.json":
                L.append("  score.json:")
                for aid, g in f["goals"].items():
                    if "missing" in g:
                        L.append(f"    {aid}: missing on {g['missing']}")
                        continue
                    L.append(f"    {aid} ({g['goal']}): score {g['score']['base']} -> {g['score']['head']}")
                    for d in g["paths"][:4]:
                        if d["path"] != "score":
                            L.append(f"      {d['path']}: {_short(d['base'], 60)}  ->  {_short(d['head'], 60)}")
                for k, v in f["other"].items():
                    L.append(f"    {k}: {v['count']} differing value(s), e.g. "
                             + "; ".join(f"{d['path']}: {_short(d['base'], 40)} -> {_short(d['head'], 40)}" for d in v["paths"][:3]))
            else:
                L.append(f"  {name}: {f['count']} differing value(s)")
                for d in f["paths"][:8]:
                    L.append(f"    {d['path']}: {_short(d['base'], 70)}  ->  {_short(d['head'], 70)}")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------------------------- CLI

def _pairs(xs, flag):
    out = {}
    for x in xs or []:
        k, sep, v = x.partition("=")
        if not sep or not k or not v:
            raise SystemExit(f"{flag} expects OLD=NEW, got {x!r}")
        out[k] = v
    return out


def add_arguments(p: argparse.ArgumentParser):
    p.add_argument("--base", required=True, help="git revision for the reference side")
    p.add_argument("--head", default="WORKTREE", help="git revision, or WORKTREE for the current checkout (default)")
    p.add_argument("--presets", default="E0,E1,E2,E3,E4,E5,E6,E7,society", help="comma-separated presets or spec paths")
    p.add_argument("--seeds", default="1,2", help="comma-separated seeds")
    p.add_argument("--rounds", type=int, default=None, help="rounds per run (default: the preset's)")
    p.add_argument("--set", action="append", default=[], help="spec override for both sides, e.g. turns=simultaneous (repeatable)")
    p.add_argument("--head-set", action="append", default=[], help="spec override for the head side only, e.g. code.enabled=true "
                   "(repeatable)")
    p.add_argument("--ignore-code-acts", action="store_true", help="drop the default code's code_act records (renumbering event "
                   "ids), its Act law records and the instance's code record")
    p.add_argument("--ignore-field", action="append", default=[], help="key name (any depth) or dotted path to drop (repeatable)")
    p.add_argument("--ignore-type", action="append", default=[], help="event type to drop (repeatable)")
    p.add_argument("--rename", action="append", default=[], help="OLD=NEW key rename applied to the base side (repeatable)")
    p.add_argument("--rename-type", action="append", default=[], help="OLD=NEW event type rename on the base side (repeatable)")
    p.add_argument("--float-tol", type=float, default=0.0, help="numeric tolerance (default exact)")
    p.add_argument("--json", help="write the JSON report here")
    p.add_argument("--text", help="also write the text report here")
    p.add_argument("--keep", help="keep the run directories under this path (default: temporary, removed)")
    p.add_argument("--jobs", type=int, default=0, help="parallel runs (default min(8, cpus))")


def cmd(a) -> int:
    norm = Norm(a.ignore_field, a.ignore_type, _pairs(a.rename, "--rename"), _pairs(a.rename_type, "--rename-type"), a.float_tol,
                code_acts=getattr(a, "ignore_code_acts", False))
    rep = difftest(a.base, a.head, [p for p in a.presets.split(",") if p], [int(s) for s in a.seeds.split(",") if s],
                   a.rounds, a.set, norm, keep=a.keep, jobs=a.jobs, log=lambda *x: print(*x, file=sys.stderr),
                   head_sets=getattr(a, "head_set", []) or [])
    txt = text_report(rep)
    print(txt, end="")
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1, default=str) + "\n")
    if a.text:
        Path(a.text).write_text(txt)
    return 0 if rep["identical"] else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m charter.difftest", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(ap)
    raise SystemExit(cmd(ap.parse_args(argv)))


if __name__ == "__main__":
    main()
