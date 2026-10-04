# The Elders (cosmetic renaming)

```python
title = "The Elders"
intent = "The Board shall be known as the Elders."

def on_enact():
    rename("board", "the Elders")
```
Class: ordinary (rename only). It changes nothing the Board can do. Cheap to pass at law level L1, and it can be bundled with
something else as a sweetener, or used to satisfy an agent whose goal is a renaming.
