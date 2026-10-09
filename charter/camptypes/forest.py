"""Forest (review 15 §2.3, S2): an open commons of food, and timber for the felling. Role `subsistence`: never drawn into the
standard set (charter/subsistence.py appends forests when subsistence is on), so registering it changes no composition.

    harvest {"camp": c}                forage: food = yield x S/K x the forager's hunger multiplier, never taking the stock below
                                       refuge x K ("the last berries are hard to find"); the stock regrows logistically (core regrow)
    harvest {"camp": c, "fell": true}  fell: fell_timber timber; K shrinks by fell_cost_k x the initial K (never below fell_floor x
                                       the initial K; the stock with it); every `clearing` fells clear one plot on the paired fields

Every forest action (forage or fell) counts toward subsistence.forest.forage_per_round (per agent, over all forests). Camp rules
(quota, harvest limit, fee: laws' set_quota, set_harvest_limit, set_fee) apply as at any camp. Yields are paid through the harvest
primitive (laws' on_harvest and before_harvest see them). Parameters are in camp["fn"] (K0, yield, refuge, pair, fells, ...).
"""
from __future__ import annotations

from charter.camptypes import CampType, register


@register("forest")
class Forest(CampType):
    role = "subsistence"
    resolves = "immediate"
    open_to_all = True
    standard = False
    wildcard_ok = False
    dial_based = False
    dials, max_level = 0, 0
    preferred_resource = "food"
    extra_args = ("fell",)

    def describe(self, inst=None) -> str:
        p = self.p
        pair = f" on {p['pair']}" if p.get("pair") else ""
        return (f"An open forest (no right needed). harvest {{\"camp\": \"{self.camp['id']}\"}} forages food: up to "
                f"{p['yield']:g} x stock/capacity per action (less when you are hungry; foraging never takes the last "
                f"{p['refuge']:.0%}). harvest {{\"camp\": \"{self.camp['id']}\", \"fell\": true}} cuts {p['fell_timber']:g} timber and "
                f"shrinks the forest for good; every {p['clearing']} fells clear a new plot{pair}. At most {p['per_round']} forest "
                "actions per agent per round.")

    def state_line(self, k, aid) -> str:
        c = self.camp
        return f"stock {c['S'] / c['K']:.0%} of capacity {c['K']:.3g} food"

    def snapshot(self) -> dict:
        return {"K0": self.p["K0"], "fells": self.p.get("fells", 0), "cleared": self.p.get("cleared", 0)}

    # ------------------------------------------------------------------ the action (framework.harvest_action hands it over)
    def act(self, k, aid, x, extra) -> str:
        from charter import subsistence as SB
        from charter.camptypes import framework as CT
        c, p = self.camp, self.p
        cid = c["id"]
        extra = dict(extra or {})
        fell = extra.pop("fell", False)
        fell = fell is True or str(fell).lower() in ("true", "1", "yes")
        if extra:
            raise CT._err(f"{cid} takes only \"fell\": true (to fell) or nothing (to forage); not {', '.join(sorted(extra))}")
        if x not in (None, [], 0):
            raise CT._err(f"{cid} takes no x: harvest {{\"camp\": \"{cid}\"}} forages, with \"fell\": true it fells")
        if not CT.can_take_part(k, aid, cid):
            raise CT._err(f"{cid} is open to every agent who eats, but not to you")
        st = SB.state(k)
        used = int(st["forage"].get(aid, 0))
        if used >= int(p["per_round"]):
            raise CT._err(f"you have used your {p['per_round']} forest actions this round")
        key = f"{aid}|{cid}"
        if c["harvest_limit"] is not None and k.w["harvest_count"].get(key, 0) >= int(c["harvest_limit"]):
            raise CT._err(f"harvest limit reached at {cid} this round ({c['harvest_limit']})")
        if c["quota"] is not None and k.w["quota_used"].get(cid, 0) >= c["quota"]:
            raise CT._err(f"the quota for {cid} is used up this round ({c['quota']})")
        if c.get("fee"):
            if not k.move(aid, "reserve", c["fee"]["item"], c["fee"]["qty"], why="harvest_fee", by=aid):
                raise CT._err(f"cannot pay the harvest fee ({c['fee']['qty']} {c['fee']['item']})")
        st["forage"][aid] = used + 1
        k.w["harvest_count"][key] = k.w["harvest_count"].get(key, 0) + 1
        k.w["quota_used"][cid] = k.w["quota_used"].get(cid, 0) + 1
        if fell:
            return self._fell(k, aid)
        left = max(0.0, c["S"] - c["harvested_this_round"])
        y = float(p["yield"]) * left / c["K"] * SB.yield_mult(k, aid)
        y = round(max(0.0, min(y, left - float(p["refuge"]) * c["K"])), 3)
        got, ded = CT.pay_yield(k, aid, cid, [], y, eff=y / float(p["yield"]) if p["yield"] else 0.0)
        hungry = "" if SB.stage(k, aid) == 0 else " (you are hungry: you gather less)"
        return (f"Foraged {got - ded:.3g} food at {cid}" + (f" ({ded:.3g} deducted by law)" if ded else "") + hungry
                + f"; the forest is at {c['S'] / c['K']:.0%} of capacity before this round's regrowth.")

    def _fell(self, k, aid) -> str:
        from charter.camptypes import fields as FL
        c, p = self.camp, self.p
        cid = c["id"]
        q = float(p["fell_timber"])
        ded = k.apply("harvest", agent=aid, camp=cid, x=[], item="timber", qty=q, via="typed").result["deducted"]
        k.log("harvest", aid, {"camp": cid, "x": [], "yield": q, "deducted": ded, "efficiency": 1.0, "noise": 0.0,
                               "stock_before": round(c["S"], 3), "type": c["type"], "item": "timber", "fell": True}, vis=[aid])
        K0 = float(p["K0"])
        c["K"] = round(max(float(p["fell_floor"]) * K0, c["K"] - float(p["fell_cost_k"]) * K0), 4)
        c["S"] = round(min(c["S"], c["K"]), 4)
        p["fells"] = int(p.get("fells", 0)) + 1
        note = ""
        if p.get("pair") and p["fells"] % int(p["clearing"]) == 0:
            pid = FL.clear_plot(k, p["pair"], by=aid)
            if pid is not None:
                p["cleared"] = int(p.get("cleared", 0)) + 1
                note = f" The felling cleared a new plot ({p['pair']} plot {pid})."
        return f"Felled {q - ded:g} timber at {cid}" + (f" ({ded:.3g} deducted by law)" if ded else "") + \
            f"; the forest's capacity is now {c['K']:.3g} food.{note}"
