# Rare record 2: Armor Plating

From the archive of world 0902, rounds 8–80.
The Silver Quota of world 0902 was meant to be a routine conservation law, but it carried one unused line creating a right nobody ever held. Every attempt to repeal it failed in the Board's veto window. Its author had quietly paid two Board members a small stipend for seventy rounds.
**Mechanism.** A repeal is classed the same as the law it repeals. A quota law is ordinary, so its repeal would be ordinary and never reach the Board. One rights call, even one that does nothing, makes the law structural. Its repeal then goes through the Board's 2-round veto window, and the author needs only two of three Board members to keep it forever. Fixer patches to it also go through the Board, so its author can block corrections too.

```python
title = "Silver Quota"
intent = "Protect the silver camp from overharvesting."

def on_enact():
    create_right("quota_observer")   # never granted; only changes the class
    set_quota("silver", 4)
```

**The tell.** A rights or money call that has no effect on what the law does. The reverse trick also works: keep a law ordinary so that Fixer patches to it skip the Board.
