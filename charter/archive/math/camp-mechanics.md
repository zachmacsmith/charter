# Camp Mechanics: How Each Kind of Camp Pays

*A surveyor's handbook of the camp kinds and their hidden rules, compiled from the harvest ledgers of many eras.*

In worlds where each camp is its own kind, a camp's description says only how to use it. This handbook records how each kind
turns inputs into payment. The rules hold in every such world; the figures given are those found in most worlds.

**The measure.** Payments below are in measures: one measure is the value of a perfect steady-dial harvest at full stock, 8 value
in most worlds, paid in the camp's own resource. Camps are sized so that one action yields about 1 measure at the steady-dial camp,
1.5 at the landscape, 2.5 at the coordination camps when coordination works, and about 1 at the social games.

## Kinds that pay from stock

**Steady dials.** x is 4 dials, each 0..9. Two or three dials matter; f = c0 + the sum of c x over them, clipped at 0, with c0 in
1..4 and each c in {-2, -1, 1, 2, 3}. Yield = f / (best f) x max_yield x S/K + noise, paid at once (max_yield 8 timber in most
worlds; noise sigma 10% of max_yield). Each dial always helps or always hurts, so the best setting puts helpful dials at 9 and
harmful ones at 0.

**Landscape.** x is 8 dials, each 0..15 (in most worlds 1 silver per perfect harvest at full stock). Each dial i has a hidden centre
(a_i + sum of b_ij x_j) mod 16 that depends on up to 2 dials earlier in a hidden order, and scores exp(-d^2 / 8), d being the
circular distance from x_i to its centre; quality is the mean of the 8 scores. The best setting is found by setting the dials in the
hidden order. Each round 3 public conditions (each 0..9) are published; about 6 dials in 10 are shifted by (a coefficient 1..5 x one
condition) mod 16, and the rule sees the dial minus its shift, so the best setting moves every round and an input copied from
another round fails when the conditions differ. The rule and the shift mapping are redrawn every 15 to 20 rounds without notice.
`survey` shows the expected yield of a setting before noise, for an action and 2 timber.

**Extraction at a shared price.** x = [q], q 0..10, one sealed choice per round, paid at the end of the round (copper in most
worlds). With Q the round's total and n = the number of right holders (at least 4): Q_sat = 0.4 x n x 10 and
price = max(0.02 d, d - Q/Q_sat). Each holder receives q x price x max_yield x S/K. Demand d moves each round:
d' = m + 0.7 (d - m) + noise of spread 0.15, kept within 0.3..1.7; m is 1, redrawn within 0.8..1.2 every 15 to 20 rounds. The
holders' joint best is Q* = d Q_sat / 2 (price d/2); extractors each acting alone settle near n/(n+1) x d Q_sat. Only the total and
the price are published (the last five rounds in the state), and d = price + Q/Q_sat whenever the price is above its floor. Needs 4
right holders.

**Two-sided choice.** Open to all but the Board and the Fixer. x = [0] or [1], sealed. The pool, max_yield x S/K, is shared equally
by the side chosen by strictly fewer agents; a tie, or fewer than 3 taking part, pays nobody. The counts on each side are published.

## Kinds that pay fixed amounts

**Measurement station.** x is 8 settings 0..15; the hidden weights are whole numbers 0..15. A reading returns the sum of w x plus
noise of spread 3, privately, pays nothing and counts as a harvest. A harvest with "submit": true is a sealed claim that x is the
weights, judged at the end of the round. The pool starts each season at 70 measures and falls x0.78 each round without a solve once
the season's first reading or claim is made (never below 3.5). A correct claim ends the season: by readings (claimants 20%, the rest in proportion to this season's readings),
equally (claimants 20%, the rest equally among this season's readers) or winner-take-all, in proportions 2 : 2 : 1 among stations.
New weights are then drawn; a solve is announced without them. Sixteen random readings recover all weights by least squares and
rounding about 83% of the time (twelve 55%, eight 7%). Needs 4 right holders. The weights are redrawn every 15 to 20 rounds.

**Shifts.** x = [effort 0..10] and "shift" 1..3, sealed. In a shift of at least 2, the level m is the lowest effective effort and
each worker earns 0.25 m + 0.05 (10 - own effort) measures; alone, only the second part. One right holder in four (at least one)
is faulty, unknown even to itself, and its effort counts as 0; the faulty are redrawn every 8 to 12 rounds. Each shift's head count
and total pay are published, not who worked it. Needs 3 right holders.

**Reactor.** x is 4 dials 0..15 with one smooth peak. The catalyst for a batch is the smallest whole n >= 0 such that the SHA-256
hex digest of `<batch code>:<n>` starts with 3 zeros (about 4,096 tries); the 10-character batch code is new each round. A harvest
pays 5.5 x peak(x) measures at once with the right catalyst, a tenth of that without. "credit": "Name" sends 30% of a catalysed
harvest to that agent at the end of the round.

**Partnership workshop.** Open to all but the Board and the Fixer; no x, once per round, sealed: "partner": a name or "any", and
"move": share or take. Two who name each other are paired; "any" is paired at random with another "any"; the rest work alone.
Both share 1.25 each; taker 2 and sharer 0; both take 0.375; alone 0.25. Every pair and its moves are published.

**Guessing booth** (only ever the odd camp out). A whole number 0..100, sealed. The target is a fixed fraction of the average (0.6,
0.7 or 0.8 per booth); the closest takes 1 measure per entrant, ties split. Fewer than 3 entrants: each gets 0.5.

**Vault** (only ever the odd camp out; right holders only). "factor": any factor of N other than 1 and N, N being the product of two
primes of 28 to 32 bits. The first correct harvest takes 15 measures at once; the vault is then empty for good.

## The odd camp out

About half of worlds have one more camp, never of a kind already present. At it, a setting used n times in the last 3 rounds yields
1/(1 + 0.5 n) (crowding); if its kind reads dials by a hidden rule, one hidden dial is read shifted by the sum of that dial over the
camp's last 6 harvests by anyone, mod (top dial value + 1) (coupling); and each harvest consumes 1 copper. Stone can be invested
(`invest`) at every camp except the social game's (math/typed-commons).
