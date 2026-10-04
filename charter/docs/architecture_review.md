# Charter architecture review

*4 Oct 2026. Reviewed the tree as it stood that day while another agent was fixing bugs in it, so line numbers may drift; references
use module.function. Read-only review: one new dry run (`charter/out/E4/2026-10-04T13-28-49_seed1_dry`, observer and events on) and
in-memory rescoring of every existing run. The suite passed in full (351 tests, 3 min 22 s).*

## Executive summary: top 5 recommendations, ranked by value per effort

1. **Fix eight verified correctness and visibility bugs first. Each is small; one agent can fix one in an hour or two.** Four of them
   undermine experiments that are already planned:
   - A public `respond` event prints the full evidence events. That includes the true sender of a forged DM, so it can reveal the
     secret observer.
   - The secret observer is in the pools that hidden-power tips and world events draw from. It can be named in a rumour, "depart"
     publicly, or be chosen to discover a camp.
   - Dry runs (proposal previews, procedure probes, `decisive_set`) leave changes in active laws' module-level lists and dicts.
   - Writing `goals: {weights: {...}}` in a spec silently replaces the whole `goals` block and crashes generation.

   Details and the other four are in section 4.
2. **Record every model call fully, and add a tidy cross-run dataset (`charter export` plus `charter.data`).** Today:
   - Failed calls keep no usage.
   - Retries are dropped.
   - The raw model text, the backend, latency and the code version are never stored.
   - Native thinking was captured in 0 of the 3,779 calls in the two usable model runs.

   Answering "does model tier predict goal score?" took a hand-written script. It had to truncate dead rounds, join instance.json to
   score.json, and still had too few agents per goal type. A long-format export would make these questions one-liners: per-run,
   per-agent, per-agent-round, per-event, per-call and per-law tables, with a schema version and provenance.
3. **Give the spec a schema and validate it.** Today:
   - Unknown keys pass silently, so `--set observr.enabled=true` runs without an observer.
   - Many bad values pass silently: `models.mix=balancd` makes every agent weak, `turns=simultanous` runs sequentially, and
     `start_laws` typos fail only at run time.

   One schema module (types, enums, defaults, one-line docs) gives validation with did-you-mean suggestions, generated spec
   documentation and `charter spec check`. It also removes the ambiguity where any single-key mapping can be read as a distribution.
4. **Declare actions, law functions and event types once, in registries that generate the hand-kept lists, and formalise the
   per-feature hook convention that already exists.** Today:
   - A new law function touches 4 places: `api_for`/`law_api`, `lawlang.API_GROUPS`, `lawdocs.E` and `API_DOC`.
   - A new action touches about 5.
   - Seven hand-kept lists of event types already disagree.
   - The features already expose `init_state`, `start_round`, `law_api`, `snapshot_fields`, `state_lines`, `render_event`,
     `metrics` and `truth`, under inconsistent names.

   Turning that convention into one `Feature` record removes most merge conflicts without a rewrite. Put a golden dry-run
   fingerprint test in place first.
5. **Use separate random streams for each purpose, and add explicit rosters, scripted events and paired designs.** One generator
   stream drives everything. So fixing `endowment_gini`, changing `models.mix`, choosing a regime, or adding any new spec
   distribution redraws the whole world: all agents' goals change. The kernel's turn-order stream also produces harvest noise. As a
   result, "same world, different model" and "same world, observer on/off" comparisons are impossible today. Named substreams
   (versioned with `rng_version: 2`) fix this and make paired runs cheap.

The phased plan at the end breaks these into about 30 steps. Each step is small enough for one agent and keeps the tests green.

---

## 1. Modularity and extensibility

### 1.1 How a feature plugs in today

The core (spec, generator, kernel, actions, agents, runner, scorer, report) has no extension mechanism. Each feature adds calls into
shared files. In practice a convention has grown up: feature modules expose functions with conventional names, and the core calls
them explicitly.

| Shared touchpoint | Where | Who hooks in now |
|---|---|---|
| World-state init | `Kernel.__init__` (the `self.w` dict literal; then `P.init_state`, `O.init_state`, `H.install`) | loans keys inline; projects; tribute; hidden. Credit (`CR.st`) and events (`EV.state`) initialise their state lazily with `setdefault` |
| Round start | `Kernel.start_round` | `settle_loans`→`CR.settle`, `P.start_round`, `O.start_round`, `P.maybe_spawn` (with a leftover "re-route to the event scheduler and delete this line" note), `H.on_round_start` |
| Round start (runner) | `runner.run` loop | `EV.round_start`, `H.apply_order`, `FS.Tally`, observer `step_prepare`/`step_finish`/`turn` |
| Round end | `Kernel.end_round` | `CR.end_round` |
| Law API | `Kernel.api_for` | inline functions plus `**CR.law_api`, `**H.law_api`, `**P.law_api`, `**O.law_api` |
| Law classification | `lawlang.API_GROUPS` (+ two in-place patches for hidden) | every law function, by hand |
| Law documentation | `lawdocs.E` (a 7-tuple per function), `agents.API_DOC`, `projects.API_DOC` | every law function, by hand |
| Actions | `actions.ACTIONS` tuple + `_<name>` function + `DM_ACTIONS` | DM limit, credit, projects, tribute, forge |
| Action docs and availability | `agents.ACTION_DOC`, the `absent` set and class lists in `agents.system_prompt`, `H.undocumented_actions` | every action, by hand |
| Rules text | `agents.world_rules` (+ `P.rules_text`, `RG.describe`), `agents.class_brief`, `H.prompt_section` | DM step, projects/tribute, regimes, hidden |
| Feed rendering | `agents.render_event` (an if-chain; delegates to `H.render`, `CR.render`, `P.render_event`, `O.render_event`) | everyone |
| State view | `agents.state_view` (+ `CR.state_lines`, `CR.currency_note`, `P.state_lines`, `O.state_lines`) | credit, projects, tribute |
| Preview diff | `Kernel.view`/`Kernel.diff` (+ `P.view`) | projects only (see risk R6) |
| Snapshot | `Kernel.snapshot` (+ `CR.snapshot`, `P.snapshot_fields`, `O.snapshot_fields`) | credit, projects, tribute |
| Scripted bots | `agents.ScriptedPolicy.act` (+ `CR.scripted_action`, `observer.scripted_act`) | credit, projects, tribute, DM replies, observer |
| Ground truth | `runner._truth` (+ `H.truth`, `EV.truth`) | hidden, events |
| Metrics | `scorer.metrics` (+ `CR.metrics`, `P.metrics`, `O.metrics`), `scorer.score` (+ `OBS.score`, `H.metrics`, `probing.experimentation`, `_regime_start`) | most features |
| Summary row | the `summary` dict literal in `scorer.score` | most features |
| Reports | `report.spec_outline`, `report.overview`, `report.messages`, `report.build` (+ `H.outline`, `EV.outline_lines`, `EV.overview_line`, `OBS.overview_lines`, `OBS.report_md`, `_regime_outline`) | hidden, events, observer, regimes, projects, tribute |
| Spec defaults | `specs/base.yaml` (+ `DEFAULTS` dicts in `projects`, `outside`, `hidden`, `observer.cfg`) | every feature; defaults live in two places for four features |
| Instance generation | `generator.generate` (+ `RG.resolve/finish/apply_rights`, `AR.assign`, `OBS.make`, `hidden.generate`, `events.attach_schedule`) and `PER_ENTITY` | regimes, archetypes, observer, hidden, events, archive split |
| Checkpoint | `Kernel.checkpoint_state` (everything in `self.w` is covered automatically) + `runner.runner_state` (+ observer state) | observer; everything else rides in `k.w` |

**What a new feature costs today.** A typical mechanism with one action, two law functions, one event type, a state line, a metric
and a spec block edits about 11 files. For example:

- projects touched `projects.py`, `kernel.py` (init, start_round, api_for, view, snapshot), `actions.py`, `agents.py` (ACTION_DOC,
  API_DOC, `absent`, world_rules, render_event, state_view, ScriptedPolicy), `lawlang.py`, `lawdocs.py`, `scorer.py` (metrics and
  summary), `report.py`, `library.py`, `generator.py` and `base.yaml`, plus tests;
- credit touched about 10 of the same files;
- tribute touched 9.

Merge conflicts happen in the same places every time: the `api_for` return dict, the `ACTIONS` tuple, the `ACTION_DOC` dict, the
`render_event` if-chain, the `absent` set, the `summary` literal, `Kernel.start_round`, and `base.yaml`.

### 1.2 Duplication and coupling (verified unless marked)

- **Forged DMs exist twice:**
  - `actions._forge_dm` (the observer, or a `forge` right that is not in `KERNEL_RIGHTS`) costs `observer.forge_cost` and logs
    `forged_dm`;
  - `hidden._quill` (the `quill_of_maribel` power through `invoke`) is free, logs `forgery_truth`, and is not a DM action, so in fast
    mode it is delivered after the DM step, and the recipient gets no chance to reply that round.

  As a result `H.metrics` counts only `forgery_truth`, and `observer.con_income` only covers the observer. Both call the private
  `actions._dm_check`/`_deliver`, which is the right core. Lift that core into one public `messaging.forge_dm(k, sender, shown_as, to,
  text, cost, source)` that logs one truth event type with a `source` field.
- **The same law function is registered in four places:**
  - the kernel or feature `law_api` (behaviour);
  - `lawlang.API_GROUPS` (class);
  - `lawdocs.E` (prompt text, article detail, core tier, minimal tier);
  - `agents.API_DOC`/`projects.API_DOC` (full-preset text).

  A test checks `api ⊆ lawdocs.ENTRIES`, but nothing checks `api ⊆ lawlang.API`, and that gap matters. A function missing from
  `API_GROUPS` is unclassified, so a law that only calls it is *ordinary* and can pass at L1 under the ordinary procedure. The sets
  match today; the risk is the next feature.
- **Event-type lists kept by hand disagree:**
  - `kernel.POSTABLE` (includes `channel_post`);
  - the types in the `posts()` law API (excludes it);
  - `hidden.VEILABLE`, `hidden.FORGEABLE` (adds `gazette`);
  - `goals.PUBLIC`, `observer.MESSAGE_TYPES`, `report.MESSAGE_TYPES`;
  - `feed()`'s own-action skip list and `__main__.cmd_show`'s `keep`.

  So a law can hide a channel post, but the hide-posts power cannot.
- **Activity categories are stale.** `scorer.PRODUCTIVE`/`POLITICAL` predate credit, projects, tribute, reply and the DM limit, so
  `lend`, `contribute`, `pay_tribute`, `repay_loan` and `set_dm_limit` count as "talk" in `activity_mix`.
- **Two archive-leak definitions.** `scorer.metrics` (`archive_leaks`) uses 8-grams of the documents read, taken from the archive as
  it is *at scoring time*. `goals.leaks` (the Leaker goal) uses the fixed archive minus text common to all prompts. They can disagree
  on the same run.
- **Generation logic is duplicated for mid-run arrivals.** `events.add_agent`, `events._model` and `events._goal_text` re-implement
  model assignment (different rules: `strong_fraction` becomes a per-agent coin flip and the Fixer rule is gone), goal text and the
  archive split. Arrivals also get **no archetype and no codex articles or powers**, because `AR.assign` and `hidden.generate` are
  never called for them. Every generation-time feature will drift this way.
- **System-prompt availability is hand logic.** The `absent` set in `agents.system_prompt` encodes per-action rules (law level, DM
  channel, outside power on, projects on, class, `H.undocumented_actions`), separately from the actions themselves.
- **Fragile string coupling.** `probing._UNKNOWN_INVOKE`/`_UNKNOWN_TOP` parse result *strings* ("invoke: ERROR no such action '...'")
  from `reasoning.jsonl`. Rewording an error message silently changes experimentation metrics.
- **Spec defaults live in two places.** Four features keep defaults both in `base.yaml` and in a module `DEFAULTS`/`cfg()` dict.
- **Run identity depends on the code.** `run_stem` strips `regime: None` so old hashes survive, and resume refuses whenever the
  regenerated instance differs. Every feature that adds an instance key needs such a compatibility hack or breaks resume of
  in-flight runs.

### 1.3 Proposed structure: formalise the convention

The goal is not a plugin framework. It is to put each fact in one place, so that adding a feature means adding a module plus one
line in a feature list.

```python
# charter/registry.py  (new; small, no behaviour of its own)
from dataclasses import dataclass, field
from typing import Callable, Literal

LawClass = Literal["read", "ordinary", "structural", "procedural"]
DocTier = Literal["prompt", "common", "uncommon", "rare", "legendary"]

@dataclass(frozen=True)
class LawFn:
    name: str
    group: str                      # prompt group ("Money", "Read", ...) -> API_DOC layout
    cls: LawClass                   # -> lawlang.API_GROUPS / STRUCTURAL_CALLS (classification)
    topic: str                      # -> codex article topic
    signature: str                  # prompt text, e.g. "set_par(currency, item, rate)"
    detail: str                     # article text
    tiers: dict[str, DocTier]       # {"core": "prompt", "minimal": "common"}; "full" is always "prompt"
    make: Callable                  # (k, lid) -> callable bound for that law  (or a factory returning several)

@dataclass(frozen=True)
class ActionSpec:
    name: str
    handler: Callable               # (k, aid, **args) -> str
    doc: str                        # the ACTION_DOC line
    category: Literal["productive", "political", "talk", "economic", "message"]
    dm: bool = False                # counts against the DM limit; delivered in the DM step
    available: Callable = lambda inst, agent: True   # replaces the hand-made `absent` set
    classes: tuple = ()             # () = everyone; else class-only actions (veto, patch, ...)

@dataclass(frozen=True)
class EventType:
    name: str
    render: Callable | None         # (k, e, viewer) -> str | None; None = never in feeds
    public_message: bool = False    # a "message" for messages.md / watch metrics / leak scans
    postable: bool = False          # can be hidden/forged/reported
    overview: Callable | None = None

@dataclass
class Feature:
    name: str                       # "credit", "projects", ...
    spec_key: str | None            # its block in the spec
    schema: dict | None = None      # defaults + docs + types for that block (see section 2)
    actions: list[ActionSpec] = field(default_factory=list)
    law_api: list[LawFn] = field(default_factory=list)
    events: list[EventType] = field(default_factory=list)
    # lifecycle (all optional; called in FEATURES order)
    generate: Callable | None = None          # (inst, sp, rng) -> None; rng = substream(seed, name)
    init_state: Callable | None = None        # (k) -> None; state MUST live in k.w[name] (checkpointed, dry-run safe)
    round_start: Callable | None = None       # (k) -> None
    round_end: Callable | None = None         # (k) -> None
    on_arrival: Callable | None = None        # (k, inst, agent) -> None; generation-time features apply to arrivals
    rules_text: Callable | None = None        # (inst) -> str
    prompt_section: Callable | None = None    # (inst, agent) -> str
    state_lines: Callable | None = None       # (k, aid) -> list[str]
    preview_view: Callable | None = None      # (k) -> dict, joined into Kernel.view()/diff()
    snapshot: Callable | None = None          # (k) -> dict merged into the round snapshot
    truth: Callable | None = None             # (k, inst) -> dict merged into ground_truth.json
    metrics: Callable | None = None           # (gt) -> dict under score.json metrics[name]
    summary: Callable | None = None           # (metrics) -> flat dict for summary.json / runs table
    agent_rows: Callable | None = None        # (gt) -> {aid: {col: value}} for the agents table
    report: Callable | None = None            # (run_dir, inst, gt) -> list[str] markdown section
    scripted: Callable | None = None          # (k, aid, rng) -> action | None for ScriptedPolicy

FEATURES: list[Feature] = []        # filled in charter/features.py in an explicit, reviewed ORDER
```

The core then derives every list it keeps by hand today:

| Today (hand-kept) | Derived from the registry |
|---|---|
| `actions.ACTIONS`, `DM_ACTIONS`, `globals()[f"_{name}"]` dispatch | `{a.name: a for f in FEATURES for a in f.actions}` |
| `agents.ACTION_DOC`, the `absent` set, class lists in `system_prompt` | `ActionSpec.doc`, `available`, `classes` |
| `scorer.PRODUCTIVE`/`POLITICAL` | `ActionSpec.category` |
| `Kernel.api_for` return dict | core functions + `{fn.name: fn.make(k, lid)}` |
| `lawlang.API_GROUPS`, `STRUCTURAL_CALLS` | `LawFn.cls` |
| `lawdocs.E`, `agents.API_DOC` (full preset), `projects.API_DOC` | `LawFn.signature/detail/tiers/group/topic`. Keep the full-preset text byte-identical, enforced by a test |
| `render_event` if-chain, `MESSAGE_TYPES` ×2, `PUBLIC`, `POSTABLE`, `VEILABLE`, `FORGEABLE` | `EventType` flags |
| `Kernel.start_round`/`end_round`/`snapshot`/`view` feature calls | loops over `FEATURES` |
| `scorer.metrics`/`summary` literal, `report` sections, `runner._truth` | loops over `FEATURES` |

**How features build on one another** (the user's main aim). Each feature declares `LawFn`s, and a law is the main way features
compose: a later feature can register a law function that reads an earlier feature's `k.w[name]` state. Add one convention: a
feature reads another's state only through its public helpers (as `actions._contribute` already does with `P.pooled_value`), never
through its private keys. Then registry order (`FEATURES`) is the only dependency declaration needed. A `requires=("credit",)` field
can be added later if needed.

**What stays as it is.** Laws stay restricted Python, and kernel invariants stay in the kernel. Feature state stays in `k.w`, which
already gives checkpointing and dry-run rollback for free. Write that rule down: *no feature may keep state outside `k.w`*. The
observer is the one exception (`Observer` object state in `runner_state`), and it is fine as is.

**Cost against benefit.**
- Registries for actions, law functions and events: high benefit (they remove about 70% of merge conflicts), about 1.5 agent-days,
  low risk behind a golden test.
- `Feature` lifecycle loops: medium benefit, about 1 agent-day.
- Moving every feature module into a `features/` package: low benefit. **Do not do it.**
- Per-feature schema fragments: worth doing, but only together with recommendation 3.

---

## 2. Configurability

### 2.1 How runs are specified today

- **Specs** are YAML files in `charter/specs/`. `extends: [base, E3]` deep-merges the parents (`spec.deep_merge`, later files win),
  then this file on top. Presets E0–E7 are 4–13 lines each over `base.yaml` (212 lines, the full design, commented).
- **Distributions.** A value is fixed or a single-key mapping `{uniform|randint|choice|weights|beta: ...}` (`spec.is_dist`).
  - `generator.resolve_instance_level` samples all instance-level distributions with **one** `random.Random(seed)`, depth-first in
    key order.
  - `PER_ENTITY` keeps per-camp and per-agent ones (regrowth, stock, noise, personality, jitter, compute, archive copies, regime,
    events) as distributions for later draws.
- **Overrides.** `--set a.b=yaml` (`spec.apply_overrides`/`set_path`) applies last. A distribution given there is sampled.
  - `--fast` sets `turns: simultaneous`.
  - `sweep --vary k=v1,v2` (grid) and `explore --perturb k=<dist>` use the same path setter.
- **Regimes.** `regime:` takes a name, `{choice: [...]}` or an inline definition (`regimes.resolve`, own RNG). It fixes the
  constitution, statutes, rights and offices, and some spec keys. `start_laws:` enacts library laws at round 0.
- **Per-agent explicit choices.** These are keyed by agent *name*: `models.overrides`, `goals.explicit` (primary name only),
  `personality.explicit`, `personality.archetypes.explicit`, `judge`.
- **Enable flags.** `hidden.enabled`, `observer.enabled`, `events.enabled`, `projects.enabled`, `outside_power.enabled`,
  `personality.enabled`/`.archetypes.enabled`, `archive_split.enabled`, `shared_archive.enabled`, `dm_step.enabled`. Loans and credit
  have no flag: they are on by law (`start_laws`).
- **Run identity.** The directory name is `<spec>_seed<N>[_dry]_<sha of the resolved spec>`. `--fresh` gives a timestamped
  directory.

### 2.2 What is hard or impossible to express (all verified)

| Need | Today |
|---|---|
| **Typo detection** | None. Unknown keys are carried into `instance.json` and ignored (`--set observr.enabled=true` → no observer). Bad enums mostly pass: `models.mix=balancd` makes everyone weak, `turns=simultanous` and `conditions.fixer=honst` are accepted, and `start_laws=["Loan Registri"]` is accepted at generation but raises a `KeyError` in `runner.run` after the run directory exists. Only some keys validate: constitution, regime, `law_docs.preset`, archetype names. |
| **Mappings that look like distributions** | `goals: {weights: {Wealth: 2, Power: 1}}` in a spec file is read as a `weights` distribution. `deep_merge` **replaces the whole `goals` block**, `resolve` draws it to a string, and generation crashes with `AttributeError: 'str' object has no attribute 'get'`. `personality.archetypes` has a hand-written guard against this; `goals` and any future block with a `choice`/`weights` key do not. |
| **Exact rosters** | Agents come from class counts. Names are drawn by the generator RNG *after* a class shuffle, so names change whenever class counts or earlier draws change. Per-agent settings keyed by name must be re-learned after any change; `base.yaml`'s own example (`{A03: claude-opus-5-5}`) uses a naming scheme the generator no longer produces. Missing per agent: class, goal *parameters* (`goals.explicit` keeps only the goal name and always redraws params, e.g. a Rival's target), powers, codex articles, endowment and action count. |
| **"Same world, vary one factor"** | Works only for a fixed value replaced by another fixed value that consumes no draws (`constitution: assembly` vs `council`: same world). These all change every agent's goals: `{choice}` vs a fixed value, fixing `endowment_gini`, `models.mix` (strong_fraction samples, balanced shuffles), `goals.secondary_prob`, adding any new distribution key anywhere in the spec, and a regime (regimes change rights, and rights change goal weights such as Office). Observer on/off and events on/off keep the generated world, but runtime streams shift (see R5). |
| **Scripted events at given rounds** | Not possible. `events.attach_schedule` draws only Poisson times. You can lower a type's `mean_interval`, but not say "blight camp3 at round 12, public". The machinery (`events.fire(k, inst, e)` with `e = {round, type, seed}`) would accept a scripted entry with little change. |
| **Paired runs and designs** | `sweep` is a full grid with independent worlds per arm, so there is no way to declare paired arms on common random numbers, replicate blocks or a held-out factor. The README lists "the paired run needed for the Saboteur score" as not built. |
| **Documentation of every key** | Only `base.yaml` comments (good, but not checked, and silent about keys the code reads without listing them, e.g. `llm.backend_overrides`, `parallel_calls` defaults, `goals.class_conditioned` behaviour). |
| **Provenance** | The backend (`LLM_BACKEND`), code version, CLI version and command line are not stored. Resume infers dry mode from `"_dry" in out.name`. |

### 2.3 Proposals

1. **A spec schema (`charter/schema.py`), generated docs, `charter spec check|doc|explain`.** A plain nested dict of `Field(type,
   default, doc, enum=None, dist_ok=True, per_entity=False)` is enough; no dependency is needed (pydantic is optional). Each feature
   contributes its block (`Feature.schema`).
   - Validate after `extends` and `--set`, before sampling: unknown key → error with `difflib.get_close_matches`; enum and type
     checks; library and law names checked at generation.
   - Generate `docs/spec.md` and the defaults (`base.yaml` becomes a thin preset, or is checked against the schema in a test, which
     is cheaper and keeps its comments).
   - Make distributions unambiguous with the schema: a key whose type is `mapping` is never read as a distribution. Also accept an
     explicit tagged form `{dist: choice, of: [...]}` for new code.
   - `charter spec explain goals.secondary_prob` prints the doc, the default, which presets override it, and whether it consumes
     draws.
2. **Explicit rosters.** `roster:` is a list of agents; class counts are derived from it, and missing fields are drawn as now from
   per-agent substreams:

   ```yaml
   roster:
     - {name: Ada, cls: legislator, model: claude-opus-5-5, goal: {primary: Rival, params: {target: Bram}}, archetype: zealot,
        personality: {honesty: 0.1}, powers: [forge_dm], articles: [codex/law/credit-common], endowment: {stone: 10}, actions: 4}
     - {name: Bram, cls: worker}
     - {cls: worker, count: 6}          # anonymous slots, named from a stream independent of the rest
   ```

   Keep `agents: {worker: 6, ...}` as shorthand. Names come from a name substream indexed by slot, so the same slot gets the same
   name across factor changes.
3. **Scripted events.** `events.script: [{round: 12, type: camp_blight, visibility: public, params: {camp: camp3, factor: 0.2}}]`,
   merged into `world_events.schedule` (scripted entries get ids `X1..`). Handlers read `ctx["params"]` before drawing. Also allow
   `events.types.<t>.mean_interval: null` with a script, so the world contains only the scripted events.
4. **Designs and paired runs.** Add `charter design FILE.yaml`:

   ```yaml
   base: E6
   set: {rounds: 40, turns: simultaneous}
   seeds: [1, 2, 3, 4, 5]          # every arm uses the same seeds (paired)
   arms:
     control: {}
     observer: {observer.enabled: true, observer.disposition: manipulative}
   factors: {models.mix: [all_weak, all_strong]}   # optional grid crossed with arms
   ```

   This needs recommendation 5 (random substreams) to be meaningful. Rows carry `design`, `arm`, `pair_id = seed` and the factor
   values.
5. **Provenance.** Write a `run.json` with: the command line, `LLM_BACKEND` and `llm.backend_overrides`, `claude --version` or the
   SDK version, Python version, a content hash of `charter/**/*.py`, `generator_version`, `rng_version`, `scorer_version`, start and
   end times, and the resolved spec hash. Store `dry` explicitly instead of parsing the directory name.

---

## 3. Data and post-run analysis

### 3.1 Inventory of what a run writes

| File | Content | Notes |
|---|---|---|
| `instance.json` | resolved spec, agents (class, rights, model, tier, actions, goal slots and params, personality, archetype, endowment, archive docs), camps with hidden functions, constitution code, library, `observer`, `hidden` (articles, holders, secret camps, law-doc mapping), `regime`, `world_events` schedule, repairs, unreachable goals | Written once; arrivals are not added (they are in `ground_truth.arrived_agents`) |
| `events.jsonl` | every kernel event with `vis` (public, list, `channel:x`, monitor) | Includes harvest noise, turn orders, truth events (`anon_truth`, `report_truth`, `forged_dm`, `forgery_truth`, `world_event_truth`, `power_use`, `tip`, ...) |
| `reasoning.jsonl` | one row per model call: round, position, agent, model, phase (`decide`, `dm_reply_N`, `observer_step`, `observer`), native `reasoning`, `stated_reasoning`, notes, actions, results, `final_actions`, usage, `prompt` (the user turn), `prompt_chars`, error | System prompt only by reference (`prompts/`). About 1 MB for 4 dry rounds of E4; 28–51 MB for the partial E4/E6 runs |
| `prompts/<agent>.system.md` | system prompt per agent; `.from_rN.md` after a goal change or arrival | The observer's system prompt is here too |
| `snapshots.json` | per round: values, holdings, rights, vote weights, decisive set, franchise share, laws active, stocks, prices, supplies, reserve, effects, DM limits, loans, credit fields, projects, tribute, efficiency, predicates, welfare, `observer` | Monitor view |
| `ground_truth.json` | completion, start values, goals, final guesses, laws (code, patches, state), welfare series, units, cases, currencies, names, `shared_archive_at_start`, `hidden` truth, `world_events` truth and boundaries, `arrived_agents` | |
| `observer.jsonl`, `observer.md` | per observer call: transcripts read, assessments, actions sent, reasoning, usage | Only with the observer |
| `score.json`, `summary.json` | goal scores (per slot, segments), about 40 metrics, per-agent experimentation, observer score | Recomputed by `charter score` with *current* code |
| `checkpoint.pkl` | kernel state (`w`, events, snapshots, `turn_log` with all reasoning, RNG states, law globals, marshalled callbacks) + runner state | Grows with the run; `marshal` code objects are Python-version specific (R13) |
| `STOPPED.md`, `stop_history.md`, `report_error.txt` | fail-stop and reporting problems | |
| `spec_outline.md`, `overview.md`, `messages.md`, `agents/<name>/transcript.md`, `agents/<name>/working/*` | readable reports, rebuilt from the files above | |

### 3.2 Is everything needed saved?

| Item | Status |
|---|---|
| Full prompt per call | **Mostly.** The user prompt is saved per call (decide, DM replies, observer). The system prompt is saved per agent version in `prompts/`, but not referenced from the call row: you infer which `.from_rN` applied. DM-reply prompts embed the whole turn prompt again (the main source of file size). |
| Native thinking per call | **Field exists, but empty in practice.** 0 of 3,779 calls in the two usable model runs carry native thinking text, Haiku included. The current code adds `thinking_withheld` to the CLI usage, but the runs shown predate it. Record `thinking_present`/`thinking_withheld` explicitly per call, and warn at run start when the backend cannot return thinking for a model. |
| Stated reasoning per call | Yes, for every phase, including DM replies and the observer. |
| Model usage and cost | Tokens yes. Cost only for Claude Code (`cc_equiv_usd`); API calls get no cost; there is no per-run total. **Failed calls keep `usage: {}`** (2,098 failed calls in the two usable runs). `llm.call` discards the first failed attempt when its retry succeeds, so retries and their cost are invisible. |
| Failed calls | The error string only (`"_error"`). Not kept: the raw stdout/stderr, the exit code, whether it was a rate limit or a parse failure, and the raw text that failed `parse_json`. |
| Calls in an abandoned round | **Deleted.** `failstop.abandon` truncates `reasoning.jsonl` back to the checkpoint, so their prompts, outputs and token cost are lost. Writes to the shared archive in that round persist (documented). |
| Backend, model parameters, latency | Not stored per call or per run (`max_tokens`, thinking budget and backend override are in the spec but not in the call row). No timestamps or latency. |
| Random draws | Mostly reproducible from seeds, and logged where it matters: turn orders, harvest noise, event seeds, tips, regime draws. Not logged: values returned by laws' `rng()`, and the generator's intermediate draws (outcomes are in instance.json). Model sampling is not seeded and its temperature is not recorded. |
| The archive as read | Not frozen. Scoring re-reads `archive/` and the shared archive at scoring time (`scorer.metrics` leaks, `goals._archive_shingles`), so a later edit to the archive changes old runs' scores. |
| Code version | Not stored, so scores cannot be tied to the code that produced them. |

### 3.3 Trying the research questions on existing runs

Runs under `charter/out/`:
- E4 seed 1 `USABLE-r1-23` (23 good rounds of 40);
- E6 seed 1 `USABLE-r1-10` (10 good rounds of 80; the other rounds failed when the Claude Code session limit was hit);
- seven dry runs, plus the new one;
- old, invalid and stopped runs.

**Q1. Do smarter agents achieve their goals more often** (score by model tier and class, controlling for goal type)? Doing it took a
script that:
1. loads `ground_truth`, `snapshots` and `events`, and **truncates them by hand to the usable rounds**: the scorer has no
   `until_round`, and the validity notes are free-text `VALIDITY.md` files (one run also has a hand-added `usable_rounds` in
   summary.json);
2. calls `scorer.goal_scores`;
3. joins `tier` from `instance.json`, because `score.json -> agents` has `model` and `archetype` but no tier, goal type or category;
4. finds that 28 of 47 agents' truncated scores differ from the stored `score.json`, so the stored files are misleading.

Result (anecdotal, n=47 across 2 worlds): weak 0.458 (n=13), strong 0.289 (n=20), strongest 0.260 (n=14). This cannot be read as an
effect:
- there are 22 distinct primary goals among 47 agents, and only 9 goal × tier cells have n ≥ 2;
- goal scores sit on different scales: relative to the richest agent (Wealth), binary (Office, Sovereign), or fractions of rounds
  (Safety);
- no "achieved" threshold is defined.

**Q2. Which archetypes experiment more?** `summary.experimentation_by_archetype` exists, but **every stored summary.json predates it**
(all 8 lack it, and `regime_start`). The data must be rescored in memory. Rescoring worked for all 11 runs with ground truth, but
`charter score` would overwrite the stored files, so there is no "rescore to a side location" option. Archetypes exist only in the
dry runs. Experimentation counts come from regexes over result text (see 1.2).

**Q3. Does the observer's presence change what agents write?** `metrics.watch_mentions` is computed in every run, which is a good
design. But no model run has the observer, and the comparison is confounded today, because turning the observer on changes
hidden-layer tip draws for other agents (R5). The observer can also leak into feeds (R2, R3), which would cause exactly the
mentions being measured.

**Q4. How often do regimes change, by starting regime?** `regime_start` and `regime_changes` are in the current summary but not in
any stored one. `regime_changes` counts flips of a label computed from decisive-set size and franchise share. Small worlds flip on
noise; for example, E0 starts as "dictatorship" because its single Legislator is the decisive set. `scorer.regime(s, n_agents)`
ignores `n_agents`.

**Cross-run friction.** There is no cross-run aggregation except `sweep`'s `summary.csv`, which is per sweep and covers summary
fields only. `charter/out/` mixes stable and `--fresh` names, and labels like `_USABLE-r1-23` are hand-renamed directories. No
machine-readable validity or exclusion flag exists.

### 3.4 Proposal: a tidy, versioned, cross-run dataset layer

**1. Per-call record (runner and llm).** Extend each `reasoning.jsonl` row (or add `calls.jsonl`) with:
- `call_id`, `ts_start`, `latency_s`, `backend`, `model`, `max_tokens`, `thinking_budget`;
- `system_prompt_sha` (prompts stored by hash), the user prompt;
- `raw_text` (pre-parse), `parsed`, `native_thinking`, `thinking_present`, `stated_reasoning`;
- `attempts: [{error, usage, latency}]`, `usage` (summed over attempts), `cost_usd` (API rate table or CC figure), `error_kind`
  (`rate_limit`, `auth`, `parse`, `timeout`, `cli`).

On fail-stop, move the abandoned round's rows to `abandoned_calls.jsonl` instead of truncating them away.

**2. `validity.json`** (machine-readable), written by the runner:

```json
{"usable_rounds": [0, 22], "excluded": false, "notes": "..."}
```

The runner fills it automatically: rounds in which every agent call failed are marked dead. This replaces `VALIDITY.md` and
directory renames.

**3. `scorer.score(run_dir, until_round=None, out=None)`.** Scores the usable window by default, writes `score_version`, and can
write to a side location. Freeze scoring inputs: copy the archive documents read during the run, and the shared archive at start,
into `run_dir/frozen/` (or store their hashes), so that scores are recomputable.

**4. `charter export RUNS... --out DIR [--format parquet|csv]` and `charter.data.load(glob)`.** Writes long tables with
`dataset_schema_version` in each file's metadata:

| Table | Grain | Key columns |
|---|---|---|
| `runs` | run | `run_id`, design/arm/pair, spec factors flattened (`constitution`, `regime`, `law_level`, `models.mix`, `observer.enabled`, `events.enabled`, ...), provenance (backend, code hash, versions), validity window, all summary metrics |
| `agents` | agent × run | class, model, tier, `tier_rank` (0/1/2), archetype, personality traits, goal per slot (name, category from `goals.CATALOGUE`, weight, params, reachable, score), total score, an `achieved` flag per goal (a documented threshold per goal), segments, arrival/departure, powers held/known, articles held, experimentation counts, start/end value, power index, tokens/cost/failed calls |
| `agent_rounds` | agent × round × run | holdings value, rights count, vote weight, in decisive set, efficiency by camp, actions by category, DMs sent/received, posts, errors, tokens, `watch_mentions` |
| `events` | event | `run_id`, `id`, round, type, agent, `vis_kind` (public, private, channel, monitor), recipients, flattened common data fields (to, item, qty, law, text_len), plus `data_json` |
| `calls` | model call | as in point 1, minus long text by default (`--with-text` keeps it) |
| `laws` | law × run | author, class, status, proposed/enacted/repealed round, library match, patches, `self_dealing` |
| `observer_assessments` | observer × target × round | suspected goal, correct, deceptive flag, `read_this_round` |

Each `Feature.agent_rows`/`summary` adds its own columns, so new features appear in the dataset automatically.

**5. `charter analyze` and a short `charter/analysis.py`** of tested recipes for the four questions above. For example, Q1 becomes:

```python
ag = charter.data.load("charter/out/**").agents
ag.query("not fixed").groupby(["goal_category", "tier"]).score.mean()
```

A mixed model `score ~ tier + cls + (1|goal)` is documented, not built in.

### 3.5 Is scoring consistent, documented and recomputable?

- **Recomputable:** partly. `charter score` rebuilds from the files with the current code. It is not reproducible across code or
  archive changes: there is no `score_version`, archive leaks are read live, and `regime_start` re-plays the instance with the
  current regimes and kernel code.
- **Consistent:**
  - Goal scores mix scales (see Q1), and `README` does not state them.
  - `capability_gap_by_class` lumps `strongest` and `explicit` into "strong".
  - `knowledge_transfers` can append one entry per later snapshot for the same DM (the `break` only leaves the inner loop).
  - `mean_goal_score` raises if every score is None, and `lowest_stock` raises if no stocks remain (all camps destroyed or
    secret).
  - Leak metrics have two definitions (see 1.2).
- **Documented:** the module docstrings list the metrics. There is no per-metric definition table and no goal-scale table. Generate
  both from the registry (`Feature.metrics` docstrings) into `docs/metrics.md`.

---

## 4. Risks found along the way

V = verified (code read *and* reproduced, or unambiguous by code reading); S = suspected.

| # | Risk | Status | Where | Fix |
|---|---|---|---|---|
| R1 | **The public `respond` event leaks the evidence events in full**, including a forged DM's true sender (`agent`) and `shown_as`. Reproduced: a third agent's feed showed `"agent": "Nina"` (the secret observer) for a forged DM | V | `actions._respond` logs full event dicts; `agents.render_event` maps evidence to ids only for `accuse` | Log evidence ids only, for both actions |
| R2 | **The secret observer is in the hidden layer's pools.** `hidden.on_round_start` iterates `sorted(k.w["agents"])`, so the observer receives tips. `hidden.tip`'s `others` includes it, so a false rumour can name it: in 400 sample tips, 4 named the observer. `_quill`/`_agent_arg` accept it as sender or recipient | V | hidden.py | Use `k.roster()` (minus departed) everywhere outside the kernel |
| R3 | **The observer is in the world-event pools.** `events.active()` excludes only Board and Fixer, so the observer can be the discoverer, receive subset or rumour news, be named in holdings or deal rumours, or **be the agent that publicly departs** | V | events.active, h_agent_departs, _r_holdings, _r_deal | Same as R2 |
| R4 | **Dry runs leave changes in law module globals.** `_snapshot`/`_restore` deep-copy `law["state"]` but not module-level mutable values. Reproduced: a law that appends to a module-level `ticks = []` gained three entries after another law's preview. The same happens through `procedure_spec` (called once per agent per round by `decisive_set`) and `probe`, and these values are then checkpointed in `ns_data` | V | kernel._snapshot/_restore | Deep-copy each law namespace's non-callable data (as `checkpoint_state` already selects it) in `_snapshot` and restore it |
| R5 | **Random streams are coupled.** (a) One generator stream: any change in draws upstream (a distribution fixed, a new spec distribution, model mix, regime rights) redraws all goals, camps and endowments. (b) The kernel `rng` produces both turn orders and harvest noise (and drift), so one extra harvest changes all later turn orders. (c) `hidden.on_round_start` draws two numbers per agent in sorted-name order, so the observer or an arrival shifts every later agent's tips and discoveries | V | generator.generate, kernel.rng, hidden.on_round_start | Named substreams (plan phase 5); per-round order stream `Random(f"{seed}|order|{r}")`; per-agent tip stream |
| R6 | **The effect preview misses feature state.** `Kernel.view` compares holdings, rights, reserve, currencies, procedures, camps, names, actions, laws, limits, DM limit, suspensions and projects, but not loans, default consequence, interest cap, par or redemption, tribute, or hidden-layer changes (`disclose`, revoked capabilities). A law's preview can look empty while it changes credit rules | V | kernel.view | `Feature.preview_view` |
| R7 | **Resume overwrites original system prompts.** After `EV.restore`, agents whose goal changed have their new goal, and `runner.run` writes `prompts/<agent>.system.md` again from it. The pre-change prompt is lost (the `.from_rN` file stays) | V (code) | runner.run on resume | Do not rewrite existing prompt files; store by hash |
| R8 | **Arrivals miss generation-time features:** no archetype, no codex articles or powers; models and archive drawn by different rules | V (code) | events.add_agent | `Feature.on_arrival` |
| R9 | **Spec merge clobbers single-key mappings** (`goals: {weights: ...}` crashes; any `{choice: ...}`-keyed block is at risk) | V | spec.deep_merge/is_dist | Schema-aware merge |
| R10 | **Forged DMs differ by path:** cost, truth event type, metrics, and fast-mode delivery (an `invoke` forgery misses the DM step). The power can also forge to a departed agent, because `act()` checks `to`/`agent` only in dict args, not `invoke` arg lists | V / S (departed) | actions._forge_dm, hidden._quill | One `messaging.forge_dm` |
| R11 | **The fail-stop tally includes the observer's DM-reply calls**, although the code says "the observer never counts" | V (code) | runner.dm_exchange `tally.add` over `asks` | Filter out `obs.id` |
| R12 | **Unchecked spec values** (`start_laws`, `models.mix`, `turns`, `conditions.*`) fail late or silently | V | generator, runner | Schema (plan 3.1) |
| R13 | **Checkpoints are fragile and large.** Callbacks are pickled as `marshal`-ed code objects, which are Python-minor-version specific (a resume after a Python upgrade fails). The pickle holds all events and the full `turn_log` (every turn's reasoning), so it grows quadratically in I/O over a long run | S | kernel.checkpoint_state | Store the Python version and refuse a mismatch with a clear message; keep `turn_log` bounded (the readers use the last few rounds) or rebuild it from `reasoning.jsonl` on resume |
| R14 | **Snapshot cost.** `decisive_set` calls `procedure_spec` once per roster agent, and each call deep-copies `k.w`. That is O(agents × world size) per round, heavy at E7 (61 agents, more with arrivals) | S | kernel.decisive_set | Probe once per distinct (class, author-relevant) case, or cache by procedure key and round |
| R15 | **Scoring reads live external state** (archive files, current code), so old scores change silently | V | scorer.metrics, goals.leaks, scorer._regime_start | Freeze inputs; `score_version` |
| R16 | **Experimentation metrics parse error strings** | V | probing | Log a structured `action_error` event with `kind` |
| R17 | **The run's backend is not recorded**, so model runs on the API and on Claude Code cannot be told apart afterwards (except by `cc_equiv_usd`) | V | __main__.run_one | `run.json` provenance |
| R18 | **Leftover parallel-build seams.** The `P.maybe_spawn` "re-route ... delete this line" note in `Kernel.start_round`; two copies of model assignment (generator and events); `PER_ENTITY` must list every per-entity distribution, or it is drawn once for the whole instance | V | kernel, generator, events | Plan phase 4 |

Nothing found suggests resume is wrong for state inside `k.w`. Everything except the observer's object state and the runner's
notes and cursors lives there, and both of those are checkpointed. The weak points are module globals (R4), prompt files (R7) and
external side effects (the shared archive, documented).

---

## Phased plan

Every step is sized for one agent, leaves the tests green, and touches few shared files. Steps within a phase are independent
unless noted.

**Phase 0: safety net (do first)**
- 0.1 **Golden dry-run fingerprints.** A test runs scripted dry runs (E2 6 rounds; E4 fast 4 rounds; E6 3 rounds; E7 3 rounds with
  events; E4 with observer and hidden) and compares SHA-256s of `events.jsonl`, `snapshots.json` and `instance.json` with stored
  values. `CHARTER_UPDATE_GOLDEN=1` rewrites them; the commit message must say why. Refactors must not change them; bug fixes that
  change behaviour update them explicitly.
- 0.2 **Consistency tests:**
  - `api_for` keys == `lawlang.API` == `lawdocs.ENTRIES` (minus hooks and features);
  - every `ACTIONS` entry has an `ACTION_DOC` line and an activity category;
  - every logged event type in the golden runs has a render rule or is explicitly feed-silent;
  - no non-roster agent ever appears in a `vis="public"` event or in another agent's `notify`.

**Phase 1: correctness fixes (each about one hour; update golden hashes where noted)**
- 1.1 R1: evidence ids only in `respond` (and `accuse`).
- 1.2 R2 and R3: one `k.players(include_departed=False)` helper (roster minus observer); use it in `events.active`, `hidden.tip`,
  `hidden.on_round_start` and `hidden._agent_arg`. Golden update: hidden-tip draws change.
- 1.3 R4: snapshot and restore law namespace data in dry runs, with a regression test (the `ticks` law above).
- 1.4 R9: make `deep_merge`/`resolve` leave known mapping keys alone (a stopgap list now; the schema later), and add a test for
  `goals: {weights: ...}`.
- 1.5 R7: never overwrite an existing `prompts/*.system.md`.
- 1.6 R6: add credit, tribute and hidden fields to `Kernel.view`.
- 1.7 R10: a single `forge_dm` core with a `source` field; `forged_dm` and `forgery_truth` become one truth type (keep a reader
  alias for old runs).
- 1.8 Stale `PRODUCTIVE`/`POLITICAL` sets; the `mean_goal_score` and `lowest_stock` empty-input crashes; the `knowledge_transfers`
  duplicates; R11.
- 1.9 Validate `start_laws` and library names at generation.

**Phase 2: data and provenance (highest research value)**
- 2.1 `run.json` provenance (R17); `dry` stored explicitly; `generator_version`/`scorer_version` constants.
- 2.2 Per-call record: raw text, attempts with usage, latency, backend, cost, `error_kind`, `thinking_present`; abandoned-round
  calls kept in `abandoned_calls.jsonl`.
- 2.3 `validity.json` written automatically (dead rounds detected); `scorer.score(until_round=..., out=...)`; `charter score
  --until-round --out`.
- 2.4 Freeze scoring inputs (the archive documents read, hashed or copied); one leak definition.
- 2.5 `charter export` with the `runs`/`agents`/`agent_rounds`/`events`/`calls`/`laws` tables and a schema version (CSV always;
  parquet if pyarrow is present).
- 2.6 `charter.data.load` + `charter analyze` with the four recipes; a documented goal-scale table and an `achieved` threshold per
  goal.

**Phase 3: configuration**
- 3.1 `schema.py` covering `base.yaml`, plus validation in `build_spec` (unknown keys with did-you-mean, enums, types).
  `charter spec check`.
- 3.2 Generate `docs/spec.md`; add `charter spec explain KEY`; a test that `base.yaml` and the schema agree.
- 3.3 `roster:` (explicit agents; a name substream by slot; goal params honoured).
- 3.4 `events.script` (scripted events merged into the schedule).
- 3.5 `charter design` (paired arms on shared seeds; arm, pair and factor columns in the outputs). Do this after phase 5.

**Phase 4: registries (reduces merge conflicts)**
- 4.1 `ActionSpec` registry; derive `ACTIONS`, `DM_ACTIONS`, `ACTION_DOC`, `absent` and the categories. The golden hashes and
  system prompts must stay byte-identical (add a test comparing every preset's system prompts before and after).
- 4.2 `LawFn` registry; generate `API_GROUPS`, `lawdocs.E` and the `API_DOC` text. Full-preset text byte-identical.
- 4.3 `EventType` registry; replace the seven type lists and the `render_event` if-chain (delegation stays).
- 4.4 `Feature` lifecycle loops in the kernel (init, round start, round end, view, snapshot), runner (truth), scorer (metrics,
  summary, agent rows) and report sections. Wrap the existing module functions; do not move code.
- 4.5 `Feature.on_arrival` (fixes R8); `Feature.schema` fragments merged into `schema.py`.

**Phase 5: random-stream isolation (breaks world reproduction once; gate it)**
- 5.1 `rng_version: 2` in the spec (default for new runs). In the kernel, turn order comes from `Random(f"{seed}|order|{r}")` and
  harvest noise from `Random(f"{seed}|noise|{agent}|{camp}|{r}|{n}")`. Keep version 1 code paths for resuming old runs.
- 5.2 Generator substreams: `sub(seed, "classes")`, `"names"`, `"camps", i`, `"rights"`, `"models"`, `"goals", slot_index`,
  `"personality", slot_index`, `"endowments"`, and instance-level distributions keyed by their dotted path
  (`sub(seed, "spec", "endowment_gini")`). Test that fixing one factor leaves the other draws unchanged.
- 5.3 Then do 3.5 (designs and paired runs), and the Saboteur paired score.

Suggested order: 0 → 1 → 2.1–2.3 → 3.1 → 4.1–4.3 → 2.4–2.6 → 5 → 3.3–3.5 → 4.4–4.5.

---

## Appendix: shared touchpoints per feature

Columns:
- K: kernel.py (init, start_round, end_round, api_for, view, snapshot, other);
- A: actions.py;
- AG: agents.py (ACTION_DOC, API_DOC, absent, world_rules or class_brief, render_event, state_view, ScriptedPolicy);
- R: runner.py;
- LL: lawlang.py;
- LD: lawdocs.py;
- G: generator.py;
- S: scorer.py;
- Rep: report.py;
- Y: base.yaml.

The last column counts shared files edited.

| Feature | K | A | AG | R | LL | LD | G | S | Rep | Y | Other | Shared files |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DM step and DM limit | init (`dm_limit`, `dm_sent`), start_round reset, `dm_cap`/`dm_limit`/`set_dm_limit`, api_for, view, snapshot | `_dm_check`, `_set_dm_limit`, `DM_ACTIONS` | ACTION_DOC, API_DOC, absent, world_rules, class_brief, render_event, turn_prompt, `dm_prompt` | `dm_exchange`, `execute` filtering | read and sanction groups | messages topic | `dm_rules` to the controller | — | — | `dm_step` | failstop counts reply calls | 8 |
| Loans and credit | init (loans keys), `settle_loans`, `price` (par), end_round, api_for (+`CR.law_api`), snapshot | lend, accept, repay, extend, redeem par, deposit | ACTION_DOC ×4, API_DOC Credit and Par, absent, render_event (inline loan types + `CR.render`), state_view, ScriptedPolicy | — | money and read groups | loans, credit, par topics | — | metrics and summary | 1 | `credit` | goals (Creditor, Reserve banker), library laws | 8 + library + goals |
| Goals (49, three slots) | — | — | system prompt goal text, `goal_prior` | `_truth` goals | — | — | goal drawing, `_relational_targets`, score weights | `goal_scores` | goal sections | `goals` | events (segments, draw_goals), observer (goal guesses) | 5 |
| Archive split and rare records | — | `_read_archive`/`_search_archive` (`archive_docs`) | class_brief, library_text | — | — | — | split and rare draws | leaks | outline | `archive_split` | events.add_agent (separate split) | 5 |
| Archetypes and probing | — | — | (temperament text via generator) | — | — | — | `AR.assign` | experimentation, agents_out, summary | outline | `personality.archetypes` | probing parses result strings | 4 |
| Fail-stop and resume | `checkpoint_state`/`restore_state`, `_dump_fn`/`_load_fn` | — | — | checkpoints, `Tally`, resume trimming | — | — | — | — | — | `llm.fail_stop_fraction` | __main__ (stable dirs, `_same_instance`) | 3 + __main__ |
| World events | (via `w["world_events"]`), `round_summary` hides undisclosed camps, `has` (departed) | `act` departed checks, `_harvest` destroyed check | render_event (`world_event`), state_view (`known_by`) | `EV.round_start`, `EV.restore`, `_truth` | — | — | `attach_schedule`, `PER_ENTITY` | load (arrivals), `goal_scores` segments | overview, outline | `events` | hidden spawn requests | 7 |
| Projects | `P.init_state`, `P.start_round`, `P.maybe_spawn`, api_for, view, snapshot | `_contribute` | ACTION_DOC, API_DOC, absent, world_rules, render_event, state_view, ScriptedPolicy | — | projects groups | projects topic | — | metrics and summary | overview | `projects` | library laws | 8 + library |
| Tribute (outside power) | `O.init_state`, `O.start_round`, api_for, snapshot | `_pay_tribute` | ACTION_DOC, absent, world_rules, render_event, state_view, ScriptedPolicy | — | projects group | projects topic | — | metrics and summary | overview | `outside_power` | library laws | 8 + library |
| Hidden powers and codex | `H.install`, `H.on_round_start`, api_for (+`H.law_api`), `rights_of`/`camps` filters | `_invoke` routing, `_read_archive`/`_search_archive`, `_harvest` (visible camps) | API_DOC via `H.api_doc`, `H.prompt_section`, absent (`H.undocumented_actions`), render_event (`H.as_shown`, `H.render`), state_view (secret rights and camps) | `H.apply_order`, `_truth` | patched in place | the whole module | `hidden.generate` | `H.metrics` and summary | `H.outline` | `hidden`, `law_docs` | events (spawn requests), archive | 10 |
| Secret observer | init (observer agent), `roster()`, snapshot `observer` entry, `franchise_share` | `_forge_dm` | `LLMPolicy` schema switch, ScriptedPolicy delegation | `OBS.start`, step_prepare/finish, turn, `runner_state` | — | — | `OBS.make` | `OBS.score`, watch metrics, summary | overview, `observer.md` | `observer` | — | 7 |
| Starting regimes | — | — | world_rules (`RG.describe`) | `RG.enact_statutes` | — | — | `RG.resolve/finish/apply_rights/validate`, `constitution_code` | `_regime_start`, summary | outline, overview | `regime` | __main__ `run_stem` compatibility hack | 6 + __main__ |
