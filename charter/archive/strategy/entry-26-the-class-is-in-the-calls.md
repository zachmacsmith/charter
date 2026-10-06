# Entry 26: The class is in the calls, not the intent

A law's class, which decides whether it reaches the Board and what vote it needs, is read off the API calls in its code; adding or
hiding one call moves a law between classes without changing what it mostly does.

- **One stray call plates a law in armor.** An ordinary quota law's repeal is ordinary and never reaches the Board. Add a single
  `create_right` that is never granted and the law is structural: its repeal now goes through the Board's veto window, so two of three
  Board members can keep it forever (Rare record 2). The call does nothing; it only changes the class.
- **`repeal` is a meta call, so it doesn't count.** A plain repeal law is classed like its target, but a repeal law that also calls
  one output function is classed by that function. `repeal("Entrenchment")` plus a `gazette` line is **ordinary**, and removes a
  procedural law under the ordinary vote with no veto (see laws/housekeeping-repeal).
- **Taxes hide as returns.** `on_harvest` and `on_transfer` are structural only if they return something other than a constant 0 or
  None. A hook that returns 0 is ordinary even if it has read every holding and messaged an ally first.
- **Patches flip too.** A Fixer patch is reviewed by the Board only if the patch or the old code is structural or procedural. Keep a
  law ordinary and its patches skip the Board; the patch can add an `on_round_start` that repeals a rival's entrenchment (tested).
- **Procedures can't read class tricks.** A procedure function sees a proposal's code but runs before enactment; it can gate on text,
  not on what the law will later become through a patch.

**Counter.** Judge a law by its calls, not its title or intent: list every `grant`, `repeal`, `define_action` and non-zero hook return,
and send ordinary laws that touch rights, repeals or camp settings to the stricter vote anyway.
