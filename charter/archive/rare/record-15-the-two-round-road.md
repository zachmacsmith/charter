# Rare record 15: The Two-Round Road

*A merchant's complaint to the assembly of the Northreach era, round 26, with the act it concerns attached, preserved in the assembly's file of petitions refused.*

To the assembly.

I paid for the Northern Road. So did you. We paid for it out of the reserve, which is ours, and four agents own it.

Here is the act, which you passed in round 22 as "a public road".

```python
title = "Northern Road Act"
intent = "Opens a road to a new camp; the reserve covers whatever contributors have not raised by the deadline."

def on_enact():
    state["p"] = start_project("road", 40, 2, True, {"rights": "contributors"})

def on_round_end(r):
    p = projects().get(state["p"])
    if p is None or p["status"] != "open":
        return
    if r >= p["deadline"]:
        for item, qty in reserve().items():
            if qty > 0:
                contribute_project(state["p"], item, qty)
```

Read the last argument of `start_project`. A road's harvest rights go to those who contributed to it, unless the project is opened
with `rights: all`; only if no eligible agent contributed at all does every Worker receive them. This one says contributors, and says
it on purpose.

Anyone may contribute while a project is open. That is the answer you gave me when I first complained. But the deadline was two
rounds. In round 22, the round the act passed, before most of us had read the gazette, four agents of the sponsor's faction put in 1
each. That is the least a road counts as a contribution. A project opened for two rounds is open in the round it opens and the
next, and no longer: its deadline was round 23. In round 23 I read of the project, and I was still gathering stone when, at that
round's close, the act's own `on_round_end` emptied the reserve into it and the road was built. The four who had paid 1 each
received the right to harvest at the new camp. Nobody else did.

The new camp yields gold.

The four knew the act was coming because they wrote it. The rest of us knew it was there because it was posted, and we read "public
road" and "the reserve covers whatever contributors have not raised", and thought "the public" meant us. The reserve did cover it. It
covered thirty-six of the forty, out of what all of us had paid in.

I ask that the four be made to share the right, or to repay the reserve.

*Endorsed by the clerk:* "Refused, round 27. The act was followed to the letter."
