# Review 08: the feature contract (primitives, law and registries)

*7 Oct 2026. Read-only, at `main` = `f56d387` (rights, lawapi, facts and provenance merged). Line numbers are for that commit. No
runs. Two claims were checked in memory (`render_event` on synthetic events, `generator` start_laws check); everything else is from
reading. Legend for §2: **R** registered (a table a test checks), **P** partly registered, **H** hand-wired call or hand list,
**M** a feature-local mechanism no central test sees, **X** gap or bug, **-** not applicable.*

## 1. Verdict

The owner's principle is sound, and it can be stated precisely for this code. A **primitive** is a kernel-checked operation on world state. It has a
conservation class, an authority rule and a visibility rule. Each primitive should show up on three surfaces at once:
- an agent action (the agent acts for itself, with its consent, at its cost);
- a law face, which is either *compel* (do it to members) or *gate* (constrain or tax agents doing it), plus reads;
- an event type (what is recorded and who sees it).

Today that mapping exists only as habit. Transfer has a generic gate (`on_transfer`), forge has a bespoke one (`ban_forging`),
guard has a compel face (`oblige_guard`) that logs nothing, and attack has no gate at all.

The registries merged since review 01 cover four of roughly twenty contribution kinds: actions (prompt side only), rights,
law-function *scoping*, and facts. `lawapi.LAWFNS` describes 51 of the 117 law functions. Classification (`API_GROUPS`), docs
(four mechanisms) and previews (`Kernel._module_rules`) are still hand lists. Event types have no registry, and the cost of that
is now measurable: 79 of the 205 logged types are neither declared nor rendered. Twelve of them are logged `vis="public"`: seven
`jur_*` types, `birth_rules`, `official_stream`, `procedure_restored`, `treasury_coins` and `factored`. `render_event` returns
`None` for each of them, so no agent's feed shows them (reproduced in memory for seven of them).

What is missing for the contract to be *checkable*:
- an EventType registry (03);
- a complete LawFn table with `cls` and `module`;
- a thin `features.py` (identity, on-check, owned state keys, RNG prefixes, phase slots);
- a metadata-only `Primitive` table that ties the three surfaces together;
- one completeness test.

No plugin framework is needed. Behaviour stays in modules under fixed names; order stays in two reviewed tables.

## 2. The contribution matrix

**Where each kind is wired today** (one row per kind, ordered by how much drift it causes):

| Kind | Wiring site(s) today | Mechanism | Registry |
|---|---|---|---|
| State section | `Kernel.__init__` kernel.py:96-111 (9 calls, life behind inline `if`), `k.w` keys undeclared | H | none |
| Action dispatch | `actions.ACTIONS` actions.py:20-31 (5 concatenations), `globals()[f"_{name}"]`, 46 trampolines | H | none |
| Action prompt row | action_registry.py:205-309 (`needs`, `when`, section, `msg`) | R | `AR.REG` |
| Action doc | `agents.ACTION_DOC` agents.py:41, `.update(J/MD.ACTION_DOC)` :114-115 | H | none |
| Action category | `scorer.CATEGORIES` scorer.py:28-45 + `MD.CATEGORIES` | H (strict test) | none |
| DM flag | `actions.DM_ACTIONS` actions.py:32 vs `Act.msg` | H, duplicated | half |
| Legacy availability | `agents.system_prompt` absent-set agents.py:333-368 + 4 `absent_actions` | H | none |
| Rights | rights.py | R | `RT.REG` |
| Event render | `agents.render_event` if-chain agents.py:399-497, 8 module tuples | H | none |
| Feed priority | `context.OFFICIAL/POSTS` context.py:1010-1013, unknown → priority 1 | H | none |
| Board/search membership | `context.BOARD_TYPES` :68, `RECENT_KINDS` :395, + ~10 post lists (03 §2.4) | H | none |
| Law callables | `api_for` kernel.py:317-575, 10 `**X.law_api` spreads :566-574 | H | none |
| Law classification | `lawlang.API_GROUPS` lawlang.py:23-60 (11 per-module `|=` lines) | H | none |
| Law scoping | `lawapi.LAWFNS` (51 functions) → `AGENT_ARGS`, `REFUSED`, `LEGACY_ONLY` | R | `LAWFNS` |
| Law docs | `lawdocs.E` + `conflict.LAW_DOCS` (lawdocs.py:210) + `projects.API_DOC` (agents.py:156) + `hidden.api_doc`; gates `OPTIONAL`, `REQUIRES`, `_gated_off`, `MODULE_ENTRIES` | M×4 | consistency test only |
| Law hooks | `lawlang.HOOKS` lawlang.py:65 (15), call sites in handlers | H | none |
| Previews | `Kernel.view` kernel.py:744 + `_module_rules` :772-836 (per-module code in the kernel) | H | none |
| Library laws | `library.LIB` + `GATED_CATEGORIES` library.py:801; `conflict.LAWS` conflict.py:788 is outside both | M, X | `LIB` |
| Archive/codex docs | `archive.NEEDS` archive.py:53, `GATED_DOCS` :37, `codex/conflict/` | M | `NEEDS` |
| Goals and gates | `goals.EXTRA_GATES` goals.py:170, `NEW_GOALS`, `ONLY_WHEN`, `OPT_IN` | H | none |
| Probes | `library.PREDICATES` → `k.end_round(PREDICATES)` runner.py:438 | M | `PREDICATES` |
| Snapshot | kernel.py:1212-1250 (7 spreads; credit spelled `snapshot`) | H | none |
| Truth | `runner._truth` runner.py:481-503 (9 calls, 2 signatures) | H | none |
| State lines | `agents.state_view` agents.py:544-558 | H | none |
| Core prompt and module prompt | `agents.system_prompt` :374-386; `context.core_prompt` | H | none |
| Overview "Also:" | `context.overview` context.py:898-921 (one `if on(...)` per module) | H | none |
| Leverage | `context.LEVERAGE_CLASS/ROLE` context.py:782-807 | H | none |
| Manual | `composition.manual_section` (conflict, media, life); manual.py:153,160 hard-codes credit/projects; `context.MANUAL_SECTIONS` :86 | M×3 | none |
| Facts | facts.py:39-80 imports CF/MD/CX configs centrally | P | `facts()` |
| Spec defaults | module `DEFAULTS`/`cfg()`, 10 helper spellings of "enabled" | M | none |
| RNG streams | string seeds `f"{seed}|conflict|..."` by convention (≈40 sites) | M | none |
| Lifecycle | `start_round` kernel.py:1067, `end_round` :1091, runner (events, editorial turns), death fan-out in `mortality.disable` mortality.py:72-121 | H | none |
| Checkpoint | free (plain `k.w`); `STATE_SCHEMA` kernel.py:1282 | R | provenance |
| Golden | tests/test_charter_golden.py:36 (`society_small_4` turns most modules on) | R | fixtures |

**Feature × kind** (columns: St state, Ac actions, Rt rights, Ev events, LF law functions, LD law docs, Pv previews, Lb library and
regimes, Dc codex and archive, Gl goals, Sn snapshot and truth, Pr prompt/leverage/Also, Mn manual, Fx facts, Sp spec, Ph phases, Gd golden):

| Feature | St | Ac | Rt | Ev | LF | LD | Pv | Lb | Dc | Gl | Sn | Pr | Mn | Fx | Sp | Ph | Gd |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| conflict | H | P | - | H | P | M | H | **X** | M | H | H | H | M | P | M | H | R |
| media2 | H | P | - | H, **X** | P | R | H | M | M | H | H | H | M | P | M | H+runner | R |
| scholars | H (inside media) | P | R | H | - | - | - | - | - | - | H | H | H | P | M (in media2) | H (inside media) | R |
| jurisdictions | H | P | - | **X** | P | M | H | - | M | H | H | H | H | - | M | seam | R |
| life | H (inline `if`) | P | R | H, **X** | P (`__import__`) | M | H | M | M | H | H | H | M | - | M | H | R |
| mortality | H | P | - | H | H | M | H | - | - | H | H | - | - | - | derived | **X** (death) | R |
| roles | H | - | R | H | - | - | - | - | - | H | H | H | H | - | M | H | R |
| projects | H | P | - | H | P | M | H | R | - | H | H | H | H | - | M (on by default) | H | R |
| outside | H | P | - | H | P | M | H | - | - | - | H | H | H | - | M | H | R |
| hidden | H | P | R | M (`as_shown`) | P | M | H | - | M (codex) | - | H | H | H | - | M | H | R |
| credit | H (kernel) | P | - | M | P | R | H (in `view`) | R | - | H | H | - | H | P | M | H | R |
| regimes | - | - | H | - | - | - | - | R | - | - | - | H | H | - | R | gen | R |
| events | H | - | - | R (world events) | - | - | - | - | - | H | H | - | - | - | M | runner | R |
| camptypes | H | P | R | H | P | M | H | - | M | H | H | H | H | - | M | H×3 | R |
| context | H | P | - | H | - | - | - | - | - | H | H | owns | owns | R | M | H | R |
| observer | H | own schema | - | H | - | - | - | - | - | - | H | own | - | P | M | runner | R |

Two of the X cells are bugs:
- **Public events with no renderer.** `jur_joined`, `jur_left`, `jur_declared`, `jur_join_accepted`/`refused`,
  `jur_leave_pending`, `jur_born_into`, `birth_rules` (life.py:671), `official_stream`, `procedure_restored` and `treasury_coins`
  are all logged `vis="public"` (jurisdictions.py:895-1020, kernel.py:632, media.py:1272), and `render_event` returns `None` for
  each, so feeds drop them (reproduced). Some of them have a parallel gazette or notify, for example the declaration
  (jurisdictions.py:1004) and `factored` (actions.py:232). Joins and leaves have none.
- **Conflict's library laws** (`Arms Control`, `Mutual Defence Pact`, `Bounty on Aggressors`) are not in `library.LIB`. That makes
  them invisible to the Law library manual section, to the archive's library documents and to `start_laws`
  (generator.py:475 rejects them).

## 3. Primitives: one declaration, three surfaces

**Definition.** A primitive is a kernel-checked state change with four properties:
- an **effect class** (`read`, `move` conserves goods, `create`/`destroy` changes totals, `relation` links agents, `rule` sets a
  parameter, `reveal` changes visibility);
- an **authority** (who may cause it);
- a **cost**;
- a **visibility** (who learns that it happened).

**Today's pairs:**

| Primitive | Action (self, consent) | Law: compel (on members) | Law: gate | Law: read | Event (action) | Event (law) |
|---|---|---|---|---|---|---|
| move | `transfer` | `move`, `fine` | hook `on_transfer` (tax or block) | `balance` | `transfer` [parties] | `move` [monitor] only (kernel.py:271) |
| harvest | `harvest` | - | hook `on_harvest` + `set_quota/fee/limit` | `stock` | `harvest` [self] | `rules` in preview |
| forge | `forge` | - | `ban_forging` (bespoke) | `weapons_of` | `arms` [self] | `forge_ban` public |
| guard | `guard` (paid, accepted) | `oblige_guard` | - | `guards`, `defense_of` | `guard` | **none** (preview only, conflict.py:757) |
| attack | `attack` | `lawful_attack` (armory-paid) | **none** | `attacks` | `disabled`/`attack_failed` | `lawful_force` [monitor] |
| subscribe | `subscribe` | `compel_subscription` | - | `outlets` (counts) | `subscribe` | `compelled_subscription` [monitor] (media.py:1252) |
| lease | `lease`/`accept_lease` | - | `set_lease_rules` | `leases` | `lease_*` | `lease_rules` |
| commission | `commission` | - | hook `on_commission` + `set_birth_rules` | `commissions` | `commission` [monitor] | `birth_rules` public, unrendered |
| post | `post` | `hide_post` | hook `on_post`, licences | `posts` | `post` | `post_hidden` |

**Is there a principle?** Yes, but implicit. Three regularities hold everywhere:
1. Actions act only for the actor, which is kernel invariant "laws never act for an agent" (kernel.py:10) read from the other side.
2. Compel faces are scoped to members (`LAWFNS.agents`) and are structural.
3. Every compel that consumes goods pays from a treasury (`lawful_attack` from the armory, `fine` into the reserve), never by minting.

Two things are accidental:
- **Gates.** Some gates are generic hooks and some are one-off rule functions. A hook is strictly more expressive (`ban_forging` is
  `def on_forge(a, qty): return False`). Bespoke rules exist only because they preview as state, and attack and guard simply never
  got one.
- **Compel visibility.** It ranges from public (`forge_ban`) to monitor-only (`move`, `compelled_subscription`) to nothing
  (`oblige_guard`). The affected agent may never be told.

**Can one row generate the surfaces?** Yes for the metadata, no for the behaviour.

```python
@dataclass(frozen=True)
class Primitive:                          # charter/primitives.py: metadata only, behaviour stays where it is
    name: str                             # "guard"
    feature: str                          # "conflict"
    effect: str                           # read | move | create | destroy | relation | rule | reveal
    act: str | None = None                # action name (AR row must exist, emits ⊆ events)
    compel: str | None = None             # law fn acting on members ("oblige_guard")
    gate: str | None = "auto"             # "auto": hook on_<act>(agent, **args) -> False blocks, number deducts; or a rule fn name
    reads: tuple = ()                     # law reads ("guards", "defense_of")
    emits: tuple = ()                     # event types the act writes
    compel_emits: str | None = None       # event the compel face writes ...
    compel_vis: str = "parties"           # ... and who must see it: parties | public | monitor (monitor needs why=)
    preview: tuple = ()                   # k.w path a compel/gate writes, for Kernel.view (("conflict", "obligations"))
    why: dict = field(default_factory=dict)   # {"compel": "laws never act for an agent", "gate": "..."} for missing faces

P("guard", "conflict", "relation", act="guard", compel="oblige_guard", reads=("guards", "defense_of"), emits=("guard",),
  compel_emits="guard_obliged", preview=("conflict", "obligations"))
P("move", "core", "move", act="transfer", compel="move", gate="on_transfer", reads=("balance",), emits=("transfer",),
  compel_emits="move", compel_vis="parties")             # today monitor: a decision for you (see below)
P("dm", "core", "reveal", act="dm", gate="on_dm", emits=("dm",), why={"compel": "laws never act for an agent"})
```

**What the row generates or checks:**
- **LawFn rows** for `compel`, `reads` and the gate. `cls` comes from `effect`: reads are `read`; compel and gate are structural,
  except `rule` gates that are ordinary today, which an override covers.
- **Agent parameters**, checked against the real signature as `test_charter_jurisdictions.py:326-336` does now.
- **`API_GROUPS` membership and the `HOOKS` entry** for an `auto` gate.
- **A lawdocs Hooks skeleton**, with the signature taken by `inspect`; the prose is still required.
- **EventType rows**, with `feed` defaulting from `compel_vis`.
- **A preview key** read by a generic `Kernel.view` loop, filtered through `RT.is_secret` and hidden-jurisdiction checks.
- **The activity category**, defaulted from `effect` (move/create → economic, relation/force → political, reveal → talk); the
  Act row may override it.

The `auto` gate is how "a new primitive extends the legal system automatically" becomes literal. The handler calls one helper,
`k.gate("forge", aid, qty=qty)`, which runs the hooks with jurisdiction binding and returns `(blocked, deduction)`. A new act
then gets a law hook, its docs line and a jurisdiction-correct dispatch without anyone editing `lawlang`, `lawdocs` or
`jurisdictions`.

**Where the surfaces must differ** (and stay hand-written):
- **Authority.** An action needs rights, class and `needs`. A compel needs membership scoping and structural class.
- **Consent.** Compelled relations are revocable only by repeal: `compelled()` blocks unsubscribing, and an obligation ends with its
  law. That is why `compel_vis` defaults to `parties`.
- **Cost.** An action costs action slots and goods, stated through facts. A compel costs step limits and treasury goods only.
- **Timing.** An action runs in turn order. A compel runs at enactment or hook time. A gate runs inside the action.
- **Prose.** `ACTION_DOC` addresses the actor. Lawdocs addresses the legislator. Codex articles teach. None can be generated.

One decision for you: should compel faces **notify their targets**? Making `move`/`fine` by law visible to the parties changes
every feed in law-heavy runs, and so every golden.

## 4. The Feature contract

The contract has three parts.
1. **A feature row** in `charter/features.py`: identity and wiring only.
2. **Rows in each registry tagged `module=`**: actions, rights, events, LawFns, primitives, goals, library laws, archive docs.
3. **Module-level names with fixed signatures.** No decorators decide order. The two order-sensitive tables (actions in
   `action_registry.py`, phases in `features.py`) are central and reviewed.

```python
# charter/features.py
@dataclass(frozen=True)
class Feature:
    name: str                      # "conflict"
    module: str                    # "charter.conflict"
    spec_key: str | None           # "conflict"; None: core, always on
    default_on: bool = False       # projects: True
    implied_by: tuple = ()         # mortality: ("life", "conflict")
    state: tuple = ()              # k.w keys install() adds; nothing when off
    rng: tuple = ()                # stream prefixes ("conflict", "conflict-bot")
    golden: str | None = None      # the golden case that turns it on
    def on(self, x) -> bool: ...   # THE enabled check; replaces 10 helper spellings and 13 inline checks

FEATURES = [F("credit", ..., state=("loans", "credit")), F("projects", ..., default_on=True), F("outside", ...),
            F("hidden", ...), F("context", ...), F("roles", ...), F("camps", "charter.camptypes.framework", "camps"),
            F("life", ...), F("mortality", ..., implied_by=("life", "conflict")), F("conflict", ...),
            F("jurisdictions", ...), F("media", "charter.media", "media2"), F("scholars", ..., "media2"), F("events", ...)]
# FEATURES order = today's merge order for law_api, snapshot, state_lines, truth, render (snapshot key order reaches bytes).

PHASES = {                         # one reviewed list per phase; ("core", x) is kernel code, ("law", hook) runs law hooks
  "init":        [("projects", "init_state"), ("outside", "init_state"), ("hidden", "install"), ("context", "install"),
                  ("roles", "init_state"), ("camps", "init_state"), ("life", "install"), ("conflict", "install"),
                  ("jurisdictions", "install"), ("media", "install"), ("scholars", "install")],
  "round_start": [... as review 01 §4.3 ...],
  "round_end":   [... as review 01 §4.3 ...],
  "after_turns": [("observer", "act"), ("media", "editorial_turns")],          # runner-level phases, currently inline
  "death":       [("life", "on_death"), ("roles", "pass_on_death"), ("mortality", "seat"), ("law", "on_death"),
                  ("mortality", "bequest"), ("life", "after_death")],          # today hand-coded in mortality.disable
  "birth":       [("jurisdictions", "assign_newborn"), ("law", "on_birth"), ("media", "subscribe_newborn")],
}
```

**Fixed module names**, which a test checks by `inspect.signature`. All of them are optional, and each is consumed by one loop:

| Name | Signature | Consumer (replaces) |
|---|---|---|
| `DEFAULTS` | dict | `Feature.on`, spec schema test (10 `cfg` helpers) |
| `install`, phase functions | `(k)` | `PHASES` loops (`Kernel.__init__`, `start_round`, `end_round`) |
| `law_api` | `(k, lid) -> dict` | `api_for` loop over `FEATURES` (10 spreads) |
| `preview_rules` | `(k, ag) -> dict` | `Kernel.view` (moves `_module_rules` code out of the kernel) |
| `snapshot_fields`, `truth` | `(k) -> dict` | snapshot and `runner._truth` loops |
| `state_lines` | `(k, aid) -> list` | `agents.state_view` |
| `render_event` | `(k, e, tag, viewer) -> str or None` | the `render_event` dispatch, by `EventType.module` |
| `facts` | `(spec) -> dict` | `facts.facts` merges, names must be unique (stops facts.py importing every module) |
| `SECTIONS` | `Section` rows (02 §4.4) | manual, core prompt, legacy prompt: the module prompt, rules text, "Also:" line and leverage sentences become Sections with `needs=("mod:x",)` |
| `LAW_DOCS` | lawdocs rows | `lawdocs.E` (folds `conflict.LAW_DOCS`, `projects.API_DOC` and `OPTIONAL`/`REQUIRES` into `module=`) |
| `LAWS` | library rows with `category` | `library.LIB` (folds `conflict.LAWS` and `GATED_CATEGORIES`) |

**Registry rows tagged by module** (order-insensitive, so they may live in the module file and be collected in `FEATURES` order):
- `Act(module=, handler="conflict:act_fortify", doc=, category=, emits=)`, with the row itself kept in `action_registry.py`;
- `Right(module=)`;
- `EventType(module=, feed=, post=, board=, truth=)` as in 03;
- `LawFn(module=, cls=)` extended to all functions;
- `Primitive`;
- `Goal(requires=(features), rule, score, probes)` as in 05;
- archive `NEEDS`.

**What stays hand-written:**
- **Behaviour**: handlers, law closures and phase functions.
- **All prose**: docs, manual text, codex articles and leverage sentences.
- **Renderer wording.**
- **Goal score functions.**
- **Jurisdictions.** They remain a kernel seam: `_add`, `log` visibility, `hooks`, `enact`, `scope_api` and the 22 action
  branches. Contracts (06) extend that seam rather than plug into it.
- **The core law API** in `api_for`.
- **`Kernel.view`'s core keys.**
- **Calibrations and RNG call sites.** The table only declares the prefixes.

## 5. Gap analysis and the completeness test

| Registry | Status | Needed for the contract |
|---|---|---|
| Actions (`AR.REG`) | prompt only | `handler`, `doc`, `category`, `emits`, `module`; derive `ACTIONS`, `ACTION_DOC`, `CATEGORIES`, `DM_ACTIONS` (01 §4.1) |
| Rights | done | `module` |
| LawFn (`lawapi`) | 51/117, scoping only | all 117 + hooks; `cls` (derive `API_GROUPS`, `STRUCTURAL_CALLS`), `module` (derive lawdocs gates), `preview` |
| Facts | central function | per-feature `facts(spec)` pieces |
| Provenance | done | add `FEATURES` on/off per run to `run.json` |
| **EventType** | missing | name, module, `feed` (required), post/board/truth flags, renderer by module (03 §4) |
| **Feature/Module** | missing | §4 |
| **Section** | missing | 02 §4.4 |
| **Goal** | missing | 05 (`requires` replaces `EXTRA_GATES`/`ONLY_WHEN`) |
| **State sections** | missing | `Feature.state` is enough; skip a separate `vocab.STATE` |
| **Spec schema** | missing | `DEFAULTS` per feature + a test against `base.yaml` |
| **Primitive** | new here | metadata only, last |
| Hooks | tuple | rows in LawFn (`kind="hook"`, signature, module) |

**Minimal set for a checkable contract:** EventType, complete LawFn and Feature. Sections, Goals and Primitive make the test
stricter as they land.

```python
# tests/test_charter_feature_contract.py
KNOWN_GAPS = {...}                 # (feature, check) pairs open today; the set may only shrink (asserted against a frozen copy)

@pytest.mark.parametrize("f", FEATURES, ids=lambda f: f.name)
def test_feature_is_complete(f):
    mod = importlib.import_module(f.module)
    for name, sig in CONTRACT_SIGS.items():                          # fixed names have fixed signatures
        if hasattr(mod, name): assert_sig(getattr(mod, name), sig)
    k_on, k_off = kernel_with(f, on=True), kernel_with(f, on=False)
    assert set(k_on.w) - set(k_off.w) == set(f.state)                # owns exactly its declared state; nothing when off
    for a in AR.rows(module=f.name):
        assert resolve(a.handler) and a.doc and a.category in CATEGORIES and set(a.emits) <= EVENTS
        assert f"mod:{f.spec_key}" in a.needs or f.spec_key is None   # off means unavailable, on both prompt paths
    for fn in LA.rows(module=f.name):
        assert fn.name in k_on.api_for("L0") and fn.cls and fn.name in LD.ENTRIES
        if fn.cls != "read": assert fn.preview or fn.why               # every write is previewable or says why not
    for t in EV.rows(module=f.name):
        assert t.feed == "silent" or render(k_on, sample(t)) is not None   # catches jur_joined today
    for p in PR.rows(feature=f.name):
        assert p.compel or "compel" in p.why                         # every agent primitive has a law face or a reason
        assert p.gate or "gate" in p.why
        assert p.compel_vis != "monitor" or "compel_vis" in p.why
    for g in GOALS.rows(requires=f.name): assert f.on(spec_with(f))
    for law in LB.rows(module=f.name): assert law.name in LB.LIB      # catches conflict.LAWS
    assert f.golden in GOLDEN_CASES or (f.name, "golden") in KNOWN_GAPS
    assert any(s.needs == (f"mod:{f.spec_key}",) for s in SECTIONS.rows(module=f.name)) or not AR.rows(module=f.name)

def test_logged_events_are_registered(tmp_path):                    # strict k.log in the golden society run (03)
    ...
def test_rng_streams_are_declared():                                # every random.Random(f"...") prefix belongs to one feature
    ...
```

## 6. Worked examples

**(a) Scheduling / standing orders.** 07 recommends building these as a contract template (a one-member association whose
`on_round_start` pays from an allowance) and rejects a kernel scheduler. Under that recommendation the feature is **one library
row (category `contract`), one manual paragraph and one test: 2-3 files, today or under the contract**. The contract only adds
the check that the template's category is gated by `contracts`.

For comparison, suppose it were a standalone primitive `schedule {action, args, every, until}`, with law functions
`orders()`/`cancel_orders(agent)` and events `order_set`/`order_run`.

| Touch | Today | Under the contract |
|---|---|---|
| behaviour (new module) | `schedule.py` | `schedule.py` (+ `DEFAULTS`, `LAW_DOCS`, `SECTIONS`, `facts`, event, LawFn and Primitive rows) |
| dispatch, doc, category, DM | actions.py, agents.py, scorer.py | (Act row) |
| prompt row | action_registry.py | action_registry.py |
| legacy availability | agents.py (`absent`) | (derived) |
| phase (run orders at round start) | kernel.py `start_round` | features.py (row + phase slot) |
| law API spread, classification, scoping, docs | kernel.py, lawlang.py, lawapi.py, lawdocs.py | (rows in module) |
| preview, snapshot, state lines, truth | kernel.py, agents.py, runner.py | (fixed names) |
| render, feed priority | agents.py, context.py | (EventType row) |
| overview "Also:", manual | context.py, manual.py or composition | (Section rows) |
| spec | specs/base.yaml | specs/base.yaml |
| tests, golden | 2 tests + fixture | 2 tests + fixture |
| **Shared files edited** | **14** (actions, agents, scorer, action_registry, kernel, lawlang, lawapi, lawdocs, runner, context, manual, base.yaml, 2 tests) | **4** (action_registry, features, base.yaml, golden test) |

**(b) Associations/contracts (06 §3-§5).**
- **Seam work.** Jurisdiction `kind`, many-to-many `binds`/`hooks`/`passed`, per-law tax destination in `_send`/`_harvest`,
  `scope_api` power sets. This is kernel-seam work in jurisdictions.py, actions.py and kernel.py **under either regime**, because
  the contract deliberately does not absorb jurisdictions.
- **Rest of the feature, as in (a).** Actions `create_contract` plus `join`/`leave` with an id prefix. Law functions `pull`,
  `contract_state`, `contracts`, `breaches`, plus a `contract` column. Events `contract_created`, `contract_breach`, `pull`.
  Templates, an enforcement fact, a manual section, institution goals, previews, snapshot and truth.
- **New hooks.** `on_death` and `on_raid`/`on_event` need edits at their call sites in mortality.py, outside.py and conflict.py.
  Under the contract, `on_death` is a slot in `PHASES["death"]`. `on_raid` comes from a `Primitive`/`EventType` flag `hookable=True`,
  dispatched once by the phase runner at the end of the action or phase, never re-entrantly from inside `k.log`.

| | Today | Under the contract |
|---|---|---|
| Seam (unavoidable) | jurisdictions.py, actions.py, kernel.py | same 3 |
| Feature wiring | action_registry, agents, scorer, lawlang, lawapi, lawdocs, context, manual, library, goals, facts, runner, mortality, outside, conflict, base.yaml | contracts.py (new), action_registry, lawapi (`contract` column), features, base.yaml |
| Tests | contracts test, jurisdictions test, golden fixture | same |
| **Shared files edited** | **≈21** | **≈10** (3 of them seam) |

The remaining cost is the seam, which is the honest place for it: contracts change what a law *is*.

## 7. Migration order (fits README §Order of work)

1. **README step 1-2** (safety net, bugs): add two small fixes from this review. Renderers for the public `jur_*`,
   `birth_rules`, `official_stream`, `procedure_restored` and `treasury_coins` events (prompt and feed fingerprints change for
   jurisdiction and life worlds). Move `conflict.LAWS` into `library.LIB` under a gated `conflict` category.
2. **README step 4**:
   - EventType with a required `feed` and a renderer per module;
   - finish `Act` (`handler`, `doc`, `category`, `emits`, `module`);
   - extend `LawFn` to all 117 functions and the 15 hooks, with `cls` and `module`;
   - derive `API_GROUPS`, the lawdocs gates, `CATEGORIES`, `DM_ACTIONS` and `ACTIONS`.

   Goldens stay unchanged.
3. **Thin `features.py`** (identity, `on`, `state`, `rng`, `golden`). `mod:` and the 10 enabled helpers resolve through it. Add
   the completeness test with a `KNOWN_GAPS` set that may only shrink.
4. **README step 5** (goals): `Goal.requires` replaces `EXTRA_GATES`/`ONLY_WHEN`, and the test gains the goal checks.
5. **README step 7**:
   - Section model, with feature-owned prompt and manual sections, "Also:" lines and leverage;
   - per-feature `facts`;
   - then `PHASES` (01 step 6), adding the `death`, `birth` and `after_turns` phases and `preview_rules`.

   Goldens must stay identical; loop in today's order.
6. **Primitive table** (metadata) and `k.gate` with automatic `on_<act>` hooks, starting with forge, guard and attack. Adding
   hooks does not bump `LAW_API_VERSION` (lawlang.py:19). Decide compel visibility (§3) here, as one golden update.
7. **Contracts v1 (06 §8 step 2)**, written to the contract. Standing orders and scripts follow as templates.

Do not do steps 6-7 before 2-3. Otherwise contracts add another twenty hand-wired sites to the lists this plan exists to remove.
