"""Catalyst (science + coordination): Workers set dials (a smooth hidden peak), but full yield also needs this round's catalyst
number, which only a computation can produce: the smallest n >= 0 such that sha256("<batch code>:<n>") in hex starts with
DIFFICULTY zeros. The batch code is public and new each round (state line). That is a few thousand hashes: instant in the sandbox,
impossible by hand, and not guessable.

Science role: computing the catalyst each round (a sandbox holder). Coordination role: Worker-Scientist pairs. The camp makes the
split trustless with an optional "credit" argument that pays a named partner CREDIT_SHARE of each catalysed harvest at the end of
the round. Participation: at least one Worker holder and one sandbox holder in the world (feasible()).

Harvest (pays at once): {"camp": c, "x": [4 dials 0..15], "catalyst": n (optional), "credit": "Name" (optional)}.
  yield = PEAK x peak(x) tutorial units, x 1 with the right catalyst or x NO_CATALYST without it; with the right catalyst and a
  credit to another agent, CREDIT_SHARE of it is held back and paid to that agent at the end of the round.

Calibration, in tutorial units (V0 = 8 value by default; see _bcommon):
  a working pair spends about 4 actions per round (Worker: 2 harvests; Scientist: 1 sandbox run + 1 message) for 2 x PEAK x ~0.9
  = 9.9 units, i.e. ~2.5 per action; without the catalyst a Worker's harvest at the peak pays PEAK x NO_CATALYST = 0.55.
"""
from __future__ import annotations

import hashlib
import math

from charter.camptypes import CampType, register
from charter.camptypes import _bcommon as B

PEAK = 5.5                    # tutorial units for a catalysed harvest at the best setting
NO_CATALYST = 0.1
CREDIT_SHARE = 0.3
DIFFICULTY = 3                # leading hex zeros: ~4096 hashes on average
WIDTH = (3.0, 4.5)


def catalyst_for(code: str, difficulty: int = DIFFICULTY) -> int:
    pre = "0" * difficulty
    n = 0
    while not hashlib.sha256(f"{code}:{n}".encode()).hexdigest().startswith(pre):
        n += 1
    return n


@register("catalyst")
class Catalyst(CampType):
    role = "coordination"
    resolves = "immediate"
    min_holders = 1
    dials, max_level = 4, 15
    preferred_resource = None
    value_target = 2.5
    dial_based = True
    extra_args = ("catalyst", "credit")

    @classmethod
    def build(cls, cfg, rng, ctx):
        mx = int(ctx.get("max", cls.max_level))
        return {"seed": rng.getrandbits(32), "center": [rng.randint(2, mx - 2) for _ in range(int(ctx.get("dials", cls.dials)))],
                "width": round(rng.uniform(*WIDTH) * (mx + 1) / 16, 4), "difficulty": int(cfg.get("difficulty", DIFFICULTY))}

    @classmethod
    def feasible(cls, ctx):
        return ctx.get("eligible", 0) >= 1 and ctx.get("sandbox", 1) >= 1

    @classmethod
    def stock(cls, cfg, y_ref, ctx, fn, max_yield, r):
        return B.generous_stock(y_ref, ctx, r)

    @staticmethod
    def check_args(k, aid, camp, x, extra):
        if extra.get("credit") not in (None, "") and str(extra["credit"]) not in k.players():
            raise B.err(f"no such agent to credit: {extra['credit']}")

    # ------------------------------------------------------------------ the per-round value
    def code(self, r: int) -> str:
        return hashlib.sha256(f"{self.p['seed']}|{self.camp['id']}|code|{r}".encode()).hexdigest()[:10]

    def catalyst(self, r: int) -> int:
        cache = self.p.setdefault("cache", {})
        if cache.get("round") != r:
            cache.clear()
            cache.update({"round": r, "value": catalyst_for(self.code(r), self.p["difficulty"])})
        return cache["value"]

    def unit(self, k, x) -> float:
        return math.exp(-sum((a - b) ** 2 for a, b in zip(x, self.p["center"])) / (2 * self.p["width"] ** 2))

    def best_input(self, k):
        return list(self.p["center"])

    # ------------------------------------------------------------------ text
    def describe(self, inst=None) -> str:
        c = self.camp
        u = B.v0q(c, type(self))
        return (f"A reactor with {c['dials']} dials (x, each 0..{c['max']}). Output rises smoothly as the dials approach a hidden best "
                f"setting. The reactor also needs this round's catalyst number: the smallest whole number n >= 0 such that the SHA-256 "
                f"hash (hex digest) of the text '<batch code>:<n>' starts with {'0' * self.p['difficulty']}. The batch code is shown "
                f"each round. Harvest with x and \"catalyst\": n. Without the right catalyst a harvest yields only {NO_CATALYST:.0%} of "
                f"its output. Optionally add \"credit\": \"Name\": when the catalyst is right, {CREDIT_SHARE:.0%} of that harvest goes "
                f"to the named agent at the end of the round. At its best setting a catalysed harvest yields about {PEAK * u:.3g} "
                f"{c['resource']}.")

    def state_line(self, k, aid) -> str:
        return f"this round's batch code is '{self.code(k.r)}'"

    # ------------------------------------------------------------------ play
    def harvest(self, k, aid, args) -> dict:
        c = self.camp
        cat = args.get("catalyst")
        try:
            ok = cat is not None and int(cat) == self.catalyst(k.r)
        except (TypeError, ValueError):
            ok = False
        u = self.unit(k, args.get("x_eff", args["x"]))
        units = PEAK * u * (1.0 if ok else NO_CATALYST)
        credit = args.get("credit")
        held = 0.0
        if ok and credit and credit != aid:
            held = units * CREDIT_SHARE
            cr = B.play(c, {"credits": {}})["credits"]
            cr[credit] = round(cr.get(credit, 0.0) + held, 6)
        st = B.play(c, {"credits": {}})
        st["harvests"] = st.get("harvests", 0) + 1
        st["catalysed"] = st.get("catalysed", 0) + int(ok)
        note = "catalyst accepted" if ok else ("wrong catalyst" if cat is not None else "no catalyst")
        if held:
            note += f"; {B.qty(c, type(self), held):.3g} credited to {credit} at the end of the round"
        return {"yield": B.qty(c, type(self), units - held), "efficiency": u * (1.0 if ok else NO_CATALYST), "noise": 0.0,
                "public": None, "private": f"({note})"}

    def end_of_round(self, k) -> list:
        c = self.camp
        if "play" not in c or not c["play"]["credits"]:
            return []
        cr, c["play"]["credits"] = c["play"]["credits"], {}
        return [B.entry(a, v, c, type(self), f"credited {B.qty(c, type(self), v):.3g} for catalysed harvests by others")
                for a, v in sorted(cr.items())]

    def drift(self, rng) -> None:
        self.p["center"] = [rng.randint(2, self.camp["max"] - 2) for _ in range(self.camp["dials"])]

    # ------------------------------------------------------------------ records
    def snapshot(self) -> dict:
        p = B.peek(self.camp, {"credits": {}})
        return {"harvests": p.get("harvests", 0), "catalysed": p.get("catalysed", 0), "pending_credits": dict(p["credits"])}

    def truth(self) -> dict:
        return {"type": self.name, "fn": self.p, "best_input": self.best_input(None)}
