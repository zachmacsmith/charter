"""Compel visibility (P3.7; D-5; review 08 §3, review 09 §4.6).

Behind law.v2: spec law.notify_parties (None: follows law.v2, so every world without v2 is untouched). A change of a primitive in
NOTIFY (live rows with a compel face and compel_vis "parties") that a law causes -- a law frame on the cause stack: its hooks, its
API calls, its procedures and callbacks, and what they set off -- logs a `compelled` event to the row's agent parties: which law
(and the hook or function it ran in), what changed (the payload as the party may see it), why, and who the parties are. A law's
own before-hook charge is not repeated (its payer is told by law_charged). Redaction per recipient (D-18): concealed actors, a
covert attacker, an unnamed killer and the observer read as None (a party always sees itself); a law of a hidden jurisdiction
reads as "hidden" to non-members (its id masked everywhere in the data, the hook left out). Recipients who would read the same
data share one event. Rows in NOTIFY whose own event already reaches the parties (offer_loan's loan_offer) or that have no agent
party (create_currency, create_right, define_action, create_clause) log nothing more."""
from __future__ import annotations

import copy as _copy
import json as _json

from charter import jurisdictions as J
from charter import primitives as PR

from charter.dispatch.base import v2
from charter.dispatch.hooks import hidden_agents, _scrub


NOTIFY = tuple(n for n, p in PR.PRIMITIVES.items() if p.status == "live" and p.compel and p.compel_vis == "parties")
# NOTIFY rows not routed through apply, and how their parties learn of a law-caused change (tests/test_charter_notify.py)
NOTIFY_SITES = {"set_title": "kernel:Kernel.api_for.title calls compel_note/compelled itself",
                "offer_loan": "its own loan_offer event reaches the lender and the borrower",
                "create_clause": "no party: a clause is the law's own record"}
OWN_EVENT = ("offer_loan",)          # routed through apply since loans became primitives, but its own event already tells the parties


def notify_on(k) -> bool:
    """law.notify_parties, defaulting to law.v2 (I-8); never without law.v2."""
    if not v2(k):
        return False
    x = (k.spec.get("law") or {}).get("notify_parties")
    return True if x is None else bool(x)


def _released(k, p, opts):
    """guard_release by a law (why "law") clears its obligations: the pairs it releases, read before the change."""
    if (opts or {}).get("why") != "law":
        return None
    pairs = [list(x) for x in ((k.w.get("conflict") or {}).get("obligations") or {}).get((opts or {}).get("lid")) or []]
    return {"released": pairs}, [a for pair in pairs for a in pair]


SUBJECTS = {"guard_release": _released}                              # (change, parties) where the payload does not name them


DONE = {"move": lambda r: bool(r) and (r.get("moved") or 0) > 0}       # did the change happen (a short balance moves nothing)


def compel_note(k, name, p, opts=None) -> dict | None:
    """Before a change: the note compelled() logs after it, or None (notification off, not law-caused, no agent party)."""
    if name not in NOTIFY or name in OWN_EVENT or k.dry or not notify_on(k):
        return None
    f = next((f for f in reversed(k._causes) if next(iter(f)) == "law"), None)
    if f is None or f.get("charge"):
        return None
    P = PR.get(name)
    sub = SUBJECTS.get(name)
    got = sub(k, p, opts) if sub else None
    change, who = got if got is not None else (dict(p), [p.get(x) for x in P.parties])
    if name == "move" and change.get("memo") is None:                 # W6a: a move without a memo reads as before
        change.pop("memo", None)
    if name == "breach" and change.get("victim") is None:             # W7e: a breach without a victim reads as before
        change.pop("victim", None)
    who = [a for a in dict.fromkeys(who) if isinstance(a, str) and a in k.w["agents"]]
    if not who:
        return None
    why = p.get("why") or (opts or {}).get("why") or f.get("hook")
    return {"primitive": name, "law": f["law"], "hook": f.get("hook"), "why": why, "change": _copy.deepcopy(change),
            "parties": who, "hide": hidden_agents(k, name, p, opts or {})}


def _mask(x, lid):
    """A hidden law's id out of event data (also inside "law:L7"-style strings)."""
    if isinstance(x, str):
        return "hidden" if x == lid else (":".join("hidden" if s == lid else s for s in x.split(":")) if ":" in x else x)
    if isinstance(x, dict):
        return {kk: _mask(v, lid) for kk, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_mask(v, lid) for v in x]
    return x


def compelled(k, note, result=None) -> None:
    """Log the `compelled` events of a note (compel_note) once its change is made."""
    done = DONE.get(note["primitive"])
    if done is not None and not done(result):
        return
    lid = note["law"]
    lj = J.law_jur(k, lid)
    insiders = set(J.members(k, lj)) if "jur" in k.w and k._hidden_jur(lj) else None
    groups: dict = {}
    for aid in note["parties"]:
        hide = set(note["hide"]) - {aid}
        data = {"primitive": note["primitive"], "law": lid, "hook": note["hook"], "why": note["why"],
                "change": note["change"], "parties": note["parties"]}
        data = _scrub(data, hide) if hide else _copy.deepcopy(data)
        if insiders is not None and aid not in insiders:
            data = {**_mask(data, lid), "law": "hidden", "hook": None}
        data = {x: v for x, v in data.items() if v is not None}
        groups.setdefault(_json.dumps(data, sort_keys=True, default=str), (data, []))[1].append(aid)
    for data, who in groups.values():
        k.log("compelled", None, data, vis=who)
