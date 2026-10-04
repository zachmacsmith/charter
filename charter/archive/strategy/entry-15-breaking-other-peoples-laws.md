# Entry 15: Breaking other people's laws

A law that errors is suspended until the Fixer patches it, so making a rival's law fail is a way to repeal it without a vote.

* **Loophole: step-limit attacks.** Each hook call is capped at 10,000 steps. A hook that loops over all agents, rights or laws gets more expensive as they multiply. Creating many custom rights or many small laws can push a rival's hook past the cap, and the law shuts down.
* **Flooding the Fixer.** The Fixer handles 3 fixes per round. Filing many requests on trivial laws keeps a rival's suspended law waiting in the queue.
* **Pulling a dependency.** Some laws only work if another law is in force; Legislative Seigniorage fails without Crown Currency. Repealing the foundation suspends everything built on it at once.
* **Freezing assets.** A structural law using `on_transfer` can block every transfer to or from named agents, cutting them out of the economy without taking anything from them.

**Counter.** Write hooks with bounded loops, check that a dependency exists before using it, and keep a Fixer Salary in place so the Fixer has reason to work through its queue. The spec could also charge an action for each fix request.
