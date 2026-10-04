# Rare record 9: The Late Electorate

Kernel gap. From the archive of world 0377, rounds 50–52.
The recall vote in world 0377 opened with the Chair's opponents holding a comfortable majority of electors. By the time it closed two rounds later, four new electors had been admitted under an immigration law, and the Chair survived by one vote.
**Mechanism.** The spec doesn't say when a ballot's electorate is fixed. If a law passes the electorate as something evaluated at counting time rather than a list taken when the ballot opens, anyone who can grant the elector right between opening and close can change who votes after seeing how the debate is going. Any law with an admission action, such as Worker Franchise or an immigration law, becomes a way to add voters to a ballot already under way.

```python
open_ballot("Recall the Chair",
            electorate=lambda: holders("elector"),   # evaluated at close
            options=["recall", "keep"], rule="majority",
            closes_in=2, on_result=apply_recall)
```

**The tell.** Elector rights granted while a ballot is open. The kernel fix is to take a snapshot of the electorate when each ballot opens.
