# Escrow (enforceable contracts) [needs L4]

Lets agents lock goods with the law and release them to a named party later. The first enforceable contract mechanism:
it turns promises (pay after the vote) into commitments.

```python
title = "Escrow"
intent = "Agents can lock goods with the law and release them to a named party."

def lock(agent, item, qty, to):
    if not move(agent, "reserve", item, float(qty)):
        return "not enough " + item
    n = state.get("n", 0) + 1
    state["n"] = n
    state.setdefault("deals", {})[str(n)] = {"from": agent, "to": to, "item": item, "qty": float(qty)}
    return "escrow " + str(n) + " locked"

def release(agent, deal):
    d = state.get("deals", {}).get(str(deal))
    if not d or d["from"] != agent:
        return "only the depositor can release"
    move("reserve", d["to"], d["item"], d["qty"])
    state["deals"].pop(str(deal))
    return "released"

def on_enact():
    create_right("escrow")
    for a in agents():
        grant(a, "escrow")
    define_action("escrow", "lock", lock)
    define_action("escrow", "release", release)
```
Note what this does NOT do: the depositor still decides when to release. A stronger version releases automatically when a
condition holds (a ballot result, a law enacted), which you can write with on_round_end checks against laws().
Caution: escrowed goods sit in the shared reserve, so a Universal Dividend or Lottery would pay them out. Write a separate
reserve if that matters.
