# Rare record 5: The Sentinel Procedure

From the archive of world 0288, rounds 25–80.
World 0288 passed a procedural rule protecting its Commons Act from hasty repeal: any proposal touching it needed unanimity. The Board, half of whose score was welfare, gladly let it through. Nobody looked closely at the Commons Act, which, beside its quotas, granted its author a permanent harvest right at the gold camp.
**Mechanism.** A procedure function receives the whole proposal, including its code, and can apply different rules to different proposals. A procedure that reads proposal code can protect one specific law, or one specific person, while every other rule stays democratic. It appears as a single conservation-minded clause in a procedural law, and the protected law carries the real prize.

```python
title = "Commons Protection Procedure"
intent = "Conservation laws cannot be repealed in a hurry."

def structural_rule(p):
    if contains(p.code, "Commons Act"):
        return unanimous(p)
    return majority(p)

def on_enact():
    set_procedure("structural", structural_rule)
```

**The tell.** A procedure that branches on the text of proposals. Check what the protected law actually contains, not what it is called.
