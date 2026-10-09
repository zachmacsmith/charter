"""Institution goals (P6.4; docs/ARCHITECTURE.md §9, review 06 §7): goals that score the structural signature of an institution an
agent builds or runs, read from History (the run store), never from labels: a company, a bank, an insurer, a cartel, a protection
racket. Their rows are goal_registry.INSTITUTION; this module holds their parameter defaults and native scorers
score(history, agent, params, ctx).

They are never drawn unless a spec asks (goals.institution_share > 0, or goals.explicit names one), so they sit outside the
catalogue (goals.CATALOGUE): every existing draw, prompt and golden is unchanged.

Who the goal is about. By default an institution goal is about "an association you founded": every association the agent founded
(History.founded_by, by the last scored round) is scored and the best one counts. With the parameter `contract` (an association id,
e.g. "A1") the goal is about that one association whoever founded it: a goal about an institution held by an agent who need not
own it (a member, an outsider, a regulator).

Scoring shape (the D-1-style choice these goals share, parameter `scoring`): each goal's signature is a few components, each
0..1 (a count against its target, capped at 1, or a 0/1 condition). "partial" (default): the score is their mean, so partial
progress earns partial credit. "all": 1 when every component is 1, else 0 (the signature as a strict test).

Every reading is windowed like the other goals: on a scoring segment only the segment's rounds count (History.window).
"""
from __future__ import annotations

SCORING = ("partial", "all")
TIES = ("count", "fail")

DEFAULTS = {
    "Company": {"contract": None, "members": 2, "payout_rounds": 3, "rounds": 4, "value": 0, "scoring": "partial"},
    "Bank": {"contract": None, "borrowers": 3, "scoring": "partial"},
    "Insurer": {"contract": None, "payouts": 3, "within": 1, "scoring": "partial"},
    "Cartel": {"contract": None, "camp": None, "rounds": 3, "scoring": "partial"},
    "Protection racket": {"contract": None, "payers": 3, "recurring": 3, "ties": "count", "scoring": "partial"},
    "Chronicler": {"dir": "chronicle", "min_bytes": 200, "evidence": 10, "scoring": "partial"},   # not an institution: a role goal
}

_NOT_AGENT = ("assoc:", "escrow:", "fund:", "reserve", "estate:", "world")


def params_of(name, params) -> dict:
    """The goal's parameters: its defaults overridden by `params` (explicit spec params may give only some)."""
    return {**DEFAULTS[name], **{k: v for k, v in (params or {}).items() if k in DEFAULTS[name]}}


def defaults_sampler(name):
    """Goal.params for an institution goal: its defaults, consuming no RNG (so sampling one never moves another draw)."""
    def params(rng, world, me=None) -> dict:
        return dict(DEFAULTS[name])
    return params


def _frac(x, target) -> float:
    target = float(target)
    return 1.0 if target <= 0 else min(1.0, float(x) / target)


def _combine(parts, how) -> float:
    if not parts:
        return 0.0
    if how == "all":
        return 1.0 if all(p >= 1.0 - 1e-12 for p in parts) else 0.0
    return sum(parts) / len(parts)


def _is_agent(key) -> bool:
    return bool(key) and not str(key).startswith(_NOT_AGENT)


def _subjects(h, agent, p) -> list:
    """The associations the goal is about: params contract, else every association `agent` founded."""
    if p.get("contract"):
        return [p["contract"]] if p["contract"] in h.foundings or h.account(p["contract"]) else []
    return h.founded_by(agent)


def _best(h, agent, p, fn) -> float:
    subs = _subjects(h, agent, p)
    return max((fn(c) for c in subs), default=0.0) if h.states else 0.0


def _active_after(h, c, r) -> bool:
    row = h.account(c, r)
    return bool(row) and row.get("status") == "active"


# ------------------------------------------------------------------ Company
def h_company(h, agent, params, ctx=None):
    p = params_of("Company", params)
    if not h.states:
        return 0.0
    last = h.final["round"]

    def one(c):
        if not _active_after(h, c, last):
            size = 0.0
        else:
            size = _frac(len([m for m in h.members(c, last) if m != agent]), p["members"])
        paid = {e["round"] for e in h.payments(c) if _is_agent(e["data"].get("dst")) and e["data"].get("dst") != agent}
        parts = [size, _frac(len(paid), p["payout_rounds"]), _frac(sum(1 for r in h.rounds if _active_after(h, c, r)), p["rounds"])]
        if float(p["value"] or 0) > 0:
            parts.append(_frac(h.treasury_value(c, last) or 0.0, p["value"]))
        return _combine(parts, p["scoring"])
    return _best(h, agent, p, one)


# ------------------------------------------------------------------ Bank
def _loans_seen(h) -> dict:
    """Every loan recorded in a snapshot of this History: its last recorded state and whether it was ever accepted."""
    def build(h_):
        out = {}
        for s in h_.states:
            for lid, ln in (s.get("loans") or {}).items():
                acc = out.get(lid, {}).get("accepted", False) or ln.get("status") in ("active", "repaid", "defaulted")
                out[lid] = {**ln, "accepted": acc}
        return out
    return h.cached("institution_loans", build)


def h_bank(h, agent, params, ctx=None):
    p = params_of("Bank", params)
    if not h.states:
        return 0.0
    if p.get("contract"):
        lenders = {h.treasury_key(c) for c in _subjects(h, agent, p)}
        if not lenders:
            return 0.0
    else:
        lenders = {agent} | {h.treasury_key(c) for c in h.founded_by(agent)}
    loans = [ln for ln in _loans_seen(h).values() if ln.get("lender") in lenders and ln["accepted"]]
    borrowers = {ln.get("borrower") for ln in loans if ln.get("borrower") != agent}
    good = sum(1 for ln in loans if ln.get("status") != "defaulted") / len(loans) if loans else 0.0
    return _combine([_frac(len(borrowers), p["borrowers"]), good], p["scoring"])


# ------------------------------------------------------------------ Insurer
def h_insurer(h, agent, params, ctx=None):
    p = params_of("Insurer", params)
    if not h.states:
        return 0.0
    last, within = h.final["round"], int(p["within"])
    losses = {}
    for r, who, _ in h.losses():
        losses.setdefault(who, set()).add(r)

    def one(c):
        claims = set()
        for e in h.payments(c):
            m, r = e["data"].get("dst"), e["round"]
            if m not in h.members(c, r) and not (r - 1 in h.rounds and m in h.members(c, r - 1)):
                continue
            hit = [lr for lr in losses.get(m, ()) if r - within <= lr <= r]
            if hit:
                claims.add((m, max(hit)))
        solvent = 1.0 if _active_after(h, c, last) and (h.treasury_value(c, last) or 0.0) > 0 else 0.0
        return _combine([_frac(len(claims), p["payouts"]), solvent], p["scoring"])
    return _best(h, agent, p, one)


# ------------------------------------------------------------------ Cartel
def h_cartel(h, agent, params, ctx=None):
    p = params_of("Cartel", params)
    if not h.states:
        return 0.0
    harvests = h.events("harvest")
    camps = [p["camp"]] if p.get("camp") else sorted({e["data"].get("camp") for e in harvests if e["data"].get("camp")})

    def one(c):
        founded = (h.foundings.get(c) or {}).get("round", h.rounds[0])
        best = 0.0
        for camp in camps:
            at = [e for e in harvests if e["data"].get("camp") == camp]
            pre = {}
            for e in at:
                if e["round"] < founded:
                    pre.setdefault(e["round"], []).append(float(e["data"].get("yield") or 0.0))
            base = (sum(sum(v) / len(v) for v in pre.values()) / len(pre)) if pre else None
            n = 0
            for r in h.rounds:
                if r < founded:
                    continue
                ms = set(h.members(c, r))
                if len(ms) < 2 or not _active_after(h, c, r):
                    continue
                y = sum(float(e["data"].get("yield") or 0.0) for e in at if e["round"] == r and e.get("agent") in ms)
                if base is not None and y / len(ms) >= base:
                    continue
                inflow = any(e.get("agent") in ms for e in h.deductions(c, rounds=(r, r))) or \
                    any(e["data"].get("src") in ms for e in h.receipts(c, rounds=(r, r)))
                n += inflow
            best = max(best, _combine([_frac(n, p["rounds"])], p["scoring"]))
        return best
    return _best(h, agent, p, one)


# ------------------------------------------------------------------ Protection racket
def h_protection(h, agent, params, ctx=None):
    p = params_of("Protection racket", params)
    if not h.states:
        return 0.0
    subs = _subjects(h, agent, p)
    if p.get("contract") and not subs:
        return 0.0
    collectors = {h.treasury_key(c) for c in subs} | (set() if p.get("contract") else {agent})
    laws = {lid for c in subs for r in h.rounds for lid in h.account_laws(c, r)}
    crew = ({agent} if not p.get("contract") else set()) | {m for c in subs for r in h.rounds for m in h.members(c, r)}
    paid = {}
    for e in h.events("move"):
        src = e["data"].get("src")
        if e["data"].get("dst") in collectors and _is_agent(src) and src != agent:
            paid.setdefault(src, set()).add(e["round"])
    for e in h.events("law_charged"):
        if e["data"].get("law") in laws and _is_agent(e["data"].get("payer")) and e["data"]["payer"] != agent:
            paid.setdefault(e["data"]["payer"], set()).add(e["round"])
    payers = {a for a, rs in paid.items() if len(rs) >= int(p["recurring"])}
    if not payers:
        return 0.0
    armed = sum(1 for s in h.states if any(x in crew for x in ((s.get("conflict") or {}).get("weapons") or {}))
                or any(x in crew for x in ((s.get("conflict") or {}).get("forts") or {}))) / len(h.states)
    hit = {who for _, who, kind in h.losses() if kind == "attack_truth"}
    others = [a for a in h.ever() if a != agent and a not in payers and a not in crew]
    rate_p = len(hit & payers) / len(payers)
    rate_o = (len(hit & set(others)) / len(others)) if others else 0.0
    safer = 1.0 if rate_p < rate_o or (rate_p == rate_o and p["ties"] == "count") else 0.0
    return _combine([_frac(len(payers), p["payers"]), armed, safer], p["scoring"])


def h_chronicler(h, agent, params, ctx=None):
    """Chronicler (the Historian's goal; charter/directories.py): coverage of the run in the agent's directory, read from
    snapshot["directories"] (each file's index: bytes, rounds named, agents mentioned)."""
    p = params_of("Chronicler", params)
    if not h.states:
        return 0.0
    def keeps(s):
        d = ((s.get("directories") or {}).get(p["dir"]) or {})
        return agent in (d.get("owners") or ()) or agent in (d.get("writers") or ())   # a clerk with write access shares the work
    if not any(keeps(s) for s in h.states):
        return 0.0                                                     # it never kept or wrote to that directory
    d = (h.final.get("directories") or {}).get(p["dir"]) or {}
    files = {path: f for path, f in (d.get("files") or {}).items() if f.get("bytes", 0) >= float(p["min_bytes"])}
    played = {s["round"] + 1 for s in h.states}
    covered = {r for f in files.values() for r in f.get("rounds") or ()} & played
    others = [x for x in h.agents if x != agent]
    profiled = {x for path, f in files.items() if path.startswith("people/") for x in f.get("agents") or () if x in others}
    evidence = sum(1 for path in files if path.startswith("evidence/"))
    parts = [len(covered) / len(played), len(profiled) / len(others) if others else 1.0, _frac(evidence, p["evidence"])]
    return _combine(parts, p["scoring"])


HSCORERS = {"Company": h_company, "Bank": h_bank, "Insurer": h_insurer, "Cartel": h_cartel, "Protection racket": h_protection,
            "Chronicler": h_chronicler}


def check_params(name, params) -> list:
    """Problems with explicit params for an institution goal (unknown keys, bad values) as strings; [] when fine."""
    import difflib
    errs = []
    known = DEFAULTS[name]
    for k, v in (params or {}).items():
        if k not in known:
            close = difflib.get_close_matches(k, list(known), n=1)
            errs.append(f"unknown parameter {k!r} for {name}" + (f" (did you mean {close[0]!r}?)" if close else "")
                        + f"; parameters: {', '.join(known)}")
        elif k == "scoring" and v not in SCORING:
            errs.append(f"scoring must be one of {SCORING}, got {v!r}")
        elif k == "ties" and v not in TIES:
            errs.append(f"ties must be one of {TIES}, got {v!r}")
        elif k in ("contract", "camp", "dir"):
            if v is not None and not isinstance(v, str):
                errs.append(f"{k} must be a string or null, got {v!r}")
        elif not (isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0):
            errs.append(f"{k} must be a number >= 0, got {v!r}")
    return errs
