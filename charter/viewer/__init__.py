"""The story viewer: one self-contained HTML page that replays a run as a group chat (centre), each agent's dossier (goals,
personality, rights, wealth, a diary of reasoning, notes and actions) and message inboxes (left), and the world as it stood at
that moment, laws in force and who holds what (right). Every agent is drawn as a mascot in its own colour; hovering a law shows
its intent, how it passed and what it hooks into. The Story / Society switch (or M) swaps the page for a map of the whole
world at the same moment, which can also play the run; switching back scrolls the story to wherever the map got to.

    python -m charter view RUN_DIR            writes RUN_DIR/story.html (and opens it with --open)

The page embeds instance.json, events.jsonl, snapshots.json, ground_truth.json, score.json and reasoning.jsonl without the
prompts (the monitors' full view: forged messages, anonymous authors, rumour truth and final goal scores are all shown).
Opened without embedded data, the template lets you pick a run folder.
"""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("template.html")
MARK = "/*__CHARTER_DATA__*/"


REASONING_KEYS = ("round", "position", "agent", "phase", "reasoning", "stated_reasoning", "notes", "error")


def _reasoning(d: Path) -> list:
    """Each turn's private reasoning and notes, without the prompts (most of the file's size)."""
    p = d / "reasoning.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:                                              # empty, or a line still being written by a live run
            continue
        out.append({k: r[k] for k in REASONING_KEYS if r.get(k) not in (None, "")})
    return out


def load(run_dir) -> dict:
    d = Path(run_dir)
    read = lambda f: json.loads((d / f).read_text()) if (d / f).exists() else None
    events = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines() if l.strip()]
    return {"name": d.name, "instance": read("instance.json"), "events": events, "snapshots": read("snapshots.json") or [],
            "truth": read("ground_truth.json") or {}, "reasoning": _reasoning(d), "score": read("score.json") or {}}


def build(run_dir, out=None) -> Path:
    """Write the story page for a run (default RUN_DIR/story.html) and return its path."""
    data = json.dumps(load(run_dir), separators=(",", ":"), default=str)
    data = data.replace("</", "<\\/")                                   # never close the <script> early
    html = TEMPLATE.read_text().replace(MARK, data, 1)
    out = Path(out) if out else Path(run_dir) / "story.html"
    out.write_text(html)
    return out
