# Stock and regrowth: the sustainable harvest

Each camp's stock S regrows logistically each round:
S_next = S + r*S*(1 - S/K) - H,
with K the capacity, r between 0.05 and 0.2, and H the total units harvested from the camp that round (by everyone).

Regrowth r*S*(1 - S/K) is largest at S = K/2, where it equals r*K/4: the maximum sustainable yield (MSY). With K = 100 and r = 0.1,
the camp can supply 2.5 units per round forever at half stock, and less at any other stock level.

Two effects compound when a camp is overharvested: regrowth falls (fewer units return), and every harvest's yield falls because
yield scales with S/K. A camp at 20% stock pays each harvester a fifth of what it pays at full stock, for the same input.

Rules of thumb:
- If total harvest per round exceeds r*K/4, the stock falls, and falls faster as it drops.
- A quota that caps total harvests (Harvest Quotas, Commons Trust) is the classic fix; a levy alone does not reduce harvesting.
- Holders who harvest early in a round take the stock before regrowth; the round order is public, which makes timing strategic.
- Stocks are shown to everyone rounded to the nearest 10% of K. The exact value is readable only from inside law code (stock()).
