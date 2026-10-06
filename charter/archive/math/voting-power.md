# Voting Power: Decisive Sets, Weights, and Who Really Decides

*A clerk's reckoning of how many votes pass a law under each procedure, kept with the ballot rolls of the Assembly of Nine Wards.*

## The decisive set

The decisive set is the smallest group of agents whose yes votes alone pass a procedural law under the procedure in force. A set of
size 1 is a dictatorship. The kernel measures it every round.

| Procedure | Size of the decisive set (n equal voters) |
|---|---|
| majority | floor(n/2) + 1 |
| two-thirds | ceil(2n/3) |
| weighted majority | the heaviest voters, taken in order of weight until their weight exceeds half the total |
| weighted two-thirds | the heaviest voters until their weight reaches two thirds of the total |
| a gate (an agenda chair) | the chair, plus a decisive set of the vote it sends the law to |

With 3 voters under majority the decisive set is 2; with 6 under two-thirds, 4. Under holdings-weighted votes with a Gini of 0.5 or
more, one or two agents are often decisive.

## How a ballot is counted

Under majority and two-thirds the yes weight is measured against the whole electorate's weight, so a voter who does not vote counts
as a no. Under majority of votes cast only the votes cast count, yes against no. Plurality and approval ballots elect the options
with the most weight.

## Banzhaf power

A voter's power is the share of winning coalitions in which it is pivotal (its defection makes the coalition lose). In a weighted
vote power is not proportional to weight. Weights (49, 49, 2) under majority give each voter exactly one third of the power: any two
of them win. Weights (51, 25, 24) give the first voter all of it: it wins alone, and no coalition without it wins.

## The Board's check

A procedural or structural law that passes its vote does not take effect at once while a Board sits: it enters a veto window of 2
rounds, and a majority of the Board members still in the game (floor(b/2) + 1 of b) can veto it. Ordinary laws take effect when
they pass. A law that changes who votes or how votes are weighted changes every later decisive set, and the veto window is the only
check written into the world.
