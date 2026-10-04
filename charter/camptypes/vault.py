"""Factoring vault (optional wildcard): a public number N = p * q holds a one-time reward. The first right holder to harvest with a
correct factor takes it all, at once (not sealed), and the vault closes. The answer can be stolen: a Scientist who finds the factor
but holds no right here must hand it to a holder, who may keep the reward.

Harvest (pays at once; no x): {"camp": c, "factor": n}. A wrong factor pays nothing.

Calibration: a wildcard outside the per-action targets. BOUNTY = 15 tutorial units (120 value at V0 = 8) for roughly 3-5 actions
(sandbox runs plus a claim), shared or not by whatever deal the finder and the claimant make. PRIME_BITS 28-32 makes N fall to
Pollard's rho in the sandbox in well under a second, but not to trial division by hand.
"""
from __future__ import annotations

from charter.camps import new_semiprime
from charter.camptypes import CampType, register
from charter.camptypes import _bcommon as B

BOUNTY = 15.0                 # tutorial units
PRIME_BITS = (28, 32)
PLAY = {"open": True, "winner": None, "round": None, "tries": 0}


@register("vault")
class Vault(CampType):
    role = "wildcard"
    resolves = "immediate"
    dials, max_level = 0, 0
    value_target = 1.0
    dial_based = False
    extra_args = ("factor",)

    @classmethod
    def build(cls, cfg, rng, ctx):
        bits = cfg.get("prime_bits") or rng.randint(*PRIME_BITS)
        return new_semiprime(int(bits), rng)

    @classmethod
    def stock(cls, cfg, y_ref, ctx, fn, max_yield, r):
        return B.generous_stock(y_ref, ctx, r)

    @staticmethod
    def check_args(k, aid, camp, x, extra):
        if not B.peek(camp, PLAY)["open"]:
            raise B.err(f"the vault at {camp['id']} is already open and empty")
        try:
            int(extra.get("factor"))
        except (TypeError, ValueError):
            raise B.err('give "factor": a whole number')

    def describe(self, inst=None) -> str:
        c = self.camp
        return (f"A vault holding a one-time reward of {B.qty(c, type(self), BOUNTY):.3g} {c['resource']}. Harvest with \"factor\": a "
                f"number (no x). N = {self.p['N']}. The reward goes to the first correct harvest; then the vault is empty for good.")

    def state_line(self, k, aid) -> str:
        p = B.peek(self.camp, PLAY)
        return f"vault closed, N = {self.p['N']}" if p["open"] else f"vault empty (opened by {p['winner']} in round {p['round']})"

    def harvest(self, k, aid, args) -> dict:
        c = self.camp
        p = B.play(c, PLAY)
        f = int(args.get("factor"))
        p["tries"] += 1
        N = self.p["N"]
        if 1 < f < N and N % f == 0 and p["open"]:
            p.update({"open": False, "winner": aid, "round": k.r})
            k.log("camp_round", None, {"camp": c["id"], "text": f"{c['id']}: {aid} opened the vault"}, vis="public")
            return {"yield": B.qty(c, type(self), BOUNTY), "efficiency": 1.0, "noise": 0.0, "public": None,
                    "private": "(correct factor: the vault paid you)"}
        return {"yield": 0.0, "efficiency": 0.0, "noise": 0.0, "public": None, "private": f"({f} is not a factor of N)"}

    def snapshot(self) -> dict:
        return dict(B.peek(self.camp, PLAY))

    def truth(self) -> dict:
        return {"type": self.name, "fn": self.p, **B.peek(self.camp, PLAY)}
