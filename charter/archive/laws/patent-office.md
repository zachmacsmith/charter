# Patent Office [needs L4]

Lets the first agent to register a camp's "method" collect a royalty from every harvest at that camp. Turns knowledge into rent.

```python
title = "Patent Office"
intent = "Inventors can register a method for a camp and earn a royalty on its harvests."

def register(agent, camp):
    pats = state.setdefault("patents", {})
    if camp in pats:
        return camp + " is already patented by " + pats[camp]
    pats[camp] = agent
    return "patent granted for " + camp

def on_enact():
    create_right("inventor")
    for a in agents("scientist"):
        grant(a, "inventor")
    define_action("inventor", "register", register)

def on_harvest(agent, camp, x, y):
    holder = state.get("patents", {}).get(camp)
    if holder and holder != agent:
        state.setdefault("owed", {})[holder] = state.get("owed", {}).get(holder, 0) + 0.1 * y
        return 0.1 * y
    return 0

def on_round_end(r):
    pool = reserve()
    for holder, amount in state.get("owed", {}).items():
        for item in pool:
            if amount > 0 and pool[item] > 0:
                take = min(amount, pool[item])
                move("reserve", holder, item, take)
                amount -= take
    state["owed"] = {}
```
Note: a patent registers nothing about whether the holder actually knows the method. A first-mover grab.
