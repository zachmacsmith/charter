"""`python -m charter rerun RUN_DIR [--out DIR] [--dry-run] [--keep-worktree]`: play a run's command again under its own code.

A run records the git sha it started under (run.json `git`) and the command line (the start segment's `argv`). rerun checks out
that sha in a temporary git worktree, runs the same command there (with .env copied in, so the same backend is used) and moves
the run directory it makes to OUT (default <RUN_DIR>_rerun, numbered if taken); run.json of the copy gets `rerun_of`. This is the
way to repeat a run made before frozen settings (charter/settings.py, D-50) whose defaults cannot be inferred, or any run whose
behaviour depends on code since changed.

Refused, with the reason: no git sha, or a sha this repository does not have; a dirty tree when the run started (the diff itself
is not stored, only its sha, so that code cannot be rebuilt) or untracked charter/*.py files; a fork or rewind (rerun its parent and
fork that). A run not started by `python -m charter run` (a test, a sweep, a script) is played from its saved spec instead:
instance.json spec_source and seed, --dry when it was dry (refused when it has no spec_source).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from charter import provenance as PV


class RerunError(SystemExit):
    pass


def _out_for(run: Path, out) -> Path:
    if out is not None:
        out = Path(out)
        if out.exists() and any(out.iterdir()):
            raise RerunError(f"{out} exists and is not empty")
        return out
    out, n = run.parent / f"{run.name}_rerun", 2
    while out.exists():
        out, n = run.parent / f"{run.name}_rerun{n}", n + 1
    return out


def _rebase(arg: str, wt: str) -> str:
    """An absolute path inside this repository points into the worktree instead (the spec file as it was at the sha)."""
    p = Path(arg)
    if p.is_absolute():
        try:
            return str(Path(wt) / p.resolve().relative_to(PV.REPO.resolve()))
        except ValueError:
            return arg
    return arg


def plan(run, out=None) -> dict:
    """What rerun would do: {run, sha, command (arguments after `python -m charter`), source (argv | spec_source), out}.
    RerunError when it cannot be reproduced."""
    run = Path(run)
    meta = PV.read(run)
    if meta is None:
        raise RerunError(f"{run} has no run.json: the code it ran under is unknown")
    if meta.get("parent"):
        raise RerunError(f"{run} is a {', '.join(sorted({s.get('kind') for s in meta.get('segments') or []} & {'fork', 'rewind'})) or 'branch'} "
                         f"of {meta['parent'].get('run')}: rerun the parent run, then branch it again")
    segs = meta.get("segments") or []
    start = next((s for s in segs if s.get("kind") == "start"), None)
    git = (start or {}).get("git") or meta.get("git") or {}
    sha = git.get("sha")
    if not sha:
        raise RerunError(f"{run}: run.json records no git sha (git was unavailable when it started)")
    if PV._git("cat-file", "-e", f"{sha}^{{commit}}") is None:
        raise RerunError(f"{run}: git {sha[:12]} is not in this repository (fetch the branch it was made on)")
    if git.get("dirty"):
        raise RerunError(f"{run}: the run started with uncommitted changes (diff sha {git.get('diff_sha')}); only the diff's sha is "
                         f"recorded, not the diff, so its code cannot be rebuilt")
    if git.get("untracked_py"):
        raise RerunError(f"{run}: the run started with untracked charter files ({', '.join(git['untracked_py'])}), not recorded")
    argv = list((start or {}).get("argv") or [])
    exe = Path(argv[0]).name if argv else ""
    if argv[1:2] == ["run"] and exe in ("__main__.py", "charter", "-m"):
        cmd, source = argv[1:], "argv"
    else:
        inst = json.loads((run / "instance.json").read_text()) if (run / "instance.json").exists() else {}
        if "spec_source" not in inst:
            raise RerunError(f"{run}: it was not started by `python -m charter run` (argv {argv[:3]}) and instance.json has no "
                             f"spec_source to run instead")
        dry = bool(meta.get("dry")) if meta.get("dry") is not None else "_dry" in run.name
        cmd = ["run", "{spec}", "--seed", str(inst.get("seed"))] + (["--dry", "--sandbox", "off"] if dry else [])
        if (run / "interventions.yaml").exists():
            cmd += ["--apply", str((run / "interventions.yaml").resolve())]
        source = "spec_source"
    return {"run": str(run), "sha": sha, "command": cmd, "source": source, "out": str(_out_for(run, out)),
            "engine_version": meta.get("engine_version")}


def execute(p: dict, keep_worktree: bool = False, log=print, worktree_root=None) -> Path:
    """Run the plan: a detached worktree at the sha, the command there, the run directory it made moved to p["out"]."""
    run, out = Path(p["run"]), Path(p["out"])
    root = Path(tempfile.mkdtemp(prefix="charter_rerun_", dir=worktree_root))
    wt = root / "src"
    if PV._git("worktree", "add", "--detach", str(wt), p["sha"]) is None:
        shutil.rmtree(root, ignore_errors=True)
        raise RerunError(f"git worktree add at {p['sha'][:12]} failed")
    try:
        if (PV.REPO / ".env").exists():
            shutil.copy2(PV.REPO / ".env", wt / ".env")
        cmd = []
        for a in p["command"]:
            if a == "{spec}":
                f = wt / "rerun_spec.yaml"
                f.write_text(json.dumps(json.loads((run / "instance.json").read_text())["spec_source"], indent=1, default=str))
                a = str(f)
            cmd.append(_rebase(a, str(wt)))
        log(f"[rerun] {run.name}: git {p['sha'][:12]} in {wt}: python -m charter {' '.join(cmd)}")
        proc = subprocess.run([sys.executable, "-m", "charter", *cmd], cwd=wt, capture_output=True, text=True)
        made = next((ln.split("run dir:", 1)[1].strip() for ln in reversed(proc.stdout.splitlines()) if ln.startswith("run dir:")),
                    None)
        if proc.returncode != 0 or not made:
            raise RerunError(f"the rerun command failed (exit {proc.returncode}):\n{proc.stdout[-2000:]}\n{proc.stderr[-3000:]}")
        made = Path(made) if Path(made).is_absolute() else wt / made
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.rmdir()
        shutil.move(str(made), str(out))
        PV.annotate(out, rerun_of={"run": str(run.resolve()), "run_id": (PV.read(run) or {}).get("run_id") or run.name,
                                   "sha": p["sha"], "command": p["command"], "source": p["source"]})
        log(f"[rerun] {out}")
        return out
    finally:
        if keep_worktree:
            log(f"[rerun] worktree kept: {wt}")
        else:
            PV._git("worktree", "remove", "--force", str(wt))
            shutil.rmtree(root, ignore_errors=True)
            PV._git("worktree", "prune")


def cmd(a) -> None:
    p = plan(a.run, a.out)
    if a.dry_run:
        print(json.dumps(p, indent=1))
        return
    execute(p, keep_worktree=a.keep_worktree)


def add_command(sub) -> None:
    p = sub.add_parser("rerun", help="play a run's command again under the code it ran (a git worktree at its sha; charter/rerun.py)")
    p.add_argument("run")
    p.add_argument("--out", default=None, help="where the new run directory goes (default <run>_rerun)")
    p.add_argument("--dry-run", action="store_true", help="print what would be run (sha, command, out) and stop")
    p.add_argument("--keep-worktree", action="store_true", help="leave the temporary worktree in place (to inspect it)")
    p.set_defaults(fn=cmd)
