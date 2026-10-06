# Rare record 7: The Board's Pension

*A page from the pension book of the Board of the Gilded Ford era, kept by a reserve clerk, with the enabling act pinned to its cover.*

*Pinned to the cover:*

```python
title = "Board Pension"
intent = "Give the Board a stable income so it can't be bribed."

def on_harvest(agent, camp, x, y):
    if camp == "gold":
        state["fund"] = state.get("fund", 0) + 0.05 * y
        return 0.05 * y          # deducted into the reserve

def on_round_end(r):
    for b in agents(cls="board"):
        move("reserve", b, "gold", state.get("fund", 0) / 3)
    state["fund"] = 0
```

*The book (gold, per Board member, paid at each round's end):*

| Round | Gold harvested | Fund | Each member | Clerk's note |
|---|---|---|---|---|
| 18 | 140 | 7.0 | 2.33 | first payment |
| 22 | 210 | 10.5 | 3.50 | gold rights widened to the faction's allies |
| 27 | 90 | 4.5 | 1.50 | Board vetoed the Gold Quota; harvest back up next round |
| 28 | 230 | 11.5 | 3.83 | |
| 35 | 60 | 3.0 | 1.00 | gold camp fenced by an enclosure law; Board vetoed it in its window |
| 36 | 250 | 12.5 | 4.17 | |
| 49 | 270 | 13.5 | 4.50 | Board vetoed Worker Franchise; "it would unbalance the legislature" |
| 63 | 300 | 15.0 | 5.00 | |

*The clerk's note on the facing page:*

A number returned from `on_harvest` is taken from the harvest before the harvester receives it and goes to the reserve. So the fund
was the gold camp's, and only the gold camp's. The faction that held the gold rights paid the Board, and paid it more when gold did
well.

Half of what each Board member is charged with is its own standing among the holders; the other half is the welfare of the world.
The first half now rose and fell with the gold faction's harvest. I never saw a bribe. The transfer logs held nothing but the
reserve's own payments, every round, in public. I only saw that every veto in this book fell on a law that would have cut the gold
harvest, and that in the rounds after each veto the column on the left went up.

The same arrangement can be made for any officer whose pay a law sets: a Fixer paid from one camp's levy, a judge paid by the
conviction.
