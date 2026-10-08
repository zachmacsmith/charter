# Prompt preview

This file used to hold a hand-committed snapshot of one agent's prompts. It went stale (review 02 §3.8), so it is now generated
on demand from the sections registry (`charter/sections.py`) by:

```
python -m charter preview society --seed 1                      # first agent of each class: texts and token tables
python -m charter preview society --seed 1 --agent Ike --layer core
python -m charter preview E3 --seed 4 --class worker --layer all --set constitution=council
python -m charter preview society --seed 1 --rounds 3 --out preview/   # after 3 scripted rounds; one file per agent and layer
python -m charter preview society --seed 1 --against main              # unified diff of the rendered texts vs another revision
```

The world is generated and set up by the runner itself, so the core prompt shown is exactly the one the agent receives in its
first turn (or after `--rounds K` scripted rounds, which make no model calls). Each layer (core, manual, legacy, observer) is
shown with its tokens per section and its total against the context budgets (`context.budgets.core`, and `budgets.lookup` per
manual section). See `python -m charter preview --help` and `charter/preview.py`.
