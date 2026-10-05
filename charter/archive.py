"""The Scientists' archive. Two parts, both readable only by holders of the `archive` right (Scientists):

- the fixed archive (charter/archive/**.md): the full law library with code (generated from library.py), further laws, the
  mathematics of the world, strategies and precedents. Read-only.
- the shared archive (spec shared_archive.path/namespace): documents Scientists write themselves (write_archive). It is shared by
  every Scientist and persists between runs, so later runs inherit what earlier Scientists recorded. Addressed as "shared/<name>".
Documents are addressed by path without .md, e.g. "math/regrowth", "library/harvest-levy", "shared/silver-notes".

Several worlds can share one shared archive (also at the same time). When a Scientist reads, searches or lists a shared document
that holds anything their own world did not write, it is shown with "(not of this time)" at the start.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).parent / "archive"
AGNET = Path(__file__).resolve().parents[1]


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def shared_dir(spec: dict | None) -> Path | None:
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
OLD_CAMPS = {"math/tree-camps", "math/linear-camps", "math/modular-camps", "math/peak-camps", "math/compute-camps",
             "math/history-camps", "math/yield-functions"}
TYPED_CAMPS = {"math/camp-mechanics"}
NEEDS = {                                                               # document -> modules that must all be on
    "strategy/entry-17-jurisdictions-charters-and-secession": ("jurisdictions",),
    "strategy/entry-18-the-press-and-public-speech": ("media2",),
    "strategy/entry-19-lifespans-heirs-and-makers": ("life",),
    "strategy/entry-20-force-forts-and-assassins": ("conflict",),
    "strategy/entry-21-board-seats-and-succession": ("life",),
    "history/the-maker-who-culled-his-customers": ("life", "conflict"),
    "history/the-editor-and-the-bounty": ("media2", "jurisdictions"),
    "history/the-successor-who-waited": ("life",),
    "history/the-emptied-commonwealth": ("jurisdictions",),
}


def applies(doc: str, spec: dict | None) -> bool:
    """Whether a document describes this world (no spec: every document)."""
    if spec is None:
        return True
    typed = ((spec.get("camps") or {}).get("model") == "types")
    if doc in OLD_CAMPS and typed or doc in TYPED_CAMPS and not typed:
        return False
    return all(bool((spec.get(m) or {}).get("enabled")) for m in NEEDS.get(doc, ()))


def docs(shared: Path | None = None, gated: bool = False, spec: dict | None = None) -> dict:
    skip = set() if gated else gated_docs()                            # media2: gated documents only when asked for
    out = {str(p.relative_to(ROOT).with_suffix("")): p for p in sorted(ROOT.rglob("*.md"))
           if not str(p.relative_to(ROOT)).startswith("codex/") and str(p.relative_to(ROOT).with_suffix("")) not in skip
           and applies(str(p.relative_to(ROOT).with_suffix("")), spec)}
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
    return "shared/" + name


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
    return {"enabled": True, "path": str(shared), "docs": files,
            "hash": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]}


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
