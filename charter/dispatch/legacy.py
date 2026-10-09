"""Legacy hook aliases (P2.1-P2.4; W8b): today's change hooks (on_transfer, on_harvest, on_post, on_dm, on_proposal, on_vote,
on_ruling, on_admission, on_exit, on_birth, on_commission), dispatched by apply exactly as their old call sites did, with or without law.v2 (R5).

For a routed primitive, apply runs the BEFORE aliases (primitives.ALIASES) whose filter matches the payload and the cause chain,
through Kernel.hooks (enactment order; with jurisdictions on, J.hooks' binding), in canonical order. `resolve` reads their verdicts
with today's reader per alias (on_transfer: False blocks, a positive non-bool number taxes; on_harvest: a positive number, True
counting 1, deducts); charges go to the charging law's treasury (accounts.charge_destination, P4.1), capped by the change. After the
change the AFTER aliases run synchronously, as today (on_post with current_post set, on_dm). No legal act has a before-alias (P2.3):
on_proposal (None), on_vote and on_ruling fire after the act, from an agent's action only; on_enact/on_repeal are the law's own
lifecycle hooks, run inside do_enact/do_repeal (changes.legal)."""
from __future__ import annotations

from contextlib import contextmanager

from charter import accounts as AC
from charter import jurisdictions as J
from charter import primitives as PR

from charter.dispatch.base import Charge, Decision, NotRouted, ROUTED


# The aliases of each routed primitive, by phase (primitives.ALIASES order).
ALIASES_BEFORE = {n: tuple(a for a in PR.ALIASES if a.primitive == n and a.phase == "before") for n in ROUTED}
ALIASES_AFTER = {n: tuple(a for a in PR.ALIASES if a.primitive == n and a.phase == "after") for n in ROUTED}


# ---------------------------------------------------------------------- dispatch
def legacy_hooks(k, name: str, args: tuple, p: dict | None = None) -> list:
    """Dispatch a legacy hook exactly as its old call site did (Kernel.hooks: enactment order; jurisdictions' binding). One literal
    call per alias of a routed primitive, so lawapi.dispatch_sites() finds them (P2.3/P2.4 add theirs here). `p` is the payload:
    the membership hooks run on one jurisdiction's laws only (J.hooks_of the payload's polity), as they always have."""
    if name == "on_transfer":
        return k.hooks("on_transfer", *args)
    if name == "on_harvest":
        return k.hooks("on_harvest", *args)
    if name == "on_post":
        return k.hooks("on_post", *args)
    if name == "on_dm":
        return k.hooks("on_dm", *args)
    # P2.3: legal acts
    if name == "on_proposal":
        return k.hooks("on_proposal", *args)
    if name == "on_vote":
        return k.hooks("on_vote", *args)
    if name == "on_ruling":
        return k.hooks("on_ruling", *args)
    if name == "on_admission":                                       # P2.4d: membership (the polity's own laws only)
        return J.hooks_of(k, p["polity"], "on_admission", *args)
    if name == "on_exit":
        return J.hooks_of(k, p["polity"], "on_exit", *args)
    if name == "on_birth":
        return J.hooks_of(k, p["polity"], "on_birth", *args) if p["polity"] else []
    if name == "on_commission":                                      # W8b: life (commission is routed)
        return k.hooks("on_commission", *args)
    raise NotRouted(f"legacy hook {name} is not dispatched by k.apply yet")


# ---------------------------------------------------------------------- verdicts
def _read_transfer(out):
    """on_transfer (block_or_tax): False blocks; a positive number (not a bool) is a tax."""
    if out is False:
        return "block", None
    if isinstance(out, (int, float)) and not isinstance(out, bool) and out > 0:
        return "charge", float(out)
    return None, None


def _read_harvest(out):
    """on_harvest (deduct): a positive number is deducted (True counts as 1, as it always has); nothing blocks."""
    if isinstance(out, (int, float)) and out > 0:
        return "charge", float(out)
    return None, None


def _read_typed_harvest(out):
    """on_harvest at a typed camp (camptypes.framework.pay_yield): a positive number (not a bool) is deducted, as it always was."""
    if isinstance(out, (int, float)) and not isinstance(out, bool) and out > 0:
        return "charge", float(out)
    return None, None


def _read_admission(out):
    """on_admission (admit_or_refuse): False refuses (a block), True admits (directive admit); anything else is no answer."""
    if out is False:
        return "block", None
    if out is True:
        return "directive", ("admit", True)
    return None, None


def _read_birth(out):
    """on_birth (jurisdiction_or_none): False puts the child in no jurisdiction, a jurisdiction's id puts it there if declared
    (DIRECTIVE_OK, checked when resolved); the last valid answer in canonical order wins (today's fold)."""
    if out is False:
        return "directive", ("jurisdiction", None)
    if isinstance(out, str):
        return "directive", ("jurisdiction", out)
    return None, None


def _read_ignored(out):
    return None, None


def _read_refuse(out):
    """on_commission (refuse, W8b): False refuses the order (a block); anything else is no answer."""
    return ("block", None) if out is False else (None, None)


# Readers by alias name; a (name, payload via) key overrides one for a variant of a primitive (typed camps' harvests).
READERS = {"on_transfer": _read_transfer, "on_harvest": _read_harvest, ("on_harvest", "typed"): _read_typed_harvest,
           "on_admission": _read_admission, "on_birth": _read_birth, "on_exit": _read_ignored, "on_commission": _read_refuse}


# A directive value a verdict may set, checked when it is resolved (not valid: the verdict is ignored, as today).
DIRECTIVE_OK = {"admit": lambda k, v: True,
                "jurisdiction": lambda k, v: v is None or J.st(J.jurs(k).get(v)) == "declared"}


def resolve(k, P: PR.Primitive, payload: dict, verdicts: list) -> Decision:
    """Before-verdicts -> a Decision: any block blocks; numeric verdicts are charges of the row's (payer, item) to the charging
    law's own treasury (accounts.charge_destination, P4.1; today always the payer's home reserve), their sum capped by the payload's
    quantity."""
    blocked, charges, directives = [], [], {}
    for alias, lid, out in verdicts:
        kind, qty = (READERS.get((alias.name, payload.get("via"))) or READERS[alias.name])(out)
        if kind == "block":
            blocked.append(lid)
        elif kind == "directive" and qty[0] in P.directives and DIRECTIVE_OK[qty[0]](k, qty[1]):
            directives[qty[0]] = qty[1]                              # the last in canonical order wins
        elif kind == "charge" and P.charge:
            payer, item = (payload[x] for x in P.charge)
            charges.append(Charge(lid, payer, item, qty, AC.charge_destination(k, lid, payer)))
    total = 0.0
    for c in charges:
        total += c.qty
    cap = payload.get("qty")
    charged = min(total, cap) if cap is not None else total
    return Decision(block=bool(blocked), blocked_by=tuple(blocked), charges=tuple(charges), charged=charged, directives=directives)


@contextmanager
def _after_context(k, name: str, payload: dict, result: dict):
    """What an after-hook sees beside its arguments: a post's id through current_post() (posts and anonymous posts, as before)."""
    if name == "post" and payload["kind"] in ("post", "anon_post"):
        k.current_post = result.get("event")
        try:
            yield
        finally:
            k.current_post = None
    else:
        yield


# ---------------------------------------------------------------------- the legacy steps of apply (both paths)
def _legacy_before(k, P, p, chain) -> Decision:
    """The legacy BEFORE aliases whose filter matches, resolved: exactly as before P3.1, with or without law.v2 (R5)."""
    verdicts = []
    for a in (ALIASES_BEFORE.get(P.name, ()) if P.before else ()):
        if a.when(p, chain):
            verdicts.extend((a, lid, out) for lid, out in legacy_hooks(k, a.name, a.args(p), p))
    return resolve(k, P, p, verdicts) if verdicts else Decision()


def _extra(P, d: Decision) -> dict:
    """What the change gets from the legacy decision: the capped charge and its plan (rows with `charge`), and the directives set."""
    extra = {"charged": d.charged, "charge_to": AC.charge_plan(d.charges, d.charged)} if P.charge else {}
    extra.update(d.directives)                                      # the verdicts' directives (only those set) reach the change
    return extra


def _legacy_after(k, P, p, chain, result) -> None:
    """The legacy AFTER aliases whose filter matches, synchronously, as today."""
    after = ALIASES_AFTER.get(P.name, ()) if P.after else ()
    if not after:
        return
    with _after_context(k, P.name, p, result):
        for a in after:
            if a.when(p, chain):
                legacy_hooks(k, a.name, a.args(p), p)


# Legacy aliases a phase step dispatches instead of apply. None since P2.4d moved on_birth onto the child's join (via "born"), which
# the birth phase's jurisdiction step applies; kept as the place to name one if a future alias needs a phase's own position.
PHASE_ALIASES: dict = {}
