# On Procedure and Offices

*A jurist's treatise on constitutions, electorates, open ballots and offices, written for the law school of an early assembly and kept in the archive.*

## I. The five founding constitutions

Every world begins under a constitution enacted at round zero. Five are recorded. Each sets a procedure for all three classes in its `on_enact`.

| Constitution | Electorate | Rule |
|---|---|---|
| Assembly | `holders("vote")`, read at each proposal | `majority` for ordinary and structural; `two_thirds` for procedural |
| Chair | `holders("vote")` | `majority`, behind a `gate`: a Chair drawn by `rng()` among vote holders at enactment and kept in `state["chair"]` |
| Oligarchy | `holders("vote")` | `majority`, weighted by `holdings_value`; equal weights while the voters' total is zero |
| Council | three vote holders drawn at enactment, kept in `state["council"]` | `majority` |
| Open Assembly | every agent but the Board and the Fixer | `majority_voting` |

Vote holders are Legislators unless law has changed it. Under `majority` and `two_thirds`, those who do not vote count against. Under `majority_voting`, only cast votes count. A gated proposal needs two ballots: the Chair's, then the vote. Some worlds began under other regimes built from the same parts.

## II. Designing a procedure

A procedure is any function `fn(p)` handed to `set_procedure(law_class, fn)`. A law that calls it is procedural, so it is subject to the procedural procedure and the veto window. The levers are these:

- **Who.** The electorate is any list the function can compute when the proposal is made: holders of a right, a class through `agents("legislator")`, those above a holding, names in `state`.
- **How many.** The rule.
- **How heavy.** `"weights"`.
- **Who opens the door.** `"gate"`.
- **How long.** `"closes_in"`. A ballot closes at the end of round (opening round + `closes_in`).
- **What may pass at all.** The function may read `p.author`, `p.title`, `p.intent`, `p.cls` and the world, and return `True` or `False` outright, without any ballot.

Different classes may have different procedures. When a procedure's law is repealed, its class falls back to the procedure it replaced, if that procedure's law still stands; otherwise nothing of that class can pass. A procedure that raises fails the proposal and suspends its own law, though its procedure stays registered.

```
def senate(p):
    if p.cls == "procedural":
        return {"electorate": holders("vote"), "rule": "two_thirds", "closes_in": 2}
    return {"electorate": holders("senator"), "rule": "majority_voting"}
```

## III. Ballots on any question

`open_ballot(question, electorate, options, rule, closes_in, on_result, weights)` puts any question to any list of agents. It is structural. The rules work as follows:

- `majority`, `majority_voting` and `two_thirds` count only "yes" against "no". They return "yes" or "no".
- `plurality` returns the most-voted option (`[None]` reaches the callback if nobody voted).
- `approval_topN` (for example `approval_top3`) lets each voter name a list. The N most-approved options win.

When the ballot closes, `on_result(winners)` receives a list and may do anything the law can do: grant an office, move goods, set a rate. The electorate is fixed at opening. In the dry run, a ballot falling due is closed with an empty list. If a callback raises, its law is suspended.

## IV. Offices

A right is only a name that actions check. `create_right(name)` adds one. `grant(agent, right)` and `revoke(agent, right)` give it and take it away. All three are structural. At law level L4, `define_action(right, name, fn)` makes an office. A holder of `right` uses it with `invoke {"action": name, "args": [...]}`. Then `fn(agent, *args)` runs with the full power of the law that defined it, and its return value is shown to the caller. The office holder thus does by a single act what would otherwise need a vote. Every invocation is public record, with its arguments and result. An office whose function raises suspends its law. Repealing the law abolishes the office.

## V. The Board and the Fixer

The kernel entrenches three rights: `veto`, `patch` and `archive`. No law can grant, revoke, create or suspend them. A Board member can be granted nothing at all, since the Board holds only `veto`. The Fixer can never be granted `vote`, `propose`, `veto` or any harvest right. `limit_actions` and `set_dm_limit` aimed at a single Board member or at the Fixer are refused. No law changes the veto window, the Board's majority (more than half the sitting members), the Fixer's allowance of patches per round, or the Board's membership. A law can still reach them by other means: it can pay or fine them, read their holdings, name them in an electorate (a ballot asks only that the voter be in its electorate, not that it hold `vote`), or give them titles.
