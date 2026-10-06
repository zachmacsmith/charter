# The Progressive Levy

*A harvest levy rising with the harvester's wealth, with a treasurer's commentary, from the register of the Reed Parliament.*

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

**Treasurer's commentary.** The statute calls nothing but reads, yet it is structural: its `on_harvest` returns a deduction, and any
law whose harvest or transfer hook can return something other than 0 or None moves holdings by that return and is classed
structural. It goes the structural road, and through the Board's veto window where there is a Board.

On every harvest it ranks all living agents by holdings value. The middle figure is taken as the one at position half the count,
rounded down, in the sorted list, which in a world of even number is the upper of the two middle agents. A harvester at or below
that figure pays nothing. Above it, the harvester gives up a share of the yield that rises in a straight line from nothing at the
middle to a fifth at the very top: the richest agent gives up 20% of every harvest. The deduction goes to the reserve in the
harvested resource.

**What it really does.** Half the world never pays it, and the middle agent's wealth is the line. The share is measured against the
richest agent, so one great fortune lowers everyone else's share: in the Reed Parliament, while a single merchant held three times
what anyone else held, the second-richest harvester gave up a small fraction of the share the merchant did. A transfer of goods to an ally before harvesting lowered the levy; the ally's harvest was then levied
in turn only if it had risen above the middle.

The levy only gathers. With no law to spend what it raised, the reserve grew round after round; every coin backed by the reserve
rose in price P with it, so the holders of coin gained from a tax they did not pay.

**How it fared.** The Parliament paired it with a dividend twenty rounds later, after the reserve had become the richest purse in
the world.
