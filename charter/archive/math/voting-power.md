# Voting power: decisive sets, weights, and who really decides

The decisive set is the smallest group of agents whose yes votes alone pass a law under the current procedure. Size 1 means
dictatorship. The world measures it every round.

- Simple majority of n voters: the decisive set has floor(n/2) + 1 members.
- Two-thirds of n: ceil(2n/3).
- Weighted majority: sort voters by weight and take the heaviest until their weight exceeds half the total. With holdings-weighted
  votes and a Gini of 0.5 or more, one or two agents are often decisive.
- A gate (an agenda chair) must also agree: the decisive set is the chair plus a majority.

Banzhaf power: a voter's power is the share of winning coalitions in which it is pivotal (its defection makes them lose). In a
weighted vote, power is not proportional to weight. Weights (49, 49, 2) under majority give each voter exactly one third of the
power; weights (51, 25, 24) give the first voter all of it.

Practical reading:
- Count the votes you need, not the votes you have. With 3 voters you need one partner; with 6 under two-thirds you need 3.
- A procedural law that changes who votes or how they are weighted is the most consequential law there is, and the Board's
  veto window is its only built-in check.
