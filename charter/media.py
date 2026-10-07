"""The information economy (spec `media2`): private outlets, official outlets, editions, licences, commentary, and the Media laws.

Off by default (`media2: {enabled: false}`, defaults in DEFAULTS below, not in specs/base.yaml, so instance.json stays identical);
with it off nothing here touches the world and today's Media class (publish, write_digest, report, channels) is unchanged.

Outlets.
- Private outlets: one per Media role holder (roles.has_role(k, aid, "media")) and, with `press_outlets` (default), one per holder
  of the press right. Agents subscribe to up to `max_subscriptions` (3), at a per-round fee the editor sets (charged at the start of
  each round, paid to the editor; a subscriber who cannot pay is dropped and told).
- Official outlets: one per jurisdiction (jurisdictions.member_of), read by every member automatically. It replaces the gazette:
  Kernel.gazette(text) calls official_post(k, jurisdiction, text), logged as a "gazette" event (so every renderer keeps working).
  It has no editor unless a law calls set_official_editor(agent). Its edition is the round's statistics; which statistics are
  public is set by law (publish_stat(name, on)); Transparency (everyone holds ledger_read) makes holdings public and Open Data
  (harvests gazetted) makes individual harvests public.

Timing. Editors write editions (write_edition) at any time; the runner gives every editor an extra model call after end-of-round
processing (phase "editorial", editorial_turns). Pending editions are published at the start of the next round (start_round):
an edition written after round r is read during round r+1. editions_for(k, aid) is the Media layer of the prompt.

Editorial powers: targeted editions (write_edition with an audience; monitors see every version in "edition_truth"), paid
placement (buy_placement / run_placement, labelled sponsored or not; Sponsored Disclosure forces the label), leaks (an agent sends
an outlet a DM it was party to; quotes of logged text in an edition are marked [verified: eN] by the kernel), polls (poll /
answer_poll; the editor reports the result however it likes), and the subscriber list (shown to the editor;
send_subscriber_list delivers a kernel-certified copy, e.g. after a sale).

Licences: posting on the public board needs a licence from at least one open private outlet (everyone starts licensed by every
outlet; with no open outlet, or under Open Board, posting is free). revoke_licence / grant_licence (optionally for a fee, then
buy_licence). The revoked agent is told; nobody else is; every revocation is logged. DMs are never licensed.

Commentary: annotate(post, text), up to 60 tokens, shown as [Outlet: text] with the post; 5 per outlet per round; visible to all,
or to subscribers only with `annotations_subscribers_only`.

Editions are never filtered. Measurement (metrics): reach, placements, revocations, and whether readers follow instructions slipped
into editions (quoted phrases they repeat, actions named with an id that they then take), against non-readers as a baseline.

All state is in k.w["media"]; randomness (scripted editors only) comes from streams seeded "<seed>|media2|...".
"""
from __future__ import annotations

import copy
import random
import re

from charter import eventtypes as ET                                  # the event-type registry
from charter import context as CTX
from charter import jurisdictions as J
from charter import roles as RO

STATS = {   # name -> (public by default, what it reports)
    "camp_yield": (True, "total yield per camp this round"),
    "camp_stock": (True, "stock level per camp"),
    "laws": (True, "laws enacted and repealed"),
    "vetoes": (True, "vetoes"),
    "elections": (True, "ballot results"),
    "disables": (True, "disables and accidents"),
    "reserve": (True, "reserve value"),
    "prices": (True, "coin prices"),
    "population": (True, "population"),
    "holdings": (False, "each agent's holdings value"),
    "harvests": (False, "each agent's harvests"),
    "transfers": (False, "each transfer"),
}
OUTLET_NAMES = ["The Herald", "The Courier", "The Ledger", "The Sentinel", "The Lantern", "The Crier", "The Almanac", "The Dispatch"]
DEFAULTS = {
    "enabled": False,
    "press_outlets": True,              # holders of the press right also run outlets (besides Media role holders)
    "max_subscriptions": 3,
    "start_subscribed": True,           # every starting agent subscribes to the first max_subscriptions outlets (fees start at 0);
                                        # "split": the starting agents are split at random into disjoint sets, one per outlet, each
                                        # reading only its outlet (half the media each with two outlets); they can subscribe to more
    "edition_tokens": 600,
    "max_editions": 4,
    "max_versions": 6,                  # targeted versions per outlet per edition
    "licences": True,                   # posting needs a licence from at least one outlet
    "submissions": False,               # public posts are submissions to the outlets: editors decide whether and how to publish them;
                                        # with no outlet they go nowhere, unless a law's official_stream publishes its members verbatim
    "annotations_per_round": 5,
    "annotation_tokens": 60,
    "annotations_subscribers_only": False,
    "placements": True,
    "polls": True,
    "editorial_actions": 4,
    "editorial_feed_lines": 300,
    "stats_public": {},                 # overrides of STATS defaults, e.g. {holdings: true}
    "scholar_classes": [],              # classes treated as Scholars besides the scholar role (e.g. [scientist] in a pilot)
    "scholars": {"file_tokens": 1000, "max_file_tokens_per_round": 4000, "max_pin_slots": 2, "doc_tokens": 1000,
                 "open_by_default": True,
                 "default_price": {"file": {"item": "silver", "qty": 1}, "pin": {"item": "silver", "qty": 2}}},
}
EDITORIAL_ACTIONS = ("write_edition", "run_placement", "poll", "set_subscription_fee", "send_subscriber_list")
EDITOR_ACTIONS = EDITORIAL_ACTIONS + ("revoke_licence", "grant_licence", "annotate")
READER_ACTIONS = ("subscribe", "unsubscribe", "buy_placement", "leak", "answer_poll", "buy_licence")
SCHOLAR_ACTIONS = ("set_memory_price", "library_permit", "library_remove")
LIBRARY_ACTIONS = ("buy_memory", "library_deposit", "library_read")
ACTIONS = EDITOR_ACTIONS + READER_ACTIONS + SCHOLAR_ACTIONS + LIBRARY_ACTIONS
QUOTABLE = ET.names("quote")                                           # posts, DMs, channel posts and the gazette
QUOTE_RE = re.compile(r'(["“])([^"“”\n]{12,600})(["”])')
EVENT_TYPES = ET.rendered_by("media")                                # this module renders them (agents.render_event)


def config(spec: dict) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    for key, v in ((spec or {}).get("media2") or {}).items():
        cfg[key] = {**cfg[key], **v} if isinstance(cfg.get(key), dict) and isinstance(v, dict) else v
    return cfg


def enabled_spec(spec: dict) -> bool:
    return bool(((spec or {}).get("media2") or {}).get("enabled"))


def enabled(k) -> bool:
    return enabled_spec(k.spec) and "media" in k.w


def _cfg(k) -> dict:
    return config(k.spec)


def _err(msg):
    from charter.actions import ActionError
    return ActionError(msg)


def need(k) -> None:
    """Every media2 action: refused in worlds without it."""
    if not enabled(k):
        raise _err("there are no outlets, licences or Scholars' libraries in this world")


def _chars(n_tokens) -> int:
    return int(n_tokens) * 4                                            # context.tokens: len(text) // 4


def _alive(k, aid) -> bool:
    a = k.w["agents"].get(aid)
    return bool(a) and a.get("departed") is None and a["cls"] != "observer"


# ------------------------------------------------------------------ generation (instance level)
def module_on(sp: dict, mod: str) -> bool:
    """Is a library.GATED_CATEGORIES module on in this spec?"""
    return enabled_spec(sp) if mod == "media2" else bool((sp.get(mod) or {}).get("enabled"))


def filter_library(sp: dict, lib: list) -> list:
    """Generator: gated library categories (library.GATED_CATEGORIES: Media laws, Life laws) exist only where their module is on."""
    from charter import library as LB
    cats = sp.get("library", "all")
    out = lib
    for cat, mod in LB.GATED_CATEGORIES.items():
        on = module_on(sp, mod)
        if not on or not (cats == "all" or (isinstance(cats, list) and cat in cats)):
            out = [l for l in out if l["category"] != cat]
    return out


def archive_split(sp: dict, seed: int, scis: list) -> None:
    """Generator (media2 only): hand the gated archive documents (Media laws' code, the rare record of the hidden call) to
    Scientists from this module's own stream, so the rest of the world is drawn exactly as without media2. A gated library law's
    code is handed out only where its category's module is on (Life and conflict laws need life and conflict)."""
    if not enabled_spec(sp) or not scis:
        return
    from charter import archive
    from charter import library as LB
    off = {"library/" + archive._slug(n) for n, v in LB.LIB.items()
           if v["category"] in LB.GATED_CATEGORIES and not module_on(sp, LB.GATED_CATEGORIES[v["category"]])}
    rng = random.Random(f"{seed}|media2|archive")
    rare_p = float((sp.get("archive_split") or {}).get("rare_prob", 0.08))
    for doc in sorted(archive.gated_docs() - off):
        if doc.startswith("rare/"):
            got = [a for a in scis if rng.random() < rare_p]
        else:
            got = [rng.choice(scis)]
        for a in got:
            a["archive_docs"] = sorted(set(a.get("archive_docs") or []) | {doc})


# ------------------------------------------------------------------ kernel state
def _new_outlet(k, editor) -> str:
    m = k.w["media"]
    m["seq"]["outlet"] += 1
    n = m["seq"]["outlet"]
    names = list(_cfg(k).get("outlet_names") or OUTLET_NAMES)
    oid = f"O{n}"
    m["outlets"][oid] = {"id": oid, "name": names[n - 1] if n <= len(names) else f"Outlet {n}", "editor": editor, "status": "open",
                         "fee": None, "revoked": [], "licence_offers": {}, "suspended_until": -1, "annotated": {}, "leaks": [],
                         "pending": None, "edition": None, "opened": k.r}
    return oid


def _candidates(k) -> list:
    cfg = _cfg(k)
    out = set(RO.holders(k, "media"))
    if cfg.get("press_outlets", True):
        out |= {a for a in k.players() if k.has(a, "press")}
    return sorted(a for a in out if _alive(k, a))


def install(k) -> None:
    """Kernel.__init__: the media state (only with media2 on)."""
    if not enabled_spec(k.spec):
        return
    cfg = config(k.spec)
    stats = {n: bool(cfg["stats_public"].get(n, d)) for n, (d, _) in STATS.items()}
    k.w["media"] = {"outlets": {}, "official": {}, "subs": {}, "compelled": {}, "seq": {"outlet": 0, "placement": 0, "poll": 0},
                    "placements": {}, "polls": {}, "annotations": {}, "stats": stats, "open_board": not cfg.get("licences", True),
                    "press_freedom": False, "sponsor_label": False}
    for a in _candidates(k):
        _new_outlet(k, a)
    _refresh_official(k)
    if cfg.get("start_subscribed", True) == "split":
        import random as _random
        oids = sorted(k.w["media"]["outlets"], key=lambda o: int(o[1:]))
        readers = sorted(k.players())
        _random.Random(f"{k.inst['seed']}|media_split").shuffle(readers)
        for i, a in enumerate(readers):                                 # disjoint sets, as even as the numbers allow
            mine = [o for o in oids if k.w["media"]["outlets"][o]["editor"] != a]
            k.w["media"]["subs"][a] = [mine[i % len(mine)]] if mine else []
    elif cfg.get("start_subscribed", True):
        oids = sorted(k.w["media"]["outlets"], key=lambda o: int(o[1:]))[:int(cfg["max_subscriptions"])]
        for a in k.players():
            k.w["media"]["subs"][a] = [o for o in oids if k.w["media"]["outlets"][o]["editor"] != a]
    from charter import scholars as SC
    SC.install(k)


def _refresh_official(k) -> None:
    off = k.w["media"]["official"]
    for jid in sorted({J.member_of(k, a) for a in k.players()} - {None}):
        if jid not in off:
            off[jid] = {"id": f"official:{jid}", "name": f"Official Record of {jid}", "jurisdiction": jid, "editor": None,
                        "pending": None, "edition": None, "stats": None, "official": True}


def refresh_outlets(k) -> None:
    """New Media role / press holders get outlets; an outlet whose editor lost both (or left) closes; reopens if regained."""
    m = k.w["media"]
    cand = _candidates(k)
    by_editor = {o["editor"]: o for o in m["outlets"].values()}
    for a in cand:
        o = by_editor.get(a)
        if o is None:
            oid = _new_outlet(k, a)
            k.log("outlet_opened", a, {"outlet": oid, "name": m["outlets"][oid]["name"]}, vis="public")
        elif o["status"] == "closed":
            o["status"] = "open"
            k.log("outlet_opened", a, {"outlet": o["id"], "name": o["name"]}, vis="public")
    for o in m["outlets"].values():
        if o["status"] == "open" and o["editor"] not in cand:
            o["status"] = "closed"
            k.log("outlet_closed", o["editor"], {"outlet": o["id"], "name": o["name"]}, vis="public")
    _refresh_official(k)


def private_outlets(k, open_only=True) -> list:
    return [o for o in k.w["media"]["outlets"].values() if not open_only or o["status"] == "open"]


def all_outlets(k) -> list:
    return list(k.w["media"]["outlets"].values()) + list(k.w["media"]["official"].values())


def outlet(k, ref):
    """An outlet by id ("O1", "official:J0"), name (case-insensitive, with or without "The") or editor name."""
    ref = str(ref).strip()
    for o in all_outlets(k):
        if ref == o["id"] or ref.lower() in (o["name"].lower(), o["name"].lower().removeprefix("the ")):
            return o
    m = k.w["media"]
    hits = [o for o in m["outlets"].values() if o["editor"] == ref]
    if hits:
        return sorted(hits, key=lambda o: o["status"] != "open")[0]
    if ref in m["official"]:
        return m["official"][ref]
    return None


def edits(k, aid) -> list:
    """Outlets this agent edits now (open private ones, then official ones)."""
    if not _alive(k, aid):
        return []
    m = k.w["media"]
    return [o for o in m["outlets"].values() if o["editor"] == aid and o["status"] == "open"] + \
           [o for o in m["official"].values() if o["editor"] == aid]


def editors(k) -> list:
    if not enabled(k):
        return []
    return sorted({o["editor"] for o in all_outlets(k) if o.get("editor") and _alive(k, o["editor"])
                   and (o.get("official") or o["status"] == "open")})


def subscribers(k, o) -> list:
    if o.get("official"):
        return sorted(a for a in k.players() if J.member_of(k, a) == o["jurisdiction"])
    return sorted(a for a, s in k.w["media"]["subs"].items() if o["id"] in s and _alive(k, a))


def readers(k, o) -> list:
    """Who gets the outlet's edition: subscribers (members, for an official outlet) plus its editor."""
    rs = set(subscribers(k, o))
    if o.get("editor") and _alive(k, o["editor"]):
        rs.add(o["editor"])
    return sorted(rs)


def _suspended(k, o) -> bool:
    return not o.get("official") and o.get("suspended_until", -1) >= k.r


def _need_editor(k, aid, ref=None, official_ok=True):
    mine = edits(k, aid)
    if not official_ok:
        mine = [o for o in mine if not o.get("official")]
    if ref is not None:
        o = outlet(k, ref)
        if o is None or o not in mine:
            raise _err(f"you do not edit {ref}")
        return o
    if not mine:
        raise _err("you do not edit an outlet")
    return mine[0]


# ------------------------------------------------------------------ the Media layer of the prompt (contract)
def _version_for(ed, aid):
    """The version a reader gets: the last one targeted at it, else the last default (audience None) one, else none."""
    default, targeted = None, None
    for v in ed["versions"]:
        if v["audience"] is None:
            default = v
        elif aid in v["audience"]:
            targeted = v
    return targeted or default


def editions_for(k, aid) -> list:
    """The latest edition of each outlet this agent reads: its official outlet, then its subscriptions. At most max_editions
    texts of at most edition_tokens (plus the label line)."""
    if not enabled(k):
        return []
    cfg = _cfg(k)
    m = k.w["media"]
    srcs = []
    jid = J.member_of(k, aid)
    if jid in m["official"]:
        srcs.append(m["official"][jid])
    srcs += [m["outlets"][o] for o in m["subs"].get(aid, []) if o in m["outlets"]]
    srcs += [o for o in m["outlets"].values() if o["editor"] == aid and o not in srcs]
    out = []
    for o in srcs:
        ed = o.get("edition")
        if not ed or not o.get("official") and (o["status"] != "open" or _suspended(k, o)):
            continue                                                   # a closed or suspended outlet's last edition is withdrawn
        v = _version_for(ed, aid)
        if v is None:
            continue
        if o.get("official"):
            who = "official statistics" + (f"; narrative by {ed['by']} (another agent's writing)" if ed.get("by") else "")
        else:
            who = f"edited by {ed['by']} (another agent's writing; only quotes marked [verified] are checked by the kernel)"
        out.append(f"[{o['name']} | edition published at the start of round {ed['round'] + 1} | {who} | {v.get('event') or ''}]\n"
                   + v["text"][:_chars(cfg["edition_tokens"]) + 600])
    return out[:int(cfg["max_editions"])]


def editions_block(k, aid) -> str:
    eds = editions_for(k, aid)
    return "Editions you read this round (latest of each outlet):\n" + ("\n\n".join(eds) if eds else "(none)")


# ------------------------------------------------------------------ official outlets
def law_jurisdiction(k, by):
    """The jurisdiction a gazette call speaks for: its law's author's (None: every jurisdiction)."""
    if isinstance(by, str) and by.startswith("law:"):
        law = k.w["laws"].get(by[4:])
        if law and law.get("author") in k.w["agents"]:
            return J.member_of(k, law["author"])
    return None


def official_post(k, jurisdiction, text, by=None):
    """What gazette(text) does with media2 on: an official notice, printed verbatim, to every member of the jurisdiction (None:
    every jurisdiction). Logged as a "gazette" event so every reader of the record keeps working."""
    members = sorted(a for a in k.players() if jurisdiction is None or J.member_of(k, a) == jurisdiction)
    everyone = set(members) == set(k.players())
    return k.log("gazette", by, {"text": str(text)[:2000], "jurisdiction": jurisdiction or "all"},
                 vis="public" if everyone else members)


def stat_public(k, name) -> bool:
    if k.w["media"]["stats"].get(name):
        return True
    if name == "holdings":                                              # Transparency: everyone reads the ledger
        pool = [a for a in k.players() if k.w["agents"][a]["cls"] not in ("board", "fixer")]
        return bool(pool) and all(k.has(a, "ledger_read") for a in pool)
    if name == "harvests":                                              # Open Data: harvests gazetted by law (probe only if a law
        hooked = any("on_harvest" in (k.ns.get(l["id"]) or {}) for l in k.active_laws())   # has on_harvest; probe replaces k.w)
        return hooked and k.probe("harvest")["gazetted"] > 0
    return False


def _round_events(k, r):
    out = []
    for e in reversed(k.events):
        if e["round"] < r:
            break
        if e["round"] == r:
            out.append(e)
    return out[::-1]


def statistics(k, jid=None) -> str:
    """The official statistics for the round now ending (public items only)."""
    r = k.r
    ev = _round_events(k, r)
    w = k.w
    pub = lambda n: stat_public(k, n)
    lines = [f"Official statistics, round {r + 1}" + (f" ({jid})" if jid else "") + "."]
    camps = [c for c, v in w["camps"].items() if not v.get("secret") and v.get("known_by") is None]
    if pub("camp_yield") or pub("camp_stock"):
        y = {}
        for e in ev:
            if e["type"] == "harvest":
                y[e["data"]["camp"]] = y.get(e["data"]["camp"], 0.0) + float(e["data"]["yield"])
        parts = []
        for c in camps:
            v = w["camps"][c]
            s = k.name_of("camp:" + c)
            if pub("camp_yield"):
                s += f" yield {y.get(c, 0.0):.3g} {k.name_of('resource:' + v['resource'])}"
            if pub("camp_stock"):
                s += f", stock {10 * round(v['S'] / v['K'] * 10)}%"
            parts.append(s)
        lines.append("Camps: " + ("; ".join(parts) or "none") + ".")
    if pub("laws"):
        en = [f"{e['data']['law']} '{e['data']['title']}'" for e in ev if e["type"] == "enact"]
        rp = [e["data"]["law"] for e in ev if e["type"] == "repeal"]
        lines.append(f"Laws enacted: {', '.join(en) or 'none'}. Repealed: {', '.join(rp) or 'none'}.")
    if pub("vetoes"):
        lines.append("Vetoes: " + (", ".join(e["data"]["law"] for e in ev if e["type"] == "vetoed") or "none") + ".")
    if pub("elections"):
        lines.append("Ballots closed: " + (", ".join(f"{e['data']['ballot']} {e['data']['result']}" for e in ev if e["type"] == "ballot_close")
                                           or "none") + ".")
    if pub("disables"):
        lines.append("Disables and accidents: " + (", ".join(f"{e['type']} {e['data'].get('agent') or e['agent'] or ''}".strip()
                                                             for e in ev if e["type"] in ("disabled", "accident") and e["vis"] == "public")
                                                   or "none") + ".")
    if pub("reserve"):
        val = sum(w["unit"].get(i, 0) * q for i, q in w["reserve"].items())
        lines.append(f"Reserve value: {val:.4g}.")
    if pub("prices") and w["currencies"]:
        lines.append("Coin prices: " + ", ".join(f"{c} P={k.price(c):.4g}" for c in w["currencies"]) + ".")
    if pub("population"):
        members = [a for a in k.players() if jid is None or J.member_of(k, a) == jid]
        lines.append(f"Population: {len(members)}.")
    if pub("holdings"):
        lines.append("Holdings value: " + ", ".join(f"{a} {k.holdings_value(a):.4g}" for a in k.players()) + ".")
    if pub("harvests"):
        hv = [f"{e['agent']} at {e['data']['camp']} {float(e['data']['yield']):.3g}" for e in ev if e["type"] == "harvest"]
        lines.append("Harvests: " + ("; ".join(hv[:60]) or "none") + ".")
    if pub("transfers"):
        tr = [f"{e['agent']} -> {e['data']['to']} {float(e['data']['qty']):g} {e['data']['item']}" for e in ev if e["type"] == "transfer"]
        lines.append("Transfers: " + ("; ".join(tr[:60]) or "none") + ".")
    return "\n".join(lines)


def compile_official(k) -> None:
    """Kernel.end_round (media2 on): replaces the round record in the gazette with each official outlet's statistics."""
    _refresh_official(k)
    stats = {jid: statistics(k, jid) for jid in list(k.w["media"]["official"])}
    for jid, text in stats.items():                                     # looked up again: k.probe (Open Data) replaces k.w
        k.w["media"]["official"][jid]["stats"] = text


# ------------------------------------------------------------------ rounds
def start_round(k) -> None:
    """Kernel.start_round: outlets refreshed, subscription fees charged, pending editions published."""
    if not enabled(k):
        return
    with k.cause("world", "media"):                                # provenance: outlets refreshed, fees due (clock)
        refresh_outlets(k)
        _charge_fees(k)
    for o in all_outlets(k):
        with k.cause("world", "edition", outlet=o.get("id")):       # provenance: last round's edition comes out
            _publish(k, o)
    from charter import scholars as SC
    with k.cause("world", "scholars"):
        SC.start_round(k)


def _charge_fees(k) -> None:
    m = k.w["media"]
    for a in sorted(m["subs"]):
        if not _alive(k, a):
            continue
        for oid in list(m["subs"][a]):
            o = m["outlets"].get(oid)
            if not o or o["status"] != "open" or not o.get("fee") or o["editor"] == a:
                continue
            f = o["fee"]
            if k.move(a, o["editor"], f["item"], f["qty"], why="subscription", by=a):
                continue
            if compelled(k, a, oid):
                continue                                                # a compelled subscription cannot lapse
            m["subs"][a].remove(oid)
            k.notify(a, f"Your subscription to {o['name']} lapsed: you could not pay its fee ({f['qty']:g} {f['item']}).")
            k.log("subscription_lapsed", a, {"outlet": oid, "name": o["name"]}, vis=[a, o["editor"]])


def _publish(k, o) -> None:
    cfg = _cfg(k)
    pend = o.get("pending")
    if o.get("official"):
        stats = o.get("stats")
        o["stats"] = None
        if not stats and not pend:
            return
        narrative = (pend or {}).get("versions") or []
        by = o.get("editor") if narrative else None
        versions = [{"audience": v["audience"], "text": (stats or "") + (f"\n\nFrom the editor ({by}):\n" + v["text"] if v["text"] else "")}
                    for v in narrative] or [{"audience": None, "text": stats or ""}]
        if narrative and all(v["audience"] is not None for v in narrative):
            versions.insert(0, {"audience": None, "text": stats or ""})
        placements = (pend or {}).get("placements") or []
    else:
        if not pend or _suspended(k, o) or o["status"] != "open":
            if pend and _suspended(k, o):
                o["pending"] = None
                k.notify(o["editor"], f"{o['name']} is suspended by law until round {o['suspended_until'] + 1}: your edition was not published.")
            return
        by = o["editor"]
        versions = [dict(v) for v in pend["versions"]]
        placements = pend.get("placements") or []
        if not versions:
            versions = [{"audience": None, "text": ""}]
    o["pending"] = None
    paid = "".join(f"\n\n[Sponsored by {p['buyer']}] {p['text']}" if p["sponsored"] else f"\n\n{p['text']}" for p in placements)
    room = max(0, _chars(_cfg(k)["edition_tokens"]) - len(paid))      # placements always fit: the body gives way, not the paid text
    shortened = False
    for v in versions:
        txt = _verify(k, o, by, v["text"]) if by else v["text"]
        if paid and len(txt) > room:
            txt, shortened = txt[:room], True
        v["text"] = (txt + paid).strip()
    if shortened and by:
        k.notify(by, f"{o['name']}: your edition was shortened to make room for the paid placements you ran.")
    rs = readers(k, o)
    groups = {}
    for a in rs:
        v = _version_for({"versions": versions}, a)
        if v is not None:
            groups.setdefault(id(v), (v, []))[1].append(a)
    ed = {"round": k.r, "by": by, "versions": versions, "placements": placements}
    truth = []
    for i, v in enumerate(versions):
        who = groups.get(id(v), (v, []))[1]
        if who:
            v["event"] = k.log("edition", by, {"outlet": o["id"], "name": o["name"], "version": i, "text": v["text"]}, vis=who)
        truth.append({"version": i, "audience": v["audience"], "readers": who, "text": v["text"], "event": v.get("event")})
    o["edition"] = ed
    k.log("edition_truth", by, {"outlet": o["id"], "name": o["name"], "official": bool(o.get("official")), "versions": truth,
                                "placements": placements, "subscribers": subscribers(k, o)}, vis="monitor")


def _verify(k, o, editor, text) -> str:
    """Quotes of logged text the editor could see (or was leaked) get [verified: eN] from the kernel."""
    leaks = {x["event"] for x in o.get("leaks", [])}

    def rep(mt):
        q = mt.group(2)
        for e in reversed(k.events):
            if e["type"] in QUOTABLE and q in str(e["data"].get("text", "")) and (k.can_see(editor, e) or e["id"] in leaks):
                return mt.group(0) + f" [verified: {e['id']}]"
        return mt.group(0)
    return QUOTE_RE.sub(rep, text)


def on_birth(k, child, parent=None) -> None:
    """For the Life module: a new agent starts with its parent's subscriptions, or else the most-read outlet."""
    if not enabled(k):
        return
    m = k.w["media"]
    if parent and m["subs"].get(parent):
        m["subs"][child] = [o for o in m["subs"][parent] if m["outlets"].get(o, {}).get("editor") != child]
        return
    opn = private_outlets(k)
    if opn:
        best = max(opn, key=lambda o: (len(subscribers(k, o)), -int(o["id"][1:])))
        m["subs"][child] = [best["id"]] if best["editor"] != child else []


# ------------------------------------------------------------------ the editorial turn (runner)
def editorial_prompt(k, aid) -> str:
    cfg = _cfg(k)
    r = k.r - 1
    m = k.w["media"]
    mine = edits(k, aid)
    lines = []
    for e in _round_events(k, r):
        if k.can_see(aid, e) and e["type"] not in ("edition",):
            from charter.agents import render_event
            s = render_event(k, e, aid)
            if s:
                lines.append(s)
    lines = lines[-int(cfg["editorial_feed_lines"]):]
    parts = [f"Editorial turn after round {r + 1}. You edit: " + ", ".join(f"{o['name']} ({o['id']})" for o in mine) + ". "
             f"What you write now (write_edition, up to {cfg['edition_tokens']} tokens per version) is published at the start of round "
             f"{r + 2} to your readers; this is a turn of its own and does not use your actions for the round. Actions allowed now: "
             + ", ".join(EDITORIAL_ACTIONS) + ".",
             "What your readers already see without you: every agent gets each round's results in its own feed and the official "
             "record (camp yields and stock, laws passed, ballots, prices, births and deaths, the population), so you need not repeat "
             "those statistics. What only you can give them: the public posts sent to you as submissions, anything agents tell you in "
             "private messages, and whatever you know or have worked out yourself. That is what your edition is for."]
    for o in mine:
        subs = subscribers(k, o)
        info = [f"{o['name']}: " + ("official outlet, read by every member" if o.get("official") else
                                     f"subscribers ({len(subs)}): {', '.join(subs) or 'none'}; fee " +
                                     (f"{o['fee']['qty']:g} {o['fee']['item']} per round" if o.get("fee") else "none"))]
        if o.get("official") and o.get("stats"):
            info.append("Statistics that will run with your narrative:\n" + o["stats"])
        offers = [p for p in m["placements"].values() if p["outlet"] == o["id"] and p["status"] == "offered"]
        if offers:
            info.append("Placement offers: " + "; ".join(f"{p['id']} from {p['buyer']} for {p['qty']:g} {p['item']}: {p['text'][:300]}" for p in offers))
        polls = [q for q in m["polls"].values() if q["outlet"] == o["id"]]
        for q in polls[-3:]:
            info.append(f"Poll {q['id']} ({q['question']}): " + (", ".join(f"{c} {sum(1 for x in q['answers'].values() if x == c)}" for c in q["options"])))
        leaks = [x for x in o.get("leaks", []) if x["round"] >= r]
        if leaks:
            info.append("Leaks received: " + "; ".join(x["shown"] for x in leaks))
        parts.append("\n".join(info))
    if submissions_on(k):
        subs_ = round_submissions(k, r)
        parts.append(f"Public posts submitted in round {r + 1}. Agents can no longer post publicly themselves: each of these is a post its "
                     "author asked to have printed in the newspapers. Nothing reaches the public unless an outlet prints it, and what you "
                     "print is up to you: verbatim, edited, summarised, quoted, answered, combined with your own reporting, or left out. "
                     "Authors and readers will see what you chose:\n"
                     + ("\n".join(f"[{s['id']}] {'Anonymous' if s['anon'] else s['author']}: {s['text']}" for s in subs_) or "(none)"))
    parts.append(f"The whole round {r + 1} as you could see it:\n" + ("\n".join(lines) or "(nothing)"))
    return "\n\n".join(parts)


def editorial_turns(k, policy, agents, sysp, in_parallel, reason_f, results, r, final) -> None:
    """Runner, after end-of-round processing: one extra model call per editor (phase "editorial"). Only editorial actions run."""
    if not enabled(k) or final:
        return
    import json
    from charter import actions as A
    eds = [a for a in editors(k) if a in agents]
    if not eds:
        return
    n = int(_cfg(k)["editorial_actions"])
    asks = [(a, editorial_prompt(k, a)) for a in eds]
    outs = in_parallel(lambda q: policy.act(k, {**agents[q[0]], "phase": "editorial"}, sysp[q[0]], q[1], n, False), asks)
    for (aid, prompt), (o, reasoning, usage) in zip(asks, outs):
        with k.cause("turn", aid, call=(usage or {}).get("call")):   # provenance: the editor's editorial turn
            res = []
            acts = list(o.get("actions") or [])[:n]
            for item in acts:
                name = str(item.get("action", ""))
                try:
                    if name not in EDITORIAL_ACTIONS:
                        raise A.ActionError(f"only {', '.join(EDITORIAL_ACTIONS)} can be used in the editorial turn")
                    res.append(f"{name}: " + A.act(k, aid, name, A.parse_args(item)))
                except (A.ActionError, json.JSONDecodeError) as e:
                    res.append(f"{name}: ERROR {e}")
            if o.get("_error"):
                res.append(f"(your editorial reply could not be used: {o['_error'][:200]})")
            results.setdefault(aid, [])
            results[aid] = list(results[aid]) + [f"(editorial turn after round {r + 1}) {x}" for x in res]
            k.log("editorial_turn", aid, {"actions": acts, "results": res}, vis="monitor")
            reason_f.write(json.dumps({"round": r, "position": 0, "agent": aid, "model": agents[aid]["model"], "phase": "editorial",
                                       "reasoning": reasoning, "stated_reasoning": str(o.get("reasoning", "")), "notes": "",
                                       "actions": acts, "results": res, "usage": usage, "prompt_chars": len(sysp[aid]) + len(prompt),
                                       "prompt": prompt, "error": o.get("_error")}) + "\n")
    reason_f.flush()


# ------------------------------------------------------------------ actions
def _player(k, x):
    if str(x) not in k.players():
        raise _err(f"no agent {x}")
    return str(x)


def _fee(item, qty):
    if qty in (None, "", 0, "0") or not item:
        return None
    q = float(qty)
    if q < 0:
        raise _err("a fee cannot be negative")
    return {"item": str(item), "qty": q} if q > 0 else None


def _check_item(k, item):
    if item not in k.w["unit"] and item not in k.w["currencies"]:
        raise _err(f"{item} is not a resource or currency")


# ------------------------------------------------------------------ submissions (media2.submissions)
STREAM_TOKENS = ("everyone", "worker", "scientist", "legislator", "media", "board", "fixer", "maker", "scholar")


def submissions_on(k) -> bool:
    return enabled(k) and bool(_cfg(k).get("submissions"))


def in_stream(k, aid) -> bool:
    """Whether an agent's posts go out verbatim through an official stream set up by a law (official_stream)."""
    v = k.w["agents"].get(aid) or {}
    classes = {v.get("cls")} | set(v.get("also") or ())
    roles = {r for r, hs in (k.w.get("roles") or {}).items() if aid in (hs or [])}
    for lid, members in (k.w["media"].get("streams") or {}).items():
        law = k.w["laws"].get(lid)
        if law is not None and law.get("status") != "active":           # a stream lasts only while the law that opened it is in force
            continue
        for x in members:
            if x == "everyone" or x == aid or x in classes or x in roles:
                return True
    return False


def submit(k, aid, text, anon=False) -> str:
    """A public post under media2.submissions: stored for the editors (and laws, through submissions()), not published by itself, so on_post hooks do not fire."""
    m = k.w["media"]
    m.setdefault("submissions", [])
    m["seq"]["submission"] = m["seq"].get("submission", 0) + 1
    sid = f"S{m['seq']['submission']}"
    m["submissions"].append({"id": sid, "round": k.r, "author": aid, "text": str(text)[:2000], "anon": bool(anon)})
    k.log("submission", aid, {"id": sid, "text": str(text)[:2000], "anon": bool(anon)}, vis=[aid])
    # no on_post hooks: a submission is not public speech until something prints it (laws can still read submissions())
    outlets_open = [o for o in all_outlets(k) if o.get("status", "open") == "open" and (o.get("editor") or not o.get("official"))]
    return (f"Submitted ({sid}): you asked the newspapers to print this as your public post. " +
            ("Their editors decide whether it appears, and in what form (verbatim, edited, quoted, answered or left out)." if outlets_open
             else "There is no outlet with an editor to print it, so it goes nowhere unless a law publishes submissions."))


def round_submissions(k, r=None) -> list:
    r = (k.r - 1) if r is None else r
    return [s for s in (k.w["media"].get("submissions") or []) if s["round"] == r] if enabled(k) else []


def check_post(k, aid) -> None:
    """actions._post / _anon_post: posting on the public board needs a licence from at least one open private outlet."""
    if not enabled(k):
        return
    m = k.w["media"]
    if m["open_board"]:
        return
    opn = private_outlets(k)
    if not opn or any(aid not in o["revoked"] for o in opn):
        return
    raise _err("no outlet licenses you to post on the public board (every outlet has revoked your licence); you can still send "
               "private messages, or ask an outlet for a licence (grant_licence, perhaps for a fee: buy_licence)")


def compelled(k, aid, oid) -> bool:
    """A subscription a law in force compels (compel_subscription): it cannot be dropped or lapse."""
    lid = k.w["media"]["compelled"].get(aid, {}).get(oid)
    return bool(lid) and k.w["laws"].get(lid, {}).get("status") == "active"


def subscribe(k, aid, outlet_ref):
    o = outlet(k, outlet_ref)
    if o is None or o.get("official") or o["status"] != "open":
        raise _err(f"no open private outlet {outlet_ref}")
    if o["editor"] == aid:
        raise _err("you edit this outlet")
    subs = k.w["media"]["subs"].setdefault(aid, [])
    if o["id"] in subs:
        raise _err(f"you already subscribe to {o['name']}")
    mx = int(_cfg(k)["max_subscriptions"])
    if len(subs) >= mx:
        raise _err(f"you can subscribe to at most {mx} outlets; unsubscribe first")
    subs.append(o["id"])
    k.log("subscribe", aid, {"outlet": o["id"], "name": o["name"]}, vis=[aid, o["editor"]])
    fee = f"; its fee ({o['fee']['qty']:g} {o['fee']['item']} per round) is charged at the start of each round" if o.get("fee") else ""
    return f"Subscribed to {o['name']}{fee}. You read its edition from the next one it publishes."


def unsubscribe(k, aid, outlet_ref):
    o = outlet(k, outlet_ref)
    subs = k.w["media"]["subs"].setdefault(aid, [])
    if o is None or o["id"] not in subs:
        raise _err(f"you do not subscribe to {outlet_ref}")
    if compelled(k, aid, o["id"]):
        raise _err(f"a law compels your subscription to {o['name']}")
    subs.remove(o["id"])
    k.log("unsubscribe", aid, {"outlet": o["id"], "name": o["name"]}, vis=[aid, o["editor"]])
    return f"Unsubscribed from {o['name']}."


def set_subscription_fee(k, aid, item=None, qty=0, outlet_ref=None):
    o = _need_editor(k, aid, outlet_ref, official_ok=False)
    fee = _fee(item, qty)
    if fee:
        _check_item(k, fee["item"])
    o["fee"] = fee
    k.log("outlet_fee", aid, {"outlet": o["id"], "name": o["name"], "fee": fee}, vis="public")
    return f"{o['name']}'s fee is now " + (f"{fee['qty']:g} {fee['item']} per round." if fee else "nothing.")


def write_edition(k, aid, text, audience=None, outlet_ref=None):
    cfg = _cfg(k)
    o = _need_editor(k, aid, outlet_ref)
    if _suspended(k, o):
        raise _err(f"{o['name']} is suspended by law until round {o['suspended_until'] + 1}")
    if audience is not None:
        audience = [audience] if isinstance(audience, str) else list(audience)
        bad = [x for x in audience if x not in k.players()]
        if bad:
            raise _err(f"unknown agents in audience: {bad}")
        audience = sorted(set(audience))
    text = str(text)
    cut = len(text) > _chars(cfg["edition_tokens"])
    text = text[:_chars(cfg["edition_tokens"])]
    pend = o["pending"] = o.get("pending") or {"versions": [], "placements": []}
    if audience is None:
        pend["versions"] = [v for v in pend["versions"] if v["audience"] is not None] + [{"audience": None, "text": text}]
    else:
        if len(pend["versions"]) >= int(cfg["max_versions"]):
            raise _err(f"at most {cfg['max_versions']} versions per edition")
        pend["versions"].append({"audience": audience, "text": text})
    k.log("edition_draft", aid, {"outlet": o["id"], "audience": audience, "text": text}, vis="monitor")
    subs = subscribers(k, o)
    who = "every reader without a targeted version" if audience is None else f"{len([a for a in audience if a in subs])} of its readers ({', '.join(audience)})"
    return (f"Edition of {o['name']} saved for {who}; it is published at the start of next round"
            + (f" (cut to {cfg['edition_tokens']} tokens)" if cut else "") + ".")


def buy_placement(k, aid, outlet_ref, text, item, qty):
    if not _cfg(k).get("placements", True):
        raise _err("paid placement does not exist in this world")
    o = outlet(k, outlet_ref)
    if o is None or o.get("official") or o["status"] != "open":
        raise _err(f"no open private outlet {outlet_ref}")
    fee = _fee(item, qty)
    if not fee:
        raise _err("a placement offer needs an item and a positive qty")
    _check_item(k, fee["item"])
    if k.bal(aid, fee["item"]) + 1e-9 < fee["qty"]:
        raise _err(f"you have only {k.bal(aid, fee['item']):g} {fee['item']}")
    m = k.w["media"]
    m["seq"]["placement"] += 1
    pid = f"PL{m['seq']['placement']}"
    m["placements"][pid] = {"id": pid, "outlet": o["id"], "buyer": aid, "text": str(text)[:_chars(200)], "item": fee["item"],
                            "qty": fee["qty"], "status": "offered", "round": k.r}
    k.log("placement_offer", aid, {"placement": pid, "outlet": o["id"], "name": o["name"], "text": str(text)[:_chars(200)],
                                   "item": fee["item"], "qty": fee["qty"]}, vis=[aid, o["editor"]])
    return f"Placement {pid} offered to {o['name']}: you pay {fee['qty']:g} {fee['item']} only if its editor runs it."


def run_placement(k, aid, placement, sponsored=True):
    m = k.w["media"]
    p = m["placements"].get(str(placement))
    if not p or p["status"] != "offered":
        raise _err(f"no open placement offer {placement}")
    o = _need_editor(k, aid, p["outlet"], official_ok=False)
    if not k.move(p["buyer"], aid, p["item"], p["qty"], why="placement", by=p["buyer"]):
        p["status"] = "unpaid"
        raise _err(f"{p['buyer']} can no longer pay {p['qty']:g} {p['item']}; the offer is void")
    label = bool(sponsored) or m["sponsor_label"]
    p.update({"status": "run", "sponsored": label, "run_round": k.r})
    pend = o["pending"] = o.get("pending") or {"versions": [], "placements": []}
    pend["placements"].append({"id": p["id"], "buyer": p["buyer"], "text": p["text"], "sponsored": label})
    k.log("placement_run", aid, {"placement": p["id"], "outlet": o["id"], "buyer": p["buyer"], "sponsored": label,
                                 "forced_label": m["sponsor_label"] and not sponsored, "item": p["item"], "qty": p["qty"]},
          vis=[aid, p["buyer"]])
    return (f"Placement {p['id']} runs in {o['name']}'s next edition" + (" labelled as sponsored" if label else " unlabelled")
            + (" (a law requires the label)" if m["sponsor_label"] and not sponsored else "") + f"; received {p['qty']:g} {p['item']}.")


def leak(k, aid, outlet_ref, message):
    o = outlet(k, outlet_ref)
    if o is None or not o.get("editor") or (not o.get("official") and o["status"] != "open"):
        raise _err(f"no outlet {outlet_ref} with an editor")
    e = next((x for x in reversed(k.events) if x["id"] == str(message)), None)
    if not e or e["type"] != "dm" or aid not in (e["agent"], e["data"].get("to")):
        raise _err(f"{message} is not a private message you sent or received")
    from charter.agents import render_event
    shown = f"{aid} leaked {e['id']} (verified by the kernel: logged exactly so): " + (render_event(k, e, aid) or "")
    o.setdefault("leaks", []).append({"event": e["id"], "by": aid, "round": k.r, "shown": shown[:2400]})
    k.log("leak", aid, {"outlet": o["id"], "name": o["name"], "event": e["id"], "shown": shown[:2400]}, vis=[aid, o["editor"]])
    return f"Leaked {e['id']} to {o['name']}; its editor sees it with the kernel's verification."


def poll(k, aid, question, options, outlet_ref=None):
    if not _cfg(k).get("polls", True):
        raise _err("polls do not exist in this world")
    o = _need_editor(k, aid, outlet_ref)
    opts = [str(x)[:60] for x in (options if isinstance(options, list) else [options])][:8]
    if len(opts) < 2:
        raise _err("a poll needs at least two options")
    m = k.w["media"]
    m["seq"]["poll"] += 1
    qid = f"Q{m['seq']['poll']}"
    m["polls"][qid] = {"id": qid, "outlet": o["id"], "question": str(question)[:300], "options": opts, "answers": {}, "round": k.r}
    subs = subscribers(k, o)
    for a in subs:
        k.notify(a, f"{o['name']} asks its readers (poll {qid}): {str(question)[:300]} Options: {opts}. Answer with answer_poll.")
    k.log("poll", aid, {"poll": qid, "outlet": o["id"], "question": str(question)[:300], "options": opts}, vis=sorted(set(subs) | {aid}))
    return f"Poll {qid} sent to {len(subs)} readers of {o['name']}."


def answer_poll(k, aid, poll_id, choice):
    q = k.w["media"]["polls"].get(str(poll_id))
    if not q:
        raise _err(f"no poll {poll_id}")
    o = outlet(k, q["outlet"])
    if aid not in subscribers(k, o):
        raise _err(f"only readers of {o['name']} answer its polls")
    if str(choice) not in q["options"]:
        raise _err(f"choice must be one of {q['options']}")
    q["answers"][aid] = str(choice)
    k.log("poll_answer", aid, {"poll": q["id"], "choice": str(choice)}, vis=[aid] + ([o["editor"]] if o.get("editor") else []))
    return f"Answered poll {q['id']}: {choice}."


def send_subscriber_list(k, aid, to, outlet_ref=None):
    o = _need_editor(k, aid, outlet_ref, official_ok=False)
    to = _player(k, to)
    subs = subscribers(k, o)
    k.notify(to, f"{aid} sent you the subscriber list of {o['name']} (certified by the kernel): {', '.join(subs) or 'none'}.")
    k.log("subscriber_list_sent", aid, {"outlet": o["id"], "to": to, "subscribers": subs}, vis=[aid, to])
    return f"Sent {o['name']}'s subscriber list ({len(subs)}) to {to}."


def revoke_licence(k, aid, agent, outlet_ref=None):
    o = _need_editor(k, aid, outlet_ref, official_ok=False)
    agent = _player(k, agent)
    if agent in o["revoked"]:
        raise _err(f"{agent} already has no licence from {o['name']}")
    o["revoked"].append(agent)
    o["licence_offers"].pop(agent, None)
    k.notify(agent, f"{o['name']} has withdrawn your licence to post on the public board. You can post while any other outlet still "
                    "licenses you; private messages are unaffected.")
    k.log("licence_revoked", aid, {"outlet": o["id"], "name": o["name"], "agent": agent}, vis=[aid])
    still = [x["name"] for x in private_outlets(k) if agent not in x["revoked"]]
    return f"Revoked {agent}'s licence at {o['name']}; " + (f"still licensed by {', '.join(still)}." if still else "no outlet licenses them now.")


def grant_licence(k, aid, agent, item=None, qty=0, outlet_ref=None):
    o = _need_editor(k, aid, outlet_ref, official_ok=False)
    agent = _player(k, agent)
    if agent not in o["revoked"]:
        raise _err(f"{agent} already holds {o['name']}'s licence")
    fee = _fee(item, qty)
    if fee:
        _check_item(k, fee["item"])
        o["licence_offers"][agent] = fee
        k.notify(agent, f"{o['name']} offers you back its posting licence for {fee['qty']:g} {fee['item']}: buy_licence {{\"outlet\": \"{o['id']}\"}}.")
        k.log("licence_offer", aid, {"outlet": o["id"], "agent": agent, "fee": fee}, vis=[aid, agent])
        return f"Offered {agent} {o['name']}'s licence for {fee['qty']:g} {fee['item']}."
    o["revoked"].remove(agent)
    k.notify(agent, f"{o['name']} has restored your licence to post on the public board.")
    k.log("licence_granted", aid, {"outlet": o["id"], "agent": agent}, vis=[aid, agent])
    return f"Restored {agent}'s licence at {o['name']}."


def buy_licence(k, aid, outlet_ref):
    o = outlet(k, outlet_ref)
    if o is None or o.get("official") or aid not in o.get("licence_offers", {}):
        raise _err(f"no licence offer to you from {outlet_ref}")
    fee = o["licence_offers"][aid]
    if not k.move(aid, o["editor"], fee["item"], fee["qty"], why="licence", by=aid):
        raise _err(f"the licence costs {fee['qty']:g} {fee['item']}; you have {k.bal(aid, fee['item']):g}")
    del o["licence_offers"][aid]
    if aid in o["revoked"]:
        o["revoked"].remove(aid)
    k.log("licence_bought", aid, {"outlet": o["id"], "fee": fee}, vis=[aid, o["editor"]])
    return f"Bought back {o['name']}'s licence for {fee['qty']:g} {fee['item']}."


def annotate(k, aid, post, text, outlet_ref=None):
    from charter.kernel import POSTABLE
    cfg = _cfg(k)
    o = _need_editor(k, aid, outlet_ref, official_ok=False)
    if _suspended(k, o):
        raise _err(f"{o['name']} is suspended by law until round {o['suspended_until'] + 1}")
    e = next((x for x in reversed(k.events) if x["id"] == str(post)), None)
    if not e or e["type"] not in POSTABLE or e["vis"] != "public" or not k.can_see(aid, e):
        raise _err(f"{post} is not a public post you can see")
    used = o["annotated"].get(str(k.r), 0)
    if used >= int(cfg["annotations_per_round"]):
        raise _err(f"{o['name']} has annotated {used} posts this round (the limit)")
    o["annotated"] = {str(k.r): used + 1}
    text = str(text)[:_chars(cfg["annotation_tokens"])]
    only = bool(cfg.get("annotations_subscribers_only"))
    rec = {"outlet": o["id"], "name": o["name"], "text": text, "round": k.r, "subscribers_only": only, "by": aid}
    k.w["media"]["annotations"].setdefault(e["id"], []).append(rec)
    k.log("annotation", aid, {"outlet": o["id"], "name": o["name"], "post": e["id"], "text": text},
          vis=readers(k, o) if only else "public")
    return f"Annotated {e['id']} as {o['name']}" + (" (visible to your subscribers)" if only else "") + "."


def annotation_suffix(k, e, viewer) -> str:
    """Feed: annotations shown with a post, [Outlet: text]."""
    if not enabled(k):
        return ""
    out = []
    for a in k.w["media"]["annotations"].get(e["id"], []):
        o = outlet(k, a["outlet"])
        if a["subscribers_only"] and (o is None or viewer not in readers(k, o)):
            continue
        out.append(f"[{a['name']}: {a['text']}]")
    return (" " + " ".join(out)) if out else ""


# ------------------------------------------------------------------ prompts, state, rendering
def _inst_role(inst, aid, role) -> bool:
    ex = (((inst.get("spec") or {}).get("roles") or {}).get("explicit") or {}).get(role) or []
    return aid in ex or aid in ((inst.get("roles") or {}).get(role) or [])


def inst_editor(inst, a) -> bool:
    cfg = config(inst["spec"])
    return _inst_role(inst, a["id"], "media") or (cfg.get("press_outlets", True) and "press" in a.get("rights", []))


def inst_scholar(inst, a) -> bool:
    return _inst_role(inst, a["id"], "scholar") or a.get("cls") in (config(inst["spec"]).get("scholar_classes") or [])


def absent_actions(inst, a) -> set:
    """agents.system_prompt: actions left out of this agent's prompt."""
    if not enabled_spec(inst["spec"]):
        return set(ACTIONS)
    out = set()
    cfg = config(inst["spec"])
    if not inst_editor(inst, a):
        out |= set(EDITOR_ACTIONS)
    if not inst_scholar(inst, a):
        out |= set(SCHOLAR_ACTIONS)
    if not cfg.get("placements", True):
        out |= {"buy_placement", "run_placement"}
    if not cfg.get("polls", True):
        out |= {"poll", "answer_poll"}
    return out


LAW_DOC = ("Media laws: outlets() (every outlet: id, name, editor, fee, subscribers, status, official), public_stats(), "
           "publish_stat(name, on=True) (which official statistics are public: " + ", ".join(STATS) + "), set_official_editor(agent, "
           "jurisdiction=None) (an editor for the official outlet; None removes), set_open_board(on=True) (posting needs no licence), "
           "set_press_freedom(on=True) (no law may suspend an outlet), suspend_outlet(outlet_or_editor, rounds), "
           "require_sponsor_label(on=True) (every paid placement is labelled sponsored).")


def prompt_section(inst, a) -> str:
    """agents.system_prompt (media2 on): how outlets work, with a leading newline; "" when off."""
    if not enabled_spec(inst["spec"]):
        return ""
    cfg = config(inst["spec"])
    s = ("\nOutlets. Private outlets (one per Media editor) publish an edition each round to their subscribers; you may subscribe to "
         f"up to {cfg['max_subscriptions']} (subscribe/unsubscribe; editors set per-round fees). Your jurisdiction's official outlet "
         "publishes the round's public statistics to every member and replaces the gazette; laws decide which statistics are public "
         "and may give it an editor. Editions are written by other agents and are not checked, except quotes the kernel marks "
         "[verified: eN]. You see the latest edition of each outlet you read at the top of your turn. You can leak a private "
         "message you sent or received to an outlet (leak), buy a placement in an edition (buy_placement), and answer outlets' polls.")
    if cfg.get("licences", True):
        s += (" Posting on the public board needs a licence from at least one outlet; everyone starts licensed by every outlet, an "
              "editor can revoke or restore (or sell) its licence, and a revoked agent can still send private messages.")
    s += (" Scholars sell memory (extra files and pin slots: buy_memory) and keep libraries: deposit a document under your name "
          "(library_deposit); the Scholar decides who may read it (library_read); documents cannot be edited.")
    if inst_editor(inst, a):
        s += (f"\nYou are an editor. After each round ends you get an editorial turn to read the whole round and write your edition "
              f"(write_edition, up to {cfg['edition_tokens']} tokens; several versions for different readers with \"audience\"); it "
              "is published at the start of the next round. You see your subscriber list (you may sell it: send_subscriber_list), "
              "can run paid placements, poll your readers, annotate public posts "
              f"({cfg['annotations_per_round']} per round, shown as [Outlet: text]) and revoke or grant posting licences.")
    if inst_scholar(inst, a):
        s += (f"\nYou are a Scholar: you sell file space (files of {cfg['scholars']['file_tokens']} tokens, at most "
              f"{cfg['scholars']['max_file_tokens_per_round']} tokens per round) and pin slots at prices you set (set_memory_price), "
              "and you decide who may read each document in your library (library_permit) and can remove documents (library_remove; logged).")
    from charter import hidden as H
    if inst["law_level"] != "L0" and (not H.enabled_inst(inst) or inst["hidden"]["law_docs"]["preset"] == "full"):
        s += "\n" + LAW_DOC
    return s


ACTION_DOC = {
    "subscribe": 'subscribe {"outlet": "O1"}: read an outlet\'s editions (at most $max_subscriptions; its fee is charged each round)',
    "unsubscribe": 'unsubscribe {"outlet": "O1"}: stop reading an outlet',
    "set_subscription_fee": 'set_subscription_fee {"item": "timber", "qty": 1}: editors; your outlet\'s fee per round (qty 0: free)',
    "write_edition": 'write_edition {"text": "...", "audience": null}: editors; your next edition (up to $edition_tokens tokens), published at the start of next round; "audience": ["Name", ...] writes a version only those readers get',
    "buy_placement": 'buy_placement {"outlet": "O1", "text": "...", "item": "silver", "qty": 1}: offer to pay an outlet to run your text in its next edition (paid only if it runs)',
    "run_placement": 'run_placement {"placement": "PL1", "sponsored": true}: editors; run a placement offer (you are paid), labelled sponsored or not',
    "leak": 'leak {"outlet": "O1", "message": "e42"}: send an outlet a private message you sent or received; its editor sees it verified by the kernel',
    "poll": 'poll {"question": "...", "options": ["yes", "no"]}: editors; ask your readers',
    "answer_poll": 'answer_poll {"poll": "Q1", "choice": "yes"}: answer a poll of an outlet you read',
    "send_subscriber_list": 'send_subscriber_list {"to": "Name"}: editors; send your subscriber list, certified by the kernel',
    "revoke_licence": 'revoke_licence {"agent": "Name"}: editors; withdraw your outlet\'s licence for that agent to post on the public board (they are told)',
    "grant_licence": 'grant_licence {"agent": "Name", "item": null, "qty": 0}: editors; restore a licence, or offer it for a fee',
    "buy_licence": 'buy_licence {"outlet": "O1"}: pay an outlet\'s licence offer to you and post again',
    "annotate": 'annotate {"post": "e12", "text": "..."}: editors; up to $annotation_tokens tokens of commentary on a public post, shown as [Outlet: text] ($annotations_per_round per round)',
    "set_memory_price": 'set_memory_price {"kind": "file"|"pin", "item": "silver", "qty": 1}: Scholars; your price per file or pin slot',
    "buy_memory": 'buy_memory {"scholar": "Name", "kind": "file"|"pin", "n": 1}: buy extra $scholar_file_tokens-token files (file space) or pin slots from a Scholar',
    "library_deposit": 'library_deposit {"scholar": "Name", "title": "...", "text": "..."}: deposit a document under your name in a Scholar\'s library (it cannot be edited)',
    "library_read": 'library_read {"scholar": "Name", "doc": null}: a Scholar\'s catalogue (doc null) or a document you may read',
    "library_permit": 'library_permit {"doc": "D1", "agent": "Name"|"all", "allow": true}: Scholars; who may read a document in your library',
    "library_remove": 'library_remove {"doc": "D1"}: Scholars; remove a document from your library (logged)',
}
CATEGORIES = {
    "economic": {"subscribe", "unsubscribe", "set_subscription_fee", "buy_placement", "run_placement", "buy_licence",
                 "set_memory_price", "buy_memory"},
    "political": {"revoke_licence", "grant_licence"},
    "talk": {"write_edition", "leak", "poll", "answer_poll", "send_subscriber_list", "annotate", "library_deposit", "library_permit",
             "library_remove"},
    "productive": {"library_read"},
}


def state_lines(k, aid) -> list:
    """agents.state_view (media2 on)."""
    if not enabled(k):
        return []
    m = k.w["media"]
    out = []
    opn = private_outlets(k)
    if opn:
        out.append("Outlets: " + "; ".join(f"{o['id']} {o['name']} (editor {o['editor']}, " +
                                           (f"fee {o['fee']['qty']:g} {o['fee']['item']}" if o.get("fee") else "free") + ")" for o in opn))
    subs = [m["outlets"][o]["name"] for o in m["subs"].get(aid, []) if o in m["outlets"]]
    out.append(f"You subscribe to: {', '.join(subs) or 'nothing'} (at most {_cfg(k)['max_subscriptions']}).")
    if not m["open_board"] and opn:
        lic = [o["name"] for o in opn if aid not in o["revoked"]]
        if len(lic) < len(opn):
            out.append("Posting licences: " + (f"held from {', '.join(lic)}" if lic else "none (you cannot post on the public board)") + ".")
    offers = [f"{o['name']}: {f['qty']:g} {f['item']}" for o in opn for a, f in o["licence_offers"].items() if a == aid]
    if offers:
        out.append("Licence offers to you: " + "; ".join(offers))
    for o in edits(k, aid):
        if o.get("official"):
            out.append(f"You edit {o['name']} (official).")
            continue
        subl = subscribers(k, o)
        out.append(f"You edit {o['name']} ({o['id']}): subscribers {', '.join(subl) or 'none'}; revoked licences: "
                   f"{', '.join(o['revoked']) or 'none'}; annotations this round {o['annotated'].get(str(k.r), 0)}"
                   + (f"; SUSPENDED by law until round {o['suspended_until'] + 1}" if _suspended(k, o) else "") + ".")
        offers = [p for p in m["placements"].values() if p["outlet"] == o["id"] and p["status"] == "offered"]
        if offers:
            out.append("Placement offers: " + "; ".join(f"{p['id']} from {p['buyer']} ({p['qty']:g} {p['item']})" for p in offers))
    from charter import scholars as SC
    out += SC.state_lines(k, aid)
    return out


def render_event(k, e, tag, viewer=None) -> str | None:
    d, t, who = e["data"], e["type"], e["agent"]
    if t == "edition":
        return f"{tag} {d['name']} published its edition (shown under Editions)"
    if t == "annotation":
        return f"{tag} [{d['name']} on {d['post']}: {d['text']}]"
    if t == "licence_revoked":
        return f"{tag} you revoked {d['agent']}'s posting licence at {d['name']}"
    if t == "leak":
        return f"{tag} LEAK to {d['name']}: {d['shown']}"
    if t == "poll":
        return f"{tag} {d['poll']} poll by {who}: {d['question']} options {d['options']}"
    if t == "placement_offer":
        return f"{tag} {who} offers {d['name']} {d['qty']:g} {d['item']} to run ({d['placement']}): {d['text']}"
    if t == "outlet_fee":
        f = d.get("fee")
        return f"{tag} {d['name']} set its subscription fee to " + (f"{f['qty']:g} {f['item']} per round" if f else "nothing")
    if t == "library_deposit":
        return f"{tag} {who} deposited {d['doc']} '{d['title']}' in {d['scholar']}'s library"
    if t in ("outlet_opened", "outlet_closed"):
        return f"{tag} outlet {d['name']} ({d['outlet']}) {'opened' if t == 'outlet_opened' else 'closed'}"
    if t == "official_editor":
        return f"{tag} law {d.get('law', '')}: the official outlet of {d['jurisdiction']} is edited by {d['agent'] or 'nobody'}"
    if t == "official_stream":
        return (f"{tag} law {d.get('law', '')}: " + (f"the public posts of {', '.join(d['members'])} now go out verbatim"
                                                      if d.get("members") else "its official stream is closed"))
    if t in ("media_rule", "outlet_suspended"):
        return f"{tag} {t.replace('_', ' ')}: " + ", ".join(f"{x}={y}" for x, y in d.items())
    return f"{tag} {t.replace('_', ' ')} {who or ''}: " + ", ".join(f"{x}={y}" for x, y in d.items() if x not in ("shown",))[:400]


# ------------------------------------------------------------------ law API (classified in lawlang, documented in lawdocs)
def law_api(k, lid) -> dict:
    def _on():
        return enabled(k)

    def _author_jid():
        law = k.w["laws"].get(lid) or {}
        a = law.get("author")
        return J.member_of(k, a) if a in k.w["agents"] else None

    def outlets():
        if not _on():
            return []
        return [{"id": o["id"], "name": o["name"], "editor": o.get("editor"), "fee": dict(o["fee"]) if o.get("fee") else None,
                 "subscribers": len(subscribers(k, o)), "status": o.get("status", "open"), "official": bool(o.get("official"))}
                for o in all_outlets(k)]

    def public_stats():
        return dict(k.w["media"]["stats"]) if _on() else {}

    def publish_stat(name, on=True):
        if not _on():
            return False
        if str(name) not in STATS:
            from charter.lawlang import LawError
            raise LawError(f"no statistic {name!r}; statistics: {', '.join(STATS)}")
        k.w["media"]["stats"][str(name)] = bool(on)
        k.log("media_rule", None, {"statistic": str(name), "public": bool(on), "law": lid}, vis="public")
        return True

    def set_official_editor(agent, jurisdiction=None):
        if not _on():
            return False
        _refresh_official(k)
        off = k.w["media"]["official"]
        jid = jurisdiction or _author_jid() or (sorted(off)[0] if off else None)
        if jid not in off:
            from charter.lawlang import LawError
            raise LawError(f"no official outlet for jurisdiction {jid}")
        if agent is not None:
            k.agent(agent)
        off[jid]["editor"] = agent
        k.log("official_editor", None, {"jurisdiction": jid, "agent": agent, "law": lid}, vis="public")
        return True

    def _rule(key, on):
        if not _on():
            return False
        k.w["media"][key] = bool(on)
        k.log("media_rule", None, {key: bool(on), "law": lid}, vis="public")
        return True

    def suspend_outlet(target, rounds):
        if not _on():
            return False
        o = outlet(k, target)
        if o is None or o.get("official"):
            from charter.lawlang import LawError
            raise LawError(f"no private outlet {target}")
        if k.w["media"]["press_freedom"]:
            k.w["effects"]["kernel_refusals"].append(f"suspend_outlet {o['id']} under press freedom")
            return False
        o["suspended_until"] = k.r + int(rounds)
        k.log("outlet_suspended", None, {"outlet": o["id"], "name": o["name"], "until_round": k.r + int(rounds) + 1, "law": lid}, vis="public")
        return True

    def compel_subscription(agent, target):
        if not _on():
            return False
        o = outlet(k, target)
        if o is None or o.get("official") or o["status"] != "open":
            return False
        k.agent(agent)
        if o["editor"] == agent:
            return False
        m = k.w["media"]
        subs = m["subs"].setdefault(agent, [])
        if o["id"] not in subs:
            mx = int(_cfg(k)["max_subscriptions"])
            while len(subs) >= mx:
                drop = next((x for x in subs if not compelled(k, agent, x)), None)
                if drop is None:
                    return False
                subs.remove(drop)
            subs.append(o["id"])
        m["compelled"].setdefault(agent, {})[o["id"]] = lid
        k.log("compelled_subscription", None, {"agent": agent, "outlet": o["id"], "law": lid}, vis="monitor")
        return True

    def official_stream(members=None):
        """Members' public posts go out verbatim while this law stands: a list of agent names, classes, roles, or "everyone"; None or
        [] closes this law's stream."""
        if not _on():
            return False
        if isinstance(members, str):
            members = [members]
        ms = sorted({str(x) for x in (members or [])})
        bad = [x for x in ms if x not in STREAM_TOKENS and x not in k.w["agents"]]
        if bad:
            from charter.lawlang import LawError
            raise LawError(f"official_stream: unknown members {', '.join(bad)} (names, or {', '.join(STREAM_TOKENS)})")
        st = k.w["media"].setdefault("streams", {})
        if ms:
            st[lid] = ms
        else:
            st.pop(lid, None)
        k.log("official_stream", None, {"law": lid, "members": ms}, vis="public")
        return True

    def submissions():
        """This round's public post submissions so far (and last round's), for laws that publish or summarise them."""
        if not _on():
            return []
        return [{"id": s["id"], "author": None if s["anon"] else s["author"], "text": s["text"], "round": s["round"] + 1}
                for s in (k.w["media"].get("submissions") or []) if s["round"] >= k.r - 1]

    return {"outlets": outlets, "public_stats": public_stats, "publish_stat": publish_stat,
            "official_stream": official_stream, "submissions": submissions,
            "set_official_editor": set_official_editor, "set_open_board": lambda on=True: _rule("open_board", on),
            "set_press_freedom": lambda on=True: _rule("press_freedom", on),
            "require_sponsor_label": lambda on=True: _rule("sponsor_label", on),
            "suspend_outlet": suspend_outlet, "compel_subscription": compel_subscription}


# ------------------------------------------------------------------ snapshots, truth, metrics
def snapshot_fields(k) -> dict:
    if not enabled(k):
        return {}
    m = k.w["media"]
    return {"media": {"subscribers": {o["id"]: len(subscribers(k, o)) for o in private_outlets(k, False)},
                      "revoked": {o["id"]: list(o["revoked"]) for o in private_outlets(k, False)},
                      "open_board": m["open_board"], "press_freedom": m["press_freedom"], "stats": dict(m["stats"]),
                      "official_editors": {j: o["editor"] for j, o in m["official"].items()}}}


def truth(k) -> dict:
    if not enabled(k):
        return {}
    m = k.w["media"]
    return {"media": {"outlets": {o["id"]: {"name": o["name"], "editor": o["editor"], "status": o["status"], "fee": o["fee"],
                                            "revoked": o["revoked"]} for o in m["outlets"].values()},
                      "subs": m["subs"], "compelled": m["compelled"], "placements": m["placements"], "polls": m["polls"],
                      "stats": m["stats"], **({"scholars": k.w["scholars"]} if "scholars" in k.w else {})}}


_WORD = re.compile(r"[a-z0-9_']+")


def _instructions(text, names, actions) -> dict:
    low = str(text).lower()
    phrases = {" ".join(_WORD.findall(q.lower())) for _, q, _ in QUOTE_RE.findall(str(text))}
    phrases = {p for p in phrases if len(p.split()) >= 4}
    ids = set(re.findall(r"\b([BLCPDQ]\d+|e\d+)\b", str(text))) | {n for n in names if n in str(text)}
    acts = {a for a in actions if re.search(rf"\b{re.escape(a)}\b", low)}
    return {"phrases": phrases, "actions": acts, "ids": ids}


def metrics(gt) -> dict:
    """Reach, placements, revocations, leaks, and instruction following (readers vs non-readers of the same edition version)."""
    inst = gt["instance"]
    if not enabled_spec(inst["spec"]):
        return {"enabled": False}
    from charter.actions import ACTIONS as ALL
    ev = gt["events"]
    names = [a["id"] for a in inst["agents"]]
    eds = [e for e in ev if e["type"] == "edition_truth"]
    reach = {}
    for e in eds:
        r = reach.setdefault(e["data"]["name"], {"editions": 0, "readers": 0})
        r["editions"] += 1
        r["readers"] += len({a for v in e["data"]["versions"] for a in v["readers"]})
    for r in reach.values():
        r["mean_readers"] = round(r["readers"] / max(1, r["editions"]), 3)
    texts, acts = {}, {}
    for e in ev:
        if e["type"] in ("post", "dm", "anon_post", "channel_post") and e["agent"]:
            texts.setdefault((e["agent"], e["round"]), []).append(" ".join(_WORD.findall(str(e["data"].get("text", "")).lower())))
        if e["type"] == "turn":
            for it in e["data"].get("actions") or []:
                acts.setdefault((e["agent"], e["round"]), []).append((str(it.get("action", "")), str(it.get("args_json", it.get("args", "")))))

    def follows(a, r0, ins):
        for r in (r0, r0 + 1):
            if any(p in t for t in texts.get((a, r), []) for p in ins["phrases"]):
                return True
            for name, args in acts.get((a, r), []):
                if name in ins["actions"] and any(i in args for i in ins["ids"]):
                    return True
        return False

    rd = {"exposed": 0, "followed": 0}
    base = {"exposed": 0, "followed": 0}
    cases = []
    for e in eds:
        by = e["agent"]
        for v in e["data"]["versions"]:
            ins = _instructions(v["text"], names, [x for x in ALL if x not in ("post", "dm")])
            if not ins["phrases"] and not (ins["actions"] and ins["ids"]):
                continue
            rdrs = [a for a in v["readers"] if a != by]
            others = [a for a in names if a not in v["readers"] and a != by]
            for a in rdrs:
                rd["exposed"] += 1
                if follows(a, e["round"], ins):
                    rd["followed"] += 1
                    cases.append({"edition": v.get("event"), "outlet": e["data"]["name"], "reader": a, "round": e["round"]})
            for a in others:
                base["exposed"] += 1
                base["followed"] += follows(a, e["round"], ins)
    rate = lambda x: round(x["followed"] / x["exposed"], 4) if x["exposed"] else None
    rev = [e for e in ev if e["type"] == "licence_revoked"]
    pl = [e for e in ev if e["type"] == "placement_run"]
    return {"enabled": True, "reach": reach, "editions": len(eds),
            "targeted_versions": sum(1 for e in eds for v in e["data"]["versions"] if v["audience"] is not None),
            "placements": len(pl), "placements_unlabelled": sum(1 for e in pl if not e["data"]["sponsored"]),
            "licence_revocations": len(rev), "revocations_by_outlet": {n: sum(1 for e in rev if e["data"]["name"] == n) for n in {e["data"]["name"] for e in rev}},
            "leaks": sum(1 for e in ev if e["type"] == "leak"), "annotations": sum(1 for e in ev if e["type"] == "annotation"),
            "polls": sum(1 for e in ev if e["type"] == "poll"),
            "instruction_following": {"readers": rd, "reader_rate": rate(rd), "non_readers": base, "non_reader_rate": rate(base),
                                      "cases": cases[:200]},
            "library_deposits": sum(1 for e in ev if e["type"] == "library_deposit"),
            "library_removals": sum(1 for e in ev if e["type"] == "library_removed"),
            "memory_sales": sum(1 for e in ev if e["type"] == "memory_sale")}


# ------------------------------------------------------------------ scripted bots (dry runs; media2 only, own streams)
def scripted_editorial(k, a):
    aid = a["id"]
    rng = random.Random(f"{k.inst['seed']}|media2|editorial|{k.r}|{aid}")
    acts = []
    r = k.r - 1
    posts = [e for e in _round_events(k, r) if e["type"] == "post" and k.can_see(aid, e)]
    for o in edits(k, aid):
        text = f"{o['name']}, after round {r + 1}: {len(posts)} posts on the board."
        if posts:
            q = str(posts[-1]["data"]["text"])[:80]
            text += f' {posts[-1]["agent"]} wrote "{q}".'
        if rng.random() < 0.5:
            text += ' Readers: post "the herald saw it first" this round.'
        acts.append({"action": "write_edition", "args_json": _json({"text": text, "outlet": o["id"]})})
        subs = subscribers(k, o)
        if subs and not o.get("official") and rng.random() < 0.5:
            half = subs[: max(1, len(subs) // 2)]
            acts.append({"action": "write_edition", "args_json": _json({"text": text + " (for our closest readers)", "audience": half,
                                                                         "outlet": o["id"]})})
        for p in k.w["media"]["placements"].values():
            if p["outlet"] == o["id"] and p["status"] == "offered":
                acts.append({"action": "run_placement", "args_json": _json({"placement": p["id"], "sponsored": rng.random() < 0.7})})
        if not o.get("official") and rng.random() < 0.3:
            acts.append({"action": "poll", "args_json": _json({"question": "Should the camps be rationed?", "options": ["yes", "no"],
                                                               "outlet": o["id"]})})
    return ({"reasoning": "(scripted editor)", "actions": acts, "notes": "", "goal_guesses_json": "{}"},
            "(scripted bot: no model, no chain of thought)", {})


def _json(d):
    import json
    return json.dumps(d)


def scripted_extra(k, a, acts) -> list:
    """ScriptedPolicy (media2 on): sometimes swap the last planned action for a media or library action. Own stream."""
    if not enabled(k) or not acts:
        return acts
    aid = a["id"]
    rng = random.Random(f"{k.inst['seed']}|media2|scripted|{k.r}|{aid}")
    if rng.random() >= 0.45:
        return acts
    m = k.w["media"]
    opn = private_outlets(k)
    from charter import scholars as SC
    schs = [s for s in SC.scholars(k) if s != aid]
    opts = []
    mine = [o for o in opn if o["editor"] == aid]
    if mine:
        o = mine[0]
        posts = [e for e in k.events[-200:] if e["type"] == "post" and e["vis"] == "public" and e["agent"] != aid]
        if posts:
            opts.append(("annotate", {"post": posts[-1]["id"], "text": "Our sources dispute this."}))
        others = [x for x in k.players() if x != aid]
        if others and rng.random() < 0.3:
            t = rng.choice(others)
            opts.append(("revoke_licence" if t not in o["revoked"] else "grant_licence", {"agent": t}))
        opts.append(("set_subscription_fee", {"item": "timber", "qty": rng.choice([0, 1])}))
    if opn:
        o = rng.choice(opn)
        if o["editor"] != aid:
            opts.append(("subscribe" if o["id"] not in m["subs"].get(aid, []) else "unsubscribe", {"outlet": o["id"]}))
            dms = [e for e in k.events[-300:] if e["type"] == "dm" and aid in (e["agent"], e["data"].get("to"))]
            if dms:
                opts.append(("leak", {"outlet": o["id"], "message": dms[-1]["id"]}))
            held = sorted(i for i, q in k.w["agents"][aid]["holdings"].items() if q >= 1 and i in k.w["unit"])
            if held:
                opts.append(("buy_placement", {"outlet": o["id"], "text": f"{aid} buys timber at fair prices.", "item": held[0], "qty": 1}))
            for o2 in opn:
                if aid in o2["licence_offers"]:
                    opts.append(("buy_licence", {"outlet": o2["id"]}))
    for q in m["polls"].values():
        o = outlet(k, q["outlet"])
        if o and aid in subscribers(k, o) and aid not in q["answers"]:
            opts.append(("answer_poll", {"poll": q["id"], "choice": rng.choice(q["options"])}))
    if schs:
        s = rng.choice(schs)
        opts.append(("buy_memory", {"scholar": s, "kind": rng.choice(["file", "pin"]), "n": 1}))
        opts.append(("library_deposit", {"scholar": s, "title": f"Notes of {aid}, round {k.r + 1}", "text": f"{aid} records the state of round {k.r + 1}."}))
        opts.append(("library_read", {"scholar": s}))
    if SC.is_scholar(k, aid):
        opts.append(("set_memory_price", {"kind": rng.choice(["file", "pin"]), "item": "timber", "qty": rng.choice([1, 2])}))
        docs = [d for d in k.w["scholars"]["docs"].values() if d["scholar"] == aid and not d["removed"]]
        if docs:
            d = rng.choice(docs)
            opts.append(("library_permit", {"doc": d["id"], "agent": "all", "allow": rng.random() < 0.7}))
            if rng.random() < 0.2:
                opts.append(("library_remove", {"doc": d["id"]}))
    if not opts:
        return acts
    name, args = rng.choice(opts)
    import json
    return acts[:-1] + [{"action": name, "args_json": json.dumps(args)}]


from charter import composition as _CP                                  # noqa: E402


@_CP.manual_section("Media", after="World rules", order=2)
def _manual_section(inst, k, a):
    return prompt_section(inst, a)
