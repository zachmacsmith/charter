"""Institutions: one store for polities and associations (P4.6 done properly; review 14 §3.1, §3.5, §6.1 row D, §6.3; D-35, D-37).

Behind spec `institutions.unified` (default false). Off, nothing here writes state: jurisdictions keep k.w["jurisdictions"],
associations k.w["contracts"]["assoc"], and every world is byte-identical. The read helpers at the bottom (get, kind_of, is_member,
members, status, published) work either way, so code written for the unified store (channels, WP-C; grants, WP-E) can call them
in any world.

On:
  The store, k.w["institutions"] = {iid: record}: every jurisdiction (kind "polity", J0 included) and every contract association
  (kind "association") as one record kind. The fields every record has (both old records already had most of them):
      id, kind, name, founder, founded_round, treasury (owner key), reserve (its holdings),
      status      forming | active | dissolved   ("dormant" is WP-F's)
      published   who its existence is published to: "members" (founded in secret: its members only) | "public"
      members     agent ids: an association's members; a polity's members in roster order (its pledged members while forming,
                  its declared members once active), synced after every membership change and at the end of the round
      parent      None for a root; the polity a company is incorporated under (W8e)
  A kind's own fields stay on the record as before (a polity's procedures, camp rules, charter, dormant laws, hidden_members,
  pending declaration; an association's escrow, allowances, applicants, proposals, template and params): they are its template's
  state, read and written by its module. Laws and offices are not copied in: laws(k, iid) and offices(k, iid) index the law store
  and the defined actions, which stay the one record of each.
  k.w["jurisdictions"] and k.w["contracts"]["assoc"] are not stored. jurisdictions.jurs(k) and accounts.assocs(k) return read-only
  views over the store (view(k, kind)); writes go through add / remove. Snapshots keep their shape (jurisdictions.snapshot_fields
  and contracts.snapshot_fields project each record as before; legacy_view(rec) is the old record), so History, the scorer, goals,
  context and export read what they always read.

  "Hidden" is no longer a status. A polity founded in secret is `forming`, its existence published to its members; declaring it
  publishes its existence and activates it (jurisdictions.set_status(..., "declared")). The secrecy checks (jurisdictions.vis,
  linker, evidence, the law previewer, dispatch.hooks.SECRET, Kernel._hidden_jur) read the publication (jurisdictions.secret), the
  lifecycle checks read the status (jurisdictions.st gives today's name: hidden | declared | dissolved).

  One path:
    found        the found action founds a polity, or an association when given code or a template (create_contract and its
                 primitive stay as the association alias: laws hook before_create_contract); the found primitive takes kind None
                 for a new institution (the polity template), "jurisdiction" as an alias
    membership   join, leave, admit and expel (dispatch.changes.membership) go through change(k, op, ...): the kind's handler
                 (HANDLERS), then sync. Exit stays each kind's (D-26: a polity's on_exit is law; an association's exit is kept)
    dissolve     a contract's dissolution is routed (the dissolve primitive, kind "association"): laws' before/after hooks see it.
                 A block cannot keep a memberless contract (dormancy is WP-F): it is dissolved all the same
Not here: grants (WP-E: charter/grants.py), dormancy and succession (WP-F), recognition and institutions as members (WP-G),
channels (WP-C).

Offices (WP-E, institutions.grants on; review 14 §3.1, §7.2). An office is a named right "<iid>.<office>" its code declares with a
top-level constant, read statically when the law comes into force (an association's founding code and adopted changes, a polity's
enacted laws, J0's laws):
    offices = {"treasurer": {"title": "Treasurer", "powers": ["pay"], "holders": ["founder"], "seats": 1, "term": 4}}
  title    what the office is called (default: the name)
  powers   what its holder may do: names (the institution's defined actions the right gates, "speak" to speak for it) and bounded
           grants in P4.5 agency format, {"action": "transfer", "item": "grain", "qty": 5, "to": None, "rounds": None}: a standing
           authorization from the institution (grantor) to whoever holds the office (grantee), review 18 §2.3. The verbs are
           GRANT_VERBS; using a grant `as` the institution (every use an agency_used event) is review 18 H2, not built here
  holders  its first holders ("founder" or agent ids; members only for an association)
  seats    how many may hold it (None: any; recorded, not enforced); term: rounds a holding lasts (None: no term)
  Holding is an explicit record, k.w["offices"][iid][office] = {"id": "<iid>.<office>", "office", "title", "powers" (names),
  "grants": [{"grantor": iid, "grantee": "<iid>.<office>", "action", "item", "qty", "to", "rounds"}], "seats", "term", "law",
  "declared", "holders": [{"holder", "since", "term_end"}], "past": [{"holder", "since", "term_end", "until"}]},
  kept in step with the right: dispatch's grant_right / revoke_right changes call on_right. Vacancies (death, exit, term end,
  removal) and succession: charter/succession.py (institutions.succession; an office may then declare "succession": {"rule": ...},
  stored on the record, and a holding's end records its cause in `past`). Without that flag a dead or departed holder stays in the
  record (holders() skips it). Under it, the repeal of the law that declared an office abolishes the office (on_law_repealed).
  Reads: offices(k, iid), office(k, iid, name), holders(k, iid, office), officers(k, iid) (holders of any office).
"""
from __future__ import annotations

from types import MappingProxyType

KEY = "institutions"
KINDS = ("polity", "association")
STATUSES = ("forming", "active", "dissolved")
PUBLISHED = ("members", "public")
UNIFIED = ("published", "members", "parent")      # fields the unified record adds to an old one (members: a polity's)
LEGACY_STATUS = {"forming": "hidden", "active": "declared"}       # a polity's old names (an association's are unchanged)
_FROM_LEGACY = {"hidden": "forming", "declared": "active"}
HANDLERS = {"polity": "charter.jurisdictions", "association": "charter.contracts"}   # each kind's membership changes
OFFICES = "offices"                                                  # k.w["offices"] (institutions.grants): office records
OFFICE_FIELDS = ("title", "powers", "holders", "seats", "term")
_EMPTY = MappingProxyType({})


# ---------------------------------------------------------------------- the flag
def unified_spec(spec) -> bool:
    return bool(((spec or {}).get(KEY) or {}).get("unified"))


def unified(k) -> bool:
    return unified_spec(k.spec)


# ---------------------------------------------------------------------- the store (flag on)
def store(k) -> dict:
    """The live store (created on the first founding; a world with neither jurisdictions nor contracts has none)."""
    st = k.w.get(KEY)
    if st is None:
        st = k.w[KEY] = {}
    return st


def unify(rec: dict) -> dict:
    """An old record as a unified one (in place): today's status names to forming / active, plus published, members and parent."""
    if rec["kind"] == "polity":
        hidden = rec["status"] == "hidden"
        rec["status"] = _FROM_LEGACY.get(rec["status"], rec["status"])
        rec["published"] = "members" if hidden else "public"
        rec["members"] = list(rec.get("hidden_members") or []) if hidden else []
    else:
        rec["published"] = "public"                                    # an association is public from its founding
    rec.setdefault("parent", None)
    return rec


def add(k, rec: dict) -> dict:
    store(k)[rec["id"]] = unify(rec)
    k._inst_views = None
    return rec


def remove(k, iid) -> None:
    """A founding that failed (its laws did not load): the record goes, as it went from the old stores."""
    del store(k)[iid]
    k._inst_views = None


def view(k, kind: str):
    """A read-only view of the store's records of one kind, in founding order (the records themselves: changes to a record are
    changes to the store). Rebuilt when the store is replaced (a dry run's rollback) or grows."""
    st = k.w.get(KEY)
    if st is None:
        return _EMPTY
    c = getattr(k, "_inst_views", None)
    if c is None or c[0] is not st or c[1] != len(st):
        c = k._inst_views = (st, len(st), {})
    v = c[2].get(kind)
    if v is None:
        v = c[2][kind] = MappingProxyType({i: r for i, r in st.items() if r["kind"] == kind})
    return v


def legacy_status(rec: dict) -> str:
    """Today's status name of a record (hidden | declared | dissolved for a polity; active | dissolved for an association)."""
    s = rec["status"]
    return LEGACY_STATUS.get(s, s) if rec.get("kind", "polity") == "polity" and "published" in rec else s


def from_legacy_status(rec: dict, s: str) -> str:
    return _FROM_LEGACY.get(s, s) if rec.get("kind", "polity") == "polity" and "published" in rec else s


def legacy_view(rec: dict) -> dict:
    """The record as the old store held it: without the unified fields, with today's status name (a company keeps its parent)."""
    out = {x: v for x, v in rec.items() if x not in UNIFIED}
    out["status"] = legacy_status(rec)
    if rec["kind"] == "association":
        out["members"] = list(rec["members"])
        if rec.get("parent") is not None:
            out["parent"] = rec["parent"]
    return out


def legacy_stores(k) -> dict:
    """{"jurisdictions": {...}, "assoc": {...}}: the old stores, rebuilt from the unified one (tests and migration)."""
    return {"jurisdictions": {i: legacy_view(r) for i, r in view(k, "polity").items()},
            "assoc": {i: legacy_view(r) for i, r in view(k, "association").items()}}


def sync(k, iid=None) -> None:
    """Refresh a polity's members (all polities' when iid is None) from the membership map. Off: nothing."""
    if not unified(k) or KEY not in k.w:
        return
    from charter import jurisdictions as J
    for jid, rec in view(k, "polity").items():
        if iid is None or jid == iid:
            rec["members"] = J.members(k, jid) if rec["status"] != "dissolved" else []


def end_round(k) -> None:
    """After the jurisdictions' end of round (arrivals, departures, deaths): every polity's members again."""
    sync(k)


# ---------------------------------------------------------------------- one path: found, membership, dissolve
def found_kind(kind):
    """The found primitive's kind: None (no longer required) is a new institution of the polity template; "jurisdiction" its
    alias. Other kinds (channel, outlet) are not institutions."""
    return "jurisdiction" if kind in (None, "polity", "institution") else kind


def _handler(k, iid):
    import importlib
    return importlib.import_module(HANDLERS[kind_of(k, iid) or "polity"])


def change(k, op: str, *args, iid=None, **kw) -> dict:
    """join / leave / admit / expel through the kind's handler (charter/jurisdictions.py or charter/contracts.py change_<op>),
    then the polities' members. args as the handler takes them; iid the institution."""
    out = getattr(_handler(k, iid), f"change_{op}")(k, *args, **kw)
    sync(k)
    return out


def dissolve(k, iid, heirs=()) -> None:
    """Route an association's dissolution (the dissolve primitive, kind "association"; contracts.change_dissolve makes it). A block
    by a law cannot keep a memberless contract alive: it is dissolved anyway, as an exit cannot be refused."""
    out = k.apply("dissolve", polity=iid, kind="association", agent=None, heirs=list(heirs))
    if not out.ok and get(k, iid)["status"] != "dissolved":
        from charter import contracts as CT
        CT.change_dissolve(k, iid, list(heirs))


# ---------------------------------------------------------------------- reads (either representation; channels and grants call these)
def get(k, iid):
    """The institution record of iid (polity or association), or None. Off: the old stores' record."""
    if not isinstance(iid, str):
        return None
    if unified(k):
        return (k.w.get(KEY) or {}).get(iid)
    from charter import jurisdictions as J
    a = J.association(k, iid)
    if a is not None:
        return a
    return (k.w.get("jurisdictions") or {}).get(iid)


def kind_of(k, iid):
    """"polity" | "association" | None (not an institution). J0 is a polity even when jurisdictions are off (the world itself)."""
    rec = get(k, iid)
    if rec is not None:
        return rec.get("kind", "polity")
    return "polity" if iid == "J0" else None


def all_(k) -> dict:
    """{iid: record} of every institution, polities first then associations in the old stores' order (flag on: founding order)."""
    if unified(k):
        return dict(k.w.get(KEY) or {})
    from charter import accounts as AC
    return {**(k.w.get("jurisdictions") or {}), **AC.assocs(k)}


def status(k, iid):
    """forming | active | dissolved, or None. Off: mapped from today's names (hidden -> forming, declared -> active)."""
    rec = get(k, iid)
    if rec is None:
        return "active" if iid == "J0" else None
    return _FROM_LEGACY.get(rec["status"], rec["status"])


def published(k, iid):
    """Who the institution's existence is published to: "members" (founded in secret, not yet declared) or "public"."""
    rec = get(k, iid)
    if rec is None:
        return "public" if iid == "J0" else None
    if "published" in rec:
        return rec["published"]
    return "members" if rec["status"] == "hidden" else "public"


def members(k, iid) -> list:
    """The institution's members: an association's; a polity's declared members (its pledged ones while forming); J0 with
    jurisdictions off: everyone on the roster."""
    from charter import jurisdictions as J
    rec = get(k, iid)
    if rec is not None and rec.get("kind") == "association":
        return list(rec["members"])
    if rec is None and iid != "J0":
        return []
    return J.members(k, iid)


def is_member(k, iid, aid) -> bool:
    return aid in members(k, iid)


def laws(k, iid) -> list:
    """The ids of the institution's laws in force, in enactment order (the law store is their one record)."""
    from charter import jurisdictions as J
    return [l["id"] for l in k.active_laws() if J.law_jur(k, l["id"]) == iid]


def offices(k, iid) -> list:
    """The institution's offices. institutions.grants: the offices its code declared (`offices = {...}`, below), by name, in
    declaration order. Off: actions defined by its laws (define_action), by name (defined_actions)."""
    from charter import grants as G
    if G.on(k):
        return list(((k.w.get(OFFICES) or {}).get(iid) or {}).keys())
    return defined_actions(k, iid)


def defined_actions(k, iid) -> list:
    """Actions defined by the institution's laws (define_action), by name."""
    from charter import jurisdictions as J
    out = []
    for name, a in sorted((k.w.get("actions") or {}).items()):
        lid = a.get("law") if isinstance(a, dict) else None
        if isinstance(lid, str) and J.law_jur(k, lid) == iid:
            out.append(name)
    return out


# ---------------------------------------------------------------------- offices (institutions.grants; see the module docstring)
def _office_name(x) -> bool:
    return isinstance(x, str) and 0 < len(x) <= 24 and all(c.isalnum() or c == "_" for c in x)


# The verbs an office grant may cover (review 18 §2.3: the closed list an officer may use `as` the institution; never vote,
# attack, commission or bequest). The use path (`as` on these verbs, agency_used events) is review 18 H2's; this package records
# the grants in P4.5 agency format so H2 has one record to read.
GRANT_VERBS = ("transfer", "deposit_escrow", "lend", "accept_loan", "repay_loan", "contribute", "harvest", "lease", "accept_lease",
               "send", "post", "open_channel", "set_channel", "dir_write", "dir_grant", "accuse")
GRANT_KEYS = ("action", "item", "qty", "to", "rounds")


def _office_grant(name, g) -> dict:
    """One bounded office grant, checked: the P4.5 agency scope {action, item, qty (per round), to (recipients | None), rounds}."""
    from charter import lawlang as L
    if any(x not in GRANT_KEYS for x in g):
        raise L.LawError(f"offices.{name}.powers: a grant is {{{', '.join(GRANT_KEYS)}}}")
    act = g.get("action")
    if act not in GRANT_VERBS:
        raise L.LawError(f"offices.{name}.powers: an office grant's action is one of {', '.join(GRANT_VERBS)} (never vote or attack)")
    item = g.get("item") or ("message" if act in ("send", "post") else None)
    if item is not None and not isinstance(item, str):
        raise L.LawError(f"offices.{name}.powers: item is a name")
    qty = g.get("qty")
    if qty is not None and (isinstance(qty, bool) or not isinstance(qty, (int, float)) or qty < 0):
        raise L.LawError(f"offices.{name}.powers: qty is a number per round (or None: no bound)")
    to = g.get("to")
    if to is not None and not (isinstance(to, list) and all(isinstance(x, str) for x in to)):
        raise L.LawError(f"offices.{name}.powers: to is a list of recipients (or None: any)")
    rounds = g.get("rounds")
    if rounds is not None and (isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1):
        raise L.LawError(f"offices.{name}.powers: rounds is a whole number from 1 (or None: until changed)")
    return {"action": act, "item": item, "qty": None if qty is None else float(qty), "to": to, "rounds": rounds}


def parse_offices(code, succession=False) -> dict:
    """The offices a law's code declares ({} when none), checked: a LawError says what is wrong. succession (institutions.succession):
    an office may also declare its succession clause (succession.check_clause)."""
    from charter import grants as G
    from charter import lawlang as L
    v = G._declared(str(code or ""), "offices")
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise L.LawError("offices is a literal {name: {title, powers, holders, seats, term}}")
    out = {}
    for name, d in v.items():
        if not _office_name(name):
            raise L.LawError(f"offices: an office name is 1-24 letters, digits or _ (got {name!r})")
        d = {} if d is None else d
        fields = OFFICE_FIELDS + (("succession",) if succession else ())
        if not isinstance(d, dict) or any(x not in fields for x in d):
            raise L.LawError(f"offices.{name}: an object with {', '.join(fields)}")
        powers, holders_ = d.get("powers") or [], d.get("holders") or []
        if not isinstance(powers, list) or not all(isinstance(x, (str, dict)) for x in powers):
            raise L.LawError(f"offices.{name}.powers: a list of names or bounded grants {{action, item, qty, to, rounds}}")
        names = [x for x in powers if isinstance(x, str)]
        grants = [_office_grant(name, x) for x in powers if isinstance(x, dict)]
        if not isinstance(holders_, list) or not all(isinstance(x, str) for x in holders_):
            raise L.LawError(f"offices.{name}.holders: a list of agent ids or \"founder\"")
        for f in ("seats", "term"):
            n = d.get(f)
            if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < 1):
                raise L.LawError(f"offices.{name}.{f}: a whole number from 1 (or None)")
        out[name] = {"title": str(d.get("title") or name.replace("_", " ").title())[:60], "powers": names, "grants": grants,
                     "holders": list(holders_), "seats": d.get("seats"), "term": d.get("term")}
        if succession:
            from charter import succession as SU
            out[name]["succession"] = SU.check_clause(name, d["succession"]) if d.get("succession") is not None else None
    return out


def declare_offices(k, iid, lid) -> list:
    """Law lid of institution iid came into force (flag on): the offices its code declares that iid does not have yet become
    records and rights; their first holders are granted the right (a public `rights` event each). Returns the new offices' names.
    A malformed declaration declares nothing (it was checked at founding; a later law's is skipped)."""
    from charter import dispatch as D
    from charter import grants as G
    from charter import lawlang as L
    from charter import succession as SU
    if not G.on(k):
        return []
    law = k.w["laws"].get(lid) or {}
    try:
        decl = parse_offices(law.get("code"), SU.on(k))
    except L.LawError:
        return []
    if not decl:
        return []
    mine = k.w.setdefault(OFFICES, {}).setdefault(iid, {})
    rec = get(k, iid)
    new = []
    for name, d in decl.items():
        if name in mine:
            continue
        right = f"{iid}.{name}"
        if right not in k.w["rights"]:
            k.apply("create_right", right=right)
        mine[name] = {"id": right, "office": name, "title": d["title"], "powers": d["powers"],
                      "grants": [{"grantor": iid, "grantee": right, **g} for g in d["grants"]], "seats": d["seats"],
                      "term": d["term"], "law": lid, "declared": k.r, "holders": [], "past": []}
        if "succession" in d:                                           # institutions.succession: its clause (None: polity law)
            mine[name]["succession"] = d["succession"]
        new.append(name)
        for h in d["holders"]:
            aid = (rec or {}).get("founder") if h == "founder" else h
            if aid not in k.w["agents"] or k.w["agents"][aid].get("departed") is not None:
                continue
            if kind_of(k, iid) == "association" and not is_member(k, iid, aid):
                continue
            try:
                k.apply("grant_right", agent=aid, right=right, lid=lid)
            except D.PhysicsError:
                continue
    return new


def on_right(k, agent, right, granted: bool) -> None:
    """dispatch's grant_right / revoke_right changed an agent's right: if it is a declared office, its holding record follows."""
    if not isinstance(right, str) or "." not in right:
        return
    iid, _, name = right.partition(".")
    o = ((k.w.get(OFFICES) or {}).get(iid) or {}).get(name)
    if o is None:
        return
    cur = next((h for h in o["holders"] if h["holder"] == agent), None)
    if granted and cur is None:
        o["holders"].append({"holder": agent, "since": k.r, "term_end": k.r + o["term"] if o["term"] else None})
    elif not granted and cur is not None:
        o["holders"].remove(cur)
        from charter import succession as SU
        if SU.on(k):                                                    # institutions.succession: the end is a vacancy (cause)
            past = {**cur, "until": k.r, "cause": SU.current_cause(k)}
            o["past"].append(past)
            SU.vacated(k, iid, name, past)
        else:
            o["past"].append({**cur, "until": k.r})


def on_law_repealed(k, lid, replaced_by=None) -> list:
    """institutions.succession: a law left force (repealed; an association's law retired, replaced or ended with its contract). The
    offices it declared are abolished: their holders lose the right (no vacancy), an `office_abolished` event each, and the record
    goes. An office the replacing law (replaced_by) declares again is kept, bound to that law, with its new declaration's fields.
    Off: nothing. Returns the abolished offices' names."""
    from charter import lawlang as L
    from charter import succession as SU
    if not SU.on(k) or OFFICES not in k.w:
        return []
    from charter import jurisdictions as J
    iid = J.law_jur(k, lid)
    mine = (k.w[OFFICES] or {}).get(iid) or {}
    again = {}
    if replaced_by is not None:
        try:
            again = parse_offices((k.w["laws"].get(replaced_by) or {}).get("code"), True)
        except L.LawError:
            again = {}
    out = []
    for name, o in list(mine.items()):
        if o["law"] != lid:
            continue
        if name in again:
            d = again[name]
            o.update({"law": replaced_by, "title": d["title"], "powers": d["powers"], "seats": d["seats"], "term": d["term"],
                      "grants": [{"grantor": iid, "grantee": o["id"], **g} for g in d["grants"]], "succession": d["succession"]})
            continue
        with SU.cause(k, None):
            for h in list(o["holders"]):
                k.apply("revoke_right", agent=h["holder"], right=o["id"], via="vacancy")
        del mine[name]
        k.log("office_abolished", None, {"institution": iid, "office": name, "right": o["id"], "law": lid,
                                         "past": [h["holder"] for h in o["past"]]}, vis="public")
        out.append(name)
    return out


def usable_grants(k, iid, name) -> list:
    """The office's agency-format grants usable now: none while the office is vacant (no living holder; review 18 §2.5)."""
    o = office(k, iid, name)
    return list(o["grants"]) if o is not None and holders(k, iid, name) else []


def office(k, iid, name):
    """The office record (or None). name: "treasurer" or "<iid>.treasurer"."""
    if isinstance(name, str) and name.startswith(f"{iid}."):
        name = name[len(iid) + 1:]
    return ((k.w.get(OFFICES) or {}).get(iid) or {}).get(name)


def holders(k, iid, name) -> list:
    """The office's current holders (live agents only: a dead holder stays in the record until WP-F's vacancy path)."""
    o = office(k, iid, name)
    if o is None:
        return []
    ag = k.w["agents"]
    return [h["holder"] for h in o["holders"] if h["holder"] in ag and ag[h["holder"]].get("departed") is None]


def officers(k, iid) -> list:
    """Holders of any office of the institution, in office then holding order, each once."""
    out = []
    for name in ((k.w.get(OFFICES) or {}).get(iid) or {}):
        for a in holders(k, iid, name):
            if a not in out:
                out.append(a)
    return out


def has_offices(k, iid) -> bool:
    return bool((k.w.get(OFFICES) or {}).get(iid))


def on_law_in_force(k, lid) -> None:
    """A law came into force (dispatch do_enact; an association's founding code or adopted change): its institution's offices.
    Off: nothing."""
    from charter import grants as G
    if not G.on(k):
        return
    from charter import jurisdictions as J
    declare_offices(k, J.law_jur(k, lid), lid)
