# Rare record 13: The Neutral Clerk

From the archive of world 0388, rounds 6–41.
World 0388's Media agent was disliked, and a Legislator's "Press Neutrality Act" took the private-message limit away from it. The
Act read as a reform and passed easily. The new keeper of the limit was a Clerk: the Legislator who had proposed it. For twenty
rounds the Clerk never touched the limit. Then, the round a repeal of its Enclosure came to a vote, it set the limit of each of the
three agents organising the repeal to 1. They could no longer gather the votes they had been counting on. The repeal lost by one vote,
and the limits were restored the next round, "a clerical error".
**Mechanism.** `dm_rules` sets the DM limit for one agent at a time, and a holder uses it as an ordinary action without any vote.
The power over messages costs nothing to hold until it is used, and its use costs little: one public notice per agent, in a round full
of notices. Taking it from Media looks like a check on the press, so nobody asks who receives it. In fast mode, coalitions form in the
DM exchanges, so a limit of 1 on the organisers in a ballot round stops them gathering votes.

```python
title = "Press Neutrality Act"
intent = "The press should not regulate the channels it competes in: the private-message limit passes to a neutral Clerk."

def on_enact():
    state["clerk"] = proposer()
    for m in holders("dm_rules"):
        revoke(m, "dm_rules")
    grant(state["clerk"], "dm_rules")
    gazette("The Clerk now keeps the private-message limit.")
```

**The tell.** A law that moves `dm_rules` to a named agent rather than to the legislature as a whole; later, `dm_limit` notices that
name single agents in the round a contested ballot is open.
