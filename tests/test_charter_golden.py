"""Golden fingerprints: scripted runs of several presets must produce byte-identical events, snapshots and instances, the same
goal scores, and the same system prompts and manuals.

Refactors must leave these unchanged. A deliberate behaviour change updates them with
    CHARTER_UPDATE_GOLDEN=1 python -m pytest tests/test_charter_golden.py
(fixture: tests/fixtures/charter_golden.json) and the commit message says why.

Everything here is offline: ScriptedPolicy is a heuristic bot that never calls a model, and the shared archive is off so the
results do not depend on what a local archive directory holds.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from charter import agents as AG
from charter import context as CX
from charter import generator, manual, scorer
from charter import spec as S
from charter.kernel import Kernel

import charter_golden_cases as GC
import charter_law_v2_laws as V2  # noqa: F401
from charter_golden_cases import CASES, GOLDEN, PROMPT_CASES, SOCIETY_SMALL, V2_CASES   # noqa: F401 (re-exported)

pytestmark = pytest.mark.xdist_group("golden_runs")     # shares the session's golden runs with test_charter_history.py


def _sha(b) -> str:
    if not isinstance(b, bytes):
        b = json.dumps(b, sort_keys=True, default=str).encode()
    return hashlib.sha256(b).hexdigest()[:16]


def score_fingerprint(out: Path) -> dict:
    """score.json, minus anything that names the run directory: per-agent goal scores (readable) and hashes of the rest."""
    sc = scorer.score(out)
    summary = {k: v for k, v in sc["summary"].items() if k != "run"}
    return {"goal_scores": {aid: g.get("score") for aid, g in sorted(sc["goals"].items())},
            "goals": _sha(sc["goals"]), "agents": _sha(sc["agents"]), "lineage": _sha(sc.get("lineage")),
            "summary": _sha(summary), "activity_mix": _sha(sc["metrics"].get("activity_mix"))}


def fingerprint(name: str, tmp: Path) -> dict:
    """The fingerprint of a fresh, plain run of a golden case."""
    return files_fingerprint(GC.run(name, tmp))


def files_fingerprint(out: Path) -> dict:
    fp = {f: _sha((out / f).read_bytes()) for f in ("instance.json", "events.jsonl", "snapshots.json")}
    fp["score"] = score_fingerprint(out)
    return fp


def prompt_fingerprint(name: str) -> dict:
    preset, seed = PROMPT_CASES[name]
    inst = generator.generate(S.apply_overrides(S.load(preset), ["shared_archive.enabled=false"]), seed)
    k = Kernel(inst)
    out = {}
    for a in inst["agents"]:
        core = CX.core_prompt(inst, a, k) if CX.enabled(inst) else AG.system_prompt(inst, a)
        out[a["id"]] = {"core": _sha(core.encode()), "manual_base": _sha(manual.sections(inst, k, a["id"])),
                        "manual": _sha(CX.build_manual(inst, k, a["id"]))}
    return out


def _check(name, got):
    stored = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else {}
    if os.environ.get("CHARTER_UPDATE_GOLDEN"):
        stored[name] = got
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(stored, indent=1, sort_keys=True) + "\n")
        return
    assert name in stored, f"no golden fingerprint for {name}; run with CHARTER_UPDATE_GOLDEN=1"
    want = stored[name]
    diff = sorted(x for x in set(got) | set(want) if got.get(x) != want.get(x))
    assert got == want, f"{name} changed in {diff}: {json.dumps({x: [got.get(x), want.get(x)] for x in diff})}"


@pytest.mark.parametrize("name", sorted(CASES))
def test_golden_dry_run(name, golden_runs):
    """The session's golden run of the case (built once, shared with test_charter_history.py) against the stored fingerprint."""
    _check(name, files_fingerprint(golden_runs[name][0]))


@pytest.mark.parametrize("name", sorted(PROMPT_CASES))
def test_prompt_fingerprints(name):
    _check(name, prompt_fingerprint(name))


def test_golden_runs_are_deterministic(tmp_path, golden_runs):
    """Runs of a case in one process agree: two fresh plain runs, and the session's run (built with the recording spies, so this
    also shows the spies leave the files unchanged)."""
    a = fingerprint("E4_fast_4", tmp_path / "a")
    b = fingerprint("E4_fast_4", tmp_path / "b")
    assert a == b
    assert a == files_fingerprint(golden_runs["E4_fast_4"][0])
