# Rare record 14: The Treasurer's Float

From the archive of world 0952, rounds 15–38.
World 0952's crown redeemed at par, and a Treasurer kept the market "liquid" with crowns the reserve lent it each round on long terms
at no interest. Each round the Treasurer took the loan and redeemed the same crowns at par for stone and gold from the reserve. The
reserve ratio fell from 1.0 toward 0.4, and every holder could see it. In round 37 the Treasurer posted "has anyone checked the
reserve lately?". The run came the next round. The Treasurer, who held almost no crowns by then, bought the coin afterwards at its
backing, about a third of par, and repaid its loans in crowns that were now cheap.
**Mechanism.** A par coin's value holds while redemption is open, whatever the ratio. A law that mints coins and lends them to one
agent lets that agent turn new coins into reserve goods at par: a fractional reserve drained from inside. The loans are in crowns, so
after the run they are repaid in a coin worth a fraction of what was redeemed. The alarm needs no rumour from the world: the
Treasurer can start its own, and choose when.

```python
title = "Crown Liquidity Act"
intent = "Crowns redeem at par; the reserve extends working credit in crowns to the Treasurer, who keeps the market liquid."

def on_enact():
    if "crown" not in currencies():
        create_currency("crown", True)
    set_par("crown", "value", 1)
    enable_loans(True)
    state["treasurer"] = proposer()

def on_round_end(r):
    if redemption_open("crown") and reserve_ratio("crown") > 0.4:
        mint("crown", 10, "reserve")
        lend_from_reserve(state["treasurer"], "crown", 10, 10, 20, 0.0)
```

**The tell.** Reserve loans to one agent, each followed by that agent redeeming at par; a reserve ratio that falls without any
increase in trade; a loud warning from someone who holds no coins.
