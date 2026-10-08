"""Amendment through the procedure, and proposals by law (P3.4; review 09 §7; ARCHITECTURE §6, D-16). law.v2 only: with it off
nothing here is reachable (the `amend` action is unknown, propose_law/propose_amendment are not law functions).

Agents  amend {law, code, reason}: a draft with `amends = law` goes through the `propose` primitive and the procedure, like any
        proposal (actions._amend).
Laws    propose_law(code, intent=None), propose_amendment(target, code, reason=""): from law level L3 (D-16), procedural
        (lawapi.PROCEDURAL). The draft's author is "law:<lid>", its jurisdiction the proposing law's. The result is returned to the
        law as data: {"ok": True, "law": "L9"} or {"ok": False, "reason": "...", ["law": "L9"]} (a refusal never raises, so it
        never suspends the proposing law or calls the Fixer). The checks and the `propose` primitive run in the call (a
        before_propose block comes back as the refusal); the procedure decides when the call's cascade has drained (Cascade.at_end),
        so a procedure never runs inside another law's call.

An amendment draft is an ordinary law record (its own id, e.g. L9) with
  amends        the target law id
  cls           max(cls(target now), cls(new code with its imports), every following dependent's class after relinking)
                (linker.amendment_class; review 09 §6.4): the procedure of the highest affected class decides
  rank          max(rank(target), the new code's declared rank): the integration point for rank-based procedures (P3.2 reads
                the record's rank; Kernel.decide passes it to the decide primitive)
  dependents    linker.preview_amend: what the amendment will do to each importer (unaffected, relinked, auto_pinned)
  amend_reason  the proposer's reason
Refused at proposal: a target not in force (or invisible), a charter-rank target, an amendment by a law of lower rank than its
target (lex superior) or of another jurisdiction, a repeal law as the new code, unchanged code, and an import cycle the new code
would close through the target's dependents (linker.check_graph with the new code as an override).
When the draft passes (directly, after a ballot, or after the Board's veto window: Kernel.pass_or_veto as for any proposal),
Kernel.enact applies the `amend` primitive to the TARGET with via="procedure" (enact_amendment): same id, same state, same public,
same place in the enactment order; the version history grows by one (via "procedure"); registered functions are re-bound;
dependents are relinked or auto-pinned (linker.on_amend). The draft's status becomes "enacted_amendment" (like "enacted_repeal").
A before_amend block strikes the amendment down (status "struck_down"); a new code that fails to load fails it.
"""
from __future__ import annotations

import difflib

from charter import dispatch as D
from charter import jurisdictions as J
from charter import lawlang as L
from charter import linker as LK
from charter import powers as PW

LawError = L.LawError

BY_LAW_LEVEL = "L3"                 # D-16: the lowest law level at which laws may propose laws or amendments
PER_LAW_PER_ROUND = 1               # law-originated proposals a law may make per round
PER_ROUND = 5                       # law-originated proposals per round in the whole world (a law proposing laws that propose laws)
IN_FORCE = ("active", "suspended")


def _rank_n(r) -> int:
    return D.RANKS.get(r, D.RANKS["statute"])


def declared_rank(code: str) -> str:
    r = L.static_info(L.check(code, v2=True)).get("rank")
    return r if isinstance(r, str) and r in D.RANKS else "statute"


def max_rank(*ranks) -> str:
    return max(ranks, key=_rank_n)


def max_cls(*classes) -> str:
    return max(classes, key=lambda c: L.CLASS_RANK.get(c, 0))


# ---------------------------------------------------------------------- the draft
def amendment_draft(k, target: str, code, author: str, reason="", by_law: str | None = None, intent=None) -> str:
    """Check an amendment of `target` to `code` and record its draft (a law record with `amends`); returns the draft's id.
    Raises LawError with the refusal. by_law: the proposing law (lex superior, same jurisdiction, visibility)."""
    target, code = str(target), str(code)
    tgt = k.w["laws"].get(target)
    if tgt is None or tgt.get("status") not in IN_FORCE or (by_law is not None and not LK._visible(k, by_law, target)):
        raise LawError(f"no law {target} in force to amend")
    if D.rank_of(k, target) == "charter":
        raise LawError(f"{target} has rank charter: no procedure can amend it")
    if by_law is not None:
        if _rank_n(D.rank_of(k, by_law)) < _rank_n(D.rank_of(k, target)):
            raise LawError(f"a {D.rank_of(k, by_law)} cannot amend {target}, a {D.rank_of(k, target)} (a law amends only laws of "
                           "rank at most its own)")
        if J.law_jur(k, by_law) != J.law_jur(k, target):
            raise LawError(f"{target} is a law of {J.law_jur(k, target)}; a law proposes amendments only in its own jurisdiction")
    tree = L.check(code, v2=True)
    L.check_hooks(tree, True, D.ROUTED)
    if L.is_repeal(tree):
        raise LawError("an amendment cannot be a repeal law: propose the repeal itself")
    if LK.sha(code) == tgt.get("code_sha", LK.sha(tgt["code"])):
        raise LawError(f"the new code is {target}'s current code")
    LK.check_graph(k, f"{target}@{LK.sha(code)}", code, overrides={target: code})   # a cycle closed through a dependent
    cls = max_cls(tgt["cls"], LK.amendment_class(k, target, code))
    rank = max_rank(D.rank_of(k, target), declared_rank(code))
    deps = LK.preview_amend(k, target, code)
    lid = k.new_law(code, author, intent_override=intent)
    law = k.w["laws"][lid]
    law.update({"amends": target, "cls": cls, "rank": rank, "amend_reason": str(reason or "")[:600], "dependents": deps})
    if "jurisdiction" in tgt:
        law["jurisdiction"] = tgt["jurisdiction"]
    return lid


def check_level(k, account, law) -> None:
    """The account's law level allows the draft's class (and define_action): else LawError (the record is marked failed_check)."""
    if not PW.level_allows(k, account, law["cls"]):
        law["status"] = "failed_check"
        raise LawError(f"{law['cls']} laws are not allowed at law level {PW.law_level(k, account)}")
    if law["defines_action"] and not PW.level_allows_define_action(k, account):
        law["status"] = "failed_check"
        raise LawError("define_action needs law level L4")


# ---------------------------------------------------------------------- enactment: the amend primitive, via procedure
def enact_amendment(k, lid, via=None) -> None:
    """Kernel.enact for a draft with `amends`: the amend primitive on the target (via "procedure"). Raises LawError when the target
    is no longer in force or the new code fails to load (callers record a failed proposal, as for an enactment)."""
    rec = k.w["laws"][lid]
    target = rec["amends"]
    tgt = k.w["laws"].get(target)
    if tgt is None or tgt.get("status") not in IN_FORCE:
        raise LawError(f"{target} is no longer in force")
    old = tgt["code"]
    diff = "".join(difflib.unified_diff(old.splitlines(True), rec["code"].splitlines(True), f"{target} (before)", f"{target} (after)"))
    patch = {"code": rec["code"], "reason": rec.get("amend_reason") or "", "diff": diff, "by": rec["author"], "cls": rec["cls"],
             "via": "procedure", "proposal": lid, "passed_via": via or D.via_of(k, "procedure")}
    out = k.apply("amend", jurisdiction=D.jur_of(k, target), law=target, old_sha=D.sha(old), new_sha=D.sha(rec["code"]),
                  diff=diff, via="procedure", by=rec["author"], patch=patch)
    if not out.ok:                                                     # a before_amend hook kept the old code (logged by on_block)
        rec["status"] = "struck_down"
        return
    if not (out.result or {}).get("ok", True):
        raise LawError((out.result or {}).get("error") or "the amended code failed to load")
    rec["status"] = "enacted_amendment"
    rec["enacted_round"] = k.r


# ---------------------------------------------------------------------- proposals by law
def _count(k, caller) -> str | None:
    """The per-round limits on law-originated proposals: a refusal, or None (and the proposal is counted)."""
    rec = k.w.get("law_proposals")
    if not rec or rec.get("round") != k.r:
        rec = k.w["law_proposals"] = {"round": k.r, "by": {}}
    if rec["by"].get(caller, 0) >= PER_LAW_PER_ROUND:
        return f"a law may make at most {PER_LAW_PER_ROUND} proposal per round"
    if sum(rec["by"].values()) >= PER_ROUND:
        return f"laws together may make at most {PER_ROUND} proposals per round"
    rec["by"][caller] = rec["by"].get(caller, 0) + 1
    return None


def _decide_later(k, lid) -> None:
    """The procedure decides a law-originated proposal once the proposing call's cascade has drained (or now, outside any)."""
    def run():
        law = k.w["laws"].get(lid)
        if law is None or law["status"] != "draft":
            return
        try:
            k.decide(lid)
        except D.Blocked as e:                                          # e.g. a before_open_ballot block of its ballot
            law["status"] = "failed"
            k.log("proposal_failed", law["author"], {"law": lid, "why": str(e)}, vis="public")

    cas = k.cascade()
    if cas is not None:
        cas.at_end(k, run)
    else:
        run()


def propose_by_law(k, caller: str, code, intent=None, target: str | None = None, reason="") -> dict:
    """propose_law / propose_amendment for law `caller`: {"ok": True, "law": lid[, "amends": target]} or {"ok": False, "reason"}."""
    account = J.law_jur(k, caller)
    level = PW.law_level(k, account)
    if PW.LEVELS.index(level) < PW.LEVELS.index(BY_LAW_LEVEL):
        return {"ok": False, "reason": f"laws may propose laws only at law level {BY_LAW_LEVEL} or higher (here: {level})"}
    if not isinstance(code, str) or not code.strip():
        return {"ok": False, "reason": "the code must be a law's complete source, as a string"}
    if intent is not None and not isinstance(intent, str):
        return {"ok": False, "reason": "intent must be a string"}
    author = f"law:{caller}"
    lid = None
    try:
        if target is not None:
            lid = amendment_draft(k, str(target), code, author, reason, by_law=caller)
        else:
            lid = _law_draft(k, caller, code, author, intent)
        check_level(k, account, k.w["laws"][lid])
    except LawError as e:
        if lid is not None and k.w["laws"][lid]["status"] == "draft":
            k.w["laws"][lid]["status"] = "failed_check"
        return {"ok": False, "reason": str(e), **({"law": lid} if lid else {})}
    why = _count(k, caller)
    if why:
        k.w["laws"][lid]["status"] = "failed_check"
        return {"ok": False, "law": lid, "reason": why}
    try:
        k.apply("propose", jurisdiction=D.jur_of(k, lid), draft=D.draft(k, lid), actor=None, preview=None)
    except D.Blocked as e:                                              # a before_propose block: logged as proposal_blocked
        return {"ok": False, "law": lid, "reason": str(e)}
    if not k.dry:                                                       # a preview of the proposing law proposes nothing further
        _decide_later(k, lid)
    return {"ok": True, "law": lid, **({"amends": str(target)} if target is not None else {})}


def _law_draft(k, caller, code, author, intent) -> str:
    lid = k.new_law(code, author, intent_override=intent)
    law = k.w["laws"][lid]
    if "jurisdiction" in k.w["laws"][caller]:
        law["jurisdiction"] = k.w["laws"][caller]["jurisdiction"]
    if law["repeal_target"]:
        tgt = next((l for l in k.active_laws() if (l["id"] == law["repeal_target"] or l["title"].lower() == law["repeal_target"].lower())
                    and J.law_jur(k, l["id"]) == J.law_jur(k, caller)), None)
        if not tgt:
            law["status"] = "failed_check"
            raise LawError(f"no active law {law['repeal_target']!r} to repeal")
        if _rank_n(D.rank_of(k, caller)) < _rank_n(D.rank_of(k, tgt["id"])):
            law["status"] = "failed_check"
            raise LawError(f"a {D.rank_of(k, caller)} cannot propose the repeal of {tgt['id']}, a {D.rank_of(k, tgt['id'])}")
        law["cls"] = tgt["cls"]
    return lid


NAMES = ("propose_law", "propose_amendment")


def law_api(k, lid) -> dict:
    """The law functions (lawapi rows, module "amendment"; law.v2 only: Kernel.api_for adds them)."""
    def propose_law(code, intent=None):
        return propose_by_law(k, lid, code, intent=intent)

    def propose_amendment(target, code, reason=""):
        return propose_by_law(k, lid, code, target=str(target), reason=reason)

    return {"propose_law": propose_law, "propose_amendment": propose_amendment}
