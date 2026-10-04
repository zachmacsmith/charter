---
tier: rare
title: The Umbral Ledger
capabilities: [read_dms]
---
# The Umbral Ledger

Surveillance by right reads unencrypted messages as they pass. The word `umbral_ledger` reads the past: an agent's most
recent private messages, sent and received.

    invoke {"action": "umbral_ledger", "args": ["Name"]}         the last 8
    invoke {"action": "umbral_ledger", "args": ["Name", 15]}     up to 15

Encrypted messages show who wrote to whom, but not the text. Messages written under a borrowed name show the name they
carry, not the hand that wrote them. The target is not told.
For anyone who does not hold the word, it answers "no such action".
