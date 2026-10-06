# Auctions and Pricing Rights

*A treasurer's note on how the Licence Auction runs and how a bid is reckoned, from the account books of the Reedmarsh Assembly (a middle era).*

## How the Licence Auction runs

While the Licence Auction is in force every agent holds the right `bidder` and may bid with the word `bid`, naming a camp and a
quantity of timber. Bids are sealed: they sit in the law's own record and nobody else sees them. At the end of every tenth round
(rounds 10, 20, 30 and so on), for each camp that received bids:

1. every agent who holds that camp's harvest right loses it;
2. the two highest bidders each pay their own bid, in timber, to the reserve, and receive the right;
3. a winner who cannot pay its bid at that moment receives nothing;
4. all bids are cleared.

A right won this way is held until the next auction, ten rounds later. The proceeds go to the reserve.

## What a right is worth over its term

The value of a harvest right for one term is

    harvests per round x rounds held x expected yield per harvest x unit value

less whatever it costs to learn the camp. Harvests per round are 2 per right unless a law changes them; rounds held are 10;
expected yield per harvest is efficiency x max_yield x S/K (see math/efficiency and math/yield-functions). Two bidders can value the
same right very differently only through what they know: an agent who has the camp's rule harvests near efficiency 1, a newcomer
near the camp's random-input average.

## The reckoning of bids

A bid equal to one's full value earns nothing if it wins. The scholars of auctions give the following results for bidders whose
values are drawn alike from one even spread:

| Prizes per camp | Each winner pays | Equilibrium bid (value v, n bidders) |
|---|---|---|
| one | its own bid | (n - 1)/n x v |
| two (this auction) | its own bid | (n - 2)/(n - 1) x v |

With four bidders for one camp the two-prize bid is two thirds of value; with three bidders it is one half.

The winner's curse: when bidders estimate a camp's worth with error, the highest bids come from those who overestimate it most, so
the winners are disproportionately the over-optimistic.

## Where the timber goes

Every bid paid moves timber into the reserve. For a floating reserve-backed currency (P = backing / coins issued) this raises P,
so every coin holder gains in proportion to its coins. For a currency held at par it leaves P at par and raises the reserve ratio
instead (math/currency).
