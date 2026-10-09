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
Not here: grants (WP-E), dormancy and succession (WP-F), recognition and institutions as members (WP-G), channels (WP-C).
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
    """The institution's offices: actions defined by its laws (define_action), by name."""
    from charter import jurisdictions as J
    out = []
    for name, a in sorted((k.w.get("actions") or {}).items()):
        lid = a.get("law") if isinstance(a, dict) else None
        if isinstance(lid, str) and J.law_jur(k, lid) == iid:
            out.append(name)
    return out
