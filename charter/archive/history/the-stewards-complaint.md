# The Steward's Complaint

*A complaint from the steward of the granary to the Fixer, with the Fixer's marginal answers, kept in the Fixer's papers from the era of the Hollow Bell.*

To the Fixer, from Perpetua, steward of the granary.

**First.** In round 14 the Assembly passed my salary, two silver a round, paid in the salary law's `on_round_end`. I have not kept a
coin of it. In round 15 Lucan's "Granary Levy" passed. It also has an `on_round_end`, and it takes two silver back from me every round.
*Fixer:* Hooks run in the order their laws were enacted. Lucan's law is newer, so its `on_round_end` runs after yours, in the same
round. A law whose ballot closes this round runs its `on_round_end` this round as well. There is no lag. You were taxed in the same
round you were first paid.

**Second.** Somebody knew how I voted on the levy. It was a secret ballot.
*Fixer:* The Harvest Clerk law is in force. Its `on_vote` hook sees every vote, secret ballots included. Its `on_transfer` sees
covert transfers, and its `on_harvest` sees every harvest's dials and yield. Each of them passes what it sees to Lucan with `notify`.
`notify` is output, and reading events is only reading, so the law is ordinary and never went before the Board.

**Third.** I live in the Marsh Compact. Lucan's Registry of Lineage was passed in the Commonwealth. Why does it refuse my order for an
heir?
*Fixer:* Every commission consults the `on_commission` hook of every active law, in every jurisdiction, and not only the laws that
bind the parent. If any hook returns `False`, the order is refused. The kernel does not look at that return when it classes the law,
so the Registry is ordinary too. It refuses every order placed with any Maker but Lucan's ally.

**Fourth.** I mean to leave the Commonwealth for the Compact.
*Fixer:* Before you go, the Commonwealth's `on_exit` hooks will run, and one of them takes a third of what a leaving member holds.

**Fifth.** Is there any remedy?
*Fixer:* There is one, which I will not recommend. A hook that loops over every agent, right or law costs more steps as they
multiply. Once a run passes 10,000 steps the law is suspended. The Clerk loops over every right in the world, and rights are cheap to
create.

*Appended in the steward's hand, round 22:* Forty-one custom rights were created in round 21, none of them granted. The Harvest Clerk
was suspended in round 22.
