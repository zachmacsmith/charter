"""The publication layer (review 12 WP2, §4; ARCHITECTURE D-30): who is told of an event is law, not the call site's literal.

Behind spec `law.publication` (default false). Off, nothing here runs: Kernel.log keeps every call site's `vis=` exactly as before.

On, every event still gets its one monitor record (Kernel.log appends it whatever happens here). Who else sees it is decided in two
layers by `publish`, called once from Kernel.log:
  1. The natural audience (E, the floor): who perceives the event by nature. An event its call site logs with a restricted
     audience (a list of agents, "channel:<id>", "monitor") keeps it: that audience is natural (the parties of a transfer or a DM,
     a channel's readers, nobody). An event its call site logs "public" gets the natural audience its event type declares
     (eventtypes.EventType.natural): "public" (posts, a gazette, world events anyone observes), "parties" (the event's agent and the
     agents its data names, `parties`) or "channel" (the channel's members, plus the parties). No one -> "monitor".
  2. Publication (L, the widening): the publication table of the event's polity maps the event's key to an audience, and the result
     is the natural audience widened by it. Publication can only widen.

Publication keys: the event type, except for the types some call sites log public and others not (MIXED: veto votes under secret
board votes, private bequests, covert deaths, members-only gazettes, ...): there the instances today's code logs public have the key
"<type>.open" and the rest "<type>". review 12 §4.3's sub-keys; the condition is the call site's own (a spec dial, a data flag).

Audiences (a table's values, AUDIENCES):
  natural            no widening (the residual: an event no rule names is natural)
  parties            the event's agent and the agents its data names
  members            the members of the event's polity (an association's members; a jurisdiction's members; with jurisdictions
                     off, every agent on the roster)
  officials:<right>  the polity's members who hold <right> when the event is logged
  public             everyone
An event widened to parties, members or officials records {"pub": {"polity", "audience"}} (never under the today table, so today's
events are byte-identical): the polity's own laws may read it (evidence.law_can_see), as its register.

Ceilings (E: technology and secrecy, review 12 §4.2 item 3; D-30): an encrypted DM is never widened, an unencrypted one only where
the world lets laws read DMs (conditions.law_reads_dms); a channel post never leaves its channel; truth and record events
(kind truth/record: the monitor's ground truth, goals, roles) cannot be published at all; an event about a hidden jurisdiction
published "public" reaches its members only (jurisdictions.vis, as today).

The event's polity (`polity`): the account its data is about (evidence.about: a jurisdiction, a contract, a law's or a ballot's
polity), else the polity its agent belongs to (jurisdictions on), else "J0".

The store, k.w["publication"] (only with the flag on; checkpointed with the world):
  {"base": "today" | "none", "rules": {polity: {key: {"audience": a, "law": lid or None}}}}
`base` is the table every polity starts from: "today" (TODAY, generated from the event registry, reproduces every call site's
literal: spec law.publication_seed, the default) or "none" (natural perception only: a state of nature). `rules` are a polity's
own rows over it (the Publication Act's store, review 12 §3; the Act itself is WP4's). `table(k, polity)` is the merged table.

Interface for the default code (W8d / WP4):
  table(k, polity) -> {key: audience}        the polity's table in force (base plus its own rows)
  audience(k, event) -> vis                  who was told of a logged event ("public", a list of agent ids, "channel:<id>",
                                             "monitor"): the one source for "who may know" (evidence.law_can_see reads it)
  published_to(k, event) -> (polity, aud)    the polity register an event was widened to, or None
  set_rule(k, polity, key, audience, lid)    write a row (the change of the set_publication primitive); "natural" clears the
                                             widening; reset_rule(...) drops the row (the base's row applies again)
  set_base(k, name)                          "today" | "none"
  law API (law.v2 and law.publication): publish(event_type, audience), unpublish(event_type), publication(event_type=None),
  routed as the primitive set_publication (hookable: before_set_publication / after_set_publication).

The today table (TODAY): one row "<key>": "public" for every event type some call site logs public (registry vis contains "public",
checked statically and in scripted runs by tests/test_charter_eventtypes.py), keyed "<type>.open" for MIXED types. Nothing else:
every other event is natural, which is its call site's literal. So with the today base, publish() returns every call site's literal
(tests/test_charter_publication.py: statically over every k.log site, and dynamically over the golden runs).
"""
from __future__ import annotations

from charter import eventtypes as ET
from charter import lawlang as L

AUDIENCES = ("natural", "parties", "members", "public")          # plus "officials:<right>"
BASES = ("today", "none")
OPEN = ".open"                                                    # the sub-key suffix of a MIXED type's public instances
SEALED_KINDS = ("truth", "record")                                # never publishable (X: the monitor's own record)
# the data keys whose values name an event's parties (top level; lists read whole); evidence.DATA_AGENT_KEYS plus a few
DATA_AGENT_KEYS = ("to", "from", "src", "dst", "member", "members", "accused", "accuser", "agent", "target", "victim", "parties",
                   "borrower", "lender", "a", "b", "by", "who", "guard", "attacker", "heir", "heirs", "electorate", "author",
                   "owner", "tenant", "holder", "successor", "grantor", "grantee", "voter", "appellant")


# ---------------------------------------------------------------------- the spec
def enabled_spec(spec: dict) -> bool:
    return bool(((spec or {}).get("law") or {}).get("publication"))


def enabled(k) -> bool:
    return bool(getattr(k, "_publication", False))


def seed_of(spec: dict) -> str:
    s = ((spec or {}).get("law") or {}).get("publication_seed") or "today"
    if s not in BASES:
        raise ValueError(f"law.publication_seed must be one of {', '.join(BASES)}, not {s!r}")
    return s


def install(k) -> None:
    """Kernel.__init__: with the flag on, the store (base from law.publication_seed, no rows). Off: nothing."""
    k._publication = enabled_spec(k.spec)
    if k._publication:
        k.w["publication"] = {"base": seed_of(k.spec), "rules": {}}


# ---------------------------------------------------------------------- keys and the today table
MIXED = frozenset(n for n, t in ET.REG.items() if "public" in t.vis and len(t.vis) > 1)


def key(kind: str, vis="public") -> str:
    """The publication key of an event of type `kind` its call site logs with `vis`."""
    kind = ET.canonical(kind)
    return kind + OPEN if kind in MIXED and vis == "public" else kind


def generate_today() -> dict:
    """The today table, from the event registry: every type a call site logs public -> "public" (MIXED: its .open key)."""
    return {key(n, "public"): "public" for n, t in ET.REG.items() if "public" in t.vis}


TODAY = generate_today()
BASE_TABLES = {"today": TODAY, "none": {}}


def keys() -> list:
    """Every valid publication key: each publishable type, and the .open key of each MIXED type."""
    out = []
    for n, t in ET.REG.items():
        if t.kind in SEALED_KINDS:
            continue
        out.append(n)
        if n in MIXED:
            out.append(n + OPEN)
    return out


# ---------------------------------------------------------------------- the store
def _store(k) -> dict:
    st = k.w.get("publication")
    if st is None:                                                 # flag on, before install ran (or an old checkpoint)
        st = k.w["publication"] = {"base": seed_of(k.spec), "rules": {}}
    return st


def table(k, polity) -> dict:
    """The publication table in force for `polity`: its base (today or none) overlaid with the polity's own rows."""
    st = _store(k)
    t = dict(BASE_TABLES[st["base"]])
    for kk, row in (st["rules"].get(polity) or {}).items():
        t[kk] = row["audience"]
    return t


def check_key(name) -> str:
    kk = str(name)
    base = kk[:-len(OPEN)] if kk.endswith(OPEN) else kk
    if base not in ET.REG and base not in ET.ALIASES:
        raise L.LawError(f"publication: no event type {base}")
    canon = ET.canonical(base)
    if ET.REG[canon].kind in SEALED_KINDS:
        raise L.LawError(f"publication: {canon} is the monitor's own record and cannot be published")
    if kk.endswith(OPEN):
        if canon not in MIXED:
            raise L.LawError(f"publication: {canon} has no {OPEN} sub-key (only types logged both publicly and not)")
        return canon + OPEN
    return canon


def check_audience(a) -> str:
    s = str(a)
    if s in AUDIENCES or (s.startswith("officials:") and len(s) > len("officials:")):
        return s
    raise L.LawError(f"publication: an audience is one of {', '.join(AUDIENCES)} or officials:<right>, not {s!r}")


def set_rule(k, polity, kk, audience, lid=None) -> dict:
    """The set_publication primitive's change: polity's row for key kk (validated by the caller)."""
    _store(k)["rules"].setdefault(polity, {})[kk] = {"audience": audience, "law": lid}
    k.log("publication_set", None, {"polity": polity, "key": kk, "audience": audience, "law": lid}, vis="public")
    return {"key": kk, "audience": audience}


def reset_rule(k, polity, kk, lid=None) -> dict:
    rows = _store(k)["rules"].get(polity) or {}
    rows.pop(kk, None)
    k.log("publication_set", None, {"polity": polity, "key": kk, "audience": None, "law": lid}, vis="public")
    return {"key": kk, "audience": None}


def set_base(k, name) -> None:
    if name not in BASES:
        raise ValueError(f"publication base is one of {', '.join(BASES)}")
    _store(k)["base"] = name


# ---------------------------------------------------------------------- audiences
def _agents(k, xs) -> list:
    ag = k.w["agents"]
    out = []
    for x in xs:
        if isinstance(x, str) and x in ag and x not in out:
            out.append(x)
    return out


def parties(k, agent, data) -> list:
    """The event's agent, then the agents its data names under DATA_AGENT_KEYS (top level; lists whole), in that order."""
    xs = [agent]
    if isinstance(data, dict):
        for kk in DATA_AGENT_KEYS:
            v = data.get(kk)
            if isinstance(v, (list, tuple)):
                xs.extend(v)
            else:
                xs.append(v)
    return _agents(k, xs)


def polity(k, agent, data) -> str:
    from charter import evidence as EVD
    from charter import jurisdictions as J
    a = EVD.about(k, data)
    if isinstance(a, str) and (a in (k.w.get("jurisdictions") or {}) or J.association(k, a) is not None or a == "J0"):
        return a
    if "jur" in k.w and agent in k.w["agents"]:
        m = J.member_of(k, agent)
        if m:
            return m
    return "J0"


def members(k, pol) -> list:
    from charter import jurisdictions as J
    a = J.association(k, pol)
    if a is not None:
        return list(a["members"])
    if "jur" not in k.w:
        return k.roster()
    return J.members(k, pol)


def natural(k, kind, agent, data, vis="public"):
    """The natural audience (a vis value): the call site's own when restricted, else by the type's declared natural audience."""
    if vis != "public":
        return vis
    t = ET.REG.get(ET.canonical(kind))
    nat = t.natural if t is not None else "parties"
    if nat == "public":
        return "public"
    xs = parties(k, agent, data)
    if nat == "channel" and isinstance(data, dict):
        ch = k.w["channels"].get(str(data.get("channel")))
        if ch:
            xs = _agents(k, [ch["owner"], *ch["members"], *xs])
    return xs or "monitor"


def _audience_list(k, aud, pol, agent, data) -> list:
    if aud == "parties":
        return parties(k, agent, data)
    mem = members(k, pol)
    if aud == "members":
        return mem
    right = aud.split(":", 1)[1]
    return [a for a in mem if k.has(a, right)]


def _sealed(k, kind, data) -> bool:
    """Ceilings: a DM (encrypted: never; else only where laws may read DMs) and a channel post never widen."""
    if kind in ("dm", "forged_dm"):
        return bool((data or {}).get("encrypted")) or not (k.spec.get("conditions") or {}).get("law_reads_dms")
    return kind == "channel_post"


def _widen(k, nat, extra) -> object:
    if nat == "public":
        return "public"
    if nat == "monitor":
        base = []
    elif isinstance(nat, str) and nat.startswith("channel:"):
        ch = k.w["channels"].get(nat.split(":", 1)[1])
        base = _agents(k, [ch["owner"], *ch["members"]]) if ch else []
    else:
        base = list(nat)
    out = base + [a for a in extra if a not in base]
    return out or "monitor"


def publish(k, kind, agent, data, vis="public"):
    """Kernel.log's one publication step: (the vis the event is logged with, extra fields for the event record or None)."""
    kk = key(kind, vis)
    pol = polity(k, agent, data)
    aud = table(k, pol).get(kk, "natural")
    t = ET.REG.get(ET.canonical(kind))
    extra = None
    if aud == "natural" or (t is not None and t.kind in SEALED_KINDS) or _sealed(k, kind, data):
        out = natural(k, kind, agent, data, vis)
    elif aud == "public":
        out = "public"
    else:
        nat = natural(k, kind, agent, data, vis)
        out = _widen(k, nat, _audience_list(k, aud, pol, agent, data))
        if out != nat:
            extra = {"pub": {"polity": pol, "audience": aud}}
    if out == "public" and "jur" in k.w:                               # a hidden jurisdiction's events reach its members only
        from charter import jurisdictions as J
        out = J.vis(k, data, out)
    return out, extra


# ---------------------------------------------------------------------- reading what was published
def audience(k, event):
    """Who was told of a logged event: its vis ("public", a list of agent ids, "channel:<id>", "monitor"). With the flag on this is
    the published audience (natural, widened by the polity's table); off, the call site's literal (narrowed for hidden
    jurisdictions). The one source for "who may know" (evidence.law_can_see)."""
    return event.get("vis")


def published_to(k, event):
    """(polity, audience) when the event was widened to a polity's register (parties, members or officials), else None."""
    p = event.get("pub")
    return (p.get("polity"), p.get("audience")) if isinstance(p, dict) else None


# ---------------------------------------------------------------------- the law API (law.v2 and law.publication)
def law_api(k, lid) -> dict:
    from charter import accounts as AC

    def pol():
        return AC.account_of(k, lid)

    def publish_(event_type, audience="public"):
        kk = check_key(event_type)
        a = check_audience(audience)
        k.apply("set_publication", polity=pol(), key=kk, audience=a, lid=lid)
        return True

    def unpublish(event_type):
        kk = check_key(event_type)
        k.apply("set_publication", polity=pol(), key=kk, audience=None, lid=lid)
        return True

    def publication(event_type=None):
        t = table(k, pol())
        if event_type is None:
            return dict(sorted(t.items()))
        return t.get(check_key(event_type), "natural")

    return {"publish": publish_, "unpublish": unpublish, "publication": publication}


def change_set(k, polity, key, audience, lid=None) -> dict:
    """The set_publication primitive's change (dispatch.changes.publication:do_set_publication): audience None drops the row."""
    if audience is None:
        return reset_rule(k, polity, key, lid)
    return set_rule(k, polity, key, audience, lid)


# ---------------------------------------------------------------------- V17: the channel register as laws see it
def channel_visible(k, lid, name) -> bool:
    """May law lid know that channel `name` exists (and who is in it)? Only if it may read the channel's creation (its latest
    channel_created event): under the today table every creation is public, as before."""
    from charter import evidence as EVD
    for e in reversed(k.events):
        if e["type"] == "channel_created" and (e.get("data") or {}).get("channel") == name:
            return EVD.law_can_see(k, lid, e)
    return False
