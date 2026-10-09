"""Channels v2 (review 14 §4.6; ARCHITECTURE D-33, D-37; wave 9 package C): one channel structure for every communication form.

Spec flag `channels.v2` (default off: nothing here runs and every world is byte-identical to before). With it on:

A channel is a named, owned, append-only log with access rules, a v2 record in k.w["channels"] (it keeps the old keys owner,
members and open, so every reader of the old records keeps working):
    {"v": 2, "id", "owner": agent id | institution id (a jurisdiction or a contract association) | "world", "purpose",
     "readers": <selector>, "writers": <selector>, "listed": bool (in the directory; unlisted ids carry a random suffix, so the
     address is a capability), "inbox": bool (send to the owner delivers here), "identity": "named" | "anonymous",
     "retention": "all" | "joined" (new readers see only posts made after they joined), "rate": posts per agent per round | None,
     "members": [aid] (explicit admits), "subscribers": [aid], "since": {aid: event seq} (when each joined), "known": [aid] (who
     learned the address), "known_via": [channel] (its address was posted there: its readers know it), "known_public": bool,
     "open": writers == {"all": true} (the old flag), "created", "by"}
Selectors are a closed vocabulary, resolved when a post is read or written (no code in selectors):
    {"agents": [aid, ...]}  {"members": true} (this channel's own members)  {"members": "<iid>"} (an institution's members)
    {"office": "<iid>.<right>"} (holders of that right)  {"subscribers": true}  {"all": true}  {"camp": "<camp>"} (agents present at
    a camp: its harvest right or an open typed camp)  {"address": true} (anyone who knows the channel's address)
    {"any": [selector, ...]}, a list, or a dict with several keys: the union.
The owner (an agent) always reads and writes its channel. Who may change a channel: its owning agent, or for an institution's
channel the holders of its speak office "<iid>.speak"; the owner's laws hook before_set_channel, before_post, before_subscribe,
before_admit and before_expel (dispatch.hooks.bound_laws binds the owner's laws to changes in its channels: owner_laws).

Every agent and every institution has an inbox ("@<id>"); `send` to an account delivers there (a DM to an agent is a `dm` event
carrying channel_id "@<agent>"; to an institution, a channel_post in its inbox). The world owns the square(s): one, or one per
camp (spec channels.square: one by default; per_camp squares are read and written by the agents present at the camp), rate-limited. Anyone may open a channel (D-33's residual); the Press Act (charter/code/press.py)
seeds today's press gate where a preset wants it (spec channels.found_right does the same without the default code).

Delivery (spec channels.delivery, pull by default): pull leaves channel posts out of the feed and shows, per channel an agent
follows, the unread count and the latest headline (state_lines); `read` opens one (a look-up). DMs and the agent's own inbox are
always pushed. push: posts reach the feed as before.

Institutions are reached only through the helpers owner_kind, institutions, is_member and may_speak_for, which read WP-D's
charter/institutions.py (institutions.unified on or off). Media2 is untouched (WP-H re-expresses it on channels).
"""
from __future__ import annotations

import bisect
import hashlib
import json
import re

FIELDS = ("purpose", "readers", "writers", "listed", "inbox", "identity", "retention", "rate")
SELECTORS = ("agents", "members", "office", "subscribers", "all", "camp", "address", "any")
IDENTITIES = ("named", "anonymous")
RETENTIONS = ("all", "joined")
SQUARES = ("one", "per_camp", "none")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-.]{0,39}$")
WORLD = "world"
SQUARE = "square"
DEFAULTS = {"v2": False, "delivery": "pull", "square": "one", "square_rate": 2, "found_right": None, "headlines": 8}
ACTIONS = ("send", "read", "open_channel", "set_channel", "join_channel", "leave_channel")
OLD_ACTIONS = ("create_channel", "channel_post")                       # replaced by open_channel and send/post under v2
# Actions whose handler differs under channels.v2 (actions._act): the same verbs, with channels.
OVERRIDES = {"post": "channels:act_post", "standing_order": "channels:act_standing_order"}
# P4.5 agency: what an authorization may also cover under channels.v2 (contracts.act_authorize): sending in the grantor's name.
AGENCY = {"send": "send up to qty messages per round in the grantor's name (send with \"as\": the grantor)"}


# ---------------------------------------------------------------------- the flag
def _spec(x) -> dict:
    sp = getattr(x, "spec", None)
    if sp is None and isinstance(x, dict):
        sp = x["spec"] if isinstance(x.get("spec"), dict) else x
    return sp or {}


def on(x) -> bool:
    """Spec channels.v2 (x: a kernel, an instance or a spec)."""
    return bool((_spec(x).get("channels") or {}).get("v2"))


def cfg(x) -> dict:
    c = _spec(x).get("channels") or {}
    return {key: c.get(key, v) for key, v in DEFAULTS.items()}


def active(k) -> bool:
    return "channels_v2" in k.w


def pull(k) -> bool:
    return active(k) and cfg(k)["delivery"] == "pull"


def _st(k) -> dict:
    return k.w["channels_v2"]


def _err(msg):
    from charter.actions import ActionError
    return ActionError(msg)


# ---------------------------------------------------------------------- institutions (through WP-D's charter/institutions.py)
# The read helpers of the unified institution store (get, kind_of, all_, status, members, is_member) work with
# institutions.unified on or off; membership is computed live through them. J0 counts as an institution where the world has it
# (jurisdictions off: the world's polity; on: unless the world starts in the state of nature).
def _iid_live(k, iid) -> bool:
    from charter import institutions as IN
    if iid == "J0" and "jur" not in k.w:
        return True
    return IN.get(k, iid) is not None and IN.status(k, iid) == "active"


def owner_kind(k, owner) -> str | None:
    """agent | jurisdiction | association | world | None (unknown, or no longer an active institution)."""
    from charter import institutions as IN
    if owner == WORLD:
        return "world"
    if not isinstance(owner, str):
        return None
    if owner in k.w["agents"]:
        return "agent"
    if not _iid_live(k, owner):
        return None
    return {"polity": "jurisdiction", "association": "association"}.get(IN.kind_of(k, owner))


def institutions(k) -> list:
    """Every active institution: polities (J0 when jurisdictions are off) and contract associations."""
    from charter import institutions as IN
    out = ["J0"] if "jur" not in k.w else []
    pol = [i for i in IN.all_(k) if IN.kind_of(k, i) == "polity" and _iid_live(k, i) and i not in out]
    ass = [i for i in IN.all_(k) if IN.kind_of(k, i) == "association" and _iid_live(k, i)]
    return out + pol + sorted(ass, key=lambda x: (len(x), x))


def is_member(k, iid, aid) -> bool:
    from charter import institutions as IN
    return IN.is_member(k, iid, aid)


def may_speak_for(k, aid, iid) -> bool:
    """`as` an institution: a holder of its speak office ("<iid>.speak", a right its code creates and grants)."""
    return owner_kind(k, iid) in ("jurisdiction", "association") and k.has(aid, f"{iid}.speak")


def name_of_owner(k, owner) -> str:
    from charter import institutions as IN
    rec = IN.get(k, owner)
    return f"{owner} ({rec.get('name')})" if rec is not None and rec.get("name") else str(owner)


# ---------------------------------------------------------------------- selectors
def check_selector(sel, path="selector"):
    """A selector, checked (raises ActionError). Lists and {"any": [...]} are unions."""
    if isinstance(sel, list):
        return [check_selector(x, path) for x in sel]
    if not isinstance(sel, dict) or not sel:
        raise _err(f"{path} must be an object such as {{\"all\": true}}, {{\"agents\": [\"Name\"]}}, {{\"members\": true}}, "
                   f"{{\"members\": \"<institution>\"}}, {{\"office\": \"<institution>.<right>\"}}, {{\"subscribers\": true}} or "
                   f"{{\"address\": true}}")
    out = {}
    for key, v in sel.items():
        if key not in SELECTORS:
            raise _err(f"{path}: unknown selector {key!r} (selectors: {', '.join(SELECTORS)})")
        if key == "agents":
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise _err(f"{path}: agents is a list of names")
            out[key] = sorted(set(v))
        elif key == "any":
            if not isinstance(v, list):
                raise _err(f"{path}: any is a list of selectors")
            out[key] = [check_selector(x, path) for x in v]
        elif key in ("office", "camp"):
            if not isinstance(v, str) or not v:
                raise _err(f"{path}: {key} names " + ("a right such as \"J1.speak\"" if key == "office" else "a camp"))
            out[key] = v
        elif key == "members":
            if v is not True and not isinstance(v, str):
                raise _err(f"{path}: members is true (this channel's members) or an institution's id")
            out[key] = v
        else:
            if v is not True:
                raise _err(f"{path}: {key} takes true")
            out[key] = True
    return out


def _present(k, aid, camp) -> bool:
    if k.has(aid, f"harvest:{camp}"):
        return True
    from charter.camptypes import framework as CT
    return CT.typed(k) and camp in CT.open_camps(k, aid)


def matches(k, ch, sel, aid, depth=0) -> bool:
    """Does the selector admit this agent now?"""
    if isinstance(sel, list):
        return any(matches(k, ch, x, aid, depth) for x in sel)
    if not isinstance(sel, dict):
        return False
    a = k.w["agents"].get(aid)
    if not a or a.get("departed") is not None:
        return False
    for key, v in sel.items():
        if key == "agents" and aid in v:
            return True
        if key == "members" and (aid in ch["members"] if v is True else is_member(k, v, aid)):
            return True
        if key == "office" and k.has(aid, v):
            return True
        if key == "subscribers" and aid in ch["subscribers"]:
            return True
        if key == "all" and a["cls"] != "observer":
            return True
        if key == "camp" and _present(k, aid, v):
            return True
        if key == "address" and knows(k, aid, ch, depth):
            return True
        if key == "any" and any(matches(k, ch, x, aid, depth) for x in v):
            return True
    return False


def _has(sel, key) -> bool:
    if isinstance(sel, list):
        return any(_has(x, key) for x in sel)
    if not isinstance(sel, dict):
        return False
    return key in sel or any(_has(x, key) for x in sel.get("any", []))


def describe(sel) -> str:
    if isinstance(sel, list):
        return " or ".join(describe(x) for x in sel)
    if not isinstance(sel, dict):
        return "nobody"
    parts = []
    for key, v in sel.items():
        parts.append({"agents": lambda: ", ".join(v) or "nobody", "members": lambda: "its members" if v is True else f"members of {v}",
                      "office": lambda: f"holders of {v}", "subscribers": lambda: "subscribers", "all": lambda: "everyone",
                      "camp": lambda: f"agents at {v}", "address": lambda: "anyone with the address",
                      "any": lambda: " or ".join(describe(x) for x in v)}[key]())
    return " or ".join(parts)


# ---------------------------------------------------------------------- reading and writing
def _seq(e) -> int:
    return int(str(e["id"])[1:])


def knows(k, aid, ch, depth=0) -> bool:
    """Does the agent know the channel's address? Listed channels are known to all; else whoever was told (a DM or post naming
    it), its owner, members and subscribers, and the readers of any channel where it was posted."""
    if ch["listed"] or ch.get("known_public") or aid == ch["owner"] or aid in ch["members"] or aid in ch["subscribers"]:
        return True
    if aid in ch["known"]:
        return True
    if depth > 3:
        return False
    for src in ch["known_via"]:
        s = k.w["channels"].get(src)
        if s is not None and src != ch["id"] and can_read(k, aid, s, depth=depth + 1):
            return True
    return False


def can_read(k, aid, ch, e=None, depth=0) -> bool:
    if aid == ch["owner"]:
        return True
    if not matches(k, ch, ch["readers"], aid, depth):
        return False
    if e is not None and ch["retention"] == "joined":
        since = ch["since"].get(aid)
        if since is not None and _seq(e) <= since:
            return False
    return True


def can_write(k, aid, ch, as_=None) -> bool:
    if aid == ch["owner"] or (as_ is not None and as_ == ch["owner"]):
        return True
    if as_ is not None and isinstance(ch["writers"], dict) and as_ in ch["writers"].get("agents", ()):
        return True
    return matches(k, ch, ch["writers"], aid)


def may_manage(k, aid, ch) -> bool:
    kind = owner_kind(k, ch["owner"])
    if kind == "agent":
        return aid == ch["owner"]
    if kind in ("jurisdiction", "association"):
        return may_speak_for(k, aid, ch["owner"])
    return False


def check_manage(k, aid, ch) -> None:
    if not may_manage(k, aid, ch):
        who = ch["owner"] if owner_kind(k, ch["owner"]) == "agent" else (
            "nobody (the world owns it)" if ch["owner"] == WORLD else f"holders of {ch['owner']}.speak")
        raise _err(f"only the channel's owner can change {ch['id']} ({who})")


def can_see(k, aid, ch, e) -> bool:
    """Kernel.can_see for an event in a v2 channel (vis "channel:<id>")."""
    return can_read(k, aid, ch, e)


def followed(k, aid, ch) -> bool:
    """Channels whose counts an agent sees (pull) and that its state lists: its own, those it is a member of or subscribes to,
    the squares it can read, and the inboxes it reads for an institution."""
    if aid == ch["owner"] or aid in ch["members"] or aid in ch["subscribers"]:
        return True
    if ch["owner"] == WORLD or (ch["inbox"] and owner_kind(k, ch["owner"]) in ("jurisdiction", "association")):
        return can_read(k, aid, ch)
    return False


# ---------------------------------------------------------------------- records
def _record(k, cid, owner, by=None, purpose="", readers=None, writers=None, listed=True, inbox=False, identity="named",
            retention="all", rate=None, members=()) -> dict:
    writers = writers if writers is not None else {"all": True}
    return {"v": 2, "id": cid, "owner": owner, "purpose": str(purpose)[:200], "readers": readers if readers is not None else {"all": True},
            "writers": writers, "listed": bool(listed), "inbox": bool(inbox), "identity": identity, "retention": retention,
            "rate": rate, "members": sorted(set(members)), "open": writers == {"all": True}, "subscribers": [], "since": {},
            "known": [], "known_via": [], "known_public": False, "created": k.r, "by": by}


def inbox_id(owner) -> str:
    return f"@{owner}"


def _inbox_record(k, owner) -> dict:
    if owner_kind(k, owner) == "agent":
        return _record(k, inbox_id(owner), owner, purpose=f"{owner}'s inbox", readers={"agents": [owner]}, writers={"all": True},
                       listed=True, inbox=True)
    return _record(k, inbox_id(owner), owner, purpose=f"{name_of_owner(k, owner)}'s inbox", readers={"members": owner},
                   writers={"all": True}, listed=True, inbox=True)


def _summary(ch) -> dict:
    return {x: ch[x] for x in ("id", "owner", "purpose", "readers", "writers", "listed", "inbox", "identity", "retention", "rate",
                               "members")}


def squares(k) -> list:
    return sorted(c for c, ch in k.w["channels"].items() if ch.get("v") == 2 and ch["owner"] == WORLD)


def _square_mode(k) -> str:
    return cfg(k)["square"]


def sync(k) -> None:
    """Every agent and institution has an inbox; the world has its square(s). New records log one monitor-only channel_seeded."""
    if not active(k):
        return
    chans = k.w["channels"]
    new = []
    if not _st(k)["seeded"]:
        _st(k)["seeded"] = True
        mode = _square_mode(k)
        rate = int(cfg(k)["square_rate"]) or None
        if mode == "one":
            chans[SQUARE] = _record(k, SQUARE, WORLD, purpose="the square: anyone may speak here", rate=rate)
            new.append(chans[SQUARE])
        elif mode == "per_camp":
            for c in sorted(k.w["camps"]):
                if k.w["camps"][c].get("secret"):
                    continue
                cid = f"{SQUARE}:{c}"
                chans[cid] = _record(k, cid, WORLD, purpose=f"the square at {c}: agents at the camp speak here",
                                     readers={"camp": c}, writers={"camp": c}, rate=rate)
                new.append(chans[cid])
    for owner in list(k.players()) + institutions(k):
        cid = inbox_id(owner)
        if cid not in chans:
            chans[cid] = _inbox_record(k, owner)
            new.append(chans[cid])
    if new:
        k.log("channel_seeded", None, {"channels": [_summary(c) for c in new]}, vis="monitor")


def inbox(k, owner) -> dict:
    """The owner's inbox record (made on demand: an institution founded this round)."""
    ch = k.w["channels"].get(inbox_id(owner))
    if ch is None:
        sync(k)
        ch = k.w["channels"].get(inbox_id(owner))
        if ch is None:
            raise _err(f"{owner} has no inbox")
    return ch


def install(k) -> None:
    """Kernel.__init__ (end): the store, the squares and every agent's and institution's inbox. Off: nothing."""
    if not on(k):
        return
    k.w["channels_v2"] = {"seq": 0, "seeded": False, "read": {}, "log": {}, "posted": {}}
    sync(k)


def round_start(k) -> None:
    """Kernel round start (reset_counters): rate counts reset; inboxes for newcomers and new institutions."""
    if not active(k):
        return
    _st(k)["posted"] = {}
    sync(k)


# ---------------------------------------------------------------------- the log index and addresses
def _index(k, cid, eid) -> None:
    if eid:
        _st(k)["log"].setdefault(cid, []).append(int(str(eid)[1:]))


def _mark_read(k, aid, cid, seq=None) -> None:
    log = _st(k)["log"].get(cid) or []
    upto = seq if seq is not None else (log[-1] if log else 0)
    _st(k)["read"].setdefault(aid, {})[cid] = max(upto, _st(k)["read"].get(aid, {}).get(cid, 0))


def learn(k, text, *, agents=(), channel=None, public=False) -> None:
    """An unlisted channel's address is learned by being told: whoever can see a message naming it now knows it."""
    if "~" not in str(text):
        return
    for cid, ch in k.w["channels"].items():
        if ch.get("v") != 2 or ch["listed"] or "~" not in cid or cid not in text:
            continue
        if public:
            ch["known_public"] = True
        for a in agents:
            if a in k.w["agents"] and a not in ch["known"]:
                ch["known"] = sorted(ch["known"] + [a])
        if channel and channel != cid and channel not in ch["known_via"]:
            ch["known_via"] = ch["known_via"] + [channel]


def _new_id(k, name, listed) -> str:
    name = str(name or "").strip()
    if not NAME.match(name):
        raise _err("a channel name is 1-40 letters, digits, _, - or . (starting with a letter or digit)")
    if listed:
        return name
    st = _st(k)
    st["seq"] += 1
    h = hashlib.sha1(f"{k.inst['seed']}|{k.r}|{st['seq']}|{name}".encode()).hexdigest()[:6]
    return f"{name}~{h}"


# ---------------------------------------------------------------------- templates (library entries; not verbs)
# Each is one open_channel with settings. "OWNER" stands for the channel's owner (an institution, for the chamber).
TEMPLATES = {
    "group": {"doc": "DM or group chat: the members write and read; unlisted (send to agents is the shortcut for two)",
              "readers": {"members": True}, "writers": {"members": True}, "listed": False},
    "square": {"doc": "a public square: everyone reads and writes, listed, rate-limited (the world's squares are kernel-made)",
               "readers": {"all": True}, "writers": {"all": True}, "listed": True, "rate": 2},
    "inbox": {"doc": "an inbox: anyone writes, only you read; listed (every agent and institution already has one, @<id>)",
              "readers": {"members": True}, "writers": {"all": True}, "listed": True},
    "newspaper": {"doc": "a newspaper, gazette or bulletin: the editors (members) write, subscribers read (join_channel), listed; "
                         "a fee is the owner's code (before_subscribe)",
                  "readers": {"subscribers": True}, "writers": {"members": True}, "listed": True},
    "chamber": {"doc": "a chamber: an institution's deliberation, its members write and read (opened as the institution)",
                "readers": {"members": "OWNER"}, "writers": {"members": "OWNER"}, "listed": False},
    "secret_cell": {"doc": "a secret cell: whoever knows the address may write, the members read; unlisted (the address is the key)",
                    "readers": {"members": True}, "writers": {"address": True}, "listed": False},
}

# Example owner laws (law.v2 code; the library's channel entries): moderation, an auto-reply, a relay.
LAW_EXAMPLES = {
    "Channel Moderation": '''
title = "Channel Moderation"
intent = "Posts in the channel CHANNEL that contain BANNED are refused (an owner's moderation: before_post refusing)."
CHANNEL = "guild"
BANNED = "traitor"

def before_post(p, chain):
    if p["outlet"] == CHANNEL and contains(lower(p["text"]), BANNED):
        refuse("moderated: posts naming " + BANNED + " are not allowed in " + CHANNEL)
''',
    "Inbox Auto-Reply": '''
title = "Inbox Auto-Reply"
intent = "Whoever writes to the inbox INBOX gets REPLY back from this institution (after_post sends it)."
INBOX = "@J1"
REPLY = "Received. The council reads its inbox at the end of each round."

def after_post(p, chain):
    if p["outlet"] == INBOX and p["agent"] is not None:
        send_message(p["agent"], REPLY)
''',
    "Channel Relay": '''
title = "Channel Relay"
intent = "Every post in SOURCE is relayed into TARGET in this institution's name."
SOURCE = "@J1"
TARGET = "J1-bulletin"

def after_post(p, chain):
    if p["outlet"] == SOURCE and p["agent"] is not None:
        send_message(TARGET, p["agent"] + " wrote: " + p["text"])
''',
}
LAW_EXAMPLES = {n: c.strip() + "\n" for n, c in LAW_EXAMPLES.items()}


def _fill(sel, owner):
    if isinstance(sel, list):
        return [_fill(x, owner) for x in sel]
    if isinstance(sel, dict):
        return {key: (owner if v == "OWNER" else _fill(v, owner) if isinstance(v, (list, dict)) else v) for key, v in sel.items()}
    return sel


# ---------------------------------------------------------------------- the gate (D-33 residual; the Press Act)
def found_right(k):
    """The right opening a channel needs: None (anyone: the residual) unless the Press Act (default code) or spec
    channels.found_right says otherwise."""
    from charter import code as DC
    return DC.rule(k, DC.ROOT, "Press Act", "right", cfg(k)["found_right"])


# ---------------------------------------------------------------------- actions
def _pop_as(kw):
    as_ = kw.pop("as", None)
    if as_ is None:
        as_ = kw.pop("as_", None)
    return None if as_ in (None, "") else str(as_)


def _speaker(k, aid, as_):
    """Check an `as`: an institution (its speak office) or an agent (an authorization to send for it). Returns the auth used."""
    if as_ is None:
        return None
    if as_ in k.w["agents"]:
        from charter import contracts as CT
        if "contracts" not in k.w:
            raise _err(f"you cannot speak as {as_}")
        for g in sorted(CT._auths(k).values(), key=lambda g: g["id"]):
            if (g["grantor"] == as_ and g["action"] == "send" and aid in CT._grantee_agents(k, g) and CT._auth_live(k, g)
                    and CT._auth_left(k, g) >= 1 - 1e-9):
                return g
        raise _err(f"you hold no authorization to send for {as_} (they authorize you: authorize {{\"agent\": \"{aid}\", "
                   f"\"action\": \"send\", \"qty\": 3}})")
    if not may_speak_for(k, aid, as_):
        raise _err(f"to speak as {as_} you need its speak office ({as_}.speak)")
    return None


def _use_auth(k, aid, g, to) -> None:
    if g is None:
        return
    if g["used"]["round"] != k.r:
        g["used"] = {"round": k.r, "qty": 0.0}
    g["used"]["qty"] = round(g["used"]["qty"] + 1, 6)
    g["total"] = round(g["total"] + 1, 6)
    k.log("agency_used", aid, {"auth": g["id"], "grantor": g["grantor"], "grantee": aid, "action": "send", "item": g["item"],
                               "qty": 1.0, "to": to, "done": True}, vis=[g["grantor"]] + ([aid] if aid != g["grantor"] else []))


def _dm_slot(k, aid) -> None:
    used, lim = k.w["dm_sent"].get(aid, 0), k.dm_limit(aid)
    if used >= lim:
        raise _err(f"you have sent your {lim} private messages for this round: 0 left (a message to an inbox counts too)")


def _rate(k, aid, ch) -> None:
    if ch.get("rate") is None:
        return
    key = f"{ch['id']}|{aid}"
    n = _st(k)["posted"].get(key, 0)
    if n >= int(ch["rate"]):
        raise _err(f"{ch['id']} allows {ch['rate']} post(s) per agent per round; you have used them")
    _st(k)["posted"][key] = n + 1


def post_to(k, aid, cid, text, as_=None, auth=None, to=None, law=None) -> str:
    """A post in a v2 channel (the post primitive, kind channel_post; the square of a one-square world: kind post, public). aid
    None: a law's (send_message); as_: the account it is sent in the name of."""
    ch = k.w["channels"].get(str(cid))
    if ch is None or ch.get("v") != 2:
        raise _err(f"no channel {cid}")
    cid = ch["id"]
    text = str(text)[:2000]
    if aid is not None:
        if not (knows(k, aid, ch) or can_write(k, aid, ch, as_)):
            raise _err(f"no channel {cid}")
        if not can_write(k, aid, ch, as_):
            raise _err(f"you cannot write in {cid} (writers: {describe(ch['writers'])})")
        _rate(k, aid, ch)
    data = {"channel": cid, "channel_id": cid, "text": text, "v2": True, **({"as": as_} if as_ else {}),
            **({"to": to} if to else {}), **({"law": law} if law else {}), **({"auth": auth["id"]} if auth else {})}
    anon = ch["identity"] == "anonymous" and aid is not None and not as_
    if cid == SQUARE and ch["owner"] == WORLD:                          # one square: the public board (type post, public)
        t = k.agent(aid)["title"] if aid else None
        data = {"text": text, "title": t, "channel_id": cid, **({"as": as_} if as_ else {})}
        if anon:
            with k.concealing(aid):
                eid = k.apply("post", agent=aid, kind="anon_post", text=text, actor=None, data={"text": text, "channel_id": cid}).result["event"]
        else:
            eid = k.apply("post", agent=aid, kind="post", text=text, actor=aid, data=data).result["event"]
        _index(k, cid, eid)
        learn(k, text, public=True)
        if aid:
            _mark_read(k, aid, cid)
        return eid
    if anon:
        with k.concealing(aid):
            eid = k.apply("post", agent=aid, kind="channel_post", text=text, outlet=cid, actor=None, data={**data, "anonymous": True},
                          vis=f"channel:{cid}").result["event"]
        k.log("anon_truth", aid, {"event": eid, "author": aid}, vis="monitor")
    else:
        eid = k.apply("post", agent=aid, kind="channel_post", text=text, outlet=cid, actor=aid, data=data,
                      vis=f"channel:{cid}").result["event"]
    _index(k, cid, eid)
    learn(k, text, channel=cid)
    if aid:
        _mark_read(k, aid, cid)
    return eid


def act_post(k, aid, text, channel=None, **kw):
    """post under channels.v2: the square (no channel), or any channel you may write in ("channel"), optionally "as" an
    institution whose speak office you hold."""
    as_ = _pop_as(kw)
    if kw:
        raise TypeError(f"act_post() got unexpected arguments: {sorted(kw)}")
    if channel in (None, "", SQUARE):
        sq = squares(k)
        if channel in (None, "") and len(sq) != 1:
            mine = [c for c in sq if can_write(k, aid, k.w["channels"][c])]
            if len(mine) != 1:
                raise _err("name the square to post in (\"channel\"): " + (", ".join(mine) or "you are at no camp's square"))
            channel = mine[0]
        elif channel in (None, ""):
            channel = sq[0]
        if channel == SQUARE and SQUARE in k.w["channels"] and as_ is None:
            from charter import media as MD
            if MD.submissions_on(k) and not MD.in_stream(k, aid):         # media2 untouched: its submissions and licences
                return MD.submit(k, aid, text)
            MD.check_post(k, aid)
    auth = _speaker(k, aid, as_)
    eid = post_to(k, aid, channel, text, as_=as_, auth=auth)
    _use_auth(k, aid, auth, channel)
    return f"Posted in {channel} ({eid})."


def act_send(k, aid, to, text, encrypted=False, **kw):
    """send: to an agent (a private message, into its inbox), to an institution (its inbox) or to a channel. "as": an institution
    (its speak office) or an agent who authorized you to send for it. A message to an agent or an inbox counts against your
    private-message limit."""
    from charter import actions as A
    as_ = _pop_as(kw)
    if kw:
        raise TypeError(f"act_send() got unexpected arguments: {sorted(kw)}")
    target = str(to).strip()
    if target.startswith("@") and target[1:] in k.w["agents"]:
        target = target[1:]
    if target in k.w["agents"] and as_ is None:
        return A._dm(k, aid, target, text, encrypted)
    if encrypted:
        raise _err("only a private message to an agent can be encrypted")
    auth = _speaker(k, aid, as_)
    if target in k.w["agents"] or (target.startswith("@") and target[1:] in k.w["agents"]):
        target = target.lstrip("@")
        if k.w["agents"][target].get("departed") is not None or target == aid:
            raise _err(f"unknown recipient {target}")
        ch = inbox(k, target)
        _dm_slot(k, aid)
        eid = post_to(k, aid, ch["id"], text, as_=as_, auth=auth, to=target)
        k.w["dm_sent"][aid] = k.w["dm_sent"].get(aid, 0) + 1
        _use_auth(k, aid, auth, target)
        return f"Message sent to {target} as {as_} ({eid})." + A._dm_left_note(k, aid)
    kind = owner_kind(k, target)
    if kind in ("jurisdiction", "association"):
        ch = inbox(k, target)
        _dm_slot(k, aid)
        eid = post_to(k, aid, ch["id"], text, as_=as_, auth=auth, to=target)
        k.w["dm_sent"][aid] = k.w["dm_sent"].get(aid, 0) + 1
        _use_auth(k, aid, auth, target)
        return f"Message sent to {target}'s inbox {ch['id']}" + (f" as {as_}" if as_ else "") + f" ({eid})." + A._dm_left_note(k, aid)
    ch = k.w["channels"].get(target)
    if ch is not None and ch.get("v") == 2:
        if ch["inbox"]:
            _dm_slot(k, aid)
        eid = post_to(k, aid, target, text, as_=as_, auth=auth)
        if ch["inbox"]:
            k.w["dm_sent"][aid] = k.w["dm_sent"].get(aid, 0) + 1
        _use_auth(k, aid, auth, target)
        return f"Posted in {target}" + (f" as {as_}" if as_ else "") + f" ({eid})."
    raise _err(f"unknown recipient {target}: an agent, an institution or a channel (read {{}} lists the directory)")


def act_open_channel(k, aid, name, purpose="", readers=None, writers=None, listed=None, identity="named", retention="all",
                     members=None, template=None, rate=None, **kw):
    """open_channel: a new channel you own (or an institution owns: "as"). Anyone may (unless the world's Press Act gates it)."""
    as_ = _pop_as(kw)
    if kw:
        raise TypeError(f"act_open_channel() got unexpected arguments: {sorted(kw)}")
    right = found_right(k)
    if right and not k.has(aid, right):
        raise _err(f"opening a channel needs the {right!r} right in this world (the Press Act)")
    owner = aid
    if as_ is not None:
        if as_ in k.w["agents"] or not may_speak_for(k, aid, as_):
            raise _err(f"to open a channel as {as_} you need its speak office ({as_}.speak)")
        owner = as_
    t = {}
    if template is not None:
        t = TEMPLATES.get(str(template).lower().replace(" ", "_"))
        if t is None:
            raise _err(f"no channel template {template!r} (templates: {', '.join(TEMPLATES)})")
        t = _fill(t, owner)
    readers = check_selector(readers if readers is not None else t.get("readers", {"all": True}), "readers")
    writers = check_selector(writers if writers is not None else t.get("writers", {"all": True}), "writers")
    listed = t.get("listed", True) if listed is None else bool(listed)
    rate = t.get("rate") if rate is None else rate
    if identity not in IDENTITIES or retention not in RETENTIONS:
        raise _err(f"identity is {' or '.join(IDENTITIES)}; retention is {' or '.join(RETENTIONS)}")
    if rate is not None and (isinstance(rate, bool) or not isinstance(rate, int) or rate < 1):
        raise _err("rate is a whole number of posts per agent per round (at least 1), or null")
    mem = members if isinstance(members, list) else ([] if members is None else [members])
    bad = [m for m in mem if m not in k.w["agents"]]
    if bad:
        raise _err(f"no agent {bad[0]}")
    mem = sorted(set(mem) | ({aid} if owner == aid or _has(readers, "members") else set()))
    cid = _new_id(k, name, listed)
    if cid in k.w["channels"] or cid.startswith(("@", SQUARE)):
        raise _err(f"channel {cid} exists")
    settings = {"purpose": str(purpose or t.get("doc", ""))[:200], "readers": readers, "writers": writers, "listed": listed,
                "identity": identity, "retention": retention, "rate": rate, "owner": owner}
    k.apply("found", agent=aid, polity=cid, kind="channel", members=mem, open=writers == {"all": True}, settings=settings)
    return (f"Channel {cid} opened (owner {owner}; readers: {describe(readers)}; writers: {describe(writers)}; "
            + ("listed in the directory" if listed else f"unlisted: its address {cid} is known only to those you tell") + ").")


def change_found(k, agent, polity, members, open, settings) -> dict:
    """found(kind="channel") under channels.v2 (dispatch.changes.membership.do_found)."""
    s = dict(settings)
    owner = s.pop("owner", agent)
    ch = k.w["channels"][polity] = _record(k, polity, owner, by=agent, members=members, **s)
    for m in ch["members"]:
        ch["since"][m] = len(k.events)
    vis = "public" if ch["listed"] else sorted({m for m in [agent, *ch["members"]] if m in k.w["agents"]})
    k.log("channel_opened", agent, {"channel": polity, "open": ch["open"], **_summary(ch)}, vis=vis)
    return {"channel": polity}


def act_set_channel(k, aid, channel, field, value=None):
    """set_channel: change one setting of a channel you may manage (purpose, readers, writers, listed, identity, retention, rate,
    inbox)."""
    ch = k.w["channels"].get(str(channel))
    if ch is None or ch.get("v") != 2 or not knows(k, aid, ch):
        raise _err(f"no channel {channel}")
    check_manage(k, aid, ch)
    key = str(field)
    if key not in FIELDS:
        raise _err(f"field is one of {', '.join(FIELDS)}")
    if key in ("readers", "writers"):
        value = check_selector(value, key)
    elif key in ("listed", "inbox"):
        if not isinstance(value, bool):
            raise _err(f"{key} is true or false")
        if key == "listed" and value != ch["listed"] and "~" in ch["id"] and value:
            pass                                                        # an unlisted address may be listed later: it keeps its id
    elif key == "identity" and value not in IDENTITIES:
        raise _err(f"identity is {' or '.join(IDENTITIES)}")
    elif key == "retention" and value not in RETENTIONS:
        raise _err(f"retention is {' or '.join(RETENTIONS)}")
    elif key == "rate" and value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
        raise _err("rate is a whole number (at least 1) or null")
    elif key == "purpose":
        value = str(value or "")[:200]
    k.apply("set_channel", agent=aid, channel=ch["id"], key=key, value=value)
    return f"{ch['id']}: {key} set to {json.dumps(value)}."


def change_set_channel(k, agent, channel, key, value) -> dict:
    ch = k.w["channels"][channel]
    ch[key] = value
    if key == "writers":
        ch["open"] = value == {"all": True}
    k.log("channel_set", agent, {"channel": channel, "key": key, "value": value}, vis=f"channel:{channel}")
    return {"channel": channel, "key": key}


def act_join_channel(k, aid, channel):
    """join_channel: subscribe to a channel (follow it; readers that admit subscribers then include you)."""
    ch = k.w["channels"].get(str(channel))
    if ch is None or ch.get("v") != 2 or not knows(k, aid, ch):
        raise _err(f"no channel {channel}")
    if aid in ch["subscribers"]:
        return f"You already follow {ch['id']}."
    if not (_has(ch["readers"], "subscribers") or can_read(k, aid, ch)):
        raise _err(f"{ch['id']}'s readers are {describe(ch['readers'])}: joining would not let you read it (ask its owner)")
    k.apply("subscribe", agent=aid, outlet=ch["id"], on=True, via="channel")
    return f"You follow {ch['id']} now" + (" (you see its posts from now on)" if ch["retention"] == "joined" else "") + "."


def act_leave_channel(k, aid, channel):
    ch = k.w["channels"].get(str(channel))
    if ch is None or ch.get("v") != 2 or aid not in ch["subscribers"]:
        raise _err(f"you do not follow {channel}")
    k.apply("subscribe", agent=aid, outlet=ch["id"], on=False, via="channel")
    return f"You no longer follow {ch['id']}."


def change_subscribe(k, agent, channel, on) -> dict:
    """subscribe (via "channel"; dispatch.changes.press.do_subscribe)."""
    ch = k.w["channels"][channel]
    if on and agent not in ch["subscribers"]:
        ch["subscribers"] = sorted(ch["subscribers"] + [agent])
        ch["since"][agent] = len(k.events)
    elif not on:
        ch["subscribers"] = [a for a in ch["subscribers"] if a != agent]
    vis = sorted({a for a in (agent, ch["owner"]) if a in k.w["agents"]})
    k.log("channel_subscribed", agent, {"channel": channel, "agent": agent, "on": bool(on)}, vis=vis)
    return {"on": bool(on)}


def register_vis(k, ch, extra=()):
    """Who learns of a v2 channel's membership changes and closing: everyone for a listed channel; for an unlisted one, its owner,
    members and the agents concerned (its existence is secret)."""
    if ch["listed"]:
        return "public"
    return sorted({a for a in [ch["owner"], *ch["members"], *extra] if a in k.w["agents"]}) or "monitor"


def on_member(k, ch, agent, change) -> None:
    """actions.change_channel_member for a v2 record: when the member joined (retention)."""
    if change == "add":
        ch["since"][agent] = len(k.events)


# ---------------------------------------------------------------------- read: the directory and a channel (a look-up)
def directory(k, aid) -> str:
    lines = ["Directory (listed channels and inboxes; unlisted channels are known only by their address):"]
    for cid, ch in sorted(k.w["channels"].items()):
        if ch.get("v") != 2 or not knows(k, aid, ch) or (ch["inbox"] and owner_kind(k, ch["owner"]) == "agent"):
            continue
        n = len(_st(k)["log"].get(cid) or [])
        lines.append(f"- {cid}: {ch['purpose'] or '(no purpose given)'}; owner {ch['owner']}; readers {describe(ch['readers'])}; "
                     f"writers {describe(ch['writers'])}; {n} post(s)" + ("" if ch["listed"] else "; unlisted"))
    lines.append("Every agent's inbox is @<name>: send {\"to\": \"<name>\", \"text\"} reaches it as a private message.")
    return "\n".join(lines)


def read(k, aid, channel=None, n=10) -> str:
    """The read look-up: the directory (no channel), or a channel's latest n posts you may read (marked read)."""
    from charter import agents as AG
    if channel in (None, "", "directory"):
        return directory(k, aid)
    ch = k.w["channels"].get(str(channel))
    if ch is None and str(channel) in k.w["agents"]:
        ch = k.w["channels"].get(inbox_id(channel))
    if ch is None or ch.get("v") != 2 or not knows(k, aid, ch):
        raise _err(f"no channel {channel} (read {{}} lists the directory)")
    if not can_read(k, aid, ch):
        raise _err(f"you cannot read {ch['id']} (readers: {describe(ch['readers'])})")
    try:
        n = max(1, min(30, int(n)))
    except (TypeError, ValueError):
        n = 10
    cid = ch["id"]
    seqs = _st(k)["log"].get(cid) or []
    shown = []
    for s in reversed(seqs):
        e = k.events[s - 1] if s - 1 < len(k.events) else None
        if e is None or not k.can_see(aid, e):
            continue
        txt = AG.render_event(k, e, aid)
        if txt:
            shown.append(txt)
        if len(shown) >= n:
            break
    if seqs:
        _mark_read(k, aid, cid, seqs[-1])
    head = (f"Channel {cid} ({ch['purpose'] or 'no purpose given'}; owner {ch['owner']}; readers {describe(ch['readers'])}; "
            f"writers {describe(ch['writers'])}; {len(seqs)} post(s)):")
    return head + "\n" + ("\n".join(reversed(shown)) or "(no posts you can read)")


def act_read(k, aid, channel=None, n=10):
    return read(k, aid, channel, n)


# ---------------------------------------------------------------------- the feed and the state
def pulled(k, aid, e) -> bool:
    """Pull delivery: a channel post that stays out of the feed (counted in the state instead). DMs and the agent's own inbox are
    pushed."""
    d = e.get("data")
    if not isinstance(d, dict) or e["type"] == "dm":
        return False
    cid = d.get("channel_id")
    return bool(cid) and cid != inbox_id(aid)


def unread(k, aid, cid) -> tuple:
    """(unread count, latest event) of a channel for this agent."""
    seqs = _st(k)["log"].get(cid) or []
    mark = _st(k)["read"].get(aid, {}).get(cid, 0)
    n, latest = 0, None
    for s in seqs[bisect.bisect_right(seqs, mark):]:
        e = k.events[s - 1] if s - 1 < len(k.events) else None
        if e is None or e.get("agent") == aid or not k.can_see(aid, e):
            continue
        n += 1
        latest = e
    return n, latest


def _headline(e) -> str:
    d = e["data"]
    who = d.get("as") or e.get("agent") or "Anonymous"
    t = " ".join(str(d.get("text", "")).split())
    return f"{who}: \"{t[:80]}{'...' if len(t) > 80 else ''}\""


def state_lines(k, aid) -> list:
    """The channel lines of an agent's state (agents.state_view under channels.v2)."""
    chans = [ch for ch in k.w["channels"].values() if ch.get("v") == 2 and ch["id"] != inbox_id(aid) and followed(k, aid, ch)]
    own = f"Your inbox: {inbox_id(aid)} (messages to you arrive in your feed)."
    if not pull(k):
        names = ", ".join(sorted(c["id"] for c in chans))
        return [own, "Channels you follow: " + (names or "none") + " (read {} lists the directory)."]
    rows = []
    for ch in chans:
        n, latest = unread(k, aid, ch["id"])
        rows.append((n, ch["id"], latest))
    rows.sort(key=lambda x: (-x[0], x[1]))
    cap = int(cfg(k)["headlines"])
    parts = [f"{cid} {n} unread" + (f", latest {_headline(e)}" if e is not None else "") for n, cid, e in rows[:cap]]
    more = len(rows) - cap
    line = ("Channels (their posts are not in your feed: read {\"channel\": \"<id>\"} opens one; read {} lists the directory): "
            + ("; ".join(parts) or "none") + (f"; and {more} more" if more > 0 else "") + ".")
    return [own, line]


def render(k, e, tag, viewer=None) -> str:
    d = e["data"]
    who = e.get("agent")
    if d.get("as"):
        who = f"{d['as']} (sent by {who})" if who else d["as"]
    elif d.get("anonymous") or who is None:
        who = "Anonymous"
    to = f" to {d['to']}" if d.get("to") and d.get("channel") != inbox_id(viewer) else ""
    return f"{tag} #{d['channel']} {who}{to}: {d['text']}"


EVENT_TYPES = ("channel_opened", "channel_set", "channel_subscribed")


def render_event(k, e, tag) -> str:
    d, t, who = e["data"], e["type"], e.get("agent")
    if t == "channel_opened":
        return (f"{tag} {who} opened channel {d['channel']} (owner {d['owner']}; {d.get('purpose') or 'no purpose given'}; readers "
                f"{describe(d['readers'])}; writers {describe(d['writers'])}" + ("" if d.get("listed") else "; unlisted") + ")")
    if t == "channel_set":
        return f"{tag} {who} set {d['channel']}'s {d['key']} to {json.dumps(d['value'])}"
    return f"{tag} {who} {'joined' if d.get('on') else 'left'} channel {d['channel']}"


def dm_extra(k, aid, to, extra) -> dict:
    """actions._deliver under channels.v2: a DM lands in the recipient's inbox (its channel_id)."""
    return {**(extra or {}), "channel_id": inbox_id(to)}


def check_dm(k, aid, to) -> None:
    """actions._dm_check under channels.v2: the recipient's inbox writers decide who may message it."""
    ch = k.w["channels"].get(inbox_id(to))
    if ch is not None and not can_write(k, aid, ch):
        raise _err(f"{to} accepts messages only from {describe(ch['writers'])}")


def after_dm(k, aid, to, text, eid) -> None:
    if eid:
        _index(k, inbox_id(to), eid)
    learn(k, text, agents=[to])


# ---------------------------------------------------------------------- law: owners' laws, the law API, the register
def _channel_of(P, payload):
    if P.name in ("post", "subscribe"):
        return payload.get("outlet")
    if P.name == "set_channel":
        return payload.get("channel")
    if P.name in ("admit", "expel", "dissolve", "found") and payload.get("kind") == "channel":
        return payload.get("polity")
    return None


def owner_laws(k, P, payload, laws) -> list:
    """dispatch.hooks.bound_laws: the laws of the institution owning the channel a change is about (its own code decides who
    posts, joins or changes its channels, whoever acts)."""
    cid = _channel_of(P, payload)
    ch = k.w["channels"].get(cid) if isinstance(cid, str) else None
    if ch is None or ch.get("v") != 2 or owner_kind(k, ch["owner"]) not in ("jurisdiction", "association"):
        return []
    from charter import jurisdictions as J
    return [l for l in laws if J.law_jur(k, l["id"]) == ch["owner"]]


def law_reads(k, lid, cid) -> bool:
    """dispatch.hooks.hook_payload: may this law read a post's text in this channel? Its own institution's channel, or one every
    agent reads (public speech). Closed channels stay closed to other laws (V18; surveillance is a world dial, not a law's)."""
    from charter import jurisdictions as J
    ch = k.w["channels"].get(cid) if isinstance(cid, str) else None
    if ch is None or ch.get("v") != 2 or lid is None:
        return False
    return ch["owner"] == J.law_jur(k, lid) or ch["readers"] == {"all": True}


def law_visible(k, lid, cid) -> bool:
    """The law API's channels(): listed channels, and the unlisted ones its own institution owns."""
    from charter import jurisdictions as J
    ch = k.w["channels"].get(cid)
    return ch is None or ch.get("v") != 2 or ch["listed"] or ch["owner"] == J.law_jur(k, lid)


def send_as(k, iid, to, text, lid=None) -> bool:
    """A message in an institution's name (the law API's send_message): to an agent's or institution's inbox, or a channel the
    institution may write in. False (logged for the monitor) when it cannot be delivered."""
    from charter import actions as A
    from charter import dispatch as D
    target = str(to)
    try:
        if target in k.w["agents"] or owner_kind(k, target) in ("jurisdiction", "association"):
            ch = inbox(k, target)
            eid = post_to(k, None, ch["id"], text, as_=iid, to=target, law=lid)
        else:
            ch = k.w["channels"].get(target)
            if ch is None or ch.get("v") != 2 or not (ch["owner"] == iid or ch["writers"] == {"all": True}
                                                       or iid in (ch["writers"] or {}).get("agents", ())):
                raise _err(f"{iid} cannot write in {target}")
            eid = post_to(k, None, target, text, as_=iid, law=lid)
        return bool(eid)
    except (A.ActionError, D.PhysicsError, D.Blocked) as e:            # a law's call fails quietly (the monitor sees why)
        k.log("message_refused", None, {"law": lid, "as": iid, "to": target, "why": str(e)[:300]}, vis="monitor")
        return False


def law_api(k, lid) -> dict:
    """channels.v2: send_message(to, text), a message in the name of the law's own institution (Kernel.api_for)."""
    from charter import jurisdictions as J

    def send_message(to, text):
        return send_as(k, J.law_jur(k, lid), to, text, lid)
    return {"send_message": send_message}


# ---------------------------------------------------------------------- standing orders that send
STANDING_MESSAGE = '''
title = "Standing message"
intent = "The founder's standing message: at the end of every EVERY-th round TEXT is sent to TO (an agent, an institution or a channel) in this contract's name. After TIMES messages (0: no limit) the order ends. The founder cancels it by leaving (leave_contract)."
TO = ""
TEXT = ""
EVERY = 1
TIMES = 0

def on_round_end(r):
    me = contract_state(jurisdiction())["founder"]
    if state.get("done") or me not in members() or TO == "":
        return
    start = state.setdefault("start", r)
    if (r - start) % EVERY != 0:
        return
    if send_message(TO, TEXT):
        state["sent"] = state.get("sent", 0) + 1
        if TIMES > 0 and state["sent"] >= TIMES:
            state["done"] = True
            expel(me)
'''.strip() + "\n"


def act_standing_order(k, aid, to=None, item=None, qty=None, every=1, keep=0, times=0, name=None, act=None, text=None):
    """standing_order under channels.v2: as before (a payment), or act "send": a timed or recurring message (a one-member contract
    whose code sends TEXT to TO every EVERY rounds, TIMES times)."""
    from charter import contracts as CT
    from charter import lawlang as L
    if act in (None, "", "transfer", "pay"):
        return CT.act_standing_order(k, aid, to, item, qty, every, keep, times, name)
    if act != "send":
        raise L.LawError("act is transfer (a payment, the default) or send (a message)")
    CT._need_on(k)
    if not text or to in (None, ""):
        raise L.LawError("a standing message needs to and text")
    if int(every) < 1 or int(times) < 0:
        raise L.LawError("every is 1 or more; times is 0 or more")
    target = str(to)
    if not (target in k.w["agents"] or owner_kind(k, target) or target in k.w["channels"]):
        raise L.LawError(f"unknown recipient {target} (an agent, an institution or a channel)")
    params = {"TO": target, "TEXT": str(text)[:500], "EVERY": int(every), "TIMES": int(times)}
    out = CT.act_create_contract(k, aid, name=name or f"standing message to {target}",
                                 code=CT.instantiate(STANDING_MESSAGE, params), admission="closed")
    cid = f"A{k.w['contracts']['seq']}"
    return (f"Standing message {cid}: to {target} every {int(every)} round(s)" + (f", {int(times)} times" if int(times) else "")
            + f", sent in {cid}'s name (cancel with leave_contract {{\"contract\": \"{cid}\"}}). " + out.split(":", 1)[0] + ".")


# ---------------------------------------------------------------------- the manual (agent-facing text)
def manual_text(k=None) -> str:
    return (
        "A channel is a named, owned stream with access rules: who writes, who reads, whether it is listed in the directory, whether "
        "authors are named, and whether newcomers see its history. Every agent and every institution has an inbox (@<name>); the "
        "world has a square. Verbs:\n"
        "- send {\"to\": \"<agent, institution or channel>\", \"text\": \"...\", \"as\": \"<institution>\"}: to an agent it is a "
        "private message; to an institution it lands in its inbox; to a channel it is a post. \"as\" speaks for an institution "
        "whose speak office (<id>.speak) you hold, or for an agent who authorized you (authorize with action send). Messages to "
        "an agent or an inbox count against your private-message limit.\n"
        "- post {\"text\": \"...\", \"channel\": \"<id>\", \"as\": \"<institution>\"}: without a channel, the square.\n"
        "- read {\"channel\": \"<id>\", \"n\": 10} (a look-up): the latest posts of a channel you may read; read {} lists the "
        "directory. Channel posts do not come to your feed: your state shows each channel you follow with its unread count and "
        "latest headline. Private messages and your own inbox always reach your feed.\n"
        "- open_channel {\"name\": \"...\", \"purpose\": \"...\", \"readers\": <selector>, \"writers\": <selector>, \"listed\": true, "
        "\"identity\": \"named\"|\"anonymous\", \"retention\": \"all\"|\"joined\", \"members\": [\"Name\"], \"rate\": null, "
        "\"template\": \"<name>\", \"as\": \"<institution>\"}: you (or the institution) own it. An unlisted channel's id gets a "
        "random suffix: its address is a key, learned only by being told (a message that names it).\n"
        "- set_channel {\"channel\": \"<id>\", \"field\": \"readers\", \"value\": <selector>}: fields purpose, readers, writers, "
        "listed, identity, retention, rate, inbox (owner only; an institution's channels: its speak office).\n"
        "- join_channel / leave_channel {\"channel\": \"<id>\"}: follow a channel (subscribe); add_member, remove_member and "
        "close_channel manage a channel's members.\n"
        "Selectors: {\"all\": true}, {\"agents\": [\"Name\"]}, {\"members\": true} (the channel's members), {\"members\": "
        "\"<institution>\"}, {\"office\": \"<institution>.<right>\"}, {\"subscribers\": true}, {\"address\": true} (anyone who "
        "knows the address), {\"camp\": \"<camp>\"}, {\"any\": [...]} (any of them).\n"
        "Templates (open_channel {\"template\": ...}; examples, not rules): "
        + "; ".join(f"{n}: {t['doc']}" for n, t in TEMPLATES.items()) + ".\n"
        "An institution's code governs its channels: its laws see posts, joins and changes in them (before_post, before_subscribe, "
        "before_set_channel, after_post) and can refuse them (moderation), charge, relay or answer them (send_message(to, text) "
        "sends in the institution's name). A standing order can send: standing_order {\"act\": \"send\", \"to\", \"text\", "
        "\"every\", \"times\"}.")


from charter import sections as _SC                                    # noqa: E402  (registered after the module is defined)


@_SC.section("Channels", after="World rules", order=5, needs=("flag:channels.v2",))
def _manual_section(v):
    return manual_text(v.k)
