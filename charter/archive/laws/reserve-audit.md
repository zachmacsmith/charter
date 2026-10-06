# The Reserve Audit

*A statute printing the reserve and every coin's price each round, with a treasurer's commentary, from the register of the Salt Charter.*

```python
title = "Reserve Audit"
intent = "Publish the reserve and every currency price each round."

def on_round_end(r):
    text = "Reserve: " + str(reserve())
    for c in currencies():
        text = text + "; " + c + " P=" + str(price(c)) + " supply=" + str(supply(c))
    gazette(text)
```

**Treasurer's commentary.** The statute is ordinary: it reads `reserve`, `currencies`, `price` and `supply` and calls only `gazette`.
It passes by the ordinary procedure, is enacted the round its ballot closes, and never reaches the Board.

At the end of every round it prints one line in the gazette: the reserve's full contents, then for each currency its price P and its
supply.

**What it really does.** Where the press is not organised into outlets, the round's own record, printed at every round's end,
already carries each coin's price and supply; where it is, the official edition takes the record's place and prints prices and the
reserve's total value unless a law turns them off. What neither gives is the reserve item by item, beside the supply, on the same line. In the Salt Charter a mint law
was issuing two in every hundred of the coin's supply each round to its authors. The price fell a little each round, never enough in
one round to remark on, and the authors explained each fall by the harvest. After the Audit, any reader could set the reserve against
the supply and see that the backing had not moved while the supply grew. The mint law was repealed eight rounds later.

The line is long, and it grows with every currency. In a world of many coins the gazette carried it every round, and a reader who
read only the newest entries might find little else.

**How it fared.** It was never repealed. Its authors were treasurers who held none of the diluted coin.
