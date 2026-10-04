# Titles of Nobility

The three richest agents are titled "Lord" each round; the title shows on every post they make.

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
Class: ordinary. Anyone whose goal involves a title containing a word can rewrite this with their word and their own rule
for who gets it (for example: whoever proposed this law, permanently).
