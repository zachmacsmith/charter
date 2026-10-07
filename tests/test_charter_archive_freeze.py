"""P5.4: the shared archive frozen per run (archive.Frozen: base snapshot + overlay, published at the end) and sandbox outputs
recorded as blobs (sandbox.Recording) and served by replay (replay.ReplaySandbox). Scripted bots only; the sandbox is faked."""
from __future__ import annotations

import hashlib
import itertools
import json
import shutil
import threading

import pytest

from charter import agents as AG
from charter import archive
from charter import generator, runner
from charter import provenance as PV
from charter import replay as RP
from charter import spec as S

QUIET = dict(log=lambda *a: None)
LOGDOC = "shared/scientists-log"


def _jsonl(p):
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()] if p.exists() else []


def _norm(p):
    return [json.dumps({x: v for x, v in json.loads(ln).items() if x not in ("ts", "time")}, sort_keys=True)
            for ln in p.read_text().splitlines() if ln.strip()]


class ArchivePolicy(AG.ScriptedPolicy):
    """Scripted bots whose Scientists read the Scientists' log every turn and (writer) leave their note in round 1."""

    def __init__(self, seed=0, write=True):
        super().__init__(seed)
        self.write = write

    def act(self, k, a, system, user, n_actions, final):
        out, reasoning, usage = super().act(k, a, system, user, n_actions, final)
        if a.get("cls") == "scientist" and isinstance(out, dict) and a.get("phase") in (None, "decide"):
            extra = [{"action": "read_archive", "args_json": json.dumps({"doc": LOGDOC})}]
            if self.write and k.r == 0:
                extra.append({"action": "write_archive", "args_json": json.dumps({"text": f"{a['id']} says: watch the levy"})})
            out = {**out, "actions": extra + list(out.get("actions") or [])}
        return out, reasoning, usage


def det_sandbox(agent, code):
    return "det:" + hashlib.sha256(f"{agent}|{code}".encode()).hexdigest()[:12]


class CountingSandbox:
    """Output differs on every call (as Docker's may: time, random, the 10 s timeout): only a recorded output replays."""

    def __init__(self):
        self.n = itertools.count()

    def __call__(self, agent, code):
        return f"run {next(self.n)} for {agent}"


def no_sandbox(agent, code):
    raise AssertionError("the sandbox ran during a replay")


def _inst(shared, ns="t", rounds=3, run_id="run", on=True):
    sp = S.apply_overrides(S.load("E4"), [f"rounds={rounds}", "turns=simultaneous"])
    sp["shared_archive"] = {"enabled": on, "path": str(shared), "namespace": ns}
    inst = generator.generate(sp, 1)
    inst["run_id"] = run_id
    return inst


def _seed_live(shared, ns="t"):
    """A live shared archive with one earlier world's note in it."""
    live = archive.live_dir({"shared_archive": {"path": str(shared), "namespace": ns}})
    archive.log_note(live, "an older world says: trust no one", "Left by s9 of an older world", "s9", "older-run")
    return live


def _reads(run):
    return [e["data"]["chars"] for e in _jsonl(run / "events.jsonl")
            if e.get("type") == "archive_read" and e.get("data", {}).get("doc") == LOGDOC]


# ------------------------------------------------------------------ frozen archive + replay
def test_replay_after_the_shared_archive_changed_is_identical(tmp_path):
    shared = tmp_path / "shared"
    live = _seed_live(shared)
    before = (live / "scientists-log.md").read_text()
    run = runner.run(_inst(shared), ArchivePolicy(1), tmp_path / "E4_run", CountingSandbox(), **QUIET)
    meta = PV.read(run)["shared_archive"]
    base = json.loads((run / "archive" / "base.json").read_text())
    assert meta["hash"] == base["hash"] and "scientists-log.md" in base["files"] and "_writes.jsonl" in base["files"]
    assert all((run / "blobs" / h).exists() for h in base["files"].values())
    gt = json.loads((run / "ground_truth.json").read_text())["shared_archive_at_start"]
    assert gt["hash"] == base["docs_hash"] == meta["docs_hash"] and gt["base_hash"] == base["hash"]
    ops = _jsonl(run / "archive_overlay.jsonl")
    assert ops and all(o["op"] == "log_note" and (run / "blobs" / o["text"]).exists() for o in ops)
    published = (live / "scientists-log.md").read_text()                # the end-of-run publish: the notes reach the live archive
    assert published != before and all(PV.get_blob(run, o["text"]) in published for o in ops)
    assert json.loads((run / "archive" / "state.json").read_text())["published"] == len(ops)
    assert _reads(run) and max(_reads(run)) > min(_reads(run))          # the run saw its own notes (overlay) after round 1

    (live / "scientists-log.md").write_text("TAMPERED\n" * 50)          # the live archive changes after the run
    (live / "new-doc.md").write_text("# A new document\n\nwritten later")
    live_after = (live / "scientists-log.md").read_text()
    res = RP.replay(run, tmp_path / "replay", sandbox=no_sandbox, **QUIET)
    assert res["identical"] and res["events_identical"] and res["snapshots_identical"], res
    assert res["shared_archive"] == meta["hash"] and "note" not in res
    assert res["sandbox_replayed"] == len(_jsonl(run / "sandbox.jsonl")) > 0
    assert (live / "scientists-log.md").read_text() == live_after       # a replay never publishes
    assert "TAMPERED" not in (tmp_path / "replay" / "reasoning.jsonl").read_text()


def test_resume_after_the_shared_archive_changed_reads_the_frozen_copy(tmp_path):
    _seed_live(tmp_path / "a")                                          # the same archive, the same run, uninterrupted
    full = runner.run(_inst(tmp_path / "a"), ArchivePolicy(1), tmp_path / "a" / "E4_run", det_sandbox, **QUIET)
    live = _seed_live(tmp_path / "b")
    d = tmp_path / "b" / "E4_run"
    runner.run(_inst(tmp_path / "b"), ArchivePolicy(1), d, det_sandbox, until=1, **QUIET)
    log_now = (live / "scientists-log.md").read_text()
    assert "watch the levy" not in log_now                             # paused: nothing published yet
    (live / "scientists-log.md").write_text("TAMPERED " * 200)
    (live / "planted.md").write_text("# Planted\n\nby hand")
    runner.run(_inst(tmp_path / "b"), ArchivePolicy(1), d, det_sandbox, resume=True, **QUIET)
    assert _norm(d / "events.jsonl") == _norm(full / "events.jsonl")    # == the uninterrupted run on an unchanged archive
    assert (d / "snapshots.json").read_text() == (full / "snapshots.json").read_text()
    assert "TAMPERED" not in (d / "reasoning.jsonl").read_text() and not (d / "archive" / "view" / "planted.md").exists()
    assert PV.read(d)["shared_archive"]["docs_hash"] == PV.read(full)["shared_archive"]["docs_hash"]   # (_writes.jsonl has times)
    assert json.loads((d / "archive" / "base.json").read_text())["hash"] == PV.read(d)["shared_archive"]["hash"]
    assert "watch the levy" in (live / "scientists-log.md").read_text()  # published once complete, onto the live contents


def test_rewind_and_fork_use_the_frozen_copy_and_never_publish(tmp_path):
    shared = tmp_path / "shared"
    live = _seed_live(shared)
    run = runner.run(_inst(shared), ArchivePolicy(1), tmp_path / "E4_run", CountingSandbox(), **QUIET)
    (live / "scientists-log.md").write_text("TAMPERED")
    r = RP.rewind(run, 1, tmp_path / "rw")
    assert (r / "archive" / "base.json").read_text().count("hash") and \
        json.loads((r / "archive" / "base.json").read_text())["hash"] == PV.read(run)["shared_archive"]["hash"]
    kept = _jsonl(r / "archive_overlay.jsonl")
    assert kept and json.loads((r / "archive" / "state.json").read_text())["published"] == len(kept)
    [f] = RP.fork(run, 1, [], tmp_path / "fk", policy_factory=lambda sp, dry, seed: ArchivePolicy(seed), sandbox=det_sandbox, log=None)
    assert "TAMPERED" not in (f / "reasoning.jsonl").read_text()
    assert (live / "scientists-log.md").read_text() == "TAMPERED"       # a fork never publishes
    rows = _jsonl(f / "sandbox.jsonl")                                  # the parent's outputs before the fork point, live after
    assert rows and all(PV.get_blob(f, x["output"]).startswith("run ") for x in rows if x["round"] < 1)
    assert all(PV.get_blob(f, x["output"]).startswith("det:") and not x.get("replayed") for x in rows if x["round"] >= 1)


# ------------------------------------------------------------------ sandbox outputs as blobs
def test_run_python_output_replays_from_the_blob_without_the_sandbox(tmp_path):
    inst = _inst(tmp_path / "shared", on=False)
    run = runner.run(inst, AG.ScriptedPolicy(1), tmp_path / "E4_run", CountingSandbox(), **QUIET)
    rows = _jsonl(run / "sandbox.jsonl")
    assert rows and len({r["call"] for r in rows}) == len(rows)
    for r in rows:
        assert r["call"] == f"r{r['round']}:{r['agent']}:{r['n']}"
        assert PV.get_blob(run, r["output"]).startswith("run ") and "print" in PV.get_blob(run, r["code"])
    ev = [e for e in _jsonl(run / "events.jsonl") if e.get("type") == "sandbox"]
    assert [e["data"]["output"] for e in ev] == [PV.get_blob(run, r["output"]) for r in rows]
    assert not (run / "archive").exists() and "shared_archive" not in PV.read(run)   # archive off: no frozen copy
    res = RP.replay(run, tmp_path / "replay", sandbox=no_sandbox, **QUIET)
    assert res["identical"] and res["sandbox_replayed"] == len(rows), res
    assert all(r.get("replayed") for r in _jsonl(tmp_path / "replay" / "sandbox.jsonl"))
    res = RP.replay(run, tmp_path / "replay2", to=2, **QUIET)           # --to: only those rounds' records are expected
    assert res["identical"]


def test_a_tampered_sandbox_record_fails_the_replay_loudly(tmp_path):
    run = runner.run(_inst(tmp_path / "shared", on=False), AG.ScriptedPolicy(1), tmp_path / "E4_run", CountingSandbox(), **QUIET)
    rows = _jsonl(run / "sandbox.jsonl")
    bad = tmp_path / "bad"
    shutil.copytree(run, bad)
    rows[0]["code"] = PV.put_blob(bad, "print('something else')")
    (bad / "sandbox.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(RP.ReplayDivergence, match="sandbox call"):
        RP.replay(bad, tmp_path / "r1", **QUIET)
    (bad / "sandbox.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows[1:] + [{**rows[0], "call": "r9:x:0", "round": 1}]))
    with pytest.raises(RP.ReplayMiss):
        RP.replay(bad, tmp_path / "r2", **QUIET)


# ------------------------------------------------------------------ isolation between runs
def test_concurrent_runs_are_isolated_until_the_end_of_run_publish(tmp_path):
    shared = tmp_path / "shared"
    live = _seed_live(shared)
    base_len = len(archive.read(LOGDOC, live, run_id="B"))              # as B reads it ("(not of this time)" tagged)
    a_dir, b_dir = tmp_path / "A", tmp_path / "B"
    runner.run(_inst(shared, run_id="A"), ArchivePolicy(1), a_dir, det_sandbox, until=1, **QUIET)   # A writes, then pauses
    assert len(_jsonl(a_dir / "archive_overlay.jsonl")) > 0
    assert "watch the levy" not in (live / "scientists-log.md").read_text()
    errs = []

    def play(**kw):
        try:
            runner.run(**kw, **QUIET)
        except BaseException as e:                                      # pragma: no cover - surfaced below
            errs.append(e)
    tb = threading.Thread(target=play, kwargs=dict(inst=_inst(shared, run_id="B"), policy=ArchivePolicy(2, write=False),
                                                   out_dir=b_dir, sandbox=det_sandbox))
    ta = threading.Thread(target=play, kwargs=dict(inst=_inst(shared, run_id="A"), policy=ArchivePolicy(1), out_dir=a_dir,
                                                   sandbox=det_sandbox, resume=True))
    tb.start(); ta.start(); tb.join(); ta.join()
    assert not errs, errs
    assert set(_reads(b_dir)) == {base_len}                             # B read only its frozen base the whole run
    assert "watch the levy" in (live / "scientists-log.md").read_text()  # A's notes reached the live archive at A's end
    c = runner.run(_inst(shared, run_id="C"), ArchivePolicy(3, write=False), tmp_path / "C", det_sandbox, **QUIET)
    assert min(_reads(c)) > base_len                                     # a later run inherits them
