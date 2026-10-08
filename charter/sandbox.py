"""Scientists' private Python sandbox: each call runs in a throwaway container with numpy and scipy, no network, 10 s, 512 MB.
Every call a run makes is recorded (Recording: sandbox.jsonl + blobs), and replays and forks serve the recorded outputs
(replay.ReplaySandbox) instead of running Docker again."""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

IMAGE = "charter-sandbox"


class DockerSandbox:
    def __init__(self, timeout=10):
        self.timeout = timeout
        self._built = False

    def build(self):
        if not self._built:
            have = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0
            if not have:                                                 # a prebuilt image (e.g. behind a proxy) is used as is
                subprocess.run(["docker", "build", "-q", "-t", IMAGE, str(Path(__file__).parent / "sandbox")], check=True, capture_output=True)
            self._built = True

    def __call__(self, agent: str, code: str) -> str:
        self.build()
        try:
            p = subprocess.run(["docker", "run", "--rm", "-i", "--network", "none", "--memory", "512m", "--cpus", "1", "--pids-limit", "64",
                                IMAGE, "timeout", str(self.timeout), "python", "-"], input=code, capture_output=True, text=True,
                               timeout=self.timeout + 30)
        except subprocess.TimeoutExpired:
            return "timed out"
        out = (p.stdout + p.stderr).strip()
        if p.returncode == 124:
            out += "\n(timed out after 10 s)"
        return out[:4000] or "(no output)"


def disabled(agent: str, code: str) -> str:
    return "(the sandbox is disabled in this run)"


# ------------------------------------------------------------------ recording (P5.4)
RECORD = "sandbox.jsonl"                                                # <run>/sandbox.jsonl (provenance.APPEND_ONLY)


def call_id(round_, agent, n) -> str:
    """A sandbox call's key: the n-th sandbox call of `agent` in round `round_` (0-based, as k.r): `r<round>:<agent>:<n>`."""
    return f"r{round_}:{agent}:{n}"


class Recording:
    """Wraps the sandbox the kernel calls (k.sandbox(agent, code)): every call's code and output are stored as content-addressed
    blobs (blobs/<sha256>) and a row {call, round, agent, n, code, output, chars} appended to sandbox.jsonl, so a replay or fork
    serves the output (replay.ReplaySandbox) instead of running Docker again (its 10 s timeout and any time/random use make
    re-running nondeterministic). A wrapped sandbox with `takes_key` gets the call key as `key=`. `k` (the kernel, for the
    round) is set by the runner once the kernel exists. append: a resume (counters go on from the rows kept)."""

    def __init__(self, inner, out, k=None, append: bool = False):
        self.inner, self.out, self.k = inner, Path(out), k
        self._lock = threading.Lock()
        self._n: dict = {}
        p = self.out / RECORD
        if append and p.exists():
            for ln in p.read_text().splitlines():
                if ln.strip():
                    row = json.loads(ln)
                    kt = (row["round"], row["agent"])
                    self._n[kt] = max(self._n.get(kt, 0), row["n"] + 1)
        elif not append:
            p.write_text("")                                            # present (if empty): the run records its sandbox calls

    def __call__(self, agent: str, code: str) -> str:
        from charter import provenance as PV
        r = getattr(self.k, "r", None)
        with self._lock:
            n = self._n.get((r, agent), 0)
            self._n[(r, agent)] = n + 1
        key = {"call": call_id(r, agent, n), "round": r, "agent": agent, "n": n}
        inner = self.inner
        out = str(inner(agent, code, key=key) if getattr(inner, "takes_key", False) else inner(agent, code))
        row = {**key, "code": PV.put_blob(self.out, str(code)), "output": PV.put_blob(self.out, out), "chars": len(out)}
        if getattr(inner, "takes_key", False) and key["call"] in getattr(inner, "served", ()):
            row["replayed"] = True
        with self._lock, open(self.out / RECORD, "a") as f:
            f.write(json.dumps(row) + "\n")
        return out
