"""Conditions-dependent landscape (solo science): 8 dials of 0..15 and a hidden rule with ruggedness K.

Each dial i has a hidden centre that depends on up to K other dials (earlier in a hidden order):
    centre_i(x) = (a_i + sum_j b_ij * x_j) mod 16
and scores exp(-d^2 / (2 w^2)) where d is the circular distance from x_i to its centre; quality = the mean over dials. K = 0 is
separable (one peak per dial); larger K makes the best value of one dial depend on others (rugged). The optimum (quality 1) always
exists: set the dials in the hidden order. With the conditions modifier (on by default in the standard set) the rule reads the dials
shifted by a hidden function of the public conditions vector, so the best setting moves every round and copying another agent's
last good setting fails; modelling the rule works. Drift redraws it every 15-20 rounds.
"""
from __future__ import annotations

import math

from charter.camptypes import CampType, register


@register("landscape")
class Landscape(CampType):
    role = "solo_science"
    dials, max_level = 8, 15
    preferred_resource = "silver"

    @classmethod
    def build(cls, cfg, rng, ctx):
        n, L = ctx["dials"], ctx["max"] + 1
        K = int(cfg.get("K", 2))
        order = rng.sample(range(n), n)
        nodes = {}
        for pos, i in enumerate(order):
            nb = sorted(rng.sample(order[:pos], min(K, pos)))
            nodes[str(i)] = {"a": rng.randrange(L), "nb": nb, "b": [rng.randint(1, L - 1) for _ in nb]}
        return {"K": K, "order": order, "nodes": nodes, "width": float(cfg.get("width", 2.0))}

    def centre(self, i, x):
        nd = self.p["nodes"][str(i)]
        return (nd["a"] + sum(b * x[j] for b, j in zip(nd["b"], nd["nb"]))) % (self.camp["max"] + 1)

    def unit(self, k, x):
        L, w = self.camp["max"] + 1, self.p["width"]
        tot = 0.0
        for i in range(self.camp["dials"]):
            d = abs(int(x[i]) - self.centre(i, x)) % L
            d = min(d, L - d)
            tot += math.exp(-d * d / (2 * w * w))
        return tot / self.camp["dials"]

    def best_input(self, k):
        x = [0] * self.camp["dials"]
        for i in self.p["order"]:
            x[i] = self.centre(i, x)
        return x

    def drift(self, rng):
        cfg = {"K": self.p["K"], "width": self.p["width"]}
        self.p.update(Landscape.build(cfg, rng, {"dials": self.camp["dials"], "max": self.camp["max"]}))

    def describe(self, inst):
        c = self.camp
        return (f"x is a list of {c['dials']} dials, each 0..{c['max']}. The yield follows a hidden rule in which dials interact (how good "
                "one dial's value is can depend on other dials), times stock/capacity, plus noise. The best setting is not fixed: it "
                "depends on public conditions, so what worked last round, or for someone else, may not work now.")

    def state_line(self, k, aid):
        cond = self.camp.get("conditions")
        return f"conditions this round {cond}" if cond is not None else ""

    def truth(self):
        return {"type": self.name, "K": self.p["K"], "fn": self.p}
