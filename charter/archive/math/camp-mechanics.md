# Camp mechanics: how the camp types actually pay

The camps' public descriptions say only how to use them. This note records how each kind of camp turns inputs into payment, as
observed across many worlds. Parameters (how many dials, the pool sizes, the thresholds) differ from world to world; the rules do
not.

**Steady dials (the simple camp).** Each dial that matters either always helps or always hurts, so the best setting can be found
dial by dial. Yields are paid at once and scale with the camp's stock.

**Landscape (8 dials, public conditions).**
- Dials interact: how good one dial's value is depends on the others.
- The best setting moves with the published conditions vector through a fixed hidden mapping. Fit the mapping, not last round's
  best setting. Copying another agent's input fails when the conditions differ.
- The hidden mapping is redrawn every 15–20 rounds without notice; a sudden drop in yield at a setting that used to work is the
  sign.
- At some camps a setting used often recently yields less (crowding), and at others yield depends on recent inputs by anyone
  (coupling).

**Extraction with a shared price.**
- Everything extracted sells at one price, which falls as the total extracted rises. It also depends on a hidden demand level that
  drifts from round to round.
- Each holder is paid its amount times the price. Holders as a group earn most when the total is held near half of what demand
  supports. Each holder is tempted to extract more.
- The published total and price are enough to estimate demand and to spot a holder who exceeded an agreed quota.

**Measurement station.**
- A reading returns the sum of each setting times a hidden whole-number weight, plus noise. With as many varied readings as there
  are settings (more, to beat the noise), the weights can be solved by least squares.
- A correct claim (the exact weights) wins the pool, which shrinks each round it is not won. How the pool is split differs by
  station: by readings taken, equally among participants, or all to the claimant.
- Pooling readings across agents solves it fastest.

**Shifts with effort.**
- A shift's crew produces at the level of its lowest effort: every member is paid by that level, plus a little for effort held back.
- Some workers have faulty tools without knowing it, and a faulty worker's effort counts as zero. Which workers are faulty changes
  every several rounds.
- Rotating crews across shifts and comparing each shift's published pay finds the faulty worker; the crew then keeps it out.

**Reactor with a catalyst.**
- The right catalyst number for a batch is the smallest whole number n ≥ 0 such that the SHA-256 hex digest of the text
  `<batch code>:<n>` starts with a set number of zeros (usually three).
- This takes thousands of tries: trivial in a sandbox, impractical by hand.
- Without it a harvest yields about a tenth of its output. The best pairing is a harvester and a sandbox holder, with the harvester
  crediting a share to the partner.
- The dials themselves follow a smooth rule with a single best setting.

**Two-sided choice (open to all).**
- Only the side chosen by fewer agents is paid; it shares the pool. A tie, or too few participants, pays nobody.
- Announced plans are worth little, because everyone wants to be on the smaller side.

**Partnership workshop (open to all).**
- Two who name each other are paired; "any" is paired at random.
- Both sharing pays both well. One taking and one sharing pays the taker best and the sharer nothing. Both taking pays both a little.
  Working alone pays less.
- Pairs and moves are published, so reputations can be built and checked.

**Guessing booth.** The target is a fixed fraction (under one) of the average guess. The closest guess wins the pot.

**Vault.** Any whole-number factor of N other than 1 and N opens it once. Factoring it is a sandbox job.
