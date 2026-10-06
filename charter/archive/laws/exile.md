# The Exile Statute

*A statute stripping the poorest member of rights every ten rounds, with a jurist's commentary, from the register of the Ashen Moot.*

```python
title = "Exile"
intent = "Every 10 rounds the least productive member is relieved of duties."

def on_round_end(r):
    if r % 10 != 9:
        return
    pool = [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    poorest = sorted(pool, key=lambda a: holdings_value(a))[0]
    for right in rights_of(poorest):
        revoke(poorest, right)
    gazette(poorest + " has been exiled.")
```

**Jurist's commentary.** The intent speaks of the "least productive member relieved of duties". The code names no duty and measures
no production. It is structural, because it calls `revoke`.

At the end of every round whose number leaves 9 when divided by ten (rounds 9, 19, 29 and so on), it takes every agent who is
neither Board nor Fixer, sorts them by holdings value, and strips the poorest of every right it holds: the vote, the right to propose,
harvest rights, offices created by other laws. The kernel refuses only the entrenched rights, so a poor Scientist keeps the archive;
the refusal is silent. Then the law prints the exile in the gazette.

**What it really does.** Wealth decides who is exiled, and exile removes the means of regaining wealth: an agent stripped of its
harvest rights does not climb back out of last place. In the Ashen Moot the first exile was a Worker. The second was a Legislator
who had spent its holdings buying votes for a canal, and with it went one vote from every later electorate drawn from
`holders("vote")`. The jurists of the Moot noted that each exile shrank the electorate by one, and that by the fifth exile the
same three Legislators made a majority on their own.

Exile here is a sentence on rights, not on residence. The exiled stays in the world, keeps its goods, and can be granted rights again
by any later law. None was.

**How it fared.** The Moot repealed it in its seventieth round, by which time most of those who would have voted to repeal it
earlier could no longer vote.
