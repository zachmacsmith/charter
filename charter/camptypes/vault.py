"""Factoring vault (optional wildcard): a public number N = p * q opens a one-time bounty. The first right holder to harvest
with a correct factor takes it all, at once (not sealed), and the vault closes. The answer can be stolen: a Scientist who
finds the factor but holds no right here must hand it to a holder, who may keep the bounty.

Harvest args: {"factor": int}. A wrong factor pays nothing and is told privately.

Calibration: a wildcard, outside the per-action targets. BOUNTY 120 value (15 tutorial harvests) for roughly 3-5 actions
(sandbox runs plus a claim), shared or not by whatever deal the finder and the claimant make. PRIME_BITS 28-32 makes N fall to
Pollard's rho in the sandbox in well under a second but not to trial division by hand.
"""
from __future__ import annotations

from charter.camps import new_semiprime
from charter.camptypes import CampType, register
from charter.camptypes import bcommon as B

BOUNTY = 120.0
PRIME_BITS = (28, 32)


@register("vault")
class Vault(CampType):
    default_resource = "gold"

    def __init__(self, camp, rng):
        super().__init__(camp, rng)
        camp.setdefault("resource", self.default_resource)
        if "hidden" not in camp:
            sp = new_semiprime(rng.randint(*PRIME_BITS), rng)
            camp["hidden"] = {"seed": rng.getrandbits(32), "p": sp["p"], "q": sp["q"]}
            camp["N"] = sp["N"]
        camp.setdefault("play", {"open": True, "winner": None, "round": None, "tries": 0})

    def describe(self, inst=None) -> str:
        c = self.camp
        return (f"Camp {c.get('id')}: a vault with a one-time reward of {BOUNTY:g} value in {c['resource']}. It opens for the first "
                f"harvest that gives a whole number factor of N = {c['N']} (other than 1 and N): harvest with factor=<number>. The "
                f"reward is paid at once to whoever harvests first, and the vault then closes for good.")

    def state_line(self, k, aid) -> str:
        p = self.camp["play"]
        return (f"{self.camp.get('id')}: vault open, N = {self.camp['N']}." if p["open"]
                else f"{self.camp.get('id')}: vault closed (opened by {p['winner']} in round {p['round']}).")

    def harvest(self, k, aid, args) -> dict:
        c, p = self.camp, self.camp["play"]
        if not p["open"]:
            raise B.err(f"the vault at {c.get('id')} is already closed")
        try:
            f = int((args or {}).get("factor"))
        except (TypeError, ValueError):
            raise B.err("give factor=<whole number>")
        p["tries"] += 1
        if 1 < f < c["N"] and c["N"] % f == 0:
            p.update({"open": False, "winner": aid, "round": B.rnd(k)})
            q = B.qty(k, c["resource"], BOUNTY)
            return {"yield": q, "public": f"{aid} opened the vault at {c.get('id')}.",
                    "private": f"Correct: the vault at {c.get('id')} paid you {q:g} {c['resource']}."}
        return {"yield": 0.0, "public": None, "private": f"{f} is not a factor of N at {c.get('id')}."}

    def snapshot(self) -> dict:
        return {"type": "vault", "N": self.camp["N"], **self.camp["play"]}

    def truth(self) -> dict:
        h = self.camp["hidden"]
        return {"p": h["p"], "q": h["q"]}
