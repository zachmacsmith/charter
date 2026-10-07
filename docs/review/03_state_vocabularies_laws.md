# Review 03: world state, cross-cutting vocabularies, the law API

*7 Oct 2026. Read-only. Line numbers refer to the working tree, which includes the uncommitted `action_registry` wiring. Checks
were run in-process on `generator.generate(...)` + `Kernel(...)`; no simulations were run. This builds on
`charter/docs/architecture_review.md` (4 Oct; "AR" below), recommendations 3 and 4, §1.2 and §3.5, and on
`design_laws_rights_capabilities.md` §3. I don't repeat them. I say where I agree, where I disagree and what they missed.*

## 1. Verdict: C+

The owner's suspicion is **right about vocabularies and wrong about state**. World state is one plain dict, `k.w`, with 55
top-level keys, mostly the same keys in every world. It is touched about 1,000 times across 31 files. Its schema is written down
nowhere. It is built in 12 places: the `Kernel.__init__` literal, 10 `install`/`init_state` calls, and more than 20 lazy
`setdefault`s. Its checkpoint is stamped `"version": 1` (runner.py:453), and that number has never been raised. Even so, the
dict is not the problem. Checkpoints, dry-run rollback and JSON snapshots all work because it is plain data. Converting it to
dataclasses would touch every access site and pay back little.

The real cost is in the **names**: the rights, event types, action names, law functions and module toggles that every module
compares as bare strings. None of these has a single owner. Each is listed again by hand in 4 to 13 places, and the copies have
drifted in ways that are bugs today, not just untidiness. I found these:

- The Spy's secret right leaks through the law API.
- The Maker's right and the Maker's role disagree.
- The Spy, Maker and Scholar manuals call their own rights "a right created by law".
- Three agent-affecting law functions ignore jurisdiction scope.
- Four actions are scored in the wrong category, and a consistency test that cannot fail hides it.

`action_registry.py` shows the right pattern, but it is a fifth copy of the action vocabulary, not the only one. Five small,
interlocking registries (modules, rights, actions, events, law functions), each fail-closed and checked by one test file, would
remove this class of bug. They are worth doing. They will not make the code much shorter (a few hundred lines saved, not
thousands), and the owner should not expect them to.

## 2. Inventory

### 2.1 World state (`k.w`)
- **Shape.** Every value is a plain dict, list or scalar. The whole package has one dataclass (`action_registry.Act`) and no
  TypedDicts. There are 266 `k.log` call sites and about 1,018 `k.w[...]`/`w[...]` accesses. The heaviest are kernel 179,
  jurisdictions 95, media 74, actions 73, conflict 61, context 55 and events 50.
- **Shared keys.** `agents` is read directly in 25 files, `unit` in 17, `camps` in 14, `currencies` in 12, `laws` in 10 and
  `roles` in 9.
- **Optional sections.** These are read defensively with `k.w.get(...) or {}`: `roles` 11×, `mortality`, `life`, `leases`,
  `hidden_caps` and `files` 5× each. Feature sections are present only when the feature is on, so every reader repeats the
  absence check.
- **Rights are mutated outside the kernel.** Writes to `rights` happen in 10 modules without going through `grant`/`revoke`:
  `camptypes/leases.py:123-151`, `framework.py:165-189`, `projects.py:366-376`, `events.py:393,496-500`, `hidden.py:145,568`,
  `mortality.py:355,375` and `roles.py:152,196`. Some keep the list sorted and some `append`, so the sorted invariant `grant`
  maintains is not universal. Only `grant`/`revoke` emit the `rights` event.
- **Migration is ad hoc.** `kernel._migrate_rights` (kernel.py:1219) and `__main__.py:84-87` both apply `RENAMED_RIGHTS`.
  Neither touches `w["actions"][*]["right"]` or law source code, so a restored law calling `has(x, "forge")` silently gets
  `False`.

### 2.2 Rights: about 15 definition sites, no owner
| Where | What |
|---|---|
| kernel.py:34-38 | `ENTRENCHED`, `KERNEL_RIGHTS` (14), `NEVER` |
| kernel.py:690 | `Kernel.SECRET_RIGHTS = ("impersonate",)`, used **only** by `view()` (the preview diff) |
| kernel.py:1216 | `RENAMED_RIGHTS`; also re-applied in `__main__.py:84` |
| generator.py:36 | `CLASS_RIGHTS` (also used by `events.py:330-335` for arrivals) |
| roles.py:55-56,150,196,299 | `RIGHTS` (role→right), `NO_BOARD`, the literal `"impersonate" if r == "spy"` twice, the literal `{"scholar","maker","impersonate"}` added to the catalogue |
| hidden.py:185 | `secret_right()`: secret **harvest** rights only |
| manual.py:11 | `RIGHT_DOC` (14 entries; no `impersonate`, `maker`, `scholar`) |
| goals.py:376 | the Capture goal's eligible rights (`press, dm_rules, vote, propose, sandbox`) |
| goals.py:1035-1036 | `OFFICE_RIGHTS` (includes `decree` and `elector`, which only *library laws* create: regimes.py:54, library.py:376), `BASE_RIGHTS` |
| action_registry.py | `needs=("right:…")`, `edge=`, `UNIVERSAL_RIGHTS` |
| context.py:750-772 | `LEVERAGE_CLASS`/`LEVERAGE_ROLE`: prose restating who holds what |
| agents.py `API_DOC` | "Rights nobody holds at the start include anon … see_hidden" |
| kernel.py:526 | `rights_of` law API, which filters secret harvest camps only |

**Drift, verified:**
1. **The Spy is exposed to any law.** I built a world with `society` + `roles.enabled=true, observer.mode=member`. In it,
   `api["holders"]("impersonate")` returns `['Rakel']` and `api["rights_of"]("Rakel")` includes `impersonate`. So a law
   `gazette(str(holders("impersonate")))` unmasks the secret role. `SECRET_RIGHTS` guards the preview but not the runtime API;
   `hidden.secret_right` guards a different notion of secrecy.
2. **Maker: the role and the right are two sources of truth.** The registry gates `create_agent`/`copy_agent` on
   `right:maker` (action_registry.py:213,229), and `_k_maker_exists` (:177) checks `"maker" in r`. Execution checks
   `RO.has_role(k, aid, "maker")` (life.py:696,705). A law that grants or revokes `maker` changes the prompt but not the
   capability, or the reverse.
3. **Wrong manual text.** The manual tells the Spy "impersonate: a right created by law", and tells the Maker and the Scholar
   the same about theirs (reproduced with `manual.sections`; the fallback is at manual.py:92).
4. **Role rights inflate a score.** `goals._offices` counts `impersonate`, `maker`, `scholar` and `anon` as *offices*, because
   they are in neither list.

### 2.3 Classes: about 9 sites
`kernel.CLASSES` (:39) and `regimes.CLASSES` (:38) are identical copies. The others are `hidden.HOLDER_CLASSES`/`SPAWN_CLASSES`
(:37-38), `life.CHILD_CLASSES` (:57), `events.OFFICIALS` and `projects.OFFICIALS` (identical), `generator.CLASS_RIGHTS`,
`goals.CLASS_TILT`, `context.LEVERAGE_CLASS`, the article dictionary in `context._class_line` (:792), and the class→actions
dictionary in `agents.system_prompt` (:360). The class set is stable (six names), so drift is low. A `Klass` registry is cheap
but has the lowest priority.

### 2.4 Event types: 205 literal types, about 13 hand lists
**The post family.** Each list below restates "public posts", each slightly differently:

| List | Where | Types |
|---|---|---|
| `kernel.POSTABLE` | kernel.py:37 | 6, with `channel_post` |
| law API `posts()` | kernel.py:510 | 5, inline, without `channel_post` |
| `context.BOARD_TYPES` | context.py:68 | 5 + `gazette` |
| `context.RECENT_KINDS` | context.py:395 | posts 5; "all" adds `edition`, `gazette`, `dm`, but no `channel_post` |
| `context.POSTS` | context.py:976 | 6 |
| `goals.PUBLIC` | goals.py:734 | 5 |
| `hidden.FORGEABLE` | hidden.py:55 | 5 + `gazette` |
| `hidden.VEILABLE` | hidden.py:56 | 5 |
| `media.QUOTABLE` | media.py:95 | 8 |
| inline list | media.py:1341 | 4 |
| `report.MESSAGE_TYPES` | report.py:332 | 16 |
| `observer.MESSAGE_TYPES` | observer.py:55 | 7 |

**Other classifications:** `context.OFFICIAL` (:973, feed priority), per-module `EVENT_TYPES` tuples (H, P, O, life), and the
if-chains in `report.py` (40 type dispatches), `goals.py` (23), `media.py` (30), `agents.render_event` (26) and `credit.py` (19).

**Drift.** AR noted `posts()` against `POSTABLE` (AR §1.2). It is still there, and the list has grown by three since. Two things
AR did not note:
- **Unregistered types fail open.** `context._priority` (:981-992) gives any type that is not in `POSTS`/`OFFICIAL` priority 1,
  the highest, which is never dropped first. So every new module's public events (`jur_*`, `lease_*`, `outlet_*`, `edition`,
  `rights`, `sanction`) outrank messages to the agent by default. Nobody chose that.
- **Legacy names have no home.** `forgery_truth` survives in `report.py:216` and `hidden.py:604` as an old-run alias. That is
  the event counterpart of `RENAMED_RIGHTS`, with no declared place to live.

**What is good.** All 266 `log` calls pass `vis=` explicitly. Only `world_event` is logged with more than one visibility class,
and that is intentional. Every `*_truth` event is `vis="monitor"`. This discipline is a real safety property; see §6.

### 2.5 Actions: 5 parallel definitions
The five are:
- `actions.ACTIONS` (actions.py:20-32, assembled from 5 modules), plus `DM_ACTIONS` (:33);
- `action_registry.REG` (with `msg=True`, which duplicates `DM_ACTIONS`);
- `agents.ACTION_DOC` (+ `J.`/`MD.ACTION_DOC`);
- `scorer.CATEGORIES` (:25-42, + `MD.CATEGORIES`);
- `actions._ALIASES`/`_IGNORED`.

There are also two availability systems: `action_registry.needs/when` (the context-on prompt) and the hand-written `absent` set in
`agents.system_prompt` (:332-362, the legacy prompt).

**Drift.** `fund`, `set_charter`, `read_law` and `recent` have no category, so `scorer.category` falls back to "talk". That makes
jurisdiction funding and charter-setting count as talk. `test_every_action_has_a_doc_and_an_activity_category` cannot catch this,
because `category()` never returns anything outside the four categories.

### 2.6 Law functions: 117 names, 6 tables
The six tables:
- `Kernel.api_for` (about 50 inline closures) plus 10 module `law_api(k, lid)` dicts (no name collisions today; checked);
- `lawlang.API_GROUPS`, patched in place 9 times (lawlang.py:38-56);
- `lawdocs.E`/`ENTRIES`;
- `agents.API_DOC`;
- `jurisdictions.AGENT_ARGS`/`REFUSED`/`LEGACY_ONLY` (:77-83);
- in lawdocs alone, **four** different gating mechanisms: `MODULE_ENTRIES`, `OPTIONAL`, `_gated_off`, `REQUIRES`
  (lawdocs.py:212-243).

AR said "nothing checks `api ⊆ lawlang.API`". That is now fixed: `test_law_api_classification_and_docs_agree` checks equality.

**What is still unguarded: jurisdiction scoping.** `AGENT_ARGS` lists 8 functions written before the newer modules. Three
agent-targeting functions added since are not scoped: `oblige_guard(guard, agent)` (conflict.py:755),
`compel_subscription(agent, target)` (media.py:1232) and `lend_from_reserve(borrower, …)` (credit.py:476). A hidden
jurisdiction's law can therefore bind non-members (verified by code reading; this needs a world with jurisdictions on together
with conflict or media2). Separately, `lawdocs.REQUIRES["set_succession_public"]` (:243) re-implements `mortality.active`.

### 2.7 Spec keys and module toggles
- **Seven naming variants** for "is it on": `enabled(k)`, `enabled(spec)`, `enabled(x)` (context takes anything),
  `enabled_spec`, `enabled_inst`, `on(k)`, `active(spec)`.
- **Five names for the config:** `cfg`, `_cfg`, `config`, `cfg_of`, `DEFAULTS`.
- **More re-implementations.** `action_registry._mod` (:58-74) re-implements six of them as special cases. Its `projects`
  default `True` restates `projects.DEFAULTS`. `kernel.py:75` inlines `life.enabled`.
- **No single home for defaults.** Feature blocks `conflict`, `context`, `jurisdictions`, `life`, `media2`, `resources` and
  `roles` are **not in base.yaml at all**; their defaults exist only in module `DEFAULTS`. AR said defaults "live in two places
  for four features". It is now one place or the other, depending on the feature.

## 3. Problems ranked by cost × risk

1. **Secrecy is enforced per call site, not per right** (§2.2 items 1-3). This breaks the experiments' core premise (a secret
   Spy), it is silent, and the next secret role will repeat it. *High.*
2. **Law-function attributes are scattered** (§2.6): the class, docs, jurisdiction scope and module gate of a single function
   live in 4 to 6 tables. Only the class and docs are test-guarded, and scope has already drifted. *High.*
3. **Unknown names fail open**: priority 1 in the feed, "talk" in the scorer, "a right created by law" in the manual. Every new
   module inherits wrong defaults silently, and the tests are vacuous. *Medium-high; cheap to fix.*
4. **The action vocabulary is half-migrated** (§2.5): the registry exists, but `ACTIONS`, `DM_ACTIONS`, `ACTION_DOC`,
   `CATEGORIES`, `_ALIASES` and the legacy `absent` set still duplicate it. Two availability systems will diverge. *Medium.*
5. **The event-type lists** (§2.4): 13 lists, three of which are already inconsistent in user-visible ways. *Medium.*
6. **Module toggles** (§2.7): 7 predicate names and 4 lawdocs gating mechanisms. Mostly an edit-locality cost. *Medium-low.*
7. **The state schema is implicit and has no migration chain** (§2.1). Today it is only a resume and old-run risk. *Low-medium.*
8. **Duplicated class constants** (§2.3). *Low.*

## 4. Proposed registries and how they interlock

One file, `charter/vocab.py` (about 300 lines, no behaviour), holds five registries. Feature modules register into it at import
time, just as `action_registry` does. Every lookup **raises** on an unknown name. One test file walks all five and checks the
cross-references.

```python
# charter/vocab.py
@dataclass(frozen=True)
class Module:                     # a switchable feature
    key: str                      # spec block, e.g. "media2"
    enabled: Callable[[dict], bool]          # (spec) -> bool: THE predicate; every enabled_*/on/active wraps it
    defaults: dict = field(default_factory=dict)   # merged by cfg(); base.yaml checked against it in a test

@dataclass(frozen=True)
class Right:
    name: str                     # "impersonate"; families: "harvest:*"
    doc: str                      # manual line (replaces RIGHT_DOC)
    kind: Literal["office", "tool", "property", "role", "law"]   # goals._offices, Capture eligibility
    secret: bool | Callable = False          # hidden from law reads, previews, public rights events, others' manuals
    entrenched: bool = False      # ENTRENCHED
    never: tuple = ()             # classes that can never hold it (NEVER, roles.NO_BOARD)
    role: str | None = None       # carried by this role (roles.RIGHTS + the spy special case)
    aliases: tuple = ()           # old names: ("forge",) -> norm_right and checkpoint migration
    module: str | None = None

@dataclass(frozen=True)
class EventType:
    name: str
    module: str | None = None
    truth: bool = False           # must be logged with vis="monitor" (asserted), never rendered to agents
    post: bool = False            # a public post: POSTABLE / posts() / VEILABLE / goals.PUBLIC
    board: bool = False           # search_board (post + gazette)
    forgeable: bool = False       # quill / history rewriting
    quotable: bool = False        # media leaks/quotes
    message: bool = False         # report/observer MESSAGE_TYPES
    feed: Literal["event", "official", "post", "message", "silent"] = ...   # REQUIRED: context._priority
    aliases: tuple = ()           # "forgery_truth" for old runs

@dataclass(frozen=True)
class LawFn:                      # metadata only; behaviour stays in api_for/law_api closures
    name: str
    cls: Literal["read", "ordinary", "structural", "procedural"]   # -> API_GROUPS, STRUCTURAL_CALLS
    module: str | None            # gate: -> lawdocs OPTIONAL/REQUIRES/_gated_off/MODULE_ENTRIES
    agent_params: tuple = ()      # ((0, "agent"),): jurisdiction scoping is derived (AGENT_ARGS)
    refused: Any = False          # what an out-of-scope call returns (REFUSED)
    legacy_only: bool = False     # LEGACY_ONLY
    reads_rights: bool = False    # holders/has/rights_of: filtered by Right.secret
    # docs stay in lawdocs.E, keyed by name; the test asserts 1:1

# Act (action_registry) gains: category, doc (the ACTION_DOC line), emits=(event types), aliases (arg synonyms);
# "mod:x" resolves through MODULES[x].enabled; "right:r" must name a Right; msg=True replaces DM_ACTIONS.
```

**How they interlock** (each arrow is a check in `tests/test_charter_vocab.py`, or a derivation):
- **Action → Right.** `needs=("right:r",)` must be a registered `Right`. `create_agent` would need `role:maker` (a new
  requirement kind), resolved by `Right.role`, so the role-versus-right split can no longer happen.
- **Action → EventType.** `emits` must be a subset of `EVENTS`. A golden-run test asserts that every logged type is registered:
  `k.log` checks `kind in EVENTS` when `CHARTER_STRICT_VOCAB=1`, which the test suite sets.
- **Right.secret → law API.** `api_for` wraps the `reads_rights` functions once, filtering secret rights for every law.
  `Kernel.view`, the `rights` event visibility and `manual._rights` all use the same `is_secret(k, r)`.
  `hidden.secret_right` becomes the `harvest:*` family's secret predicate.
- **LawFn.agent_params → jurisdictions.** `scope_api` iterates `LAWFNS` instead of `AGENT_ARGS`. A test fails when a new
  `LawFn` has a parameter named `agent`, `aid`, `borrower`, `guard` or `target` but no `agent_params`. That would have caught
  all three gaps.
- **Module.** `Act.needs "mod:x"`, `LawFn.module`, `Right.module`, `EventType.module`, `agents.absent` and
  `library.GATED_CATEGORIES` all resolve through one `MODULES[x].enabled(spec)`.
- **Derived old names, kept as module constants** so call sites don't change:
  `POSTABLE = names(EVENTS, post=True)`, `ENTRENCHED = names(RIGHTS, entrenched=True)`,
  `scorer.CATEGORIES = group(REG, "category")`, `lawlang.API_GROUPS = group(LAWFNS, "cls")`.

On the coordinator's question of whether an event type should declare a *visibility default*: **no**. Visibility is per call,
and explicit `vis=` everywhere is the current safety net. The registry should only *assert* constraints: `truth ⇒ monitor`, and
a `post ⇒ public` or `channel:` visibility.

**State.** Do not type it; declare it. Add `STATE` as a list of `Section(key, owner_module, init, present_when)` in `vocab.py`,
where `present_when` is a `Module` key. Add `w["schema"] = N` and a `MIGRATIONS = {n: fn}` chain that runs in `restore_state`
and in `__main__`'s instance check. That chain replaces `_migrate_rights` and the rename hack, and is generated from
`Right.aliases`. Add an `assert set(k.w) <= declared` in the strict test mode. Add optional TypedDicts for `Agent`, `Law` and
`Event` as documentation only.

**Agreements and disagreements with AR §1.3.**
- I agree with the action, law-function and event registries, and with "derive the hand lists".
- I disagree with `LawFn.make`. Moving behaviour into the registry means rewriting about 120 closures. Metadata keyed by name,
  validated against `api_for`, gets about 90% of the benefit for about 10% of the churn.
- I am lukewarm on the 20-hook `Feature` lifecycle record. Lifecycle call sites are few, ordered and fail loudly as merge
  conflicts (the order in `Kernel.__init__` is load-bearing: "lets the roles module set up its state first", life.py:176).
  Vocabularies fail silently, so they come first.
- AR has no Right registry. Rights are where the silent bugs are, and `design_laws_rights_capabilities.md` §3.3's
  `rights_model` (right / capability / entrenched) belongs as a field on this registry, not as another spec table.

## 5. Migration plan
Each step keeps `tests/test_charter_golden.py` byte-identical unless it says "golden update", and runs
`tests/test_charter_consistency.py` and `tests/test_charter_prompts.py` (the latter covers prompt byte-identity).

1. **Make scoring fail closed.** Change `scorer.category` so tests raise on unknown names, then add `fund` and `set_charter`
   (political), `read_law` and `recent` (productive). `activity_mix` changes, but the golden files hash events and snapshots,
   not scores, so they should stay identical; confirm by running the golden test.
2. **`vocab.Module` plus the predicate wrappers.** The old `enabled_*`/`on`/`active` names call into it. `action_registry._mod`
   and the four lawdocs gates read it. Add a test that every `Module.defaults` key is either in base.yaml or listed as
   module-only.
3. **The `EventType` registry, with every current list re-derived** into its old constant name. Make each existing
   difference a deliberate flag. The `posts()` law API either keeps excluding `channel_post` (no-op) or includes it (golden
   update, recorded in the commit). Add strict-mode `k.log` checking. Make `feed=` required (a priority-1 default only where
   it is declared).
4. **The `Right` registry.** Derive `KERNEL_RIGHTS`, `ENTRENCHED`, `NEVER`, `SECRET_RIGHTS`, `RENAMED_RIGHTS`, `RIGHT_DOC`,
   `roles.RIGHTS` and the goals lists. Golden unchanged; the instance hashes don't include docs.
5. **Fix secrecy through `Right.secret`.** Covers the law API reads, `rights` events and the manual. This is a behaviour
   change only in roles-on worlds, which aren't in the golden cases. Add a regression test for `holders("impersonate") == []`.
6. **The Maker role-versus-right split.** Add the `role:` requirement kind, and decide whether `maker`/`scholar` should be
   rights at all. My recommendation: no. Role-carried capabilities are "entrenched" in the design doc's terms, and
   `create_right` should refuse their names.
7. **Fold `ACTION_DOC`, `CATEGORIES`, `DM_ACTIONS` and `_ALIASES` into `Act`.** Derive the legacy `absent` set from `needs`,
   or delete the context-off prompt path if it is no longer used for new runs. Prompt byte-identity test required.
8. **`LawFn` metadata.** Generate `API_GROUPS`, `AGENT_ARGS`, `REFUSED` and `LEGACY_ONLY`, and add the parameter-name
   scoping test. Fixes the three unscoped functions; golden unchanged, since no golden case has jurisdictions on.
9. **`STATE` sections, `w["schema"]` and the migration chain.** Make `_migrate_rights` migration 1→2, and keep the runner's
   `"version": 1` reader.

Steps 1 to 5 are one or two agent-days and carry most of the value. Steps 6 to 9 are optional and can each be done in isolation.

## 6. What NOT to change
- **`k.w` as plain JSON-able dicts.** No dataclasses or ORM for world state. Checkpointing, `_snapshot`/`_restore`, previews and
  JSON snapshots all depend on it, and 1,000 access sites would churn for documentation value only.
- **Explicit `vis=` on every `log` call.** Do not introduce registry defaults for visibility.
- **`lawlang`'s static classification by calls**, and laws as restricted Python. This design is good; only the table feeding
  it should be generated.
- **The per-module `law_api(k, lid)` closure dicts.** The convention is uniform and collision-free. Add metadata beside it, not
  instead of it.
- **Hand-written prose** (`ACTION_DOC` lines, `lawdocs` details, `LEVERAGE_*`). Co-locate it with the registry entries where
  that is cheap, but don't template it. The prompts are tuned text and byte-identity is tested.
- **The explicit, ordered `install` calls in `Kernel.__init__`.** A generic lifecycle loop adds indirection and hides an order
  that matters.
- **Do not build a `features/` package or a plugin framework.** AR agrees. A Klass registry is optional; the six class names have
  not drifted.
