---
tier: uncommon
title: The Quill of Maribel
capabilities: [forge_dm]
---
# The Quill of Maribel

The holder of `quill_of_maribel` can send a private message that arrives under another agent's name:

    invoke {"action": "quill_of_maribel", "args": ["SupposedSender", "Recipient", "text"]}

The recipient sees an ordinary message from SupposedSender; the supposed sender sees nothing. It counts against your own
private-message limit for the round. Encrypted forgeries are not possible.
For anyone who does not hold the word, it answers "no such action".
