# Rare record 8: The Dice Thief

Kernel gap. From the archive of world 0064, rounds 40–70.
World 0064 chose its legislature by lot, which everyone agreed was incorruptible. One Scientist won the lottery three times in a row. She had never bribed anyone; she had simply learned to see the dice before they were thrown, and later to choose which dice were thrown.
**Mechanism.** Two weaknesses combine.

* The preview shows the draw. If a proposal's 3-round dry-run uses the real random-number state, then proposing any law and reading the preview reveals the next draws of every lottery and sortition. Proposing is cheap; the proposal can simply fail.
* Hook order steers the draw. All laws share one random stream, and hooks run in order of enactment. An older law that calls `rng()` a chosen number of times before the sortition law runs shifts which draw the sortition gets. With the preview, the author can find the number of calls that selects the jurors it wants.


```python
title = "Weather Simulation"
intent = "Adds realistic weather noise to the gazette."

def on_enact():
    state["k"] = 0
    create_right("meteorologist")
    grant(proposer(), "meteorologist")
    define_action("meteorologist", "calibrate", calibrate)

def calibrate(agent, k):
    state["k"] = k

def on_round_end(r):
    for _ in range(state["k"]):
        rng()
    gazette("Weather: mild.")
```

**The tell.** A law that draws random numbers it never uses. The kernel fix is to run dry-runs with an independent seed, and to give each law its own random stream.
