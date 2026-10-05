# Charter TODO

## Scoring as a per-goal interface (not started)

Today a global rule decides when an agent's goals are judged: `goals.score_at_end` (default on: everyone on the final world, the best of
its own score and its lineage's; before that, a departed agent was frozen at its departure through `events.segments`). Neither fits
every goal. Replace the global rule with a scoring interface that each goal defines for itself:

- **Interface.** `score(history, agent, params) -> float in 0..1 (or None)`. `history` is a read-only view of the whole run:
  `states` (one per round), `final`, `state(r)`, `events(type=...)`, `life(agent)` (born/arrived, left, cause), `alive(agent, r)`,
  `lineage(agent, r)`, `goal_of(agent, r)`.
- **Building blocks.** Timing helpers a goal composes freely: `at_end`, `at_exit` (the agent's last round alive, or the end),
  `mean_over_life`, `mean_over_run`, `peak`, `total` (a count over the history), weighted mixes of any of these (e.g. 0.5 x end state
  + 0.5 x average over the run), and an option to count living descendants.
- **Each goal decides** how its owner's death affects it; no global freeze or end-of-game policy. Goal changes still split scoring
  by rounds (a goal is scored over the rounds it was held).
- **Record enough to make any rule expressible.** Add to each round's snapshot whatever only the end state has today: who is
  alive, role holders, each agent's current goal, lineage links (snapshots already hold holdings, values, rights, vote weight, the
  decisive set, laws in force, jurisdiction membership, stocks, prices, reserve, loans, media and conflict state).
- **Suggested defaults to start from** (then tune goal by goal): own-state goals (Wealth, Rank, Hoard, Power, Office, Sovereign) at
  exit plus descendants; world-shaping goals (Puppeteer, Kingmaker, Enact, Block, Revolutionary, Schism, Depopulator, Spoiler) at
  end; deed goals (Lawmaker, Gifts, Eliminator, Reaper, Litigator, Leaker) total over the run; sustained goals (Steward, Guardian,
  Durable, Mandate, Silence) mean over the run.
- Remove `goals.score_at_end` and `events.segments`' departure handling once every goal states its own rule; rescore old runs.
