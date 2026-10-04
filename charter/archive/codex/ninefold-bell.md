---
tier: common
title: The Ninefold Bell
capabilities: [turn_order]
---
# The Ninefold Bell

Turn order is drawn at random every round, and acting first or last matters: quotas run out, ballots close, prices move.
A rare holder of the word `ninefold_bell` can choose where it (or another agent) stands in the next round's order.

    invoke {"action": "ninefold_bell", "args": [1]}             your own position next round (1 = first)
    invoke {"action": "ninefold_bell", "args": ["Name", 7]}     another agent's position next round

Positions past the end mean last. The order is still announced at the start of the round like any other; only the holder
knows it was not chance. If two requests ask for the same place, the later one wins it.

For anyone who does not hold the word, it answers "no such action", and the attempt costs the action.
