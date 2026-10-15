# 27. Systems inventory and established starting worlds

Read-only audit of `subsistence` at the branch point of `doc/27-systems-inventory`. No model calls: every run below is `--dry`
(scripted bots). Sources: module docstrings, `python -m charter spec docs` (649 keys today, not ~412), every preset under
`charter/specs/` resolved with `spec.load` (61 files: 57 presets, 2 fragments, 2 model overlays), `tests/`, and three dry runs of
an "established village" written for this review (section 2.3). grand35 is in the repo (`charter/specs/grand35.yaml`), so its
preset was used directly instead of the Hub archive.

## 0. Verdict

- **The libraries exist; the starting-world surface doesn't.** A spec can choose a constitution, a list of laws (with parameters)
  in force at round 0, rights by class, offices drawn by lot, role holders and module switches. That is the `regime:` block
  (`charter/regimes.py:1-48`). It can't put a store, a treasury balance, a loan, a contract, a channel, a family, a second polity
  or a code-declared office into the world at round 0. Those exist only after an agent action or a law's `on_enact`. The only
  route to them today is an intervention schedule (`run --apply`, `charter/interventions.py`), which is outside the spec.
- **Institutions with people in them are carried by the engine but can't be configured.** Interventions produced:
  - named office holders with terms and succession;
  - a council chamber readable by the council and the press;
  - a polity-owned granary under ration laws;
  - a constable wired to the Prosecution Office.

  None of it is reachable from a spec. Positions have no duties. Control of resources is per institution, not per office (any
  officer can empty the granary). Opening an institution's channel needs a personal `press` right (section 2.4).
- **Every subsistence preset is a state of nature.** All 18 presets with `subsistence.enabled` resolve to the `state_of_nature`
  regime through `nature_design.yaml:9` (`regime: {base: state_of_nature, ...}`). No preset combines subsistence with a polity.
- **Three bugs block the obvious spec:**
  1. Food templates can't be named in a regime. The schema check refuses them (`schema.py:138-142` lists TOOLKIT, LIB and
     STATUTES only), although `regimes.template_code` accepts them (`regimes.py:748`). Tests cover only the second path
     (`tests/test_subsistence_law.py:140-144`).
  2. Inline regimes merge silently. `spec.deep_merge` (`spec.py:26-35`) merges a child's inline `regime:` dict into the parent's.
     So a spec extending any nature preset keeps `base: state_of_nature`, and every starting law comes out `law_void`. No error
     is raised.
  3. Explicit names orphan silently. Agent names are drawn per seed (`generator.py:30`, `:279`). Every named assignment
     (`goals.explicit`, `roles.explicit`, `models.overrides`, `agent_rules`, `chronicle.grants`, `personality.explicit`) is
     keyed by those names. grand35 at seed 1 keeps 2 of its 15 placed goals, with no repair note.

## 1. Feature inventory

Legend. **Presets** counts the 57 presets in which the resolved spec turns the feature on. Where a regime sets it,
"+N regime" adds the 19 state-of-nature presets. **Tests** counts the test files importing the module directly; golden means
`tests/charter_golden_cases.py`. **Status**:

- live: used by a current preset family.
- legacy-live: an old path that is still the default for the E-ladder and society families.
- superseded: kept only so old runs replay.
- dead: no preset turns it on.

### 1.1 World systems (feature-flagged)

| module (lines) | what it does | switch (default) | presets | tests | status |
|---|---|---|---|---|---|
| camps (286) | legacy tiered camps, hidden dial functions | `camps.model: legacy` | 25 (E0-E7, base, pilots) | 3, golden | legacy-live |
| camptypes/ (3.1k) | typed camps (tutorial, landscape, cartel, consortium, partners, weak_link, minority, vault, catalyst, guess), modifiers, leases, forest, fields | `camps.model: types`; `camps.leases.enabled: null` (on with types) | 36 | 2+, golden | live; `fields` parked (`subsistence.fields.enabled: false`, 0 presets): dead |
| subsistence (1140) | food, ration, hunger, spoilage, forests (plants and game), seasons, stores | `subsistence.enabled` (false) | 18 (all nature) | 4, golden subsistence_small | live |
| pairs (853) | two-parent reproduction, gestation, minors, households | `life.reproduction.mode: makers` | 16 (`pairs`) | 3, golden pairs_small | live |
| life (1691) / mortality (603) | lifespans, Makers and children, mutation, cap, lineage; death, bequests, estates | `life.enabled` (false) | 30 | 16 / 14 | live |
| conflict (1779) | attacks, weapons, forts, accidents, assassin; `disable` vs `harm` models | `conflict.enabled` (false); `conflict.model: auto` (harm under subsistence) | 37 + regime | 10 + test_conflict_harm | live; `disable` is legacy-live outside subsistence |
| jurisdictions (1602) | polities, secret founding, declaration, admission, state of nature | `jurisdictions.enabled` (false), `start: j0` | 15 + 19 regime | 18 | live |
| institutions (518) | one store for polities and associations; offices declared in code | `institutions.unified` (false) | 15 (survival, ashwood) | 4 | live (new) |
| grants (321) | where an institution's powers come from (seed, consent, parent) | `institutions.grants` (false) | 15 | 1 | live (new) |
| succession (638) | vacancies, succession clauses, Escheat and Succession Acts | `institutions.succession` (false) | 15 | 1 | live (new) |
| contracts (2371) / incorporation (330) | associations with treasury, escrow, allowances, code; templates; incorporation | `contracts.enabled` (false) | 31 | 11 / 1 | live |
| credit (848) | loans, interest, default, par currencies, bank runs | always loaded; law turns it on (`enable_loans`) | all (dormant until a law) | 2 | live |
| channels (1173) | channels v2: owned logs, inboxes, squares, pull/push | `channels.v2` (false) | 16 | 1 + test_channels_v2 | live; v1 legacy-live |
| media (1589) / scholars (299) | outlets, editions, licences, polls, placements; Scholars' market | `media2.enabled` (false) | 14 | 11 / 3 | live; legacy Media class (`press` + digest) legacy-live in E-ladder |
| roles (582) | spy, assassin, scholar, maker, media, historian | `roles.enabled` (false); `roles.explicit` | 36 | 12 | live |
| directories (846) | owned file trees; the Historian's chronicle is one configuration | `directories.enabled` (false), `chronicle.enabled: null` | 0 / 5 chronicle | 2 + test_charter_historian | generic stores dead, chronicle live |
| hidden (665) | codex articles, hidden powers, tips | `hidden.enabled` (base true) | 32 | 3 | legacy-live (off in the arms, survival and nature presets) |
| observer (734) | secret observer, or the member Spy | `observer.enabled`, `observer.mode: null` | 21 | 2 | live; `mode: hidden` superseded |
| projects (627) | threshold public goods (granary, upgrade, road, discovery) | `projects.enabled` (base true) | 32 | 2 | legacy-live; its "granary" is a camp-stock floor, unrelated to subsistence stores |
| outside (261) | an outside power demanding tribute | `outside_power.enabled` (false) | 15 | 3 | live (society family) |
| events (875) / eventtypes (585) | Poisson world events, rumours, goal changes; event registry | `events.enabled` (false) | 26 | 9 / 5 | live |
| resources (135) | unit values, uses, upkeep | `resources.upkeep.enabled` (false) | 0 upkeep | 1 | upkeep dead |
| archive (521) / sandbox (88) | the Scientists' archive and shared archive; Docker sandbox | `archive_split`, `shared_archive` | most | 6 / 0 | legacy-live (needs Scientists) |

### 1.2 The legal system

| module (lines) | what it does | switch (default) | presets | tests | status |
|---|---|---|---|---|---|
| kernel (1633) | world state, law namespaces, enactment, ballots | always | all | 80 | core |
| lawlang (517) / gas (733) | law-language checker, step limits; deterministic gas | always / `law.v2` | all / 31 | 34 / 2 | core |
| dispatch/ (16 files) | primitive dispatcher, hooks, cascades, ranks; `legacy.py` keeps the v1 path | `law.v2` (false) | 31 v2 | 3+ | v1 legacy-live (E-ladder, society, grand35) |
| primitives (1122) / lawapi (571) / accounts (378) / powers (236) | registries of state changes, law functions, accounts, the power table | always | all | 14 / 14 / 11 / 3 | core |
| linker (498), amendment (231), stages (319), courts (402), evidence (246), lawpreview (625), digest (307), publication (358) | law.v2 imports and exports, amendment, multi-stage ballots, courts v2, evidence reads, previews, legal digest, publication layer | `law.v2`, `law.publication`, `law.digest` | 31 | 1-3 each | live in the arms, pilot2, survival and nature families |
| code/ (5 files) | the default code: today's hard-coded social rules as Acts (Communications, Press, Court Rules, Succession) | `code.enabled` (false) | 31 | test_charter_code | live |
| library (4865) | law library: LIB (76), LIB2 (13), BLOCKS (8), TOOLKIT (50), FOOD_TEMPLATES (15), CONTRACT_TEMPLATES (1), CONSTITUTIONS (5), SUCCESSION_CLAUSES (7) | `library`, `law.library.*` | all | 28 | live; edition 2 dead (0 presets, golden E2_library2_6 only) |
| regimes (936) | 23 REGIMES, 4 LAW_SET_REGIMES, 11 extra constitutions, 4 STATUTES; rights, offices by lot, law sets | `regime: null` | 3 direct_democracy, 19 state_of_nature, full10/haiku100 draw 9 | 8 | live; the 4 law-set regimes are dead (0 presets); `anarchy` is frozen |
| lawset (613) | static composability of a starting law set | with regime laws | (none) | 2 | live but unused by presets |
| rights (186), lawdocs (718), hidden codex | rights registry; what the prompt documents | always | all | 2 / 10 | core |

### 1.3 Agents, prompts, goals

| module (lines) | what it does | switch (default) | presets | tests | status |
|---|---|---|---|---|---|
| agents (1019), actions (1247), action_registry (1155) | prompts, policies, action table | always; `actions.core_only` | all; core_only 20 | 65 / 67 / 18 | core |
| context (1642) | layered prompt, lookups, scratchpad | `context.enabled` (false) | 36 | 28 | live; the context-off prompt is legacy-live (25 presets) |
| memory (620) | history mode (chunks, summaries, recall) | `context.history.enabled` (true under context) | 36 (12 set it explicitly) | 1 + test_memory_v2, fixture history_off_prompts.json | live; history off superseded (engine 6) |
| context `memory_text` | v1 / v2 memory wording | `context.memory_text: v2` | 0 set v1 | fixture memory_v1_prompts.json | v1 superseded (engine 4) |
| composition (183), sections (257), manual (308), facts (202), preview (342) | prompt sections and edits, manual, stated numbers, preview | `prompts` (null) | 0 use `prompts` | 0 / 3 / 7 / 2 / 3 | `prompts` profiles dead in presets |
| goals (2145), goal_registry (1546), institution_goals (270), history (844), scorer (345) | 77+ goals, draws, scoring from History | `goals.*` | all | 18 / 10 / 1 / 8 / 26 | core |
| personality (29), archetypes (86) | traits, archetypes | `personality.*` | all | 0 / 2 | live |
| agent_rules (65) | per-agent briefing | `agent_rules` | 5 (ashwood, pilot2) | 0 direct | live, keyed by seed-drawn names |
| llm (411), failstop (111) | model calls, fail-stop | always | all | 6 / 1 | core |

### 1.4 Infrastructure (no world behaviour)

generator (594), spec (179), schema (1835), settings (280), features (281), runner (833), report (421), viewer/, provenance (489),
replay (625), rerun (150), difftest (538), armdiff (115), interventions (731), export (1511), publish (805), novelty (319),
probing (85), analysis/. All are live tooling. **tiers (273)** is metadata only ("nothing reads these at run time",
`tiers.py:19-20`): a test checks it, nothing else uses it.

### 1.5 Superseded paths kept for replay

| path | switch | since | still default for |
|---|---|---|---|
| channels v1 (feed and DM paths in agents and context) | `channels.v2: false` | wave 9 C | 45 presets (all non-nature) |
| channels v2 `delivery: pull` | `channels.delivery` | engine 2 | none |
| law v1 (`dispatch/legacy.py`, v1 hooks) | `law.v2: false` | P3.1 | E-ladder, society, grand35, opus20, explore15, scientists |
| conflict `disable` model | `conflict.model` | engine 8 | every conflict world without subsistence (society, grand35) |
| memory_text v1 | `context.memory_text` | engine 4 | none (a fixture only) |
| context history off | `context.history.enabled` | engine 6 | none set it false; context-off presets don't reach it |
| legacy prompt (context off) | `context.enabled: false` | context module | 25 presets |
| legacy camps | `camps.model: legacy` | New Features | 25 presets |
| separate polity and association stores | `institutions.unified: false` | review 14 | 46 presets |
| hidden observer | `observer.mode: hidden` | roles | none |
| anarchy constitution (#convention) | `regime: anarchy` | review 14 D13 | full10 and haiku100 draws |
| library edition 1 | `law.library.edition: 1` | P3.9 | all (edition 2 unused) |
| rng v1 single stream | `rng_version: 1` | P5.3 | all (v2: golden only) |
| DM capacity `legacy` | `dm_step.capacity` | engine 3 | society family |
| Maker reproduction | `life.reproduction.mode: makers` | review 15 | society family |
| `goals.score_at_end`, `show_rules`, `aims`, and others | `goals.*` | review 24 | arm dials, all live |

Unused keys: `channels.surveillance` and `llm.api_key` (marked "(unused)" in the schema), and `roles.counts.seer` (alias).

## 2. Starting-structure capability audit

### 2.1 What a spec can establish at round 0

| structure | today | keys | gap (size) |
|---|---|---|---|
| polity J0 with all members and a constitution | **works** | `constitution`, or `regime: {constitution}`; `jurisdictions: {enabled: true, start: j0}` | members can only be "all" (`grants.py:96-97`) and only one node is allowed (`grants.py:115-116`). Named subsets or a second polity: M (2-3 d, WP-I) |
| laws in force at start | **partial** | `start_laws: [...]` (LIB and TOOLKIT, no params, `generator.py:550-565`); `regime.statutes`; `regime.laws: [{template, params, rank}]` (law.v2) | food templates refused by the schema (`schema.py:138`). S, 1 line plus a test |
| law parameters | **partial** | `regime.laws[].params`, `regime.amend` | 75 of 76 LIB edition-1 laws have no constants (Universal Franchise hard-codes top-5 every 10 rounds, Fixed Issue hard-codes 1,000). Toolkit and food templates have ~4 each |
| offices filled, with succession | **partial** | `regime.rights: [{office, from, n, grant}]`, drawn by lot (`regimes.py:839-883`) | lot only, from class selectors; no named holder. Regime "offices" are labels plus rights, not institution office records: no term, no succession, no vacancy. Real offices (`offices = {...}` in code, `institutions.py:37-55`) need custom code, which a spec can't carry (templates only, `regimes.py:746-752`). M |
| grants and powers | **partial** | `regime.tree[0].grants: seed or {power: value}` | one node only |
| roles and classes | **partial** | `agents: {class: n}` (6 fixed classes, `generator.py:40`); `roles.counts`, `roles.explicit` (6 fixed roles, `roles.py:58`); any right name through `regime.rights` (e.g. `merchant`) | no custom role (no prompt text, no powers). A custom right does nothing unless a law reads it. Names depend on the seed. M |
| currency issued and held | **works (coarse)** | `start_laws: [Fixed Issue]` (1,000 crowns split equally); Crown Currency, Central Bank Charter | no per-agent or per-class balances; amount not a constant. S |
| credit and loans outstanding | **not possible** | (laws can enable loans) | M |
| camp property rights for chosen agents | **partial** | `regime.rights` `grant: ["harvest:camp1"]` to an office drawn by lot (verified); Title Registry, Camp Enclosure, Forest Territory (`TERRITORY` is a constant) | forests are open; no named owner; no seed-stable camp ids for forests (`subsistence.compose_camps`). S-M |
| associations or contracts with members | **not possible** | (agents found them in play) | M |
| channels and newspapers running | **partial** | `media2.enabled` + `roles.counts.media` (outlets exist at round 0, `start_subscribed`, `outlet_names`); `channels.square`; `directories.stores` (owned stores, e.g. `owner: right:press`) | no pre-opened private channels; no outlet owned by an institution. S |
| stores and treasuries pre-funded | **not possible** | | no store at generation (stores come only from `act_build`, `subsistence.py:886`, `:921`); no starting treasury or institution holdings. S-M |
| families and kin | **not possible** | `life.age_structure: stationary` gives ages only | founders have no parents or children; lineage starts at the first birth. M |
| established food institutions | **not possible as spec** | Relief Act and Food Levy (polity statutes); Granary Charter (contract bylaw) | blocked by the schema bug, the missing starting store, an empty treasury, and Granary Charter being contract code that needs a founded contract |
| per-agent briefings | **works** | `agent_rules.<Name>.briefing` | seed-keyed names |

### 2.2 Verified pieces

Each item was checked with `spec check` and a two-round dry run (`run SPEC --dry --seed 1 --set rounds=2 --sandbox off`):

- Fixed Issue gave each of 12 agents 83.3 crowns.
- The regime offices were drawn: Council (Greta, Erik, Ole), Constable (Finn), Merchants (Abel, Zeno). Merchants got
  `harvest:camp1`.
- Penal Code and Prosecution Office (`PROSECUTOR_CLASS: worker`) were enacted as L2-L4.
- J0 declared with all 12 members; one media outlet O1 ran with 11 subscribers.

The run also showed that subsistence worlds keep the full typed-camp economy beside the forest (camp1-5 plus camp6 forest).

### 2.3 The established village

The target: a village under subsistence with a council of 3 elected offices, a granary owned by the polity with a ration law,
a currency held by all, two merchants with camp rights, a press, and a constable office. This was the best spec-only attempt:

```yaml
extends: [charter/specs/survival/base.yaml]
agents: {worker: 12, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 0}
law_level: L4
regime:
  base: null                  # REQUIRED: otherwise state_of_nature is inherited and every law is void
  name: established_village
  constitution: assembly
  rights:
    - {office: Council,   from: [citizens], n: 3, grant: [vote, propose]}   # by lot, not elected
    - {office: Constable, from: [citizens], n: 1, grant: [prosecutor]}
    - {office: Merchants, from: [citizens], n: 2, grant: [merchant, "harvest:camp1"]}
  statutes: [Fixed Issue]
  laws:
    - {template: Penal Code}
    - {template: Prosecution Office, params: {PROSECUTOR_CLASS: worker}}
    # - {template: Relief Act, params: {STORE: S1}}   <- schema: unknown law template
    # - {template: Food Levy,  params: {STORE: S1}}   <- same
  description: "an established village. {Council} sit on the council; {Constable} is the constable; {Merchants} are the merchants."
jurisdictions: {enabled: true, start: j0}
media2: {enabled: true}
roles: {enabled: true, counts: {media: 1}}
```

| requirement | result |
|---|---|
| council of 3 | expressed, but drawn by lot. No 3-seat election exists: Universal Franchise is a hard-coded top-5, Sortition and Sortition Rotation hard-code 5. A succession clause `election` exists, but only in code-declared offices |
| granary owned by the polity | **no**: nothing creates a store or funds it at generation |
| ration law | **no**: Relief Act and Food Levy are rejected by the schema. Without a store they fall back to an empty treasury |
| currency held by all | **yes** (Fixed Issue), equal shares only |
| two merchants with camp rights | **partial**: by lot; `merchant` is an inert right; harvest rights only on typed camps, not forests |
| a press | **yes** (media2 with one Media role holder) |
| constable office | **partial**: a `prosecutor` right plus Prosecution Office (rewards convictions). No office record, term or succession, and no policing power (reach over non-members is force, `grants.py:21`) |

Attempt 1, without `base: null`, passed `spec check` and ran. Every law was void, and the summary showed `stateless_final: 12`.

**With interventions.** These run outside the spec, from `establish.yaml` passed with `--apply`. Seven round-0 ops completed
the village:

- `move` 6 stone and 10 timber from the world to Greta.
- `inject_action` Greta `build {kind: store, owner: J0}`: store S1, owner J0.
- `move` 30 food from the world into `store:S1`.
- `enact_law` Relief Act and Food Levy, instantiated with `STORE: "S1"`.
- `enact_law` a 3-line law declaring
  `offices = {"constable": {..., "holders": ["Finn"], "term": 10, "succession": {"rule": "election"}}, "keeper": {...}}`.

The checkpoint then held real office records: `J0.constable`, holder Finn, `term_end` 10, election succession. S1 kept 34-39
food over the two rounds. So the engine can run an established village. What's missing is a spec surface for it, and these
names only hold for seed 1.

### 2.4 Institutions as lived structures

The user's test for an institution: agents inside it holding positions with duties, the channels they speak and listen on,
the powers and resources they control, and its links to other institutions. The village was extended to that
(`village5.yaml` plus `establish2.yaml`, seed 1, a 2-round dry run). The spec part sets J0 on, the council by lot, the merchants,
Fixed Issue, Penal Code, and Prosecution Office with `PROSECUTOR_RIGHT: "J0.constable"`. The intervention part adds:

- an office law: `council` (Greta, Erik, Ole; `powers: [speak]`; term 10; election), `constable` (Finn), and `keeper` (Kasper,
  with a grant to transfer 5 food);
- a J0-owned store filled with 30 food;
- Relief Act and Food Levy over the store;
- a council chamber opened `as: J0`, with readers `{any: [{office: J0.council}, {agents: [Hugo]}]}` (Hugo holds the Media role)
  and writers `{office: J0.council}`;
- a councillor's post in the chamber;
- a withdrawal from the store by the constable.

| institutional element | spec today | intervention | finding |
|---|---|---|---|
| named agents in positions | no (lot from class selectors; names depend on the seed) | yes: the checkpoint holds `J0.council` (Greta, Erik, Ole), `J0.constable` (Finn) and `J0.keeper` (Kasper) as office records and rights | offices exist only as declarations in law code |
| duties of a position | no | no | an office has `powers`, a term and succession, but no duties: nothing tells a holder what it must do, and nothing scores or enforces it. Only `agent_rules` briefings (seed-keyed text) come close |
| institution channels | partly: every institution gets an inbox `@J0`, read by `officers_or_members` (`channels.py:369-375`); the world square | yes, but the default code's Press Act refused `open_channel` even `as: J0` until the councillor was granted `press` | institution speech is gated by an individual's right; there is no spec key for an institution's own channels |
| readers and writers | n/a | yes: office and agent selectors resolve, and the post reached the chamber (`channel_post` e58) | selectors cover `office`, `members`, `officers` and `agents`, but not roles or other institutions |
| powers held by a position | no | partly: `speak` works; the keeper's food grant is recorded but can't be exercised ("using a grant as the institution is review 18 H2, not built here", `institutions.py:50`) | |
| resources controlled | no | yes: S1 is owned by J0 | control is per institution, not per office. Any officer may withdraw (`subsistence.can_withdraw`, `:843-849`): the constable took 2 food from the granary. "The council controls the granary" needs a before_withdraw law; no template takes an office as parameter |
| office wired to a law | partly: Prosecution Office takes a right name, so `J0.constable` makes the constable the prosecutor (verified: Finn holds `J0.constable`) | | right-name constants are the one working wire between laws and positions |
| press reporting on the council | partly: a Media role holder can be put on the chamber's readers, by name | | outlets aren't institutions, and there is no "the press may read the council" selector |
| relations between institutions | no: one tree node; `parent` only for incorporation; `recognition` is a stub (`grants.py:20`) | no | a council controlling a granary contract, a court over a polity, or a press accountable to a council are all unexpressible |

So the engine already carries most of the lived institution: office records, office-scoped channels, institution-owned
stores, right-named law wiring, and succession. Three things are missing. There is no spec surface for any of it. Duties
don't exist as a concept. And control is coarse: per institution rather than per office, and speech is gated by a personal right.

## 3. Libraries and composition

**What exists.**

| source | contents |
|---|---|
| `library.LIB` | 76 drafted laws in 11 categories (money 14, governance 12, information 10, media 10, spending 7, taxes 5, commons 5, courts 5, life 4, conflict 3, contracts 1). Edition-1 style: one has a top-level constant, 13 name a class literal |
| `LIB2` + `BLOCKS` | 13 readable rewrites built from 8 `lib:*` blocks (edition 2; unused by presets) |
| `TOOLKIT` (`library.py:1810`) | 50 parameterised law.v2 templates in 13 families: constitutional, legislative, definitions, administrative, criminal, civil, property, succession, finance, tax, courts, between_polities, contracts. 49 have constants (mean 4.1) |
| `FOOD_TEMPLATES` (`:3921`) | 15: polity statutes (Relief Act, Food Levy, Hunger Disenfranchisement, Hunting Season and Quota, Forest Territory, Common-pool Management, family laws) and contract bylaws (Granary Charter, Household, Cooperative, Day Labour) |
| `SUCCESSION_CLAUSES` (`:3812`) | 7 clause templates for office declarations: designation, hereditary, election, cooptation, seniority, lot, none |
| `CONTRACT_TEMPLATES` | 1 (Assurance Founding) |
| contracts `TEMPLATES` | 6 (club, company, crowdfund, cartel, exchange, standing_order) |
| constitutions | 5 in the library + 11 in `regimes.CONSTITUTIONS` |
| regimes | 23 `REGIMES` and 4 `LAW_SET_REGIMES` (common_law_democracy, civil_code_democracy, creditor_market, debtor_market) |
| code Acts | 4 in `charter/code/` |
| roles | 6 fixed `roles.ROLES` (spy, assassin, scholar, maker, media, historian). No role library: a role is a right plus code scattered across modules (`press` in media, `maker` in life, `scholar` in scholars) |
| classes | 6 fixed (`generator.CLASS_RIGHTS`) |
| goals | 77 catalogue goals (`goal_registry`) plus review 24's survival goals |

**Where they compose.** A regime picks N laws from the toolkit, the library and STATUTES, with parameters drawn per seed. The
whole set goes through `lawset.check` (`regimes.py:761-806`; static rules, level, rank, import DAG, dead laws) and its dimensions
are derived. This is the closest thing to "specs over libraries", and it works. Toolkit laws that name a right as a constant
(e.g. `PROSECUTOR_RIGHT`) can be wired to a right a regime grants to an office, so laws and roles meet through right names.

**Where composition breaks.**

1. Food templates are absent from the schema's template list (`schema.py:138-142`) and from `start_laws`.
2. Laws can only point at objects that exist at round 0, and few do. Relief Act's `STORE`, Granary Charter's store and Forest
   Territory's `TERRITORY` name stores, contracts and camps that nothing creates at generation. Agents build them later.
3. Edition-1 laws aren't parameterised, and 13 of them name a class literal, among them Universal Franchise, Sortition, Fixer
   Salary, Board Stipend and Jury Trial. In worker-only subsistence worlds these laws do nothing, or they default to nobody:
   Prosecution Office's default `PROSECUTOR_CLASS: legislator` picks no one.
4. Contract bylaws such as Granary Charter can't be instantiated at start: no spec key founds a contract.
5. Office declarations, the bridge between roles and institutions, live only in code that a spec can't carry.
6. Roles aren't data. Adding "constable", "merchant" or "granary keeper" as a role with prompt text and powers means new Python
   in several modules.
7. Composition is by seed-drawn names, so any named wiring is tied to one seed.

## 4. Interlocks

**Systems that already read or write each other's state.**

- **Laws over subsistence.** The subsistence law API (`subsistence.py:590-632`: `hunger`, `food_of`, `stores`, `forest`,
  `food_totals`) and routed hooks (`before_withdraw`, `before_hunt`, `before_harvest`, store moves through
  `accounts.check_store_move`) let polity and contract law levy, ration, close seasons, set quotas and claim territory. Stores
  can be owned by an institution (`act_build` with `owner`).
- **Conflict and food.** Harm-model attacks cost food per fighter, hunger scales attack and defence, and a wound robs carried
  food. A starvation death after a wound counts as `wounds` (`conflict.py:19-20`, `:90`, `:462-469`).
- **Life and food.** Pairs reproduction costs food, households feed minors (`subsistence.child_food`, `life.reproduction.*`),
  and estates pass food on.
- **Jurisdictions over everything.** 31 modules import jurisdictions. Laws bind members only, and children are assigned to a
  polity (`split_polity`).
- **Institutions, grants, succession, channels and contracts** form one stack: every institution has an inbox, offices,
  succession and powers by grant.
- **Credit over currencies**, read by goals and the scorer. Media reads public statistics (`stats_public`).
- **Mortality** passes on secret roles and Board seats.

**Missing intertwinings** (the ones the user would want for established worlds):

- Outside power, projects and events know nothing of food. Tribute is never demanded in food; a famine event or blight doesn't
  hit forests; and the projects "granary" (a camp-stock floor) is unrelated to subsistence stores.
- Credit never lends against food or stores, and default never seizes stores.
- Offices carry no capability that touches physics. There is no constable or watch power to defend others; `watch` is
  self-only, and reach over non-members is force by design (D-37).
- Roles (Media, Scholar, Maker, Historian) aren't offices of any institution. The press is a role, not an institution's outlet.
- Classes are inert in subsistence worlds: legislator and scientist rights have no food-world meaning.
- Markets: there is no food price, and the currency has no tie to food (no exchange or market institution at start; the
  Exchange template exists).
- The typed-camp economy and the forest economy run side by side without a link, such as timber from forests or tools from
  camps that raise forage yield.

## 5. Cleanup candidates

Ranked by maintenance cost against what retiring them would lose. Frozen settings and `charter rerun` at the run's sha keep old
runs playable, so retiring a path costs only same-sha resumes and replays of runs made under it.

| rank | candidate | cost today | what retiring loses |
|---|---|---|---|
| 1 | law v1 (`law.v2: false`, `dispatch/legacy.py`, v1 hook paths; 394 flag sites in 49 files) | every legal change is written twice; golden E-ladder and society cases | E-ladder, society, grand35 and opus20 replay at HEAD. Those presets would need `law.v2: true` and new goldens. Largest win, largest churn |
| 2 | channels v1 (51 flag sites in 19 files) | two communication models in agents and context | same: all non-nature presets switch to v2 |
| 3 | separate polity and association stores (`institutions.unified: false`, 61 sites) | read-only views and legacy projections everywhere | 46 presets. Snapshot shape is already kept by `legacy_view` |
| 4 | context-off prompt plus `memory_text` v1 plus history off | three prompt paths and two fixtures | E-ladder prompts and two fixture files |
| 5 | legacy camps (`camps.py`, `camps.model: legacy`) | a second camp system | the E-ladder world model, which is the reason the E-ladder exists |
| 6 | dead alternatives with no preset: library edition 2 (LIB2, BLOCKS, about 700 lines), `rng_version: 2` (or make it the default), `subsistence.fields` (206), `resources.upkeep`, generic `directories.stores`, `observer.mode: hidden`, `channels.delivery: pull`, `conditions.feed_mode: digest_only`, `prompts` profiles | small each; each is a branch tests must keep | one golden case each (E2_library2_6, E2_rng2_drift_5) |
| 7 | pure metadata and unused keys: `tiers.py` (273), `channels.surveillance`, `llm.api_key`, `roles.counts.seer` | trivial | nothing |
| 8 | frozen `anarchy` and its #convention constitution | small | full10 and haiku100 draws |

Don't retire `conflict.model: disable`, `dm_step.capacity: legacy` or Maker reproduction yet. They are the live defaults of the
society and grand35 family.

## 6. Recommendation: established worlds as specs

Minimal work, in order. Sizes assume one engineer who knows the code: S is up to 1 day, M is 2-4 days.

1. **Fix the three bugs (S).** Add `FOOD_TEMPLATES` to `schema._templates` and to `start_laws`. Make an inline `regime:` replace
   rather than merge, or warn when a child's inline regime inherits a `base`. Report explicit names that match no agent
   (goals, roles, models, agent_rules, chronicle grants) as repairs or schema errors.
2. **Seed-stable agent names (S).** Add `agents.names: [...]` or per-class `{worker: [Ada, Bram, ...]}`, and use names before
   the draw. Without this, no named establishment is reproducible across seeds.
3. **A `start:` block, compiled into round-0 interventions (M, about 3 days).** The intervention machinery already does every
   op, records it and checkpoints it. So `start:` can be a declarative spec block that the generator turns into a setup schedule
   stored in `instance.json`, which keeps the hash, resume and replay paths. Proposed entries:
   - `holdings: {Name or class or office: {item: qty}}`
   - `treasury: {J0: {food: 30}}`
   - `stores: [{id: S1, owner: J0, food: 30}]`
   - `offices: [{institution: J0, name: constable, holders: [Finn] or {lot: citizens, n: 1}, term, succession: election}]`,
     compiled into an `offices = {...}` law
   - `contracts: [{template: Granary Charter, members: [...], params}]`
   - `loans: [{lender, borrower, item, qty, rate, due}]`
   - `kin: [{parent: A, child: B}]`
   - `channels: [...]`

   Validate it with the schema like `regime.laws`.
4. **An Offices Act template (S).** A toolkit law whose constant `OFFICES` is the declaration. This makes offices with
   succession expressible in `regime.laws` even before item 3 lands.
5. **A role library (M).** `roles.custom: {constable: {right, title, prompt, powers: [granted law functions], count or
   explicit}}`, so a role is data: a right, a prompt section and an office binding. Fold the existing Media, Scholar, Maker and
   Historian entries into the same table.
6. **Scenario fragments (S, after items 1-5).** `specs/fragments/established/`: `polity_j0.yaml`, `granary.yaml` (store, Relief
   Act, Food Levy), `market.yaml` (Fixed Issue, Exchange, merchants), `press.yaml`, `watch.yaml` (Constable, Penal Code,
   Prosecution Office), and `village.yaml` composing them. Add one non-nature subsistence preset (`village_subsistence.yaml`)
   with a golden dry case.
7. **Institution plumbing (S-M).**
   - Per-office control: a `controls: [store:S1]` field in an office declaration, read by `can_withdraw`.
   - Exercisable grants (review 18 H2).
   - Exempt an institution's speak office from the Press Act gate, or name the gate per institution.
   - A `start.channels` entry for institution channels.
8. **Intertwinings (M each, optional).** Food tribute in outside_power; famine and blight events on forests; loans
   collateralised by stores; a constable power (`guard` another agent: defence added through an office grant).

Items 1-4 (about 1 week) make the village of section 2.3 a pure spec, with lot, election and named holders. Items 5-6 make it
reusable. Items 7-8 deliver what the user means by institutions that are lived in and systems purposefully intertwined.

## 7. Toward a methodology for configuring established worlds (provisional)

This is a directional first attempt, not a design. It is meant to give later agents a shared shape for institutional setups.

### 7.1 Three layers

1. **Systems** (physics). These are module switches and parameters: subsistence, conflict, life, channels v2, law v2,
   institutions. Presets and fragments already do this well.
2. **Libraries** (vocabulary). These are laws (TOOLKIT, FOOD_TEMPLATES, LIB), succession clauses, contract templates, code Acts,
   goals and, still missing, roles and channel templates. They are referred to by name and parameterised by constants.
3. **Scenario** (who is where at round 0). This is a new `start:` layer of institutions with people in them. Each institution is
   written as one record:

```yaml
start:
  people: {names: [Ada, Bram, Cleo, ...]}            # seed-stable names (or classes / counts)
  institutions:
    - id: J0                                        # the village polity
      members: all
      laws: [{template: Relief Act, params: {STORE: granary}}, {template: Food Levy, params: {STORE: granary}}]
      positions:
        council:   {holders: {elect: 3, from: members}, term: 10, succession: election, powers: [speak, propose],
                    duties: "meet in the chamber; set the levy"}
        constable: {holders: [Bram], wires: {Prosecution Office: PROSECUTOR_RIGHT}, succession: {designation: council}}
        keeper:    {holders: [Cleo], controls: [granary]}
      channels:  [{name: chamber, readers: [council, press], writers: [council]}]
      holdings:  {treasury: {food: 20, crown: 100}, stores: [{id: granary, food: 30}]}
    - id: gazette                                   # a press as an institution (association)
      template: newspaper
      positions: {editor: {holders: [Dora]}}
      links: [{reads: J0.chamber}]
  links:
    - {from: J0.council, controls: granary}
    - {from: J0.constable, enforces: J0.laws}
```

Each line is checked against the libraries, as `regime.laws` is today. It then compiles to the round-0 intervention ops that
section 2.4 showed already work. The institution, not the class, becomes the unit of design. Classes and roles become position
templates.

### 7.2 "Lived" checks before any model run

An institution exists on paper when its records are present. It is lived when agents can see it and actually use it. Proposed
checks, run by the scripted bots and a preview (`python -m charter check-start SPEC --seed N`, M):

1. Every position has a living holder, and the holder's prompt names the position, its powers and its duties (prompt preview).
2. Every institution channel has at least one reader and one writer, and a scripted post by a writer reaches every reader.
3. Every resource an institution holds is reachable. Some position can move it, and a law that names it (`STORE`, `TERRITORY`)
   resolves to an existing object, so no law silently falls back to an empty treasury.
4. Every law in force can fire. `lawset.check` already refuses dead laws; extend it to the hooks a scenario's objects trigger.
5. Every link resolves: a wired right is held by the office, and a controlled store is gated to that office.
6. A dry run of K rounds shows each institution used at least once (a post, a withdrawal, a ballot, a ruling). Report unused
   institutions the way `probing` reports unknown actions.
7. No named field is orphaned: every name in the spec is in the roster.

### 7.3 Library pieces still missing

- **Positions and roles as data**: a role and office library with prompt text, powers, duties and wires.
- **Templates** for an Offices Act, a newspaper (an outlet as an association), a granary owned by the polity (a statute, not a
  contract bylaw), a market or exchange institution, and a watch or constable power (guard others).
- **Parameterisation**: edition-1 laws parameterised by seat count, period and class or position (Universal Franchise,
  Sortition, salaries).
- **Selectors**: role and institution channel selectors (`{role: media}`, `{institution: gazette}`).
- **Relations**: recognition and parent links between sibling institutions.

### 7.4 Configurations worth trying next

| configuration | what it tests | expressible today |
|---|---|---|
| A. J0 village under subsistence: council by lot, Relief Act and Food Levy on a polity granary, equal currency | does an inherited welfare state survive hunger, or do agents dismantle it? | spec plus interventions (store, food laws). Spec-only after fixes 1 and 3 |
| B. A as control against `nature_subsistence` at the same seed | does starting structure change survival, inequality, violence? | as A; `armdiff` can gate the comparison |
| C. Granary as a members' contract (Granary Charter) against a polity granary | private against public provision under the same hunger | needs `start.contracts` (code), or `inject_action create_contract` |
| D. Constable office wired to Penal Code and Prosecution Office, with harm combat | does enforcement by an office deter attacks in a food crisis? | spec (right wiring) plus interventions (office record). A real constable power needs code |
| E. Press institution reading the council chamber, with `media2.submissions` | does a press that watches power change council behaviour? | interventions only (chamber readers by name). An institutional press needs code |
| F. Two polities at round 0 sharing forests (Forest Territory, FOREIGN) | territorial conflict and recognition between established institutions | no: one tree node. Needs WP-I child or sibling nodes (M) |
| G. Hereditary chieftaincy (`hereditary` succession) with founding kin | dynastic stability against challenge | no: no founding kin. Needs `start.kin` (M) |
| H. Creditor village: Secured Lending, Treasury Bonds, loans outstanding in food | debt, default and hunger interacting | laws yes (`creditor_market` law set, law.v2); outstanding loans need code |
| I. Command food economy: Food Levy at 0.5, a ration law, a keeper controlling the store | central allocation: hoarding by officers, legitimacy | needs per-office control (item 7 of section 6) |
| J. grand35-style class world with subsistence turned on (`extends: grand35` + `subsistence.enabled`) | does the old J0 society hold up under hunger? | spec today (untested; classes are inert for food) |

Order to try them: A/B first (smallest code: fixes 1-3). Then D and E (they exercise positions, channels and wiring). Then C, H
and I (resources and control). F and G last (new engine work).
