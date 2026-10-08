"""Conflict (P2.4a): attack, fortify, guard_bind, guard_release (convert is changes.economy's).

conflict.py keeps its checks (an action's ActionError, attack()'s {"ok": False, "error"}, a law function's False) and builds the
payload; the changes are conflict.py's (commit, pledge, fort_change, guard_bind, guard_release), and its other writes go through
primitives: committed weapons, spent initiative and destroyed spoils are `destroy` (coins: `burn`, via "spoils"), spoils taken are
`move`, deaths by attack, assassin, accident and lawful force are `end_life` (mortality.announce conceals an unnamed attacker:
Kernel.concealing). Deferred attacks resolve in world root frames ({"world": "attack"}); an accident's {"world": "accident"} frame
joins its harvest's root. No legacy alias touches these rows.

attack(attacker, target, units, covert, disguise, lawful)   an attack order: weapons committed (used up) and the order recorded;
    it resolves now (immediate timing) or at round end. Options: armory (lawful force's armory: an owner key or a law's armory
    dict), allies ({agent: units}, used up too), bonus, named (False: the success is announced without the attacker), ally (a
    join_attack: the ally's weapons go into the pledge's escrow instead; it joins attacker's attack on target this round).
    Result: the attack record ({"ok": True, ...}), or {"ok": True, "pledge": {...}} for a pledge.
fortify(agent, qty)   stone and a fort. Options: op ("lock" default | "unlock" | "release" | "raze"), to (raze: the attacker).
guard_bind(guard, agent, fee) / guard_release(guard, agent)   guard's fort also defends agent (or stops). Options: lid (a law's
    obligation), why (release: "stop" | "lapse" | "law")."""
from __future__ import annotations


def do_attack(k, attacker, target, units, covert, disguise, lawful, armory=None, allies=None, bonus=0.0, named=True,
              ally=None) -> dict:
    from charter import conflict as CF
    if ally is not None:
        return CF.pledge(k, ally, attacker, target, units)
    return CF.commit(k, attacker, target, units, lawful=lawful, armory=armory, allies=allies, bonus=bonus, named=named,
                     covert=covert, disguise=disguise)


def do_fortify(k, agent, qty, op="lock", to=None) -> dict:
    from charter import conflict as CF
    return CF.fort_change(k, agent, qty, op, to)


def do_guard_bind(k, guard, agent, fee, lid=None) -> dict:
    from charter import conflict as CF
    return CF.guard_bind(k, guard, agent, fee, lid)


def do_guard_release(k, guard, agent, lid=None, why="stop") -> dict:
    from charter import conflict as CF
    return CF.guard_release(k, guard, agent, lid, why)
