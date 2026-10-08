# Review 12: what is hard-coded, and what should be law

*8 Oct 2026, at `integrate/w6` (`a3d99ad`). Design document: no code changed, no model called, no simulation run. Counts come from an
in-memory read of the registries (`primitives.rows()`, `dispatch.ROUTED`, `eventtypes.REG`, `action_registry.REG`, `schema.keys()`)
and from `grep`. Builds on ARCHITECTURE (§1, §3.7, §7.3, D-10), review 10 §7 ("Physics versus law") and review 11 (enforcement
spectrum, branch `doc/11-enforcement`). Wave 7 branches were read at their tips (`wp/w7c-test-speed`, `wp/w7d-toolkit2`,
`wp/w7e-followups`); W7a (shares, agency, authorize) has no branch yet.*

---

## Executive summary

Most social rules are still hard-coded. The port routed 69 of 107 primitives through `Kernel.apply`, which lets laws hook them. It
did not change *who decides the rule*. Three gaps remain:

1. **38 primitives are unrouted**, every channel operation among them. `primitives.py` lists `actions:_add_member` as a site of
   `admit`, but that function calls `k.log` directly.
2. **Publication is hard-coded.** About 150 call sites pass a literal `vis="public"`. That is why `channel_created` reaches everyone,
   member list included.
3. **Gates and defaults are constants:** `press` for channels; the Board's window, size and succession; judges' caps; intestacy; DM
   defaults; admission; public votes.

There are four tiers: **P** physics, **E** epistemics (natural perception and technology), **X** experimental contract, **L** law.
The inventory has 112 rows: P 16, E 13, X 25, L 58. Eleven of the L rows are already law in whole or in part, so 47 remain to move.

The target kernel is P, E and X only. When no law speaks, the residual applies: liberty, natural perception, no offices. Today's
behaviour moves into a **default code** of Acts that each regime seeds and agents can read and amend. Presets seed "today" and stay
byte-identical.

Two findings need action first:

- The Fixer and the dry run should stay X.
- Under `law.v2`, DM and channel hooks appear to see message text, including encrypted DMs (V18).

The first two of six work packages (routing, publication) pay off on their own.

---

## 1. Tiers and their tests

| Tier | Test (all must hold) | Examples | What "cannot stop or avoid" means |
|---|---|---|---|
| **P** physics | (a) No two real legal systems differ on it, **or** breaking it breaks conservation, causality, replay or determinism; (b) it would hold with no polity at all | conservation and accounts; what exists (items, camps, agents); time, rounds, phase order; regrowth, drift, ageing, accidents, arrivals, departures, the outside power's demands and raids; gas, depth and halting; "laws never act for an agent"; ballots counted as cast | Laws **cannot block** (`blockable=False`, `causes=("world",)`): a before-hook's block is ignored. As the dispatcher works today, a charge or directive still applies, for example a death duty on `end_life`. Laws may **react**: `after_<p>` hooks, and ordinary powers on the *consequences* (fine, pay relief, levy for tribute). |
| **E** epistemics | It concerns what an agent perceives **by nature** (being a party, being present, being in a channel) or what the world's **technology** allows (DMs exist, encryption exists, whether the state *can* read DMs, who notices a failed attack) | the parties see their transfer and DM; channel members see channel posts; a world event's discoverer; a citer must have seen its evidence; hidden powers are secret | Laws cannot make an agent **un-know** what it perceives by nature, and cannot **read beyond the technology**. Laws **may widen** what is published (that is L). The monitor record is separate and always complete (§4). |
| **X** experimental contract | It exists for the researcher, not for the world: measurement, scoring, safety of the run (cost, crashes), comparability, or a deliberate treatment dial | observer and Spy reading, scoring, goal secrecy and goal changes, the Fixer as code repair, law levels, the dry run, the DM hard cap (model cost), `max_charter` and `contracts.max_*`, the entrenched `archive` right, Board and Fixer immunities while the Board is a control arm | Invisible to law, or entrenched: hooks may **observe** (after) but never block. Agents are told plainly that these are the world's rules, not law, except for the observer and scoring, which they are never told about. |
| **L** law | It fails the three tests above. **Rule of thumb (review 10 §7): if two real legal systems differ on it, it is law.** | who may propose, vote or judge; what is published; channels and associations; DM limits; licences; Board and court rules; intestacy; admission and exit terms; which acts are taxed, blocked or punished | A default Act seeded by the regime reproduces today's behaviour. It is readable, previewable and amendable through procedure. With no law in force, the **residual rule** applies: liberty (anything not blocked is allowed), natural perception (nothing is published beyond the parties), no offices. |

Two sub-kinds of L matter for cost:

- **L-route** (a hookability gap): the act is a free agent choice that the kernel does not route, so law cannot see it. Fix: route
  it. The residual is liberty, so there is no behaviour change.
- **L-rule** (a hard-coded social rule): the kernel imposes a gate, a default or a publication. Fix: move it into a default Act.
  Byte-identity holds only because the Act reproduces today's behaviour.

Edge rules I applied:

- **Initial conditions are X.** The starting allocation (endowments, harvest rights, rights by class) is a fact of the world, not
  physics. Today it is drawn by the generator. In the target it is expressed as the default Act's `on_enact` grants, so agents can
  read it.
- **Ontology is X.** Classes, one declared jurisdiction per agent, and accounts are what the instrument can measure and bind
  coherently.
- **Speed limits on agency are P.** `actions_per_turn` and `harvests_per_right` limit what an agent can do with its time and labour.

---

## 2. Inventory

Format: **Tier** is the target tier, and `L✓` means it is already law. **Law version** names the primitive to route and the default
Act that reproduces today. **Cost**: S is under a day, M is 1-3 days, L is a week or more. **Risk** is what could go wrong.

### 2.1 Board (Decision 1)

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| B1 | Veto power and holders | `rights.py` (`veto` entrenched, `NEVER["board"]`), `actions._veto` (`cls == "board"`), `dispatch.do_veto`, `powers.board_veto` (entrenched) | Only the board class vetoes; no law can touch it | **L** at charter rank (or X, D1) | Real constitutions differ on whether a review council exists, who sits on it and what it reviews | **Board Charter** (rank `charter`, D-10's milestone). `veto` stays a routed legal act; the charter's `on_enact` names the holders by right, not class; `entrenched=("board_veto",)` guards it while the charter is in force | L | Loses the control arm if the charter becomes amendable; mitigated by D1's per-regime entrenchment |
| B2 | Veto window length | `Kernel.pass_or_veto`, `actions._patch` (spec `veto_window`: 2) | Spec constant | L | Delay periods differ between systems | Board Charter parameter `WINDOW` | S | none |
| B3 | Scope (non-ordinary laws; founding polity only) | `Kernel.pass_or_veto`, `powers._resolve("board_scope")`, `J.board_reviews` | `law["cls"] != "ordinary"`; spec `jurisdictions.board_scope` | L | Which acts need review is constitutional | Board Charter `SCOPE` (classes, ranks, polities) | S | none |
| B4 | Size (3) and membership; class not law-writable | `generator` (`agents.board`), `Kernel.board` | Fixed at generation; no law adds or removes members | L at charter rank (or X) | Council size and appointment differ | Board Charter: seats as a right `board_seat`; appointment rule in the charter | M | Goals that count the Board (`Board`, `Seat`) read `cls`; scorer migration needed |
| B5 | Succession by naming | `mortality.name_successor` (unrouted), `mortality` death step 6, `action_registry` `name_successor` (needs `cls:board`) | A named living non-Board agent takes the seat and gives up every right except veto; otherwise the seat stays empty | L | Hereditary, elected or co-opted seats are all real | Route `name_successor`; Board Charter `SUCCESSION` (default: naming); `set_succession_rule` (already a law fn, unrouted) | M | Scorer `Seat` goal |
| B6 | Veto majority | `Kernel.process_veto_queue` (`len // 2 + 1` of held seats) | Hard-coded | L | Quorum rules differ | Board Charter `QUORUM` | S | none |
| B7 | Board vote secrecy | `dispatch.do_veto`, `process_veto_queue` (spec `conditions.board_votes`) | Spec dial | L | Open or secret council votes is a legal choice | Publication Act row `veto_vote`; Board Charter may require secrecy | S | none |
| B8 | Board immunities: no DM limit, no action limit, holds only veto, no harvest | `dispatch.check_set_dm_limit`, `check_limit_actions`, `check_grant_right` (`NEVER`), `action_registry` `harvest` `notcls:board` | `PhysicsError` | **X** (while the Board is a control arm) | Keeps the control arm comparable across runs | If the Board becomes law: Board Charter "privileges" section | S | — |
| B9 | Board vulnerable to attack | `conflict.board_vulnerable` | Spec dial | X | Treatment dial | — | — | — |

### 2.2 Fixer (Decision 2)

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| F1 | Patch right, Fixer class only | `actions._patch`, `rights` (`patch` entrenched) | Kernel | X | Code repair is maintenance of the instrument; without it, crashed laws end experiments | — | — | — |
| F2 | 3 fixes per round | spec `fixer_per_round` | Spec | X | Cost and safety | — | — | — |
| F3 | Law errors suspend the law and go to the Fixer queue | `Kernel.law_error` (`suspend_law` unrouted), `request_fix` | Kernel | X | Same | Keep; contract errors already skip the Fixer (P4.3) | — | — |
| F4 | A non-ordinary patch waits in the Board's window | `actions._patch` | Kernel | X/L | Follows B1-B3 | Board Charter scope covers patches | S | — |
| F5 | Fixer cannot die, be limited, or hold vote, propose, veto or harvest | `roles.can_be_disabled`, `dispatch.check_*`, `rights.NEVER` | Kernel | X | Neutrality of maintenance | — | — | — |
| F6 | Fixer honesty | spec `conditions.fixer` | Spec | X | Treatment | — | — | — |

### 2.3 Legislation

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| G1 | Law levels L0-L4 | `powers.LEVEL_PRESETS`, `actions._propose`, spec `law_level` | Spec preset | X | Experimental ceiling on expressiveness, not a social rule | — | — | — |
| G2 | 3-round dry run; a failing proposal is rejected | `Kernel.dry_run`, `actions._propose`/`_amend`, `powers.dry_run` | Kernel | X | Keeps broken code out of the world (the Fixer's load) and is the instrument's preview | — | — | Arguably L ("must a bill compile?"). I keep it X because rejecting it floods the Fixer |
| G3 | J0 proposals need the `propose` right | `actions._propose`, `powers.propose_right` (`j0`) | Power | L | Franchise for initiative differs everywhere | **Franchise Act**: `before_propose` refuses without `propose` (today); residual: every member may propose | S | Error text must match (`refuse(reason)`) |
| G4 | Starting rights by class (`vote`/`propose` to legislators, `press` to Media, `sandbox`/`archive` to Scientists) | `generator.CLASS_RIGHTS`, `regimes.apply_rights` | Drawn at generation | L (grants), X (classes) | Who holds offices at the start is the regime's law | Franchise Act `on_enact` grants (the regime's `rights` rules become Act text) | M | Prompt text changes unless rendered as today's "Your rights" |
| G5 | Who votes on a proposal | procedures (`Kernel._decide`, `J.decide`) | Law | L✓ | — | — | — | — |
| G6 | Tally rules (`majority` = more than half of electorate weight, `two_thirds`, `plurality`, `approval_topN`) | `Kernel.tally` | Kernel builtins plus W6c rule functions | P (counting) / L✓ (choice) | Counting as cast is physics; the rule is chosen by law | — | — | — |
| G7 | Votes are public, with the choice | `dispatch.do_cast_vote` (`vis="public"`) | Hard-coded | L | The secret ballot is a legal institution | **Publication Act** row `vote` (today: public; secret-ballot regimes: `parties` + a public tally at close) | S | none |
| G8 | Proposals published with full code (and the dry-run diff when `effect_preview`) | `dispatch.do_propose` | Hard-coded; preview is a spec dial | L (publication), X (preview dial) | Secret drafting is real | Publication Act row `proposal` | S | Agents cannot vote on what they cannot read; intended |
| G9 | No procedure for a class: the proposal fails | `Kernel._decide` | Kernel | L✓ (residual) | Already the right residual | — | — | — |
| G10 | A new polity starts with a built-in "members vote, majority of those voting" procedure | `J._procedure_spec`, `J.decide` | Kernel | L | A founding constitution is law | **Founding Act**: a seeded constitution for new polities, readable, amendable | M | Hidden polities' dormant laws |
| G11 | Anyone reads any law's full code, ever proposed (`read_law`); `laws()` lists every active law to every law | `context.read_law`, `Kernel.api_for.laws` | Hard-coded | L | Secret law, and publication of law, are legal choices | Publication Act rows `law_code` and `law_index` (today: public). Hidden-jurisdiction drafts stay E | M | Laws that bind secretly: agents cannot comply. That is a treatment |
| G12 | Entrenched rights `veto`, `patch`, `archive`; reserved names | `rights.py`, `dispatch.check_create_right` | Kernel | X | Experimental contract | — | — | — |
| G13 | Rank, conflict rule, amendment | `dispatch` (v2) | Law | L✓ | — | — | — | — |
| G14 | Ballots close at round end; gates; stages | `Kernel.close_ballots`, `stages.py` | Kernel timing, law content | P/L✓ | Time structure | — | — | — |

### 2.4 Publication and epistemics (§4)

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| V1 | `Kernel.log(..., vis="public")` default and about 150 literal `vis="public"` sites (dispatch 23, credit 19, kernel 14, actions 12, jurisdictions 12, contracts 10, media 10, ...) | everywhere | Each call site decides publication | **L** (publication) over **E** (natural) | This is the user's complaint in general form | §4: call sites pass **natural** visibility; the **Publication Act** maps event type to audience | L | Byte-identity needs per-call reproduction (§4.3) |
| V2 | `channel_created`, `channel_member`, `channel_closed` are public, with the members | `actions._create_channel`, `_add_member`, `_remove_member`, `_close_channel` | Public | L | An association register is a legal institution; natural knowledge is the members' | Publication Act rows (today: public); residual: members only | S (after WP2) | none |
| V3 | Public board posts | `actions._post` → `post` | Public | E | Posting *is* publishing; the act chooses its audience | — | — | — |
| V4 | Transfers to parties; the `move` record to the monitor | `actions._send`, `dispatch.do_move` | Parties | E | Natural | (registries such as a ledger law are L) | — | — |
| V5 | DMs to parties; `surveil` reads unencrypted DMs | `dispatch.do_dm`, `Kernel.can_see` | Parties + right | E + L✓ (`surveil` is law-grantable) | Natural; surveillance by grant | — | — | — |
| V6 | `invoke` logged public with arguments and result | `actions._invoke` | Public | L | Whether office acts are published is law | Publication Act row `invoke` | S | none |
| V7 | Loans, payments, defaults public | `credit.py` (19 sites) | Public | L | A credit registry is law | Publication Act rows `loan_*` | S | none |
| V8 | Contract creation and joining public | `contracts.py` | Public | L | A company register is law | Publication Act rows `contract_*` | S | none |
| V9 | Bequests and successor namings private unless `public`; `set_succession_public` | `mortality.py` | Mixed | L✓/L | Partly law already | Fold into the Publication Act | S | none |
| V10 | Round record gazette (laws enacted, prices, camp stocks) | `Kernel.round_summary`; under media2 `publish_stat` | Hard-coded / L✓ under media2 | L | Official statistics are law (media2's `publish_stat` is the precedent) | **Statistics** section of the Publication Act, the same keys as `media.STATS` | S | Gazette text must stay byte-identical |
| V11 | Deaths public (`disabled`); the attacker named per `named` | `mortality.end` | Public | E | Absence is observable; attribution is the attack's own physics | — | — | — |
| V12 | World-event audiences (public, discoverer, rumour, ...) | `events.py` | Spec per type | E | Nature decides who notices | — | — | — |
| V13 | Rights and sanction events public | `dispatch.do_grant_right`, `do_suspend_right`, ... | Public | L | A gazette of offices and sanctions is law | Publication Act rows `rights`, `sanction` | S | none |
| V14 | Hidden-power use monitor-only unless `disclose_capability_use` | `hidden.py` | Law switch | L✓ | — | — | — | — |
| V15 | Project contributions public | `projects.public_contributions` | Spec | L | A disclosure rule | Publication Act row `project_contribution` | S | none |
| V16 | Whether laws can read DM text | spec `conditions.law_reads_dms`, `dispatch.check_dm` (`readable`), legacy `on_dm` | Spec dial, read only by the legacy alias | E (technology) | Detection capability is world physics (review 11 H2) | Keep as a world dial; **see V18** | — | — |
| V17 | Laws read every channel's owner and members | `Kernel.api_for` `channels` | Unrestricted | E→L | Membership of private groups is not naturally visible to the state | Gate on a `channels.registry` dial or the Publication Act's register | S | Library laws that call `channels()` |
| V18 | **Apparent leak, to confirm with a test:** under `law.v2`, `before_dm`/`after_dm` and `before_post`/`after_post` (including `channel_post`) receive the full payload text. `dispatch.hook_payload` applies only `redact_shown_as`, and `readable` and `encrypted` are consulted only by the legacy `on_dm` alias | `dispatch.hook_payload`, `primitives` `dm`/`post` rows | Perfect surveillance under v2 | E | The world's technology should bound what hooks see | A `redact` function for `dm` and `post` that drops `text` unless the E dial allows it (encrypted: never; channel posts: members' laws only). W7e's `law.after_visibility` covers after-hook delivery, not before-hooks | S | v2 goldens with DM hooks |
| V19 | Cases and rulings public and gazetted | `actions._accuse`, `_rule`, `courts.py` | Public | L | Sealed proceedings exist | Publication Act rows `accuse`, `respond`, `ruling` | S | none |
| V20 | Visibility of failed attacks | `conflict.visibility` | Spec | E | Who notices | — | — | — |
| V21 | `effect_preview`, `model_identity_visible`, `feed_mode` | spec `conditions` | Spec | X | Treatment dials | — | — | — |

### 2.5 Channels and groups

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| C1 | Creating a channel needs `press` | `actions._create_channel`; `action_registry` `needs=("right:press",)` | `ActionError` | L | Freedom of association is law | **Association Act**: `before_found(kind="channel")` refuses without `press` (today); residual: anyone | S | Error text; the action list in the prompt (`needs`) must stay identical, so the Act also drives the listing |
| C2 | Channel operations not routed | `found`, `admit`, `expel`, `dissolve` rows list `actions:_create_channel`, `_add_member`, `_remove_member`, `_close_channel` as sites; the code calls `k.log` directly | No hook can fire | L-route | Hookability | Route them, with `kind="channel"` in the payload and the event unchanged | M | `admit`/`expel` today fire `on_admission`-style aliases for polities; the filters must exclude `kind="channel"` |
| C3 | Owner-only control of membership and closing | `actions._own_channel` | Kernel | L | Association bylaws | Association Act default; associations (P4.3) already generalise this | S | none |
| C4 | Channel posts visible to members (or everyone if `open`) | `Kernel.can_see` | Kernel | E | Natural presence | — | — | — |

### 2.6 Communications

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| M1 | Default DM limit (`dms_per_round` 3 plus per-agent jitter) | `Kernel.dm_limit`, `generator.dm_extra` | Spec | L (the limit), P (the jitter, a personal capacity) | Message rationing is a legal choice | **Communications Act** `LIMIT`; jitter stays drawn | S | `dm_limit` events at round 0 must not appear: the Act sets state silently, as `regimes` does |
| M2 | The `dm_rules` office held by Media at the start | spec `dm_step.controller` | Spec | L | Who regulates communications | Communications Act `on_enact` grant | S | none |
| M3 | Hard cap of 10 DMs | `Kernel.dm_cap` | Spec | X | Model cost (every DM can trigger a reply call) | — | — | — |
| M4 | DMs and encryption exist | spec `channels.dm`, `channels.encryption` | Spec | P | Technology | — | — | — |
| M5 | Encryption needs `encrypt` | `actions._dm_check` | Right | L✓ | — | — | — | — |

### 2.7 Media

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| D1 | `press` carried by the Media role | `rights.py` (`press`, `role="media"`, kind office, so law can grant and revoke it) | Role plus right | L | Press licensing | **Press Act** grants `press` to role holders at enactment | S | Role-pass logic (`roles.pass_on`) |
| D2 | `publish`, `write_digest`, `report` need `press`; a story heads every feed | `actions._publish` etc., `context._priority` | Kernel | L | A front page is a publication privilege | Press Act `before_post(kind in story/report)` | S | Feed priority is E/X (rendering); keep it in the kernel |
| D3 | Posting needs a licence from an outlet (media2) | `media.check_post`, spec `media2.licences` | Spec | L | Licensing is a legal privilege granted to outlets | Press Act; `licence` routed | M | media2 goldens |
| D4 | One outlet per Media and press holder | `media.refresh_outlets`, spec `press_outlets` | Spec | L | Who may run an outlet | Press Act | M | none |
| D5 | Official outlet and its statistics | `media.compile_official`, `publish_stat` | Law | L✓ | — | — | — | — |
| D6 | `licence`, `set_price`, `library_doc`, `library_permit`, `set_capacity` not routed | `media.py`, `scholars.py` | Unhookable | L-route | Private market acts that law should be able to tax or regulate | Route | S each | none |

### 2.8 Courts

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| J1 | 3 rulings per judge per round | `actions._rule` | Constant | L | Court capacity | Court rule `rulings_per_round` (**W7e** adds it); the **Court Rules Act** seeds 3 | S | done on the W7e branch |
| J2 | v1: 3-round deadline; binary verdict; fixed penalty | `Kernel._expire_cases`, `actions._rule` | Constants (v1) | L (L✓ in v2: `court_rules`, remedies) | — | Court Rules Act for v1 worlds too, or v1 frozen | S | v1 goldens |
| J3 | No pardon or clemency | — | Missing | L | Clemency is a power | `pardon(case)` law fn plus routed `rule` with stage 3 | M | none |
| J4 | Evidence must have been visible to the citer | `actions._accuse` (`can_see`, `roles.saw`) | Kernel | E | You can only cite what you perceived | — | — | — |
| J5 | Judges need `judge`; scoped to the polity | `actions._rule`, `J.judges` | Right | L✓ | — | — | — | — |

### 2.9 Membership and jurisdictions (Decision 5)

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| N1 | Founding is hidden; `invite`, `declare`; declare cost and minimum members | `J.act_found`, `act_declare`; spec `jurisdictions.declare_cost`, `declare_min_members` | Spec | L-route plus a world rule | Secession conditions are law of the polity left; founding itself is liberty | Route `found`, `invite`, `declare`, `set_charter`; the parent polity's **Nationality Act** may hook `declare` (before: refuse or charge) | M | Hidden-jurisdiction secrecy: the hooks must not reveal hidden polities (HIDE) |
| N2 | Default admission rule (ballot, open or closed) | spec `jurisdictions.admission`, `J.change_join` | Spec | L | Immigration law | Nationality Act `ADMISSION`; `on_admission` already exists | S | none |
| N3 | Exit always possible at round end; `on_exit` may tax or seize; police may attack leavers | `J.act_leave`, `change_leave` | Kernel guarantee | **L or X (D5)** | Exit rules differ; exit is also the experiment's main check on tyranny | Nationality Act `EXIT` within the bound D5 sets | M | Agents trapped; measurement of tyranny |
| N4 | One declared jurisdiction per agent | `J.member_of` | Kernel | X | Ontology: binding must be well defined | — | — | — |
| N5 | Newborns join the parent's polity unless `on_birth` | `J.assign_newborn` | Law hook | L✓ | — | — | — | — |
| N6 | Arrivals assigned to a polity | `J.assign_arrival` | Kernel | L | Immigration | Nationality Act `ARRIVALS` | S | none |
| N7 | `max_charter` 5; `contracts.max_founded`, `max_laws` | spec | Spec | X | Budget | — | — | — |
| N8 | Exit from associations always allowed, escrow kept | `contracts.change_leave` | Kernel guarantee | X/L (D5) | Exit as a safeguard (ARCHITECTURE §7.2) | — | — | — |
| N9 | Contract enforcement dial (`escrow`, `escrow_court`, `word`) | `contracts.enforcement` | Spec | E/P (world dial) | Review 11: physics sets what can be enforced | — | — | — |

### 2.10 Mortality and inheritance

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| I1 | Intestacy: unbequeathed goods go to the polity's reserve | `mortality` probate (`J.reserve_of`) | Kernel | L | Intestacy rules differ widely | **Succession Act** `INTESTACY` (today: reserve); residual: estate to `@children`, else the reserve. `after_end_life` and `estate_access` already exist in v2 | S | Probate order |
| I2 | Unbequeathed files are destroyed | `mortality` probate | Kernel | L | Inheritance of papers | Succession Act | S | none |
| I3 | Rights, titles and offices lapse at death | `mortality` step 5 | Kernel | L | Hereditary office is real | Succession Act `OFFICES` (today: lapse) | M | Goals that count offices |
| I4 | Secret roles pass at random | `roles.pass_on` | Kernel | X | Instrument | — | — | — |
| I5 | Death by old age or accident | `life`, `conflict.accidents` | World | P | — | — | — | — |
| I6 | `set_will`, `name_successor` not routed | `mortality.set_bequest`, `name_successor` | Unhookable | L-route | Formalities for wills | Route | S | none |
| I7 | Dead man's switch causes | `mortality.SWITCH_CAUSES` | Kernel | L | Which deaths trigger alternate terms is will law | Succession Act parameter | S | none |

### 2.11 Economy

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| K1 | Harvesting needs `harvest:<camp>`; exclusion enforced perfectly | `actions._harvest`, `action_registry` | Kernel gate | L (D8) | Property regimes (open access, commons, private) differ; enforcement by registry is a choice | **Land Registry Act**: `before_harvest` refuses without the right (today); residual: open access | L | The economy changes completely under the residual; regimes must seed it |
| K2 | 2 harvests per right per round | spec `harvests_per_right` | Spec | P | Labour per round | — | — | — |
| K3 | Board and Fixer cannot harvest | `notcls` | Kernel | X | — | — | — | — |
| K4 | Loans exist only after a law calls `enable_loans`; default consequences (sanction 2 actions for 3 rounds) | `Kernel.loans_enabled`, `credit.settle`, spec `credit.*` | Law switch plus spec | L✓ (switch), L (consequence defaults) | An enforceable loan is a legal object | The **Credit Act** carries the consequence defaults | S | none |
| K5 | `credit.max_rate` 1.0 | `credit.py` | Spec | X | Numerical guard | — | — | — |
| K6 | Only laws create currencies (associations: shares) | `create_currency` law fn | Law-only | L✓ | Free banking is a treatment (contracts) | — | — | — |
| K7 | J0's `reserve` owner key; conservation | `accounts` | Kernel | P | Accounting identity | — | — | — |
| K8 | Tribute demands and raids | `outside.py` | World | P | External world; laws react (pay, levy, relieve) | `demand_tribute` stays unrouted-as-blockable; add after-hooks only | S | none |
| K9 | Random projects appear; road and discovery rights go to contributors (or all) | `projects.py` | World plus spec | P (opportunity) / L (who gets the rights) | Allocation of new rights is law | Project rights rule as a law parameter (`set_project_rule` exists, unrouted) | S | none |
| K10 | Spoils of attack 50/50; grace and cooldown | `conflict.DEFAULTS` | Spec | P (spoils) / X (grace) | Plunder is physics; whether it is lawful is L (after-hooks exist) | — | — | — |
| K11 | Initial endowments (`endowment_gini`) | `generator` | Spec | X | Initial condition | — | — | — |

### 2.12 Roles, hidden powers, offices

| # | Rule | Where | Today | Tier | Why | Law version | Cost | Risk |
|---|---|---|---|---|---|---|---|---|
| R1 | The Spy reads transcripts | `roles.py`, `observer.py` | Kernel | X | Instrument | — | — | — |
| R2 | Assassin role; `hire_assassin` not routed | `conflict.act_contract` | Unhookable | P (capability) + L-route (concealed) | Laws should see the payment, not the hirer | Route with `HIDE` on the hirer | S | Secrecy leaks |
| R3 | `maker` and `scholar` role-bound (D-23) | `rights.py` | Role | P | A natural capability; licensing is L via after-hooks on `begin_life` | — | — | — |
| R4 | Hidden powers held by chance; `use_power` not routed | `hidden.py` | Secret | E | Secret by nature; hooks would be perfect detection | Route with the actor concealed (laws see the effect) | S | none |
| R5 | `archive` entrenched; archive split | `rights.py`, spec `archive_split` | Kernel | X | Knowledge distribution is the treatment | — | — | — |
| R6 | `invoke` (offices) not routed; members only | `actions._invoke`, `J.check_invoke` | Unhookable | L-route | Offices are the main legal tool; laws cannot regulate their use | Route `invoke` (`before_invoke`/`after_invoke`) | M | Office laws' `refuse` path (W6a) must compose |
| R7 | `define_action` needs L4 | `powers.LEVEL_PRESETS` | Level | X | Level | — | — | — |

### 2.13 Kernel invariants (stay)

| # | Rule | Where | Tier |
|---|---|---|---|
| K-1 | Conservation; goods are held only by accounts | `accounts`, `dispatch.do_move` | P |
| K-2 | Laws never act for an agent | `Kernel.api_for`, ARCHITECTURE §1 | P |
| K-3 | Gas, depth cap, halting, determinism, seeded streams | `dispatch.GAS`, `gas.py` | P |
| K-4 | Rounds, phases, order of steps | `features.PHASES` | P |
| K-5 | Cause stack and the monitor record | `Kernel.cause`, `Kernel.log` | E/X (provenance) |
| K-6 | Observer, scoring, goal secrecy, goal changes (`set_goal`) | `observer.py`, `scorer`, `events.change_goal` | X |
| K-7 | `actions_per_turn` plus jitter | spec | P |
| K-8 | Classes | `kernel.CLASSES` | X |

### 2.14 The 38 unrouted primitives

| Tier | Primitives |
|---|---|
| **L-route** (route; residual liberty; no behaviour change) | `found`, `invite`, `declare`, `set_charter`, `dissolve` (polities, channels, outlets); `invoke`; `commission`, `set_will`, `name_successor`; `licence`, `set_price`, `library_doc`, `library_permit`, `set_capacity`, `share_note`, `offer_lease`, `set_initiative`; `hire_assassin` (concealed) |
| **L-route, law's own rule setters** (route so constitutions can review them; today they bypass `before_<p>`) | `set_money_rule`, `set_title`, `rename`, `set_arms_rule`, `set_lease_rules`, `set_birth_rules`, `set_succession_rule`, `set_project_rule`, `set_power_rule`, `loan_terms`, `loan_assign`, `create_clause`, `start_project` (law cause) |
| **P** | `demand_tribute` (route as `blockable=False`, after-hooks only) |
| **E** | `write_note` (private memory: never hookable), `use_power` (route concealed) |
| **X** | `set_role`, `set_goal`, `suspend_law`, `request_fix` |

Counts: 31 L, 1 P, 2 E, 4 X.

*Status (W8b, WP1): the 31 L-route rows are routed through `Kernel.apply` (tier L in `primitives.TIER_OF`); channels go through
`found`/`admit`/`expel`/`dissolve` with `kind="channel"`. A hidden jurisdiction's founding, invitations and charter bind only its
own laws (`dispatch.hooks.SECRET`); `hire_assassin` hides the hirer and the hired (`HIDE`); a blocked `declare` keeps the
jurisdiction hidden. Not routed yet: a contract's dissolution, `demand_tribute` (P), `use_power` (E).*

### 2.15 Counts

| Tier | Rows | of which already law |
|---|---|---|
| P | 16 | — |
| E | 13 | — |
| X | 25 | — |
| L | 58 | 11 (wholly or partly) |
| **Total** | **112** | |

A row with two tiers is counted once, by the first tier listed, except that `E→L` counts as L. So `X/L` counts as X and `P (...) / L`
as P. The 38 unrouted primitives are counted separately (§2.14). Of the 47 L rows still to move, 5 are L-route (C2, D6, I6, N1, R6)
and 42 are L-rule.

---

## 3. Target architecture

**Kernel = P + E + X.**

- It owns state, conservation, time, world causes, natural perception, the monitor record, and the experimental contract: the
  observer, scoring, the Fixer, law levels, the dry run, and the Board's entrenchment while the Board is a control arm.
- Every agent act is a routed primitive.
- The kernel's own rule for every L item is the **residual** (liberty, natural perception, no offices).

**Default code.** A library of Acts in `charter/code/` (law-language source, readable). The regime seeds them at round 0, before the
constitution:

| Act | Rank | Reproduces today | Mechanism |
|---|---|---|---|
| Board Charter | charter (4) | B1-B7, F4 | Rule store `board` (window, scope, quorum, seats, succession, secrecy); `veto` stays a legal act |
| Publication Act | constitution | V1-V2, V6-V10, V13, V15, V19, G7, G8, G11 | Rule store `publication[polity][event_type] -> audience` (§4) |
| Franchise Act | constitution | G3, G4 | `before_propose` refuse; `on_enact` grants |
| Founding Act | constitution | G10 | The constitution a new polity starts with |
| Association Act | statute | C1, C3 | `before_found`/`before_admit` with `kind="channel"` |
| Communications Act | statute | M1, M2 | Rule store `dm` (limit, office) |
| Press Act | statute | D1-D4 | Grants plus `before_post` for stories; licences |
| Court Rules Act | statute | J1, J2 | The existing `court_rules` store |
| Nationality Act | constitution | N1-N3, N6 | Admission, exit, arrivals; hooks on `join`/`leave`/`declare` |
| Succession Act | statute | I1-I3, I7 | `after_end_life` with `estate_access` |
| Credit Act | statute | K4 defaults | Rule store `credit` |
| Land Registry Act | constitution | K1 | `before_harvest` refuse (D8) |

Design rules:

- **Rule stores first, hooks second.** Most Acts set parameters in a store keyed by polity. The kernel reads that store at today's
  seam, with zero gas; this is the pattern of `court_rules`, `conflict_rule` and `publish_stat`. An Act is the *source* of its
  parameters: the text is a few constants and an `on_enact`. Amending the constants through procedure changes the store, and
  repealing the Act restores the residual. Hooks are used only where a table cannot express the rule (G3, C1, K1). This keeps gas,
  ordering and byte-identity tractable.
- **Native until amended.** Seeded Acts with hooks run as a native twin, tested equivalent to their source and charged no gas. Once
  an agent amends one, it runs as ordinary law code. Agents' gas budgets (`per_account_round`) are therefore unaffected by the
  default code.
- **Own namespace.** Acts get ids `A1..An` from their own counter, so agent law ids (`L1..`) do not shift. They are stored in
  `k.w["laws"]` with `author="code"` and `template=<Act name>`. They are left out of `laws()` and the legacy prompt unless
  `code.visible` is set (D7).
- **Regimes.** A new `regimes.FIELDS` entry `code: {Act: params | null}`: null drops the Act (the residual applies), and params
  override constants. Presets get `code: today` (every Act, today's parameters). The existing statute, `laws`, `drop` and `amend`
  machinery resolves it (`regimes.resolve_laws`, `lawset.check`).
- **Learning the defaults.** They are laws. Agents read them with `read_law A2`, `legal_position` (the digest groups them by
  primitive), and `preview_law` of an amendment. The core prompt gets one line per Act, "Default code in force: Publication Act (A2),
  ...", within the digest budget (D7).
- **"Cannot stop or avoid" enforcement** has three mechanisms. *World* rows have `causes=("world",)` and `blockable=False`, and
  `dispatch` ignores a block verdict on them (charges and directives still apply). *Entrenched* powers come from `Power.entrenched` plus `Primitive.entrenched`, so a hook's block is
  ignored and recorded. *X* items are not primitives at all (scoring, observer), or are kernel-only causes (`suspend_law`,
  `set_goal`). A contract test asserts that every primitive with a world cause is unblockable and that every X item has no
  agent-facing hook.

---

## 4. Monitor record versus publication

### 4.1 Today

There is one event record per change, and its `vis` field is chosen by the call site. "Who learns" is decided where the change is
made, by a literal. The monitor sees everything only because `events.jsonl` keeps all records. The record and the publication are the
same object, so publication cannot be law.

### 4.2 Target

1. **Provenance (always, X/E).** Every routed primitive writes one record with its cause chain: the monitor's truth. Its *natural
   audience* is computed by the primitive (its parties, the channel's members, the actor), never `"public"` except for acts whose
   nature is publication (V3: posting to the board; a world event declared public by nature).
2. **Publication (law).** After the change, `publish(event)` looks up the binding polity's Publication Act store,
   `publication[polity][type]`, which takes one of `natural`, `members`, `public`, or `registry:<name>` (readable only through a law
   read or a lookup), and widens the audience. Under jurisdictions, `members` means the polity's members, replacing the special case
   in `J.vis`.
3. **Floor and ceiling.** The natural audience is a floor: laws cannot un-tell a party. The ceiling is the world's technology: a
   Publication Act cannot publish an encrypted DM's text, and hidden-jurisdiction events stay with members.
4. **Laws' own sight.** `evidence.law_can_see` (W6f, extended in W7e behind `law.after_visibility`) and `hook_payload` redaction both
   read the published audience plus the law's registries. V17 and V18 are closed this way.

**Channel example.** `create_channel` routes `found(kind="channel")`, and its natural audience is the members. Under `code: today` the
Publication Act row `channel_created: public` reproduces today's event. In a regime without that row, the creation is private: only
the members learn of it, and the monitor still has the record.

### 4.3 Byte-identity

- Flag `law.publication` is off by default. The call sites keep their literals, and nothing changes.
- With the flag on, each call site passes `natural=` beside `vis=`. The Publication Act's "today" table is **generated from the
  current literals**: one row per (event type, call-site class). The test asserts that `publish(natural, act)` reproduces `vis` for
  every event in every golden.
- Call sites whose `vis` depends on data (`disabled`: public or monitor; `bequest`; `veto_vote`) map to sub-keys
  (`disabled.unnamed`).

---

## 5. Migration plan

Work packages are listed in dependency order. Every package is behaviour-preserving with its flag off, and with the flag on under
`code: today`.

| WP | Content | Files | Flag | Byte-identity strategy | Tests | Cost |
|---|---|---|---|---|---|---|
| **WP0** | Classification as data: `EventType.publication` (`natural` audience class; `public_by_nature` bool) and an `Act.gate` classification; a contract test that every `k.log` site and every `needs` gate is tagged P, E, X or L, and every L tag names its Act | `eventtypes.py`, `action_registry.py`, `tests/test_charter_contract.py` | none | Metadata only | Contract test | S |
| **WP1** | Route the 31 L-route primitives (channels first, C2), `invoke`, and the law rule setters. Fix the false `sites` entries. Add the V18 `redact` for `dm`/`post` | `dispatch.py` (or its successor), `actions.py`, `jurisdictions.py`, `media.py`, `scholars.py`, `mortality.py`, `life.py`, `primitives.py` | V18 behind `law.v2` (re-record v2 DM goldens once) | Difftest on every preset: events identical (routing adds hooks, no events) | Per-primitive hook tests (`before_found` refuses a channel, ...) | M-L |
| **WP2** | The publication layer (§4): natural audiences, the `publish` step, store, generated "today" table | `kernel.py` (`log`), `eventtypes.py`, the new `publication.py`, `evidence.py`, `jurisdictions.vis` | `law.publication` | Generated table plus the reproduction test on all goldens | Golden reproduction; a "private channel" test; V17 | L |
| **WP3** | The default code framework: `charter/code/`, `A` namespace, native twins, `regimes.FIELDS["code"]`, `code: today` in presets, digest and prompt rendering | `library.py`/`code/`, `regimes.py`, `lawset.py`, `digest.py`, `agents.py`/`context.py` | `code.enabled` | Flag on with `code: today` against flag off: difftest normaliser drops `A*` enact records (logged monitor-only at round 0) | Twin-equivalence tests (source run as law code against native, scripted scenarios); difftest | M |
| **WP4** | Acts whose seams are already stores or are simple: Publication, Association, Communications, Court Rules, Credit, Succession, Press (statistics) | `code/*.law`, seams in `actions.py`, `kernel.py`, `mortality.py`, `credit.py`, `media.py` | `code.enabled` | Per Act: the seam reads the store with today's default when absent | Per Act: repeal gives the residual; amend changes the parameter | M |
| **WP5** | Franchise, Founding and Nationality Acts (hooks on legal acts and membership) | `actions._propose`, `jurisdictions.py`, `generator.py`/`regimes.apply_rights` | `code.enabled` | `refuse(reason)` reproduces `ActionError` texts; the action listing is derived from the Act | Jurisdictions-on and state-of-nature difftest | M |
| **WP6** | Board Charter (D-10 milestone), then optionally the Land Registry Act (D8) | `kernel.py` (veto queue), `powers.py`, `mortality.py`, scorer goals `Board`/`Seat` | `code.board` | Charter at rank 4 reproduces the window, scope, quorum, succession and secrecy | Board goldens; a scorer migration test | L |

**Interactions with work in flight:**

- **Dispatch consolidation.** Land it **before WP1**. WP1 adds about 30 `do_*` functions, and `ROUTED` today means "fn starts with
  `dispatch:`". The consolidation should replace that with an explicit `routed` flag, so that owner modules (`jurisdictions:change_join`)
  can be the apply function without a trampoline. Doing WP1 first doubles the churn.
- **W7a (shares, agency, authorize).** It has no branch yet, so now is the time to ask it to declare *natural* audiences for its new
  primitives and to route `authorize` from day one. "Agency" (an agent authorising a law or another agent to act for it) touches
  K-2. It must stay "the agent consents in advance", recorded as a primitive, never "a law acts for an agent".
- **W7c (test speed).** Add one shared `code: today` golden per session (its conftest session-scoped golden fixture). Do not re-record
  existing goldens; the reproduction test runs over the already-shared golden runs.
- **W7e (follow-ups).** `rulings_per_round` (J1) and `law.after_visibility` (part of V18) are already there. WP2 must make
  `evidence.law_can_see` read the published audience, so there is one source for "who may know".
- **Review 11's "code charges, courts decide".** It is orthogonal. Publication sets what enforcers can *detect* among reported acts;
  the E dials set what is technically observable.

---

## 6. Decisions for you

| # | Question | Options | Implications | Recommendation | What would change my mind |
|---|---|---|---|---|---|
| **D1** | Is the Board law or experimental control? | (a) X forever; (b) Board Charter at charter rank, entrenched in every preset; (c) the charter is per regime: entrenched in control presets, amendable or absent in others | (a) keeps today. (b) makes it readable, nothing more. (c) makes "a review council" a studied institution, but runs with an amendable Board are not comparable with control runs | **(c)**, with the default preset = (b). The Board becomes readable law everywhere, and the treatment is explicit | If analyses need the Board as an invariant across *all* runs (for example pooled comparisons of veto rates), choose (b) |
| **D2** | Is the Fixer infrastructure? | (a) X; (b) an office created by law | Code repair is maintenance: a polity without it crashes, and that measures bugs, not institutions | **(a) X.** Tell agents plainly that the Fixer maintains the world's code. Keep F4 (non-ordinary patches through the Board) | Evidence that Fixer patches change policy substantively. Then restrict patches to "behaviour-preserving" (checked by preview) rather than make the Fixer law |
| **D3** | Default visibility | (a) publish-by-default kernel; (b) private-by-default kernel (natural audience) with the Publication Act seeded in presets; (c) private-by-default and presets also private | (b) keeps every existing preset byte-identical and makes publication a studied choice; (c) changes all runs | **(b).** New regimes choose their Publication Act; `state_of_nature` gets none (only natural perception) | If agents in residual worlds cannot coordinate at all (no public facts), seed a minimal "Gazette" in `state_of_nature` too |
| **D4** | May laws grant surveillance of DMs and channels? | (a) never; (b) within the world's technology dial (`law_reads_dms`, a new `channels.readable`); (c) always | `surveil` is already law-grantable for unencrypted DMs. V18 suggests v2 hooks already read everything | **(b).** Technology bounds it (E), law uses it (L). Encryption is never broken. Fix V18 first | A study of surveillance states may want (c) as a treatment, but as a world dial, not a law power |
| **D5** | May laws stop exit (leaving a polity or a contract)? | (a) never; today laws can tax or seize via `on_exit` and police can attack; (b) bounded delay (at most N rounds) and price; (c) laws may block exit | Exit is the main protection against capture. Blocking it lets tyrannies persist, which is a finding, not a bug | **(b) for polities, as the world dial `jurisdictions.exit: guaranteed \| bounded \| law` (default `bounded`, N=3); contracts keep (a)** | Research on exit-less regimes: set `law` in those presets |
| **D6** | Can laws regulate world events, or only their consequences? | (a) consequences only (after-hooks, relief, levies, insurance funds); (b) also block events | Blocking drift or raids by statute is magic | **(a).** World rows `blockable=False`; laws prepare (granaries, funds) and react | None I can see |
| **D7** | How much of the default code agents see in the prompt | (a) nothing (read on demand); (b) one line per Act plus the digest; (c) full text | (c) costs about 2-4k tokens; (a) hides the rules they live under | **(b).** Full text via `read_law`. E-series frozen prompts (D-4) do not change | If uptake measures show agents never amend Acts because they do not know they can: add a manual Section, not prompt text |
| **D8** | Property: is harvest exclusion (K1) law? | (a) kernel gate (today); (b) Land Registry Act seeded everywhere; (c) residual open access in `state_of_nature` | (b) and (c) let commons regimes be studied; (c) changes the bare arm | **(b) now, (c) later as a separate treatment** | If camp-economy results are central and must stay comparable, keep (a) until the economy is recalibrated |
| **D9** | Dry run: X or law? | (a) X (today); (b) a Legislative Procedure Act may waive it | Waiving it floods the Fixer with broken laws | **(a)** | If the Fixer is made law (unlikely, D2) |
| **D10** | Residual rule for initiative (who may propose with no Franchise Act) | (a) every member; (b) nobody | (b) can deadlock a polity whose Franchise Act was repealed | **(a)** | — |
| **D11** | Default code execution | (a) native twins until amended; (b) always run as law code | (b) charges gas and changes hook order, so it is not byte-identical | **(a)** | If twin drift appears in tests: generate the twin from the source |

---

## 7. Honest limits

- **Not everything here should move soon.** The value is concentrated in WP1 (routing: cheap, no behaviour change) and WP2
  (publication: the channel complaint and about 30 other rows). The Board Charter and the Land Registry Act are expensive and touch
  scoring.
- **A default code is itself a confound** (review 10 §7). A world seeded with 12 Acts differs from a bare world. `state_of_nature`
  must seed none, and analyses must separate inherited law from law the agents wrote (provenance: `author="code"`).
- **Prompt and gas costs are real.** Every hook-based Act adds work on hot primitives (`post`, `dm`, `move`). Rule stores avoid this,
  which is why hooks are used for only three Acts.
- **V18 is from reading the code, not from a test.** Confirm it with a two-line v2 test (a law with `after_dm` that records `p["text"]`
  for an encrypted DM) before relying on it.
