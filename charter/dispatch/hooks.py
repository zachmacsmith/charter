"""New-style hooks (P3.1, P3.2, W6a): which laws a change binds and in what order, what payload they see, and how their
before-verdicts become a decision.

bound_laws: the active laws in force whose account binds the payload (review 09 §4.5), in canonical order (§8.1); hooked: the hook
index (a primitive no law hooks skips the binding work); hook_payload: the payload a law may see (V18 redaction, the row's `redact`,
hidden agents as None); normalise: a before-hook's value -> a Verdict; resolve_v2: the verdicts -> a DecisionV2 by the polity's
conflict rule (ranks.conflict_rule: any_block, superior, posterior, specialis, a constitution's function)."""
from __future__ import annotations

import copy as _copy
from dataclasses import dataclass, field
import importlib
import math as _math

from charter import accounts as AC
from charter import gas as G
from charter import jurisdictions as J
from charter import primitives as PR

from charter.dispatch.base import Charge, quiet, RANKS, v2
from charter.dispatch.chains import _observer
from charter.dispatch.legacy import DIRECTIVE_OK
from charter.dispatch.ranks import conflict_rule, _polity, rank_of
from charter.dispatch.validity import in_force


# ---------------------------------------------------------------------- binding and order


def _binds_value(k, lid, key, value):
    """Does a law's account bind this payload value? None: the value names no one bindable."""
    jid = J.law_jur(k, lid)
    if key == "jurisdiction":
        return (value or "J0") == jid
    if not isinstance(value, str):
        return None
    if value.startswith(AC.ESTATE):
        value = value[len(AC.ESTATE):]
    if value in k.w["agents"]:
        return J.binds(k, lid, value)
    if value == "reserve" or value.startswith("reserve:"):
        return J.reserve_key(k, jid) == value
    return None


def bound_laws(k, P, payload, phase) -> list:
    """Active laws whose account binds the payload (review 09 §4.5), in canonical order (§8.1: rank descending, then enactment, then
    id). Without jurisdictions: every active law. With them: laws of declared jurisdictions (any in a dry run) binding the subject
    (before) or any party (after); a payload naming nothing bindable is seen by all of them."""
    laws = [l for l in k.active_laws() if in_force(k, l["id"])]        # W6a: laws outside their declared window are skipped
    assoc = []
    if "contracts" in k.w:                                             # P4.3: associations' laws see their members' changes only
        from charter import contracts as CT                            # (contracts.sees; D-24: no polity legal acts)
        assoc = [l for l in laws if CT.sees(k, l["id"], P, payload, phase)]
        laws = [l for l in laws if J.association(k, J.law_jur(k, l["id"])) is None]
    if "jur" in k.w:
        keys = ((P.subject,) if P.subject else ()) if phase == "before" else tuple(P.parties)
        seen = []
        for law in laws:
            j = J.jurs(k).get(J.law_jur(k, law["id"]))
            if not k.dry and (not j or j["status"] != "declared"):
                continue
            hits = [_binds_value(k, law["id"], x, payload.get(x)) for x in keys]
            if any(h for h in hits) or all(h is None for h in hits):
                seen.append(law)
        laws = seen
    laws = laws + assoc
    pos = {lid: i for i, lid in enumerate(k.w["law_order"])}
    return sorted(laws, key=lambda l: (-RANKS[rank_of(k, l["id"])], pos.get(l["id"], 1 << 30), l["id"]))


def _hook_fn(k, lid, hook):
    ns = k.ns.get(lid) or k._load(lid)
    fn = ns.get(hook)
    return fn if callable(fn) else None


# Hooks indexed by name (review 10 §7 "Gas and performance"): {hook: frozenset of active law ids whose module defines it}, rebuilt
# when the active laws or their loaded modules change (identity of each namespace). A primitive no law hooks skips bound_laws
# altogether. Unknown (None) while an active law is not loaded yet: callers then take the full path, which loads laws exactly as
# before, so the index never changes which laws load or run, or in what order.
def _hook_index(k) -> dict | None:
    act = [lid for lid in k.w["law_order"] if k.w["laws"][lid]["status"] == "active"]
    nss = tuple(k.ns.get(lid) for lid in act)
    hit = k.__dict__.get("_hook_index")
    if hit is not None and hit[0] == act and len(hit[1]) == len(nss) and all(a is b for a, b in zip(hit[1], nss)):
        return hit[2]
    if any(ns is None for ns in nss):
        return None
    idx: dict = {}
    for lid, ns in zip(act, nss):
        for name, v in ns.items():
            if name in PR.HOOKS and callable(v):
                idx.setdefault(name, set()).add(lid)
    idx = {h: frozenset(v) for h, v in idx.items()}
    k._hook_index = (act, nss, idx)
    return idx


def hooked(k, hook) -> bool:
    """May any active law define `hook`? False only when every active law is loaded and none defines it."""
    idx = _hook_index(k)
    return idx is None or hook in idx


# ---------------------------------------------------------------------- redaction of payloads
# Agents a call's options or payload make secret from laws: an unnamed killer (end_life named=False), a covert attacker.
HIDE = {"end_life": lambda p, o: (p.get("by"),) if o.get("named") is False else (),
        "attack": lambda p, o: (p.get("attacker"),) if p.get("covert") else ()}


def hidden_agents(k, name, p, opts) -> tuple:
    """Who a law may not see in this change: concealed actors (Kernel.concealing), the observer, and HIDE's."""
    out = set(getattr(k, "_concealed", None) or ())
    o = _observer(k)
    if o:
        out.add(o)
    f = HIDE.get(name)
    if f:
        out.update(x for x in f(p, opts) if x)
    return tuple(sorted(out))


def _scrub(x, hide):
    if isinstance(x, str):
        return None if x in hide else x
    if isinstance(x, dict):
        return {kk: _scrub(v, hide) for kk, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_scrub(v, hide) for v in x]
    return x


def hook_payload(k, P, payload, viewer, hide=()) -> dict:
    """A deep copy of the payload as a law may see it: the row's redact function, then hidden agents as None (anywhere in it)."""
    p = _copy.deepcopy(payload)
    if P.name == "dm" and (not p.get("readable") or p.get("encrypted")):   # as the legacy on_dm: a law reads a DM's text only where
        p["text"] = None                                                 # the world lets laws read DMs and it is not encrypted (V18)
    if P.name == "post" and p.get("kind") == "channel_post":           # a private channel's text: never to laws (legacy on_post never
        p["text"] = None                                                 # saw channel posts; V18). Who posted where stays visible.
    if P.redact and viewer is not None:
        mod, _, fn = P.redact.partition(":")
        p = getattr(importlib.import_module(f"charter.{mod}"), fn)(k, p, viewer)
    return _scrub(p, set(hide)) if hide else p


# ---------------------------------------------------------------------- verdicts
@dataclass(frozen=True)
class Verdict:
    law: str
    block: bool = False
    allow: bool = False
    charge: float = 0.0
    reason: str | None = None
    exempt: bool = False
    directives: dict = field(default_factory=dict)
    specific: float = 0.0           # W6a: lex specialis: a dict's "specific" (True counts 1; a number its specificity)


def _specificity(x) -> float:
    """W6a: a verdict's "specific" value: True 1, False/None 0, a finite number itself; anything else is the law's runtime error."""
    if x is None or isinstance(x, bool):
        return 1.0 if x else 0.0
    if isinstance(x, (int, float)) and _math.isfinite(float(x)):
        return float(x)
    raise G.LawError(f"specific must be True or a number, not {x!r}")


def normalise(P, lid, out):
    """A before-hook's return value -> a Verdict (or None). A malformed verdict is the law's runtime error."""
    if out is None:
        return None
    if out is True:
        return Verdict(lid, allow=True)
    if out is False:
        return Verdict(lid, block=True)
    if isinstance(out, (int, float)) and not isinstance(out, bool):
        x = float(out)
        if not _math.isfinite(x) or x < 0:
            raise G.LawError(f"before_{P.name} returned {out!r}: a charge must be a non-negative finite number")
        if x > 0 and not P.charge:
            raise G.LawError(f"before_{P.name} returned a charge, but a {P.name} cannot be charged")
        return Verdict(lid, charge=x) if x > 0 else None
    if isinstance(out, dict):
        allowed = {"block", "charge", "reason", "exempt", "specific"} | set(P.directives)   # W6a: specific
        bad = sorted(str(x) for x in out if x not in allowed)
        if bad:
            raise G.LawError(f"before_{P.name} returned unknown keys {bad} (allowed: {sorted(allowed)})")
        ch = out.get("charge") or 0
        if isinstance(ch, bool) or not isinstance(ch, (int, float)) or not _math.isfinite(float(ch)) or ch < 0:
            raise G.LawError(f"before_{P.name}: charge must be a non-negative number, not {ch!r}")
        if ch > 0 and not P.charge:
            raise G.LawError(f"before_{P.name} returned a charge, but a {P.name} cannot be charged")
        return Verdict(lid, block=bool(out.get("block")), allow="block" in out and not out["block"], charge=float(ch),
                       reason=None if out.get("reason") is None else str(out["reason"])[:300], exempt=bool(out.get("exempt")),
                       directives={x: out[x] for x in P.directives if x in out}, specific=_specificity(out.get("specific")))
    raise G.LawError(f"before_{P.name} must return None, True, False, a number or a dict, not {type(out).__name__}")


@dataclass(frozen=True)
class DecisionV2:
    block: bool = False
    blocked_by: tuple = ()
    reason: str | None = None
    charges: tuple = ()
    directives: dict = field(default_factory=dict)


def resolve_v2(k, P, payload, verdicts) -> DecisionV2:
    """The before-verdicts (in canonical order) -> a decision, by the polity's conflict rule (review 09 §8.3; P3.2):
      any_block (the default, D-13): any block blocks; charges (rows with `charge` only) sum, capped when applied, each to the
        charging law's treasury (accounts.charge_destination); the first valid directive in canonical order wins.
      superior: among the explicit verdicts (a block, True, or a dict naming block), those of the highest rank decide, any block among
        them blocking (ties: any_block); no explicit verdict, no block. Charges sum, except that an exempt verdict of a law of rank >=
        the charging law's cancels that charge. Directives: canonical order (highest rank first).
      posterior: the latest-enacted law with an explicit verdict decides; charges sum; directives: latest enactment first.
      specialis (W6a, lex specialis): as superior, except that within the highest rank only the explicit verdicts of the highest
        specificity (a dict's "specific": True counts 1, a number itself, none 0) decide; ties: any_block among them. Exemptions as
        superior.
      function: the constitution's fn(verdicts) -> {"block": bool, "charges": [{"law", "charge"}]} (verdicts: [{law, rank, seq, block,
        allow, charge, exempt, reason, specific (W6a)}]), run as the constitution's call; its output is validated, and any_block decides when it
        fails or returns something invalid. Directives as any_block.
    The polity: the payload's jurisdiction (legal acts with jurisdictions on), else that of the first verdict's law; J0 without
    jurisdictions."""
    if not verdicts:
        return DecisionV2()
    pol = payload.get("jurisdiction") if "jur" in k.w and isinstance(payload.get("jurisdiction"), str) else _polity(k, verdicts[0].law)
    rule = conflict_rule(k, pol) if v2(k) else None
    name = rule["rule"] if rule else "any_block"
    pos = {lid: i for i, lid in enumerate(k.w["law_order"])}
    order = verdicts
    deciding = verdicts                                                 # the verdicts whose blocks count
    exempting = ()
    if name in ("superior", "specialis"):
        explicit = [v for v in verdicts if v.block or v.allow]
        top = max((RANKS[rank_of(k, v.law)] for v in explicit), default=None)
        deciding = [v for v in explicit if RANKS[rank_of(k, v.law)] == top]
        if name == "specialis":                                         # W6a: within the top rank, the most specific decide
            most = max((v.specific for v in deciding), default=None)
            deciding = [v for v in deciding if v.specific == most]
        exempting = [v for v in verdicts if v.exempt]
    elif name == "posterior":
        order = sorted(verdicts, key=lambda v: -pos.get(v.law, -1))
        deciding = next(([v] for v in order if v.block or v.allow), [])
    charges = []
    if P.charge:
        payer, item = (payload[x] for x in P.charge)
        charges = [Charge(v.law, payer, item, v.charge, AC.charge_destination(k, v.law, payer)) for v in verdicts if v.charge > 0
                   and not any(e.law != v.law and RANKS[rank_of(k, e.law)] >= RANKS[rank_of(k, v.law)] for e in exempting)]
    blocked = tuple(v.law for v in deciding if v.block)
    reasons = [v.reason for v in deciding if v.block and v.reason]
    if name == "function":
        out = _rule_function(k, rule, P, verdicts, pos, charges)
        if out is not None:
            block, charges = out
            blocked = (blocked or (rule["law"],)) if block else ()
            reasons = reasons if block else []
    directives = {}
    for v in order:
        for x, val in v.directives.items():
            if x not in directives and DIRECTIVE_OK.get(x, lambda k, v: True)(k, val):
                directives[x] = val
    return DecisionV2(bool(blocked), blocked, "; ".join(reasons)[:300] or None, tuple(charges), directives)


def _rule_function(k, rule, P, verdicts, pos, charges):
    """Run a constitution's conflict-rule function (quietly: no new-style hook runs inside it) and validate its output: (block,
    charges) with each charge {"law": a charging verdict's law, "charge": 0 <= x <= that law's own charge}, in canonical order; or
    None (a runtime error or an invalid output: the caller keeps any_block's decision)."""
    lid, fn = k.fnreg[rule["key"]]
    view = [{"law": v.law, "rank": rank_of(k, v.law), "seq": pos.get(v.law, -1), "block": v.block, "allow": v.allow,
             "charge": v.charge, "exempt": v.exempt, "reason": v.reason, "specific": v.specific} for v in verdicts]   # W6a: specific
    try:
        with quiet(k):
            out = k.call(lid, fn, view)
    except G.LawError:
        if k.dry:
            raise
        return None
    if not isinstance(out, dict) or not isinstance(out.get("block"), bool):
        return None
    if "charges" not in out:
        return out["block"], charges
    asked = out["charges"]
    if not isinstance(asked, list) or not all(isinstance(c, dict) and isinstance(c.get("charge"), (int, float))
                                              and not isinstance(c.get("charge"), bool) for c in asked):
        return None
    by_law = {c.law: c for c in charges}
    kept = []
    for c in asked:
        old = by_law.get(c.get("law"))
        q = float(c["charge"])
        if old is None or not _math.isfinite(q) or q < 0 or q > old.qty:
            return None
        if q > 0:
            kept.append(Charge(old.law, old.payer, old.item, q, old.dst))
    return out["block"], [c for o in charges for c in kept if c.law == o.law]
