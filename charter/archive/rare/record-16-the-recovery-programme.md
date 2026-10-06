# Rare record 16: The Recovery Programme

*A letter from an indebted Worker of the Ashfall era to her sister in another camp, round 41, found among the sister's belongings.*

Sister,

You asked why I vote as I do now. I will tell you, and you may think less of me.

In round 19 the Creditor Relief Act passed. It looked like the old Bailout Act with mercy added. I copied it out for you:

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

You know I defaulted on the two loans from the copper men, at the rates they asked. At the end of round 19 the reserve bought both.
`buy_loan` pays the lender everything owed, the interest too, so the copper men lost nothing for lending to me at those rates. Then
the reserve was my lender, and the act decided what the reserve forgave.

"The recovery programme" is whatever the sponsor votes. Look at `on_vote`: it runs on every vote in the world, not only on votes
about debts. When the sponsor votes on a ballot, the act writes down the choice. When I vote the same way afterwards, one of my debts
to the reserve is forgiven, the moment my vote is cast. If I vote first, or vote otherwise, nothing.

So I wait for the sponsor to vote, and then I vote the same. So do ten others like me. Nobody bribed us. No coin changed hands that
anyone could point to. A forgiven debt is worth more to me than any bribe the sponsor could have paid, and it was paid out of the
reserve, which is everyone's.

The two copper men are the sponsor's partners. I learned that last.

Somebody will notice soon. Every forgiveness is posted as a `loan_forgiven` notice, and each one comes in the same round as a vote of
mine, and every vote of mine matches the sponsor's, cast just before. I am not proud of it. I am out of debt.

Your sister
