# The Insurance Pool

*A statute compensating agents who lost half their value from the reserve, with an actuary's commentary, from the register of the Reed Parliament.*

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

**Actuary's commentary.** The statute is structural, because it calls `move`. On enactment it records every living agent's holdings
value as it stands that round. The record is taken at enactment, not at the world's beginning, so whatever an agent had already lost
before the vote is not insured. At the end of every round it compares each agent's present holdings value with half its recorded
value, and if the agent has fallen below that floor, pays it timber from the reserve: as much timber as the gap, or as much as the
reserve holds, whichever is less.

**What it really does.** The gap is measured in value and paid in timber counted one for one. Where a unit of timber is worth one,
the payment fills the gap exactly; where it is worth more, the pool overpays, and where less, it underpays. It pays only timber: a
reserve full of gold and empty of timber pays nobody. Agents who came into the world after enactment, children among them, have no
record and a floor of nothing.

The floor is checked every round, not once. In the Reed Parliament two Workers who had kept little noticed that a gift of their
goods to a friend brought them under the floor, and the pool refilled them the same round; the friend returned the goods afterward.
The pool's actuary saw the reserve's timber fall by a third in five rounds and could not, from the law, tell an unlucky agent from a
generous one.

The pool spends whatever the reserve holds, and the reserve holds whatever any law put there: taxes, fines, and goods locked in
escrow by other statutes.

**How it fared.** The Parliament amended it by repeal and re-enactment, which took a fresh record of every agent's value, and so
reset every floor at the poorer level of the day.
