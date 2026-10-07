"""Run provenance: what code, interpreter, backend and inputs produced a run directory, and every model call made in it.

Writes to the run directory:
  run.json            provenance at the start of the run (git sha, dirty flag + sha of `git diff HEAD`, python, policy/backend/models,
                      llm config without secrets, dry flag, spec and instance sha, seed, a `code` block with a sha per charter module
                      and the explicit state-schema / law-API / scoring versions) and `segments`: one record per start or resume
                      (later: fork) with its first round, the code it ran under and the modules whose hash changed since the
                      previous segment. A resume under different code is recorded here, never hidden.
  calls.jsonl         one row per model call (policy.act): call id `r<round>:<agent>:<n>` (also put in the reasoning row's
                      usage["call"]), phase, model, backend, system_sha / user_sha, latency, the raw reply text of every attempt
                      (retries and failed attempts with their errors), usage and error. Scripted policies have no raw text: their
                      parsed reply is stored instead.
  prompts/system/<sha>.txt  each distinct system prompt sent, once (content-addressed: sha256 of the text, first 16 hex digits);
                      context runs rebuild the system prompt every turn, so this is the only record of what was actually sent.
  abandoned_calls.jsonl  calls of rounds abandoned by fail-stop or cut by a resume (kept, not deleted).

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
APPEND_ONLY = ("events.jsonl", "reasoning.jsonl", "observer.jsonl", "calls.jsonl")
KEEP_CUT = {"calls.jsonl": "abandoned_calls.jsonl"}                     # cut bytes of these files are moved, not deleted
SECRET = re.compile(r"key|token|secret|password|credential|auth", re.I)


def sha(text) -> str:
    b = text if isinstance(text, bytes) else str(text).encode()
    return hashlib.sha256(b).hexdigest()[:16]


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
    return {"state_schema": kernel.STATE_SCHEMA, "law_api": lawlang.LAW_API_VERSION, "scoring": scorer.SCORING_VERSION}


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


def begin(out, inst: dict, policy, kind: str, first_round: int, dry: bool | None = None, checkpoint_version=None) -> dict:
    """Write run.json at a start (kind "start": a fresh run.json) or append a segment (kind "resume", later "fork")."""
    out = Path(out)
    code, git, env, pol = code_block(), git_info(), env_info(), policy_info(policy, inst, dry)
    prev = read(out) if kind != "start" else None
    seg = {"kind": kind, "first_round": first_round, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "git": git,
           "python": env["python"], "dry": pol["dry"], "backend": pol["backend"], "argv": list(sys.argv), "code": code}
    if checkpoint_version is not None:
        seg["checkpoint_version"] = checkpoint_version
    if prev is None:
        spec = inst.get("spec") or {}
        data = {"run_id": inst.get("run_id") or out.name, "created": seg["started"], "seed": inst.get("seed"),
                "spec_sha": sha(json.dumps(spec, sort_keys=True, default=str)),
                "instance_sha": sha(json.dumps(inst, sort_keys=True, default=str)),
                **pol, "git": git, **env, "code": code, "segments": []}
        if kind != "start":
            data["note"] = "run.json first written on a resume: earlier segments are unknown"
        seg["changed_modules"], seg["changed_versions"] = [], {}
    else:
        data = prev
        last = (data.get("segments") or [{}])[-1].get("code") or data.get("code") or {}
        old, new = last.get("modules") or {}, code["modules"]
        seg["changed_modules"] = sorted(m for m in set(old) | set(new) if old.get(m) != new.get(m))
        seg["changed_versions"] = {v: [last.get(v), code[v]] for v in ("state_schema", "law_api", "scoring") if last.get(v) != code[v]}
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

    def act(self, k, a, system, user, n_actions, final):
        r, aid = getattr(k, "r", None), a.get("id")
        with self._lock:
            i = self._n.get((r, aid), 0)
            self._n[(r, aid)] = i + 1
        cid = f"r{r}:{aid}:{i}"
        sys_sha = self._prompt(system or "")
        attempts = None
        t0 = time.monotonic()
        if hasattr(self.inner, "act_recorded"):
            out, reasoning, usage, attempts = self.inner.act_recorded(k, a, system, user, n_actions, final)
        else:
            out, reasoning, usage = self.inner.act(k, a, system, user, n_actions, final)
        latency = round(time.monotonic() - t0, 3)
        o = out if isinstance(out, dict) else {}
        usage = {**(usage or {}), "call": cid}
        row = {"call": cid, "round": r, "agent": aid, "phase": a.get("phase") or ("observer" if a.get("cls") == "observer" else None),
               "model": a.get("model"), "backend": (attempts[-1].get("backend") if attempts else None) or getattr(self.inner, "backend", None)
               or "scripted", "system_sha": sys_sha, "system_chars": len(system or ""), "user_sha": sha(user or ""),
               "user_chars": len(user or ""), "latency_s": latency, "usage": usage, "error": o.get("_error")}
        if attempts is not None:
            row["attempts"] = attempts
            row["n_attempts"] = len(attempts)
            if not (attempts and attempts[-1].get("raw")):
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
