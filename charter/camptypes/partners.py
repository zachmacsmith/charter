"""Partner choice (social): each round agents pick a partner and, sealed, either share or take. Two sharers both do well; a taker
facing a sharer does best of all and the sharer gets nothing; two takers do poorly. Pairs and moves are published after the round,
so reputations form and agents can refuse known takers. Open to every agent (no harvest right needed).

Harvest (sealed; one entry per agent per round; no x): {"camp": c, "partner": "Name" | "any", "move": "share" | "take"}.
Entries are kept in camp["pending"][agent] = [partner, move].

Matching at end of round: two agents who named each other are paired. Agents who named "any" are paired with each other at random;
an odd one out, and anyone whose named partner did not name them back, works alone for ALONE.

Calibration, in tutorial units (V0 = 8 value by default; see _bcommon): both share 1.25; take vs share 2.0 / 0; both take 0.375;
alone 0.25. Moves mixed at random average (1.25 + 2 + 0 + 0.375) / 4 = 0.91 per action with a spread of 0..2: a social game at
about 1x with high variance. Steady mutual sharing is the best stable outcome at 1.25.
"""
from __future__ import annotations

from charter.camptypes import CampType, register, who_plays
from charter.camptypes import _bcommon as B

MOVES = ("share", "take")
PAST = {"share": "shared", "take": "took"}
PAYOFF = {("share", "share"): 1.25, ("share", "take"): 0.0, ("take", "share"): 2.0, ("take", "take"): 0.375}
ALONE = 0.25
PLAY = {"history": []}


@register("partners")
class Partners(CampType):
    role = "social"
    resolves = "end_of_round"
    open_to_all = True
    dials, max_level = 0, 0
    value_target = 1.0
    dial_based = False
    extra_args = ("partner", "move")

    @classmethod
    def stock(cls, cfg, y_ref, ctx, fn, max_yield, r):
        return B.generous_stock(y_ref, ctx, r)

    @staticmethod
    def check_args(k, aid, camp, x, extra):
        move = str(extra.get("move", "")).strip().lower()
        partner = str(extra.get("partner", "")).strip()
        if move not in MOVES:
            raise B.err('give "move": "share" or "take"')
        if not partner:
            raise B.err('give "partner": "Name" (or "any")')
        if partner.lower() != "any":
            if partner == aid:
                raise B.err("you cannot partner with yourself")
            if partner not in k.players():
                raise B.err(f"no such agent in play: {partner}")

    @classmethod
    def bot_args(cls, k, aid, camp, rng):
        others = [a for a in k.players() if a != aid]
        return {"partner": rng.choice(others + ["any", "any"]) if others else "any", "move": rng.choice(MOVES)}

    def describe(self, inst=None) -> str:
        return ("A joint workshop, " + who_plays(inst) + " (no harvest right needed). "
                "Once per round, "
                "harvest with \"partner\": \"Name\" (or \"any\") and \"move\": \"share\" or \"take\" (no x); entries are sealed "
                "until the end of the round, when you are paid. Every pair and its moves are published.")

    def state_line(self, k, aid) -> str:
        hist = B.peek(self.camp, PLAY)["history"]
        if not hist:
            return who_plays(k.inst)
        last = hist[-1]
        return who_plays(k.inst) + "; last round " + ("; ".join(f"{a} {PAST[ma]}, {b} {PAST[mb]}" for a, ma, b, mb in last["pairs"]) or "no pairs")

    def harvest(self, k, aid, args) -> dict:
        partner = str(args.get("partner")).strip()
        partner = "any" if partner.lower() == "any" else partner
        move = str(args.get("move")).strip().lower()
        self.camp.setdefault("pending", {})[aid] = [partner, move]
        return {"yield": 0.0, "public": None, "private": f"Entry: partner {partner}, {move}; paired and paid at the end of the round."}

    def match(self, entries: dict) -> tuple:
        """(pairs [(a, b)], alone [a]) from {agent: [partner, move]}."""
        pairs, used = [], set()
        for a in sorted(entries):
            b = entries[a][0]
            if a in used or b == "any" or b in used or b not in entries:
                continue
            if entries[b][0] == a:
                pairs.append((a, b))
                used |= {a, b}
        pool = sorted(a for a in entries if a not in used and entries[a][0] == "any")
        self.rng.shuffle(pool)
        for i in range(0, len(pool) - 1, 2):
            pairs.append((pool[i], pool[i + 1]))
            used |= {pool[i], pool[i + 1]}
        return pairs, sorted(a for a in entries if a not in used)

    def end_of_round(self, k) -> list:
        c = self.camp
        entries = dict(c.get("pending") or {})
        if not entries:
            return []
        pairs, alone = self.match(entries)
        out, rec = [], []
        for a, b in pairs:
            ma, mb = entries[a][1], entries[b][1]
            rec.append((a, ma, b, mb))
            for me, you, mm, ym in ((a, b, ma, mb), (b, a, mb, ma)):
                out.append(B.entry(me, PAYOFF[(mm, ym)], c, type(self), f"paired with {you}: you {PAST[mm]}, they {PAST[ym]}",
                                   eff=PAYOFF[(mm, ym)] / PAYOFF[("take", "share")]))
        for a in alone:
            out.append(B.entry(a, ALONE, c, type(self), "no partner this round: you worked alone"))
        out.append({"public": "pairs: " + ("; ".join(f"{a} {PAST[ma]}, {b} {PAST[mb]}" for a, ma, b, mb in rec) or "none")
                    + (f"; alone: {', '.join(alone)}" if alone else "")})
        p = B.play(c, PLAY)
        p["history"] = (p["history"] + [{"round": k.r, "pairs": rec, "alone": alone}])[-20:]
        return out

    def calibration_input(self, k, aid, strategy, rng):
        return []

    def snapshot(self) -> dict:
        hist = B.peek(self.camp, PLAY)["history"]
        last = hist[-1] if hist else {}
        return {"pairs": last.get("pairs", []), "alone": last.get("alone", []), "last_round": last.get("round")}

    def truth(self) -> dict:
        return {"type": self.name, "history": list(B.peek(self.camp, PLAY)["history"])}
