"""Declared temporal validity (W6a; review 10 §4, roadmap #2; W7e window_note).

A law declares `in_force_from = R` / `in_force_until = R` (lawlang.check_window). Under law.v2, outside [from, until] (inclusive) the
dispatcher skips its change hooks (new-style before_/after_: hooks.bound_laws; old ones: Kernel.hooks, jurisdictions.hooks/hooks_of)
and its clock hooks (on_round_start/end), and its offices refuse (actions._invoke); its lifecycle hooks (on_enact, on_repeal) still
run, its exports still link and its procedures, conflict rule and ballots stand. At the end of round `until` (Kernel's round_end
step expire_cases) the kernel repeals it: a routed repeal with via "expired" in a {"kernel": "expiry"} root frame, so before_repeal
may keep it in force (it then stays out of force; the kernel tries again each round) and after_repeal sees it; the repeal event says
via "expired". Associations' laws (P4.3) end only by their own procedure and never expire. Off: every law is in force."""
from __future__ import annotations

import functools as _functools

from charter import jurisdictions as J
from charter import lawlang as L

from charter.dispatch.base import v2
from charter.dispatch.changes.legal import jur_of


@_functools.lru_cache(maxsize=4096)
def code_window(code: str) -> tuple:
    import ast
    try:
        return L.window(ast.parse(code))
    except SyntaxError:
        return (None, None)


def window_of(k, lid) -> tuple:
    """W6a: (in_force_from, in_force_until) of a law's current code (None: open on that side)."""
    code = (k.w["laws"].get(lid) or {}).get("code")
    return code_window(code) if isinstance(code, str) and "in_force_" in code else (None, None)


def window_note(k, lid) -> str:
    """W7e: a law's declared window for agents' text (law list, read_law, previews): "" when it declares none or law.v2 is off, else
    e.g. " [in force while round() is 3-9; out of force now]". The numbers are the law's own (round(), in_force_*), which an
    agent's "Round N" header shows as N = round() + 1."""
    if not v2(k):
        return ""
    lo, hi = window_of(k, lid)
    return window_text(lo, hi, in_force(k, lid))


def window_text(lo, hi, now=True) -> str:
    if lo is None and hi is None:
        return ""
    span = f"is {lo}-{hi}" if lo is not None and hi is not None else (f">= {lo}" if lo is not None else f"<= {hi}")
    return f" [in force while round() {span}{'' if now else '; out of force now'}]"


def in_force(k, lid) -> bool:
    """W6a: is the law inside its declared window this round? Always True without law.v2."""
    if not v2(k):
        return True
    lo, hi = window_of(k, lid)
    return (lo is None or k.r >= lo) and (hi is None or k.r <= hi)


def expire_laws(k) -> list:
    """W6a: at the end of a round, repeal (via "expired") every law in force whose in_force_until is this round or earlier. Returns
    the ids repealed."""
    if not v2(k) or k.dry:
        return []
    from charter import linker as LK
    done = []
    for law in list(k.active_laws()):
        hi = window_of(k, law["id"])[1]
        if hi is None or k.r < hi or law["status"] != "active":
            continue
        if "contracts" in k.w and J.association(k, J.law_jur(k, law["id"])) is not None:
            continue
        with k.cause("kernel", "expiry", root=True):
            out = k.apply("repeal", jurisdiction=jur_of(k, law["id"]), law=law["id"], by_law=None, via="expired")
            if out.ok:
                done.append(law["id"])
                if LK.enabled(k):                                      # as Kernel.repeal: following importers auto-pin (D-8)
                    LK.on_repeal(k, law["id"])
    return done
