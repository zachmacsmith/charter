"""Data consortium: each reading returns a noisy weighted sum of the reader's settings with hidden weights; only submitting the
exact weights pays, and the pool is split by a rule set in the camp.

Science role: solving for the weights from pooled readings (least squares, then rounding). Coordination role: taking *varied*
readings (identical settings add no information), pooling them, and agreeing who submits and how the pool is split.

Harvest args (one harvest = one action):
  {"x": [8 ints 0..15]}       a reading: returns sum(w_i * x_i) + noise, privately. Pays nothing.
  {"submit": [8 ints 0..15]}  a sealed claim of the weights, resolved at end of round.

End of round: if any submission this round equals the hidden weights, the pool is paid out by the camp's split rule, the
weights are redrawn and a new season starts; otherwise the pool shrinks by POOL_DECAY. Every submitter learns privately whether
its claim was right; a solve is announced publicly (without the weights).

Split rules (drawn per camp, public in the description):
  by_readings  SUBMIT_SHARE to the correct submitter(s), the rest in proportion to this season's readings by each reader;
  equal        SUBMIT_SHARE to the correct submitter(s), the rest equally among this season's readers;
  winner       the correct submitter(s) take the whole pool.

Calibration (value per action; tutorial = 8, see bcommon):
  NOISE_SIGMA 3 means about 16 random readings recover all 8 weights by least squares and rounding (~83% of the time;
  12 readings ~55%, 8 readings ~7%; better-designed settings do better). Coordinated: 4 holders x 2 readings pool 16
  readings in two rounds and submit in round 3; 17 actions share POOL_START x POOL_DECAY^2 = 560 x 0.608 = 340, i.e. 20 per action = 2.5x tutorial. Failed coordination: one holder alone
  needs 8 rounds of readings and submits in round 9; 17 actions earn 560 x 0.78^8 = 77, i.e. 4.5 per action = 0.56x.
"""
from __future__ import annotations

from charter.camptypes import CampType, register
from charter.camptypes import bcommon as B

DIM = 8
MAXV = 15
NOISE_SIGMA = 3.0
POOL_START = 560.0            # value
POOL_DECAY = 0.78             # per round without a solve
POOL_FLOOR = 0.05             # the pool never falls below this fraction of POOL_START
SUBMIT_SHARE = 0.2
SPLITS = ("by_readings", "equal", "winner")
SPLIT_WEIGHTS = (0.4, 0.4, 0.2)


@register("consortium")
class Consortium(CampType):
    default_resource = "silver"

    def __init__(self, camp, rng):
        super().__init__(camp, rng)
        camp.setdefault("resource", self.default_resource)
        if "hidden" not in camp:
            camp["hidden"] = {"seed": rng.getrandbits(32), "w": [rng.randint(0, MAXV) for _ in range(DIM)]}
        camp.setdefault("split", rng.choices(SPLITS, SPLIT_WEIGHTS)[0])
        camp.setdefault("play", {"season": 1, "season_start": None, "pool": POOL_START, "readings": {}, "submissions": [],
                                 "solved": []})

    # ------------------------------------------------------------------ text
    def describe(self, inst=None) -> str:
        c = self.camp
        rule = {"by_readings": f"{SUBMIT_SHARE:.0%} goes to whoever submitted the correct answer, and the rest is shared in proportion "
                               f"to how many readings each participant took this season",
                "equal": f"{SUBMIT_SHARE:.0%} goes to whoever submitted the correct answer, and the rest is shared equally among "
                         f"everyone who took at least one reading this season",
                "winner": "whoever submitted the correct answer takes the whole pool (shared if several did in the same round)"}[c["split"]]
        return (f"Camp {c.get('id')}: a measurement station. It has {DIM} settings, each a whole number 0..{MAXV}, and {DIM} hidden "
                f"whole-number weights (each 0..{MAXV}). A reading (harvest with x=[{DIM} settings]) returns the sum of each setting "
                f"times its weight, plus random noise (standard deviation about {NOISE_SIGMA:g}); readings are private and pay nothing. "
                f"Submitting the weights (harvest with submit=[{DIM} weights]) is sealed until the end of the round. If a submission is "
                f"exactly right, the station's pool is paid out in {c['resource']} and new weights are drawn. The pool starts at "
                f"{POOL_START:g} value and shrinks to {POOL_DECAY:.0%} of itself at the end of each round it is not won. How it is "
                f"split: {rule}. Readings at the same settings repeat the same information.")

    def state_line(self, k, aid) -> str:
        p = self.camp["play"]
        mine = p["readings"].get(aid, 0)
        return (f"{self.camp.get('id')}: pool {p['pool']:.0f} value (season {p['season']}); readings this season: "
                f"{sum(p['readings'].values())} in total, {mine} by you.")

    # ------------------------------------------------------------------ play
    def harvest(self, k, aid, args) -> dict:
        args = args or {}
        p, h = self.camp["play"], self.camp["hidden"]
        r = B.rnd(k)
        if p["season_start"] is None:
            p["season_start"] = r
        if "submit" in args:
            s = B.ints(args["submit"], DIM, 0, MAXV, "submit")
            p["submissions"].append({"agent": aid, "w": s, "round": r})
            return {"yield": 0.0, "public": None, "private": f"Submission {s} recorded at {self.camp.get('id')}; it is checked at the end of the round."}
        x = B.ints(args.get("x"), DIM, 0, MAXV, "x")
        n = p["readings"].get(aid, 0)
        noise = B.stream(self.camp, "reading", p["season"], r, aid, n).gauss(0, NOISE_SIGMA)
        val = round(sum(a * b for a, b in zip(x, h["w"])) + noise, 2)
        p["readings"][aid] = n + 1
        return {"yield": 0.0, "public": None, "private": f"Reading at {self.camp.get('id')} with x={x}: {val}"}

    def end_of_round(self, k) -> list[dict]:
        c, p, h = self.camp, self.camp["play"], self.camp["hidden"]
        out = []
        subs, p["submissions"] = p["submissions"], []
        winners = []
        for s in subs:
            ok = s["w"] == h["w"]
            out.append(B.private(s["agent"], f"Your submission {s['w']} at {c.get('id')} was {'correct' if ok else 'not correct'}."))
            if ok and s["agent"] not in winners:
                winners.append(s["agent"])
        if not winners:
            if p["season_start"] is not None:
                p["pool"] = round(max(POOL_START * POOL_FLOOR, p["pool"] * POOL_DECAY), 3)
            return out
        shares = self.split(p["pool"], winners, p["readings"], c["split"])
        for aid, v in shares.items():
            if v > 0:
                out.append(B.payout(aid, c["resource"], B.qty(k, c["resource"], v), f"consortium:{c.get('id')}"))
        out.append(B.public(f"The weights at {c.get('id')} were found; the pool of {p['pool']:.0f} value was paid out. New weights drawn."))
        out.append(B.monitor({"camp": c.get("id"), "solved": h["w"], "winners": winners, "shares": shares, "season": p["season"]}))
        p["solved"].append({"season": p["season"], "round": B.rnd(k), "winners": winners, "pool": p["pool"]})
        h["w"] = [B.stream(c, "redraw", p["season"], i).randint(0, MAXV) for i in range(DIM)]
        p.update({"season": p["season"] + 1, "season_start": None, "pool": POOL_START, "readings": {}})
        return out

    @staticmethod
    def split(pool: float, winners: list, readings: dict, rule: str) -> dict:
        """Value to each agent. Winners share SUBMIT_SHARE (all of it under 'winner'); readers share the rest by the rule.
        With no readers the whole pool goes to the winners."""
        shares = {a: 0.0 for a in list(winners) + list(readings)}
        readers = {a: n for a, n in readings.items() if n > 0}
        sub = 1.0 if rule == "winner" or not readers else SUBMIT_SHARE
        for a in winners:
            shares[a] += pool * sub / len(winners)
        rest = pool * (1 - sub)
        if rest > 0:
            tot = sum(readers.values())
            for a, n in readers.items():
                shares[a] += rest * (n / tot if rule == "by_readings" else 1 / len(readers))
        return {a: round(v, 3) for a, v in shares.items()}

    # ------------------------------------------------------------------ records
    def snapshot(self) -> dict:
        p = self.camp["play"]
        return {"type": "consortium", "split": self.camp["split"], "season": p["season"], "pool": p["pool"],
                "readings": dict(p["readings"]), "pending_submissions": len(p["submissions"]), "solved": list(p["solved"])}

    def truth(self) -> dict:
        return {"w": list(self.camp["hidden"]["w"]), "noise_sigma": NOISE_SIGMA}
