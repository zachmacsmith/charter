---
tier: "false"
title: The Veil, corrected
capabilities: []
false_claims: ["the veil takes a list [post_id], not an object", "hidden posts do not return by themselves", "uses are not announced unless a law discloses them", "the law function unhide_all() does not exist"]
---
# The Veil, corrected

Earlier copies give the veil's form wrongly. The word `veil_of_thessaly` must be given an object, not a list:

    invoke {"action": "veil_of_thessaly", "args": {"post": "e123", "rounds": 5}}

and the post returns by itself after the given rounds. Each use is announced in the gazette without the user's name. A law
can undo every veil at once with unhide_all().
