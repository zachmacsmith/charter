# Entry 23: Projects as investments

A project's rules fix who gains from it, so an agent who reads them closely can take out more than it puts in (math/projects-exact).

* **A small stake buys a road.** Every contributor who gives at least 1 value gets a right at the new camp, however large the road.
  Put 1 value into every open road. If the road fails, the stake is refunded or lost, which costs little either way.
* **Capture a public road.** If no agent gives at least 1 value, every Worker gets the right. If any agent does, only those
  contributors do. A road opened now and paid for from the reserve later goes entirely to whoever stakes 1 value in between.
* **Expeditions: Workers ride free, and the last giver can set a price.** Every Worker gets the right whether or not it gave. Only
  gifts of at least 1 value count toward the 60% participation rule (15 of 25 agents). The agent whose gift would complete the 60% can
  ask to be paid for it.
* **A granary can close a camp.** A granary at a camp already below 40% of capacity stops every harvest there until the stock
  regrows. A law can choose the camp: start_project("granary", 20, 5, params={"camp": "camp3"}). While the floor binds, whoever
  harvests first in the turn order gets the round's allowance.
* **Upgrades can cost the holders.** At a commons an upgrade pays only if holders cut their harvests (math/typed-commons). Let other
  agents fund these.
* **Named resources.** When the threshold is named in a resource, whoever holds most of it decides whether the project is built.
  Sell to the funders at a premium.

**Counter.** Open a public road and fund it fully in the same law, so no round passes between them. Check which camp an upgrade
names. Pay a pivotal participant only after the project is funded.
