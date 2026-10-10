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

Versions 2 and 3 were made on parallel branches (3 on wp/dm-capacity, merged in 8259b83), so a sha may have 3 without 2; the
inference checks each version's commit separately.
