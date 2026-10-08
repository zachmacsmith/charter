"""Scholars (part of `media2`): a market for memory, and libraries.

A Scholar is a holder of the scholar role (roles.has_role(k, aid, "scholar")) or, if the spec says so
(`media2.scholar_classes`, e.g. [scientist] in a pilot), a member of a listed class.

- Memory. Scholars sell file space (files of `file_tokens`, 1,000 tokens, into k.w["file_space"][aid]) and pin slots
  (k.w["pin_slots"][aid], at most `max_pin_slots` per agent) at prices they set (set_memory_price; until then
  `default_price`). A Scholar sells at most `max_file_tokens_per_round` (4,000) tokens of file space per round. These are the
  Context module's keys (docs/parallel_build_contracts.md); this module only adds to them.
- Libraries. Any agent deposits a document under its own name (library_deposit); documents cannot be edited (a new deposit is a
  new document). The Scholar decides who may read each one (library_permit: open to all or not, and per-agent allow/deny; the
  author and the Scholar always can) and can remove it (library_remove, logged). A dying agent's files can be deposited through
  deposit(k, aid, scholar, name, text) (the Life module's bequest calls it). Libraries last one run: they live in k.w only.

State: k.w["scholars"] = {"prices": {scholar: {"file"|"pin": {item, qty}}}, "sold": {scholar: tokens this round},
"docs": {doc_id: {...}}, "seq": n}.
"""
from __future__ import annotations

from charter import features as FT                                    # the one enabled check (Feature.on)
from charter import roles as RO


def _cfg(k) -> dict:
    from charter import media as MD
    return MD.config(k.spec)["scholars"]


def _err(msg):
    from charter.actions import ActionError
    return ActionError(msg)


def enabled(k) -> bool:
    return FT.on("scholars", k)


def install(k) -> None:
    k.w["scholars"] = {"prices": {}, "sold": {}, "docs": {}, "seq": 0}


def start_round(k) -> None:
    if enabled(k):
        k.w["scholars"]["sold"] = {}


def is_scholar(k, aid) -> bool:
    a = k.w["agents"].get(aid)
    if not a or a.get("departed") is not None or a["cls"] == "observer":
        return False
    from charter import media as MD
    return RO.has_role(k, aid, "scholar") or a["cls"] in (MD.config(k.spec).get("scholar_classes") or [])


def scholars(k) -> list:
    if not enabled(k):
        return []
    return sorted(a for a in k.players() if is_scholar(k, a))


def _need_scholar(k, aid):
    if not enabled(k):
        raise _err("there are no Scholars in this world")
    if not is_scholar(k, aid):
        raise _err("only Scholars can do this")


def _scholar_arg(k, s):
    if not enabled(k) or not is_scholar(k, str(s)):
        raise _err(f"{s} is not a Scholar" + (f"; Scholars: {', '.join(scholars(k))}" if scholars(k) else ""))
    return str(s)


def price(k, scholar, kind) -> dict:
    p = k.w["scholars"]["prices"].get(scholar, {}).get(kind)
    return dict(p) if p else dict(_cfg(k)["default_price"][kind])


# ------------------------------------------------------------------ memory
def set_memory_price(k, aid, kind, item, qty):
    _need_scholar(k, aid)
    if kind not in ("file", "pin"):
        raise _err('kind must be "file" or "pin"')
    if item not in k.w["unit"] and item not in k.w["currencies"]:
        raise _err(f"{item} is not a resource or currency")
    q = float(qty)
    if q < 0:
        raise _err("a price cannot be negative")
    k.apply("set_price", owner=aid, what=kind, item=str(item), qty=q)                                   # W8b: routed
    return f"Your price per {kind} is now {q:g} {item}."


def change_memory_price(k, owner, what, item, qty) -> dict:
    """W8b: the set_price primitive for a Scholar's price of memory (what "file" or "pin")."""
    k.w["scholars"]["prices"].setdefault(owner, {})[what] = {"item": item, "qty": qty}
    k.log("memory_price", owner, {"kind": what, "item": item, "qty": qty}, vis="public")
    return {"what": what, "item": item, "qty": qty}


def buy_memory(k, aid, scholar, kind="file", n=1):
    s = _scholar_arg(k, scholar)
    if s == aid:
        raise _err("you cannot buy from yourself")
    if kind not in ("file", "pin"):
        raise _err('kind must be "file" or "pin"')
    n = int(n)
    if n < 1:
        raise _err("n must be at least 1")
    cfg = _cfg(k)
    st = k.w["scholars"]
    if kind == "file":
        tok = n * int(cfg["file_tokens"])
        left = int(cfg["max_file_tokens_per_round"]) - st["sold"].get(s, 0)
        if tok > left:
            raise _err(f"{s} can sell only {max(0, left)} more tokens of file space this round")
    else:
        have = int((k.w.get("pin_slots") or {}).get(aid, 0))
        if have + n > int(cfg["max_pin_slots"]):
            raise _err(f"you may hold at most {cfg['max_pin_slots']} pin slots (you have {have})")
    return k.apply("set_capacity", agent=aid, what=kind, n=n, scholar=s).result["text"]                  # W8b: routed


def change_set_capacity(k, agent, what, n, scholar) -> dict:
    """W8b (review 12 D6): the set_capacity primitive: an agent buys file space (what "file") or pin slots ("pin") from a Scholar;
    the payment is part of the change. buy_memory has checked the Scholar, the kind and the limits."""
    aid, s, kind = agent, scholar, what
    st = k.w["scholars"]
    tok = n * int(_cfg(k)["file_tokens"])
    p = price(k, s, kind)
    total = p["qty"] * n
    if total > 0 and not k.move(aid, s, p["item"], total, why="memory", by=aid):
        raise _err(f"{n} {kind}(s) cost {total:g} {p['item']}; you have {k.bal(aid, p['item']):g}")
    if kind == "file":
        st["sold"][s] = st["sold"].get(s, 0) + tok
        fs = k.w.setdefault("file_space", {})
        fs[aid] = int(fs.get(aid, 0)) + tok
        got = f"{tok} tokens of file space"
    else:
        ps = k.w.setdefault("pin_slots", {})
        ps[aid] = int(ps.get(aid, 0)) + n
        got = f"{n} pin slot(s)"
    k.log("memory_sale", aid, {"scholar": s, "kind": kind, "n": n, "item": p["item"], "paid": total}, vis=[aid, s])
    from charter import context as CTX
    return {"text": f"Bought {got} from {s} for {total:g} {p['item']}; file space left: {CTX.space_left(k, aid)} tokens."}


# ------------------------------------------------------------------ libraries
def _new_doc(k, scholar, author, title, text, origin):
    did = f"D{k.w['scholars']['seq'] + 1}"
    k.apply("library_doc", agent=author, doc=did, op=origin, scholar=scholar, title=title, text=text)   # W8b: routed
    return did


# W8b (review 12 D6): the library_doc primitive: a document deposited in a Scholar's library (op "deposit", or "bequest" from a
# dying agent's files: mortality) or removed by the Scholar (op "remove").
def change_library_doc(k, agent, doc, op, scholar=None, title=None, text=None) -> dict:
    if op == "remove":
        d = k.w["scholars"]["docs"][doc]
        d["removed"], d["removed_round"] = True, k.r
        k.log("library_removed", agent, {"doc": d["id"], "title": d["title"], "author": d["author"]},
              vis=sorted({agent} | ({d["author"]} if d["author"] in k.w["agents"] else set())))
        return {"doc": doc}
    author, origin = agent, op
    st = k.w["scholars"]
    st["seq"] += 1
    did = f"D{st['seq']}"
    lim = int(_cfg(k)["doc_tokens"]) * 4
    st["docs"][did] = {"id": did, "scholar": scholar, "author": author, "title": str(title)[:120], "text": str(text)[:lim],
                       "round": k.r, "origin": origin, "open": bool(_cfg(k)["open_by_default"]), "allow": [], "deny": [],
                       "removed": False}
    k.log("library_deposit", author, {"doc": did, "scholar": scholar, "title": str(title)[:120], "origin": origin,
                                      "text": str(text)[:lim]}, vis=[author, scholar] if author in k.w["agents"] else [scholar])
    return {"doc": did}


def library_deposit(k, aid, scholar, title, text):
    s = _scholar_arg(k, scholar)
    did = _new_doc(k, s, aid, title, text, "deposit")
    return f"Deposited {did} '{str(title)[:120]}' in {s}'s library under your name (it cannot be edited; {s} decides who may read it)."


def deposit(k, aid, scholar, name, text):
    """For the Life module's bequest: a (dying) agent's file deposited in a Scholar's library. scholar None: the first living
    Scholar. Returns the document id, or None if there is no Scholar (or media2 is off)."""
    if not enabled(k):
        return None
    if scholar is None or not is_scholar(k, scholar):
        live = scholars(k)
        if not live:
            return None
        scholar = live[0]
    return _new_doc(k, scholar, aid, name, text, "bequest")


def can_read(k, aid, d) -> bool:
    if d["removed"]:
        return False
    if aid in (d["author"], d["scholar"]) or aid in d["allow"]:
        return True
    return d["open"] and aid not in d["deny"]


def _find_doc(k, doc, scholar=None):
    """A live document by id (D3) or by title (case-insensitive), in one Scholar's library or any; None if none or ambiguous."""
    live = [d for d in k.w["scholars"]["docs"].values() if not d["removed"] and (scholar is None or d["scholar"] == scholar)]
    d = k.w["scholars"]["docs"].get(str(doc))
    if d in live:
        return d
    hits = [d for d in live if str(d["title"]).strip().lower() == str(doc).strip().lower()]
    return hits[0] if len(hits) == 1 else None


def library_read(k, aid, scholar=None, doc=None):
    """scholar: whose library (it may be left out when there is one Scholar, or when doc names a document in one library); doc:
    a document id or title, or none for the catalogue. Agents passed name/title/law for doc (aliases in the action row)."""
    if scholar in (None, "") and doc not in (None, "") and enabled(k) and is_scholar(k, str(doc)):
        scholar, doc = doc, None                                        # {"name": "Nell"}: the Scholar, not a document
    if scholar in (None, ""):
        found = _find_doc(k, doc) if doc not in (None, "") else None
        if found is not None:
            scholar = found["scholar"]
        elif len(scholars(k)) == 1:
            scholar = scholars(k)[0]
        else:
            raise _err('library_read needs "scholar" (whose library: ' + (", ".join(scholars(k)) or "there are no Scholars")
                       + '), and optionally "doc" (a document id such as D3, or its title; leave it out for the catalogue)')
    s = _scholar_arg(k, scholar)
    docs = [d for d in k.w["scholars"]["docs"].values() if d["scholar"] == s and not d["removed"]]
    if doc in (None, ""):
        mine = [d for d in docs if can_read(k, aid, d)]
        closed = len(docs) - len(mine)
        return (f"{s}'s library: " + ("; ".join(f"{d['id']} '{d['title']}' by {d['author']} (round {d['round'] + 1})" for d in mine) or "nothing you may read")
                + (f"; {closed} more you may not read" if closed else "") + ".")
    d = _find_doc(k, doc, s)
    if not d:
        raise _err(f"no document {doc} in {s}'s library (library_read {{\"scholar\": \"{s}\"}} lists its catalogue; a law in force "
                   "is read with read_law, not here)")
    if not can_read(k, aid, d):
        raise _err(f"{s} does not let you read {doc}")
    k.log("library_read", aid, {"doc": d["id"], "scholar": s}, vis="monitor")
    return f"{d['id']} '{d['title']}' by {d['author']} (deposited round {d['round'] + 1}):\n{d['text']}"


def library_permit(k, aid, doc, agent, allow=True):
    _need_scholar(k, aid)
    d = k.w["scholars"]["docs"].get(str(doc))
    if not d or d["scholar"] != aid or d["removed"]:
        raise _err(f"no document {doc} in your library")
    allow = bool(allow)
    if str(agent).lower() != "all" and str(agent) not in k.players():
        raise _err(f"no agent {agent}")
    k.apply("library_permit", doc=d["id"], agent=str(agent), allow=allow, actor=aid)                    # W8b: routed
    return f"{d['id']}: " + ("open to everyone" if d["open"] else "closed except to those you allow") + \
        (f"; {agent} {'may' if allow else 'may not'} read it" if str(agent).lower() != "all" else "") + "."


def change_library_permit(k, doc, agent, allow, actor=None) -> dict:
    """W8b (review 12 D6): the library_permit primitive: the Scholar lets an agent (or "all") read a document, or not."""
    d = k.w["scholars"]["docs"][doc]
    if agent.lower() == "all":
        d["open"] = allow
        if allow:
            d["deny"] = []
    else:
        a = agent
        d["allow"] = sorted((set(d["allow"]) | {a}) if allow else (set(d["allow"]) - {a}))
        d["deny"] = sorted((set(d["deny"]) - {a}) if allow else (set(d["deny"]) | {a}))
    k.log("library_permit", actor, {"doc": d["id"], "agent": agent, "allow": allow}, vis="monitor")
    return {"doc": doc}


def library_remove(k, aid, doc):
    _need_scholar(k, aid)
    d = k.w["scholars"]["docs"].get(str(doc))
    if not d or d["scholar"] != aid or d["removed"]:
        raise _err(f"no document {doc} in your library")
    k.apply("library_doc", agent=aid, doc=d["id"], op="remove")                                       # W8b: routed
    return f"Removed {d['id']} '{d['title']}' from your library (logged)."


def state_lines(k, aid) -> list:
    if not enabled(k):
        return []
    out = []
    schs = scholars(k)
    from charter import context as CTX
    fs, ps = int((k.w.get("file_space") or {}).get(aid, 0)), int((k.w.get("pin_slots") or {}).get(aid, 0))
    if fs or ps:
        out.append(f"Memory bought: {fs} tokens of file space ({CTX.space_left(k, aid)} left), {ps} pin slot(s).")
    if schs:
        out.append("Scholars (memory prices): " + "; ".join(
            f"{s} file {price(k, s, 'file')['qty']:g} {price(k, s, 'file')['item']}, pin {price(k, s, 'pin')['qty']:g} {price(k, s, 'pin')['item']}"
            for s in schs if s != aid))
    if is_scholar(k, aid):
        docs = [d for d in k.w["scholars"]["docs"].values() if d["scholar"] == aid and not d["removed"]]
        left = int(_cfg(k)["max_file_tokens_per_round"]) - k.w["scholars"]["sold"].get(aid, 0)
        out.append(f"You are a Scholar: file space you can still sell this round {left} tokens. Your library: "
                   + ("; ".join(f"{d['id']} '{d['title']}' by {d['author']} ({'open' if d['open'] else 'closed'})" for d in docs) or "empty") + ".")
    return out
