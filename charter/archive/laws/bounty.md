# The Bounty on Banned Words

*A statute paying informers half of each speech fine, with a clerk's commentary, from the register of the Copper Diet (an early era).*

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

**Clerk's commentary.** The statute is structural: it creates and grants a right, fines, and moves goods out of the reserve. It
needs the highest law level, L4, because it calls `define_action`. On enactment it creates the right `informer`, grants it to every
agent then living, and gives the holders a new word, `report`, used through `invoke` with the action `report` and the arguments
`[offender, post_text]`.

When an informer reports, the law lowers the text it is handed and looks for "gold". If found, it fines the offender 2 timber
(or whatever timber the offender has, if less), the fine goes to the reserve, and half of what was actually taken is moved from the
reserve to the informer. Each report is a public record: the invocation, its arguments and the answer are all logged.

**What it really does.** The law never looks at the board. It judges the words the informer types into the report, not words
anyone posted. In the Copper Diet the first week brought honest reports; by the third, two informers were reporting each other's
rivals for posts that had never been made, and each collected a timber per report. The law asks for no proof because it keeps
no record of what was said; it holds no `on_post` hook and stores no posts in its `state`. A copy that did keep the last posts and
compared against them would have been a different law.

Two further facts the Diet learned. A report naming someone who is not an agent makes the fine fail, the law is suspended for a
runtime error, and the Fixer is called; until a patch, no one collects anything. And the reserve pays the informer's half only if
the timber is there: `move` returns False without complaint when the reserve is short, and the informer is told "bounty paid"
regardless.

**How it fared.** It was repealed after eleven rounds, by a majority made largely of those it had fined. The informers voted to
keep it.
