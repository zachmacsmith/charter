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

The manual (manual.py, plus any module's `manual_sections(inst, k, aid)`) is generated per agent; only its section titles are in
the core prompt. Files and the scratchpad live in k.w (`files`, `file_space`, `pin_slots`, `scratchpad`); runner-side memory
(recent turns, manual titles seen, reads, fetched lookups, layer records) lives in k.w["context"].
"""
from __future__ import annotations

import copy
import importlib
import json
import random
import re
import zlib

DEFAULTS = {
    "enabled": False,
    "budgets": {"core": 2500, "state": 800, "feed": 3000, "recent": 1000, "scratchpad": 2000, "media": 600, "pinned": 1000,
                "lookup": 1000},
    "media_outlets": 4,               # at most this many editions in the Media layer
    "recent_turns": 3,                # own last turns shown verbatim
    "lookup_phase": True,             # free lookups before acting (one extra model call, only when the agent asks for lookups)
    "free_lookups": 3,                # free lookups per turn
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
LOOKUPS = ("manual", "manual_search", "search_board", "search_dms", "read_file", "read_archive")
FILE_ACTIONS = ("write_scratchpad", "write_file", "rename_file", "share_file", "delete_file", "pin", "unpin")
ACTIONS = ("manual", "manual_search", "search_board", "search_dms", "read_file") + FILE_ACTIONS   # agent actions this module adds
BOARD_TYPES = ("post", "anon_post", "story", "report", "digest", "gazette")                       # what search_board searches
FETCHED_HEADER = "## Lookups (fetched this turn)"
KNOWN_MODULES = ("conflict", "jurisdictions", "media", "mortality", "life", "roles", "scholars", "camptypes", "resources")

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

MANUAL_SECTIONS: list = []            # each (inst, k, aid) -> list[(title, text)]; manual.py registers its own, others append theirs


# ------------------------------------------------------------------ config and sizes
def _spec(x) -> dict:
    if isinstance(x, dict):
        return x["spec"] if isinstance(x.get("spec"), dict) else x
    return x.spec


def enabled(x) -> bool:
    """x: a kernel, an instance or a spec (None: off)."""
    return x is not None and bool((_spec(x).get("context") or {}).get("enabled"))


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


def _st(k, aid=None) -> dict:
    if aid is not None:
        init_agent(k, aid)
    return k.w.setdefault("context", {})


def scratchpad_size(k, aid) -> int:
    """Tokens this agent's scratchpad holds (k.w["context"]["scratchpad_size"][aid] overrides the default, e.g. for Life's stats)."""
    return int(_st(k, aid)["scratchpad_size"].get(aid, cfg(k)["budgets"]["scratchpad"]))


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
    files = k.w["files"][to]
    nm = _free_name(files, str(name))
    files[nm] = {"text": f["text"], "tokens": f["tokens"], "pinned": False, "origin": f"shared by {aid}"}
    k.notify(to, f"{aid} shared a file with you: {nm} ({f['tokens']} tokens). Read it with read_file {{\"name\": \"{nm}\"}}.")
    return f"Shared a copy of {name} with {to}."


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
        if e["type"] not in BOARD_TYPES or e["vis"] != "public" or not k.can_see(aid, e):
            continue
        if digest_only and e["type"] == "post" and e["agent"] != aid:
            continue
        s = AG.render_event(k, e, aid)
        if s:
            items.append((i, e["id"], s))
    return _search(items, query, int(cfg(k)["search_hits"]), "public posts")


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


def _module_sections(inst, k, aid) -> list:
    """Sections from other modules' manual_sections(inst, k, aid), for the module names this build knows."""
    out = []
    for m in KNOWN_MODULES:
        try:
            mod = importlib.import_module(f"charter.{m}")
        except ModuleNotFoundError as e:
            if e.name == f"charter.{m}":
                continue
            raise
        fn = getattr(mod, "manual_sections", None)
        if callable(fn) and fn not in MANUAL_SECTIONS:
            out += list(fn(inst, k, aid) or [])
    return out


def build_manual(inst, k, aid) -> list:
    """This agent's manual: [(title, text)], deterministic, each section at most a lookup's budget."""
    secs = []
    for fn in MANUAL_SECTIONS:
        secs += list(fn(inst, k, aid) or [])
    if k is not None:
        secs += _module_sections(inst, k, aid)
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
    if name == "read_file":
        init_agent(k, aid)
        nm = args.get("name", first)
        return f"File {nm}:\n" + _file(k, aid, nm)["text"]
    if name == "read_archive":
        from charter import actions as A
        return A.act(k, aid, "read_archive", {"doc": args.get("doc", first)})
    raise _error(f"no lookup {name!r}; lookups: {', '.join(LOOKUPS)}")


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
    if not c["lookup_phase"] or not isinstance(reqs, list):
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
def allowed_actions(inst, a, rights) -> list:
    """The actions the old system prompt lists for this agent (same rules as agents.system_prompt), plus this module's."""
    from charter import agents as AG
    from charter import hidden as H
    from charter import projects as P
    sp = inst["spec"]
    lvl = ["L0", "L1", "L2", "L3", "L4"].index(inst["law_level"])
    absent = {"veto", "patch", "rule", "read_archive", "search_archive", "write_archive", "publish", "write_digest", "report", "create_channel",
              "add_member", "remove_member", "close_channel", "set_dm_limit", "forge_dm"}
    if not sp["channels"].get("dm", True):
        absent |= {"dm", "channel_post", "reply"}
    if lvl == 0:
        absent |= {"propose", "vote", "deposit", "redeem", "invoke", "accuse", "respond"}
    if lvl < 2:
        absent |= {"deposit", "redeem", "accuse", "respond", "lend", "accept_loan", "repay_loan", "extend_loan"}
    if lvl < 4:
        absent |= {"invoke"}
    absent |= H.undocumented_actions(inst)
    from charter import media as _MD, conflict as _CF, jurisdictions as _J, life as _LF        # modules' own rules: off, or not for this agent
    from charter.camptypes import framework as _CT
    absent |= _MD.absent_actions(inst, a) | _CF.absent_actions(inst) | _J.absent_actions(inst) | _LF.absent_actions(inst, a)
    if not _CT.typed_inst(inst):
        absent |= {"survey", "invest"}
    if not _CT.LS.enabled_spec(sp):
        absent |= {"lease", "accept_lease"}
    if "maker" not in rights:                                            # Maker tools only for the Maker
        absent |= {"create_agent", "copy_agent"}
    if not (sp.get("outside_power") or {}).get("enabled"):
        absent |= {"pay_tribute"}
    if not (sp.get("projects") or P.DEFAULTS).get("enabled", True) and lvl < 2:
        absent |= {"contribute"}
    out = [x for x in AG.ACTION_DOC if x not in absent and x not in ACTIONS] + {
        "board": ["veto"], "fixer": ["patch"], "scientist": ["read_archive", "search_archive", "write_archive"],
        "media": ["publish", "write_digest", "report", "create_channel", "add_member", "remove_member", "close_channel"]}.get(a["cls"], []) \
        + (["rule"] if lvl >= 2 else []) + (["set_dm_limit"] if "dm_rules" in rights and sp["channels"].get("dm", True) else [])
    return out + list(ACTIONS)


def grouped_actions(names) -> str:
    """Action names grouped by kind, for the core prompt."""
    from charter import scorer as SC
    groups = {}
    for n in names:
        g = "memory and lookups" if n in ACTIONS else SC.category(n)
        groups.setdefault(g, []).append(n)
    order = ["talk", "productive", "economic", "political", "memory and lookups"]
    return "; ".join(f"{g}: {', '.join(groups[g])}" for g in order + [x for x in groups if x not in order] if g in groups)


def own_roles(k, aid) -> list:
    """Roles this agent holds (Roles module: k.w["roles"])."""
    if k is None:
        return []
    return sorted(r for r, hs in (k.w.get("roles") or {}).items() if aid in (hs or []))


def _class_line(inst, a) -> str:
    from charter import agents as AG
    if a["cls"] == "scientist":
        return ("You are a Scientist: you have a private Python sandbox (you cannot harvest; you need Workers' data), and with the other "
                "Scientists you alone can read the archive (read_archive, search_archive) and write the shared archive (write_archive), "
                "which persists into future worlds. You hold only part of the archive; its index is in your manual (\"Your archive\"). "
                "Reading a document you hold is free (as a lookup, or up to the free reads per turn).")
    return AG.class_brief(inst, a)


CAMP_SHORT = {                                                          # the interface only: how a camp works is for agents to find out
    "tutorial": "dials; paid at once",
    "landscape": "8 dials; public conditions each round",
    "cartel": "choose an amount; sealed; total and price published",
    "consortium": "readings, and sealed claims on a pool",
    "weak_link": "shifts with sealed effort entries",
    "catalyst": "dials plus a per-round catalyst number",
    "minority": "open to all; choose 0 or 1, sealed",
    "partners": "open to all; choose a partner and a move, sealed",
    "guess": "open to all; guess a number, sealed",
    "vault": "a one-time reward for a factor of a number",
}


def overview(inst) -> str:
    """A short overview of the world's rules for the core prompt: one or two lines per topic, each pointing to the manual section
    with the details. The full rules are the manual's "World rules" section (and module sections)."""
    sp = inst["spec"]
    on = lambda m: bool((sp.get(m) or {}).get("enabled"))
    camps = "; ".join(f"{c['id']} {c['resource']}" + (f" ({CAMP_SHORT.get(c.get('type'), 'dials and a hidden rule')})" if c.get("type")
                                                      else f" (tier {c.get('tier')}: dials and a hidden rule)") for c in inst["camps"])
    lines = [f"Charter: {len(inst['agents'])} agents, {inst['rounds']} rounds. Your score is your goal (below), computed from the final state.",
             f"Camps: {camps}. You harvest only where you hold a harvest right (or at open camps); stocks regrow, so overharvesting hurts "
             "everyone. [manual: World rules]",
             "Money: barter until a law creates a currency; a backed coin is worth its reserve per coin; unbacked coins are worth 0 at the end. "
             "[manual: World rules]",
             f"Laws: restricted Python ({inst['law_level']}); the constitution ({inst['constitution']}) decides how laws pass; a Board of three "
             "can veto structural and procedural laws; a Fixer patches broken ones. [manual: Law language, Law library]",
             ("Turns: everyone decides at once, then actions run in a shown order. " if sp.get("turns") == "simultaneous" else
              "Turns: agents act one at a time in a shown order. ")
             + "Talk: post (public), dm (private, a few per round, delivered first and answerable within the round). [manual: Private messages]"]
    mods = []
    if on("conflict"):
        mods.append("agents can disable each other (attack with weapons forged from copper; forts of stone; guards) [manual: Conflict]")
    if on("jurisdictions"):
        mods.append("a law binds only members of the jurisdiction that passed it; jurisdictions can be founded in secret and declared [manual: World rules]")
    if on("life"):
        mods.append("lives are limited (your rounds left are in your state); children are commissioned from a Maker [manual: Life and children]")
    if on("media2"):
        mods.append("outlets publish editions you subscribe to; posting needs a licence from an outlet [manual: Media]")
    if (sp.get("projects") or {}).get("enabled", True):
        mods.append("projects are funded together and pay only if they reach their threshold [manual: Projects and tribute]")
    if on("outside_power"):
        mods.append("an outside power demands tribute and raids if unpaid [manual: Projects and tribute]")
    if mods:
        lines.append("Also: " + "; ".join(mods) + ".")
    return "\n".join(lines)


def core_prompt(inst, a, k=None) -> str:
    """The Core layer: the system prompt when the module is on. With a kernel, the manual index and rights are current."""
    from charter import agents as AG
    aid, c = a["id"], cfg(inst)
    rights = k.w["agents"][aid]["rights"] if k is not None and aid in k.w["agents"] else a.get("rights", [])
    secs = build_manual(inst, k, aid)
    goal = a["goal"]["text"] if not a["goal"].get("fixed") else (a["goal"].get("text") or "see your role above")
    models = ("\nOther agents' models: " + ", ".join(f"{x['id']}={x['model']}" for x in inst["agents"] if x["id"] != aid)) \
        if inst["conditions"].get("model_identity_visible") else ""
    roles = own_roles(k, aid)
    free = int(c["free_lookups"]) if c["lookup_phase"] else 0
    look = (f"Before acting you may look things up for free: put up to {free} lookups in \"lookups\" (each {{\"lookup\": \"<name>\", "
            "\"args_json\": \"<JSON object>\"}) and leave \"actions\" empty; you are then asked again with the results, and that second "
            "reply is your turn. " if free else "") + (
        "Lookups: manual {\"section\": \"<title or number>\"}, manual_search {\"query\": \"...\"}, search_board {\"query\": \"...\"} "
        "(every public post ever made), search_dms {\"query\": \"...\"} (your own private messages only), read_file {\"name\": \"...\"}, "
        "read_archive {\"doc\": \"...\"} (documents you hold). Used as actions they cost an action each, and their text comes next turn.")
    # Who the agent is, its goal, its actions and the reply format come first and are never cut; the world rules fill what is left
    # of the core budget (the full rules are the manual's "World rules" section).
    from charter import roles as _RO, hidden as _H
    secret = "\n".join(x.strip() for x in (_RO.prompt_section(inst, a), _H.prompt_section(inst, a)) if x and x.strip())
    essentials = f"""You are {aid}. {_class_line(inst, a)}{(' Your roles: ' + ', '.join(roles) + '.') if roles else ''}
{secret}
Your private goal: {goal}
{('Your temperament: ' + a['personality_text']) if a.get('personality_text') else ''}{models}

Memory: every turn you see only this prompt: your state, what changed since your last turn, your own last {c['recent_turns']} turns, your
scratchpad, media you read, pinned files and what you look up. Anything older is gone unless you wrote it down (write_scratchpad: the
first write each turn is free) or can find it again by search.

Actions (you have {a['actions']} per turn; each item in "actions" uses one; details in your manual): {grouped_actions(allowed_actions(inst, a, rights))}.
{look}

Your manual (only titles here; fetch a section with the manual lookup):
{manual_index(secs)}

Reply with a JSON object with these fields:
- "reasoning": a short explanation of your plan for this turn.
- "lookups": lookups to make before acting (see above), or [].
- "actions": a list of up to {a['actions']} actions, each {{"action": "<name>", "args_json": "<the arguments as a JSON object string>"}}.
- "goal_guesses_json": on the final round, a JSON object mapping each other agent to the goal name from the goals section of your
  manual that best fits what they did; on other rounds, "{{}}"."""
    room = max(200, int(c["budgets"]["core"]) - tokens(essentials) - 10)
    rules, cut = clip(overview(inst), room, '...(more: manual section "World rules")')
    text = rules + "\n\n" + essentials

    if k is not None:
        _st(k, aid)["core"][aid] = {"tokens": tokens(text), "budget": int(c["budgets"]["core"]), "trimmed": cut, "sections": len(secs)}
    return text


# ------------------------------------------------------------------ the turn prompt
OFFICIAL = {"gazette", "enact", "repeal", "vetoed", "veto_window", "proposal", "proposal_failed", "ballot_open", "ballot_close", "vote",
            "ruling", "patched", "patch_submitted", "patch_failed", "law_error", "request_fix", "veto_vote", "case_dismissed", "accuse",
            "respond", "rename", "channel_created", "channel_member", "channel_closed", "dm_limit", "post_hidden", "post_revealed"}
POSTS = {"post", "anon_post", "story", "report", "digest", "channel_post"}
PRIORITY_NAMES = {1: "events", 2: "results of your actions", 3: "messages to you", 4: "posts mentioning you", 5: "announcements", 6: "posts"}
POINTERS = {3: "search_dms", 4: "search_board", 6: "search_board"}


def _priority(k, aid, e) -> int:
    t, d = e["type"], e["data"]
    if e["agent"] == aid:
        return 2
    if t == "dm":
        return 3 if d.get("to") == aid else 6
    if t in POSTS:
        said = f"{d.get('headline', '')} {d.get('text', '')}"
        return 4 if re.search(rf"(?<!\w){re.escape(aid)}(?!\w)", said) else 6
    if t in OFFICIAL:
        return 5
    return 1


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
    for i, e in enumerate(k.events[since:], since):
        if not k.can_see(aid, e):
            continue
        if digest_only and e["type"] == "post" and e["agent"] != aid:
            continue
        if e["agent"] == aid and e["type"] in ("post", "vote", "transfer", "dm", "proposal", "story", "digest", "report", "channel_post"):
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
    lim = k.dm_limit(aid)
    extra = (f", plus at most {lim} private messages (dm) this round, replies included; they are delivered first and can be answered within the round"
             if simultaneous and dmc.get("enabled") and k.spec["channels"].get("dm", True) else
             f" (at most {lim} of them can be private messages)" if k.spec["channels"].get("dm", True) else "")
    lines = [f"Round {k.r + 1} of {k.inst['rounds']}. {when} You have {n_actions} actions this turn{extra}."]
    lines += AG.state_view(k, aid).split("\n")
    if (k.spec.get("jurisdictions") or {}).get("enabled"):
        j = _optional("jurisdictions", "member_of", k, aid)
        lines.append(f"Your jurisdiction: {j or 'none (no law binds or protects you)'}.")
    if (k.spec.get("life") or {}).get("enabled"):
        left = _optional("life", "rounds_left", k, aid)
        if left is not None:
            lines.append(f"Rounds of life left: {left}.")
    lines.append(memory_line(k, aid))
    text, dropped = _clip_lines(lines, budget, "lines of state")
    return text, {"tokens": tokens(text), "budget": budget, "lines": len(lines), "dropped_lines": dropped}


def recent_layer(k, aid, budget) -> tuple[str, dict]:
    turns = list(reversed(_st(k, aid)["recent"].get(aid, [])))      # newest first
    out, used, dropped = [], 0, 0
    for t in turns:
        acts = "; ".join(t["actions"]) or "(no actions)"
        res = "\n".join("  " + clip(x, 150, "...(full text in Lookups)" if x.split(":", 1)[0] in LOOKUPS else "...(cut)")[0]
                        for x in t["results"]) or "  (no results)"
        s = f"Round {t['round'] + 1}: {acts}\n{res}"
        room = budget - used - 20
        if dropped or room < 60:
            dropped += 1
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
    med = [clip(x, int(b["media"]))[0] for x in eds]
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
    if carry:
        parts.append("## Lookups you paid for last turn\n" + "\n\n".join(carry))
    if fetched is not None:
        parts.append(FETCHED_HEADER + "\n" + "\n\n".join(got))
    if final:
        parts.append("This is the final round. In goal_guesses_json, map each other agent to the goal name from the list that best fits what they did.")
    if fetched is not None:
        parts.append("Your free lookups for this turn are used: reply with your actions now (\"lookups\" is ignored; a further lookup "
                     "costs an action: put it in \"actions\").")
    elif c["lookup_phase"] and int(c["free_lookups"]) > 0:
        parts.append(f"Act now, or first list up to {c['free_lookups']} free lookups in \"lookups\" (with \"actions\" empty) to be asked "
                     "again with their results.")
    text = "\n\n".join(parts)
    core = st["core"].get(aid) or {}
    rec["core"] = core
    rec["total_tokens"] = tokens(text) + int(core.get("tokens", 0))
    st["layers"][aid] = rec
    return text, cursor


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
    del rows[:-int(c["recent_turns"])]
    st["carry"][aid] = [str(x) for x in results if str(x).split(":", 1)[0] in LOOKUPS and not str(x).split(":", 1)[1].strip().startswith("ERROR")][:3]
    st["manual_titles"][aid] = {t: _digest(x) for t, x in build_manual(k.inst, k, aid)}
    st["fetched"].pop(aid, None)


def truth(k) -> dict:
    """For ground_truth.json: which manual sections each agent read (and how often), and every agent's files at the end."""
    st = _st(k)
    return {"manual_reads": copy.deepcopy(st.get("manual_reads", {})),
            "files": {aid: {n: {"tokens": f["tokens"], "pinned": f["pinned"], "origin": f["origin"]} for n, f in fs.items()}
                      for aid, fs in (k.w.get("files") or {}).items()},
            "scratchpad_tokens": {aid: tokens(t) for aid, t in (k.w.get("scratchpad") or {}).items()}}


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


from charter import manual as _manual                                  # noqa: E402  (registers the base sections)

MANUAL_SECTIONS.append(_manual.sections)
