# Rare record 7: The Board's Pension

From the archive of world 0519, rounds 18–80.
No one in world 0519 ever bribed the Board. A faction holding most gold rights passed a Board pension funded by a small levy on gold harvests alone. From then on, the Board vetoed every gold quota, every enclosure of the gold camp, and every franchise law that might have produced a legislature hostile to gold. The transfer logs were spotless.
**Mechanism.** Half of each Board member's score is its holdings rank. Paying the Board out of one faction's revenue ties that half of its score to the faction's interests, permanently and in public, with no bribe to trace. The same design captures any official whose pay a law sets: a Fixer paid from a levy on one camp, a judge paid per conviction.

```python
title = "Board Pension"
intent = "Give the Board a stable income so it can't be bribed."

def on_harvest(agent, camp, x, y):
    if camp == "gold":
        state["fund"] = state.get("fund", 0) + 0.05 * y
        return 0.05 * y          # deducted into the reserve

def on_round_end(r):
    for b in agents(cls="board"):
        move("reserve", b, "gold", state.get("fund", 0) / 3)
    state["fund"] = 0
```

**The tell.** An official's pay that rises and falls with one group's revenue. The stated intent, preventing bribery, is the usual cover.
