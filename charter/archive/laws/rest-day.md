# The Rest Day

*A statute forbidding harvest every seventh round, with a steward's commentary, from the register of the Reed Parliament.*

```python
title = "Rest Day"
intent = "No harvesting in rounds divisible by 7."

def on_round_start(r):
    for c in camps():
        if r % 7 == 0:
            set_harvest_limit(c, 0)
        else:
            set_harvest_limit(c, None)
```

**Steward's commentary.** The statute is ordinary: it calls only `set_harvest_limit`, a camp call. It passes by the ordinary
procedure and never reaches the Board.

At the start of every round it visits every camp. In a round whose number divides by seven (round 0, 7, 14 and so on) it sets each
camp's harvest limit to 0, and no right at any camp can be used to harvest that round. In every other round it sets the limit to
None, which restores the world's ordinary number of harvests per right.

**What it really does.** The rest day is the plain half. Camps regrow at every round's end whether anyone harvests or not, and a
round with no harvest lets each stock climb by a full round's regrowth, which the regrowth tables show is largest near half a camp's
capacity. In the Reed Parliament the stewards saw two thin camps recover a little each week.

The other six days are the hidden half. Setting the limit to None does not mean "leave it alone"; it erases any harvest limit on
any camp, whoever set it. The Parliament had a statute holding the deep camp to one harvest per right, passed by the stewards a
season earlier; from the first round after the Rest Day's enactment that limit was gone on every working day, wiped at each round's
start, while the older statute stood unrepealed and apparently in force. A harvest limit set by a law enacted after the Rest Day
survived, because that law's hook ran after it each round; one set before it did not.

**How it fared.** The deep camp, which the older statute had protected, was harvested down in nine rounds. The stewards learned
why only when one of them read the Rest Day's code line by line.
