"""Run provenance: what code, interpreter, backend and inputs produced a run directory, and every model call made in it.

Writes to the run directory:
  run.json            provenance at the start of the run (`log_format`: the raw format version, LOG_FORMAT; git sha, dirty
                      flag + sha of `git diff HEAD`, python, policy/backend/models, llm config without secrets, dry flag, spec and instance sha, seed, a `code` block with a sha per charter module
                      and the explicit state-schema / law-API / scoring versions) and `segments`: one record per start or resume
                      (rewind and fork: replay.py) with its first round, the code it ran under and the modules whose hash changed since the
                      previous segment. A resume under different code is recorded here, never hidden.
  calls.jsonl         one row per model call (policy.act): call id `r<round>:<agent>:<n>` (also put in the reasoning row's
                      usage["call"]), the explicit call key the runner passes ({round, phase, wave, agent, n} and its id
                      `r<round>:<phase>:<wave>:<agent>:<n>`, the replay key: see call_key), phase, model, backend, system_sha /
                      user_sha, latency, the raw reply text of every attempt (retries and failed attempts with their errors), the
                      reasoning text returned, usage and error. The parsed reply is stored as well whenever the raw text would not
                      give it back through llm.parse_json (scripted policies have no raw text: always), so every row can be replayed
                      exactly (charter/replay.py).
  prompts/system/<sha>.txt  each distinct system prompt sent, once (content-addressed: sha256 of the text, first 16 hex digits);
                      context runs rebuild the system prompt every turn, so this is the only record of what was actually sent.
  abandoned_calls.jsonl  calls of rounds abandoned by fail-stop or cut by a resume (kept, not deleted).
  blobs/<sha256>      content-addressed store (full sha256 hex of the bytes; each distinct content once): the frozen shared
                      archive's base and overlay texts (archive.py, archive/base.json, archive_overlay.jsonl) and sandbox code and
                      outputs (sandbox.py, sandbox.jsonl). put_blob / get_blob.
  run.json `shared_archive`  the frozen archive's snapshot: {enabled, hash (of archive/base.json's file map), docs_hash (the
                      documents only: archive.snapshot's hash), files, taken, source, publish} (archive.Frozen).

APPEND_ONLY lists every file the runner appends to; checkpoints store each one's size and a resume or fail-stop cuts each back to it
(the one registry checkpoints and failstop.abandon consult).
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

PKG = Path(__file__).resolve().parent
REPO = PKG.parent
APPEND_ONLY = ("events.jsonl", "reasoning.jsonl", "observer.jsonl", "calls.jsonl", "turns.jsonl",   # turns.jsonl: k.turn_log
               "archive_overlay.jsonl", "sandbox.jsonl",                # P5.4: this run's shared-archive writes; sandbox calls
               "memory.jsonl")                                          # review 20: history mode's round records (charter/memory.py)
KEEP_CUT = {"calls.jsonl": "abandoned_calls.jsonl"}                     # cut bytes of these files are moved, not deleted
SECRET = re.compile(r"key|token|secret|password|credential|auth", re.I)
# The raw log format (run.json `log_format`): bump it when what the runner writes into a run directory changes shape, and keep
# charter/export.py able to read every format ever written (docs/data_format.md). 0: before the field existed; 1: export schema 2.
LOG_FORMAT = 1

# The engine version (docs/engine_versions.md): bump it whenever a code default flips or the simulation's behaviour changes on purpose,
# and list the flips in ENGINE_FLIPS. run.json `engine_version` (the code's) and inst["settings"]["engine_version"] (the defaults a
# run plays under, charter/settings.py) record it. ENGINE_FLIPS[v]: the commits that made version v (the first decides, by git
# ancestry, whether a run's recorded sha has it: settings.infer_version) and the default flips, (settings target, key path, old,
# new); settings.use sets a flip back to `old` for a run of an earlier version whose frozen snapshot lacks the key.
ENGINE_VERSION = 7
ENGINE_FLIPS = {
    2: {"commits": ["38070e15cf97e171258cd0dbdb7ddfd710ed30ab"],
        "flips": [("charter.channels.DEFAULTS", ("delivery",), "pull", "push")],
        "note": "channels v2: push delivery by default"},
    3: {"commits": ["55d11fb785f1b859193d3b301fd8a7276f1fbbde", "97631829d31ce90bf9775a48a297e93babcf62a2"],
        "flips": [],
        "note": "dm_step.capacity natural (opt-in key, set by nature_subsistence and ashwood); the Communications Act caps at LIMIT "
                "under natural (behaviour, not a default)"},
    4: {"commits": ["6a69002946d066769d9a6b25f68b8cf5e8b3e4f6"],
        "flips": [("charter.context.DEFAULTS", ("memory_text",), "v1", "v2")],
        "note": "context.memory_text v2 by default"},
    5: {"commits": ["23c948aaefc9e12fa7cb1ee1e0bc0837d024a808", "b629aa09a0e9b132fed5e10ce52f4df65b3bda75"],
        "flips": [("charter.context.DEFAULTS", ("dm_delta",), False, True)],
        "note": "context.dm_delta on by default; the next round shows last round's DM exchange whole (under dm_delta)"},
    6: {"commits": ["b04001c96682f890f5089b4c0f0e8251db7918c0", "b8e4b73ca847cbbfbbe40b0001baef7a987dd070"],
        "flips": [("charter.context.DEFAULTS", ("history", "enabled"), False, True)],
        "note": "history mode on by default (review 20 §4: chunked conversations, the memory gradient, recall); recall added to "
                "the lookups and actions (only in history mode)"},
    7: {"commits": ["05f21c4550da3c39ed4f2c0bff3602cb5ecd5894"],
        "flips": [],
        "note": "llm.cache_ttl 5m in base.yaml (a spec key, so each run's saved spec records it; absent = auto, the backend's choice, "
                "which was 1h on the CLI subscription); a run flags rounds averaging longer than the lifetime"},
}


def sha(text) -> str:
    b = text if isinstance(text, bytes) else str(text).encode()
    return hashlib.sha256(b).hexdigest()[:16]


# ------------------------------------------------------------------ content-addressed blobs (P5.4)
BLOBS = "blobs"


def blob_sha(data) -> str:
    """A blob's name: the full sha256 hex of its bytes (text as UTF-8)."""
    return hashlib.sha256(data if isinstance(data, bytes) else str(data).encode()).hexdigest()


def put_blob(out, data) -> str:
    """Store bytes (or text, as UTF-8) under blobs/<sha256> once; return the sha."""
    b = data if isinstance(data, bytes) else str(data).encode()
    h = blob_sha(b)
    d = Path(out) / BLOBS
    p = d / h
    if not p.exists():
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f".{h}.{os.getpid()}.{threading.get_ident()}.tmp"
        tmp.write_bytes(b)
        os.replace(tmp, p)
    return h


def get_blob(out, h: str, text: bool = True):
    """A blob's content (str, or bytes with text=False); KeyError when it is missing."""
    p = Path(out) / BLOBS / h
    if not p.exists():
        raise KeyError(f"blob {h} is missing from {Path(out) / BLOBS}")
    b = p.read_bytes()
    return b.decode() if text else b


def copy_blobs(src, dst, shas) -> None:
    """Copy the named blobs from one run directory's store to another's (hard links where possible)."""
    sd, dd = Path(src) / BLOBS, Path(dst) / BLOBS
    for h in set(shas):
        if (dd / h).exists():
            continue
        dd.mkdir(parents=True, exist_ok=True)
        try:
            os.link(sd / h, dd / h)
        except OSError:
            import shutil
            shutil.copy2(sd / h, dd / h)


# ------------------------------------------------------------------ append-only files (checkpoint offsets)
def offsets(out) -> dict:
    """Size of every append-only file (0 when absent, so a file created after the checkpoint is cut to nothing on resume).
    Flush open handles before calling."""
    out = Path(out)
    return {n: (os.path.getsize(out / n) if (out / n).exists() else 0) for n in APPEND_ONLY}


def truncate(out, sizes: dict, why: str = "") -> None:
    """Cut each file back to its checkpointed size; the cut part of calls.jsonl goes to abandoned_calls.jsonl."""
    out = Path(out)
    for name, size in sizes.items():
        p = out / name
        if not p.exists() or p.stat().st_size <= size:
            continue
        if name in KEEP_CUT:
            with open(p, "rb") as f:
                f.seek(size)
                tail = f.read()
            with open(out / KEEP_CUT[name], "ab") as g:
                for ln in tail.splitlines():
                    if ln.strip():
                        try:
                            row = json.loads(ln)
                        except json.JSONDecodeError:
                            continue
                        g.write((json.dumps({**row, "abandoned": why or True}) + "\n").encode())
        with open(p, "r+b") as f:
            f.truncate(size)


# ------------------------------------------------------------------ code version
def module_hashes() -> dict:
    """sha of each charter/*.py and of each subpackage (all its .py files, by relative path)."""
    out = {}
    for p in sorted(PKG.glob("*.py")):
        out[p.stem] = sha(p.read_bytes())
    for d in sorted(x for x in PKG.iterdir() if x.is_dir() and (x / "__init__.py").exists()):
        h = hashlib.sha256()
        for p in sorted(d.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            h.update(str(p.relative_to(d)).encode() + b"\0" + p.read_bytes() + b"\0")
        out[d.name + "/"] = h.hexdigest()[:16]
    return out


def versions() -> dict:
    from charter import kernel, lawlang, scorer
    return {"state_schema": kernel.STATE_SCHEMA, "law_api": lawlang.LAW_API_VERSION, "scoring": scorer.SCORING_VERSION,
            "engine": ENGINE_VERSION}


def code_block() -> dict:
    return {"modules": module_hashes(), **versions()}


def _git(*args) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.decode(errors="replace") if p.returncode == 0 else None


def git_info() -> dict:
    head = _git("rev-parse", "HEAD")
    if head is None:
        return {"sha": None, "dirty": None}
    status = _git("status", "--porcelain", "--untracked-files=no") or ""
    info = {"sha": head.strip(), "branch": (_git("rev-parse", "--abbrev-ref", "HEAD") or "").strip() or None, "dirty": bool(status.strip())}
    if info["dirty"]:
        info["diff_sha"] = sha((_git("diff", "HEAD") or "").encode())
    untracked = [x for x in (_git("ls-files", "--others", "--exclude-standard", "--", "charter") or "").splitlines() if x.endswith(".py")]
    if untracked:
        info["untracked_py"] = untracked
    return info


# ------------------------------------------------------------------ policy / backend description (never secrets)
def _scrub(x):
    if isinstance(x, dict):
        return {k: ("<redacted>" if SECRET.search(str(k)) else _scrub(v)) for k, v in x.items()}
    if isinstance(x, list):
        return [_scrub(v) for v in x]
    return x


def policy_info(policy, inst: dict, dry: bool | None) -> dict:
    inner = policy
    is_llm = getattr(inner, "llm", None) is not None
    models = sorted({a.get("model") for a in inst.get("agents", []) if a.get("model")}
                    | ({inst["observer"]["model"]} if (inst.get("observer") or {}).get("model") else set()))
    info = {"dry": (not is_llm) if dry is None else bool(dry), "policy": type(inner).__name__,
            "backend": getattr(inner, "backend", None) if is_llm else "scripted", "models": models,
            "llm": _scrub((inst.get("spec") or {}).get("llm") or {})}
    return info


def env_info() -> dict:
    pk = {}
    for name in ("anthropic", "pyyaml"):
        try:
            from importlib.metadata import version
            pk[name] = version(name)
        except Exception:
            pass
    return {"python": sys.version.split()[0], "implementation": platform.python_implementation(), "platform": platform.platform(),
            "packages": pk}


# ------------------------------------------------------------------ run.json and segments
def _write(out, data) -> None:
    p = Path(out) / "run.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str))
    os.replace(tmp, p)


def read(out) -> dict | None:
    p = Path(out) / "run.json"
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def begin(out, inst: dict, policy, kind: str, first_round: int, dry: bool | None = None, checkpoint_version=None,
          instance_source=None) -> dict:
    """Write run.json at a start (kind "start": a fresh run.json, `parent` and `replicate` null) or append a segment (kind
    "resume"; rewinds and forks get theirs from branch())."""
    out = Path(out)
    code, git, env, pol = code_block(), git_info(), env_info(), policy_info(policy, inst, dry)
    prev = read(out) if kind != "start" else None
    seg = {"kind": kind, "first_round": first_round, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "git": git,
           "python": env["python"], "dry": pol["dry"], "backend": pol["backend"], "argv": list(sys.argv), "code": code}
    if checkpoint_version is not None:
        seg["checkpoint_version"] = checkpoint_version
    if instance_source is not None:
        seg["instance"] = instance_source
    from charter import settings as ST
    st = ST.describe(inst)
    if st is not None:
        seg["settings"] = st                                           # the engine version of the defaults it played under
    if prev is None:
        spec = inst.get("spec") or {}
        data = {"run_id": inst.get("run_id") or out.name, "created": seg["started"], "log_format": LOG_FORMAT,
                "engine_version": ENGINE_VERSION,
                "seed": inst.get("seed"),
                "spec_sha": sha(json.dumps(spec, sort_keys=True, default=str)),
                "instance_sha": sha(json.dumps(inst, sort_keys=True, default=str)),
                **pol, "git": git, **env, "code": code, "parent": None, "replicate": None, "segments": []}
        if kind != "start":
            data["note"] = "run.json first written on a resume: earlier segments are unknown"
        seg["changed_modules"], seg["changed_versions"] = [], {}
    else:
        data = prev
        last = (data.get("segments") or [{}])[-1].get("code") or data.get("code") or {}
        old, new = last.get("modules") or {}, code["modules"]
        seg["changed_modules"] = sorted(m for m in set(old) | set(new) if old.get(m) != new.get(m))
        seg["changed_versions"] = {v: [last.get(v), code[v]] for v in ("state_schema", "law_api", "scoring", "engine")
                                  if last.get(v) != code[v]}
        if pol["dry"] != data.get("dry"):
            seg["dry_changed"] = [data.get("dry"), pol["dry"]]
    data.setdefault("segments", []).append(seg)
    _write(out, data)
    return seg


def end(out, status: str, last_round: int | None) -> None:
    """Mark the current segment's end: status "complete" or "stopped" (fail-stop), with the last round kept."""
    data = read(out)
    if not data or not data.get("segments"):
        return
    data["segments"][-1].update({"ended": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "status": status, "last_round": last_round})
    _write(out, data)


def branch(out, kind: str, first_round: int, parent: dict) -> dict:
    """A new run directory made from another (kind "rewind" or "fork"): run.json (copied from the parent) gets `parent` and a
    segment of that kind, with the code it was made under; the resume that continues it appends its own segment as usual."""
    out = Path(out)
    data = read(out) or {"segments": [], "note": "parent had no run.json"}
    code, git, env = code_block(), git_info(), env_info()
    last = (data.get("segments") or [{}])[-1].get("code") or data.get("code") or {}
    old, new = last.get("modules") or {}, code["modules"]
    seg = {"kind": kind, "first_round": first_round, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "git": git,
           "python": env["python"], "argv": list(sys.argv), "code": code, "parent": parent,
           "changed_modules": sorted(m for m in set(old) | set(new) if old.get(m) != new.get(m)), "status": "ready"}
    data["lineage"] = list(data.get("lineage") or []) + ([data["parent"]] if data.get("parent") else [])
    data.update({"run_id": out.name, "parent": parent, "created": seg["started"]})
    data.setdefault("segments", []).append(seg)
    _write(out, data)
    return seg


def annotate(out, **fields) -> None:
    """Add top-level fields to run.json (e.g. what a replay reproduced)."""
    data = read(out)
    if data is not None:
        data.update(fields)
        _write(out, data)


# ------------------------------------------------------------------ call keys
def call_key(key: dict) -> str:
    """The id of an explicit call key: `r<round>:<phase>:<wave>:<agent>:<n>` (e.g. r3:decide:0:a4:0, r3:dm_reply:2:a4:0)."""
    return f"r{key['round']}:{key['phase']}:{key.get('wave') or 0}:{key['agent']}:{key.get('n') or 0}"


def reply_from_raw(attempts, error):
    """The parsed reply a recorded model call gives back from its raw text alone (the last attempt through llm.parse_json; every
    attempt failed: llm.call's empty turn with the error), or None when it cannot be rebuilt (the row then stores `parsed`)."""
    if not attempts:
        return None
    last = attempts[-1]
    if last.get("ok") and last.get("raw"):
        from charter import llm
        try:
            return llm.parse_json(last["raw"])
        except Exception:
            return None
    if not last.get("ok") and error and not any(x.get("ok") for x in attempts):
        return {"actions": [], "notes": "", "goal_guesses_json": "{}", "_error": error}
    return None


class Keyed:
    """A policy view that tags every call with a key (phase, wave): the runner hands it to code that calls policy.act itself
    (the observer's turn, media2's editorial turns), so those calls get explicit keys too."""

    def __init__(self, inner, **key):
        self.inner, self.key = inner, key

    def __getattr__(self, name):
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)

    def act(self, k, a, system, user, n_actions, final, key=None):
        return self.inner.act(k, a, system, user, n_actions, final, key={**self.key, **(key or {})})


# ------------------------------------------------------------------ model-call recording
class Recorder:
    """Wraps a policy: every policy.act is recorded in calls.jsonl, its system prompt stored once under prompts/system/.
    Attribute access falls through to the wrapped policy (rng, parallel_safe, ...). Thread-safe (parallel calls)."""

    def __init__(self, inner, out, append: bool):
        self.inner, self.out = inner, Path(out)
        self._lock = threading.Lock()
        self._n: dict = {}
        self._dir = self.out / "prompts" / "system"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._known = {p.stem for p in self._dir.glob("*.txt")}
        if not append and (self.out / "abandoned_calls.jsonl").exists():   # a fresh start: nothing abandoned yet
            (self.out / "abandoned_calls.jsonl").unlink()
        if append and (self.out / "calls.jsonl").exists():             # a resume: counters go on from the kept calls (e.g. the editorial
            for ln in (self.out / "calls.jsonl").read_text().splitlines():   # calls made after the checkpointed round's end, at k.r + 1)
                try:
                    row = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                r, aid = row.get("round"), row.get("agent")
                self._n[(r, aid)] = self._n.get((r, aid), 0) + 1
                kf = row.get("key_fields")
                if kf:
                    kt = (kf["round"], kf["phase"], kf["wave"], kf["agent"])
                    self._n[kt] = max(self._n.get(kt, 0), kf["n"] + 1)
        self.f = open(self.out / "calls.jsonl", "a" if append else "w")

    def __getattr__(self, name):
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)

    def _prompt(self, system: str) -> str:
        h = sha(system)
        with self._lock:
            if h not in self._known:
                p = self._dir / f"{h}.txt"
                tmp = p.with_suffix(".tmp")
                tmp.write_text(system)
                os.replace(tmp, p)
                self._known.add(h)
        return h

    def act(self, k, a, system, user, n_actions, final, key=None):
        """key: the runner's explicit call key ({"phase", "wave"}; round and agent are filled in here, n counts calls with the same
        key). Without one (direct callers, tests) the phase is inferred from the agent dict."""
        r, aid = getattr(k, "r", None), a.get("id")
        key = dict(key or {})
        key.setdefault("phase", a.get("phase") or ("observer" if a.get("cls") == "observer" else "decide"))
        key.update(round=r, agent=aid, wave=int(key.get("wave") or 0))
        with self._lock:
            i = self._n.get((r, aid), 0)
            self._n[(r, aid)] = i + 1
            kt = (r, key["phase"], key["wave"], aid)
            key["n"] = self._n.get(kt, 0)
            self._n[kt] = key["n"] + 1
        key = {x: key[x] for x in ("round", "phase", "wave", "agent", "n")}
        cid = f"r{r}:{aid}:{i}"
        sys_sha = self._prompt(system or "")
        attempts = None
        t0 = time.monotonic()
        kw = {"key": {**key, "id": call_key(key), "system_sha": sys_sha, "user_sha": sha(user or "")}} \
            if getattr(self.inner, "takes_key", False) else {}
        if hasattr(self.inner, "act_recorded"):
            out, reasoning, usage, attempts = self.inner.act_recorded(k, a, system, user, n_actions, final, **kw)
        else:
            out, reasoning, usage = self.inner.act(k, a, system, user, n_actions, final, **kw)
        latency = round(time.monotonic() - t0, 3)
        o = out if isinstance(out, dict) else {}
        usage = {**(usage or {}), "call": cid}
        row = {"call": cid, "key": call_key(key), "key_fields": key, "round": r, "agent": aid,
               "phase": a.get("phase") or ("observer" if a.get("cls") == "observer" else None),
               "model": a.get("model"), "backend": (attempts[-1].get("backend") if attempts else None) or getattr(self.inner, "backend", None)
               or "scripted", "system_sha": sys_sha, "system_chars": len(system or ""), "user_sha": sha(user or ""),
               "user_chars": len(user or ""), "latency_s": latency, "usage": usage, "error": o.get("_error"), "reasoning": reasoning}
        if getattr(self.inner, "replaying", False):
            row["replayed"] = True
        if attempts is not None:
            row["attempts"] = attempts
            row["n_attempts"] = len(attempts)
            if reply_from_raw(attempts, o.get("_error")) != o:          # the raw text alone would not give this reply back
                row["parsed"] = o
        else:
            row["parsed"] = o                                         # scripted bots: no raw text, the reply itself
        line = json.dumps(row, default=str) + "\n"
        with self._lock:
            self.f.write(line)
            self.f.flush()
        return out, reasoning, usage

    def flush(self) -> None:
        with self._lock:
            if not self.f.closed:
                self.f.flush()

    def close(self) -> None:
        with self._lock:
            if not self.f.closed:
                self.f.close()
