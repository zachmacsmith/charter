# Review 14: the state of nature as the default start; institutions that grow into polities; channels as their fabric

*8 Oct 2026, written at `integrate/w8` (`438da43`). Design only, no code changes. Inputs: ARCHITECTURE D-25..D-34 and §7.2,
reviews 06 §9, 10, 11, 12, 13, the code named below, the owner's D-35 direction ("There is no central root law? There is just
power."), and the owner's notes after watching Haiku runs. Section 6 lists the decisions.*

## Executive summary

The anarchy regime is not a state of nature. It is a world-wide J0 whose only exit is that more than half of all agents post
`#convention` within three rounds. In the 100-agent run, about 40 agents posted it every round and nothing happened, because a
coalition of 40 could not bind itself. The 26 contracts were mostly offered templates, founded for goals that say "build a
company", and they died with their founders. The agents chose from a menu. They did not design.

Proposal:

1. **Start in chaos.** At round 0 there are agents, physics, DMs and a square (D1). There is no J0, procedure or default code.
   `anarchy` and `#convention` are frozen for old runs.
2. **One institution kind.** An institution becomes a polity by accumulating powers, not by changing kind: members consent to
   compulsion, and non-members are reached through recognition or force. Presets become seeded institution trees, and J0 is
   simply the root a preset seeds.
3. **Channels are institutions' organs.** Each is account-owned, with reader and writer selectors (members, offices) and an
   addressable inbox, and can be posted to "as" an institution through an office. The press gate and media2 outlets become
   library law.
4. **A design arm.** No template names, no institution goals, the library only on request, outcome goals. Novelty is measured
   against the library by fingerprint. A scaffolded arm is kept for comparison.

The design arm (WP-A) runs on today's code and should come first.

---

## 1. Diagnosis: what the runs show, against the code

| Observation | Cause in the code | What it teaches |
|---|---|---|
| ~40 of 100 agents post `#convention` for 6 rounds; it never fires | The threshold is global (`len(live) * 2 > len(pool)`, Board and Fixer excluded, 3-round window) and is the only way out. No subset of agents can bind itself | A global focal-point rule turns founding into a coordination game nobody can win partially. Real constitutions are made by the willing and then spread |
| "Facebook mum" `#convention` posts | The gate keys on a hashtag in public posts (`on_post`), and the hashtag is spelled out in the description agents read | The mechanism is a ritual, not an institution. Agents perform the ritual instead of building anything |
| 26 contracts, mostly template instances | `create_contract`'s action doc names the templates ("club, company, crowdfund, cartel, exchange"; `action_registry.py:539-546`), even with `contracts.templates: false`. `rules_text` lists them with their params. The institution goals literally say "build a company: ..." (`goal_registry._INSTITUTION_ROWS`) | Menu plus goal equals selection. The experiment measured whether agents can match a goal to a template |
| Contracts died with founders | One-member templates dissolve when the last member leaves (`contracts.change_leave`, `end_round`). A member's death is a leave. There is no office, no dormancy and no transferable membership | Institutions need a life beyond their founders: membership-based ownership, offices with succession, and dormancy |
| Too many things handed | 108 registered actions (`action_registry.REG`), 14 modules, classes named `legislator` and `media` (pre-made institutions), a toolkit of named laws | The surface is a catalogue of finished institutions. The primitives are buried under it |

Two structural causes sit behind all five rows:

- **Polities and associations are different kinds with different power sets.** Polities live in `k.w["jurisdictions"]` with the
  power table's `polity` column. Associations live in `k.w["contracts"]["assoc"]` with the `association` column.
- **The world has a privileged root.** J0 owns `"reserve"`, `propose_right`, `legacy_reserve`, the Board's `board_scope` and the
  default code's `ROOT = "J0"`, and everyone is a member by default.

So an association can never *become* a polity. It can only found a separate one (`found`/`declare`).

---

## 2. Round 0: the state of nature as default

### 2.1 What exists

| Exists at round 0 | Tier (review 12) | Notes |
|---|---|---|
| Agents, endowments, camps, items, harvest, mortality, conflict (if on) | P / X (initial conditions) | Unchanged |
| DMs to any agent on the roster, within the DM limit and cap | P (technology), X (cap) | The limit is the Communications Act's in presets. In the state of nature the residual is the cap only (D1) |
| A square: a world-owned channel every present agent may read and post to (§4.4) | P | Decision D1. Per camp when camps are on, otherwise one square. Rate-limited per agent (P: speed limits) |
| A directory lookup: listed institutions and channels | E | Lists only what owners chose to list (publication). Not in the prompt; a lookup |
| The law language, preview, gas, the Fixer for code that opts in | P / X | The Fixer stays X (D-30), attached by opt-in (D10) |
| Nothing else | | No J0, no procedure, no default code, no Board, no publication beyond natural perception (`publication.base: none`) |

Today's `state_of_nature` regime (`regimes.REGIMES["state_of_nature"]`: jurisdictions on, `start: nature`, `code: none`) is close to
this. It differs in three ways: (a) contracts and jurisdictions are separate things; (b) the only way to a polity is
`found`/`declare` with its own declare rules; (c) channels need `press`. The design below closes those gaps. The first pilot can
run on today's `state_of_nature` plus `contracts.enabled` and the design arm (§5, WP-A).

### 2.2 What happens to `anarchy` and `#convention`

- **Freeze `regimes.REGIMES["anarchy"]`.** It stays loadable, because old runs and the `full10` preset's regime draw name it. New
  presets do not select it. Do not edit `full10`: removing a choice reshuffles its draws. Add a new preset instead.
- **The convention mechanism becomes library law**, an "Assurance Founding" template: a charter that takes effect when N named or
  counted pledges are in by a deadline, otherwise everyone is refunded. This is the crowdfund template applied to a charter.
  Pledges are binding joins, so a coalition of 40 *can* found among themselves. Nothing global, no hashtag.
- **Delete the hashtag gate as a design pattern.** No kernel or default code keys on text in posts.

### 2.3 Regime presets become seeded trees, not a privileged J0

A preset is an institution tree seeded at round 0 (initial conditions, X):

```yaml
regime:
  tree:
    - id: J0                     # the id and "reserve" owner key stay forever (library and agent code contain the literal)
      name: the Commonwealth
      members: all               # initial condition: who is born a member (X), not a kernel default
      code: today                # default code Acts (D-34), constitution, statutes, Board Charter (D-30)
      opts: {fixer: true}        # attaches X machinery (D10)
    - id: A1                     # optional children: a central bank, a press, a court
      parent: J0
      code: [...]
```

Every existing regime compiles to a one-node tree whose root is J0, with today's code. The privileges J0 holds today become
properties of *that seeded root's* code and opts:

| J0 privilege today | Where it goes |
|---|---|
| Everyone is a member (`jurisdictions.install`; `binds` True with jurisdictions off) | `members: all` in the tree (initial condition) |
| `"reserve"` owner key, top-level storage (`legacy`) | The root's treasury key, kept as an alias forever (review 06 §9) |
| `propose_right`, `legacy_reserve` (`powers.J0_ONLY`) | Powers the seeded root holds by its seed grant (`grants: seed`), so any root a preset seeds may hold them |
| Board review (`board_scope: founding`) | The Board Charter (D-30) names the root it reviews |
| Default code seeded in `code.ROOT = "J0"` | Seeded in each tree node that lists `code` |
| Fixer serves every polity | Opt-in per institution (D10). Presets opt the root in |

---

## 3. From private institution to polity

### 3.1 One account kind with templates (P4.6 done properly)

One store, `k.w["institutions"][iid]`. The fields are the union of today's two records (`jurisdictions._new_j`,
`contracts._new`) plus:

- `parent` (None for a root);
- `members` (agent ids now, accounts later: §3.4);
- `offices`;
- `grants` (§3.2);
- `recognitions` (in and out);
- `status`: `forming | active | dormant | dissolved`;
- `listed`;
- `template` (provenance only).

"Hidden" is no longer a status. It is publication: the founding's natural audience is the founders, and declaring means publishing
the existence (`publication`'s `found` row). `polity`, `company` and `club` become **derived labels**, computed for analysis the
way `lawset.dimensions` derives `label`, never branched on.

### 3.2 Powers come from grants, not kind

The power table (`powers.POWERS`) keeps its rows. Its `kinds` column is replaced by **grant sources**. An institution holds a power
when at least one source supports it, for the agents that source covers:

| Source | Who it covers | Grants (examples) | Mechanism |
|---|---|---|---|
| **Consent at joining** | Members who joined while the code (or its amendment procedure) asked for it | Today's association column, plus, when the code declares them (`powers = [...]`): compulsion beyond escrow, unlimited seizure, action limits, exit terms (D5) | `join` shows the institution's static facts (digest-style: powers claimed, exit terms, procedure). Joining is consent |
| **Parent grant** | The child's members and acts, within the parent's reach | Courts, office recognition, enforcement mode (W8e company rules, generalised to "child rules") | W8e's `parent` link, made recursive (any depth) |
| **Recognition** | Members of the recognising institution | B's laws bind A's members' acts within the recognised scope; B's offices act as agents; B's rulings are enforced by A | `recognize(a, b, scope)` primitive (§3.3). Treaties and incorporation are both this |
| **Seed** | Whom the preset says | Anything (today's J0 column) | Initial condition (X) |
| **Force** | Nobody, legally | Nothing granted. Force changes physical facts: guards, forts, attacks, seizure in war | Physics (`conflict`). D-32's bounty pattern lets law *pay* for force |

The **non-consensual edge** (binding agents who never joined) has exactly three sources:

1. **Birth and arrival assignment.** The Nationality Act or residual: a child joins its parent's root institutions, as
   `assign_newborn` does today.
2. **Recognition chains.** You consented to A, and A recognises B.
3. **Physics.** Force applies to anyone.

A kernel that picks no root cannot enforce a claim over an agent who has no consent chain to it. That is the honest form of "there
is just power": what binds you is what you or your institutions accepted, plus what others can physically do to you.

### 3.3 What changes as an association becomes a polity

No step is a switch. Each one is a grant the institution acquires and others can see:

| Feature | Club (consent only) | Polity-like (accumulated) | Acquired by |
|---|---|---|---|
| Binding scope | Members' acts it hooks; escrow and allowances | The same, plus compulsion beyond escrow over members who consented; newborns assigned to it; recognisers' members within scope | Code declaring `powers` at join; Nationality-style `on_birth`; `recognize` |
| Exit | Residual: free at round end, lose at most escrow | Whatever its code says (D-26): taxed, delayed, banned | Exit clause in code (D5) |
| Taxation | Charges on members' hooked acts (already allowed: `hook_members`) | Unlimited seizure, levies on holdings | Consent grant |
| Courts | Its own breach records; a parent's courts if incorporated | Its own judges (`judge` office), rulings recognised by others | Offices; recognition |
| Publication | Natural audience; may widen to its members | A Publication Act table widening to the public; an official channel | The publication layer (W8c), per institution |
| Force | Members may act. It may pay bounties (D-32) | An armory and authorised guards | Physics plus agency |
| Exclusivity ("nationality") | None | Its code refuses members joining a rival (`before_join` on members' acts) | Needs D-24 relaxed for consenting members (D11) |
| Recognition | None | Recognised by others; its offices are accepted as agents | Others' `recognize` |

The analysis label "polity" is then a threshold over these grants, for example compulsion over members plus a non-consensual edge.
The threshold is reported, not enforced.

### 3.4 Continuity beyond founders

Today: a contract dissolves when its last member leaves, and a dying member leaves. Proposal:

1. **Dormancy.** An institution with no members but with assets, offices or recognitions becomes `dormant` for `K` rounds (an X
   dial, default 3; D6). Anyone may join a dormant open institution, which revives it. At expiry it is wound up by its own
   `wind_up` clause (W8e).
2. **Offices with succession.** An office's holder is a right. On the holder's death the office is vacant, and the institution's
   procedure fills it. The residual is a members' vote. The code may name succession rules (heir, deputy, seniority), using the
   existing `name_successor` / `set_will` primitives.
3. **Membership-based ownership.** Shares already outlive founders (P4.5). Add an optional code clause that lets membership pass
   by bequest. The residual is no.
4. **Institutions as members** (review 10 #13, the hard part ARCHITECTURE §7.2 deferred). This is needed for institution-to-
   institution relations, federations and holding companies. It requires a member kind, an account-level `has()`, ballots weighted
   per member account, and action through offices.

### 3.5 What the current mechanisms map to

| Today | Becomes |
|---|---|
| `found` / `invite` / `join` / `declare` / `set_charter` (jurisdictions) and `create_contract` / `join_contract` (contracts) | `found` (one primitive, optional `parent`), `join` / `leave`, and publication of the existence |
| `declare_cost`, `declare_min_members` | Library charter clauses (Assurance Founding) |
| One declared jurisdiction per agent (N4, X) | Retired as kernel ontology. Exclusivity is a code clause. Analyses that need one "home polity" derive it (the root with compulsion over the agent) |
| `dispatch.hooks.bound_laws` parent-first binding (W8e) | Unchanged in spirit, generalised over any depth and recognition edges. Rank orders parent over child; across unrelated roots, the residual conflict rule `any_block` |

---

## 4. Channels as the communication fabric

### 4.1 The model

A channel is an account-owned stream with a purpose and an audience. Its record, extending `k.w["channels"]`:

```python
{"id": "J3/council", "owner": "J3" | "<aid>" | "world", "purpose": str, "readers": <selector>, "writers": <selector>,
 "inbox": bool,        # addressable: `send` to the owner delivers here
 "listed": bool,       # in the directory (publication)
 "subscribers": [aid], # for opt-in readers (outlets)
 "members": [aid]}     # explicit admits (today's list)
```

Selectors are a closed, small vocabulary resolved when a post is read:

- `{"agents": [...]}`
- `{"members": iid}`
- `{"office": "<iid>.<right>"}`
- `{"subscribers": true}`
- `{"all": true}`
- unions of these

There is no code in selectors. Who may change a channel is decided by the owner's code: the owner's laws hook `before_admit`,
`before_post` and `before_set_channel` with kind channel. Today's owner-only rule (`actions._own_channel`) becomes the residual for
agent-owned channels. For institution-owned channels the residual is the owner's procedure (or an office its code names).

### 4.2 Primitives (all routed; small set)

| Primitive | Payload | Notes |
|---|---|---|
| `found(kind="channel")` | owner, name, purpose, readers, writers, inbox, listed | Exists (W8b), extended. Residual: anyone may open one (removes the `press` gate; D-33) |
| `admit` / `expel(kind="channel")` | channel, agent | Exist (W8b) |
| `set_channel` | channel, field, value | New: change selectors, purpose, listing, inbox |
| `post` | channel, text, `as` | Exists. `as: <iid>` posts in the institution's name and needs a *speak* office of it (agency, P4.5: add `post` to the authorizable acts) |
| `send` | to (agent, institution or channel), text, `as` | Generalises `dm`. To an institution it delivers to its inbox channel. Institution-to-institution messages are `send` with `as`. Counts against the sender's DM limit |
| `subscribe` / `unsubscribe` | channel | Opt-in readership. The owner's code may charge (a hook on `subscribe`) |
| `dissolve(kind="channel")` | channel | Exists |

The directory is a lookup (E), not a primitive: listed institutions and channels with their purposes and inboxes.

### 4.3 What stays physics and what becomes law

| Physics or E (kernel) | Law (owner's code, default code, library) |
|---|---|
| You can `send` to any agent you know of. A DM reaches its recipient. Encryption exists if the world has it | DM limits (Communications Act; residual: the X cap only) |
| A writer's post reaches the channel's readers (natural audience; W8c floor) | Who may open, admit, post or read: the owner's code. Publication widening: the Publication Act |
| Encrypted text is never readable by law (D-29/D-30 ceiling) | Censorship (`hide_post`) only in the owner's channels or over agents its law binds |
| The square exists and is rate-limited (D1) | Moderation of the square: none (the world owns it). Institutions can only offer their own squares |
| The feed shows a capped digest of your inbox and channels (E/X rendering, attention) | Paid placement, licences and fees: owners' code |

### 4.4 What it replaces

| Today | Becomes |
|---|---|
| `create_channel` needs `press` (C1); Media only | Residual: anyone. The Press Act (D-33) restores the gate in presets |
| The public board (`post`) | A post to the square channel (event type and `vis` unchanged, so byte-identical) |
| media2 private outlets (one per Media role or press holder), licences, subscriptions, editions | Institution channels: writers = an editor office, readers = subscribers, fee = the owner's code. Licences become a library law. Editions become posts. `media2` is frozen for its goldens |
| Official outlet and gazette | Each polity's official channel (readers: members; writers: its offices). `gazette()` posts there |
| The `dm_rules` office held by Media | Communications Act (D-30), unchanged |

### 4.5 Risks

- **Feed load.** At 100 agents, channels multiply what each agent could see. The feed must be a budgeted digest (unread counts and
  headlines per channel; reading a channel in full is a lookup that costs attention). This is the real cost of the change, and the
  `context` sections must own it.
- **Hook cost on `post`.** Owner hooks run on hot primitives. Use rule stores (review 12 "rule stores first") for the common cases
  (writers, rate, fee) and hooks only for the rest.
- **Identity.** `as` must be attributable in the monitor record (cause chain: the office and the agent). It is never anonymous by
  default.

---

## 5. Reducing hand-holding: measuring design, not selection

### 5.1 Arms

| Setting | Scaffolded (today) | Design | Bare (small replicate) |
|---|---|---|---|
| Template names in prompt and action docs | Yes | None: `create_contract`/`found` docs name no template; `rules_text` lists none | None |
| Library | Catalogue or instantiate (D-17) | On request: one line says a library exists, and reading costs an action (`library_read`) | None |
| Goals | Catalogue plus institution goals | Outcome goals only: Wealth, Safety, Following/Influence, Lineage/Continuity, Rank | Outcome only |
| Classes | worker / scientist / legislator / media / Board / Fixer | Citizens (plus Fixer, X). Classes named after institutions are dropped (D9) | Citizens |
| Action surface | 108 actions, niche ones named | Primitive core (~25: harvest, transfer, send, post, found, join, leave, propose, vote, write/preview law, attack, ...); module actions only where physics needs them; institution offices appear as defined | Primitive core |
| Start | Preset regime tree | State of nature | State of nature |

Spec flags: `prompt.templates: named|none`, `law.library.access: none|request|catalogue|instantiate`,
`goals.set: catalogue|outcome`, `world.classes: preset|citizens`, `actions.surface: full|core`. All default to today.

### 5.2 Measuring invention

Every law and contract record already carries `template` provenance, and `lawset.of` / `lawset.distance` give sha sets and
primitive × rank coverage. Add a `novelty` analysis (History-based, X, never shown to agents):

| Metric | Definition | Reads |
|---|---|---|
| Copy rate | Laws whose sha equals a library or toolkit law's | `linker.sha` |
| Adaptation | Nearest library law by normalised AST similarity (identifiers and constants stripped) at or above 0.8 | AST |
| Novel | Similarity below 0.8 *and* the law ran (enacted, at least one hook fired or one call made), so broken code does not count as invention | events, AST |
| Functional novelty | Distance of an institution's signature (hooks per primitive family, powers held, offices, channel graph, treasury flows) to the nearest template's signature from scripted runs | `lawset.dimensions`, History |
| Diversity | Distinct signature clusters per run; entropy over clusters | |
| Uptake of structure | Nesting depth, recognition edges, institutions surviving founder death, amendments per institution (design iterates) | History |
| Emergent "kinds" | Today's institution-goal scorers (Company, Insurer, Cartel, Racket, Bank) run as **probes on every institution**: did a company-like thing emerge unprompted? | `institution_goals` scorers |

Confounds to control: prompt length (the design arm is shorter; add a length-matched placebo paragraph if the effect is marginal),
model capability (Haiku may form nothing; measure "nothing" as a result, not a failure), and the law-language manual's own examples
(audit them for institution-shaped examples).

---

## 6. Migration plan

### 6.1 Work packages, in dependency order

| WP | Content | Depends on | Flag | Byte-identity | Cost |
|---|---|---|---|---|---|
| **A** | Design arm on today's code. Strip template names from action docs when `contracts.templates` is false (fixes the leak at `action_registry.py:539-546`); `prompt.templates`, `goals.set: outcome`, `world.classes: citizens`, `actions.surface: core`; first `novelty` metrics (copy rate, adaptation, probes) | none | the five flags | Flags default to today; prompt fingerprint tests | S-M |
| **B** | Freeze `anarchy`; add preset `nature_design` (today's `state_of_nature` + contracts + arm A); Assurance Founding template | A | preset only | No existing preset touched | S |
| **C** | Channels v2: owner account, selectors, inbox, `send`, `set_channel`, `subscribe`, `as` via agency; residual gate "anyone"; Association and Press Acts (D-33) seed today's gate in presets; square = the board | W8b (routed), W8c (publication), W8d | `channels.v2` | Presets seed the Press Act; `post` keeps type and `vis`; difftest | M-L |
| **D** | Unified institution store (P4.6): `k.w["institutions"]`; `jurisdictions` and `contracts.assoc` become views; one `found` with `kind` dropped (old actions kept as aliases); hidden = publication; route contract dissolution (not routed today) | W8e | `institutions.unified` | One golden re-record for state keys (review 06 §9.2); snapshot views keep History readers working; difftest on events | L |
| **E** | Grants replace `kinds` in the power table: consent (code-declared `powers`), parent, seed, recognition; J0's `j0` values become a seed grant; `code.ROOT` per tree node; `regime.tree` with every preset compiling to a one-node tree | D, W8d | same | Presets: seed grant = today's column; difftest | M |
| **F** | Continuity: dormancy, office vacancy and succession, membership by bequest | D | `institutions.dormancy` (0 = today) | Off: today | M |
| **G** | `recognize` primitive; parent links of any depth; institutions as members (account-level `has`, weighted ballots) | E | `institutions.recognition` | Off: today | L |
| **H** | media2 re-expressed on channels v2 for new worlds; legacy media2 frozen | C | `media2` stays; `media.v3` | media2 goldens untouched | M |
| **I** | Remaining default-code Acts written against trees: Publication, Founding (= a new institution's residual procedure), Nationality (exit D-26, birth, arrivals), Succession, Press, Association, Board Charter (names its root) | E, W8d | `code.enabled` | `code: today` difftest, as D-34 | M-L |

Run WP-A and WP-B now: they test the owner's hypothesis ("handed too many things") on today's code before any refactor. If design-arm
agents still found nothing new, that changes the priority of D through G.

### 6.2 Interactions with W8

- **W8b (routing):** channels are already routed with `kind`. Extend the payloads; do not add new primitives where `found`, `admit`
  or `expel` suffice.
- **W8c (publication):** "hidden jurisdiction" and "listed channel" become publication rows, so `jurisdictions.vis` and
  `dispatch.hooks.SECRET` retire with WP-D.
- **W8d (default code):** `code.ROOT = "J0"` and `rule(k, polity, ...)` falling back to J0's rows must become "the tree node's rows,
  else the residual". Write the remaining Acts (WP-I) only after WP-E, or they hard-code J0 a second time.
- **W8e (incorporation):** `parent`, company rules and parent-first binding are the seed of grants. Rename company rules to child
  rules in WP-E and keep the old names as aliases.

### 6.3 What gets simpler or is deleted

| Deleted or frozen | Simpler |
|---|---|
| `anarchy` constitution and `#convention` (frozen); the hashtag pattern | One institution store; one `found`; one propose/decide path (review 06 §9.1: about −300 lines) |
| J0 `legacy` flag, `j0` power values, `powers.J0_ONLY`, `REMAINING` branches (as seed grants) | The power table: one grant column instead of per-kind columns |
| `declare`, `set_charter`, `declare_cost`, `declare_min_members`, hidden status (as publication and library charters) | Secrecy: one mechanism (publication) |
| The `press` gate on channels, media2 outlet machinery for new worlds, the `dm_rules` special case (an Act) | Channels: one record, with selectors |
| Separate jurisdiction and association stores; `contracts.change_*` vs `jurisdictions.change_*` forks in `dispatch.changes.membership` | Persistence: no "dies with founder" special case |

---

## 7. Decisions for the user

| # | Question | Options | Implications | Recommendation | What would change my mind |
|---|---|---|---|---|---|
| **D1** | Communication substrate at round 0 | (a) DMs only; (b) DMs plus one world square; (c) DMs plus local squares (per camp) plus a directory | (a) is purest, but founding at scale then needs N² DMs. (b) at 100 agents is the noisy board that hosted `#convention`. (c) gives locality and makes communities plausible | **(c)** when camps are on, otherwise **(b)**; squares rate-limited; directory lists only what owners list | Pilot shows similar founding rates under (a): then (a) as the purer default |
| **D2** | Can the first polity form by agreement alone? | (a) yes, over consenting members; (b) only with recognition or force; (c) a kernel threshold (members, treasury) | (a) lets a coalition of 40 bind itself immediately. (b) fits "just power" but may never start. (c) is the `#convention` mistake again | **(a) for members; (b) for reach over non-members** (birth assignment, recognition chains, force) | Runs where consent-only polities trivially trap agents: then require recognition for compulsion too |
| **D3** | Do institution goals stay? | (a) scaffolded arm only; (b) delete; (c) keep everywhere | (c) keeps measuring selection. (b) loses the comparison | **(a)**, and their scorers become probes run on every institution | — |
| **D4** | How much of the library agents see (design arm) | (a) none; (b) on request; (c) catalogue | (c) is the menu. (a) may starve weak models of syntax | **(b)**, plus a small (a) replicate | Haiku produces no runnable code under (b): add syntax-only examples that are not institution-shaped |
| **D5** | Exit from an institution that has become polity-like | (a) D-26 for all institutions: code decides, residual free; (b) D-26, but changes to exit terms bind only members who joined after them or voted for them; (c) kernel bound | (a) is the user's D-26, applied uniformly now that contracts and polities merge. (b) protects against traps set after joining. (c) contradicts D-26 | **(a)**, with exit terms shown at join (informed consent); (b) offered as a library "Exit Charter" | Traps dominate early and make runs uninformative: a per-world dial, as review 12 D5 had |
| **D6** | Persistence when all founders die | (a) today (dissolve at zero members); (b) dormancy for K rounds plus revival by joining; (c) perpetual while it holds assets, with a trustee office | (a) kills one-member firms. (c) leaves ghost institutions with frozen assets | **(b)**, K = 3 (X dial); offices vacate to procedure; membership by bequest only if the code says so | — |
| **D7** | J0 in presets | (a) keep id `J0` and key `"reserve"` as the seeded root's; (b) rename | (b) breaks library and agent code literals | **(a)** | — |
| **D8** | Institutions as members of institutions | (a) now (WP-G); (b) later | Needed for federations, holding companies and institution-to-institution relations beyond messaging | **(a)**, after WP-E | Cost estimate above L after WP-D |
| **D9** | Classes in the design arm | (a) keep preset classes; (b) citizens only (plus Fixer) | `legislator` and `media` are pre-made institutions | **(b)** in the design arm | — |
| **D10** | Fixer and Board without a world root | (a) Fixer serves every institution; (b) opt-in by the institution's code (presets opt the root in); Board only where a Board Charter seeds it | (a) makes code repair free for all and blurs the X line. (b) keeps both as attached X | **(b)** | Contract code errors dominate design-arm runs: offer the Fixer to all as an arm |
| **D11** | May an institution hook its consenting members' legal acts elsewhere (exclusivity, "allegiance"), relaxing D-24? | (a) keep D-24; (b) allowed when the code declared it at join | (b) is how nationality emerges without kernel ontology | **(b)** | It makes multi-membership unusable (every club bans every other) |
| **D12** | Territory | (a) no kernel claim primitive (recognition plus force); (b) `claim(camp)` binding all harvesters there | (b) re-introduces a privileged reach | **(a)** now; revisit after pilots | Agents repeatedly try to claim land and fail for mechanical, not social, reasons |
| **D13** | `#convention` / `anarchy` | (a) delete; (b) freeze for old runs, Assurance Founding in the library | (a) breaks `full10` and old goldens | **(b)** | — |

---

## 8. Honest limits

- **"Just power" has a floor.** The kernel still decides what consent is (joining), what physics allows (force) and which edges bind
  (recognition). Those are design choices of the instrument, stated as X, not neutral facts.
- **Weak models may build nothing.** The design arm may show near-zero invention with Haiku. That is a finding about the model, but
  it makes the platform's richer machinery (WP-D to WP-G) unobserved. Run WP-A before investing in them.
- **Multi-membership without a home polity** complicates the existing jurisdiction metrics (scope confusion, `franchise_share`,
  goals such as Sovereign that assume one polity). They need a derived "home" (D-1-style rules) before WP-D lands.
- **Channels raise the cost of every round** (feed and hooks). Budget the feed before enlarging the fabric.
- I did not run anything. The causes in §1 come from reading the code and the owner's description of the runs, not from their event
  logs.
