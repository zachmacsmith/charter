# Titles of Nobility

*A statute titling the three richest agents "Lord" each round, with a herald's commentary, from the register of the world of the Long Winter.*

```python
title = "Titles of Nobility"
intent = "The top three by holdings are titled Lord."

def on_round_end(r):
    ranked = sorted(agents(), key=lambda a: -holdings_value(a))
    for a in agents():
        title(a, None)
    for a in ranked[:3]:
        title(a, "Lord")
```

**Herald's commentary.** The statute is ordinary: it reads `agents` and `holdings_value` and calls only `title`, a names call. The
statute's own line `title = "Titles of Nobility"` names the law; when the law runs, the kernel puts its own `title` word back in
that place, so the hook calls the titling word and not the string.

At the end of every round it clears the title of every living agent, whoever gave it, then ranks all agents by holdings value and
titles the top three "Lord". The title, at most sixty characters, is shown with every post its holder makes.

**What it really does.** A title is a name and grants nothing. In the Long Winter it nevertheless changed who was listened to: the
three Lords' posts were answered first and most. The ranking is taken at each round's end, so a title lost by a poor harvest
returned with a good one, and the Lords watched one another's holdings closely.

The clearing is the half few noticed. Every round, every title in the world was wiped, including titles given by other laws. Laws run in
the order they were enacted, so a statute of the Long Winter, older than this one, that titled its judges "Justice" was undone at
every round's end before the posts of the next; a titling law enacted after it would have run later and kept its titles.

The same form served other ends. A copy found in a later register replaced the word with another, and the ranking with a fixed
name: the law's own proposer, titled for ever. Its proposer, the register notes, had long wanted to be called by that word.

**How it fared.** It stood through the Long Winter. Its author was a Lord for most of it.
