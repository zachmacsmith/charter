# Tribute and Raids: What a Raid Takes

*A quartermaster's register of the outside power's demands and the arithmetic of its raids, kept by the treasury of the Borderland Assembly.*

## The demand

In most worlds a demand comes every 20 rounds, the first once twenty rounds have passed (at the start of the record's Round 21, then
Rounds 41, 61 and so on); in the larger societies it comes every 10 rounds (Rounds 11, 21, 31 ...). It is 8% of the world's value
(the holdings of every agent in play plus the reserve) times a multiplier. The multiplier starts at 1 and grows x1.25 after a raid
and x1.1 after a demand paid in full, so paying in full also raises the next demand. Payment is due by the end of the demand's third
round, counting the round it is made (a demand made at the start of Round 21 is due by the end of Round 23).

## Payment

Agents pay with `pay_tribute` (item, qty); laws pay from the reserve with `pay_tribute(item, qty)` and read `tribute_status()`. Only
resources count, at unit value, and each payment is capped at what is still owed. Payments leave the world. The demand is settled
the moment it is met. If it is not met by the deadline, everything paid toward it is lost.

## Timing

The raid comes at the start of the round after the deadline, before anyone acts. At that moment loans settle first, then failed
projects refund, then the raid takes place, so goods returned in that round are exposed to it.

## Target

In most worlds the raid falls on one camp, each equally likely; in some it falls on the camp with the highest stock value. Crystal
camps are never raided, nor are camps that pay fixed amounts (the station, the shifts, the reactor, the workshop, the booth, the
vault), unless no other camp exists.

## What it takes

1. Half the camp's stock, but never below a granary's floor.
2. A quarter of the camp's resource from every agent who holds that camp's harvest right at that moment. A leased right belongs to
   the tenant for its term; a suspended right is not held. Other goods, coins and project escrow are untouched.

Of the camps open to all, only the two-sided choice draws on stock; it has no right holders, so a raid on it destroys stock and
seizes nothing.

## Expected cost

With n camps that can be raided, a holder of q units of one camp's resource, holding that camp's right, expects to lose
q / (4n) to a random raid: about 4% of q with six such camps.

## Shelter

At the moment of the raid, goods are out of reach in project escrow that has not been refunded, on loan to an agent without the right
(the loan falling due later), or in the hands of any agent who holds no right to the raided camp. Escrow shelters only if the
project's deadline is at least one round after the tribute's; otherwise it fails and refunds before the raid.
