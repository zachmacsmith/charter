"""charter publish: staging layout, catalog, dataset card, raw archive hygiene and the upload guards (no network: the hub calls
are replaced)."""
from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

pa = pytest.importorskip("pyarrow")
import pyarrow.parquet as pq  # noqa: E402

from charter import agents as AG, generator, publish as P, runner, scorer  # noqa: E402
from charter import spec as S  # noqa: E402

QUIET = dict(log=lambda *a: None)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """A 2-round scripted E0 run under <root>/E0/pub1, with a VALIDITY.md and a file that names its own absolute path."""
    d = tmp_path_factory.mktemp("out") / "E0" / "pub1"
    inst = generator.generate(S.apply_overrides(S.load("E0"), ["rounds=2", "shared_archive.enabled=false"]), 1)
    inst["run_id"] = "pub1"
    runner.run(inst, AG.ScriptedPolicy(1), d, **QUIET)
    scorer.score(d)
    (d / "VALIDITY.md").write_text("# Validity\n\n**Usable rounds: 1-2 of 2.** A test run.\n")
    (d / "notes.txt").write_text(f"written at {d.resolve()}/events.jsonl by {Path.home()}\n")
    (d / "checkpoint.pkl").write_bytes(b"not for the public")
    return d


@pytest.fixture()
def offline(monkeypatch):
    monkeypatch.setattr(P, "remote_catalog", lambda repo, revision=None: [])
    monkeypatch.setattr(P, "_api", lambda: pytest.fail("no hub access in tests"))


def test_stage_layout_catalog_and_card(run, tmp_path, offline):
    s = P.publish([run], repo="me/data", staging=tmp_path / "st", cards={"pub1": {"title": "A test", "tags": ["t"]}}, **QUIET)
    st = Path(s["staging"])
    tdir = st / "runs" / "E0" / "pub1"
    assert (tdir / "manifest.json").exists() and (tdir / "events.parquet").exists()
    card = json.loads((tdir / "card.json").read_text())
    assert card["title"] == "A test" and card["usable_rounds"] == "1-2" and "A test run" in card["validity"]
    [row] = json.loads((st / "catalog.json").read_text())["runs"]
    assert row["path"] == "runs/E0/pub1" and row["raw"] == "raw/E0/pub1.tar.gz" and row["n_agents"] > 0
    assert json.loads(row["tags_json"]) == ["t"] and pq.read_table(st / "catalog.parquet").num_rows == 1
    readme = (st / "README.md").read_text()
    for t in json.loads((tdir / "manifest.json").read_text())["tables"]:
        assert f"data_files: runs/*/*/{t}.parquet" in readme
    assert "config_name: catalog" in readme and "license: cc-by-4.0" in readme and not s["pushed"]


def test_raw_archive_drops_pickles_and_scrubs_paths(run, tmp_path):
    out = tmp_path / "raw.tar.gz"
    P.raw_archive(run, out, "E0")
    with tarfile.open(out) as tf:
        names = tf.getnames()
        notes = tf.extractfile("E0/pub1/notes.txt").read().decode()
    assert not any(n.endswith(".pkl") for n in names) and "E0/pub1/events.jsonl" in names
    assert str(Path.home()) not in notes and not notes.split("at ", 1)[1].startswith("/")
    assert notes.startswith("written at E0/pub1/events.jsonl")


def test_guard_flags_absolute_paths_in_tables(tmp_path):
    pq.write_table(pa.table({"run_id": ["r"], "run_dir": [str(Path.home() / "x" / "r")], "ok": ["E0/r"]}), tmp_path / "runs.parquet")
    probs = P.check_tables(tmp_path)
    assert len(probs) == 1 and "runs.parquet.run_dir" in probs[0]
    pq.write_table(pa.table({"run_id": ["r"], "run_dir": ["E0/r"]}), tmp_path / "runs.parquet")
    assert P.check_tables(tmp_path) == []


def test_push_refused_with_problems(run, tmp_path, offline, monkeypatch):
    monkeypatch.setattr(P, "check_staging", lambda stage: ["never published: checkpoint.pkl"])
    with pytest.raises(SystemExit):
        P.publish([run], repo="me/data", staging=tmp_path / "st", push=True, **QUIET)


def test_catalog_merge_and_schema_mix(run, tmp_path, monkeypatch):
    old = {"run_id": "older", "spec": "E1", "path": "runs/E1/older", "raw": "raw/E1/older.tar.gz", "title": "older",
           "schema_version": -1, "models_list_json": "[]", "tags_json": "[]"}
    same = {**old, "run_id": "pub1", "title": "stale title"}
    monkeypatch.setattr(P, "remote_catalog", lambda repo, revision=None: [old, same])
    s = P.publish([run], repo="me/data", staging=tmp_path / "st", **QUIET)
    rows = {r["run_id"]: r for r in json.loads((Path(s["staging"]) / "catalog.json").read_text())["runs"]}
    assert set(rows) == {"older", "pub1"} and rows["pub1"]["title"] != "stale title"
    assert any("mix export schema majors" in p for p in s["problems"])


def test_load_cards(tmp_path):
    (tmp_path / "one.json").write_text(json.dumps({"title": "T"}))
    (tmp_path / "many.yaml").write_text("r1:\n  title: A\nr2:\n  tags: [x]\n")
    assert P.load_cards(tmp_path / "one.json") == {"*": {"title": "T"}}
    assert P.load_cards(tmp_path / "many.yaml") == {"r1": {"title": "A"}, "r2": {"tags": ["x"]}}
    assert P.parse_rounds("rounds 1–23") == [1, 23] and P.parse_rounds(None) is None


def test_raw_archive_scrubs_writing_checkout_and_refuses_leftovers(tmp_path):
    run = tmp_path / "ckout" / "charter" / "out" / "spec" / "r1"
    run.mkdir(parents=True)
    root = str(tmp_path / "ckout")
    (run / "run.json").write_text(json.dumps({"argv": [f"{root}/charter/__main__.py"], "dir": f"{root}/runs/x"}))
    stage = tmp_path / "stage"
    out = stage / "raw" / "spec" / "r1.tar.gz"
    P.raw_archive(run, out, "spec")
    with tarfile.open(out) as tf:
        text = tf.extractfile("spec/r1/run.json").read().decode()
    assert root not in text and "charter/__main__.py" in text
    assert P.check_staging(stage) == []
    (run / "notes.md").write_text("see /home/someone/elsewhere/file")
    P.raw_archive(run, out, "spec")
    assert any("local path left" in p for p in P.check_staging(stage))
