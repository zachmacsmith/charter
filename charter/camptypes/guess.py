"""Guess the crowd (optional social game): each round entrants name a whole number 0..100, sealed. The target is a published
fraction (drawn per camp from FRACTIONS) of the entrants' average; whoever is closest takes the round's pot (ties split).

Open to every agent (no harvest right needed).

Harvest args: {"number": 0..100}; the last entry of the round counts.

Calibration (value per action; tutorial = 8, see bcommon): the pot is POT_PER_ENTRY x entrants, so the mean payout per entry
is exactly 8 (1x) and the spread is large (one winner takes all). With fewer than MIN_ENTRANTS entrants nobody wins and each
gets SMALL (0.5x).
"""
from __future__ import annotations

from charter.camptypes import CampType, register
from charter.camptypes import bcommon as B

POT_PER_ENTRY = 8.0
MIN_ENTRANTS = 3
SMALL = 4.0
FRACTIONS = (0.6, 0.7, 0.8)


@register("guess")
class Guess(CampType):
    default_resource = "timber"
    open_to_all = True

    def __init__(self, camp, rng):
        super().__init__(camp, rng)
        camp.setdefault("resource", self.default_resource)
        camp.setdefault("open", True)
        if "hidden" not in camp:
            camp["hidden"] = {"seed": rng.getrandbits(32)}
        camp.setdefault("fraction", rng.choice(FRACTIONS))
        camp.setdefault("play", {"entries": {}, "history": []})

    def describe(self, inst=None) -> str:
        c = self.camp
        return (f"Camp {c.get('id')}: a guessing booth open to everyone. Each round, harvest with number=<whole number 0..100>; "
                f"entries are sealed and your last one counts. At the end of the round the target is {c['fraction']:g} times the "
                f"average of all entries, and the entry closest to it takes the pot of {POT_PER_ENTRY:g} value per entrant (ties "
                f"split). With fewer than {MIN_ENTRANTS} entrants there is no contest and each entrant gets {SMALL:g} value. The "
                f"average, target and winners are published. Paid in {c['resource']}.")

    def state_line(self, k, aid) -> str:
        p = self.camp["play"]
        s = f"{self.camp.get('id')}: "
        if p["history"]:
            h = p["history"][-1]
            s += f"last round {h['n']} entrants, average {h['mean']:.3g}, target {h['target']:.3g}, won by {', '.join(h['winners']) or 'nobody'}. "
        e = p["entries"].get(aid)
        return s + (f"Your entry this round: {e}." if e is not None else "You have no entry this round.")

    def harvest(self, k, aid, args) -> dict:
        try:
            n = int((args or {}).get("number"))
        except (TypeError, ValueError):
            raise B.err("give number=<whole number 0..100>")
        if not 0 <= n <= 100:
            raise B.err("give number=<whole number 0..100>")
        self.camp["play"]["entries"][aid] = n
        return {"yield": 0.0, "public": None, "private": f"Entry {n} recorded at {self.camp.get('id')}; sealed until the end of the round."}

    def resolve(self, entries: dict) -> tuple[dict, dict]:
        """({agent: value}, record)."""
        n = len(entries)
        mean = sum(entries.values()) / n
        target = self.camp["fraction"] * mean
        if n < MIN_ENTRANTS:
            return {a: SMALL for a in entries}, {"n": n, "mean": mean, "target": target, "winners": []}
        best = min(abs(v - target) for v in entries.values())
        win = sorted(a for a, v in entries.items() if abs(v - target) == best)
        pot = POT_PER_ENTRY * n
        return {a: (pot / len(win) if a in win else 0.0) for a in entries}, {"n": n, "mean": mean, "target": target, "winners": win}

    def end_of_round(self, k) -> list[dict]:
        c, p = self.camp, self.camp["play"]
        entries, p["entries"] = p["entries"], {}
        if not entries:
            return []
        pay, rec = self.resolve(entries)
        out = [B.payout(a, c["resource"], B.qty(k, c["resource"], v), f"guess:{c.get('id')}") for a, v in pay.items() if v > 0]
        out += [B.private(a, f"At {c.get('id')} you entered {entries[a]} and earn {v:.3g} value.") for a, v in pay.items()]
        out.append(B.public(f"{c.get('id')}: {rec['n']} entrants, average {rec['mean']:.3g}, target {rec['target']:.3g}, "
                            f"won by {', '.join(rec['winners']) or 'nobody'}."))
        p["history"] = (p["history"] + [{"round": B.rnd(k), **rec}])[-20:]
        return out

    def snapshot(self) -> dict:
        p = self.camp["play"]
        return {"type": "guess", "fraction": self.camp["fraction"], "pending_entries": len(p["entries"]), "history": list(p["history"])}

    def truth(self) -> dict:
        return {"pending": dict(self.camp["play"]["entries"])}
