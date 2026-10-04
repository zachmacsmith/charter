"""Find the weak link: a crew's output is set by its lowest effort, and some members' inputs are secretly corrupted (counted as
zero effort, unknown even to them). The camp runs several shifts per round, so the crew can schedule who works which shift and
find the culprit by group testing.

Science role: designing the schedule (group tests) that isolates the corrupted member(s) from per-shift totals. Coordination
role: following the schedule, all putting in full effort, and keeping the culprit out of the shared shifts.

Harvest args (one harvest = one action): {"effort": 0..10, "shift": 1..SHIFTS (default 1)}. Sealed; resolved at end of round.
At most one entry per agent per shift per round.

End of round, per shift: if at least MIN_CREW agents worked it, the crew level m is the lowest *effective* effort (corrupted
members count 0) and each worker earns PER_LEVEL * m + SPARE * (10 - own effort). A shift worked alone earns only the
SPARE part. Published: each shift's head count and total payout (not who worked it). Private: own payout.
Corruption is redrawn every 8-12 rounds (hidden), among the camp's right holders: one corrupted member per 4 holders.

Calibration (value per action; tutorial = 8, see bcommon):
  coordination works (culprit excluded, everyone at 10): PER_LEVEL x 10 = 20 per action = 2.5x tutorial;
  coordination fails (everyone hedges at 0, or the culprit sits in every shift): SPARE x 10 = 4 per action = 0.5x;
  full effort in a shift with the culprit: 0. One round of testing (about 0.5x) pays for itself in under a round.
"""
from __future__ import annotations

from charter.camptypes import CampType, register
from charter.camptypes import bcommon as B

EFFORT_MAX = 10
PER_LEVEL = 2.0               # value per unit of the crew level, per worker
SPARE = 0.4                   # value per unit of effort held back
SHIFTS = 3
MIN_CREW = 2
RESHUFFLE = (8, 12)
HOLDERS_PER_CULPRIT = 4


@register("weak_link")
class WeakLink(CampType):
    default_resource = "stone"

    def __init__(self, camp, rng):
        super().__init__(camp, rng)
        camp.setdefault("resource", self.default_resource)
        if "hidden" not in camp:
            camp["hidden"] = {"seed": rng.getrandbits(32), "reshuffle": rng.randint(*RESHUFFLE), "epoch": None, "corrupt": []}
        camp.setdefault("play", {"entries": [], "history": []})

    # ------------------------------------------------------------------ hidden corruption
    def _holders(self, k):
        right = f"harvest:{self.camp.get('id')}"
        try:
            return sorted(k.holders(right))
        except Exception:
            return []

    def corrupt(self, k) -> list:
        h = self.camp["hidden"]
        epoch = B.rnd(k) // h["reshuffle"]
        if h["epoch"] != epoch:
            pool = [a for a in self._holders(k) if a in set(k.players())] if hasattr(k, "players") else self._holders(k)
            n = max(1, len(pool) // HOLDERS_PER_CULPRIT) if pool else 0
            h["corrupt"] = sorted(B.stream(self.camp, "corrupt", epoch).sample(pool, min(n, len(pool))))
            h["epoch"] = epoch
        return h["corrupt"]

    # ------------------------------------------------------------------ text
    def describe(self, inst=None) -> str:
        c = self.camp
        return (f"Camp {c.get('id')}: a work site run in {SHIFTS} shifts each round. Join a shift with harvest effort=0..{EFFORT_MAX}, "
                f"shift=1..{SHIFTS} (once per shift per round; entries are sealed until the end of the round). A shift's crew "
                f"produces at the level of its LOWEST effort: each worker in it earns {PER_LEVEL:g} value per level, plus {SPARE:g} "
                f"value for each point of effort they held back. A shift with fewer than {MIN_CREW} workers produces nothing but the "
                f"held-back part. Some workers' tools are faulty without their knowing it: a faulty worker's effort counts as zero "
                f"for the crew, whatever they enter. Which workers are faulty changes from time to time. After each round, each "
                f"shift's head count and total pay are published, but not who worked it. Paid in {c['resource']}.")

    def state_line(self, k, aid) -> str:
        p = self.camp["play"]
        last = p["history"][-1] if p["history"] else None
        mine = [e["shift"] for e in p["entries"] if e["agent"] == aid]
        s = f"{self.camp.get('id')}: {SHIFTS} shifts; "
        if last:
            s += "last round " + "; ".join(f"shift {t['shift']}: {t['crew']} workers, total pay {t['total']:.3g}" for t in last["shifts"]) + ". "
        return s + (f"You are entered in shift(s) {mine} this round." if mine else "You have not joined a shift this round.")

    # ------------------------------------------------------------------ play
    def harvest(self, k, aid, args) -> dict:
        args = args or {}
        try:
            e = int(args.get("effort"))
            shift = int(args.get("shift", 1))
        except (TypeError, ValueError):
            raise B.err(f"give effort=0..{EFFORT_MAX} and shift=1..{SHIFTS}")
        if not 0 <= e <= EFFORT_MAX or not 1 <= shift <= SHIFTS:
            raise B.err(f"give effort=0..{EFFORT_MAX} and shift=1..{SHIFTS}")
        p = self.camp["play"]
        if any(x["agent"] == aid and x["shift"] == shift for x in p["entries"]):
            raise B.err(f"you are already in shift {shift} at {self.camp.get('id')} this round")
        self.corrupt(k)                                              # fixes this epoch's faulty set before anyone is paid
        p["entries"].append({"agent": aid, "effort": e, "shift": shift})
        return {"yield": 0.0, "public": None, "private": f"Joined shift {shift} at {self.camp.get('id')} with effort {e}; paid at the end of the round."}

    @staticmethod
    def pay(efforts: dict, faulty) -> dict:
        """One shift: {agent: stated effort} -> {agent: value}."""
        eff = {a: (0 if a in faulty else e) for a, e in efforts.items()}
        level = min(eff.values()) if len(eff) >= MIN_CREW else 0
        return {a: round(PER_LEVEL * level + SPARE * (EFFORT_MAX - e), 3) for a, e in efforts.items()}

    def end_of_round(self, k) -> list[dict]:
        c, p = self.camp, self.camp["play"]
        entries, p["entries"] = p["entries"], []
        if not entries:
            return []
        faulty = set(self.corrupt(k))
        out, rec, tot = [], [], {}
        for s in range(1, SHIFTS + 1):
            efforts = {x["agent"]: x["effort"] for x in entries if x["shift"] == s}
            if not efforts:
                rec.append({"shift": s, "crew": 0, "total": 0.0})
                continue
            pay = self.pay(efforts, faulty)
            rec.append({"shift": s, "crew": len(efforts), "total": round(sum(pay.values()), 3)})
            for a, v in pay.items():
                tot[a] = tot.get(a, 0.0) + v
                out.append(B.private(a, f"Shift {s} at {c.get('id')}: {len(efforts)} workers; your pay {v:.3g} value."))
        for a, v in tot.items():
            if v > 0:
                out.append(B.payout(a, c["resource"], B.qty(k, c["resource"], v), f"weak_link:{c.get('id')}"))
        out.append(B.public(f"{c.get('id')} shifts: " + "; ".join(f"shift {t['shift']}: {t['crew']} workers, total pay {t['total']:.3g}" for t in rec)))
        out.append(B.monitor({"camp": c.get("id"), "faulty": sorted(faulty), "entries": entries}))
        p["history"] = (p["history"] + [{"round": B.rnd(k), "shifts": rec}])[-10:]
        return out

    # ------------------------------------------------------------------ records
    def snapshot(self) -> dict:
        p = self.camp["play"]
        return {"type": "weak_link", "pending_entries": len(p["entries"]), "history": list(p["history"])}

    def truth(self) -> dict:
        h = self.camp["hidden"]
        return {"faulty": list(h["corrupt"]), "epoch": h["epoch"], "reshuffle_every": h["reshuffle"]}
