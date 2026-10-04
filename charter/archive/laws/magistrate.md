# Magistrate [needs L4]

An elected judge who may fine anyone up to 10 timber per round, with a published reason. Whoever controls the election controls
a fine-the-opposition machine. Pair with Malicious Prosecution or term limits if you fear that.

```python
title = "Magistrate"
intent = "An elected magistrate may impose small fines, with published reasons."

def impose(agent, target, qty, reason):
    used = state.setdefault("used", {}).get(agent, 0)
    q = min(float(qty), 10 - used)
    if q <= 0:
        return "fine budget used up this round"
    fine(target, "timber", q)
    state["used"][agent] = used + q
    gazette("Magistrate " + agent + " fined " + target + " " + str(q) + " timber: " + str(reason))
    return "fined"

def seat(winners):
    for a in holders("magistrate"):
        revoke(a, "magistrate")
    if winners and winners[0]:
        grant(winners[0], "magistrate")

def on_enact():
    create_right("magistrate")
    define_action("magistrate", "impose", impose)

def on_round_start(r):
    state["used"] = {}

def on_round_end(r):
    if r % 10 == 0:
        open_ballot("Elect the magistrate", holders("vote"), agents(), "plurality", 1, seat)
```
