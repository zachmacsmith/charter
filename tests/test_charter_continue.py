"""Continuing a published run (charter/fetch.py; docs/data_format.md): a run goes through publish's staging and raw archive, is
unpacked as `charter fetch` does, replays byte for byte from the archive alone (no checkpoints: they are never published) and is
continued with `charter continue` (replay to N, fork at N, play on). Also: history mode's restarts at a resume are replayed, and
calls_seen (what each model call was shown) from the runner's own record agrees with the prompt parser of older runs.
Offline: scripted bots, no Hub access (hf_hub_download and the catalog are replaced)."""
from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from charter import agents as AG, generator, runner
from charter import export as X
from charter import fetch as FC
from charter import publish as P
from charter import replay as RP
from charter import spec as S

QUIET = dict(log=lambda *a: None)
SETS = ["rounds=4", "turns=simultaneous", "context.enabled=true", "shared_archive.enabled=false"]


def _jsonl(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    """A scripted E4 run with context and history mode on, stopped after round 2 and resumed (so history mode restarted every
    conversation at round 2), published to a staging directory: (run, staged archive, staging dir)."""
    root = tmp_path_factory.mktemp("pub")
    d = root / "out" / "E4" / "cont1"
    inst = generator.generate(S.apply_overrides(S.load("E4"), SETS), 1)
    inst["run_id"] = "cont1"
    runner.run(inst, AG.ScriptedPolicy(1), d, until=2, **QUIET)
    runner.run(json.loads((d / "instance.json").read_text()), AG.ScriptedPolicy(1), d, resume=True, **QUIET)
    from charter import scorer
    scorer.score(d)
    stage = root / "stage"
    rows, problems, _ = P.stage_runs([d], stage, {}, **QUIET)
    assert problems == [] and P.check_staging(stage) == []
    P.write_catalog(rows, stage)
    return d, stage / rows[0]["raw"], stage


def _extract(archive, dest) -> Path:
    [run] = P.extract_archive(archive, dest)
    return run


def test_the_archive_holds_what_a_replay_needs_and_no_pickle(published):
    run, archive, _ = published
    with tarfile.open(archive) as tf:
        names = {n.split("/", 2)[2] for n in tf.getnames() if n.count("/") >= 2}
    assert not any(n.endswith(".pkl") or n.startswith("checkpoints") for n in names)
    assert {"instance.json", "calls.jsonl", "events.jsonl", "snapshots.json", "run.json", "memory.jsonl", "reasoning.jsonl"} <= names
    assert json.loads((run / "run.json").read_text())["history_restarts"] == [2]


def test_extracted_archive_replays_byte_identically(published, tmp_path):
    run, archive, _ = published
    got = _extract(archive, tmp_path / "fetched")
    assert not (got / "checkpoints").exists() and not (got / "checkpoint.pkl").exists()
    res = RP.replay(got, tmp_path / "replay", **QUIET)
    assert res["identical"] and res["events_identical"] and res["snapshots_identical"]
    for f in ("events.jsonl", "snapshots.json", "memory.jsonl", "turns.jsonl", "ground_truth.json"):
        assert (tmp_path / "replay" / f).read_bytes() == (run / f).read_bytes(), f


def test_replay_without_the_recorded_restarts_diverges(published, tmp_path, monkeypatch):
    """The resume restarted every history conversation; a replay that ignored run.json history_restarts would not reproduce it."""
    run, _, _ = published
    real = runner.run
    monkeypatch.setattr(runner, "run", lambda *a, **kw: real(*a, **{**kw, "history_restarts": ()}))
    with pytest.raises(RP.ReplayDivergence):
        RP.replay(run, tmp_path / "replay", **QUIET)


def test_fork_of_a_fetched_run_without_checkpoints_says_how(published, tmp_path):
    got = _extract(published[1], tmp_path / "fetched")
    with pytest.raises(SystemExit, match="charter continue"):
        RP.fork(got, 2, out=tmp_path / "f", policy_factory=lambda sp, dry, seed: AG.ScriptedPolicy(seed), **QUIET)


def test_continue_replays_to_n_then_forks_and_plays_k_rounds(published, tmp_path):
    run, archive, _ = published
    got = _extract(archive, tmp_path / "fetched")
    r = FC.continue_run(got, 3, rounds=1, out=tmp_path / "cont", dry=True, **QUIET)
    b = Path(r["branch"])
    assert r["code"] == "current" and r["replay_result"]["identical"]
    ev, ref = (b / "events.jsonl").read_text().splitlines(), (run / "events.jsonl").read_text().splitlines()
    n = sum(1 for e in _jsonl(run / "events.jsonl") if (e.get("round") if e.get("round") is not None else -1) < 3)
    assert ev[:n] == ref[:n]                                            # the inherited prefix is the run's, byte for byte
    assert len(json.loads((b / "snapshots.json").read_text())) == 4
    meta = json.loads((b / "run.json").read_text())
    assert meta["parent"]["round"] == 3 and meta["continued_from"]["run_id"] == "cont1"
    assert [s["kind"] for s in meta["segments"]][-2:] == ["fork", "resume"]
    live = [c for c in _jsonl(b / "calls.jsonl") if not c.get("replayed")]
    assert live and all(c["round"] == 3 for c in live)


def test_continue_refuses_a_run_without_recorded_replies(tmp_path):
    d = tmp_path / "old"
    d.mkdir()
    (d / "instance.json").write_text("{}")
    with pytest.raises(SystemExit, match="calls.jsonl"):
        FC.continue_run(d, 1, **QUIET)


def test_fetch_unpacks_a_published_run(published, tmp_path, monkeypatch):
    run, archive, stage = published
    row = json.loads((stage / "catalog.json").read_text())["runs"][0]
    monkeypatch.setattr(P, "remote_catalog", lambda repo, revision=None: [row])
    import huggingface_hub
    seen = {}

    def download(repo, name, repo_type=None, revision=None):
        seen.update(repo=repo, name=name, revision=revision)
        return str(stage / name)
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    got = FC.fetch("cont1", "me/data", "v1.0", tmp_path / "f", **QUIET)
    assert got == tmp_path / "f" / "E4" / "cont1" and (got / "events.jsonl").read_bytes() == (run / "events.jsonl").read_bytes()
    assert seen == {"repo": "me/data", "name": "raw/E4/cont1.tar.gz", "revision": "v1.0"}
    with pytest.raises(SystemExit, match="not in the catalog"):
        FC.fetch("nope", "me/data", out=tmp_path / "g", **QUIET)


def test_extract_skips_unsafe_members(tmp_path):
    import io
    a = tmp_path / "a.tar.gz"
    with tarfile.open(a, "w:gz") as tf:
        for name in ("S/r/instance.json", "../evil.txt", "/abs.txt", "S/r/checkpoint.pkl"):
            info = tarfile.TarInfo(name)
            info.size = 2
            tf.addfile(info, io.BytesIO(b"{}"))
        link = tarfile.TarInfo("S/r/link")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tf.addfile(link)
    runs = P.extract_archive(a, tmp_path / "x")
    assert runs == [tmp_path / "x" / "S" / "r"]
    assert sorted(p.name for p in (tmp_path / "x" / "S" / "r").iterdir()) == ["instance.json"]
    assert not (tmp_path / "evil.txt").exists()


# ------------------------------------------------------------------ calls_seen: the runner's record and the prompt parser agree
def test_calls_seen_recorded_matches_the_prompt_parser(published, tmp_path):
    run = published[0]
    rows = _jsonl(run / "reasoning.jsonl")
    assert all("shown" in r for r in rows if X.call_step(r.get("phase")) is not None)
    rec = X.run_tables(run)["calls_seen"]
    assert rec and {r["seen_source"] for r in rec} == {"recorded"} and sum(r["n_seen"] for r in rec) > 0
    old = tmp_path / "E4" / "old"
    import shutil
    shutil.copytree(run, old)
    (old / "reasoning.jsonl").write_text("".join(json.dumps({k: v for k, v in r.items() if k not in ("shown", "lookup_results")})
                                                 + "\n" for r in rows))
    par = X.run_tables(old)["calls_seen"]
    assert {r["seen_source"] for r in par} == {"prompt"}
    key = lambda r: (r["round"], r["agent"], r["phase"])
    assert {key(r): r["seen_msg_ids_json"] for r in rec} == {key(r): r["seen_msg_ids_json"] for r in par}
    msgs = {m["msg_id"]: m for m in X.run_tables(run)["messages"]}
    for r in rec:                                                       # first sightings, of others' messages, each once
        assert all(msgs[i]["sender"] != r["agent"] for i in r["seen_msg_ids_json"])
    pairs = [(r["agent"], i) for r in rec for i in r["seen_msg_ids_json"]]
    assert len(pairs) == len(set(pairs))


def _row(rnd, agent, phase, prompt, **kw):
    return {"round": rnd, "agent": agent, "phase": phase, "prompt": prompt, "position": 1, "actions": [], **kw}


def test_calls_seen_columns_from_a_recorded_dm_step(tmp_path):
    rows = [_row(0, "Ann", "lookup", "p0", lookups=[{"name": "manual", "args": {"section": "x"}, "text": "Manual x"}], shown=[]),
            _row(0, "Ann", "decide", "p1", shown=["e1", "e2"], actions=[{"action": "dm", "args_json": "{}"}],
                 final_actions=[{"action": "harvest", "args_json": "{}"}], usage={"call": "r0:Ann:1"}),
            _row(0, "Ann", "dm_reply_1", "p2", shown=["e2", "e5"], lookup_results=["Lookup read {}:\nthe text"]),
            _row(0, "Ann", "editorial", "p3", shown=["e9"])]
    (tmp_path / "reasoning.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = X.calls_seen_rows(tmp_path, {"e1": "Bo", "e2": None, "e5": "Bo", "e9": "Bo"}, lambda r: False)
    assert [(r["phase"], r["step"], r["wave"]) for r in out] == [("lookup", -1, None), ("decide", 0, None), ("dm_reply_1", 1, 1)]
    lk, dec, dm = out
    assert dec["seen_msg_ids_json"] == ["e1", "e2"] and dm["seen_msg_ids_json"] == ["e5"] and dec["call_id"] == "r0:Ann:1"
    assert dec["final_actions_json"] == [{"action": "harvest", "args_json": "{}"}] and dm["final_actions_json"] is None
    assert dec["lookup_results_json"] == [{"head": 'manual {"section": "x"}', "text": "Manual x"}]
    assert dm["lookup_results_json"] == [{"head": "Lookup read {}", "text": "the text"}] and dm["n_lookup_results"] == 1
    for r in out:
        X.coerce("calls_seen", {"run_id": "r", **r})
