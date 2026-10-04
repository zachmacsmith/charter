# Currency: backing, price and dilution

A reserve-backed currency is worth P = (sum over resources of unit value * reserve holdings) / M, where M is the number of coins
in circulation. P = 1 while no coins exist.

- Deposit q units of a resource worth v each: you receive q*v/P coins and P is unchanged.
- Redeem c coins: you receive c*P/v units of a resource from the reserve and P is unchanged (if the reserve holds enough).
- Mint m coins with no deposit: P becomes P*M/(M + m). Every holder loses value in proportion to their coins; the minter gains it.
- Taxes paid into the reserve raise P (more backing, same M); spending from the reserve lowers it.

Seigniorage at rate s per round (mint s*M to some group each round) gives P_t = P_0 / (1 + s)^t: at 2% per round, coins lose 18%
of their value in 10 rounds and 33% in 20. Holders who notice can redeem before the fall; holders who don't, pay for it.

An unbacked currency is worth 0 at the end of the game. It trades only on the expectation that it will be backed later (a law
can make it convertible and give it a reserve), so its value is a bet on future legislation.

Several currencies may share the one reserve: each coin's backing is the whole reserve divided by its own supply, so two backed
currencies on one reserve both claim the same goods. The first to redeem wins.

## Par and fractional reserve

A law can fix a par instead: set_par(currency, item, rate) makes 1 coin redeem for `rate` units of `item` (or, with "value", for
`rate` units of value paid in any reserve resources, the asked-for one first). Then:

- While redemption is open, P = par value (rate x unit value), whatever the reserve holds. Minting no longer dilutes anyone on paper.
- Reserve ratio R = backing / (coins in circulation x par value); coins held by the reserve itself are not in circulation. Minting
  m coins at par lowers R from B/(M p) to B/((M + m) p). R < 1 means the coins promise more than the reserve holds.
- Redemptions are first come first served. If all holders redeem, the first R share of coins is paid in full and the rest gets
  nothing. A redemption the reserve cannot pay in full pays what is there and suspends redemption (by default for the rest of the
  round and one more). While suspended, P = min(par value, B / M): with R = 0.4 a coin falls to 40% of par at once.
- Deposits are closed while redemption is suspended.
- A bank run is logged when the round's redemption demand (at par, refused requests included) exceeds the backing at the round's
  start. Expected value of holding a coin through a run is R x par; of redeeming first, par. So once R < 1 is known, the first
  mover gains (1 - R) x par per coin over the last: the incentive to run grows as R falls, and R falls with every coin redeemed.
