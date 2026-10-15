# Review 31.07: rules, courts and the legal profession

*15 Oct 2026. Subsystem design under the shared framework (`00_framework.md`). Chain: propose → decide → enforce → adjudicate.
Every engine claim cites file:line in this worktree (branch `subsistence`). "New" marks code that does not exist yet.*

## 1. Summary

- **Most of the legal machinery already exists.** Proposal, amendment and procedures (`charter/amendment.py`,
  `dispatch/changes/legal.py`), courts v2 with panels, appeals, deadlines and remedies (`charter/courts.py`), clause-based civil
  law (Compensation Act, Graded Remedies, Contract Registry), strict-liability criminal law (Penal Code), a paid prosecutor
  (Prosecution Office), juries, a Court of Appeal, stare decisis, judicial review (Constitutional Court) and a law previewer
  (`charter/lawpreview.py`, the `preview_law` pre-action). Lawyers have no engine role. Clerks of court have none either.
  Representation is impossible: agency covers only `transfer` and `deposit_escrow` (`contracts.py:141-145`).
- **Millbrook had no court at all.** No agent held `judge` (`specs/base.yaml:118`, `judge: null`; Millbrook grants none). Its
  Penal Code sentences by after-hook with no case and no clause (`library.py:2330-2370`). So the Constable, "public prosecutor
  under the Penal Code" (`millbrook.yaml:156`), had no clause to bring a case under and nobody to rule on one. Adjudication was
  empty. Rule changes and self-help were the only legal tools, which is part of why the keeper's code-reading paid off.
- **The silent no-op has five engine causes (§4).** (1) An amendment never touches office records: `do_amend` reloads the code
  but calls no institutions hook (`dispatch/changes/legal.py:263-293`). Enactment does call one (`:228-230`), and so does repeal
  (`:256-258`). (2) Even where a declaration is re-read, existing offices are skipped (`institutions.py:403`) and holders are
  never re-applied (`:478-486`), because `holders` means "first holders" (`:48`). (3) The `intent` is free text. (4) The
  proposal's dry run compares `Kernel.view`, which has no offices, stores or association treasuries (`kernel.py:981-1005`), and
  publishes an empty diff as `preview: []` with no flag (`legal.py:142-148`). (5) `preview_law` cannot preview an amendment as an
  amendment (`lawpreview.py:358-375`, `:190`).
- **Fix it in three layers.** Engine: reconcile offices on amendment and refuse a holders edit loudly. Add a public `law_effect`
  report of what every legal act changed, with an `inert` flag. Teach the previewer amendments and the enactment diff. Template:
  a declarative `expects` block of postconditions that the engine checks after enactment, failing loudly. Roles: lawyers and a
  clerk whose job is to run that preview and certify it.
- **Per regime**, the four regimes differ mainly in four things: who may file and who rules; who pays counsel (the market, the
  firms, the state, the members by rotation); whether contracts are enforced by escrow, by arbitration or by courts; and how hard
  the bench is to pack.

## 2. The rules chain and what each regime makes of each stage

| Stage | Engine today | Merchant | Private | State | Cooperative |
|---|---|---|---|---|---|
| **Propose** | `propose`/`amend` need the `propose` right (`actions.py:689-690`); 3-round dry run if the polity holds `dry_run` (`actions.py:700-707`, `powers.py:80`) | any citizen; lawyers draft for pay | council members and the firms' counsel | the Executive and its Law Office (drafts); councillors | any member, at the general meeting |
| **Decide** | the procedure law of the class and rank (`Simple Majority`, `Supermajority`, `Quorum`, `Referendum`, `Bicameral`, `Executive Assent with Override`) | weak assembly: Quorum Procedure, all citizens, quorum 0.5 (most proposals fail for want of a quorum) | council of property holders: Simple Majority over `J0.council`, seats elected by a `freeholder` right | council by majority, then the Executive's assent (Executive Assent with Override, override 2/3) | general meeting: Quorum Procedure over `vote`, constitution under Entrenched Constitution (2/3) |
| **Enforce** | automatic hooks (before/after on routed primitives), or penalties run by a ruling (`courts.py:279-289`); law `move`/`fine` | escrow and reputation (`contracts.enforcement: escrow`/`word`); self-help | escrow plus courts (`escrow_court`, `breach_cases: true`) | Penal Code (automatic) plus a salaried prosecutor and a Watch (force designer) | members' sanctions by meeting vote; escrow in the co-op |
| **Adjudicate** | cases under clauses (`accuse`, `respond`, `rule`, `appeal`); judges = holders of `judge` filtered by court rule `judges` (`courts.py:123-131`, `:163-189`) | private arbitrators named in contracts; one elected Magistrate for torts | appointed Judge (council), council as appeal bench | professional bench appointed by the Executive, Court of Appeal, Constitutional Court; Public Defender | jury by lot (Jury Panel), a rotating Moderator as appeal |

Who owns each stage is the regime: **Merchant** privatises adjudication, **Private** sells access to it, **State** monopolises
all four stages, **Cooperative** spreads them by lot.

## 3. The regimes

The legal subsystem takes about 5-7 of the world's ~24 seats, each with a second affiliation from another subsystem (framework
§10). Opus goes in seats where a decision has to read code: the senior lawyer and the chief judge or arbitrator. Haiku goes in
clerks and jurors, with one swapped seat per world.

Shared across regimes (and offered to the integrator once):
- **The statute book** = `k.w["laws"]`: code, intent, status, versions and patches. Anyone reads it with `read_law`
  (`action_registry.py:478-480`). The engine keeps the history (`do_amend` appends to `patches`, `legal.py:267-268`), and no
  agent can amend it. That entrenchment is good and is kept.
- **Case files** = `k.w["cases"]`: accuser, accused, clause, evidence ids, counter-evidence, votes, verdict, reason, remedy. All
  public events (`courts.py:186-188`). Laws may read only the cases under their own account's clauses (`courts.py:35-37`).
- **The court's notices** go through the gazette, plus the shared notice board (integrator). **No dedicated legal channel in any
  regime by default.** Filings and rulings are already public events. Counsel-client work is DMs (2 parties). A court channel
  would duplicate the gazette. One justified exception is listed under Private.

### 3.1 Merchant: weak assembly, private arbitration

**Institutions.**

| Part | Assembly of Citizens (J0) | Arbitrators' Hall (association) | Magistrate (J0 office) |
|---|---|---|---|
| Purpose | the few public rules (levy, torts, the hall's licence) | sell dispute resolution to contracting parties | public torts between people with no contract |
| Assets | J0 treasury (small) | hall treasury (fees), its arbitration-clause template, its award register (public state) | none; fees |
| Roles | all citizens vote; no officers but the Magistrate | 2 arbitrators (offices `A?.arbiter`), founder = senior arbitrator | 1 Magistrate, elected, term 8 |
| Contracts | none run by default | the **Arbitration Agreement** (new contract template): escrowed deposits; an award `pull`s from the loser's escrow to the winner; fee to the hall | fee per case (filing fee by `after_open_case`) |
| Rules | Quorum Procedure (`library.py:3060`), quorum 0.5 | hall code, procedure `founder` | Graded Remedies (clause `tort`, `library.py:3246-3278`), Precedent Register |
| Records | statute book | award register (public), arbitration clauses in each contract's code | case files, precedent register |
| Accountability | none above the assembly | reputation (awards public); parties choose another hall next time | re-election; Court of Appeal absent |
| Change | assembly amends | founder changes code; arbitrators quit or are hired | assembly sets fees and remedies |
| Capture | low prize (the state is weak) | an arbitrator paid by a repeat player (the big trader) rules for it; parties cannot appeal | Magistrate bribed (no recusal rule) |
| Failure | quorum fails (nothing passes, so the world keeps its start laws) | escrow too small to cover the award (the award is capped at what was deposited); the hall dissolves | backlog: cases dismissed at deadline 3 (`courts.py:291-300`) |

**Role cards.**
- *Senior Arbitrator* (Opus). Purpose: decide disputes under the contracts that name the hall. Routine: nothing (escrow sits).
  Decisions: (1) award or dismiss a pending dispute (`invoke award`); (2) set the hall's fee (`propose_contract_change`); (3) take
  or refuse a repeat client. Answers to its clients' reputation. Sees the contracts it is named in, their escrow and breach
  records. Pay: the fee from each escrow.
- *Arbitrator* (Sonnet): the same, junior, one decision fewer.
- *Lawyer, independent* (Opus, 1; Sonnet, 1). Purpose: draft contracts and laws for clients, preview them, argue disputes. Routine:
  none. Decisions: (1) take a client and fee (DM, transfer); (2) draft and `preview_law` a contract or law (3 previews per round,
  `lawpreview.py:65`); (3) file or answer on a client's behalf (new: counsel agency, §8). Pay: per job, by transfer, or a retainer
  as a standing order (`start.wages` with an agent employer, `start.py:29`).
- *Magistrate* (Sonnet). Rules on `tort` cases (`rule {case, verdict, remedy}`). Pay: filing fees.
- *Clerk of the Hall* (Haiku). Keeps the award register, certifies that an award was paid. Pay: a wage from the hall.

**Change processes.** Arbitrators enter and leave by the hall's code (join/leave/expel). Clients switch forum by writing another
hall into their next contract. The assembly can license or ban arbitration, which is the entrenchment dial: is private
arbitration protected by a constitution-rank clause?

**Failure modes.** No public enforcement of awards beyond escrow, so a party who deposits too little can walk away and keep only
a public breach record (the `word` dial, `contracts.py:41-50`). Agents with nothing at stake ignore the law.

### 3.2 Private: council of property holders, contract law

**Institutions.**

| Part | Council (J0) | Court of Contracts (J0 office: Judge; Clerk of the Court) | Law firm(s) (associations) |
|---|---|---|---|
| Purpose | rules that protect property and contracts | hear breach and tort cases; enforce awards | sell counsel |
| Assets | J0 treasury (levy income) | the bench (`judge` + `J0.judge`), the docket | treasury, retainers, staff |
| Roles | 3-5 councillors elected by `freeholder` holders | Judge (appointed by the council, term 12); Clerk (appointed by the Judge) | Senior Partner (Opus), associate (Sonnet) |
| Contracts | levy | Judge's salary: J0 wage, 4/round; filing fee 2 to treasury | **retainers** from the firms (standing order each round) and per-case fees |
| Rules | Simple Majority over `J0.council`; Entrenched Constitution for procedure | Contract Enforcement Act MODE court (`library.py:1184-1230`); Graded Remedies; Contract Registry; Court of Appeal = the council (APPEAL_RIGHT `J0.council`) | firm's own code |
| Records | statute book | case files, registry of agreements, precedent register | client files (DMs; a firm channel is not justified at 2 members) |
| Accountability | election by freeholders | removal by 2/3 of the council (Recall-style ballot on `J0.judge`); appeal | partners' own procedure |
| Change | majority | the council can amend the court rules (`set_court_rule`, panel 1-9) | partners hire, fire, merge |
| Capture | property holders write the franchise | **the firms retain the best lawyer; the Judge is appointed by a council of their owners**; the appeal bench *is* the council | one firm represents both sides (conflict) |
| Failure | a council of 3 deadlocks or is bought | the Judge sits as a party: no recusal check in `actions._rule` (`actions.py:1132-1150`) | the retainer lapses when a firm's treasury runs dry |

One channel is justified here, as a **pull board**: the `registry` (readers all, writers the Clerk). Under the Contract Registry
an agreement counts in court only once it is registered and posted. That is business valid only there, and it reaches the
public. The integrator may fold it into the shared notice board.

**Role cards.**
- *Judge* (Opus). Purpose: decide cases on the docket. Routine: open cases past the deadline are dismissed automatically.
  Decisions: (1) rule guilty or not guilty with a remedy (damages within MAX_DAMAGES); (2) recuse (new: Recusal Act); (3) refer a
  case to the council on appeal. Answers to the council (removal). Sees: the docket (pushed: `notify` on filing,
  `courts.py:183-184`) and the evidence. Pay: J0 wage.
- *Clerk of the Court* (Haiku). Routine: Contract Registry entries are confirmed by the parties. Decisions: (1) certify (or
  refuse) a registration (new: the clerk's certification, §8); (2) post the docket summary; (3) run `preview_law` for any
  councillor who asks and post the result. Pay: wage. Real power: an uncertified agreement is not enforceable.
- *Senior Partner* (Opus). Decisions: (1) take a retainer, or refuse a rival firm's adversary; (2) draft and preview; (3)
  represent. Pay: retainers from the firms (standing orders).
- *Councillors* (one Opus, two Sonnet, also owners in the food/money subsystems): propose and vote, appoint and remove the Judge.

### 3.3 State: council and executive, strong enforcement

**Institutions.**

| Part | Council + Executive (J0) | Ministry of Justice (J0 offices) | Watch (force designer) |
|---|---|---|---|
| Purpose | make law, appoint officers | prosecute, judge, defend, draft | arrest and enforce |
| Assets | treasury (taxes) | salaries; the docket; the Law Office's drafts | armoury |
| Roles | Council of 5; the Executive (`president`) | **Prosecutor** (Prosecution Office), **2 Judges** + **Chief Judge** on appeal, **Public Defender**, **Clerk of Laws** (drafts and previews every bill), **Clerk of the Court** | Captain, watchmen |
| Contracts | salaries | Prosecutor: salary 3 + REWARD 3 per conviction (`library.py:2372-2402`); Judges: salary 4; Defender: salary 3 | wages |
| Rules | Executive Assent with Override (`library.py:3027`); Entrenched Constitution; Constitutional Court (`library.py:1926-1978`, the Chief Judge as justice) | Penal Code with clauses (new variant: offences as clauses, so they go to trial), Court of Appeal (`library.py:3206-3244`), Stare Decisis, Administrative Procedure Act (`library.py:3090-3134`) | the Watch's orders |
| Records | statute book; Law Office opinions (public state) | docket (Prosecution Office `public.docket`), precedent register, appeals register | arrest log |
| Accountability | council elected; Executive elected | judges appointed by the Executive with council consent, term 12; removal by 2/3 of the council; the Prosecutor serves at the Executive's pleasure | Executive |
| Change | procedure, rank | court rules by statute; the bench's size by statute (packing route) | — |
| Capture | the Executive controls the Prosecutor (selective prosecution) and nominates judges (packing: raise `panel` and add loyal seats) | conviction bonuses create false charges; the Defender is paid by the prosecuting state | the Watch enforces against critics |
| Failure | the Executive vetoes the budget and courts go unpaid | appeal backlog (deadline 3); Stare Decisis locks in early bad rulings | — |

**Role cards.**
- *Prosecutor* (Opus, also a Watch officer: the conflict is deliberate). Routine: the Penal Code's automatic sentences still run.
  Decisions: (1) charge or not (`accuse` under a clause); (2) drop a case (new: `withdraw_case`; today a case can only lapse); (3)
  plea (offer a fine for no trial, via DM). Answers to the Executive. Pay: salary plus per-conviction reward.
- *Judge* ×2 (Sonnet, one swapped to Opus). Chief Judge (Opus): appeals and constitutional review (`strike_down`).
- *Public Defender* (Sonnet). Represents any accused who asks (new: counsel agency). Pay: salary from the state that prosecutes.
- *Clerk of Laws* (Haiku, swapped seat: one world gives it to Opus). Routine: every draft proposed in the council gets a preview
  posted (new: `law_effect` and `expects`; today the clerk can call `preview_law`). Decisions: (1) certify a bill as "does what
  its intent says"; (2) refuse certification. A bill without certification is not refused (a dial), but it is marked.
- *Clerk of the Court* (Haiku): docket, assignment of judges (new: an `assign` court rule), publication of rulings.

### 3.4 Cooperative: general meetings, rotating offices

**Institutions.**

| Part | General Meeting (J0 = the co-op) | Jury and Moderator | Advocates by lot |
|---|---|---|---|
| Purpose | members make every rule | members judge members | every member gets counsel |
| Assets | the commons treasury | none | none |
| Roles | all members vote; Moderator (lot, term 4) chairs and is the appeal | Jury Panel: 3 jurors by lot every 5 rounds (`library.py:3164-3204`) | 2 Advocates by lot, term 4 (offices with `succession: {rule: lot}`) |
| Contracts | members' dues | jurors paid 1/round while seated (new: a duty stipend, a wage from the treasury) | Advocates paid 1/round |
| Rules | Quorum Procedure; Entrenched Constitution (2/3); Commons Charter | Jury Panel; Graded Remedies; Precedent Register | Recusal Act (new) |
| Records | minutes = the gazette, statute book | case files, panels (`public.panels`) | none private |
| Accountability | everyone | rotation | rotation |
| Change | meeting votes anything not entrenched | jury size by statute | — |
| Capture | a bloc that turns out every time; agenda-setting by the Moderator | lot favours no one, but a 3-person jury can be bribed cheaply | a lot-drawn Advocate who cannot read code |
| Failure | no quorum; free-riding (nobody previews) | a Haiku jury rules at random | competence collapse: nobody spots the no-op |

**Role cards.** *Moderator* (lot; tier by seat): decides the agenda (`gate` in a chair's ballot), the appeal. *Juror*
(Haiku/Sonnet): one decision, the verdict and remedy. *Advocate* (lot): represent; preview drafts for the meeting. One Opus
member is deliberately placed in the cast so the "best lawyer" emerges informally. That measures informal expertise as power.

## 4. The silent-no-op problem

### 4.1 What happened (Millbrook forks)

The council (Simple Majority over `J0.council`, `millbrook.yaml:57-59`) passed an amendment to J0's Offices Act. The Act is
instantiated from the `start:` block (`start.py:258-277`), whose `offices` constant declared `keeper: {holders: [Elspeth], ...}`.
The amendment changed that `holders` list and wrote "the keeper's hoard is seized" in the `intent`. The keeper kept the office,
the store control and the hoard. She read the code (`read_law`) and exploited it.

### 4.2 Exact cause in the engine

1. **An amendment does not reach office records.** `Kernel.enact` sends an amendment draft to `enact_amendment`
   (`kernel.py:827-834`, `amendment.py:111-131`), which applies the `amend` primitive. `do_amend` swaps the code, reloads and
   rebinds it, logs `amended` with the text diff, and returns (`dispatch/changes/legal.py:263-293`). It never calls
   `institutions.on_law_in_force` or `on_law_repealed`. Only `do_enact` (`legal.py:228-230`) and `do_repeal` (`:256-258`) do.
   `on_enact` is not re-run on amendment either, so even a seizure written in `on_enact` of the amended code would not run.
   **Every change to an Offices Act by amendment is a no-op on offices: holders, powers, controls, duties, term, succession, and
   even newly added offices.**
2. **Re-reading a declaration does not reseat anyway.** `declare_offices` skips any office the institution already has
   (`institutions.py:403`) and grants the declared holders only for new offices (`:417-427`). The replace path for associations
   (`_retire` → `on_law_repealed(replaced_by)`, `contracts.py:834`; `institutions.py:478-486`) updates title, powers, seats,
   term, grants, succession, duties and controls, but never holders. That is by design: `holders` is "its first holders"
   (`institutions.py:48`). Holding is the right `<iid>.<office>`, changed only by `grant_right`/`revoke_right` (`on_right`,
   `:432-453`). So the working law is `revoke("Elspeth", "J0.keeper")`, which triggers a vacancy and the council's election
   (succession on).
3. **Intent is not code.** `intent` is a required string constant (`lawlang.py:90`). Nothing executes or checks it.
4. **The check that ran saw nothing and said nothing.** The proposal-time dry run applied the amendment on a copy
   (`actions.py:700-707` → `Kernel.dry_run`, `kernel.py:1106-1124`). It compares `Kernel.view()` (`kernel.py:981-1005`): agents'
   holdings and rights, reserve, currencies, procedures, camps, laws and module rules. It has no office records, no store
   contents, no association treasuries, no clauses and no court rules. The diff was empty and was published as `"preview": []`
   in the `proposal` event (`legal.py:142-148`). An empty preview carries no warning. Had the law revoked the right, the diff
   would have read `Elspeth loses right J0.keeper` (`kernel.py:1092-1095`).
5. **The lawyer's tool could not have checked it.** `preview_law` proposes the draft as a *new* law (`lawpreview.py:358-375`,
   `A.act(k, aid, "propose", ...)`). `amends` is used only to list dependents (`lawpreview.py:190`). Run as a new Offices Act,
   `declare_offices` again skips `keeper` (it exists). The window's per-round diff is taken after enactment (`lawpreview.py:435`),
   so what the enactment itself changes is never shown as a diff.
6. **A related silent path.** A law's `move` returns False when the balance is short or a hook blocks it (`kernel.py:337-345`,
   `:636-637`), with nothing logged for the law's authors. A seizure that moves more than the target holds does nothing.

### 4.3 Proposed fix: laws that work or fail loudly

**E1. Reconcile offices on amendment (engine, S-M).** In `do_amend`, after a successful reload, call a new
`institutions.on_law_amended(k, lid, old_code)`. It diffs the old and new declarations, then:
- adds new offices (`declare_offices` path);
- abolishes removed ones (the `on_law_repealed` per-office path);
- applies changed fields to existing offices (as `:478-486`);
- for changed `holders`, takes one of two choices (a spec dial `institutions.reseat`):
  - `refuse` (default) **fails the amendment at proposal**: "offices.keeper.holders only seats an office when it is first
    declared; to change who holds J0.keeper, revoke and grant the right J0.keeper (or call reseat)". This goes in
    `amendment_draft` (`amendment.py:82-91`), so the proposer sees it before any vote.
  - `apply` reseats: revoke the right from holders no longer listed (via "amendment", a vacancy with that cause) and grant it to
    the new ones.

  Also add a law function `reseat(office, [agents])` (new lawapi row, "rights" family) that does the same in one call.

**E2. Report what every legal act changed (engine, M).** Extend `Kernel.view` with `offices` (holders, controls, powers per
office), store holdings, institution treasuries, clauses, court rules and defined actions. Wrap `do_enact`, `do_amend` and
`do_repeal` in before/after views. Log a public `law_effect` event with the diff and two flags: `inert` (empty diff *and* no
hooks, clauses or actions installed or changed) and `failed_calls` (law calls that returned False or refused: E4). The proposal
event's preview gets the same `inert` flag. Agents see `law_effect` in their state when they voted on, proposed or are named in
the law (framework §12: they use only what they see).

**E3. Preview amendments as amendments (engine, S).** In `preview_law`, when `amends` is given (or the code's title matches a
law in force and the agent says so), create the draft with `amendment.amendment_draft` and enact it with `enact_amendment`
inside the transaction. Add an "At enactment:" diff line taken around `_enact` (`lawpreview.py:411-430`). Add the `amends`
argument to the action's documentation (`action_registry.py:485-489`).

**E4. Failed law calls are events (engine, S).** `move`, `fine`, `grant`, `revoke` and `reseat` called from a law log
`law_call_failed {law, fn, args, reason}`, visible to the law's jurisdiction members and shown in previews.

**T1. Expectations: a law states its effect, the engine checks it (template plus engine, M).** A law may declare a constant:

```python
expects = [{"office": "J0.keeper", "holders": ["Osric"]},
           {"holding": "Elspeth", "item": "food", "at_most": 0},
           {"store": "S1", "item": "food", "at_least": 120}]
```

The engine checks it after enactment or amendment, in the dry run, in `preview_law` and for real. A failed expectation in the
dry run refuses the proposal ("your law does not do what it expects: J0.keeper is held by Elspeth"). For real, a failure is a
public `law_expectation_failed` event (fail loudly, never roll back: the law is in force and everyone is told). This is the
machine-checkable half of "intent". Lawyers write `expects`; councils can demand it with a procedure law (`before_propose`
blocks drafts without `expects`), which is a regime dial.

**R1. The human (agent) half: lawyers and clerks.** The Clerk of Laws (State) or Clerk of the Court (Private), or any lawyer,
runs `preview_law` on each bill and posts the effect summary. Their role cards make "read `law_effect` and compare it with the
intent" an explicit decision. With E2 and E3 in place, the Millbrook amendment previews as `At enactment: no change; inert`. Any
lawyer who reads it catches the no-op, and the keeper loses her edge unless she is the only one who reads.

**What should *not* be done:** auto-deriving effects from the intent text with an LLM. It makes the law ambiguous, and it hides
the very skill (reading code) that the lawyer role exists to measure.

## 5. Contract enforcement and breach

Interface with the standing-contract template (money/labour designer). I assume that template is an association contract
(contract code under `contracts.enabled`) with escrow and allowances, so that `breach()` is available to it. `breach()` is a
contract-law function for its own members only (`contracts.py:1240-1250`).

1. **Detect.** Each round's automatic delivery (wage, food, rent) is checked by the template. A short delivery calls
   `breach(member, clause, remedy, victim)` with the clause name of the term broken (e.g. `"deliver_food"`). This is public under
   `word`, and actionable under `escrow_court` (`contracts.py:41-50`).
2. **Choose a forum** with a new template parameter `FORUM`:
   - `"escrow"`: the contract's own code settles the breach at once (`forfeit`/`pull` from the breacher's escrow to the victim).
     No court. Merchant default.
   - `"arbiter:<office or agent>"`: the contract defines an office `arbiter` (`define_action`, contract offices
     `contracts.py:68-73`) with `award(member, qty, reason)`, bounded by the escrow. The arbiter is paid ARB_FEE from the
     parties' deposits. Merchant and Cooperative.
   - `"court"`: spec `contracts.enforcement: escrow_court` and `breach_cases: true`. The breach opens a case automatically
     (`file_breach_case`, `contracts.py:1404-1424`) under the first in-force clause named `breach_of_contract`
     (`breach_clause`, `:1384-1401`), i.e. the Contract Enforcement Act's (`library.py:1184-1230`), with source `contract`. The
     judge rules, and the Act's penalty fines FINE per breach, to the victim. Private and State.
3. **Remedy gap.** The Contract Enforcement Act's penalty takes `(accused, accuser)` (`library.py:1221`), so the judge's remedy is
   ignored. Add a **Graded Contract Enforcement** variant whose penalty takes `(accused, accuser, remedy)` (courts pass the
   remedy by arity, `courts.py:267-289`): damages up to the contract's declared `DAMAGES_CAP`, paid first from escrow, then from
   holdings.
4. **Cancellation and notice.** Cancel-with-notice is the template's. A *wrongful* cancellation is a breach under the same path.
5. **Retainers are standing contracts too.** A lawyer's retainer is the same template (employer = client, worker = lawyer,
   item = penny), with a duty clause `"represent"`. A lawyer who takes a retainer from the opposing party breaches it, and the
   client can sue: conflict of interest becomes enforceable rather than a prompt rule.
6. **Engine gap.** A contract law cannot read the J0 cases its members are party to (`courts.py:35-37`). The retainer cannot
   condition pay on "per case represented" without a new read (`cases_of(agent)`, public data, S).

## 6. Cross-link interfaces

| With | We need | We give |
|---|---|---|
| **Records / information** | events as evidence (`accuse` cites event ids the accuser saw, `actions.py:1095-1101`); registers (contract registry, office holders) and ledgers (store draws, Granary Ration `public.draws`) as citable public state; the archive's version history | the statute book, case files, precedent register and docket as records; rulings as news |
| **Force** | the Watch to execute what money cannot (detention = `limit_actions`, disarmament); `lawful_attack` licences from a ruling | warrants: a guilty ruling under an "arrest" clause makes the attack lawful for N rounds (penalty calls `lawful_attack`) |
| **Money / labour** | the standing-contract template's `breach()` and escrow; wages for judges, clerks, prosecutors, defenders; a filing-fee item | fines and damages (`fine`, `move`), filing fees, retainers; Contract Enforcement as the backstop that makes credit and wages trustworthy |
| **Food** | the granary's draw book and controls (Granary Ration) as evidence; the keeper's office as an object of law | the legal path to remove a keeper (revoke the office right, then succession) and the seizure path (`move` from holdings, `expects`) |
| **Media** | outlets to publish rulings and the Clerk's previews | defamation clause (`library.py:839`) |
| **Offices (all)** | `institutions.reseat` dial and `law_effect` (§4.3) | the recall and removal procedures each designer's officers rely on |

## 7. Spec sketch: Private regime (`start:` with real keys)

Keys used exist today unless marked `# NEW`. Seat names are placeholders the integrator replaces.

```yaml
law: {v2: true}
institutions: {unified: true, grants: true, succession: true, office_control: true}
contracts: {enabled: true, enforcement: escrow_court, breach_cases: true, max_laws: 4}
regime:
  base: null
  name: private_rules
  constitution: assembly
  laws:
    - template: Simple Majority Procedure
      params: {ELECTORATE: J0.council, CLASSES: [ordinary, structural], RANKS: [statute]}
    - template: Supermajority Procedure          # procedure and constitution: two thirds of the council
      params: {ELECTORATE: J0.council, CLASSES: [procedural], RANKS: [constitution]}
start:
  rights:
    Hale: [judge]                                # the Judge also holds kernel `judge`; the Bench Act keeps them in step
    Ashworth: [freeholder, vote, propose]        # the property franchise (a new right is created at round 0)
    Pell: [freeholder, vote, propose]
    Quill: [freeholder, vote, propose]
    Marsh: [freeholder]
  institutions:
    - id: J0
      offices:
        council:
          title: Councillor
          holders: [Ashworth, Pell, Quill]
          seats: 3
          term: 8
          term_calendar: true
          powers: [speak]
          duties: "Decide the laws by majority; appoint and remove the Judge; hear appeals."
          succession: {rule: election, electorate: freeholder}
        judge:
          title: Judge of the Court of Contracts
          holders: [Hale]
          term: 12
          duties: "Rule on the cases on the docket within their deadline; give reasons; recuse when you are a party."
          succession: {rule: election, electorate: J0.council}
        clerk:
          title: Clerk of the Court
          holders: [Tibbs]
          duties: "Keep the registry of agreements, certify registrations, post the docket, and preview every bill for the council."
          succession: {rule: election, electorate: J0.judge}
      treasury: {penny: 200}
    - id: A1
      name: Pell & Quill, Counsel
      founder: Marsh
      members: [Dace]
      admission: closed
      procedure: founder
      charter: "A law firm: drafts contracts and laws, previews them, and represents clients for retainers and fees."
      offices:
        partner: {title: Senior Partner, holders: [Marsh], powers: [speak], controls: [treasury]}
      treasury: {penny: 40}
  wages:
    - {employer: J0, worker: Hale, item: penny, qty: 4}          # NEW: start.wages takes an association or agent employer (start.py:29); J0 as employer to build or use a J0 standing order
    - {employer: J0, worker: Tibbs, item: penny, qty: 2}
    - {employer: A2, worker: Marsh, item: penny, qty: 3}         # the supermarket's retainer (A2 from the food designer)
    - {employer: A3, worker: Marsh, item: penny, qty: 3}         # the bank's retainer: one lawyer, two big clients
  laws:
    - template: Contract Enforcement Act
      params: {MODE: court, SANCTION: fine, ITEM: penny, FINE: 5, PAY: victim}
    - template: Graded Remedies
      params: {CLAUSE: tort, DAMAGES_ITEM: penny, MAX_DAMAGES: 20, DEFAULT: 2}
    - template: Contract Registry
      params: {CLAUSE: registered_agreement, DAMAGES_ITEM: penny, DAMAGES: 5}
    - template: Court of Appeal                  # the council is the appeal bench
      params: {APPEAL_RIGHT: J0.council, BENCH: 3, WINDOW: 2, PANEL: 3}
    - template: Precedent Register
      params: {SHOW: 3}
    - code: |                                    # Bench Act: expressible today; NEW as a library template
        title = "Bench Act"
        intent = "Only the holder of J0.judge judges at first instance; whoever holds the office holds the judge right, and nobody else."
        OFFICE = "J0.judge"
        def sync():
            for a in holders("judge"):
                if not has(a, OFFICE):
                    revoke(a, "judge")
            for a in holders(OFFICE):
                if not has(a, "judge"):
                    grant(a, "judge")
        def on_enact():
            set_court_rule("judges", OFFICE)
            sync()
        def on_round_start(r):
            sync()
    - template: Recusal Act                      # NEW (S): before_rule blocks a judge who is accuser or accused, or who
      params: {LOOKBACK: 5, GIFT_LIMIT: 5}       #   received GIFT_LIMIT or more from a party in the last LOOKBACK rounds
```

Notes. (a) `Court of Appeal`'s `seat()` grants APPEAL_RIGHT to the BENCH_CLASS pool only when nobody holds it; with
`J0.council` already held it seats nobody new and just sets the court rules (`library.py:3214-3232`). That is what we want, but it
should be confirmed by a dry run. (b) The Bench Act syncs once a round, so a removed judge keeps `judge` until the next round
start. An `after_revoke_right` hook would close that gap if it is routed (to check). (c) The State variant swaps the procedures
for Executive Assent with Override and adds the Prosecution Office (`PROSECUTOR_RIGHT: J0.prosecutor`, `PROSECUTOR_CLASS: none`,
`REWARD_ITEM: penny`, `REWARD: 3`), Constitutional Court (`JUSTICE_RIGHT: J0.chief_judge`) and a clause-based Penal Code (NEW
variant).

## 8. Code needed

| # | What | Kind | Size |
|---|---|---|---|
| 1 | `on_law_amended`: reconcile office records on amendment; `institutions.reseat` dial (`refuse` at proposal / `apply`) | engine (`legal.py` do_amend, `institutions.py`, `amendment.py`) | M |
| 2 | `reseat(office, agents)` law function | engine (lawapi row) | S |
| 3 | `Kernel.view` gains offices, stores, institution treasuries, clauses, court rules; public `law_effect` event with `inert` flag on enact, amend and repeal | engine | M |
| 4 | `preview_law` runs amendments as amendments; shows the enactment diff; documents `amends` | engine (`lawpreview.py`, registry doc) | S |
| 5 | `law_call_failed` events for failed `move`/`fine`/`grant`/`revoke` from law code | engine | S |
| 6 | `expects` postconditions checked in dry run, preview and enactment (`law_expectation_failed`) | engine + lawlang constant | M |
| 7 | **Counsel agency**: `authorize` rows for `accuse`, `respond`, `appeal`, `propose`, `amend` (acting *for* the client: the client is the party and the victim); `counsel` shown on the case | engine (`contracts.AGENCY_ACTIONS`, actions) | M |
| 8 | `cases_of(agent)` public read for any law (retainers per case) | engine (courts law_api) | S |
| 9 | `withdraw_case` (accuser or prosecutor drops a case; plea deals) | engine (routed primitive) | S |
| 10 | Recusal Act (before_rule: party or recent payer) | template | S |
| 11 | Bench Act (office ↔ `judge` right; `judges` court rule) | template | S |
| 12 | Graded Contract Enforcement (remedy-reading breach penalty, escrow first) | template | S |
| 13 | Arbitration Agreement (contract template: deposits, `arbiter` office, `award`, fee) | contract template | M |
| 14 | Penal Code (clauses variant): offences tried, not auto-sentenced; the auto variant kept for "strong enforcement" | template | S |
| 15 | Clerk's certification: Contract Registry variant where the `clerk` office confirms, and Bill Certification (clerk posts a preview and certify/refuse to public state; procedure dial may require it) | template | S |
| 16 | Duty stipends (jurors and advocates paid while seated) | template (round hook paying holders) | S |
| 17 | Metrics in §9 | analysis | M |

Sizes: S ≤1 day, M 2-4 days. Items 1-6 are the no-op fix (about 2 engineer-weeks); items 7-16 are the profession.

## 9. Dry-run checks and metrics

**Checks (scripted bots, 3 rounds of zero attention, framework §11):**
1. Courts exist: at least one live holder of `judge` per regime, and at least one clause in force per filing path
   (`k.w["clauses"]`). Millbrook fails this today.
2. A scripted short delivery under the standing contract opens a case (Private, State) or an arbiter award (Merchant), and the
   remedy moves goods.
3. A case left alone is dismissed at its deadline; an appealable ruling becomes final after the window (`courts.py:291-318`).
4. **The Millbrook regression:** an amendment that edits an Offices Act's `holders` is refused with the reseat message (dial
   `refuse`), or reseats (dial `apply`). Its preview reads `At enactment: J0.keeper: holders Elspeth -> Osric` or the refusal. A
   law with only intent text previews as `inert`.
5. Every legal seat appears in its holder's state (duties, docket, retainers), per framework §12.

**Metrics (from the event log):**
- **Inert laws**: count and share of enacted laws and amendments with `law_effect.inert`, and of `law_expectation_failed` and
  `law_call_failed`. Who proposed them, and who exploited them (actions within 3 rounds by an agent who `read_law` it).
- **Preview use**: `preview_law` calls per bill, by role (lawyer, clerk, councillor, target). Share of bills passed with no
  preview by anyone. Share of inert bills caught (amended or withdrawn after a preview).
- **Cases**: filed, decided, dismissed by deadline, appealed, reversed; time to ruling; source (agent, contract, prosecutor).
  Conviction rate by accused's wealth tercile and by whether they had counsel.
- **Lawyer use**: retainers and fees paid, cases with counsel, drafts by lawyers that passed, clients per lawyer, and conflicts
  (a lawyer paid by both sides).
- **Legal vs extra-legal action**: for each dispute (a breach, theft, an office capture), whether the response was a case or
  amendment (legal) or attack, self-help seizure or exit (extra-legal), and its share by regime.
- **Capture**: judge-party payments within 5 rounds of a ruling; selective prosecution (prosecution rate given the same
  automatic Penal Code record, by bloc); bench changes (panel size, new judicial seats) within 3 rounds of an adverse ruling
  (packing).
- **Role adherence**: judges ruling within deadline; clerks posting previews; arbiters issuing awards.

## 10. Open questions and honest critique

1. **Do LLM lawyers actually read code?** Millbrook says one Opus did, adversarially. Whether a hired lawyer does it for a client
   is untested. The `inert` flag may make lawyers redundant for the easy cases. That is acceptable: the hard cases (laws that do
   *something*, but not what was intended) remain theirs, and `expects` cannot be written for effects nobody anticipated.
2. **`expects` can be gamed.** A drafter writes weak expectations. The defence is a clerk or lawyer reading them, so the human
   layer stays necessary.
3. **Reseat semantics are a value choice.** `refuse` keeps "holding = right" clean and forces explicit revocation. `apply` is
   friendlier but makes an Offices Act edit a power grab with no vacancy procedure. I recommend `refuse` by default, plus the
   `reseat()` function.
4. **Strict-liability enforcement crowds out courts.** The Penal Code sentences with perfect detection (its own doc,
   `library.py:2368-2370`). Where it is on, courts only handle torts and contracts. The State regime keeps it on purpose; the
   others should use the clause variant or no one will file.
5. **Judges as a bottleneck.** 3 rulings per judge per round, deadline 3. Twenty-four agents with standing contracts may produce
   more breaches than one judge can hear. That would turn the court into a dismissal machine, which needs a dry-run measurement
   before the panel and deadline are set.
6. **No hearing.** A judge may rule before the accused responds (review 11 §2.1). An "answer window" court rule (S) would make
   representation matter. Without it, a lawyer's value at trial is small.
7. **Counsel agency widens the surface.** A lawyer authorised to `propose` or `amend` for a client becomes a proxy legislator. Is
   that intended (Private: yes; Cooperative: no)? It should be a per-regime spec list.
8. **Overlaps with other designers.** The Watch (force) executes rulings. Records (information) owns registers and the archive.
   Money owns fees. Food owns the keeper. The integrator must ensure the standing-contract template calls `breach()` with a
   victim, or nothing reaches a court.
9. **Channel budget.** The design adds at most one channel (Private's registry board) and relies on the gazette. If the gazette
   is clipped from agents' state (Millbrook's clipped state), rulings go unseen. Push the docket into parties' state instead.

### Engine facts that bear on the framework

- Framework §3 lists "Offices Act offices (powers, duties, controls, term, succession)" as the way roles change. **None of those
  fields changes by amending the Offices Act** (`legal.py:263-293` calls no institutions hook). Only enactment, repeal and an
  association's replace path re-read a declaration, and none of them reseats holders (`institutions.py:403`, `:478-486`). Role
  changes today must go through `grant`/`revoke` of the office right or the succession machinery.
- Framework §9 says lawyers "check whether a law does what it claims (preview / dry run)". The preview exists but cannot preview
  an amendment as one (`lawpreview.py:358-375`), shows no enactment diff (`:435`), and cannot see offices, stores or association
  treasuries (`kernel.py:981-1005`). Lawyers need E2-E3 before that duty is possible.
- "Represent clients" has no engine path. Agency is limited to `transfer` and `deposit_escrow` (`contracts.py:141-145`).
- Millbrook's "prosecutor" had no court: no `judge` holder and no clause in force.
