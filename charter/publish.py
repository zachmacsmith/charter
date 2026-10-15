"""Publish runs to a Hugging Face dataset: export tables, a raw archive, a run catalog and the dataset card, in one commit.

    python -m charter publish RUN [RUN...] --repo OWNER/NAME [--card CARDS.yaml] [--push] [--release vX.Y[.Z] [--notes "..."]]
    python -m charter publish --repo OWNER/NAME --reexport-all [--push]      # rebuild every published run's tables

Without --push nothing leaves the machine: the dataset is staged in --staging (default charter/out/_publish/<time>) and a summary
of what would be uploaded is printed. Layout on the Hub (docs/data_format.md, "Layout on Hugging Face"):

    catalog.parquet, catalog.json             one row per published run: the site's index (curated card + key run facts)
    stories.json                              the stories registry the site's home page rotates through (--stories)
    runs/<spec>/<run_id>/<table>.parquet      charter.export tables for that run, plus manifest.json and card.json
    raw/<spec>/<run_id>.tar.gz                the raw run directory (the record; re-exported from when the schema changes)
    README.md                                 dataset card with one config per table (the Hub's viewer and SQL console span all runs)
    CHANGELOG.md                              one entry per release, newest first (also the card's "Changelog" section)

Each run is replaced as a unit: publishing a run deletes whatever its folder and archive held before, so a republish never leaves
stale files behind. Tables are written by charter.export and are never edited here; publish refuses to upload when an exported
table holds an absolute path or the home directory (fix the exporter, not the output), when a checkpoint or pickle is staged,
or when the published runs would mix export schema majors (use --reexport-all). Raw files are text logs written by the
simulator; local paths in them are rewritten to `<spec>/<run>`-relative ones before archiving.

A card gives a run its curated facts, all optional: title, description, tags, featured, usable_rounds ("1-23"), validity. --card
takes a YAML or JSON file: either one card, or {run_id: card, ...}. Without one, the title is "<spec> seed <seed>" and usable
rounds and validity come from VALIDITY.md / STOPPED.md when present. A card may also set `era` (see below).

Versions and releases (docs/data_format.md, "Versions and releases"; every person or agent publishing follows this):

- The dataset is a git repo; a release is a git tag `vMAJOR.MINOR[.PATCH]` on the commit that publishes it. Publish with
  `--push --release vX.Y[.Z] --notes "..."`: the upload commit carries a new entry at the top of CHANGELOG.md and of the card's
  "Changelog" section (version, date, runs added / replaced, export schema, engine versions, notes; earlier entries are read
  from the Hub and kept), then the tag is created at that commit. Publish refuses a malformed version, one whose tag exists, or
  one not greater than the latest `v*` semver tag (non-semver tags such as `v0-legacy-layout` are ignored). A push without
  --release uploads as before (no tag, no entry) and prints a reminder; the next release's notes should mention it.
- MAJOR: a breaking change: the export schema major changes (`schema_version`) or the layout on the Hub changes.
  MINOR: runs added or replaced, or columns / tables added (export `schema_minor`, catalog columns).
  PATCH: card, catalog or changelog fixes only (no table changes). Publish warns when the bump looks smaller than the change.
- Old layouts live in tags (e.g. `v0-legacy-layout`), never in archive folders on main. Readers pin a release with
  `revision="v1.0"` (huggingface_hub / datasets) or `hf://datasets/<repo>@v1.0/...` (DuckDB, pandas, polars).
- Runs are kept when the simulation changes. Catalog `era`: "legacy" for a run whose run.json has no `engine_version` (played
  before engine versions, under earlier simulation designs), else "current"; a card's `era` overrides it. Sites filter
  `era = 'legacy'` out by default. The catalog's `engine_version` is the export's `runs.engine_version`.
- Papers cite a DOI snapshot of a tagged release (e.g. Zenodo), not main.

--stories takes the stories registry (site/stories.yaml: a list of {title, subtitle, quote, agent, run_id, class, model, mood,
round}) and writes it as stories.json, replacing the published one. With no runs, only stories.json is staged and uploaded.
A story whose run is not in the catalog is a problem (nothing is uploaded); --skip-missing-stories instead warns, drops it from
stories.json and lists it in the summary ("stories_dropped").
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import tarfile
import time
from pathlib import Path

from charter import export as X

DEFAULT_REPO = "zachmacsmith/charter-runs"
STAGING = Path(__file__).resolve().parent / "out" / "_publish"
# raw files never published: pickles execute code when loaded; the rest are reports rebuilt from the data
NEVER = re.compile(r"(^|/)(checkpoints?(/|$)|.*\.pkl$|.*\.pickle$|abandoned_calls\.jsonl$)")
REPORTS = {"story.html", "messages.md", "overview.md", "observer.md", "spec_outline.md"}
CARD_KEYS = ("title", "description", "tags", "featured", "usable_rounds", "validity", "era")
STORY_KEYS = ("title", "subtitle", "quote", "agent", "run_id", "class", "model", "mood", "round")
STORY_REQUIRED = ("title", "subtitle", "quote", "agent", "run_id")
CATALOG_RUN_COLS = ("seed", "rounds", "rounds_played", "complete", "dry", "backend", "schema_version", "models_json",
                    "parent_run_id", "fork_round", "code_sha", "engine_version")
ERAS = ("legacy", "current")
RELEASE = re.compile(r"^v(\d+)\.(\d+)(?:\.(\d+))?$")


# ------------------------------------------------------------------ helpers
def _home() -> str:
    return str(Path.home())


def _local_prefixes(run: Path) -> list[str]:
    """Absolute path prefixes that may appear in a run's logs: the run's own location (resolved and as given), and home."""
    out = {str(run.resolve().parent.parent), str(run.parent.parent.absolute()), str(Path.cwd()),
           str(Path(__file__).resolve().parents[1])}                   # this checkout
    for q in (run.resolve(), run.absolute()):                          # the checkout that wrote the run (<root>/charter/out/...)
        parts = q.as_posix().split("/charter/out/")
        if len(parts) > 1 and parts[0]:
            out.add(parts[0])
    for p in list(out):
        if p.startswith("/private/"):
            out.add(p[len("/private"):])
    return sorted(out, key=len, reverse=True)


def spec_of(run: Path) -> str:
    """The spec a run belongs to: instance.json's spec name when it records one, else the directory the run sits in."""
    inst = X._json(run / "instance.json", {}) or {}
    spec = inst.get("spec") if isinstance(inst.get("spec"), dict) else {}
    return str(inst.get("spec_name") or spec.get("name") or run.parent.name)


def run_id_of(run: Path) -> str:
    from charter import provenance as PV
    return (PV.read(run) or {}).get("run_id") or run.name


def parse_rounds(text: str | None):
    """'1-23' / '1–23' -> [1, 23]; None when absent."""
    m = re.search(r"(\d+)\s*[-–]\s*(\d+)", text or "")
    return [int(m.group(1)), int(m.group(2))] if m else None


def default_card(run: Path) -> dict:
    """Card facts a run states itself: usable rounds and the first paragraph of VALIDITY.md or STOPPED.md."""
    card = {}
    for f in ("VALIDITY.md", "STOPPED.md"):
        p = run / f
        if p.exists():
            text = p.read_text()
            m = re.search(r"[Uu]sable rounds:?\s*\**\s*(\d+\s*[-–]\s*\d+)", text)
            if m:
                card["usable_rounds"] = m.group(1).replace(" ", "").replace("–", "-")
            body = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip() and not b.lstrip().startswith("#")]
            if body:
                card["validity"] = re.sub(r"\s+", " ", body[0])[:600]
            break
    return card


def era_of(run: Path, card: dict | None = None) -> str:
    """'legacy' when run.json records no engine_version (a run from before engine versions), else 'current'; a card's era wins."""
    era = (card or {}).get("era")
    if era:
        if era not in ERAS:
            raise SystemExit(f"card era must be one of {ERAS}, not {era!r}")
        return era
    meta = X._json(run / "run.json", {}) or {}
    return "current" if meta.get("engine_version") is not None else "legacy"


def load_cards(path) -> dict:
    """{run_id: card} from a YAML/JSON file holding one card or a mapping of cards (a single card is returned under '*')."""
    if not path:
        return {}
    text = Path(path).read_text()
    if str(path).endswith((".yaml", ".yml")):
        import yaml
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    if any(k in data for k in CARD_KEYS):
        return {"*": data}
    return data


def load_stories(path) -> list[dict] | None:
    """The stories registry: a YAML/JSON list of stories (or {"stories": [...]}), trimmed to STORY_KEYS."""
    if not path:
        return None
    text = Path(path).read_text()
    if str(path).endswith((".yaml", ".yml")):
        import yaml
        data = yaml.safe_load(text) or []
    else:
        data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("stories", [])
    return [{k: (v.strip() if isinstance(v, str) else v) for k, v in st.items() if k in STORY_KEYS and v is not None}
            for st in data]


def check_stories(stories: list[dict], run_ids: set[str]) -> list[str]:
    problems = []
    for i, st in enumerate(stories):
        name = st.get("title") or f"story {i + 1}"
        missing = [k for k in STORY_REQUIRED if not st.get(k)]
        if missing:
            problems.append(f"story '{name}': missing {', '.join(missing)}")
        if st.get("run_id") and st["run_id"] not in run_ids:
            problems.append(f"story '{name}': run {st['run_id']} is not in the catalog")
        if st.get("mood", "ok") not in ("ok", "happy", "sad"):
            problems.append(f"story '{name}': mood must be ok, happy or sad")
    return problems


def drop_missing_stories(stories: list[dict], run_ids: set[str], log=print) -> tuple[list[dict], list[dict]]:
    """(kept, dropped): the stories whose run is in the catalog, and those whose run is not (each dropped one is warned about)."""
    kept, dropped = [], []
    for st in stories:
        (kept if not st.get("run_id") or st["run_id"] in run_ids else dropped).append(st)
    for st in dropped:
        log(f"WARNING: story '{st.get('title')}' dropped: run {st['run_id']} is not in the catalog")
    return kept, dropped


def write_stories(stories: list[dict], stage: Path) -> None:
    (stage / "stories.json").write_text(json.dumps({"stories": stories}, indent=1, ensure_ascii=False))


# ------------------------------------------------------------------ guards
LOCAL = re.compile(r"(^|[\s\"'=(:])(/Users/|/home/|/private/var/|[A-Za-z]:\\\\Users\\\\)")


def _strings_with_local_paths(values, home: str) -> list[str]:
    bad = []
    for v in values:
        if isinstance(v, str) and (v.startswith("/") or home in v or LOCAL.search(v)):
            bad.append(v[:120])
    return bad


def check_tables(table_dir: Path) -> list[str]:
    """Problems in exported tables: any string value that is an absolute path or holds the home directory."""
    home, problems = _home(), []
    for f in sorted(table_dir.glob("*.parquet")):
        import pyarrow.parquet as pq
        t = pq.read_table(f)
        for name in t.column_names:
            col = t.column(name)
            if str(col.type) not in ("string", "large_string"):
                continue
            bad = _strings_with_local_paths(col.to_pylist(), home)
            if bad:
                problems.append(f"{f.name}.{name}: {len(bad)} value(s) like {bad[0]!r}")
    man = table_dir / "manifest.json"
    if man.exists():
        bad = _strings_with_local_paths(re.findall(r'"([^"]*)"', man.read_text()), home)
        if bad:
            problems.append(f"manifest.json: {len(bad)} value(s) like {bad[0]!r}")
    return problems


def check_staging(stage: Path) -> list[str]:
    problems = []
    for p in stage.rglob("*"):
        rel = p.relative_to(stage).as_posix()
        if NEVER.search(rel):
            problems.append(f"never published: {rel}")
    for tar in stage.glob("raw/**/*.tar.gz"):
        with tarfile.open(tar) as tf:
            for m in tf.getmembers():
                if NEVER.search(m.name):
                    problems.append(f"never published: {tar.name}:{m.name}")
                elif m.isfile():
                    try:
                        text = tf.extractfile(m).read().decode()
                    except UnicodeDecodeError:
                        continue
                    hit = LOCAL.search(text)
                    if hit:
                        problems.append(f"local path left in {tar.name}:{m.name}: ...{text[max(0, hit.start() - 20):hit.end() + 40]}...")
    return problems


# ------------------------------------------------------------------ raw archive
def _scrub(text: str, prefixes: list[str], home: str) -> str:
    for p in prefixes:
        text = text.replace(p.rstrip("/") + "/", "")
    return text.replace(home, "~")


def raw_archive(run: Path, out: Path, spec: str) -> dict:
    """The run directory as a .tar.gz under <spec>/<run>/ (no checkpoints, pickles or rebuilt reports; local paths scrubbed)."""
    prefixes, home = _local_prefixes(run), _home()
    out.parent.mkdir(parents=True, exist_ok=True)
    files, size = 0, 0
    with tarfile.open(out, "w:gz") as tf:
        for p in sorted(run.rglob("*")):
            rel = p.relative_to(run).as_posix()
            if p.is_dir() or NEVER.search(rel) or rel in REPORTS:
                continue
            data = p.read_bytes()
            if p.suffix in (".json", ".jsonl", ".md", ".txt", ".yaml", ".yml", ".log", ".csv"):
                try:
                    data = _scrub(data.decode(), prefixes, home).encode()
                except UnicodeDecodeError:
                    pass
            info = tarfile.TarInfo(f"{spec}/{run.name}/{rel}")
            info.size, info.mtime, info.mode = len(data), int(p.stat().st_mtime), 0o644
            tf.addfile(info, io.BytesIO(data))
            files, size = files + 1, size + len(data)
    return {"files": files, "bytes_raw": size, "bytes_archive": out.stat().st_size}


def viewer_data(run: Path) -> dict:
    """TEMPORARY (--with-viewer-json): the story viewer's data, plus each model call's planned actions (and, for the decide call,
    the actions that finally ran), so the site can order a round's phases: decide -> DM waves (dm_reply_1, 2) -> final actions."""
    from charter import viewer as V
    data = V.load(run)
    plans = {}
    p = Path(run) / "reasoning.jsonl"
    for line in (p.read_text().splitlines() if p.exists() else []):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        plans[(r.get("round"), r.get("agent"), r.get("phase"))] = {k: r[k] for k in ("actions", "final_actions") if r.get(k)}
    for x in data["reasoning"]:
        x.update(plans.get((x.get("round"), x.get("agent"), x.get("phase")), {}))
    _what_each_call_saw(data, p)
    return data


_DM_LINE = re.compile(r"\[(e\d+) r\d+\] DM ")
_PHASE_ORDER = {"lookup": -1, "decide": 0}
# A DM-step reply prompt's new part, in the two formats the engine has written:
# - full (agents.dm_prompt, before context.dm_delta): "New messages to you ...:" up to "Your plan for this round", followed by
#   the plan and the whole turn prompt again (whose messages the decide call already saw);
# - delta (agents.dm_delta_prompt, context.dm_delta, on by default since): a continuation of the round's conversation, "Since you
#   acted you received:" up to "You have N of your M messages left this round"; nothing else in it repeats earlier text.
_DM_STEP_FULL = re.compile(r"New messages to you(?: \(and the text of any lookups you asked for\))?:\n(.*?)\n\nYour plan for this round", re.S)
_DM_STEP_DELTA = re.compile(r"Since you acted you received:\n(.*)\n\nYou have \d+ of your \d+ messages left this round", re.S)


def _dm_step_section(prompt: str) -> str:
    """The messages and look-up answers a DM-step reply prompt showed for the first time. An unknown format falls back to the
    whole prompt: its messages were either new here or already counted at an earlier call (each is counted once)."""
    m = _DM_STEP_FULL.search(prompt) or _DM_STEP_DELTA.search(prompt)
    return m.group(1) if m else prompt


def _what_each_call_saw(data: dict, reasoning: Path) -> None:
    """From the prompts themselves (the record of what each model call was shown): "saw", the private messages to this agent that
    the call showed it for the first time, and for a DM-step reply, "lookup_results", the look-up answers that arrived with them.
    The site places received messages, and the wave each message was sent in, from this rather than from inference."""
    if not reasoning.exists():
        return
    to = {e["id"]: (e.get("data") or {}).get("to") for e in data["events"] if e.get("type") == "dm"}
    calls = []
    for line in reasoning.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        ph = str(r.get("phase") or "")
        order = _PHASE_ORDER.get(ph, int(ph[9:]) if re.fullmatch(r"dm_reply_\d+", ph) else None)
        if order is not None and r.get("prompt"):
            calls.append(((r["round"], order), r))
    seen, out = set(), {}
    for _, r in sorted(calls, key=lambda c: (c[0], c[1].get("agent", ""))):
        aid, prompt, results = r["agent"], r["prompt"], []
        if str(r.get("phase")).startswith("dm_reply"):
            prompt = _dm_step_section(prompt)
            dm_part, _, rest = prompt.partition("(lookup result) ")
            for chunk in (("(lookup result) " + rest).split("(lookup result) ")[1:] if rest else []):
                head, _, text = chunk.partition(":\n")
                results.append({"head": head.strip()[:300], "text": text.strip()[:6000]})
            prompt = dm_part
        saw = [i for i in dict.fromkeys(_DM_LINE.findall(prompt)) if to.get(i) == aid and (i, aid) not in seen]
        seen.update((i, aid) for i in saw)
        out[(r["round"], aid, r.get("phase"))] = {k: v for k, v in (("saw", saw), ("lookup_results", results)) if v}
    for x in data["reasoning"]:
        x.update(out.get((x.get("round"), x.get("agent"), x.get("phase")), {}))


# ------------------------------------------------------------------ export, catalog, card
def export_run(run: Path, out: Path, root: Path | None = None, with_prompts: bool = False) -> dict:
    """charter.export for one run into `out`, passing root=/with_prompts= when the exporter supports them."""
    import inspect
    params = inspect.signature(X.export).parameters
    kw = {}
    if "root" in params:
        kw["root"] = root or run.parent.parent
    if "with_prompts" in params:
        kw["with_prompts"] = with_prompts
    return X.export([run], out, fmt="parquet", **kw)


def _read_rows(table_path: Path) -> list[dict]:
    import pyarrow.parquet as pq
    return pq.read_table(table_path).to_pylist() if table_path.exists() else []


def catalog_row(spec: str, run_id: str, table_dir: Path, card: dict, published_at: str) -> dict:
    """One catalog row: the curated card plus the facts the site lists runs by, read from the exported tables."""
    runs = _read_rows(table_dir / "runs.parquet")
    r = runs[0] if runs else {}
    agents = _read_rows(table_dir / "agents.parquet")
    man = json.loads((table_dir / "manifest.json").read_text())
    models = sorted({a.get("model") for a in agents if a.get("model")})
    row = {"run_id": run_id, "spec": spec, "path": f"runs/{spec}/{run_id}", "raw": f"raw/{spec}/{run_id}.tar.gz",
           "title": card.get("title") or f"{spec} seed {r.get('seed', '?')}",
           "description": card.get("description"), "tags_json": json.dumps(card.get("tags") or []),
           "featured": bool(card.get("featured", False)), "usable_rounds": card.get("usable_rounds"),
           "validity": card.get("validity"), "era": card.get("era"), "published_at": published_at,
           "schema_version": man.get("schema_version"), "schema_minor": man.get("schema_minor"),
           "n_agents": len(agents), "models_list_json": json.dumps(models),
           "rows_json": json.dumps({t: v.get("rows") for t, v in man.get("tables", {}).items()}, sort_keys=True)}
    for k in CATALOG_RUN_COLS:
        if k in r and k not in row:
            row[k] = r[k]
    return row


CATALOG_COLS = ("run_id", "spec", "path", "raw", "title", "description", "tags_json", "featured", "usable_rounds", "validity",
                "era", "published_at", "schema_version", "schema_minor", "n_agents", "models_list_json", "rows_json") + CATALOG_RUN_COLS


def write_catalog(rows: list[dict], stage: Path) -> None:
    rows = sorted(rows, key=lambda r: (r["spec"], r["run_id"]))
    (stage / "catalog.json").write_text(json.dumps({"runs": rows}, indent=1, default=str))
    import pyarrow as pa
    import pyarrow.parquet as pq
    cols = {c: [r.get(c) for r in rows] for c in CATALOG_COLS}
    pq.write_table(pa.table(cols), stage / "catalog.parquet")


# ------------------------------------------------------------------ dataset card
CARD_HEAD = """---
license: cc-by-4.0
pretty_name: Charter runs
language: [en]
tags: [multi-agent, llm-agents, agent-societies, governance, simulation, claude, transcripts]
configs:
{configs}
---
"""

CARD_BODY = """# Charter runs

Complete records of societies of LLM agents (Claude Haiku, Sonnet and Opus) played in
[Charter](https://github.com/zachmacsmith/charter): agents harvest, trade, message each other and govern themselves through laws
written as executable code, each with private goals scored from game state.

The agents are told they are playing a scored game, and when interviewed they say they know it is a multi-agent simulation in
which they are AI models playing roles ("Underneath the character, I'm Claude, an AI model (Haiku 5.5), playing this role and
trying to keep Jory alive"), so read behaviour here as play within a game frame, not as what the models would do with real stakes.

## Layout
- `catalog.parquet` / `catalog.json`: one row per run (title, description, tags, models, rounds, usable rounds, validity notes).
- `runs/<spec>/<run_id>/<table>.parquet`: the run as typed tables (events, messages, channels, turns, state, laws, scores, ...),
  with `manifest.json` (schema version, rows per table) and `card.json`. Column reference:
  [docs/data_format.md](https://github.com/zachmacsmith/charter/blob/main/docs/data_format.md) and
  [docs/export.md](https://github.com/zachmacsmith/charter/blob/main/docs/export.md).
- `raw/<spec>/<run_id>.tar.gz`: the raw run directory (event log, turn log, model calls, snapshots, run.json); the tables are
  rebuilt from it with `python -m charter export`.

Each table is also a config here, spanning every run, so the viewer and SQL console work across runs. With DuckDB:

```sql
SELECT run_id, channel_id, sender, text FROM 'hf://datasets/{repo}/runs/*/*/messages.parquet' WHERE channel_kind = 'dm' LIMIT 20;
```

## Runs ({n_runs})
| run | spec | agents | models | usable rounds | |
|---|---|---|---|---|---|
{run_rows}

Runs with `era = legacy` were played before engine versions, under earlier simulation designs; they are kept for the record.

## Versions
Releases are git tags `vMAJOR.MINOR[.PATCH]` on this dataset (major: export schema major or layout change; minor: runs or
columns added; patch: card or catalog fixes). Older layouts live in tags (`v0-legacy-layout`), not in folders. Pin a release
with `revision="v1.0"` or `hf://datasets/{repo}@v1.0/catalog.parquet`; cite a DOI snapshot of a tagged release.

## Changelog
{changelog}

## License
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The Charter code is MIT-licensed.
"""

CHANGELOG_HEAD = """# Changelog

Releases of this dataset, newest first. Each is a git tag on the commit that published it; the rules are in the dataset card's
"Versions" section and in [docs/data_format.md](https://github.com/zachmacsmith/charter/blob/main/docs/data_format.md).

"""


def changelog_entries(text: str) -> str:
    """The entries of a CHANGELOG.md (everything from the first '## ' heading), or of a card's '## Changelog' section ('### ')."""
    if not text:
        return ""
    if not text.lstrip().startswith("# Changelog"):                     # a dataset card: only its Changelog section (a card
        if "\n## Changelog" not in "\n" + text:                         # without one has no entries, not its Layout and Runs)
            return ""
        sec = ("\n" + text).split("\n## Changelog", 1)[1]
        sec = re.split(r"\n## ", sec, maxsplit=1)[0]
        return re.sub(r"(?m)^### ", "## ", sec).strip() if "### " in sec else ""
    m = re.search(r"(?m)^## ", text)
    return text[m.start():].strip() if m else ""


def changelog_entry(version: str, date: str, added: list[str], replaced: list[str], catalog: list[dict],
                    notes: str | None) -> str:
    """One CHANGELOG.md entry (a '## ' section)."""
    schemas = sorted({f"{r.get('schema_version')}.{r.get('schema_minor') or 0}" for r in catalog if r.get("schema_version") is not None})
    engines = sorted({r["engine_version"] for r in catalog if r.get("engine_version") is not None})
    n_legacy = sum(1 for r in catalog if r.get("era") == "legacy")
    out = [f"## {version} ({date})", ""]
    out.append(f"- Runs added ({len(added)}): " + (", ".join(f"`{x}`" for x in added) or "none"))
    out.append(f"- Runs replaced ({len(replaced)}): " + (", ".join(f"`{x}`" for x in replaced) or "none"))
    out.append(f"- Export schema: {', '.join(schemas) or 'unknown'}")
    out.append(f"- Engine versions: {', '.join(map(str, engines)) or 'none'}"
               + (f" (plus {n_legacy} legacy run(s) without one)" if n_legacy else ""))
    out.append(f"- Catalog: {len(catalog)} run(s)")
    if notes:
        out.append(f"- Notes: {notes.strip()}")
    return "\n".join(out)


def render_changelog(entries: str) -> str:
    return CHANGELOG_HEAD + (entries.strip() + "\n" if entries.strip() else "")


def card_changelog(entries: str) -> str:
    return re.sub(r"(?m)^## ", "### ", entries.strip()) if entries.strip() else "No tagged release yet."


def dataset_card(repo: str, tables: list[str], catalog: list[dict], changelog: str = "") -> str:
    configs = ["- config_name: catalog\n  data_files: catalog.parquet\n  default: true"]
    configs += [f"- config_name: {t}\n  data_files: runs/*/*/{t}.parquet" for t in sorted(tables)]
    rows = []
    for c in sorted(catalog, key=lambda r: (r["spec"], r["run_id"])):
        models = ", ".join(m.replace("claude-", "") for m in json.loads(c.get("models_list_json") or "[]"))
        rows.append(f"| {c['title']} | `{c['spec']}` | {c.get('n_agents') or ''} | {models} | {c.get('usable_rounds') or 'all'} | "
                    f"[files]({c['path']}) |")
    return CARD_HEAD.format(configs="\n".join(configs)) + "\n" + CARD_BODY.format(repo=repo, n_runs=len(catalog),
                                                                              run_rows="\n".join(rows),
                                                                              changelog=card_changelog(changelog))


# ------------------------------------------------------------------ releases
def parse_release(version: str) -> tuple[int, int, int]:
    m = RELEASE.match(version or "")
    if not m:
        raise SystemExit(f"--release must look like v1.2 or v1.2.3, not {version!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def latest_release(tags: list[str]) -> str | None:
    """The greatest semver tag (vX.Y[.Z]); other tags (v0-legacy-layout) are ignored."""
    sem = [t for t in tags if RELEASE.match(t)]
    return max(sem, key=parse_release) if sem else None


def check_release(version: str, tags: list[str]) -> str | None:
    """Refuse a malformed version, an existing tag or one not above the latest release; returns that latest release."""
    v = parse_release(version)
    if version in tags:
        raise SystemExit(f"tag {version} already exists on the dataset: pick the next version")
    last = latest_release(tags)
    if last and v <= parse_release(last):
        raise SystemExit(f"--release {version} is not greater than the latest release {last}")
    return last


def suggested_bump(published: list[dict], catalog: list[dict], new_ids: set[str]) -> str:
    """The smallest bump the change needs: major (export schema major changed), minor (runs or columns), patch."""
    old_major = {r.get("schema_version") for r in published if r.get("schema_version") is not None}
    new_major = {r.get("schema_version") for r in catalog if r.get("schema_version") is not None}
    if old_major and new_major != old_major:
        return "major"
    old_cols = set().union(*(r.keys() for r in published)) if published else set()
    if new_ids or (published and set(CATALOG_COLS) - old_cols):
        return "minor"
    return "patch"


def bump_of(version: str, last: str | None) -> str:
    if not last:
        return "major"
    a, b = parse_release(version), parse_release(last)
    return "major" if a[0] != b[0] else "minor" if a[1] != b[1] else "patch"


# ------------------------------------------------------------------ hub access
def _api():
    from huggingface_hub import HfApi
    return HfApi()


def remote_catalog(repo: str, revision: str | None = None) -> list[dict]:
    """The catalog currently published, or [] (a new repo, or one from before catalogs)."""
    try:
        from huggingface_hub import hf_hub_download
        p = hf_hub_download(repo, "catalog.json", repo_type="dataset", revision=revision)
        return json.loads(Path(p).read_text()).get("runs", [])
    except Exception:
        return []


def remote_changelog(repo: str) -> str:
    """The published changelog entries: CHANGELOG.md, else the card's Changelog section, else ''."""
    from huggingface_hub import hf_hub_download
    for name in ("CHANGELOG.md", "README.md"):
        try:
            entries = changelog_entries(Path(hf_hub_download(repo, name, repo_type="dataset")).read_text())
        except Exception:
            continue
        if entries:
            return entries
    return ""


def remote_tags(repo: str) -> list[str]:
    """Tag names on the dataset ([] for a repo that does not exist yet)."""
    from huggingface_hub.errors import RepositoryNotFoundError
    try:
        return [t.name for t in _api().list_repo_refs(repo, repo_type="dataset").tags]
    except RepositoryNotFoundError:
        return []


def fetch_raw(repo: str, row: dict, dest: Path) -> Path:
    """Download and unpack a published run's raw archive; returns the run directory."""
    from huggingface_hub import hf_hub_download
    p = hf_hub_download(repo, row["raw"], repo_type="dataset")
    with tarfile.open(p) as tf:
        safe = [m for m in tf.getmembers() if not (m.name.startswith("/") or ".." in Path(m.name).parts) and not NEVER.search(m.name)]
        tf.extractall(dest, members=safe)
    return dest / row["spec"] / Path(row["raw"]).name.removesuffix(".tar.gz")


# ------------------------------------------------------------------ publish
def stage_runs(runs: list[Path], stage: Path, cards: dict, log=print, with_prompts: bool = False,
               spec_override: str | None = None, with_viewer_json: bool = False) -> tuple[list[dict], list[str], set[str]]:
    """Stage each run (tables, card, raw archive). Returns (catalog rows, problems, table names)."""
    rows, problems, tables = [], [], set()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for run in runs:
        spec, rid = spec_override or spec_of(run), run_id_of(run)
        tdir = stage / "runs" / spec / rid
        man = export_run(run, tdir, with_prompts=with_prompts)
        tables |= set(man.get("tables", {}))
        card = {**default_card(run), **cards.get("*", {}), **cards.get(rid, {})}
        card = {k: card[k] for k in CARD_KEYS if card.get(k) is not None}
        card["era"] = era_of(run, card)
        (tdir / "card.json").write_text(json.dumps({"run_id": rid, "spec": spec, **card}, indent=1))
        raw = raw_archive(run, stage / "raw" / spec / f"{rid}.tar.gz", spec)
        if with_viewer_json:                                            # TEMPORARY: the story viewer's own data file, until the
            text = json.dumps(viewer_data(run), separators=(",", ":"), default=str)
            (tdir / "viewer.json").write_text(_scrub(text, _local_prefixes(run), _home()))
        problems += [f"{rid}: {p}" for p in check_tables(tdir)]
        rows.append(catalog_row(spec, rid, tdir, card, now))
        log(f"staged {spec}/{rid}: {sum(v.get('rows') or 0 for v in man['tables'].values())} table rows, raw {raw['files']} files "
            f"{raw['bytes_raw'] / 1e6:.1f} MB -> {raw['bytes_archive'] / 1e6:.1f} MB")
    return rows, problems, tables


def publish(runs, repo: str = DEFAULT_REPO, cards: dict | None = None, push: bool = False, staging=None,
            reexport_all: bool = False, with_prompts: bool = False, spec_override: str | None = None,
            prune_legacy: bool = False, message: str | None = None, release: str | None = None, notes: str | None = None,
            with_viewer_json: bool = False, stories=None, skip_missing_stories: bool = False, log=print) -> dict:
    """Stage (and with push=True, upload) runs as one dataset commit. Returns a summary dict.

    release="vX.Y[.Z]" also prepends a changelog entry (CHANGELOG.md and the card) in that commit and tags it (module docstring).
    stories (a list from load_stories) are written as stories.json, checked against the catalog; skip_missing_stories drops (with a
    warning) the ones whose run is not in it instead of refusing."""
    last_release = None
    if release:
        parse_release(release)
        last_release = check_release(release, remote_tags(repo))     # before any staging or upload
    stage = Path(staging) if staging else STAGING / time.strftime("%Y%m%d-%H%M%S")
    if stage.exists() and any(stage.iterdir()):
        raise SystemExit(f"{stage} is not empty: pass a new --staging directory")
    stage.mkdir(parents=True, exist_ok=True)
    published = remote_catalog(repo)
    cards = cards or {}
    run_dirs = X.find_runs(runs) if runs else []
    tmp = None
    if reexport_all:                                                    # rebuild every published run from its raw archive
        tmp = stage.parent / f".raw-{stage.name}"
        for row in published:
            if not any(run_id_of(d) == row["run_id"] for d in run_dirs):
                log(f"fetching raw {row['raw']}")
                run_dirs.append(fetch_raw(repo, row, tmp))
                cards.setdefault(row["run_id"], {k: (json.loads(row["tags_json"]) if k == "tags" else row.get(k))
                                                 for k in CARD_KEYS if (row.get("tags_json") if k == "tags" else row.get(k))})
    if not run_dirs and stories is not None:
        return publish_stories(stories, repo, stage, published, push=push, message=message,
                               skip_missing_stories=skip_missing_stories, log=log)
    if not run_dirs:
        raise SystemExit("no runs to publish")
    rows, problems, tables = stage_runs(run_dirs, stage, cards, log=log, with_prompts=with_prompts, spec_override=spec_override,
                                        with_viewer_json=with_viewer_json)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    new_ids = {r["run_id"] for r in rows}
    catalog = [r for r in published if r["run_id"] not in new_ids] + rows
    majors = {r.get("schema_version") for r in catalog}
    if len(majors) > 1:
        problems.append(f"published runs would mix export schema majors {sorted(majors, key=str)}: rerun with --reexport-all")
    write_catalog(catalog, stage)
    entries = remote_changelog(repo)                                    # history is kept: the new entry goes on top
    if release:
        old_ids = {r["run_id"] for r in published}
        ref = {r["run_id"]: f"{r['spec']}/{r['run_id']}" for r in rows}
        entry = changelog_entry(release, time.strftime("%Y-%m-%d", time.gmtime()),
                                sorted(ref[i] for i in new_ids - old_ids), sorted(ref[i] for i in new_ids & old_ids),
                                catalog, notes)
        entries = entry + ("\n\n" + entries if entries else "")
        need, got = suggested_bump(published, catalog, new_ids), bump_of(release, last_release)
        order = ("patch", "minor", "major")
        if last_release and order.index(got) < order.index(need):
            log(f"WARNING: {release} is a {got} bump after {last_release}, but this change looks {need} "
                f"(docs/data_format.md, 'Versions and releases')")
    if entries:
        (stage / "CHANGELOG.md").write_text(render_changelog(entries))
    dropped = []
    if stories is not None:
        if skip_missing_stories:
            stories, dropped = drop_missing_stories(stories, {r["run_id"] for r in catalog}, log=log)
        problems += check_stories(stories, {r["run_id"] for r in catalog})
        write_stories(stories, stage)
    (stage / "README.md").write_text(dataset_card(repo, sorted(tables), catalog, entries))
    problems += check_staging(stage)
    files = sorted(p for p in stage.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    summary = {"repo": repo, "staging": str(stage), "runs": sorted(new_ids), "catalog_runs": len(catalog), "files": len(files),
               "bytes": total, "problems": problems, "pushed": False, "release": release, "tag": None}
    if stories is not None:
        summary.update(stories=len(stories), stories_dropped=[f"{st.get('title')} ({st['run_id']})" for st in dropped])
    log(f"\n{len(new_ids)} run(s) staged in {stage}: {len(files)} files, {total / 1e6:.1f} MB; catalog would list {len(catalog)} run(s)")
    for p in problems:
        log(f"  PROBLEM {p}")
    if not push:
        log("dry run: nothing uploaded (add --push to publish)")
        return summary
    if problems:
        raise SystemExit("not uploading: fix the problems above")
    deletes = []
    for r in rows:                                                      # replace each run as a unit (also its pre-catalog files)
        deletes += [f"{r['path']}/*", f"{r['path']}/**", r["raw"]]
    if prune_legacy:
        deletes += ["runs.csv"]
    api = _api()
    msg = message or ((f"{release}: " if release else "") + f"publish {len(new_ids)} run(s): " + ", ".join(sorted(new_ids))[:180])
    commit = api.upload_folder(folder_path=str(stage), repo_id=repo, repo_type="dataset", delete_patterns=deletes,
                               commit_message=msg)
    summary.update(pushed=True, commit=str(getattr(commit, "oid", commit)), url=str(getattr(commit, "commit_url", "")))
    log(f"pushed: {summary['url'] or summary['commit']}")
    if release:
        api.create_tag(repo, tag=release, repo_type="dataset", revision=summary["commit"],
                       tag_message=f"{release}: {notes}" if notes else release)
        summary["tag"] = release
        log(f"tagged {release} at {summary['commit']}: load with revision=\"{release}\"")
    else:
        log("reminder: no release tag. Releases are tagged: rerun with --release vX.Y[.Z] --notes \"...\" "
            "(docs/data_format.md, 'Versions and releases')")
    return summary


def publish_stories(stories: list[dict], repo: str, stage: Path, published: list[dict], push: bool = False,
                    message: str | None = None, skip_missing_stories: bool = False, log=print) -> dict:
    """Stage (and with push=True, upload) only stories.json, checked against the published catalog."""
    dropped = []
    if skip_missing_stories:
        stories, dropped = drop_missing_stories(stories, {r["run_id"] for r in published}, log=log)
    problems = check_stories(stories, {r["run_id"] for r in published})
    write_stories(stories, stage)
    summary = {"repo": repo, "staging": str(stage), "runs": [], "stories": len(stories), "files": 1, "problems": problems,
               "stories_dropped": [f"{st.get('title')} ({st['run_id']})" for st in dropped],
               "pushed": False}
    log(f"{len(stories)} stories staged in {stage / 'stories.json'}")
    for p in problems:
        log(f"  PROBLEM {p}")
    if not push:
        log("dry run: nothing uploaded (add --push to publish)")
        return summary
    if problems:
        raise SystemExit("not uploading: fix the problems above")
    commit = _api().upload_file(path_or_fileobj=str(stage / "stories.json"), path_in_repo="stories.json", repo_id=repo,
                                repo_type="dataset", commit_message=message or f"stories: {len(stories)}")
    summary.update(pushed=True, commit=str(getattr(commit, "oid", commit)), url=str(getattr(commit, "commit_url", commit)))
    log(f"pushed: {summary['url']}")
    return summary


# ------------------------------------------------------------------ CLI
def add_command(sub) -> None:
    p = sub.add_parser("publish", help="publish runs to a Hugging Face dataset (charter/publish.py; docs/data_format.md)")
    p.add_argument("runs", nargs="*", help="run directories, or directories holding runs")
    p.add_argument("--repo", default=DEFAULT_REPO, help=f"dataset repo (default {DEFAULT_REPO})")
    p.add_argument("--card", help="YAML/JSON card, or {run_id: card} (title, description, tags, featured, usable_rounds, validity)")
    p.add_argument("--stories", help="stories registry (site/stories.yaml) to publish as stories.json; runs are optional")
    p.add_argument("--skip-missing-stories", action="store_true",
                   help="drop (with a warning) stories whose run is not in the catalog, instead of refusing to upload")
    p.add_argument("--title"), p.add_argument("--description"), p.add_argument("--tags", help="comma-separated")
    p.add_argument("--spec", help="override the spec folder name")
    p.add_argument("--staging", help="staging directory (default charter/out/_publish/<time>)")
    p.add_argument("--reexport-all", action="store_true", help="also rebuild every published run's tables from its raw archive")
    p.add_argument("--with-prompts", action="store_true", help="include the prompts table (blobs) when the exporter supports it")
    p.add_argument("--with-viewer-json", action="store_true",
                   help="TEMPORARY: also write the story viewer's data (viewer.json) per run, until the site reads the tables")
    p.add_argument("--prune-legacy", action="store_true", help="delete pre-catalog files (runs.csv) from the dataset")
    p.add_argument("--message", help="commit message")
    p.add_argument("--push", action="store_true", help="upload (without it: stage and summarise only)")
    p.add_argument("--release", help="tag the upload commit vX.Y[.Z] and add a changelog entry (major: schema major or layout; "
                                     "minor: runs or columns added; patch: card/catalog fixes)")
    p.add_argument("--notes", help="changelog notes for --release")
    p.set_defaults(fn=cmd)


def cmd(a) -> None:
    if a.notes and not a.release:
        raise SystemExit("--notes goes with --release (the changelog entry)")
    cards = load_cards(a.card)
    flags = {k: v for k, v in (("title", a.title), ("description", a.description),
                                ("tags", [t.strip() for t in a.tags.split(",")] if a.tags else None)) if v}
    if flags:
        cards["*"] = {**cards.get("*", {}), **flags}
    s = publish(a.runs, repo=a.repo, cards=cards, push=a.push, staging=a.staging, reexport_all=a.reexport_all,
                with_prompts=a.with_prompts, spec_override=a.spec, prune_legacy=a.prune_legacy, message=a.message,
                release=a.release, notes=a.notes, with_viewer_json=a.with_viewer_json, stories=load_stories(a.stories),
                skip_missing_stories=a.skip_missing_stories)
    if s["problems"] and not a.push:
        raise SystemExit(1)
