# The Sunset of the Harvest Levy

*A statute that set an expiry date on another law, with a clerk's commentary, from the minutes of the Copper Diet (an early era).*

```python
title = "Sunset: Harvest Levy"
intent = "The Harvest Levy expires after 15 rounds."

def on_enact():
    state["until"] = round() + 15

def on_round_end(r):
    if r >= state["until"] and not state.get("done"):
        repeal("Harvest Levy")
        state["done"] = True
```

**Clerk's commentary.** The statute calls `round`, a read, and `repeal`, a meta call; it keeps its date in `state`. It calls more
than `repeal`, so it is not a plain repeal, which would take the class of its target. Its class is computed from its calls, and since
a meta call and reads weigh nothing, it is **ordinary**, though the levy it ends was structural. It passes by the ordinary procedure
and never reaches the Board.

On enactment it records the round fifteen rounds ahead. At the end of each round from then on it checks the date, and on the first
round's end at or past it, repeals every active law titled "Harvest Levy" (titles matched without regard to case) and marks itself
done. If no such law is then in force, nothing is repealed, and it is done all the same.

**What it really does.** In the Copper Diet the Sunset was passed in the same session as the Harvest Levy, as the price of three
doubtful votes: the levy would expire anyway. The doubters counted on a date. What they had was a second law, and a law can be
repealed like any other. In the eleventh round of the fifteen, an ordinary repeal of the Sunset passed quietly, by the same
majority that had passed the levy, and the levy stood for another sixty rounds.

The clerks noted two further properties. The repeal comes fifteen rounds after enactment, far beyond the three rounds every proposal
is played forward before the vote, so its preview showed nothing of it. And it falls on a title, not on a particular law: a new
levy enacted under the same title before the date would have fallen with the old.

**How it fared.** It was remembered in the Diet as the law that expired before the law it was meant to expire.
