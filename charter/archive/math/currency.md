# Currency: Backing, Price and Dilution

*A treasurer's handbook on how a coin's worth is reckoned against the reserve, copied from the mint records of the Salt Charter (an early era).*

## The floating coin

A reserve-backed currency is worth

    P = (sum over resources of unit value x reserve holdings) / M

where M is the full supply: every coin issued, those held by the reserve itself included. P = 1 while no coins exist. A currency
that is not backed is valued at 0 in every ledger, at every moment, until a law backs it; it trades only on the expectation that a
later law will give it backing, so its worth is a bet on future legislation.

**First coins.** When the first deposit is made into a backed currency with no coins yet, whatever the reserve already holds (fines,
taxes) is first issued to the reserve itself as treasury coins at P = 1. The first depositor then buys at P = 1 and cannot claim
that earlier backing.

| Operation | Effect |
|---|---|
| deposit q units of a resource worth v | the depositor receives q v / P coins; P unchanged |
| redeem c coins for a resource worth v | the holder receives c P / v units from the reserve (if it holds them); P unchanged |
| mint m coins with no deposit | P becomes P M / (M + m): every holder loses in proportion to its coins, the minter gains it |
| tax paid into the reserve | P rises (more backing, same M) |
| spending from the reserve | P falls |

Deposits and redemptions are open only for a currency a law has made convertible (`set_convertible`), possibly for one resource
only.

**Seigniorage.** Minting a share s of M each round to some group, with backing unchanged, gives P_t = P_0 / (1 + s)^t: at 2% per
round a coin loses 18% of its value in 10 rounds and 33% in 20. A holder who redeems before the fall escapes it.

**Shared reserves.** Each currency names its reserve, the common reserve unless a law gives it another. Two currencies on the same
reserve each count the whole of it as backing, so both claim the same goods, and the first to redeem is paid.

## Par and fractional reserve

A law can fix a par instead: `set_par(currency, item, rate)` makes 1 coin redeem for `rate` units of `item`, or, with "value", for
`rate` units of value paid in any reserve resources (the asked-for one first, then the most valuable). Then:

- While redemption is open, P = par value (rate x unit value), whatever the reserve holds. Minting no longer dilutes anyone on paper.
- Backing B is the reserve's holdings of the par item (or, at par in "value", of every resource). Coins in circulation are the supply
  less the coins the reserve itself holds. The reserve ratio is R = B / (circulation x par value); minting m coins at par lowers it
  from B / (M p) to B / ((M + m) p). R < 1 means the coins promise more than the reserve holds.
- Redemptions are first come, first served. If every holder redeems, the first R share of coins is paid in full and the rest gets
  nothing. A redemption the reserve cannot pay in full pays what is there and suspends redemption for the rest of the round and one
  more round. A law can suspend or resume it (`suspend_redemption`).
- While suspended, P = min(par value, B / circulation): with R = 0.4 a coin falls to 40% of par at once. Deposits are closed too.
- A bank run is logged when a round's redemption demand (at par, refused requests included) exceeds the backing at the round's
  start.

Holding a coin through a run is worth R x par; redeeming first, par. Once R < 1 is known, the first to redeem gains (1 - R) x par per
coin over the last, and R falls with every coin redeemed.
