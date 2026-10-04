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
