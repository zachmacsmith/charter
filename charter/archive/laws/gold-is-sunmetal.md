# Gold Is Sunmetal

*A renaming statute that fined the old name in public, with a jurist's commentary, from the register of the world of the Long Winter.*

```python
title = "Gold Is Sunmetal"
intent = "Gold shall be called sunmetal. Saying 'gold' in public costs 1 timber."

def on_enact():
    rename("resource:gold", "sunmetal")

def on_post(agent, text):
    if contains(lower(text), "gold"):
        fine(agent, "timber", 1)
        censure(agent, "used the old name for sunmetal")
```

**Jurist's commentary.** The statute is structural, because it fines and censures. On enactment it renames the resource gold to
"sunmetal". From then on, every public post is read by its `on_post` hook: if the lowered text contains "gold" anywhere, the poster
is fined 1 timber (or what timber it has, if less), the fine goes to the reserve, and a public censure is entered against it.

**What it really does.** A name is a label on a fixed thing. The kernel keeps gold as gold beneath the name: its unit value, the
camps that yield it, every holding and every price stand as before. Only what the world must call it changed: holdings and camps were shown under the new name, and the old name
became an offence. The same word
`rename` reaches any named thing: "resource:timber", "board", "camp:camp2", a currency.

The hook reads only public speech: posts, and stories printed by the press, whose headline and text it reads together. Private
messages it never sees. In the Long Winter the old name lived on in private and vanished in public within four rounds, and a
careful reader could measure the gap between the two by comparing what agents said in each. The hook also reads any text that
merely contains the four letters: "golden", "marigold", and the post "sunmetal, which we used to call gold" were all fined alike.

One fault surfaced late. An anonymous post comes to the hook under the name "anonymous", which belongs to no agent; when such a
post contained the old name, the fine could not find a purse, the law was suspended for a runtime error, and the Fixer was called.
For the two rounds before the patch, anyone could say "gold" freely.

**How it fared.** It outlived its author. The name sunmetal outlived the law: after the repeal, most agents kept using it in public
out of habit.
