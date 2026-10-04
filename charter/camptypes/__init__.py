"""Camp types (the New Features Update): a camp is a TYPE, which decides how inputs become yield, plus MODIFIERS that apply to any
type (modifiers.py). Active only under `camps.model: types`; the default `legacy` keeps the five fixed tiers of camps.py.

Registry: `TYPES = {name: class}`, filled by the `@register(name)` decorator. Every module in this package (other than the framework
files in `_FRAMEWORK`) is imported on first use, so a new type is one new file: Camps-B's consortium, weak link, catalyst and
partner-choice dilemma slot in without editing anything here. The run composer (framework.compose) draws from the registry by role.

Interface (the contract in docs/parallel_build_contracts.md; framework.py calls exactly these):

    class CampType:
        name, role, resolves, open_to_all, min_holders, dials, max_level, preferred_resource, wildcard_ok, value_target
        def __init__(self, camp: dict, rng: random.Random)      # camp is the live dict in k.w["camps"]; params in camp["fn"]
        @classmethod build(cls, cfg, rng, ctx) -> dict          # hidden parameters at generation (stored in camp["fn"])
        @classmethod scale(cls, cfg, y_ref, ctx, fn) -> float   # the camp's max_yield (yield units) for its value target
        @classmethod stock(cls, cfg, y_ref, ctx, fn, max_yield, r) -> (K, r)   # capacity and regrowth
        @classmethod feasible(cls, ctx) -> bool                 # participation rule at generation (enough right holders?)
        def describe(self, inst) -> str                         # agent-facing; never names the underlying game
        def harvest(self, k, aid, args) -> dict                 # {"yield", "public", "private"} (+ optional "efficiency", "noise")
        def end_of_round(self, k) -> list[dict]                 # sealed inputs: payouts [{"agent", "yield", "x", "efficiency", "private"}]
                                                                #   and public lines [{"public": text}]
        def state_line(self, k, aid) -> str
        def snapshot(self) -> dict                              # monitor-only, per round (snapshots.json)
        def truth(self) -> dict                                 # monitor-only, at the end (ground_truth.json)
      optional:
        def unit(self, k, x) -> float | None                    # noise-free quality in [0, 1] of an (effective) input: dial types
        def best_input(self, k) -> list | None                  # the optimum of `unit` in effective-input space (truth/calibration)
        def drift(self, rng) -> None                            # the drift modifier redraws the hidden rule
        def calibration_input(self, k, aid, strategy, rng)      # strategy: random | learned | fail

All state lives in the camp dict (k.w), never on the instance: a CampType object is a short-lived view built per call by
framework.view(k, cid), with an rng seeded from (seed, camp, round, call count), so checkpoints, resume and dry runs work.
Sealed submissions go in camp["pending"] = {agent: x}; the framework voids those of agents who left play before end_of_round.
"""
from __future__ import annotations

import importlib
import pkgutil
import random

TYPES: dict = {}
ROLES = ("tutorial", "solo_science", "coordination", "social", "wildcard")
_FRAMEWORK = {"framework", "modifiers", "leases", "harness", "calibrate"}
_loaded = False


def register(name: str):
    """Class decorator: TYPES[name] = cls (and cls.name = name)."""
    def deco(cls):
        cls.name = name
        TYPES[name] = cls
        return cls
    return deco


def load_all() -> dict:
    """Import every type module in this package (sorted, so registration order is deterministic). Returns TYPES."""
    global _loaded
    if not _loaded:
        _loaded = True
        for m in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
            if m.name not in _FRAMEWORK and not m.name.startswith("_"):
                importlib.import_module(f"{__name__}.{m.name}")
    return TYPES


def get(name: str):
    load_all()
    if name not in TYPES:
        raise ValueError(f"unknown camp type {name!r}; registered: {', '.join(sorted(TYPES))}")
    return TYPES[name]


class CampType:
    name = "base"
    role = "wildcard"               # tutorial | solo_science | coordination | social | wildcard
    resolves = "immediate"          # immediate: paid when harvested | end_of_round: sealed inputs, paid at end-of-round step 2
    open_to_all = False             # True: no harvest right needed (social games); the Board and the Fixer still cannot take part
    min_holders = 1                 # participation: right holders needed at generation (cartel 4, consortium 4, weak link 3)
    dials = 8                       # input shape: x is a list of `dials` integers 0..max_level
    max_level = 15
    preferred_resource = None       # e.g. "copper" for the cartel: the composer gives it that slot when it can
    wildcard_ok = True              # may be drawn as the wildcard camp
    value_target = None             # value per action relative to the tutorial (None: the role's target from the spec)
    capacity_mult = 1.0             # stock capacity relative to the default stock()
    dial_based = True               # False: conditions, history coupling, survey and split control do not apply

    def __init__(self, camp: dict, rng: random.Random):
        self.camp, self.rng = camp, rng
        self.p = camp["fn"]

    # ---------------------------------------------------------------- generation
    @classmethod
    def build(cls, cfg: dict, rng: random.Random, ctx: dict) -> dict:
        """Hidden parameters (JSON-serialisable). ctx: {"holders": n right holders, "agents": n players, "dials", "max"}."""
        return {}

    @classmethod
    def scale(cls, cfg: dict, y_ref: float, ctx: dict, fn: dict) -> float:
        """max_yield for this camp: y_ref is the yield (in the camp's resource) worth the role's value target per action."""
        return y_ref

    @classmethod
    def stock(cls, cfg: dict, y_ref: float, ctx: dict, fn: dict, max_yield: float, r: float) -> tuple:
        """(capacity K, regrowth r); r arrives drawn from the spec. Default: the stock sustains, at about half capacity, each right
        holder taking `sustain_harvests` (default 1) ideal harvests per round; more than that (the default right allows 2) runs it
        down, so the commons still bites."""
        h = max(1, int(ctx.get("holders") or 1))
        return 2.0 * h * float(cfg.get("sustain_harvests", 1.0)) * y_ref / r * cls.capacity_mult, r

    @classmethod
    def feasible(cls, ctx: dict) -> bool:
        return cls.open_to_all or ctx.get("eligible", 0) >= cls.min_holders

    # ---------------------------------------------------------------- play
    def unit(self, k, x) -> float | None:
        return None

    def best_input(self, k) -> list | None:
        return None

    def harvest(self, k, aid, args) -> dict:
        """Default for dial types that resolve at once: yield = unit(effective x) x max_yield x stock/capacity + noise."""
        c = self.camp
        if self.resolves == "end_of_round":
            c.setdefault("pending", {})[aid] = list(args["x"])
            return {"yield": 0.0, "public": None, "private": f"input {args['x']} submitted; sealed until the end of the round"}
        u = self.unit(k, args.get("x_eff", args["x"]))
        noise = self.rng.gauss(0, c["sigma"])
        y = max(0.0, u * c["max_yield"] * c["S"] / c["K"] + noise)
        return {"yield": y, "efficiency": min(1.0, u / (c.get("norm") or 1.0)), "noise": noise, "public": None, "private": ""}

    def end_of_round(self, k) -> list:
        return []

    def drift(self, rng: random.Random) -> None:
        return None

    def calibration_input(self, k, aid, strategy: str, rng: random.Random) -> list:
        c = self.camp
        if strategy == "learned":
            from charter.camptypes import modifiers as M
            b = self.best_input(k)
            if b is not None:
                return M.to_actual(k, c, b)
        return [rng.randint(0, c["max"]) for _ in range(c["dials"])]

    # ---------------------------------------------------------------- views
    def describe(self, inst: dict) -> str:
        return f"x is a list of {self.camp['dials']} integers, each 0..{self.camp['max']}."

    def state_line(self, k, aid) -> str:
        return ""

    def snapshot(self) -> dict:
        return {}

    def truth(self) -> dict:
        return {"type": self.name, "fn": self.p}
