"""Exact replay and rewind of a run (docs/review/04_provenance_replay_interventions.md, migration steps 4-6).

  python -m charter replay RUN [--to N] [--out DIR] [--sandbox off|docker]
      Re-executes RUN from its recorded inputs (instance.json and every model reply in calls.jsonl) into a new directory and
      reports whether events.jsonl and snapshots.json came out byte-identical (ignoring timestamps). --to N stops after N rounds
      and compares with RUN's state after round N. Exit status 1 when they differ.
  python -m charter rewind RUN --to N --out NEWDIR
      A new run directory continuing from RUN's state after N complete rounds (checkpoints/rNNNN.pkl): the append-only logs copied
      up to that checkpoint's offsets, snapshots cut to N rounds, run.json with a segment of kind "rewind" naming the parent run
      and round. `python -m charter resume NEWDIR` then plays on from round N + 1. RUN is never changed.
  python -m charter fork RUN --at N [--apply iv.yaml] [--replicates K] [--out DIR] [--replay strict|prompt-match|none]
      Branches: rewind to round N (from the latest checkpoint at or before it), apply the intervention schedule
      (charter/interventions.py), and play to the end with ForkPolicy: the parent's recorded replies before round N, the live
      policy (models, or scripted bots for dry runs) from N. --replicates K: K branches DIR/rep1..repK whose live policies get
      distinct seeds. run.json: a segment of kind "fork" and `parent` {run, round, branch, replicate, live_seed, schedule}.
  python -m charter branches RUN [--json]
      The lineage: RUN's ancestors and the tree of rewinds and forks made from its root (run.json parent pointers).

Replay (ReplayPolicy) serves each call's recorded reply by its explicit call key (provenance.call_key: round, phase, wave, agent,
n), for model runs by passing the recorded raw text through llm.parse_json again (the parsed reply when the raw text would not
give it back). It fails loudly: ReplayMiss when a call has no recorded reply or recorded calls are never asked for, and
ReplayDivergence when a call's prompt (system or user, by hash) differs from the recorded one, i.e. the run has already diverged.
Runs from before call keys fall back to the per-round call id `r<round>:<agent>:<n>` (and to empty reasoning text when calls.jsonl
did not keep it: "approximate").

Sandbox and shared archive (P5.4). Sandbox outputs are served from the run's record (sandbox.jsonl + blobs, ReplaySandbox) by call
key r<round>:<agent>:<n>, never by running Docker again (a call whose code differs from the recorded one: ReplayDivergence; a call
with no record: ReplayMiss); only runs from before the record (no sandbox.jsonl) run the given sandbox (--sandbox docker). A fork
serves the parent's record before the fork point and runs the live sandbox from it. The shared archive is the run's frozen copy
(archive.Frozen: archive/base.json + blobs, plus the run's own overlay, which a rewind copies up to the checkpoint): a replay starts
from the run's frozen base, so it reproduces the run however the live shared archive has changed since; replays and forks never
publish to the live archive. A run from before the freeze has no frozen base: its replay snapshots the live archive's current
contents (and says so in replay.json), exact only while that is unchanged.
"""
from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

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


class ReplaySandbox:
    """Serves a run's recorded sandbox outputs (sandbox.jsonl, blobs/) by call key; the runner wraps it in sandbox.Recording, which
    passes the key. until: only calls of rounds before it are served, later ones go to `live` (a fork); None: every call is served
    (a replay). A run without a record (from before P5.4) runs `live` for every call. live None: the disabled sandbox."""
    takes_key = True

    def __init__(self, run, live=None, until: int | None = None):
        from charter import sandbox as SB
        self.run, self.until = Path(run), until
        self.live = live or SB.disabled
        self.recorded = (self.run / SB.RECORD).exists()
        self.rows = {r["call"]: r for r in _jsonl(self.run / SB.RECORD)}
        self.served: set = set()
        self.lock = threading.Lock()

    def __call__(self, agent, code, key=None):
        if not self.recorded or key is None or (self.until is not None and key["round"] >= self.until):
            return self.live(agent, code)
        row = self.rows.get(key["call"])
        if row is None:
            raise ReplayMiss(f"sandbox call {key['call']} ({agent}, round {key['round'] + 1}) has no recorded output")
        if row["code"] != PV.blob_sha(str(code)):
            raise ReplayDivergence(f"sandbox call {key['call']}: the code differs from the recorded code: the replay diverged "
                                   "before this call")
        with self.lock:
            self.served.add(key["call"])
        return PV.get_blob(self.run, row["output"])

    def unused(self, until: int | None = None) -> list:
        """Recorded sandbox calls (of rounds before `until`) never asked for."""
        if self.until is not None:
            until = self.until if until is None else min(until, self.until)
        return sorted(c for c, r in self.rows.items() if c not in self.served and (until is None or r["round"] < until))


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
    from charter import settings as ST                                  # and its code defaults (frozen, else inferred; D-43): a replay
    inst["settings"] = ST.resolve(run, inst, allow_code_drift=True, record=False)   # under other defaults diverges, never hides it
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
    from charter import interventions as IV                             # the run's interventions are inputs too
    sched = IV.load_schedule(run / "interventions.yaml") if (run / "interventions.yaml").exists() else None
    sbx = ReplaySandbox(run, live=sandbox)                              # recorded sandbox outputs, not Docker
    runner.run(inst, pol, out, sbx, log=log, dry=dry, until=to, instance_source="replay of " + str(run), schedule=sched,
               archive_from=run, publish_archive=False)                 # the run's frozen archive; never published
    extra = pol.unused(to)
    if extra:
        raise ReplayMiss(f"{len(extra)} recorded call(s) were never asked for in the replay (first: {', '.join(extra[:5])})")
    extra = sbx.unused(to)
    if extra:
        raise ReplayMiss(f"{len(extra)} recorded sandbox call(s) were never asked for in the replay (first: {', '.join(extra[:5])})")
    res = compare(run, out, to)
    res.update(calls_replayed=len(pol.used), sandbox_replayed=len(sbx.served), legacy_keys=legacy,
               approximate=pol.approximate or legacy, rounds=to if to is not None else inst["rounds"], out=str(out))
    from charter import archive
    if not sbx.recorded:
        res["sandbox_note"] = "the run has no sandbox record (made before P5.4): sandbox calls were executed again"
    ra, oa = (PV.read(run) or {}).get("shared_archive"), (PV.read(out) or {}).get("shared_archive")
    if oa:
        res["shared_archive"] = oa.get("hash")
        if not (run / archive.FROZEN_DIR / "base.json").exists():
            res["note"] = "shared archive: the run has no frozen copy (made before P5.4); replayed against the live archive's current contents"
        elif ra and ra.get("hash") != oa.get("hash"):
            raise ReplayDivergence(f"the replay's frozen archive {oa.get('hash')} is not the run's {ra.get('hash')}")
    PV.annotate(out, replay_of={"run": str(run.resolve()), "run_id": meta.get("run_id") or run.name, "to": to}, replay=res)
    (out / "replay.json").write_text(json.dumps(res, indent=1))
    return res


def rewind(run, to: int, out, kind: str = "rewind", parent_extra: dict | None = None, first_round: int | None = None) -> Path:
    """A new run directory holding `run` as it was after `to` complete rounds, ready to resume (see module docstring). kind and
    parent_extra: the run.json segment (fork() makes "fork" segments); first_round: the segment's first round (default `to`)."""
    from charter import interventions as IV
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
    for f in ("instance.json", "run.json", "interventions.yaml"):
        if (run / f).exists():
            shutil.copy2(run / f, out / f)
    if (run / "prompts").exists():
        shutil.copytree(run / "prompts", out / "prompts")
    for name in PV.APPEND_ONLY:                                         # the logs up to the checkpoint, not beyond
        size = ent["files"].get(name, 0)
        if (run / name).exists():
            with open(run / name, "rb") as f:
                (out / name).write_bytes(f.read(size))
    if (run / PV.BLOBS).exists():                                       # content-addressed texts (hard links where possible)
        PV.copy_blobs(run, out, [p.name for p in (run / PV.BLOBS).iterdir() if not p.name.startswith(".")])
    from charter import archive
    if (run / archive.FROZEN_DIR / "base.json").exists():               # the frozen archive: base; the overlay was cut above
        (out / archive.FROZEN_DIR).mkdir()
        shutil.copy2(run / archive.FROZEN_DIR / "base.json", out / archive.FROZEN_DIR / "base.json")
        try:
            st = json.loads((run / archive.FROZEN_DIR / "state.json").read_text())
        except (OSError, json.JSONDecodeError):
            st = {}
        kept = sum(1 for ln in (out / archive.OVERLAY).read_text().splitlines() if ln.strip()) \
            if (out / archive.OVERLAY).exists() else 0
        st["published"] = kept                                          # the parent's writes are the parent's to publish
        st.pop("published_at", None)
        (out / archive.FROZEN_DIR / "state.json").write_text(json.dumps(st, indent=1))
    from charter import directories as DR
    if (run / DR.FROZEN_DIR / "base.json").exists():                    # the frozen directories: base, and the parent's write-backs
        (out / DR.FROZEN_DIR).mkdir()                                   # are the parent's (the branch writes back only its own changes)
        shutil.copy2(run / DR.FROZEN_DIR / "base.json", out / DR.FROZEN_DIR / "base.json")
        try:
            st = json.loads((run / DR.FROZEN_DIR / "state.json").read_text())
        except (OSError, json.JSONDecodeError):
            st = {}
        import pickle
        w = pickle.loads((run / runner.CKPT_DIR / ent["file"]).read_bytes())["kernel"]["w"]
        st["published"] = {n: {p: PV.put_blob(out, t) for p, t in sorted(d["files"].items())} for n, d in (w.get("dirs") or {}).items()
                           if d.get("scope") == "namespace"}
        st.pop("written_back_at", None)
        (out / DR.FROZEN_DIR / "state.json").write_text(json.dumps(st, indent=1))
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
    ck = runner.load_checkpoint(out, out / "checkpoint.pkl")            # the copied logs agree with the checkpoint
    if ck["kernel"]["w"].get("interventions") is not None:              # interventions applied up to the checkpoint
        IV.write_log(out, SimpleNamespace(w=ck["kernel"]["w"]))
    meta = PV.read(run) or {}
    PV.branch(out, kind, int(to) if first_round is None else int(first_round),
              {"run": str(run.resolve()), "run_id": meta.get("run_id") or run.name, "round": int(to), "checkpoint": ent["file"],
               **(parent_extra or {})})
    return out


# ------------------------------------------------------------------ fork
class _RngGuard:
    """The live policy's RNG as the runner sees it: a replicate ignores the checkpoint's policy RNG state (restored once at the
    resume), so its post-fork sampling follows its own seed; checkpoints of the fork then save and restore it as usual."""

    def __init__(self, rng, skip_restore: bool):
        self._rng, self._skip = rng, skip_restore

    def setstate(self, state) -> None:
        if self._skip:
            self._skip = False
            return
        self._rng.setstate(state)

    def getstate(self):
        return self._rng.getstate()

    def __getattr__(self, name):
        if name in ("_rng", "_skip"):
            raise AttributeError(name)
        return getattr(self._rng, name)


class ForkPolicy:
    """Replay up to the fork point, then the live policy (ARCHITECTURE §8.4: Replay(parent.calls, until=N, live=policy)).
    mode strict: calls of rounds before `until` are served from the parent's record, and must match it (ReplayMiss /
    ReplayDivergence otherwise); every later call goes to the live policy. prompt-match: as strict, and after the fork point a
    recorded reply is still served while the call's key and both prompt hashes match the parent's (the run has not diverged at
    that call), else the live policy answers. none: every call is live."""
    takes_key = True

    def __init__(self, calls: dict, legacy: bool, live, until: int, mode: str = "strict", skip_rng_restore: bool = False):
        if mode not in ("strict", "prompt-match", "none"):
            raise ValueError(f"replay mode {mode!r}: strict, prompt-match or none")
        self.replay = ReplayPolicy(calls, legacy, check_prompts=True)
        self.live, self.until, self.mode = live, int(until), mode
        self._tl = threading.local()
        self._guard = _RngGuard(live.rng, skip_rng_restore) if hasattr(live, "rng") else None
        self.counts = {"replayed": 0, "live": 0}
        self._lock = threading.Lock()

    def __getattr__(self, name):
        if name in ("live", "replay", "_tl", "_guard", "counts", "_lock", "mode", "until"):
            raise AttributeError(name)
        if name == "rng":
            if self._guard is None:
                raise AttributeError(name)
            return self._guard
        return getattr(self.live, name)

    @property
    def replaying(self) -> bool:                                        # provenance.Recorder: this call's row says "replayed"
        return getattr(self._tl, "replayed", False)

    @property
    def parallel_safe(self) -> bool:
        return getattr(self.live, "parallel_safe", False)

    def act(self, k, a, system, user, n_actions, final, key=None):
        return self.act_recorded(k, a, system, user, n_actions, final, key=key)[:3]

    def act_recorded(self, k, a, system, user, n_actions, final, key=None):
        rec = self.replay.calls.get((key or {}).get("id"))
        use = self.mode != "none" and key["round"] < self.until
        if not use and self.mode == "prompt-match" and rec is not None:
            use = rec.get("system_sha") == key.get("system_sha") and rec.get("user_sha") == key.get("user_sha")
        self._tl.replayed = use
        with self._lock:
            self.counts["replayed" if use else "live"] += 1
        if use:
            return self.replay.act_recorded(k, a, system, user, n_actions, final, key=key)
        if hasattr(self.live, "act_recorded"):
            return self.live.act_recorded(k, a, system, user, n_actions, final)
        return (*self.live.act(k, a, system, user, n_actions, final), None)


def replicate_seed(seed, at: int, i: int) -> int:
    """The live policy's seed for replicate i of a fork at round `at` (replicates differ only after the fork point)."""
    return int(PV.sha(f"{seed}|fork|{at}|{i}"), 16) % 2 ** 31


def fork(run, at: int, schedule=None, out=None, replicates: int | None = None, replay_mode: str = "strict",
         policy_factory=None, sandbox=None, log=print, fresh_schedule: bool = False, allow_code_drift: bool = False) -> list[Path]:
    """Branches of `run` from round `at` (0-based: the first round played anew; `at` complete rounds are kept): each a new run
    directory restored from the latest checkpoint at or before `at`, with the schedule applied (merged by id into the parent's
    pending schedule, unless fresh_schedule) and played to the end with ForkPolicy (the parent's recorded replies before `at`, the
    live policy from `at`). replicates K: K branches <out>/rep1..repK whose live policies get distinct seeds (replicate_seed);
    otherwise one branch whose live policy continues from the parent's state. run.json of each: a "fork" segment, `parent`
    {run, run_id, round, checkpoint, branch, replicate, live_seed, schedule, replay} and top-level `replicate`. Returns the dirs."""
    import pickle
    from charter import interventions as IV
    from charter import runner
    run = Path(run)
    at = int(at)
    meta = PV.read(run) or {}
    idx = _index(run)
    have = sorted(int(x) for x, v in idx.items() if (run / runner.CKPT_DIR / v["file"]).exists())
    base = max((n for n in have if n <= at), default=None)
    if base is None:
        raise SystemExit(f"{run} has no checkpoint at or before round {at} (per-round checkpoints: {', '.join(map(str, have)) or 'none'})")
    inst0 = json.loads((run / "instance.json").read_text())
    from charter import settings as ST                                  # the parent's code defaults (D-43); refuse before any copy
    settings = ST.resolve(run, inst0, allow_code_drift, record=False)
    if not 0 <= at < int(inst0["rounds"]):
        raise SystemExit(f"--at {at}: the run has rounds 0..{int(inst0['rounds']) - 1} (fork at N plays round N onwards)")
    sched = IV.load_schedule(schedule if schedule is not None else [])
    early = [e["id"] for e in sched if e["at"]["phase"] != "setup" and e["at"]["round"] < at]
    if early:
        raise SystemExit(f"interventions before the fork point (round {at}): {', '.join(early)}")
    if policy_factory is None:
        from charter import __main__ as M
        policy_factory = M.policy_for
    dry = bool(meta["dry"]) if meta.get("dry") is not None else "_dry" in run.name
    seed = inst0.get("seed")
    calls, legacy = load_calls(run)
    if out is None:
        out, n = run.parent / f"{run.name}_fork{at}", 2
        while out.exists():
            out, n = run.parent / f"{run.name}_fork{at}_{n}", n + 1
    out = Path(out)
    reps = [None] if not replicates else list(range(1, int(replicates) + 1))
    dirs = [out] if reps == [None] else [out / f"rep{i}" for i in reps]
    sched_sha = PV.sha(json.dumps(sched, sort_keys=True, default=str))
    made = []
    for i, d in zip(reps, dirs):
        live_seed = seed if i is None else replicate_seed(seed, at, i)
        rewind(run, base, d, kind="fork", first_round=at,
               parent_extra={"round": at, "checkpoint_round": base, "branch": d.name, "replicate": i, "live_seed": live_seed,
                             "schedule": [e["id"] for e in sched], "schedule_sha": sched_sha, "replay": replay_mode})
        PV.annotate(d, replicate=i)
        prefix = {r.get("key") or r.get("call") for r in _jsonl(d / "calls.jsonl")}   # calls made before the checkpoint
        if fresh_schedule:                                              # drop the parent's pending interventions
            ck = pickle.loads((d / "checkpoint.pkl").read_bytes())
            ck["runner"]["schedule"] = []
            blob = pickle.dumps(ck)
            runner._atomic(d / "checkpoint.pkl", blob)
            runner._atomic(d / runner.CKPT_DIR / runner.ckpt_name(base), blob)
        inst = json.loads((d / "instance.json").read_text())
        if "settings" not in inst:                                      # an older parent: the branch keeps what it was given
            inst["settings"] = settings
            PV.annotate(d, settings_inferred=settings)
        live = policy_factory(inst["spec"], dry, live_seed)
        pol = ForkPolicy(calls, legacy, live, until=at, mode=replay_mode, skip_rng_restore=i is not None)
        if log:
            log(f"[{d.name}] fork of {run.name} at round {at + 1} (from the checkpoint after {base} rounds), replicate {i}, "
                f"{len(sched)} intervention(s), replay {replay_mode}")
        sbx = ReplaySandbox(run, live=sandbox, until=at if replay_mode != "none" else 0)   # recorded outputs before the fork point
        runner.run(inst, pol, d, sbx, log=log or (lambda *a: None), resume=True, dry=dry, schedule=sched,
                   instance_source=f"fork of {run} at round {at}", publish_archive=False)   # the parent's frozen archive, unpublished
        missed = [kid for kid, r in calls.items() if base <= r["round"] < at and kid not in pol.replay.used
                  and kid not in prefix] if replay_mode != "none" else []
        if missed:
            raise ReplayMiss(f"{d}: {len(missed)} recorded call(s) before the fork point were never asked for: {', '.join(missed[:5])}")
        PV.annotate(d, fork={"calls": dict(pol.counts)})
        made.append(d)
    return made


def branches(run) -> dict:
    """The lineage of a run: its ancestors (run.json parent pointers, root first) and the tree of branches made from the root
    (found among run directories next to it and one level inside them, e.g. replicates). {"ancestors": [...], "tree": node};
    node: {run, name, kind, round, replicate, schedule, status, children}."""
    run = Path(run).resolve()
    chain, cur, seen = [], run, set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        p = (PV.read(cur) or {}).get("parent")
        cur = Path(p["run"]).resolve() if p and p.get("run") and Path(p["run"]).exists() else None
    root = chain[-1]
    cands = set()
    for top in {root.parent} | {c.parent for c in chain}:
        for d in [top, *top.iterdir()] if top.exists() else []:
            for x in [d, *(d.iterdir() if d.is_dir() else [])]:
                if x.is_dir() and (x / "run.json").exists():
                    cands.add(x.resolve())
    kids: dict = {}
    for c in cands:
        p = (PV.read(c) or {}).get("parent")
        if p and p.get("run"):
            kids.setdefault(Path(p["run"]).resolve(), []).append(c)

    def node(d, depth=0):
        m = PV.read(d) or {}
        p = m.get("parent") or {}
        segs = m.get("segments") or []
        kind = next((s["kind"] for s in reversed(segs) if s.get("kind") in ("fork", "rewind")), "start") if p else "start"
        last = segs[-1] if segs else {}
        return {"run": str(d), "name": d.name, "kind": kind, "round": p.get("round"), "replicate": m.get("replicate"),
                "schedule": p.get("schedule"), "status": last.get("status"), "last_round": last.get("last_round"),
                "children": [node(c, depth + 1) for c in sorted(kids.get(d, []), key=lambda x: (str(x.parent), x.name))]
                if depth < 20 else []}
    return {"ancestors": [str(c) for c in reversed(chain)], "tree": node(root)}


def format_branches(b: dict, mark=None) -> str:
    lines = []

    def walk(n, pre=""):
        bits = [n["kind"]] + ([f"from round {n['round'] + 1}"] if n.get("round") is not None else []) \
            + ([f"replicate {n['replicate']}"] if n.get("replicate") is not None else []) \
            + ([f"interventions {', '.join(n['schedule'])}"] if n.get("schedule") else []) + ([n["status"]] if n.get("status") else [])
        lines.append(f"{pre}{n['name']}{'  <-' if mark and n['run'] == mark else ''}  ({'; '.join(bits)})  {n['run']}")
        for c in n["children"]:
            walk(c, pre + "  ")
    walk(b["tree"])
    return "\n".join(lines)


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


def cmd_fork(a) -> None:
    from charter import interventions as IV
    from charter import __main__ as M
    run = Path(a.run)
    meta = PV.read(run) or {}
    dry = bool(meta.get("dry", "_dry" in run.name))
    sandbox = None
    if (a.sandbox or ("off" if dry else "docker")) == "docker":
        from charter.sandbox import DockerSandbox
        sandbox = DockerSandbox()
    sched = []
    for f in a.apply or []:
        sched = IV.merge(sched, IV.load_schedule(f))
    try:
        dirs = fork(run, a.at, sched, a.out, a.replicates, a.replay, M.policy_for, sandbox, fresh_schedule=a.fresh_schedule,
                    allow_code_drift=a.allow_code_drift)
    except (ReplayMiss, ReplayDivergence, IV.InterventionError) as e:
        print(f"fork FAILED: {type(e).__name__}: {e}")
        raise SystemExit(1)
    from charter import report, scorer
    for d in dirs:
        scorer.score(d)
        report.build(d)
    print("\n".join(f"branch: {d}" for d in dirs))


def cmd_branches(a) -> None:
    b = branches(a.run)
    if a.json:
        print(json.dumps(b, indent=1))
    else:
        print(format_branches(b, mark=str(Path(a.run).resolve())))


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
    import argparse
    from charter import interventions as IV
    p = sub.add_parser("fork", help="branch a run at round N, apply interventions, play on with the live policy",
                       formatter_class=argparse.RawDescriptionHelpFormatter,
                       epilog="Intervention ops (schedule format: charter/interventions.py):\n" + IV.describe())
    p.add_argument("run")
    p.add_argument("--at", type=int, required=True, help="fork point: round N (0-based) is the first round played anew")
    p.add_argument("--apply", action="append", default=[], help="an intervention schedule (YAML/JSON; repeatable, merged by id)")
    p.add_argument("--replicates", type=int, default=None, help="K branches OUT/rep1..repK with distinct live seeds")
    p.add_argument("--out", default=None, help="branch directory (default <run>_fork<N>)")
    p.add_argument("--replay", choices=["strict", "prompt-match", "none"], default="strict",
                   help="strict: recorded replies before N, live from N; prompt-match: also after N while prompts match")
    p.add_argument("--fresh-schedule", action="store_true", help="drop the parent's pending interventions")
    p.add_argument("--allow-code-drift", action="store_true", help="a parent without frozen settings whose code defaults cannot be "
                   "inferred: play the branch under the current defaults (recorded) instead of refusing")
    p.add_argument("--sandbox", choices=["docker", "off"], default=None, help="default: off for dry runs, docker for model runs")
    p.set_defaults(fn=cmd_fork)
    p = sub.add_parser("branches", help="the lineage of a run: ancestors and the branches made from them")
    p.add_argument("run")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_branches)
