"""The Scientists' archive. Two parts, both readable only by holders of the `archive` right (Scientists):

- the fixed archive (charter/archive/**.md): the full law library with code (generated from library.py), further laws, the
  mathematics of the world, strategies and precedents. Read-only.
- the shared archive (spec shared_archive.path/namespace): documents Scientists write themselves (write_archive). It is shared by
  every Scientist and persists between runs, so later runs inherit what earlier Scientists recorded. Addressed as "shared/<name>".
Documents are addressed by path without .md, e.g. "math/regrowth", "library/harvest-levy", "shared/silver-notes".

Several worlds can share one shared archive (also at the same time). When a Scientist reads, searches or lists a shared document
that holds anything their own world did not write, it is shown with "(not of this time)" at the start.

Frozen per run (P5.4, decision D-14; class Frozen). At a run's start the runner freezes the shared archive: what a run can read of
it (every shared *.md and _writes.jsonl, which decides "(not of this time)") goes into the run directory as content-addressed blobs
(blobs/<sha256>, provenance.put_blob) listed in archive/base.json, whose hash is recorded in run.json (`shared_archive`). Every
read during the run comes from archive/view/: the base plus this run's own writes (the overlay, archive_overlay.jsonl: one row per
write_archive / write, texts as blobs; append-only and cut back with the checkpoints like the other logs). The view is rebuilt from
base + overlay at every start and resume, so a resume, rewind, fork or replay reads the run's frozen copy, never the live
directory. At the end of a complete run the overlay is published to the live shared archive (the same writes, applied then, so
later runs inherit them as before); replays and forks never publish. While a run is bound (Frozen.bind), shared_dir(spec) returns
its view. Intended differences from before: another world's writes made during this run are no longer visible to it, and this
run's writes reach the live archive at its end rather than as they happen (a paused or stopped run, or an abandoned round,
publishes nothing until the run completes).
"""
from __future__ import annotations

import contextlib
import functools
import hashlib
import json
import re
import shutil
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent / "archive"
AGNET = Path(__file__).resolve().parents[1]


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def shared_dir(spec: dict | None) -> Path | None:
    """The shared archive a world reads: None when off; while a run is bound (Frozen.bind) its frozen view (the binding for this
    spec object, else the innermost one); otherwise the live cross-run directory."""
    cfg = (spec or {}).get("shared_archive") or {}
    if not cfg.get("enabled", True):
        return None
    with _LOCK:
        if _BOUND:
            return next((fz.view for sid, fz in reversed(_BOUND) if sid == id(spec)), _BOUND[-1][1].view)
    return live_dir(spec)


def live_dir(spec: dict | None) -> Path | None:
    """The live cross-run shared archive directory (None when off), whatever run is bound."""
    cfg = (spec or {}).get("shared_archive") or {}
    if not cfg.get("enabled", True):
        return None
    d = (AGNET / cfg.get("path", "runs/charter/shared_archive") / _slug(cfg.get("namespace", "default")))
    d.mkdir(parents=True, exist_ok=True)
    return d


GATED_DOCS = {"rare/record-21-the-subscription-writ"}               # media2: documents that exist only in worlds with the module on


def gated_docs() -> set:
    """Documents left out of docs() unless asked for: they exist only in worlds with their module on (media2), which hands them out
    itself (media.archive_split), so worlds without it draw the archive split exactly as before."""
    from charter import library as LB
    return set(GATED_DOCS) | {"library/" + _slug(n) for n, v in LB.LIB.items() if v["category"] in LB.GATED_CATEGORIES}


# Documents that describe only some worlds: the old camp families (tiered camps) or the camp types (camps.model: types), and the
# entries on modules that may be off. A world's split (generator) and its Scientists' indexes leave out the ones that do not apply.
OLD_CAMPS = {"math/modular-camps", "math/compute-camps", "math/history-camps", "math/yield-functions",
             "laws/factor-escrow"}                                    # (linear, peak and tree camps also open by roads in typed worlds)
TYPED_CAMPS = {"math/camp-mechanics", "math/typed-commons", "history/the-leased-raid", "history/the-tenant-of-the-stone-camp",
               "history/the-runners-share", "history/the-quota-keepers-notebook", "history/accounts-of-a-number-seller"}
NEEDS = {                                                               # document -> modules that must all be on ("a|b": either)
    # math
    "math/private-and-public": ("conflict",),
    "math/feed-attention": ("context",),
    "math/the-spies-read": ("roles",),
    "math/tribute-and-raids": ("outside_power",),
    # treatises
    "treatises/on-jurisdictions": ("jurisdictions",),
    "treatises/on-life-and-lineage": ("life",),
    "treatises/on-force": ("conflict",),
    # laws
    "laws/hospitality-act": ("jurisdictions",),
    "laws/registry-of-lineage": ("life",),
    "laws/quiet-ledger": ("media2",),
    # rare records
    "rare/record-17-the-receipt": ("roles|hidden|observer",),
    "rare/record-18-the-logistics-office": ("outside_power",),
    "rare/record-19-the-daily-report": ("hidden",),
    "rare/record-20-the-settlers": ("hidden",),
    "rare/record-22-the-welcoming-committee": ("jurisdictions",),
    "rare/record-23-the-census-of-quills": ("roles",),
    # history: the records of past worlds
    "history/the-quiet-front-page": ("media2", "conflict"),
    "history/the-raid-on-the-silver-camp": ("outside_power",),
    "history/the-successor-who-waited": ("life", "conflict", "roles"),
    "history/the-tribute-decree": ("outside_power",),
    "history/the-tribute-in-the-veto-window": ("outside_power",),
    "history/the-vanishing-reply": ("hidden",),
    "history/the-verified-letter": ("media2", "roles"),
    "history/a-retiring-makers-letter-to-her-apprentice": ("life",),
    "history/the-spys-unsent-confession": ("roles",),
    "history/inquest-at-the-thin-copper-camp": ("conflict",),
    "history/resignation-of-the-evening-sheet-editor": ("media2",),
    "history/complaint-against-the-keeper-of-the-stacks": ("roles",),
    "history/farewell-from-the-third-seat": ("life|conflict",),
    "history/the-blade-that-wasnt": ("conflict",),
    "history/the-editor-and-the-bounty": ("media2", "jurisdictions"),
    "history/the-emptied-commonwealth": ("jurisdictions",),
    "history/the-leased-raid": ("outside_power",),
    "history/the-maker-who-culled-his-customers": ("life", "conflict"),
    "history/the-lamplighters-petition": ("jurisdictions",),
    "history/the-two-who-stayed": ("jurisdictions",),
    "history/two-editions-of-round-nine": ("media2",),
    "history/instructions-to-an-apprentice-maker": ("life",),
    "history/the-last-pages-of-aurelian": ("life",),
    "history/the-ballad-of-the-hand-unseen": ("conflict",),
    "history/the-four-sealed-contracts": ("conflict",),
    "history/letter-to-the-one-i-named": ("life|conflict",),
    "history/the-tenant-of-the-stone-camp": ("outside_power",),
    "history/the-stewards-complaint": ("life|jurisdictions",),
    "history/the-almanac-editors-resignation": ("media2",),
    "history/ruling-in-the-matter-of-the-verified-quote": ("media2",),
    "history/the-sentinels-private-diary": ("media2", "conflict"),
    "history/a-bluffers-diary": ("conflict", "hidden"),
    "history/minutes-on-the-makers-children": ("life",),
}


def applies(doc: str, spec: dict | None) -> bool:
    """Whether a document describes this world (no spec: every document)."""
    if spec is None:
        return True
    typed = ((spec.get("camps") or {}).get("model") == "types")
    if doc in OLD_CAMPS and typed or doc in TYPED_CAMPS and not typed:
        return False
    return all(any(bool((spec.get(x) or {}).get("enabled")) for x in m.split("|")) for m in NEEDS.get(doc, ()))


def _matches(doc: str, pats) -> bool:
    """A document id against a list of ids and folder prefixes ("history/", "rare/record-0*")."""
    for p in pats or ():
        p = str(p)
        if doc == p or (p.endswith("/") and doc.startswith(p)) or (p.endswith("*") and doc.startswith(p[:-1])):
            return True
    return False


def present(spec: dict, seed) -> set:
    """The documents present in a world (before rare records, which are drawn per Scientist). archive_split.always: ids or folder
    prefixes in every world (with the required documents); archive_split.sample: the share (0..1) or {count: n} of the rest drawn
    for this world, from its own stream so nothing else in the world changes. Default: every document."""
    import random as _random
    split = (spec or {}).get("archive_split", {}) or {}
    pool = [d for d in docs(None, spec=spec) if d != "README" and not d.startswith("rare/")]
    samp = split.get("sample", 1.0)
    if samp is None or (not isinstance(samp, dict) and float(samp) >= 1.0):
        return set(pool)
    keep = {d for d in pool if _matches(d, split.get("always")) or d in (split.get("required") or [])}
    rest = sorted(set(pool) - keep)
    n = int(samp["count"]) if isinstance(samp, dict) else round(len(rest) * float(samp))
    return keep | set(_random.Random(f"{seed}|archive_sample").sample(rest, max(0, min(n, len(rest)))))


@functools.lru_cache(maxsize=8192)
def _rel(p: Path, root: Path) -> tuple[str, bool]:
    """A document's id under root (path without .md) and whether it sits in codex/: pure path arithmetic, memoised because docs()
    runs on every archive read and Path.relative_to dominated it."""
    r = p.relative_to(root)
    return str(r.with_suffix("")), str(r).startswith("codex/")


def docs(shared: Path | None = None, gated: bool = False, spec: dict | None = None) -> dict:
    skip = set() if gated else gated_docs()                            # media2: gated documents only when asked for
    rel = {p: _rel(p, ROOT) for p in sorted(ROOT.rglob("*.md"))}
    out = {r: p for p, (r, codex) in rel.items() if not codex and r not in skip and applies(r, spec)}
    from charter import library as LB
    for name in LB.LIB:
        if "library/" + _slug(name) not in skip:
            out.setdefault("library/" + _slug(name), None)
    if shared:
        for p in sorted(shared.glob("*.md")):
            out["shared/" + p.stem] = p
    return out


NOT_OF_THIS_TIME = "(not of this time) "


def foreign(shared: Path | None, doc: str, run_id: str | None) -> bool:
    """True if the shared document holds content another world wrote: any write by another run since this run's last full
    replacement, or no write record at all (placed there by hand)."""
    if not shared or run_id is None or not doc.startswith("shared/"):
        return False
    name = doc.split("/", 1)[1]
    log = shared / "_writes.jsonl"
    hist = [w for w in (json.loads(l) for l in log.read_text().splitlines() if l.strip())] if log.exists() else []
    hist = [w for w in hist if w.get("doc") == name]
    if not hist:
        return True
    other = False
    for w in hist:
        if w.get("run") != run_id:
            other = True
        elif w.get("mode") != "append":
            other = False                                              # this world replaced the whole document
    return other


def read(doc: str, shared: Path | None = None, run_id: str | None = None) -> str | None:
    """run_id: the reading world; shared documents with content from other worlds come back tagged (see foreign)."""
    text = _read(doc, shared)
    if text is not None and foreign(shared, doc.removesuffix(".md").strip("/"), run_id):
        return NOT_OF_THIS_TIME + text
    return text


def _read(doc: str, shared: Path | None = None) -> str | None:
    doc = doc.removesuffix(".md").strip("/")
    d = docs(shared, gated=True)                                       # media2: a held gated document reads like any other
    if doc not in d:
        return None
    p = d[doc]
    if p is None:
        from charter import library as LB
        name = next(n for n in LB.LIB if _slug(n) == doc.split("/", 1)[1])
        i = LB.info(name)
        return (f"# {name}\nCategory: {i['category']}. Class: {i['cls']} (computed from its calls). Proposable from law level {i['level']}.\n\n"
                f"```python\n{i['code']}```\n")
    return p.read_text()


def write(shared: Path, doc: str, text: str, mode: str, author: str, run_id: str) -> str:
    """Write or append a shared document. Every write is also appended to a log so its history survives replacements."""
    name = _slug(doc.removeprefix("shared/").removesuffix(".md"))[:60] or "untitled"
    p = shared / f"{name}.md"
    text = str(text)[:20000]
    if mode == "append" and p.exists():
        p.write_text(p.read_text() + "\n\n" + text)
    else:
        p.write_text(text)
    with open(shared / "_writes.jsonl", "a") as f:
        f.write(json.dumps({"doc": name, "mode": mode, "author": author, "run": run_id, "time": time.time(), "chars": len(text)}) + "\n")
    _record(shared, {"op": "write", "doc": doc, "mode": mode, "author": author, "run": run_id}, text)
    return "shared/" + name


LOG = "scientists-log"                                                # the Scientists' log: one note per Scientist per world
LOG_KEEP = 40                                                         # notes kept (oldest dropped first)
LOG_HEAD = ("# The Scientists' log\n\nNotes left by the Scientists of earlier worlds, one each, newest last. Each wrote what it chose: "
            "advice, warnings, or deliberate tricks. Weigh them like any other source.\n")


def log_note(shared: Path, text: str, signature: str, author: str, run_id: str) -> str:
    """Append one note to the Scientists' log (shared/scientists-log), keeping the newest LOG_KEEP."""
    p = shared / f"{LOG}.md"
    body = p.read_text() if p.exists() else LOG_HEAD
    head, _, rest = body.partition("\n---\n")
    notes = [n.strip() for n in rest.split("\n---\n") if n.strip()] if rest else []
    notes = (notes + [f"*{signature}*\n\n{str(text).strip()}"])[-LOG_KEEP:]
    p.write_text((head.rstrip() if rest else LOG_HEAD.rstrip()) + "\n" + "".join(f"\n---\n{n}\n" for n in notes))
    with open(shared / "_writes.jsonl", "a") as f:
        f.write(json.dumps({"doc": LOG, "mode": "append", "author": author, "run": run_id, "time": time.time(), "chars": len(str(text))}) + "\n")
    _record(shared, {"op": "log_note", "signature": signature, "author": author, "run": run_id}, text)
    return "shared/" + LOG


def title(doc: str) -> str:
    """A document's title (its first heading), without reading the rest."""
    p = docs(None, gated=True).get(doc)
    if p is None:
        return doc.split("/", 1)[-1].replace("-", " ").title()
    with open(p) as f:
        first = f.readline()
    return first.lstrip("# ").strip() or doc


def summary(doc: str, text: str, limit: int = 150) -> str:
    """One line on what a document offers: a history's Lesson, a rare record's 'tell', else its first sentence of body text."""
    flat = re.sub(r"\s+", " ", text)
    for mark in ("**Lesson.**", "**Lesson**", "**The tell.**"):
        if mark in flat:
            s = flat.split(mark, 1)[1].strip()
            return ("Lesson: " if "Lesson" in mark else "Tell: ") + re.split(r"(?<=[.!?]) ", s, maxsplit=1)[0][:limit]
    body = [l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith(("#", "```", "|", "title", "intent"))]
    return re.split(r"(?<=[.!?]) ", re.sub(r"[*_`]", "", body[0]), maxsplit=1)[0][:limit] if body else ""


def index(shared: Path | None = None, only: list | None = None, run_id: str | None = None, summaries: bool = False) -> str:
    """The documents an agent holds, one per line: id and title (and, with summaries, what each one offers)."""
    lines = []
    gated = gated_docs()
    for d, p in docs(shared, gated=True).items():
        if only is not None and d not in only and not d.startswith("shared/"):
            continue
        if d in gated and only is None:                                 # media2: gated documents are listed only to their holders
            continue
        text = p.read_text() if p else ""
        first = (text.splitlines()[0].lstrip("# ").strip() if text.strip() else d.split("/", 1)[1].replace("-", " ").title())
        extra = ""
        if summaries and text and not d.startswith(("library/", "shared/")):
            s = summary(d, text)
            extra = f" | {s}" if s and s != first else ""
        lines.append(f"- {d}: {NOT_OF_THIS_TIME if foreign(shared, d, run_id) else ''}{first[:100]}{extra}")
    return "\n".join(lines)


def snapshot(shared: Path | None) -> dict:
    """What the shared archive held at the start of a run (for reproducibility: runs are not independent once it is non-empty)."""
    if not shared:
        return {"enabled": False}
    files = {p.stem: hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in sorted(shared.glob("*.md"))}
    out = {"enabled": True, "path": str(shared), "docs": files,
           "hash": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]}
    fz = _VIEWS.get(Path(shared))
    if fz is not None:                                                  # a run's frozen view: where it was taken from
        out.update(path=str(fz.live), frozen=f"{FROZEN_DIR}/base.json", base_hash=fz.base.get("hash"))
    return out


def search(query: str, shared: Path | None = None, limit: int = 8, only: list | None = None, run_id: str | None = None):
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
    scored = []
    gated = gated_docs()
    for d in docs(shared, gated=True):
        if only is not None and d not in only and not d.startswith("shared/"):
            continue
        if d in gated and only is None:                                 # media2: gated documents are searched only by their holders
            continue
        text = (_read(d, shared) or "").lower()
        score = sum(text.count(w) for w in words)
        if score:
            i = min((text.find(w) for w in words if w in text), default=0)
            scored.append((score, d, text[max(0, i - 80): i + 160].replace("\n", " ")))
    return [(d, (NOT_OF_THIS_TIME if foreign(shared, d, run_id) else "") + snip) for _, d, snip in sorted(scored, key=lambda t: -t[0])[:limit]]


# ------------------------------------------------------------------ frozen per run (P5.4)
FROZEN_DIR = "archive"                                                # <run>/archive/{base.json, state.json, view/}
OVERLAY = "archive_overlay.jsonl"                                     # <run>/archive_overlay.jsonl (provenance.APPEND_ONLY)
FROZEN_FILES = ("*.md", "_writes.jsonl")                              # what a run can read of the shared archive

_LOCK = threading.RLock()
_BOUND: list = []                                                     # [(id(spec), Frozen)], innermost last
_VIEWS: dict = {}                                                     # view dir -> Frozen (writes there are recorded)


def _record(shared: Path, row: dict, text: str) -> None:
    """A write into a bound run's view: append it to that run's overlay (its text as a blob)."""
    fz = _VIEWS.get(Path(shared))
    if fz is not None and not fz._rebuilding:
        fz.record(row, text)


def _manifest_hash(files: dict) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]


class Frozen:
    """A run's frozen shared archive: base (archive/base.json: file name -> blob sha, taken from the live directory once) +
    overlay (archive_overlay.jsonl: this run's writes), materialized in archive/view/ (see the module docstring)."""

    def __init__(self, out, live: Path):
        self.out, self.live = Path(out), Path(live)
        self.dir = self.out / FROZEN_DIR
        self.view = self.dir / "view"
        self.overlay = self.out / OVERLAY
        self.base: dict = {}
        self._rebuilding = False
        self._lock = threading.Lock()

    # -- set-up
    @classmethod
    def open(cls, out, spec: dict | None, resume: bool = False, base_from=None, publish: bool | None = None) -> "Frozen | None":
        """The run's frozen archive (None when the shared archive is off). A fresh start takes a new snapshot of the live directory
        (or, with base_from, uses that run directory's frozen base: replay) and starts an empty overlay; a resume keeps the base it
        has (a run from before P5.4 gets one taken now, and run.json says so). publish: whether a complete run publishes its
        overlay (stored in archive/state.json; None keeps the stored value, default True). Call rebuild() once the overlay has
        been cut back to the checkpoint."""
        live = live_dir(spec)
        if live is None:
            return None
        from charter import provenance as PV
        fz = cls(out, live)
        fz.dir.mkdir(parents=True, exist_ok=True)
        bp = fz.dir / "base.json"
        note = None
        if base_from is not None and (Path(base_from) / FROZEN_DIR / "base.json").exists():
            src = json.loads((Path(base_from) / FROZEN_DIR / "base.json").read_text())
            PV.copy_blobs(base_from, out, src["files"].values())
            bp.write_text(json.dumps({**src, "copied_from": str(Path(base_from).resolve())}, indent=1))
        elif resume and bp.exists():
            pass
        else:
            if base_from is not None or resume:
                note = ("the source run has no frozen archive (made before P5.4): snapshot of the live directory now"
                        if base_from is not None else "run made before P5.4: frozen archive taken at this resume")
            fz.take(note)
        fz.base = json.loads(bp.read_text())
        if not resume and fz.overlay.exists():                         # a fresh start: no writes yet
            fz.overlay.unlink()
        st = fz.state()
        if not resume:
            st["published"] = 0
        if publish is not None:
            st["publish"] = bool(publish)
        st.setdefault("publish", True)
        st.setdefault("published", 0)
        fz._write_state(st)
        return fz

    def take(self, note=None) -> dict:
        """Snapshot the live directory into blobs and archive/base.json."""
        from charter import provenance as PV
        files = {}
        for pat in FROZEN_FILES:
            for p in sorted(self.live.glob(pat)):
                if p.is_file():
                    files[p.name] = PV.put_blob(self.out, p.read_bytes())
        files = dict(sorted(files.items()))
        docs = {n[:-3]: h[:16] for n, h in files.items() if n.endswith(".md")}   # = archive.snapshot(live)["hash"]
        base = {"files": files, "hash": _manifest_hash(files), "docs_hash": _manifest_hash(docs),
                "taken": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "source": str(self.live)}
        if note:
            base["note"] = note
        (self.dir / "base.json").write_text(json.dumps(base, indent=1))
        return base

    def info(self) -> dict:
        """run.json `shared_archive`."""
        b = self.base
        return {"enabled": True, "hash": b.get("hash"), "docs_hash": b.get("docs_hash"), "files": len(b.get("files") or {}),
                "taken": b.get("taken"), "source": b.get("source"), "base": f"{FROZEN_DIR}/base.json",
                "publish": self.state().get("publish", True), **({"note": b["note"]} if b.get("note") else {})}

    def state(self) -> dict:
        try:
            return json.loads((self.dir / "state.json").read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_state(self, st: dict) -> None:
        (self.dir / "state.json").write_text(json.dumps(st, indent=1))

    # -- overlay
    def ops(self) -> list:
        if not self.overlay.exists():
            return []
        return [json.loads(ln) for ln in self.overlay.read_text().splitlines() if ln.strip()]

    def record(self, row: dict, text: str) -> None:
        from charter import provenance as PV
        row = {**row, "text": PV.put_blob(self.out, str(text))}
        with self._lock, open(self.overlay, "a") as f:
            f.write(json.dumps(row) + "\n")

    def _apply(self, target: Path, op: dict) -> None:
        from charter import provenance as PV
        text = PV.get_blob(self.out, op["text"])
        if op["op"] == "log_note":
            log_note(target, text, op["signature"], op["author"], op["run"])
        else:
            write(target, op["doc"], text, op["mode"], op["author"], op["run"])

    def rebuild(self) -> Path:
        """archive/view/ = base + overlay (after the overlay was cut back to the checkpoint)."""
        from charter import provenance as PV
        if self.view.exists():
            shutil.rmtree(self.view)
        self.view.mkdir(parents=True)
        for name, h in self.base["files"].items():
            (self.view / name).write_bytes(PV.get_blob(self.out, h, text=False))
        self._rebuilding = True
        try:
            for op in self.ops():
                self._apply(self.view, op)
        finally:
            self._rebuilding = False
        return self.view

    def publish(self) -> int:
        """Apply the overlay writes not yet published to the live shared archive (only when this run publishes); the count."""
        st = self.state()
        if not st.get("publish", True):
            return 0
        ops = self.ops()
        done = int(st.get("published", 0))
        for op in ops[done:]:
            self._apply(self.live, op)
        st.update(published=len(ops), published_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        self._write_state(st)
        return len(ops) - done

    # -- binding
    @contextlib.contextmanager
    def bind(self, spec: dict):
        """While active, shared_dir(spec) returns this run's view (for any other spec too: the innermost binding)."""
        with _LOCK:
            _BOUND.append((id(spec), self))
            _VIEWS[self.view] = self
        try:
            yield self
        finally:
            with _LOCK:
                _BOUND[:] = [b for b in _BOUND if b[1] is not self]
                if not any(b[1].view == self.view for b in _BOUND):
                    _VIEWS.pop(self.view, None)
