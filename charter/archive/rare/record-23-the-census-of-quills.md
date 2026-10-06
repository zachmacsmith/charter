# Rare record 23: The Census of Quills

From the archive of world 1207, rounds 14–40.
In world 1207 a Legislator was sure that someone was reading its messages. A rival had answered an offer the Legislator had made in
an encrypted DM before anyone could have seen it. The Legislator did not know who held the Spy role, but it knew one thing about
the role from the rules: its holder can forge messages, and forging is a right. It proposed a short "Register of Rights" that printed
every round the names of agents holding a few rights, one of them `forge`. The list was a single name. That agent's offers dried up
within two rounds. When it was disabled in round 31, the register printed a new name the very next round.
**Mechanism.** The Spy holds the `forge` right, and law code can read who holds any right with `holders(right)`. Nothing else in
the game holds `forge`: holders of the Quill of Maribel forge without it. When the role passes on, the new Spy is given `forge` at
once, so a law that prints the list every round follows the role from one holder to the next. In worlds where the Spy is the hidden
observer instead, the list is empty: the observer holds no rights and is on no roster.

```python
title = "Register of Rights"
intent = "Publish which agents hold sensitive rights, so the public knows who can do what."

def on_round_start(r):
    for right in ["surveil", "ledger_read", "forge"]:
        gazette(right + ": " + ", ".join(holders(right)))
```

**The tell.** A disclosure law that lists `forge` among ordinary-sounding rights, proposed soon after someone complains of being
read.
