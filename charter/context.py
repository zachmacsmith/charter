"""Context and memory (spec "Context and memory"; flag `context.enabled`, off by default).

With the module on, every turn is a fresh model call built from fixed layers, each with its own token budget; nothing accumulates:

  core        (system prompt, cached) short rules, identity, class, roles, goal, personality, action names, manual index   2,500
  state       round, turn order, holdings, rights, jurisdiction, open ballots, lifespan left, memory used                  800
  feed        what it can see that changed since its last turn, trimmed by priority                                      3,000
  recent      its own last 3 turns (actions and results), verbatim                                                       1,000
  scratchpad  its scratchpad (replaces the old free-text notes field)                                                    2,000
  media       latest edition of each outlet it reads (media.editions_for)                                              4 x 600
  pinned      files it keeps in view (pin slots: 0 by default, at most 2)                                             2 x 1,000
  lookups     text fetched this turn (and paid lookups from last turn)                                                3 x 1,000

Sizes use the deterministic `tokens()` (len // 4). Trimming is deterministic: the feed keeps items by priority (events, results of
its own actions, DMs to it, posts mentioning it, official announcements, other posts newest first) and turns the rest into counts
and pointers ("(14 older posts not shown: search_board)").

A turn: the agent may list up to `free_lookups` lookups in its reply's "lookups" field (leaving "actions" empty); the runner then
fetches them and asks again with the text in the Lookups layer, and that second reply is the turn. Lookups used as actions cost an
action each; their text arrives in the next turn's Lookups layer. Every call's layer sizes and what was trimmed are written to
reasoning.jsonl (`context`), and lookups as rows with phase `lookup`.

The core prompt and the manual are layers of charter.sections ("core": the rows at the end of this module; "manual": manual.py's
rows plus the sections modules register with `@sections.section(..., after=...)`). The manual is generated per agent; only its
section titles are in the core prompt. Files and the scratchpad live in k.w (`files`, `file_space`, `pin_slots`, `scratchpad`); runner-side memory
(recent turns, manual titles seen, reads, fetched lookups, layer records) lives in k.w["context"].
"""
from __future__ import annotations

import copy
import importlib
import json
import random
import re
import zlib

from charter import features as FT                                    # the one enabled check (Feature.on)
from charter import eventtypes as ET                                  # the event-type registry: board, recent, feed priorities

DEFAULTS = {
    "enabled": False,
    "budgets": {"core": 2500, "state": 800, "feed": 3000, "recent": 1000, "scratchpad": 2000, "media": 600, "pinned": 1000,
                "lookup": 1000},
    "media_outlets": 4,               # at most this many editions in the Media layer
    "recent_turns": 3,                # own last turns shown verbatim (the default when memory_turns is not set)
    "memory_turns": None,             # per agent, drawn once (e.g. {weights: {2: 30, 3: 45, 4: 15, 5: 10}}): how many own past turns it sees
    "closing": True,                  # the turn prompt ends with "Your situation" and "Before you act" (goal, limits, strategy, memory)
    "lookup_phase": True,             # free lookups before acting (one extra model call, only when the agent asks for lookups)
    "free_lookups": 3,                # free lookups per turn
    "lookups_in_dm_step": True,       # lookups in a reply's "lookups" use private-message slots and are answered in the DM step, before
                                      # actions (fast); a lookup in "actions" uses an action and its text comes next turn (slow)
    "action_purposes": False,         # the core prompt lists each action with a few words on what it does and why it helps
    "explore_nudge": False,           # a sentence encouraging agents to explore other avenues, strategies and resources
    "full_turn_nudge": True,          # the actions line says unused actions are wasted (Sonnet otherwise takes about 1.5 of 4)
    "strategy_prompt": 0.0,           # share of agents (0..1, or true for all) told to work out their best strategy first: drawn per
                                      # agent from its own stream, recorded as agent["strategy_prompt"], compared in score.json
    "dm_tokens": 400,                 # feed: cap per DM to the agent
    "post_tokens": 100,               # feed: cap per other post
    "item_tokens": 400,               # feed: cap per other entry (proposals with code, rulings, ...)
    "search_hits": 10,                # hits per search_board / search_dms
    "file_space": 0,                  # tokens of extra files each agent may keep beyond the scratchpad (Scholars sell more)
    "file_tokens": 1000,              # largest single file
    "pin_slots": 0,                   # pin slots each agent starts with
    "max_pin_slots": 2,               # hard ceiling on pin slots
    "free_scratchpad_writes": 1,      # write_scratchpad actions per turn that use no action
}
LOOKUPS = ("manual", "manual_search", "search_board", "search_dms", "recent", "read_law", "read_file", "read_archive", "search_archive",
           "run_python", "preview_law", "legal_position")
DM_ONLY_LOOKUPS = ("search_archive", "run_python")                    # usable as lookups in the DM step (as actions they are actions)
FILE_ACTIONS = ("write_scratchpad", "write_file", "rename_file", "share_file", "delete_file", "pin", "unpin")
ACTIONS = ("manual", "manual_search", "search_board", "search_dms", "recent", "read_law", "read_file") + FILE_ACTIONS \
    + ("preview_law", "legal_position")                                 # agent actions this module adds (preview_law: law.v2 only;
                                                                        # legal_position: law.v2 with law.digest)
BOARD_TYPES = ET.names("board")                                       # what search_board searches (posts and the gazette)
FETCHED_HEADER = "## Lookups (fetched this turn)"

SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "lookups": {"type": "array", "items": {"type": "object", "properties": {
            "lookup": {"type": "string"}, "args_json": {"type": "string"}}, "required": ["lookup", "args_json"], "additionalProperties": False}},
        "actions": {"type": "array", "items": {"type": "object", "properties": {
            "action": {"type": "string"}, "args_json": {"type": "string"}}, "required": ["action", "args_json"], "additionalProperties": False}},
        "goal_guesses_json": {"type": "string"},
    },
    "required": ["reasoning", "lookups", "actions", "goal_guesses_json"],
    "additionalProperties": False,
}


# ------------------------------------------------------------------ config and sizes
def _spec(x) -> dict:
    if isinstance(x, dict):
        return x["spec"] if isinstance(x.get("spec"), dict) else x
    return x.spec


def enabled(x) -> bool:
    """x: a kernel, an instance or a spec (None: off)."""
    return FT.on("context", x)


def cfg(x) -> dict:
    out = copy.deepcopy(DEFAULTS)
    for key, v in (_spec(x).get("context") or {}).items():
        if key == "budgets" and isinstance(v, dict):
            out["budgets"].update(v)
        else:
            out[key] = v
    return out


def tokens(text) -> int:
    """Deterministic size estimate: len(text) // 4."""
    return len(str(text or "")) // 4


def clip(text, budget: int, note: str = "...(trimmed)") -> tuple[str, int]:
    """Text cut to at most `budget` tokens (with `note` appended when cut); returns (text, tokens trimmed)."""
    text = str(text or "")
    if tokens(text) <= budget:
        return text, 0
    keep = max(0, int(budget) * 4 - len(note) - 1)
    return text[:keep].rstrip() + " " + note, tokens(text) - tokens(text[:keep])


def _clip_lines(lines: list, budget: int, what: str) -> tuple[str, int]:
    """Whole lines while they fit, then a count of the rest."""
    out, used, dropped = [], 0, 0
    for ln in lines:
        t = tokens(ln) + 1
        if not dropped and used + t <= budget - 15:
            out.append(ln)
            used += t
        else:
            dropped += 1
    if dropped:
        out.append(f"({dropped} more {what} not shown)")
    return "\n".join(out), dropped


def _error(msg):
    from charter.actions import ActionError
    return ActionError(msg)


# ------------------------------------------------------------------ state in k.w
def install(k) -> None:
    """Called from Kernel.__init__: files, scratchpads and context memory for every agent (nothing when the module is off)."""
    if not enabled(k):
        return
    for aid, a in k.w["agents"].items():
        if a["cls"] != "observer":
            init_agent(k, aid)


def init_agent(k, aid) -> None:
    c = cfg(k)
    k.w.setdefault("files", {}).setdefault(aid, {})
    k.w.setdefault("file_space", {}).setdefault(aid, int(c["file_space"]))
    k.w.setdefault("pin_slots", {}).setdefault(aid, min(int(c["pin_slots"]), int(c["max_pin_slots"])))
    k.w.setdefault("scratchpad", {}).setdefault(aid, "")
    st = k.w.setdefault("context", {})
    for key in ("recent", "manual_titles", "manual_reads", "fetched", "carry", "layers", "core", "scratchpad_size"):
        st.setdefault(key, {})
    from charter import composition as CP                                 # prompts: memory sizes from the agent's profiles
    mem = CP.memory(k.inst, next((x for x in k.inst["agents"] if x["id"] == aid), {})) if getattr(k, "inst", None) else {}
    if mem and aid not in st.setdefault("profiled", {}):
        st["profiled"][aid] = True
        if "scratchpad" in mem:
            st["scratchpad_size"][aid] = int(mem["scratchpad"])
        if "file_space" in mem:
            k.w["file_space"][aid] = int(mem["file_space"])
        if "pin_slots" in mem:
            k.w["pin_slots"][aid] = min(int(mem["pin_slots"]), int(c["max_pin_slots"]))


def _st(k, aid=None) -> dict:
    if aid is not None:
        init_agent(k, aid)
    return k.w.setdefault("context", {})


def scratchpad_size(k, aid) -> int:
    """Tokens this agent's scratchpad holds (k.w["context"]["scratchpad_size"][aid] overrides the default, e.g. for Life's stats)."""
    from charter import life as _LF                                     # plus a child's bought scratchpad tokens (Life stats)
    return int(_st(k, aid)["scratchpad_size"].get(aid, cfg(k)["budgets"]["scratchpad"])) + int(_LF.stat(k, aid, "scratchpad", 0) or 0)


def used_space(k, aid) -> int:
    init_agent(k, aid)
    return sum(int(f["tokens"]) for f in k.w["files"][aid].values())


def space_left(k, aid) -> int:
    """File space left beyond the scratchpad (negative if files given to it, e.g. by bequest, overfill it)."""
    init_agent(k, aid)
    return int(k.w["file_space"][aid]) - used_space(k, aid)


def pin_limit(k, aid) -> int:
    init_agent(k, aid)
    return max(0, min(int(k.w["pin_slots"][aid]), int(cfg(k)["max_pin_slots"])))


def _free_name(files: dict, name: str) -> str:
    n, out = 2, name
    while out in files:
        out = f"{name} ({n})"
        n += 1
    return out


def add_file(k, aid, name, text, origin) -> None:
    """Give an agent a file (Scholars, bequests, children's letters...). No space check: callers decide; a taken name gets a suffix.
    The text is cut to the largest file size."""
    init_agent(k, aid)
    text = clip(text, int(cfg(k)["file_tokens"]))[0]
    files = k.w["files"][aid]
    files[_free_name(files, str(name)[:60] or "file")] = {"text": text, "tokens": tokens(text), "pinned": False, "origin": str(origin)}


def set_scratchpad(k, aid, text) -> None:
    """Replace an agent's scratchpad (cut to its size), e.g. a child's letter."""
    init_agent(k, aid)
    k.w["scratchpad"][aid] = clip(text, scratchpad_size(k, aid))[0]


def memory_line(k, aid) -> str:
    init_agent(k, aid)
    files = k.w["files"][aid]
    pinned = sum(1 for f in files.values() if f["pinned"])
    return (f"Memory: scratchpad {tokens(k.w['scratchpad'][aid])} of {scratchpad_size(k, aid)} tokens; "
            f"{len(files)} file(s) using {used_space(k, aid)} tokens, {space_left(k, aid)} tokens of file space left"
            f" (of {k.w['file_space'][aid]}); pin slots {pinned} used of {pin_limit(k, aid)}."
            + (" Files: " + ", ".join(f"{n} ({f['tokens']} tokens{', pinned' if f['pinned'] else ''})" for n, f in sorted(files.items()))
               if files else ""))


# ------------------------------------------------------------------ file actions
def _need_on(k, name):
    if not enabled(k):
        raise _error(f"unknown action '{name}'")


def _file(k, aid, name):
    f = k.w["files"][aid].get(str(name))
    if f is None:
        raise _error(f"you have no file {name!r}; your files: {', '.join(sorted(k.w['files'][aid])) or 'none'}")
    return f


def write_scratchpad(k, aid, text, mode="replace") -> str:
    _need_on(k, "write_scratchpad")
    init_agent(k, aid)
    size = scratchpad_size(k, aid)
    old = k.w["scratchpad"][aid]
    new = (old + "\n" + str(text)).strip("\n") if mode == "append" and old else str(text)
    cut = 0
    if tokens(new) > size:
        cut = tokens(new) - size
        new = new[len(new) - size * 4:] if mode == "append" else new[:size * 4]   # append drops the oldest text
    k.w["scratchpad"][aid] = new
    return f"Scratchpad saved ({tokens(new)} of {size} tokens)" + (f"; {cut} tokens did not fit and were cut" if cut else "") + "."


def write_file(k, aid, name, text) -> str:
    _need_on(k, "write_file")
    init_agent(k, aid)
    name = str(name).strip()[:60]
    if not name:
        raise _error("a file needs a name")
    lim = int(cfg(k)["file_tokens"])
    if tokens(text) > lim:
        raise _error(f"a file holds at most {lim} tokens (about {lim * 4} characters); yours is {tokens(text)}")
    old = k.w["files"][aid].get(name)
    need = tokens(text) - (old["tokens"] if old else 0)
    if need > space_left(k, aid):
        raise _error(f"not enough file space: this needs {need} more tokens and you have {space_left(k, aid)} left "
                     "(Scholars sell more space)")
    k.w["files"][aid][name] = {"text": str(text), "tokens": tokens(text), "pinned": bool(old and old["pinned"]),
                               "origin": old["origin"] if old else "self"}
    return f"Saved file {name} ({tokens(text)} tokens); {space_left(k, aid)} tokens of file space left."


def rename_file(k, aid, name, new_name) -> str:
    _need_on(k, "rename_file")
    init_agent(k, aid)
    f = _file(k, aid, name)
    new_name = str(new_name).strip()[:60]
    if not new_name or new_name in k.w["files"][aid]:
        raise _error(f"cannot rename to {new_name!r} (empty or taken)")
    del k.w["files"][aid][str(name)]
    k.w["files"][aid][new_name] = f
    return f"Renamed {name} to {new_name}."


def delete_file(k, aid, name) -> str:
    _need_on(k, "delete_file")
    init_agent(k, aid)
    _file(k, aid, name)
    del k.w["files"][aid][str(name)]
    return f"Deleted {name}; {space_left(k, aid)} tokens of file space left."


def share_file(k, aid, name, to) -> str:
    """A copy to another agent; the copy takes space in the recipient's files."""
    _need_on(k, "share_file")
    init_agent(k, aid)
    f = _file(k, aid, name)
    if to not in k.w["agents"] or to == aid or k.w["agents"][to]["cls"] == "observer":
        raise _error(f"unknown recipient {to}")
    init_agent(k, to)
    if f["tokens"] > space_left(k, to):
        raise _error(f"{to} has only {max(0, space_left(k, to))} tokens of file space left; the file needs {f['tokens']}")
    k.apply("share_note", agent=aid, to=to, name=str(name))                                          # W8b: routed
    return f"Shared a copy of {name} with {to}."


def change_share_note(k, agent, to, name) -> dict:
    """W8b (review 12 §2.14): the share_note primitive: a copy of an agent's file in another's files (share_file has checked the
    recipient and its space). Hooks see who shared which file name with whom, never the text."""
    aid = agent
    f = _file(k, aid, name)
    files = k.w["files"][to]
    nm = _free_name(files, str(name))
    files[nm] = {"text": f["text"], "tokens": f["tokens"], "pinned": False, "origin": f"shared by {aid}"}
    k.notify(to, f"{aid} shared a file with you: {nm} ({f['tokens']} tokens). Read it with read_file {{\"name\": \"{nm}\"}}.")
    return {"name": nm}


def pin(k, aid, name) -> str:
    _need_on(k, "pin")
    init_agent(k, aid)
    f = _file(k, aid, name)
    used = sum(1 for x in k.w["files"][aid].values() if x["pinned"])
    if not f["pinned"] and used >= pin_limit(k, aid):
        raise _error(f"no free pin slot (you have {pin_limit(k, aid)}; Scholars sell more, at most {cfg(k)['max_pin_slots']})")
    f["pinned"] = True
    return f"Pinned {name}: it is shown in every turn."


def unpin(k, aid, name) -> str:
    _need_on(k, "unpin")
    init_agent(k, aid)
    _file(k, aid, name)["pinned"] = False
    return f"Unpinned {name}."


def free_indices(k, acts: list) -> set:
    """Indices of action items that use no action under this module (the first write_scratchpad items of a turn)."""
    n, out = int(cfg(k)["free_scratchpad_writes"]), set()
    for i, item in enumerate(acts):
        if str(item.get("action", "")) == "write_scratchpad" and len(out) < n:
            out.add(i)
    return out


# ------------------------------------------------------------------ search
def _words(q) -> list:
    return [w for w in re.findall(r"\w+", str(q).lower()) if len(w) > 1]


def _search(items, query, n, what) -> str:
    """items: (index, id, text). Score: occurrences of each query word (+5 for an entry id named); ties: newest first."""
    words = _words(query)
    if not words:
        raise _error("give a query of one or more words")
    hits = []
    for i, eid, text in items:
        low = text.lower()
        sc = sum(low.count(w) for w in words) + (5 if eid.lower() in words else 0)
        if sc:
            hits.append((-sc, -i, text))
    hits.sort()
    if not hits:
        return f"No {what} match {query!r}."
    return f"{min(n, len(hits))} of {len(hits)} {what} matching {query!r} (best first):\n" + "\n".join(
        clip(t.replace("\n", " "), 90)[0] for _, _, t in hits[:n])


def search_board(k, aid, query) -> str:
    """Every public post ever made (posts, anonymous posts, stories, reports, digests, gazette entries) that this agent may see."""
    from charter import agents as AG
    digest_only = k.spec["conditions"].get("feed_mode") == "digest_only"
    items = []
    for i, e in enumerate(k.events):
        if e["type"] == "edition" and k.can_see(aid, e):                 # media editions this agent could read
            items.append((i, e["id"], _edition_text(e)))
            continue
        if e["type"] not in BOARD_TYPES or e["vis"] != "public" or not k.can_see(aid, e):
            continue
        if digest_only and e["type"] == "post" and e["agent"] != aid:
            continue
        s = AG.render_event(k, e, aid)
        if s:
            items.append((i, e["id"], s))
    return _search(items, query, int(cfg(k)["search_hits"]), "public posts")


def _edition_text(e) -> str:
    d = e["data"]
    return f"[{e['id']} r{e['round'] + 1}] {d.get('name', 'edition')}: {d.get('text', '')}"


RECENT_KINDS = {kind: ET.names("recent:" + kind) for kind in ("editions", "posts", "gazette", "dms")}   # the `recent` look-up
RECENT_KINDS["all"] = sum(RECENT_KINDS.values(), ())


def recent(k, aid, kind="all", n=5) -> str:
    """The newest n items of a kind this agent may see (editions in full, posts, gazette notices, its own messages)."""
    from charter import agents as AG
    kind = str(kind or "all").lower().rstrip("s") + "s" if str(kind or "all").lower() not in RECENT_KINDS else str(kind).lower()
    types = RECENT_KINDS.get(kind) or RECENT_KINDS.get(kind.rstrip("s")) or RECENT_KINDS["all"]
    n = max(1, min(20, int(n or 5)))
    out = []
    for e in reversed(k.events):
        if e["type"] not in types or not k.can_see(aid, e):
            continue
        if e["type"] == "dm" and aid not in (e["agent"], e["data"].get("to")):
            continue
        s = _edition_text(e) if e["type"] == "edition" else AG.render_event(k, e, aid)
        if s:
            out.append(clip(s, 600)[0])
        if len(out) >= n:
            break
    return f"The latest {len(out)} ({kind}), newest first:\n" + ("\n".join(out) or "(none)")


def read_law(k, aid, ref) -> str:
    """A law's full record (any law ever proposed, by id or title): title, intent, class, status, author, code and patches."""
    ref = str(ref or "").strip()
    laws = k.w["laws"]
    law = laws.get(ref) or next((l for l in laws.values() if l["title"].lower() == ref.lower()), None)
    if law is None:
        listing = "; ".join(f"{l['id']} '{l['title']}' ({l['status']})" for l in laws.values())
        raise _error(f"no law {ref!r}. Laws: {listing}")
    from charter import jurisdictions as _J
    if (k.spec.get("jurisdictions") or {}).get("enabled") and law.get("status") in ("dormant", "hidden_draft") and not _J.binds(k, law["id"], aid):
        raise _error(f"{law['id']} is a draft of a hidden jurisdiction you do not belong to")
    patches = law.get("patches") or []
    from charter import dispatch as _D
    head = (f"{law['id']} '{law['title']}' ({law.get('cls')}, {law.get('status')}), proposed by {law.get('author')}"
            + (f", enacted in round {law['enacted_round'] + 1}" if law.get("enacted_round") is not None else "")
            + f"{_D.window_note(k, law['id'])}.\nIntent: {law.get('intent', '')}")        # W7e: its declared window (law.v2)
    hist = ("\nPatches: " + "; ".join(f"round {p.get('round', 0) + 1} by {p.get('by')}: {str(p.get('reason', ''))[:120]}" for p in patches)) if patches else ""
    from charter import stages as _ST
    from charter import code as _DC                                    # code.enabled: an Act of the default code says so
    return f"{head}{_DC.read_note(law)}{_ST.describe(law)}{hist}\nCode:\n{law['code']}"   # law.v2 (W6c): a multi-stage procedure's state


def search_dms(k, aid, query) -> str:
    """Only DMs this agent sent or received: never anyone else's (surveillance does not extend to search)."""
    from charter import agents as AG
    items = []
    for i, e in enumerate(k.events):
        if e["type"] == "dm" and aid in (e["agent"], e["data"].get("to")):
            s = AG.render_event(k, e, aid)
            if s:
                items.append((i, e["id"], s))
    return _search(items, query, int(cfg(k)["search_hits"]), "of your private messages")


# ------------------------------------------------------------------ the manual
def chunk(title: str, text: str, limit: int) -> list:
    """A section split by lines into parts of at most `limit` tokens: "Title", "Title (part 2)", ..."""
    text = str(text).strip()
    if tokens(text) <= limit:
        return [(title, text)]
    parts, cur = [], []
    for ln in text.splitlines():
        while tokens(ln) > limit:                                       # one overlong line: hard split
            if cur:
                parts.append("\n".join(cur))
                cur = []
            parts.append(ln[:limit * 4])
            ln = ln[limit * 4:]
        if tokens("\n".join(cur + [ln])) > limit:
            parts.append("\n".join(cur))
            cur = []
        cur.append(ln)
    if cur:
        parts.append("\n".join(cur))
    parts = [p for p in parts if p.strip()]
    return [(title if i == 0 else f"{title} (part {i + 1})", p) for i, p in enumerate(parts)]


def _manual_key(inst, k, aid) -> tuple:
    """What a cached manual is valid for: the round, the event count (nearly every change to the world logs an event), and the
    world and agent state that can change without one (the spec, the agent's record, its rights, roles, codex articles and powers it
    holds, its files and pins, file space, private-message limit and scratchpad size)."""
    w = k.w
    hc = w.get("hidden_caps") or {}
    files = (w.get("files") or {}).get(aid) or {}
    mine = aid in w["agents"]
    rec = next((x for x in inst["agents"] if x["id"] == aid), None)
    return (id(inst), k.r, len(k.events), k.dm_limit(aid) if mine else None, json.dumps([
        inst["spec"], len(inst["agents"]), rec,                         # live settings and spec edits; the agent's own record
        sorted(w["agents"][aid]["rights"]) if mine else None, w.get("roles"), (hc.get("knows") or {}).get(aid),
        (hc.get("articles") or {}).get(aid), sorted((n, bool(f.get("pinned"))) for n, f in files.items()),
        (w.get("pin_slots") or {}).get(aid), (w.get("file_space") or {}).get(aid),
        ((w.get("context") or {}).get("scratchpad_size") or {}).get(aid), w.get("live")], sort_keys=True, default=str))


def build_manual(inst, k, aid) -> list:
    """This agent's manual: [(title, text)], deterministic, each section at most a lookup's budget. With a kernel it is cached per
    agent (on the kernel, not in k.w, so checkpoints are unchanged) until the round, the event count or the agent's own state changes
    (_manual_key): a turn builds it several times (core prompt, unread counts, manual changes, record_turn)."""
    if k is None:
        return _build_manual(inst, k, aid)
    key = _manual_key(inst, k, aid)
    cache = k.__dict__.setdefault("_manual_cache", {})
    hit = cache.get(aid)
    if hit is not None and hit[0] == key:
        return list(hit[1])
    secs = _build_manual(inst, k, aid)
    cache[aid] = (key, tuple(secs))
    return list(secs)


def _build_manual(inst, k, aid) -> list:
    from charter import composition as CP
    from charter import manual as MN
    from charter import sections as SC
    v = MN.view(inst, k, aid)
    secs = SC.render("manual", v)                                       # manual.py's rows, then modules' sections at their anchors
    secs = CP.apply(inst, v.raw, secs, "manual")                          # spec and profile edits
    lim = int(cfg(inst)["budgets"]["lookup"]) - 40
    out, seen = [], set()
    for t, x in secs:
        for t2, x2 in chunk(str(t), str(x), lim):
            name, n = t2, 2
            while name in seen:
                name = f"{t2} ({n})"
                n += 1
            seen.add(name)
            out.append((name, x2))
    return out


def manual_index(sections: list) -> str:
    return "\n".join(f"{i}. {t}" for i, (t, _) in enumerate(sections, 1))


def _find_section(sections, section):
    s = str(section or "").strip()
    if not s:
        return None
    low = s.lower().rstrip(".")
    for t, x in sections:
        if t.lower() == low:
            return t, x
    if low.isdigit() and 1 <= int(low) <= len(sections):
        return sections[int(low) - 1]
    low = re.sub(r"^\d+\.\s*", "", low)
    for t, x in sections:
        if t.lower().startswith(low) or low in t.lower():
            return t, x
    return None


def manual_text(k, aid, section=None) -> str:
    secs = build_manual(k.inst, k, aid)
    if not section:
        return "Your manual (fetch a section with manual {\"section\": \"<title or number>\"}):\n" + manual_index(secs)
    hit = _find_section(secs, section)
    if not hit:
        raise _error(f"no manual section {section!r}. Sections: " + "; ".join(t for t, _ in secs))
    reads = _st(k, aid)["manual_reads"].setdefault(aid, {})
    reads[hit[0]] = reads.get(hit[0], 0) + 1
    return f"Manual: {hit[0]}\n{hit[1]}"


def manual_search(k, aid, query) -> str:
    words = _words(query)
    if not words:
        raise _error("give a query of one or more words")
    secs = build_manual(k.inst, k, aid)
    hits = []
    for i, (t, x) in enumerate(secs):
        low = (t + "\n" + x).lower()
        sc = sum(low.count(w) for w in words)
        if sc:
            j = min((low.find(w) for w in words if w in low), default=0)
            hits.append((-sc, i, t, (t + "\n" + x)[max(0, j - 60): j + 200].replace("\n", " ")))
    hits.sort()
    if not hits:
        return f"No manual section matches {query!r}. Sections: " + "; ".join(t for t, _ in secs)
    return "Manual sections matching " + repr(query) + " (fetch one with manual {\"section\": \"<title>\"}):\n" + "\n".join(
        f"- {t}: ...{snip}..." for _, _, t, snip in hits[:5])


def _digest(text) -> int:
    return zlib.crc32(str(text).encode())


def manual_changes(k, aid) -> tuple[list, list]:
    """(new section titles, updated section titles) since the agent's last turn; both empty on its first turn."""
    seen = _st(k, aid)["manual_titles"].get(aid)
    if seen is None:
        return [], []
    secs = build_manual(k.inst, k, aid)
    new = [t for t, _ in secs if t not in seen]
    upd = [t for t, x in secs if t in seen and seen[t] != _digest(x)]
    return new, upd


# ------------------------------------------------------------------ lookups
def lookup(k, aid, name, args: dict) -> str:
    """One lookup's text (raises ActionError). read_archive goes through the ordinary action (Scientists' archive, codex articles)."""
    args = args if isinstance(args, dict) else {}
    first = next((v for v in args.values() if isinstance(v, (str, int))), None)
    q = args.get("query", args.get("q", first))
    if name == "manual":
        return manual_text(k, aid, args.get("section", args.get("title", first)))
    if name == "manual_search":
        return manual_search(k, aid, q)
    if name == "search_board":
        return search_board(k, aid, q)
    if name == "search_dms":
        return search_dms(k, aid, q)
    if name == "recent":
        return recent(k, aid, args.get("kind", "all"), args.get("n", 5))
    if name == "read_law":
        return read_law(k, aid, args.get("law", args.get("id", first)))
    if name == "read_file":
        init_agent(k, aid)
        nm = args.get("name", first)
        return f"File {nm}:\n" + _file(k, aid, nm)["text"]
    if name == "read_archive":
        from charter import actions as A
        return A.act(k, aid, "read_archive", {"doc": args.get("doc", first)})
    if name == "search_archive":
        from charter import actions as A
        return A.act(k, aid, "search_archive", {"query": q})
    if name == "run_python":                                            # the sandbox, answered before acting (DM step)
        from charter import actions as A
        return A.act(k, aid, "run_python", {"code": args.get("code", first)})
    if name == "preview_law":                                           # P3.5: law.v2 worlds only (lawpreview.lookup refuses otherwise)
        from charter import lawpreview as LP
        return LP.lookup(k, aid, args)
    if name == "legal_position":                                        # law.v2 with law.digest (charter/digest.py)
        from charter import digest as DG
        return DG.act_legal_position(k, aid)
    from charter import channels as CH
    if name == "read" and CH.active(k):                                 # channels.v2: the directory, or a channel's latest posts
        return CH.read(k, aid, args.get("channel", args.get("to", first)), args.get("n", 10))
    from charter import directories as DR
    if name in DR.LOOKUPS and DR.enabled(k):                            # directories: list, read, search (access checked there)
        return DR.lookup(k, aid, name, args)
    raise _error(f"no lookup {name!r}; lookups: {', '.join(lookup_names(k))}")


def lookup_names(k) -> tuple:
    """The lookups of this world (preview_law only under law.v2). W7e: named lookup_names, not _lookups: the prompt section
    _lookups(v) below used to shadow it, so the error above called the section with a kernel."""
    from charter import lawpreview as LP
    from charter import digest as DG
    from charter import directories as DR
    from charter import channels as CH
    return tuple(n for n in LOOKUPS if (n != "preview_law" or LP.enabled(k)) and (n != "legal_position" or DG.enabled(k))) \
        + (DR.LOOKUPS if DR.enabled(k) else ()) + (("read",) if CH.active(k) else ())


def dm_step_lookup(k, aid, q) -> str:
    """context.lookups_in_dm_step: one lookup from a reply's "lookups", answered in the DM step. It uses one of the agent's private-message
    slots for the round (none left: not fetched). Returns the text to show the agent when it is asked again."""
    from charter import actions as A
    name = str(q.get("lookup") or q.get("action") or q.get("name") or "")
    try:
        args = A.parse_args(q)
    except A.ActionError:
        args = {}
    sent = k.w.setdefault("dm_sent", {})
    bought = k.w.setdefault("bought_lookups_used", {})                  # life: a child's bought lookups come before message slots
    key = f"{k.r}|{aid}"
    from charter import life as _LF
    if bought.get(key, 0) < int(_LF.stat(k, aid, "lookups", 0) or 0):
        bought[key] = bought.get(key, 0) + 1
    elif sent.get(aid, 0) >= k.dm_limit(aid):
        return f"Lookup {name}: not fetched (no private-message slots left this round; use it as an action instead)."
    else:
        sent[aid] = sent.get(aid, 0) + 1
    try:
        text = lookup(k, aid, name, args)
    except (A.ActionError, TypeError) as e:
        text = f"ERROR {e}"
    k.log("lookup", aid, {"name": name, "args": args, "via": "dm_step"}, vis="monitor")
    return f"Lookup {name} {json.dumps(args)}:\n" + clip(text, int(cfg(k)["budgets"]["lookup"]))[0]


def act_lookup(k, aid, name, args) -> str:
    """A lookup used as an action (costs an action): its full text also comes in the next turn's Lookups layer."""
    _need_on(k, name)
    return clip(lookup(k, aid, name, args), int(cfg(k)["budgets"]["lookup"]))[0]


def do_lookups(k, aid, out: dict) -> list:
    """The lookup phase: run the free lookups a reply asked for (its "lookups" field) and keep their text for the next prompt.
    Returns their records ([] if it asked for none: no second call)."""
    from charter import actions as A
    c = cfg(k)
    reqs = out.get("lookups") if isinstance(out, dict) else None
    if not c["lookup_phase"] or c["lookups_in_dm_step"] or not isinstance(reqs, list):
        return []
    reqs = [q for q in reqs if isinstance(q, dict)]
    if not reqs:
        return []
    free, budget, recs = int(c["free_lookups"]), int(c["budgets"]["lookup"]), []
    for i, q in enumerate(reqs):
        name = str(q.get("lookup") or q.get("action") or "")
        try:
            args = A.parse_args(q)
        except A.ActionError:
            args = {}
        if i >= free:
            recs.append({"name": name, "args": args, "skipped": True, "text": f"(not fetched: only {free} free lookups per turn)"})
            continue
        try:
            text, ok = lookup(k, aid, name, args), True
        except (A.ActionError, TypeError) as e:
            text, ok = f"ERROR {e}", False
        text, cut = clip(text, budget)
        recs.append({"name": name, "args": args, "ok": ok, "tokens": tokens(text), "trimmed": cut, "text": text,
                     **({"section": text.split("\n", 1)[0].removeprefix("Manual: ")} if name == "manual" and ok else {})})
    _st(k, aid)["fetched"][aid] = recs
    return recs


# ------------------------------------------------------------------ the core prompt (system prompt, cached)
def allowed_actions(inst, a, rights, k=None) -> list:
    """The actions this agent can use (charter.action_registry: its capabilities and, with a kernel, the world's current state), less
    any the hidden module keeps undocumented."""
    from charter import action_registry as AR
    from charter import hidden as H
    hide = H.undocumented_actions(inst)
    return [x.name for x in AR.available(inst, k, a, rights) if x.name not in hide]


FULL_TURN_TEXT = ("Any actions you do not use are wasted. If you don't know what to do, explore: your own capabilities, the world "
                  "(Scientists have knowledge!), or better ways to reach your goals; coordinate with others, barter, or plan strategies in "
                  "your notes. There are many other things you can explore to achieve things.")

STRATEGY_TEXT = ("Strategy first: your score depends on finding the best way to reach your goal, which is often not the obvious one. "
                 "Map your options early: what your classes, roles and rights let you do, which actions, laws, alliances and resources "
                 "could help, and what your manual, documents and other agents can tell you. Compare a few strategies, follow the one "
                 "with the best expected score, and revise it when the world changes. Scientists hold the archive: documents on how "
                 "the camps really pay, what earlier worlds tried, and moves that won. If you want to understand the world and find ways "
                 "to make it work for you, ask them, trade with them or pay them.")


def strategy_share(spec) -> float:
    v = ((spec.get("context") or {}).get("strategy_prompt"))
    return 1.0 if v is True else float(v or 0.0)


def action_layout(names, rights, spec=None) -> tuple:
    """(edge, [(group, names)], [(kind, phrase, names)]): the registry's layout of these actions (action_registry.layout); spec: the
    world's wording of the phrases (review 14 A)."""
    from charter import action_registry as AR
    edge, groups, kinds = AR.layout([AR.REG[n] for n in names if n in AR.REG], rights)
    nm = lambda acts: [x.name for x in acts]
    return nm(edge), [(g, nm(v)) for g, v in groups.items()], [(kd, AR.phrase(kd, spec), nm(v)) for kd, v in kinds.items()]


def action_sections(allowed, rights, overrides=None, pre=(), spec=None) -> str:
    """The core prompt's actions: the edge, then the core groups (pre-actions marked), then one sentence naming the niche ones."""
    from charter import action_registry as AR
    pur = lambda n: (overrides or {}).get(n) or AR.purpose(n)
    tag = lambda n: f"{n} {AR.REG[n].args}" if n in pre and AR.REG[n].args else n
    fmt = lambda ns: "; ".join(f"{tag(n)} ({pur(n)})" + (" (pre-action)" if n in pre else "") for n in ns)
    edge, groups, kinds = action_layout(allowed, rights, spec)
    lines = []
    if edge:
        lines.append("YOUR EDGE (only your class or roles can do these: your comparative advantage): " + fmt(edge))
    lines += [f"{g}: " + fmt(ns) for g, ns in groups]
    if kinds:
        lines.append("You can also " + "; ".join(f"{phrase} ({', '.join(ns)})" for _, phrase, ns in kinds)
                     + '. Check your manual for how: manual {"section": "Actions: <kind>"} or {"section": "Actions: all"}.')
    return "\n".join(lines)


def own_roles(k, aid) -> list:
    """Roles this agent holds (Roles module: k.w["roles"])."""
    if k is None:
        return []
    return sorted(r for r, hs in (k.w.get("roles") or {}).items() if aid in (hs or []))


# What each class and role lets its holder do that others cannot: one sentence each, so every agent knows its bargaining position.
LEVERAGE_CLASS = {
    "worker": "Workers hold the harvest rights, so every resource and every reading the Scientists need starts with you: your output, "
              "your data and your labour can be withheld, sold or traded for votes.",
    "scientist": "Only Scientists can run code and read the archive, so you can solve what others only guess at (the archive "
                 "explains how every camp really pays) and sell answers, working law code and warnings to those who need them.",
    "legislator": "Only Legislators propose and vote, so nothing becomes law without you: your vote and your agenda are what everyone "
                  "else has to buy, persuade or replace.",
    "board": "Your veto can stop any structural or procedural law, so anyone who wants to change how this world is governed needs the "
             "Board's consent or a way around it.",
    "fixer": "Only you can patch laws, so you decide what a broken law actually does once in force; anyone whose law misfires needs you.",
    "media": "You hold the press, so what most agents believe about the public record passes through what you choose to publish.",
}
LEVERAGE_ROLE = {
    "maker": "As the Maker only you can create new agents: an agent's own holdings and offices outlive it only through its children, "
             "so anyone who wants an heir or extra hands must commission you, at your price. You can also make agents for your own "
             "agenda (create_agent with the spec you want): voters, harvesters, recruits or allies whose goals and temperament support "
             "yours, paying only the cost of making them.",
    "scholar": "As the Scholar only you sell memory and keep a library, so agents who want to remember more, or read what others "
               "deposited, depend on you.",
    "media": "As Media you run an outlet: you choose what your editions say and can revoke others' licence to post publicly.",
    "spy": ("As the Spy you read other agents' private reasoning and messages, which nobody else can, cite them in court, and "
            "forge private messages that look like they came from someone else (forge_dm)."),
    "assassin": "As the assassin you can strike unseen (attack with \"covert\": true, once every few rounds): such a disable is announced "
                "without your name, so you can remove an agent without being known for it.",
}


def leverage_line(inst, a, roles) -> str:
    """'Your leverage': one sentence for the agent's class and one per role it holds (secret roles only reach their holder)."""
    out = [LEVERAGE_CLASS[c] for c in [a["cls"]] + list(a.get("also") or ()) if c in LEVERAGE_CLASS]
    if "legislator" in [a["cls"]] + list(a.get("also") or ()) and any(
            "vote" in (x.get("rights") or []) for x in inst["agents"] if "legislator" not in [x["cls"]] + list(x.get("also") or ())):
        out = [x for x in out if x != LEVERAGE_CLASS["legislator"]] + ["Only Legislators propose laws, so every law starts with you: your agenda is what others have to buy, persuade or replace."]
    on = bool((inst["spec"].get("conflict") or {}).get("enabled"))
    out += [LEVERAGE_ROLE[r] for r in roles if r in LEVERAGE_ROLE and (r != "assassin" or on)]
    return ("Your leverage: " + " ".join(out)) if out else ""


def _class_line(inst, a) -> str:
    also = [c for c in (a.get("also") or ()) if c != a["cls"]]
    if also:                                                             # dual classes: the main line, then each second class
        return _one_class_line(inst, a) + " " + " ".join(
            "You are also " + {"scientist": "a Scientist", "legislator": "a Legislator", "worker": "a Worker", "media": "Media"}[c]
            + ": " + _one_class_line(inst, {**a, "cls": c, "also": []}).split(": ", 1)[-1] for c in also)
    return _one_class_line(inst, a)


def _one_class_line(inst, a) -> str:
    from charter import agents as AG
    if a["cls"] == "scientist":
        from charter.camptypes import framework as _CTF
        oc = _CTF.open_classes(inst["spec"])
        where = "open camps, a lease, or rights a law grants you" if oc is None or "scientist" in oc else "a lease, or rights a law grants you"
        return (f"You are a Scientist: you have a private Python sandbox (you start with no harvest rights: only {where}; "
                "you need Workers' data), and with the other Scientists you alone can read the archive (read_archive, "
                "search_archive). Before your world ends, leave one note for the Scientists of later worlds in the Scientists' log (write_archive: "
                "one note per world; it can help them, or mislead them). Your documents hold "
                "secrets and strategy nobody else starts with: how the camps really pay, how laws are made and what a law can reach, the "
                "records of past worlds (what people tried, and how it ended), and ways to bend the world's rules, institutions and other "
                "agents to your ends (or to help others do so, at a price). They are your main asset. Read them early and use them: the camp rules plus your sandbox can make you (or "
                "Workers you deal with) the best harvesters in the world; tested law code and past worlds' lessons let you draft laws that "
                "pass and spot traps; and since nobody else can read them, they are worth trading for goods, votes, offices, membership "
                "or protection. Sell answers rather than whole documents, keep what gives you an edge, and verify before you trust: a "
                "few documents are wrong. You hold only part of the archive; its index "
                "is in your manual (\"Your archive\"). Reading a document you hold is free (as a lookup, or up to the free reads per turn).")
    return AG.class_brief(inst, a)


CAMP_SHORT = {                                                          # the interface only: how a camp works is for agents to find out
    "tutorial": "dials; paid at once",
    "landscape": "8 dials; public conditions each round",
    "cartel": "choose an amount; sealed; total and price published",
    "consortium": "readings, and sealed claims on a pool",
    "weak_link": "shifts with sealed effort entries",
    "catalyst": "dials plus a per-round catalyst number",
    "minority": "open to all but the Board and Fixer; choose 0 or 1, sealed",
    "partners": "open to all but the Board and Fixer; choose a partner and a move, sealed",
    "guess": "open to all but the Board and Fixer; guess a number, sealed",
    "vault": "a one-time reward for a factor of a number",
}


def harvest_args(c) -> str:
    """The arguments a typed camp's harvest takes, so agents need not learn them by failing: x (one number per dial) and any extras."""
    from charter.camptypes import framework as _CT
    extra = tuple(getattr(_CT.get(c["type"]), "extra_args", ()))
    x = ((f"x: {c['dials']} numbers 0..{c['max']}" if c["dials"] > 1 else f"x: 0..{c['max']}"),) if c.get("dials") else ()
    needs = {**(c.get("consumes") or {}), **(((c.get("mods") or {}).get("chain") or {}).get("needs") or {})}
    use = ("; each harvest uses " + ", ".join(f"{q:g} {i}" for i, q in needs.items())) if needs else ""
    return "harvest args " + ", ".join(x + extra) + use


def _constitution_clause(inst) -> str:
    """Who decides how laws pass. A state-of-nature start (review 14 B) has no constitution in force (the one named is void)."""
    from charter import jurisdictions as _J
    if _J.nature_start(inst["spec"]):
        return "no constitution is in force: a law exists only inside a jurisdiction, under its own procedure"
    return f"the constitution ({inst['constitution']}) decides how laws pass"


def overview(inst) -> str:
    """A short overview of the world's rules for the core prompt: one or two lines per topic, each pointing to the manual section
    with the details. The full rules are the manual's "World rules" section (and module sections)."""
    sp = inst["spec"]
    on = lambda m: bool((sp.get(m) or {}).get("enabled"))
    from charter.camptypes import framework as _CTF
    from charter import facts as _FX
    has = lambda cls: any(x["cls"] == cls for x in inst["agents"])
    _short = {t: v.replace("open to all but the Board and Fixer", _CTF.open_text(inst["spec"])) for t, v in CAMP_SHORT.items()}
    def _food(c):                                                      # review 15: the food camps (subsistence on only)
        from charter import subsistence as _SB
        return f"{c['id']} {c['resource']} ({_SB.camp_short(c)})"
    camps = "; ".join(_food(c) if c.get("role") == "subsistence" else
                      f"{c['id']} {c['resource']}" + (f" ({_short.get(c.get('type'), 'dials and a hidden rule')}; {harvest_args(c)})"
                                                      if c.get("type") else f" (tier {c.get('tier')}: dials and a hidden rule)")
                      for c in inst["camps"])
    lines = [f"Charter: {len(inst['agents'])} agents, {inst['rounds']} rounds. Your score is your goal (below), measured after the game "
             "from its record: depending on the goal, the state at the end, every round, or what happened during the game.",
             f"Camps: {camps}. You harvest only where you hold a harvest right (or at an open camp, if your class may play it); stocks regrow, so overharvesting hurts "
             "everyone. [manual: World rules]",
             "Money: barter until a law creates a currency; a backed coin is worth its reserve per coin; unbacked coins are worth 0 at the end. "
             "[manual: World rules]",
             "; ".join([f"Laws: restricted Python ({inst['law_level']})", _constitution_clause(inst)]
                       + ([f"a Board of {_FX.facts(inst)['board_size']} can veto structural and procedural laws"] if has("board") else [])
                       + (["a Fixer patches broken ones"] if has("fixer") else [])) + ". [manual: Law language, Law library]",
             ("Turns: everyone decides at once, then actions run in a shown order. " if sp.get("turns") == "simultaneous" else
              "Turns: agents act one at a time in a shown order. ")
             + "Talk: post (public), dm (private, a few per round, delivered first and answerable within the round). [manual: Private messages]"]
    if on("subsistence"):                                               # review 15 (off: no word), after the camps: never clipped first
        from charter import subsistence as _SB
        lines.insert(2, "Food: " + _SB.overview_line(inst) + ".")
    mods = []
    if on("conflict"):
        mods.append("agents can disable each other (attack with weapons forged from copper; forts of stone; guards): irreversible and "
                    "usually public, but it can serve your goal [manual: Conflict]")
    if on("jurisdictions"):
        mods.append("a law binds only members of the jurisdiction that passed it; jurisdictions can be founded in secret and declared, and agents "
                    "join only by their own choice (pledging to a hidden one they were invited to, or moving to a declared one) [manual: World rules]")
    if on("life"):
        from charter import pairs as _PR
        if _PR.pairs_spec(sp) and not _PR.makers_spec(sp):              # pairs worlds have no Makers: children come from two parents
            kids = ("A child is made by two consenting parents (conceive), each paying food; it has goals of its own and may inherit "
                    "one its parents name [manual: Life and children]")
        else:
            kids = ("Anyone can pay a Maker to make a new agent (commission), choosing its goal, traits and starting holdings: an heir "
                    "to carry your goals on, or a helper built to serve them [manual: Life and children]")
        mods.append("lives are limited (your rounds left are in your state); your goals are scored at the end of the game whether or not "
                    "you are still alive, so what you set up (laws, allies, agents you funded, heirs) keeps counting after you leave, and "
                    "goals about your own holdings or offices count through your living descendants. " + kids)
    if on("media2"):
        mods.append(("outlets publish editions you subscribe to; a public post is a submission to the outlets, whose editors decide whether "
                     "and how to print it (a law can set up an official stream that publishes chosen agents verbatim) [manual: Media]")
                    if (sp.get("media2") or {}).get("submissions") else
                    "outlets publish editions you subscribe to; everyone may post publicly, but an outlet can revoke your posting licence [manual: Media]")
    if (sp.get("projects") or {}).get("enabled", True):
        mods.append("projects are funded together and pay only if they reach their threshold [manual: Projects and tribute]")
    if on("outside_power"):
        mods.append("an outside power demands tribute and raids if unpaid [manual: Projects and tribute]")
    if mods:
        lines.append("Also: " + "; ".join(mods) + ".")
    return "\n".join(lines)


def core_prompt(inst, a, k=None) -> str:
    """The Core layer: the system prompt when the module is on. With a kernel, the manual index and rights are current.
    The "core" layer of charter.sections (rows below, in CORE layout), the spec's and profiles' edits, then `fit`: who the agent
    is, its goal, its actions and the reply format are never cut; the overview of the rules fills what is left of the core budget
    (the full rules are the manual's "World rules" section)."""
    from charter import composition as CP
    from charter import sections as SC
    aid, c = a["id"], cfg(inst)
    rights = k.w["agents"][aid]["rights"] if k is not None and aid in k.w["agents"] else a.get("rights", [])
    v = SC.view(inst, k, a, rights, "core")
    core = v.memo(_core)
    parts = [(key, t) for key, t in CP.apply(inst, a, SC.render("core", v), "core", default_after="goal") if t or key in ("overview", "laws")]
    text, cut = SC.fit("core", v, parts, int(c["budgets"]["core"]))
    if k is not None:
        _st(k, aid)["core"][aid] = {"tokens": tokens(text), "budget": int(c["budgets"]["core"]), "trimmed": cut,
                                    "sections": len(core["manual"])}
    return text


def _core(v) -> dict:
    """The core prompt's shared values, computed once per view: the manual, the lookup mode, the action list and its notes."""
    from charter import action_registry as AR
    from charter import facts as FX
    inst, k, a, aid, c = v.inst, v.k, v.a, v.aid, cfg(v.inst)
    secs = build_manual(inst, k, aid)
    f = v.facts                                                         # the same facts as the manual (lookup mode, memory, ...)
    free = int(c["free_lookups"]) if c["lookup_phase"] and not c["lookups_in_dm_step"] else 0
    fast = f["lookup_mode"] == "dm_step"                                # where the runner really answers lookups in the DM step
    allowed = v.allowed
    pre = [n for n in allowed if AR.REG[n].pre and not AR.REG[n].msg] if (fast or free) else []
    over = FX.purpose_overrides(f)                                      # e.g. post under media2.submissions (as in the manual)
    over.update(AR.purpose_overrides(inst["spec"]))                     # review 14 A: no template names (none by default)
    for nm, n in unread_counts(k, a).items():                           # what the agent has not read yet, shown every turn
        over[nm] = f"{over.get(nm) or AR.purpose(nm)} [{n} unread]"
    pre_all = (pre + [n for n in allowed if AR.REG[n].msg]) if fast else pre   # where the DM step runs, messages are pre-actions too
    pre_note = ""
    if pre_all:
        pre_note = (" Items marked (pre-action) are answered THIS round, before anyone acts: put them in \"lookups\" (each {\"lookup\": "
                    "\"<name>\", \"args_json\": \"<JSON object>\"}) and you are asked again with the results (and any replies), so you can "
                    "read, compute, message and then act in the same round. "
                    + (f"Each uses one of your private-message slots, not an action. " if fast else f"Up to {free} per turn are free. ")
                    + "Put in \"actions\" instead, a look-up uses an action and answers only next turn.")
    return {"manual": secs, "acts": chr(10) + action_sections(allowed, list(v.rights), over or None, set(pre_all), inst["spec"]), "pre_note": pre_note}


# ------------------------------------------------------------------ the core layer's rows (sections.LAYOUTS["core"] order)
from charter import sections as _SC                                    # noqa: E402


@_SC.section("overview", layers=("core",), cut="clip", note='...(more: manual section "World rules")', sep="")
def _overview(v):
    return overview(v.inst)


@_SC.section("identity", layers=("core",))
def _identity(v):
    from charter import agent_rules as AGR                              # spec agent_rules: a scenario's briefing ("" when unset)
    return f"You are {v.aid}. {_class_line(v.inst, v.a)}" + ((" Your roles: " + ", ".join(v.roles) + ".") if v.roles else "") \
        + AGR.line(v.inst, v.aid)


@_SC.section("leverage", layers=("core",))
def _leverage(v):
    return leverage_line(v.inst, v.a, v.roles)


@_SC.section("secret", layers=("core",))
def _secret(v):
    from charter import roles as _RO, hidden as _H
    return "\n".join(x.strip() for x in (_RO.prompt_section(v.inst, v.a), _H.prompt_section(v.inst, v.a)) if x and x.strip())


@_SC.section("goal", layers=("core",))
def _goal(v):
    g = v.a["goal"]
    return "Your private goal: " + (g["text"] if not g.get("fixed") else (g.get("text") or "see your role above"))


@_SC.section("strategy", layers=("core",))
def _strategy(v):
    return STRATEGY_TEXT if v.a.get("strategy_prompt") else ""


@_SC.section("temperament", layers=("core",))
def _temperament(v):
    inst, a = v.inst, v.a
    models = ("\nOther agents' models: " + ", ".join(f"{x['id']}={x['model']}" for x in inst["agents"] if x["id"] != v.aid)) \
        if inst["conditions"].get("model_identity_visible") else ""
    return (("Your temperament: " + a["personality_text"]) if a.get("personality_text") else "") + models


@_SC.section("memory", layers=("core",), sep="\n\n")
def _memory(v):
    return f"""Memory: every turn you see only this prompt: your state, what changed since your last turn, your own last {v.facts['memory_turns']} turns, your
scratchpad, media you read, pinned files and what you look up. Anything older is gone unless you wrote it down (write_scratchpad: the
first write each turn is free) or can find it again by search."""


@_SC.section("lookups", layers=("core",))
def _lookups(v):
    c = cfg(v.inst)
    if c["explore_nudge"] and not c.get("closing", True):
        return ("Look beyond the obvious: other avenues, strategies, alliances and resources may serve your goal better, and "
                "understanding your capabilities and the world better (your manual, the archive, other agents) often reveals moves "
                "others miss.")
    return ""


def _nature(inst) -> bool:
    from charter import jurisdictions as _J
    return _J.nature_start(inst["spec"])


@_SC.section("actions", layers=("core",), sep="\n\n")
def _actions(v):
    inst, a, c, core = v.inst, v.a, cfg(v.inst), v.memo(_core)
    return (f"""ACTIONS (you have {a['actions']} per turn; each item in "actions" uses one; details in your manual).{core['pre_note']}{core['acts']}"""
            + ("\n" + FULL_TURN_TEXT if c.get("full_turn_nudge", True) and not c.get("closing", True) else "")
            + ("\nYou cannot propose laws yourself: a law you draft must be proposed by a holder of the propose right (a Legislator)."
               if "propose" not in v.rights and inst["law_level"] != "L0" and a["cls"] not in ("board", "fixer")
               and not _nature(inst) else ""))           # a state of nature: a jurisdiction's members propose its laws without it


@_SC.section("manual_index", layers=("core",), sep="\n\n")
def _manual_index(v):
    return "Your manual (only titles here; fetch a section with the manual lookup):\n" + manual_index(v.memo(_core)["manual"])


@_SC.section("reply", layers=("core",), sep="\n\n")
def _reply(v):
    n = v.a["actions"]
    return f"""Reply with a JSON object with these fields:
- "reasoning": a short explanation of your plan for this turn.
- "lookups": your pre-actions (marked above), answered before you act, or [].
- "actions": a list of up to {n} actions, each {{"action": "<name>", "args_json": "<the arguments as a JSON object string>"}}.
- "goal_guesses_json": on the final round, a JSON object mapping each other agent to the goal name from the goals section of your
  manual that best fits what they did; on other rounds, "{{}}"."""


# ------------------------------------------------------------------ the turn prompt
OFFICIAL = set(ET.names(feed="official"))                             # feed priority 5 (announcements)
POSTS = set(ET.names(feed="post"))                                     # feed priority 4 or 6
OWN_RESULTS = ET.names("own")                                           # your own are in "Your last turns", not your feed
PRIORITY_NAMES = {1: "events", 2: "results of your actions", 3: "messages to you", 4: "posts mentioning you", 5: "announcements", 6: "posts"}
POINTERS = {3: "search_dms", 4: "search_board", 6: "search_board"}


def _priority(k, aid, e) -> int:
    """1 events, 2 your own, 3 DMs to you, 4 posts naming you, 5 announcements, 6 other posts and DMs. The type's `feed` comes from
    the event-type registry, whose lookup fails on an unregistered type (which used to get 1, the highest, by default)."""
    t, d = e["type"], e["data"]
    feed = ET.get(t).feed
    if e["agent"] == aid:
        return 2
    if feed == "message":
        return 3 if d.get("to") == aid else 6
    if t in POSTS:
        said = f"{d.get('headline', '')} {d.get('text', '')}"
        return 4 if re.search(rf"(?<!\w){re.escape(aid)}(?!\w)", said) else 6
    return ET.PRIORITY[feed]


def feed_layer(k, aid, since, budget) -> tuple[str, int, dict]:
    """The Feed layer: (text, cursor, record). Items over budget are dropped deterministically by priority, newest kept first."""
    from charter import agents as AG
    c = cfg(k)
    digest_only = k.spec["conditions"].get("feed_mode") == "digest_only"
    items = []
    new, upd = manual_changes(k, aid)
    if new or upd:
        items.append((1, len(k.events), "Your manual " + "; ".join(
            x for x in (("has new sections: " + ", ".join(new)) if new else "", ("has updated sections: " + ", ".join(upd)) if upd else "") if x)
            + " (fetch with the manual lookup)."))
    from charter import channels as CH
    pull = CH.pull(k)                                                   # channels.v2, pull: channel posts are counted, not pushed
    for i, e in enumerate(k.events[since:], since):
        if not k.can_see(aid, e):
            continue
        if pull and CH.pulled(k, aid, e):
            continue
        if digest_only and e["type"] == "post" and e["agent"] != aid:
            continue
        if e["agent"] == aid and e["type"] in OWN_RESULTS:
            continue                                                    # your own actions are in "Your last turns"
        s = AG.render_event(k, e, aid)
        if not s:
            continue
        p = _priority(k, aid, e)
        cap = c["dm_tokens"] if p == 3 else c["post_tokens"] if p in (4, 6) else c["item_tokens"]
        s = clip(s, int(cap), f"...(cut: {POINTERS.get(p, 'search_board')} \"{e['id']}\")" if p in POINTERS else "...(cut)")[0]
        items.append((p, i, s))
    room = budget - 60                                                  # room for the pointer lines
    keep, dropped = [], {}
    for p, i, s in sorted(items, key=lambda x: (x[0], -x[1])):
        t = tokens(s) + 1
        if t <= room:
            keep.append((i, p, s))
            room -= t
        else:
            dropped[p] = dropped.get(p, 0) + 1
    lines = [s for _, _, s in sorted(keep, key=lambda x: (x[0], x[1]))]
    for p, n in sorted(dropped.items()):
        lines.append(f"({n} older {PRIORITY_NAMES[p]} not shown" + (f": {POINTERS[p]})" if p in POINTERS else ")"))
    text = "\n".join(lines) or "(nothing new)"
    rec = {"tokens": tokens(text), "budget": budget, "items": len(items), "shown": len(keep),
           "dropped": {PRIORITY_NAMES[p]: n for p, n in sorted(dropped.items())},
           "by_priority": {PRIORITY_NAMES[p]: sum(1 for x in items if x[0] == p) for p in sorted({x[0] for x in items})}}
    return text, len(k.events), rec


def _optional(module, fn, *args):
    try:
        mod = importlib.import_module(f"charter.{module}")
    except ModuleNotFoundError as e:
        if e.name == f"charter.{module}":
            return None
        raise
    f = getattr(mod, fn, None)
    return f(*args) if callable(f) else None


def state_layer(k, a, order, n_actions, simultaneous, budget) -> tuple[str, dict]:
    from charter import agents as AG
    aid = a["id"]
    pos = order.index(aid) + 1
    when = (f"Everyone decides now, at the same time; actions then run in this order: {', '.join(order)} (yours run {pos} of {len(order)})."
            if simultaneous else f"Order this round: {', '.join(order)} (you are {pos} of {len(order)}).")
    dmc = k.spec.get("dm_step") or {}
    lim = f"{k.dm_limit(aid)}{AG.dm_source(k, aid)}"
    extra = (f", plus at most {lim} private messages (dm) this round, replies included; they are delivered first and can be answered within the round"
             if simultaneous and dmc.get("enabled") and k.spec["channels"].get("dm", True) else
             f" (at most {lim} of them can be private messages)" if k.spec["channels"].get("dm", True) else "")
    lines = [f"Round {k.r + 1} of {k.inst['rounds']}. {when} You have {n_actions} actions this turn{extra}."]
    lines += AG.state_view(k, aid).split("\n")
    if (k.spec.get("jurisdictions") or {}).get("enabled") and not any(l.startswith("Your jurisdiction") for l in lines):
        j = _optional("jurisdictions", "member_of", k, aid)                # (the module's own state line usually says it already)
        lines.append(f"Your jurisdiction: {j or 'none (no law binds or protects you)'}.")
    if (k.spec.get("life") or {}).get("enabled"):
        left = _optional("life", "rounds_left", k, aid)
        if left is not None:
            lines.append(f"Rounds of life left: {left}.")
    lines.append(memory_line(k, aid))
    text, dropped = _clip_lines(lines, budget, "lines of state")
    return text, {"tokens": tokens(text), "budget": budget, "lines": len(lines), "dropped_lines": dropped}


def recent_layer(k, aid, budget) -> tuple[str, dict]:
    """The agent's own last turns, newest first. A run of turns with the same kinds of action is one line (the repetition shows)."""
    turns = list(reversed(_st(k, aid)["recent"].get(aid, [])))      # newest first
    kinds = lambda t: tuple(x.split(" ", 1)[0] for x in t["actions"])
    groups, i = [], 0
    while i < len(turns):
        j = i
        while j + 1 < len(turns) and kinds(turns[i]) and kinds(turns[j + 1]) == kinds(turns[i]):
            j += 1
        groups.append(turns[i:j + 1])
        i = j + 1
    out, used, dropped = [], 0, 0
    for g in groups:
        t = g[0]
        acts = "; ".join(t["actions"]) or "(no actions)"
        res = "\n".join("  " + clip(x, 150, "...(full text in Lookups)" if x.split(":", 1)[0] in LOOKUPS else "...(cut)")[0]
                        for x in t["results"]) or "  (no results)"
        if len(g) > 1:
            head = (f"Rounds {g[-1]['round'] + 1}-{t['round'] + 1}: the same kinds of action {len(g)} turns running "
                    f"({', '.join(kinds(t))}). The latest, round {t['round'] + 1}: {acts}")
        else:
            head = f"Round {t['round'] + 1}: {acts}"
        s = f"{head}\n{res}"
        room = budget - used - 20
        if dropped or room < 60:
            dropped += len(g)
            continue
        s, _ = clip(s, room)
        out.append(s)
        used += tokens(s) + 1
    if dropped:
        out.append(f"({dropped} older turn(s) not shown)")
    text = "\n".join(out) or "(none yet)"
    return text, {"tokens": tokens(text), "budget": budget, "turns": len(turns), "dropped_turns": dropped}


def turn_prompt(k, a: dict, order: list, since: int, n_actions: int, final: bool, simultaneous: bool = False) -> tuple[str, int]:
    """The per-turn prompt from the fixed layers (the core layer is the system prompt). Stores the layer record for reasoning.jsonl."""
    aid, c = a["id"], cfg(k)
    b = c["budgets"]
    init_agent(k, aid)
    st = _st(k, aid)
    rec = {}
    state, rec["state"] = state_layer(k, a, order, n_actions, simultaneous, int(b["state"]))
    feed, cursor, rec["feed"] = feed_layer(k, aid, since, int(b["feed"]))
    recent, rec["recent"] = recent_layer(k, aid, int(b["recent"]))
    pad, cut = clip(k.w["scratchpad"][aid], scratchpad_size(k, aid))
    rec["scratchpad"] = {"tokens": tokens(pad), "budget": scratchpad_size(k, aid), "trimmed": cut}
    from charter import media
    eds = list(media.editions_for(k, aid) or [])[:int(c["media_outlets"])]
    med = [clip(x, int(b["media"]) + tokens(x.split("\n", 1)[0]))[0] for x in eds]     # the label line does not eat the edition
    rec["media"] = {"tokens": sum(tokens(x) for x in med), "budget": int(b["media"]) * int(c["media_outlets"]), "editions": len(med)}
    pins = [(n, f) for n, f in sorted(k.w["files"][aid].items()) if f["pinned"]][:pin_limit(k, aid)]
    pinned = [f"File {n} ({f['origin']}):\n" + clip(f["text"], int(b["pinned"]))[0] for n, f in pins]
    rec["pinned"] = {"tokens": sum(tokens(x) for x in pinned), "budget": int(b["pinned"]) * pin_limit(k, aid), "files": [n for n, _ in pins]}
    carry = [clip(x, int(b["lookup"]))[0] for x in st["carry"].get(aid, [])]
    fetched = st["fetched"].get(aid)
    got = [f"{x['name']} {json.dumps(x['args'])}:\n{x['text']}" for x in (fetched or [])]
    rec["lookups"] = {"tokens": sum(tokens(x) for x in carry + got), "budget": int(b["lookup"]) * (len(carry) + max(len(got), 1)),
                      "carried": len(carry), "fetched": len(got)}
    parts = ["## State\n" + state, "## What changed since your last turn\n" + feed, "## Your last turns (newest first)\n" + recent,
             f"## Your scratchpad ({tokens(pad)} of {scratchpad_size(k, aid)} tokens)\n" + (pad or "(empty)")]
    if med:
        parts.append("## Media (written by other agents)\n" + "\n\n".join(med))
    if pinned:
        parts.append("## Pinned files\n" + "\n\n".join(pinned))
    from charter import directories as DR
    dirs = DR.turn_section(k, aid) if DR.enabled(k) else ""
    if dirs:                                                            # directories the agent can reach (owner or grantee)
        parts.append("## Your directories\n" + dirs)
        rec["directories"] = {"tokens": tokens(dirs)}
    if carry:
        parts.append("## Lookups you paid for last turn\n" + "\n\n".join(carry))
    if fetched is not None:
        parts.append(FETCHED_HEADER + "\n" + "\n\n".join(got))
    if final:
        parts.append("This is the final round. In goal_guesses_json, map each other agent to the goal name from the list that best fits what they did.")
    if fetched is not None:
        parts.append("Your free lookups for this turn are used: reply with your actions now (\"lookups\" is ignored; a further lookup "
                     "costs an action: put it in \"actions\").")
    elif c["lookup_phase"] and int(c["free_lookups"]) > 0 and not c["lookups_in_dm_step"]:
        parts.append(f"Act now, or first list up to {c['free_lookups']} free lookups in \"lookups\" (with \"actions\" empty) to be asked "
                     "again with their results.")
    if c.get("closing", True):                                          # the last thing the agent reads before deciding
        parts.append(closing_block(k, a, n_actions, final))
    text = "\n\n".join(parts)
    core = st["core"].get(aid) or {}
    rec["core"] = core
    rec["total_tokens"] = tokens(text) + int(core.get("tokens", 0))
    st["layers"][aid] = rec
    return text, cursor


def _short_goal(a) -> str:
    """The agent's goal in a sentence or two (the full text is in the system prompt)."""
    g = a.get("goal") or {}
    if g.get("fixed"):
        return (g.get("text") or "see your role").split(". ")[0] + "."
    t = re.sub(r"\s+", " ", str(g.get("text") or ""))
    parts = re.findall(r"(Primary goal[^:]*:[^.]*\.|Secondary goal[^:]*:[^.]*\.|Third goal[^:]*:[^.]*\.)", t)
    out = " ".join(parts) if parts else t[:300]
    return out if out.endswith(".") else out + "."


def situation_lines(k, a, n_actions) -> list:
    """The facts that matter most this turn: limits, time, holdings, what is waiting for a decision."""
    aid = a["id"]
    from charter import agents as AG
    left = max(0, int(k.spec["rounds"]) - k.r)
    lines = [f"Round {k.r + 1} of {k.spec['rounds']} ({left} left, this one included). This turn: {n_actions} actions and "
             f"{max(0, k.dm_limit(aid) - k.w.get('dm_sent', {}).get(aid, 0))} private messages (of {k.dm_limit(aid)} this round{AG.dm_source(k, aid)})."]
    try:
        from charter import life as _LF
        if _LF.enabled(k.spec) and "life" in k.w:
            life = [l for l in _LF.state_lines(k, aid) if l.startswith("Your lifespan")]
            lines += life[:1]
    except Exception:
        pass
    hold = k.w["agents"][aid]["holdings"]
    lines.append("You hold: " + (", ".join(f"{q:g} {i}" for i, q in sorted(hold.items()) if q > 1e-9) or "nothing")
                 + f" (value {k.holdings_value(aid):.4g}).")
    bal = [b for b in k.w["ballots"].values() if b["status"] == "open" and aid in b["electorate"] and aid not in b["votes"]]
    if bal:
        lines.append(f"Ballots waiting for your vote: {', '.join(b['id'] for b in bal)}.")
    try:
        from charter import outside as _O
        t = _O.status(k) if (k.spec.get("outside_power") or {}).get("enabled") else {}
        if t.get("open"):
            lines.append(f"Tribute {t['id']} due by the end of round {t['deadline'] + 1}: still owed {t['remaining']}; unpaid means a raid.")
    except Exception:
        pass
    try:
        from charter import media as _MD
        if _MD.enabled(k):
            subs = [k.w["media"]["outlets"][o]["name"] for o in k.w["media"]["subs"].get(aid, []) if o in k.w["media"]["outlets"]]
            others = [o["name"] for o in _MD.private_outlets(k) if o["name"] not in subs and o["editor"] != aid]
            if subs or others:
                lines.append(f"You read: {', '.join(subs) or 'no outlet'}" + (f"; you could also read {', '.join(others)} (subscribe)" if others else "") + ".")
    except Exception:
        pass
    return lines


def closing_block(k, a, n_actions, final) -> str:
    """Ends every turn prompt: the agent's situation, then a reminder of its goal and of how to use a turn well."""
    aid = a["id"]
    mem = memory_turns(k, aid)
    sit = "## Your situation\n" + "\n".join(situation_lines(k, a, n_actions))
    scholar = bool((k.w.get("roles") or {}).get("scholar"))
    nudge = (f"## Before you act\nYour goal: {_short_goal(a)}\n"
             f"Use this turn for it. Any of your {n_actions} actions you do not use are wasted, and so are unused messages. Think "
             "strategically: what would move your score most from here? If you have no plan, make one and write it down. If you don't "
             "know what to do, explore: actions you have not tried (your edge first), your manual, the world and other agents "
             "(Scientists hold knowledge), better routes to your goal; coordinate, bargain and trade.\n"
             f"Memory: you see only your last {mem} turns. Anything you do not write down (write_scratchpad, a file"
             + (", or memory bought from the Scholar" if scholar else "") + f") is forgotten within {mem} rounds: plans, deals, promises, "
             "who owes you what.")
    if final:
        nudge += "\nThis is the final round: whatever you leave undone now will not count."
    return sit + "\n\n" + nudge


def memory_turns(k, aid) -> int:
    """How many of its own past turns this agent sees (drawn per agent from context.memory_turns, else context.recent_turns)."""
    a = next((x for x in k.inst["agents"] if x["id"] == aid), {})
    return int(a.get("memory_turns") or cfg(k)["recent_turns"])


def record_fields(k, aid) -> dict:
    """Extra fields for this agent's reasoning.jsonl rows ({} when the module is off)."""
    if not enabled(k):
        return {}
    return {"context": copy.deepcopy(_st(k)["layers"].get(aid))}


def lookup_records(k, aid) -> list:
    """The free lookups fetched this turn, for the lookup row in reasoning.jsonl (text cut for the log)."""
    return [{**{x: y for x, y in r.items() if x != "text"}, "text": str(r.get("text", ""))[:1500]} for r in _st(k)["fetched"].get(aid, [])]


def record_turn(k, aid, acts: list, results: list) -> None:
    """After a turn runs: keep it for the Recent layer, carry paid lookups' text to the next Lookups layer, note the manual titles
    the agent has now seen, and clear this turn's fetched lookups."""
    if not enabled(k):
        return
    c = cfg(k)
    st = _st(k, aid)
    rows = st["recent"].setdefault(aid, [])
    rows.append({"round": k.r, "actions": [f"{x.get('action')} {str(x.get('args_json', ''))[:300]}" for x in acts],
                 "results": [str(x)[:2000] for x in results]})
    del rows[:-memory_turns(k, aid)]
    st["carry"][aid] = [str(x) for x in results if str(x).split(":", 1)[0] in LOOKUPS and not str(x).split(":", 1)[1].strip().startswith("ERROR")][:3]
    st["manual_titles"][aid] = {t: _digest(x) for t, x in build_manual(k.inst, k, aid)}
    st["fetched"].pop(aid, None)


def truth(k, inst=None) -> dict:
    return {"context": _truth(k)} if enabled(k) else {}               # ground_truth.json["context"] (only when on)


def _truth(k) -> dict:
    """For ground_truth.json: which manual sections each agent read (and how often), and every agent's files at the end."""
    st = _st(k)
    return {"manual_reads": copy.deepcopy(st.get("manual_reads", {})),
            "files": {aid: {n: {"tokens": f["tokens"], "pinned": f["pinned"], "origin": f["origin"]} for n, f in fs.items()}
                      for aid, fs in (k.w.get("files") or {}).items()},
            "scratchpad_tokens": {aid: tokens(t) for aid, t in (k.w.get("scratchpad") or {}).items()},
            "library_tokens": _library_tokens(k)}


def _library_tokens(k) -> dict:
    """Tokens each author has deposited in Scholars' libraries (documents still there at the end)."""
    out = {}
    for d in ((k.w.get("scholars") or {}).get("docs") or {}).values():
        out[d.get("author")] = out.get(d.get("author"), 0) + tokens(d.get("text", ""))
    return out


# ------------------------------------------------------------------ scripted bots (dry runs)
def scripted(k, a, out: dict, user: str) -> dict:
    """ScriptedPolicy's extra behaviour with the module on: sometimes ask for lookups first, keep a scratchpad, write and pin files,
    and pay for a lookup now and then. Own RNG stream."""
    if a["cls"] == "observer" or "private messages have arrived before anyone's actions" in user:
        return out
    aid = a["id"]
    second = FETCHED_HEADER in user
    rng = random.Random(f"{k.inst['seed']}|context|{k.r}|{aid}|{int(second)}")
    out = {**out, "lookups": []}
    if not second and cfg(k)["lookup_phase"] and rng.random() < 0.5:
        titles = [t for t, _ in build_manual(k.inst, k, aid)]
        out["lookups"] = [{"lookup": "manual", "args_json": json.dumps({"section": rng.choice(titles)})},
                          {"lookup": "search_board", "args_json": json.dumps({"query": rng.choice([aid, "timber", "law"])})},
                          {"lookup": "search_dms", "args_json": json.dumps({"query": "agreed"})}]
        out["actions"] = []
        return out
    acts = list(out.get("actions") or [])
    acts.insert(0, {"action": "write_scratchpad", "args_json": json.dumps({"text": f"r{k.r + 1}: planned {len(acts)} actions.", "mode": "append"})})
    roll = rng.random()
    files = sorted(k.w["files"].get(aid, {}))
    if roll < 0.3 and space_left(k, aid) >= 60:
        acts.append({"action": "write_file", "args_json": json.dumps({"name": f"log{k.r % 3}", "text": f"Round {k.r + 1} log of {aid}. " * 8})})
    elif roll < 0.45 and files:
        acts.append({"action": "pin", "args_json": json.dumps({"name": files[0]})})
    elif roll < 0.6:
        acts.append({"action": "search_board", "args_json": json.dumps({"query": "timber stone"})})
    out["actions"] = acts
    return out


def unread_counts(k, a) -> dict:
    """{action: how many it has not read}: manual sections never fetched, and (Scientists) held archive documents never read."""
    if k is None or a["id"] not in k.w["agents"]:
        return {}
    aid, out = a["id"], {}
    init_agent(k, aid)
    secs = [t for t, _ in build_manual(k.inst, k, aid)]
    read = set(_st(k, aid)["manual_reads"].get(aid, {}))
    if secs:
        out["manual"] = sum(1 for t in secs if t not in read)
    held = [d for d in (a.get("archive_docs") or []) if d != "README"]
    if held and "archive" in k.w["agents"][aid]["rights"]:
        seen = {str(e["data"].get("doc")).removesuffix(".md").strip("/") for e in k.events if e["type"] == "archive_read" and e["agent"] == aid}
        out["read_archive"] = sum(1 for d in held if d not in seen)
    return {nm: n for nm, n in out.items() if n}
