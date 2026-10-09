"""Build the site's generated files (run from the repository root):

    python site/build.py

- site/notes/index.json  the notes list, from the front matter of site/notes/*.md (title, date, summary, draft)
- site/assets/mascots.svg  a sprite of the mascots used on the site (the README header's drawing code)

Everything else in site/ is hand-written static HTML, CSS and JS: no node, no bundler. Serve with
`python3 -m http.server 8790 --directory site`.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

def front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, m.group(2)


def build_notes() -> None:
    notes = []
    for p in sorted((SITE / "notes").glob("*.md")):
        meta, body = front_matter(p.read_text())
        words = len(re.findall(r"\w+", body))
        notes.append({"slug": p.stem, "title": meta.get("title", p.stem), "date": meta.get("date", ""),
                      "summary": meta.get("summary", ""), "draft": meta.get("draft", "false") == "true",
                      "minutes": max(1, round(words / 230))})
    notes.sort(key=lambda n: n["date"], reverse=True)
    (SITE / "notes" / "index.json").write_text(json.dumps(notes, indent=1))


def build_mascots() -> None:
    spec = importlib.util.spec_from_file_location("make_headers", ROOT / "docs" / "assets" / "make_headers.py")
    mh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mh)
    cast = [("Bjorn", "legislator"), ("Fen", "worker"), ("Soren", "scientist"), ("Dara", "worker"), ("Cyrus", "worker"),
            ("Greta", "media"), ("Kasper", "worker"), ("Ole", "scientist"), ("Zeno", "scientist"), ("Cora", "legislator"),
            ("Hal", "fixer"), ("Cleo", "board"), ("Sena", "worker"), ("Yara", "legislator"), ("Gus", "observer"), ("Asta", "board")]
    syms = []
    for name, cls in cast:
        mh.cast(name, cls)
        for mood in ("ok", "happy", "sad"):
            syms.append(mh.symbol(f"{name}-{mood}", name, cls, mh.HUE[name], mood))
    svg = '<svg xmlns="http://www.w3.org/2000/svg" style="display:none">' + "".join(syms) + "</svg>"
    (SITE / "assets" / "mascots.svg").write_text(svg)


if __name__ == "__main__":
    build_notes()
    build_mascots()
    print("built site/notes/index.json, site/assets/mascots.svg")
