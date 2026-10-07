"""Exact replay and rewind of a run (docs/review/04_provenance_replay_interventions.md, migration steps 4-6).

  python -m charter replay RUN [--to N] [--out DIR] [--sandbox off|docker]
      Re-executes RUN from its recorded inputs (instance.json and every model reply in calls.jsonl) into a new directory and
      reports whether events.jsonl and snapshots.json came out byte-identical (ignoring timestamps). --to N stops after N rounds
      and compares with RUN's state after round N. Exit status 1 when they differ.
  python -m charter rewind RUN --to N --out NEWDIR
      A new run directory continuing from RUN's state after N complete rounds (checkpoints/rNNNN.pkl): the append-only logs copied
      up to that checkpoint's offsets, snapshots cut to N rounds, run.json with a segment of kind "rewind" naming the parent run
      and round. `python -m charter resume NEWDIR` then plays on from round N + 1. RUN is never changed.

Replay (ReplayPolicy) serves each call's recorded reply by its explicit call key (provenance.call_key: round, phase, wave, agent,
n), for model runs by passing the recorded raw text through llm.parse_json again (the parsed reply when the raw text would not
give it back). It fails loudly: ReplayMiss when a call has no recorded reply or recorded calls are never asked for, and
ReplayDivergence when a call's prompt (system or user, by hash) differs from the recorded one, i.e. the run has already diverged.
Runs from before call keys fall back to the per-round call id `r<round>:<agent>:<n>` (and to empty reasoning text when calls.jsonl
did not keep it: "approximate").

Not replayed: Docker sandbox output (run_python is executed again: --sandbox docker for model runs that used it) and the shared
archive, which is live state shared across runs; a replay reads and writes a private copy of its current contents, so a run that
read the archive replays exactly only while the archive is unchanged (a difference shows as a ReplayDivergence).
"""
from __future__ import annotations

import contextlib
import json
import shutil
import threading
from pathlib import Path

from charter import provenance as PV


class ReplayMiss(RuntimeError):
    """A model call with no recorded reply, or recorded replies that the replay never asked for."""


class ReplayDivergence(RuntimeError):
    """A replayed call whose prompt differs from the recorded one: the run diverged before it."""


def _jsonl(p: Path) -> list:
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()] if p.exists() else []


def load_calls(run) -> tuple[dict, bool]:
    """calls.jsonl indexed by call key id (legacy runs: by call id); (rows, legacy)."""
    rows = _jsonl(Path(run) / "calls.jsonl")
    legacy = any("key" not in r for r in rows)
    by = {}
    for r in rows:
        kid = r["call"] if legacy else r["key"]
        if kid in by:
            raise ReplayMiss(f"calls.jsonl has two rows for call {kid}")
        by[kid] = r
    return by, legacy


class ReplayPolicy:
    """Serves recorded replies by explicit call key (passed by provenance.Recorder, which the runner wraps every policy in)."""
    takes_key = True                                                    # provenance.Recorder passes the full key
    replaying = True                                                    # calls.jsonl rows of the replay say "replayed"
    parallel_safe = False

    def __init__(self, calls: dict, legacy: bool = False, check_prompts: bool = True):
        self.calls, self.legacy, self.check = calls, legacy, check_prompts
        self.used: set = set()
        self.approximate = False
        self._n: dict = {}
        self._lock = threading.Lock()

    def act(self, k, a, system, user, n_actions, final, key=None):
        return self.act_recorded(k, a, system, user, n_actions, final, key=key)[:3]

    def act_recorded(self, k, a, system, user, n_actions, final, key=None):
        if key is None:
            raise ReplayMiss("a model call without a call key (ReplayPolicy must be wrapped in provenance.Recorder)")
        kid = key["id"]
        if self.legacy:                                                 # r<round>:<agent>:<n>, n counted per round and agent
            with self._lock:
                i = self._n.get((key["round"], key["agent"]), 0)
                self._n[(key["round"], key["agent"])] = i + 1
            kid = f"r{key['round']}:{key['agent']}:{i}"
        row = self.calls.get(kid)
        if row is None:
            raise ReplayMiss(f"call {kid} ({a.get('id')}, round {key['round'] + 1}, {key['phase']}) has no recorded reply")
        if self.check:
            for what in ("system_sha", "user_sha"):
                if row.get(what) and row[what] != key.get(what):
                    raise ReplayDivergence(f"call {kid}: the {what[:-4]} prompt differs from the recorded one "
                                           f"({key.get(what)} != {row[what]}): the replay diverged from the run before this call")
        if "parsed" in row:
            out = row["parsed"]
        else:
            out = PV.reply_from_raw(row.get("attempts"), row.get("error"))
            if out is None:
                raise ReplayMiss(f"call {kid}: the recorded raw text does not give a reply back and no parsed reply was kept")
        if "reasoning" not in row:
            self.approximate = True
        with self._lock:
            self.used.add(kid)
        usage = {x: v for x, v in (row.get("usage") or {}).items() if x != "call"}
        attempts = json.loads(json.dumps(row["attempts"])) if row.get("attempts") is not None else None
        return json.loads(json.dumps(out)), row.get("reasoning", ""), usage, attempts

    def unused(self, until: int | None = None) -> list:
        """Recorded calls (of rounds before `until`) the replay never asked for."""
        return sorted(kid for kid, r in self.calls.items() if kid not in self.used and (until is None or r["round"] < until))


@contextlib.contextmanager
def _private_archive(inst: dict, out: Path):
    """The shared archive for the replay: a copy of its current contents inside the replay directory (never the live one)."""
    from charter import archive
    real = archive.shared_dir
    live = real(inst["spec"])
    if live is None:
        yield None
        return
    copy = out / "shared_archive_copy"
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(live, copy)
    archive.shared_dir = lambda spec: copy if (spec or {}).get("shared_archive", {}).get("enabled", True) else None
    try:
        yield copy
    finally:
        archive.shared_dir = real


def _norm(lines: list) -> list:
    return [json.dumps({x: v for x, v in json.loads(ln).items() if x not in ("ts", "time")}, sort_keys=True) for ln in lines]


def _index(run: Path) -> dict:
    try:
        return json.loads((run / "checkpoints" / "index.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def compare(run, out, to: int | None = None) -> dict:
    """Events and snapshots of a replay against the run (its state after `to` rounds when given)."""
    run, out = Path(run), Path(out)
    new_ev = (out / "events.jsonl").read_bytes()
    ref_ev = (run / "events.jsonl").read_bytes()
    ref_snaps = json.loads((run / "snapshots.json").read_text())
    full = to is None or to >= len(ref_snaps)
    basis = "whole run"
    if not full:
        ent = _index(run).get(str(to))
        if ent:
            ref_ev, basis = ref_ev[:ent["files"]["events.jsonl"]], f"checkpoint after round {to}"
        else:                                                           # no per-round index: the same number of lines
            ref_ev, basis = b"".join(ref_ev.splitlines(keepends=True)[:len(new_ev.splitlines())]), "line prefix"
        ref_snaps = ref_snaps[:to]
    new_snaps_b = (out / "snapshots.json").read_bytes()
    ref_snaps_b = (run / "snapshots.json").read_bytes() if full else json.dumps(ref_snaps, default=list).encode()
    a, b = new_ev.decode().splitlines(), ref_ev.decode().splitlines()
    res = {"events_identical": new_ev == ref_ev, "snapshots_identical": new_snaps_b == ref_snaps_b,
           "events": [len(a), len(b)], "snapshots": [len(json.loads(new_snaps_b)), len(ref_snaps)], "compared_to": basis}
    if not res["events_identical"]:
        na, nb = _norm(a), _norm(b)
        res["events_identical_ignoring_timestamps"] = na == nb
        diff = next((i for i, (x, y) in enumerate(zip(na, nb)) if x != y), min(len(na), len(nb)))
        res["first_difference"] = {"line": diff + 1, "replay": a[diff][:400] if diff < len(a) else None,
                                   "run": b[diff][:400] if diff < len(b) else None}
    res["identical"] = res["snapshots_identical"] and (res["events_identical"] or res.get("events_identical_ignoring_timestamps", False))
    return res


def replay(run, out=None, to: int | None = None, sandbox=None, log=print, check_prompts: bool = True) -> dict:
    """Re-execute `run` from its recorded inputs into `out` (default: <run>_replay, numbered if taken); return the comparison."""
    from charter import runner
    run = Path(run)
    inst = json.loads((run / "instance.json").read_text())             # the saved world is authoritative
    meta = PV.read(run) or {}
    dry = bool(meta["dry"]) if meta.get("dry") is not None else "_dry" in run.name
    if out is None:
        out, n = run.parent / f"{run.name}_replay", 2
        while out.exists():
            out, n = run.parent / f"{run.name}_replay{n}", n + 1
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty")
    out.mkdir(parents=True, exist_ok=True)
    calls, legacy = load_calls(run)
    pol = ReplayPolicy(calls, legacy, check_prompts)
    with _private_archive(inst, out) as arch:
        runner.run(inst, pol, out, sandbox, log=log, dry=dry, until=to, instance_source="replay of " + str(run))
    extra = pol.unused(to)
    if extra:
        raise ReplayMiss(f"{len(extra)} recorded call(s) were never asked for in the replay (first: {', '.join(extra[:5])})")
    res = compare(run, out, to)
    res.update(calls_replayed=len(pol.used), legacy_keys=legacy, approximate=pol.approximate or legacy,
               rounds=to if to is not None else inst["rounds"], out=str(out))
    if arch is not None:
        res["note"] = "shared archive: replayed against a copy of its current contents, not its state when the run started"
    PV.annotate(out, replay_of={"run": str(run.resolve()), "run_id": meta.get("run_id") or run.name, "to": to}, replay=res)
    (out / "replay.json").write_text(json.dumps(res, indent=1))
    return res


def rewind(run, to: int, out) -> Path:
    """A new run directory holding `run` as it was after `to` complete rounds, ready to resume (see module docstring)."""
    from charter import runner
    run, out = Path(run), Path(out)
    idx = _index(run)
    ent = idx.get(str(int(to)))
    if ent is None or not (run / runner.CKPT_DIR / ent["file"]).exists():
        have = sorted(int(x) for x in idx)
        raise SystemExit(f"{run} has no checkpoint after round {to} (per-round checkpoints: "
                         f"{', '.join(map(str, have)) or 'none; the run predates them'})")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty")
    out.mkdir(parents=True, exist_ok=True)
    for f in ("instance.json", "run.json"):
        if (run / f).exists():
            shutil.copy2(run / f, out / f)
    if (run / "prompts").exists():
        shutil.copytree(run / "prompts", out / "prompts")
    for name in PV.APPEND_ONLY:                                         # the logs up to the checkpoint, not beyond
        size = ent["files"].get(name, 0)
        if (run / name).exists():
            with open(run / name, "rb") as f:
                (out / name).write_bytes(f.read(size))
    snaps = json.loads((run / "snapshots.json").read_text())[:ent["counts"]["snapshots"]]
    (out / "snapshots.json").write_text(json.dumps(snaps, default=list))
    if (run / "ground_truth.json").exists():
        gt = json.loads((run / "ground_truth.json").read_text())
        gt.update(complete=False, rounds_played=len(snaps), rewound_from={"run": str(run.resolve()), "round": int(to)})
        (out / "ground_truth.json").write_text(json.dumps(gt, indent=1, default=list))
    d = out / runner.CKPT_DIR
    d.mkdir()
    keep = {x: v for x, v in idx.items() if int(x) <= int(to) and (run / runner.CKPT_DIR / v["file"]).exists()}
    for v in keep.values():
        shutil.copy2(run / runner.CKPT_DIR / v["file"], d / v["file"])
    (d / "index.json").write_text(json.dumps(keep, indent=1))
    shutil.copy2(run / runner.CKPT_DIR / ent["file"], out / "checkpoint.pkl")
    runner.load_checkpoint(out, out / "checkpoint.pkl")                 # the copied logs agree with the checkpoint
    meta = PV.read(run) or {}
    PV.branch(out, "rewind", int(to), {"run": str(run.resolve()), "run_id": meta.get("run_id") or run.name, "round": int(to),
                                         "checkpoint": ent["file"]})
    return out


# ------------------------------------------------------------------ command line (python -m charter replay / rewind)
def cmd_replay(a) -> None:
    run = Path(a.run)
    meta = PV.read(run) or {}
    dry = bool(meta.get("dry", "_dry" in run.name))
    sandbox = None
    if (a.sandbox or ("off" if dry else "docker")) == "docker":
        from charter.sandbox import DockerSandbox
        sandbox = DockerSandbox()
    try:
        res = replay(run, a.out, a.to, sandbox, check_prompts=not a.no_prompt_check)
    except (ReplayMiss, ReplayDivergence) as e:
        print(f"replay FAILED: {type(e).__name__}: {e}")
        raise SystemExit(1)
    print(json.dumps(res, indent=1))
    print(("IDENTICAL" if res["identical"] else "DIFFERENT") + f": replay of {run} -> {res['out']}")
    if not res["identical"]:
        raise SystemExit(1)


def cmd_rewind(a) -> None:
    out = rewind(a.run, a.to, a.out)
    print(f"rewound {a.run} to the end of round {a.to}: {out}\ncontinue with: python -m charter resume {out}")


def add_commands(sub) -> None:
    p = sub.add_parser("replay", help="re-execute a run from its recorded model replies and check it reproduces")
    p.add_argument("run")
    p.add_argument("--to", type=int, default=None, help="stop after N rounds (compare with the run's state then)")
    p.add_argument("--out", default=None, help="replay directory (default <run>_replay)")
    p.add_argument("--sandbox", choices=["docker", "off"], default=None, help="default: off for dry runs, docker for model runs")
    p.add_argument("--no-prompt-check", action="store_true", help="serve replies even when a prompt hash differs")
    p.set_defaults(fn=cmd_replay)
    p = sub.add_parser("rewind", help="a new run directory continuing from a run's state after round N")
    p.add_argument("run")
    p.add_argument("--to", type=int, required=True, help="number of complete rounds to keep")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_rewind)
