# Tribute and raids: what a raid takes

**Demand (in most worlds).** Every 20 rounds, the first at round 20. It is 8% of the world's value (holdings plus reserve) times a
multiplier. The multiplier grows x1.25 after a raid and x1.1 after a demand is paid, so paying in full also raises the next demand.
Payment is due by the end of the demand's third round.

**Payment.** Only resources count, at unit value, capped at what is still owed. The demand is settled as soon as it is met. If it is
not met, everything paid toward it is lost. Laws pay from the reserve with pay_tribute.

**Timing.** The raid comes at the start of the round after the deadline, before anyone acts. At that point loans settle first, then
failed projects refund, then the raid takes place. Goods returned at that moment are exposed.

**Target.** In most worlds a random camp, each equally likely. Compute camps and fixed-pay camps are never raided (unless no other
camp exists). Some worlds raid the camp with the highest stock value.

**What it takes.**
- Half the camp's stock, but never below a granary's floor.
- A quarter of the camp's resource from every agent holding that camp's right at that moment. A leased right belongs to the tenant.
  A suspended right is not held. Other goods, coins and project escrow are untouched.
- Open camps (workshop, booth, two-sided choice) have no right holders, so a raid on one seizes nothing.

**Expected cost of a raid.** With n camps, a holder of q units of a camp's resource expects to lose q/(4n), about 4% of q with six
camps.

**Shelters.** At the moment of the raid, goods are safe in unrefunded escrow, on loan to an agent without the right (with the loan due
later), or with any agent who holds no right to the raided camp. Escrow shelters only if the project's deadline is at least one round
after the tribute's.
