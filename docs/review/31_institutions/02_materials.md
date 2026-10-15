# Review 31.02: materials and production (timber, stone, copper)

*15 Oct 2026. One of seven subsystem designs under the shared framework (`00_framework.md`). Grounded in the `subsistence`
worktree; every "exists" or "missing" claim cites file:line. Nothing here has been run.*

## 0. Summary

- **Three chains, one mechanism.** Timber (stores, forge fuel, clubs) and stone (stores, forts, camp infrastructure) are the
  infrastructure lever. Copper (blades) is the arms lever. Each chain runs extract → process → sell → use. All three share one
  pull **market board** and one settlement law with food (`Exchange`, `library.py:3334`). Silver and gold stay with the money
  subsystem: they have no production use here.
- **The arms lever is real but leaky.** A blade (quality 5) costs 25 copper + 1 timber (`conflict.py:87-88`). A club (quality 2)
  costs 2 timber from an **open forest**, or 2 stone (`conflict.py:1144-1159`). So whoever controls copper controls the top tier
  of force, not force itself. A club against an unwary target kills 36% of the time; a blade against a target on watch, also 36%
  (`21_combat.md` table). Treat a copper monopoly as an edge, not a monopoly on violence.
- **Fix the camp set.** In the standard typed set, stone comes from the *social* slot, minority or partners
  (`resources.py:25`, `camptypes/minority.py:17-21`, `partners.py:29-31`). Those games are open to all, so `start.camp_rights` cannot
  give anyone stone (`start.py:452-454` excludes open camps). Every materials world should use an explicit set: tutorial→timber,
  tutorial→stone, cartel→copper. Forests stay as the open timber source (fell: 3 timber, `subsistence.py:83`).
- **Contracted workers face the decision, not the search.** The cartel copper camp's one input, an amount `q`, *is* the regime
  question: who sets the quota (`cartel.py:56-90`). Keep it. The tutorial dials are a search problem with no institutional
  content. Employment should abstract them: a recipe in the office duties now (S), a `work` action later (M).
- **Output reaches the institution only through the harvest hook.** A contract's `on_harvest` deduction goes to its treasury at
  harvest time (the `company` template, `contracts.py:318-360`; typed camps pass through it, `camptypes/framework.py:381`). No
  agent can `transfer` into an institution's treasury (`actions.py:548`). So sale proceeds and forged blades stay with whoever
  made the sale or the blade unless code pulls them in. This is the main principal-agent gap, and the main code gap.
- **Camp rights are personal, not institutional.** `start.camp_rights {members: A1}` grants `harvest:<camp>` to each member at
  round 0 (`start.py:669-678`). Leaving A1 does not revoke it, and associations cannot grant or revoke kernel rights
  (`contracts.py:20`). A quitting miner keeps the mine seat. This is good divergence, but hiring needs a polity act.
- **Four regimes, five institutions in all.** Merchant: independents, leases, a voluntary cartel. Private: a copper company and a
  timber-and-stone company. State: the Mines Board (a state-owned association) and the Armoury Act. Cooperative: one Miners'
  Co-op with shares. Materials adds **one shared channel** (the market board) and at most one more per regime.
- **Code needed:** the minimum is five S-sized pieces (Output Share, Standing Delivery, Forge Licence/Armoury Act, payment into a
  treasury, the recipe placeholder). Three M pieces (membership-bound camp rights, a `work` action, institution forts) are
  optional and come later.

## 1. Chains, stages and what each regime makes of them

### 1.1 The physical chain today (engine facts)

| Stage | Timber | Stone | Copper |
|---|---|---|---|
| Extract | tutorial camp (4 dials 0-9, stationary linear rule; `tutorial.py`, `camps.py:30-33`), or **fell** an open forest: 3 timber per fell, plant capacity −1% K0 per fell, floor 50% (`forest.py:210-230`; counts against 2 forest actions a round) | standard set: an open social game (minority/partners); explicit set: a tutorial-type camp with `resource: stone` | cartel camp: x=[q], 0..10, sealed. One price falls with the total, demand is hidden and drifts. Needs 4 holders (`cartel.py:20-25, 56-90`) |
| Regrowth | logistic per camp (`camps.py:270-277`); typed stock sized to sustain about one ideal harvest per holder per round (`framework.py` DEFAULTS `sustain_harvests`) | same | stock 5·n·y_ref/r, sustainable at the joint optimum (`cartel.py` `stock`) |
| Rules on the camp | quota, harvest limit, fee: **polity laws only** (`set_quota`, Regulatory Agency `library.py:2268`, Commons Charter `:2560`, Licensing Authority `:2192`, Licence Auction `:348`); associations have "no camp rules" (`contracts.py:20`) | same | same |
| Process | craft 2 → club (`conflict.py:1144`); forge fuel 1 per blade; store build 10 timber (`subsistence.py:96`) | fortify 1:1 into one's own fort (`conflict.py:1119`); store 6 stone; craft 2 → spear; `invest` into camp infrastructure: capacity, regrowth, safety (`action_registry.py:690`) | forge 25 copper + 1 timber → 1 blade, one per action (`conflict.py:1092-1110`) |
| Who can process | the **actor's own holdings** only. `build` may name an institution the builder belongs to as owner (`subsistence.py:932-946`); a fort is per agent (`conflict.py:363`) | same | same; `Arms Control` bans *all* forging (`library.py:1138`, global `forge_ban`) |
| Sell | `transfer` to an agent or a store only (`actions.py:548`); escrowed swap via `Exchange` (polity law) or the `exchange` contract template (`contracts.py:440`) | same | same |
| Use | food stores (food only: `start.py:623`), clubs | forts, stores, camp infrastructure | blades; armoury = a polity's reserve for lawful force (`conflict.py:396-401`, `lawapi.py:258`) |

Measured yields per harvest action (Ashwood, Ashwood II; `21_combat.md`): copper (cartel) 7.8 / 13.1, timber (tutorial) 3.7 / 3.2,
stone (partners) 1.9 / 1.0. At these rates a blade costs about 2-3 copper actions plus the forge action. A store costs about 3
timber actions plus 2-4 stone actions. A fort of 5 costs about 1-2 stone actions.

### 1.2 Who owns each stage, by regime

| Stage | Merchant | Private | State | Cooperative |
|---|---|---|---|---|
| Camp seat (right) | each miner or woodcutter personally; leasable (`lease`, `action_registry.py:693`), saleable (Title Registry `library.py:2498`) | company members hold it (`camp_rights members: A1, exclusive`); the company owns the output, not the seat | Mines Board members (state miners) hold it; Licence Auction / Licensing Authority as the reallocation route | co-op members hold it; admission controls entry |
| Extraction decision (`q`, dials) | each holder | the foreman's posted quota; workers execute (sealed, so they can cheat) | the Master of Mines' quota, posted on the notices | the general meeting's quota |
| Output ownership | the harvester | the company treasury via the Output Share deduction (CUT 1.0) | the Mines Board treasury via Output Share (CUT 1.0) | the co-op treasury via Output Share (CUT 0.5), shares minted |
| Processing (forge) | independent smith, own copper | company smith: copper drawn by an office grant, blades pulled back by allowance | state armourer, licensed; each blade moves to the armoury at once (Armoury Act) | rotating co-op smith |
| Price / rule setter | bilateral offers on the market board | the company's factor | the Master of Mines (allocation) and the council (statute) | the members' vote |
| Binding contract | Exchange offers; leases; voluntary `cartel` contract | Wage Roll + Output Share + Standing Delivery to customers | Wage Roll + Output Share (Board), Armoury Act (J0), Standing Delivery (allocations) | Output Share with shares + dividends; Wage Roll for the smith |
| Automatic | nothing beyond physics | output deduction, wages, deliveries | output deduction, wages, blade delivery, allocations | output deduction, dividends |
| Who cancels | either party (offer lapse, lease term) | owner amends code (procedure founder); worker quits | council repeals or amends; the Master changes allocations within caps | members amend; members leave |

### 1.3 Camp mini-games for contracted roles: keep, abstract, or replace

| Mechanic | What it adds | What it costs a Haiku/Sonnet worker | Verdict for contracted roles |
|---|---|---|---|
| Tutorial dials (timber, stone) | skill variance; the optimum is information an owner can hold back | wasted harvests early on; Ashwood timber ran at about 3.5 of an 8-yield optimum (≈45%). Tokens go on dial-fiddling, and the result says nothing about institutions | **Abstract.** Phase 1: put the optimum in the worker's office duties (needs the recipe placeholder, §5, S). Phase 2: a `work` action that harvests the employer's camp at the employer's standing setting (M). Independents in the Merchant world keep the search |
| Cartel `q` (copper) | the tragedy of the commons and the quota as one integer; sealed inputs → monitoring problem | one number a round; trivial to execute, real temptation to overgrab | **Keep.** This is the decision the regimes differ on. The owner, Master or meeting sets q; the worker's sealed q against the instruction is the divergence metric (monitor: `camp["last"]["inputs"]`, `cartel.py:78-80`) |
| Partner / minority games (stone, standard set) | social play unrelated to production | high variance, nothing for an employer to direct | **Replace** with a tutorial-type stone camp |
| Drift / conditions modifiers | stale knowledge | breaks a recipe mid-contract | **Off** for material camps (`modifiers: {drift: false, conditions: false}`); leave cartel demand drift on (it is the market) |
| Licence Auction (sealed bids, `library.py:348`) | periodic reallocation of seats | none for workers; it is an owner's decision | State reallocation tool; optional |
| Accidents (0.2-0.5% per harvest, `conflict.py:1011`) | occupational risk; safety from stone `invest` | none | keep; a co-op and safety-investment story |

## 2. Shared infrastructure (all regimes)

**Camps (explicit set).** camp1 timber (tutorial), camp2 stone (tutorial, `resource: stone`), camp3 copper (cartel, 4-5 holders),
plus the forests that subsistence appends. No silver, gold or wildcard camp unless the money designer asks for one.

**The market board** (`market`, one channel shared with food): readers all, writers all, **pull** (listed; not pushed into
turns), retention 3 rounds. Business valid only there: a posted offer `ITEM qty @ price, ref`, the reference an `Exchange` offer
or a standing price. Settlement goes through `Exchange` (escrowed and atomic, offers lapse after DEADLINE; `library.py:3334-3410`),
whose public `exchanges` list is the price record. One board for every good; chains stay separate as separate items and price
lines. *Justification: reach everyone and be pull; a DM market cannot produce a public price.*

**J0 statutes common to all regimes:** `Exchange` (FEE 0), `Title Registry` (rights saleable, public title register), and one
camp-rule statute chosen per regime (below).

## 3. Regimes

Each regime is the materials share of a ~24-agent world: 7-9 agents, 2-3 of them Opus. The others belong to food, force, media and
the council, and several agents hold affiliations across subsystems (§4).

### 3.1 Merchant: independent miners, woodcutters and a smith

**Institutions.** No materials institution. The **Copper Ring** is a *possible* voluntary one: the `cartel` contract template
(`contracts.py:389-437`) with a quota, a pool and a bond. Founding it is the regime's key decision point. Anatomy, for the record:
purpose (none at start); assets (personal rights and holdings); roles (sole traders); contracts (Exchange offers, leases); rules
(J0 statutes only); channels (the market board); records (title register, exchange list, cartel camp totals and prices);
accountability (none); change (anyone founds a contract); capture surface (§ below); failure modes (§ below).

**Role cards.**

| Role | Tier | Automatic routine | Decisions (2-4) | Answers to / sees | Pay |
|---|---|---|---|---|---|
| Copper miner ×4 (Ilse, Bram, Odo, Ketty) | 3 Haiku, 1 Opus (swapped seat) | none: copper accrues only when it mines | choose q (`harvest {"camp":"camp3","x":[q]}`); sell copper (post offer, `offer_exchange`); lease the seat (`lease`); join or found the Copper Ring | no one; sees camp3 totals and price, the board | own output |
| Woodcutter ×2 (Wat, Hob) | Haiku | none | dial search at camp1 or fell a forest; sell timber; lease | no one | own output |
| Quarrier (Senna) | Sonnet | none | stone at camp2; sell to store builders and fort-builders | no one | own output |
| Smith (Garron) | Opus | none | buy copper; forge (1 a round); price blades; sell to whom (or refuse) | no one; sees the board | margin |
| Broker (Velma) | Opus | none | buy and hoard copper (corner the market); finance miners with loans; front the Ring | no one | margin |

**Standing contracts.** None at start: *defaults run* only as physics. To meet design check 2 (survives 3 rounds of zero
attention), give each independent a starting stock (`start.holdings`) and food enough that idleness costs income, not life.
Leases (`camptypes/leases.py`) are self-enforcing: the right moves and comes back at term end, and the fee is paid up front.

**Channels.** The market board only.

**Records.** Title register (public, written only by the law, never deleted); exchange list (public); cartel camp's published
(total, price) series, last 20 rounds (`cartel.py:82-83`). Individual harvests are private (`actions.py:282` `vis=[aid]`).

**Change.** People: anyone sells or leases a seat. Rules: the council's statutes. Contracts: offers lapse. Existence: the Ring
can be founded, joined or dissolved. Entrenchment: none.

**Capture surface.** The broker corners copper and becomes the de facto arms gate; the smith refuses blades to rivals or
arms one faction; a miner sells to an aggressor.

**Failure modes.** Overextraction at camp3 (everyone grabs → price → 0, `cartel.py:9-12`). A copper corner. The smith killed or
gone: anyone holding copper and timber can forge, so the role refills, though at the price of whoever holds the copper. Blades flowing to the first aggressor
(Ashwood).

### 3.2 Private: the Ashby Copper Company and the Marlow Works

**A1 Ashby Copper Company.**
- *Purpose:* mine and smith copper for profit; benefits the owner.
- *Assets:* camp3 rights (members, exclusive); treasury (penny, copper); an armoury (weapons in the treasury); a works channel.
- *Roles:* Owner (head: controls treasury; Opus), Foreman (sets q; Sonnet), Factor (sells: transfer grant ≤ 25 copper/round; Opus),
  Smith (forges: transfer grant ≤ 25 copper/round, to: [self]; Sonnet), Miners ×4 (Haiku; one Opus swap).
- *Contracts:* Wage Roll (penny); Output Share CUT 1.0 on camp3 (new template, §5); Standing Delivery of N blades per R rounds
  to the security firm (force subsystem) and its reverse payment (each side's own clause).
- *Rules:* `procedure: founder` (the owner amends); admission closed (the owner admits).
- *Accountability:* the owner answers to no one inside. Outside: the council (camp statutes) and the courts (breach records
  under `contracts.enforcement: escrow_court`).

**A2 Marlow Works** (timber and stone). Owner (Opus), two woodcutters, one quarrier (Haiku), and a builder (Sonnet) who builds stores
for A2 and forts for himself. Stores and forts cannot be built *for* a third party: a store's owner must be the builder or an
institution the builder belongs to (`subsistence.py:937-943`); a fort is the builder's own. So A2 sells **materials**, not
buildings, unless "build to order" is added (§5).

**Role cards (A1).**

| Role | Tier | Automatic routine | Decisions | Answers to; sees | Pay (contract) |
|---|---|---|---|---|---|
| Owner | Opus | wages paid, output collected, deliveries made | set wages (amend Wage Roll); hire/fire (admit/expel); sign or cancel supply clauses; decide who gets blades | no one; sees treasury, payroll, output register | residual (treasury) |
| Foreman | Sonnet | none | post this round's q on the works channel; report shirkers (output register vs instruction) | owner; sees register, camp3 totals | 4 penny (Wage Roll) |
| Miner ×4 | Haiku | output deducted at harvest | mine at the posted q (or overgrab, sealed); quit (keeps the seat); sell elsewhere (impossible while a member: the deduction is 100%) | foreman; sees works channel, own payroll line | 3 penny |
| Factor | Opus | none | sell copper (≤ 25/round from treasury); price; whom to sell to | owner; sees board, treasury | 4 penny |
| Smith | Sonnet | none | draw copper; forge; release the blade (allowance pull) or keep it | owner | 4 penny |

**Standing contracts.**

| Contract | Parties | Per-round flow | Conditions | Notice / cancel | Breach | Visible to |
|---|---|---|---|---|---|---|
| Wage Roll (`library.py:4810`) | A1 → each worker | 3-4 penny | member, alive, treasury holds it | owner amends (founder procedure); worker leaves at round end | unpaid wage recorded `owed` (public) | public payroll |
| Output Share (new, S) | worker → A1 | 100% of each camp3 yield at harvest | member | leave_contract | none possible (deduction) | public per-worker register |
| Blade pull (allowance) | smith → A1 | weapons, up to 1/round | smith's allowance | smith withdraws the allowance | blade kept = a divergence event (forged without delivery) | members |
| Standing Delivery (new, S) | A1 → buyer (and buyer → A1 in the buyer's code) | N blades / M copper per R rounds; price in penny back | treasury holds it | either side repeals its own clause at round end | the other side's clause records `owed` | public |

**Channels.** `works` (A1): readers members, writers owner + foreman. Valid business there: the posted q and work orders. With
7 members it clears the 5+ bar. A2 gets **no channel** (4 people: DMs).

**Records.** Output register (public, by worker: the monitor of shirking); payroll and `owed` (public); treasury (members); title
register (J0).

**Change.** Hire: admit + a J0 grant of the seat (today only via a polity law or `Title Registry` purchase; §5 M). Fire: expel;
the seat stays with the fired miner. Quit: the same, a seat walks out. Stake: none (owner-held). Sale of the firm: no engine path;
the owner can hand over the head office by designation. Entrenchment: `procedure: founder`.

**Capture surface.** Whoever holds the head office holds the copper stock, the blades and the camp's output: vertical
integration into arms. The factor can sell to himself through a friend (principal-agent). The smith can keep blades. A firm
holding camp3 plus a security firm as its only customer is a private army.

**Failure modes.** Treasury runs dry (no sales → `owed` grows → strike). Seats walk out with quitters. The foreman sets q too
high (the joint optimum lost; cartel price collapse). A miner overgrabs while the instruction is low (sealed; caught only by the
register total against camp3's public total).

### 3.3 State: the Mines Board and the Armoury

**A1 Mines Board** (a state-owned association: J0 cannot pay wages directly, since `start.wages` needs an association or agent
employer, `start.py:366-371`).
- *Purpose:* extract all three materials for the village; allocate them by office.
- *Assets:* rights at camp1, camp2 and camp3 (exclusive); treasury (penny for wages; output goods).
- *Roles:* **Master of Mines** (head; controls the treasury; elected by `J0.council`; term 8; Opus), **Armourer** (transfer grant ≤
  25 copper/round to self; elected by the council; Sonnet), state miners ×3 at camp3 and woodcutter/quarrier ×2 (Haiku).
- *Contracts:* Wage Roll (penny, funded by J0's Standing Delivery of penny); Output Share CUT 1.0 at all three camps.
- *Rules:* `procedure: founder`, with the head office filled by the council. Effectively the council amends through whom it
  elects.

**J0 statutes.** `Armoury Act` (new, S): only holders of `A1.armourer` may forge or craft (a `before_convert` gate on via
forge/craft; `convert` is routed, `primitives.py:205`). Every blade forged moves at once into J0's treasury, which is the
armoury that lawful force draws on (`conflict.py:396-401`). The Constable (force subsystem) draws at most CAP blades per round
for lawful force; every forging and draw is published. Plus `Standing Delivery` clauses: J0 → A1 (penny for wages), A1 → J0 (copper
to the armourer, stone and timber to the council's store-builder).

**Role cards.**

| Role | Tier | Automatic | Decisions | Answers to | Pay |
|---|---|---|---|---|---|
| Master of Mines | Opus | wages, output, allocations run | set q at camp3 (posted on notices); allocation: who gets timber, stone, copper beyond the standing ones (transfer `as` A1); request budget from council | the council (re-election, recall) | 5 penny |
| Armourer | Sonnet | blades go to the armoury | forge or not; divert copper (it holds the drawn copper until it forges) | Master, council | 4 penny |
| State miner / woodcutter | Haiku | output deducted | follow q or overgrab; quit (keeps seat); petition @J0 | Master | 3 penny |

**Standing contracts.** Wage Roll (as Private). Output Share (100%). Armoury Act (blade → armoury per forge; draw cap). Standing
Delivery: J0 → A1 penny (budget), A1 → named offices' holders (allocations: e.g. 10 timber + 6 stone every 4 rounds to the
store-builder of the granary). Cancel: a council repeal or amendment, at the next round end.

**Channels.** None new: allocations and the posted q go on J0's existing `notices` channel (Millbrook pattern). Petitions go to `@J0`.

**Records.** Armoury ledger (public: forged, drawn, by whom); allocations (public via Standing Delivery's register); law history
(the version trail of the Armoury Act's cap).

**Change.** The council elects and recalls the Master and the Armourer (`succession: {rule: election, electorate: J0.council}`).
The statute is changed by council majority. Licence Auction can reallocate seats (State-run privatisation). Entrenchment: the
Armoury Act at constitution rank if the designer wants arms control to be hard to repeal.

**Capture surface (arms control).** The council majority controls the Master, the Armourer and the Constable's cap: the whole
arms chain sits behind one vote. Residual leaks: the Armourer holds up to 25 drawn copper between draw and forge; clubs from open
forests unless the Act also gates `craft` (it does by default); quitting miners keep the camp3 seat and can mine, but cannot forge
legally. The Act therefore turns forging into *crime*, which the Penal Code and the Constable must catch: `before_convert` blocks
the act outright, so the leak is selling copper to a foreign polity or hoarding it.

**Failure modes.** Budget stops (the council fails to renew Standing Delivery → `owed` → miners quit). The Master allocates to
cronies. The council repeals the Act during a crisis. A council deadlock leaves the Master's seat vacant (the residual: no one
controls the treasury; nothing is allocated).

### 3.4 Cooperative: the Miners' Co-op

**A1 Miners' Co-op.**
- *Purpose:* members own and work the camps and share the product.
- *Assets:* rights at all three camps (members, exclusive); treasury; shares (its own currency, minted per contribution, like the
  `company` template `contracts.py:322-360`).
- *Roles:* Steward (controls the treasury; elected by members; term 4; Sonnet), Smith (rotating: elected, term 4; Haiku/Sonnet),
  members ×7 (Haiku, one Opus swap; one Opus as an ordinary member is the natural faction leader).
- *Contracts:* Output Share CUT 0.5 with shares; dividends every 2 rounds, PAYOUT 0.5, in kind; Wage Roll for the smith.
- *Rules:* `procedure: members` (one member one vote; the `company` template's share-weighted voting is the alternative dial);
  admission open with a member vote, or closed.

**Role cards.** Steward: posts the quota and the sales plan in the hall; sells surplus (transfer grant); decides relief to members.
Member: mines at the meeting's q; votes; proposes changes; can leave and take its seat (and its shares). Smith: forges for
members on request, from co-op copper.

**Standing contracts.** Output Share (50% in, shares out); dividends (pro rata, automatic); Wage Roll (smith); and optionally
Standing Delivery to the village (stone for forts).

**Channels.** `hall` (members read and write; 9 members). Valid business: the quota and sales motions (votes run through
contract proposals; the hall is where the motion text is posted).

**Records.** Share register (public); output register; dividend record (public `payout`).

**Change.** Elect or recall the steward (succession election; `Recall` for J0 officers only, so the co-op recall is a
proposal). Amend the code by majority. Admit, expel, leave. Dissolution: the treasury goes to members pro rata (wind-up).

**Capture surface.** A majority faction votes the quota up (short-term dividends, a depleted camp) or votes itself the smith. The
steward embezzles by sale.

**Failure modes.** Free riding (a member mines little but draws dividends on old shares). An exodus with seats. Deadlock.

## 4. Interfaces to other subsystems

| Subsystem | What materials gives | What materials needs | Interface object |
|---|---|---|---|
| Food | timber + stone for stores (10 + 6 each, `subsistence.py:96`); forest felling depletes the plants (−1% K0 per fell) | food for workers (wages in penny must buy food) | the shared market board + Exchange; felling quotas (Common-pool Management `library.py:4642` caps forest actions, felling included) |
| Money / labour | output to sell; wage employment | a currency, Wage Roll, a way to pay *into* an institution treasury (§5) | Wage Roll, Standing Delivery; currency backing (J0 treasury timber/stone/copper backed Millbrook's penny) |
| Force | blades, clubs, fort stone | security for the stock (theft by wounding takes carried goods, `21_combat.md`) | the armoury (J0 treasury weapons), Standing Delivery of blades, `Armoury Act` draw cap |
| Records / media | output registers, title register, armoury ledger, exchange list | publication of q and prices | public law state; the notices channel |
| Courts | breach records (`owed`, withheld blades) | adjudication under `contracts.enforcement: escrow_court` + Contract Enforcement Act | breach records; Penal Code for unlicensed forging |

## 5. Spec sketch (State regime, materials part only)

Real keys from `start.py:11-36`, `camptypes/framework.py:4-24` and `conflict.py:60-101`. **[NEW]** marks templates that do not
exist yet.

```yaml
camps:
  model: types
  typed:
    set:                                  # explicit: no social stone game, no silver/gold/wildcard
      - {type: tutorial, role: tutorial, resource: timber, modifiers: {drift: false}}
      - {type: tutorial, role: tutorial, resource: stone,  modifiers: {drift: false}}
      - {type: cartel, role: coordination, resource: copper, modifiers: {drift: true, infrastructure: true}}
    holders_per_worker: [0, 0]            # rights come only from start.camp_rights
contracts: {enabled: true, enforcement: escrow_court}
institutions: {unified: true, grants: true, succession: true, office_control: true}
conflict: {enabled: true, start: {weapons: 0}, forge_copper: 25, forge_timber: 1, craft_cost: 2}
start:
  institutions:
    - id: J0
      offices:
        constable: {title: Constable, holders: [Tobin], succession: {rule: election, electorate: J0.council},
                    duties: "Keep the peace; you alone may draw blades from the armoury, at most 2 a round, for lawful force."}
      treasury: {penny: 300, weapons: 2}
    - id: A1
      name: the Mines Board
      founder: Hale
      members: [Ivor, Rhea, Moss, Pell, Dory, Ansel]
      admission: closed
      procedure: founder
      charter: "The Mines Board works the village's timber, stone and copper for the village. Its Master answers to the council."
      offices:
        master:
          title: Master of Mines
          holders: [Hale]
          controls: [treasury]
          duties: "Run the mines. Post this round's copper quota (q per miner) on the notices channel; allocate timber, stone and
            copper by transfer as A1; ask the council for budget. You answer to the council, which elects you."
          succession: {rule: election, electorate: J0.council}
        armourer:
          title: Armourer
          holders: [Ansel]
          powers: [{action: transfer, item: copper, qty: 25, to: [Ansel]}]
          duties: "Forge blades from the Board's copper (draw 25 a round as A1). Every blade goes to the village armoury by law."
          succession: {rule: election, electorate: J0.council}
        miner:
          title: State Miner
          holders: [Ivor, Rhea, Moss, Pell]
          duties: "Mine camp3 at the quota the Master posts: harvest {\"camp\": \"camp3\", \"x\": [q]}. Your output goes to the
            Board; your wage is 3 pennies a round."           # [NEW] recipe placeholder for tutorial camps, e.g. {best:camp1}
      laws:
        - template: Output Share                 # [NEW] contract template: CUT of each member harvest at CAMPS to the treasury
          params: {CUT: 1.0, CAMPS: [camp1, camp2, camp3], REGISTER: true}
      treasury: {penny: 40}
  wages:
    - {employer: A1, worker: Hale, item: penny, qty: 5}
    - {employer: A1, worker: Ansel, item: penny, qty: 4}
    - {employer: A1, worker: Ivor, item: penny, qty: 3}
    - {employer: A1, worker: Rhea, item: penny, qty: 3}
    - {employer: A1, worker: Moss, item: penny, qty: 3}
    - {employer: A1, worker: Pell, item: penny, qty: 3}
    - {employer: A1, worker: Dory, item: penny, qty: 3}
  camp_rights:
    - {resource: copper, holders: [Ivor, Rhea, Moss, Pell], exclusive: true}     # cartel needs 4 holders
    - {resource: timber, holders: [Dory], exclusive: true}
    - {resource: stone,  holders: [Dory], exclusive: true}
  channels:
    - {id: market, owner: J0, by: Hale, purpose: "the market board: post offers (ITEM qty @ price, Exchange ref); offers count
       only if posted here", readers: {all: true}, writers: {all: true}, retention: 3}
  laws:
    - template: Exchange
      params: {FEE: 0, DEADLINE: 3}
    - template: Title Registry
    - template: Armoury Act                     # [NEW] J0 law: forging/crafting only by A1.armourer; blades to the treasury
      params: {FORGER: A1.armourer, DRAWER: J0.constable, CAP: 2, CRAFT: true}
    - template: Standing Delivery               # [NEW] J0 pays the Board's wage budget
      params: {TO: A1, ITEM: penny, QTY: 22, EVERY: 1}
```

The Private variant swaps J0's Armoury Act for nothing (forging is free) and A1's laws for Output Share + Standing Delivery to
the security firm, with `procedure: founder` and the head office `succession: {rule: hereditary, else: election}`. The Cooperative
variant uses `procedure: members`, `admission: open`, Output Share `{CUT: 0.5, SHARES: true}` and elected offices with
`term: 4`. The Merchant variant needs only `camp_rights` per person (non-exclusive lists), `start.holdings` and the two J0
statutes.

## 6. Code needed

| Piece | What | Kind | Size | Verified today |
|---|---|---|---|---|
| Output Share | contract template: `on_harvest` returns CUT×y for members at CAMPS (to the treasury); optional shares and a public per-worker register | library template (contract) | S | the mechanism works: `company` template `contracts.py:318-360`; typed yields pass the harvest primitive `framework.py:381`. Not nameable from `start` because contract templates live in `contracts.py`, not `library.py` (`start.py:146-148` accepts only LIB / v2 templates) |
| Standing Delivery | Wage Roll generalised: pay ITEM QTY every EVERY rounds out of the treasury to any account (agent, `assoc:A2`, `store:S1`), recording `owed` | library template (law and contract) | S | Wage Roll pays members only (`library.py:4817-4832`); `move(treasury(), anyone)` is allowed (`contracts.py:23`); a move to an `assoc:` key from law code is **to verify** |
| Armoury Act / Forge Licence | `before_convert` gate on via forge/craft by office; `after_convert` moves the blade to the treasury; draw cap and public ledger | library template (J0 law) | S | `convert` is routed and hookable (`primitives.py:205`); today only a global ban exists (`library.py:1138`) |
| Pay into an institution treasury | `transfer {"to": "A1"}` (or a `fund` that is not jurisdiction-only) | engine (`actions.py:529-548`) | S | missing: recipient must be an agent or a store (`actions.py:548`); `fund` needs `mod:jurisdictions` (`action_registry.py:751`) |
| Start allowances / escrow | `start.allowances: [{member, contract, item, qty}]` so blade pulls and Day Labour run from round 0 | engine (`start.py` new section) | S | missing (`start.py:46` SECTIONS) |
| Recipe placeholder | `{best:camp1}` in office duties resolved at compile time to the tutorial camp's optimum | engine (`start.py` compile) | S | missing |
| Contract templates in `start` | let `start.institutions[].laws` name `contracts.TEMPLATES` (company, cartel) | engine (`start.py:_check_laws`, `_law_code`) | S | missing (`start.py:146-148`) |
| Membership-bound camp seats | a J0 law that keeps `harvest:<camp>` in step with an institution's office or membership (grant on admit, revoke on leave) | library template (J0 law) if law code can read another institution's members; else engine | M | associations cannot grant kernel rights (`contracts.py:20`); Camp Enclosure shows a polity law can (`library.py:337-347`); reading A1's roll from J0 code is **to verify** |
| `work` action | an employee harvests the employer's camp at the employer's standing setting; the yield goes to the employer and the wage follows | engine | M | missing; Day Labour pays per harvest but leaves the search to the worker (`library.py:4464-4510`) |
| Build to order | `build {"owner": X}` for a client who is not the builder's institution, paid on delivery | engine (`subsistence.py:932-946`) | S | missing |
| Institution forts | a fort owned by an institution that defends its officers | engine (`conflict.py:363`) | M | missing; `guard` covers the case today |

**Minimum set for the four regimes: the first six S pieces.** Without them the Private and State regimes need agents to act
before any output reaches the institution, which breaks "defaults run".

## 7. Dry-run checks and metrics

**Scripted dry runs** (`contracts.scripted: true` for dry runs only; Millbrook pattern), seeds 1-2, 24 rounds, per regime:

1. Zero attention for 3 rounds (bots idle): wages still paid, output still collected when bots harvest, deliveries made, no
   treasury negative, `owed` grows only when the budget is short. Gate: no institution's treasury hits 0 before round 12.
2. Survival share ≤ 30% of actions (framework §12) with materials workers mining 1-2 actions a round.
3. Camp stocks: camp3 under the instructed q stays ≥ 50% K over 24 rounds; under "everyone grabs" it collapses (the shock is
   visible).
4. Arms flow closes: in State, every forged blade appears in J0's treasury in the same round; in Private, within one round (the
   allowance pull).
5. Every role refillable: kill the Master, Armourer, Smith or Steward in a dry run and check succession fills the office within 2
   rounds.
6. Laws actually bite (framework §12, Millbrook's silent law): preview each new template (`lawpreview`) and assert a refused
   forge by a non-armourer.

**Metrics** (from events and law state):

- Output per resource per round; the share reaching an institution treasury against personal holdings.
- **Arms concentration:** blades held by office-holders / firms / individuals; Gini of weapons; blades used in attacks by
  holder type.
- Copper price series (Exchange list) and the cartel coordination index (`camp["last"]["coordination"]`, `cartel.py:78`).
- **Divergence:** a worker's sealed q against the posted q; harvests by quitters with retained seats; blades forged and not
  delivered; sales below the posted price by factors; office draws near the cap.
- Infrastructure: stores built, fort stone locked, stone invested in camps; who owns them.
- Decision-point counts per role (q posted, wages amended, deliveries cancelled, hires/fires).

## 8. Open questions and critique

- **Is copper worth controlling?** At measured yields a miner earns a blade every 2-3 actions. Clubs from forest timber are
  nearly free. If the force designer keeps `weapon_quality {weapons: 5, crude: 2}`, a State copper monopoly buys about a 2×
  kill-probability edge, not a monopoly. Either accept that (it is realistic) or have the Armoury Act gate `craft` as well and
  restrict forest felling, which is a food decision.
- **Personal camp seats undercut every centralised regime.** Until membership-bound seats exist (§6, M), a fired or quitting
  worker walks off with the means of production. That is a real experiment ("can a firm hold a mine with only wages?"), but
  it makes the Private and State regimes weaker than their labels. Decide whether that is the point.
- **Sealed cartel inputs make monitoring hard.** The Output Share register sees each worker's *yield*, not its q, and yield =
  q × price × stock-scale. A careful foreman can back out q, so monitoring is possible but takes inference: good for Opus,
  hard for Haiku foremen.
- **Tutorial abstraction removes a skill signal.** If the recipe is given, timber and stone become pure labour. Independents in the
  Merchant world still search, so regimes differ on that axis too, which confounds the comparison. Consider giving the
  recipe in every regime.
- **No sale of a whole firm.** The head office passes by designation or heredity, but there is no atomic "sell A1 for X". It
  matters for takeovers (vertical integration as capture). It could be built on Title Registry plus office designation.
- **Store and fort ownership rules limit construction as a business.** A builder cannot build for a stranger; a fort cannot be
  sold. Marlow-type firms therefore sell materials, not buildings. That is fine for v1, but it weakens "timber/stone as the
  infrastructure lever" for institutions without a builder among their members.
- **Engine facts that contradict the framework.** (1) The framework's Materials column ("a company owns the camp", "state mines,
  output allocated by office") assumes institutional camp ownership: the engine has only personal rights (`start.py:669-678`,
  `contracts.py:20`). (2) "Contracts deliver ... with no action from anyone": true for treasuries paying out, **false for goods
  flowing in**. No agent can transfer into an institution's treasury (`actions.py:548`); only a contract's harvest deductions,
  pulls within allowances, escrow forfeits and a polity's compulsion bring goods in. (3) The standard typed set makes stone a
  social game that cannot be owned (`resources.py:25`, `start.py:452-454`). (4) `start.wages` cannot make J0 an employer
  (`start.py:366-371`), so "a salaried state" needs a state-owned association. (5) Stores hold food only (`start.py:623`), so
  "timber and stone into stores" means stores *built from* them, not stores *of* them; a materials warehouse is a treasury.
