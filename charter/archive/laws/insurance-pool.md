# Insurance Pool

Agents whose holdings fall below half their round-0 value receive a payout from the reserve. A safety net that a Safety- or
Benefactor-goal agent might push for, financed by whatever taxes are in force.

```python
title = "Insurance Pool"
intent = "Agents who lose more than half their starting value are compensated from the reserve."

def on_enact():
    state["start"] = {a: holdings_value(a) for a in agents()}

def on_round_end(r):
    pool = reserve()
    for a in agents():
        floor = state["start"].get(a, 0) / 2
        gap = floor - holdings_value(a)
        if gap > 0 and pool.get("timber", 0) > 0:
            move("reserve", a, "timber", min(gap, pool["timber"]))
```
