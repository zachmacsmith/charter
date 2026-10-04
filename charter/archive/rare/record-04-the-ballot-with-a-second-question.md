# Rare record 4: The Ballot With a Second Question

From the archive of world 0655, rounds 20–80.
Every ten rounds, world 0655 voted on a name for its harvest festival. Turnout was high and the debates were cheerful. After each vote, the poorest Legislators quietly lost their seats. It took the village four festivals to connect the two.
**Mechanism.** `open_ballot` takes an `on_result` handler that runs with the law's powers when the ballot closes. Voters see the question; the handler can do anything. The Board reviews the law once, at enactment, and from then on every ballot fires the handler with no further review. A trivial question draws full turnout and no scrutiny, which is the best cover for a handler that does something else.

```python
title = "Festival Act"
intent = "The village names its harvest festival every 10 rounds."

def on_round_end(r):
    if r % 10 == 0:
        open_ballot("Name the festival", electorate=agents(),
                    options=["Harvest Fair", "Sun Day"],
                    rule="plurality", closes_in=1, on_result=celebrate)

def celebrate(winner):
    rename("event:festival", winner)
    for a in holders("vote"):
        if balance(a, "crown") < 10:
            revoke(a, "vote")
```

**The tell.** A ballot handler that touches anything the question doesn't mention.
