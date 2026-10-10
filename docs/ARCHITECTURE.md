# Charter target architecture

*7 Oct 2026, written at `014a913` (main). This is the target for the overhaul that parallel agents implement. It consolidates
reviews 05 (goals), 06 (contracts, including the §9 addendum), 08 (feature contract) and 09 (law composition) with the owner's
decisions of 7 Oct, which override the reviews where they differ. Reviews 00-04 and 07 are inputs; their findings are cited, not
repeated. Section 10 lists the interfaces implementers must honour; section 11 is the work plan; section 12 lists open decisions,
each with a default so work can proceed.*

*Groundwork already in progress on separate branches (behaviour-preserving), which this document builds on. Where a merged
branch's names differ from the names used here, the merged names win and this document gets a follow-up edit:*

| Id | Branch | Delivers | Names assumed here |
|---|---|---|---|
| G1 | `feat/event-registry` | event-type registry | `charter/eventtypes.py`: `EventType`, `EVENTS`, `get(name)` (raises on unknown) |
| G2 | `feat/lawfn-table` | complete law-function table | `charter/lawapi.py`: `LawFn` rows for all ~117 functions with `cls` and `module`; `API_GROUPS` derived |
| G3 | `feat/cause-stack` | kernel cause stack | `Kernel.cause(kind, id, **meta)` context manager; events carry `cause` and `chain` |
| G4 | `feat/difftest` | differential test harness | runs a preset under two code versions and compares normalised `events.jsonl` and snapshots |
| G5 | `feat/history` | History object for scoring | `charter/history.py`: `History.load(run_dir, until=None)` |
| G6 | `feat/replay` | replay and per-round checkpoints | `checkpoints/rNNNN.pkl` + index of append-only offsets; `Replay` policy keyed by call |

---

## 1. Principles

1. **The kernel is physics.** It owns state, accounts, conservation, time, life and death, causes, visibility, randomness and the
   legal machinery (dispatch, gas, procedures, transactions). Institutions (laws, contracts, the library) are code that runs on it.
2. **Primitives are state changes.** Each primitive can be caused by an agent (through an action), by a law or contract (through a
   law function), by the world (clock, physics, chance) or by a researcher (an intervention). Death is one primitive,
   `end_life(agent, cause)`, whatever caused it.
3. **One chokepoint.** Every primitive is applied with `k.apply(name, **payload)`, which runs physics checks, before-hooks, the
   change, charges and queues after-hooks, inside the cause stack.
4. **Hooks attach to primitives, fire whatever the cause, and receive the cause chain.** Legal acts are primitives. Pure outputs
   (gazette, notify, editions, digests) are not.
5. **Declare once, in a registry that fails on unknown names; keep behaviour in the owning module.** Old constant names are derived
   views so call sites do not change. No plugin framework, no rewrite, no `features/` package, no decorator-driven order.
6. **Writing is free; binding is procedural.** Anyone may write and preview law or contract code. Enactment over non-consenters is
   the polity's procedure; contracts bind only members.
7. **Richer than current capability.** The world offers more than today's frontier models will use; uptake is measured, not gated.
   Library templates are an experimental condition. Prefer lower-level primitives; the library's laws are readable implementations
   built from them.
8. **Bounded by limited death.** Gas per invocation, cascade and account-round; a depth cap; deterministic order; a defined halting
   point that kills only the offending hook invocation and flags its law.
9. **The instrument is part of the product.** Every input recorded, every event caused, every round restorable, every intervention
   typed and replayable, every goal's scoring rule shown to the agent who holds it.
10. **Keep:** plain-dict `k.w`; per-module string-seeded RNG streams; explicit `vis=` on every `log` call; golden tests; the law
    language's grammar and static classification; the Board and the Fixer as kernel invariants (attached by the power table).

**Deferred** (big future modules, not designed here): space and site graphs, technology trees, coupled ecology, aliases and
identity, capital and durable goods.

---

## 2. Module map

```
charter/
  kernel.py          physics: k.w, accounts, apply(), cause stack, log/visibility, phases loop, transactions, checkpoint
  primitives.py      NEW  Primitive registry + HookAlias table + apply functions for core primitives
  dispatch/          NEW  the primitive dispatcher (W8a: a package; D.<name> re-exports every old name)
    base.py               errors, records (Outcome, Cascade, Invocation), ROUTED, law.v2 switches and V2_SEAMS, gas budgets
    chains.py             cause frames as chains, D-18 redaction, chain sugar for laws
    options.py checks.py  call options (OPTIONS) and physics checks (CHECKS) of every routed primitive
    legacy.py             legacy hook aliases (on_transfer, ...) and their verdict readers
    routing.py            apply (P2.x path) and apply_v2 (law.v2) side by side; blocks and charges
    hooks.py              binding and canonical order, hook index, payload redaction, verdicts, conflict-rule resolution
    ranks.py validity.py  rank, lex superior, procedures per rank, conflict rules; declared in-force windows
    cascade.py            invocations, limited death, flags, the after-queue and its drain
    journal.py            atomic invocations (rollback) and refuse(reason)
    notify.py billing.py  compelled notices (P3.7); gas billed to treasuries (P3.8)
    api.py                the dispatcher's law-API functions
    changes/              the primitives' changes (rows' fn) by domain: economy, status, speech, world, lifecycle, legal,
                          membership, press, force, loans, associations, cases, agency
  lawlang.py         law language: check, instrument (gas v2), classify (derived), static_info, load
  linker.py          NEW  exports, use(), public state, code store, versions, auto-pinning
  lawapi.py          LawFn table (G2) + powers column + derived API_GROUPS / HOOKS / scoping
  powers.py          NEW  power table, account kinds, level presets
  preview.py         NEW  the previewer
  accounts.py        NEW  (P4.1) account records over jurisdictions: kind, members, treasury key, binding
  contracts.py       NEW  (P4.3) associations: create/join/leave, escrow, allowances, pull, breaches
  eventtypes.py      (G1) EventType registry
  action_registry.py Act rows: availability, layout, handler, doc, category, emits, module
  rights.py          Right registry (exists)
  features.py        NEW  Feature rows + PHASES
  schema.py          NEW  spec schema from Feature DEFAULTS; validation with suggestions
  sections.py        NEW  Section registry (text for core prompt, manual, legacy prompt, observer)
  facts.py           facts dict (exists); per-feature facts pieces
  goal_registry.py   NEW  Goal rows (text, rule, score, probes, version)
  history.py         (G5) History
  scorer.py          scoring pass over History and GOALS
  interventions.py   NEW  typed ops, schedule, apply_due, records
  provenance.py      run.json, calls.jsonl, segments (exists)
  replay.py          (G6) Replay policy, per-round checkpoints
  library.py         library v1 (today) + v2 building blocks (lib:*) and implementations + the legal toolkit (TOOLKIT, PENDING)
  lawset.py          law sets: composability checks, derived dimensions, legal fingerprints (W6d)
  tiers.py           review 12 WP0 (W8a): tier codes and the hard-coded rules registry (one row per inventory item)
  <feature modules>  conflict, life, mortality, media, jurisdictions, credit, projects, outside, hidden, roles, camptypes, context, ...
```

---

## 3. Registries

Every registry is a module-level dict keyed by name, filled at import in a fixed order, whose `get(name)` raises
`Unknown<Kind>(name)` with a did-you-mean suggestion. Old constant names are kept as derived views. One test file,
`tests/test_charter_contract.py`, walks all registries and their cross-references (§3.14).

### 3.1 Features and phases (`features.py`, P1.2)

```python
@dataclass(frozen=True)
class Feature:
    name: str                      # "conflict"
    module: str                    # "charter.conflict"
    spec_key: str | None           # "conflict"; None: core, always on
    default_on: bool = False       # projects: True
    implied_by: tuple = ()         # mortality: ("life", "conflict")
    state: tuple = ()              # k.w keys install() adds; none when off
    rng: tuple = ()                # string-seed prefixes this feature owns ("conflict", "conflict-bot")
    golden: str | None = None      # the golden case that turns it on
    def on(self, x) -> bool: ...   # THE enabled check (spec, instance or kernel); replaces 10 helper spellings

FEATURES: list[Feature]            # order = today's merge order (law_api spreads, snapshot keys, state lines, truth)
PHASES: dict[str, list[tuple[str, str]]]   # "init", "round_start", "round_end", "after_turns", "death", "birth", "probate"
```

Fixed module-level names a feature module may define (checked by signature): `DEFAULTS: dict`, `install(k)`, phase functions
`(k)`, `law_api(k, lid) -> dict`, `preview_rules(k, ag) -> dict`, `snapshot_fields(k) -> dict`, `truth(k, inst) -> dict`,
`state_lines(k, aid) -> list[str]`, `render_event(k, e, tag, viewer) -> str | None`, `facts(spec) -> dict`, `SECTIONS`, `LAW_DOCS`,
`LAWS`. `PHASES` lists `("core", step)`, `("<feature>", fn)` and `("law", clock_hook)` entries in today's order (review 01 §4.3,
review 08 §4); `death` is today's hand-coded sequence in `mortality.disable`.

### 3.2 Spec schema and state sections (`schema.py`, P1.3)

- Each feature's `DEFAULTS` is the single source of its spec block; `charter/specs/base.yaml` may override but not add keys.
- `schema.validate(spec) -> list[str]` returns errors for unknown keys (with suggestions), wrong types, unknown enum values
  (`models.mix`, `turns`, agent class names, library categories); generation calls it and fails on any error.
- Keys may be marked `runtime_safe=True` (the generalisation of `runner.LIVE_KEYS`) for the `set_spec` intervention.
- State: `Feature.state` declares the `k.w` keys a feature owns (review 08 dropped a separate `vocab.STATE`). `kernel.STATE_SCHEMA`
  (exists, 1) is bumped on any shape change, with a migration in `MIGRATIONS = {n: fn}` run by `restore_state` and the History loader.

### 3.3 Primitives (`primitives.py`, P1.7 metadata, P2.1 behaviour)

```python
@dataclass(frozen=True)
class Primitive:
    name: str                       # "move", "end_life", "propose"
    feature: str                    # Feature.name; "core" for the kernel
    effect: str                     # move | create | destroy | relation | rule | status | life | speech | legal
    params: tuple[str, ...]         # payload keys, in order; payload values are JSON-able
    fn: str                         # "module:function" implementing the change: (k, **payload) -> dict result
    subject: str | None             # payload key whose binding selects before-hooks ("src", "agent", "jurisdiction")
    parties: tuple[str, ...] = ()   # payload keys whose binding selects after-hooks
    agent_params: tuple = ()        # payload keys naming agents (binding, redaction, completeness test against LawFn)
    before: bool = True             # hookable before (gate)
    after: bool = True              # hookable after (react)
    blockable: bool = True          # False: physics laws cannot stop (old age, regrowth); charges and directives still allowed
    charge: tuple | None = None     # (payer_key, item_key) when a numeric before-verdict deducts goods
    directives: tuple = ()          # extra keys a before-verdict may set ("jurisdiction" on begin_life, "admit" on join)
    legal: bool = False             # a change to the rule system: hooking it makes a law procedural
    entrenched: tuple = ()          # powers whose exercise no hook can block ("board_veto", "fixer_patch")
    event: str | None = None        # EventType the change logs (must exist in eventtypes.EVENTS)
    blocked_event: str | None = None
    act: tuple = ()                 # action names that cause it (must exist in action_registry.REG)
    compel: tuple = ()              # law functions that cause it (must exist in lawapi.LAWFNS)
    reads: tuple = ()               # law reads about it
    preview: tuple = ()             # k.w paths Kernel.view shows ("conflict", "obligations")
    redact: str | None = None       # "module:function" (k, payload, viewer_lid) -> payload
    compel_vis: str = "parties"     # who sees a law-caused instance on a non-consenting agent: parties | public | monitor
    why: dict = field(default_factory=dict)   # reasons for missing faces {"compel": "...", "gate": "..."}
    routed: bool = False            # W8a: Kernel.apply makes the change (dispatch.ROUTED); no "dispatch:" fn prefix test
    tier: str = ""                  # W8a (review 12 WP0): P | E | X | L | L-route, from primitives.TIER_OF

@dataclass(frozen=True)
class HookAlias:                    # a legacy hook name with today's exact firing condition (review 09 §4.3)
    name: str; primitive: str; phase: str; when: Callable; args: Callable; verdict: str = "before"
```

Initial catalogue (P1.7 declares all; P2.x routes them):

| Family | Primitives |
|---|---|
| goods and money | `move`, `harvest`, `regrow`, `mint`, `burn`, `create_currency`, `convert` (forge, deposit, redeem), `seize` (= move with `why` and physics for debt) |
| rights and status | `grant_right`, `revoke_right`, `suspend_right`, `limit_actions`, `create_right`, `set_title`, `rename` |
| life | `begin_life(agent, how, parent)`, `end_life(agent, cause, by)` (causes: attack, assassin, accident, old_age, law, departure, intervention) |
| force | `attack`, `fortify`, `guard_bind`, `guard_release` |
| speech | `post`, `dm`, `hide_post`, `subscribe` |
| membership | `join`, `leave`, `admit`, `expel` (polities and associations) |
| rules of things | `set_camp_rule(camp, key, value)`, `set_dm_limit`, `set_lease_rules`, `set_birth_rules` |
| legal acts | `propose`, `decide`, `open_ballot`, `cast_vote`, `close_ballot`, `veto`, `enact`, `repeal`, `amend`, `set_procedure`, `rule`, `define_action`, `set_conflict_rule` |
| contracts (P4) | `create_contract`, `deposit_escrow`, `set_allowance`, `pull`, `breach`, `dissolve`, `swap`, `open_fund` (P4.4), `authorize`, `deauthorize`, `act_for` (P4.5) |

Not primitives: `gazette`, `notify`, editions, digests, the round summary, previews, reads.

### 3.4 Actions (`action_registry.py`, P1.1)

```python
@dataclass(frozen=True)
class Act:
    name: str; purpose: str; section: str
    handler: str                    # "conflict:act_fortify": resolved lazily, so no import cycle
    doc: str                        # the ACTION_DOC line, with {fact} placeholders filled from facts()
    category: str                   # productive | economic | political | talk (no fallback)
    module: str                     # Feature.name
    emits: tuple = ()               # EventType names the handler may log
    primitives: tuple = ()          # primitives it causes
    core: bool = False; pre: bool = False; msg: bool = False      # msg replaces DM_ACTIONS
    needs: tuple = ()               # "mod:x" | "right:r" | "cls:c" | "role:r" | "level:Ln"
    when: Callable | None = None    # public can_* helpers only, never raw k.w
    args: str = ""; edge: tuple = (); aliases: dict = field(default_factory=dict)
    legacy: bool = True             # listed by the legacy (context-off) prompt
```

Derived: `actions.ACTIONS` (registry order), `DM_ACTIONS`, `agents.ACTION_DOC`, `scorer.CATEGORIES`, every `absent_actions`. `act()`
dispatches through `handler`; the 46 trampolines go.

### 3.5 Rights (`rights.py`, exists)

`Right(name, doc, kind, origin, secret, entrenched, never, role, aliases)`. Add `module` (P1.2). Secrecy is one flag consulted by
law reads, previews, `rights` events, manuals and primitive `redact` functions; role-bound rights are not hookable.

### 3.6 Law functions and hooks (`lawapi.py`, G2 + P1.7 + P4.2)

```python
@dataclass(frozen=True)
class LawFn:
    name: str
    cls: str                        # read | ordinary | structural | procedural   (G2)
    module: str                     # Feature.name                               (G2)
    agents: tuple = ()              # ((position, param), ...)                    (exists)
    scope: str = "bound"            # bound | custom | read | none                (exists)
    refused: object = None; legacy_only: bool = False; why: str = ""          # (exists)
    primitive: str | None = None    # the primitive it causes (compel face), if any       (P1.7)
    power: str | None = None        # the power an account needs to call it (P4.2; replaces legacy_only)
    contract: str = "deny"          # allow | escrow | deny: what an association law may do  (P4.3)
    preview: tuple = ()             # k.w paths it writes, for previews
```

Hooks are rows too (`kind="hook"` in a `HOOKS` table in `primitives.py`): every `before_<p>`/`after_<p>` derived from primitives,
the clock hooks `on_round_start(r)`/`on_round_end(r)`, the lifecycle hooks `on_enact()`/`on_repeal()`, and the legacy aliases.
`lawlang.HOOKS` is derived from it.

### 3.7 Powers (`powers.py`, P4.2)

```python
@dataclass(frozen=True)
class Power:
    name: str                       # "board_veto"
    doc: str
    kinds: dict                     # {"polity": True, "association": False, "personal": False}; values may be a preset name
    lawfns: tuple = ()              # law functions gated by it
    primitives: tuple = ()          # primitives it allows on non-consenting agents
    entrenched: bool = False        # kernel invariant: no law may remove it from its holder

POWERS = {p.name: p for p in (
    Power("board_veto", ..., {"polity": "founding"}, entrenched=True),        # J.board_reviews / board_scope
    Power("fixer_patch", ..., {"polity": "founding"}, entrenched=True),
    Power("law_levels", ..., {"polity": "spec", "association": "bylaw"}),     # L0-L4 presets below
    Power("dry_run", ..., {"polity": True, "association": "optional"}),
    Power("kernel_rights", ..., {"polity": True}),                            # grant/revoke/suspend vote, propose, press, ...
    Power("compel_members", ..., {"polity": True, "association": "escrow"}),  # fine, sanctions, oblige_guard, compel_subscription
    Power("pay_outsiders", ..., {"polity": False, "association": True}),
    Power("lawful_attack", ..., {"polity": True}),
    Power("default_membership", ..., {"polity": True}), Power("exclusive_membership", ..., {"polity": True}),
    Power("unlimited_exit_seizure", ..., {"polity": True}),
    Power("legacy_reserve", ..., {"polity": "founding"}),                     # credit, par, projects, tribute (LEGACY_ONLY)
    Power("estate_access", ..., {"polity": True}),                            # after_end_life may move from estate:<aid>
    Power("hook_legal_acts", ..., {"polity": True, "association": "own"}),
)}
LEVEL_PRESETS = {"L0": {...}, "L1": {"classes": {"ordinary"}, "ranks": {"regulation", "statute"}, ...}, ..., "bylaw": {...}}
def has_power(k, account: str, power: str) -> bool | str: ...
```

### 3.8 Event types (`eventtypes.py`, G1)

`EventType(name, module, feed, post, board, truth, forgeable, quotable, message, aliases, render)`, `feed` required. Add
`primitive: str | None` (the primitive whose change logs it) in P1.7. Visibility stays per call. Derived: `POSTABLE`,
`context.BOARD_TYPES`/`RECENT_KINDS`/`POSTS`/`OFFICIAL`, `goals.PUBLIC`, `hidden.FORGEABLE`/`VEILABLE`, `media.QUOTABLE`,
`report`/`observer.MESSAGE_TYPES`. Strict mode (`CHARTER_STRICT_VOCAB=1`, set by tests) makes `k.log` raise on an unregistered type.

New types introduced by this architecture (each with explicit `vis=` at its call site): `proposal_blocked` (public),
`enact_blocked` (public), `law_flagged` (public), `import_pinned` (public), `cascade_halted` (monitor), `hook_aborted` (monitor),
`account_out_of_gas` (account members), `compelled` (parties; D-5), `intervention` (monitor), `contract_*` (P4).

### 3.9 Goals (`goal_registry.py`, P1.5)

```python
@dataclass(frozen=True)
class Goal:
    name: str; category: str; weight: float
    min_level: str = "L0"; slots: frozenset = ANY_SLOT; requires: tuple = ()     # Feature names (replaces EXTRA_GATES/NEW_GOALS)
    share: str = "category"; opt_in: str | None = None
    passive: bool = False; counter_of: str | None = None; refusal_tracked: bool = False
    params: Callable[[Random, dict, str], dict] = no_params      # replaces the sample_params if-chain; same RNG consumption
    text: Callable[[dict], str] | str = ""       # WHAT to achieve; raises on a missing parameter
    rule: Callable[[dict], str] | str = ""       # HOW it is scored; shown to the agent verbatim after `text`; required
    score: Callable[["History", str, dict, "Ctx"], float | None] = ...   # THE primitive: any function of the run history
    probes: dict[str, Callable] = field(default_factory=dict)          # (k, snap, params) -> JSON, recorded each round
    needs: frozenset = frozenset()               # History tables read
    version: int = 1                             # bump with any change to score or rule; score.json records it
    fixed: bool = False; cls: str | None = None  # Board and Fixer objectives
    examples: tuple = ()                         # executable fixtures (history, agent, params, expected)
```

Timing helpers (`at_end`, `at_exit`, `mean(held)`, `peak`, `total`, scopes `self | lineage | jurisdiction`) are optional sugar in
`goal_registry.helpers`. Derived: `CATALOGUE`, `SCORERS`, `EXTRA_GATES`, `NEW_GOALS`, `OPT_IN`, `SLOTS`, `PASSIVE`,
`COUNTER_GOALS`, `HAVOC_REFUSAL`, `life.HISTORY`, `describe`, both slot-text assemblers, `scorer.SCORING_VERSION` (a hash of the
per-goal versions).

### 3.10 Sections and facts (`sections.py`, `facts.py`, P1.6)

`Section(key, render: Callable[[View], str], layers, needs, after, order, cut, priority)` as review 02 §4.4, with `needs` in the
same DSL as `Act.needs`. `View` carries `inst, k, a, rights, classes, roles` and a cached `facts`. Every number in prose comes from
`facts`. The core prompt, manual, legacy prompt and observer prompt are renderings of the same rows.
As built (P1.6): `Section(key, render, layers, needs, after, order, cut: never|clip, priority, budget, sep, note)`; each layer's
order is `sections.LAYOUTS[layer]`, modules' rows are anchored with `after=`; `render` may return `None` (absent) or a list of
`(title, text)` (one row, several manual sections). `facts.PIECES` holds one piece per feature (unique names, `facts.OWNER`).

### 3.11 Library (`library.py`, P3.9)

```python
LIB[name] = {"name", "category", "module",            # Feature gate (folds conflict.LAWS, GATED_CATEGORIES)
             "kind": "law" | "contract" | "block",    # block: a lib:* building block for use()
             "rank": "statute", "edition": 1 | 2,    # v1 = today's switches; v2 = readable implementations from primitives
             "code", "sha"}                            # sha computed; blocks are in the code store and importable by hash
```

Spec `library: {edition: 1|2, access: none|catalogue|instantiate}`: `catalogue` (agents can read library code and copy it),
`instantiate` (one-call template instantiation with parameters: the experimental "templates" condition).

As built (W6d, review 10 §5.4 and §6): the core legal toolkit, `TOOLKIT[name] = {name, category: "toolkit", kind: "law", edition:
2, family, topic, rank, doc, fires, code, sha}` (law.v2 templates; names never collide with LIB; parameters = top-level constants,
`params(name)`; `instantiate(name, params, x, rank=None)`; importable by hash like blocks), and `PENDING[name] = {family, topic,
waits_on, doc}` for the items that wait on another package. Regimes are law sets: `regime: {base, laws: [{template, rank, params}],
drop, amend}` resolved by `regimes.resolve_laws` from the stream `f"{seed}|regime_laws"`; `lawset.check(laws, spec, level)`
(composability), `lawset.dimensions(laws)` (the dimension vector derived from the laws; `expect` stays the declared label),
`lawset.fingerprint(k)` (recorded in run.json as `legal_fingerprint`, law.v2 runs) and `lawset.distance(a, b)`. A law made from a
template carries `template: {name, params, rank}` on its record. Spec `law.library.toolkit: none | all | [families]` lists toolkit
templates in the edition-2 catalogue.

### 3.12 Intervention ops (`interventions.py`, P5.1)

```python
@dataclass(frozen=True)
class Op:
    name: str                        # "move"
    fn: Callable                     # (k, inst, rs, **args) -> None; uses k.apply where a primitive exists
    phases: tuple                    # round_start | before_turn | after_turn | round_end
    args: dict                       # schema: {"src": "account", "dst": "account", "item": "str", "qty": "float"}
    primitive: str | None = None     # the primitive it applies, if any
```

Ops: `move, gazette, notify, grant, revoke, suspend, begin_life (add_agent), end_life (remove_agent), set_goal, set_model,
set_prompt_extra, enact_law, repeal_law, amend_law, set_spec, inject_action, replace_reply, python`.

### 3.13 How the registries interlock, and which constants derive from which

```
Feature ──on()──> Act.needs "mod:x", LawFn.module, Right.module, EventType.module, Goal.requires, Section.needs, LIB.module,
   │              lawdocs gates, archive NEEDS, schema (DEFAULTS)
   └─PHASES──> Kernel.__init__ / start_round / end_round / death / birth (loops in today's order)
Primitive ──act──> Act        ──compel/reads──> LawFn       ──event──> EventType      ──hooks──> HOOKS (lawlang)
          ──preview──> Kernel.view          ──entrenched──> Power    ──redact──> Right.secret
LawFn ──cls──> API_GROUPS, STRUCTURAL_CALLS, classify()     ──power──> Power ──presets──> levels
Goal ──requires──> Feature   ──needs──> History tables   ──probes──> snapshot["probes"]
Op ──primitive──> Primitive
```

| Constant today | Derived from | Package |
|---|---|---|
| `actions.ACTIONS`, `DM_ACTIONS`, `agents.ACTION_DOC`, `scorer.CATEGORIES`, `absent_actions` | `Act` rows | P1.1 |
| `KERNEL_RIGHTS`, `ENTRENCHED`, `NEVER`, `SECRET_RIGHTS`, `RIGHT_DOC`, `OFFICE_RIGHTS` | `Right` (done) | - |
| `lawlang.API_GROUPS`, `API`, `STRUCTURAL_CALLS` | `LawFn.cls` | G2 |
| `AGENT_ARGS`, `REFUSED` | `LawFn.agents/scope` (done) | - |
| `LEGACY_ONLY` | `LawFn.power == "legacy_reserve"` | P4.2 |
| `lawlang.HOOKS` | primitives (`before_*`, `after_*`) + clock + lifecycle + `ALIASES` | P1.7 |
| `lawlang.LEVEL_CLASSES` | `LEVEL_PRESETS` | P4.2 |
| `MAX_STEPS`, `MAX_DEPTH` | spec `law.gas.per_call`, `law.gas.python_depth` (same defaults) | P2.2 |
| `kernel.POSTABLE`, `posts()` types, `BOARD_TYPES`, `RECENT_KINDS`, `goals.PUBLIC`, `FORGEABLE`, `VEILABLE`, `QUOTABLE`, `MESSAGE_TYPES`, feed priority | `EventType` flags | G1 |
| `EXTRA_GATES`, `NEW_GOALS`, `OPT_IN`, `SLOTS`, `PASSIVE`, `COUNTER_GOALS`, `HAVOC_REFUSAL`, `life.HISTORY/SUMMED` | `Goal` | P1.5 |
| `SCORING_VERSION` | per-goal `version` | P1.5 |
| `LAW_API_VERSION` | bumped only when an existing call or hook changes meaning; new primitives, hooks and aliases do not bump it; `law.v2` is recorded in `run.json` | P3.1 |
| `STATE_SCHEMA` | bumped on any state shape change; `MIGRATIONS` chain | each package that changes state |
| `facts()` | per-feature `facts(spec)` pieces, unique names | P1.6 |
| enabled helpers (`enabled`, `enabled_spec`, `on`, `active`, ...) | `Feature.on` | P1.2 |
| `lawdocs` gates (`OPTIONAL`, `REQUIRES`, `MODULE_ENTRIES`, `_gated_off`) | `LawFn.module` + `Feature.on` | P1.7 |
| `Kernel._module_rules` | `Primitive.preview` + module `preview_rules` | P2.4 |
| `runner.LIVE_KEYS` | spec schema `runtime_safe` | P1.3/P5.1 |
| `goals._offices` | `Right.kind == "office"` (done) | - |

### 3.14 The completeness test

`tests/test_charter_contract.py` (P1.7 starts it, every package extends it) with a `KNOWN_GAPS` set that may only shrink (compared
with a frozen copy):

- every feature owns exactly its declared state, and nothing when off;
- every `Act`: resolvable handler, doc, category in the four, `emits ⊆ EVENTS`, `primitives ⊆ PRIMITIVES`, gated by its feature;
- every `LawFn`: in `api_for`, has `cls`, docs, and `preview` or a `why` if it writes;
- every `EventType`: `feed == "silent"` or a renderer returns text for a sample;
- every `Primitive`: `act`/`compel`/`event` names exist; a missing face has a `why`; `compel_vis != "monitor"` or a `why`; a payload
  sample round-trips through `json`;
- every `Goal`: `rule` non-empty, `version` bumped when `rule` or `score` changed (hash check), `examples` pass;
- every logged event type in the golden runs is registered (strict mode);
- every `random.Random(f"...")` prefix in the package belongs to one feature's `rng`.

---

## 4. The kernel: responsibilities ("physics")

| Responsibility | Where | Notes |
|---|---|---|
| State | `k.w` plain dict | JSON-able except the existing `effects.from_reserve_recipients` set (to become a sorted list under `STATE_SCHEMA` 2) |
| Accounts and conservation | `bal`, `_add` (private), `apply("move")` | owner keys: agent ids, `reserve` (J0, kept forever), `reserve:<jid>`, `estate:<aid>`, `escrow:<cid>:<aid>`, `world` (sink/source for interventions and gas) |
| Primitive application | `apply()` | physics checks, hooks, change, charges, after-queue |
| Authority | binding + power table + class/level/rank | laws never act for an agent; actions need rights and `needs` |
| Causes | cause stack (G3) | every event carries `cause` and `chain`; hooks receive a redacted chain |
| Time | `PHASES` | rounds, phases, clock hooks; cascades drain at root-frame exit |
| Life and death | `begin_life`, `end_life`, probate | one primitive per life event, whatever the cause |
| Visibility | `log(..., vis=)`, `can_see`, `redact` | explicit `vis=` on every call |
| Randomness | string-seeded streams per purpose | `rng_version: 2` splits order/harvest/drift/law streams |
| Legal machinery | `dispatch/` (routing, hooks, ranks, cascade, journal), procedures lookup, ballots, veto queue, transactions | gas, depth, halting, flags |
| Transactions | `_snapshot/_restore`, journal | dry runs, previews, atomic invocations |
| Checkpoint | `checkpoint_state/restore_state` | per round (G6); law code re-executed, callbacks marshalled |
| Entrenched invariants | power table entries with `entrenched=True` | Board veto, Fixer patch, laws never act for an agent |

What the kernel does **not** own: institutions (laws, contracts, library), goals and scoring, prompts and text, the runner's model
calls, analysis.

---

## 5. The cause stack and cascades

Interface (G3, extended here):

```python
@contextmanager
def cause(self, kind: str, id: str, *, root: bool = False, **meta) -> Iterator[dict]
def chain(self, viewer: str | None = None) -> tuple[dict, ...]     # root first; redacted for a viewing law
# every event: {"id", "round", "type", "agent", "data", "vis", "cause": <innermost frame>, "chain": [frame ids, root first]}
```

Frame kinds: `phase, turn, action, law, primitive, world, intervention, kernel, preview` (review 09 §4.4 has ids and meta).
`root=True` frames (action items, phase steps, intervention ops, world-event firings, preview scenarios) open a **cascade**; leaving
the frame drains its after-queue (review 09 §9.3). Nested root frames are an error. Kernel-internal probes run `quiet` (no hooks).

---

## 6. The legal system

Review 09 is the normative design. Summary of the target:

- **Hooks** `before_<p>(p, chain)` and `after_<p>(p, chain)` for every hookable primitive; verdicts `None/True/False/number/dict`;
  old hook names are aliases with today's exact firing (behaviour-preserving). New-style hooks need `law.v2: true`.
- **Legal acts are primitives**: `propose` (payload with the draft's code, class, rank, calls, hooks, rights, imports, exports),
  `decide`, `open_ballot`, `cast_vote`, `close_ballot`, `veto`, `enact`, `repeal`, `amend`, `set_procedure`, `rule`,
  `define_action`, `set_conflict_rule`. Hooking one is procedural. Entrenched powers (veto, Fixer patch) cannot be blocked.
- **Exports/imports**: `exports = [...]`, `use("L3")` (follow) or `use("L3@sha")` (pinned) or `use("lib:name@sha")`; linked with the
  importer's authority; DAG; versions in a code store; follow-imports auto-pin when the export disappears or the law is repealed.
- **Public state**: `public` dict per law; `public_of(lid)` deep copy; JSON-able; hidden-jurisdiction laws invisible.
- **Amendment**: agents `amend {law, code, reason}`; laws `propose_amendment` / `propose_law` (structural, L3+); all through the
  procedure; the Fixer's patch is `amend` with `via="fixer"`.
- **Rank**: `charter (4, reserved) > constitution > statute > regulation > bylaw`; lex superior; procedures per rank; canonical hook
  order account → rank → enactment; conflict rule set by the constitution (`any_block` default, `superior`, `posterior`, custom).
- **Limited death**: synchronous before-hooks, FIFO after-queue drained at root exit, budgets per call (10,000, as today), per
  cascade (100,000), per account-round (1,000,000), depth cap 8, re-entrancy rules R1-R5, defined halting points, deterministic
  flags, escalation to suspension, optional atomic invocations (journal) and gas billing.
- **Gas v2**: compile-time instrumentation and size-charged builtins (closes the unmetered-builtin DoS, review 09 F2).
- **Previewer**: `preview(k, code, requester=...)` and the `preview_law` pre-action: static facts, constitutional review, procedure
  outcome, scenarios, rounds, trace and gas, over the legal system visible to the requester.
- **Evidence** (review 10 #10, `evidence.py`): `event(eid)` and `history(type, agent, since, limit<=50)` read redacted copies of the
  events the law's account may know (the public record, plus a hidden polity's or an association's own members-only record; never
  monitor-only, private or channel events), metered by size through the call's gas meter.
- **Legal digest** (review 10 §7, `digest.py`, spec `law.digest`, default off): per agent, the laws that bind it grouped by the
  primitive family they hook, from static facts (hooks, verdict shapes, calls, rank, class, exports, overlaps), in the core prompt
  (a clip row, `law.digest_tokens`) and the `legal_position` look-up; visible laws only. Hooks are indexed by name
  (`dispatch.hooked`): a primitive no law in force hooks skips the binding and ordering work.
- **W7e follow-ups** (law.v2): a law's `in_force_from/until` is shown in the draft payload, previews, the law list and `read_law`
  (`dispatch.window_note`); an after-hook's `refuse(reason)` is told to the acting agent (`law_refused`); type tests `is_number`,
  `is_text`; court rules `rulings_per_round` and an appellate office that rules on appeals without `judge` (`action_registry`
  `alt`); contracts' procedures may answer with stage plans (`stages.begin(contract=)`, `contracts.stage_done`); `history(about=)`;
  cases carry `source` (agent | law | contest | contract; stored only when not agent); `evidence.law_can_see` is the one visibility
  predicate for laws, also gating after-hook delivery under spec `law.after_visibility: evidence` (default `all`: after-hooks
  still see changes whose events the law cannot read, a documented gap); with `contracts.breach_cases` an escrow_court breach
  opens a courts v2 case (source contract, accuser the breach's `victim`).
- **Classes and levels**: class derived transitively (calls, imports, hooks); rank orthogonal; levels are power-table presets.
- **Bug F1**: an ordinary law can repeal the constitution today; fixed in P1.4.

---

## 7. Accounts, contracts and the power table

### 7.1 Accounts

Every law belongs to an account. Today's jurisdiction records become accounts with a `kind` (P4.1):

```python
k.w["jurisdictions"][jid] = {"id": jid, "kind": "polity" | "association" | "personal", "status": "hidden|declared|active|dissolved",
                             "name": str, "founder": aid, "members": [aid, ...], "treasury": "reserve" | "reserve:<jid>",
                             "procedures": {...}, "conflict_rule": "any_block", "powers": {...overrides...},
                             # associations only:
                             "escrow": {aid: {item: qty}}, "allowances": {aid: {item: qty}}, "exit": {...}, "breaches": [...],
                             "template": str | None, "params": dict}
def account_of(k, lid) -> str          # the law's account id ("J0" when jurisdictions are off)
def treasury_of(k, account) -> str     # owner key for bal/move
def binds(k, account, aid) -> bool     # membership (J0: everyone)
```

`"reserve"` remains J0's owner key forever (library and agent-written laws contain the literal). Per-law charge destinations
(review 09 §4.6) land with P4.1 and are behaviour-identical for polities.

### 7.2 Contracts first

Associations v1 (P4.3) follow review 06 §3-§4 with the changes below:

- Anyone may write contract code; it binds only members, who join explicitly. Contract laws are rank `bylaw` and active at once.
- The power set is data: `LawFn.contract` (`allow | escrow | deny`) and the power table's association column. Associations may pay
  outsiders from their treasury, pull within escrow or allowances, mint their own backed currency (shares), create and grant
  their own rights among members, define offices, expel and admit, run member ballots, and hook members' primitives (charges go to
  the association's treasury). They may not touch kernel rights, fine beyond escrow, sanction, attack, or set camp rules.
- Contract law errors suspend the law and notify members; they never go to the Fixer.
- Enforcement dial `contracts.enforcement: escrow | escrow_court | word` (P4.4). `escrow`: a contract enforces itself through
  escrow and allowances, `breach()` only records. `escrow_court`: also, `breaches()` marks records `actionable` and the polity
  library law "Contract Enforcement Act" sanctions them (a judge's ruling on its clause `breach_of_contract`, or automatically);
  `contracts.court_breaches(k, member)` is the seam courts v2 builds on. `word`: no escrow at all (the escrow column refuses,
  `deposit_escrow`/`set_allowance` are refused), breaches are public (`reputation(agent)`).
- Atomic exchange (P4.4, review 10 §6 #7): primitive `swap(contract, a, b, give, get)` (both legs between two members' escrows or
  neither; hookable as `before_swap`/`after_swap`) and the `exchange` template.
- Per-law funds (P4.4, review 10 §6 #8): owner key `fund:<lid>:<name>` from `open_fund(name)`, an account of the law's account
  (`accounts.funds_of`); only law `lid` moves goods out (`accounts.check_fund_move`; an amendment keeps the id); a fund whose law
  is out of force closes into the account's treasury at the end of the round. Contracts on only.
- Dissolution (P4.4): when the last members leave, the laws' `on_dissolve(heirs)` runs, then the treasury is shared equally among
  those last members; a dead member's escrow or share follows its estate or bequest (`mortality.settle_late`).
- Shares, own rights and offices (P4.5): `create_currency`, `mint`, `burn`, `create_right`, `grant`, `revoke`, `define_action` are
  `escrow`-column functions for an association: everything it creates is named `<cid>.<name>`; its currencies are backed by its
  treasury (`Kernel.price` = net asset value per unit, D-15), minted to anyone, burned only from what it holds; `shareholders(cur)`
  is the register; at wind-up the treasury goes to the holders of its currencies pro rata (treasury stock excluded) before the
  equal split among the last members. Its rights go to members only and are dropped when a member leaves or the contract
  dissolves; its offices (`define_action`, no law level) are invoked by members holding the right and end with their law.
- Agency (P4.5, review 10 #11): actions `authorize` / `revoke_authorization` / `act_for`, primitives `authorize`, `deauthorize`
  (not blockable) and `act_for`, routed and hookable under law.v2. A grantor lets an agent or a contract office (holders of one of
  a contract's rights) give or deposit in escrow up to `qty` of one item per round on its behalf (`contracts.AGENCY_ACTIONS`;
  `vote` is never authorizable), optionally to listed recipients and for N rounds. "Laws never act for an agent" holds: no law
  function causes these primitives; the grantee acts on the grantor's recorded consent, the inner transfer is an ordinary
  transfer of the grantor's (its hooks and taxes apply), and every use is logged `{grantor, grantee, auth}` to both
  (`agency_used`). The kernel's `has`/`move` are unchanged: the check lives in `contracts.check_act_for`.
- Standing orders, scripts and registries are contract templates, not kernel features (review 07). P4.5: template
  `standing_order` (one member, closed, pulls from the founder's allowance, pays `TO` every `EVERY` rounds while the founder keeps
  `KEEP`, ends after `TIMES`) and the `standing_order` action that founds it and sets the allowance in one call.
- Associations as holders (review 10 #13), the cheap part (P4.5): an association's law may pay or mint to another association's
  treasury, and wind-up pays shares held by an association to its treasury. Not done: an association holding rights or
  membership in another (rights live on agent records and `Kernel.has`; members are agent ids in ballots, hooks, escrow keys and
  exit). It needs a member kind on association records (`{"kind": "association", "id": cid}`), an account-level `has()`, ballots
  weighted per member account, and a rule for who acts for a member association (its office holders, through agency).
- Exit: a member can always leave at round end; `on_exit` keeps at most the member's escrow.
- Incorporation (W8e, D-28; `charter/incorporation.py`): `create_contract {"under": "<polity>"}` founds a company under a polity
  (record key `parent`, absent on an unincorporated contract, which keeps today's limits and world defaults). The founding is the
  routed `create_contract` primitive with payload key `under`: the parent's laws see it whoever the founder is
  (`before_create_contract`: registration, a required template) and its company rules apply (a registration fee into its
  treasury, a required governance form, limits). Once incorporated:
  - Binding (`dispatch.hooks.bound_laws`): the parent's laws see every change naming the company (its id as the payload's
    contract / jurisdiction / polity, its treasury, an escrow it holds, its own currency or right), whoever the subject is. With
    jurisdictions on, other polities' laws no longer see the company's own acts: internal affairs belong to the polity of
    incorporation. Each member's own polity governs that member's own acts (the member is the subject or a party, as before).
  - Ranks and conflicts: a polity's laws are statute or above and a contract's code is rank bylaw, so in canonical hook order the
    parent's laws run first, and `resolve_v2` decides a company's change by its parent's conflict rule
    (`incorporation.governing_polity`). Under `superior` a parent law's block of the company's own act wins over the company's
    explicit allow (and the parent's explicit allow over the company's block); under `any_block` any block blocks, as before.
  - Benefits and bounds from the parent's law, not world dials: `company_rule(key, value)` (a polity's law only; the routed legal
    primitive `set_company_rule`, store `k.w["company_rules"][polity]`, held while its law is in force; reads `company_rules()`,
    `companies()`). Keys: `enforcement` (escrow | escrow_court | word, the dial per parent: escrow_court gives the company the
    parent's courts only, `breaches()` actionable in its laws and breach cases under its `breach_of_contract` clause),
    `recognize_offices` (False refuses agency to the company's offices), `share_valuation`, `wind_up`, `procedures` (governance
    forms allowed: a company's other form is replaced by the first listed when its changes are decided), `registration_fee`,
    `max_laws`, `max_own`. Unset keys fall back to today's behaviour.
  - D-27, first slice: share valuation (`Kernel.price` multiplies NAV by `incorporation.valuation_factor`: the parent's
    `share_valuation`, else the company's own top-level clause `share_valuation = "nav" | "none" | 0..1`, else NAV; never above
    NAV, so no clause can mint wealth); wind-up order (`_dissolve` runs `wind_up_order`: the parent's `wind_up`, else the
    clause `wind_up = [...]` of shareholders / members / parent, else shareholders then members; `parent` escheats the rest to the
    parent's treasury); built-in procedures (members, two_thirds, founder stay native default code; the library block "Contract
    Procedures" holds the same as law code, and `set_procedure` may name a built-in form); per-contract limits (spec
    `contracts.max_own`, `contracts.max_funds` with the old constants as defaults; the parent's `max_laws` / `max_own` replace the
    spec for its companies). Deferred: the contract column beyond physics, breach visibility, member liability (piercing the
    veil needs company debts), the agency action list.
  - Not done (review 10 #14, #15): a polity under a polity, treaties, an association as a member of another; the parent link is
    one level (a company under a polity).

### 7.3 The power table attaches the Board, the Fixer, levels and dry runs

Board veto, Fixer patch, law levels, the proposal dry run, kernel-rights powers, compulsion powers and legacy-reserve functions are
power-table rows (§3.7). The kernel consults `has_power(k, account, power)` instead of `"jur" in k.w` branches and `J.board_reviews`.
For J0 every entry is today's behaviour (P4.2 is behaviour-preserving under the differential harness). Entrenched powers stay kernel
invariants until the charter-rank milestone (review 09 §8.4).

### 7.4 Jurisdictions as contracts (later milestone)

After associations v1 has shipped and been piloted, and after G6 and the History schema version exist: review 06 §9.3 steps 1-7
(one political-analytics implementation; J0 installed in every world; one account path for hooks, decide, passed, enact, propose;
J0 storage moved into its record; `LEGACY_ONLY` as a founding-polity power; checkpoint migration). Gated by the differential harness
on every preset, including jurisdictions-on with hidden jurisdictions and a state-of-nature start. One golden re-record, for the new
state keys.

Wave 9 WP-D (review 14 §3.1, §6.1 row D; `charter/institutions.py`), behind spec `institutions.unified` (default false; off, every
world is byte-identical, checked by the goldens and `difftest` against the base):
- One store, `k.w["institutions"][iid]`, for jurisdictions (kind `polity`, J0 included) and contract associations (kind
  `association`), one record kind: id, kind, name, founder, founded_round, treasury, reserve, `status` (forming | active |
  dissolved), `published` (members | public), `members`, `parent`; a kind's own fields stay on the record as its template's state.
  Laws and offices are indexes (`institutions.laws`, `offices`), not copies. `k.w["jurisdictions"]` and `k.w["contracts"]["assoc"]`
  are not stored: `jurisdictions.jurs(k)` and `accounts.assocs(k)` are read-only views. Snapshots keep their shape (no new snapshot
  key), so History, the scorer, goals, context and export read what they did; `institutions.legacy_stores(k)` rebuilds the old
  stores. Checkpoints hold the new key (no migration of old checkpoints into the flag: a run keeps the flag it started with).
- Hidden is publication, not a status: a secret founding is `forming` with its existence published to its members; declaring
  publishes it and activates it. Secrecy checks read `jurisdictions.secret`, lifecycle checks `jurisdictions.st` (today's names).
- One path: the `found` action also founds an association when given code or a template (`create_contract` stays as its alias, and
  its primitive, which laws hook as `before_create_contract`); the `found` primitive takes kind None for a new institution; join,
  leave, admit and expel go through `institutions.change` (the kind's handler, then the polities' members); a contract's dissolution
  is routed (the `dissolve` primitive, kind `association`, call option `heirs`; a block cannot keep a memberless contract alive).
- With the flag on, scripted runs equal the flag-off runs except the dissolution's cause frame (tests/test_institutions_unified.py).
- Helpers for channels (WP-C) and grants (WP-E), in either representation: `institutions.get`, `kind_of`, `is_member`, `members`,
  `status`, `published`, `all_`. Not done here: grants (WP-E), dormancy and succession (WP-F), recognition and institutions as
  members (WP-G).

Wave 9 WP-E (review 14 §2.3, §3.2, §6.1 row E; `charter/grants.py`), behind spec `institutions.grants` (needs `institutions.unified`;
default false; off, byte-identical):
- Powers from grants, not kind: `powers.has_power` asks `grants.value`: seed (the preset's tree root: today's polity column, the
  j0 values included; `powers.J0_ONLY` are the seed-only powers), consent (the template's default column, plus what the founding
  code claims with `powers = [...]` from `grants.CONSENTABLE`: compel_members, unlimited_seizure, hook_legal_acts; frozen at founding
  in record key `consent`, shown to would-be joiners), parent (a parent's child rule `grants`, `grants.GRANTABLE`, only powers the
  parent holds), recognition (stub). A claim opens the compulsion functions to an association's code (`contracts.check_code` allow,
  `contracts.scope_api`) over members only: non-members are refused (`contract_out_of_scope`), per D-37. Company rules are child
  rules: `child_rule`, `child_rules`, `children` are the new names (old ones kept; `lawlang.ALIASES` classifies the new as the old).
- `regime.tree` (regime field `tree`, checked by `grants.check_tree`): every preset compiles to a one-node tree (J0, members all,
  the regime's code, the seed grant, opts fixer and code_default); a state-of-nature start to none. A written tree has one node for
  now (child nodes need their own Acts: WP-I). `code.rule` resolves through `code.chain`: the institution's node, its ancestors,
  the code_default nodes, then the residual; `code.root(k)` replaces the literal `code.ROOT` at the seams.
- Offices: `offices = {name: {title, powers, holders, seats, term}}` in an institution's code makes the right `<iid>.<name>` and a
  holding record in `k.w["offices"]` (holders with since and term_end, past holders with until), kept in step by the grant_right /
  revoke_right changes. An office's `powers` are names (what the right unlocks, "speak") and bounded grants in P4.5 agency format
  (`{action, item, qty, to, rounds}`, grantor the institution, grantee the office; review 18 §2.3: the use path `as` is H2).
  `institutions.offices`, `office`, `holders`, `officers`. Channels: selectors `{"officers": iid}` and `{"officers_or_members": iid}`;
  an institution's inbox is read by its officers once it declares an office, its members before. No vacancy or succession yet.

Wave 9 succession (review 14 §7.2, §3.4; review 18 §2.5, Q6; D-38; `charter/succession.py`, `charter/code/succession_act.py`),
behind spec `institutions.succession` (needs `institutions.grants`; default false; off, byte-identical):
- Vacancies: an office holding ends by death or departure (found at the end of the round, the round_end step `succession` after
  deaths of old age), exit or expulsion (contracts.change_leave), term end (term_end reached) or removal (a law's revoke). Each goes
  through the revoke_right change (via "vacancy" for a dead holder whose right already lapsed), so institutions.on_right stays the one
  writer of the record; `past` gains the cause; `office_vacant` is public; an office without a living holder has no usable grants
  (`institutions.usable_grants`). A dissolution or an abolition ends holdings without a vacancy.
- Filling: law hooks `on_vacancy(p)` (the governing polities' mandatory laws, the institution's own laws, then overridable polity
  laws only where the institution declared nothing), then the office's succession clause (`offices = {"x": {..., "succession":
  {"rule": designation | hereditary | election | cooptation | seniority | lot | none, "else": ...}}}`; library.SUCCESSION_CLAUSES)
  or the governing polity's Succession Act (default code, store-based, only in worlds with the flag: RULE election | receiver |
  none, RECEIVER, MANDATORY). `code.resolve_clause` walks `code.chain` nearest first: the nearest mandatory Act, else the
  institution's clause, else the nearest Act, else the residual (none: the office stays vacant). Elections are plurality ballots
  through the institution's procedure; `office_filled`. `name_successor {"office", "agent"}` designates for any office; the
  Board's seats keep their own path (the seeded designation rule), unchanged.
- Law v2 conflict handling: a law declaring `mandatory = False` is overridable; resolve_v2 drops its before-verdict where a law of an
  institution it governs gave an explicit verdict. Every other law (and every Act whose MANDATORY row is true) is mandatory.
- Dissolution (contracts._dissolve): the contract's own wind-up clause unless a mandatory Act overrides it; else shareholders, then
  the Dissolution and Escheat Act's TO (polity | family | members); no Act (a state of nature): locked (goods and loans owed stay
  frozen in the treasury, rights released, owned channels read-only; `assets_locked`). Passing to estates exists only as the
  family variant. Contracts may declare `party_death = "end" | "estate" (default) | "heirs"` (`party_died`).
- Repeal abolishes the offices a law declared (`office_abolished`; a contract law replaced by one declaring the same office keeps
  it). officers_or_members selectors fall back to members while every office is vacant. Founding docs and the contract listing show
  each office's succession rule.

---

## 8. Run store, provenance, History, interventions and forks

### 8.1 Run store

As review 04 §4.2, with what already exists marked:

```
runs/<spec>/<run_id>/
  run.json              provenance and segments (exists: provenance.begin/end); add features_on, law_v2, rng_version,
                        library edition, goal versions, parent {run, round, branch}, replicate
  instance.json         authoritative (exists: spec_source; resume regenerates from it)
  interventions.yaml    as submitted;  interventions.jsonl: as applied (round, phase, op, args, note, diff digest)
  calls.jsonl           every model call attempt (exists)
  prompts/system/<sha>.txt (exists)
  events.jsonl          + cause, chain (G3)
  snapshots.json, ground_truth.json, score.json (+ per-goal versions), validity.json
  checkpoints/rNNNN.pkl + checkpoints/index.json (G6): state only + offsets into append-only files
  blobs/<sha>           sandbox outputs and archive documents read (P5.4)
  directories/          base.json (the namespace-scoped directories' files at the start, as blob shas) and state.json (publish flag,
                        the manifest last written back): the frozen directories (charter/directories.py), as the shared archive's
                        archive/; the working copies live in k.w["dirs"] (checkpointed), written back to the live tree file by file
```

### 8.2 History (G5)

The interface review 05 §4.2 specifies, plus three additions from this architecture:

```python
class History:
    @classmethod
    def load(cls, run_dir, until: int | None = None) -> "History"
    rounds: range; final: dict; instance: dict
    def state(self, r) -> dict; def series(self, path, agent=None) -> list; def probe(self, name, r=None)
    def events(self, type=None, agent=None, r0=None, r1=None) -> Sequence[dict]
    laws: Mapping; cases: Mapping; loans: Mapping; guesses: Mapping
    def life(self, agent) -> Life; def alive(self, agent, r) -> bool; def living(self, r) -> list; def ever(self) -> list
    def lineage(self, agent, r=None, living=True) -> list; def goal_of(self, agent, r); def spans(self, agent) -> list[Span]
    def roles(self, r) -> dict; def member_of(self, agent, r) -> str | None
    def window(self, r0, r1) -> "History"; def cached(self, key, fn)
    # additions
    def caused(self, event_id) -> list[dict]          # events whose chain contains this event's cause frame
    def by_cause(self, kind=None, id=None) -> Sequence[dict]
    def law_versions(self, lid) -> list[dict]          # {v, sha, round, via, by}
    def accounts(self, r=None) -> dict                 # polities and associations with members per round (P4)
```

### 8.3 Interventions

Typed ops (§3.12), scheduled by round and phase, applied through `k.apply` (or the kernel function for non-primitive outputs) inside
`with k.cause("intervention", f"iv:{id}", root=True, op=...)`, recorded in `k.w["interventions"]` (never applied twice) and as a
monitor `intervention` event with a state-diff digest. `--notice` and `--live` become thin wrappers. A `python` op is the recorded
escape hatch. Runner state becomes one `RunState` object checkpointed whole and addressable by ops.

### 8.4 Fork, rewind, replay, replicates

```
charter fork RUN --at N [--apply iv.yaml] [--replicates K] [--replay strict|prompt-match|none] [--code current|parent]
charter rewind RUN --to N          # a fork with no interventions; never destroys the parent
charter replay RUN [--until N]     # must reproduce events.jsonl byte for byte from calls.jsonl
charter branches RUN               # lineage tree from run.json parent pointers
```

A fork copies the instance and the log prefixes to the round-N offsets, restores `checkpoints/r(N-1)`, applies the schedule, and
runs with `Replay(parent.calls, until=N, live=policy)`. Replicates differ only in post-fork sampling. Provenance records the code
version per segment (exists) and both shas under `--code current`; replay equivalence is not claimed across code versions.
`rng_version: 2` (P5.3) is the prerequisite for clean intervention contrasts.

---

## 9. Goals and scoring

- Each goal is a `Goal` row (§3.9). `score(history, agent, params, ctx)` is an arbitrary function of the full run history; it may
  read the live kernel only through its own declared `probes`, which the runner records each round.
- `text` and `rule` come from the same row; the rule is shown to the agent verbatim after the text, printed in reports and used as
  the scorer's docstring. Global timing sentences ("computed from the final state", the lineage sentence) are deleted.
- The scoring pass: `score_agent(h, agent, ctx)` splits by goal-held spans (today's rule), passes `h` and the span through `ctx.at`,
  combines slots (drop `None`, renormalise) and spans (rounds-weighted). Death no longer ends a span; each goal decides what death
  means. The global lineage override goes; lineage is a scope in the goals that say so.
- `Ctx.score_of(agent, slot, span)` memoises cross-agent goals (Spoiler, Ally, Foil, Mirror) with a cycle guard.
- Institution goals score structural signatures from History (review 06 §7); emergence studies use goal-free arms.
  As built (P6.4): `goal_registry.INSTITUTION` (Company, Bank, Insurer, Cartel, Protection racket; scorers in
  `institution_goals.py`), kept out of `GOALS`/`CATALOGUE` so no draw, prompt or golden changes; never drawn unless
  `goals.institution_share` > 0 (out of Wealth's share, where each goal's modules are on) or assigned with `goals.explicit`
  (names and params validated with did-you-mean). Each is about "an association you founded" (best one) or, with param
  `contract`, about one named association; param `scoring: partial | all` (mean of components, or all-or-nothing). The agent is
  shown the text then the rule (`goal_registry.shown`). History gains `foundings`, `accounts(r)`, `account`, `members`,
  `membership`, `founded_by`, `treasury`, `treasury_value`, `treasury_key`, `account_laws`, `payments`, `receipts`,
  `deductions`, `breaches`, `funds`, `rulings`, `losses` (all window-aware; `foundings` survives a window).
- Per-goal versions in `score.json`; old scorers stay importable by version for rescoring.

---

## 10. Interfaces implementers must honour

Signatures are Python; "→ G*" marks interfaces owned by an in-progress groundwork branch (reconcile on merge, the merged names win).

**Kernel and dispatch**

- **I-1** `Kernel.apply(self, name: str, /, **payload) -> Outcome`; raises `PhysicsError(reason: str)`. Callers convert:
  `ActionError` in action handlers, `LawError` in law functions, a logged `kernel_refusal` in phases and interventions.
- **I-2** `@dataclass(frozen=True) class Outcome: ok: bool; result: dict = {}; blocked_by: tuple[str, ...] = ();
  charges: tuple[Charge, ...] = (); refused: str | None = None` and
  `class Charge: law: str; payer: str; item: str; qty: float; dst: str`.
- **I-3** `Kernel.cause(kind, id, *, root=False, **meta)` context manager; `Kernel.chain(viewer=None) -> tuple[dict, ...]`
  (→ G3 for `cause`; `root` and `chain` added by P2.1).
- **I-4** Event shape: `{"id", "round", "type", "agent", "data", "vis", "cause", "chain"}` (→ G3). `data` stays type-specific.
- **I-5** `primitives.PRIMITIVES: dict[str, Primitive]`, `primitives.get(name) -> Primitive` (raises `UnknownPrimitive`),
  `primitives.ALIASES: tuple[HookAlias, ...]`, `primitives.HOOKS: dict[str, HookRow]`.
- **I-6** `dispatch.Cascade`, `dispatch.Invocation`, `dispatch.Meter` with `enter(inv, cas, account)` and `charge(n)`;
  `dispatch.resolve(k, P, payload, verdicts) -> Decision(block, blocked_by, reason, charges, directives)`;
  `dispatch.drain(k, cas)`; `dispatch.flag(k, lid, kind, cascade) -> None`.
- **I-7** Law hooks: `before_<p>(p: dict, chain: tuple) -> None | bool | float | dict`, `after_<p>(p: dict, chain: tuple) -> Any`;
  verdict dict keys `block, charge, reason, exempt` plus the primitive's `directives`. Clock `on_round_start(r)`, `on_round_end(r)`;
  lifecycle `on_enact()`, `on_repeal()`; legacy names with today's signatures.
- **I-8** Spec block `law: {v2: bool=false, atomic_hooks: bool=<v2>, notify_parties: bool=<v2>, previews_per_turn: 3,
  gas: {per_call: 10000, python_depth: 20, per_cascade: 100000, per_account_round: 1000000, depth_cap: 8, hook_cost: 20,
  prim_cost: 5, preview: 300000, flag_limit: 3, flag_window: 5}, gas_price: null}`.

**Law language, linker, law API**

- **I-9** `lawlang.check(code) -> ast.Module` (unchanged contract); `lawlang.static_info(tree) -> dict` with keys
  `calls, hooks, rights, imports, exports, rank, title, intent`; `lawlang.instrument(tree) -> ast.Module`;
  `lawlang.classify(tree, imported: list[ast.AST] = ()) -> str` (transitive).
- **I-10** `linker.parse_ref(ref: str) -> (kind: "law"|"lib", id: str, sha: str | None)`;
  `linker.link(k, importer: str, ref: str) -> Mapping[str, Any]`; `linker.code_store(k) -> dict[sha, code]`;
  `linker.dependents(k, lid) -> list[dict]`; `linker.on_amend(k, lid, old_sha, new_sha)`; `linker.on_repeal(k, lid)`.
- **I-11** Law record additions: `rank: str`, `version: int`, `code_sha: str`, `versions: list[{v, sha, round, via, by}]`,
  `public: dict`, `flags: list[{round, kind, cascade}]`, `imports: list[{ref, mode, sha}]`, `account: str`.
- **I-12** New law API names: `use(ref)`, `public_of(lid)`, `law_id()`, `treasury()`, `root_kind(chain)`, `caused_by_agent(chain)`,
  `caused_by_law(chain, lid)`, `chain_laws(chain)`, `propose_law(code, intent=None)`, `propose_amendment(target, code, reason)`,
  `set_conflict_rule(rule)`, `set_procedure(law_class, fn, rank=None)` (extended), `event(eid)`, `history(type, agent, since,
  limit)`; each with a `LawFn` row and a lawdocs entry.
- **I-13** `lawapi.LawFn` fields as §3.6 (→ G2 for `cls`, `module`).

**Accounts, powers, contracts**

- **I-14** `accounts.account_of(k, lid) -> str`, `accounts.treasury_of(k, account) -> str`, `accounts.binds(k, account, aid) -> bool`,
  `accounts.kind(k, account) -> str`.
- **I-15** `powers.POWERS`, `powers.LEVEL_PRESETS`, `powers.has_power(k, account, power) -> bool | str`.
- **I-16** Contract actions: `create_contract {name, code?, template?, params?}`, `join {contract}`, `leave {contract}`,
  `deposit_escrow {contract, item, qty}`, `set_allowance {contract, item, qty}`; law functions `pull(member, item, qty)`,
  `contract_state(cid)`, `contracts()`, `breaches(cid=None)`, `breach(member, clause, remedy)`.

**Previewer**

- **I-17** `preview.preview(k, code, *, requester, jurisdiction=None, amends=None, scenarios="default", rounds=3) -> dict` with keys
  `static, procedure, enact, scenarios, rounds, warnings` (review 09 §10); action `preview_law {code, jurisdiction?, amends?,
  scenarios?}` (pre-action, private result).

**Registries**

- **I-18** `eventtypes.EventType`, `EVENTS`, `get(name)` (→ G1); field `primitive` added by P1.7.
- **I-19** `action_registry.Act` fields as §3.4; `action_registry.rows(module=None)`; `resolve(handler: str) -> Callable`.
- **I-20** `features.Feature`, `FEATURES`, `PHASES`, `features.get(name)`, `features.on(name, x) -> bool`; module fixed names and
  signatures as §3.1.
- **I-21** `schema.validate(spec) -> list[str]`, `schema.defaults(feature) -> dict`, `schema.runtime_safe(path) -> bool`.
- **I-22** `sections.Section`, `sections.section(key, **kw)` decorator, `sections.render(layer, view, budget=None) ->
  list[tuple[str, str]]`, `sections.View`, `sections.view(inst, k, a) -> View` (memoised per agent-round).

**Goals and History**

- **I-23** `goal_registry.Goal` as §3.9; `GOALS`; `get(name)`; `score_agent(h, agent, ctx) -> dict`; `Ctx.score_of(agent,
  slot="primary", span=None)`; `Ctx.at(span) -> Ctx`.
- **I-24** `History` as §8.2 (→ G5 for the base; `caused`, `by_cause`, `law_versions`, `accounts` added by P6.x/P4.x).

**Run store, interventions, replay**

- **I-25** `interventions.Op`, `OPS`, `op(name, *, phases, args, primitive=None)` decorator; `apply_due(k, inst, rs, phase,
  agent=None) -> list[str]` (ids applied); schedule entry `{id, at: {round, phase, agent?}, op, args, announce?, announce_to?,
  note?}`; record `{id, round, phase, op, args, note, diff}`.
- **I-26** `runner.RunState` with `notes, cursors, results, sysp, agents, schedule, policy_state`; `RunState.to_dict()`,
  `RunState.from_dict(d)`.
- **I-27** `CallKey(round, agent, phase, wave)`; `Replay(calls, live=None, until=None, strict=True)` with
  `act(k, a, system, user, n, final, key)` (→ G6).
- **I-28** Differential harness: `difftest.run_pair(preset, seed, rounds, sets=(), old_ref, new_ref, normalise=default) -> Report`
  where `normalise` drops `cause`/`chain` and keys listed by the package (→ G4).
- **I-29** `run.json` keys added: `features_on: [str]`, `law: {v2, atomic_hooks, notify_parties}`, `rng_version`,
  `library: {edition, access}`, `goals: {name: version}`, `parent: {run, round, branch} | null`, `replicate: int | null`.

---

## 11. Phased work plan

**Golden policy.** Four kinds of fingerprint exist: *world* (events and snapshots of the golden dry runs), *instance*, *prompt*
(system prompts and manuals, `PROMPT_CASES`) and *score*. "Behaviour-preserving" means all four are byte-identical **and** the
differential harness (G4) reports no difference on every preset in `charter/specs/` it supports (normalising only `cause`/`chain`). A
"behaviour-changing" package names exactly which fingerprints it re-records and why, in the commit message, and re-records nothing
else. New features add a new golden case rather than changing old ones; old cases keep `law.v2: false`, `rng_version: 1`,
`library.edition: 1`.

**Concurrency rule.** "Files owned" are the files a package may restructure. Other packages may make one-line edits in them (an
import, a derived constant) but must not restructure them. `kernel.py` is split by region: lifecycle (`__init__`, `start_round`,
`end_round`, `snapshot`) belongs to P1.2; `move/log/api_for/laws/hooks/dry_run/view` to the P2 series in sequence.

### Phase 0: groundwork in progress (G1-G6)

As listed at the top. Everything below that names them depends on their merge; packages marked **start now** do not.

### Phase 1: registries and the contract (behaviour-preserving unless noted)

| Id | Scope | Files owned | Depends on | Acceptance | Golden |
|---|---|---|---|---|---|
| **P1.1** **start now** | Complete `Act`: `handler, doc, category, module, emits, primitives, aliases, legacy`; derive `ACTIONS`, `DM_ACTIONS`, `ACTION_DOC`, `CATEGORIES`; delete the 46 trampolines; strict category test | `action_registry.py`, `actions.py` (dispatch, trampolines), `scorer.py` (categories), the `ACTION_DOC` definition in `agents.py` | none (`emits` checked once G1 merges) | set equalities `REG == ACTIONS == ACTION_DOC`; every action has an explicit category; unknown-action error lists names in the old order | preserving: all four identical |
| **P1.2** **start now** | `features.py`: `Feature` rows, `on()`, `state`, `rng`, `golden`; the 10 enabled helpers delegate; `PHASES` with `init`, `round_start`, `round_end`, `after_turns`, `death`, `birth`; kernel lifecycle as loops in today's order; `law_api`, `snapshot_fields`, `state_lines`, `truth`, `render_event` tails as loops | `features.py` (new), kernel lifecycle region, `runner._truth`, `agents.state_view`, `mortality.disable` (death phase), module helper bodies (one line each) | none | snapshot key order identical; death phase order test; `Feature.on` agrees with every old helper on every spec in `charter/specs/` | preserving |
| **P1.3** **start now** | Spec schema: `DEFAULTS` per feature as the single source, `schema.validate`, did-you-mean errors, `runtime_safe` marks; `base.yaml` gains no keys code does not know | `schema.py` (new), `spec.py`, `generator.py` (call validate), `charter/specs/base.yaml` | none (uses module `DEFAULTS` directly until P1.2) | every spec in `charter/specs/` validates; misspelt keys (`agents: {workr: 3}`, `models.mix: balancd`) fail with a suggestion | preserving (instance identical) |
| **P1.4** **start now** | Legal-system bug fixes: F1 (a law calling `repeal` is structural; law-caused repeal of a law with a stricter class is refused); `set_official_editor` scope per D-3 | `lawlang.py` (classify), `kernel.py` `repeal`, `lawapi.py` row | none | regression tests: an ordinary law cannot repeal a procedural law; `classify` of `repeal + gazette` is structural | preserving for goldens (no golden law calls `repeal`); behaviour change recorded for agent-written laws |
| **P1.5** | Goal registry generated from today's tables, with `text`, `rule` (describing today's scorer faithfully), `score` wrapping legacy `s_*` through `legacy_gt(h)`, `version=1`; derived old names | `goal_registry.py` (new), `goals.py`, `life.py` (`HISTORY`), `roles.py` (`HAVOC_REFUSAL`), `events.py`/`generator.py` (text assembly) | G5 | `assert set(GOALS) == set(CATALOGUE)`; draw RNG consumption identical | preserving: instance and scores identical (rule text not yet shown to agents) |
| **P1.6** | `Section` model and per-feature `facts`; core prompt, manual, legacy prompt and observer prompt as renderings; perturbation test (review 02 §4.5) | `sections.py` (new), `context.py`, `manual.py`, `composition.py`, `agents.py` (prompt functions), `facts.py` | P1.1 (agents.py), P1.2 | prompt fingerprints identical; perturbation test green | preserving (prompt fingerprints identical) |
| **P1.7** **start now** | `primitives.py` metadata for the §3.3 catalogue (no behaviour), `HookAlias` table, derived `lawlang.HOOKS`, `LawFn.primitive`, `EventType.primitive`, completeness test with `KNOWN_GAPS` | `primitives.py` (new), `tests/test_charter_contract.py` (new), `lawlang.HOOKS` line | stubs against G1/G2; finalise after they merge | contract test passes with a frozen `KNOWN_GAPS` | preserving |

### Phase 2: the primitive layer (behaviour-preserving; the differential harness is the gate)

| Id | Scope | Files owned | Depends on | Acceptance | Golden |
|---|---|---|---|---|---|
| **P2.1** | `Kernel.apply`, `dispatch.py` skeleton (canonical order, legacy aliases, charges to `J.home_reserve` until P4.1), `chain()`, root frames; route core primitives: `move, harvest, mint, burn, create_currency, grant_right, revoke_right, suspend_right, limit_actions, create_right, post, dm, hide_post, set_camp_rule, set_dm_limit` | `kernel.py` (move/log/api_for/hooks), `dispatch.py` (new), `primitives.py` (fns), `actions.py` call sites of those primitives | G1, G2, G3, G4, P1.7 | differential harness clean on every preset; hook call order identical (a test logs every hook invocation in both versions) | preserving |
| **P2.2** **start now** | Gas v2: AST instrumentation, size-charged builtins, meter stack (call, cascade, account), depth cap plumbing; `Limited` kept as a thin wrapper | `lawlang.py` (Limited, load_module, new `instrument`), `dispatch.py` meter part (coordinate with P2.1; land first if ready) | none | `test_step_limit_and_recursion_depth` unchanged; new tests: `sum(range(10**8))`, `"a" * 10**8`, `7 ** 10**8`, a comprehension over a huge range all stop with a `LawError`; tick counts identical across two Python versions in CI if available | preserving for goldens; behaviour change only for pathological laws |
| **P2.3** | Legal-act primitives: `propose, decide, open_ballot, cast_vote, close_ballot, veto, enact, repeal, amend (Fixer patch), set_procedure, rule, define_action` with payloads (review 09 §5); `on_proposal` alias keeps `None`; `on_vote`, `on_ruling` aliases | `kernel.py` (laws, ballots, veto queue, patches), `actions.py` (`_propose`, `_vote`, `_veto`, `_patch`, `_rule`), `jurisdictions.py` (`propose`, `decide`, `passed`) | P2.1 | differential harness clean; payload samples JSON round-trip | preserving |
| **P2.4a** | Conflict: `attack`, `fortify`, `convert` (forge), `guard_bind/release`, `end_life` by attack/assassin/accident; direct `_add` writes in conflict.py through primitives | `conflict.py` | P2.1, P2.4b (`end_life`) | harness clean on `conflict_pilot`, `society` | preserving |
| **P2.4b** | Life and mortality: `begin_life`, `end_life` (all causes incl. `departure`), estate account with internal journaled writes, probate step = today's bequest; `death`/`birth` phases | `mortality.py`, `life.py`, `events.py` (arrival/departure call sites) | P2.1, P1.2 | harness clean on `life_pilot`, `society`; departure keeps frozen holdings | preserving |
| **P2.4c** | World causes: outside raids and tribute, blights, drift, regrowth (`regrow` unblockable), projects escrow, credit (loans, seizure as `move`/`seize`) | `outside.py`, `events.py` (world events), `projects.py`, `credit.py`, `camps.py` | P2.1 | harness clean on every preset | preserving |
| **P2.4d** | Typed camps and leases; jurisdictions membership (`join, leave, admit, expel`) with `on_admission/on_exit/on_birth` aliases; media `subscribe`, outlets (editions stay outputs); roles and hidden rights writes through `grant_right`/`revoke_right` | `camptypes/*`, `jurisdictions.py` (membership), `media.py`, `roles.py`, `hidden.py` | P2.1 | harness clean; the 36 direct writes of review 04 gone (grep test) | preserving |

### Phase 3: legal system v2 (behaviour-changing, behind `law.v2`, default off)

| Id | Scope | Files owned | Depends on | Acceptance | Golden |
|---|---|---|---|---|---|
| **P3.1** | New-style `before_*`/`after_*` hooks from any cause; cascades, FIFO after-queue drained at root exit; redacted chains to laws; R1-R5; halting points; flags and escalation; `law_flagged`, `cascade_halted`, `account_out_of_gas` events; law reads `root_kind` etc. | `dispatch.py`, `kernel.py` (root frames), `lawdocs.py` (hook docs) | P2.1, P2.2, P2.3 (P2.4 for world-cause coverage) | unit tests for each rule and halting point; worked examples 13.2 and 13.3 of review 09 as tests; determinism: two runs identical; replay identical | new golden case `society_law_v2` (3 rounds); old goldens untouched |
| **P3.2** | Rank, lex superior, procedures per rank, canonical order across accounts, conflict rules (`any_block`, `superior`, `posterior`, function) | `dispatch.py` (resolve), `kernel.py` (procedures lookup), `lawlang.py` (rank constant), `jurisdictions.py` procedure lookup | P2.3 | example 13.1 as a test; a statute cannot repeal a constitution; `superior` resolution table tests | v2 golden only |
| **P3.3** | Linker: `exports`, `use`, `public`/`public_of`, code store, versions, dependents, auto-pin, transitive classification, static rules | `linker.py` (new), `lawlang.py` (static rules), `kernel.py` (`_load`, checkpoint of links) | P2.2, P2.3 | example 13.4 as a test; confused-deputy test (imported function acts under importer's binding); cycle and size limits; checkpoint/restore with links | v2 golden only |
| **P3.4** | Amendment: agent action `amend`, law functions `propose_law`, `propose_amendment`; amendment class over dependents | `actions.py` (`_amend`), `action_registry.py` row, `kernel.py` (`amend`), lawdocs | P3.2, P3.3 | amendment keeps id, state, public, sequence; dependents relinked; procedure chosen by max class/rank | prompt fingerprints for v2 presets only |
| **P3.5** | Previewer and `preview_law` pre-action | `preview.py` (new), `action_registry.py` row, `context.py` pre-action plumbing | P3.1 (P3.2/P3.3 enrich it) | report shape test; visibility test (hidden laws absent); transaction leaves state identical | prompt fingerprints for v2 presets only |
| **P3.6** | Atomic invocations: journal helpers, rollback of state/public/module data, event-suffix truncation, `hook_aborted` | `dispatch.py` (journal), `kernel.py` (`j_set` helpers), every law-function writer | all of P2.4 | generic killed-invocation test over every writer `LawFn` | v2 golden only |
| **P3.7** | Compel visibility per D-5 (`compelled` events to parties for law-caused changes on non-consenting agents) | `dispatch.py`, `eventtypes.py` rows, renderers | P2.1, G1 | every `compel_vis="parties"` primitive notifies its parties when law-caused | v2 golden only (gated by `law.notify_parties`) |
| **P3.8** | Gas billing to treasuries (`law.gas_price`) | `dispatch.py`, `kernel.py` round end | P3.1, P4.1 | accounting test | none (off by default) |
| **P3.9** | Library v2: `lib:*` building blocks (escrow, schedule, seize, ledger, ballot helpers, tax schedules) and readable implementations of today's laws (Loan Registry = escrow + scheduled repayment + seizure); `library.edition`, `library.access`; v1 kept for old specs | `library.py`, `regimes.py` (references) | P3.3 (P4.3 for contract templates) | each v2 implementation's behaviour matches v1 on a scripted scenario where both exist (or the difference is documented) | new golden for edition 2 |

### Phase 4: accounts, contracts, the power table

| Id | Scope | Files owned | Depends on | Acceptance | Golden |
|---|---|---|---|---|---|
| **P4.1** | Account `kind` on every jurisdiction record (`polity`); `accounts.py`; per-law charge destination | `accounts.py` (new), `jurisdictions.py` (`_new_j`), `dispatch.py` charges, `actions.py` `_send/_harvest` caps | P2.1 | harness clean | preserving |
| **P4.2** | Power table as data for polities: Board veto, Fixer patch, levels (presets), dry run, kernel rights, compulsion, legacy reserve; `scope_api` and the kernel consult `has_power` | `powers.py` (new), `lawapi.py` (`power` column), `jurisdictions.py` (`scope_api`, `board_reviews`), `kernel.py` (`passed`, veto queue), `actions.py` (`_propose` level check) | P4.1, G2 | harness clean on every preset, jurisdictions on and off | preserving |
| **P4.3** | Associations v1 (review 06 §3, as amended in §7.2): records, many-to-many membership, contract actions, escrow and allowances, `pull`, power set via `LawFn.contract`, error path without the Fixer, exit rules, templates (club, company, crowdfund, cartel) | `contracts.py` (new), `accounts.py`, `jurisdictions.py` (binding/hooks branch on kind), `action_registry.py` rows, lawdocs, a manual Section | P4.2, P3.1 | power-set tests (allowed and denied per function); exit test; contract error does not reach the Fixer | new golden `contracts_small`; feature off by default |
| **P4.4** | Enforcement dial (`escrow | escrow_court | word`), breach record, `contracts()/breaches()` reads, library law "Contract Enforcement Act" | `contracts.py`, `library.py` | P4.3 | dial tests | contracts golden |
| **P4.5** | Shares (backed currency on a treasury), agency (`authorize`, every use logged `{grantor, grantee, auth}`; `vote` not authorizable by default), standing orders and scripts as templates with a compute cost | `contracts.py`, `kernel.py` (`has`/`move` authorization check), `library.py` | P4.3 (P3.9) | agency scope tests | contracts golden |
| **P4.6** | Later milestone: jurisdictions (including J0) as contracts, review 06 §9.3 steps 1-7 | `jurisdictions.py`, `kernel.py`, `accounts.py`, `actions.py` | P4.2-P4.4, a contracts pilot, G6, `STATE_SCHEMA` 2 | harness clean on every preset after normalising the new keys; checkpoint migration of old runs | one re-record of world goldens for the new state keys, stated in the commit |

### Phase 5: the instrument

| Id | Scope | Files owned | Depends on | Acceptance | Golden |
|---|---|---|---|---|---|
| **P5.1** | `RunState`; `interventions.py` with the §3.12 ops; schedule loading; `--notice`/`--live` as wrappers | `interventions.py` (new), `runner.py`, `__main__.py` | G3, G6 (P2.1 for ops via `k.apply`; start with kernel functions) | one test per op; resume after an intervention does not re-apply it | preserving for runs without interventions |
| **P5.2** | `fork`, `rewind`, `replay`, `branches`, `--replicates` | `__main__.py`, `replay.py`, `provenance.py` | G6, P5.1 | fork with an empty schedule under strict replay reproduces the parent's suffix | none |
| **P5.3** **start now** (merge after G4) | `rng_version: 2`: order, harvest, drift and per-law streams | `kernel.py` (rng sites), `runner.py` (turn order), `actions.py` (harvest noise), `generator.py` (core draws) | G4 | `rng_version: 1` identical under the harness; v2 goldens added | new v2 goldens only |
| **P5.4** | Shared archive frozen per run (base snapshot + overlay), sandbox outputs as blobs replayed by `Replay` | `archive.py`, `runner.py`, `replay.py` | G6 | replay of a Scientist run reproduces reads | none |
| **P5.5** | Export tables (runs, agents, rounds, events with causes, calls, laws and versions, interventions, state deltas) | `export.py` (new), `__main__.py` | G5, P5.2 | schema test on a golden run | none |

### Phase 6: goals

| Id | Scope | Files owned | Depends on | Acceptance | Golden |
|---|---|---|---|---|---|
| **P6.1** | Port scorers to `score(h, agent, params, ctx)` with `h.window`, `Ctx` for cross-agent goals | `goal_registry.py`, `goals.py`, `scorer.py`, `events.py` (segments) | P1.5 | per-goal `examples`; score golden identical except listed leak fixes (review 05 §3.1) with `version=2` | score goldens re-recorded with a per-goal diff list |
| **P6.2** | Probes and role holders per round; `PREDICATES` become goal probes | `runner.py`, `library.py` (predicates), `roles.py` | P1.2, P1.5 | probe values equal old predicate values | world goldens re-recorded (snapshot key layout) |
| **P6.3** | Rule text shown to agents; delete global timing sentences; owner's per-goal decisions (D-1, D-2) | `goal_registry.py`, `context.py`/`sections.py`, `life.py` | P6.1, P1.6, owner decisions | rule non-empty for every goal; prompt shows text then rule | prompt and score goldens re-recorded |
| **P6.4** | Institution goals (company, bank, insurer, cartel, protection) | `goal_registry.py` | P4.3, P6.1 | examples on synthetic histories | none |

### Phase 7: text

| Id | Scope | Depends on | Golden |
|---|---|---|---|
| **P7.1** | Legacy (context-off) prompt per D-4: freeze as-is (default) and stop adding to it | P1.6 | none |
| **P7.2** | `charter preview <spec> --seed N` replaces the committed `prompt_preview.md`; Leaker's common text from rendered sections (scoring change, versioned) | P1.6, P6.1 | score golden for Leaker only |

### What can start immediately

P1.1, P1.2, P1.3, P1.4, P1.7 (against G1/G2 stubs), P2.2, P5.3 (code now, merge after G4). As soon as G5 merges: P1.5. As soon as
G1-G4 merge: P2.1, then P2.3 and the P2.4 packages in parallel (P2.4b first, since P2.4a uses its `end_life`). As soon as G3 and G6
merge: P5.1.

Critical path to the owner's legal-system goals: G1-G4 → P1.7 → P2.1 → P2.3 → P3.1 → (P3.2 ∥ P3.3) → P3.4 → P3.5. Critical path to
contracts: P2.1 → P4.1 → P4.2 → P4.3 (needs P3.1). Critical path to forks with interventions: G3 + G6 → P5.1 → P5.2, with P5.3.

---

## 12. Open decisions for the owner (each with the default work proceeds on)

| # | Decision | Default |
|---|---|---|
| D-1 | Per-goal scoring rules (timing, death, descendants, denominators) | Review 05 §4.5 table: own-state goals (Wealth, Rank, Hoard, Power, Office, Sovereign) at the end, self only, "0 if you are not in the game at the end"; averaging goals over held rounds including after death; counting goals within held rounds; Lineage goals keep lineage; drop the global lineage override and `score_at_end`; fix the Rank and Board texts to match the scorers |
| D-2 | Saboteur (its `paired_welfare` input is never produced, so it always scores `None`) | Score it from History as the relative fall in system welfare over the rounds the goal was held, `clip(1 - welfare(end of span) / welfare(start of span), 0, 1)`, rule text stating exactly that, `version=2`. Counterfactual (paired-fork) scoring stays possible later with P5.2 replicates |
| D-3 | `set_official_editor` scoping (today `scope="none"`) | The appointee must be bound by the law (`scope="bound"`, `refused=False`): a law can only appoint a member as its jurisdiction's editor |
| D-4 | Freeze the E-series (context-off) prompts or re-render them from Sections | Freeze as-is behind a byte snapshot test; new features appear only on the context path; revisit when E0-E7 runs are no longer planned |
| D-5 | Do law actions on others notify the affected agents (compel visibility)? | Yes for new worlds: law-caused changes to a non-consenting agent (fines, moves from them, suspensions, obligations, compelled subscriptions, deaths by law) log a `compelled` event visible to the parties, with the law id; `law.notify_parties` defaults to `law.v2`, so old goldens are unaffected |
| D-6 | A before-hook that dies: abstain or block? | Abstain. A constitution-rank law may declare `fail_closed = True` to make its legal-act reviews block when they die |
| D-7 | Atomic hook invocations (rollback on death) | On for `law.v2` worlds; off for legacy (today: effects before an error stand) |
| D-8 | Following imports when the imported law is repealed or loses an export | Auto-pin to the last satisfying version, public `import_pinned` event |
| D-9 | Departures from world events as `end_life(cause="departure")` | Yes: one primitive; departure keeps today's effects (frozen holdings, no bequest) |
| D-10 | May laws block entrenched powers (Board veto, Fixer patch)? | No, until the charter-rank milestone expresses the Board as a kernel-seeded rank-4 law |
| D-11 | Previews: visible legal system only, or all laws including hidden jurisdictions'? | Visible only for `preview_law`; the proposal-time dry run keeps today's behaviour |
| D-12 | Gas budget numbers; billing gas to treasuries | Defaults in I-8 (`per_call` = today's 10,000); billing off |
| D-13 | Default conflict rule | `any_block` (today's semantics); constitutions may switch |
| D-14 | Freeze the shared archive per run (needed for exact replay) | Yes for new runs (P5.4); cross-run publishing becomes an explicit end-of-run step |
| D-15 | Contract treasuries in Wealth | Count 0, except through shares (backed currency) priced at net asset value, as `price()` already does |
| D-16 | Lowest law level at which laws may propose laws or amendments (`propose_law`, `propose_amendment`) | L3 |
| D-17 | Templates condition default | `library.access: catalogue` (agents read library code and copy it); `instantiate` (one-call templates) is a treatment arm |
| D-18 | Are hook traces shown to agents? | The affected agent sees blocks and charges with the law id and reason; reactions appear as their own events; full traces only through `preview_law` |
| D-19 | `rng_version: 2` for new runs | Yes; v1 stays loadable and is used by all existing goldens |
| D-20 | Gas counting method | AST instrumentation (deterministic across Python versions) |
| D-21 | `on_proposal` payload for old-style laws under `law.v2` | Keep `None` for the alias; the payload is available through `after_propose` / `before_propose` |
| D-22 | `publish` and `set_dm_limit` dropped from the edge in the registry wiring (README) | Confirm as wired |
| D-23 | Maker access: role or right | The role is the source of truth; `maker` and `scholar` stay role-bound rights (not grantable by law), as `rights.py` now encodes |
| D-24 | Can a contract (association) hook its members' legal acts in their polity? | No: associations hook only their own legal acts and their members' non-legal primitives |
| D-25 | Kernel scope (review 12) | The kernel holds only physics (P), epistemics (E) and the experimental contract (X); every rule two real legal systems differ on (L) becomes a default law ("default code") each regime seeds, readable and amendable; existing presets seed today's behaviour and stay byte-identical (user, 8 Oct) |
| D-26 | Exit from a polity | Law, with no kernel bound: a Nationality Act sets it (free, taxed, delayed, permitted, banned); post-exit sanctions only through agents (laws may pay bounties, never act). Supersedes review 12's "bounded" default (user, 8 Oct). Exit from a contract stays guaranteed (proposed; awaiting confirmation) |
| D-27 | Contract defaults in the kernel (W7a/P4.3-4.5) | Move to law: share valuation (Kernel.price NAV branch), wind-up order (shareholders pro rata, then members), the built-in procedures (become library procedures), per-contract limits, the contract column beyond physics, the enforcement dial, breach visibility, member liability, the agency action list (except "never votes"). Kernel keeps accounts, escrow, allowances, atomic swap, exit, "laws never act for an agent" (user, 8 Oct). W8e moved the first four (and the enforcement dial, per parent) (§7.2 "Incorporation") |
| D-28 | Incorporation | Proposed: contracts may be founded under a polity (`parent`); the parent's company law outranks the contract's code and grants benefits (courts, recognition of offices, liability rules); unincorporated contracts remain. Wave 8, with the Board port (shared nesting machinery). W8e implements it (§7.2 "Incorporation"): `under`, company rules, parent-first binding and conflict rule; member liability deferred |
| D-29 | V18: what new-style hooks may read | A law never reads a DM's text unless conditions.law_reads_dms and the DM is unencrypted, nor a private channel post's text (dispatch.hook_payload); metadata (who, to whom, where) stays visible pending the publication layer (review 12) |
| D-30 | Review 12's decision list | Adopted as recommended (user, 8 Oct): Board Charter with per-regime entrenchment (presets: entrenched, readable); Fixer stays X; kernel private by default with presets seeding a Publication Act that reproduces today; surveillance only within a world technology dial (law_reads_dms, channels.readable), encryption never broken; world events: laws regulate consequences only; prompt: one line per Act plus the legal digest; Land Registry Act seeded everywhere for now; dry run stays X; residual proposing rule: every member; default code runs as native code without gas until amended, ids A1..An. Exception: polity exit per D-26 (law, unbounded), not review 12's bounded default |
| D-31 | Dispatcher layout (W8a, before review 12's WP1) | `charter/dispatch/` is a package of modules by concern (§2) and `changes/` by domain, re-exporting every old name; a primitive is routed by its row's `routed` flag, so WP1 may name an owner module's function as `fn`; every v1/v2 fork is listed in `dispatch.base.V2_SEAMS` (checked against the source); every primitive row and every review 12 inventory item carries a tier (`primitives.TIER_OF`, `charter/tiers.py`) |
| D-32 | `lawful_attack` (a law makes a member attack: breaks "laws never act for an agent", logged monitor-only) | Replace with an authorization: a law may authorize or pay a member to attack (bounty pattern; agency-style record), the member chooses to act; the order and the attack are attributed and published per the publication layer (user, 8 Oct). Wave 8c |
| D-33 | Media and press | Not a fixed role: outlets, channels, editorship and licences are law-granted rights over forms of channel. Residual (no Act): anyone may found a channel or outlet; an Association Act and a Press Act seed today's preset behaviour (press right gates, two media roles) and are amendable. Benchmark findings that depend on today's contingent media setup (e.g. "only two press holders") are preset artefacts, not platform facts (user, 8 Oct) |
| D-34 | Default code framework (W8d, review 12 WP3) | `charter/code/`: an Act is law-language source plus a native twin; store-based Acts set rows in `k.w["default_code"]["store"][polity][Act]`, read at today's seams by `code.rule(k, polity, act, key, default)` (code off: the default; Act absent or repealed: its residual). Acts A1..An are seeded at round 0 before the constitution (author `code`, not in `law_order` while native, one monitor-only `code_act` record each); an amendment switches an Act to its source (ordinary law in the enactment order), a repeal empties its rows. Selected by `regimes.FIELDS["code"]` or spec `code.select` (today, none, overrides); flag `code.enabled`, off by default. Delivered: Communications Act (A1), Court Rules Act (A2); template and checklist in docs/default_code.md |
| D-35 | No root (user, 8 Oct; review 14) | No world constitution: polities are roots of an institution tree; any institution can be founded under a willing parent; J0 is the root a preset seeds, its kernel privileges become default code; polities and contracts become one account kind (P4.6). Start worlds in a state of nature, not the #convention anarchy regime (frozen for old runs). W9 B: the anarchy constitution and regime are frozen (code comments; tests pin their bytes and the presets that may name them: full10, haiku100); the new-world state of nature is the `nature_design` preset (state_of_nature + contracts + the design arm + the S0 demography, with a void `nature` constitution); the convention is the Assurance Founding contract template (`library.CONTRACT_TEMPLATES`) |
| D-36 | Demography (user, 8 Oct; review 15 v2.1) | Lifespans absolute (not scaled by run length); founder ages iid from the stationary distribution; no population cap (carrying capacity from food/land/fertility is the only ceiling; a run-stopping budget guard for model cost); two-parent births priced to be doable; initial conditions set incentives and boom-bust or Malthusian dynamics must be possible outcomes, not smoothed away. S0 implements the demography part behind flags (defaults unchanged): `life.scale: none`, `life.age_structure: stationary` (`age_sampling: iid`), no cap with either unless `cap_mult` is set, `life.max_population` (budget stop, STOPPED.md), `life.default_heirs: children`, `life.audit_fixes`, `roles.maker_refill`; recommended settings in `charter/specs/fragments/demography.yaml` |
| D-37 | Institutions and channels (user, 9 Oct; review 14 §4.6, §7.1) | Institutions bind non-members only by force (or recognition by agents already bound); consent binds members. Allegiance clauses allowed when visible at join. Channels are one structure (owner, writer/reader selectors including address-as-capability, listing, sender identity, retention); DMs, squares, inboxes, presses, chambers and secret cells are templates. Every agent and institution has an inbox. Delivery pull by default for new worlds (DMs and own inbox pushed). Starting conditions are configuration, not a kernel state. Institutions as members postponed |
| D-38 | Continuity and succession (user, 9 Oct; review 14 §7.2) | Institutions do not die with their founder. Death, exit, expulsion, term end and removal make a vacancy the institution's code may hook; each office declares a succession rule (library clauses). Where the institution is silent the enclosing polity's law decides, nearest first (Succession Act; Dissolution and Escheat Act: polity, family or members); each polity law is mandatory or overridable. With no governing polity vacancies stay vacant and a dissolved institution's holdings are locked (spaceless worlds: goods and claims locked, rights released, channels read-only). Contracts end when no party is left; their code may say what a party's death does (default: its estate). Passing to estates is only ever polity law. Repeal abolishes the offices a law declared |
| D-39 | Subsistence (user, 9 Oct; review 15 S1-S3) | Food is physics: every eater (not the Board, Fixer or observer, U6) eats 1 food at round end, after the laws' on_round_end; hunger stages fed / hungry / starving with a hidden seeded hazard from the third missed meal (death cause `starvation`); 15% spoilage outside stores, 2% in them. The ration, hunger and spoilage are unblockable world rows (eat, hunger, spoil: tier P). Hunger gates actions (`Act.fed`), but **starving agents keep their vote** (the lead's U14: disenfranchisement by hunger would be a kernel rule; a polity may restrict it with the `hunger(agent)` read). Hunger is public and coarse (U2 b). Food camps (forest, fields, the hunt) are appended after every other draw and ignore `typed.open_classes`; who may sow or reap a plot is law (routed sow, reap; residual liberty, U1; the Tillers' Right Act is S6). Stores are accounts `store:<sid>` owned by an agent or an institution; only the owner takes food out. All behind `subsistence.enabled` (off: byte-identical) |
| D-40 | Two-parent reproduction (user, 10 Oct; review 15 S4) | `life.reproduction.mode`: makers (default, unchanged) / pairs / both (`charter/pairs.py`). A child needs two consenting parents (`conceive`: an offer, then the partner's matching call); both must be fed adults, not expecting, under `max_children`, and each pays food only (U5: 5 provisions held as the child's first food, 1 fee destroyed; own stores count). The routed `conceive` primitive is law (tier L: before_conceive may refuse or charge; laws see whether a goal is inherited, never which; set_birth_rules' max_children and banned_goals bind it). Gestation and childhood are fixed rounds (U7: 2 and 6; presets choose). The child's model is fixed by the spec (U8: the weak tier by default; "parents" optional). It counts in both parents' lineages (U9: `life.parents`). The offer may name the child's polity, one of the parents', accepted with it (U12; unnamed: their common polity, else none in a world begun in the state of nature, else the initiator's; the polity's on_birth still decides; `parents_of` read). Minors (2 actions; no conceiving, attacking, founding, proposing, voting) eat from their parents' food after the parents eat (U3); food from the parents is the investment ledger (U4). Children in gestation are heirs (`@children`, default heirs: U22, audit B4). No Makers under pairs. Children's goals (S5): a random primary; the goal both parents named is a provisional secondary, promoted to primary at maturity with p = 0.25 + 0.6 x clip((I - provisions) / (maturity x ration), 0, 1), I = food from the parents (U4); a promotion is a goal boundary (scored as two segments) |
| D-41 | Subsistence revised: forests, the hunt, store access (user, 10 Oct; review 19) | The ration stays automatic: no eat action or agent-facing step; `subsistence.eat_from_store` (off) lets it draw on the eater's own stores. Hunger stage changes are monitor-only events; agents see stages on the state-line roster. Food comes from forests, each with two stocks: plants (forage at once; logistic r 0.6 x a shared, persistent season; refuge 10%) and game (logistic r 0.2, 1% inflow, optional Allee threshold), K 7 and 10 food per agent. Hunting is the routed `hunt` primitive (L, before_hunt: closed seasons, territories): anyone hunts alone; hunters naming the same party hunt together and draw large (20) or medium (5) game with chances rising sigmoidally with party effort and game density, else small game; food per hunter peaks at a party of about 6 (diminishing returns). Fields are parked (`fields.enabled` false: no camps, no farm action, no prompt words); the weak_link hunt is gone; world events never destroy or blight a forest. Withdrawal from a store is the routed `withdraw` primitive: an institution's own code decides (before_withdraw, bound to its laws whoever acts; True admits), and when it says nothing only its officers may (dispatch.routing.RESIDUALS, a kernel default after the hooks); an agent's store, its owner. A Maker's child starts with 2 rations (the P-tier `provision` primitive). All behind `subsistence.enabled` (off: byte-identical) |

---

## 13. What not to change

- Plain-dict `k.w`; no state classes. Per-module string-seeded RNG streams. Explicit `vis=` on every `log` call; registries assert
  constraints but never supply visibility.
- The law language's grammar, its static whitelist and static classification by calls. Extend the API, not the grammar.
- The proposal-time dry run; the Board and the Fixer as kernel invariants (attached by the power table); "laws never act for an
  agent".
- `checkpoint_state`'s approach (re-execute law modules, restore data globals, marshal callbacks, rebind).
- Post-hoc scoring from the run directory; segment splitting by goal change; `None` means "not computable".
- `composition.apply` semantics, the turn layers, the `lawdocs` tier model, `camptypes/`'s package structure.
- Golden tests and resume-equivalence tests; add harness, replay and fork tests beside them.
- No rewrite, no plugin framework, no event bus, no `features/` package, no decorator-driven order for anything order-sensitive.
