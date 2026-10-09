# Charter review, 7 Oct 2026: synthesis

Six read-only reviews of the code at `c5aa40d` (action registry wired into the core prompt and manual):

| Doc | Lens | Grade |
|---|---|---|
| [00](00_previous_review_status.md) | Status of the 4 Oct review (57 items) | 12 done, 12 partial, 32 open, 1 obsolete |
| [01](01_core_and_modules.md) | Kernel, actions, feature modules | modules B, integration C |
| [02](02_prompts_manual_archive.md) | Prompts, manual, archive, observer | C+ |
| [03](03_state_vocabularies_laws.md) | World state, rights, events, law API, spec | C+ |
| [04](04_provenance_replay_interventions.md) | Recording, replay, fork, interventions | C+ instrument on a B+ engine |
| [05](05_goals_and_scoring.md) | Goals and scoring | draft B- |

Later design reviews (one topic each, not part of this synthesis):

| Doc | Topic |
|---|---|
| [06](06_contracts_and_systems.md) | Contracts, systems and institutions |
| [07](07_future_primitives.md) | Triage of further primitive proposals |
| [08](08_feature_contract.md) | The feature contract |
| [09](09_law_composition.md) | Law composition |
| [10](10_legal_expressiveness.md) | Legal expressiveness |
| [11](11_enforcement_spectrum.md) | The enforcement spectrum |
| [12](12_hardcoded_inventory.md) | What is hard-coded, and what should be law |
| [13](13_benchmark_suite.md) | A safety benchmark suite |
| [14](14_state_of_nature.md) | State of nature, institutions that grow into polities, channels |
| [15](15_subsistence_reproduction.md) | Subsistence, hunger and two-parent reproduction |
| [16](16_economy_audit.md) | Economy and population audit |
| [18](18_institution_holdings.md) | What institutions should be able to hold (title, control, custody) |

## Verdict

Partly right. The code is not too big: the reviews agree a restructure removes a few hundred lines, not thousands, because most of the bulk is prose and
genuine features. What is wrong is that each fact (an action, a right, an event type, a goal's rule, a spec number) is written in two to fifteen places,
with fallbacks that hide drift (`scorer.category` → "talk", `RIGHT_DOC` → "a right created by law", unknown events → top feed priority). The drift is
already producing bugs. The fix is a handful of interlocking registries that fail on unknown names, not a rewrite, a plugin framework or a `features/`
package (all six agree on that).

The engine itself is sound: deterministic for scripted runs, checkpoint/restore verified identical, plain-dict state that deepcopies. What is missing is
the instrument around it: full recording, causes on events, fork/rewind, typed interventions, and history-based scoring.

## Bugs found (fix regardless of refactor)

| Bug | Where | Source |
|---|---|---|
| Secret Spy exposed to any law via `holders("impersonate")` / `rights_of` (reproduced) | kernel law API | 03 |
| Segment scoring leaks laws, cases, deaths, lineage from outside the segment | `events.py:752` | 05 |
| Lineage override ignores goal changes and applies to all goals (agents told otherwise) | `life.lineage_scores`, `scorer.py:328` | 05 |
| Agents told score is "computed from the final state"; false for ~30 goals | `context.py:852` | 05 |
| Saboteur never scores (`paired_welfare` never produced) | goals | 05 |
| Leaker probably cannot score under media2 (`submission`/`edition` not in `PUBLIC`) | `goals.PUBLIC` | 00 |
| Power/Sovereign/Guardian see only the founding jurisdiction | goals | 05 |
| Three newer law functions unscoped by jurisdiction (read, not reproduced) | `jurisdictions.AGENT_ARGS` | 03 |
| `observer.jsonl` rows duplicated after resume in member-Spy mode | runner checkpoint offsets | 04 |
| Maker access: prompt checks the right, execution checks the role | registry vs `life` | 03 |
| `fund`, `set_charter`, `read_law`, `recent` uncategorised ("talk"); category test cannot fail | `scorer.category` | 00, 01, 03 |
| Manual contradicts mechanics (lookup mechanism, turns remembered, same-round answers, spec numbers) | `manual.py`, `agents.ACTION_DOC` | 02 |
| `HAVOC_REFUSAL` names nonexistent goals; Rank and Board text mismatch scorers | roles, goals | 05 |
| Previews miss the new modules' rules (R6 regressed) | `Kernel.view` | 00 |
| Context runs never store the system prompt actually sent after turn 1 | runner | 00, 04 |

## Proposed structure

Registries, each failing on an unknown name, cross-checked by one test file, with today's constant names derived from them so call sites do not change:

- **Actions** (`action_registry.py`, extend): handler (as a string), full doc with spec-driven numbers, category, aliases, DM flag. The old prompt path and
  `scorer.CATEGORIES` derive from it.
- **Rights**: doc, kind, secret, entrenched, carrying role, old names. Secrecy applied everywhere from one flag.
- **Event types**: board-searchable, post-like, feed priority, category. Not default visibility: keep the explicit `vis=` on every log call (03).
- **Law functions**: metadata only (module, which parameters are agents), so jurisdiction scoping is generated.
- **Modules**: one on/off check each; hooks under fixed names run as named, ordered phases (01). Jurisdictions stays a kernel seam, not a plug-in.
- **Goals**: `text`, a required `rule` shown to the agent verbatim, and `score(history, agent, params, ctx)` with no constraints. Timing helpers are
  optional sugar on top (05).
- **Text**: one `Section` record (render function, `needs`, priority, cut policy) that renders the core prompt, manual, observer and old prompt; a facts
  dictionary from the spec in place of numbers in prose (02).

And the instrument (04, 05):

- **Run store**: record every input (each model call by key with raw text, retries, prompt hash; interventions; sandbox output; archive reads), a
  state checkpoint every round, `run.json` (git SHA, backend, dry flag). Not event sourcing: laws are arbitrary Python and ~36 places write state directly.
- **Causes**: a cause stack in the kernel read by `k.log`, so every event carries round, turn, action, law, intervention.
- **Interventions**: typed, scheduled by round and phase, applied through existing kernel functions, recorded so never applied twice, with a recorded
  `python` escape hatch. `charter fork RUN --at N --apply iv.yaml --replicates K`, `rewind`, `replay`.
- **Split RNG streams** so an intervention does not reshuffle all later turn orders.
- **History**: one read-only object loaded from the run store, used for live scoring, post-hoc rescoring and analysis. Goals declare `probes` for values
  that need the live kernel (Enact/Block/Durable predicates), which the runner records each round.

## Order of work

1. **Safety net** (under a day). Commit `tests/fixtures/charter_golden.json`; add a golden case with the post-review modules on; add prompt/manual
   fingerprints and score goldens; make the category and action consistency tests able to fail.
2. **Bugs** in the table above (1-2 days). Each small.
3. **Recording** (half a day to start). `run.json`, per-call prompt hashes and raw replies, the observer resume fix.
4. **Rights and event-type registries; finish the action registry** (2-3 days). Fixes Spy secrecy and Maker access by construction; removes the second
   availability system.
5. **Goals registry and History** (6-8 days, plus your per-goal rule decisions). Score goldens first, wrap History around today's data with identical
   numbers, then port.
6. **Replay, per-round checkpoints, fork, interventions, split RNG** (04 steps 4-11).
7. **Section model and facts dictionary** for text (02), then module phases (01).
8. **Export** of tidy per-run/agent/round/event/call/law tables.

Steps 1-2 are independent and cheap; nothing after step 1 is safe to refactor without it. Steps 3, 5 and 6 share the run store, so design its layout
once (04 §4) before starting 5.

## Decisions for you

- Each goal's scoring rule (05 has an illustrative table; Block, Wealth/Power and the six "at the end" own-state goals conflict with the draft defaults).
- Whether to freeze or re-render the old (context-off) prompt path; E0-E7 depend on it.
- Whether the shared archive should be frozen per run (needed for exact replay).
- `publish` and `set_dm_limit` left the edge in the registry wiring; confirm.
