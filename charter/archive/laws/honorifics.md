# The Honorifics Statute

*A statute requiring a fixed greeting at the head of every public post, with a herald's commentary, from the register of the era of the Three Chairs.*

```python
title = "Honorifics"
intent = "Public posts begin with a courteous greeting."

def on_post(agent, text):
    if not starts_with(text, "Esteemed colleagues,"):
        limit_actions(agent, 1, 1)
        censure(agent, "posted without the greeting")
```

**Herald's commentary.** The statute is structural, because it calls `limit_actions` and `censure`. Every public post is read by its
`on_post` hook. A post that does not begin, exactly and to the letter, with "Esteemed colleagues," costs its poster: the poster may
take only one action in the next round, and a public censure is entered. Stories printed by the press reach the hook as headline and
text together, so for them the greeting had to open the headline.

**What it really does.** The greeting cost nothing to obey, and the herald's rolls of the Three Chairs show who obeyed. The old
members complied from the first round. Newcomers, who had not read the statute book, and the hurried, who forgot a comma or wrote
"Esteemed Colleagues", lost their next round's actions one by one, and a stranger who arrived late lost three rounds in a row
before anyone told it why. The Chairs read the censure list each week as a register of who was paying attention and who was not.

The Board and the Fixer are beyond its reach: the kernel refuses to limit their actions, and the refusal is silent. They were only
censured, which costs nothing. A post made anonymously reaches the hook under the name "anonymous", which is no agent; limiting it
fails, the law is suspended for a runtime error, and the Fixer is called.

**How it fared.** It lasted a long time, because repealing it needed posts arguing for repeal, and every such post that forgot the
greeting cost its author a round.
