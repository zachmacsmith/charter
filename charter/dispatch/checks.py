"""The primitives' physics checks (P2.1-P4.5), run by apply before any hook, grouped as dispatch.changes is. A check returns the
checked payload, or raises PhysicsError (a refusal), LawError (a bad argument) or _Noop (nothing to do: apply returns its result at
once). CHECKS maps a primitive to its check; a row without one has none (its callers keep their checks, e.g. the legal acts'
ActionError/LawError). CHECK_OPTIONS names the call options a check reads. Checks whose rule belongs to a feature delegate to its
module (media, credit, contracts, mortality); propose's is ranks.check_propose (law.v2: lex superior)."""
from __future__ import annotations

from charter import accounts as AC
from charter import eventtypes as ET
from charter import lawlang as L
from charter import rights as RT

from charter.dispatch.base import estate_access, _Noop, PhysicsError, v2
from charter.dispatch.changes.lifecycle import LIFE_CAUSES, LIFE_HOWS
from charter.dispatch.ranks import check_propose


POSTABLE = ET.names("post")                                           # what hide_post may hide (kernel.POSTABLE)


# ---------------------------------------------------------------------- goods (changes.economy)
def check_move(k, p):
    qty = float(p["qty"])
    if qty < 0 or qty != qty:
        raise L.LawError("quantity must be non-negative")
    if qty == 0:
        raise _Noop({"moved": 0.0})
    if str(p["why"]).startswith("law:"):                            # accounts: a law's move names agents and treasuries only
        for key in (p["src"], p["dst"]):
            if not AC.law_key_allowed(k, key) and not estate_access(k, str(p["why"])[4:], key):
                raise L.LawError(f"no such agent: {key}")
    if isinstance(p["src"], str) and p["src"].startswith(AC.FUND):    # P4.4: only a fund's own law moves goods out of it
        AC.check_fund_move(k, p["src"], p["why"])
    if any(isinstance(x, str) and x.startswith(AC.STORE) for x in (p["src"], p["dst"])):   # review 15 S3: food stores
        AC.check_store_move(k, p["src"], p["dst"], p["item"], qty, p["why"])
    if not AC.can_pay(k, p["src"], p["item"], qty):
        raise PhysicsError("insufficient")
    if p.get("memo") is not None:                                    # W6a: a purpose memo (law.v2 only), a short string
        if not v2(k):
            raise L.LawError("a move's memo needs law.v2")
        return {**p, "qty": qty, "memo": memo_text(p["memo"])}
    return {**p, "qty": qty}


MEMO_MAX = 80                                                        # W6a: a memo's length cap (characters)


def memo_text(memo) -> str | None:
    """W6a: a move's purpose memo as stored and shown: a string, stripped, at most MEMO_MAX characters (None or empty: no memo)."""
    if memo is None:
        return None
    t = " ".join(str(memo).split())[:MEMO_MAX]
    return t or None


def check_create_currency(k, p):
    name = str(p["name"])
    if name in k.w["currencies"] or name in k.w["unit"]:
        raise L.LawError(f"{name} already exists")
    return {**p, "name": name}


def check_mint(k, p):
    if k.w["currencies"].get(p["currency"]) is None:
        raise L.LawError(f"no such currency: {p['currency']}")
    qty = float(p["qty"])
    if qty < 0:
        raise L.LawError("cannot mint a negative amount")
    return {**p, "qty": qty}


def check_burn(k, p):
    c = k.w["currencies"].get(p["currency"])
    if c is None or k.bal(p["frm"], p["currency"]) + 1e-9 < float(p["qty"]):
        raise PhysicsError("insufficient")
    return {**p, "qty": float(p["qty"])}


def _nonneg(p, key="qty"):
    try:
        q = float(p[key])
    except (TypeError, ValueError):
        raise L.LawError(f"{key} must be a number")
    if q < 0 or q != q:
        raise L.LawError(f"{key} must be non-negative")
    return {**p, key: q}


def check_convert(k, p):
    p = _nonneg(p)
    if p["qty"] == 0:
        raise _Noop({"converted": 0.0})
    if k.bal(p["agent"], p["src_item"]) + 1e-9 < p["qty"]:
        raise PhysicsError("insufficient")
    return p


def check_destroy(k, p):
    qty = float(p["qty"])
    if qty < 0 or qty != qty:
        raise L.LawError("quantity must be non-negative")
    if qty == 0:
        raise _Noop({"destroyed": 0.0})
    if k.bal(p["owner"], p["item"]) + 1e-9 < qty:
        raise PhysicsError("insufficient")
    return {**p, "qty": qty}


def check_contribute(k, p):
    if str(p["project"]) not in k.w["projects"]:
        raise L.LawError(f"no project {p['project']}")
    qty = float(p["qty"])
    if not qty > 0:
        raise L.LawError("qty must be positive")
    if k.bal(p["agent"], p["item"]) + 1e-9 < qty:
        raise PhysicsError("insufficient")
    return {**p, "project": str(p["project"]), "qty": qty}


# ---------------------------------------------------------------------- rights and sanctions (changes.status)
def check_grant_right(k, p, via="law"):
    right = k.norm_right(p["right"])
    a = k.agent(p["agent"])
    if right in RT.ENTRENCHED or (RT.role_bound(right) and via != "role"):   # a role's right changes only with the role (secret
        raise PhysicsError(f"grant {right}")                         # or not: refused whoever the agent is, so nothing leaks)
    if right not in k.w["rights"]:
        raise L.LawError(f"no such right: {right}")
    never = RT.NEVER.get(a["cls"], set())
    if (never is None) or (right in never) or (a["cls"] == "fixer" and right.startswith("harvest:")):
        raise PhysicsError(f"grant {right} to {a['cls']} {p['agent']}")
    return {**p, "right": right}


def check_revoke_right(k, p, via="law"):
    right = k.norm_right(p["right"])
    k.agent(p["agent"])
    if right in RT.ENTRENCHED or (RT.role_bound(right) and via != "role"):
        raise PhysicsError(f"revoke {right}")
    return {**p, "right": right}


def check_suspend_right(k, p):
    right = k.norm_right(p["right"])
    if right in RT.ENTRENCHED or RT.role_bound(right):
        raise PhysicsError(f"suspend {right}")
    return {**p, "right": right}


def check_limit_actions(k, p):
    cls = k.cls_of(p["agent"])
    if cls in ("board", "fixer"):
        raise PhysicsError(f"limit_actions on {cls}")
    return p


def check_create_right(k, p, via="law"):
    name = str(p["right"])
    if name in RT.ENTRENCHED:
        raise L.LawError("veto and patch are entrenched")
    if RT.reserved(name) and not (via == "role" and RT.role_bound(name)):  # the roles module adds its rights to the catalogue
        raise L.LawError(f"{name} is reserved: it belongs to a role or is an old name of one of its rights")
    return {**p, "right": name}


# ---------------------------------------------------------------------- speech (changes.speech)
def check_hide_post(k, p):
    eid = str(p["event"])
    if p["hide"]:
        e = next((x for x in k.events if x["id"] == eid), None)
        if e is None or e["type"] not in POSTABLE:
            raise L.LawError(f"{eid} is not a post")
    return {**p, "event": eid, "hide": bool(p["hide"])}


def check_set_dm_limit(k, p):
    if p["agent"] is not None:
        cls = k.cls_of(p["agent"])
        if cls in ("board", "fixer"):                               # the Board's and Fixer's messages cannot be limited
            raise PhysicsError(f"set_dm_limit on {cls}")
    return p


def check_dm(k, p):
    return {**p, "encrypted": bool(p["encrypted"]), "readable": bool(k.spec["conditions"].get("law_reads_dms"))}


# ---------------------------------------------------------------------- camps (changes.world)
def check_camp(k, p):
    """regrow, drift, set_camp_state and set_camp_rule: the camp exists."""
    if p["camp"] not in k.w["camps"]:
        raise L.LawError(f"no such camp: {p['camp']}")
    return p


check_set_camp_rule = check_camp                                      # W8a: one check (the two bodies were the same code)


def check_create_camp(k, p):
    if p["camp"] in k.w["camps"]:
        raise L.LawError(f"{p['camp']} already exists")
    return p


# ---------------------------------------------------------------------- life (changes.lifecycle)
def check_begin_life(k, p):
    if p["how"] not in LIFE_HOWS:
        raise L.LawError(f"how must be one of {LIFE_HOWS}, not {p['how']!r}")
    if p["agent"] in k.w["agents"]:
        raise PhysicsError(f"{p['agent']} already exists")
    return p


def check_end_life(k, p):
    from charter import mortality as MO
    if p["cause"] == "departure":                                     # today's events.depart: no check (the caller picks a player)
        return p
    v = k.w["agents"].get(p["agent"])
    if not v or v["cls"] in ("fixer", "observer") or v.get("departed") is not None:
        raise _Noop({"ended": False})
    if p["cause"] not in MO.CAUSES:
        raise ValueError(f"cause must be one of {LIFE_CAUSES}, not {p['cause']!r}")
    return p


# ---------------------------------------------------------------------- media (changes.press)
def check_set_outlet_rule(k, p):
    from charter import media as MD
    MD.check_outlet_rule(k, p["outlet"], p["key"])
    return p


# ---------------------------------------------------------------------- conflict (changes.force)
def check_attack(k, p):
    return {**_nonneg(p, "units"), "covert": bool(p["covert"]), "disguise": bool(p["disguise"]), "lawful": bool(p["lawful"])}


def check_fortify(k, p):
    return _nonneg(p)


# ---------------------------------------------------------------------- loans (changes.loans)
def check_settle_loan(k, p):
    from charter import credit as CR
    if str(p["loan"]) not in k.w["loans"]:
        raise L.LawError(f"no loan {p['loan']}")
    if p["how"] not in CR.SETTLE_HOWS:
        raise L.LawError(f"how must be one of {', '.join(CR.SETTLE_HOWS)}, not {p['how']!r}")
    paid = float(p["paid"] or 0.0)
    if paid < 0 or paid != paid:
        raise L.LawError("paid must be non-negative")
    return {**p, "loan": str(p["loan"]), "paid": paid}


# ---------------------------------------------------------------------- contracts and agency (changes.associations, changes.agency)
def check_pull(k, p):
    from charter import contracts as CT
    return CT.check_pull(k, p)


def check_deposit_escrow(k, p):
    from charter import contracts as CT
    return CT.check_deposit(k, p)


def check_set_allowance(k, p):
    from charter import contracts as CT
    return CT.check_allowance(k, p)


def check_swap(k, p):
    from charter import contracts as CT
    return CT.check_swap(k, p)


def check_authorize(k, p):
    from charter import contracts as CT
    return CT.check_authorize(k, p)


def check_act_for(k, p):
    from charter import contracts as CT
    return CT.check_act_for(k, p)


# ---------------------------------------------------------------------- the table (in the order the packages added them)
CHECK_OPTIONS = {"grant_right": ("via",), "revoke_right": ("via",), "create_right": ("via",)}   # call options a check reads

CHECKS = {
    "move": check_move, "grant_right": check_grant_right, "revoke_right": check_revoke_right,                     # P2.1
    "suspend_right": check_suspend_right, "limit_actions": check_limit_actions, "create_right": check_create_right,
    "create_currency": check_create_currency, "mint": check_mint, "burn": check_burn, "hide_post": check_hide_post,
    "set_camp_rule": check_camp, "set_dm_limit": check_set_dm_limit, "dm": check_dm,
    "begin_life": check_begin_life, "end_life": check_end_life,                                                     # P2.4b
    "regrow": check_camp, "drift": check_camp, "set_camp_state": check_camp, "destroy": check_destroy,              # P2.4c
    "create_camp": check_create_camp, "contribute": check_contribute,
    "set_outlet_rule": check_set_outlet_rule,                                                                       # P2.4d
    "attack": check_attack, "fortify": check_fortify, "convert": check_convert,                                     # P2.4a
    "settle_loan": check_settle_loan,                                                                               # loans
    "propose": check_propose,                                                                                       # P3.2 (law.v2)
    "pull": check_pull, "deposit_escrow": check_deposit_escrow, "set_allowance": check_set_allowance,             # P4.3
    "swap": check_swap,                                                                                             # P4.4
    "authorize": check_authorize, "act_for": check_act_for,                                                         # P4.5
}
