"""Legal acts (P2.3; review 09 §5): propose (payload draft = draft), decide, open_ballot, cast_vote, close_ballot, veto, enact,
repeal, amend (the Fixer's patch and, P3.4, an amendment by procedure), set_procedure, rule, define_action.

Routed exactly as before: the callers (actions._propose/_vote/_veto/_rule, jurisdictions.propose, the Kernel's decide, open_ballot,
close_ballots, enact, repeal, apply_patch, and the law API's set_procedure/define_action) keep their checks (ActionError/LawError) and
build the payload; the change below is the old code. Legacy aliases: on_proposal (None), on_vote and on_ruling after the act, from an
agent's action only; on_enact/on_repeal stay lifecycle hooks of the law itself (run inside do_enact/do_repeal). None of these
primitives has a CHECKS entry except propose under law.v2 (ranks.check_propose). set_conflict_rule's change is ranks'."""
from __future__ import annotations

from charter import code as DC
from charter import jurisdictions as J
from charter import lawlang as L
from charter import primitives as PR

from charter.dispatch.base import v2
from charter.dispatch.ranks import declared_rank, set_conflict_rule


# ---------------------------------------------------------------------- payload helpers (the callers build the payload with these)
def jur_of(k, lid) -> str | None:
    """A legal act's `jurisdiction`: the law's jurisdiction with jurisdictions on (J.law_jur), None when they are off."""
    return J.law_jur(k, lid) if "jur" in k.w else None


def via_of(k, default: str = "kernel") -> str:
    """How a lifecycle act happens when its caller does not say: inside an intervention, "intervention"; during setup (the
    constitution, regime statutes, start laws), "start"; else `default`."""
    frames = k.current_cause()
    if any("intervention" in f for f in frames):
        return "intervention"
    if any(f.get("phase") == "setup" for f in frames):
        return "start"
    return default


def sha(code) -> str:
    import hashlib
    return hashlib.sha256(str(code).encode()).hexdigest()[:12]


_RIGHT_CALLS = {"grant": "grant", "revoke": "revoke", "suspend": "suspend"}


def draft(k, lid) -> dict:
    """The `propose` payload's draft (review 09 §5): the record's fields plus static facts read from the AST, so a reviewing law
    never parses code. calls: the law-API functions it calls (sorted); hooks: the hooks it defines; rights: constant rights it
    grants, revokes or suspends; repeals: a repeal law's target. rank: the record's (an amendment's: max of its target's and its
    own, P3.4), else "statute" (P3.2). imports ([{alias, ref}]) and exports (names) from lawlang.static_info; amends: the law an
    amendment draft amends (None), and for one its reason and dependents (linker.preview_amend at proposal). W7e (law.v2):
    in_force_from / in_force_until, the draft's declared validity window (W6a; None: open on that side)."""
    import ast
    law = k.w["laws"][lid]
    tree = ast.parse(law["code"])
    info = L.static_info(tree)
    rights = {x: set() for x in _RIGHT_CALLS.values()}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _RIGHT_CALLS and len(n.args) >= 2 \
                and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
            rights[_RIGHT_CALLS[n.func.id]].add(n.args[1].value)
    hooks = sorted(n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in PR.HOOKS)
    return {"id": lid, "title": law["title"], "intent": law["intent"], "code": law["code"], "cls": law["cls"],
            "rank": law.get("rank") or (L.declared(tree, "rank") if v2(k) else None) or "statute", "author": law["author"], "calls": sorted(L.calls(tree) & L.API), "hooks": hooks,
            "rights": {x: sorted(v) for x, v in rights.items()}, "repeals": law["repeal_target"],
            **({"imports": info["imports"], "exports": info["exports"], "amends": law.get("amends"),               # law.v2 only
                "in_force_from": L.window(tree)[0], "in_force_until": L.window(tree)[1]} if v2(k) else {}),   # W7e: W6a's window
            **({"reason": law.get("amend_reason") or "", "dependents": [dict(x) for x in law.get("dependents") or ()]}
               if law.get("amends") else {}),
            **({"requires": dict(law["requires"])} if law.get("requires") else {})}   # W9: ranks.requirement


# ---------------------------------------------------------------------- duplicate proposals (law.v2: a signal, never a block)
_PENDING = ("active", "draft", "ballot", "gated", "veto_window")


def _norm_code(code) -> str | None:
    """A law's code without comments, formatting, title or intent (ast round trip), or None if it does not parse."""
    import ast
    try:
        tree = ast.parse(str(code))
    except SyntaxError:
        return None
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Assign) and len(n.targets) == 1
                                             and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("title", "intent"))]
    return ast.unparse(tree)


def similar_laws(k, lid, near=0.95) -> list:
    """law.v2: active or pending laws (same jurisdiction) whose normalised code is identical or near-identical to lid's:
    [{"law", "title", "status", "match": identical|near}]. The haiku runs enacted two identical Harvest Quotas in one round."""
    if not v2(k):
        return []
    import difflib
    law = k.w["laws"][lid]
    if law.get("amends") or law.get("repeal_target"):
        return []
    mine, jur = _norm_code(law["code"]), J.law_jur(k, lid)
    if not mine:
        return []
    out = []
    for oid, o in k.w["laws"].items():
        if oid == lid or o.get("status") not in _PENDING or J.law_jur(k, oid) != jur or o.get("amends"):
            continue
        theirs = _norm_code(o.get("code"))
        if not theirs:
            continue
        if theirs == mine:
            match = "identical"
        elif difflib.SequenceMatcher(None, mine, theirs, autojunk=False).ratio() >= near:
            match = "near"
        else:
            continue
        out.append({"law": oid, "title": o.get("title"), "status": o.get("status"), "match": match})
    return out


def similar_note(k, lid) -> str:
    """The proposal result's note on similar_laws (empty when none)."""
    sims = similar_laws(k, lid)
    if not sims:
        return ""
    return (" Note: " + "; ".join(f"{s['law']} '{s['title']}' ({s['status']}) has {'the same' if s['match'] == 'identical' else 'nearly the same'} code"
                                  for s in sims[:3]) + " (not blocked; if both are enacted, both run).")


# ---------------------------------------------------------------------- the changes
def do_propose(k, jurisdiction, draft, actor=None, preview=None) -> dict:
    """A checked draft goes to the procedure: the proposal is published with its dry-run preview (inline, or monitor-only when
    effect previews are off). The procedure runs next (Kernel.decide), after the on_proposal alias.
    The law record's "preview" stays None, as before P2.3: the callers used to set it on the record they held from before the dry
    run, which Kernel._restore had replaced, so it never reached the world (storing it changes ground_truth; a later fix)."""
    lid = draft["id"]
    law = k.w["laws"][lid]
    if v2(k):                                                          # P3.2: the rank is recorded at proposal, from the draft
        law["rank"] = draft["rank"]
    shown = k.spec["conditions"]["effect_preview"]
    extra = {}
    if law.get("amends"):                                              # P3.4: an amendment draft (agent amend, propose_amendment)
        extra.update({"amends": law["amends"], "rank": law.get("rank"), "reason": law.get("amend_reason") or ""})
    if str(law["author"]).startswith("law:"):                          # P3.4: proposed by a law; it has no dry run
        extra["by_law"] = law["author"][4:]
        preview = preview if preview is not None else []
    sims = similar_laws(k, lid)                                        # law.v2 only: a duplicate is noted, not refused
    if sims:
        extra["similar_to"] = sims
    k.log("proposal", actor, {"law": lid, "title": law["title"], "intent": law["intent"], "class": law["cls"], "code": law["code"],
                              **({"jurisdiction": jurisdiction} if jurisdiction is not None else {}), **extra,
                              **({"preview": preview[:40]} if shown else {})}, vis="public")
    if not shown:
        k.log("proposal_preview", actor, {"law": lid, "preview": preview[:40]}, vis="monitor")
    return {"law": lid}


def do_decide(k, jurisdiction, law, cls, rank, procedure_law) -> dict:
    """The procedure of the law's class decides: pass (Kernel.passed), open a ballot (or a chair's gate), or fail."""
    if "jur" in k.w:                                                   # jurisdictions: the procedure of the law's jurisdiction
        J.decide(k, law)
    else:
        k._decide(law)
    return {"status": k.w["laws"][law]["status"]}


def do_open_ballot(k, jurisdiction, ballot, question, electorate, options, rule, closes_round, proposal, opened_by, on_result=None,
                   weights=None, gate_spec=None) -> dict:
    k.w["ballot_seq"] += 1
    assert ballot == f"B{k.w['ballot_seq']}", ballot
    k.w["ballots"][ballot] = {"id": ballot, "question": question, "electorate": electorate, "options": [str(o) for o in options],
                              "rule": rule, "weights": weights or {}, "closes": closes_round, "votes": {}, "on_result": on_result,
                              "law": opened_by, "proposal": proposal, "gate": gate_spec, "status": "open"}
    if isinstance(rule, dict):                                         # law.v2 (W6c): a rule function or an assent, by name
        from charter import stages as ST
        shown = ST.shown(rule)
    else:
        shown = rule
    k.log("ballot_open", None, {"ballot": ballot, "question": question, "electorate": electorate, "options": options, "rule": shown,
                                "closes_round": closes_round}, vis="public")
    return {"ballot": ballot}


def do_cast_vote(k, jurisdiction, ballot, agent, choice) -> dict:
    k.w["ballots"][ballot]["votes"][agent] = choice
    k.log("vote", agent, {"ballot": ballot, "choice": choice}, vis="public")
    return {"choice": choice}


def do_close_ballot(k, jurisdiction, ballot, result, votes) -> dict:
    """A ballot closes with its tally; the kernel then acts on the result (Kernel.close_ballots: pass, fail, gate, callback)."""
    b = k.w["ballots"][ballot]
    b["status"] = "closed"
    b["result"] = result
    k.log("ballot_close", None, {"ballot": ballot, "result": result, "votes": votes}, vis="public")
    return {"result": result}


def do_veto(k, jurisdiction, law, member) -> dict:
    """A Board member's veto vote on a law or patch in its veto window (secret Board votes are monitor-only)."""
    item = next(v for v in k.w["veto_queue"] if v["law"] == law)
    if member not in item["vetoes"]:
        item["vetoes"].append(member)
    secret = k.spec["conditions"]["board_votes"] == "secret"
    k.log("veto_vote", member, {"law": law, "kind": item["kind"]}, vis="monitor" if secret else "public")
    return {"vetoes": len(item["vetoes"])}


def do_enact(k, jurisdiction, law, via) -> dict:
    """A law comes into force: loaded, appended to the enactment order, its on_enact run, published. With jurisdictions on, a law
    of no existing jurisdiction is void and a hidden one's dormant (J.intercept_enact). A repeal law repeals its target instead."""
    lid = law
    if "jur" in k.w and J.intercept_enact(k, lid):                     # jurisdictions: void (no such jurisdiction) or dormant (hidden)
        return {"status": k.w["laws"][lid]["status"]}
    rec = k.w["laws"][lid]
    if rec["repeal_target"]:
        rec["status"] = "enacted_repeal"
        rec["enacted_round"] = k.r
        k.repeal(rec["repeal_target"], by_law=lid, via="procedure")
        return {"status": rec["status"]}
    ns = k._load(lid)
    if v2(k):                                                          # P3.2: a law enacted without a proposal (start, intervention)
        rec.setdefault("rank", declared_rank(rec["code"]))
    rec["status"] = "active"
    rec["enacted_round"] = k.r
    k.w["law_order"].append(lid)
    if v2(k) and isinstance(ns.get("conflict_rule"), str):             # P3.2: a constitution's declared conflict rule (check_rank)
        set_conflict_rule(k, lid, ns["conflict_rule"])
    if "on_enact" in ns:
        k.call(lid, ns["on_enact"])
    k.log("enact", rec["author"], {"law": lid, "title": rec["title"], "class": rec["cls"]}, vis="public")
    if "grants" in (k.spec.get("institutions") or {}):                 # wave 9 E: offices the law declares (institutions.grants)
        from charter import institutions as IN
        IN.on_law_in_force(k, lid)
    return {"status": rec["status"]}


def do_repeal(k, jurisdiction, law, by_law, via) -> dict:
    """A law in force stops: its on_repeal runs, the procedures it set fall back to the ones they replaced (if their law is still in
    force), the actions it defined go, and the repeal is published."""
    rec = k.w["laws"][law]
    ns = k.ns.get(law, {})
    if "on_repeal" in ns:
        k.call(law, ns["on_repeal"])
    rec["status"] = "repealed"
    if DC.is_act(rec):                                                  # the default code: its rows go, the residual applies
        DC.on_repeal(k, law)
    for cl, key in list(k.w["procedures"].items()):
        if key.split("#")[0] == law:
            del k.w["procedures"][cl]
            # fall back to the procedure this law replaced, if the law that set it is still in force (e.g. the constitution)
            prev = next((h for h in reversed(k.w.get("procedure_history", [])) if h["cls"] == cl and h["law"] != law
                         and k.w["laws"].get(h["law"], {}).get("status") == "active" and h["key"] in k.fnreg), None)
            if prev:
                k.w["procedures"][cl] = prev["key"]
                k.log("procedure_restored", None, {"cls": cl, "law": prev["law"], "after_repeal_of": law}, vis="public")
    for nm, act in list(k.w["actions"].items()):
        if act["law"] == law:
            del k.w["actions"][nm]
    if "offices" in k.w:                                                # institutions.succession: its offices are abolished
        from charter import institutions as IN
        IN.on_law_repealed(k, law)
    k.log("repeal", None, {"law": law, "by": by_law, **({"via": via} if via == "expired" else {})}, vis="public")   # W6a: expiry
    return {"status": rec["status"]}


def do_amend(k, jurisdiction, law, old_sha, new_sha, diff, via, by, patch=None) -> dict:
    """A law's code is replaced (the Fixer's patch): reloaded and re-bound (procedures, callbacks, penalties run the new code), a
    suspended law back in force; a patch that fails to load is undone and logged. The diff is public unless the Fixer is hidden."""
    rec = k.w["laws"][law]
    old = rec["code"]
    rec["code"] = patch["code"]
    rec["patches"].append({**patch, "round": k.r, "old": old})
    try:
        ns = k._load(law)
        k._rebind(law, ns)                                              # procedures, callbacks, penalties now run the patched code
        if DC.is_act(rec):                                              # the default code: the Act now runs as its source
            DC.on_code_changed(k, law)
        if rec["status"] == "suspended":
            rec["status"] = "active"
    except L.LawError as e:
        rec["code"] = old
        if via == "procedure":
            rec["patches"].pop()
        k._load(law)
        if via == "procedure":                                          # P3.4: the caller fails the amendment draft
            return {"ok": False, "error": str(e)}
        k.log("patch_failed", patch["by"], {"law": law, "error": str(e)}, vis="public")
        return {"ok": False}
    if via == "procedure":                                              # P3.4: an amendment passed by the procedure (law.v2)
        from charter import linker as LK
        vs = rec.get("versions") or []
        if vs and vs[-1]["sha"] == LK.sha(rec["code"]) and vs[-1]["round"] == k.r:
            vs[-1].update({"via": "procedure", "by": by})
        k.log("amended", None, {"law": law, "proposal": patch.get("proposal"), "by": by, "reason": patch.get("reason", ""),
                                "version": rec.get("version"), "diff": patch.get("diff") or ""}, vis="public")
        return {"ok": True}
    hidden = k.spec["conditions"]["fixer"] == "hidden"
    k.log("patched", patch["by"], {"law": law, "reason": patch["reason"], **({} if hidden else {"diff": patch["diff"]})}, vis="public")
    k.log("patch_diff", patch["by"], {"law": law, "diff": patch["diff"]}, vis="monitor")
    return {"ok": True}


def do_set_procedure(k, jurisdiction, cls, procedure_law, key=None, own=False, rank=None) -> dict:
    """The procedure for a class of laws: the world's table (and the legacy J0's), or with own=True a jurisdiction's own table.
    rank (P3.2, law.v2): the procedure for drafts of that rank and class, stored under "<rank>:<cls>" (procedure_lookup)."""
    if rank is not None:
        cls = f"{rank}:{cls}"
    if own:
        jj = J.jurs(k)[jurisdiction]                                    # looked up at call time: dry runs replace k.w
        jj["procedures"][cls] = key
        jj["procedure_history"].append({"cls": cls, "key": key, "law": procedure_law})
    else:
        k.w["procedures"][cls] = key
        k.w.setdefault("procedure_history", []).append({"cls": cls, "key": key, "law": procedure_law})
    return {"key": key}


def do_rule(k, jurisdiction, case, verdict, judge, clause, accuser, accused, remedy=None, decides=True, stage=1, reason="") -> dict:
    """A judge decides a case; a guilty verdict runs the clause's penalty on the accused (a penalty's error suspends its law).
    law.v2 (courts v2, charter/courts.py): a panel judge's vote, a remedy for the penalty, a penalty deferred for an appeal."""
    if v2(k):
        from charter import courts as CO
        return CO.change_rule(k, jurisdiction, case, verdict, judge, clause, accuser, accused, remedy, decides, stage, reason)
    c = k.w["cases"][case]
    c.update({"status": "decided", "verdict": verdict, "reason": reason, "judge": judge})
    if verdict == "guilty":
        cl = k.w["clauses"][clause]
        lid, fn = k.fnreg[cl["penalty"]]
        try:
            k.call(lid, fn, accused, accuser)
        except L.LawError as e:
            k.law_error(lid, str(e))
    return {"verdict": verdict}


def do_define_action(k, law, action, right, key=None) -> dict:
    k.w["actions"][action] = {"right": right, "law": law, "fn": key}
    return {"action": action}


def do_create_clause(k, law, clause, name=None, text=None, key=None) -> dict:
    """W8b (review 12 §2.14): a law's clause(name, text, penalty): a clause courts can find a breach of (clause is "<law>:<name>";
    key the fnreg key of its penalty function)."""
    k.w["clauses"][clause] = {"law": law, "name": name, "text": text, "penalty": key}
    return {"clause": clause}
