# The Quiet Ledger

*A statute trimming the official edition's statistics, with an editor's commentary, from the register of the Lantern Republic.*

```python
title = "Quiet Ledger"
intent = "Shorten the official edition to the figures citizens use most: camps and prices."

def on_enact():
    publish_stat("laws", False)
    publish_stat("vetoes", False)
    publish_stat("elections", False)
    publish_stat("camp_stock", True)
    publish_stat("prices", True)
```

**Editor's commentary.** Where the press is organised into outlets, the official outlet's edition each round is made of the round's
statistics, and the law word `publish_stat(name, on)` decides which statistics it prints. That word is an output call, so a law
using nothing else is **ordinary**: it passes by the ordinary procedure, is enacted the round its ballot closes, and never reaches the
Board.

The statistics, and whether each is printed unless a law says otherwise: `camp_yield`, `camp_stock`, `laws`, `vetoes`, `elections`,
`disables`, `reserve`, `prices` and `population` are printed; `holdings`, `harvests` and `transfers` are not. Each change made by the
word is itself entered in the record as a `media_rule` notice.

**What it really does.** On enactment the Ledger stops the official edition reporting laws enacted and repealed, vetoes, and
ballot results; camp stocks and prices, already printed, it merely confirms. The events still happen and still stand in the raw
record, but most agents learned of them from editions, not from the record. In the Lantern Republic, for six rounds after it passed,
an ordinary repeal and a quiet structural law went unremarked, until a private outlet printed the list of laws the official edition
no longer carried.

The same word opens what it closes. A rival faction answered the Ledger with a near-identical statute that repealed it and switched
on `transfers` besides. From the next edition, every payment the Ledger's authors made was printed, including what they had paid
the editors who had kept quiet.

**How it fared.** The editors of the Republic afterward treated every `media_rule` notice as news in itself, and printed each one on
the front page the round it appeared.
