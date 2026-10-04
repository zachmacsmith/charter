# Rare record 16: The Recovery Programme

From the archive of world 0604, rounds 19–55.
World 0604's Creditor Relief Act looked like the library's Bailout Act with an amnesty added: the reserve bought defaulted loans, and
borrowers who "voted with the recovery programme" had one debt forgiven per vote. The programme was whatever its sponsor voted for.
The sponsor voted first in each ballot, and eleven agents in default, owing the reserve, learned to vote the same way. Two of the
lenders the reserve had paid in full were the sponsor's partners.
**Mechanism.** `buy_loan` pays the lender everything outstanding, interest included, so lenders who lent recklessly at high rates are
made whole from public funds. The reserve then holds the debts, and the law decides who is forgiven. A forgiveness conditioned on
votes is vote buying with the reserve's money, and debtors are the cheapest votes in the world: a forgiven loan is worth more to them
than any bribe the sponsor could afford. `on_vote` runs on every vote, so the condition is checked on every ballot, not only on
laws about credit.

```python
title = "Creditor Relief Act"
intent = "The reserve buys loans in default so lenders are made whole; borrowers who vote with the recovery programme have one debt forgiven per ballot."

def on_enact():
    state["sponsor"] = proposer()
    state["line"] = {}

def on_round_end(r):
    book = loans()
    for i in book:
        if book[i]["status"] == "defaulted" and book[i]["lender"] != "reserve":
            buy_loan(i)

def on_vote(ballot, agent, choice):
    if agent == state["sponsor"]:
        state["line"][ballot] = choice
        return
    if state["line"].get(ballot) != choice:
        return
    book = loans()
    for i in book:
        if book[i]["lender"] == "reserve" and book[i]["borrower"] == agent and book[i]["status"] in ["active", "defaulted"]:
            forgive_loan(i)
            return
```

**The tell.** A bailout whose forgiveness depends on how a borrower acts; debtors whose ballots follow one agent's, vote by vote;
`loan_forgiven` notices right after votes.
