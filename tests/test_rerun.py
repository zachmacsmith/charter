"""charter rerun (charter/rerun.py): a run's command again, under the git sha it recorded, in a temporary worktree. Scripted bots
only, no model calls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charter import __main__ as M
from charter import provenance as PV
from charter import rerun as RR
from charter import spec as S

HEAD = (PV._git("rev-parse", "HEAD") or "").strip() or None
pytestmark = pytest.mark.skipif(HEAD is None, reason="needs the git repository")
SETS = ["rounds=2", "shared_archive.enabled=false"]
ARGV = ["/somewhere/charter/__main__.py", "run", "society", "--seed", "1", "--dry", "--sandbox", "off"] + \
       [x for s in SETS for x in ("--set", s)]


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    d = tmp_path_factory.mktemp("rerun")
    out, _ = M.run_one("society", S.apply_overrides(S.load("society"), SETS), 1, True, "off", parent=d, quiet=True)
    return out


def _as_if(src: Path, dst: Path, argv=ARGV, **git) -> Path:
    """A copy of the run whose run.json says it was started by `argv` at HEAD on a clean tree (or `git`)."""
    import shutil
    shutil.copytree(src, dst)
    meta = PV.read(dst)
    meta["git"] = {"sha": HEAD, "dirty": False, **git}
    meta["segments"][0].update(git=meta["git"], argv=list(argv))
    PV._write(dst, meta)
    return dst


def test_dry_run_prints_the_plan(made, tmp_path, capsys):
    run = _as_if(made, tmp_path / "run")
    M.main(["rerun", str(run), "--dry-run"])
    p = json.loads(capsys.readouterr().out)
    assert p["sha"] == HEAD and p["command"] == ARGV[1:] and p["source"] == "argv"
    assert p["out"] == str(tmp_path / "run_rerun") and not (tmp_path / "run_rerun").exists()
    assert p["engine_version"] == PV.ENGINE_VERSION


def test_refusals(made, tmp_path):
    with pytest.raises(RR.RerunError, match="uncommitted"):
        RR.plan(_as_if(made, tmp_path / "dirty", dirty=True, diff_sha="abc"))
    with pytest.raises(RR.RerunError, match="not in this repository"):
        RR.plan(_as_if(made, tmp_path / "unknown", sha="0" * 40))
    with pytest.raises(RR.RerunError, match="no git sha"):
        RR.plan(_as_if(made, tmp_path / "nogit", sha=None))
    fork = _as_if(made, tmp_path / "fork")
    PV.annotate(fork, parent={"run": "elsewhere", "round": 1})
    with pytest.raises(RR.RerunError, match="rerun the parent"):
        RR.plan(fork)
    bare = _as_if(made, tmp_path / "bare", argv=["pytest"])
    inst = json.loads((bare / "instance.json").read_text())
    inst.pop("spec_source")
    (bare / "instance.json").write_text(json.dumps(inst))
    with pytest.raises(RR.RerunError, match="spec_source"):
        RR.plan(bare)


def test_a_run_not_started_from_the_command_line_reruns_its_spec(made, tmp_path):
    p = RR.plan(_as_if(made, tmp_path / "script", argv=["pytest", "-q"]))
    assert p["source"] == "spec_source" and p["command"] == ["run", "{spec}", "--seed", "1", "--dry", "--sandbox", "off"]


@pytest.mark.slow
@pytest.mark.parametrize("argv", [ARGV, ["pytest"]], ids=["argv", "spec_source"])
def test_rerun_reproduces_the_run_in_a_worktree(made, tmp_path, argv):
    run = _as_if(made, tmp_path / "run", argv=argv)
    out = RR.execute(RR.plan(run), log=lambda *a: None, worktree_root=tmp_path)
    assert out == tmp_path / "run_rerun"
    for f in ("events.jsonl", "snapshots.json"):
        assert (out / f).read_bytes() == (made / f).read_bytes(), f
    meta = PV.read(out)
    assert meta["rerun_of"]["sha"] == HEAD and meta["git"]["sha"] == HEAD
    assert not any(Path(x).name == "src" and "charter_rerun_" in x for x in (PV._git("worktree", "list") or "").split())
