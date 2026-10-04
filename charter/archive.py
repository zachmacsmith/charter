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


def docs(shared: Path | None = None) -> dict:
    out = {str(p.relative_to(ROOT).with_suffix("")): p for p in sorted(ROOT.rglob("*.md"))
           if not str(p.relative_to(ROOT)).startswith("codex/")}            # codex articles are held per agent (hidden.py)
    from charter import library as LB
    for name in LB.LIB:
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
    d = docs(shared)
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


def index(shared: Path | None = None, only: list | None = None, run_id: str | None = None) -> str:
    lines = []
    for d, p in docs(shared).items():
        if only is not None and d not in only and not d.startswith("shared/"):
            continue
        first = (p.read_text().splitlines()[0].lstrip("# ").strip() if p and p.read_text().strip() else d.split("/", 1)[1].replace("-", " ").title())
        lines.append(f"- {d}: {NOT_OF_THIS_TIME if foreign(shared, d, run_id) else ''}{first[:100]}")
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
    for d in docs(shared):
        if only is not None and d not in only and not d.startswith("shared/"):
            continue
        text = (_read(d, shared) or "").lower()
        score = sum(text.count(w) for w in words)
        if score:
            i = min((text.find(w) for w in words if w in text), default=0)
            scored.append((score, d, text[max(0, i - 80): i + 160].replace("\n", " ")))
    return [(d, (NOT_OF_THIS_TIME if foreign(shared, d, run_id) else "") + snip) for _, d, snip in sorted(scored, key=lambda t: -t[0])[:limit]]
