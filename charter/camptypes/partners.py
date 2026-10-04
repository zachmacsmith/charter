"""Partner choice: each round agents pick a partner and, sealed, either share or take. Two sharers both do well; a taker
facing a sharer does best of all and the sharer gets nothing; two takers do poorly. Pairs and moves are published after the
round, so reputations form and agents can refuse known takers.

Open to every agent (no harvest right needed): the framework should let any player harvest here.

Harvest args (one harvest = one action; the last entry of the round counts):
  {"partner": "<agent>" | "any", "move": "share" | "take"}

Matching at end of round: two agents who named each other are paired. Agents who named "any" are paired with each other at
random (seeded); an odd one out, and anyone whose named partner did not name them back, works alone for ALONE value.

Calibration (value per action; tutorial = 8, see bcommon): both share 10 (1.25x); take vs share 16 / 0; both take 3; alone 2.
A population mixing the moves at random averages (10+16+0+3)/4 = 7.25 per action (~0.9x) with a spread of 0..2x: a social
game at about 1x with high variance. Steady mutual sharing is the best stable outcome at 1.25x.
"""
from __future__ import annotations

from charter.camptypes import CampType, register
from charter.camptypes import bcommon as B

MOVES = ("share", "take")
PAYOFF = {("share", "share"): 10.0, ("share", "take"): 0.0, ("take", "share"): 16.0, ("take", "take"): 3.0}
ALONE = 2.0
PAST = {"share": "shared", "take": "took"}
OPEN_TO_ALL = True


@register("partners")
class Partners(CampType):
    default_resource = "timber"
    open_to_all = True

    def __init__(self, camp, rng):
        super().__init__(camp, rng)
        camp.setdefault("resource", self.default_resource)
        camp.setdefault("open", True)
        if "hidden" not in camp:
            camp["hidden"] = {"seed": rng.getrandbits(32)}
        camp.setdefault("play", {"entries": {}, "history": []})

    def describe(self, inst=None) -> str:
        c = self.camp
        return (f"Camp {c.get('id')}: a joint workshop open to everyone. Each round, harvest with partner=<agent> (or partner=any) "
                f"and move=share or move=take. Entries are sealed; your last entry of the round counts. At the end of the round, two "
                f"agents who named each other work together; agents who chose 'any' are paired at random among themselves; anyone "
                f"else works alone for {ALONE:g} value. In a pair: both share -> {PAYOFF[('share', 'share')]:g} each; one takes and "
                f"one shares -> the taker gets {PAYOFF[('take', 'share')]:g} and the sharer {PAYOFF[('share', 'take')]:g}; both take "
                f"-> {PAYOFF[('take', 'take')]:g} each. After each round every pair and its moves are published. Paid in "
                f"{c['resource']}.")

    def state_line(self, k, aid) -> str:
        p = self.camp["play"]
        s = f"{self.camp.get('id')}: "
        if p["history"]:
            last = p["history"][-1]
            s += "last round " + ("; ".join(f"{a} {PAST[ma]}, {b} {PAST[mb]}" for a, ma, b, mb in last["pairs"]) or "no pairs") + ". "
        e = p["entries"].get(aid)
        return s + (f"Your entry this round: partner {e['partner']}, {e['move']}." if e else "You have no entry this round.")

    def harvest(self, k, aid, args) -> dict:
        args = args or {}
        move = str(args.get("move", "")).strip().lower()
        partner = str(args.get("partner", "")).strip()
        if move not in MOVES:
            raise B.err("move must be 'share' or 'take'")
        if not partner:
            raise B.err("name a partner=<agent>, or partner=any")
        if partner.lower() == "any":
            partner = "any"
        elif partner == aid:
            raise B.err("you cannot partner with yourself")
        elif hasattr(k, "players") and partner not in k.players():
            raise B.err(f"no such agent in play: {partner}")
        self.camp["play"]["entries"][aid] = {"partner": partner, "move": move}
        return {"yield": 0.0, "public": None,
                "private": f"Entry at {self.camp.get('id')}: partner {partner}, {move}. Sealed until the end of the round."}

    def match(self, entries: dict, r: int) -> tuple[list, list]:
        """(pairs [(a, b)], alone [a]) from {agent: {partner, move}}."""
        pairs, used = [], set()
        for a in sorted(entries):
            b = entries[a]["partner"]
            if a in used or b == "any" or b in used or b not in entries:
                continue
            if entries[b]["partner"] == a:
                pairs.append((a, b))
                used |= {a, b}
        pool = sorted(a for a in entries if a not in used and entries[a]["partner"] == "any")
        B.stream(self.camp, "match", r).shuffle(pool)
        for i in range(0, len(pool) - 1, 2):
            pairs.append((pool[i], pool[i + 1]))
            used |= {pool[i], pool[i + 1]}
        return pairs, sorted(a for a in entries if a not in used)

    def end_of_round(self, k) -> list[dict]:
        c, p = self.camp, self.camp["play"]
        entries, p["entries"] = p["entries"], {}
        if not entries:
            return []
        pairs, alone = self.match(entries, B.rnd(k))
        out, pay, rec = [], {}, []
        for a, b in pairs:
            ma, mb = entries[a]["move"], entries[b]["move"]
            pay[a], pay[b] = PAYOFF[(ma, mb)], PAYOFF[(mb, ma)]
            rec.append((a, ma, b, mb))
            out.append(B.private(a, f"At {c.get('id')} you were paired with {b}: you {PAST[ma]}, they {PAST[mb]}; you earn {pay[a]:g} value."))
            out.append(B.private(b, f"At {c.get('id')} you were paired with {a}: you {PAST[mb]}, they {PAST[ma]}; you earn {pay[b]:g} value."))
        for a in alone:
            pay[a] = ALONE
            out.append(B.private(a, f"At {c.get('id')} you had no partner this round and earn {ALONE:g} value."))
        for a, v in pay.items():
            if v > 0:
                out.append(B.payout(a, c["resource"], B.qty(k, c["resource"], v), f"partners:{c.get('id')}"))
        out.append(B.public(f"{c.get('id')} pairs: " + ("; ".join(f"{a} {PAST[ma]}, {b} {PAST[mb]}" for a, ma, b, mb in rec) or "none")
                            + (f"; alone: {', '.join(alone)}" if alone else "")))
        p["history"] = (p["history"] + [{"round": B.rnd(k), "pairs": rec, "alone": alone}])[-20:]
        return out

    def snapshot(self) -> dict:
        p = self.camp["play"]
        return {"type": "partners", "pending_entries": len(p["entries"]), "history": list(p["history"])}

    def truth(self) -> dict:
        return {"pending": dict(self.camp["play"]["entries"])}
