"""Shared helpers for the Camps-B types (consortium, weak link, catalyst, partners, vault, guess). Not a type module (the leading
underscore keeps the registry's auto-import away).

Calibration: each type sets its payouts in tutorial units, i.e. multiples of V0, the value of one tutorial harvest at the optimum
and full stock (camps.typed.value_per_action, 8 by default). Targets (spec, "Camps"): coordination camps 2-3x per action when
coordination works and about 0.5x when it fails; social games about 1x with high variance. A type sets `value_target` to its
role's default target explicitly, so at run time one tutorial unit in the camp's resource is

    v0q(camp) = camp["y_ref"] / value_target        (y_ref = V0 x value_target / unit value of the resource, set by the framework)

and payouts follow V0 and the resource's unit value. These types are not commons: their stock is sized so that the framework's
stock cap never binds (generous_stock), and payouts do not scale with stock.

State: hidden parameters in camp["fn"] (self.p, monitor-only via truth()); play state in camp["play"], created only on paths that
mutate the live camp in k.w (harvest, end_of_round, drift), never in describe/state_line (which also see the instance's camps).
"""
from __future__ import annotations

TUTORIAL_VALUE = 8.0          # V0 at the spec default, for documentation and tests


def err(msg: str) -> Exception:
    from charter.actions import ActionError
    return ActionError(msg)


def v0q(camp: dict, cls) -> float:
    """Quantity of the camp's resource worth one tutorial harvest."""
    return float(camp["y_ref"]) / float(cls.value_target)


def qty(camp: dict, cls, units: float) -> float:
    """Tutorial units -> quantity of the camp's resource."""
    return round(units * v0q(camp, cls), 4)


def generous_stock(y_ref: float, ctx: dict, r: float) -> tuple:
    """(K, r) for a camp whose payouts are not drawn from a commons: big enough that the stock cap never binds."""
    return 1000.0 * max(4, int(ctx.get("holders") or 0), int(ctx.get("agents") or 0)) * y_ref, r


def play(camp: dict, default: dict) -> dict:
    """The live play state (created on first mutation)."""
    if "play" not in camp:
        import copy
        camp["play"] = copy.deepcopy(default)
    return camp["play"]


def peek(camp: dict, default: dict) -> dict:
    """Play state for read-only views (never creates it)."""
    return camp.get("play") or default


def entry(aid: str, units: float, camp: dict, cls, private: str, x=None, eff: float = 0.0) -> dict:
    """An end-of-round payout in the framework's shape."""
    return {"agent": aid, "yield": qty(camp, cls, units), "x": list(x or []), "efficiency": eff, "private": private}
