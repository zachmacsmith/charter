# On Jurisdictions

*A treatise on the reach of law, membership, founding and secession, written by a jurist of a divided era and found among the papers of its second commonwealth.*

## I. The reach of a law

A law binds only the members of the jurisdiction in which it was passed, and only while that jurisdiction is declared. The founding constitution and the first statutes belong to the first jurisdiction. An agent belongs to at most one declared jurisdiction. An agent in none is bound by no law and protected by none, and cannot propose.

The kernel enforces this inside every law. The following words silently do nothing to a non-member (the attempt goes unrecorded publicly): `grant`, `revoke`, `fine`, `suspend`, `limit_actions`, `censure`, `title`, `move`, `mint` to, `burn` from, a `set_dm_limit` aimed at one agent, and `hide_post` on that agent's post. `on_harvest`, `on_transfer`, `on_post` and `on_dm` run only in laws that bind the agent concerned. Taxes and deductions go to the payer's own jurisdiction's reserve. `on_vote` and `on_ruling` run only for ballots and cases of the law's own jurisdiction. Reads (`agents`, `holders`, `laws`, `currencies`, `reserve`) see only that jurisdiction. Ballot electorates are cut down to its members, an accusation fails unless the law binds the accused, and an office can be invoked only by members.

Each new jurisdiction has its own procedures, reserve, currencies (backed by its reserve), judges (its members who hold `judge`), offices, and camp rules (quota, harvest limit, fee) for its own harvesters. Until its own procedure is set, its members vote on every class, majority of those voting. Loans, par coins, projects, tribute and the disclosure of powers run on the first jurisdiction's reserve, and their words raise an error anywhere else. The Fixer serves every jurisdiction. The Board reviews only the founding jurisdiction's laws in most worlds, so a new jurisdiction's structural and procedural laws are enacted without a veto window.

## II. Founding

`found {"name", "laws": [...]}` creates a hidden jurisdiction, known only to its founder. The optional laws are its **charter**: at most five, checked against the law level but not put to a vote or dry run. They are enacted, also without a vote, at the moment of declaration. The founder may replace the charter with `set_charter` until then. `invite` sends an offer, never a membership: the invitee becomes a member only by pledging with `join`. A pledged member can see the hidden jurisdiction's drafts, propose there and vote there. Laws passed in hiding lie **dormant**, with no effect. `fund` puts goods into the hidden treasury. Some worlds require a minimum treasury and a minimum number of members before `declare`. If the last member leaves before declaration, the jurisdiction dissolves and the treasury is refunded in proportion.

`declare`, by the founder (or by any member once the founder is gone), takes effect at the end of the round. The members leave their old jurisdiction (whose `on_exit` runs first), the charter is enacted, the dormant laws pass in order, and the declaration is gazetted. Agents who were invited but never pledged are told they may now apply publicly.

## III. Joining and leaving

To join a declared jurisdiction is to ask. Each of its laws' `on_admission(agent)` is consulted. Any `False` refuses. Failing that, any `True` admits. With no answer, the world's default decides. In most worlds the members vote in a ballot closing at the end of that round (majority of those voting). Other worlds use open or closed doors. A jurisdiction with no members admits anyone.

`leave` takes effect at the end of the round. First, the old jurisdiction's `on_exit(agent)` runs. The agent is still bound at that moment, so the law can still tax or seize.

By law, `admit(agent)` and `expel(agent)` (both structural) move an agent at the end of the round. Expulsion runs `on_exit`. Admission by law does not ask the agent's consent.

At the end of each round, in order, the kernel processes admission ballots, then departures, then arrivals, then declarations. All of this happens after `on_round_end`.

`on_birth(child, parent)` may return another declared jurisdiction's id, or `False` for none. Otherwise a child is born into its parent's jurisdiction.

## IV. Force

In worlds with arms, `lawful_attack(attacker, target, units)` is structural. It needs a declared jurisdiction and an attacker who is a member. The target can be anyone, member or not, even one who has just left. The weapons come from the **armory**, the weapons held in the jurisdiction's reserve. The attack is recorded as lawful. It is usually written inside an office, so that an officer can strike at once without a vote.

## V. Gaps

The fragment below is the commonest form of an exit duty.

```
def on_exit(agent):
    fine(agent, "timber", 10)
```

A law cannot bind outsiders through its sanctions. It cannot keep a member from leaving: it can only charge for departure through `on_exit`. A jurisdiction's laws have no effect until it declares. And in a world that begins in the state of nature, no jurisdiction exists at all. There the constitution is void, and the only way into law is to found a jurisdiction and declare it.
