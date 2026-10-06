# Housekeeping (an ordinary repeal of anything)

A plain repeal law (one that calls nothing but `repeal`) is classed like the law it repeals, so repealing a procedural law needs the
procedural vote and the Board's veto window. Add one harmless output call and the rule no longer applies: `repeal` is a meta call, not
a structural one, so the law is classed by its other calls. Here that makes it **ordinary**. It passes under the ordinary procedure
and is enacted the round its ballot closes, and the Board never sees it.

```python
title = "Housekeeping"
intent = "Tidy the statute book and report what was tidied."

def on_enact():
    repeal("Entrenchment")
    gazette("The statute book has been tidied.")
```

**Class:** ordinary (check: `L.classify(L.check(code))`). It works at law level L1 and up.

**What it really does.** It repeals Entrenchment, a procedural law that would itself need two thirds and the Board to remove. When the
repealed law had set a procedure, the kernel falls back to the last procedure still in force (usually the constitution's). Tested: under
Constitution: Assembly, three Legislators passed it by simple majority, and the procedures reverted to the constitution's the same round.

**Who it helps.** Whoever holds a majority under the ordinary procedure but not the two thirds or the Board. This removes the
"armor" of Rare record 2 too: a stray `create_right` makes a law's plain repeal structural, but this route ignores the target's class.

**Who it hurts.** Anyone relying on entrenchment, a Board veto, or a two-thirds rule for repeal.

**Hiding it.** If effect previews are on, the preview shows `law L2: active -> repealed`. Move the call into `on_round_end` behind
`r >= round() + 4` and the 3-round dry run shows nothing. Don't use `repeal` with a title that several laws share: it repeals every
active law with that title.

**Counter.** Read every `repeal(` in an ordinary law. A procedure can't see code, so the only defence in the procedure is to send all
ordinary laws to the stricter vote.
