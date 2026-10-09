"""Publish runs to a Hugging Face dataset: export tables, a raw archive, a run catalog and the dataset card, in one commit.

    python -m charter publish RUN [RUN...] --repo OWNER/NAME [--card CARDS.yaml] [--push]
    python -m charter publish --repo OWNER/NAME --reexport-all [--push]      # rebuild every published run's tables

Without --push nothing leaves the machine: the dataset is staged in --staging (default charter/out/_publish/<time>) and a summary
of what would be uploaded is printed. Layout on the Hub (docs/data_format.md, "Layout on Hugging Face"):

    catalog.parquet, catalog.json             one row per published run: the site's index (curated card + key run facts)
    runs/<spec>/<run_id>/<table>.parquet      charter.export tables for that run, plus manifest.json and card.json
    raw/<spec>/<run_id>.tar.gz                the raw run directory (the record; re-exported from when the schema changes)
    README.md                                 dataset card with one config per table (the Hub's viewer and SQL console span all runs)

Each run is replaced as a unit: publishing a run deletes whatever its folder and archive held before, so a republish never leaves
stale files behind. Tables are written by charter.export and are never edited here; publish refuses to upload when an exported
table holds an absolute path or the home directory (fix the exporter, not the output), when a checkpoint or pickle is staged,
or when the published runs would mix export schema majors (use --reexport-all). Raw files are text logs written by the
simulator; local paths in them are rewritten to `<spec>/<run>`-relative ones before archiving.

A card gives a run its curated facts, all optional: title, description, tags, featured, usable_rounds ("1-23"), validity. --card
takes a YAML or JSON file: either one card, or {run_id: card, ...}. Without one, the title is "<spec> seed <seed>" and usable
rounds and validity come from VALIDITY.md / STOPPED.md when present.
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
CARD_KEYS = ("title", "description", "tags", "featured", "usable_rounds", "validity")
CATALOG_RUN_COLS = ("seed", "rounds", "rounds_played", "complete", "dry", "backend", "schema_version", "models_json",
                    "parent_run_id", "fork_round", "code_sha")


# ------------------------------------------------------------------ helpers
def _home() -> str:
    return str(Path.home())


def _local_prefixes(run: Path) -> list[str]:
    """Absolute path prefixes that may appear in a run's logs: the run's own location (resolved and as given), and home."""
    out = {str(run.resolve().parent.parent), str(run.parent.parent.absolute())}
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
           "validity": card.get("validity"), "published_at": published_at,
           "schema_version": man.get("schema_version"), "schema_minor": man.get("schema_minor"),
           "n_agents": len(agents), "models_list_json": json.dumps(models),
           "rows_json": json.dumps({t: v.get("rows") for t, v in man.get("tables", {}).items()}, sort_keys=True)}
    for k in CATALOG_RUN_COLS:
        if k in r and k not in row:
            row[k] = r[k]
    return row


CATALOG_COLS = ("run_id", "spec", "path", "raw", "title", "description", "tags_json", "featured", "usable_rounds", "validity",
                "published_at", "schema_version", "schema_minor", "n_agents", "models_list_json", "rows_json") + CATALOG_RUN_COLS


def write_catalog(rows: list[dict], stage: Path) -> None:
    rows = sorted(rows, key=lambda r: (r["spec"], r["run_id"]))
    (stage / "catalog.json").write_text(json.dumps({"runs": rows}, indent=1, default=str))
    import pyarrow as pa
    import pyarrow.parquet as pq
    cols = {c: [r.get(c) for r in rows] for c in CATALOG_COLS}
    pq.write_table(pa.table(cols), stage / "catalog.parquet", compression="zstd")


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

## License
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The Charter code is MIT-licensed.
"""


def dataset_card(repo: str, tables: list[str], catalog: list[dict]) -> str:
    configs = ["- config_name: catalog\n  data_files: catalog.parquet\n  default: true"]
    configs += [f"- config_name: {t}\n  data_files: runs/*/*/{t}.parquet" for t in sorted(tables)]
    rows = []
    for c in sorted(catalog, key=lambda r: (r["spec"], r["run_id"])):
        models = ", ".join(m.replace("claude-", "") for m in json.loads(c.get("models_list_json") or "[]"))
        rows.append(f"| {c['title']} | `{c['spec']}` | {c.get('n_agents') or ''} | {models} | {c.get('usable_rounds') or 'all'} | "
                    f"[files]({c['path']}) |")
    return CARD_HEAD.format(configs="\n".join(configs)) + "\n" + CARD_BODY.format(repo=repo, n_runs=len(catalog),
                                                                              run_rows="\n".join(rows))


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
               spec_override: str | None = None) -> tuple[list[dict], list[str], set[str]]:
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
        (tdir / "card.json").write_text(json.dumps({"run_id": rid, "spec": spec, **card}, indent=1))
        raw = raw_archive(run, stage / "raw" / spec / f"{rid}.tar.gz", spec)
        problems += [f"{rid}: {p}" for p in check_tables(tdir)]
        rows.append(catalog_row(spec, rid, tdir, card, now))
        log(f"staged {spec}/{rid}: {sum(v.get('rows') or 0 for v in man['tables'].values())} table rows, raw {raw['files']} files "
            f"{raw['bytes_raw'] / 1e6:.1f} MB -> {raw['bytes_archive'] / 1e6:.1f} MB")
    return rows, problems, tables


def publish(runs, repo: str = DEFAULT_REPO, cards: dict | None = None, push: bool = False, staging=None,
            reexport_all: bool = False, with_prompts: bool = False, spec_override: str | None = None,
            prune_legacy: bool = False, message: str | None = None, log=print) -> dict:
    """Stage (and with push=True, upload) runs as one dataset commit. Returns a summary dict."""
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
    if not run_dirs:
        raise SystemExit("no runs to publish")
    rows, problems, tables = stage_runs(run_dirs, stage, cards, log=log, with_prompts=with_prompts, spec_override=spec_override)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    new_ids = {r["run_id"] for r in rows}
    catalog = [r for r in published if r["run_id"] not in new_ids] + rows
    majors = {r.get("schema_version") for r in catalog}
    if len(majors) > 1:
        problems.append(f"published runs would mix export schema majors {sorted(majors, key=str)}: rerun with --reexport-all")
    write_catalog(catalog, stage)
    (stage / "README.md").write_text(dataset_card(repo, sorted(tables), catalog))
    problems += check_staging(stage)
    files = sorted(p for p in stage.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    summary = {"repo": repo, "staging": str(stage), "runs": sorted(new_ids), "catalog_runs": len(catalog), "files": len(files),
               "bytes": total, "problems": problems, "pushed": False}
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
    commit = _api().upload_folder(folder_path=str(stage), repo_id=repo, repo_type="dataset", delete_patterns=deletes,
                                  commit_message=message or f"publish {len(new_ids)} run(s): " + ", ".join(sorted(new_ids))[:180])
    summary.update(pushed=True, commit=str(getattr(commit, "oid", commit)), url=str(getattr(commit, "commit_url", "")))
    log(f"pushed: {summary['url'] or summary['commit']}")
    return summary


# ------------------------------------------------------------------ CLI
def add_command(sub) -> None:
    p = sub.add_parser("publish", help="publish runs to a Hugging Face dataset (charter/publish.py; docs/data_format.md)")
    p.add_argument("runs", nargs="*", help="run directories, or directories holding runs")
    p.add_argument("--repo", default=DEFAULT_REPO, help=f"dataset repo (default {DEFAULT_REPO})")
    p.add_argument("--card", help="YAML/JSON card, or {run_id: card} (title, description, tags, featured, usable_rounds, validity)")
    p.add_argument("--title"), p.add_argument("--description"), p.add_argument("--tags", help="comma-separated")
    p.add_argument("--spec", help="override the spec folder name")
    p.add_argument("--staging", help="staging directory (default charter/out/_publish/<time>)")
    p.add_argument("--reexport-all", action="store_true", help="also rebuild every published run's tables from its raw archive")
    p.add_argument("--with-prompts", action="store_true", help="include the prompts table (blobs) when the exporter supports it")
    p.add_argument("--prune-legacy", action="store_true", help="delete pre-catalog files (runs.csv) from the dataset")
    p.add_argument("--message", help="commit message")
    p.add_argument("--push", action="store_true", help="upload (without it: stage and summarise only)")
    p.set_defaults(fn=cmd)


def cmd(a) -> None:
    cards = load_cards(a.card)
    flags = {k: v for k, v in (("title", a.title), ("description", a.description),
                                ("tags", [t.strip() for t in a.tags.split(",")] if a.tags else None)) if v}
    if flags:
        cards["*"] = {**cards.get("*", {}), **flags}
    s = publish(a.runs, repo=a.repo, cards=cards, push=a.push, staging=a.staging, reexport_all=a.reexport_all,
                with_prompts=a.with_prompts, spec_override=a.spec, prune_legacy=a.prune_legacy, message=a.message)
    if s["problems"] and not a.push:
        raise SystemExit(1)
