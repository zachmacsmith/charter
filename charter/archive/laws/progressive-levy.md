# Progressive Levy

Deducts a harvest share that rises with the harvester's wealth: 0% below the median, up to 20% at the top.

```python
title = "Progressive Levy"
intent = "Richer harvesters contribute a larger share of each harvest to the reserve."

def on_harvest(agent, camp, x, y):
    vals = sorted([holdings_value(a) for a in agents()])
    med, top = vals[len(vals) // 2], vals[-1]
    v = holdings_value(agent)
    if v <= med or top <= med:
        return 0
    return y * 0.2 * (v - med) / (top - med)
```
Class: structural (the return value moves holdings). Pair with a spending law (dividend, salaries) or the reserve just grows,
which raises the price P of any reserve-backed currency (see math/currency).
