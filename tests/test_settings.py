"""Frozen settings (charter/settings.py, D-43): a run keeps the code defaults it was generated under; old runs get them inferred
from their git sha, or are refused."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from charter import __main__ as M
from charter import agents as AG
from charter import context as CX
from charter import generator, provenance as PV, runner
from charter import settings as ST
from charter import spec as S

QUIET = dict(log=lambda *a: None)
SETS = ["rounds=3", "shared_archive.enabled=false",
        "context.history.enabled=false"]   # history mode restarts its conversations at a resume (by design): compared with it off


def _inst():
    inst = generator.generate(S.apply_overrides(S.load("society"), SETS), 1)
    inst["run_id"] = "r"                                             # as run_one sets it (resume regenerates and compares)
    return inst


def _prompts(out: Path) -> list:
    """Every prompt of the run: the user prompts (reasoning.jsonl) and the system/user prompt hashes of every call."""
    rows = [json.loads(x) for x in (out / "reasoning.jsonl").read_text().splitlines()]
    calls = [json.loads(x) for x in (out / "calls.jsonl").read_text().splitlines()]
    return [(r.get("round"), r.get("agent"), r.get("phase"), r.get("prompt")) for r in rows] + \
           [(c["key"], c["system_sha"], c["user_sha"]) for c in calls]


def _flip(monkeypatch):
    """Today's code with the review 20 defaults flipped back (as a later commit might flip any default)."""
    monkeypatch.setitem(CX.DEFAULTS, "memory_text", "v1")
    monkeypatch.setitem(CX.DEFAULTS, "dm_delta", False)
    monkeypatch.setitem(CX.DEFAULTS["history"], "enabled", False)


def _resume(out, *extra):
    M.main(["resume", str(out), "--sandbox", "off", *extra])


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    """A whole run under the code's defaults, and a copy paused after round 1."""
    d = tmp_path_factory.mktemp("settings")
    ref = runner.run(_inst(), AG.ScriptedPolicy(1), d / "ref", **QUIET)
    part = runner.run(_inst(), AG.ScriptedPolicy(1), d / "part", until=1, **QUIET)
    return ref, part


def _copy(src: Path, dst: Path) -> Path:
    import shutil
    shutil.copytree(src, dst)
    return dst


def test_instance_freezes_every_default():
    inst = _inst()
    s = inst["settings"]
    assert s["engine_version"] == PV.ENGINE_VERSION
    assert set(s["defaults"]) == set(ST.targets())
    assert s["defaults"]["charter.context.DEFAULTS"]["memory_text"] == "v2"
    assert s["defaults"]["charter.schema.EXTRA"]["dm_step.capacity"] == "legacy"
    assert not ST.patches(s)                                          # today's code: nothing to install


def test_every_module_defaults_dict_is_registered():
    """A new *DEFAULTS dict must be frozen too: register it in settings.TARGETS."""
    pkg = Path(ST.__file__).parent
    found = set()
    for p in pkg.rglob("*.py"):
        mod = ".".join(("charter",) + p.relative_to(pkg).with_suffix("").parts)
        for m in re.finditer(r"^([A-Z_]*DEFAULTS)\s*(?::[^=]*)?=\s*\{", p.read_text(), re.M):
            if m.group(1) != "FEATURE_DEFAULTS":                         # schema's table of getters, not values
                found.add(f"{mod}.{m.group(1)}")
    assert found - set(ST.TARGETS) == set()


def test_resume_after_a_default_flip_plays_the_run_as_it_began(reference, tmp_path, monkeypatch):
    ref, part = reference
    run = _copy(part, tmp_path / "run")
    _flip(monkeypatch)
    _resume(run)
    assert _prompts(run) == _prompts(ref)                              # byte-identical prompts despite the flip
    assert CX.DEFAULTS["memory_text"] == "v1"                         # the code's defaults are back after the run
    seg = PV.read(run)["segments"][-1]
    assert seg["kind"] == "resume" and seg["settings"]["engine_version"] == PV.ENGINE_VERSION


def test_new_run_after_a_default_flip_takes_the_new_default(reference, tmp_path, monkeypatch):
    ref, _ = reference
    _flip(monkeypatch)
    inst = _inst()
    assert inst["settings"]["defaults"]["charter.context.DEFAULTS"]["memory_text"] == "v1"
    out = runner.run(inst, AG.ScriptedPolicy(1), tmp_path / "new", **QUIET)
    assert _prompts(out) != _prompts(ref)
    assert PV.read(out)["memory_text"] == "v1"


def test_without_frozen_settings_the_flip_would_leak_and_is_refused(reference, tmp_path, monkeypatch):
    """An old run (no settings, unknown sha) is refused; --allow-code-drift plays it under today's defaults, recorded."""
    ref, part = reference
    run = _copy(part, tmp_path / "old")
    inst = json.loads((run / "instance.json").read_text())
    inst.pop("settings")
    (run / "instance.json").write_text(json.dumps(inst, indent=1, default=str))
    PV.annotate(run, git={"sha": None})
    _flip(monkeypatch)
    with pytest.raises(ST.CodeDrift, match="charter rerun"):
        _resume(run)
    _resume(run, "--allow-code-drift")
    assert _prompts(run) != _prompts(ref)                              # the drift the frozen settings prevent
    meta = PV.read(run)
    assert meta["settings_inferred"]["code_drift"] and meta["segments"][-1]["settings"]["code_drift"]


def _have(sha):
    return ST._git("cat-file", "-e", f"{sha}^{{commit}}") is not None


@pytest.mark.skipif(not all(_have(e["commits"][0]) for e in PV.ENGINE_FLIPS.values()), reason="needs the git history")
def test_infer_version_from_git_history():
    for v, e in PV.ENGINE_FLIPS.items():
        assert ST.infer_version(e["commits"][0]) == v
        assert ST.infer_version(e["commits"][0] + "^") == (1 if v in (2, 3) else v - 1)   # 2 and 3 were made on parallel branches
    s = ST.infer(PV.ENGINE_FLIPS[3]["commits"][0])                       # version 3 without version 2's flip
    assert s["engine_version"] == 3 and s["defaults"] == {"charter.channels.DEFAULTS": {"delivery": "pull"}}
    assert ST.patches(s) == {"charter.channels.DEFAULTS": {"delivery": "pull"},
                             "charter.context.DEFAULTS": {"memory_text": "v1", "dm_delta": False, "history": {"enabled": False}}}
    assert ST.infer_version("HEAD") == PV.ENGINE_VERSION
    assert ST.infer_version("0" * 40) is None


def test_patches_revert_later_flips_only_where_the_snapshot_is_silent():
    p = ST.patches({"engine_version": 3, "defaults": {}})
    assert p == {"charter.context.DEFAULTS": {"memory_text": "v1", "dm_delta": False, "history": {"enabled": False}}}
    p = ST.patches({"engine_version": 1, "defaults": {"charter.context.DEFAULTS": {"memory_text": "v2"}}})
    assert p == {"charter.channels.DEFAULTS": {"delivery": "pull"},
                 "charter.context.DEFAULTS": {"dm_delta": False, "history": {"enabled": False}}}
    with ST.use({"engine_version": 1, "defaults": {}}):
        assert CX.DEFAULTS["memory_text"] == "v1" and CX.cfg({})["dm_delta"] is False
        assert CX.DEFAULTS["history"]["enabled"] is False and CX.DEFAULTS["history"]["chunk"] == 3   # the rest of the block kept
    assert CX.DEFAULTS["memory_text"] == "v2" and CX.cfg({})["dm_delta"] is True and CX.DEFAULTS["history"]["enabled"] is True


@pytest.mark.skipif(not _have(PV.ENGINE_FLIPS[3]["commits"][0]), reason="needs the git history")
def test_old_run_resumes_under_the_defaults_of_its_git_sha(tmp_path, monkeypatch):
    """A run made at engine version 3 (before memory_text v2 and dm_delta) without frozen settings: its resume infers version 3
    from run.json's sha and plays on with v1 / no delta, exactly as an uninterrupted run under that code."""
    with monkeypatch.context() as m:                                  # "the old code"
        _flip(m)
        old_ref = runner.run(_inst(), AG.ScriptedPolicy(1), tmp_path / "old_ref", **QUIET)
        old = runner.run(_inst(), AG.ScriptedPolicy(1), tmp_path / "old", until=1, **QUIET)
    inst = json.loads((old / "instance.json").read_text())
    inst.pop("settings")
    (old / "instance.json").write_text(json.dumps(inst, indent=1, default=str))
    PV.annotate(old, git={"sha": PV.ENGINE_FLIPS[3]["commits"][0], "dirty": False})
    _resume(old)
    assert _prompts(old) == _prompts(old_ref)
    meta = PV.read(old)
    assert meta["settings_inferred"]["engine_version"] == 3 and meta["segments"][-1]["settings"]["engine_version"] == 3


def test_export_has_the_engine_version(reference, tmp_path):
    from charter import export as X
    ref, _ = reference
    X.export([ref], tmp_path / "ds", fmt="csv")
    runs = X.load(tmp_path / "ds")["runs"]
    assert [int(r["engine_version"]) for r in runs] == [PV.ENGINE_VERSION]
    assert PV.read(ref)["engine_version"] == PV.ENGINE_VERSION


def test_engine_versions_doc_lists_every_version():
    doc = (Path(PV.__file__).parents[1] / "docs" / "engine_versions.md").read_text()
    rows = {int(m.group(1)) for m in re.finditer(r"^\| (\d+) \|", doc, re.M)}
    assert rows == set(range(1, PV.ENGINE_VERSION + 1)) and set(PV.ENGINE_FLIPS) <= rows
    for e in PV.ENGINE_FLIPS.values():
        assert e["commits"][0][:7] in doc
