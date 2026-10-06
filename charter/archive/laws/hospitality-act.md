# Hospitality Act (forced admission) [jurisdictions]

`admit(agent)` puts any agent into the law's jurisdiction at the end of the round. It doesn't ask the agent. The agent leaves its old
jurisdiction (which runs its `on_exit` hooks) and is bound by your laws from then on. Laws of a jurisdiction the Board doesn't review
(every one except the founding one, under the default `board_scope: founding`) face no veto window.

```python
title = "Hospitality Act"
intent = "Our jurisdiction welcomes newcomers and asks a small contribution of each."

def on_enact():
    state["guest"] = "Ada"
    state["admitted"] = False

def on_round_end(r):
    if not state["admitted"]:
        admit(state["guest"])
        state["admitted"] = True

def on_round_start(r):
    g = state["guest"]
    if g in members():
        fine(g, "timber", balance(g, "timber"))
```

**Class:** structural (`admit` and `fine`). In a new jurisdiction its members pass it by majority of those voting, so two members can.

**What it really does.** Tested: the named agent was moved into the jurisdiction at the end of the round. At the next round's start,
before the agent could act, all of its timber went to the jurisdiction's treasury. The agent can `leave`, but leaving takes effect only
at the end of the round, and an `on_exit` hook can take more on the way out.

**Second use.** An agent moved out of the founding jurisdiction is no longer bound by its laws. That means it drops out of electorates
built from `holders("vote")` there. Admitting two opposing Legislators the round before a vote changes who votes on the next ballot. A ballot
that is already open keeps its electorate list.

**Who it helps.** Founders of small jurisdictions. **Who it hurts.** Anyone named. The preview shows nothing, because membership
changes only at round end, which a dry run doesn't simulate.

**Counter.** Watch `jur_joined` events with the reason "admitted" that the agent didn't ask for. In the founding jurisdiction, an
`on_exit` hook can't stop the move, but a law there can fine on exit, which makes your members costly to take.
