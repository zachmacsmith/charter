"""Incorporation (W8e; docs/ARCHITECTURE.md §7.2 "Incorporation", D-28) and the first slice of D-27 (contract defaults moved out
of the kernel into the contract's own code and its parent polity's law). contracts.enabled + law.v2 only: nothing here runs, and no
state key is written, in a world where no contract is founded under a polity and no polity law sets a company rule.

Incorporation. An association may be founded under a polity (create_contract {"under": "<jid>"}, "J0" when jurisdictions are off):
its record carries `parent` (absent on an unincorporated contract, which keeps today's limits and today's world defaults). The
founding is the routed create_contract primitive with the payload key `under`, so the parent's laws see it and may refuse it
(before_create_contract: registration, a required template), and the kernel applies the parent's company rules at founding (a
registration fee, a required governance form, limits). Incorporated, the company is bound by its parent's law:
  - binding (dispatch.hooks.bound_laws): the parent's laws see every change that names the company (its id as the payload's
    contract / jurisdiction / polity, its treasury, an escrow it holds), whoever the subject is; with jurisdictions on, other
    polities' laws no longer see the company's own acts (internal affairs are the parent's: the payload values naming the company
    bind the parent's laws and no other polity's). Each member's own polity still governs that member's own acts (the subject or a
    party is the member: as today).
  - ranks and conflicts: a polity's laws are statute or above, a contract's code is rank bylaw, so in canonical hook order the
    parent's laws run first, and the conflict rule of the parent decides (dispatch.hooks.resolve_v2 maps an incorporated company to
    its parent: governing_polity). Under `superior` a parent law's block of a company's own act wins over the company's explicit
    allow; under any_block (the default) any block blocks, as today.
  - benefits, granted by the parent's law, not by world dials: company rules (below) set by the parent's laws with
    company_rule(key, value), read at the existing seams. A key the parent never set falls back to today's world behaviour.

Company rules (k.w["company_rules"][polity][key] = {"value", "law"}; created on first use, like courts' court rules; a rule holds
while the law that set it is in force). The set_company_rule primitive (routed, legal, hookable) makes the change. Keys (RULES):
  enforcement        escrow | escrow_court | word: the contracts.enforcement dial for this polity's companies. escrow_court gives
                     them the parent's courts (their breaches are actionable in its courts only, and a breach case is opened under
                     the parent's breach_of_contract clause). Unset: the world's dial.
  recognize_offices  True | False: whether the parent recognises its companies' offices as agents of the company: False refuses
                     authorizations naming such an office and their use (agency). Unset: True (today).
  share_valuation    "nav" | "none" | a number in [0, 1]: what Kernel.price values a share of its companies at: net asset value per
                     unit, nothing, or that fraction of it (a haircut; never above NAV, so no valuation can mint wealth). Overrides
                     the company's own clause. Unset: the company's clause, else "nav" (today).
  wind_up            a list of steps from WIND_UP_STEPS: the insolvency order a company is wound up in (shareholders: pro rata to
                     the holders of its currencies; members: equal shares among the last members; parent: what is left escheats to
                     the parent's treasury). Overrides the company's own clause. Unset: the company's clause, else
                     DEFAULT_WIND_UP (today: shareholders, then members).
  procedures         a list of governance forms the parent allows (contracts.PROCEDURES, or "custom": a procedure function of the
                     company's own code). A company's procedure outside the list is not used: the first listed form decides its
                     changes instead (effective_procedure); founding with a template whose form is not allowed is refused. Unset:
                     any.
  registration_fee   {item: qty}: paid by the founder into the parent's treasury when a company is founded under it (refused if
                     the founder cannot pay). Unset: none.
  max_laws, max_own  per-company limits (laws in force; own currencies, rights and offices each): the parent's value replaces
                     the spec (contracts.max_laws, contracts.max_own). Unset: the spec.

D-27, first slice (the contract's own code, bounded by its parent's company rules; today's behaviour stays the default):
  - share valuation: Kernel.price's NAV branch reads valuation_factor (the parent's share_valuation, else the company's own
    top-level clause `share_valuation = ...`, else NAV);
  - wind-up order: contracts._dissolve runs wind_up_order (the parent's wind_up, else the company's own clause `wind_up = [...]`,
    else DEFAULT_WIND_UP) after its laws' on_dissolve;
  - built-in procedures: members, two_thirds and founder are the default code of a contract's procedure (run natively, as D-30's
    default code); the library block "Contract Procedures" holds the same three as law code a contract may import and amend, and
    a contract's set_procedure may name a built-in form by name;
  - per-contract limits: contracts.MAX_OWN and MAX_FUNDS are spec keys (contracts.max_own, contracts.max_funds) with the
    constants as defaults, and the parent's company rules max_laws and max_own replace the spec for its companies.
Deferred (D-27): the rest of the contract column beyond physics, breach visibility, member liability (pierce the veil: members
liable for a company's treasury debts; a company has no debts yet), the agency action list.
"""
from __future__ import annotations

import ast
import functools

from charter import accounts as AC
from charter import jurisdictions as J
from charter import lawlang as L

ENFORCEMENT = ("escrow", "escrow_court", "word")                     # = contracts.ENFORCEMENT (contracts imports this module)
PROCEDURE_FORMS = ("members", "two_thirds", "founder", "custom")
WIND_UP_STEPS = ("shareholders", "members", "parent")
DEFAULT_WIND_UP = ("shareholders", "members")
RULES = {
    "enforcement": "escrow | escrow_court | word: how this polity enforces its companies' contracts (escrow_court: its courts hear "
                   "their breaches)",
    "recognize_offices": "True | False: whether this polity recognises its companies' offices as agents (agency to an office)",
    "share_valuation": "\"nav\" | \"none\" | a number from 0 to 1: what one of its companies' shares is valued at (net asset value, "
                       "nothing, or that fraction of it)",
    "wind_up": "a list of shareholders, members, parent: the order its companies are wound up in",
    "procedures": "a list of members, two_thirds, founder, custom: the governance forms its companies may use",
    "registration_fee": "{item: qty}: what a founder pays this polity's treasury to found a company under it",
    "max_laws": "1-10: laws one of its companies may have in force",
    "max_own": "0-10: currencies, rights and offices (each) one of its companies may create",
}
BOUNDS = {"max_laws": (1, 10), "max_own": (0, 10)}


# ---------------------------------------------------------------------- the parent link
def assoc(k, cid):
    return AC.assocs(k).get(cid) if isinstance(cid, str) else None


def parent_of(k, cid):
    """The polity association `cid` is incorporated under, or None (unincorporated, or not an association)."""
    rec = assoc(k, cid)
    return (rec or {}).get("parent")


def any_incorporated(k) -> bool:
    return any(r.get("parent") is not None for r in AC.assocs(k).values())


def key_parent(k, value):
    """The parent of the incorporated association a payload value names: its id ("A1"), its treasury ("assoc:A1") or an escrow it
    holds ("escrow:A1:<aid>"); None otherwise (an agent, a polity, an unincorporated association, anything else)."""
    if not isinstance(value, str):
        return None
    if value.startswith(AC.ASSOC):
        value = value[len(AC.ASSOC):]
    elif value.startswith(AC.ESCROW):
        value = value[len(AC.ESCROW):].partition(":")[0]
    return parent_of(k, value)


PAYLOAD_KEYS = ("contract", "jurisdiction", "polity")
OWN_KEYS = ("currency", "right")                                     # "<cid>.<name>": a company's own currency or right


def payload_parents(k, payload) -> set:
    """The parents of the incorporated associations a payload names as its contract, jurisdiction or polity, or whose own currency
    or right it names (shares issued, an office granted) (dispatch.hooks): their laws see the change whoever its subject is."""
    out = set()
    for x in PAYLOAD_KEYS + OWN_KEYS:
        v = payload.get(x)
        if x in OWN_KEYS:
            v = v.split(".", 1)[0] if isinstance(v, str) and "." in v else None
        par = parent_of(k, v)
        if par is not None:
            out.add(par)
    return out


def governing_polity(k, pol):
    """The polity whose conflict rule decides a change of account `pol` (dispatch.hooks.resolve_v2): an incorporated association's
    parent; anything else unchanged."""
    par = parent_of(k, pol)
    return pol if par is None else par


def check_under(k, under) -> str:
    """A polity a contract may be founded under: "J0" (the world, with jurisdictions off; J0 itself with them on) or a declared
    jurisdiction. LawError otherwise."""
    u = str(under).strip()
    if not J.enabled(k):
        if u != "J0":
            raise L.LawError("contracts are incorporated under a polity: in this world the only one is J0")
        return u
    j = J.jurs(k).get(u)
    if j is None or J.st(j) != "declared":
        known = [x for x, v in J.jurs(k).items() if J.st(v) == "declared"]
        raise L.LawError(f"no declared polity {u} to incorporate under" + (f" (declared: {', '.join(known)})" if known else ""))
    return u


def companies(k, polity) -> list:
    """The live associations incorporated under `polity`, in founding order."""
    return [c for c, r in AC.assocs(k).items() if r.get("parent") == polity and r["status"] != "dissolved"]


# ---------------------------------------------------------------------- company rules (the parent's law)
def _store(k) -> dict:
    return k.w.get("company_rules") or {}


def rules(k, polity) -> dict:
    """The company rules a polity has set and are in force: {key: value} (a rule holds while the law that set it is in force)."""
    out = {}
    for key, e in (_store(k).get(polity) or {}).items():
        if (k.w["laws"].get(e.get("law")) or {}).get("status") == "active":
            out[key] = e["value"]
    return out


def rule(k, cid, key):
    """The parent's company rule `key` for association cid, or None (unincorporated, or the parent never set it)."""
    par = parent_of(k, cid)
    return None if par is None else rules(k, par).get(key)


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x


def check_rule(k, key, value):
    """A company rule's value, checked and normalised (LawError on a bad key or value)."""
    if key not in RULES:
        raise L.LawError(f"no company rule {key!r}: one of {', '.join(RULES)}")
    if key == "enforcement":
        if value not in ENFORCEMENT:
            raise L.LawError(f"company rule enforcement is one of {', '.join(ENFORCEMENT)}")
        return value
    if key == "recognize_offices":
        if not isinstance(value, bool):
            raise L.LawError("company rule recognize_offices is True or False")
        return value
    if key == "share_valuation":
        if value in ("nav", "none"):
            return value
        if _num(value) and 0 <= float(value) <= 1:
            return float(value)
        raise L.LawError("company rule share_valuation is \"nav\", \"none\" or a number from 0 to 1 (a fraction of net asset value)")
    if key in ("wind_up", "procedures"):
        known = WIND_UP_STEPS if key == "wind_up" else PROCEDURE_FORMS
        if not isinstance(value, (list, tuple)) or not value or any(x not in known for x in value) or len(set(value)) != len(value):
            raise L.LawError(f"company rule {key} is a list of distinct names from {', '.join(known)}")
        return list(value)
    if key == "registration_fee":
        if not isinstance(value, dict) or not all(isinstance(i, str) and _num(q) and q >= 0 for i, q in value.items()):
            raise L.LawError("company rule registration_fee is {item: qty} (quantities zero or more)")
        return {str(i): float(q) for i, q in sorted(value.items()) if q > 0}
    lo, hi = BOUNDS[key]
    if not _num(value) or value != int(value) or not lo <= int(value) <= hi:
        raise L.LawError(f"company rule {key} is a whole number from {lo} to {hi}")
    return int(value)


def change_set_rule(k, jurisdiction, key, value, lid=None) -> dict:
    """The set_company_rule primitive's change: one company rule of the law's polity."""
    pol = AC.account_of(k, lid) if lid else (jurisdiction or "J0")
    k.w.setdefault("company_rules", {}).setdefault(pol, {})[key] = {"value": value, "law": lid}
    k.log("company_rule", None, {"key": key, "value": value, "law": lid, "polity": pol}, vis="public")
    return {"key": key, "value": value}


# ---------------------------------------------------------------------- the company's own clauses (D-27: its code, bounded by the parent)
CLAUSES = ("share_valuation", "wind_up")


@functools.lru_cache(maxsize=512)
def _clauses(code: str) -> tuple:
    """The clauses a law's code declares as top-level constants (CLAUSES): ((name, value), ...); read statically (never by running
    the law), so a valuation read does not load or call anything."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ()
    out = []
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id in CLAUSES:
            try:
                out.append((n.targets[0].id, ast.literal_eval(n.value)))
            except (ValueError, SyntaxError):
                continue
    return tuple(out)


def clause(k, rec, name):
    """The first of the contract's laws in force (in its order) that declares clause `name`: its value, else None."""
    for lid in rec["laws"]:
        law = k.w["laws"].get(lid) or {}
        if law.get("status") != "active":
            continue
        for nm, v in _clauses(law.get("code") or ""):
            if nm == name:
                return v
    return None


def _valuation(v):
    if v == "nav":
        return 1.0
    if v == "none":
        return 0.0
    if _num(v) and 0 <= float(v) <= 1:
        return float(v)
    return None


def valuation_factor(k, cid) -> float:
    """What fraction of net asset value Kernel.price gives one unit of association cid's currency: the parent's share_valuation,
    else the company's own clause, else 1.0 (NAV, today). A clause outside the allowed values is ignored."""
    rec = assoc(k, cid)
    if rec is None:
        return 1.0
    for v in (rule(k, cid, "share_valuation"), clause(k, rec, "share_valuation")):
        f = _valuation(v) if v is not None else None
        if f is not None:
            return f
    return 1.0


def _steps(v):
    if isinstance(v, (list, tuple)) and v and all(x in WIND_UP_STEPS for x in v) and len(set(v)) == len(v):
        return tuple(v)
    return None


def wind_up_order(k, rec) -> tuple:
    """The steps a contract is wound up in: the parent's wind_up rule, else its own clause (read while its laws are in force),
    else DEFAULT_WIND_UP."""
    for v in (rule(k, rec["id"], "wind_up"), clause(k, rec, "wind_up")):
        s = _steps(v) if v is not None else None
        if s is not None:
            return s
    return DEFAULT_WIND_UP


def form_of(procedure, builtin) -> str:
    """A procedure's governance form: a built-in name, else custom (a law's function)."""
    return procedure if procedure in builtin else "custom"


def allowed_forms(k, rec):
    """The governance forms the parent allows its companies (its procedures rule), or None (any)."""
    return rule(k, rec["id"], "procedures")


def effective_procedure(k, rec, builtin) -> str:
    """The procedure that decides a contract's changes: its own, unless its parent's procedures rule does not allow its form, in
    which case the first form the parent lists (a built-in; "custom" alone keeps the company's own)."""
    allowed = allowed_forms(k, rec)
    proc = rec["procedure"]
    if allowed is None or form_of(proc, builtin) in allowed:
        return proc
    return next((f for f in allowed if f in builtin), proc)


def limit(k, rec, key, spec_value) -> int:
    """A per-company limit: the parent's company rule `key` when set, else the spec's value."""
    v = rule(k, rec["id"], key) if rec is not None else None
    return int(spec_value) if v is None else int(v)


def offices_recognised(k, cid) -> bool:
    """Does the polity association cid is incorporated under recognise its offices (agency to an office)? True unless the parent
    says False (and always for an unincorporated contract: today)."""
    return rule(k, cid, "recognize_offices") is not False
