# The Housekeeping Act

*An ordinary statute that repealed an entrenched procedural law, with a jurist's commentary, from the minutes of the Copper Diet (an early era).*

```python
title = "Housekeeping"
intent = "Tidy the statute book and report what was tidied."

def on_enact():
    repeal("Entrenchment")
    gazette("The statute book has been tidied.")
```

**Jurist's commentary.** The kernel classes a law by the calls in its code. One kind of law is treated differently: a plain repeal,
a law that calls nothing but `repeal`, takes the class of the law it names. A plain repeal of a procedural law is procedural, and
must go the procedural road, and through the Board's veto window where there is a Board.

This Act is not a plain repeal. It calls `repeal` and also `gazette`. `repeal` is a meta call, neither structural nor procedural,
and `gazette` is an output call, so the Act is classed by what remains, which is nothing weightier than output: it is **ordinary**.
It is allowed at law level L1 and above, passes by the ordinary procedure, is enacted the round its ballot closes, and never reaches
the Board. On enactment it repeals every active law titled "Entrenchment" (titles are matched without regard to case, and every law
bearing the title falls), then prints a line in the gazette.

**What it really does.** In the Copper Diet, "Entrenchment" was a procedural law: it had set the procedures under which laws passed,
and repealing it plainly would have needed two thirds and the Board. Three Legislators passed Housekeeping by a simple majority under
the Diet's assembly constitution. When a law that set a procedure is repealed, the kernel restores the most recent procedure for
that class set by a law still in force, usually the constitution's own; the Diet's procedures reverted the same round.

The same road reaches any law. In an earlier season of the Diet a quota law had been armored by its author with one unused
`create_right`, making it structural so that its plain repeal would go to the Board, where its author had friends. A repeal with one
added output call ignores what class its target bears.

The Act's proposal carried its preview like any other: every proposal is played forward three rounds before the vote, and where the
world publishes previews the line `law L2: active -> repealed` stood in the record for anyone who read it. Few did. A later copy in
another world recorded `round()` in `on_enact` and called `repeal` from `on_round_end` only once four more rounds had passed,
beyond the three the preview plays; its preview showed nothing.

**How it fared.** The minority that had relied on Entrenchment learned of its end from the gazette line, which said only that the
statute book had been tidied. After this, the Diet's clerks read every `repeal(` in every ordinary proposal aloud before the vote.
A procedure cannot read a law's code, only its class, author, title and intent; the Diet's eventual answer was to send all ordinary
laws to the stricter vote.
