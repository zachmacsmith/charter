# Credit: interest, default and refinancing

Loans exist only while a law enables them. An offer names qty of an item lent now, repay_qty of a repay item owed at the due round
(due_in rounds after acceptance), and an optional rate per round, simple or compounding. Resources and coins can both be lent.

- Simple interest: the debt grows by rate x repay_qty each round, so after n rounds D = repay_qty (1 + rate n).
- Compound interest: D = repay_qty (1 + rate)^n. At 10% per round over 5 rounds: 1.50 vs 1.61 times the debt.
- The implied per-round rate of an offer is rate + (repay_qty value / qty value - 1) / due_in. An interest cap (Usury Law: 5%)
  rejects offers above it and cuts the rate of existing loans to the cap at the next accrual.
- Partial repayments may be made at any time. At the due round any unpaid part is in default. What follows is set by law: seize
  (take what the borrower holds of the repay item), sanction (2 actions per turn for 3 rounds, no new borrowing while in default),
  both, or nothing. A defaulted loan can still be repaid (it counts as repaid late), rolled over by its lender (extend_loan, same or
  lower rate), refinanced by another lender (the new loan pays the old lender first), restructured or forgiven by law.
- Credit records are public: loans taken, repaid, late, defaults, debt outstanding, interest paid and received.
- A lender with no enforcement faces expected repayment p x D where p is the chance the borrower pays; with seizure the floor is the
  borrower's holdings of the repay item at the due round. Lending in coins of a par currency carries the coin's run risk as well.
- Interest paid is measured as value repaid minus value lent. A loan the reserve buys (Bailout Act) pays the lender the full debt.
