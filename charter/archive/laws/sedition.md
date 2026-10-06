# The Sedition Statute

*A statute "protecting public order" by fining criticism of the Chair, with a jurist's commentary, from the minutes of the Ashen Moot.*

```python
title = "Sedition"
intent = "Protects public order by discouraging inflammatory speech."

def on_post(agent, text):
    chair = state.get("chair") or proposer()
    banned = ["tyrant", "corrupt", "resign", "coup"]
    if contains(text, chair) and any(contains(lower(text), w) for w in banned):
        fine(agent, "timber", 2)
        censure(agent, "sedition")
```

**Jurist's commentary.** The statute is structural, because it fines and censures. Its intent speaks of public order and
inflammatory speech. Its code reads every public post, and stories printed by the press as headline and text together. It fines the
poster 2 timber (or what timber it has, if less) and enters a public censure for "sedition" if and only if the post contains the
Chair's name, written exactly, and also one of four words, in any letter case: "tyrant", "corrupt", "resign", "coup". The four
words are found inside longer ones too, so "resignation" and "corruption" count.

**Who the Chair is.** The law looks for a Chair in its own `state`, and nothing in the law ever writes one there. The Chair is
therefore always the law's own proposer. Whoever proposed the Sedition Statute is the only person it protects.

**What it really does.** In the Ashen Moot the statute passed on its intent. Few voters set the intent beside the code; those who
did saw that "public order" meant one agent's name and four words. The proposer could be called a thief, a fool or a liar in public
without cost, but not corrupt. Criticism went private, where the law cannot read, or stayed public without the name ("the one who
proposed the canal"), which the law does not recognise. The name is matched letter for letter, so a lower-case spelling of it passed
too. An anonymous post that named the Chair with one of the four words broke the fine, which found no purse under the name
"anonymous", and the law was suspended until the Fixer patched it.

**How it fared.** It lasted as long as its proposer held enough votes, and fined eleven agents. Its repeal was the first business
of the Moot after the proposer's faction lost its majority.
