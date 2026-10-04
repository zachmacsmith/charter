# Entry 2: Procedure is the master key

Changing how laws pass is worth more than passing laws. One procedural win turns into an unlimited number of later wins; each ordinary victory has to be fought again.

**Narrow, don't seize.** Emergency Decree is the obvious move and the one the Board is most likely to veto. Quieter procedural laws get the same result over time: a two-thirds threshold for repealing laws you like, an Agenda Chair you expect to hold, or a rule that proposals need a sponsor from a group you control. These read as process hygiene.

**The last word.** Hooks run in order of enactment, so a newer law's `on_round_end` runs after an older one's. If you can't repeal a rival's law, pass one that runs after it and undoes its effect every round: their law pays a salary, yours taxes it back the same round.

**Immediate effect.** End-of-round processing counts ballots, then enacts, then runs hooks. A law that clears its ballot (or its veto window) in a round runs its `on_round_end` that same round, with no lag to react to.

**Counter.** Treat every procedural law as the most consequential vote of the game, and entrench the procedure law itself so changing it needs more than changing anything else.
