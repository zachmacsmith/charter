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
    """law.v2 (P3.2): no draft may have rank charter; a draft may repeal or amend only laws of rank <= its own (lex superior); W9: a
    draft whose declared rank is below what it does needs (requirement, the draft's "requires") is refused."""
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
    req = d.get("requires")                                           # W9: what the draft does needs a higher rank
    if why is None and req and req.get("rank") and RANKS[rank] < RANKS[req["rank"]]:
        why = requirement_text(req, rank)
    if why is None:
        return p
    k.w["laws"][d["id"]]["status"] = "blocked"
    k.log("proposal_blocked", None, {"law": d["id"], "by": [], "reason": why}, vis="public")
    raise RankRefused("propose", why)


CLASSES = ("ordinary", "structural", "procedural")


# ---------------------------------------------------------------------- what a draft does (W9: the usurpers' constitution loophole)
# A law's class is read from the functions it names (lawlang.classify) and its rank from what it declares; neither saw that a law
# can change who decides. In the usurpers run an ordinary-class "seat table" replaced the council and a procedural law then repealed
# the constitution, past the procedural threshold and the Board. requirement() reads what the draft does (statically, and on a copy
# of the world: Kernel.trial) and names the class and rank that needs:
#   - it sets a procedure (set_procedure)                                        -> procedural
#   - it grants, revokes or suspends a right the procedures in force read
#     (the electorate and the root's seats: vote, decree, a council right, ...)   -> procedural
#   - it repeals (or tries to) a procedural or constitution-rank law              -> procedural, and that law's rank if higher
# law.v2 worlds only (where ranks and the pilots live; a v1 world's classes and goldens stay as they were: there only the
# classifier's own fix applies, lawlang.api_used). A draft's class is raised to the requirement at proposal (actions._propose,
# jurisdictions.propose, actions._amend): the class is computed, never declared, so raising it is what makes the procedure,
# threshold and Board review of that class apply. Its rank is declared, so a draft whose declared rank is below the requirement is
# refused at proposal (check_propose) with a message naming the class and rank it needs.
GOVERNING = ("vote",)                                                     # always: the electorate of every built-in constitution
_TRIGGERS = {"grant", "revoke", "suspend", "revoke_capability", "set_procedure", "repeal", "open_ballot", "use"}


def governing_rights(k) -> set:
    """Rights that decide: "vote", and every right the laws that set the procedures in force read by name (holders("X"),
    has(a, "X")): a council's or a ruler's seat."""
    import ast
    out = set(GOVERNING)
    tables = [k.w.get("procedures") or {}]
    if "jur" in k.w:
        tables += [j.get("procedures") or {} for j in J.jurs(k).values()]
    lids = {str(key).split("#")[0] for t in tables for key in t.values() if key}
    for lid in lids:
        code = (k.w["laws"].get(lid) or {}).get("code")
        try:
            tree = ast.parse(code or "")
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("holders", "has"):
                arg = n.args[0] if n.func.id == "holders" and n.args else (n.args[1] if len(n.args) > 1 else None)
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    out.add(arg.value)
    return out


def requirement(k, lid) -> dict | None:
    """What draft `lid` does that needs a stricter class or rank than it has: {"cls", "rank", "why"} (rank None: no rank needed,
    or law.v2 off), or None. Static (constant rights and repeal targets) and dynamic (Kernel.trial, run only when the draft names a
    function that can do any of it, or imports)."""
    import ast
    if not v2(k):                                                     # law.v2 worlds (ranks, Board review per rank); v1 as before
        return None
    law = k.w["laws"][lid]
    try:
        tree = ast.parse(law["code"])
    except SyntaxError:
        return None
    used = L.api_used(tree)
    if not (used & _TRIGGERS):
        return None
    gov = governing_rights(k)
    need, rank, why = "ordinary", None, []

    def want(cls, reason, r=None):
        nonlocal need, rank
        if L.CLASS_RANK[cls] > L.CLASS_RANK[need]:
            need = cls
        if r is not None and (rank is None or RANKS[r] > RANKS[rank]):
            rank = r
        if reason not in why:
            why.append(reason)

    def repeal_target(t):
        if t.get("id") == lid:
            return
        tr = rank_of(k, t["id"])
        high = RANKS[tr] >= RANKS["constitution"]
        if t.get("cls") == "procedural" or high:
            want("procedural", f"repeals {t['id']} '{t['title']}', a {t.get('cls')} law of rank {tr}",
                 tr if high else None)

    for n in ast.walk(tree):                                          # static: constant rights and repeal targets
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.args:
            f = n.func.id
            if f in ("grant", "revoke", "suspend", "revoke_capability") and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant) \
                    and n.args[1].value in gov:
                want("procedural", f"{f}s the right {n.args[1].value!r}, which decides who passes laws")
            elif f == "repeal" and isinstance(n.args[0], ast.Constant):
                for t in _targets(k, n.args[0].value):
                    repeal_target(t)
    for prim, p in k.trial(lid):                                      # dynamic: what it did on a copy of the world
        if prim == "set_procedure":
            want("procedural", f"sets the procedure for {p.get('cls')} laws")
        elif prim in ("grant_right", "revoke_right", "suspend_right") and p.get("right") in gov:
            want("procedural", f"{prim.split('_')[0]}s the right {p['right']!r}, which decides who passes laws")
        elif prim == "repeal_attempt":
            t = k.w["laws"].get(p["law"])
            if t:
                repeal_target(t)
    if L.CLASS_RANK[need] <= L.CLASS_RANK.get(law["cls"], 0) and (rank is None or RANKS[rank] <= RANKS[rank_of(k, lid)]):
        return None
    return {"cls": max(need, law["cls"], key=L.CLASS_RANK.get), "rank": rank, "why": why}


def apply_requirement(k, lid) -> dict | None:
    """At proposal: raise the draft's class to what it does (requirement) and record it on the law record ("requires"), so the
    procedure, threshold and Board review of that class apply; check_propose refuses a declared rank below it (law.v2)."""
    req = requirement(k, lid)
    if req is None:
        return None
    law = k.w["laws"][lid]
    req["from"] = law["cls"]
    law["cls"] = req["cls"]
    law["requires"] = req
    return req


def requirement_note(law) -> str:
    """The proposer's note on a class raised at proposal ("" otherwise)."""
    req = law.get("requires")
    return f", not {req['from']}, because it {'; '.join(req['why'])}" if req and req["from"] != req["cls"] else ""


def requirement_text(req, have_rank=None) -> str:
    return (f"this law {'; '.join(req['why'])}: it must be a {req['cls']} law"
            + (f" of rank {req['rank']} or higher (it declares {have_rank}; add rank = \"{req['rank']}\")" if req.get("rank") else ""))


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
