"""The story viewer: one self-contained HTML page that replays a run as a group chat (centre), per-agent message inboxes (left)
and the world as it stood at that moment, laws in force and who holds what (right).

    python -m charter view RUN_DIR            writes RUN_DIR/story.html (and opens it with --open)

The page embeds instance.json, events.jsonl, snapshots.json and ground_truth.json (the monitors' full view: forged messages,
anonymous authors and rumour truth are shown as such). Opened without embedded data, the template lets you pick a run folder.
"""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("template.html")
MARK = "/*__CHARTER_DATA__*/"


def load(run_dir) -> dict:
    d = Path(run_dir)
    read = lambda f: json.loads((d / f).read_text()) if (d / f).exists() else None
    events = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines() if l.strip()]
    return {"name": d.name, "instance": read("instance.json"), "events": events, "snapshots": read("snapshots.json") or [],
            "truth": read("ground_truth.json") or {}}


def build(run_dir, out=None) -> Path:
    """Write the story page for a run (default RUN_DIR/story.html) and return its path."""
    data = json.dumps(load(run_dir), separators=(",", ":"), default=str)
    data = data.replace("</", "<\\/")                                   # never close the <script> early
    html = TEMPLATE.read_text().replace(MARK, data, 1)
    out = Path(out) if out else Path(run_dir) / "story.html"
    out.write_text(html)
    return out
