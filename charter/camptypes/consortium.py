"""Data consortium (science + coordination): each reading returns a noisy weighted sum of the reader's settings with hidden weights;
only submitting the exact weights pays, and the pool is split by a rule set in the camp.

Science role: solving for the weights from pooled readings (least squares, then rounding). Coordination role: taking *varied*
readings (identical settings add no information), pooling them, and agreeing who submits and how the pool is split.
Needs 4 right holders (participation rule).

Harvest (one action each; readings pay at once, so the right's harvests_per_right apply):
  {"camp": c, "x": [8 ints 0..15]}                  a reading: sum(w_i * x_i) + noise, private. Pays nothing.
  {"camp": c, "x": [8 ints 0..15], "submit": true}  a sealed claim that x IS the weights, checked at the end of the round.

End of round: if any claim this round equals the hidden weights, the pool is paid by the camp's split rule, new weights are drawn
and a new season starts; otherwise the pool shrinks by POOL_DECAY. Every claimant learns privately whether it was right; a solve
is announced publicly (without the weights). Drift redraws the weights mid-season (the pool and reading counts stay).

Split rules (drawn per camp, public in the description):
  by_readings  SUBMIT_SHARE to the correct claimant(s), the rest in proportion to this season's readings by each reader;
  equal        SUBMIT_SHARE to the correct claimant(s), the rest equally among this season's readers;
  winner       the correct claimant(s) take the whole pool.

Calibration, in tutorial units (V0 = 8 value by default; see _bcommon):
  NOISE_SIGMA 3: 16 random readings recover all 8 weights by least squares and rounding ~83% of the time (12 readings ~55%,
  8 ~7%; better-designed settings do better). Coordinated: 4 holders x 2 readings pool 16 readings in two rounds and claim in
  round 3: 17 actions share POOL_START x POOL_DECAY^2 = 70 x 0.608 = 42.6 units = 2.5 per action. Failed coordination: one holder
  alone needs 8 rounds of readings and claims in round 9: 17 actions earn 70 x 0.78^8 = 9.6 units = 0.56 per action.
"""
from __future__ import annotations

from charter.camptypes import CampType, register
from charter.camptypes import _bcommon as B

NOISE_SIGMA = 3.0
POOL_START = 70.0             # tutorial units
POOL_DECAY = 0.78             # per round without a solve
POOL_FLOOR = 0.05             # the pool never falls below this fraction of POOL_START
SUBMIT_SHARE = 0.2
SPLITS = ("by_readings", "equal", "winner")
SPLIT_WEIGHTS = (0.4, 0.4, 0.2)
PLAY = {"season": 1, "started": False, "pool": POOL_START, "readings": {}, "claims": [], "solved": []}


@register("consortium")
class Consortium(CampType):
    role = "coordination"
    resolves = "immediate"            # readings pay (nothing) at once; claims are sealed in camp["play"] and resolved at end of round
    min_holders = 4
    dials, max_level = 8, 15
    preferred_resource = "gold"
    value_target = 2.5
    dial_based = False
    extra_args = ("submit",)

    @classmethod
    def build(cls, cfg, rng, ctx):
        mx = int(ctx.get("max", cls.max_level))
        return {"w": [rng.randint(0, mx) for _ in range(int(ctx.get("dials", cls.dials)))],
                "split": cfg.get("split") or rng.choices(SPLITS, SPLIT_WEIGHTS)[0], "noise_sigma": float(cfg.get("noise_sigma", NOISE_SIGMA))}

    @classmethod
    def stock(cls, cfg, y_ref, ctx, fn, max_yield, r):
        return B.generous_stock(y_ref, ctx, r)

    # ------------------------------------------------------------------ text
    def describe(self, inst=None) -> str:
        c, n, mx = self.camp, self.camp["dials"], self.camp["max"]
        pool = B.qty(c, type(self), POOL_START)
        rule = {"by_readings": f"{SUBMIT_SHARE:.0%} goes to whoever submitted the correct weights, and the rest is shared in proportion "
                               f"to how many readings each participant took this season",
                "equal": f"{SUBMIT_SHARE:.0%} goes to whoever submitted the correct weights, and the rest is shared equally among "
                         f"everyone who took at least one reading this season",
                "winner": "whoever submitted the correct weights takes the whole pool (shared if several did in the same round)"}[self.p["split"]]
        return (f"A measurement station with {n} settings (x, each 0..{mx}) and {n} hidden whole-number weights (each 0..{mx}). A reading "
                f"(harvest with x) returns the sum of each setting times its weight, plus random noise (standard deviation about "
                f"{self.p['noise_sigma']:g}); readings are private and pay nothing. To claim the pool, harvest with x = the weights and "
                f"\"submit\": true; claims are sealed until the end of the round. If a claim is exactly right, the pool is paid out and "
                f"new weights are drawn. The pool starts at {pool:.3g} {c['resource']} and shrinks to {POOL_DECAY:.0%} of itself at the "
                f"end of each round it is not won. How it is split: {rule}. Readings at the same settings repeat the same information.")

    def state_line(self, k, aid) -> str:
        p = B.peek(self.camp, PLAY)
        return (f"pool {B.qty(self.camp, type(self), p['pool']):.3g} {self.camp['resource']} (season {p['season']}); readings this "
                f"season: {sum(p['readings'].values())} in total, {p['readings'].get(aid, 0)} by you")

    # ------------------------------------------------------------------ play
    def harvest(self, k, aid, args) -> dict:
        p = B.play(self.camp, PLAY)
        x = list(args["x"])
        p["started"] = True
        if args.get("submit") not in (None, False, 0, "false", "no"):
            p["claims"].append({"agent": aid, "w": x})
            return {"yield": 0.0, "efficiency": 0.0, "noise": 0.0, "public": None,
                    "private": f"Claim {x} recorded; it is checked at the end of the round."}
        noise = self.rng.gauss(0, self.p["noise_sigma"])
        val = round(sum(a * b for a, b in zip(x, self.p["w"])) + noise, 2)
        p["readings"][aid] = p["readings"].get(aid, 0) + 1
        return {"yield": 0.0, "efficiency": 0.0, "noise": noise, "public": None, "private": f"Reading with x={x}: {val}"}

    def end_of_round(self, k) -> list:
        c, h = self.camp, self.p
        if "play" not in c:
            return []
        p = c["play"]
        claims, p["claims"] = p["claims"], []
        winners = []
        for s in claims:
            if s["w"] == h["w"] and s["agent"] not in winners and k.w["agents"].get(s["agent"], {}).get("departed") is None:
                winners.append(s["agent"])
        if not winners:
            if p["started"]:
                p["pool"] = round(max(POOL_START * POOL_FLOOR, p["pool"] * POOL_DECAY), 4)
            if not claims:
                return []
            return [B.entry(s["agent"], 0.0, c, type(self), f"your claim {s['w']} was not correct", s["w"]) for s in claims]
        shares = self.split(p["pool"], winners, p["readings"], h["split"])
        out = []
        for aid in sorted(shares):
            why = ("your claim was correct; " if aid in winners else "the weights were found; ") + "your share of the pool"
            out.append(B.entry(aid, shares[aid], c, type(self), why, eff=1.0 if aid in winners else 0.0))
        for s in claims:
            if s["agent"] not in shares:
                out.append(B.entry(s["agent"], 0.0, c, type(self), f"your claim {s['w']} was not correct", s["w"]))
        out.append({"public": f"the weights were found and the pool of {B.qty(c, type(self), p['pool']):.3g} paid out; new weights drawn"})
        p["solved"].append({"season": p["season"], "round": k.r, "winners": winners, "pool": p["pool"], "w": list(h["w"])})
        h["w"] = [self.rng.randint(0, c["max"]) for _ in range(c["dials"])]
        p.update({"season": p["season"] + 1, "started": False, "pool": POOL_START, "readings": {}})
        return out

    @staticmethod
    def split(pool: float, winners: list, readings: dict, rule: str) -> dict:
        """Tutorial units to each agent. Winners share SUBMIT_SHARE (all of it under 'winner', or with no readers); readers share
        the rest by the rule."""
        shares = {a: 0.0 for a in list(winners) + list(readings)}
        readers = {a: n for a, n in readings.items() if n > 0}
        sub = 1.0 if rule == "winner" or not readers else SUBMIT_SHARE
        for a in winners:
            shares[a] += pool * sub / len(winners)
        rest = pool * (1 - sub)
        if rest > 0:
            tot = sum(readers.values())
            for a, n in readers.items():
                shares[a] += rest * (n / tot if rule == "by_readings" else 1 / len(readers))
        return {a: round(v, 4) for a, v in shares.items()}

    def drift(self, rng) -> None:
        self.p["w"] = [rng.randint(0, self.camp["max"]) for _ in range(self.camp["dials"])]

    def calibration_input(self, k, aid, strategy, rng):
        return list(self.p["w"]) if strategy == "learned" else [rng.randint(0, self.camp["max"]) for _ in range(self.camp["dials"])]

    # ------------------------------------------------------------------ records
    def snapshot(self) -> dict:
        p = B.peek(self.camp, PLAY)
        return {"split": self.p["split"], "season": p["season"], "pool_units": p["pool"], "readings": dict(p["readings"]),
                "pending_claims": len(p["claims"]), "solves": len(p["solved"])}

    def truth(self) -> dict:
        return {"type": self.name, "fn": self.p, "solved": list(B.peek(self.camp, PLAY)["solved"])}
