# Review 01: the core engine and the feature-module system

*7 Oct 2026. Read-only review of the working tree, including the uncommitted `action_registry` wiring. Builds on
`charter/docs/architecture_review.md` (4 Oct, "AR-1" below). Line numbers are for the current working tree.*

## 1. Verdict

The owner is **half right**. The code is not much bigger than it needs to be. About 25k lines are mostly real feature logic plus
agent-facing prose, and a better structure would cut only about **1–2% of lines (roughly 300–500)**. The problem is not size. It is
that **the integration layer has no contract**. Every feature wires itself into 6–9 shared files by hand-placed calls, and the
parallel lists those calls feed have already drifted (verified bugs below).

Grades:
- Module internals: **B**. Each module keeps its state in `k.w`, has its own RNG streams and is off by default.
- Integration layer: **C**. There is no declared contract, hook names are inconsistent, and the same facts are kept in several
  places.

`camptypes/` and the new `action_registry.py` show the fix is already understood. It needs to be finished, not redesigned. **A
rewrite is not justified.** About eight small, behaviour-preserving steps get most of the value. One caveat: today the golden test
protects almost none of the code this would touch (§5, step 0).

On AR-1: I agree with its diagnosis and with its `ActionSpec`/`Feature` direction. It was written before conflict, media2,
jurisdictions, life, mortality, roles, scholars, context and typed camps existed (its touchpoint appendix lists none of them). Since
then the convention it described has roughly doubled in reach. AR-1 also missed four things:
- the golden test has no fixture and covers no new module;
- the consistency test that guards categories is vacuous;
- jurisdictions is a change to kernel semantics, not a plug-in;
- the modules have back-edge imports into `actions`.

## 2. How it works today

**Plug-in mechanism: none. Each feature calls into shared files at marked points.** `charter/docs/parallel_build_contracts.md:18-28`
made this the rule ("keep additions small and clearly marked, e.g. `# conflict:`"). The de facto hook set, as each feature
spells it:

| Hook | Called from | Spellings in use |
|---|---|---|
| state init | `Kernel.__init__` kernel.py:91-112 (9 explicit calls, `life` behind an inline `if`) | `install`, `init_state` |
| round start | `Kernel.start_round` kernel.py:977-999 (P, O, CT, H, CF, MD, interleaved with core steps) | `start_round`, `on_round_start` |
| round end | `Kernel.end_round` kernel.py:1001-1022 (CF, CT×2, J, life, CR, MD) | `end_round`, `end_of_round`, `resolve_attacks`, `world_update`, `compile_official` |
| law API | `api_for` kernel.py:523-556 (10 `**X.law_api(k, lid)` spreads, one via `__import__`) | `law_api` |
| snapshot | kernel.py:1137-1148 | `snapshot_fields`, `snapshot` (credit) |
| state view | `agents.state_view` agents.py:534-548 | `state_lines` |
| prompt text | `agents.system_prompt` agents.py:364-376, `context.core_prompt` context.py:913 | `prompt_section`, `rules_text` |
| availability | agents.py:333-358 + `absent_actions` in 4 modules; `action_registry.needs/when` | two independent systems |
| feed | `agents.render_event` if-chain agents.py:466-485 | `render(k,e,tag)`, `render(e,tag)`, `render_event(e,tag)`, `render_event(k,e,tag,viewer)` |
| manual | `manual.sections` hard-coded sections; `composition.manual_section` decorator (conflict, media, life); `context.KNOWN_MODULES` + `manual_sections` | 3 mechanisms; the third has **no providers** (dead loop over 9 imports, context.py:473-486) |
| truth | `runner._truth` runner.py:479-490 | `truth(k)`, `truth(k, inst)` |
| on/off | inline `(sp.get(x) or {}).get("enabled")` in 13 files; helpers `enabled`, `enabled_spec`, `enabled_inst`, `active`, `on`, `typed*`, `need`, `_need_on` | 10 helper names; `projects` defaults on, every other module defaults off |

**Actions.** `act()` dispatches with `globals()[f"_{name}"]` (actions.py:153). 46 of the 105 `_x` functions in actions.py are pure
trampolines, about 200 lines: `return CF.act_fortify(k, aid, qty, unlock)` and similar, sometimes with a `MD.need(k)` first
(actions.py:868-1217). An action is declared in up to six places:
1. `actions.ACTIONS` (or a module `ACTIONS` concatenated in at actions.py:20-31);
2. the `_name` trampoline;
3. `agents.ACTION_DOC` (or a module `ACTION_DOC` merged in at agents.py:112-113);
4. `action_registry.register`;
5. `scorer.CATEGORIES` (or `MD.CATEGORIES`, scorer.py:25-41);
6. the legacy `absent` logic (agents.py:333-358 or a module `absent_actions`).

Evidence: `fortify` appears in 5 files and `contribute` in 4. Adding a module like conflict touched kernel (5 places), actions,
agents (5 places), action_registry, scorer, runner (6 calls) and composition: **8 shared files**. A new action touches **5–6 files**.

**Dependencies.** There are 250 function-level `from charter import …` statements; context.py has 33, life.py 27 and actions.py 24.
The core imports every feature at module level, and the features import back into the core:
- `conflict`, `media`, `hidden` and `scholars` import `actions` for `ActionError` and the private `_dm_check`/`_deliver`
  (conflict.py:92, 624; hidden.py:455);
- `media` runs a whole model-call phase (`editorial_turns`, media.py:636) and imports `actions`/`agents`/`kernel`;
- `life` and `events` import `generator` to create agents.

These local imports are how the codebase avoids import cycles.

**World-state mutation.** The state discipline is good: each module owns a `k.w[key]`, and checkpoints and dry runs work for free.
The kernel's own invariants are another matter:
- Runtime rights changes bypass `grant`/`revoke` (which enforce `ENTRENCHED`/`NEVER` and log a `rights` event):
  - mortality.py:355 and 375 (board seats);
  - projects.py:366 and 376;
  - events.py:496 and 500;
  - roles.py:196;
  - hidden.py:568.
- Modules call the private `k._add` 36 times (conflict alone 11), skipping `move`'s logging.
- `regimes.py:38-40` re-declares `CLASSES`/`ENTRENCHED`/`FIXER_NEVER` from kernel.py:34-39.

**Jurisdictions are not a feature module.** The kernel branches on them in `_add`, `price`, `log` (visibility), `enact`, `hooks`
(J replaces hook dispatch entirely, kernel.py:622-623), `decide`, `passed` and `api_for` (`J.scope_api` wraps the whole law API). In
actions it branches in `_harvest`, `_send`, `_deposit`, `_redeem`, `_propose`, `_patch`, `_invoke` and `_accuse` (22 call sites).
This is an alternative polity model threaded through the core. A lifecycle registry will not absorb it.

**Two prompt paths, both live.** `agents.system_prompt`/`turn_prompt` is the legacy path, used by E0–E7, base, every pilot and the
golden tests. `context.core_prompt`/`turn_prompt` (society, explore15, grand35) is selected at agents.py:327 and 555. The WIP moved
the context path onto `action_registry` and deleted about 260 lines of parallel tables (`EDGE_RIGHTS`, `CORE_GROUPS`, `NICHE`,
`PRE_ARGS`, `usable`, `purposes.py`). That is a real gain. The legacy path still has its own `absent` rules and is the only consumer
of `absent_actions`.

## 3. Problems, ranked by cost

1. **The safety net is weaker than it looks. Fix this first.**
   - `tests/fixtures/charter_golden.json` does not exist and was never committed, so `test_golden_dry_run` cannot pass as checked
     out. The fingerprints have to be generated locally, which means a refactor is compared against whatever the tree held that
     day.
   - The five golden cases (E2, E4, E6, E7, E4+observer) enable **none** of conflict, media2, jurisdictions, life, mortality,
     roles, scholars, context or typed camps (none of them is in base.yaml).
   - System prompts and manuals are not fingerprinted at all, and `ScriptedPolicy` ignores prompts.
   - `test_every_action_has_a_doc_and_an_activity_category` is vacuous: `scorer.category()` falls back to `"talk"` for unknown
     names, so the test always passes.
2. **Parallel lists have drifted. Verified:**
   - `fund`, `set_charter`, `read_law` and `recent` are uncategorised, so they count as "talk" in `activity_mix`. This is the
     same bug AR-1 reported, back again in new modules.
   - The `RIGHT_DOC` table (manual.py:11) lacks `maker`, `scholar` and `impersonate`. On society seed 1, the "Your rights" manual
     section of the Maker, the Scholar and the Spy each says "`<right>`: a right created by law".
   - `media2.placements: false` and `polls: false` hide `buy_placement`, `run_placement` and `poll` on the legacy path
     (media.py:1025-1028). The registry lists them anyway (action_registry.py:237-248), so on the context path they are offered
     and then refused at run time.
3. **The per-action shotgun edit.** Five or six files per action, plus about 200 lines of trampolines. Every merge conflicts in
   `ACTIONS`, `ACTION_DOC`, `CATEGORIES` and the `absent` set.
4. **Lifecycle wiring is in core code.** Every feature edits `Kernel.__init__`, `start_round`, `end_round`, `api_for`, `snapshot`,
   `agents.state_view`, `render_event` and `runner._truth`. The step order is meaningful (attacks → sealed camps → ballots → hooks
   → jurisdictions → regrow → world update → life → cases → credit → snapshot), but it is only written down as call order plus
   comments.
5. **Back-edge imports.** `ActionError` and the messaging core live in actions.py, so features import the dispatcher. That forces
   local imports, and import-order bugs then show up only at run time.
6. **Two availability systems and two prompt paths.** Each new module has to teach both of them. `hidden.undocumented_actions` is
   applied in both.
7. **Rights are scattered:**
   - `KERNEL_RIGHTS`, `ENTRENCHED` (twice), `NEVER`/`FIXER_NEVER` and `SECRET_RIGHTS`/`RENAMED_RIGHTS` in the kernel and regimes;
   - `RIGHT_DOC` in manual.py;
   - `LEVERAGE_CLASS`/`LEVERAGE_ROLE` in context.py;
   - roles appends three rights to `k.w["rights"]` itself;
   - the registry's `edge`;
   - direct mutation in 7 modules.
8. **Dead or half-built mechanisms:**
   - `context.KNOWN_MODULES`/`_module_sections` (no provider);
   - `context.grouped_actions` (no caller);
   - `composition.core_section` (only a test uses it);
   - `action_registry.UNIVERSAL_RIGHTS = ()`.
9. **`runner.run` is one 330-line function** with six closures rebuilt every round (runner.py:114-443). It is ugly but contained,
   and less urgent than items 1–6.

**Assessment of `action_registry.py`.**
- Good:
  - one declarative row per action;
  - layout, edge and manual sections generated, not hand-kept;
  - readable in one screen;
  - it removed seven parallel tables.
- Weak:
  - It covers only the *prompt* side. Dispatch, doc, category and DM-ness live elsewhere, so it is a sixth place to edit, not a
    replacement for the other five.
  - Its `when` predicates re-implement checks the handlers already make (comment at line 180) by reading other modules' private
    `k.w` keys, through 8 local imports.
  - The `mod:` mini-language hides special cases in `_mod` (projects default-on, `typed`, `leases`, `shared_archive`).

The pattern should extend, but only once each row is the *whole* truth about an action. It should also extend to rights and to the
feature lifecycle, as ordered tables.

## 4. Proposed structure

The principle: **declare once, in an ordered table, and keep behaviour in the owning module.** No plugin framework, no event bus,
no package move.

**4.1 Complete the action row** (in `action_registry.py`, which stays the single, ordered table that sets prompt order):

```python
@dataclass(frozen=True)
class Act:
    name: str; purpose: str; section: str
    handler: str                  # "conflict:act_fortify": resolved lazily, so no import cycle
    doc: str                      # today's ACTION_DOC line (manual + legacy prompt)
    category: Literal["productive", "economic", "political", "talk"]
    core: bool = False; pre: bool = False; msg: bool = False   # msg replaces DM_ACTIONS
    needs: tuple = (); when: Callable | None = None; args: str = ""; edge: tuple = ()
    aliases: dict = field(default_factory=dict)              # today's _ALIASES entry
    legacy: bool = True           # listed by the legacy system prompt (until that path is retired)

R("fortify", "turn stone into a fort: defence", "FORCE", core=True, needs=("mod:conflict",),
  handler="conflict:act_fortify", category="economic", doc="fortify {qty, unlock?}: ...")
```

- `act()` becomes: look up the row, normalise arguments, check departure, call `resolve(row.handler)(k, aid, **args)`. The 46
  trampolines go.
- `ACTIONS`, `DM_ACTIONS`, `ACTION_DOC`, `CATEGORIES` and every `absent_actions` become derived views.
- `when` predicates call public `can_*` helpers that the handler also uses (`MD.is_editor`, `P.open_projects`), never raw
  `k.w[...]`.
- `mod:<key>` resolves through the feature table below, which removes the special cases in `_mod`.

**4.2 A rights table**, with about 20 rows, in `charter/rights.py`:

```python
@dataclass(frozen=True)
class Right:
    name: str; doc: str
    entrenched: bool = False        # veto, patch, archive
    never_for: tuple = ()           # classes that may never hold it
    secret: bool = False            # impersonate: never in public previews
    kernel: bool = True             # in w["rights"] from round 0 (roles' scholar/maker/impersonate: registered by roles)
    renamed_from: str | None = None
```

This replaces `KERNEL_RIGHTS`, both `ENTRENCHED`s, `NEVER`/`FIXER_NEVER`, `SECRET_RIGHTS`, `RENAMED_RIGHTS` and `RIGHT_DOC`, which
fixes the manual bug. Add one kernel method, `k.set_rights(aid, rights, why)`, that logs. The seven direct mutations go through it.
Seat succession, which really does change class, gets an explicit `k.seat_board(aid, from_aid)`.

**4.3 A feature table with standard hook names and explicit phases** (`charter/features.py`). This builds on AR-1's `Feature`, made
lighter: the record holds *data*, the module holds *functions* under fixed names, and the core runs **named phases** whose order is
one reviewed list.

```python
@dataclass(frozen=True)
class Feature:
    name: str                 # "conflict"
    module: str               # "charter.conflict"
    spec_key: str             # "conflict"
    default_on: bool = False  # projects: True
    def on(self, spec) -> bool: ...          # the ONE enabled check (replaces 10 helper names + 13 inline checks)

FEATURES = [Feature("credit", ...), Feature("projects", ..., default_on=True), Feature("outside", ...), Feature("hidden", ...),
            Feature("context", ...), Feature("roles", ...), Feature("camps", "charter.camptypes.framework", "camps"),
            Feature("life", ...), Feature("conflict", ...), Feature("jurisdictions", ...), Feature("media", "charter.media", "media2")]

# Optional module functions, fixed names and signatures (a test checks every module's signatures):
#   install(k)  law_api(k, lid) -> dict  snapshot_fields(k) -> dict  state_lines(k, aid) -> list  truth(k, inst) -> dict
#   render_event(k, e, tag, viewer) -> str|None  EVENT_TYPES  prompt_section(inst, a) -> str  rules_text(inst) -> str
#   phase functions, named in the phase table:

START_ROUND = [("core", "reset_counters"), ("core", "settle_loans"), ("projects", "start_round"), ("outside", "start_round"),
               ("projects", "maybe_spawn"), ("core", "pending_patches"), ("core", "drift"), ("camps", "start_round"),
               ("core", "law_hooks:on_round_start"), ("hidden", "on_round_start"), ("conflict", "start_round"), ("media", "start_round")]
END_ROUND = [("conflict", "resolve_attacks"), ("camps", "end_of_round"), ("core", "close_ballots"), ("core", "veto_queue"),
             ("core", "law_hooks:on_round_end"), ("jurisdictions", "end_round"), ("core", "regrow"), ("camps", "world_update"),
             ("life", "end_of_round"), ("core", "expire_cases"), ("credit", "end_round"), ("core", "snapshot"), ("media|core", "record")]
```

`Kernel.start_round` and `end_round` become loops over these lists that skip features that are off. A new feature adds a module,
one `FEATURES` row and its phase slots. The `api_for` spreads, `snapshot` spreads, `state_view`, the `render_event` tail and
`runner._truth` become loops in `FEATURES` order. **That order must reproduce today's dict-merge order**, because snapshot key order
reaches `snapshots.json` bytes and law-API key collisions resolve last-wins.

**4.4 One manual mechanism.** Keep `composition.manual_section` and move "Credit and loans" and "Projects and tribute"
(manual.py:132-144) into credit.py and projects.py. Delete `KNOWN_MODULES`/`_module_sections`.

**4.5 Shared leaf modules.**
- `charter/errors.py` holds `ActionError` (re-exported from actions for compatibility).
- `charter/messaging.py` holds `dm_check`, `deliver` and `forge_message`, now public. This also delivers AR-1's single forge core.

Both remove the feature → actions back-edges.

**4.6 Jurisdictions: leave alone, or give it a seam.** If more polity variants are expected, the honest abstraction is a
`Polity` object on the kernel with these methods:
- `reserve_for(owner)`
- `hooks(hook, *args)`
- `decide(lid)`
- `passed(lid)`
- `scope_api(lid, api)`
- `vis(data, vis)`

The default would be a single-polity implementation, with `jurisdictions.Polity` as the alternative. That turns about 20 jurisdiction
branches in kernel.py and actions.py (`J.enabled`, `"jur" in w`, `J.pool`/`home_reserve`) into one dispatch point. If no other variants are expected, the branches are tolerable. They are marked and
the module is cohesive.

**Target layout.** Mostly the current one: `kernel.py` (core, phases), `features.py` (table), `rights.py`, `action_registry.py`
(full rows), `errors.py`, `messaging.py`, with feature modules unchanged in place. I agree with AR-1 not to move files into a
`features/` package: it brings `git blame` and import churn and no structural gain.

**What shrinks** (estimated by counting the lines that would be deleted, offset by the lines added):

| Item | − lines | + lines |
|---|---|---|
| Action trampolines (counted with `ast`) | ~200 | 15 (resolver) |
| `ACTIONS` assembly, `DM_ACTIONS`, `ACTION_DOC` merges, `CATEGORIES` (scorer + media) | ~45 | 0 (fields on rows) |
| Legacy `absent` logic + 4× `absent_actions` | ~70 | ~10 (`legacy` flag + order list) |
| Dead: `KNOWN_MODULES` loop, `grouped_actions`, `_optional`, `UNIVERSAL_RIGHTS` | ~40 | 0 |
| Kernel init/round/api/snapshot explicit calls → phase loops | ~45 | ~60 (features.py + loops) |
| Rights constants ×3 files, `RIGHT_DOC` | ~35 | ~40 (rights.py) |
| Enabled-check helpers and inline checks | ~40 | ~10 |
| **Net** | | **≈ −300** |

`ACTION_DOC` text moves rather than disappears. Deleting the legacy prompt path once E0–E7 are retired would remove another ~150
lines. **The payoff is in edit locality:** a new action goes from 5–6 files to 2 (module + one registry row), and a new feature from
about 8 shared files to 2–3. The drift class of bug in §3.2 becomes a failing test.

## 5. Migration plan

Every step is one PR, keeps the tests green and has a stated golden effect.

0. **Safety net (blocking).**
   - Commit `tests/fixtures/charter_golden.json`, generated on the current tree. The WIP touches prompts only and
     `ScriptedPolicy` ignores prompts, so the hashes are unaffected.
   - Add golden cases for `society` (3 rounds, simultaneous; this turns on every module) and for `conflict_pilot`,
     `jurisdictions_pilot`, `life_pilot`, `media2_pilot` and `camps_pilot`, 3 rounds each.
   - Add `test_prompt_fingerprints`: hash every agent's system prompt, manual (all sections) and round-1 turn prompt for E4 and
     society at a fixed seed.
   - Make the category test strict (`name in ⋃CATEGORIES`).

   Golden effect: new baselines only.
1. **Fix the verified drift.**
   - Categories for the 4 actions (score outputs change; goldens do not).
   - `RIGHT_DOC` entries (prompt fingerprints change: the reason to update is the bug).
   - placements and polls needs (prompt fingerprints change for media worlds).
   - Delete dead code.
2. **`errors.py` and `messaging.py`.** Re-export `ActionError` from actions so nothing breaks. Goldens unchanged.
3. **Complete `Act`** (`handler`, `doc`, `category`, `aliases`; `msg` replaces `DM_ACTIONS`).
   - Derive `ACTIONS`, `ACTION_DOC` and `CATEGORIES`, and delete the trampolines.
   - Keep the "unknown action" error's list in the old `ACTIONS` order (it reaches logged results).
   - Goldens unchanged.
4. **Legacy prompt from the registry.** Replace the `absent` block with `AR.available(inst, None, a)` filtered by `legacy`, in a
   frozen `LEGACY_ORDER`. Prompt fingerprints for E-presets must be byte-identical; fix the rows until they are. Then delete the
   `absent_actions` functions.
5. **`rights.py` + `k.set_rights`.** Migrate the 7 direct mutators one at a time. Goldens change only where the new `rights` log
   events appear, so either keep the logging opt-in or accept a one-time update.
6. **`features.py` + phase tables**, one hook family per PR:
   - init;
   - start_round;
   - end_round;
   - law_api;
   - snapshot;
   - state_lines;
   - render_event;
   - truth.

   Rename the odd spellings first, with aliases. Goldens must stay identical. A snapshot key-order change is the most likely
   failure, so loop in today's order.
7. **One manual mechanism.** Prompt fingerprints identical.
8. **Optional.** Split `runner.run` into a `Round` object with methods in place of the closures. A `Polity` seam if a second polity
   model is planned. A law-function registry (AR-1 4.2) only if the consistency test that now guards `api == API_GROUPS ⊆
   lawdocs` starts to be a burden.

Steps 2–4 are independent of 5–7. Step 0 must come first. Without the new golden cases, steps 3–7 are unprotected for exactly the
modules they touch.

## 6. What NOT to change

- **The kernel's invariants and the core law API in `api_for`.** They are the experimental contract. Move feature spreads into a
  loop; leave the core functions inline.
- **Plain-dict world state in `k.w`.** Snapshotting, checkpointing, dry-run rollback and resume all depend on it. Do not introduce
  state classes or objects that hold state.
- **Per-feature RNG substreams and off-by-default flags.** These are why the goldens survive feature additions.
- **The `camptypes/` package.** It already has an explicit interface, a registry, one file per type and auto-discovery. It is the
  model for the rest, not a target.
- **`lawlang`, `regimes`, `library`, `goals` and the event-type registry in `events.py`.** They are content catalogues that are
  already table-driven.
- **No `features/` directory move, no decorator-based self-registration for anything order-sensitive** (prompt order, phase
  order), and no event bus or dependency injection. Explicit ordered tables are easier to review and keep the goldens
  deterministic.
- **No rewrite.** The expected size gain is about 1–2%. The value is in locality and in drift turning into test failures, and
  incremental steps get all of it.
