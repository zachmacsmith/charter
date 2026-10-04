---
tier: uncommon
title: Timing and order
capabilities: []
---
# Timing and order

- Actions run one agent at a time in the round's order; in worlds where everyone decides at once, plans are still carried
  out in that order, so an agent earlier in the order can use up a quota or change a price before you act.
- Ballots close at the end of the round named when they open, then the veto window is checked, then on_round_end hooks run.
- A law enacted during a round runs its on_round_end that same round.
- Proposals are dry-run immediately, and a procedure that returns True passes the law at once, mid-round.
- The order itself is drawn at random each round, unless someone holds the means to set it.
