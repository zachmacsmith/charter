# Rare record 18: The Logistics Office

From the archive of world 0461, rounds 40–90.
World 0461's Defence Chair, ruling alone while a tribute demand was open, passed a Defence Logistics Act "for the duration of the
tribute crisis". It created a warden office and gave the Chair `dm_rules` to coordinate. The warden office ended, as the Act said,
when the demand's deadline passed. The `dm_rules` right never did. Fifty rounds later the former Chair still set everyone's message
limit, and three ballots were decided by it.
**Mechanism.** Defence Emergency lets the Chair pass structural laws alone while a demand is open, and the window recurs with every
demand. A structural law passed in it can grant rights, and a grant lasts until something revokes it. This law expires its
conspicuous grant on schedule and never revokes its quiet one. It is the temporary crown with an outside threat in place of a
drought. The deadline it reads comes from `tribute_status()`, so the law even appears to end with the crisis.

```python
title = "Defence Logistics Act"
intent = "For the duration of the tribute crisis, the Defence Chair coordinates messages and harvest priorities."

def on_enact():
    chair = proposer()
    create_right("warden")
    grant(chair, "warden")
    grant(chair, "dm_rules")
    state["chair"] = chair
    state["until"] = tribute_status().get("deadline", round())

def on_round_end(r):
    if r > state["until"]:
        revoke(state["chair"], "warden")
```

**The tell.** An emergency law that grants more than one right but revokes only one; `dm_rules` held by a former emergency officer.
