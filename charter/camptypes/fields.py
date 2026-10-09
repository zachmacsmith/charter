"""Fields (review 15 §2.4, S2): open land in plots; sow food, reap about mult x the seed some rounds later. Role `subsistence`:
never drawn into the standard set (charter/subsistence.py appends fields when subsistence is on).

    farm {"camp": c, "sow": qty, "plot": n?}   sow qty food (1..seed_max; the seed is used up: the crop is a claim, not goods) on a
                                               fallow plot (the lowest-numbered one if none is named)
    farm {"camp": c, "reap": n}                reap a ripe crop: seed x mult x fertility x (1 + noise) x what is left of it after
                                               rot, x the reaper's hunger multiplier; the plot is fallow again and its soil tires

Who may sow which plot and reap which crop is law (the sow and reap primitives, routed: before_sow / before_reap; review 15 U1). The
residual is liberty: anyone may sow a fallow plot or reap a ripe crop. Physics records the sower; the sower learns who reaped its
crop (the reap event reaches both). There is no kernel claim on an empty plot.

At the end of each round (subsistence step 1, world_step): a growing crop ripens at the start of round sown + grow (blight and its
yield noise are drawn then, from random.Random(f"{seed}|subsistence|crop|{camp}|{plot}|{sown}")); a blighted crop fails (the plot is
fallow); a ripe crop not reaped by the end of its first ripe round loses `rot` of what is left each round (gone below 5%); a fallow
plot regains fertility_gain (up to 1). Each harvest costs fertility_loss (floor fertility_floor). Plots: camp["plots"], a list of
{id, status (fallow | growing | ripe), sower, sown, seed, ripe, fertility, left, noise}.
"""
from __future__ import annotations

import random

from charter.camptypes import CampType, register

FOOD = "food"


@register("fields")
class Fields(CampType):
    role = "subsistence"
    resolves = "immediate"
    open_to_all = True
    standard = False
    wildcard_ok = False
    dial_based = False
    dials, max_level = 0, 0
    preferred_resource = "food"

    def describe(self, inst=None) -> str:
        p, c = self.p, self.camp
        return (f"Open fields with {len(c.get('plots') or [])} plots (no right needed). farm {{\"camp\": \"{c['id']}\", \"sow\": 1-"
                f"{p['seed_max']:g}}} sows that much of your food on a fallow plot (the seed is used up); about {p['grow']} rounds "
                f"later farm {{\"camp\": \"{c['id']}\", \"reap\": <plot>}} gives about {p['mult']:g}x the seed, less on tired soil "
                f"(each harvest tires it, fallow rounds rest it) and when you are hungry; a ripe crop left unreaped rots. Unless a law "
                "says otherwise anyone may sow a fallow plot or reap a ripe crop; the sower learns who reaped it.")

    def state_line(self, k, aid) -> str:
        ps = self.camp.get("plots") or []
        n = {s: sum(1 for p in ps if p["status"] == s) for s in ("fallow", "growing", "ripe")}
        ripe = [str(p["id"]) for p in ps if p["status"] == "ripe"]
        return (f"{n['fallow']} fallow, {n['growing']} growing, {n['ripe']} ripe plot(s)" + (f" (ripe: {', '.join(ripe)})" if ripe else ""))

    def snapshot(self) -> dict:
        return {"plots": [{x: p.get(x) for x in ("id", "status", "sower", "seed", "ripe", "fertility")} for p in self.camp.get("plots") or []]}

    def act(self, k, aid, x, extra) -> str:
        from charter.camptypes import framework as CT
        raise CT._err(f"{self.camp['id']} is farmed, not harvested: farm {{\"camp\": \"{self.camp['id']}\", \"sow\": 2}} or "
                      f"farm {{\"camp\": \"{self.camp['id']}\", \"reap\": <plot>}}")


def new_plot(pid, fertility=1.0) -> dict:
    return {"id": int(pid), "status": "fallow", "sower": None, "sown": None, "seed": 0.0, "ripe": None, "fertility": float(fertility),
            "left": 0.0, "noise": 0.0, "rested": None}


def _plot(c, pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    return next((p for p in c.get("plots") or [] if p["id"] == pid), None)


def _err(msg):
    from charter.actions import ActionError
    return ActionError(msg)


# ---------------------------------------------------------------------- the farm action (subsistence.act_farm hands it over)
def act(k, aid, cid, sow=None, reap=None, plot=None) -> str:
    from charter import subsistence as SB
    from charter.camptypes import framework as CT
    c = k.w["camps"].get(str(cid))
    if c is None or c.get("type") != "fields" or c.get("destroyed") is not None:
        raise _err(f"no fields camp {cid}. Fields: {', '.join(SB.fields_camps(k)) or 'none'}")
    cid = c["id"]
    if not CT.can_take_part(k, aid, cid):
        raise _err(f"{cid} is open to every agent who eats, but not to you")
    if (sow is None) == (reap is None):
        raise _err('name one of "sow": qty (food to sow) or "reap": <plot>')
    p = c["fn"]
    if sow is not None:
        try:
            q = float(sow)
        except (TypeError, ValueError):
            raise _err("sow is an amount of food (1 or more)")
        if q < 1 - 1e-9 or q > float(p["seed_max"]) + 1e-9:
            raise _err(f"sow between 1 and {p['seed_max']:g} food")
        if k.bal(aid, FOOD) + 1e-9 < q:
            raise _err(f"you have only {k.bal(aid, FOOD):.3g} food")
        if plot is not None:
            pl = _plot(c, plot)
            if pl is None:
                raise _err(f"{cid} has no plot {plot} (plots 1-{len(c['plots'])})")
            if pl["status"] != "fallow":
                raise _err(f"{cid} plot {pl['id']} is {pl['status']}, not fallow")
        else:
            pl = next((x for x in c["plots"] if x["status"] == "fallow"), None)
            if pl is None:
                raise _err(f"no fallow plot at {cid} this round")
        out = k.apply("sow", agent=aid, camp=cid, plot=pl["id"], qty=round(q, 6))
        if not out.ok:
            raise _err(f"a law blocked sowing {cid} plot {pl['id']}" + (f" ({out.reason})" if getattr(out, "reason", None) else ""))
        return (f"Sowed {q:g} food on {cid} plot {pl['id']} (fertility {pl['fertility']:.2f}); it ripens at the start of round "
                f"{pl['ripe'] + 1}.")
    pl = _plot(c, reap)
    if pl is None:
        raise _err(f"{cid} has no plot {reap}")
    if pl["status"] != "ripe":
        raise _err(f"{cid} plot {pl['id']} is {pl['status']}" + (f" (ripe at the start of round {pl['ripe'] + 1})"
                                                                   if pl["status"] == "growing" else "") + ": nothing to reap")
    y = round(pl["seed"] * float(p["mult"]) * pl["fertility"] * max(0.0, 1.0 + pl["noise"]) * pl["left"] * SB.yield_mult(k, aid), 3)
    sower = pl["sower"]
    out = k.apply("reap", agent=aid, camp=cid, plot=pl["id"], qty=y)
    if not out.ok:
        raise _err(f"a law blocked reaping {cid} plot {pl['id']}" + (f" ({out.reason})" if getattr(out, "reason", None) else ""))
    return (f"Reaped {y:.3g} food at {cid} plot {pl['id']}" + (f" (sown by {sower})" if sower != aid else "")
            + (" (you are hungry: you reap less)" if SB.stage(k, aid) != 0 else "") + ".")


# ---------------------------------------------------------------------- the changes (routed primitives sow and reap)
def change_sow(k, agent, camp, plot, qty) -> dict:
    """Sowing: the seed leaves the sower's food for good; the plot grows a crop recorded as the sower's (physics: who sowed)."""
    c = k.w["camps"][camp]
    pl = _plot(c, plot)
    k._add(agent, FOOD, -float(qty))
    pl.update({"status": "growing", "sower": agent, "sown": k.r, "seed": float(qty), "ripe": k.r + int(c["fn"]["grow"]),
               "left": 1.0, "noise": 0.0})
    k.log("sow", agent, {"camp": camp, "plot": pl["id"], "qty": float(qty), "ripe": pl["ripe"],
                         "text": f"{agent} sowed {float(qty):g} food on {camp} plot {pl['id']}"}, vis=[agent])
    return {"plot": pl["id"], "ripe": pl["ripe"]}


def change_reap(k, agent, camp, plot, qty) -> dict:
    """Reaping: the crop becomes the reaper's food; the plot is fallow and its soil tires. The sower learns who reaped it."""
    c = k.w["camps"][camp]
    p = c["fn"]
    pl = _plot(c, plot)
    sower = pl["sower"]
    if qty > 0:
        k._add(agent, FOOD, float(qty))
    pl["fertility"] = round(max(float(p["fertility_floor"]), pl["fertility"] - float(p["fertility_loss"])), 4)
    pl.update({"status": "fallow", "sower": None, "sown": None, "seed": 0.0, "ripe": None, "left": 0.0, "noise": 0.0, "rested": k.r})
    st = c.setdefault("stats", {"yield": 0.0, "value": 0.0, "actions": 0, "rounds": 0})
    st["yield"] = round(st["yield"] + float(qty), 6)
    st["value"] = round(st["value"] + float(qty) * float(k.w["unit"].get(FOOD, 1.0)), 6)
    st["actions"] += 1
    text = (f"{agent} reaped {float(qty):.3g} food at {camp} plot {pl['id']}" + (f", a crop {sower} sowed" if sower and sower != agent else ""))
    k.log("reap", agent, {"camp": camp, "plot": pl["id"], "qty": float(qty), "sower": sower, "text": text},
          vis=sorted({agent, sower} - {None}))
    return {"plot": pl["id"], "qty": float(qty), "sower": sower}


# ---------------------------------------------------------------------- the world (subsistence end of round, step 1)
def world_step(k, cid) -> None:
    c = k.w["camps"][cid]
    p = c["fn"]
    for pl in c.get("plots") or []:
        if pl["status"] == "growing" and k.r + 1 >= pl["ripe"]:
            rng = random.Random(f"{k.inst['seed']}|subsistence|crop|{cid}|{pl['id']}|{pl['sown']}")
            blight = rng.random() < float(p["blight"])
            pl["noise"] = round(rng.gauss(0.0, float(p["noise"])), 6)
            if blight:
                sower = pl["sower"]
                pl.update({"status": "fallow", "sower": None, "sown": None, "seed": 0.0, "ripe": None, "left": 0.0, "rested": k.r})
                if sower in k.w["agents"]:
                    k.log("crop_failed", sower, {"camp": cid, "plot": pl["id"], "text": f"The crop on {cid} plot {pl['id']} failed (blight)."},
                          vis=[sower])
            else:
                pl["status"] = "ripe"
        elif pl["status"] == "ripe" and k.r >= pl["ripe"]:
            pl["left"] = round(pl["left"] * (1.0 - float(p["rot"])), 6)
            if pl["left"] < 0.05:
                sower = pl["sower"]
                pl.update({"status": "fallow", "sower": None, "sown": None, "seed": 0.0, "ripe": None, "left": 0.0, "rested": k.r})
                if sower in k.w["agents"]:
                    k.log("crop_failed", sower, {"camp": cid, "plot": pl["id"], "text": f"The crop on {cid} plot {pl['id']} rotted unreaped."},
                          vis=[sower])
        elif pl["status"] == "fallow" and pl.get("rested") != k.r:
            pl["fertility"] = round(min(1.0, pl["fertility"] + float(p["fertility_gain"])), 4)


def clear_plot(k, cid, by=None):
    """Clearing (a forest's fells): one new fallow plot on fields cid, up to the world's plot ceiling. Returns its id or None."""
    from charter import subsistence as SB
    c = k.w["camps"].get(cid)
    if c is None or c.get("type") != "fields":
        return None
    total = sum(len(k.w["camps"][f].get("plots") or []) for f in SB.fields_camps(k))
    if total >= int(c["fn"].get("plots_max", 0)):
        return None
    pid = max([p["id"] for p in c["plots"]] or [0]) + 1
    c["plots"].append(new_plot(pid))
    k.log("plot_cleared", by, {"camp": cid, "plot": pid, "text": f"A new plot was cleared on {cid} (plot {pid})."}, vis="public")
    return pid
