"""Forest (review 15 §2.3, S2; review 19: the forest ecosystem): an open commons with two food stocks, plants and game, and timber
for the felling. Role `subsistence`: never drawn into the standard set (charter/subsistence.py appends forests when subsistence is
on), so registering it changes no composition.

Two stocks, each with its own regrowth (review 19 §6):
    plants  c["S"] of capacity c["K"] (food), logistic regrowth c["r"] (the core regrow primitive; the season sets c["r"] each round:
            subsistence._ecology); foraging never takes the stock below refuge x K ("the last berries are hard to find")
    game    c["game"] = {"G", "K"} (food, as meat on the hoof), regrowth in subsistence._ecology: G += r x m x G (1 - G/K) x allee +
            inflow x (K - G) (animals walking in from the land around); hunting takes it

Actions (each counts toward subsistence.forest.forage_per_round, per agent over all forests; camp rules (quota, harvest limit,
fee: laws' set_quota, set_harvest_limit, set_fee) apply to every forest action as at any camp):
    harvest {"camp": c}                forage: plants = yield x S/K x the forager's hunger multiplier, never below the refuge; paid at
                                       once (the harvest primitive)
    harvest {"camp": c, "fell": true}  fell: fell_timber timber; K shrinks by fell_cost_k x the initial K (never below fell_floor x
                                       the initial K; the stock with it); every `clearing` fells clear one plot on the paired fields
                                       (when fields exist; review 19: fields are parked, off by default)
    hunt {"camp": c, "party": p?}      (subsistence.act_hunt; the routed `hunt` primitive, which a law may block: closed seasons,
                                       territories, licences) one unit of hunting effort this round, sealed; hunters naming the same
                                       party at the same forest hunt together, no party: alone. Again: one more unit (up to the
                                       forest-action budget)

The hunt (end of the round, camps step 2: Forest.end_of_round; review 19 §5). For each party, in label order, with effort E (each
hunter's units x its hunger multiplier) and game density g = G/K before its draw, from random.Random(f"{seed}|subsistence|hunt|
{camp}|{round}|{label}"):
    p_large  = min(.95, catch_L) x g^theta x (1 - exp(-(E / scale_L)^shape_L))     a large animal: food_L (20)
    p_medium = min(.95, catch_M) x g^theta x (1 - exp(-(E / scale_M)^shape_M))     a deer: food_M (5)
    one draw u: u < p_large -> large; else u < p_large + (1 - p_large) p_medium -> medium; else small game: each of the party's
    whole effort units catches food_S (1) with chance min(.95, catch_S) x g^theta x E / units
The catch (never more than G) leaves the game stock and is shared by effort (the harvest primitive pays each hunter; laws'
on_harvest see it). Expected food per unit of effort at full stock: alone 1.15; 2: 1.5; 3: 1.8; 4: 2.1; 6: 2.3 (the peak); 8: 1.9;
12: 1.4 (one quarry per party: bigger parties share it more thinly). Each party's members learn its catch; the forest's round line
(public) gives each party's size and catch.
"""
from __future__ import annotations

import math
import random

from charter import dispatch as D
from charter import jurisdictions as J
from charter.camptypes import CampType, register

GAME_LEVELS = ((0.6, "plentiful"), (0.3, "fair"), (0.1, "scarce"), (0.0, "very scarce"))


def game_level(g) -> str:
    """The coarse word agents (and laws) get for a forest's game density G/K: hunters see tracks, not a census."""
    return next((name for lo, name in GAME_LEVELS if g >= lo), GAME_LEVELS[-1][1])


def kill_chances(gp, E, g) -> tuple:
    """(p_large, p_medium) for a party of effort E at game density g (gp: the forest's game parameters)."""
    gd = max(0.0, float(g)) ** float(gp["theta"])
    out = []
    for cls in ("large", "medium"):
        x = gp[cls]
        s = 1.0 - math.exp(-((max(0.0, E) / float(x["scale"])) ** float(x["shape"]))) if E > 0 else 0.0
        out.append(min(0.95, float(x["catch"])) * gd * s)
    return tuple(out)


def expected_catch(gp, E, g=1.0) -> float:
    """Expected food a party of effort E takes at game density g (before the stock cap): the doc table and the bot."""
    pl, pm = kill_chances(gp, E, g)
    small = (1 - pl) * (1 - pm) * E * min(0.95, float(gp["small"]["catch"])) * max(0.0, g) ** float(gp["theta"]) * float(gp["small"]["food"])
    return pl * float(gp["large"]["food"]) + (1 - pl) * pm * float(gp["medium"]["food"]) + small


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
        cid = self.camp["id"]
        pair = f" on {p['pair']}" if p.get("pair") else ""
        fell = (f"harvest {{\"camp\": \"{cid}\", \"fell\": true}} cuts {p['fell_timber']:g} timber and shrinks the forest for good"
                + (f"; every {p['clearing']} fells clear a new plot{pair}" if p.get("pair") else "") + ". ")
        return (f"An open forest (no right needed) with plants and game. harvest {{\"camp\": \"{cid}\"}} forages plants: up to "
                f"{p['yield']:g} food x stock/capacity per action (less when you are hungry; foraging never takes the last "
                f"{p['refuge']:.0%}). hunt {{\"camp\": \"{cid}\", \"party\": \"<name>\"}} hunts game, paid at the end of the round: "
                "alone you mostly catch small game; hunters who name the same party hunt together and have better chances of a "
                "deer or a large animal (shared by effort). " + fell + f"At most {p['per_round']} forest actions (forage, hunt or fell) "
                "per agent per round. Plants regrow fast, game slowly; both regrow faster at middling stocks than when stripped.")

    def state_line(self, k, aid) -> str:
        from charter import subsistence as SB
        c = self.camp
        g = c.get("game") or {}
        line = f"plants {c['S'] / c['K']:.0%} of capacity {c['K']:.3g} food"
        if g:
            line += f"; game {game_level(g['G'] / g['K'])}"
        mine = (c.get("hunts") or {}).get(aid)
        if mine:
            line += f"; you are hunting here this round ({mine['effort']} effort" + (f", party {mine['party']}" if mine["party"] else ", alone") + ")"
        season = SB.season_name(k)
        return line + (f"; season {season}" if season else "")

    def snapshot(self) -> dict:
        g = self.camp.get("game") or {}
        return {"K0": self.p["K0"], "fells": self.p.get("fells", 0), "cleared": self.p.get("cleared", 0),
                **({"game": round(g["G"] / g["K"], 4)} if g else {})}

    # ------------------------------------------------------------------ the forage and fell actions (framework.harvest_action)
    def check(self, k, aid) -> None:
        """May aid take one more forest action here now? The round budget over all forests, the camp's harvest limit, quota and
        fee (a law's rules). Raises the refusal."""
        from charter import subsistence as SB
        from charter.camptypes import framework as CT
        c, p = self.camp, self.p
        cid = c["id"]
        if not CT.can_take_part(k, aid, cid):
            raise CT._err(f"{cid} is open to every agent who eats, but not to you")
        if int(SB.state(k)["forage"].get(aid, 0)) >= int(p["per_round"]):
            raise CT._err(f"you have used your {p['per_round']} forest actions this round")
        key = f"{aid}|{cid}"
        cr = J.camp_rules(k, aid, cid)                                  # S6: the forager's polity's rules (D-37: members only;
        if cr["harvest_limit"] is not None and k.w["harvest_count"].get(key, 0) >= int(cr["harvest_limit"]):   # off/J0: the camp's)
            raise CT._err(f"harvest limit reached at {cid} this round ({cr['harvest_limit']})")
        if cr["quota"] is not None and k.w["quota_used"].get(cr["qkey"], 0) >= cr["quota"]:
            raise CT._err(f"the quota for {cid} is used up this round ({cr['quota']})")
        if cr["fee"] and k.bal(aid, cr["fee"]["item"]) + 1e-9 < float(cr["fee"]["qty"]):
            raise CT._err(f"cannot pay the harvest fee ({cr['fee']['qty']} {cr['fee']['item']})")

    def use(self, k, aid) -> None:
        """One forest action by aid (checked first): the fee is paid and the action counted."""
        from charter import subsistence as SB
        from charter.camptypes import framework as CT
        c = self.camp
        cid = c["id"]
        self.check(k, aid)
        cr = J.camp_rules(k, aid, cid)
        if cr["fee"]:
            if not k.move(aid, cr["reserve"], cr["fee"]["item"], cr["fee"]["qty"], why="harvest_fee", by=aid):
                raise CT._err(f"cannot pay the harvest fee ({cr['fee']['qty']} {cr['fee']['item']})")
        st = SB.state(k)
        key = f"{aid}|{cid}"
        st["forage"][aid] = int(st["forage"].get(aid, 0)) + 1
        k.w["harvest_count"][key] = k.w["harvest_count"].get(key, 0) + 1
        k.w["quota_used"][cr["qkey"]] = k.w["quota_used"].get(cr["qkey"], 0) + 1

    def _counters(self, k, aid) -> tuple:
        from charter import subsistence as SB
        cid = self.camp["id"]
        qkey = J.camp_rules(k, aid, cid)["qkey"]
        return (SB.state(k)["forage"].get(aid), k.w["harvest_count"].get(f"{aid}|{cid}"), qkey, k.w["quota_used"].get(qkey),
                self.camp["harvested_this_round"])

    def _restore(self, k, aid, undo) -> None:
        from charter import subsistence as SB
        cid = self.camp["id"]
        for d, key, v in ((SB.state(k)["forage"], aid, undo[0]), (k.w["harvest_count"], f"{aid}|{cid}", undo[1]),
                          (k.w["quota_used"], undo[2], undo[3])):
            if v is None:
                d.pop(key, None)
            else:
                d[key] = v
        self.camp["harvested_this_round"] = undo[4]

    def act(self, k, aid, x, extra) -> str:
        from charter import subsistence as SB
        from charter.camptypes import framework as CT
        c, p = self.camp, self.p
        cid = c["id"]
        extra = dict(extra or {})
        fell = extra.pop("fell", False)
        fell = fell is True or str(fell).lower() in ("true", "1", "yes")
        if "hunt" in extra or "party" in extra:
            raise CT._err(f"to hunt, use the hunt action: hunt {{\"camp\": \"{cid}\", \"party\": \"<name>\"}}")
        if extra:
            raise CT._err(f"{cid} takes only \"fell\": true (to fell) or nothing (to forage); not {', '.join(sorted(extra))}")
        if x not in (None, [], 0):
            raise CT._err(f"{cid} takes no x: harvest {{\"camp\": \"{cid}\"}} forages, with \"fell\": true it fells")
        undo = self._counters(k, aid)                                   # S6: a law's before_harvest may refuse the harvest; then
        self.use(k, aid)                                                # the action is not counted and the stock is untouched
        try:
            if fell:
                return self._fell(k, aid)
            left = max(0.0, c["S"] - c["harvested_this_round"])
            y = float(p["yield"]) * left / c["K"] * SB.yield_mult(k, aid)
            y = round(max(0.0, min(y, left - float(p["refuge"]) * c["K"])), 3)
            got, ded = CT.pay_yield(k, aid, cid, [], y, eff=y / float(p["yield"]) if p["yield"] else 0.0)
        except D.Blocked:
            self._restore(k, aid, undo)
            raise
        hungry = "" if SB.stage(k, aid) == 0 else " (you are hungry: you gather less)"
        return (f"Foraged {got - ded:.3g} food at {cid}" + (f" ({ded:.3g} deducted by law)" if ded else "") + hungry
                + f"; the plants are at {c['S'] / c['K']:.0%} of capacity before this round's regrowth.")

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
            f"; the forest's plant capacity is now {c['K']:.3g} food.{note}"

    # ------------------------------------------------------------------ the hunt (camps end of round, step 2)
    def end_of_round(self, k) -> list:
        """Resolve this round's hunting parties (see the module docstring). Returns the public round line."""
        from charter import mortality as MO
        from charter import subsistence as SB
        c, gp = self.camp, self.p.get("game")
        hunts, c["hunts"] = c.get("hunts") or {}, {}
        if not hunts or not gp or not c.get("game"):
            return []
        cid = c["id"]
        parties: dict = {}
        for aid in sorted(hunts):
            if aid not in k.w["agents"] or not MO.alive(k, aid) or k.w["agents"][aid].get("departed") is not None:
                continue
            h = hunts[aid]
            parties.setdefault(h["party"] or f"@{aid}", []).append(aid)
        lines = []
        for label in sorted(parties):
            members = parties[label]
            eff = {a: int(hunts[a]["effort"]) * SB.yield_mult(k, a) for a in members}
            units = sum(int(hunts[a]["effort"]) for a in members)
            E = sum(eff.values())
            g = c["game"]
            dens = g["G"] / g["K"] if g["K"] > 0 else 0.0
            rng = random.Random(f"{k.inst['seed']}|subsistence|hunt|{cid}|{k.r}|{label}")
            pl, pm = kill_chances(gp, E, dens)
            u = rng.random()
            if u < pl:
                kind, food = "a large animal", float(gp["large"]["food"])
            elif u < pl + (1 - pl) * pm:
                kind, food = "a deer", float(gp["medium"]["food"])
            else:
                ps = min(0.95, float(gp["small"]["catch"])) * max(0.0, dens) ** float(gp["theta"]) * (E / units if units else 0.0)
                n = sum(1 for _ in range(units) if rng.random() < ps)
                kind, food = (f"{n} small game" if n else "nothing"), n * float(gp["small"]["food"])
            food = max(0.0, min(round(food, 3), float(g["G"])))
            g["G"] = max(0.0, round(g["G"] - food, 4))
            names = ", ".join(members)
            for a in members:
                share = round(food * eff[a] / E, 3) if E > 0 else 0.0
                ded = 0.0
                if share > 0:
                    ded = k.apply("harvest", agent=a, camp=cid, x=[], item="food", qty=share, via="typed").result["deducted"]
                k.log("hunt_result", a, {"camp": cid, "party": None if label.startswith("@") else label, "hunters": members,
                                         "effort": round(E, 3), "catch": food, "kind": kind, "share": share, "deducted": ded,
                                         "text": (f"Your hunt at {cid}" + (f" (party {label}: {names})" if not label.startswith("@")
                                                                          else " (alone)") + f" took {kind}: {food:g} food; "
                                                  f"your share {share - ded:g}" + (f" ({ded:g} deducted by law)" if ded else "") + ".")},
                      vis=[a])
            st = c.setdefault("stats", {"yield": 0.0, "value": 0.0, "actions": 0, "rounds": 0})
            st["yield"] = round(st["yield"] + food, 6)
            st["actions"] += units
            lines.append(f"{len(members)} hunter(s) took {kind}" + (f" ({food:g} food)" if food else ""))
        return [{"public": f"hunting: {'; '.join(lines)}; game is {game_level(c['game']['G'] / c['game']['K'])}"}] if lines else []
