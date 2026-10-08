"""Law-readable evidence (review 10 §6 item 10, §7 "Gas and performance"; law.v2 only): two law-API reads over the event log.

    event(eid)                                         one event, if the law may see it, as a redacted plain-dict copy; else None
    history(type=None, agent=None, since=None, limit=20)   the newest `limit` events the law may see (at most MAX_LIMIT), filtered
                                                       by type (a name or a list of names), agent (the event's agent as shown)
                                                       and round (since: the first round, 0-based as round() returns it); in log
                                                       order, oldest first

Visibility: what a law may see is what its ACCOUNT may know as an institution, never what any one member privately knows.
  1. The public record: every event logged with vis "public" (Kernel.log has already narrowed a public event about a hidden
     jurisdiction to that jurisdiction's members, so such events are not public). Posts hidden by moderation stay readable with
     "hidden": True, as the posts() read has always shown them.
  2. Its own restricted record: an event whose visibility is a list of agents, when the event is about the law's own account
     (data "jurisdiction", "contract", "law" or "ballot" names it, as jurisdictions.vis attributes events) and that account is a
     hidden jurisdiction or an association, and every recipient is a member of it (a hidden jurisdiction's hidden or current members,
     an association's members). This is the members-only public record of a hidden polity or of a contract, which its own laws
     share with its members.
  Never: monitor-only events (truth and records: who wrote an anonymous post, a covert attacker, the true order), private events
  of one agent or a few (DMs, notices, private results, goals, a Spy's or other secret role's notes, law_charged and compelled
  notices of J0 or a declared polity), channel (group) messages, events about another account's restricted record.
Redaction (on the copy): the cause chain as dispatch.chain_view shows it to this law (no call ids; the observer as the world; a
hidden jurisdiction's law the viewer does not belong to as "hidden"); the observer's id as None anywhere; a hidden jurisdiction's
law ids (other than the viewer's own jurisdiction's) masked as "hidden"; a secret right or a secret camp as None. Concealed actors
(anonymous posts, forged messages, covert attacks, unnamed killers) are already absent from public events and their chains
(Kernel.concealing, the monitor-only truth events): a law reads the event as an agent would.

Gas: both reads are metered through the running call's meter (gas.Meter.tick), charged as the C-level builtins are (gas.SIZE_UNIT):
one tick per call, one per SIZE_UNIT events scanned and, per event returned, one plus one per SIZE_UNIT characters of its JSON. A
scan runs newest first and stops at `since` or at `limit` matches, so a read costs what it touches. Charged before the copy is
handed over; a read that overruns a budget dies as any other law operation does (the invocation dies; its law is flagged).
Determinism: the log, the rules and the costs are all deterministic; nothing here writes.
"""
from __future__ import annotations

import copy
import json

from charter import gas as G
from charter import jurisdictions as J
from charter import lawlang as L

MAX_LIMIT = 50                         # events one history() call may return
DEFAULT_LIMIT = 20


def _account_members(k, acct) -> set | None:
    """Members of a restricted account (a hidden jurisdiction: hidden and current members; an association: its members), or None
    when the account has no restricted record (J0, a declared polity without hidden members)."""
    a = J.association(k, acct)
    if a is not None:
        return set(a["members"])
    if "jur" not in k.w:
        return None
    j = J.jurs(k).get(acct)
    if not j:
        return None
    out = set(j.get("hidden_members") or ())
    if j["status"] != "hidden" and not out:
        return None                                                    # a declared polity: its record is the public one
    if j["status"] != "hidden":
        out |= set(J.members(k, acct))
    return out or None


def about(k, data) -> str | None:
    """The account an event is about (jurisdictions.vis's attribution, plus a contract's id), or None."""
    if not isinstance(data, dict):
        return None
    for key in ("jurisdiction", "contract"):
        if isinstance(data.get(key), str):
            return data[key]
    lid = data.get("law")
    if isinstance(lid, str) and lid in k.w["laws"]:
        return J.law_jur(k, lid)
    b = data.get("ballot")
    if isinstance(b, str) and b in k.w["ballots"]:
        return J.ballot_jur(k, k.w["ballots"][b])
    return None


def sees(k, lid, e) -> bool:
    """May law `lid` read event `e`? (the module docstring's rule)"""
    vis = e.get("vis")
    if vis == "public":
        return True
    if not isinstance(vis, list) or not vis:
        return False                                                   # monitor-only, channel messages
    acct = J.law_jur(k, lid)
    if about(k, e.get("data")) != acct:
        return False
    members = _account_members(k, acct)
    return members is not None and set(vis) <= members


def _hidden_laws(k, lid) -> set:
    """Ids of the laws of hidden jurisdictions other than this law's own."""
    if "jur" not in k.w:
        return set()
    own = J.law_jur(k, lid)
    return {x for x in k.w["laws"] if J.law_jur(k, x) != own and k._hidden_jur(J.law_jur(k, x))}


def _clean(k, x, obs, hidden_laws):
    from charter import rights as RT
    if isinstance(x, str):
        if obs is not None and x == obs:
            return None
        if x in hidden_laws:
            return "hidden"
        if ":" in x and hidden_laws and any(s in hidden_laws for s in x.split(":")):
            return ":".join("hidden" if s in hidden_laws else s for s in x.split(":"))
        return x
    if isinstance(x, dict):
        out = {}
        for kk, v in x.items():
            if kk == "right" and isinstance(v, str) and RT.is_secret(k, v):
                out[kk] = None
            elif kk == "rights" and isinstance(v, list):
                out[kk] = [_clean(k, r, obs, hidden_laws) for r in v if not (isinstance(r, str) and RT.is_secret(k, r))]
            elif kk == "camp" and isinstance(v, str) and (k.w["camps"].get(v) or {}).get("secret"):
                out[kk] = None
            else:
                out[kk] = _clean(k, v, obs, hidden_laws)
        return out
    if isinstance(x, (list, tuple)):
        return [_clean(k, v, obs, hidden_laws) for v in x]
    return x


def view(k, lid, e, hidden_laws=None) -> dict:
    """A plain-dict copy of event `e` as law `lid` may read it (call only for events `sees` admits)."""
    from charter import dispatch as D
    obs = D._observer(k)
    hl = _hidden_laws(k, lid) if hidden_laws is None else hidden_laws
    data = _clean(k, copy.deepcopy(e.get("data")), obs, hl)
    agent = _clean(k, e.get("agent"), obs, hl)
    out = {"id": e["id"], "round": e["round"], "type": e["type"], "agent": agent, "data": data,
           "cause": [dict(f) for f in D.chain_view(k, e.get("cause") or (), lid)]}
    if e["id"] in k.w.get("hidden", ()):
        out["hidden"] = True
    return out


def _find(k, eid):
    """The event with id `eid` (ids are e<n>, the n-th event; a rollback reuses ids, so the index is checked)."""
    s = str(eid)
    if s.startswith("e") and s[1:].isdigit():
        i = int(s[1:]) - 1
        if 0 <= i < len(k.events) and k.events[i]["id"] == s:
            return k.events[i]
    return None


def _charge_out(k, ev: dict) -> None:
    k.limited.meter.tick(1 + len(json.dumps(ev, sort_keys=True, default=str)) // G.SIZE_UNIT)


def event(k, lid, eid):
    k.limited.meter.tick(1)
    e = _find(k, eid)
    if e is None or not sees(k, lid, e):
        return None
    out = view(k, lid, e)
    _charge_out(k, out)
    return out


def history(k, lid, type=None, agent=None, since=None, limit=DEFAULT_LIMIT):
    meter = k.limited.meter
    meter.tick(1)
    try:
        n = int(limit)
    except (TypeError, ValueError):
        raise L.LawError("history: limit must be a number") from None
    n = max(0, min(n, MAX_LIMIT))
    types = None if type is None else ({type} if isinstance(type, str) else {str(t) for t in type})
    start = None if since is None else int(since)
    hl = _hidden_laws(k, lid)
    from charter import dispatch as D
    obs = D._observer(k)
    hits = []
    scanned = 0
    for e in reversed(k.events):
        if n <= len(hits):
            break
        if start is not None and e["round"] < start:
            break
        scanned += 1
        if scanned % G.SIZE_UNIT == 0:
            meter.tick(1)
        if types is not None and e["type"] not in types:
            continue
        if not sees(k, lid, e):
            continue
        if agent is not None and _clean(k, e.get("agent"), obs, hl) != agent:
            continue
        out = view(k, lid, e, hl)
        _charge_out(k, out)
        hits.append(out)
    return list(reversed(hits))


def law_api(k, lid) -> dict:
    return {"event": lambda eid: event(k, lid, eid),
            "history": lambda type=None, agent=None, since=None, limit=DEFAULT_LIMIT: history(k, lid, type, agent, since, limit)}
