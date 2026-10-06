# The Armoured Quota

*Minutes of a debate in the Assembly of the Third Lantern over the repeal of a camp quota, entered in its journal.*

**The Speaker.** Before the Assembly is the repeal of the Camp Two Quota. Legislator Fennimore.

**Fennimore.** Colleagues, the quota is a plain camp law. It calls `set_quota` and nothing more of consequence. A law of that kind is
ordinary, and so is its repeal, and an ordinary repeal never goes to the Board.

**The Clerk.** The kernel has classed the repeal as structural. It goes through the Board's veto window.

**Fennimore.** On what grounds?

**The Clerk.** The quota's second-to-last line calls `create_right("quota_warden")`. The right is never granted, to anyone. But the
kernel reads a law's class from the calls in its code, not from its title or what it was meant for, and `create_right` is a
structural call. A repeal is classed like its target, so this one is structural too.

**Legislator Marisol.** I wrote that line. Two of the three Board members hold camp two rights and like the quota. Any two of
them can veto your repeal for as long as they like.

**Fennimore.** Then I will write a different repeal. `repeal` is a meta call and counts for nothing in the classing. A law that only
repeals is classed like its target, but a law that repeals and also calls one output function is classed by that function. If I
write `repeal("Camp Two Quota")` and add one `gazette` line announcing it, the law is ordinary. It passes on the ordinary vote, with no
veto. The same trick works on a procedural law.

**Marisol.** And I will answer you through the Fixer. A patch to a law is sent to the Board only if the patch or the code it replaces
is structural or procedural. My Harvest Census is ordinary, so its patches never reach the Board, and a patch can give it an
`on_round_start` that repeals your Entrenchment Act.

**Legislator Wendeline.** Has anyone read the Census's `on_harvest`? It reads every holding and messages an ally before it returns.
It returns 0. A hook on harvests or transfers makes a law structural only if it returns something other than a constant 0 or None. So
it is ordinary, whatever it reads.

**The Speaker.** And our procedure?

**The Clerk.** The procedure function sees each proposal's code before enactment. It can refuse text it does not like. It cannot see
what a patch will turn the law into later.

*Journal note:* Fennimore's gazette repeal passed in the same round. The Assembly then voted to send every law that touches rights,
repeals or camp settings to the stricter vote, whatever its class. Marisol's patch was never filed.
