# Engine versions

`charter/provenance.py` `ENGINE_VERSION` names the simulation's behaviour: bump it, in the same commit, whenever a code default flips
or the engine's behaviour changes on purpose, add a line below, and list every default flip in `provenance.ENGINE_FLIPS`
(machine-readable: the settings target, key path, old and new value, and the commit that made the version). Runs record it
(run.json `engine_version`, instance.json `settings.engine_version`, export `runs.engine_version`).

How it is used (ARCHITECTURE D-43, `charter/settings.py`): a run made since frozen settings carries every default it read, so a flip
cannot reach it. A run made before has its settings inferred on resume, fork or replay: its engine version is the newest version
whose commit is an ancestor of the run's recorded git sha, and the flips of every version it lacks are set back to their old value.
When the sha is unknown the resume is refused (`--allow-code-drift` overrides it, recorded). A behaviour change that is not a
default (the "behaviour" entries below) cannot be set back: `python -m charter rerun RUN_DIR` plays the run's command again under
its own code.

| version | commit(s) | default flips | behaviour changes |
|---|---|---|---|
| 1 | everything before 38070e1 (incl. 1b39c33, channels v2) | (baseline) | channels v2 introduced with `channels.delivery: pull` |
| 2 | 38070e1 | `channels.delivery` pull -> push | |
| 3 | 55d11fb, 9763182 | none (`dm_step.capacity: natural` is opt-in; nature_subsistence and ashwood set it, and their runs' specs record it) | under `capacity: natural` the Communications Act caps at its LIMIT with no per-agent extra (9763182; not a default, reproducible only by `rerun`) |
| 4 | 6a69002 | `context.memory_text` v1 -> v2 | |
| 5 | 23c948a, b629aa0 | `context.dm_delta` false -> true | under dm_delta the next round's prompt shows last round's DM exchange whole (b629aa0) |
| 6 | b04001c, b8e4b73 | `context.history.enabled` false -> true (history mode, review 20 §4; the key is new in b8e4b73, where it defaulted to false) | `recall` added to the lookups and actions (history mode only); in history mode DM replies are always deltas and the system prompt is frozen per conversation |
| 7 | 05f21c4 | none (`llm.cache_ttl: 5m` is a spec key in base.yaml, recorded in each run's saved spec; runs without it play under `auto`, the backend's choice: 1h on the CLI subscription) | the CLI gets CLAUDE_CODE_PROMPT_CACHE_TTL and API markers carry the TTL; run.json `flags` notes rounds averaging longer than the cache lifetime |
| 8 | de0c39c | `goals.SCORING_DEFAULTS.fixes` false -> true (review 23: Wealth, Hoard and Lineage Wealth count food in the stores an agent owns; Rank and Kingmaker rank only living agents, a dead holder or target scores 0; Dynasty is scored against the largest number of living descendants, Populator against the starting population; the Dynasty and Populator texts drop "population cap" with it) | none beyond the flip: review 24's goals and spec keys (goals.aims, goals.deadline, goals.a_slot, goals.survival, life.reproduction.child_goals, actions.unlisted) are opt-in and change nothing unset |

Versions 2 and 3 were made on parallel branches (3 on wp/dm-capacity, merged in 8259b83), so a sha may have 3 without 2; the
inference checks each version's commit separately.
