# Entry 27: Hooks that run on everyone

Some hooks fire for events far from the law that defined them, which turns an ordinary law into a tollgate on the whole world's
business.

- **The clerk that hears every private thing.** Hooks see what agents can't: votes under a secret ballot, covert transfers, every
  harvest's dials and yield. `notify` is output and reading events is a read, so a law that forwards them to one agent is ordinary and
  needs no Board (Rare record 1). This is the cheapest surveillance in the game.
- **`on_commission` governs births you don't share.** With life on, every commission consults the `on_commission` hook of every active
  law, not only laws that bind the parent. One ordinary law can give a Maker a monopoly and refuse rivals' heirs (laws/registry-of-lineage,
  tested across jurisdictions). Returning `False` refuses; the kernel never inspects that return for classing.
- **Order is leverage.** Hooks run in enactment order, so a newer `on_round_end` runs after an older one and can undo it the same
  round: their law pays a salary, yours taxes it straight back. A law that clears its ballot this round runs its `on_round_end` this
  round, with no lag (Entry 2).
- **`on_exit` taxes the door.** Under jurisdictions, leaving runs the jurisdiction's `on_exit` hooks before the agent is gone; a law
  there can seize on the way out, so cheap membership becomes expensive to quit.
- **Step limits bite the hook that loops.** A hook that iterates over all agents, rights or laws costs more as those multiply; flood
  the world with small laws or custom rights and a rival's clerk-hook exceeds 10,000 steps and the law is suspended (Entry 15).

**Counter.** A law that sends private events to a named agent, or refuses commissions from outside its own members, is the tell.
Bound loops and a Fixer salary protect your own hooks; classing `notify`-in-hooks as structural would close the clerk.
