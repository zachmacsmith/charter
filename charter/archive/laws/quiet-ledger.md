# Quiet Ledger (switching off the official record) [media2]

With media2 on, the official outlet's edition is the round's statistics, and `publish_stat(name, on)` decides which of them are
printed. It is an output call, so a law using it is **ordinary**.

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

**Class:** ordinary.

**What it really does.** The official edition stops reporting laws enacted and repealed, vetoes, and ballot results. The events are
still logged, but most agents learn about them from editions, not from the raw record. For a few rounds after it passes, a
Housekeeping-style repeal or a quiet structural law goes unremarked unless a private outlet reports it.

**The trap.** It runs both ways. The same call can switch on `holdings`, `harvests` or `transfers`, which are off by default. A rival
who repeals this law with a near-identical one that also turns on `transfers` will publish every payment you make, including payments
to editors. Before relying on it, check that no one holds an outlet that will cover what the edition leaves out.

**Who it helps.** Whoever plans a series of unpopular enactments. **Who it hurts.** Agents who read only the official outlet.

**Counter.** Media agents should treat a `media_rule` notice as news in itself.
