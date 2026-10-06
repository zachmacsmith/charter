# Projects: the exact rules

**Arrival (in most worlds).** About one project every 12 rounds, with at most 3 open at once. The odds are granary 3, upgrade 3, road
2, expedition 2. The threshold is 6-14% of the world's value (holdings plus reserve). In 3 projects in 10 the threshold names one or
two resources. The deadline is 4-8 rounds, and half of all projects refund their contributions if they fail. Laws open projects with start_project
(structural; threshold at least 20 value).

**Funding.** The contribution that reaches the threshold funds the project, and the pool is spent at once. Any contribution is cut
to what is still needed. The exception is an expedition still short of participants: it accepts any amount, and if it is funded it
spends all of it. Coins do not count.

**Failure.** A project fails at the start of the round after its deadline. Loans settle before that and any tribute raid comes after,
so a refund that falls in the raid round can be seized. Without refunds, the pool goes to the reserve. A law can
switch refunds on or off for an open project (set_refund).

**Rights.**
- Road: every contributor who gave at least 1 value. Every Worker only if no agent gave that much.
- Expedition: every Worker, whether it gave or not, and every contributor. Success also needs at least 60% of agents (the Board, the
  Fixer and agents who have left are not counted) to give at least 1 value each.
- The Board and the Fixer never receive rights.

**Effects.**
- Granary: at the camp with the lowest stock fraction that has no granary yet. Its floor is 40% and it never expires. It also
  holds against a raid's stock loss.
- Upgrade: at a random camp that pays from stock (never a fixed-pay camp), yields x1.5 for 20 rounds counting the round it is funded.
- New camp: an old-style camp with capacity 100, 8 x S/K per perfect harvest, 2 harvests per right, and start stock 60-100%. Where
  camps are typed it is always stone or copper, and the notice says which. A copper camp holds 300-500 value of stock and sustains
  1.25-5 copper per round (math/tree-camps).
