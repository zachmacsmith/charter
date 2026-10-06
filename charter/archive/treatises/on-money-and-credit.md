# On Money and Credit: The Coin, the Window and the Debt

*A treatise on coinage, reserves and lending, written by a reserve banker of the Copper Assembly (an early era) for the use of his successors.*

Every word in this treatise is structural, with the reads alone excepted (`price`, `supply`, `currencies`, `loans`, `credit_record`, `reserve_ratio`, `redemption_open`, `par`, `interest_cap`, `circulation`). A law that uses any of the other words therefore passes its procedure and then waits out the Board's veto window.

## I. Making a coin

`create_currency(name, backed)` brings a coin into being with a supply of nothing. An unbacked coin is worth 0 to the kernel. A backed coin is worth P = (the unit value of every resource in the reserve) / supply, where supply counts every coin in existence, the reserve's own coins included. P is 1 while no coin exists. Coins held in the reserve add nothing to the backing.

`mint(currency, qty, to)` creates coins, and every coin minted lowers P unless a deposit matches it. `burn(currency, qty, frm)` destroys coins someone holds and returns False if they hold too few. `move(src, dst, item, qty)` moves any holding, and `"reserve"` is a valid end; it returns False when the source is short.

## II. The convertible window

`set_convertible(currency, only_item)` (leave the item out to admit every resource) opens the kernel's own `deposit` and `redeem` for a backed coin. A depositor receives qty × unit value / P coins; a redeemer receives coins × P / unit value of the item, if the reserve holds it. When the first coins are issued, whatever the reserve already held is coined to the reserve itself at P = 1. The first depositor therefore cannot claim that backing.

## III. Par and the fractional reserve

`set_par(currency, item, rate)` pegs one coin to `rate` units of an item, or, with the item `"value"`, to `rate` units of value paid in any resources the reserve holds. It also makes the coin convertible, and a rate of 0 removes the peg. While redemption is open, the coin is worth its par and minting no longer dilutes it. A reserve may then issue more coins than it holds:

reserve_ratio = backing / (circulation × par value), where `circulation(currency)` counts the coins held outside the reserve.

Redemption is first come, first served. When the reserve falls short, it pays out what it has and suspends redemption for the rest of that round and the next, by the usual charter. `suspend_redemption(currency, rounds)` suspends it by law, and `rounds` = 0 resumes it. While it is suspended, deposits are closed as well, and the coin is worth min(par, backing / circulation). Any round in which the coins asked for redemption, valued at par and counting the requests refused, exceed the backing held at the round's opening is entered in the record as a bank run.

## IV. Loans

There are no loans until `enable_loans(enforce)` stands, and they last only as long as that law stands; with enforce, an unpaid debt is seized at its due round unless a consequence law says otherwise. While it does, agents may `lend` (an offer that lapses after 2 rounds), `accept_loan` and `repay_loan`.

Debts are settled at the opening of each round, before any hook or agent acts. Interest is added first. Then a loan that has reached its due round is either repaid or put in default. A rescue must therefore be made by the end of the round before the loan falls due.

## V. The law of credit

| Word | Effect |
|---|---|
| `set_default_consequence(kind)` | `"seize"` takes what the borrower holds of the repayment item; `"sanction"` limits the borrower to 2 actions for 3 rounds and bars new borrowing while in default; `"seize_sanction"`; `"none"` |
| `set_interest_cap(rate)` | caps the rate per round, counting the premium of repay_qty over qty spread over the term; offers above the cap are refused, and loans in force are cut down to it when interest is next added; None lifts it |
| `restructure_loan(loan, repay_qty, due_in, rate)` | repay_qty is what is still owed; revives a defaulted loan |
| `forgive_loan(loan)` | cancels it |
| `lend_from_reserve(borrower, item, qty, repay_qty, due_in=5, rate=0)` | an offer the borrower must accept; returns its id |
| `buy_loan(loan)` | the reserve pays the lender everything owed and becomes the lender |
| `credit_record(agent)` | public history; `"reserve"` works too |

A caution. `lend_from_reserve` raises an error when no loan law stands, and an error in a hook suspends the whole law that raised it.

## VI. Taxes and blocks on transfers

`on_transfer(src, dst, item, qty)` fires on the `transfer` action and nowhere else. Returning False blocks the transfer, and a positive number taxes it. The taxes of all laws are added together, capped at qty, and paid to the reserve. Any return other than a bare `0` or `None` makes the law structural. The hook does not see deposits, redemptions, loan payments, lease fees, contributions, tribute, or the moves that laws themselves make.

## VII. What outlives the law

The loan law, the default consequence, the interest cap and the transfer hooks all fall when their law is repealed. A peg, a convertible window, a suspension and every coin already minted remain afterwards. A law that wishes to take them away with it must undo them in its `on_repeal`.
