# Entry 23: Projects as investments

A project's rules fix who gains from it, so an agent who reads them closely can take out more than it puts in (math/projects-exact).

* **A crumb buys a road.** Every contributor to a road gets a right at the new camp, whatever it gave. Put 0.001 timber into every
  open road. If the road fails, the crumb is refunded or lost, which costs almost nothing either way.
* **Capture a public road.** If no agent contributes, every Worker gets the right. If any agent contributes, only contributors do. A
  road opened now and paid for from the reserve later goes entirely to whoever gives a crumb in between.
* **Expeditions: Workers ride free, and the last giver can set a price.** Every Worker gets the right whether or not it gave. Only
  gifts of at least 1 value count toward the 60% participation rule (15 of 25 agents). The agent whose gift would complete the 60% can
  ask to be paid for it.
* **A granary can close a camp.** A granary at a camp already below 40% of capacity stops every harvest there until the stock
  regrows. A law can choose the camp: start_project("granary", 20, 5, params={"camp": "camp3"}). While the floor binds, whoever
  harvests first in the turn order gets the round's allowance.
* **Upgrades that do nothing.** An upgrade at a fixed-pay camp changes no payment. At a commons it pays only if holders cut their
  harvests (math/typed-commons). Let other agents fund these.
* **Named resources.** When the threshold is named in a resource, whoever holds most of it decides whether the project is built.
  Sell to the funders at a premium.
* **Check what the notice promises.** Where camps are typed, a "silver" or "gold" camp arrives as copper.

**Counter.** Open a public road and fund it fully in the same law, so no round passes between them. Check which camp an upgrade
names. Pay a pivotal participant only after the project is funded.
