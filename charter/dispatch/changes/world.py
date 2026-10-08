"""Camps and their rules (P2.1, P2.4c, P2.4d): regrow, drift, set_camp_state, create_camp (world causes: no law may stop them;
P2.4c), set_camp_rule (a law's rule), improve_camp and lease (typed camps and leases, P2.4d: made by camptypes.framework and
camptypes.leases). The world rows' call sites run inside world root frames (regrowth, drift, raids, tribute demands, world-event
firings, the projects steps)."""
from __future__ import annotations


def do_set_camp_rule(k, camp, key, value) -> dict:
    k.w["camps"][camp][key] = value
    return {key: value}


def do_regrow(k, camp, qty=None) -> dict:
    """A camp's stock grows by the logistic law, less this round's harvests (camps.regrow). Physics: no law may stop it."""
    from charter import camps as C
    c = k.w["camps"][camp]
    before = c["S"]
    C.regrow(c)
    return {"S": c["S"], "grown": c["S"] - before}


def do_drift(k, camp) -> dict:
    """A camp's hidden rule is redrawn (camps.drift) from the round's drift stream for that camp."""
    from charter import camps as C
    C.drift(k.w["camps"][camp], k.stream("drift", k.r, camp))
    return {}


def do_set_camp_state(k, camp, key, value) -> dict:
    """A camp's physical state changes by a world cause: a raid's stock loss, a blight, a destruction, a redrawn rule, a reveal,
    a granary or an upgrade a project funded. Not a rule (set_camp_rule): no law may stop it."""
    k.w["camps"][camp][key] = value
    return {key: value}


def do_create_camp(k, camp, kind, made=None) -> dict:
    """A new camp enters the world (a discovery, a funded road). `made` is the camp as camps.make_camp drew it."""
    k.w["camps"][camp] = made
    return {"camp": camp}


def do_lease(k, lease, lessor, lessee, status) -> dict:
    from charter.camptypes import leases as LS
    return LS.change_lease(k, lease, lessor, lessee, status)


def do_improve_camp(k, agent, camp, qty) -> dict:
    from charter.camptypes import framework as FW
    return FW.change_improve(k, agent, camp, qty)
