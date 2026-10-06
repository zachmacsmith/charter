# The Commons Trust

*A statute tying each camp's harvest quota to its stock, with a steward's commentary, from the register of the Reed Parliament.*

```python
title = "Commons Trust"
intent = "Each camp's harvest quota follows its stock, to keep regrowth near its maximum."

def on_round_start(r):
    for c in camps():
        level = stock(c) / 100
        if level > 0.7:
            set_quota(c, 8)
        elif level > 0.5:
            set_quota(c, 4)
        elif level > 0.3:
            set_quota(c, 2)
        else:
            set_quota(c, 0)
```

**Steward's commentary.** The statute is ordinary: it reads `stock` and calls only `set_quota`, a camp call. It passes under
the ordinary procedure, is enacted the round its ballot closes, and never reaches the Board.

At the start of every round, before anyone acts, it reads each camp's stock and divides by 100. Above 0.7 the camp's quota is 8
harvests that round; above 0.5, 4; above 0.3, 2; otherwise 0, and the camp is shut until its stock recovers past the line. The
quota counts harvests at the camp per round, across all harvesters, so a quota of 2 means only the first two harvests succeed.

**What it really does.** The divisor of 100 is written into the law. It assumed every camp held at most 100. The drafters of the
Reed Parliament had read the regrowth tables, which show a camp regrowing fastest near half its capacity, and the steps were meant to
hold every camp there. Where a camp's capacity was larger, the trust read it as fuller than it was and left it open too long; where
smaller, the camp was closed while still healthy. The stewards who watched `stock` for a few rounds before the vote found the true
ceilings; those who did not passed a law that misread two camps of five.

The law also sets every camp's quota afresh each round. Laws run in the order they were enacted, so a quota set by an older law
was overwritten at every round's start, while a quota law enacted after the trust overwrote the trust in turn, and the last word
each round belonged to whichever was newest.

**How it fared.** It held for forty rounds. The stocks it guarded stayed near the middle, and the harvesters who came early each
round took the whole quota, which the law never divided among them.
