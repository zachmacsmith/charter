"""Resources: scoring values, real uses, the camp slot that produces each, and the helpers other modules use to charge costs.

Owned by Camps-A. Other modules build the uses themselves (weapons and forts: Conflict; agent creation: Life; files and pin
slots: Context/Scholars; initiative: Conflict) and charge for them with `pay(k, aid, cost)`.

Spec keys (all optional; defaults below, nothing here is in base.yaml so legacy worlds are byte-identical):
  resources:
    placement: default        # default | copper_solo | gold_solo  ("placement as a factor": which resource the solo-science slot makes)
    upkeep: {enabled: false, every: 5, item: timber, qty: 1}   # each agent consumes 1 timber every 5 rounds or loses an action until paid
"""
from __future__ import annotations

VALUE = {"timber": 1, "stone": 2, "copper": 5, "silver": 12, "gold": 30, "quicksilver": 8}

USES = {
    "timber": ["upkeep (optional)", "poll taxes", "base cost of new agents"],
    "stone": ["forts", "camp infrastructure"],
    "copper": ["weapons", "tools in production chains"],
    "silver": ["preferred reserve backing", "files and pin slots"],
    "gold": ["creating agents", "model-tier upgrades"],
    "quicksilver": ["initiative", "catalyst inputs"],
}

# default camp slot (camp role) -> resource. The two science-plus-coordination camps make copper then gold.
SLOTS = {"tutorial": "timber", "social": "stone", "coordination": ["copper", "gold"], "solo_science": "silver", "wildcard": "quicksilver"}
PLACEMENTS = ("default", "copper_solo", "gold_solo")
UPKEEP_DEFAULTS = {"enabled": False, "every": 5, "item": "timber", "qty": 1}
EXEMPT = ("board", "fixer", "observer")


def config(spec: dict) -> dict:
    return dict(spec.get("resources") or {})


def placement(spec: dict) -> str:
    p = config(spec).get("placement", "default") or "default"
    if p not in PLACEMENTS:
        raise ValueError(f"resources.placement must be one of {PLACEMENTS}, not {p!r}")
    return p


def slot_resources(spec: dict) -> dict:
    """role -> resource (coordination -> [first, second]) after the placement factor: copper_solo / gold_solo swap that resource
    into the solo-science slot, and silver takes its old place."""
    s = {k: (list(v) if isinstance(v, list) else v) for k, v in SLOTS.items()}
    p = placement(spec)
    if p != "default":
        moved = "copper" if p == "copper_solo" else "gold"
        s["coordination"] = [s["solo_science"] if r == moved else r for r in s["coordination"]]
        s["solo_science"] = moved
    return s


def value(k, item) -> float:
    """Scoring value of a resource in this world (the kernel's unit table first, then the defaults here)."""
    if item in k.w["unit"]:
        return float(k.w["unit"][item])
    return float(VALUE.get(item, 0.0))


def cost_value(k, cost: dict) -> float:
    return sum(value(k, i) * float(q) for i, q in (cost or {}).items())


def cost_text(cost: dict) -> str:
    return ", ".join(f"{float(q):g} {i}" for i, q in (cost or {}).items()) or "nothing"


def can_pay(k, aid, cost: dict) -> bool:
    return all(k.bal(aid, i) + 1e-9 >= float(q) for i, q in (cost or {}).items())


def pay(k, aid, cost: dict, to="reserve", why="cost") -> bool:
    """Charge a cost (e.g. {"copper": 3, "timber": 1}) all or nothing. to: "reserve", an agent id, or None (destroyed).
    Returns False (charging nothing) if the agent cannot pay all of it."""
    cost = {i: float(q) for i, q in (cost or {}).items() if float(q) > 0}
    if not can_pay(k, aid, cost):
        return False
    for i, q in cost.items():
        if to is None:
            k._add(aid, i, -q)
            k.log("destroyed", aid, {"item": i, "qty": q, "why": why}, vis="monitor")
        else:
            k.move(aid, to, i, q, why=why, by=aid)
    return True


# ------------------------------------------------------------------ optional upkeep
def upkeep_cfg(spec: dict) -> dict:
    return {**UPKEEP_DEFAULTS, **(config(spec).get("upkeep") or {})}


def upkeep_on(k) -> bool:
    return bool(upkeep_cfg(k.spec).get("enabled"))


def upkeep_start_round(k) -> None:
    """Every `every` rounds each agent owes `qty` of `item` (consumed). Debts are collected automatically whenever the agent holds
    the item; an agent still owing loses one action per turn until it pays."""
    if not upkeep_on(k):
        return
    cfg = upkeep_cfg(k.spec)
    st = k.w.setdefault("upkeep", {})
    due = k.r > 0 and k.r % int(cfg["every"]) == 0
    for aid in k.players():
        if k.w["agents"][aid]["cls"] in EXEMPT:
            continue
        if due:
            st[aid] = st.get(aid, 0.0) + float(cfg["qty"])
        owed = st.get(aid, 0.0)
        if owed <= 0:
            continue
        take = min(owed, k.bal(aid, cfg["item"]))
        if take > 0:
            k._add(aid, cfg["item"], -take)
            st[aid] = round(owed - take, 6)
            k.log("upkeep_paid", aid, {"item": cfg["item"], "qty": take, "owed": st[aid]}, vis=[aid])
        if st.get(aid, 0) > 1e-9:
            k.notify(aid, f"You owe {st[aid]:g} {cfg['item']} upkeep: you have one action fewer each turn until it is paid "
                          f"(it is taken automatically when you hold {cfg['item']}).")


def actions_after_upkeep(k, aid, n: int) -> int:
    """Actions this turn after upkeep arrears (unchanged when upkeep is off)."""
    if not upkeep_on(k) or (k.w.get("upkeep") or {}).get(aid, 0.0) <= 1e-9:
        return n
    return max(0, n - 1)


def rules_text(spec: dict) -> str:
    cfg = upkeep_cfg(spec)
    if not cfg.get("enabled"):
        return ""
    return (f" Upkeep: every {cfg['every']} rounds each agent consumes {cfg['qty']:g} {cfg['item']}; until it is paid you have one "
            "action fewer per turn.")
