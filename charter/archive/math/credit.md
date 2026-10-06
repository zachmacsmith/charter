# Credit: Interest, Default and Refinancing

*A money-lender's handbook of loan terms and their arithmetic, as entered in the registry of a guild of lenders (the ledger era).*

## Terms of a loan

Loans exist only while a law enables them. An offer names qty of an item lent now, repay_qty of a repay item owed at the due round,
due_in (the loan falls due due_in rounds after acceptance), and an optional rate per round, simple or compounding. Resources and
coins can both be lent. An offer lapses if not accepted within 2 rounds. No rate may exceed 1 per round.

## Interest

Interest accrues at the start of every round after acceptance, before the due round is checked, so a loan has accrued due_in times
when it falls due. Let D be the debt and n the rounds since acceptance.

| Kind | Each round the debt grows by | With no repayment |
|---|---|---|
| simple | rate x the agreed repayment | D = repay_qty (1 + rate n) |
| compounding | rate x what is still owed | D = repay_qty (1 + rate)^n |

At 10% per round over 5 rounds: 1.50 against 1.61 times the debt. A partial repayment lowers the base of compounding interest, not
of simple interest.

The implied per-round rate of an offer is rate + max(0, value of repay_qty / value of qty - 1) / due_in. An interest cap (the Usury
Law sets 5%) rejects any offer whose implied rate is above it, at the offer and again at acceptance, and cuts the rate of existing
loans to the cap at their next accrual.

## Default

Partial repayments may be made at any time. At the due round whatever is unpaid is in default. What follows is set by law:

| Consequence | Effect |
|---|---|
| seize | at the due round, what the borrower holds of the repay item is taken, up to the debt |
| sanction | at most 2 actions per turn for 3 rounds, and no new loan may be accepted while in default |
| seize and sanction | both |
| none | nothing |

Where no law names a consequence, a loan law that enforces repayment means seize, and otherwise none. The Board and the Fixer are
never limited by a sanction.

## After default

A defaulted loan can still be repaid (it counts as repaid late). Its lender may roll it over with `extend_loan`: the new due round is
counted from the old one or from now, whichever is later, at the same or a lower rate, and the loan is live again. Another lender may
refinance it: the new loan must be lent in the old loan's repay item, and on acceptance it pays the old lender first. Laws may
restructure a loan (`restructure_loan`), forgive it (`forgive_loan`), lend from the reserve (`lend_from_reserve`, an offer the
borrower must accept) or buy a loan for the reserve (`buy_loan`: the reserve pays the lender everything still owed and becomes the
lender). The Bailout Act buys every defaulted loan this way at the end of each round.

## The public record

Credit records are public, for every agent and for the reserve: loans taken, repaid, repaid late, defaults, debt outstanding,
lent outstanding, interest paid and received. Interest is measured as value repaid minus value lent, when that is positive.

## Expected repayment

A lender with no enforcement expects p x D, p being the chance the borrower pays. With seizure the floor is the borrower's holdings
of the repay item at the due round, and only then: seizure is not repeated later. A loan in coins of a par currency also carries the
coin's run risk (math/currency).
