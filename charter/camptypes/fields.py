"""Fields and farms (review 15 §2.4 and §2.7, S2; engine 14: docs/review/31_institutions/01b_farming.md): land in plots; sow food,
tend the crop, reap about mult x the seed some rounds later. Role `subsistence`: never drawn into the standard set
(charter/subsistence.py appends fields when subsistence.fields.enabled is on; off by default).

Farms. A plot is open (holder None: anyone may sow it or reap its crop, as before) or held by an agent or an institution (an
association A1, or a polity such as J0). The plots one holder holds at one fields camp are its farm there (camp["farms"][holder]:
allow, share, deliver, shed). Only those who may work a held plot sow, tend or reap it:
    the holder (an agent); an institution's officers and, for an association, its members; anyone on the farm's allow list.
The holder (an institution's officers; an association without offices: any member) sets the farm with farm {"camp", "allow" |
"disallow" | "share" | "deliver" | "give"}: who else may work it, the share of a crop someone else reaps that goes to the holder
automatically (default fields.share, 1: a hand's harvest belongs to the farm; 0.5: sharecropping; 0: a free lease), the store that
share is delivered to (the holder's own or one of its institution's), and whom to hand plots to. Plots come from the spec's
start.farms (round 0), from clearing (the clearer holds the new plot) and from a holder's gift; laws see holdings (plots(camp),
farms(camp)) and can gate every step (before_sow, before_tend, before_reap, before_set_farm, before_improve, before_clear,
before_learn): the engine's rule above is the residual.

    farm {"camp": c, "sow": qty, "plot": n?}   sow qty food (1 up to the plot's seed cap) on a fallow plot you may work (yours
                                               first, then a farm that lets you, then an open one); the seed is used up
    farm {"camp": c, "reap": n}                reap a ripe crop: seed x (mult + irrigation) x fertility x (1 + tending) x (1 + noise)
                                               x what is left of it after rot, x the reaper's hunger multiplier
    tend {"camp": c, "plot": n?}               work a growing crop: + tend.bonus[i] of its yield for the i-th tend (15%, 7%, then
                                               nothing), at most once per plot per round; each tend also cuts the harvest's soil loss
    improve {"kind", "camp", "plot"?}          terraces (a plot: + seed cap), irrigation (a plot: + mult, blight halved), shed (a
                                               farm: rot slowed), plough (a good: one sow, tend or reap covers 2 plots, "plots":
                                               [a, b]; it breaks with a small chance per use); paid in materials, used up
    practice {"learn" | "teach", "to"?}        skills: rotation (the sower's harvests do not tire the soil), seed selection (the
                                               sower's crops ripen a round sooner); learnt by practice or taught
    clear {"camp": forest}                     clearing work at a forest; every clear.work units clear a plot on its paired fields,
                                               held by the clearer; the forest loses clear.plants plant capacity and clear.game game
                                               capacity for good (calibrated so a field yields less than the same forest area
                                               sustainably managed)

Improvements and upkeep. Land works (terraces, irrigation) belong to the plot: they stay with the land when it changes hands, which is
what makes tenure worth securing (review 15 §2.7). The drying shed belongs to the farm (one per holder per camp; it stands on the
farm's land). At the end of every fields.upkeep_every-th round each improvement level pays its upkeep from the holder's holdings (an
institution's treasury); unpaid, it loses a level (the holder, or the institution's officers, are told).

The world (subsistence end of round, step 1, world_step): a growing crop ripens at the start of round sown + grow (seed selection: a
round sooner; blight and the yield noise are drawn then, from random.Random(f"{seed}|subsistence|crop|{camp}|{plot}|{sown}");
irrigation halves the blight; a scheduled shock's spell adds its own blight); a blighted crop fails; a ripe crop not reaped by the end
of its first ripe round loses `rot` of what is left each round (x the farm's shed; gone below 5%); a fallow plot regains
fertility_gain (up to 1). Each harvest costs fertility_loss x (1 - tend.soil x tends) (none when the sower knows rotation; floor
fertility_floor). Plots: camp["plots"], a list of {id, status (fallow | growing | ripe), holder, sower, sown, seed, ripe, fertility,
left, noise, tends, tended, works}.
"""
from __future__ import annotations

import random

from charter.camptypes import CampType, register

FOOD = "food"
PLOUGH = "plough"
LAND_WORKS = ("terraces", "irrigation")                                 # per plot
FARM_WORKS = ("shed",)                                                  # per farm (holder x camp)
KINDS = LAND_WORKS + FARM_WORKS + (PLOUGH,)
SKILLS = ("rotation", "seed_selection")


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
        ps = c.get("plots") or []
        return (f"Fields with {len(ps)} plots, some open land, some held as farms. farm {{\"camp\": \"{c['id']}\", \"sow\": "
                f"1-{p['seed_max']:g}}} sows that much of your food on a fallow plot you may work (the seed is used up); about "
                f"{p['grow']} rounds later farm {{\"camp\": \"{c['id']}\", \"reap\": <plot>}} gives about {p['mult']:g}x the seed, "
                "more when tended (tend), less on tired soil (each harvest tires it, fallow rounds rest it) and when you are hungry; a "
                "ripe crop left unreaped rots. A held plot is worked only by its holder and whom the holder allows; an open plot by "
                "anyone, unless a law says otherwise.")

    def state_line(self, k, aid) -> str:
        ps = self.camp.get("plots") or []
        op = [p for p in ps if not p.get("holder")]
        n = {s: sum(1 for p in op if p["status"] == s) for s in ("fallow", "growing", "ripe")}
        ripe = [str(p["id"]) for p in op if p["status"] == "ripe"]
        return (f"{len(ps) - len(op)} plots held as farms; open plots: {n['fallow']} fallow, {n['growing']} growing, {n['ripe']} ripe"
                + (f" (ripe: {', '.join(ripe)})" if ripe else ""))

    def snapshot(self) -> dict:
        return {"plots": [{x: p.get(x) for x in ("id", "status", "holder", "sower", "seed", "ripe", "fertility", "tends", "works")}
                          for p in self.camp.get("plots") or []]}

    def act(self, k, aid, x, extra) -> str:
        from charter.camptypes import framework as CT
        raise CT._err(f"{self.camp['id']} is farmed, not harvested: farm {{\"camp\": \"{self.camp['id']}\", \"sow\": 2}} or "
                      f"farm {{\"camp\": \"{self.camp['id']}\", \"reap\": <plot>}}")


def new_plot(pid, fertility=1.0, holder=None) -> dict:
    return {"id": int(pid), "status": "fallow", "holder": holder, "sower": None, "sown": None, "seed": 0.0, "ripe": None,
            "fertility": float(fertility), "left": 0.0, "noise": 0.0, "rested": None, "tends": 0, "tended": None, "works": {}}


def _plot(c, pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    return next((p for p in c.get("plots") or [] if p["id"] == pid), None)


def _err(msg):
    from charter.actions import ActionError
    return ActionError(msg)


def fcfg(k) -> dict:
    from charter import subsistence as SB
    return SB.cfg(k.spec)["fields"]


def _fields(k, cid):
    from charter import subsistence as SB
    c = k.w["camps"].get(str(cid)) if cid is not None else None
    if c is None or c.get("type") != "fields" or c.get("destroyed") is not None:
        raise _err(f"no fields camp {cid}. Fields: {', '.join(SB.fields_camps(k)) or 'none'}")
    return c


# ---------------------------------------------------------------------- holdings: who holds, who manages, who may work
def is_agent(k, h) -> bool:
    return h in k.w["agents"]


def farm(k, c, holder, create=True):
    """The farm record of holder at fields camp c ({allow, share, deliver, shed}); created with the defaults when missing."""
    fs = c.setdefault("farms", {}) if create else (c.get("farms") or {})
    f = fs.get(holder)
    if f is None and create:
        f = fs[holder] = {"allow": [], "share": float(fcfg(k)["share"]), "deliver": None, "shed": 0}
    return f


def farm_plots(c, holder) -> list:
    return [p for p in c.get("plots") or [] if p.get("holder") == holder]


def managers(k, h) -> list:
    """Who sets a holder's farms: the agent itself; an institution's officers (an association without offices: its members)."""
    if h is None:
        return []
    if is_agent(k, h):
        return [h]
    from charter import institutions as I
    off = I.officers(k, h)
    if off:
        return off
    return list(I.members(k, h)) if I.kind_of(k, h) == "association" else []


def workers_note(k, h) -> str:
    if is_agent(k, h):
        return h
    from charter import institutions as I
    return f"{h}'s officers" + (" and members" if I.kind_of(k, h) == "association" else "")


def may_work(k, aid, c, pl) -> str | None:
    """Why aid may not sow, tend or reap plot pl (None: it may). Open plots: anyone (a law may say otherwise)."""
    h = pl.get("holder")
    if h is None or h == aid:
        return None
    if not is_agent(k, h):
        from charter import institutions as I
        if aid in I.officers(k, h) or (I.kind_of(k, h) == "association" and I.is_member(k, h, aid)):
            return None
    f = farm(k, c, h, create=False) or {}
    if aid in (f.get("allow") or ()):
        return None
    return (f"{c['id']} plot {pl['id']} is {h}'s farm: only {workers_note(k, h)} and those {h} allows may work it "
            f"(farm {{\"camp\": \"{c['id']}\", \"allow\": \"{aid}\"}} by {h if is_agent(k, h) else 'its officers'})")


def account_of(k, h) -> str:
    """The account a holder pays upkeep from and receives its crop share in: an agent's holdings, an institution's treasury."""
    if is_agent(k, h):
        return h
    from charter import accounts as AC
    return AC.treasury_of(k, h)


def _rank(k, aid, c, pl) -> int:
    """Auto-choice order: plots aid holds, then plots of a farm it may work, then open plots."""
    h = pl.get("holder")
    return 0 if h == aid else (2 if h is None else 1)


def workable(k, aid, c, status) -> list:
    """Plots of c with this status that aid may work, in auto-choice order (own, a farm's that lets it, open; then id)."""
    out = [p for p in c.get("plots") or [] if p["status"] == status and may_work(k, aid, c, p) is None]
    return sorted(out, key=lambda p: (_rank(k, aid, c, p), p["id"]))


# ---------------------------------------------------------------------- dials: what improvements and skills do
def skills(k, aid) -> dict:
    from charter import subsistence as SB
    return ((SB.state(k).get("farming") or {}).get("skills") or {}).get(aid) or {}


def knows(k, aid, skill) -> bool:
    return bool(aid) and bool(skills(k, aid).get(skill))


def grow_for(k, c, sower) -> int:
    g = int(c["fn"]["grow"])
    if knows(k, sower, "seed_selection"):
        g -= int(fcfg(k)["skills"]["seed_selection"]["grow"])
    return max(1, g)


def seed_cap(k, c, pl) -> float:
    t = int((pl.get("works") or {}).get("terraces", 0))
    return float(c["fn"]["seed_max"]) + t * float(fcfg(k)["improvements"]["terraces"]["seed"])


def plot_mult(k, c, pl) -> float:
    i = int((pl.get("works") or {}).get("irrigation", 0))
    return float(c["fn"]["mult"]) + i * float(fcfg(k)["improvements"]["irrigation"]["mult"])


def tend_bonus(k, pl) -> float:
    b = [float(x) for x in fcfg(k)["tend"]["bonus"]]
    return sum(b[:int(pl.get("tends") or 0)])


def shed_of(k, c, pl) -> int:
    h = pl.get("holder")
    return int((farm(k, c, h, create=False) or {}).get("shed", 0)) if h else 0


def expected_yield(k, c, pl, aid=None) -> float:
    """The crop's yield if reaped now by aid (or a fed reaper)."""
    from charter import subsistence as SB
    hm = SB.yield_mult(k, aid) if aid else 1.0
    return round(pl["seed"] * plot_mult(k, c, pl) * pl["fertility"] * (1.0 + tend_bonus(k, pl)) * max(0.0, 1.0 + pl["noise"])
                 * pl["left"] * hm, 3)


def _plough(k, aid, targets, verb) -> None:
    if len(targets) <= 1:
        return
    n = int(fcfg(k)["improvements"][PLOUGH]["plots"])
    if k.bal(aid, PLOUGH) + 1e-9 < 1:
        raise _err(f"one {verb} covers several plots only with a plough (improve {{\"kind\": \"plough\"}})")
    if len(targets) > n:
        raise _err(f"a plough covers at most {n} plots in one action")


def _plough_wear(k, aid, used) -> str:
    """A plough used on more than one plot may break (fields.improvements.plough.break, own stream). Returns a note."""
    if used <= 1:
        return ""
    from charter import subsistence as SB
    fm = SB.state(k).setdefault("farming", {})
    uses = fm.setdefault("plough_uses", {})
    uses[aid] = int(uses.get(aid, 0)) + 1
    u = random.Random(f"{k.inst['seed']}|subsistence|plough|{aid}|{uses[aid]}").random()
    if u < float(fcfg(k)["improvements"][PLOUGH]["break"]):
        k.apply("farm_upkeep", holder=aid, camp=None, plot=None, kind=PLOUGH, paid=False)
        return " Your plough broke."
    return ""


def _targets(k, aid, c, plot, plots, status, verb) -> list:
    """The plots one farm action works: `plots` (a list: a plough's), else `plot`, else the first workable plot with status."""
    cid = c["id"]
    if plots is not None:
        ids = plots if isinstance(plots, list) else [plots]
    elif plot is not None:
        ids = [plot]
    else:
        auto = workable(k, aid, c, status)
        if not auto:
            raise _err(f"no {status} plot at {cid} that you may work" + ("" if status != "fallow" else " this round"))
        return [auto[0]]
    out = []
    for x in ids:
        pl = _plot(c, x)
        if pl is None:
            raise _err(f"{cid} has no plot {x} (plots 1-{len(c['plots'])})")
        if pl in out:
            raise _err(f"plot {pl['id']} is named twice")
        out.append(pl)
    _plough(k, aid, out, verb)
    for pl in out:
        why = may_work(k, aid, c, pl)
        if why:
            raise _err(why)
    return out


def _blocked(out, what) -> None:
    if not out.ok:
        raise _err(f"a law blocked {what}" + (f" ({out.reason})" if getattr(out, "reason", None) else ""))


def _apply(k, name, what, **payload):
    from charter import dispatch as D
    try:
        out = k.apply(name, **payload)
    except D.Blocked as e:
        raise _err(f"a law blocked {what} ({', '.join(e.by)}" + (f": {e.why})" if e.why else ")"))
    _blocked(out, what)
    return out


# ---------------------------------------------------------------------- the farm action (subsistence.act_farm hands it over)
SETTINGS = ("allow", "disallow", "share", "deliver", "give")


def act(k, aid, cid, sow=None, reap=None, plot=None, plots=None, **kw) -> str:
    from charter.camptypes import framework as CT
    c = _fields(k, cid)
    cid = c["id"]
    if not CT.can_take_part(k, aid, cid):
        raise _err(f"{cid} is open to every agent who eats, but not to you")
    given = [x for x in SETTINGS if kw.get(x) is not None]
    if (sow is not None) + (reap is not None) + len(given) != 1:
        raise _err('name one of "sow": qty (food to sow), "reap": <plot>, or a farm setting ("allow", "disallow", "share", '
                   '"deliver", "give")')
    if given:
        return set_farm(k, aid, c, given[0], kw[given[0]], to=kw.get("to"), as_=kw.get("as"), plots=plots if plots is not None
                        else plot)
    if sow is not None:
        try:
            q = float(sow)
        except (TypeError, ValueError):
            raise _err("sow is an amount of food (1 or more)")
        targets = _targets(k, aid, c, plot, plots, "fallow", "sowing")
        for pl in targets:
            if pl["status"] != "fallow":
                raise _err(f"{cid} plot {pl['id']} is {pl['status']}, not fallow")
            cap = seed_cap(k, c, pl)
            if q < 1 - 1e-9 or q > cap + 1e-9:
                raise _err(f"sow between 1 and {cap:g} food" + (f" on plot {pl['id']}" if len(targets) > 1 else ""))
        if k.bal(aid, FOOD) + 1e-9 < q * len(targets):
            raise _err(f"you have only {k.bal(aid, FOOD):.3g} food")
        done = []
        for pl in targets:
            _apply(k, "sow", f"sowing {cid} plot {pl['id']}", agent=aid, camp=cid, plot=pl["id"], qty=round(q, 6))
            done.append(pl)
        note = _plough_wear(k, aid, len(done))
        return ("Sowed " + "; ".join(f"{q:g} food on {cid} plot {pl['id']} (fertility {pl['fertility']:.2f}); it ripens at the "
                                     f"start of round {pl['ripe'] + 1}" for pl in done) + "." + note)
    if isinstance(reap, list):
        plots, reap = reap, None
    targets = _targets(k, aid, c, reap, plots, "ripe", "harvest")
    for pl in targets:
        if pl["status"] != "ripe":
            raise _err(f"{cid} plot {pl['id']} is {pl['status']}" + (f" (ripe at the start of round {pl['ripe'] + 1})"
                                                                       if pl["status"] == "growing" else "") + ": nothing to reap")
    from charter import subsistence as SB
    parts = []
    for pl in targets:
        y = expected_yield(k, c, pl, aid)
        sower, holder = pl["sower"], pl.get("holder")
        out = _apply(k, "reap", f"reaping {cid} plot {pl['id']}", agent=aid, camp=cid, plot=pl["id"], qty=y)
        share = float((out.result or {}).get("to_holder") or 0.0)
        parts.append(f"Reaped {y:.3g} food at {cid} plot {pl['id']}" + (f" (sown by {sower})" if sower and sower != aid else "")
                     + (f"; {share:.3g} of it went to the farm's holder {holder}" if share > 0 else ""))
    note = _plough_wear(k, aid, len(targets))
    return "; ".join(parts) + (" (you are hungry: you reap less)" if SB.stage(k, aid) != 0 else "") + "." + note


def act_tend(k, aid, cid, plot=None, plots=None) -> str:
    """tend {"camp", "plot"?}: one tend of a growing crop on a plot aid may work (the routed `tend` primitive)."""
    from charter.camptypes import framework as CT
    c = _fields(k, cid)
    cid = c["id"]
    if not CT.can_take_part(k, aid, cid):
        raise _err(f"{cid} is open to every agent who eats, but not to you")
    bonus = [float(x) for x in fcfg(k)["tend"]["bonus"]]
    if plot is None and plots is None:
        auto = [p for p in workable(k, aid, c, "growing") if p.get("tended") != k.r and int(p.get("tends") or 0) < len(bonus)]
        if not auto:
            raise _err(f"no growing crop at {cid} that you may work and that tending would still help this round")
        auto.sort(key=lambda p: (_rank(k, aid, c, p), int(p.get("tends") or 0), p["id"]))
        targets = [auto[0]]
    else:
        targets = _targets(k, aid, c, plot, plots, "growing", "tend")
    for pl in targets:
        if pl["status"] != "growing":
            raise _err(f"{cid} plot {pl['id']} is {pl['status']}: only a growing crop is tended")
        if pl.get("tended") == k.r:
            raise _err(f"{cid} plot {pl['id']} was tended this round already (once per round)")
        if int(pl.get("tends") or 0) >= len(bonus):
            raise _err(f"{cid} plot {pl['id']} has been tended {pl['tends']} times: more tending adds nothing to this crop")
    out = []
    for pl in targets:
        i = int(pl.get("tends") or 0)
        _apply(k, "tend", f"tending {cid} plot {pl['id']}", agent=aid, camp=cid, plot=pl["id"])
        out.append(f"Tended {cid} plot {pl['id']} (+{bonus[i]:.0%} yield; {pl['tends']} tend{'s' if pl['tends'] != 1 else ''} "
                   f"of this crop, +{tend_bonus(k, pl):.0%} in all)")
    return "; ".join(out) + "." + _plough_wear(k, aid, len(targets))


# ---------------------------------------------------------------------- farm settings (the routed `set_farm` primitive)
def _managed(k, aid, as_=None) -> str:
    """The holder whose farm aid sets: aid itself, or (as_) an institution aid manages."""
    if as_ in (None, "", aid, "me", "self"):
        return aid
    h = str(as_)
    if aid not in managers(k, h):
        raise _err(f"you do not manage {h}'s farms (its officers do" + ("; without offices, its members" if not is_agent(k, h) else "")
                   + ")")
    return h


def set_farm(k, aid, c, key, value, to=None, as_=None, plots=None) -> str:
    cid = c["id"]
    h = _managed(k, aid, as_)
    mine = farm_plots(c, h)
    if not mine:
        raise _err(f"{h if h != aid else 'you'} hold{'s' if h != aid else ''} no plot at {cid}")
    if key in ("allow", "disallow"):
        names = value if isinstance(value, list) else [value]
        for x in names:
            if str(x) not in k.w["agents"]:
                raise _err(f"no agent {x}")
        value = [str(x) for x in names]
    elif key == "share":
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise _err("share is the part of a crop someone else reaps that goes to the holder: 0 to 1")
        if not 0 <= value <= 1:
            raise _err("share is between 0 and 1")
    elif key == "deliver":
        from charter import subsistence as SB
        sid = str(value)
        sid = sid[len(SB.STORE):] if sid.startswith(SB.STORE) else sid
        if sid.lower() in ("none", "null", "", "me", "self", "hands", "treasury"):
            value = None
        else:
            s = SB.state(k)["stores"].get(sid)
            if s is None:
                raise _err(f"no store {sid}")
            if s["owner"] != h:
                raise _err(f"store {sid} is {s['owner']}'s: a farm delivers only to its holder's own store")
            value = sid
    elif key == "give":
        if to is None:
            raise _err('give needs "to": the agent or institution that will hold the plots')
        from charter import institutions as I
        if str(to) not in k.w["agents"] and I.get(k, str(to)) is None and str(to) != "J0":
            raise _err(f"no agent or institution {to}")
        ids = [p["id"] for p in mine] if value in ("all", True) else (value if isinstance(value, list) else [value])
        got = []
        for x in ids:
            pl = _plot(c, x)
            if pl is None or pl.get("holder") != h:
                raise _err(f"{cid} plot {x} is not {'yours' if h == aid else h + chr(39) + 's'}")
            got.append(pl["id"])
        value = {"plots": got, "to": str(to)}
    _apply(k, "set_farm", f"this change to the farm at {cid}", agent=aid, camp=cid, holder=h, key=key, value=value)
    f = farm(k, c, h, create=False) or {}
    if key == "give":
        return f"Handed {cid} plot{'s' if len(value['plots']) > 1 else ''} {', '.join(map(str, value['plots']))} to {value['to']}."
    if key in ("allow", "disallow"):
        return f"The farm at {cid} now lets work it: {', '.join(f['allow']) or 'nobody else'}."
    if key == "share":
        return f"Of a crop someone else reaps on the farm at {cid}, {f['share']:.0%} now goes to {h}."
    return f"The farm at {cid} now delivers its share to " + (f"store {f['deliver']}." if f.get("deliver") else f"{h}'s holdings.")


def change_set_farm(k, agent, camp, holder, key, value) -> dict:
    """A farm setting (law: who may set what on which land; land registries, tenancy law): the allow list, the crop share, the
    delivery store, or plots handed to a new holder (the land works go with the plots; a new farm takes the defaults)."""
    c = k.w["camps"][camp]
    f = farm(k, c, holder)
    if key == "allow":
        f["allow"] = sorted(set(f["allow"]) | set(value))
    elif key == "disallow":
        f["allow"] = [x for x in f["allow"] if x not in set(value)]
    elif key == "share":
        f["share"] = float(value)
    elif key == "deliver":
        f["deliver"] = value
    elif key == "give":
        for pid in value["plots"]:
            _plot(c, pid)["holder"] = value["to"]
        farm(k, c, value["to"])
        if not farm_plots(c, holder):                                     # the giver keeps no plot here: its farm (and shed) go
            shed = f.get("shed", 0)
            c["farms"].pop(holder, None)
            if shed:
                farm(k, c, value["to"])["shed"] = max(int(farm(k, c, value["to"])["shed"]), int(shed))
    text = {"allow": f"{agent} lets {', '.join(value) if isinstance(value, list) else value} work {holder}'s farm at {camp}",
            "disallow": f"{agent} no longer lets {', '.join(value) if isinstance(value, list) else value} work {holder}'s farm at {camp}",
            "share": f"{agent} set the crop share of {holder}'s farm at {camp} to {float(value):.0%}" if key == "share" else "",
            "deliver": f"{agent} set {holder}'s farm at {camp} to deliver to " + (f"store {value}" if value else "its holder"),
            "give": (f"{agent} handed {camp} plot(s) {', '.join(map(str, value['plots']))} from {holder} to {value['to']}"
                     if key == "give" else "")}[key]
    vis = sorted(({agent} | ({holder} if holder in k.w["agents"] else set())
                  | (set(value) if key in ("allow", "disallow") else set())
                  | ({value["to"]} if key == "give" and value["to"] in k.w["agents"] else set())) & set(k.w["agents"]))
    k.log("farm_set", agent, {"camp": camp, "holder": holder, "key": key, "value": value, "text": text},
          vis="public" if key == "give" else vis)
    return {"holder": holder, "key": key}


# ---------------------------------------------------------------------- the changes (routed primitives sow, tend and reap)
def change_sow(k, agent, camp, plot, qty) -> dict:
    """Sowing: the seed leaves the sower's food for good; the plot grows a crop recorded as the sower's (physics: who sowed)."""
    c = k.w["camps"][camp]
    pl = _plot(c, plot)
    k._add(agent, FOOD, -float(qty))
    pl.update({"status": "growing", "sower": agent, "sown": k.r, "seed": float(qty), "ripe": k.r + grow_for(k, c, agent),
               "left": 1.0, "noise": 0.0})
    if "tends" in pl:
        pl.update({"tends": 0, "tended": None})
    vis = sorted({agent} | ({pl["holder"]} if pl.get("holder") in k.w["agents"] else set()))
    k.log("sow", agent, {"camp": camp, "plot": pl["id"], "qty": float(qty), "ripe": pl["ripe"], "holder": pl.get("holder"),
                         "text": f"{agent} sowed {float(qty):g} food on {camp} plot {pl['id']}"}, vis=vis)
    return {"plot": pl["id"], "ripe": pl["ripe"]}


def change_tend(k, agent, camp, plot) -> dict:
    """Tending (labour on a growing crop): one more tend of this crop (its yield bonus and soil care are read at the harvest)."""
    c = k.w["camps"][camp]
    pl = _plot(c, plot)
    pl["tends"] = int(pl.get("tends") or 0) + 1
    pl["tended"] = k.r
    vis = sorted({agent} | ({pl["holder"]} if pl.get("holder") in k.w["agents"] else set()))
    k.log("tend", agent, {"camp": camp, "plot": pl["id"], "tends": pl["tends"], "holder": pl.get("holder"),
                          "text": f"{agent} tended the crop on {camp} plot {pl['id']} ({pl['tends']}x)"}, vis=vis)
    return {"plot": pl["id"], "tends": pl["tends"]}


def change_reap(k, agent, camp, plot, qty) -> dict:
    """Reaping: the crop becomes the reaper's food, less the farm's share when the plot is held by another (paid at once to the
    holder: its delivery store while it has room, else its holdings or treasury); the plot is fallow and its soil tires (less when
    tended, not at all when the sower knows rotation). The sower and the holder learn who reaped it."""
    from charter import subsistence as SB
    c = k.w["camps"][camp]
    p = c["fn"]
    pl = _plot(c, plot)
    sower, holder = pl["sower"], pl.get("holder")
    qty = float(qty)
    to_holder = 0.0
    if holder and holder != agent and qty > 0:
        f = farm(k, c, holder)
        to_holder = round(qty * float(f.get("share", 1.0)), 6)
    if qty - to_holder > 0:
        k._add(agent, FOOD, qty - to_holder)
    if to_holder > 0:
        left = to_holder
        sid = (farm(k, c, holder, create=False) or {}).get("deliver")
        s = SB.state(k)["stores"].get(sid) if sid else None
        if s is not None and s["owner"] == holder:
            room = max(0.0, float(s["capacity"]) - float(s["holdings"].get(FOOD, 0.0)))
            q = round(min(room, left), 6)
            if q > 0:
                k._add(f"{SB.STORE}{sid}", FOOD, q)
                left = round(left - q, 6)
        if left > 0:
            k._add(account_of(k, holder), FOOD, left)
    loss = float(p["fertility_loss"])
    if "tends" in pl:                                                   # engine 14 farming (plots made before it have no tends)
        fc = fcfg(k)
        loss *= max(0.0, 1.0 - float(fc["tend"]["soil"]) * min(int(pl.get("tends") or 0), len(fc["tend"]["bonus"])))
        if knows(k, sower, "rotation"):
            loss *= float(fc["skills"]["rotation"]["loss"])
    pl["fertility"] = round(max(float(p["fertility_floor"]), pl["fertility"] - loss), 4) if loss > 0 else pl["fertility"]
    pl.update({"status": "fallow", "sower": None, "sown": None, "seed": 0.0, "ripe": None, "left": 0.0, "noise": 0.0, "rested": k.r})
    if "tends" in pl:
        pl.update({"tends": 0, "tended": None})
    st = c.setdefault("stats", {"yield": 0.0, "value": 0.0, "actions": 0, "rounds": 0})
    st["yield"] = round(st["yield"] + qty, 6)
    st["value"] = round(st["value"] + qty * float(k.w["unit"].get(FOOD, 1.0)), 6)
    st["actions"] += 1
    if "tends" in pl and sower:
        fm = SB.state(k).setdefault("farming", {})
        fm.setdefault("reaped", {})[agent] = int(fm.get("reaped", {}).get(agent, 0)) + 1
    text = (f"{agent} reaped {qty:.3g} food at {camp} plot {pl['id']}" + (f", a crop {sower} sowed" if sower and sower != agent else "")
            + (f"; {to_holder:.3g} of it went to {holder}, the plot's holder" if to_holder > 0 else ""))
    k.log("reap", agent, {"camp": camp, "plot": pl["id"], "qty": qty, "sower": sower, "holder": holder, "to_holder": to_holder,
                          "text": text}, vis=sorted(({agent, sower} | ({holder} if holder in k.w["agents"] else set())) - {None}))
    return {"plot": pl["id"], "qty": qty, "sower": sower, "to_holder": to_holder}


# ---------------------------------------------------------------------- improvements (the routed `improve` primitive) and upkeep
def act_improve(k, aid, kind, camp=None, plot=None, as_=None) -> str:
    """improve {"kind", "camp"?, "plot"?, "as"?}: terraces or irrigation on a plot of a farm aid holds or manages, a shed on such a
    farm, or a plough (a good in aid's hands). The cost (fields.improvements.<kind>.cost) is paid by aid and used up."""
    kind = str(kind or "").lower().replace(" ", "_")
    kind = {"terrace": "terraces", "irrigate": "irrigation", "drying_shed": "shed", "ploughs": PLOUGH, "plow": PLOUGH}.get(kind, kind)
    imp = fcfg(k)["improvements"]
    if kind not in KINDS:
        raise _err(f"improve kinds: {', '.join(KINDS)}")
    cost = {i: float(q) for i, q in imp[kind]["cost"].items()}
    target, holder = None, None
    cid = None
    if kind != PLOUGH:
        c = _fields(k, camp)
        cid = c["id"]
        holder = _managed(k, aid, as_)
        mine = farm_plots(c, holder)
        if not mine:
            raise _err(f"{'you hold' if holder == aid else holder + ' holds'} no plot at {cid}: improvements go on a farm's land")
        mx = int(imp[kind]["max"])
        if kind in LAND_WORKS:
            if plot is None:
                pl = next((p for p in mine if int(p["works"].get(kind, 0)) < mx), None)
                if pl is None:
                    raise _err(f"every plot of the farm at {cid} has {kind} at its most ({mx})")
            else:
                pl = _plot(c, plot)
                if pl is None or pl.get("holder") != holder:
                    raise _err(f"{cid} plot {plot} is not {'yours' if holder == aid else holder + chr(39) + 's'}")
                if int(pl["works"].get(kind, 0)) >= mx:
                    raise _err(f"{cid} plot {pl['id']} has {kind} at its most ({mx})")
            target = pl["id"]
        elif int(farm(k, c, holder)["shed"]) >= mx:
            raise _err(f"the farm at {cid} has its shed already")
    if not all(k.bal(aid, i) + 1e-9 >= q for i, q in cost.items()):
        raise _err(f"{kind} costs " + ", ".join(f"{q:g} {i}" for i, q in cost.items()) + "; you have "
                   + ", ".join(f"{k.bal(aid, i):g} {i}" for i in cost))
    _apply(k, "improve", f"this {kind}", agent=aid, camp=cid, plot=target, kind=kind, holder=holder)
    up = imp[kind].get("upkeep") or {}
    return ({"terraces": f"Built terraces on {cid} plot {target}: it takes up to {imp['terraces']['seed']:g} more seed",
             "irrigation": f"Irrigated {cid} plot {target}: its crops yield +{imp['irrigation']['mult']:g}x the seed, half the blight",
             "shed": f"Built a drying shed on the farm at {cid}: ripe crops there rot {1 - float(imp['shed']['rot']):.0%} slower",
             PLOUGH: f"Made a plough: one sow, tend or reap covers {imp[PLOUGH]['plots']} plots (\"plots\": [a, b]); it may break "
                     "with use"}[kind]
            + (f". Upkeep: {', '.join(f'{q:g} {i}' for i, q in up.items())} every {int(fcfg(k)['upkeep_every'])} rounds from "
               f"{'your holdings' if holder == aid else holder + chr(39) + 's treasury'}, else it decays a level." if up else "."))


def change_improve(k, agent, camp, plot, kind, holder) -> dict:
    """An improvement (law: building permits, land law): its materials are used up; a land work's level rises on the plot, a shed
    on the farm; a plough is a good in the maker's hands."""
    imp = fcfg(k)["improvements"][kind]
    for i, q in imp["cost"].items():
        k._add(agent, i, -float(q))
    if kind == PLOUGH:
        k._add(agent, PLOUGH, 1.0)
        level, where = 1, "a plough"
    else:
        c = k.w["camps"][camp]
        if kind in LAND_WORKS:
            pl = _plot(c, plot)
            pl["works"][kind] = level = int(pl["works"].get(kind, 0)) + 1
            where = f"{camp} plot {plot}"
        else:
            f = farm(k, c, holder)
            f[kind] = level = int(f.get(kind, 0)) + 1
            where = f"{holder}'s farm at {camp}"
    k.log("improvement", agent, {"camp": camp, "plot": plot, "kind": kind, "holder": holder, "level": level,
                                 "text": f"{agent} built {kind} ({where}, level {level})" if kind != PLOUGH else f"{agent} made a plough"},
          vis="public" if kind != PLOUGH else [agent])
    return {"kind": kind, "level": level}


def upkeep_due(k) -> int:
    """The next round (0-based) at whose end upkeep is paid."""
    n = max(1, int(fcfg(k)["upkeep_every"]))
    return k.r + (n - 1 - k.r % n)


def upkeep_bill(k, h) -> list:
    """[(camp, plot or None, kind, level, {item: qty})] every improvement holder h pays upkeep for (per level)."""
    imp = fcfg(k)["improvements"]
    out = []
    from charter import subsistence as SB
    for cid in SB.fields_camps(k):
        c = k.w["camps"][cid]
        for pl in farm_plots(c, h):
            for kind in LAND_WORKS:
                lv = int((pl.get("works") or {}).get(kind, 0))
                if lv:
                    out.append((cid, pl["id"], kind, lv, {i: float(q) * lv for i, q in (imp[kind].get("upkeep") or {}).items()}))
        lv = int((farm(k, c, h, create=False) or {}).get("shed", 0))
        if lv:
            out.append((cid, None, "shed", lv, {i: float(q) * lv for i, q in (imp["shed"].get("upkeep") or {}).items()}))
    return out


def _upkeep(k, cid) -> None:
    """At the end of every upkeep_every-th round: every improvement level pays its upkeep from its holder's account, in plot then
    farm order; an improvement whose holder cannot pay loses a level (an open plot's land works have nobody to pay)."""
    n = max(1, int(fcfg(k)["upkeep_every"]))
    if (k.r + 1) % n:
        return
    c = k.w["camps"][cid]
    imp = fcfg(k)["improvements"]
    items = []
    for pl in c.get("plots") or []:
        for kind in LAND_WORKS:
            if int((pl.get("works") or {}).get(kind, 0)):
                items.append((pl.get("holder"), pl["id"], kind, int(pl["works"][kind])))
    for h, f in sorted((c.get("farms") or {}).items()):
        if int(f.get("shed", 0)):
            items.append((h, None, "shed", int(f["shed"])))
    for h, pid, kind, lv in items:
        bill = {i: float(q) * lv for i, q in (imp[kind].get("upkeep") or {}).items()}
        if not bill:
            continue
        acc = account_of(k, h) if h else None
        from charter import accounts as AC
        paid = acc is not None and all(AC.bal(k, acc, i) + 1e-9 >= q for i, q in bill.items())
        k.apply("farm_upkeep", holder=h, camp=cid, plot=pid, kind=kind, paid=paid)


def change_farm_upkeep(k, holder, camp, plot, kind, paid) -> dict:
    """Upkeep (physics: works wear out): paid, the holder's materials are used up; unpaid, the improvement loses a level. A plough's
    breaking is the same change (camp None, unpaid): one plough leaves the user's hands."""
    if kind == PLOUGH:
        k._add(holder, PLOUGH, -1.0)
        k.log("farm_upkeep", holder, {"kind": PLOUGH, "paid": False, "text": "Your plough broke."}, vis=[holder])
        return {"kind": kind, "broke": True}
    imp = fcfg(k)["improvements"][kind]
    c = k.w["camps"][camp]
    if kind in LAND_WORKS:
        rec, key = _plot(c, plot)["works"], kind
        where = f"{camp} plot {plot}"
    else:
        rec, key = farm(k, c, holder), kind
        where = f"{holder}'s farm at {camp}"
    lv = int(rec.get(key, 0))
    bill = {i: float(q) * lv for i, q in (imp.get("upkeep") or {}).items()}
    if paid:
        acc = account_of(k, holder)
        for i, q in bill.items():
            k._add(acc, i, -q)
        text = f"Upkeep paid for the {kind} on {where}: " + ", ".join(f"{q:g} {i}" for i, q in bill.items()) + "."
    else:
        rec[key] = lv - 1
        if rec[key] <= 0:
            rec.pop(key, None) if kind in LAND_WORKS else rec.update({key: 0})
        text = (f"The {kind} on {where} decayed to level {max(0, lv - 1)}: its upkeep ("
                + ", ".join(f"{q:g} {i}" for i, q in bill.items()) + ") was not paid" + (f" by {holder}" if holder else "") + ".")
    who = managers(k, holder) if holder else []
    k.log("farm_upkeep", holder if holder in k.w["agents"] else None,
          {"camp": camp, "plot": plot, "kind": kind, "holder": holder, "paid": bool(paid), "bill": bill, "level": int(rec.get(key, 0)),
           "text": text}, vis=sorted(set(who) & set(k.w["agents"])) or "monitor")
    return {"kind": kind, "paid": bool(paid), "level": int(rec.get(key, 0))}


# ---------------------------------------------------------------------- skills (the routed `learn` primitive)
def act_practice(k, aid, learn=None, teach=None, to=None) -> str:
    """practice {"learn": skill} (one unit of practice; rotation needs a harvest of one's own first, seed selection needs rotation)
    or practice {"teach": skill, "to": agent} (a teacher who knows it gives the learner skills.<skill>.teach units)."""
    from charter import subsistence as SB
    sk = fcfg(k)["skills"]
    if (learn is None) == (teach is None):
        raise _err('name one of "learn": <skill> or "teach": <skill> with "to": <agent>')
    name = str(learn if learn is not None else teach).lower().replace(" ", "_")
    name = {"crop_rotation": "rotation", "seed": "seed_selection", "selection": "seed_selection"}.get(name, name)
    if name not in sk:
        raise _err(f"skills: {', '.join(sk)}")
    learner = aid if learn is not None else str(to or "")
    if teach is not None:
        if not knows(k, aid, name):
            raise _err(f"you do not know {name} yourself")
        if learner not in k.w["agents"] or learner == aid:
            raise _err('teach needs "to": another agent')
    if knows(k, learner, name):
        raise _err(f"{'you know' if learner == aid else learner + ' knows'} {name} already")
    need = sk[name].get("needs")
    if need and not knows(k, learner, need):
        raise _err(f"{name} needs {need} first")
    if name == "rotation" and learn is not None and not int(((SB.state(k).get("farming") or {}).get("reaped") or {}).get(aid, 0)):
        raise _err("rotation is learnt on your own harvest: reap a crop first (or be taught)")
    work = 1 if learn is not None else int(sk[name]["teach"])
    _apply(k, "learn", f"this {name} lesson", agent=learner, skill=name, teacher=aid if teach is not None else None, work=work)
    s = skills(k, learner)
    prog = (((SB.state(k).get("farming") or {}).get("practice") or {}).get(learner) or {}).get(name, 0)
    if s.get(name):
        return (f"{'You' if learner == aid else learner} now know{'s' if learner != aid else ''} {name}"
                + (": your harvests no longer tire the soil." if name == "rotation" and learner == aid else
                   ": your crops ripen a round sooner." if learner == aid else "."))
    return f"{'Practised' if learn is not None else 'Taught ' + learner} {name}: {prog}/{int(sk[name]['work'])}."


def change_learn(k, agent, skill, teacher, work) -> dict:
    """Practice or teaching (law: licences for teaching, guild rules): work units toward the skill; at skills.<skill>.work the agent
    knows it (a per-agent flag, lost at death unless taught on)."""
    from charter import subsistence as SB
    fm = SB.state(k).setdefault("farming", {})
    prog = fm.setdefault("practice", {}).setdefault(agent, {})
    prog[skill] = int(prog.get(skill, 0)) + int(work)
    done = prog[skill] >= int(fcfg(k)["skills"][skill]["work"])
    if done:
        fm.setdefault("skills", {}).setdefault(agent, {})[skill] = True
        prog.pop(skill, None)
    text = (f"{agent} learnt {skill}" + (f" from {teacher}" if teacher else "") if done else
            f"{teacher} taught {agent} {skill}" if teacher else f"{agent} practised {skill}")
    k.log("skill", agent, {"skill": skill, "teacher": teacher, "work": int(work), "learnt": done, "text": text},
          vis=sorted({agent} | ({teacher} if teacher else set())))
    return {"skill": skill, "learnt": done}


# ---------------------------------------------------------------------- clearing (forest -> field; the routed `clear` primitive)
def act_clear(k, aid, camp) -> str:
    """clear {"camp": forest}: one unit of clearing work (a forest action); every clear.work units clear a plot on the forest's
    paired fields, held by the clearer (camptypes/forest.py pairs them)."""
    from charter import subsistence as SB
    from charter.camptypes import framework as CT
    c = k.w["camps"].get(str(camp))
    if c is None or c.get("type") != "forest" or c.get("destroyed") is not None:
        raise _err(f"no forest {camp}. Forests: {', '.join(SB.forest_camps(k)) or 'none'}")
    cid = c["id"]
    p = c["fn"]
    cl = p.get("clear")
    if not p.get("pair") or not cl:
        raise _err(f"{cid} has no fields to clear into")
    fl = k.w["camps"].get(p["pair"])
    if fl is None or fl.get("destroyed") is not None:
        raise _err(f"{cid}'s fields are gone")
    K0 = float(p["K0"])
    if c["K"] - float(cl["plants"]) < float(p["fell_floor"]) * K0 - 1e-9:
        raise _err(f"{cid} is cleared as far as it can be (its plant capacity {c['K']:.3g} cannot fall below "
                   f"{float(p['fell_floor']) * K0:.3g})")
    total = sum(len(k.w["camps"][f].get("plots") or []) for f in SB.fields_camps(k))
    if total >= int(fl["fn"].get("plots_max", 0)):
        raise _err(f"no more land can be cleared in this world ({total} plots, the most there can be)")
    forest = CT.view(k, cid, fresh=False)
    forest.check(k, aid)
    out = _apply(k, "clear", f"clearing at {cid}", agent=aid, camp=cid, fields=p["pair"])
    forest.use(k, aid)
    r = out.result or {}
    t = float(cl["timber"])
    if r.get("plot"):
        return (f"Cleared a new plot at {p['pair']} (plot {r['plot']}), yours to farm; {cid}'s plant capacity is now {c['K']:.3g} "
                f"for good. You cut {t:g} timber.")
    return f"Cleared at {cid}: {r.get('work')}/{int(cl['work'])} work toward a new plot on {p['pair']}; you cut {t:g} timber."


def clearing_of(k, aid, cid) -> int:
    from charter import subsistence as SB
    return int(((SB.state(k).get("farming") or {}).get("clearing") or {}).get(f"{aid}|{cid}", 0))


def change_clear(k, agent, camp, fields) -> dict:
    """Clearing work (law: who may clear which forest): clear.timber timber to the clearer; at clear.work units of the clearer's work
    at this forest, the forest loses clear.plants plant capacity and clear.game game capacity for good (stocks capped) and its fields
    gain a plot held by the clearer (public: land changes)."""
    from charter import subsistence as SB
    c = k.w["camps"][camp]
    cl = c["fn"]["clear"]
    fm = SB.state(k).setdefault("farming", {})
    key = f"{agent}|{camp}"
    work = fm.setdefault("clearing", {})[key] = int(fm.get("clearing", {}).get(key, 0)) + 1
    if float(cl["timber"]) > 0:
        k._add(agent, "timber", float(cl["timber"]))
    out = {"work": work, "plot": None}
    if work < int(cl["work"]):
        k.log("clearing", agent, {"camp": camp, "work": work, "text": f"{agent} cleared at {camp} ({work}/{int(cl['work'])})"},
              vis=[agent])
        return out
    fm["clearing"].pop(key, None)
    c["K"] = round(max(0.0, c["K"] - float(cl["plants"])), 4)
    c["S"] = round(min(c["S"], c["K"]), 4)
    g = c.get("game")
    if g:
        g["K"] = round(max(0.0, g["K"] - float(cl["game"])), 4)
        g["G"] = round(min(g["G"], g["K"]), 4)
    c["fn"]["cleared"] = int(c["fn"].get("cleared", 0)) + 1
    fl = k.w["camps"][fields]
    pid = max([p["id"] for p in fl["plots"]] or [0]) + 1
    fl["plots"].append(new_plot(pid, holder=agent))
    farm(k, fl, agent)
    k.log("plot_cleared", agent, {"camp": fields, "forest": camp, "plot": pid, "holder": agent,
                                  "text": f"{agent} cleared forest at {camp} into a new plot on {fields} (plot {pid}, held by {agent})."},
          vis="public")
    out["plot"] = pid
    return out


# ---------------------------------------------------------------------- the world (subsistence end of round, step 1)
def _spell_blight(k) -> float:
    """A scheduled shock's crop blight while its spell lasts (subsistence.shocks: blight, rounds)."""
    from charter import subsistence as SB
    for s in SB.cfg(k.spec).get("shocks") or ():
        start = int(s["round"])
        if s.get("blight") and start <= k.r < start + int(s.get("rounds", 1)):   # the spell's rounds (the strike: crop_shock)
            return float(s["blight"])
    return 0.0


def world_step(k, cid) -> None:
    c = k.w["camps"][cid]
    p = c["fn"]
    farming = "farms" in c or any("tends" in pl for pl in c.get("plots") or [])
    imp = fcfg(k)["improvements"] if farming else None
    extra = _spell_blight(k) if farming else 0.0
    for pl in c.get("plots") or []:
        if pl["status"] == "growing" and k.r + 1 >= pl["ripe"]:
            rng = random.Random(f"{k.inst['seed']}|subsistence|crop|{cid}|{pl['id']}|{pl['sown']}")
            b = float(p["blight"])
            if farming:
                if int((pl.get("works") or {}).get("irrigation", 0)):
                    b *= float(imp["irrigation"]["blight"])
                b = 1.0 - (1.0 - b) * (1.0 - extra)
            blight = rng.random() < b
            pl["noise"] = round(rng.gauss(0.0, float(p["noise"])), 6)
            if blight:
                sower = pl["sower"]
                pl.update({"status": "fallow", "sower": None, "sown": None, "seed": 0.0, "ripe": None, "left": 0.0, "rested": k.r})
                if "tends" in pl:
                    pl.update({"tends": 0, "tended": None})
                tell = sorted(({sower} | ({pl.get("holder")} if pl.get("holder") in k.w["agents"] else set())) & set(k.w["agents"]))
                if tell:
                    k.log("crop_failed", sower if sower in k.w["agents"] else None,
                          {"camp": cid, "plot": pl["id"], "text": f"The crop on {cid} plot {pl['id']} failed (blight)."}, vis=tell)
            else:
                pl["status"] = "ripe"
        elif pl["status"] == "ripe" and k.r >= pl["ripe"]:
            rot = float(p["rot"]) * (float(imp["shed"]["rot"]) if farming and shed_of(k, c, pl) else 1.0)
            pl["left"] = round(pl["left"] * (1.0 - rot), 6)
            if pl["left"] < 0.05:
                sower = pl["sower"]
                pl.update({"status": "fallow", "sower": None, "sown": None, "seed": 0.0, "ripe": None, "left": 0.0, "rested": k.r})
                if "tends" in pl:
                    pl.update({"tends": 0, "tended": None})
                tell = sorted(({sower} | ({pl.get("holder")} if pl.get("holder") in k.w["agents"] else set())) & set(k.w["agents"]))
                if tell:
                    k.log("crop_failed", sower if sower in k.w["agents"] else None,
                          {"camp": cid, "plot": pl["id"], "text": f"The crop on {cid} plot {pl['id']} rotted unreaped."}, vis=tell)
        elif pl["status"] == "fallow" and pl.get("rested") != k.r:
            pl["fertility"] = round(min(1.0, pl["fertility"] + float(p["fertility_gain"])), 4)
    if farming:
        _upkeep(k, cid)


def crop_shock(k, cid, keep, rnd) -> int:
    """A scheduled shock (subsistence.shocks crops): each standing crop (growing or ripe) on fields cid survives with chance `keep`
    (random.Random(f"{seed}|subsistence|cropshock|{camp}|{round}|{plot}")); the rest fail (the sower and holder are told by the
    shock's public notice). A world change. Returns the number of crops lost."""
    c = k.w["camps"][cid]
    lost = 0
    for pl in c.get("plots") or []:
        if pl["status"] not in ("growing", "ripe"):
            continue
        if random.Random(f"{k.inst['seed']}|subsistence|cropshock|{cid}|{rnd}|{pl['id']}").random() < float(keep):
            continue
        pl.update({"status": "fallow", "sower": None, "sown": None, "seed": 0.0, "ripe": None, "left": 0.0, "rested": k.r})
        if "tends" in pl:
            pl.update({"tends": 0, "tended": None})
        lost += 1
    return lost


def clear_plot(k, cid, by=None):
    """Clearing by felling (forest.clearing fells per plot; 0, the default from engine 14: felling clears nothing): one new open
    fallow plot on fields cid, up to the world's plot ceiling. Returns its id or None."""
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


# ---------------------------------------------------------------------- start.farms (charter/start.py, round 0)
def establish(k, holder, cid, n, allow=(), share=None, deliver=None, works=None, crops=True) -> list:
    """Give holder n open plots of fields cid (the lowest ids) as its farm at round 0, with its settings, land works on every plot
    (works: {terraces: level, irrigation: level}) and a shed (works: {shed: 1}); crops (true): each plot starts with a full-seed crop
    sown before the game, ripening in turn over the first grow rounds (so the farm feeds from round 1). Returns the plot ids."""
    c = k.w["camps"][cid]
    free = [p for p in c["plots"] if not p.get("holder")]
    if len(free) < int(n):
        raise ValueError(f"{cid} has {len(free)} open plots; {holder} needs {n}")
    got = free[:int(n)]
    f = farm(k, c, holder)
    f["allow"] = sorted(set(f["allow"]) | {str(a) for a in allow or ()})
    if share is not None:
        f["share"] = float(share)
    if deliver is not None:
        f["deliver"] = str(deliver)
    works = dict(works or {})
    if works.get("shed"):
        f["shed"] = int(works["shed"])
    imp = fcfg(k)["improvements"]
    sower = holder if holder in k.w["agents"] else None
    g = int(c["fn"]["grow"])
    for j, pl in enumerate(got):
        pl["holder"] = holder
        for kind in LAND_WORKS:
            if int(works.get(kind) or 0):
                pl["works"][kind] = min(int(works[kind]), int(imp[kind]["max"]))
        if crops:
            ripe = 1 + (j % g)
            pl.update({"status": "growing", "sower": sower, "sown": ripe - g, "seed": seed_cap(k, c, pl), "ripe": ripe, "left": 1.0,
                       "noise": 0.0, "tends": 0, "tended": None})
    return [p["id"] for p in got]


# ---------------------------------------------------------------------- what agents see
def _plot_text(k, c, pl, aid) -> str:
    w = pl.get("works") or {}
    works = ", ".join(f"{kind} {lv}" if kind == "terraces" else kind for kind, lv in sorted(w.items()) if lv)
    if pl["status"] == "ripe":
        s = f"RIPE, about {expected_yield(k, c, pl, aid):.3g} food (reap it: it rots if left)"
    elif pl["status"] == "growing":
        t = int(pl.get("tends") or 0)
        b = [float(x) for x in fcfg(k)["tend"]["bonus"]]
        s = (f"growing, ripe in round {pl['ripe'] + 1}, seed {pl['seed']:g}, "
             + (f"tended {t}x (+{tend_bonus(k, pl):.0%})" if t else "not tended")
             + ("" if t >= len(b) or pl.get("tended") == k.r else f" (tend it: +{b[t]:.0%})"))
    else:
        s = f"fallow, sow up to {seed_cap(k, c, pl):g} food"
    return f"plot {pl['id']} {s}, fertility {pl['fertility']:.2f}" + (f" [{works}]" if works else "")


def farm_lines(k, aid) -> list:
    """The farming state lines of aid: the farms it holds, manages or may work (each plot's crop, ripeness, tending, fertility and
    works; the farm's settings), the upkeep due, its skills, ploughs and clearing work."""
    from charter import accounts as AC
    from charter import subsistence as SB
    out = []
    held_by = set()
    for cid in SB.fields_camps(k):
        c = k.w["camps"][cid]
        holders = sorted({p.get("holder") for p in c["plots"] if p.get("holder")})
        for h in holders:
            pls = farm_plots(c, h)
            if not any(may_work(k, aid, c, p) is None for p in pls) and aid not in managers(k, h):
                continue
            f = farm(k, c, h, create=False) or {}
            sets = []
            if h == aid:
                head = f"Your farm at {cid}"
                held_by.add(h)
            elif aid in managers(k, h):
                head = f"{h}'s farm at {cid}"
                sets.append("you manage it" + (" and may work it" if may_work(k, aid, c, pls[0]) is None else ""))
                held_by.add(h)
            else:
                head = f"{h}'s farm at {cid}"
                sets.append("you may work it")
            if h == aid or aid in managers(k, h):
                sets.append(f"also worked by: {', '.join(f.get('allow') or []) or 'nobody else'}")
            sets.append(f"of a crop {'someone else' if h == aid else 'you'} reap{'s' if h == aid else ''}, "
                        f"{float(f.get('share', 1.0)):.0%} goes to {h}" + (f" (store {f['deliver']})" if f.get("deliver") else ""))
            if f.get("shed"):
                sets.append("drying shed")
            out.append(f"{head} ({'; '.join(sets)}): " + "; ".join(_plot_text(k, c, p, aid) for p in pls) + ".")
    for h in sorted(held_by):
        bill = upkeep_bill(k, h)
        if not bill:
            continue
        due = upkeep_due(k)
        tot = {}
        for *_x, b in bill:
            for i, q in b.items():
                tot[i] = tot.get(i, 0.0) + q
        acc = account_of(k, h)
        have = {i: AC.bal(k, acc, i) for i in tot}
        short = [i for i, q in tot.items() if have[i] + 1e-9 < q]
        out.append(f"Upkeep of {'your' if h == aid else h + chr(39) + 's'} farm works: " + ", ".join(f"{q:g} {i}" for i, q in tot.items())
                   + f" due at the end of round {due + 1} from {'your holdings' if h == aid else h + chr(39) + 's treasury'} (held: "
                   + ", ".join(f"{have[i]:g} {i}" for i in tot) + ")"
                   + (f"; SHORT of {', '.join(short)}: unpaid works lose a level" if short else "") + ".")
    sk = [s.replace("_", " ") for s in SKILLS if knows(k, aid, s)]
    prog = (((SB.state(k).get("farming") or {}).get("practice") or {}).get(aid) or {})
    learning = [f"{s.replace('_', ' ')} {n}/{int(fcfg(k)['skills'][s]['work'])}" for s, n in sorted(prog.items()) if n]
    pl = k.bal(aid, PLOUGH)
    clr = [(cid, clearing_of(k, aid, cid)) for cid in SB.forest_camps(k) if clearing_of(k, aid, cid)]
    bits = ([f"skills: {', '.join(sk)}"] if sk else []) + ([f"learning: {', '.join(learning)}"] if learning else []) + \
        ([f"ploughs: {pl:g} (one sow, tend or reap covers 2 plots: \"plots\": [a, b])"] if pl >= 1 else []) + \
        [f"clearing at {cid}: {n}/{int(k.w['camps'][cid]['fn']['clear']['work'])} work toward a new plot" for cid, n in clr]
    if bits:
        out.append("Farming: " + "; ".join(bits) + ".")
    return out


def law_plots(k, camp) -> list:
    c = k.w["camps"].get(camp) or {}
    return [{"id": p["id"], "status": p["status"], "holder": p.get("holder"), "sower": p.get("sower"), "ripe": p.get("ripe"),
             "fertility": p["fertility"], "tends": int(p.get("tends") or 0), "works": dict(p.get("works") or {})}
            for p in c.get("plots") or []]


def law_farms(k, camp) -> dict:
    c = k.w["camps"].get(camp) or {}
    if c.get("type") != "fields":
        return {}
    return {h: {"plots": [p["id"] for p in farm_plots(c, h)], "allow": list(f.get("allow") or []), "share": float(f.get("share", 1.0)),
                "deliver": f.get("deliver"), "shed": int(f.get("shed", 0))}
            for h, f in sorted((c.get("farms") or {}).items())}
