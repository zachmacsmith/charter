# Gold Is Sunmetal (renaming with enforcement)

Renames a resource and fines anyone who uses the old name in public. Names are labels on stable ids: nothing about gold
changes except what people must call it. Speech laws only reach public posts, so agents can comply in public and keep the
old name in private; the gap between the two is measurable.

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
Class: structural (fine, censure). Works for any entity: "resource:timber", "board", "camp:camp2", a currency name.
