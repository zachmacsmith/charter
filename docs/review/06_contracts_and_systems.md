# Review 06: contracts, systems and institutions (owner's extension proposals)

*7 Oct 2026. Read-only, at `main` = `e58915d` (by then `feat/rights-registry` and `fix/laws-previews` had been merged, so `charter/rights.py`
and `charter/lawapi.py` are on main). Line numbers are for that commit. No runs were made. I have no run data on how often models use
the existing institution actions, so every statement about uptake below is a prediction.*

## 1. Verdict

The framing (rich systems, free institutions) is sound. The claim that rules can only be laws imposed by a jurisdiction is **half
true**. Most of a private-contract system already exists, but it is split across six modules, each with hand-made semantics:
- **Hidden jurisdictions** are voluntary associations with members, a treasury, a charter of code and hooks. Their code, though, is
  *dormant* until they are declared (jurisdictions.py:617-628), and an agent can belong to only one declared jurisdiction.
- **Projects** are kernel escrow with assurance refunds (projects.py:1-20).
- **Leases** are trustless rentals of a right (camptypes/leases.py:1-10).
- **Paid guarding** is a protection subscription (conflict.py:565-603).
- **Loans** come with a *law-set enforcement dial*: `seize | sanction | seize_sanction | none` (credit.py:36,62,215-258). The
  library ships both ends of that dial: "Loan Registry" against "Handshake Loans" (library.py:20-33).
- **Backed currencies** are already priced at treasury value divided by supply (kernel.py:216-228), which is exactly how a share
  should be valued.
- **`define_action` offices** are a form of agency (kernel.py:365; actions.py:731-752).

So **contracts should be built by generalising hidden jurisdictions** into live, non-exclusive associations with a *restricted*
power set. They should not get a second interpreter. That is an M-sized job (about 4-6 agent-days for v1), and agency and claims sit
cheaply on top of it.

The elegant end state, "a jurisdiction is a contract plus force", is achievable only as **shared machinery plus a power set per
kind**. Re-expressing J0 as a contract would break about 40 legacy branch sites and every golden fingerprint, and buys only
conceptual tidiness.

The three real risks are not engineering:
1. **Uptake.** Haiku-class models will rarely write contract code. Without parameterised templates the feature will be inert.
2. **Scoring.** Self-issued tokens can inflate Wealth unless they are valued conservatively.
3. **Confounding.** An association that can deduct from its members' harvests is a shadow state, and it changes what every
   jurisdiction experiment measures.

Ship contracts off by default, as an experimental condition, and template-first.

## 2. The proposals against the code

| # | Proposal | Exists today | Fit | Effort | Risk | Synergies |
|---|---|---|---|---|---|---|
| 1 | Systems vs institutions framing | Systems: camps with regrowth, drift and blights (events.py:135); resources and optional upkeep (resources.py:9,88); force (conflict.py); life and mortality; messages, files and archives (context.py, archive.py). Institutions: hidden and declared jurisdictions, projects, leases, loans, outlets (media.py:1-30) | Good as a design rule; already half-followed | none (a principle) | Used as a reason to rewrite. Don't | Everything |
| 2 | Private contracts | **Partial.** Hidden jurisdictions have members, a treasury (`fund`), a charter, code and hooks, but laws stay dormant until declared (jurisdictions.py:617, 645-661); `hooks()` skips undeclared ones (:493-500); one declared membership per agent (:131); the treasury cannot pay non-members (`owner()`, :332-370) | Strong: reuse `_new_j`, `scope_api`, `hooks`, `fnreg`, `Limited` | **M** | Uptake; prompt budget (94 actions registered already); confounds jurisdiction experiments | 4, 5, 6, 9, 11 |
| 3 | Capital (durable goods, wear) | Partial: commons capital through camp `invest` (camptypes/modifiers.py:171-182) and project `upgrade`/`granary`; upkeep; **no perishability, no depreciation, no owned durable goods** | Medium: holdings are plain item counts; durable goods need per-unit age or a decay pass | M-L | Changes Wealth and holdings_value scoring; models must reason about decay | 2 (storage firms), 8 |
| 4 | Agency (`authorize`) | Partial: offices through `define_action` + `invoke` (L4, scoped to members, invoke logged publicly). Leases move the right itself. Permit design in `charter/docs/design_laws_rights_capabilities.md` §4. **Note:** the context prompt advertises `invoke` only when `hidden` is on (action_registry.py:309), so law-made offices are invisible on the context path otherwise. Probably a bug; verify | Good: one check in `Kernel.move` / `has` | M | Vote proxies become vote markets (exclude `vote` by default); the log is the answer key only if every use carries `by=grantee, auth=id` | 2, 5, 9 |
| 5 | Claims and tokens | Partial: currencies only through law `create_currency`/`mint` (kernel.py:372-390); unbacked = value 0, backed = treasury/supply (kernel.py:216-228); loans are claims but cannot be transferred | Good for **shares** (backed currency on a contract's treasury); weak for free IOUs (no price discovery, no exchange) | S (shares), M (agent IOUs) | Scoring inflation if IOUs are valued above 0; the kernel invariant "currency only from mint in enacted laws" (kernel.py:8) must be restated | 2, 9 |
| 6 | Group channels with code rules | Partial: `create_channel` gated on `press` (actions.py:815-816, action_registry.py:303); owner-managed; `open` flag; paid subscriptions exist for media2 outlets | Easy | **S** | Feed fragmentation; little else | 2 (an association gets a channel) |
| 7 | Identity and aliases | Partial: `anon_post`, `forge_dm`, the `impersonate` role, hidden powers | Defer, as the owner says | L | Breaks evidence and court semantics | none now |
| 8 | Coupled ecology | Partial: regrowth, drift, blights, raids (outside.py) | Defer | L | Calibration churn | 3 |
| 9 | Institution-building goals | None directly. Revolutionary, Schism and Exodus touch jurisdictions (goals.py:120,146,152) | Good once contracts and the History object (review 05) exist | S per goal after History | Planting a goal manufactures the institution: emergence studies need goal-free arms | 2, 4, 5 |
| 10 | Law library, regimes as specs | **Largely exists.** 72 library laws in 9 categories (the docstring says 58, library.py:1); 22 named regimes, inline definitions with `base:` (regimes.py:1-35, 571); 15 constitutions; `start_laws` (runner.py:149) | Good; the gaps are regimes for *founded* jurisdictions and dimensional regimes | S-M | Labels ("UK-like") exceed what the mechanics can distinguish | 2 (contract templates share the mechanism) |
| 11 | Enforcement of breach | Partial: hooks are code-enforced; clauses + `accuse`/`rule` (actions.py:1042-1110) give after-the-fact penalties; loans have the consequence dial; `lawful_attack` (jurisdictions.py:288) | Make it a spec dial for contracts (§4) | S-M | Too many dials make conditions combinatorial | 2, 10 |

## 3. Contracts: design sketch

**Principle.** A contract is a jurisdiction record with `kind: "association"`, a different power set and many-to-many membership.
Everything else is reused:
- the law language, static check and classification (lawlang.py);
- `Limited` step and depth limits (lawlang.py:150-185);
- `fnreg` and the marshalled function checkpointing (kernel.py `_dump_fn`/`_load_fn`);
- `scope_api` wrapping;
- `lawapi.LawFn` metadata, extended with a `contract` scope column;
- treasuries keyed `reserve:<id>` through `J.pool` (kernel.py:240-252, so `move`, `bal` and `price` work unchanged);
- ballots with a jurisdiction tag, for member votes.

**Data model** (in `k.w["jurisdictions"]`, so dry runs and checkpoints cover it for free):
```python
{"id": "A3", "kind": "association", "name": "Northern Timber Co", "status": "active|dissolved",
 "founder": "Ada", "members": ["Ada", "Bo"], "reserve": {...},          # treasury: owner key "reserve:A3"
 "template": "company", "params": {...},                                # or None for raw code
 "escrow": {"Bo": {"timber": 5}},                                       # member deposits the code may forfeit
 "allowances": {"Bo": {"timber": 2}},                                   # per-round pull rights members granted (section 4)
 "procedures": {...}, "exit": {"notice": 0, "forfeit": "deposit"},
 "breaches": [{"round": 14, "member": "Bo", "clause": "deliver", "remedy": "forfeit 5 timber"}]}
```
Membership sits in the record (`members`), not in `k.w["jur"]["member"]`, which stays the single declared polity. Laws carry
`law["jurisdiction"] = "A3"` exactly as today.

**Activation.** Contract law is *active at once*: `passed()` and `intercept_enact()` treat `kind == "association"` like
`declared`. `hooks()` (jurisdictions.py:493) includes associations, and `binds(k, lid, aid)` becomes
`aid in members` for association laws. Several associations can then tax one transfer.

**Tax destinations must become per law.** Today `_send` and `_harvest` sum every hook's deduction and pay it to
`J.home_reserve(payer)` (actions.py:245, 530-543). With associations, each law's deduction goes to *its own* treasury. For polities
this is behaviour-identical, because every binding law is in the home jurisdiction. That makes it a safe refactor with an unchanged
golden.

**Power set (the core design decision).** In `scope_api`, an association law may:
- read as today;
- `move` from its **own treasury to anyone**, members or not (a firm must buy from outsiders; polities can't today: :332-370);
- `move` from a member **only within that member's escrow or allowance**;
- `mint`/`burn` its own currency against its treasury;
- `create_right("A3:manager")` and grant or revoke it among members only;
- `define_action` an office invocable by holders (this is agency);
- `expel` and `admit`;
- `open_ballot` among its members;
- deduct from members' harvests and transfers, and block members' transfers, through hooks;
- `notify`, and post to its own channel.

It may **not**:
- grant, revoke or suspend kernel rights (vote, propose, judge, press, ...);
- `fine` beyond escrow;
- `limit_actions`, `set_dm_limit`, `hide_post`, `censure`;
- `lawful_attack`;
- touch camp rules;
- use any `LEGACY_ONLY` function.

This is one new column in `lawapi.LAWFNS` (`contract="allow|escrow|deny"`), so the table generates it and tests it.

**Errors.** A failing contract law is suspended and its members are notified. It does *not* go to the Fixer's queue
(kernel.py:657-662). The Fixer serves the public order. Fixing a club's bylaws would make the Fixer a free in-house engineer.

**Actions** (keep the count small; the registry already holds 94):
- `create_contract {name, template?, params?, laws?}`
- `join {"contract": "A3"}` and `leave`: reuse the jurisdiction actions with an id prefix, rather than adding new verbs
- `fund` (exists)
- `propose {"jurisdiction": "A3"}` (exists)
- `authorize` (section 4)

That is about two new verbs. Templates carry the uptake:
```python
TEMPLATES["mutual_insurance"] = '''
title = "Mutual Insurance"
intent = "Each member pays {premium} {item} per round into the pool; a member disabled or raided is paid {payout} from it."
def on_round_start(r):
    for m in members():
        pull(m, "{item}", {premium})        # allowance-checked: fails, and logs a breach, if the member withdrew it
def on_raid(camp, victims):                  # new read-only event hook; see below
    for v in victims:
        if v in members():
            move("reserve", v, "{item}", min({payout}, balance("reserve", "{item}")))
'''
```
v1 templates: `club` (dues + treasurer office), `company` (shares = backed currency on the treasury; dividends by vote),
`crowdfund` (escrow + threshold + refund: the projects logic, generalised), `cartel` (members' harvest above a quota is
deducted to the pool and redistributed), `insurance`, `protection` (fee for a guard obligation among members, reusing
`oblige_guard`).

Insurance and cartels need two new read hooks, `on_event(kind, data)` for public events and `on_disable`/`on_raid`. These are
already recommended in design_laws_rights_capabilities.md §1.2.

**Claims on top.** A share is `create_currency(name, backed=True, reserve="reserve:A3")`. `price()` then values it at net asset
value automatically. An agent-issued IOU should be an *unbacked* currency with the issuer as debtor of record, valued at 0 for
scoring. Its social value is visible in transfers, but it cannot inflate Wealth. Free IOU trading at market prices needs an
exchange. Defer that, or leave it to agents (`transfer` + DM).

**What falls out for free.** These need almost no extra code:
- **Standing orders and scheduling.** A one-member association whose `on_round_start` pays from an allowance is a standing order:
  a salary, a subscription or an instalment.
- **Member votes.** These reuse `open_ballot` with the jurisdiction tag (jurisdictions.py:432-437).
- **Inheritance rules.** An `on_death(agent)` hook added to `lawlang.HOOKS`, called from `mortality.disable` before the bequest
  runs (mortality.py:72-121). For contracts it should be limited to the member's escrow and the contract's offices.

More in review 07.

**Determinism and replay.** Hooks run in enactment order across associations. RNG comes only from `law_rng`. State is plain dicts.
Nothing new is needed beyond review 04's run store. The golden tests stay byte-identical with `contracts.enabled: false`. Add one
golden case with it on.

## 4. Enforcement and breach: recommendation

What code can enforce is bounded by what the contract **controls**:
- (a) its treasury;
- (b) escrowed deposits;
- (c) allowances members pre-authorised;
- (d) members' actions that pass through a kernel hook while they remain members (harvest, transfer, post).

For (a)-(d), breach is impossible by construction: the deduction happens, or the pull fails. Promises about *future discretionary
acts* (vote for X, deliver timber next round, don't attack Y) can be breached. The code can only detect breach (a `check(member)`
predicate run at round end that logs a public-to-members `contract_breach`) and apply remedies within (a)-(c): forfeit the deposit,
expel, publish. Everything else is outside the contract:
- **reputation:** breach events are part of a public record, like credit records (credit.py:260);
- **courts:** only where a *jurisdiction* has a law recognising contracts. Add `contracts()`/`breaches()` read functions and a
  library law "Contract Enforcement Act", whose clause lets a judge fine a member found in breach. This is how agents can
  *discover and add* enforcement later;
- **force:** guards, attacks, contract killers, all of which already exist.

**Make enforcement a spec dial for contracts:**
`contracts.enforcement: escrow | escrow_court | word`.
- `escrow` (default) is what is described above.
- `escrow_court` adds the court path above.
- `word` gives contract code no pull or forfeit powers: hooks only report, which is the Handshake Loans analogue.

This mirrors `set_default_consequence` (credit.py:454), which is precedent that the codebase already treats enforcement strength as
a variable. It answers "is it too realistic?" empirically rather than by fiat.

**Do not** add a `court_only` dial for *jurisdiction* law now. It would change the meaning of every on_harvest/on_transfer
deduction and of every library law (all of them assume self-executing code). It is L-sized and confounds every existing
experiment. The existing span (self-executing hooks vs clause + accuse + rule vs lawful_attack) already lets a world be
"kernel-enforced" or "force-backed" through *which laws are in force*. That is better than a global switch, because agents choose
it.

**Exit rights** (state them in the manual, enforce them in the kernel):
- A member can always leave at the end of the round.
- `on_exit` may keep at most the member's escrow.
- Allowances end on exit.
- Debts incurred as loans survive exit, through the credit record.

Jurisdictions differ today. Their `on_exit` can seize anything (jurisdictions.py:932-942), and police can attack leavers. That
difference *is* the compulsion, and it should stay explicit.

## 5. The jurisdiction unification path

**The slogan needs one correction for this code base.** Jurisdictions do not claim camps territorially. Camp rules bind only the
harvester's own jurisdiction (jurisdictions.py:243-257), and a stateless agent harvests unregulated. What actually separates a
polity from an association here is:
1. default membership (`assign_newborn`, `assign_arrival`, :1008-1035; J0 at start);
2. exclusivity (one declared membership);
3. `lawful_attack` on anyone (:288-302);
4. unlimited `on_exit` seizure;
5. kernel rights, sanctions and DM limits over members;
6. Board review and the Fixer.

So "jurisdiction = association + compulsion powers {1-6}".

**Incremental path. Each step is reversible and golden-safe:**
1. Add `kind` to `_new_j` (all existing records become `"polity"`). No behaviour change.
2. Per-law tax destination (§3). Behaviour-identical for polities.
3. Many-to-many association membership; `binds`, `hooks` and `passed` branch on kind.
4. A `contract` column in `lawapi.LAWFNS`; `scope_api` derives the power set from `kind`.
5. Express the polity powers {1-6} as a named power set in that same table, so polity and association differ only by data.
   This is the `Polity` seam from review 01 §4.6, reached from below.

**Stop there.** Step 6 would re-express J0 itself as an association. It breaks:
- J0's `legacy` storage (`k.w["reserve"]`, `k.w["procedures"]`, top-level currencies);
- `LEGACY_ONLY` (loans, par, projects, tribute on J0's reserve);
- the non-jurisdiction world path (`"jur" not in k.w`) that E0-E7 and the golden files depend on;
- media2's official outlet per jurisdiction;
- goals that read the founding jurisdiction (goals.py:1160);
- about 41 `J.`/`"jur" in` sites in kernel.py and actions.py.

The benefit would be one concept instead of two in the code. The agents never see the code.

## 6. Law library and regimes as specs

**What exists:**
- a 72-law library with static classes and effect predicates;
- library access modes (`library_access`, agents.py:267-280; archive gating for Scientists);
- `start_laws`;
- 22 regimes, as bundles of constitution, statutes, rights by class or by lot, spec settings and a description, with inline and
  `base:`-extended definitions;
- regime distributions (`{choice: [...]}`), which already make "every starting condition a spec" true for J0.

**Gaps:**
1. **Founded jurisdictions cannot pick a regime.** They start with "members vote, majority" (jurisdictions.py:554-562) plus up to 5
   charter laws. Add `found {"regime": "constitutional_monarchy"}`, reusing `regimes.constitution_code`/`statute_code`; offices
   go to the founder and members by the regime's rules. **S.** Contract templates should use the *same* library mechanism
   (`library.law(..., category="contract")`), so one browsing UI serves both.
2. **Regimes are named bundles, not dimensions.** To compare systems, express a regime as a vector: procedure (who decides, which
   threshold), veto points (gate, Board scope), franchise, courts (judges, appointment), property (camp rules, leases), money
   (currency, par, loan consequence), press and surveillance, exit (open/closed admission, on_exit seizure). Named regimes then
   become points in that space. Factorial comparisons need the dimensions, and a named bundle confounds them. **M**, mostly data.
3. **Real-country-inspired systems** are feasible only as caricatures. The mechanics can distinguish veto points, franchise,
   courts and money rules. They cannot distinguish history, parties, federal fiscal transfers, constitutional review doctrine or
   bureaucracy. Name them "Westminster-style: fused executive, monarch's assent gate, no judicial review", not after countries. Claims
   about "the UK" from 8 Haiku agents would not survive review.
4. The library docstring says 58 laws; there are 72. Trivial.

## 7. Institution-building goals

Score structure, not labels, from the History object (review 05 §4.2). Use probes only for what History cannot see.

| Goal | Observable signature (all from recorded events and snapshots) |
|---|---|
| Found a company | an association you founded that holds ≥N members other than you at the end, with treasury value ≥V, ≥M treasury payments to non-members over the run, an office held by a non-founder, and existence for ≥R rounds |
| Bank | an association whose currency or loans are held by ≥N non-members; its liabilities exceed its reserves (ratio < 1) at some round without a run (credit.py's `reserve_ratio`, `bank_run` events) |
| Insurer | ≥K payouts made from the pool to members within 1 round of a `disabled` or `raid` event affecting them; pool solvent at the end |
| Cartel | members' harvest at the targeted camp below the pre-cartel average for ≥R rounds, with deductions or transfers into the pool |
| Protection racket | ≥N non-founders paying recurring fees to an association (or to you) whose members hold forts or weapons; payers' attack-victim rate lower than non-payers' |

These go into the goal registry as `score(history, agent, params)`. Each one's `rule` text spells out the signature verbatim, as
review 05 requires.

**Two cautions:**
1. Giving an agent "build a bank" measures instruction-following, not emergence. The emergence question needs goal-free arms in
   which the same signatures are measured as *outcomes* (report.py and observer metrics, not scores).
2. "Vary which institutions exist" is better done by varying **which templates and powers are available**
   (`contracts.templates: [...]`, `contracts.enforcement`) than by planting goals. That is a clean between-condition factor.

## 8. Recommended order, and what to defer

**Prerequisites from reviews 00-05:** the golden safety net (done on main), the rights and law-function registries (merged), and the
goal registry with History (for §7).

1. **Channels (S, ½ day).** Spec dial `channels.create: press | anyone`. Every association gets a channel automatically. Skip
   per-channel rule code: the association *is* the rule.
2. **Associations v1 (M, 4-6 days).** Steps 1-4 of §5, the power set, escrow and pull, per-law tax destinations, the error path
   without the Fixer, 4 templates (club, company, crowdfund, cartel), one golden case, manual section. Off by default.
3. **Enforcement dial + breach record (S-M, 1-2 days).** `escrow | escrow_court | word`; `contracts()`/`breaches()` law reads; the
   "Contract Enforcement Act" library law.
4. **Shares (S, ½ day).** A backed currency on the treasury; dividends template.
5. **Agency (M, 2-3 days).** `authorize {to, scope, limit, rounds}`, checked in `Kernel.move`/`has`. Every use logs
   `{grantor, grantee, auth}`. Merge with the permits design (§4 of the rights doc). `vote` cannot be authorized by default. Fix the
   `invoke` advertisement first.
6. **Regime on `found` + regime dimensions (S-M).**
7. **Institution goals (S each)**, after the goal registry.

**Defer:**
- capital and durable goods. Exception: per-item perishability as an off-by-default dial is S and makes storage and credit
  meaningful, if wanted early;
- identity and aliases;
- coupled ecology;
- free agent IOUs with market pricing, and an exchange;
- a `court_only` dial for jurisdiction law;
- re-expressing J0 as a contract.

**Measure before building past step 3.** Run one pilot with associations and templates on. Count `create_contract`/`join` uses
and template-vs-raw-code share per model tier. If Haiku-class agents found fewer than one association per run, steps 4-7 are
building for agents that will not use them. Spend the effort on prompt affordances (a short "institutions you can set up" menu)
instead.
