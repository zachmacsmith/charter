"""Guess the crowd (optional social game; drawn only as a wildcard, standard = False): each round entrants name a whole number
0..100, sealed. The target is a published fraction (drawn per camp from FRACTIONS) of the entrants' average; whoever is closest
takes the round's pot (ties split). Open to every agent.

Harvest (sealed; one per agent per round): {"camp": c, "x": [number 0..100]}.

Calibration, in tutorial units (V0 = 8 value by default; see _bcommon): the pot is POT_PER_ENTRY x entrants, so the mean payout
per entry is exactly 1 and the spread is large (one winner takes all). With fewer than MIN_ENTRANTS nobody wins and each entrant
gets SMALL (0.5).
"""
from __future__ import annotations

from charter.camptypes import CampType, register
from charter.camptypes import _bcommon as B

POT_PER_ENTRY = 1.0
MIN_ENTRANTS = 3
SMALL = 0.5
FRACTIONS = (0.6, 0.7, 0.8)
PLAY = {"history": []}


@register("guess")
class Guess(CampType):
    role = "social"
    standard = False                  # not in the standard set's social slot (minority or partners); may be the wildcard
    resolves = "end_of_round"
    open_to_all = True
    dials, max_level = 1, 100
    value_target = 1.0
    dial_based = False

    @classmethod
    def build(cls, cfg, rng, ctx):
        return {"fraction": float(cfg.get("fraction") or rng.choice(FRACTIONS))}

    @classmethod
    def stock(cls, cfg, y_ref, ctx, fn, max_yield, r):
        return B.generous_stock(y_ref, ctx, r)

    def describe(self, inst=None) -> str:
        c = self.camp
        return (f"A guessing booth open to everyone (no harvest right needed; the Board and the Fixer cannot take part). Once per round, "
                f"harvest with x = [a whole number 0..{c['max']}]; entries are sealed until the end of the round. The average, the "
                "target and the winners are published.")

    def state_line(self, k, aid) -> str:
        hist = B.peek(self.camp, PLAY)["history"]
        if not hist:
            return "open to all"
        h = hist[-1]
        return (f"open to all; last round {h['n']} entrants, average {h['mean']:.3g}, target {h['target']:.3g}, won by "
                f"{', '.join(h['winners']) or 'nobody'}")

    def resolve(self, entries: dict) -> tuple:
        """({agent: tutorial units}, record)."""
        n = len(entries)
        mean = sum(entries.values()) / n
        target = self.p["fraction"] * mean
        if n < MIN_ENTRANTS:
            return {a: SMALL for a in entries}, {"n": n, "mean": mean, "target": target, "winners": []}
        best = min(abs(v - target) for v in entries.values())
        win = sorted(a for a, v in entries.items() if abs(v - target) == best)
        pot = POT_PER_ENTRY * n
        return {a: (pot / len(win) if a in win else 0.0) for a in entries}, {"n": n, "mean": mean, "target": target, "winners": win}

    def end_of_round(self, k) -> list:
        c = self.camp
        entries = {a: int(x[0]) for a, x in sorted((c.get("pending") or {}).items())}
        if not entries:
            return []
        pay, rec = self.resolve(entries)
        out = [B.entry(a, v, c, type(self), f"you entered {entries[a]}; the target was {rec['target']:.3g}", [entries[a]],
                       eff=1.0 if a in rec["winners"] else 0.0) for a, v in pay.items()]
        out.append({"public": f"{rec['n']} entrants, average {rec['mean']:.3g}, target {rec['target']:.3g}, won by "
                              f"{', '.join(rec['winners']) or 'nobody'}"})
        p = B.play(c, PLAY)
        p["history"] = (p["history"] + [{"round": k.r, **rec}])[-20:]
        return out

    def snapshot(self) -> dict:
        hist = B.peek(self.camp, PLAY)["history"]
        return dict(hist[-1]) if hist else {}

    def truth(self) -> dict:
        return {"type": self.name, "fn": self.p, "history": list(B.peek(self.camp, PLAY)["history"])}
