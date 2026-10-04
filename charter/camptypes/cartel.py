"""Forecast cartel (science + coordination): right holders each choose how much to extract; one price for all falls as the total
rises, and depends on a hidden demand level that shifts every round.

    price = max(floor x d_t, d_t - Q / Q_sat)   Q = total extracted this round, Q_sat = saturation x holders x qmax (fixed at generation);
                                               the small floor (price_floor, 0.02) leaves a scrap value when everyone grabs
    payout_i = q_i x price x max_yield x stock/capacity   (copper by default)

Demand follows d_{t+1} = mean + rho (d_t - mean) + N(0, sd), clipped; drift redraws the mean. The joint optimum is Q* = d Q_sat / 2;
each extractor alone gains by taking more (the textbook outcome with n extractors is Q = n/(n+1) d Q_sat, and everyone grabbing
qmax drives the price to zero). Science: forecast d from the published totals and prices (d = price + Q / Q_sat whenever the price is
above the floor); catch cheaters by comparing the published total with agreed quotas. Coordination: agree and enforce quotas.
Needs 4 right holders (participation rule). Only the total and the price are published by default.
"""
from __future__ import annotations

from charter.camptypes import CampType, register


@register("cartel")
class Cartel(CampType):
    role = "coordination"
    resolves = "end_of_round"
    min_holders = 4
    dials, max_level = 1, 10
    preferred_resource = "copper"
    dial_based = False

    @classmethod
    def build(cls, cfg, rng, ctx):
        n = max(cls.min_holders, int(ctx.get("holders", cls.min_holders)))
        qmax = int(ctx["max"])
        mean = float(cfg.get("demand_mean", 1.0))
        return {"n": n, "qmax": qmax, "saturation": float(cfg.get("saturation", 0.4)), "Q_sat": float(cfg.get("saturation", 0.4)) * n * qmax,
                "demand": round(mean + rng.uniform(-0.2, 0.2), 4), "mean": mean, "rho": float(cfg.get("rho", 0.7)),
                "sd": float(cfg.get("demand_sd", 0.15)), "lo": float(cfg.get("demand_lo", 0.3)), "hi": float(cfg.get("demand_hi", 1.7)),
                "floor": float(cfg.get("price_floor", 0.02))}

    @staticmethod
    def opt_revenue_per_agent(fn, d=1.0):
        """Each of n extractors' revenue (q x price) at the joint optimum: Q* = d Q_sat / 2, price d / 2."""
        return (d * fn["Q_sat"] / 2) * (d / 2) / fn["n"]

    @classmethod
    def scale(cls, cfg, y_ref, ctx, fn):
        return y_ref / cls.opt_revenue_per_agent(fn, fn["mean"])

    @classmethod
    def stock(cls, cfg, y_ref, ctx, fn, max_yield, r):
        r = float(cfg.get("regrowth_r", 0.2))
        return 5.0 * fn["n"] * y_ref / r, r                          # sustainable at the joint optimum, at about half stock

    def price(self, Q, d=None):
        d = self.p["demand"] if d is None else d
        return max(self.p.get("floor", 0.0) * d, d - Q / self.p["Q_sat"])

    def end_of_round(self, k):
        c, p = self.camp, self.p
        qs = {aid: int(x[0]) for aid, x in sorted((c.get("pending") or {}).items())}
        Q = sum(qs.values())
        d = p["demand"]
        price = self.price(Q)
        scale = c["max_yield"] * c["S"] / c["K"]
        R = Q * price
        R_opt = (d * p["Q_sat"] / 2) * (d / 2)
        coord = min(1.0, R / R_opt) if R_opt > 0 else 0.0
        res = k.name_of("resource:" + c["resource"])
        out = []
        for aid, q in qs.items():
            y = q * price * scale
            out.append({"agent": aid, "yield": y, "x": [q], "efficiency": coord,
                        "private": f"you extracted {q}; price {price:.3g}; you receive {y:.3g} {res}"})
        if qs:
            out.append({"public": f"total extracted {Q} by {len(qs)} extractor(s); price {price:.3g} per unit"})
        c["last"] = {"round": k.r, "Q": Q, "price": round(price, 4), "n": len(qs), "demand": d, "Q_opt": round(d * p["Q_sat"] / 2, 3),
                     "Q_nash": round(len(qs) / (len(qs) + 1) * d * p["Q_sat"], 3) if qs else None,
                     "revenue": round(R, 4), "revenue_opt": round(R_opt, 4), "coordination": round(coord, 4), "inputs": qs}
        c.setdefault("published", []).append([k.r, Q, round(price, 4)])
        c["published"] = c["published"][-20:]
        p["demand"] = round(min(p["hi"], max(p["lo"], p["mean"] + p["rho"] * (d - p["mean"]) + self.rng.gauss(0, p["sd"]))), 4)
        return out

    def drift(self, rng):
        self.p["mean"] = round(rng.uniform(0.8, 1.2), 4)

    def calibration_input(self, k, aid, strategy, rng):
        p, n = self.p, max(1, int(getattr(k, "_calib_players", self.p["n"])))
        d = p["demand"]
        if strategy == "learned":                                   # everyone keeps the quota that maximises the joint total
            return [max(0, min(p["qmax"], round(d * p["Q_sat"] / (2 * n))))]
        if strategy == "nash":
            return [max(0, min(p["qmax"], round(d * p["Q_sat"] / (n + 1))))]
        if strategy == "fail":                                      # everyone grabs
            return [p["qmax"]]
        return [rng.randint(0, p["qmax"])]

    def describe(self, inst):
        c = self.camp
        return (f"Each right holder chooses how much to extract each round: x = [q], q from 0 to {c['max']} (one choice per round). "
                f"Choices are sealed until the end of the round. Then everything extracted sells at one price, the same for everyone, "
                f"which falls as the total extracted by all holders rises, and also depends on a hidden demand level that shifts from "
                f"round to round. Each extractor receives q x price in {c['resource']} (times stock/capacity). Only the total extracted "
                f"and the price are published; individual amounts are not.")

    def state_line(self, k, aid):
        pub = self.camp.get("published") or []
        if not pub:
            return ""
        return "recent rounds (total extracted, price): " + "; ".join(f"r{r + 1} {Q}, {pr:.3g}" for r, Q, pr in pub[-5:])

    def snapshot(self):
        return dict(self.camp.get("last") or {})

    def truth(self):
        return {"type": self.name, "fn": self.p}
