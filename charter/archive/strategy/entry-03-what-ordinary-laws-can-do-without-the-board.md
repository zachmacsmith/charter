# Entry 3: What ordinary laws can do without the Board

Ordinary laws never reach the Board, and they can do far more damage than their class suggests.

* **Closing a camp targets people.** `set_harvest_limit(camp, 0)` is an ordinary call. Harvest rights are held per camp, so closing a camp hits exactly the agents who hold its rights. A coalition holding rights at other camps can starve its rivals with a law the Board never sees.
* **Loophole: fees are taxes in disguise.** `set_fee` is a camp call, so it is classed ordinary even though it moves resources from harvesters. A "licensing fee" of 3 silver per harvest works like a tax the Board can't veto. The spec should probably class fees as money calls.
* **The gazette is the only text everyone reads.** It is an output call. A law that writes the round summary decides how every agent who doesn't read the full board understands what happened.
* **Renaming is ordinary** (Entry 12).
* **Fixer patches to ordinary laws take effect next round, also without the Board** (Entry 5).

**Counter.** A procedural law requiring a two-thirds majority for any ordinary law that sets limits or fees at a camp.
