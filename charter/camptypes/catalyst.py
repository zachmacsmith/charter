"""Catalyst: Workers set dials (a smooth hidden peak), but full yield also needs this round's catalyst number, which only a
computation can produce: the smallest n >= 0 such that sha256("<batch code>:<n>") in hex starts with DIFFICULTY zeros. The
batch code is public and new each round. That is a few thousand hashes: instant in the sandbox, impossible by hand, and not
guessable.

Science role: computing the catalyst each round (a sandbox holder). Coordination role: Worker-Scientist pairs; the camp makes
the split trustless with an optional `credit` argument that pays a named partner CREDIT_SHARE of each catalysed harvest.

Harvest args (one harvest = one action): {"x": [DIALS ints 0..MAXV], "catalyst": int (optional), "credit": agent (optional)}.
Paid at once: value = PEAK_VALUE * peak(x), times 1 with the right catalyst or NO_CATALYST without it. With the right catalyst
and a credit to another agent, CREDIT_SHARE of the value is held back and paid to that agent at the end of the round.

Calibration (value per action; tutorial = 8, see bcommon):
  a working pair spends about 4 actions per round (Worker: 2 harvests; Scientist: 1 sandbox run + 1 message) for
  2 x PEAK_VALUE x ~0.9 = 79 value, i.e. ~20 per action = 2.5x tutorial;
  without the catalyst a Worker's harvest pays PEAK_VALUE x NO_CATALYST = 4.4 at the peak, i.e. 0.55x.
"""
from __future__ import annotations

import hashlib
import math

from charter.camptypes import CampType, register
from charter.camptypes import bcommon as B

DIALS = 4
MAXV = 15
PEAK_VALUE = 44.0
NO_CATALYST = 0.1
CREDIT_SHARE = 0.3
DIFFICULTY = 3                 # leading hex zeros: ~4096 hashes on average
WIDTH = (3.0, 4.5)


def catalyst_for(code: str, difficulty: int = DIFFICULTY) -> int:
    pre = "0" * difficulty
    n = 0
    while not hashlib.sha256(f"{code}:{n}".encode()).hexdigest().startswith(pre):
        n += 1
    return n


@register("catalyst")
class Catalyst(CampType):
    default_resource = "copper"

    def __init__(self, camp, rng):
        super().__init__(camp, rng)
        camp.setdefault("resource", self.default_resource)
        if "hidden" not in camp:
            camp["hidden"] = {"seed": rng.getrandbits(32), "center": [rng.randint(2, MAXV - 2) for _ in range(DIALS)],
                              "width": round(rng.uniform(*WIDTH), 3), "cache": {}}
        camp.setdefault("play", {"credits": {}, "harvests": 0, "catalysed": 0})

    # ------------------------------------------------------------------ the per-round value
    def code(self, r: int) -> str:
        return hashlib.sha256(f"{self.camp['hidden']['seed']}|{self.camp.get('id')}|code|{r}".encode()).hexdigest()[:10]

    def catalyst(self, r: int) -> int:
        cache = self.camp["hidden"]["cache"]
        if cache.get("round") != r:
            cache.clear()
            cache.update({"round": r, "value": catalyst_for(self.code(r))})
        return cache["value"]

    def peak(self, x) -> float:
        h = self.camp["hidden"]
        return math.exp(-sum((a - b) ** 2 for a, b in zip(x, h["center"])) / (2 * h["width"] ** 2))

    # ------------------------------------------------------------------ text
    def describe(self, inst=None) -> str:
        c = self.camp
        return (f"Camp {c.get('id')}: a reactor with {DIALS} dials, each 0..{MAXV}. Output rises smoothly as the dials approach a "
                f"hidden best setting. The reactor also needs this round's catalyst number: the smallest whole number n >= 0 such "
                f"that the SHA-256 hash (hex) of the text '<batch code>:<n>' starts with {'0' * DIFFICULTY}. The batch code is "
                f"published each round. Harvest with x=[{DIALS} dials], catalyst=n. Without the right catalyst a harvest yields "
                f"only {NO_CATALYST:.0%} of its output. Optionally add credit=<agent>: when the catalyst is right, "
                f"{CREDIT_SHARE:.0%} of that harvest goes to the named agent at the end of the round. At its best setting a "
                f"catalysed harvest is worth about {PEAK_VALUE:g} value, paid in {c['resource']}.")

    def state_line(self, k, aid) -> str:
        return f"{self.camp.get('id')}: this round's batch code is '{self.code(B.rnd(k))}'."

    # ------------------------------------------------------------------ play
    def harvest(self, k, aid, args) -> dict:
        args = args or {}
        c, p = self.camp, self.camp["play"]
        x = B.ints(args.get("x"), DIALS, 0, MAXV, "x")
        r = B.rnd(k)
        cat = args.get("catalyst")
        try:
            ok = cat is not None and int(cat) == self.catalyst(r)
        except (TypeError, ValueError):
            ok = False
        value = PEAK_VALUE * self.peak(x) * (1.0 if ok else NO_CATALYST)
        credit = args.get("credit")
        held = 0.0
        if ok and credit and credit != aid:
            if hasattr(k, "w") and credit not in k.w.get("agents", {credit: 1}):
                raise B.err(f"no such agent to credit: {credit}")
            held = value * CREDIT_SHARE
            p["credits"][credit] = round(p["credits"].get(credit, 0.0) + held, 3)
        p["harvests"] += 1
        p["catalysed"] += int(ok)
        q = B.qty(k, c["resource"], value - held)
        note = "catalyst accepted" if ok else ("wrong catalyst" if cat is not None else "no catalyst")
        extra = f"; {held:.3g} value credited to {credit}" if held else ""
        return {"yield": q, "public": None, "private": f"Harvested {q:g} {c['resource']} at {c.get('id')} with x={x} ({note}{extra})."}

    def end_of_round(self, k) -> list[dict]:
        c, p = self.camp, self.camp["play"]
        cr, p["credits"] = p["credits"], {}
        out = []
        for a, v in cr.items():
            out.append(B.payout(a, c["resource"], B.qty(k, c["resource"], v), f"catalyst_credit:{c.get('id')}"))
            out.append(B.private(a, f"You were credited {v:.3g} value for catalysed harvests at {c.get('id')}."))
        return out

    # ------------------------------------------------------------------ records
    def snapshot(self) -> dict:
        p = self.camp["play"]
        return {"type": "catalyst", "harvests": p["harvests"], "catalysed": p["catalysed"], "pending_credits": dict(p["credits"])}

    def truth(self) -> dict:
        h = self.camp["hidden"]
        return {"center": list(h["center"]), "width": h["width"], "catalyst_round": h["cache"].get("round"),
                "catalyst": h["cache"].get("value")}
