# The Whispered Run

A world adopted the Reserve Bank Act in round 9. Crowns redeemed at par for one unit of value, and the reserve lent new crowns to
Workers whenever it held more than half of what the crowns promised. By round 25 the reserve ratio stood near 0.55 and crowns were
the only money anyone used. Nobody had redeemed a coin in ten rounds.

In round 26 a rumour reached four agents: the Legislator who had proposed the Act "has been quietly paying" the Chair. It was false
(the record showed no such transfer), but two of the four hearers held most of their wealth in crowns. They did the arithmetic every
holder can do from the state view: a ratio of 0.55 means the first 55% of coins are paid and the rest are not. Both redeemed
everything that round. A third hearer posted the rumour with "#run", and four more agents queued redemptions.

The round's demand exceeded the backing the reserve had held at its start, and the kernel logged a bank run. The redemption that
found the reserve short was paid in part and redemption was suspended. For that round crowns traded at the reserve's backing per
coin, about half of par. The Workers who had borrowed crowns at 3% still owed crowns at par to the reserve.

The two first redeemers ended the world well. The agents who believed the reserve's own gazette lost almost half their savings in a
round.

**Lesson.** A fractional reserve is stable only while nobody checks. Redemption is first come first served, so a rumour need not be
true: it only has to reach holders who can count. What happened: a false rumour about one transfer became a true run on the
currency. Why: the reserve ratio is public and the queue rewards whoever moves first. A careful agent watches `reserve_ratio` every
round, keeps no more coins than it needs for the next few trades, and if it holds a fractional coin it redeems before acting on any
rumour, not after checking it. A careful legislature that wants a par coin pairs it with a law that suspends redemption by law at
the first sign of a run, so the loss falls evenly rather than on the slow.
