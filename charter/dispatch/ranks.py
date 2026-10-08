"""Rank, lex superior, procedures per rank and conflict rules (P3.2; review 09 §8, D-13).

Ranks (lawlang.RANKS): charter (reserved) > constitution > statute > regulation > bylaw. A law declares `rank = "..."` as a top-level
constant (lawlang.check_rank; default statute). Under law.v2 the rank is recorded on the law record when it is proposed (from the
draft payload, changes.legal.do_propose) or, for a law enacted without a proposal (start laws, interventions), when it is enacted.
Without law.v2 nothing is recorded and every law is a statute (law_rank), so procedure lookups and repeals are exactly as before.
  - Lex superior (may_change): a law or draft may repeal or amend only laws of rank <= its own. A draft that repeals (or, P3.4,
    amends) a higher-rank law is refused at proposal (check_propose: status blocked, proposal_blocked logged, Blocked to its cause);
    a law-caused repeal of a higher-rank law does nothing (Kernel.repeal returns False). Rank charter can never be proposed.
  - Procedures per rank (procedure_lookup): set_procedure(cls, fn, rank=R) stores "<R>:<cls>"; only a law of rank >= R may set it.
  - Conflict rules (hooks.resolve_v2): any_block (default, D-13), superior, posterior, specialis (W6a) or a constitution's function.
    The set_conflict_rule primitive's change (do_set_conflict_rule) lives here with its helpers."""
from __future__ import annotations

from charter import jurisdictions as J
from charter import lawlang as L

from charter.dispatch.base import Blocked, PhysicsError, RANKS, v2


# ---------------------------------------------------------------------- rank, lex superior, procedures per rank (review 09 §8)
def declared_rank(code) -> str:
    """The rank a law's code declares at the top level, else statute."""
    import ast
    try:
        r = L.declared(ast.parse(code), "rank")
    except SyntaxError:
        return "statute"
    return r if isinstance(r, str) and r in RANKS else "statute"


def rank_of(k, lid) -> str:
    """A law's rank: its record's (recorded at proposal or enactment under law.v2), else (law.v2) the rank its code declares, else
    statute."""
    law = k.w["laws"].get(lid) or {}
    r = law.get("rank") or (declared_rank(law["code"]) if v2(k) and law.get("code") else None)
    return r if isinstance(r, str) and r in RANKS else "statute"


def law_rank(k, lid) -> str:
    """The rank the kernel acts on: rank_of under law.v2, else statute (v2 off: no ranks, nothing changes)."""
    return rank_of(k, lid) if v2(k) else "statute"


def may_change(k, by_rank: str, target: str) -> bool:
    """Lex superior (§8.1): something of rank `by_rank` may repeal, amend or override law `target` only if the target's rank is <= it."""
    return RANKS.get(by_rank or "statute", 2) >= RANKS[rank_of(k, target)]


def _targets(k, ref) -> list:
    return [l for l in k.active_laws() if l["id"] == ref or l["title"].lower() == str(ref).lower()]


class RankRefused(Blocked):
    """A proposal the rank physics refuses (P3.2): a draft of rank charter, or one repealing or amending a higher-rank law. A Blocked
    (by no law), so its cause sees what it sees for a law's block: an agent's action fails, a law's call ends."""
    def __init__(self, primitive: str, reason: str):
        PhysicsError.__init__(self, reason)
        self.primitive, self.by, self.why = primitive, (), reason


def check_propose(k, p):
    """law.v2 (P3.2): no draft may have rank charter; a draft may repeal or amend only laws of rank <= its own (lex superior)."""
    if not v2(k):
        return p
    d = p["draft"]
    rank = d.get("rank") or "statute"
    why = None
    if rank not in RANKS:
        why = f"unknown rank {rank!r}"
    elif rank == "charter":
        why = "rank charter is reserved: no procedure can enact, amend or repeal a charter-rank law"
    for key, verb in (("repeals", "repeal"), ("amends", "amend")):
        for t in (_targets(k, d[key]) if d.get(key) and why is None else []):
            if not may_change(k, rank, t["id"]):
                why = (f"a {rank} cannot {verb} {t['id']} '{t['title']}', a {rank_of(k, t['id'])} (lex superior): the draft must "
                       f"declare rank = \"{rank_of(k, t['id'])}\" and pass that rank's procedure")
                break
    if why is None:
        return p
    k.w["laws"][d["id"]]["status"] = "blocked"
    k.log("proposal_blocked", None, {"law": d["id"], "by": [], "reason": why}, vis="public")
    raise RankRefused("propose", why)


CLASSES = ("ordinary", "structural", "procedural")


def procedure_lookup(table: dict, cls: str, rank: str | None):
    """The key of the procedure that decides a draft of class `cls` and rank `rank` (§8.1, P3.2): table["<rank>:<cls>"]; for a
    constitution- or charter-rank draft also the procedures its rank has for stricter classes ("constitution:procedural" covers every
    constitutional draft unless one is set for its own class: a constitution changes only by its rank's procedures once it sets one);
    then table[cls]; then, for rank >= constitution, table["procedural"]. With rank statute and no "<rank>:" keys (always, without
    law.v2) this is table.get(cls), as before."""
    rank = rank if rank in RANKS else "statute"
    high = RANKS[rank] >= RANKS["constitution"]
    own = CLASSES[CLASSES.index(cls):] if high and cls in CLASSES else (cls,)
    for key in [f"{rank}:{c}" for c in own] + [cls] + (["procedural"] if high else []):
        if table.get(key):
            return table[key]
    return None


def check_procedure_rank(k, lid, rank) -> None:
    """set_procedure(cls, fn, rank=R): law.v2 only; R a known rank other than charter; the setting law's rank >= R. Raises LawError."""
    if not v2(k):
        raise L.LawError("set_procedure's rank argument needs ranks (law.v2)")
    if rank not in RANKS or rank == "charter":
        raise L.LawError(f"rank must be one of {', '.join(r for r in RANKS if r != 'charter')}")
    if RANKS[rank_of(k, lid)] < RANKS[rank]:
        raise L.LawError(f"a {rank_of(k, lid)} cannot set the procedure for {rank} drafts (only a law of rank {rank} or higher)")


# ---------------------------------------------------------------------- conflict rules (review 09 §8.3, D-13)
# k.w["conflict_rules"]: {polity: {"rule": any_block|superior|posterior|function, "law": lid, "key": fnreg key (function)}}, created on
# first use (worlds that never set one never have it). A rule holds while the law that set it is in force; otherwise any_block.
def _polity(k, lid) -> str:
    return (J.law_jur(k, lid) or "J0") if "jur" in k.w else "J0"


def _conflict_rule_arg(k, lid, rule):
    """Checks shared by the law API and a constitution's declaration: only a law of rank constitution or higher; a name of
    lawlang.CONFLICT_RULES or a function fn(verdicts) -> {"block": bool, "charges": [...]} (registered: the payload names its key)."""
    if RANKS[rank_of(k, lid)] < RANKS["constitution"]:
        raise L.LawError("only a constitution-rank law may set the conflict rule")
    if isinstance(rule, str) and rule in L.CONFLICT_RULES:
        return rule
    if callable(rule):
        return {"fn": k._reg(lid, rule)}
    raise L.LawError(f"the conflict rule is one of {', '.join(L.CONFLICT_RULES)} or a function fn(verdicts)")


def law_set_conflict_rule(k, lid, rule) -> None:
    """Law API set_conflict_rule(name_or_fn) (procedural): the set_conflict_rule primitive, routed (hookable, logged)."""
    k.apply("set_conflict_rule", jurisdiction=_polity(k, lid), rule=_conflict_rule_arg(k, lid, rule), law=lid)


def set_conflict_rule(k, lid, rule) -> None:
    """A constitution's declared `conflict_rule` at enactment (part of the enact act, so not a separate primitive)."""
    do_set_conflict_rule(k, _polity(k, lid), _conflict_rule_arg(k, lid, rule), lid, quiet=True)


def do_set_conflict_rule(k, jurisdiction, rule, law, quiet=False) -> None:
    """The set_conflict_rule primitive's change: rule is a CONFLICT_RULES name or {"fn": fnreg key}."""
    entry = {"rule": "function", "law": law, "key": rule["fn"]} if isinstance(rule, dict) else {"rule": rule, "law": law}
    k.w.setdefault("conflict_rules", {})[jurisdiction] = entry
    if not quiet:
        k.log("conflict_rule_set", None, {"jurisdiction": jurisdiction, "law": law, "rule": entry["rule"]}, vis="public")


def conflict_rule(k, polity) -> dict | None:
    """The polity's conflict rule in force (None: any_block)."""
    e = (k.w.get("conflict_rules") or {}).get(polity)
    if e and (k.w["laws"].get(e["law"]) or {}).get("status") == "active" and (e["rule"] != "function" or e.get("key") in k.fnreg):
        return e
    return None
