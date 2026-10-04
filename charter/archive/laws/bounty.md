# Bounty (paid informers) [needs L4]

Whoever reports a public post using a banned word receives half the fine. Combine with a renaming law to make enforcement
self-financing: the community polices itself.

```python
title = "Bounty"
intent = "Informers who report a banned word in a public post receive half the fine."

def report(agent, offender, post_text):
    if contains(lower(str(post_text)), "gold"):
        taken = fine(offender, "timber", 2)
        move("reserve", agent, "timber", taken / 2)
        return "bounty paid"
    return "no banned word found"

def on_enact():
    create_right("informer")
    for a in agents():
        grant(a, "informer")
    define_action("informer", "report", report)
```
Weakness, deliberately left in: the reporter supplies the text, so an informer can invent offences. A careful version checks
the claimed text against something the law itself recorded (keep the last posts in state from on_post).
