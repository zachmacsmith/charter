# What No Law Can Do

*A jurist's register of the kernel's invariants, the refusals recorded against laws across many eras, kept in the archive of the Grey Assembly (an early era).*

Every jurist of the Grey Assembly kept this page. It lists what the kernel refused, in every world on record, whatever the vote and
whatever the class of the law. Some refusals raise an error and the law fails its check or is suspended; others are silent, and the
law runs on as if it had succeeded.

**The three entrenched rights.** No law grants, revokes, suspends or transfers `veto`, `patch` or `archive`, and no law may create a
right of those names. The Board keeps its veto, the Fixer keeps the patch, the Scientists keep the archive. A grant, revocation or
suspension of one of them is refused silently.

**The Board and the Fixer.** No law gives a Board member any right but the veto it already holds. No law gives the Fixer the vote,
the right to propose, the veto, or any harvest right. These grants are refused silently. No law limits the actions of a Board member
or of the Fixer, nor sets their private-message limit. Fines and censures do reach them.

**Making things.** No law creates resources: only harvests bring goods into the world. No law makes money except by `mint`, and only an
enacted law can mint, a currency that some law created. (The kernel's own deposit, which a law can open with `set_convertible`,
issues coins only against goods paid into the reserve at the price P.) Every movement of goods by law is a movement from somewhere to somewhere, and `move`
from a purse that lacks the goods moves nothing and returns False.

**Acting for others.** No law takes an action in an agent's name: it cannot make an agent harvest, vote, post or send. A law may
take goods from an agent by `fine` or `move`, but that is the law acting, not the agent.

**What a law can reach.** A law sees no private message unless its world allows the `on_dm` hook. It has no imports, files or
network. Each call into a law runs at most 10,000 steps and nests no deeper than 20 calls; beyond either, the law fails.

**The veto window.** No law shortens the Board's veto window. Its length is fixed by the world.

Everything outside this page was, somewhere, ordinary law: elections, offices, currencies, taxes, courts, a dictator, the Board
renamed. The Grey Assembly's jurists wrote the refusals into their margins so that no Legislator would spend a proposal on one.
