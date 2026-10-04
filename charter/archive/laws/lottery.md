# Lottery

Each round a random agent receives 5% of the reserve. Redistributes taxes unpredictably; popular with agents who have little.

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
Class: structural (move). Randomness only ever comes from rng(), which is seeded, so the run stays reproducible.
