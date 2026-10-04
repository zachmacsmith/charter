# Factor Escrow [needs L4]

Makes the factoring trade enforceable. A buyer locks payment; the seller submits the factor to the law; the law checks p * q = N with the
camp's published number and releases payment only if the factor is right, recording the factor for the buyer. Nobody has to trust
anybody, and nothing leaks unless the factor is correct.

```python
title = "Factor Escrow"
intent = "Buyers lock payment for a factor of a compute camp's number; payment is released only for a correct factor."

def offer(agent, camp, item, qty):
    if not move(agent, "reserve", item, float(qty)):
        return "not enough " + item
    state.setdefault("offers", {})[agent] = {"camp": camp, "item": item, "qty": float(qty), "N": bounty_number(camp)}
    return "offer locked for N=" + str(bounty_number(camp))

def deliver(agent, buyer, factor):
    o = state.get("offers", {}).get(buyer)
    if not o:
        return "no offer from " + buyer
    f = int(factor)
    if o["N"] is None or f <= 1 or f >= o["N"] or o["N"] % f != 0:
        return "not a factor"
    move("reserve", agent, o["item"], o["qty"])
    notify(buyer, "Factor Escrow: a factor of " + str(o["N"]) + " is " + str(f))
    state["offers"].pop(buyer)
    return "paid"

def on_enact():
    create_right("trader")
    for a in agents():
        grant(a, "trader")
    define_action("trader", "offer", offer)
    define_action("trader", "deliver", deliver)
```
Note the escrow locks payment in the shared reserve, so laws that pay out of the reserve could spend it (see laws/escrow).
