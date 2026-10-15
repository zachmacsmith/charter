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
    monkeypatch.setattr(P, "remote_changelog", lambda repo: "")
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
    monkeypatch.setattr(P, "remote_changelog", lambda repo: "")
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


# ------------------------------------------------------------------ releases (a fake HfApi records the hub calls)
class FakeApi:
    def __init__(self, tags=()):
        self.tags, self.calls, self.uploaded = list(tags), [], {}

    def list_repo_refs(self, repo, repo_type=None):
        from types import SimpleNamespace as NS
        return NS(tags=[NS(name=t) for t in self.tags])

    def upload_folder(self, folder_path, repo_id, repo_type, delete_patterns, commit_message):
        from types import SimpleNamespace as NS
        self.calls.append(("upload", commit_message, sorted(p.name for p in Path(folder_path).iterdir())))
        self.uploaded = {n: (Path(folder_path) / n).read_text() for n in ("README.md", "CHANGELOG.md")
                         if (Path(folder_path) / n).exists()}
        return NS(oid="abc123", commit_url="https://hf.co/c/abc123")

    def create_tag(self, repo_id, tag, repo_type=None, revision=None, tag_message=None):
        self.calls.append(("tag", tag, revision, repo_type))


OLD_LOG = """# Changelog

Releases of this dataset.

## v1.0 (2026-10-01)

- Runs added (1): `E1/older`
- Notes: first release"""


@pytest.fixture()
def hub(monkeypatch):
    api = FakeApi(tags=["v0-legacy-layout", "v1.0"])
    monkeypatch.setattr(P, "_api", lambda: api)
    monkeypatch.setattr(P, "remote_catalog", lambda repo, revision=None: [])
    monkeypatch.setattr(P, "remote_changelog", lambda repo: P.changelog_entries(OLD_LOG))
    return api


def test_release_prepends_changelog_and_tags_upload_commit(run, tmp_path, hub):
    s = P.publish([run], repo="me/data", staging=tmp_path / "st", push=True, release="v1.1", notes="adds pub1", **QUIET)
    assert s["tag"] == "v1.1" and s["commit"] == "abc123"
    up, tag = hub.calls
    assert up[0] == "upload" and up[1].startswith("v1.1: ") and "CHANGELOG.md" in up[2]
    assert tag == ("tag", "v1.1", "abc123", "dataset")
    log = hub.uploaded["CHANGELOG.md"]
    assert log.startswith("# Changelog") and log.index("## v1.1 (") < log.index("## v1.0 (2026-10-01)")
    assert "Runs added (1): `E0/pub1`" in log and "Notes: adds pub1" in log and "Notes: first release" in log
    assert "Export schema: 2." in log and "Engine versions: " in log
    card = hub.uploaded["README.md"]
    assert "## Changelog" in card and card.index("### v1.1 (") < card.index("### v1.0 (2026-10-01)")
    assert "## Runs (1)" in card and "license: cc-by-4.0" in card               # the card's own content is kept
    # the card's section is itself a source of history (the fallback when CHANGELOG.md is missing)
    entries = P.changelog_entries(card)
    assert entries.startswith("## v1.1 (") and "## v1.0 (2026-10-01)" in entries and "## License" not in entries


def test_release_replaced_runs_and_second_release_keeps_history(run, tmp_path, hub, monkeypatch):
    prev = {"run_id": "pub1", "spec": "E0", "path": "runs/E0/pub1", "raw": "raw/E0/pub1.tar.gz", "title": "x",
            "models_list_json": "[]", "tags_json": "[]"}
    monkeypatch.setattr(P, "remote_catalog", lambda repo, revision=None: [prev])
    P.publish([run], repo="me/data", staging=tmp_path / "a", push=True, release="v1.1", **QUIET)
    first = hub.uploaded["CHANGELOG.md"]
    assert "Runs replaced (1): `E0/pub1`" in first and "Runs added (0): none" in first
    hub.tags.append("v1.1")
    monkeypatch.setattr(P, "remote_changelog", lambda repo: P.changelog_entries(first))
    P.publish([run], repo="me/data", staging=tmp_path / "b", push=True, release="v1.1.1", **QUIET)
    log = hub.uploaded["CHANGELOG.md"]
    assert log.index("## v1.1.1 (") < log.index("## v1.1 (") < log.index("## v1.0 (")


@pytest.mark.parametrize("version", ["v1.0", "v0.9", "v1.0.0", "1.2", "v1", "v1.2-beta"])
def test_release_refused_existing_lower_or_malformed(run, tmp_path, hub, version):
    with pytest.raises(SystemExit):
        P.publish([run], repo="me/data", staging=tmp_path / "st", push=True, release=version, **QUIET)
    assert hub.calls == [] and not (tmp_path / "st").exists()                     # refused before staging or upload


def test_changelog_entries_of_a_card_without_a_changelog_is_empty():
    card = "---\nlicense: cc-by-4.0\n---\n\n# Charter runs\n\nIntro.\n\n## Layout\n- files\n\n## Runs (2)\n| a |\n\n## License\nCC"
    assert P.changelog_entries(card) == ""                                       # the first release on a pre-release card
    assert P.changelog_entries(OLD_LOG).startswith("## v1.0 (2026-10-01)")


def test_release_ignores_non_semver_tags():
    assert P.latest_release(["v0-legacy-layout", "v1.2", "v1.10", "v1.9.3", "draft"]) == "v1.10"
    assert P.check_release("v0.1", ["v0-legacy-layout"]) is None
    assert P.check_release("v0.9", ["v0-legacy-layout"]) is None and P.parse_release("v0.9")       # the first release on the Hub
    assert P.bump_of("v2.0", "v1.4") == "major" and P.bump_of("v1.5", "v1.4") == "minor" and P.bump_of("v1.4.1", "v1.4") == "patch"


def test_release_warns_on_small_bump(run, tmp_path, hub):
    logs = []
    P.publish([run], repo="me/data", staging=tmp_path / "st", push=True, release="v1.0.1", log=logs.append)
    assert any("WARNING" in m and "minor" in m for m in logs) and hub.calls[-1][:2] == ("tag", "v1.0.1")


def test_push_without_release_no_tag_no_entry(run, tmp_path, hub):
    logs = []
    s = P.publish([run], repo="me/data", staging=tmp_path / "st", push=True, log=logs.append)
    assert [c[0] for c in hub.calls] == ["upload"] and s["tag"] is None
    assert "## v1.0 (2026-10-01)" in hub.uploaded["CHANGELOG.md"] and "## v1.1" not in hub.uploaded["CHANGELOG.md"]
    assert "### v1.0 (2026-10-01)" in hub.uploaded["README.md"]                   # history stays on the card
    assert any("reminder" in m and "--release" in m for m in logs)


def test_era_derivation_and_override(run, tmp_path, offline):
    meta = json.loads((run / "run.json").read_text())
    assert meta.get("engine_version") is not None and P.era_of(run) == "current"
    legacy = tmp_path / "old"
    legacy.mkdir()
    (legacy / "run.json").write_text(json.dumps({k: v for k, v in meta.items() if k != "engine_version"}))
    assert P.era_of(legacy) == "legacy" and P.era_of(tmp_path / "missing") == "legacy"
    assert P.era_of(run, {"era": "legacy"}) == "legacy"
    with pytest.raises(SystemExit):
        P.era_of(run, {"era": "ancient"})
    s = P.publish([run], repo="me/data", staging=tmp_path / "st", cards={"pub1": {"era": "legacy"}}, **QUIET)
    [row] = json.loads((Path(s["staging"]) / "catalog.json").read_text())["runs"]
    assert row["era"] == "legacy" and row["engine_version"] is not None
    assert {"era", "engine_version"} <= set(pq.read_table(Path(s["staging"]) / "catalog.parquet").column_names)


def test_stories_only_publish_checks_the_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "remote_catalog", lambda repo, revision=None: [{"run_id": "r1"}])
    (tmp_path / "stories.yaml").write_text(
        "- {title: A, subtitle: B, quote: C, agent: Ann, run_id: r1, mood: happy, extra: dropped}\n"
        "- {title: D, quote: E, agent: Bo, run_id: gone}\n")
    stories = P.load_stories(tmp_path / "stories.yaml")
    assert "extra" not in stories[0]
    s = P.publish([], repo="me/data", staging=tmp_path / "st", stories=stories, **QUIET)
    assert json.loads((tmp_path / "st" / "stories.json").read_text())["stories"][0]["agent"] == "Ann"
    assert any("missing subtitle" in p for p in s["problems"]) and any("gone is not in the catalog" in p for p in s["problems"])
    monkeypatch.setattr(P, "_api", lambda: pytest.fail("no upload with problems"))
    with pytest.raises(SystemExit):
        P.publish([], repo="me/data", staging=tmp_path / "st2", stories=stories, push=True, **QUIET)


def test_skip_missing_stories_drops_and_lists_them(run, tmp_path, offline):
    stories = [{"title": "A", "subtitle": "B", "quote": "C", "agent": "Ann", "run_id": "pub1"},
               {"title": "D", "subtitle": "E", "quote": "F", "agent": "Bo", "run_id": "elsewhere"}]
    logs = []
    s = P.publish([run], repo="me/data", staging=tmp_path / "st", stories=stories, skip_missing_stories=True, log=logs.append)
    assert s["problems"] == [] and s["stories"] == 1 and s["stories_dropped"] == ["D (elsewhere)"]
    assert [x["title"] for x in json.loads((tmp_path / "st" / "stories.json").read_text())["stories"]] == ["A"]
    assert any("WARNING" in m and "elsewhere" in m for m in logs)
    s = P.publish([run], repo="me/data", staging=tmp_path / "st2", stories=stories, **QUIET)     # without it: refused
    assert any("elsewhere is not in the catalog" in p for p in s["problems"])


# ------------------------------------------------------------------ what each call saw: the two prompt formats
# Abridged from real reasoning.jsonl prompts. Full: agents.dm_prompt (Ashwood I and earlier: the DM step repeats the whole turn
# prompt after "Your plan for this round"). Delta and history (context.dm_delta, context.history: Ashwood II on): the DM step is a
# short continuation ("Since you acted you received:"), and the next turn shows last round's private messages as threads.
def _dm(i, rnd, frm, to):
    return {"id": i, "type": "dm", "round": rnd, "agent": frm, "data": {"to": to, "text": "x"}}


def _saw(tmp_path, rows, events):
    (tmp_path / "reasoning.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    data = {"events": events, "reasoning": [{"round": r["round"], "agent": r["agent"], "phase": r["phase"]} for r in rows]}
    P._what_each_call_saw(data, tmp_path / "reasoning.jsonl")
    return {(x["round"], x["agent"], x["phase"]): {k: x[k] for k in ("saw", "lookup_results") if k in x} for x in data["reasoning"]}


FULL_TURN = ("Round 1 of 2. Everyone decides now ...\n\nWhat changed since your last turn:\n"
             "[e1 r1] DM Bo -> Ann: before the round\n[e2 r1] Bo posted: hello\n\nYour notes from last turn:\n(none)")


def test_what_each_call_saw_full_dm_prompts(tmp_path):
    rows = [
        {"round": 0, "agent": "Ann", "phase": "decide", "prompt": FULL_TURN},
        {"round": 0, "agent": "Ann", "phase": "dm_reply_1", "prompt":
            "Round 1: private messages have arrived before anyone's actions have run this round (exchange 1 of 2).\n\n"
            "New messages to you (and the text of any lookups you asked for):\n[e5 r1] DM Bo -> Ann: deal?\n"
            "(lookup result) Lookup manual {\"section\": \"x\"}:\nManual: x\n- a line\n\n"
            "Your plan for this round (not yet carried out):\n- harvest {}\n\nYour reasoning when you made that plan:\nr\n\n"
            "The turn prompt you saw at the start of this round, for reference:\n" + FULL_TURN
            + "\n[e9 r1] DM Cy -> Ann: only in the repeated part"},
        {"round": 1, "agent": "Ann", "phase": "decide", "prompt":
            "What changed since your last turn:\n[e5 r1] DM Bo -> Ann: deal?\n[e7 r1] DM Bo -> Ann: last wave"},
    ]
    out = _saw(tmp_path, rows, [_dm("e1", 0, "Bo", "Ann"), _dm("e5", 0, "Bo", "Ann"), _dm("e7", 0, "Bo", "Ann"),
                                _dm("e9", 0, "Cy", "Ann")])
    assert out[(0, "Ann", "decide")] == {"saw": ["e1"]}
    assert out[(0, "Ann", "dm_reply_1")] == {"saw": ["e5"], "lookup_results": [
        {"head": "Lookup manual {\"section\": \"x\"}", "text": "Manual: x\n- a line"}]}
    assert out[(1, "Ann", "decide")] == {"saw": ["e7"]}


def _delta(n, body, left="2 of your 3"):
    return (f"Round 1: private messages have arrived before anyone's actions have run this round (exchange {n} of 2). "
            f"Since you acted you received:\n{body}\n\nYou have {left} messages left this round (extra ones are not sent). Reply "
            "in the same format: \"actions\" is your whole plan for the round ... Anyone you message now is shown it at once.")


def test_what_each_call_saw_delta_and_history_prompts(tmp_path):
    rows = [
        {"round": 0, "agent": "Ann", "phase": "decide", "prompt": "# Round 1 (now)\n\n## What happened since your last turn\n"
            "[e1 r1] DM Bo -> Ann: before the round\n\n## State (round 1)\n..."},
        {"round": 0, "agent": "Bo", "phase": "decide", "prompt": "# Round 1 (now)\n\n## What happened since your last turn\n(nothing new)"},
        {"round": 0, "agent": "Ann", "phase": "dm_reply_1", "prompt": _delta(1, "[e5 r1] DM Bo -> Ann: deal?\nsecond line\n"
            "(lookup result) Lookup read_file {\"name\": \"rounds/r05\"}:\nERROR you have no file 'rounds/r05'")},
        {"round": 0, "agent": "Bo", "phase": "dm_reply_2", "prompt": _delta(2, "[e6 r1] DM Ann -> Bo (reply to e5): yes", "0 of your 3")},
        # round 2, a continuing conversation: last round's results and private messages, as threads (e7: Ann's last-wave reply)
        {"round": 1, "agent": "Bo", "phase": "decide", "prompt": "# Round 2\n\n## Results of your round 1 actions\nWhat you did: ...\n\n"
            "## Your private messages in round 1 (every message you received and sent, in order)\nWith Ann:\n"
            "  [e5 r1] DM Bo -> Ann: deal?\n  [e6 r1] DM Ann -> Bo (reply to e5): yes\n  [e7 r1] DM Ann -> Bo: last wave\n\n"
            "## What happened since your last turn\n(nothing new)"},
        # context.dm_delta without history: the turn prompt's "## Your private messages last round" section
        {"round": 1, "agent": "Ann", "phase": "decide", "prompt": "## State\n...\n\n## Your private messages last round (round 1, every "
            "message you received and sent, in order)\nWith Bo:\n  [e1 r1] DM Bo -> Ann: before the round\n  [e5 r1] DM Bo -> Ann: deal?\n"
            "  [e6 r1] DM Ann -> Bo (reply to e5): yes\nWith Cy:\n  [e8 r1] DM Cy -> Ann: late\n\n## What changed since your last turn\n..."},
        # a restarted conversation (every 3 rounds): the history block repeats earlier rounds' messages; nothing in it is new
        {"round": 3, "agent": "Bo", "phase": "decide", "prompt": "# Earlier rounds\n## Round 1\nWith Ann:\n  [e5 r1] DM Bo -> Ann: deal?\n"
            "  [e6 r1] DM Ann -> Bo (reply to e5): yes\n  [e7 r1] DM Ann -> Bo: last wave\n\n# Round 4 (now)\n\n## What happened since "
            "your last turn\n[e20 r4] DM Ann -> Bo: new"},
    ]
    events = [_dm("e1", 0, "Bo", "Ann"), _dm("e5", 0, "Bo", "Ann"), _dm("e6", 0, "Ann", "Bo"), _dm("e7", 0, "Ann", "Bo"),
              _dm("e8", 0, "Cy", "Ann"), _dm("e20", 3, "Ann", "Bo")]
    out = _saw(tmp_path, rows, events)
    assert out[(0, "Ann", "decide")] == {"saw": ["e1"]} and out[(0, "Bo", "decide")] == {}
    assert out[(0, "Ann", "dm_reply_1")] == {"saw": ["e5"], "lookup_results": [
        {"head": "Lookup read_file {\"name\": \"rounds/r05\"}", "text": "ERROR you have no file 'rounds/r05'"}]}
    assert out[(0, "Bo", "dm_reply_2")] == {"saw": ["e6"]}
    assert out[(1, "Bo", "decide")] == {"saw": ["e7"]}             # sent in the last wave: first shown next round
    assert out[(1, "Ann", "decide")] == {"saw": ["e8"]}             # its own e6 and the already seen e1, e5 are not counted
    assert out[(3, "Bo", "decide")] == {"saw": ["e20"]}


def test_what_each_call_saw_unknown_dm_step_falls_back_to_the_whole_prompt(tmp_path):
    rows = [{"round": 0, "agent": "Ann", "phase": "decide", "prompt": "[e1 r1] DM Bo -> Ann: a"},
            {"round": 0, "agent": "Ann", "phase": "dm_reply_1", "prompt": "Some later format\n[e1 r1] DM Bo -> Ann: a\n[e2 r1] DM Bo -> Ann: b"},
            {"round": 0, "agent": "Bo", "phase": "dm_reply_1"}]                                       # no prompt recorded: skipped
    out = _saw(tmp_path, rows, [_dm("e1", 0, "Bo", "Ann"), _dm("e2", 0, "Bo", "Ann")])
    assert out[(0, "Ann", "dm_reply_1")] == {"saw": ["e2"]} and out[(0, "Bo", "dm_reply_1")] == {}
