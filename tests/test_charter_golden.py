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
from charter import generator, manual, runner, scorer
from charter import spec as S
from charter.kernel import Kernel

import charter_law_v2_laws as V2

GOLDEN = Path(__file__).parent / "fixtures" / "charter_golden.json"

# society, shrunk: every post-review module on (context, conflict, media2, jurisdictions, life with mortality, roles with the
# Scholar and Maker, typed camps, observer, events, outside power), 11 founders, 4 rounds. Lifespans are 3-6 rounds, everyone
# starts armed and conflict has no grace period, so births, attacks, deaths (mortality: bequests, succession, roles passing on)
# all happen inside the short run (seed 5: 1 birth, 6 attacks, 6 disabled, a jurisdiction founded, editions, a tribute).
SOCIETY_SMALL = ["rounds=4", "agents={worker: 4, scientist: 2, legislator: 2, media: 0, board: 2, fixer: 1}",
                 "life.full_scale_rounds=4", "life.lifespan=[3, 6]", "life.elapsed=[0, 2]", "outside_power.every=2",
                 "conflict.grace=0", "conflict.start.weapons=3"]

CASES = {
    "E2_seq_6": ("E2", 3, ["rounds=6"]),
    "E4_fast_4": ("E4", 1, ["rounds=4", "turns=simultaneous"]),
    "E6_seq_3": ("E6", 2, ["rounds=3"]),
    "E7_events_3": ("E7", 4, ["rounds=3"]),
    "E4_observer_hidden_4": ("E4", 5, ["rounds=4", "turns=simultaneous", "observer.enabled=true", "events.enabled=true",
                                       "outside_power.enabled=true", "outside_power.every=2"]),
    "society_small_4": ("society", 5, SOCIETY_SMALL),
    "E2_rng2_drift_5": ("E2", 3, ["rounds=5", "rng_version=2", "conditions.drift=true", "camps.drift_every=2"]),   # P5.3 streams
    # P3.1: law.v2 (new-style hooks from any cause, cascades, gas) with library-style v2 laws (tests/charter_law_v2_laws.py) in force
    "society_law_v2": ("society", 5, SOCIETY_SMALL + ["rounds=3", "law.v2=true", "start_laws=" + json.dumps(V2.GOLDEN_LAWS)]),
}
V2_CASES = {"society_law_v2"}                          # their start laws are test fixtures: registered in library.LIB while they run

PROMPT_CASES = {                                       # (preset, seed): system prompt and manual of every agent, with a kernel
    "prompts_society_5": ("society", 5),
    "prompts_E4_1": ("E4", 1),
}


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
    if name in V2_CASES:
        with V2.registered():
            return _fingerprint(name, tmp)
    return _fingerprint(name, tmp)


def _fingerprint(name: str, tmp: Path) -> dict:
    preset, seed, sets = CASES[name]
    sp = S.apply_overrides(S.load(preset), sets + ["shared_archive.enabled=false"])
    inst = generator.generate(sp, seed)
    inst["run_id"] = f"golden_{name}"
    out = runner.run(inst, AG.ScriptedPolicy(seed), tmp / name, log=lambda *a: None)
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
def test_golden_dry_run(name, tmp_path):
    _check(name, fingerprint(name, tmp_path))


@pytest.mark.parametrize("name", sorted(PROMPT_CASES))
def test_prompt_fingerprints(name):
    _check(name, prompt_fingerprint(name))


def test_golden_runs_are_deterministic(tmp_path):
    a = fingerprint("E4_fast_4", tmp_path / "a")
    b = fingerprint("E4_fast_4", tmp_path / "b")
    assert a == b
