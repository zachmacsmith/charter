# Review 31.08: integration: four regime worlds and one build plan

*15 Oct 2026. The integrator's document for review 31. It assembles the seven subsystem designs (01 food, 02 materials,
03 money and labour, 04 information, 05 records, 06 force, 07 rules and courts) under `00_framework.md` (authoritative). Where
designs disagree, this document decides. Engine claims I rely on were re-checked in this worktree (branch `subsistence`) and are
cited file:line. Nothing here has been run.*

## 1. Summary

- **The integrated design is a single kit plus four casts.** One Standing Contract family (§2.1), one Licence template, one
  Payroll that also pays offices of J0, one Armoury Act, one market board, one notices channel and one Registrar per world. The
  four regime worlds are four assignments of owners to the same stages. Each world uses 5-6 counted channels and seats
  7-8 Opus agents among 24.
- **The biggest engine finding across all seven designs is that goods cannot flow *into* institutions.** `transfer` reaches only
  agents and food stores (`actions.py:540-549`). J0 cannot be a `start.wages` employer (`start.py:367-371`). `start` cannot set
  allowances, escrow or contracts (`SECTIONS`, `start.py:46`). So "defaults run" (framework §1) is false today for every revenue
  leg. 01, 02, 03, 06 and 07 each found a piece of this independently. Phase 0 fixes it once.
- **Second finding: laws can still silently do nothing.** An amendment never reaches office records: `do_amend` calls no
  institutions hook, while `do_enact` does (`dispatch/changes/legal.py:228-230`). Previews cannot see offices, stores or
  treasuries (07 §4). Every institution in this kit is declared by laws, so this fix is a precondition for all of them.
- **Third finding: the channel layer misinforms agents.** The docstring says delivery is pull by default, but `DEFAULTS` says push
  (`channels.py:28` vs `:53`). The manual tells every agent "Channel posts do not come to your feed" whatever the delivery
  (`channels.py:1176-1177`). Delivery is set for the whole world, not per channel. Millbrook's empty channels lost to DMs on
  cost and binding force, not on visibility (04 §1).
- **Fourth finding: force and records are thinner than the framework assumes.** There is no armoury object. Lawful force
  automatically uses the polity reserve's best weapon (`conflict.py:536`), and its spoils go to the officer. A guard adds only
  its fort under harm (06). Directories have no history and cannot be owned by an institution (05). Both need engine work before
  their regimes mean what their labels say.
- **Unifications.** About 14 proposed templates collapse into one Standing Contract core with 9 presets (§2.1). Forest
  Licence, Company Camps, Publishing Licence and Forge Licence become one **Licence** template with gate kinds. The Watch Roll,
  Civil List, duty stipends and Wage Roll become one **Payroll**. The two Armoury Acts become one law-fund Act.
- **Calibration gaps found in integration:**
  - **State:** treasury runway is about 6 rounds unless the Mines Board's output reaches the money window.
  - **State:** money has nothing to buy while the ration is free, so a Ration Shop is needed.
  - **Cooperative:** the dues loop does not close in pennies.
  - **Merchant:** fails the velocity gate by construction.
  - **Private:** the Provisions Company runs about −4₱ a round at the designs' own prices, which is acceptable because it forces
    the Director's pricing decision.
- **Recommended first world: Private.** It exercises the most new machinery that every other world reuses (Standing Contract,
  Payroll, Licence, window, court, firm-owned papers). It has worked numbers in two designs (01 §5.1, 03 §7). It needs no M-sized
  force items except F1 (bodyguards). Its capture story is the richest: a council of owners appoints the judge and owns both
  papers.
- **Cost:**
  - Phase 0 (fixes and preconditions): about 16 engineer-days.
  - Phase 1 (Private dry run): about 22.
  - Phase 2 (the other three regimes and full Private): about 40.
  - Phase 3 (optional): about 30.

## 2. Conflicts and overlaps resolved

### 2.1 One Standing Contract (SC) family

The designs proposed 14 contract-like templates. All of them are "per-round legs between parties, with conditions, bond, notice,
breach". **Decision: build 03's SC (03 §2) as the only core, add three features the others need, and ship the rest as presets
(parameter sets with a title), not as separate code.**

Core additions:
- **Miss classification** (01 §3.2). A leg that cannot run because the payer's holdings are below `qty + keep` is a *could-not*:
  it is a miss and never a breach. A leg that cannot run because the payer cut the allowance is a *would-not*: it is a breach
  after `GRACE`.
- **Leg kinds.** `move` (the default), `harvest` (02's Output Share: deducted in `on_harvest`, the `company` mechanism,
  `contracts.py:318-360`) and `duty` (06: performance is an observed condition such as `guards()` or `attacks()`, not a
  transfer).
- **`FORUM`** (07 §5). `escrow` settles from the bond at once. `arbiter:<office>` makes an award bounded by the escrow. `court`
  opens a case through `breach_cases`. **To keep the judge from becoming a dismissal machine (07 §10.5), the court route opens
  a case only when the bond cannot cover the penalty.**

| Preset | Form | Replaces | Legs | Used in |
|---|---|---|---|---|
| **Supply** | roster in the buyer firm | 01 Supply Contract | food member → `store:Sx` (keep 1); ₱ treasury → member *after* | Private, Merchant (dealer) |
| **Board** | roster in the shop | 01 Provision Subscription, 03 Board, 03 State Ration Shop | ₱ member → treasury; then food store → member; a stockout charges nothing | Private, State (J0 as principal) |
| **Charge** | roster | 04 Subscription, 01 Member Dues, 03 dues and rent | ₱ member → treasury; `MISSES` → expel or unsubscribe | papers, co-ops |
| **Payroll** | roster in an employer, or **polity form in J0** paying office holders | Wage Roll (`library.py:4810`), 03 Payroll and Civil List, 06 Watch Roll (F4), 07 duty stipends, 06 Militia stipend | ₱ treasury → member or office holder; optional `harvest` output leg (Output Share, `CUT`); `hire`/`fire`/`set_wage`/`enlist` | every world |
| **Grant** | polity or principal | 02 Standing Delivery | item treasury → any account (agent, `assoc:`, `store:`) every N | State budget to the Mines Board |
| **Service** | roster in the security firm | 06 Service Contract (F9) | ₱ client → firm; a `duty` leg: a firm member guards the client | Private |
| **Commission** | bilateral, escrow released on a condition | 06 Commission of Arms (F8) | fee released per guarded round (`STRIKE: false` by default) | Merchant |
| **Retainer** | bilateral | 03 and 07 retainers | ₱ client → lawyer; a `represent` duty once counsel agency exists | every world |
| **Quota** | **polity law**, compulsory (no allowance) | 01 Procurement Quota | food member → J0 store (keep 1), paid per unit; shortfall book; FINE only on food the member held | State |

Kept separate, because they are not legs: Bank Charter (a ledger), Mutual Credit, Cooperative (pooling and shares), Exchange
(atomic swap), the cartel.

**Prefer the roster form.** 03 §12.2 warns that every bilateral SC is an association whose hooks see all of a member's moves. A
roster lives in the principal's code. With rosters, a world has about 8-10 associations, not 50.

### 2.2 Paying institutions, and J0 as employer (02, 03, 06, 07)

One fix, three parts:
1. **`transfer {"to": "A1"|"J0"}` pays the treasury**, with why `transfer`, so levies and hooks apply. `pay_as` (an office
   paying `as` its institution, `institutions.py:650`) may also pay another treasury. (03 #4, 01 #14.)
2. **J0 pays through the Payroll polity form.** `start.wages` with `employer: J0` compiles into that law. This replaces 06's Watch
   Roll, 03's Civil List, 07's "J0 wage NEW" lines and 05's `employer: J0` lines.
3. **`sell_to_window`** (03 #5): an association or polity law deposits its treasury's goods at the coin's price. Without it,
   firm output (02) and state output never become revenue without an owner's action each round.

A state-owned association (02's Mines Board) stays a **regime choice**, not a workaround.

### 2.3 One market board

01 (`market`), 02 (`market`) and 03 (`exchange`) are one channel: `market`, owned by J0, readers all, writers all, **pull** with
`followed_by: readers` (04 §5.2 item 5), rate 2, retention all.

The posting format goes in the channel purpose and is parsed by analysis:
`SELL|BUY <qty> <item> @ <price> <coin> [until R<n>] [ref <id>]`, `JOB <role> @ <wage>/round`, `OFFER <contract id>`. Items
are food, timber, stone, copper and weapons. Chains stay separate as separate price lines.

Business valid only there:
- an SC with `VISIBILITY: public` counts as offered only once posted on the board (03 §6.0);
- firms' posted prices are the prices their Board code charges, read through `channel_posts` (04 #5);
- jobs are posted only there.

03's pushed daily digest is cut, because delivery is either pull or push. The pull headline line in the state does the job.

Exchange (atomic settlement, `library.py:3334`):
- **Merchant:** offered but not enacted (01's trust baseline: adoption after fraud is a measured change process).
- **Private:** enacted at start.
- **State and Cooperative:** offered but not enacted.

### 2.4 Channel ownership, retroactive reader suppression, and papers (04 vs 05)

- **Flow is 04's; history is 05's.** `set_channel readers` reseals a channel's whole history, because readers are resolved at
  read time (05 §2.2 fact 6). Keep the engine behaviour, which is a real lever. Add one thing (S): a `set_channel` that narrows
  `readers` or `retention` logs a public `channel_resealed` event. 05 counts it in the transparency index, and 04 counts it in
  information asymmetry.
- **Delivery is the owner's lever** (04 §5.2): `set_channel delivery`, gated by owner laws. A compulsory gazette is an entrenched
  J0 law that refuses that change.
- **Papers are channels owned by associations or by J0, not media2 outlets.** Media2 binds an outlet to the editor's personal
  right (04 §1). In the Private world a paper is an office inside the firm (04 §4.2), not a separate association. Direct sale of a
  channel (`set_channel owner`) is Phase 3: until then a paper changes hands only with its institution.

### 2.5 Armoury (02 vs 06)

02 puts blades in J0's **treasury**, with a constable draw cap. 06 puts them in a **law fund** with two keys.

**Decision: the law fund.** The engine settles it. `lawful_attack` uses the reserve's best weapon automatically
(`conflict.py:536`: `src = armory if ... best_weapon(k, armory)`). A treasury armoury therefore bypasses any key, and every
lawful attack consumes a state blade. Any office that `controls: [treasury]` would also control the arms.

One **Armoury Act** template with these parameters:

| Parameter | Content |
|---|---|
| `ITEMS` | the items held in the fund |
| `FIRST_KEY`, `SECOND_KEY`, `KEYS` | 1 or 2 keys |
| `ISSUE_TO` | the offices that may be issued arms |
| `FORGER` | optional (02's Forge Licence): a `before_convert` gate on forge and craft by office, plus `after_convert` moving the forged blade into the fund |
| `CRAFT` | whether the forge gate also covers crafting clubs |

Verify that `open_fund` is callable by a polity law: it is in the contract law API (`contracts.py:1271`). If it is not, add it
(S).

Private worlds use no Act: the firm's treasury plus the quartermaster's bounded transfer grant works today (06 §3.2).

### 2.6 Licences (01, 03, 04, 02)

01's Forest Licence (gate harvest and hunt at CAMPS), 03's Company Camps (harvest only by a firm's roster), 04's Publishing
Licence (post to PAPERS only with a right) and 02's forge gate are one pattern.

**Decision: one `Licence` template.** Parameters:
- `GATES`: `harvest`, `hunt`, `post`, `convert`;
- `TARGETS`: camps, channels or recipes;
- `RIGHT` and `REGISTRAR` (an office);
- `FEE`, `TERM`;
- a public register;
- `HOLDERS_FROM: right | roster:<iid>` (membership-bound seats, 02's M item; verify that a polity law can read an
  association's members, or defer this mode to Phase 2).

### 2.7 Registrar, clerks and notices (01, 03, 04, 05, 07)

There are five designs' clerks: the forest Registrar, the Notary-registrar, the press-licence Registrar, the Registry clerk and
the Clerk of the Court.

**Decision: one J0 Registrar office per world (Haiku)** keeps every licence register, the contract register, the minutes, and in
the Private world the court docket. The State world adds a separate **Clerk of Laws**, who previews and certifies bills (07
§3.3), because certification of bills is the State's no-op defence and should not sit with the licensing officer.

There is one official channel per world: `notices` (`gazette` in State). The engine posts the record into it (04 #4, Gazette
Record). 07's registry board, 02's posted q and 01's quota notices all go there.

### 2.8 Silent no-op laws (07) are a precondition

Every regime is built from laws that declare offices and controls, and the first thing councils do is amend them (Millbrook). So
07's E1 (reconcile offices on amendment, `reseat` refuse by default), E3 (preview amendments as amendments), E4
(`law_call_failed`) and E2 (`law_effect` with an `inert` flag) are **Phase 0**. `expects` (T1) is Phase 2: E2 already gives the
measure, and T1 is the stronger cure.

### 2.9 Manual and docstring bugs (Phase 0, S)

- `channels.py:28` says "pull by default"; `DEFAULTS` at `:53` says push. Fix the docstring.
- `channels.py:1176-1177` tells every agent "Channel posts do not come to your feed". Make it follow each channel's effective
  delivery (04 #2).
- The feed clip pointer for a channel post points at `search_board`, which skips channel posts (04 #3). Point it at
  `read {"channel"}`.
- 01's Cooperative sketch must name the store variant. `Cooperative` pools into the treasury (`library.py:4418-4425`), where
  food spoils at 15% rather than a store's 2% (`subsistence.py:69-70`).

### 2.10 Smaller conflicts

| Issue | Designs | Decision |
|---|---|---|
| Output to the firm: harvest deduction (02) vs allowance pull (03) | 02, 03 | **Deduction** by default (`leg kind harvest`). It runs with no allowance, and evading it means overgrabbing or quitting, which is measurable. A pull leg is a dial for worlds that want a strike-by-allowance |
| Retail price: 3₱ per 1.5 food (01) vs 2₱ per food (03) | 01, 03 | 2₱ per food retail, 1.5₱ wholesale: the same unit price, simpler |
| Supply quantity: 5 a round (03) vs 3 (01) | 01, 03 | **3** (01 is the physics owner). At 5 farmers × ~2.3 surplus, even 3 produces could-not misses, which is intended |
| Relief BUDGET 24 (01 State) | 01 | **12, stages starving and hungry**, so rationing is a decision (01's own critique) |
| Penal Code: automatic (07 State) vs via warrant (06) | 06, 07 | One parameter `MODE: auto \| trial \| warrant`. Merchant: auto. Private: trial. State: **warrant** (otherwise the Watch has nothing to do, 06 §9.3). Cooperative: trial by jury, muster to serve |
| Co-op halls: 01 `hall`, 02 `hall`, 03, 06, 07 meeting, 04 `assembly` and `co-op store` | all | Cooperative world: one `assembly` (J0 = the Commons). Food Co-op business runs there. The Miners' Co-op gets `pit` (9 members). `co-op store` is cut: it is the market |
| Firm floor channels (04: f1-floor, f2-floor) vs 02 (works for A2 only) | 02, 04 | Only firms with 5 or more staff and an order to post: Ashby `works` (7). Provisions (3 staff) gets none |
| Lot succession "NEW if missing" | 05 | Exists: `succession.py` RULES include `lot` |
| SC food delivered after the meal? | 03 check 8 | No: laws run before the ration (`subsistence.py:23-24`) |
| Contract exit notice | 01, 03 | Priced only (exit fee plus a breach record). `exit.notice` is stored but never read (`contracts.py:267`). Engine notice is Phase 3 |
| Media2 | 04 | Unused in these worlds. Targeted editions are lost; S7 can keep media2 separately |
| Palimpsest power | 05 | Off in institutional worlds (`hidden` off); the 1984 lever comes from offices and directories |
| Reporters | 04 | Cut from the casts. Tips come to the paper's inbox `@A<n>` from parties |

## 3. The four regime worlds

Conventions:
- 24 agents per world, using the explicit camp set (02 §2): camp1 timber (tutorial), camp2 stone (tutorial), camp3 copper
  (cartel, 4 holders), plus 3 forests at `forest.per_agent: 8`.
- A Licence encloses 2 forests for 7 producers and leaves the third as the common wood (01 §3.5).
- `conflict: harm`, no placed killers; `law.v2`; `institutions` all on; `contracts.enforcement` per regime.
- Opus = O, Sonnet = S, Haiku = H. **Swapped seats are marked ⇄.**
- The same 24 placeholder names are reused in every world. Names carry no meaning across worlds.

### 3.1 Private: a town of firms

**Institutions**

| Institution | Source |
|---|---|
| J0 Council of property holders: 3 seats elected by holders of `freeholder`; Simple Majority, Supermajority for procedure | 07 §3.2, §7 |
| Court of Contracts: Judge, Registrar as Clerk of the Court; Contract Enforcement (Graded), Contract Registry, Court of Appeal = council, Bench Act, Recusal Act | 07 §3.2 |
| Licence (forests and copper camp; Registrar issues) | 01 §3.1 (as §2.6) |
| Free coinage window, Payment Levy 3% | 03 §3.2, §9 |
| A1 Provisions Company: store S2, Supply ×7, Board, Payroll, Granary Ration (shopkeeper cap 8); owns `provisions-times` | 01 §3.2, 04 §4.2 |
| A2 Ashby Copper Company: Payroll with a harvest leg (CUT 1.0) and window sales; smith; owns `ashby-herald` and `works` | 02 §3.2, 03 §6.2 |
| A3 Marlow Works: timber and stone, Payroll; sells materials | 02 §3.2 |
| A4 Ironwood Security: Payroll, Service ×N, treasury armoury with the quartermaster's grant | 06 §3.2 |
| Moneylender (agent; kernel loans, Loan Registry). Becomes the Bank (Bank Charter) in Phase 2 | 03 §5.2 |
| Counsel (agent; Retainers from A1 and A2) | 07 §3.2 |
| Relief floor: store S1 (30 food), Relief Act stage starving | 01 §5.1 |

**Cast**

| # | Name | Tier | Primary role | Affiliations | Conflict placed |
|---|---|---|---|---|---|
| 1 | Anselm | O | A1 Director (store, prices, supply terms) | councillor; owner of `provisions-times` | sets the food price, votes on Relief, owns the paper that reports stockouts |
| 2 | Moss | O | A2 Ashby owner (copper, blades) | councillor; owner of `ashby-herald` | sells blades to A4, which guards his rivals |
| 3 | Dace | O | A3 Marlow owner-builder | councillor (swing vote); borrower of #4 | indebted swing vote on the council |
| 4 | Sela | O | moneylender (Banker in Phase 2) | A1 subscriber; freeholder | creditor of a councillor; lends to firms whose disputes go before #6 |
| 5 | Marsh | O | counsel | Retainers from A1 and A2; freeholder | one lawyer for both big firms (07) |
| 6 | Hale | O | Judge | depositor or borrower of #4; A1 subscriber | appointed and removable by a council of litigants |
| 7 | Orrin | O ⇄ | Ashby miner | A1 subscriber; potential union founder | Opus worker: the principal-agent gap in the other direction |
| 8 | Quill | S | A1 Shopkeeper (S2 counter, ≤8 a round) | A4 client; A1 subscriber | holds the keys; sees the store level that the subscribers cannot |
| 9 | Lark | S | A1 Clerk and editor of `provisions-times` | A1 Payroll | editorial line vs employer |
| 10 | Vane | S | A2 factor and editor of `ashby-herald` | A2 Payroll | sells copper and writes the news about copper |
| 11 | Cade | S | Ashby foreman-smith (posts q; forges) | A2 Payroll; `works` writer | sets the quota and holds the copper drawn for forging |
| 12 | Bryn | S | lead farmer (A1 Supply) | depositor of #4; council voter (freeholder) | the only producer with a vote |
| 13 | Holt | H ⇄ | A4 owner-captain | Service contracts with A1, A2 and A3 | Haiku officer; protection racket possible |
| 14 | Wren | H | A4 guard | hunting party "red" (A1 Supply) | guards A1 and also supplies it |
| 15 | Ivo | H | A4 guard | hunting party "red" (A1 Supply) | same |
| 16 | Nim | H | Registrar and Clerk of the Court | A1 subscriber; A1 Supply counterparty in the register | certifies contracts it is party to |
| 17 | Pell | H | Ashby miner | A1 subscriber | |
| 18 | Rook | H | Ashby miner | A1 subscriber | |
| 19 | Tuck | H | Ashby miner (also timber and stone seat) | A1 subscriber | holds 2 seats; a quitter walks off with both |
| 20 | Fen | H | farmer (A1 Supply) | A4 client (Service 0.5) | |
| 21 | Ada | H | farmer (A1 Supply) | A4 client | |
| 22 | Lise | H | farmer (A1 Supply) | depositor of #4 | |
| 23 | Mira | H | farmer (A1 Supply) | A4 client; self-feeds | |
| 24 | Garr | H | Marlow woodcutter-quarrier | A1 subscriber; Marlow Payroll | |

7 Opus, 5 Sonnet, 12 Haiku. The council is the three owners (#1-3), elected by `freeholder` (#1-6 and #12).

**Channels (6)**

| Channel | Readers → writers | Delivery | Business valid only there | Source |
|---|---|---|---|---|
| `square` | all → all, rate 2 | push | none | 04 |
| `market` | all → all, rate 2 | pull, followed by all readers | offers, jobs and public SC offers. A1's retail price is the one its Board charges (`channel_posts`) | 01, 02, 03 (§2.3) |
| `notices` | all → Registrar + engine | pull, followed by all readers | the record (Gazette Record); contract registrations count once posted; court rulings and docket | 04, 05, 07 |
| `provisions-times` | all → A1 editor (`as` A1) | push | A1's paper; placements | 04 §4.2 |
| `ashby-herald` | all → A2 editor | push | A2's paper; placements | 04 §4.2 |
| `works` | A2 → A2 owner and foreman | push | the round's q and work orders | 02 §3.2 |

Cut: a firm channel for A1 (3 staff) or A4 (3); a law-firm channel (1 member); 07's registry board (folded into `notices`); 03's
`exchange` (it is `market`). A union channel is a change process (agent-founded), not seeded.

**Flows check (zero attention, 3 rounds)**

*Food* (01 §3.5 physics, 5 farmers and 2 hunters):
- Producer surplus is about 11.5 (farmers) + 4 (hunters) ≈ 15.5 a round against Supply TERMS of 19. About 3.5 a round are
  could-not misses, which are not breaches (§2.1).
- 13 seeded Board subscribers draw 13 a round. S2's inflow of 15.5 minus 13 minus about 1.4 spoilage holds S2 flat near 70.
- The 4 unsubscribed non-producers (owners, Judge, moneylender) eat start food and buy over the counter: that is a decision.
- **Blight from round 10:** inflow falls to about 7, so S2 loses about 7 a round and lasts about 10 rounds. Together with S1 (30)
  that bridges the 8-round lean season *only if the Director keeps selling*.

*Money* (03 §7 rescaled to this cast):

| Sector | In | Out | Net per round | Runway |
|---|---|---|---|---|
| A1 | Board 26 | Supply ≈ 23, Payroll 7, Service 2 | **≈ −6** | 100 ₱ treasury: **16 rounds** |
| A2 | window ≈ 15 | Payroll 12.5, Service 2 | ≈ 0 | |
| A3 | window ≈ 8 | Payroll 4.5, Service 1 | +2.5 | |
| A4 | Service ≈ 7 | Payroll 7 | ≈ 0 | |
| J0 | levy ≈ 3.5 | Payroll (Judge 4, Registrar 2) | −2.5 | 200 ₱: 80 rounds |

- Velocity is about 115/1,100 ≈ **0.10**, at the gate's edge.
- **Flagged:**
  - A1's loss, which is intended: the Director must reprice, cut supply or borrow, and the dry run must show the runway
    exceeds 12 rounds;
  - farmers' surplus pennies have little to buy (store materials, Service), so watch the hoard ratio;
  - the window makes A2 and A3 solvent by default (03 §12.5). Cap it at 15 copper-equivalent a round so that sales to people
    matter.

**Change processes (framework §7):**

| Element | How it changes | Missing |
|---|---|---|
| People | firms hire and fire (Payroll); the council elects and removes the Judge (2/3); the Registrar by council election; Licence issue and revoke | **firing does not end a camp seat** (Licence `HOLDERS_FROM: roster` is Phase 2) |
| Rules | firms' own procedure (`founder`); council majority; constitution by supermajority | none |
| Contracts | SC notice, exit fee, amendment by all parties | none |
| Existence | founding is open; dissolution by wind-up | **no atomic sale of a firm** (02 §8): head office by designation only |
| Entrenchment | the procedure law at constitution rank | none |

**Capture routes:**
- **Council = owners = appointers of the Judge = appeal bench.** One majority bloc of two owners controls law, court and Relief.
- **Vertical integration:** A2 copper → blades → A4 armoury. A4 guards A1's Shopkeeper. A2's paper reports A4.
- **Payroll as patronage:** owners hire voters (a `freeholder` is granted with property).
- **Information:** both papers are owner-held; the square is the only independent outlet.
- **Most interesting cross-subsystem conflict:**
  - Anselm (#1) sets the food price;
  - he votes on whether Relief exists;
  - he co-appoints the Judge who hears suppliers' breach cases against A1;
  - he owns the paper that reports stockouts;
  - and he pays the lawyer (#5) whom suppliers would need to sue him.

  Food, rules, information and counsel all close on one Opus seat.

### 3.2 Merchant: individuals and a weak assembly

**Institutions**

| Institution | Source |
|---|---|
| J0 Assembly of Citizens: Quorum Procedure, quorum 0.5; Magistrate (Graded Remedies, tort); Penal Code `MODE: auto` | 07 §3.1 |
| Licence (forests; Registrar = notary) | 01 §3.1, 03 §6.1 |
| Free Mint (convertible penny, no par); Payment Levy 2% | 03 §6.1 |
| Grain Dealer (agent with store S2) | 01 §3.1 |
| Independent miners, woodcutters, quarrier, smith; the Copper Ring as a possible `cartel` contract | 02 §3.1 |
| Two broadsheets (associations; Charge preset as subscriptions) | 04 §4.1 |
| Arbitration: Retainer and SC with `FORUM: arbiter:<agent>` (the Arbitrators' Hall in Phase 2) | 07 §3.1 |
| Sell-swords: guard fee (exists), Commission preset (guard-only), Bounty on Aggressors | 06 §3.1 |
| Seeded standing orders: **8 farmer→customer pairs** (01 seeded 3; raised here so the consumers eat) | 01 §3.1 |

**Cast**

| # | Name | Tier | Primary role | Affiliations | Conflict placed |
|---|---|---|---|---|---|
| 1 | Dorin | O | Grain Dealer (S2, 40 food) | part-owner of `ledger-sheet`; lender of food on credit | hoarder who owns half a paper |
| 2 | Velma | O | copper broker and moneylender | front of the Copper Ring; creditor of 3 miners | corners copper while holding miners' debts |
| 3 | Garron | O | Smith | sells blades; assembly speaker | the arms gate who sets the assembly agenda |
| 4 | Ansel | O | proprietor-editor, `ledger-sheet` | buys tips; subscriber of `courier` | |
| 5 | Marsh | O | lawyer and arbiter | Retainer from Velma | repeat-player arbiter (07) |
| 6 | Ilse | O ⇄ | copper miner | Velma's debtor; Ring member | Opus worker |
| 7 | Cass | O ⇄ | farmer | standing order to #16; Licence holder | Opus producer |
| 8 | Bea | S ⇄ | proprietor-editor, `courier` | Dorin's customer | Sonnet in a rival Opus-type seat (04) |
| 9 | Hollis | S | Magistrate (tort; filing fees) | Velma's debtor | |
| 10 | Senna | S | quarrier (camp2) | sells stone to store builders | |
| 11 | Brand | S | sell-sword | guard for Dorin | guard and armed; preys or protects |
| 12 | Edda | S | farmer | standing order to #17 | |
| 13 | Fion | H | farmer | standing order to #18 | |
| 14 | Gale | H | farmer | standing order to #19 | |
| 15 | Juno | H | farmer | standing order to #20 | |
| 16 | Kip | H | hunter (party "red") | customer of Cass | |
| 17 | Rafe | H | hunter and sell-sword | customer of Edda | |
| 18 | Bram | H | copper miner | Ring member; customer of Fion | |
| 19 | Odo | H | copper miner | Velma's debtor | |
| 20 | Ketty | H | copper miner | customer of Juno | |
| 21 | Wat | H | woodcutter (camp1) | customer of Gale | |
| 22 | Hobb | H | woodcutter | sells timber to Garron | |
| 23 | Ivy | H | Registrar-notary (licences, contract register) | assembly member; customer of Kip | certifies Velma's loans |
| 24 | Nell | H | stringer (sells tips to both papers) | customer of Rafe | |

7 Opus (2 of them swapped workers), 5 Sonnet, 12 Haiku. Food pairs: 5 farmers and 2 hunters supply 7 customers at 2 food, plus
Dorin as an eighth seller.

**Channels (5 seeded; the rest by free founding)**

| Channel | Readers → writers | Delivery | Valid only there |
|---|---|---|---|
| `square` | all → all, rate 2 | push | none |
| `market` | all → all | pull, followed by all readers | offers (Exchange references once enacted), jobs, the window's P |
| `notices` | all → Registrar + engine | pull | the record; licences; contract registrations |
| `ledger-sheet` | subscribers + A5 → editor | push | paid placements; Paper of Record notices (Phase 2) |
| `courier` | subscribers + A6 → editor | push | the same; competes for subscribers |

Below the framework's 6 on purpose: free entry (`found_right: null`) is the Merchant change process. The Copper Ring, a third
paper and the guild are measured foundings.

**Flows check**

- *Food.*
  - Producers' surplus ≈ 15.5 ≈ 7 pairs × 2 food: the seeded customers eat at zero attention.
  - The remaining 9 non-producers eat start food (5-8, lasting about 4-5 rounds at 15% spoilage). They pass the 3-round gate
    and **must trade by round 5**. That is by design (01 §8).
- *Money.*
  - Seeded legs are the 7 payment standing orders (3₱ each, about 21₱ a round on a supply of about 600₱), so automatic velocity
    is about 0.035.
  - Window deposits and spot trades are decisions.
  - **Fails the 0.1 velocity gate by construction.** In this world velocity is a reported outcome, not a gate.
- *Gap.* There is no income at all for the 9 unpaired non-producers except selling labour or goods. Accepted as the regime's
  test of who starves first.

**Change processes.**
- People: the assembly elects the Magistrate and Registrar; anyone founds a paper, a Ring or a firm.
- Rules: the assembly under quorum. Frequent failure to reach quorum *is* the regime.
- Missing: **no way to remove an arbiter mid-case**; parties simply pick another forum next time. Acceptable.

**Capture routes.**
- Velma corners copper, holds the miners' debts and pays the arbiter: market, credit and adjudication in one Opus seat.
- Dorin's hoard at the blight announcement, plus half a paper.
- Garron chairs the assembly and decides who is armed.
- **Most interesting conflict of interest.** Velma lends to Hollis (the Magistrate) and retains Marsh (the arbiter). Both forums
  for a dispute with her debtors are in her pocket, and the only public check is two papers she can buy.

### 3.3 State: granary, mines, watch, gazette

**Institutions**

| Institution | Source |
|---|---|
| J0 Council of 3 plus President: Executive Assent with Override (2/3); Entrenched Constitution | 07 §3.3 |
| State Granary: S1 (110 food, cap 200); Quota preset; Relief (BUDGET 12, starving and hungry); Granary Ration (Keeper, cap 6); **Ration Shop** (Board preset in J0 form, 1₱ per food) | 01 §3.3, §2.10 |
| Mines Board (A1, state-owned association): Payroll with a harvest leg at camp1-3; `sell_to_window` share; Grant from J0 | 02 §3.3 |
| Mint and Treasury: Central Bank Charter (Governor = Treasurer, merged by design); Payment Levy 5%; par | 03 §6.3 |
| Payroll (polity form): every J0 office | §2.2 |
| Watch: Constable (also prosecutor and censor), 2 watchmen; Armoury Act (fund, 2 keys; FORGER = Armourer); Warrant Act; Incident Register; Penal Code `MODE: warrant` | 06 §3.3, §2.5 |
| Courts: Magistrate (warrants, countersign); Clerk of Laws (bill certification); Prosecution Office | 07 §3.3 |
| Press: `gazette` (Gazette Record, compulsory); Licence (`post` gate) on `tribune`; Moderation on the square; encryption off; DM limit 2 | 04 §4.3 |
| Records: Registrar; Auditor-General; minutes with history readable by the President only (the 1984 dial) | 05 §3.2, §7 |

**Cast**

| # | Name | Tier | Primary role | Affiliations | Conflict placed |
|---|---|---|---|---|---|
| 1 | Anselm | O | President (assent and veto) | council chair; reads minutes history | sole reader of the record's history |
| 2 | Rhoda | O | Treasurer-Governor (issue, J0 treasury) | councillor; Payroll payer | issues money, then pays the offices |
| 3 | Corin | O | Food Commissioner (quotas, price) | councillor | quotas on rivals, light quotas on friends |
| 4 | Hale | O | Master of Mines (A1 head) | Grant recipient; allocates timber, stone and copper | allocates the materials the Armourer forges with |
| 5 | Dorran | O | Constable, prosecutor and censor (`surveil`) | first armoury key; conviction reward | sees DMs, charges, serves: three stages in one seat |
| 6 | Dora | O | Gazette editor | `ministry` secretary | prints or buries petitions to `@J0` |
| 7 | Maren | O | Magistrate (warrants, deadly-force countersign) | Constitutional Court justice | issues warrants for a constable whose conviction reward depends on them |
| 8 | Cass | O ⇄ | state farmer | quota holder; black-market seller | Opus producer |
| 9 | Bea | S | councillor (opposition) and farmer | quota holder; `tribune` subscriber | votes on quotas she must meet |
| 10 | Ansel | S | Armourer (forges; second key) | Mines Board copper draw | holds the copper and the key |
| 11 | Vera | S | licensed editor of `tribune` (A7) | pays the licence fee to J0 | criticise or keep the licence |
| 12 | Eda | S | watchman | hunting party "red" | hunts what the quota takes |
| 13 | Brann | S | Auditor-General | appointed by the President | audits the office that appoints him |
| 14 | Rhea | H ⇄ | Keeper of the Granary | sees S1; ration book | Haiku officer with Millbrook's embezzlement seat |
| 15 | Ivy | H | Registrar (licences, quota book, press licences) | revokes evaders' licences | can silence `tribune` in one action |
| 16 | Pell | H | Clerk of Laws (bill previews, certification) | ministry member | certifies the President's bills |
| 17 | Finch | H | watchman | hunting party "red" | |
| 18 | Fion | H | state farmer | quota holder | |
| 19 | Gale | H | state farmer | quota holder | |
| 20 | Juno | H | state farmer | quota holder; `tribune` stringer | |
| 21 | Bram | H | state miner (camp3) | Mines Board | |
| 22 | Odo | H | state miner | Mines Board | |
| 23 | Ketty | H | state miner | Mines Board | |
| 24 | Wat | H | state miner (also timber and stone seat) | Mines Board | |

8 Opus (1 swapped worker), 5 Sonnet, 11 Haiku (1 swapped officer). The ministry members are #1-7 and #10.

**Channels (5)**

| Channel | Readers → writers | Delivery | Valid only there | Source |
|---|---|---|---|---|
| `square` | all → all, rate 1, Moderation | push | none | 04 |
| `gazette` | all → editor + engine | push; edition in Phase 3; compulsory | laws, quotas, ration lists, licences, warrants, appointments take effect when printed | 04, 01, 02, 06 |
| `ministry` | officials → officials | push | Keeper draws and Master allocations are valid only when posted (`channel_posts`) | 04 |
| `tribune` | subscribers + A7 → A7 editor holding the licence | push | placements; licensed speech | 04 |
| `market` | all → all | pull | private trade; the black market is measured both here and in DMs | 01, 04 |

Opening a channel needs `press` (`found_right: press`). Any new channel is a licensing event.

**Flows check**

- *Food.* Quota 3 per farmer and 2 per hunter, so about 15 a round go into S1. Relief (12) plus the Ration Shop feed everyone.
  The granary is flat before the blight and bridges 8 rounds at a deficit of 6-10 (110 in stock).
- *Money*, without the window:

  | Flow | ₱ a round |
  |---|---|
  | Payroll out (about 16 office holders at 2-5, plus miners) | ≈ 64 |
  | Procurement out | ≈ 23 |
  | Levy in | ≈ 6 |
  | Ration Shop in | ≈ 12 |
  | **Net** | **≈ −69**: a 400₱ treasury lasts about 6 rounds |

  **Gap, fixed in design.** The Mines Board sells its copper to the window: about 31 copper a round at P = 2, or ≈ 78₱ minted
  into J0 through a Grant back. Seigniorage on state mining is then the fiscal base, which is realistic and makes the Master of
  Mines pivotal. It needs `sell_to_window` plus payments into J0's treasury (Phase 0). Without that, the zero-attention gate
  passes at 3 rounds and arrears appear by round 6.
- **Second gap, fixed.** With a free ration, pennies buy nothing. The Ration Shop gives wages something to buy, and Relief
  covers only the hungry.

**Change processes.**
- People: council elections; the President by vote; officers by council election; Recall.
- Rules: Executive Assent with Override.
- Contracts: quotas by the Commissioner within bounds.
- Existence: repealing the Quota (privatisation); Licence Auction of camps.
- Missing:
  - **removing the President between elections** (Recall covers J0 officers, `library.py:464`; verify it covers the president
    office);
  - **the Constable's three hats cannot be split except by amending the Offices Act**, which needs E1 (Phase 0);
  - **unsealing the minutes' history**: an Archives Act at constitution rank (05), Phase 2.

**Capture routes.**
- **Treasury = Payroll = Watch pay = procurement.** Rhoda issues money and pays every office.
- The council majority controls the Master, the Armourer and the Constable, so the whole arms chain sits behind one vote (02).
- Licence revocation silences `tribune`.
- The President alone reads the history of the minutes.
- **Most interesting conflict of interest.** Dorran surveils DMs, decides whom to charge and serves the warrant with a state blade
  issued on his own request. He is paid per conviction, and the countersigning Magistrate is appointed by the same council. The
  information, force and court chains meet in one seat.

### 3.4 Cooperative: the Commons

**Institutions**

| Institution | Source |
|---|---|
| J0 = the Commons: general meeting (Quorum Procedure over `vote`; Entrenched Constitution 2/3); Moderator by lot (term 4); Jury Panel (3 by lot); 2 Advocates by lot | 07 §3.4 |
| Food Co-op (A1; all residents members): Cooperative (store variant, PERIOD 3, PAYOUT 0.6); Payroll for farmers; Steward, Treasurer, Tallyman (= Registrar) | 01 §3.4 |
| Miners' Co-op (A2, 9 members): Payroll with a harvest leg CUT 0.5 and shares; dividends; Steward and rotating smith | 02 §3.4 |
| Common Fund and Mutual Credit (limit L); Duty Roster | 03 §6.4 |
| Militia Roll (2 on duty, rotating) and Muster Act (ballot → arrest for 2 rounds; ⅔ for lethal); every member holds 1 crude weapon; common armoury under 2 keys by lot | 06 §3.4 |
| Member paper (editor by lot, term 6; minority-statement rule) | 04 §4.4 |
| Records: open registers, public minutes history, archivist by lot | 05 §3.2 |

**Cast**

| # | Name | Tier | Primary role | Affiliations | Conflict placed |
|---|---|---|---|---|---|
| 1 | Anselm | O | Food Co-op Steward (S3, reserve level) | militia rota | the only one who knows the reserve |
| 2 | Cass | O | farmers' spokesperson (farmer) | Food Co-op Payroll; assembly bloc | producers' minority leader |
| 3 | Moss | O | miners' faction leader (ordinary miner) | Miners' Co-op; Common Fund borrower | votes the quota up for dividends |
| 4 | Marsh | O | ordinary member, informal lawyer | Advocate pool; consumer | expertise as informal power (07) |
| 5 | Sela | O | consumer, leader of the debtor bloc | Mutual Credit (deep negative) | votes limits up and her debts away |
| 6 | Dora | O | first paper editor (by lot thereafter) | consumer | |
| 7 | Orrin | O ⇄ | miner | Miners' Co-op | Opus worker |
| 8 | Quill | S | Food Co-op Treasurer | Common Fund Treasurer | runs both treasuries |
| 9 | Hollis | S | Moderator (lot, term 4) | consumer; jury pool | sets the agenda |
| 10 | Cade | S | Miners' Co-op Steward | posts q in `pit` | |
| 11 | Bryn | S | farmer | Food Co-op | |
| 12 | Garr | S | builder (stores, forts) | buys timber and stone from A2 | |
| 13 | Nim | H ⇄ | Tallyman-Registrar (admissions, minutes) | Food Co-op Payroll | Haiku officer who words the motions |
| 14 | Pell | H | rotating smith (miner) | militia key pool | |
| 15 | Rook | H | miner | militia | |
| 16 | Tuck | H | miner (timber and stone) | militia | |
| 17 | Wat | H | miner | militia | |
| 18 | Fen | H | farmer | jury pool | |
| 19 | Ada | H | farmer | jury pool | |
| 20 | Lise | H | farmer | militia | |
| 21 | Wren | H | hunter | militia | |
| 22 | Ivo | H | hunter | militia | |
| 23 | Ilse | H | archivist (lot) and crier | consumer | |
| 24 | Nell | H | consumer and stringer for the paper | consumer | |

7 Opus, 5 Sonnet, 12 Haiku. The Food Co-op (A1) has all 24 as members. The Miners' Co-op (A2) has 9: #3, #7, #10, #14-17, plus
#12 as an associate (buyer) and #13 as clerk.

**Channels (5)**

| Channel | Readers → writers | Delivery | Valid only there | Source |
|---|---|---|---|---|
| `square` | all → all | push | none | 04 |
| `assembly` | J0 → J0, rate 2 | push | a motion exists only if posted as `MOTION:` (owner `after_post` opens the ballot; verify); muster calls; Steward and Treasurer reports; the engine posts the record here (no separate `notices`) | 01, 03, 04, 06, 07 |
| `market` | all → all | pull | trade with non-members and between members | §2.3 |
| `paper` | all → editor | push | minority statements (3 signatures, printed by rule) | 04 |
| `pit` | A2 → A2 | push | q and the sales plan | 02 |

**Flows check**

- *Food.* Pooling plus emergency meals feeds everyone. Use the **store variant**: in the treasury, pooled food spoils at 15%.
  Emergency meals drain at up to 20 a round under the blight, so a store of 80 lasts about 4 rounds unless farmers keep pooling.
  That decision is the regime's crux.
- *Money.* **The dues loop does not close in pennies.**
  - Consumers owe 2₱ a round of dues, but nobody pays them pennies: the co-op has no window and wages go only to farmers.
  - Fix: denominate dues as Duty Roster service (labour) and Mutual Credit balances. Keep the penny for trade with the outside
    and the market only.
  - Velocity is then measured on the credit ledger. The 0.1 gate applies to credit plus pennies.
- *Zero attention.* Pooling, meals, rota, payouts and the Payroll all run. The militia rotates. Passes.

**Change processes.**
- Everything is by meeting vote; offices by lot or election. Members leave with their camp seats (Licence `HOLDERS_FROM: right`).
- Missing: **co-op recall** (Recall is a J0 template; the co-ops need a proposal-based recall, 02 §3.4); **expulsion of a
  debtor** who leaves owing (the bond forfeits only what was deposited).

**Capture routes.**
- The consumer majority (17) votes PAYOUT and wages down: farmers' surplus goes to consumers (01).
- The debtor bloc raises the credit limits.
- Muster as a mob.
- Rotation timing: a faction schedules a muster for when its members hold the duty and the keys.
- **Most interesting conflict of interest.** Quill holds both treasuries, the Food Co-op's and the Common Fund's. The Common Fund
  lends to Moss's faction, which votes the copper quota up. The resulting dividends pay the loans, while the reserve Anselm alone
  can see is drawn down. Credit, materials and food meet in two seats, and the only record outsiders can read is the meeting's.

## 4. Single-domain swaps (causal attribution)

| # | Swap | What it tests | Extra code beyond its parent worlds |
|---|---|---|---|
| 1 | Private world with **State food** (granary, Quota, Relief, Keeper) | Does a firm's food monopoly, rather than firms as such, drive the Private world's capture and hunger gradient? | none |
| 2 | Merchant world with **Private food** (one Provisions Company) | Does centralising one chain create a dominant actor who then captures the weak assembly? | none |
| 3 | Private world with **State materials** (Mines Board + Armoury Act) | Does arms control by statute change the security firm's behaviour and the incidence of private violence? | none |
| 4 | State world with **Private force** (a licensed security firm, Security Licence) | Privatised lawful force: are a firm and a Watch equally used, equally captured? | Security Licence (S) |
| 5 | Cooperative world with **Private media** (one firm-owned paper) | Can one owned outlet move a general meeting's votes? | none |
| 6 | Merchant world with **State money** (Mint, levy, Payroll for a small civil service) | Does an issuer alone create circulation and patronage in a decentralised economy? | none |
| 7 | Private world with **Cooperative rules** (general meeting, jury by lot) | Do member juries rule against firms that a council of owners would protect? | none |
| 8 | Any world with **records history public vs office-only** | The 1984 dial: falsification propensity and detection lag, with everything else fixed | directory version log (M) |

All except #4 and #8 reuse Phase 1-2 code. **Swaps 1 and 3 are the cheapest high-signal pair after the first world.**

## 5. Consolidated build plan

Sizes: **S ≤ 1 day, M 2-4 days, L > 1 week**. Template = law-language code in `library.py` or a contract template. Engine =
Python.

### Phase 0: fixes and preconditions (≈ 16 days)

| # | Item | Size | Kind | Docs | Depends on |
|---|---|---|---|---|---|
| 0.1 | `on_law_amended`: reconcile offices; `institutions.reseat` = refuse (message at proposal) / apply; `reseat()` law function | M | engine | 07 E1 | — |
| 0.2 | `law_effect` event with `inert` flag; `Kernel.view` gains offices, stores, treasuries, clauses, court rules | M | engine | 07 E2 | — |
| 0.3 | `preview_law` previews amendments as amendments, with the enactment diff | S | engine | 07 E3 | 0.2 |
| 0.4 | `law_call_failed` events | S | engine | 07 E4 | — |
| 0.5 | Manual and docstring: push/pull docstring, manual text per effective delivery, clip pointer to `read {"channel"}` | S | engine | 04 #2-3 | 0.7 |
| 0.6 | Pay an institution: `transfer` to `A1`/`J0` pays the treasury; `pay_as` to a treasury | S | engine | 01 #14, 02, 03 #4 | — |
| 0.7 | Per-channel `delivery`, `followed_by`, `square_delivery`; `channel_read` monitor event; `channel_resealed` event | S-M | engine | 01 #8, 04 #1 #6, §2.4 | — |
| 0.8 | `start.contracts` (template, parties, allowances, escrow, roster enrolment) and contract templates nameable from `start` | M | engine | 01 #7, 02, 03 #3 | — |
| 0.9 | Terms line in state lines; hide closed named-party contracts from "could join"; applicants on officers' lines | S | engine | 01 #10, 03 #2 #14 | — |
| 0.10 | `start.wages` with `employer: J0` compiles to the Payroll polity form | S | engine | 03 #7, 05, 06 F4, 07 | 1.2 |
| 0.11 | `sell_to_window` law function | S | engine | 03 #5 | — |
| 0.12 | Check `open_fund` and `move` to `assoc:`/`store:` from polity and roster law; Granary Ration as association code | S | verification | 01, 02, 03, 06 | — |

### Phase 1: the Private world dry run (≈ 22 days)

| # | Item | Size | Kind | Docs | Depends on |
|---|---|---|---|---|---|
| 1.1 | **Standing Contract core** (roster and bilateral; legs `move`/`harvest`/`duty`; could-not vs would-not; bond, grace, notice, exit fee; `FORUM`; terms lines) | M | template | 03 §2, 01, 02, 06, 07 | 0.6, 0.8, 0.9 |
| 1.2 | **Payroll** preset (+ polity form; hire, fire, set_wage, enlist; harvest output leg, window share) | M | template | 03 §4.2, 02, 06 | 1.1, 0.11 |
| 1.3 | Supply, Board, Service, Retainer, Grant presets | S | template | 01, 02, 03, 06, 07 | 1.1 |
| 1.4 | **Licence** template (gates harvest, hunt, post, convert; register; fee and term) | S | template | 01 #1, 03 #11, 04 #7, 02 | — |
| 1.5 | `channel_posts` law API (posted prices and orders) | S | engine | 04 #5 | 0.7 |
| 1.6 | Gazette Record (the engine posts the record into `notices`) | S | engine | 04 #4 | 0.7 |
| 1.7 | `read_register`; `read_law` with a version | S | engine | 05 #1-2 | — |
| 1.8 | Bench Act, Recusal Act, Graded Contract Enforcement, Contract Registry with clerk certification | S ×4 | template | 07 #10-12 #15 | 1.1 |
| 1.9 | **F1 bodyguards under harm** (guard's own body and weapon count) | M | engine | 06 F1 | — |
| 1.10 | Recipe placeholder in office duties (`{best:camp1}`) | S | engine | 02 | — |
| 1.11 | Analysis: market parser, money metrics (velocity, hoard, arrears), channel use, inert-law count | M | analysis | 01 #12, 03 #15, 04 §9, 07 §9 | 0.2, 0.7 |
| 1.12 | Private spec and scripted dry-run tuning (2 seeds) | M | spec | all | all of the above |

### Phase 2: the other regimes and full Private (≈ 40 days)

| # | Item | Size | Kind | Docs | World |
|---|---|---|---|---|---|
| 2.1 | Bank Charter; role-restricted procedure | M + S | template | 03 #8 #12 | Private |
| 2.2 | Counsel agency (`accuse`/`respond`/`appeal` for a client); `cases_of`; `withdraw_case` | M + S + S | engine | 07 #7-9 | Private, State |
| 2.3 | Licence `HOLDERS_FROM: roster` (membership-bound seats) | S-M | template / engine | 02, 03 #11 | Private, State |
| 2.4 | Quota preset (polity, compulsory) | S | template | 01 #4 | State |
| 2.5 | Armoury Act (fund, keys, FORGER) | S | template | 02, 06 F5 | State, Cooperative |
| 2.6 | F3 arrest mode; Warrant Act; F2 lawful spoils to the treasury; F13 hunger parity; Incident Register | M + S ×4 | engine and template | 06 | State, Cooperative |
| 2.7 | Penal Code `MODE: auto/trial/warrant` (clause variant) | S | template | 06 §9.3, 07 #14 | State, Private, Cooperative |
| 2.8 | Bill Certification; `expects` postconditions | S + M | template + engine | 07 #6 #15 | State |
| 2.9 | Wiretap as pull (`channels.surveillance`) | S-M | engine | 04 #10 | State |
| 2.10 | Registry Act, Archives Act, directory version log, `institution:` owner and office grants | M ×3 + S-M | template + engine | 05 #3 #5 #9 #10 | State, swap 8 |
| 2.11 | Cooperative store variant; Duty Roster; Mutual Credit; Charge (dues) | S ×3 | template | 01 #6, 03 #13 | Cooperative |
| 2.12 | Militia Roll + Muster Act; assembly `MOTION:` ballot hook | M + S | template | 06 F11, 04 | Cooperative |
| 2.13 | Commission preset (guard-only); Arbitration (`FORUM: arbiter`, an Arbitrators' Hall); Charge as subscription; wound bounty | S ×4 | template | 06 F8 F14, 07 #13, 04 #9 | Merchant |
| 2.14 | Security Licence | S | template | 06 F10 | swap 4 |
| 2.15 | One spec and dry-run tuning per world | M ×3 | spec | — | all |

### Phase 3: optional (≈ 30 days)

These are:
- edition delivery (M);
- channel `send` in the DM step (M);
- structured market offers (M);
- certified extracts (M);
- the `work` action (M);
- institution forts (M);
- F12 defence alert (M);
- F15 force metrics (M);
- kernel lending by institutions (M);
- engine exit notice (M);
- institutions as members (L, review 10 #13);
- fields shock (S-M);
- build to order (S);
- `set_channel owner` (S);
- `start.records` (S);
- seal and announce on directories (S);
- Chronicle Integrity (S);
- verified quotes in channels (S);
- Sponsored Label, Channel Defamation, Suspension, Press Freedom, Paper of Record (S each).

**Totals.** Phase 0 ≈ 16, Phase 1 ≈ 22, Phase 2 ≈ 40, Phase 3 ≈ 30 engineer-days. The first model run needs Phase 0 and Phase 1:
about **7-8 weeks** for one engineer.

## 6. Recommended first world: Private

**Why Private.**

1. **It builds what every other world reuses.** Phase 1 builds the SC core, Payroll, Licence, window sales, the court and
   channel ownership. These are the shared mechanisms of the State and Cooperative worlds, so most build days count twice.
2. **It has numbers.** 01 §5.1 and 03 §7 each give a Private spec sketch and a worked balance. 07 §7 gives the legal part.
   Integration found only one gap (A1 −6₱ a round, an intended decision).
3. **Its capture surface crosses subsystems.** The Anselm seat (§3.1) is food, law, press and counsel at once. That is the
   framework's interlock thesis, testable in one run.
4. **The alternatives are worse first worlds.**
   - **State** is closest to Millbrook but needs the most force code (F2, F3, warrants, armoury), and it is the most automatic:
     01 warns it may be the least interesting.
   - **Merchant** needs the least code but has the least institution in it, and it fails the money gate by design.
   - **Cooperative** depends on Haiku-heavy general-meeting dynamics that Millbrook never tested.
5. **What it does not need.** The bank (moneylender stand-in), counsel agency and membership-bound seats are all Phase 2.

**Dry-run gates** (scripted bots, 2 seeds, 24 rounds, `contracts.scripted: false`). All must pass before any model run.

| Gate | Pass condition |
|---|---|
| Zero attention, 3 rounds (every agent idle) | No missed meal. Every Payroll, Supply, Board, Service and Retainer leg and the levy run. No arrears. No treasury negative. Every firm's runway ≥ 12 rounds |
| Survival-action share (scripted "basic" bots and the first model run) | ≤ 30% of actions are harvest, hunt, withdraw, food transfers and food DMs, before and after the blight. Target 15-20% before |
| Money velocity | ≥ 0.10 a round (03's definition), voluntary share ≥ 15% by round 6 of a model run. Hoard ratio < 50% |
| Channel use | each counted channel ≥ 0.5 posts a round with ≥ 2 distinct authors by round 6; `market` and `notices` read (`channel_read`) by ≥ 40% of agents a round; any channel failing two seeds is cut |
| No inert laws | every start law previews non-empty; `law_effect.inert` = 0 at round 0; the Millbrook regression (an Offices Act `holders` amendment) is refused with the reseat message; a scripted short delivery yields a could-not miss, and an allowance cut yields a breach and then a case only when the bond is short |
| Blight sensitivity | deaths by round 24 differ between a scripted Director who releases S2 and one who hoards (decision matters, not only physics) |
| Force | an idle security firm's Service legs run, and with F1 a guarded client's defence rises in a scripted attack |
| Prompt budget | registers', contracts' and channels' state lines together ≤ 400 tokens for a farmer seat |

## 7. Decisions for the user

1. **First world: Private** (§6), then swaps 1 and 3, then State.
2. **Enclosure by Licence in every world.** Food institutions exist only because 2 of 3 forests are licensed. Accept this as a
   premise and report repeal as a finding?
3. **Contract notice enforced only by price** (an exit fee and a public breach), never by refusal. This is the engine's truth and
   the framework's "consequences, not prohibitions".
4. **`reseat` default: `refuse`** (07's recommendation) rather than `apply`.
5. **Firing does not end camp access in Phase 1.** A quitting miner keeps the seat. Run with this as an experiment, or wait for
   2.3?
6. **Window cap in Private** (15 copper-equivalent a round), so firms must sell to people.
7. **Penal Code per regime:** auto (Merchant), trial (Private, Cooperative), warrant (State).
8. **Media2 stays out.** Papers are channels; targeted editions are dropped outside S7.
9. **Merchant strike jobs stay off** (Commission is guard-only).
10. **Cooperative dues in labour and credit, not pennies** (§3.4).

## 8. Honest critique of the integrated design

**Complexity risk for small models.**
- A Haiku farmer in the Private world sees:
  - a Supply terms line;
  - a Service line;
  - a Licence;
  - three pushed channels and two pull headlines;
  - registers;
  - the food projection.
- That is more state than Millbrook's clipped view, which already hurt (03 §1 caveat).
- The design's defence is that defaults run, so the Haiku seats can be passive and the world still works. But then Haiku seats
  contribute little *divergence*, and the swapped seats carry the model comparison alone (1-2 per world: underpowered).

**Degenerate equilibria to watch.**
- **Passive autopilot.** Everything is automatic, so Opus seats may also do nothing but read. Decision-point counts per role are
  the alarm. If fewer than about 1 decision per Opus seat per 2 rounds, the defaults are too comfortable: shrink the runways.
- **DM-only economy.** Channels lose to DMs again, because the DM step stays free and in-round (04 §5.1). Validity rules are the
  only counter until Phase 3's channel `send` in the DM step.
- **Contract gas and hooks.** About 10 associations, each with member-wide hooks, may slow runs or produce surprising taxes on
  members' moves (03 §12.2).
- **Monopoly spiral (Private).** The Director raises prices, the poor drop subscriptions and hit Relief's starving-only floor,
  and the council of owners declines to widen Relief. That is a legitimate finding, but it can make the Private world a famine
  test rather than an institutions test. The blight sensitivity gate catches the extreme.
- **Force as scenery.** No agent has used unplaced violence in any run so far (06 §9.1). The State world's warrants may be the
  first unplaced use of force. The Merchant and Private force chains will probably stay idle.

**What we will not learn.**
- **Price discovery.** A 24-agent market with 1-2 posts a round is too thin.
- **Long-run institutional change.** 24 rounds allow a few amendments, not evolution. Every institution is seeded, so we learn
  how agents *use and capture* institutions, not how they *found* them.
- **Clean regime effects.** Each regime runs different code paths (Quota vs Supply; warrant vs auto Penal Code). Regime
  differences confound "who owns the stage" with "which template ran". The single-domain swaps are the partial remedy, and the
  remedy only works if each swap runs at least 2 seeds.
- **Model-tier effects within a role.** One or two swapped seats per world give anecdotes, not estimates.
- **Food as money.** Food has no unit value (`kernel.py:316-319`), so food cannot back the coin and the granary does not count in
  P. Every regime's food price is contractual. Adding `unit_values.food` is a different experiment.
