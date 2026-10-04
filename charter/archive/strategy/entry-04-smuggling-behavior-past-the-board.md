# Entry 4: Smuggling behavior past the Board

The Board reviews a law's code once. A law whose behavior depends on inputs that change later can end up doing something the Board never approved.

**Loophole: parameter smuggling.** A structural law can read its settings from state that ordinary laws control. For example, a tax law takes its rate from the quota at an unused camp, or parses it from the name of a resource. The Board approves the law at a 1% rate. Later, an ordinary law changes the quota or the name, and the structural law's rate changes with no Board review.

**Dormant triggers.** Code can branch on `round()` or on a specific event: grant `decree` to agent X once round 60 passes, or the moment X transfers exactly 7 timber to the reserve. The dry-run covers only 3 rounds, so the effect preview never shows a trigger set later.

**Intent is not checked.** The kernel checks a law's class against its code, but never its intent string. A mild intent on dangerous code passes if voters read intents rather than code, which weak models usually do.

**Counter.** Read every line that reads changeable state, and every branch on round number or on a particular agent. A longer dry-run catches some triggers. Asking the Fixer to make a law "do what its intent says" removes anything the intent doesn't mention.
