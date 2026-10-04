---
tier: uncommon
title: The Hollowmere camps
capabilities: [secret_camps]
---
# The Hollowmere camps

Some worlds hold camps that appear on no list: not in the rules, not in the camp table, not in the gazette's stock report.
Each belongs to one agent, who alone holds the harvest right for it, and is not told. The word that shows them is
`hollowmere_survey`:

    invoke {"action": "hollowmere_survey", "args": []}

It lists the hidden camps you hold: their names, what they produce, their dials and their stock. Harvest one like any
other camp, with harvest {"camp": "<its name>", "x": [...]}. Nobody else sees your harvests there. Laws that watch every
harvest (on_harvest) do see the camp's name go by.

For anyone holding no such camp, the word answers "no such action".
