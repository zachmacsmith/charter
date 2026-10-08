"""The differential harness (charter/difftest.py): identical revisions agree, an injected change is located, normalisation works.

The end-to-end tests build a throwaway git repository holding a copy of charter/ (commit c1), then commit a change to it (c2) that
adds a field to every harvest event. Runs are scripted (no model calls), 2 rounds of E2.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from charter import difftest as D

PKG = Path(D.__file__).resolve().parent
PRESET, SEED, ROUNDS = "E2", 1, 2


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=difftest", "-c", "user.email=difftest@example.invalid",
                           "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("difftest_repo")
    shutil.copytree(PKG, root / "charter", ignore=shutil.ignore_patterns("out", "__pycache__", "*.pyc"))
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c1")
    c1 = _git(root, "rev-parse", "HEAD")
    f = root / "charter" / "actions.py"
    src = f.read_text()
    old = 'k.log("harvest", aid, {"camp": camp, '
    assert src.count(old) == 1, "injection point moved; update this test"
    f.write_text(src.replace(old, 'k.log("harvest", aid, {"camp": camp, "cause": "injected", '))
    _git(root, "commit", "-q", "-am", "c2: harvest events carry a cause")
    c2 = _git(root, "rev-parse", "HEAD")
    yield {"root": root, "c1": c1, "c2": c2}
    assert "difftest" not in _git(root, "worktree", "list").replace(str(root), ""), "temporary worktrees were not removed"


@pytest.fixture(scope="module")
def injected(repo, tmp_path_factory):
    keep = tmp_path_factory.mktemp("difftest_runs")
    rep = D.difftest(repo["c1"], repo["c2"], [PRESET], [SEED], ROUNDS, repo=repo["root"], keep=keep, jobs=2, log=lambda *a: None)
    return rep, keep


@pytest.mark.slow
def test_identical_revisions_report_no_divergence(repo):
    rep = D.difftest(repo["c1"], repo["c1"], [PRESET], [SEED], ROUNDS, repo=repo["root"], jobs=2, log=lambda *a: None)
    assert rep["identical"], D.text_report(rep)
    case = rep["cases"][0]
    assert all(f["identical"] for f in case["files"].values())
    assert case["files"]["events.jsonl"]["n_base"] > 0
    assert "no divergence" in D.text_report(rep)
    assert json.loads(json.dumps(rep, default=str))["identical"]


@pytest.mark.slow
def test_injected_change_is_located(injected):
    rep, keep = injected
    assert not rep["identical"]
    case = rep["cases"][0]
    ev = case["files"]["events.jsonl"]
    base_events = [json.loads(l) for l in (keep / "base" / f"{PRESET}_s{SEED}" / "events.jsonl").read_text().splitlines()]
    want = next(i for i, e in enumerate(base_events) if e["type"] == "harvest")
    first = ev["first"]
    assert first["index"] == want
    assert first["round"] == base_events[want]["round"]
    assert first["type_base"] == first["type_head"] == "harvest"
    assert first["fields"] == [{"path": "data.cause", "base": "<missing>", "head": "injected"}]
    assert not ev["count_changes"]                                   # an added field changes no event counts
    assert ev["n_differing"] == ev["counts"]["harvest"]["base"]
    assert case["files"]["snapshots.json"]["identical"] and case["files"]["score.json"]["identical"]
    txt = D.text_report(rep)
    assert f"FIRST DIVERGENCE: event #{want}, round {first['round']}, type harvest" in txt
    assert "data.cause" in txt


@pytest.mark.slow
@pytest.mark.parametrize("field", ["cause", "data.cause"])
def test_ignore_field_hides_an_additive_change(injected, field):
    _, keep = injected
    res = D.compare_dirs(keep / "base" / f"{PRESET}_s{SEED}", keep / "head" / f"{PRESET}_s{SEED}", D.Norm(ignore_fields=[field]))
    assert res["identical"], res["files"]["events.jsonl"]["first"]


def test_ignore_field_does_not_mask_real_divergence(tmp_path):
    """Synthetic run directories: an ignored added field plus a real value change; the real change is still reported."""
    base, head = tmp_path / "a", tmp_path / "b"
    evs = [{"id": f"e{i}", "round": i // 2, "type": "harvest" if i % 2 else "post", "agent": "A", "data": {"y": i}} for i in range(6)]
    changed = [dict(e, data=dict(e["data"], cause="x")) for e in evs]
    changed[3] = dict(changed[3], data={"y": 99, "cause": "x"})
    snaps = [{"round": 0, "holdings": {"A": 1}}, {"round": 1, "holdings": {"A": 2}}]
    for d, ev, sn, sc in ((base, evs, snaps, 1.0), (head, changed, [snaps[0], {"round": 1, "holdings": {"A": 3}}], 0.5)):
        d.mkdir()
        (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ev))
        (d / "snapshots.json").write_text(json.dumps(sn))
        (d / "instance.json").write_text(json.dumps({"seed": 1}))
        (d / "ground_truth.json").write_text(json.dumps({"complete": True}))
        (d / "score.json").write_text(json.dumps({"summary": {"run": str(d)}, "goals": {"A": {"goal": "Wealth", "score": sc}}}))
    res = D.compare_dirs(base, head, D.Norm(ignore_fields=["cause"]))
    ev = res["files"]["events.jsonl"]
    assert ev["first"]["index"] == 3 and ev["first"]["round"] == 1 and ev["n_differing"] == 1
    assert ev["first"]["fields"] == [{"path": "data.y", "base": 3, "head": 99}]
    snap = res["files"]["snapshots.json"]
    assert [r["round"] for r in snap["rounds"]] == [1] and list(snap["rounds"][0]["fields"]) == ["holdings"]
    sc = res["files"]["score.json"]
    assert sc["goals"]["A"]["score"] == {"base": 1.0, "head": 0.5} and not sc["other"]     # run path normalised to <RUN>
    assert res["files"]["instance.json"]["identical"]


def test_renames_and_ignored_types():
    norm = D.Norm(ignore_fields=["id"], ignore_types=["note"], renames={"amt": "amount"}, type_renames={"pay": "transfer"})
    a = [{"id": "e1", "round": 0, "type": "pay", "data": {"amt": 3}}, {"id": "e2", "round": 0, "type": "vote", "data": {}}]
    b = [{"id": "e1", "round": 0, "type": "transfer", "data": {"amount": 3}}, {"id": "e2", "round": 0, "type": "note", "data": {}},
         {"id": "e3", "round": 0, "type": "vote", "data": {}}]
    r = D.compare_events(a, b, norm)
    assert r["identical"], r["first"]
    r = D.compare_events(a, b, D.Norm())
    assert r["first"]["index"] == 0 and r["count_changes"]["note"] == {"base": 0, "head": 1}


def test_float_tolerance():
    assert D.compare_plain({"x": 1.0}, {"x": 1.0004}, D.Norm(float_tol=1e-3))["identical"]
    assert not D.compare_plain({"x": 1.0}, {"x": 1.0004}, D.Norm())["identical"]
