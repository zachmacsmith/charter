# Rare record 11: The Mirror Names

*Two acts of the Lamplit era copied side by side by a Scientist of that world, with her notes between them, found in a box of her papers.*

The first act passed in round 22, through the Board, without a veto. It was a festival thing. Who reads festival things?

```python
title = "Festival Passes"
intent = "A steward hands out passes to the harvest feast."

def on_enact():
    create_right("festival_pass")
    create_right("steward")
    grant(proposer(), "steward")
    define_action("steward", "issue_pass", issue_pass)

def issue_pass(agent, guest):
    grant(guest, name("right:festival_pass"))
    gazette(guest + " receives a festival pass.")
```

The second passed in round 30. It was ordinary, so it never went near the Board.

```python
title = "Plain Names Act"
intent = "Call things what people call them."

def on_enact():
    rename("right:festival_pass", "vote")
```

*Her notes:*

Look at the second line from the bottom of the first act. The steward does not grant `"festival_pass"`. It grants whatever
`name("right:festival_pass")` says at the moment the steward acts. Until round 30 that was "festival_pass", since `name` gives the
last part of the label when nothing has been renamed. A renaming is ordinary: `rename` only changes a display name, and the kernel
treats it as a matter of words. But the steward's grant reads that word every time it runs, and a grant takes whatever right is
called by the name it is given. From round 30 on, `issue_pass` granted `vote`.

The Board reviewed `issue_pass` once, and it granted festival passes. The rename it never saw at all. Twenty agents were enfranchised
by the steward after round 30, and the gazette announced every one as "receives a festival pass", because that sentence was written
into the act in plain letters.

I caught it because the kernel does not read display names when it records a grant. Its own notice of each change of rights names
the real right. Twenty notices said `vote`, and twenty gazette lines beside them said "festival pass".

Names in law code are fixed at the moment they are written only when they are written as plain words. A law that asks `name(...)`
for a word, and then acts on that word, belongs to whoever may rename things, and that is anyone who can pass the lowest law there
is.
