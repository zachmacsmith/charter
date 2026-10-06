"""Minority game (social): any agent picks one of two options each round; only the less crowded side is paid.

Sealed until the end of the round. The round's pool (max_yield x stock/capacity) is shared equally by the agents on the strictly
less crowded side; on a tie, or with fewer than `min_players` taking part, nobody is paid. The pool is sized so that the value per
action is about the tutorial's when `participation` of the agents play (free entry: more players, less each). Stated plans are
expected to be lies: there is nothing to learn beyond what others will do.
"""
from __future__ import annotations

import math

from charter.camptypes import CampType, register, who_plays


@register("minority")
class Minority(CampType):
    role = "social"
    resolves = "end_of_round"
    open_to_all = True
    dials, max_level = 1, 1
    preferred_resource = "stone"
    dial_based = False

    @classmethod
    def build(cls, cfg, rng, ctx):
        return {"participation": float(cfg.get("participation", 0.5)), "min_players": int(cfg.get("min_players", 3)),
                "agents": int(ctx.get("agents", 10))}

    @classmethod
    def expected_players(cls, fn):
        return max(fn["min_players"], fn["participation"] * fn["agents"])

    @staticmethod
    def win_share(n: int, min_players: int) -> float:
        """Chance that n players choosing at random leave a strictly less crowded, non-empty side (someone is paid)."""
        if n < min_players:
            return 0.0
        tie = math.comb(n, n // 2) / 2 ** n if n % 2 == 0 else 0.0
        return max(1e-6, 1.0 - tie - 2 / 2 ** n)

    @classmethod
    def scale(cls, cfg, y_ref, ctx, fn):
        """The pool per round at full stock: y_ref per expected player, divided by the chance that some side is paid."""
        n = round(cls.expected_players(fn))
        return y_ref * n / cls.win_share(n, fn["min_players"])

    @classmethod
    def stock(cls, cfg, y_ref, ctx, fn, max_yield, r):
        return 20.0 * max_yield, float(cfg.get("regrowth_r", 0.25))

    def end_of_round(self, k):
        c = self.camp
        pend = c.get("pending") or {}
        sides = {aid: int(x[0]) for aid, x in sorted(pend.items())}
        n0, n1 = sum(1 for s in sides.values() if s == 0), sum(1 for s in sides.values() if s == 1)
        res = k.name_of("resource:" + c["resource"])
        side = None
        if len(sides) >= self.p["min_players"] and n0 != n1:
            side = 0 if n0 < n1 else 1
        winners = [a for a, s in sides.items() if s == side]
        pool = c["max_yield"] * c["S"] / c["K"] if winners else 0.0
        each = pool / len(winners) if winners else 0.0
        out = []
        for aid, s in sides.items():
            won = s == side
            out.append({"agent": aid, "yield": each if won else 0.0, "x": [s], "efficiency": 1.0 if won else 0.0,
                        "private": f"you chose {s}; " + (f"your side was the less crowded one: you receive {each:.3g} {res}" if won
                                                          else "you were not paid")})
        why = (f"those who chose {side} share {pool:.3g} {res} ({each:.3g} each)" if side is not None else
               ("a tie: nobody is paid" if len(sides) >= self.p["min_players"] else f"fewer than {self.p['min_players']} took part: nobody is paid"))
        out.append({"public": f"{len(sides)} took part: {n0} chose 0, {n1} chose 1; {why}"})
        c["last"] = {"round": k.r, "counts": [n0, n1], "paid_side": side, "each": round(each, 4), "players": len(sides)}
        return out

    def calibration_input(self, k, aid, strategy, rng):
        if strategy == "fail":
            return [0]                                              # everyone on the same side: nobody is paid
        return [rng.randint(0, 1)]

    def describe(self, inst):
        return (who_plays(inst)[:1].upper() + who_plays(inst)[1:] + " (no harvest right needed). "
                "Each round you may choose "
                "x = [0] or x = [1] (one choice per round, sealed until the end of the round). Payment comes at the end of the round. "
                "The number of agents on each side is published.")

    def state_line(self, k, aid):
        last = self.camp.get("last")
        if not last:
            return "open to all"
        return (f"open to all; last round {last['counts'][0]} chose 0, {last['counts'][1]} chose 1"
                + (f", side {last['paid_side']} was paid {last['each']:.3g} each" if last["paid_side"] is not None else ", nobody was paid"))

    def snapshot(self):
        return dict(self.camp.get("last") or {})

    def truth(self):
        return {"type": self.name, "fn": self.p}
