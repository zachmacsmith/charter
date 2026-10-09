"""Find the weak link (science + coordination): a crew's output is set by its lowest effort, and some members' inputs are secretly
corrupted (counted as zero effort, unknown even to them). The camp runs several shifts per round, so the crew can schedule who
works which shift and find the culprit by group testing across rounds.

Science role: designing the schedule (group tests) that isolates the corrupted member(s) from per-shift results. Coordination
role: following the schedule, all putting in full effort, and keeping the culprit out of the shared shifts. Needs 3 right holders.

Harvest (sealed; one entry per agent per round): {"camp": c, "x": [effort 0..10], "shift": 1..SHIFTS (default 1)}.
Entries are kept in camp["pending"][agent] = [effort, shift].

End of round, per shift: with at least MIN_CREW workers, the crew level m is the lowest *effective* effort (corrupted members count
0) and each worker earns PER_LEVEL x m + SPARE x (10 - own effort) tutorial units; a shift worked alone earns only the SPARE part.
Published: each shift's head count and total pay (not who worked it). Private: own pay. Corruption: one member per
HOLDERS_PER_CULPRIT right holders, redrawn every 8-12 rounds (and on drift).

Calibration, in tutorial units (V0 = 8 value by default; see _bcommon):
  works (culprit excluded, everyone at 10): PER_LEVEL x 10 = 2.5 per action;
  fails (everyone hedges at 0, or the culprit sits in every shift): SPARE x 10 = 0.5 per action;
  full effort in a shift with the culprit: 0. A round or two of testing costs about 0.5-1 per action and then pays 2.5.
"""
from __future__ import annotations

from charter.camptypes import CampType, register
from charter.camptypes import _bcommon as B

PER_LEVEL = 0.25              # tutorial units per crew level, per worker
SPARE = 0.05                  # tutorial units per point of effort held back
SHIFTS = 3
MIN_CREW = 2
RESHUFFLE = (8, 12)
HOLDERS_PER_CULPRIT = 4
PLAY = {"history": []}


@register("weak_link")
class WeakLink(CampType):
    role = "coordination"
    resolves = "end_of_round"
    min_holders = 3
    dials, max_level = 1, 10
    preferred_resource = None
    value_target = 2.5
    dial_based = False
    extra_args = ("shift",)

    @classmethod
    def build(cls, cfg, rng, ctx):
        return {"reshuffle": rng.randint(*RESHUFFLE), "epoch": None, "faulty": [], "shifts": int(cfg.get("shifts", SHIFTS))}

    @classmethod
    def stock(cls, cfg, y_ref, ctx, fn, max_yield, r):
        return B.generous_stock(y_ref, ctx, r)

    @staticmethod
    def check_args(k, aid, camp, x, extra):
        try:
            s = int(extra.get("shift", 1))
        except (TypeError, ValueError):
            s = 0
        if not 1 <= s <= int(camp["fn"].get("shifts", SHIFTS)):
            raise B.err(f"shift must be 1..{camp['fn'].get('shifts', SHIFTS)}")

    # ------------------------------------------------------------------ hidden corruption
    def faulty(self, k) -> list:
        h = self.p
        epoch = k.r // h["reshuffle"]
        if h["epoch"] != epoch:
            right = f"harvest:{self.camp['id']}"
            pool = sorted(a for a in k.players() if k.has(a, right))
            n = max(1, len(pool) // HOLDERS_PER_CULPRIT) if pool else 0
            h["faulty"] = sorted(self.rng.sample(pool, min(n, len(pool))))
            h["epoch"] = epoch
        return h["faulty"]

    # ------------------------------------------------------------------ text
    def describe(self, inst=None) -> str:
        c, n = self.camp, self.p["shifts"]
        if self.p.get("hunt"):                                         # review 15: the hunt (subsistence), open to every eater
            return (f"A hunt, open to every agent who eats (no right needed). Join with x = [effort 0..{c['max']}]; entries are "
                    "sealed until the end of the round, when the catch is shared out: a party's catch is set by its weakest "
                    "member's effort, so a party of two or more at full effort catches far more than a lone hunter. The party's "
                    "size and total catch are published.")
        return (f"A work site run in {n} shifts each round. Join one shift per round with x = [effort 0..{c['max']}] and \"shift\": "
                f"1..{n} (default 1); entries are sealed until the end of the round, when you are paid. Each shift's head count and total "
                "pay are published, but not who worked it.")

    def state_line(self, k, aid) -> str:
        hist = B.peek(self.camp, PLAY)["history"]
        if not hist:
            return f"{self.p['shifts']} shifts"
        return "last round " + "; ".join(f"shift {t['shift']}: {t['crew']} workers, total pay {t['total']:.3g}" for t in hist[-1]["shifts"])

    # ------------------------------------------------------------------ play
    def harvest(self, k, aid, args) -> dict:
        e, s = int(args["x"][0]), int(args.get("shift", 1))
        self.camp.setdefault("pending", {})[aid] = [e, s]
        return {"yield": 0.0, "public": None, "private": f"joined shift {s} with effort {e}; paid at the end of the round"}

    @staticmethod
    def pay(efforts: dict, faulty, mx: int = 10) -> dict:
        """One shift: {agent: stated effort} -> {agent: tutorial units}."""
        eff = {a: (0 if a in faulty else e) for a, e in efforts.items()}
        level = min(eff.values()) if len(eff) >= MIN_CREW else 0
        return {a: round(PER_LEVEL * level + SPARE * (mx - e), 4) for a, e in efforts.items()}

    def end_of_round(self, k) -> list:
        c = self.camp
        pend = c.get("pending") or {}
        if not pend:
            return []
        bad = set(self.faulty(k))
        out, rec = [], []
        for s in range(1, self.p["shifts"] + 1):
            efforts = {a: int(v[0]) for a, v in sorted(pend.items()) if int(v[1]) == s}
            if not efforts:
                continue
            pay = self.pay(efforts, bad, c["max"])
            rec.append({"shift": s, "crew": len(efforts), "total": round(sum(B.qty(c, type(self), v) for v in pay.values()), 4)})
            for a, v in pay.items():
                out.append(B.entry(a, v, c, type(self), f"shift {s} had {len(efforts)} worker(s); your pay {B.qty(c, type(self), v):.3g}",
                                   [efforts[a]], eff=v / (PER_LEVEL * c["max"]) if PER_LEVEL * c["max"] else 0.0))
        out.append({"public": "; ".join(f"shift {t['shift']}: {t['crew']} worker(s), total pay {t['total']:.3g}" for t in rec)})
        p = B.play(c, PLAY)
        p["history"] = (p["history"] + [{"round": k.r, "shifts": rec, "faulty": sorted(bad)}])[-10:]
        return out

    def drift(self, rng) -> None:
        self.p["epoch"] = None                                       # faulty set redrawn at next use

    def calibration_input(self, k, aid, strategy, rng):
        return [self.camp["max"]] if strategy != "fail" else [0]

    # ------------------------------------------------------------------ records
    def snapshot(self) -> dict:
        hist = B.peek(self.camp, PLAY)["history"]
        last = hist[-1] if hist else {}
        return {"faulty": list(self.p["faulty"]), "last": last.get("shifts", []), "last_round": last.get("round")}

    def truth(self) -> dict:
        return {"type": self.name, "fn": self.p, "history": list(B.peek(self.camp, PLAY)["history"])}
