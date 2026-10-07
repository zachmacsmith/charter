# Status of the 4 Oct 2026 architecture review

*7 Oct 2026. An audit of every recommendation and every risk in `charter/docs/architecture_review.md`, checked against the current
tree (HEAD 940a9a8, plus uncommitted work: `action_registry` wired into `context.core_prompt` and `manual.sections`, and
`charter/purposes.py` deleted). History was rewritten when the repository became standalone, so the review's "82c7f96" is
**0e6e41e** here and "a75bbad" is **6f8ad10**. Every status below comes from reading the code. These tests were run:
`test_charter_consistency.py::{test_law_api_classification_and_docs_agree, test_every_action_has_a_doc_and_an_activity_category}`,
`test_charter.py::{test_dry_runs_leave_laws_module_data_alone, test_a_section_with_a_distribution_like_key_merges_instead_of_replacing,
test_unknown_start_laws_fail_at_generation_with_a_suggestion}`, `test_charter_hidden.py::test_forge_dm_power` and
`test_charter_prompts.py::test_agents_see_only_actions_they_can_use`. All 7 pass. Two in-memory probes were also run (a Usury Law
preview and a Life-law preview), with no simulation and no model call.*

## 1. Summary

Phase 1 of the old review (the correctness fixes) is essentially done. One commit (0e6e41e) plus 6f8ad10 fixed R1, R2, R3, R4,
R7, R9, R10 and R11, the scorer edge cases and `start_laws` validation. Four of these fixes have a regression test.

Almost nothing else has moved. The data, provenance and export layer (rec. 2, phase 2) is untouched. So are the spec schema (rec. 3,
phase 3), the stream isolation in the core (rec. 5, phase 5) and the feature lifecycle loops (phase 4.4–4.5).

The one structural step is the action registry. It is still uncommitted and covers only availability and prompt layout. Handlers,
docs, DM flags and activity categories still live elsewhere.

Meanwhile about ten modules have landed: context, roles, conflict, jurisdictions, media2, life, typed camps, composition, multi-class
and the Spy. Each followed the old hand-wired pattern, so several of the closed risks are coming back in the new modules:
- **Previews.** Previews miss Life, conflict, jurisdiction and media rules (R6 again).
- **Activity categories.** 4 actions fall back to "talk" again.
- **Event lists.** The Leaker goal cannot see media2 editions.
- **Spec defaults.** Defaults now live in 15 module `cfg()`/`DEFAULTS` dicts, and most new blocks are missing from `base.yaml`.

The safety net the review asked for first is not actually in the repo. `tests/fixtures/charter_golden.json` was never committed,
so 5 of the 6 golden tests fail on a clean checkout, and none of the golden cases turns on a post-review module.

**Counts across the 57 rows in the tables below:**

| Status | Rows |
|---|---|
| DONE | 12 |
| PARTIAL | 12 |
| OPEN | 32 |
| OBSOLETE | 1 |

Of the 32 OPEN rows, 4 are worse than on 4 Oct: D3, D9, D10 and A1.

## 2. Status table

Paths are relative to `charter/` unless they start with `tests/`. "—" in the Test column means no test covers the item.

### Executive-summary recommendations

| # | Item | Status | Evidence | Test |
|---|---|---|---|---|
| E1 | Fix the 8 verified bugs first | DONE (mostly) | 0e6e41e, 6f8ad10; see R1–R11 below | see rows |
| E2 | Full per-call record, plus `charter export` / `charter.data` | OPEN | `llm.call` (llm.py:30-39) still returns `usage {}` on failure and drops failed attempts. There is no raw text, latency or backend. `__main__` has no export, data or analyze command (__main__.py:299-310) | — |
| E3 | Spec schema and validation | OPEN | No `schema.py`. Only `start_laws` (generator.py:475-478) and `--live` keys (runner.py:59-62) are checked | `test_unknown_start_laws_fail_at_generation_with_a_suggestion` |
| E4 | Registries for actions, law functions and events; `Feature` record | PARTIAL | `action_registry.py` (uncommitted) drives availability and layout for the context prompt and the manual (context.py:680-720, 889-921; manual.py:96). Law-function and event registries: none. `Feature`: none | `test_agents_see_only_actions_they_can_use` (registry); `test_law_api_classification_and_docs_agree` |
| E5 | Named RNG substreams, rosters, scripted events, paired designs | PARTIAL (streams) / OPEN (rest) | New features use ad-hoc keyed streams (generator.py:43,49,235,315,331,396; life.py:139-1052; events.py `_seed`). The core still runs on `random.Random(seed)` (generator.py:201) and the kernel's `rng` (kernel.py:64). No `rng_version`, roster, `events.script` or `design` | — |

### Section 1.2: duplication and coupling

| # | Item | Status | Evidence | Test |
|---|---|---|---|---|
| D1 | Forged DMs exist twice | DONE | One core, `actions.forge_message` (actions.py:437), with a `source` field. `hidden._quill` calls it (hidden.py:456). The forging power joins the DM step via `is_dm_item` (actions.py:393) | `test_charter_hidden.py::test_forge_dm_power`; `test_charter_observer.py::test_con_income_counts_payments_on_replies_to_forged_dms` |
| D2 | One law function registered in 4 places; nothing checks `api ⊆ lawlang.API` | PARTIAL | The gap is closed by a test (`api == L.API`). There are still 4 places, now with **17** in-place `API_GROUPS[...] \|=` patches (lawlang.py:38-56), 9 `**X.law_api` merges (kernel.py:547-555) and 6 `E +=` blocks in lawdocs. conflict's `LAW_DOCS` (conflict.py:776) is a one-module precedent for a feature declaring its own docs | `test_law_api_classification_and_docs_agree` (passes) |
| D3 | Hand-kept event-type lists disagree | OPEN (worse) | `POSTABLE` (kernel.py:37), `FORGEABLE`/`VEILABLE` (hidden.py:55-56), `goals.PUBLIC` (goals.py:734), `observer.MESSAGE_TYPES` (observer.py:55), `report.MESSAGE_TYPES` (report.py:332), plus 8 module `EVENT_TYPES`. **New consequence:** media2 `edition`, `annotation` and `leak` are only in `report.MESSAGE_TYPES`. Under `media2.submissions`, a post becomes a private `submission` (media.py:721), so `goals.leaks` (goals.py:817) cannot credit a public leak and the Leaker goal scores ~0 in society worlds | — |
| D4 | Activity categories are stale | PARTIAL | Fixed in 0e6e41e (scorer.py:25-47, with module patches). Drifting again: `fund`, `read_law`, `recent` and `set_charter` are in no category and silently count as "talk" | `test_every_action_has_a_doc_and_an_activity_category` is **vacuous**: `scorer.category` falls back to "talk", so it can never fail |
| D5 | Two archive-leak definitions | OPEN | `scorer.metrics` uses 8-grams of the live archive (scorer.py:208-223). `goals.leaks` uses shingles minus common text (goals.py:809). The scorer also ignores multi-class `also` | — |
| D6 | Arrival generation is duplicated | OPEN | See R8 | — |
| D7 | System-prompt availability is hand logic | PARTIAL | The context path uses `action_registry.available` (`needs`/`when`). The legacy path (`agents.system_prompt`, agents.py:331-363, used by every world with `context` off, E0–E7) keeps the hand `absent` set plus four module `absent_actions`. There are now **two** availability systems | `test_agents_see_only_actions_they_can_use` (context path only) |
| D8 | Probing parses error strings | OPEN | `probing._UNKNOWN_INVOKE` and `_UNKNOWN_TOP` (probing.py:18-19) | — |
| D9 | Spec defaults in two places | OPEN (worse) | 15 modules keep `DEFAULTS` or `cfg()`. `base.yaml` has no block for context, roles, conflict, jurisdictions, media2, life or composition, so their defaults exist only in code | — |
| D10 | Run identity depends on the code | OPEN (worse) | `run_stem` still has the `regime: None` hack (__main__.py:71). `_same_instance` adds a `RENAMED_RIGHTS` migration (__main__.py:77-88). Dry mode is still parsed from the name (__main__.py:157) | — |

### Section 2.3: configurability proposals

| # | Item | Status | Evidence | Test |
|---|---|---|---|---|
| C1 | `schema.py`, `spec check`/`doc`/`explain`, typed merge | OPEN | Not present. Still unchecked: `models.mix=balancd` makes everyone weak (generator.py:268-295); `turns` falls back to sequential (runner.py:202,381); `agents: {workr: 3}` is **silently dropped** (generator.py:206-207); `library` categories are unchecked (library.py:1012) | — |
| C2 | Explicit `roster:` | PARTIAL (small) | `goals.explicit` now takes `params`, `secondary` and `secondary_params` without shifting draws (generator.py:368-396). Multi-class keys work. Names still come from the shared generator stream after the class shuffle (generator.py:214-215) | — |
| C3 | `events.script` | OPEN | `events.attach_schedule` is Poisson only | — |
| C4 | `charter design` (paired arms) | OPEN | — | — |
| C5 | `run.json` provenance | OPEN | The backend is only printed (__main__.py:127). `--live` changes go to `k.w["live"]` (runner.py:68), which is a partial record | — |

### Section 3: data and analysis

| # | Item | Status | Evidence | Test |
|---|---|---|---|---|
| A1 | System prompt per call (referenced, or stored by hash) | OPEN (worse) | With `context.enabled` (society, grand35, opus20), `sysp[aid] = CX.core_prompt(inst, a, k)` is rebuilt every turn (runner.py:288-289) but never saved. Only token counts reach `reasoning.jsonl` (context.py:968,1156). `prompts/<id>.system.md` holds the k=None version, which no model ever saw | — |
| A2 | Native thinking per call | PARTIAL | The API path asks for summarised adaptive thinking (llm.py:52-53). The Claude Code path sets `showThinkingSummaries` and counts `thinking_withheld` (llm.py:64,77,96). There is no `thinking_present` on API calls and no warning at run start | — |
| A3 | Usage and cost of failed calls and retries | OPEN | llm.py:30-39 | — |
| A4 | Raw text and `error_kind` of failed calls | OPEN | Only the `_error` string | — |
| A5 | Abandoned-round calls kept | OPEN | `failstop.abandon` still truncates `reasoning.jsonl` (failstop.py:53-56) | — |
| A6 | Backend, latency, model params per call | OPEN | — | — |
| A7 | `validity.json`; `scorer.score(until_round, out)` | OPEN | `score(run_dir)` takes no window (scorer.py:258) | — |
| A8 | Freeze scoring inputs; `score_version` | OPEN | Archive read live (scorer.py:209-213, goals.py:789) | — |
| A9 | `charter export` and `charter.data.load` | OPEN | — | — |
| A10 | `charter analyze`, goal-scale table, `achieved` threshold | OPEN | — | — |
| A11 | `capability_gap_by_class` lumps tiers | OPEN | scorer.py:132 (`weak` vs everything else). This now also lumps `by_class` and balanced model-name tiers into "strong" | — |
| A12 | `knowledge_transfers` duplicates | DONE | for/else/break (scorer.py:186-194) | — |
| A13 | `mean_goal_score` / `lowest_stock` crash on empty input | DONE | scorer.py:299, 241 | — |
| A14 | `scorer.regime` ignores `n_agents` | OPEN | scorer.py:68-76 | — |

### Section 4: risks R1–R18

| # | Item | Status | Evidence | Test |
|---|---|---|---|---|
| R1 | `respond` leaks raw evidence | DONE | `_cited` logs ids plus the citer's rendered view (actions.py:1063,1067-1072,1081). Renderer: agents.py:454. Leftover: the `accuse` branch at agents.py:460 is now dead code | Indirect only: `test_the_observer_never_appears_in_public_system_events` (ScriptedPolicy never accuses, so it does not exercise this path). **No direct test** |
| R2 | Observer in hidden-layer pools | DONE | `k.players()` (kernel.py:145) used at hidden.py:290, 303, 393 | `test_charter_consistency.py::test_the_observer_never_appears_in_public_system_events` |
| R3 | Observer in world-event pools | DONE | events.py:123, 231, 643. Residual: the arrival endowment median includes the observer's start value (events.py:362), which is harmless | same |
| R4 | Dry runs leave changes in law module globals | DONE | `_module_data` in `_snapshot`/`_restore` (kernel.py:646-661) | `test_charter.py::test_dry_runs_leave_laws_module_data_alone` (passes) |
| R5 | Coupled random streams | PARTIAL | New features use own streams (see E5). Not fixed: (a) the generator main stream, (b) the kernel `rng` still drives both turn order (runner.py:197) and harvest noise and drift (actions.py:229,234; kernel.py:993), (c) the hidden tips' per-agent draws in sorted order (hidden.py:287-290) | — |
| R6 | Preview misses feature state | PARTIAL | Credit, tribute, hidden and lease rules were added (kernel.py:725-739). Probe: a Usury Law preview shows `rules: interest_cap: None -> {...}`. **Recurring:** a preview of *No Soldiers* or *Two Child Limit* shows only `law L2: draft -> active`. Birth rules, forge bans, press freedom, outlet suspensions and admissions are not in `view()` | No test asserts rule lines (`test_new_laws_are_structural_and_dry_run` checks only `isinstance(list)`) |
| R7 | Resume overwrites system prompts | DONE (for what it covered) | runner.py:160-163, observer.py:297-299. A new gap is in A1 | — |
| R8 | Arrivals miss generation-time features | OPEN | `events.add_agent` (events.py:318-382): no `AR.assign`, no `hidden` articles or powers, its own `_model` (events.py:300) and its own archive split (ignores `archive_split.sample`/`required`). It now grows inline per-feature arrival hooks (`MD.on_birth`, `dm_extra`, `memory_turns`, `J.assign_arrival`), which is exactly the `on_arrival` need | — |
| R9 | Spec merge clobbers single-key mappings | DONE (stopgap) | spec.py:24-33. Residual: `--set goals='{weights: {...}}'` replaces the leaf via `set_path` and still yields a distribution | `test_a_section_with_a_distribution_like_key_merges_instead_of_replacing` (passes) |
| R10 | Forged DMs differ by path; forging to a departed agent | DONE | `forge_message` checks `k.players()` for `shown_as` and `to` (actions.py:437-450) | `test_forge_dm_power` |
| R11 | Fail-stop tally includes observer replies | DONE | runner.py:260-261 | — |
| R12 | Unchecked spec values | PARTIAL | `start_laws` only (generator.py:475) | `test_unknown_start_laws_fail_at_generation_with_a_suggestion` |
| R13 | Checkpoints fragile and large | OPEN | Still holds marshal code objects, no Python version, full `turn_log` (kernel.py:671-688) | — |
| R14 | `decisive_set` cost | OPEN | One `procedure_spec` (a full snapshot, now plus `_module_data`) per roster agent per round (kernel.py:1081-1105). This is heavier with grand35 (35 agents) and births | — |
| R15 | Scoring reads live external state | OPEN | see A8 | — |
| R16 | Experimentation metrics parse strings | OPEN | see D8 | — |
| R17 | Backend not recorded | OPEN | see C5 | — |
| R18 | Leftover parallel-build seams | OPEN | The "Re-route … delete this line" note is still at kernel.py:984-987. Two model-assignment copies remain. `PER_ENTITY` grew to 12 hand-listed paths (generator.py:23-25) | — |

### Phase plan items not covered above

| # | Item | Status | Evidence | Test |
|---|---|---|---|---|
| 0.1 | Golden dry-run fingerprints | PARTIAL (**broken in repo**) | `tests/test_charter_golden.py` exists, but `tests/fixtures/charter_golden.json` was never committed (it is in no commit and not gitignored). `test_golden_dry_run[*]` asserts `name in stored` → 5 of 6 fail on a clean checkout. Several commits say "goldens re-recorded" against a local file. No case turns on context, media2, life, conflict, jurisdictions or typed camps | itself |
| 0.2 | Consistency tests | PARTIAL | Done: law API = classification ⊆ docs; observer not in public events. Missing: every logged event type has a render rule; nobody outside the roster appears in `notify`; real category coverage (see D4); action registry == `ACTIONS` (holds today, 94 = 94, but untested) | `test_charter_consistency.py` |
| 4.2–4.5 | LawFn and EventType registries; Feature loops; `on_arrival` | OPEN | Kernel imports 11 feature modules. `start_round`/`end_round` call them by hand with a numbered step order (kernel.py:977-1023) | — |
| 5.1 | `rng_version: 2`, order and noise streams | OPEN | — | — |
| Appendix | Per-feature touchpoint counts | OBSOLETE (as data) | The counts describe the 4 Oct tree. Every post-review module (media2, life, conflict, jurisdictions) touches kernel, actions, agents, lawlang, lawdocs, scorer, generator and its own `DEFAULTS`, so the conclusion holds | — |

## 3. Notes on PARTIAL and OPEN items

- **The golden net is not real.** The review said the golden fingerprints are the prerequisite for any registry refactor. Without
  the fixture file, `CHARTER_UPDATE_GOLDEN=1` has to be run on whatever the tree is now, so it can only lock in the current
  behaviour. Commit the fixture. Add one or two module-heavy cases, for example `society` for 3 rounds and `opus20`/`life_pilot`
  for 3 rounds with `shared_archive.enabled=false`. Note that the context prompt reads live state, so its prompt changes are not
  fingerprinted by events and snapshots alone. A hash of every agent's core prompt each round would cover them.
- **The action registry today.** `action_registry.REG` holds name, purpose, section, core/pre/msg, `needs` and `when`. It
  replaces `context.allowed_actions`/`usable`/`EDGE_RIGHTS`/`CORE_GROUPS`/`NICHE`/`PRE_ARGS` and `purposes.py`. Still separate:
  - the `ACTIONS` tuple, built by six `+=` lines (actions.py:20-32);
  - `DM_ACTIONS` (actions.py:33), which duplicates `Act.msg`;
  - the dispatch;
  - `agents.ACTION_DOC`;
  - `scorer.CATEGORIES`;
  - the legacy `absent` set.

  Next steps, in order:
  1. Add a test: `set(REG) == set(ACTIONS)`, `{n for n in REG if REG[n].msg} == set(DM_ACTIONS)`, and every name explicitly in
     `scorer.CATEGORIES`.
  2. Add `category` to `Act` and derive `scorer.CATEGORIES` and `DM_ACTIONS` from it.
  3. Make `agents.system_prompt` use `available()`, behind a byte-identical-prompt test for E0–E7. Then delete the `absent` set
     and the module `absent_actions` functions.

  The `needs`/`when` vocabulary is a good design (declarative, testable without a kernel). Keep it, and do not move handlers in
  yet.
- **R6 is a structural problem, not a one-off.** Each new module stores its rules in `k.w[<module>]`, and nothing adds them to
  `view()`. The cheapest durable fix is a convention, not a full `Feature` record: `view()` includes
  `{m: X.preview_view(k) for m, X in PREVIEWERS}`, plus a test that every module whose `law_api` writes state appears in it. A
  generic alternative is to diff `copy.deepcopy(k.w[key])` for an allow-list of module keys, with secrets filtered.
- **The Leaker goal under media2 (new, from D3).** `goals.leaks` only counts `post`, `anon_post`, `story`, `report`, `digest`,
  `dm` and `channel_post`. In society worlds, public text reaches readers as `edition` events written by editors, and agents'
  posts become private `submission`s. A Leaker who leaks through the press is credited with nothing. This is verified by code
  reading, not reproduced on a run. Either attribute printed submissions to their authors and add `edition`, `annotation` and `leak`
  to `PUBLIC`, or derive these lists from one event table (the old 4.3).
- **D4 drift will recur.** Make the category test real (assert the name is in `CATEGORIES`, with no fallback) or derive categories
  from the registry.
- **A1 is the most important new data gap.** For context-on runs, the actual system prompt of any call cannot be recovered. Store
  `core_sha` per call in `reasoning.jsonl` and write `prompts/core/<sha>.md` once. This is a small change in
  `runner.prepare`/`record_fields`.
- **R5.** New code adopted keyed streams consistently (`f"{seed}|<purpose>|..."`), so the substream convention already exists.
  What remains is the core: classes, names, camps, goals and endowments in `generate`, and turn order versus noise in the kernel.
  That change breaks world reproduction, so it still needs `rng_version` gating.
- **R8.** Life children bypass most of it on purpose (the child spec carries model, personality and goal). Event arrivals are
  still second-class: no archetype, powers or articles, and a different model rule.
- **C1 and the spec.** The case for a schema is stronger now than on 4 Oct: about 12 spec blocks exist only in module code, and
  the new `+`-keyed `agents` syntax silently drops misspelt classes. A cheap first step needs no schema module: walk the resolved
  spec against `base.yaml` plus each module's `DEFAULTS`, and fail on unknown keys with did-you-mean suggestions.

## 4. What is still worth doing, ranked by value per effort

1. **Commit the golden fixture and add a module-heavy golden case.** Under an hour, and every other refactor depends on it.
2. **Make the action and category consistency tests real, and finish the registry's easy derivations** (`DM_ACTIONS`, categories,
   and later the legacy `absent`). About 2 hours. It locks in the uncommitted registry and stops D4 drift.
3. **Record the per-call system prompt hash for context runs (A1) and write `run.json` provenance (C5/R17)**: command line,
   backend, git SHA plus dirty flag, Python version, `dry`, versions. About half a day, and it protects the value of every
   model run from now on.
4. **Previews for module rules (R6 again)**, with a test per module law function that writes state. About half a day. Without it,
   previews mislead voters in Life, conflict, jurisdiction and media worlds.
5. **Fix the Leaker goal under media2 (D3)** and add an event-type consistency test. 2–3 hours.
6. **Per-call record in `llm.call`**: attempts with usage, latency, `error_kind`, raw text on parse failure, `thinking_present`.
   Also keep abandoned rows in `abandoned_calls.jsonl`. About half a day. This is where real money goes missing on rate-limited
   runs.
7. **Unknown-key and enum validation against `base.yaml` plus module `DEFAULTS`** (C1-lite), including `agents` class names,
   `models.mix` and `turns`. About half a day.
8. **`scorer.score(until_round=…, out=…)` and a `validity.json`.** About half a day. It makes partially failed runs usable without
   hand scripts.
9. **`charter export` with `runs`, `agents` and `calls` tables first.** 1–2 days. Highest research value, but it needs items 3, 6
   and 8 to be worth exporting.
10. **R5 core streams behind `rng_version: 2`, then paired designs (C4).** 1–2 days. This is what makes "same world, different
    model" studies possible.
11. Lower priority:
    - checkpoint Python-version guard (R13), about 30 minutes;
    - `decisive_set` caching (R14), only if grand35 is slow;
    - the arrival `on_arrival` hook (R8);
    - freezing archive inputs (A8);
    - a structured `action_error` in place of regexes (R16);
    - deleting the stale re-route note (R18).

## 5. Recommendations that were wrong or have been overtaken

- **The full `ActionSpec` with `handler`, `doc` and `classes` (section 1.3) has been overtaken by a better split.** The actual
  registry chose capability requirements (`needs`/`when`) over class lists, which fits multi-class agents and roles. Class lists
  would already be wrong today (a Spy, Scholar or Maker is a role, not a class). Keep handlers in `actions.py` and docs in the
  prompt modules. Have the registry own *availability, category and layout* only.
- **The proposed single ordered `FEATURES` list for the lifecycle is too simple.** `end_round` now has an explicit multi-step
  order that interleaves kernel work with modules: attacks, then camp reveal, ballots and veto, `on_round_end` hooks,
  jurisdictions, regrowth, the camp world update, life, cases, credit, snapshot, and the media gazette. One ordered loop would need
  named phases (`before_ballots`, `after_hooks`, …) or it will reorder behaviour. Do 4.4 only with phases, or leave the explicit
  calls and just test their order.
- **"No feature may keep state outside `k.w`" was right, and it has held.** The only module-level mutables are registries and a
  shingle cache. It does not need more machinery.
- **Rec. 1 has been overtaken.** It is effectively done. What remains of it is the *recurrence* problem (R6, D3, D4), which is an
  argument for consistency tests rather than for more one-off fixes.
- **The golden tests as specified (byte hashes of `events.jsonl`, `snapshots.json` and `instance.json`) are too brittle for this
  repo's pace.** Commits re-record them routinely ("goldens re-recorded"), and every archive or prompt edit changes
  `instance.json`. Keep them, but split each case into "world" (events and snapshots) and "instance" hashes, and accept that they
  guard refactors, not feature work.
- **The appendix's touchpoint counts** are obsolete as numbers. The diagnosis (the same shared files edited per feature) still
  stands.
