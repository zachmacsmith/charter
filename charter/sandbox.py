"""Scientists' private Python sandbox: each call runs in a throwaway container with numpy and scipy, no network, 10 s, 512 MB."""
from __future__ import annotations

import subprocess
from pathlib import Path

IMAGE = "charter-sandbox"


class DockerSandbox:
    def __init__(self, timeout=10):
        self.timeout = timeout
        self._built = False

    def build(self):
        if not self._built:
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
