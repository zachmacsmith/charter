"""Linear tutorial camp (an optional type; the standard set uses it as its tutorial slot): yield is linear in 2-3 of a few dials,
the legacy tier-1 rule. Easy to learn, so it anchors calibration: every other type's value per action is measured against it."""
from __future__ import annotations

from charter import camps as C
from charter.camptypes import CampType, register


@register("tutorial")
class Tutorial(CampType):
    role = "tutorial"
    dials, max_level = 4, 9
    preferred_resource = "timber"
    wildcard_ok = False

    @classmethod
    def build(cls, cfg, rng, ctx):
        fn = C.make_function(1, ctx["dials"], ctx["max"], rng)
        fn.pop("family")
        return fn

    def unit(self, k, x):
        return C.unit_value({"family": "linear", **{a: self.p[a] for a in ("dials", "coef", "intercept")}}, list(x), self.camp["max"])

    def best_input(self, k):
        x = [0] * self.camp["dials"]
        for d, c in zip(self.p["dials"], self.p["coef"]):
            x[d] = self.camp["max"] if c > 0 else 0
        return x

    def describe(self, inst):
        c = self.camp
        return (f"x is a list of {c['dials']} dials, each 0..{c['max']}. The yield is a simple, steady function of a few of the dials "
                "(each dial that matters either always helps or always hurts), times stock/capacity, plus a little noise.")

    def truth(self):
        return {"type": self.name, "fn": self.p, "best_input": self.best_input(None)}
