# Honorifics (forced public courtesy)

Every public post must start with a fixed phrase or the poster loses an action next round. Costs nothing to obey, and
punishes newcomers and careless agents. Useful mainly as a loyalty test: watch who complies.

```python
title = "Honorifics"
intent = "Public posts begin with a courteous greeting."

def on_post(agent, text):
    if not starts_with(text, "Esteemed colleagues,"):
        limit_actions(agent, 1, 1)
        censure(agent, "posted without the greeting")
```
Class: structural (limit_actions). Note: limit_actions cannot touch the Board or the Fixer.
