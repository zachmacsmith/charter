"""Golden dry-run fingerprints: scripted runs of several presets must produce byte-identical events, snapshots and instances.

Refactors must leave these unchanged. A deliberate behaviour change updates them with
    CHARTER_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_charter_golden.py
and the commit message says why.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from charter import agents as AG
from charter import generator, runner
from charter import spec as S

GOLDEN = Path(__file__).parent / "fixtures" / "charter_golden.json"

CASES = {
    "E2_seq_6": ("E2", 3, ["rounds=6"]),
    "E4_fast_4": ("E4", 1, ["rounds=4", "turns=simultaneous"]),
    "E6_seq_3": ("E6", 2, ["rounds=3"]),
    "E7_events_3": ("E7", 4, ["rounds=3"]),
    "E4_observer_hidden_4": ("E4", 5, ["rounds=4", "turns=simultaneous", "observer.enabled=true", "events.enabled=true",
                                       "outside_power.enabled=true", "outside_power.every=2"]),
}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def fingerprint(name: str, tmp: Path) -> dict:
    preset, seed, sets = CASES[name]
    sp = S.apply_overrides(S.load(preset), sets + ["shared_archive.enabled=false"])
    inst = generator.generate(sp, seed)
    inst["run_id"] = f"golden_{name}"
    out = runner.run(inst, AG.ScriptedPolicy(seed), tmp / name, log=lambda *a: None)
    return {f: _sha((out / f).read_bytes()) for f in ("instance.json", "events.jsonl", "snapshots.json")}


@pytest.mark.parametrize("name", sorted(CASES))
def test_golden_dry_run(name, tmp_path):
    got = fingerprint(name, tmp_path)
    stored = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else {}
    if os.environ.get("CHARTER_UPDATE_GOLDEN"):
        stored[name] = got
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(stored, indent=1, sort_keys=True) + "\n")
        return
    assert name in stored, f"no golden fingerprint for {name}; run with CHARTER_UPDATE_GOLDEN=1"
    assert got == stored[name], f"{name} changed: {got} != {stored[name]}"


def test_golden_runs_are_deterministic(tmp_path):
    a = fingerprint("E4_fast_4", tmp_path / "a")
    b = fingerprint("E4_fast_4", tmp_path / "b")
    assert a == b
