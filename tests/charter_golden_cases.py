"""The golden cases (scripted runs of several presets) and the runs built from them, shared by tests/test_charter_golden.py and
tests/test_charter_history.py.

Each golden run is built once per test session (per xdist worker) by the session fixture `golden_runs` (tests/conftest.py) and
read by both modules: the golden tests fingerprint its files, the History tests score it and compare it with the run's in-memory
parts, which the build records with transparent spies (they call straight through and only keep copies). The runs are read-only
for the tests that share them. Both modules carry the xdist group "golden_runs" so that `-n` keeps them on one worker (conftest
switches plain `--dist load` to `loadgroup`).

Everything here is offline: ScriptedPolicy is a heuristic bot that never calls a model, and the shared archive is off so the
results do not depend on what a local archive directory holds.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from charter import agents as AG
from charter import generator, runner
from charter import spec as S

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
    "E2_library2_6": ("E2", 3, ["rounds=6", "law.v2=true", "law.library.edition=2", "law.library.access=catalogue",   # P3.9
                                "start_laws=[Crown Currency, Loan Registry, Usury Law, Wealth Tax, Harvest Levy, Transfer Tax, "
                                "Mint by Ballot]"]),
    # P4.3: contracts (associations) with law.v2: the scripted bots found a club, a cartel, a crowdfund and a company, join, set
    # allowances, deposit escrow, vote a change and leave (contracts.scripted_actions)
    "contracts_small": ("E2", 3, ["rounds=5", "law.v2=true", "contracts.enabled=true"]),
}
V2_CASES = {"society_law_v2"}                          # their start laws are test fixtures: registered in library.LIB while they run

PROMPT_CASES = {                                       # (preset, seed): system prompt and manual of every agent, with a kernel
    "prompts_society_5": ("society", 5),
    "prompts_E4_1": ("E4", 1),
}


def instance(name: str) -> dict:
    preset, seed, sets = CASES[name]
    inst = generator.generate(S.apply_overrides(S.load(preset), sets + ["shared_archive.enabled=false"]), seed)
    inst["run_id"] = f"golden_{name}"
    return inst


def run(name: str, tmp: Path) -> Path:
    """A plain run of a golden case (no spies) into tmp/name; returns the run directory."""
    if name in V2_CASES:                               # their start laws are test fixtures (tests/charter_law_v2_laws.py)
        with V2.registered():
            return _run(name, tmp)
    return _run(name, tmp)


def _run(name, tmp):
    preset, seed, _ = CASES[name]
    return runner.run(instance(name), AG.ScriptedPolicy(seed), tmp / name, log=lambda *a: None)


# ------------------------------------------------------------------ a run with its in-memory parts (for History)
class _JsonSpy:
    """Stands in for runner's `json` module: records the last ground-truth dict the runner serialises (still in memory)."""

    def __init__(self, store):
        self._store = store

    def dumps(self, obj, *a, **kw):
        if isinstance(obj, dict) and "rounds_played" in obj and "goals" in obj:
            self._store["truth"] = copy.deepcopy(obj)
        return json.dumps(obj, *a, **kw)

    def __getattr__(self, name):
        return getattr(json, name)


def build(name: str, tmp: Path) -> tuple[Path, dict]:
    """A golden run into tmp/name, with what the runner held in memory: the instance as written to instance.json, the kernel's
    snapshots and events, and the ground-truth dict. The spies only record; the files are those of a plain run."""
    if name in V2_CASES:
        with V2.registered():
            return _build(name, tmp)
    return _build(name, tmp)


def _build(name, tmp):
    preset, seed, _ = CASES[name]
    inst = instance(name)
    mem = {}
    real_begin, real_truth = runner.PV.begin, runner._truth

    def begin(out, inst_, *a, **kw):                     # the instance as it is written to instance.json (before the run edits it)
        mem["instance"] = json.loads(json.dumps(inst_, default=str))
        return real_begin(out, inst_, *a, **kw)

    def truth(out, inst_, k, *a, **kw):
        mem["snapshots"], mem["events"] = copy.deepcopy(k.snapshots), copy.deepcopy(k.events)
        return real_truth(out, inst_, k, *a, **kw)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(runner.PV, "begin", begin)
        mp.setattr(runner, "_truth", truth)
        mp.setattr(runner, "json", _JsonSpy(mem))
        out = runner.run(inst, AG.ScriptedPolicy(seed), tmp / name, log=lambda *a: None)
    return out, mem


class Runs(Mapping):
    """name -> (run directory, in-memory parts), each golden run built on first use and then kept (read-only for the tests)."""

    def __init__(self, tmp: Path):
        self._tmp, self._built = tmp, {}

    def __getitem__(self, name):
        if name not in CASES:
            raise KeyError(name)
        if name not in self._built:
            self._built[name] = build(name, self._tmp)
        return self._built[name]

    def __iter__(self):
        return iter(sorted(CASES))

    def __len__(self):
        return len(CASES)
