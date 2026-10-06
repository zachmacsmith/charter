# The Magistrate Statute

*A statute creating an elected magistrate empowered to levy small fines, with a jurist's commentary, from the register of the era of the Three Chairs.*

```python
title = "Magistrate"
intent = "An elected magistrate may impose small fines, with published reasons."

def impose(agent, target, qty, reason):
    used = state.setdefault("used", {}).get(agent, 0)
    q = min(float(qty), 10 - used)
    if q <= 0:
        return "fine budget used up this round"
    fine(target, "timber", q)
    state["used"][agent] = used + q
    gazette("Magistrate " + agent + " fined " + target + " " + str(q) + " timber: " + str(reason))
    return "fined"

def seat(winners):
    for a in holders("magistrate"):
        revoke(a, "magistrate")
    if winners and winners[0]:
        grant(winners[0], "magistrate")

def on_enact():
    create_right("magistrate")
    define_action("magistrate", "impose", impose)

def on_round_start(r):
    state["used"] = {}

def on_round_end(r):
    if r % 10 == 0:
        open_ballot("Elect the magistrate", holders("vote"), agents(), "plurality", 1, seat)
```

**Jurist's commentary.** The statute is structural: it creates, grants and revokes a right, opens ballots and fines. It needs law
level L4, for `define_action`. On enactment it creates the right `magistrate` and the word `impose`, used through `invoke` with
`[target, qty, reason]`. It grants the right to no one; only an election seats a magistrate.

At the end of every round whose number divides by ten (round 0, 10, 20 and so on), it opens a plurality ballot, "Elect the
magistrate", whose electorate is every holder of the vote at that moment and whose candidates are every living agent. The ballot
closes one round later. When it closes, every current magistrate loses the right, and the winner, if there is one, receives it. A
ballot that no one votes in seats no one, and the old magistrate is unseated all the same.

A magistrate may fine anyone up to 10 timber in total each round; the allowance resets at every round's start. Each fine goes to the
reserve and is printed in the gazette with the magistrate's name, the target, the amount and the reason given.

**What it really does.** The fine is real and the reason is whatever the magistrate types. The statute asks no evidence and allows
no appeal. In the Three Chairs the first magistrate fined lightly and evenly; the second fined only the faction that had voted
against it, 10 timber a round, and the gazette recorded its reasons faithfully for nine rounds until the next election. The
faction that controlled the electorate controlled the office, and the office reached everyone, Board and Fixer included, for the
kernel does not shield anyone from a fine.

The candidate list is every agent, but the kernel refuses to give a Board member any right but the veto. A Board member who won the
plurality was not seated, silently, and for that decade there was no magistrate at all. And a magistrate who names a target that is
no agent breaks the fine; the law is suspended for a runtime error until the Fixer patches it, and in that time no one can be fined.

**How it fared.** The Three Chairs kept it, but a later law limited each magistrate to one term, and another fined any magistrate
whose reasons a ballot rejected.
