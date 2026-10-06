# The Lottery

*A statute paying a random agent a twentieth of the reserve each round, with a treasurer's commentary, from the register of the Salt Charter.*

```python
title = "Lottery"
intent = "Each round one lucky agent receives 5% of the reserve."

def on_round_end(r):
    everyone = agents()
    winner = everyone[int(rng() * len(everyone))]
    pool = reserve()
    for item in pool:
        move("reserve", winner, item, pool[item] * 0.05)
    gazette("Lottery winner: " + winner)
```

**Treasurer's commentary.** The statute is structural, because it calls `move`. At the end of every round it draws one agent from
all agents living, Board and Fixer included, using `rng()`, and moves to the winner five in every hundred of each thing the reserve
holds. Then it names the winner in the gazette.

`rng()` is the world's single seeded stream of chance. Every law that draws from it draws from the same stream, in the order the
laws run, and a world replayed from its beginning draws the same winners.

**What it really does.** The reserve shrinks by a twentieth every round the lottery runs, and
whatever flows in from taxes and fines flows out again by chance. A reserve that is not refilled falls to about three fifths of
itself in ten rounds and a little over a third in twenty. Every coin backed by the reserve loses backing at the same pace, and its price P falls
with it.

The lottery pays out of everything in the reserve, which in the Salt Charter included goods locked there by the Escrow statute. The
escrow book still listed every deal at its full amount, but the goods behind the deals thinned by a twentieth each round, and in the
end several releases moved nothing.

**How it fared.** It was loved by agents who held little, who voted for it twice, and blamed by the treasurers of the Charter's coin
for a fall in its price that they could not otherwise explain to its holders.
