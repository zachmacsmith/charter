# Review 02: prompts, manual, archive (everything an agent reads)

*7 Oct 2026. Read-only review of the working tree, including the uncommitted wiring of `action_registry` into `context.core_prompt`
and `manual.sections` (`purposes.py` deleted). Evidence comes from reading the code and from rendering `society` seed 5 and `E6`
seed 1 in memory. `tests/test_charter_prompts.py` passes (15 tests). This review builds on `charter/docs/architecture_review.md`
(4 Oct, rec. 4 and §1.2-1.3) and does not repeat its status audit.*

## 1. Verdict

**Grade: C+.** The owner is half right. The infrastructure is better than the line count suggests:

- deterministic token sizing and clipping;
- per-layer budgets with a record of what was cut;
- a declarative action registry with a small requirements DSL;
- a tiered law-docs registry (`lawdocs`) that generates both prompt text and codex articles;
- spec- and profile-level section edits (`composition.apply`).

The weak part is the content model around that infrastructure. The same fact is written in prose in two to four places, and those
places already disagree. In the most-read manual sections they disagree with the mechanics the agent actually runs under.

- Two prompt pipelines coexist: `agents.system_prompt` and `context.core_prompt`.
- Three extension mechanisms exist for manual sections, and only one has users.
- Four condition DSLs decide "is this text relevant here".
- Mechanic numbers are hardcoded in prose and patched with `str.replace`.

The total cannot shrink much, because most of the bulk is prose content, and prose is the product. The realistic code reduction is
about 15-20% of the ~1,500 text-generation lines. The real payoff is one source of truth per fact, plus a test that catches drift.

## 2. How text is generated today

```
                       spec + instance (+ kernel when live)
                                    │
     ┌──────────────── context.enabled? ────────────────┐
     │ no (E0-E7, full10, opus20, village7 ...)          │ yes (society, grand35, scientists, explore15, context_pilot)
     ▼                                                   ▼
agents.system_prompt (agents.py:325)               context.core_prompt (context.py:889)  ← rebuilt every turn (runner.py:289)
  world_rules + class_brief + goal_prior            overview() [the only cuttable part] + identity(_class_line)
  + hand-made `absent` set (332-358)                + leverage_line (LEVERAGE_CLASS/ROLE) + roles/hidden prompt_section
  + ACTION_DOC lines + API_DOC (via hidden)         + action_sections(action_registry.layout) + manual_index
  + hidden/media/roles/conflict prompt_section      + composition.insert(_CORE) + composition.apply(edits)
  + library_text                                    │
agents.turn_prompt / feed / state_view              ├── build_manual (context.py:489)
                                                    │     MANUAL_SECTIONS=[manual.sections]   (base: world_rules, class_brief,
                                                    │       RIGHT_DOC, goal_prior, "Actions: *" via ACTION_DOC|purpose,
                                                    │       API_DOC, codex, archive index)
                                                    │     + composition._MANUAL (Conflict, Media, Life: reuse prompt_section)
                                                    │     + _module_sections(KNOWN_MODULES)    ← no module implements it
                                                    │     + composition.apply(edits) → chunk() to lookup budget
                                                    └── context.turn_prompt: state/feed/recent/scratchpad/media/pinned/lookups
observer.system_prompt (observer.py:189): world_rules + ACTION_DOC[allowed_actions] + own prose
media.editorial_prompt (media.py:586), roles.role_text (roles.py:219), hidden.api_doc → lawdocs.api_doc
goals._common_shingles (goals.py:798): AG.API_DOC + world_rules  ← scoring depends on old-pipeline prose
```

**Budgets.** `core_prompt` assembles the "essentials" (identity, goal, actions, manual index, reply), which are never cut, and then
clips `overview()` into whatever room is left. The floor is `max(200, ...)` (context.py:963), so the budget is soft: if the
essentials grow, the prompt goes over. With the default `core: 2500`, the Scientists in `society` would be at 2,658-2,825 tokens.
`society.yaml` raised the budget to 3,500 with the comment "the sectioned action list needs the room" rather than fixing the size.
Manual sections are hard-chunked into "(part N)" pieces at `lookup - 40` tokens (context.py:500). The turn layers trim
deterministically by priority (feed_layer), and this part is good.

**Cost.** `build_manual` runs at least 4 times per agent turn: `core_prompt`, `unread_counts`, `feed_layer→manual_changes` and
`record_turn`. For a Scientist each build takes about 0.8 s, because it indexes the archive and lists every other Scientist's
titles. That makes `core_prompt` 1.8 s for a Scientist against 0.05 s for a Worker. A 40-round `society` run spends roughly 9 CPU
minutes rebuilding identical manuals.

## 3. Duplication and inconsistency found

### 3.1 One action, four descriptions

Each action now has:

- a `purpose` and `args` in `action_registry.REG`;
- a full doc line in `agents.ACTION_DOC`, merged with `J.ACTION_DOC` and `MD.ACTION_DOC`;
- membership in a module `ACTIONS` tuple and in `actions.ACTIONS`;
- a category in `scorer` / `MD.CATEGORIES`.

The four name sets agree today (94 each, checked), but only `ACTIONS ⊆ ACTION_DOC` is tested (test_charter_consistency.py:23).
Nothing pins `REG == ACTIONS`. The registry's `args` repeats the JSON shapes already in `ACTION_DOC`, and one of them already
differs: `dm` in REG omits `encrypted`. `context.LOOKUPS` / `ACTIONS` / `FILE_ACTIONS` restate `pre=True` and `needs=mod:context`.

### 3.2 Availability is still decided twice

`agents.system_prompt` keeps its own `absent` set:

- per-level rules, DM channel, typed camps, leases, outside power, projects (agents.py:332-358);
- plus class lists (agents.py:359-362);
- plus `CF/J/MD/LF.absent_actions`.

These are the only callers of the four `absent_actions` functions. `MD.absent_actions` uses `inst_editor` / `inst_scholar`, while
the registry uses `_k_editor` / `_k_scholar_self`, with the comment "the checks the actions themselves make". That is a third copy
of the rules that live in the action handlers.

### 3.3 The manual contradicts the core prompt

In `society`, `lookups_in_dm_step` is on and context defaults apply:

- **"How your turn works"** (manual.py:70-79) says lookups go in the `"lookups"` field "with `actions` empty" and that you "are then
  asked again". The core prompt says pre-actions use private-message slots. The section also hardcodes "10 best matches"
  (`search_hits`), "your own last {recent_turns} turns" (Zeno is told 2 in the core prompt, 3 in the manual), and the scratchpad
  default size, ignoring profiles and Life stats (`scratchpad_size`).
- **The `read_archive` doc line** reads "Scientists only; the text comes back next turn". **The `run_python` doc line** reads "you see
  the output next turn". Both are wrong as pre-actions. The prompt test bans the phrase "each read or search uses an action" in
  the core prompt but never checks the manual.
- **`post`** is "public board" in the manual. In the core prompt, the submissions override turns it into "ask the newspapers to print
  your public post" (context.py:915). The override is applied to only one of the two renderers.

### 3.4 Numbers in prose versus spec values

| Prose | Spec value | Places |
|---|---|---|
| attack "uses 2 actions" | `conflict.attack_cost` | ACTION_DOC; `prompt_section` uses the config value |
| fortify "after 2 rounds" | `conflict.fort_unlock_rounds` | ACTION_DOC |
| loan offer "lapses after 2 rounds" | `credit.offer_lapse` | agents.py:70, manual.py:133, lawdocs.py:109 |
| Board "2-round window" | `veto_window` | world_rules:177, class_brief:291 |
| "a Board of three" | number of board agents | overview:857 (not conditional on a Board existing, unlike world_rules) |
| subscribe "at most 3", edition "600 tokens", annotate "5 per round", "60 tokens", "1,000-token files" | `media2.*` | MD.ACTION_DOC; `prompt_section` uses the config values |
| forge_dm "costs 1 copper" | `observer.forge_cost` | ACTION_DOC |
| "dry-run for 3 rounds" | proposal preview length | API_DOC and lawdocs.FOOTER |

The forge_dm cost is patched with `AG.ACTION_DOC["forge_dm"].replace("1 copper", cost)` in roles.py. The observer prompt prints the
real cost in its own prose and then the unpatched ACTION_DOC line beneath it, so the observer can be told two different prices.
More string surgery of the same kind:

- `CAMP_SHORT[...].replace("open to all but the Board and Fixer", ...)` (context.py:848);
- `class_brief(...).split("\nYour part of the archive")[0]` (manual.py:90);
- `leverage_line` swapping out the Legislator sentence (context.py:780).

### 3.5 Class, role and right text is scattered

- **Scientist class description.** Written twice in different words: `context._one_class_line` (core) and `AG.class_brief` (manual
  "Your role", old pipeline). Their free-read rules differ ("Reading a document you hold is free (as a lookup...)" against "up to
  {free} read_archive per turn... the text arrives with your next turn's results").
- **Dual-class articles.** A hand dict of articles for dual classes (context.py:792).
- **Roles in the core prompt.** Each role is described twice: `LEVERAGE_ROLE[r]` (context.py) and `roles.role_text` (roles.py:219).
  Maker is described twice in Zeno's prompt, in consecutive paragraphs.
- **Rights.** `manual.RIGHT_DOC` names actions in prose ("Media's press: publish, write_digest, report, channels"), which the
  registry already knows (`needs=right:press`).
- **Codex articles.** The held list appears in the core prompt (`H.prompt_section`) and again in the manual ("Codex articles you
  hold").

### 3.6 Extension mechanisms and dead code

- **Manual sections.** Three ways in: `context.MANUAL_SECTIONS` (manual.py only), `composition.manual_section` (conflict, media,
  life: used), and `KNOWN_MODULES.manual_sections` (no implementer; `importlib` loops over 9 modules on every build). The
  `manual.py` docstring advertises the dead path.
- **Core sections.** `composition.core_section` has no registrations.
- **Hand-kept lists.** `composition.PLUGINS` is a hand list that must name every module that registers a section.
- **Dead functions.** `context.grouped_actions` is dead.

### 3.7 Four condition DSLs for "is this relevant here"

- `action_registry` needs: `mod:` / `right:` / `cls:` / `level:` plus `when`;
- `archive.NEEDS`: `"a|b"` module strings plus the `OLD_CAMPS` / `TYPED_CAMPS` sets;
- `lawdocs`: `OPTIONAL`, `REQUIRES`, `_gated_off`, `MODULE_ENTRIES`;
- section functions returning `""`.

Each module-enabled check is reimplemented. Examples: `(sp.get(x) or {}).get("enabled")` with differing defaults (projects
defaults on), and `inst_editor` against `_k_editor`.

### 3.8 Stale or coupled artefacts

- `docs/prompt_preview.md` is a hand-committed snapshot that is already stale: "Actions (" in place of "ACTIONS (", and
  `copy_agent` shown in the edge.
- `goals._common_shingles` treats only old-pipeline text (API_DOC, world_rules) as public. In context worlds the overview, manual
  and codex text are what agents actually see, so the Leaker metric is computed against the wrong "common knowledge".

## 4. Proposed design

The principle: **every fact is owned by the module that implements it, as data plus a render function. Every reader-facing surface
(core prompt, manual, "Actions: all", observer prompt, old prompt) is a view over the same records.** No templating engine, and no
prose moved to YAML. f-strings over a facts dict are enough.

### 4.1 One context object, cached per agent-round

```python
@dataclass(frozen=True)
class View:                        # what every text function receives instead of (inst, k, aid) / (inst, a) / (k, aid)
    inst: dict; k: object | None; a: dict
    rights: frozenset; classes: frozenset; roles: frozenset
    @cached_property
    def facts(self) -> dict:       # every number prose may mention, read from spec/config once
        sp = self.inst["spec"]
        return {"veto_window": sp["veto_window"], "attack_cost": CF.config(sp)["attack_cost"],
                "offer_lapse": CR.cfg_spec(sp)["offer_lapse"], "search_hits": CX.cfg(sp)["search_hits"],
                "forge_cost": fmt_cost(sp), "memory_turns": CX.memory_turns_of(self.a), ...}
    def on(self, mod) -> bool: ...  # the ONE module-enabled check (projects default etc. live here)

def view(inst, k, a) -> View: ...  # memoised on (a["id"], k.r, len(k.events)) → build_manual once per turn
```

### 4.2 Actions: extend the existing registry, do not replace it

I disagree with the old review's `available(inst, agent)` callable plus `classes` tuple. The `needs` DSL that now exists is better:
it can be inspected, so it can also generate the "who can do what" text and the "requires the X right" notes. Extend `Act`:

```python
R("attack", section="FORCE", core=True, needs=("mod:conflict",), category="political",
  purpose="disable an agent for good",
  args='{"target": "Name", "units": 3}',                                  # single source; ACTION_DOC's JSON goes here
  doc="uses {attack_cost} actions; commit weapons to disable the target ...",   # .format(**view.facts)
  variants={"secret:assassin": "..."})                                   # replaces the special cases in action_doc()
```

- `ACTION_DOC`, `MD/J.ACTION_DOC`, the module `ACTIONS` tuples, `context.LOOKUPS` / `ACTIONS` / `FILE_ACTIONS`, `MD.CATEGORIES` and
  the `scorer` category sets all become derived views of `REG`.
- Registrations move next to their handlers: `media.py` registers media actions and `conflict.py` registers conflict actions.
  `action_registry` keeps only the class, DSL and layout.
- A per-world override, such as the `post` text under submissions, becomes a `variants` key read by every renderer, not a dict
  passed to one renderer.
- Whether `Act` should also own the handler (the old review's `ActionSpec.handler`) is a separate, later step. It touches dispatch
  and golden runs, not text.

### 4.3 Classes, roles, rights as registries

```python
CLASS("scientist", title="a Scientist",
      brief=lambda v: ...,        # one text for identity line, manual "Your role" and the old prompt
      leverage="Only Scientists can run code and read the archive, ...")
ROLE("maker", secret=False, right="maker", leverage="...", told=lambda v: "...")   # merges LEVERAGE_ROLE + roles.role_text
RIGHT("press", doc="Media's press")   # the action list is appended from REG: actions whose needs include right:press
```

`_who_can_do_what`, `RIGHT_DOC`, `LEVERAGE_*`, `_one_class_line` and `class_brief` all collapse into these records.

### 4.4 One Section model for core prompt, manual and archive-like docs

```python
@dataclass
class Section:
    key: str                         # "identity", "World rules", "Actions: press"
    render: Callable[[View], str]
    layers: tuple = ("manual",)      # "core", "manual", "legacy" (old system prompt), "observer"
    needs: tuple = ()                # the SAME DSL as actions: "mod:conflict", "right:archive", "cls:scientist", "role:maker"
    after: str | None = None; order: int = 0
    cut: str = "never"               # core budget policy: "never" | "clip" (overview) | "drop" (strategy, temperament...)
    priority: int = 0                # lower is cut first

SECTIONS: list[Section] = []
def section(key, **kw): ...          # decorator; replaces MANUAL_SECTIONS, composition._MANUAL/_CORE, KNOWN_MODULES

def render(layer, v: View, budget=None) -> list[tuple[str, str]]:
    secs = [(s.key, s.render(v)) for s in ordered(SECTIONS) if layer in s.layers and needs_ok(v, s.needs)]
    secs = composition.apply(v.inst, v.a, secs, layer)             # spec/profile edits: unchanged
    return fit(secs, budget) if budget else secs                   # cut by priority, record what was cut
```

Action sections are generated from `REG`:

- one `Section` per niche kind, plus "Actions: all", plus the core `ACTIONS` block;
- the same `layout()` result feeds all three, so the core list, the manual kinds and the index cannot diverge.

`archive.NEEDS` and the `lawdocs` gates use the same `needs_ok`. Codex articles and law-library entries are already
`(title, text)` records, and their manual sections become `Section`s generated per held doc.

**Budget.** `fit()` makes the budget hard. It cuts sections in priority order (overview first, then strategy and temperament) and
fails loudly in tests if the never-cut set alone exceeds the budget. The `society` budget of 3,500 tokens can then be a deliberate
choice, not a workaround.

### 4.5 Drift test: perturb the facts

```python
def test_prose_follows_the_spec():
    sp = S.apply_overrides(S.load("society"), ["veto_window=7", "conflict.attack_cost=3", "credit.offer_lapse=5",
                                               "context.search_hits=13", "media2.max_subscriptions=4", "observer.forge_cost.copper=6"])
    text = all_rendered_text(sp)          # every layer, every agent, the observer
    for stale in ("2-round window", "uses 2 actions", "lapses after 2 rounds", "10 best matches", "at most 3", "1 copper"):
        assert stale not in text
```

This single test would have caught every row of the table in §3.4. A second test asserts that an action's doc line is identical in
the core prompt, the manual and the observer prompt.

### 4.6 The old pipeline

`agents.system_prompt` cannot simply be deleted:

- E0-E7 and the golden fingerprints run on it;
- `events.py:447` rewrites it for arrivals;
- `goals._common_shingles` reads its pieces.

It can, however, become a layout of the same sections: `render("legacy", v)` with `world_rules`, class brief, the full action docs,
API_DOC and the module sections in the old order. That deletes the `absent` set and the four `absent_actions` functions. The golden
tests do not hash system prompts: ScriptedPolicy ignores them. So byte-identity has to be pinned by a new snapshot test of
`system_prompt` for E2/E4/E6/E7 before the switch. If byte-identity of old E-series prompts is not required (for example, no E0-E7
LLM runs are planned), freeze the old path as-is instead. Doing both is not worth it.

### 4.7 Estimated shrink

| Area | Now (approx. lines) | After | Why |
|---|---|---|---|
| ACTION_DOC (3 dicts) + REG + action tuples + LOOKUPS + categories | ~280 | ~170 | one entry per action instead of 2-4 |
| `absent` set + 4 `absent_actions` + editor/scholar duplicates | ~45 | 0 | `needs` already encodes them |
| class/role/right text (LEVERAGE_*, `_one_class_line`, `class_brief`, RIGHT_DOC, `role_text` names, `_who_can_do_what`) | ~150 | ~100 | one text per class/role, no dual-class hack |
| manual plumbing (MANUAL_SECTIONS, `_module_sections`, KNOWN_MODULES, PLUGINS, `insert`, `core_section`, `grouped_actions`) | ~90 | ~40 | one registry, one decorator |
| `core_prompt` assembly | ~80 | ~35 | sections plus `fit()` |
| condition gating (archive NEEDS logic, lawdocs gates, enabled checks) | ~60 | ~30 | one `needs_ok` |

Net: about 300-350 lines out of ~1,500 text-generation lines (~20%). The prose itself (world rules, archive docs, codex, library)
stays, and should. The larger gain is that adding an action or a module touches one file for its text instead of three to five.

## 5. Migration plan (each step green and small)

1. **Pin first.**
   - Add the snapshot test of `agents.system_prompt` for E2/E4/E6/E7 agents (if the old path is kept).
   - Add `REG == actions.ACTIONS == ACTION_DOC` set equality to test_charter_consistency.
   - Add the perturbation test (§4.5) as `xfail`.
2. **Delete dead paths.** Remove `grouped_actions`, `_module_sections`/`KNOWN_MODULES`, the `manual_sections` docstring and the
   unused `core_section`. Test impact: none.
3. **Memoise `build_manual`** per `(aid, k.r, len(k.events))`. Test impact: none; Scientist turns get about 3 s faster.
4. **Facts dict.** Introduce `View.facts` and convert the hardcoded numbers in §3.4 one module at a time. Remove the
   `.replace("1 copper", ...)` patch. The perturbation test turns green. Golden runs are unaffected, because prompts are not hashed.
5. **Fix the manual contradictions.** "How your turn works" should branch on `lookups_in_dm_step` exactly as `core_prompt` does, and
   the `read_archive`/`run_python` lines should get pre-action wording. Extend `test_prompts_do_not_contradict_the_rules` to manual
   text.
6. **Fold docs into the registry.**
   - Move `args` and `doc` from ACTION_DOC into `R(...)`, module by module (media and jurisdictions first; their `ACTION_DOC` dicts
     already sit in their own modules).
   - Keep `AG.ACTION_DOC` as a derived dict for the old path and for `goals`.
   - test_charter_prompts must stay green unchanged.
7. **Derive `scorer` categories and module `ACTIONS` tuples from `REG`.** Check `activity_mix` on an old run for identical output.
8. **Class/role/right registry.** Do it in two steps, so that a test edit and a code edit never land together:
   - Merge LEVERAGE_ROLE with `role_text`, and `_one_class_line` with `class_brief`.
   - Update `test_every_prompt_states_its_leverage_per_class_and_role` and test_charter_classes to read from the registry.
9. **Section registry.** Introduce `Section` and `section()`, and port `manual.sections` piece by piece, keeping titles identical.
   test_charter_context and test_charter_prompts pin the titles ("Your archive", "Actions: all", "World rules").
10. **Core prompt as sections with `fit()`.** Assert the token counts per agent are unchanged on `society` before tightening the
    budget.
11. **Old pipeline as the `legacy` layout**, against the step-1 snapshot. Then delete the `absent` set and the `absent_actions`
    functions.
12. **Archive and law-docs gating onto `needs_ok`.** `archive.present` must return identical sets for every spec in `specs/`, so
    add a parametrised test.
13. **Generate the prompt preview.** Add `charter preview <spec> --seed N` and delete the committed `prompt_preview.md`. Point
    `goals._common_shingles` at the rendered core and manual text for context worlds. This is a deliberate scoring change, so record
    it in the commit.

## 6. What NOT to change

- **`lawdocs`.** Its tier model (prompt/common/.../legendary, presets, overrides, generated articles) is already the right shape.
  Only its gates move to the shared DSL. Do keep API_DOC's byte-identity guarantee for preset `full`.
- **`composition.apply`.** The spec/profile edits (exclude/set/append/add, profiles, assign) are a research instrument, not
  plumbing. Keep their semantics and keys exactly; the new renderer calls it unchanged.
- **The turn layers** (`state_layer`, `feed_layer` priority trimming, `recent_layer` run-collapsing, deterministic `tokens()` and
  `clip`). They are compact and well specified. Do not generalise them into the Section model: they are per-turn state, not docs.
- **Archive markdown as files.** Do not move document text into Python or YAML. `archive.NEEDS` could become front-matter in each
  `.md` (`needs: [conflict]`), which is a modest win; do it only when the gating DSL is unified.
- **`render_event`.** It is in the old review's EventType registry scope. Merging it into the Section model would not pay off.
- **No templating engine** (Jinja and similar). Conditional prose is mostly small branches, and f-strings plus `facts` keep it
  greppable.
- **No `features/` package move.** I agree with the old review here.
- **Where I part from the old review:** its `Feature.rules_text` / `prompt_section` hooks would recreate today's problem: one
  fixed-name hook per module, with no layer, condition or budget metadata, and the same text needed in core, manual and legacy
  layouts. Use `Section` registrations instead.
- **What the old review missed:** the core and manual contradictions (§3.3), the prose-number drift (§3.4), the dead extension paths,
  the manual rebuild cost, the soft budget, and the Leaker metric's dependence on old-pipeline text.
