"""Continuing a published run (docs/data_format.md, "Continuing a published run").

    python -m charter fetch RUN_ID [--repo OWNER/NAME] [--revision vX.Y] [--out DIR]
        Downloads a published run's raw archive (catalog `raw`) and unpacks it into DIR/<spec>/<run_id> (default
        charter/out/_fetched), a run directory ready for replay, fork (via continue) and rerun.
    python -m charter continue RUN_DIR --at N [--rounds K] [--out DIR] [--apply iv.yaml] [--dry] [--replay strict|prompt-match]
        Plays a run on from round N (0-based: N complete rounds are kept) with the live policy: replays the record to round N
        into DIR/replay (rebuilding the checkpoints a published run does not have, and proving the state at N is the run's:
        `replay` compares events and snapshots byte for byte and every model prompt by hash), then forks that replay at N into
        DIR/branch (`fork --at N`), playing K rounds (default: to the end). --dry continues with the scripted bots instead of
        models (no model calls). When the replay does not reproduce the run under the current code, the same two steps run under
        the run's recorded git sha in a temporary worktree (charter/rerun.py), or continue refuses and says why.

Checkpoints are never published: they are pickles, and unpickling a downloaded file runs whatever code it names. The record
(instance.json, every model reply in calls.jsonl, sandbox outputs, the frozen archive and directories, interventions) holds
everything a replay needs, so the state after any round is rebuilt locally, from data, by the engine itself.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from charter import provenance as PV

FETCHED = Path(__file__).resolve().parent / "out" / "_fetched"


# ------------------------------------------------------------------ fetch
def catalog_row(run_id: str, repo: str, revision: str | None = None) -> dict:
    from charter import publish as PB
    rows = PB.remote_catalog(repo, revision)
    if not rows:
        raise SystemExit(f"no catalog on {repo}" + (f" at {revision}" if revision else ""))
    row = next((r for r in rows if r["run_id"] == run_id), None)
    if row is None:
        near = [r["run_id"] for r in rows if run_id.lower() in r["run_id"].lower()]
        raise SystemExit(f"run {run_id} is not in the catalog of {repo}" + (f" at {revision}" if revision else "")
                         + (f" (did you mean {', '.join(near[:5])}?)" if near else ""))
    return row


def fetch(run_id: str, repo: str | None = None, revision: str | None = None, out=None, log=print) -> Path:
    """Download and unpack a published run's raw archive into out/<spec>/<run_id>; returns the run directory."""
    from charter import publish as PB
    repo = repo or PB.DEFAULT_REPO
    row = catalog_row(run_id, repo, revision)
    out = Path(out) if out else FETCHED
    target = out / row["spec"] / Path(row["raw"]).name.removesuffix(".tar.gz")
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"{target} exists and is not empty")
    tmp = Path(tempfile.mkdtemp(prefix=".fetch-", dir=out if out.exists() else None))
    try:
        got = PB.fetch_raw(repo, row, tmp, revision=revision)
        if not (got / "instance.json").exists():
            raise SystemExit(f"the archive {row['raw']} holds no run directory {row['spec']}/{got.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.rmdir()
        shutil.move(str(got), str(target))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    meta = PV.read(target) or {}
    (target / "fetched.json").write_text(json.dumps({"repo": repo, "revision": revision, "raw": row["raw"], "run_id": run_id},
                                                    indent=1))
    log(f"fetched {repo}{'@' + revision if revision else ''} {row['raw']} -> {target}")
    if meta.get("git"):
        log(f"recorded code: git {str(meta['git'].get('sha'))[:12]} ({meta['git'].get('branch')})")
    log(f"next: python -m charter replay {target}   |   python -m charter continue {target} --at N [--rounds K]")
    return target


# ------------------------------------------------------------------ continue
def segment_sha(run, at: int) -> str | None:
    """The git sha of the run.json segment that played round at - 1 (the code the state at round `at` was made by)."""
    meta = PV.read(run) or {}
    segs = [s for s in meta.get("segments") or [] if s.get("first_round") is not None]
    seg = None
    for s in segs:
        if int(s["first_round"]) <= max(0, at - 1):
            seg = s
    git = (seg or {}).get("git") or meta.get("git") or {}
    return git.get("sha")


def _dry_factory(spec, dry, seed):
    from charter import __main__ as M
    return M.policy_for(spec, True, seed)


def continue_run(run, at: int, rounds: int | None = None, out=None, schedule=None, dry: bool = False, replay_mode: str = "strict",
                 log=print, worktree_root=None, sandbox=None) -> dict:
    """Replay `run` to round `at` (DIR/replay), check it reproduces the run, fork it at `at` (DIR/branch) and play `rounds` rounds
    (None: to the end) with the live policy (dry: scripted bots). Under the current code when the replay reproduces the run, else
    under the recorded sha in a worktree. Returns {replay, branch, code, replay_result}."""
    from charter import replay as RP
    run = Path(run).resolve()
    at = int(at)
    if not (run / "instance.json").exists():
        raise SystemExit(f"{run} is not a run directory (no instance.json)")
    if not (run / "calls.jsonl").exists():
        raise SystemExit(f"{run} has no calls.jsonl (a run from before model calls were recorded): its replies cannot be replayed, "
                         "so its state after a round cannot be rebuilt")
    played = len(json.loads((run / "snapshots.json").read_text()))
    if not 0 < at <= played:
        raise SystemExit(f"--at {at}: the run has {played} complete round(s); continue from 1..{played}")
    if out is None:
        out, n = run.parent / f"{run.name}_cont{at}", 2
        while out.exists():
            out, n = run.parent / f"{run.name}_cont{at}_{n}", n + 1
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty")
    out.mkdir(parents=True, exist_ok=True)
    rdir, bdir = out / "replay", out / "branch"
    log(f"[continue] replaying {run.name} to round {at} under the current code -> {rdir}")
    why = None
    try:
        res = RP.replay(run, rdir, to=at, sandbox=None, log=lambda *a: None)
        if not res["identical"]:
            why = f"the replay differs from the run: {json.dumps(res.get('first_difference'))[:300]}"
    except (RP.ReplayMiss, RP.ReplayDivergence) as e:
        res, why = None, f"{type(e).__name__}: {e}"
    if why is None:
        log(f"[continue] the replay reproduces rounds 1-{at} (events and snapshots identical); forking at round {at + 1}")
        from charter import __main__ as M
        sched = []
        if schedule:
            from charter import interventions as IV
            for f in schedule:
                sched = IV.merge(sched, IV.load_schedule(f))
        made = RP.fork(rdir, at, sched, bdir, None, replay_mode, _dry_factory if dry else M.policy_for, sandbox, log=log,
                       rounds=rounds)
        PV.annotate(made[0], continued_from={"run_id": (PV.read(run) or {}).get("run_id") or run.name, "round": at,
                                             "replay": str(rdir.name), "code": "current", "live": "scripted" if dry else "models"})
        return {"replay": str(rdir), "branch": str(made[0]), "code": "current", "replay_result": res}
    log(f"[continue] the current code does not reproduce the run ({why[:300]})")
    shutil.rmtree(rdir, ignore_errors=True)
    sha = segment_sha(run, at)
    meta = PV.read(run) or {}
    git = meta.get("git") or {}
    if not sha:
        raise SystemExit(f"continue refused: the current code does not reproduce {run.name} and run.json records no git sha to "
                         f"check out ({why[:200]})")
    if PV._git("cat-file", "-e", f"{sha}^{{commit}}") is None:
        raise SystemExit(f"continue refused: the current code does not reproduce {run.name}, and its recorded code (git {sha[:12]}) "
                         "is not in this repository: fetch the branch it was made on and try again")
    if git.get("dirty") or any((s.get("git") or {}).get("dirty") for s in meta.get("segments") or []):
        raise SystemExit(f"continue refused: the current code does not reproduce {run.name}, and it ran with uncommitted changes "
                         "(only their sha is recorded), so its code cannot be rebuilt")
    return _continue_at_sha(run, at, rounds, rdir, bdir, sha, schedule, dry, replay_mode, log, worktree_root, why)


def _continue_at_sha(run, at, rounds, rdir, bdir, sha, schedule, dry, replay_mode, log, worktree_root, why) -> dict:
    """continue's two steps (replay --to, fork --at) with the charter CLI of a worktree at `sha`."""
    root = Path(tempfile.mkdtemp(prefix="charter_continue_", dir=worktree_root))
    wt = root / "src"
    if PV._git("worktree", "add", "--detach", str(wt), sha) is None:
        shutil.rmtree(root, ignore_errors=True)
        raise SystemExit(f"continue refused: git worktree add at {sha[:12]} failed")
    try:
        if (PV.REPO / ".env").exists():
            shutil.copy2(PV.REPO / ".env", wt / ".env")
        log(f"[continue] under the recorded code: git {sha[:12]} in {wt}")

        def cli(*args):
            p = subprocess.run([sys.executable, "-m", "charter", *map(str, args)], cwd=wt, capture_output=True, text=True)
            return p.returncode, p.stdout + p.stderr

        code, text = cli("replay", run, "--to", at, "--out", rdir, "--sandbox", "off")
        if code != 0:
            raise SystemExit(f"continue refused: the run does not replay under its recorded code either (git {sha[:12]}):\n"
                             f"{text[-1500:]}\n(under the current code: {why[:300]})")
        fork_help = cli("fork", "--help")[1]
        args = ["fork", rdir, "--at", at, "--out", bdir, "--replay", replay_mode, "--sandbox", "off"]
        for f in schedule or []:
            args += ["--apply", Path(f).resolve()]
        if rounds and "--rounds" in fork_help:
            args += ["--rounds", rounds]
        elif rounds:
            log(f"[continue] the code at {sha[:12]} has no fork --rounds: the branch plays to the end")
        if dry:
            raise SystemExit("continue refused: --dry under a recorded sha is not supported (the old CLI's fork uses the run's own "
                             "policy); continue under the current code instead")
        code, text = cli(*args)
        if code != 0:
            raise SystemExit(f"continue: fork under git {sha[:12]} failed:\n{text[-1500:]}")
        PV.annotate(bdir, continued_from={"run_id": (PV.read(run) or {}).get("run_id") or Path(run).name, "round": at,
                                          "replay": rdir.name, "code": sha, "live": "models"})
        return {"replay": str(rdir), "branch": str(bdir), "code": sha, "replay_result": None}
    finally:
        PV._git("worktree", "remove", "--force", str(wt))
        shutil.rmtree(root, ignore_errors=True)
        PV._git("worktree", "prune")


# ------------------------------------------------------------------ CLI
def cmd_fetch(a) -> None:
    print(f"run dir: {fetch(a.run_id, a.repo, a.revision, a.out)}")


def cmd_continue(a) -> None:
    sandbox = None
    if not a.dry and a.sandbox == "docker":
        from charter.sandbox import DockerSandbox
        sandbox = DockerSandbox()
    r = continue_run(a.run, a.at, a.rounds, a.out, a.apply, a.dry, a.replay, sandbox=sandbox)
    print(json.dumps({k: v for k, v in r.items() if k != "replay_result"}, indent=1))
    print(f"branch: {r['branch']}")


def add_commands(sub) -> None:
    from charter import publish as PB
    p = sub.add_parser("fetch", help="download a published run's raw archive into a run directory (charter/fetch.py)")
    p.add_argument("run_id")
    p.add_argument("--repo", default=PB.DEFAULT_REPO, help=f"dataset repo (default {PB.DEFAULT_REPO})")
    p.add_argument("--revision", default=None, help="a release tag (vX.Y) or commit; default main")
    p.add_argument("--out", default=None, help="where <spec>/<run_id> goes (default charter/out/_fetched)")
    p.set_defaults(fn=cmd_fetch)
    p = sub.add_parser("continue", help="replay a run (e.g. a fetched one) to round N, check it reproduces, fork it there and play on")
    p.add_argument("run")
    p.add_argument("--at", type=int, required=True, help="round N (0-based) is the first round played anew; N rounds are kept")
    p.add_argument("--rounds", type=int, default=None, help="play K rounds and pause (default: to the end)")
    p.add_argument("--out", default=None, help="directory for replay/ and branch/ (default <run>_cont<N>)")
    p.add_argument("--apply", action="append", default=[], help="an intervention schedule for the branch (repeatable)")
    p.add_argument("--dry", action="store_true", help="continue with the scripted bots (no model calls)")
    p.add_argument("--replay", choices=["strict", "prompt-match"], default="strict", help="fork replay mode")
    p.add_argument("--sandbox", choices=["docker", "off"], default="off",
                   help="run_python after round N (default off; recorded outputs before N are always served from the record)")
    p.set_defaults(fn=cmd_continue)
