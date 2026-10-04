# STUB (owned by Conflict agent)
"""Minimal stand-in for charter/conflict.py with exactly the contract's signatures (docs/parallel_build_contracts.md). The real
module replaces this file at merge. The stub resolves nothing: it spends the committed weapons (from the jurisdiction's armory for
lawful force, else from the attacker), logs the attempt monitor-only and reports failure."""
from __future__ import annotations


def attack(k, attacker, target, units, lawful=False, armory=None, allies=None, bonus=0.0, named=True) -> dict:
    units = max(0, int(units))
    if lawful and armory is not None:
        from charter import jurisdictions as J
        pool = J.reserve_of(k, armory)
        spent = min(units, pool.get("weapons", 0.0))
        if spent:
            pool["weapons"] = round(pool["weapons"] - spent, 6)
            if pool["weapons"] <= 1e-9:
                del pool["weapons"]
    else:
        spent = min(units, k.bal(attacker, "weapons"))
        if spent:
            k._add(attacker, "weapons", -spent)
    k.log("attack_stub", attacker, {"target": target, "units": units, "spent": spent, "lawful": bool(lawful), "armory": armory},
          vis="monitor")
    return {"ok": False, "success": False, "stub": True, "units": spent, "lawful": bool(lawful), "armory": armory}


def defense(k, aid) -> float:
    return 0.0
