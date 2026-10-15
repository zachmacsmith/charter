# Review 31.01: the food chain as institutions

*15 Oct 2026. Subsystem design 01 of 07 under the shared framework (00_framework.md). It covers produce, collect, store,
distribute and consume, with payment flowing back, in the four regimes. Engine claims cite file:line in this worktree (branch
`subsistence`). NEW marks anything that does not exist yet.*

## 1. Summary

- **Production is foraging and hunting, not farming.** Fields are parked (`subsistence.py:92`, `fields.enabled: false`) and
  scheduled shocks hit forests only (`subsistence.py:264-289`). In this design a "farmer" is a forager who holds a forest licence and
  a "hunter" is a member of a hunting party. Fields are a later swap (§8).
- **A chain needs enclosure.** Forests are open to everyone (`camptypes/forest.py:75`). `start.camp_rights` skips subsistence
  camps (`start.py:453-454`). As things stand, all 24 agents can feed themselves and no institution is needed. Every regime therefore
  starts with one J0 law, a **Forest Licence** (NEW, small; a variant of Licensing Authority, `library.py:2192`, that also gates
  `before_hunt`). It licenses 2 of the 3 forests to 7 producers (5 farmers, 2 hunters) and leaves one "common wood" open as a
  safety valve, thinned by a forest-action quota (`COMMON_QUOTA: 3` a round, through the existing `set_quota`, `library.py:4668`).
  That valve is also the survival-share dial.
- **Sized for the whole population (framework §11a).** Spec dials `forest: {capacity_per_agent: 10, regrowth: 0.8, yield: 4}`
  make normal licensed output ≈33 food a round against 24 eaten (1.38×). Every regime holds ≥120 food in stores at start (130-140 where centralised), serves
  all 17 non-producers automatically with per-customer limits, and prices the ration below the lowest income (§3.5).
- **One supply mechanism shared by all regimes**, in three templates:
  - **Supply Contract** (contract code, NEW, M): an allowance-pulled delivery into a store, paid per unit, with a bond, a notice
    action and renegotiation;
  - **Provision Subscription** (contract code, NEW, S-M): automatic retail, pennies in and a food bundle out every round;
  - **Procurement Quota** (polity law, NEW, S-M): compulsory delivery at a fixed price.
  
  Everything else is in the library already: Relief Act, Food Levy, Granary Ration, Cooperative, Wage Roll, standing orders,
  Exchange and Contract Enforcement Act.
- **The four regimes answer "who owns the store and who sets the price":**
  - **Merchant:** farmers' own pantries plus a grain dealer's store; prices posted on a pull Market Board.
  - **Private:** a Provisions Company's store; it sets the retail price, and supplier prices are set by contract.
  - **State:** the J0 granary; a Commissioner sets quota and price, and the Relief Act rations.
  - **Cooperative:** the Co-op's store; the general meeting sets dues, wages and the payout share.
- **Defaults run.** Contracts pull and pay at round end, before the ration (`subsistence.py:24`). So in every regime a passive
  world eats for at least 3 rounds:
  - Merchant: two-way standing orders seeded via `start.wages`.
  - Private: allowances on the company contract.
  - State: the quota and the Relief Act.
  - Cooperative: pooling plus emergency meals.
  
  One gap blocks this: `start` cannot set allowances or escrow (NEW, S).
- **Decisions are few and logged:** set or post a price; give notice or cut an allowance (a breach); hoard or release a store;
  set a quota; draw from the granary; admit, expel or vote on payouts.
- **Channels:** one Market Board (Merchant and Private; public, pull, rate 1, with a posting format the metrics can parse) and one
  Co-op Hall (Cooperative). State uses the shared J0 notices. That is at most 2 food channels in any world.
- **Blight stress:** plants ×0.4 and game ×0.5, then a lean season (regrowth ×0.5) for 8 rounds. This takes output from about 33
  to about 14-19 food a round (mean 17) against 24 eaten, a shortfall of about 60-70 over the spell. Stores of 150-175 at the
  blight bridge it if released and do not if hoarded or embezzled (§3.5). Each regime has a different cheater:
  - Merchant: the dealer hoards.
  - Private: the firm rations by price and drops suppliers.
  - State: quota evasion and a black market.
  - Cooperative: the consumer majority votes to raid the reserve.

## 2. The chain, stage by stage

Physics shared by all regimes:
- Each agent eats 1 food at round end, automatically; empty hands are topped up from the agent's own stores
  (`subsistence.py:377-406`).
- Food in hand spoils 15% a round; food in a store spoils 2% (`subsistence.py:69-70`).
- A store holds 40 by default, or any capacity given in `start.stores`.
- Forage yields `yield` × stock/capacity per action (3 by default; 4 in these worlds), at most 2 forest actions a round
  (`subsistence.py:82`, `forest.py:198-200`).
- The hunt pays at round end, shared within the party (`forest.py` docstring).
- Taking food out of an institution's store is the routed `withdraw`. The owner's code decides who may; if the code is silent,
  the officers or the office that controls the store may (`subsistence.py:1040-1063`).
- Only those who may withdraw see a store's level (`subsistence.py:909-916`). This is a transparency lever in every regime.

| Stage | Merchant | Private | State | Cooperative |
|---|---|---|---|---|
| **Produce** (who does it / owns the output) | licensed independent farmers and a 2-hunter party; the output is theirs | the same farmers, as the company's suppliers; the output is theirs until it is pulled | licensed state farmers; the output is theirs until the quota takes it | member farmers; the output is theirs until the co-op pulls their allowance |
| Who sets the rule | the J0 licence law; the Registrar issues and revokes licences | the same | the same, plus the Commissioner's quotas | the same; the co-op admits members |
| **Collect** | none, or the dealer buys by DM | Supply Contract: pulls up to `qty` a round into the company store, pays `price` per unit | Procurement Quota: J0 takes `quota` (above a keep) into the granary and pays the fixed price | Cooperative: pulls each member's food allowance into the treasury; shares are credited |
| Contract / cancel | none, or the farmer's standing order of food (either side leaves at will) | Supply Contract: notice of 2 rounds, a bond and breach records | statute: only the council amends it; evasion is fined | the co-op code; a member may leave and gives up its shares |
| **Store** (asset owner) | farmers' pantries (agent stores, 5 × 12) and the dealer's store S2 (60) | the company store S2 (cap 200, 100 at start) and J0's relief store S1 (40) | the J0 granary S1 (cap 250, 130 at start) | the co-op store S3 (cap 250, 130 at start) |
| Who may draw | each owner | the Shopkeeper office (controls S2; cap by Granary Ration on S2) | the Keeper (Granary Ration cap 6); laws (Relief Act) | the co-op code (emergency meals, payouts); the Steward |
| **Distribute** / price-setter | seeded standing orders (every non-producer has one, 1 food for 2₱ a round) plus spot sales on the Market Board, settled by DM and transfer; price set by each seller; delivery not guaranteed | Provision Subscription (automatic, open to all, at most 2 food per subscriber a round) and counter sales by the Shopkeeper; the Director sets the price, changes take effect after notice | Ration Shop (open to all, 1₱ per food, at most 2 per customer a round); Relief Act tops up the hungry and starving; the Keeper makes discretionary draws | Cooperative: emergency meals to members short of food; periodic pro-rata payouts; dues in pennies |
| **Consume** | buyers eat what they bought | subscribers get their food each round | Ration Shop customers get theirs; Relief tops up the hungry | members short of a meal get one |
| **Payment back** | buyer to seller, by transfer (trust) | subscriber allowance to company treasury, then to suppliers per unit and to staff as wages | J0 treasury to farmers per unit delivered; taxes from the money subsystem | member dues to co-op treasury, then wages to farmers (Wage Roll) and payouts in food |
| Automatic each round | the standing orders seeded at start | delivery, payment, subscriptions, wages | quota take and pay, relief | pooling, meals, dues, wages, payouts |

## 3. The regimes

Casting convention: the food slice of a 24-agent world uses 10-12 agents. Each also holds an affiliation in another subsystem
(employer, watch, press). The food slice puts 2-3 of the world's 6-8 Opus seats in decision seats. All other agents are
**consumers**: their food role is "buy, subscribe or receive", and their card is one line on another subsystem's card.

### 3.1 Merchant: farmers post, buyers pull

**Institutions**

*The Market Board* is shared infrastructure, not an institution with officers. *The Licence Register* is part of the J0 Forest
Licence law. *The Grain Dealer* is an agent with a store, not an institution, so it has no anatomy of its own.

| Part | Forest Licence (J0 law) |
|---|---|
| Purpose | Ration the forests so that producers have something to sell; licence fees go to the J0 treasury |
| Assets | 2 licensed forests; the licence register (law `public`); fee income |
| Roles | the Registrar (J0 office: issue and revoke); licensees |
| Contracts | none; fee FEE penny per TERM rounds |
| Rules | J0 statute; the council amends it (FEE, TERM, CAMPS, number of licences) |
| Channels | none of its own; revocations are gazetted |
| Records | public licence register: issued, revoked and expired, with round and reason (append-only by its code) |
| Accountability | the council appoints the Registrar (succession: election by J0.council) |
| Change | the council amends; anyone may propose opening the woods (repeal) or licence auctions (Licence Auction, `library.py:348`) |
| Capture surface | the Registrar revokes rivals' licences, or sells them for side payments |
| Failure under blight | licensees overharvest; the unlicensed flood the common wood and strip it; pressure to repeal |

**Role cards (Merchant)**

| Role | Tier | Purpose | Automatic routine | Decisions (actions) | Answers to / sees | Pay |
|---|---|---|---|---|---|---|
| Farmer ×5 | Haiku ×3, Sonnet, Opus (swap) | Grow the food the town eats and sell it | standing orders of 1 food to each of 3 seeded customers, each of whose 2-penny orders pays back | post an offer (`post` to `market`); answer DMs and deliver (`transfer` food); cut or keep the standing order (`leave_contract`); store or sell (`transfer` to own `store:`) | no one; sees the board (pull), DMs, own pantry | sales |
| Hunter ×2 | Haiku | Hunt as a party and sell meat | standing order of 1 food to one seeded customer, paid 2 penny | `hunt` with party "red"; post and sell as farmers do | the same | sales |
| Grain Dealer | **Opus** | Buy cheap, store, sell dear | none | bid on the board; buy by DM and transfer; release or hold store S2 (`withdraw`); set the asking price | sees the board, own store level | margin |
| Registrar | Haiku | Keep the licence register | renewals by fee (automatic) | `revoke_licence` (with reason); answer enquiries | the council; sees the register | J0 wage (money subsystem) |

**Standing contracts.** Per seeded pair (17 pairs: each farmer has 3 customers, each hunter 1, so every non-producer has one):
the producer's standing order of 1 food each round to the customer, and the customer's standing order of 2 penny back. These are
two independent one-member contracts (`contracts.py:479-503`, `start.wages` with `employer: <agent>`, `start.py:368`). There is no notice and no penalty: either side cancels with `leave_contract`, which takes
effect at round end. The breach is visible only to the two parties, through the standing-order notices. This is deliberate: it is
the trust baseline.

**Channel (1).**
- `market`: readers all, writers all, **pull**, rate 1 per agent per round, retention all.
- Justification: the only place where prices are public and pulled, so the only price discovery.
- Valid business: an offer counts as "posted" only here (the State and Private variants reuse the board for spot and black-market
  sales).
- Format, set in the channel purpose:
  `SELL <qty> food @ <price> penny [until R<n>]` / `BUY <qty> food @ <price> penny`, one line per order.
- Settlement: by DM and `transfer`. Delivery is not guaranteed.

**Records.**
- Board posts: append-only (`channels.py:5`).
- Licence register.
- Transfers: visible to the parties only. A Public Register law (`library.py:2315`) is the change process for "who sold what".

**Change processes.**
- Anyone may propose the **Exchange** (`library.py:3334`, atomic escrow, delivery versus payment) after the first fraud.
- Someone may propose a Food Levy with `WITHDRAW_CAP`, which caps withdrawals from stores and so works as an anti-hoarding law.
- Farmers may found a **Cartel** (`contracts.py:389`) to fix output.
- Dissolving or entrenching anything goes through J0's procedure.

**Capture surface.**
- The dealer's store is the only large low-spoil stock. Whoever holds S2 when the blight is announced sets the famine price.
- The Registrar controls entry to production.

**Failure under blight.**
- Asking prices jump. Buyers without income starve; the money subsystem must provide wages.
- Farmers net ≈1.5 each after their meal against 3 orders, so about half the standing orders miss (could-not); ≈8 a round
  must come from the dealer's store, the farmers' pantries or the board.
- Fraud rises: prepaid buyers are not delivered to, and food is short.
- Standing orders get cut, so farmers switch to the board.
- The dealer hoards, then releases at the peak. Agents demand the Exchange, a price ceiling (unenforceable, §6) or seizure of the
  dealer's store. Seizure needs force or Eminent Domain (`library.py:2606`); no "loot a store" action exists (§4).

### 3.2 Private: a Provisions Company with supply contracts

**Institution: Provisions Company (A1)**

| Part | Content |
|---|---|
| Purpose | Profit from provisioning the town; the owner benefits, subscribers buy convenience and security |
| Assets | store S2 (cap 200, 100 food at start); treasury 100 penny; the subscription and supply books |
| Roles | Director (founder; controls the treasury; sets prices and terms); Shopkeeper (controls `store:S2`, draws ≤30 a round for counter sales, ≤3 per buyer); Clerk (keeps the books, posts the price on the board, `speak`) |
| Contracts | Supply Contract (5 farmers, 2 hunters); Provision Subscription (open to all); Wage Roll (staff) |
| Rules | procedure `founder` (the Director alone changes the code); admission `open` (anyone may subscribe; supplier status only by named terms) |
| Channels | none of its own; posts its price on the shared `market` board; business with suppliers by DM |
| Records | public in contract state: `terms`, `deliveries`, `owed`, `subscribers`, `stockouts`, `payroll`; store level visible to Director and Shopkeeper only |
| Accountability | none internal (private); external: Contract Enforcement Act (courts) and the council's laws |
| Change | **people**: Director hires (adds to WAGES) and fires (expel), staff quit, a new Director by hereditary or else election; **rules**: Director alone; **contracts**: the terms protocol (below); **existence**: dissolve (wind-up pays the treasury to members, `contracts.py:1663`), sell control by passing the Director office; **entrenchment**: none |
| Capture surface | Director: monopoly price, and choosing who gets food in a stockout. Shopkeeper: the principal-agent gap (counter stock sold privately; the 30/round cap and the draw book limit it) |
| Failure under blight | supply falls short of subscriptions, giving stockouts. Director raises the price (notice) or rations by join order; suppliers short-deliver and sell on the board at spot prices; the treasury runs dry and wages and supplier pay become owed |

**Contracts (A1's code; contracts.max_laws: 5)**

1. **Supply Contract** (NEW, contract code). Parties: A1 and each named supplier (a member).
   - **Each round end:** q = min(qty, allowance left, holdings − KEEP, room in S2) is pulled into S2. A1 pays q × price penny from
     its treasury, or records it as `owed`. A delivery short of `qty` records `breach(supplier, "short delivery", victim=Director)`.
   - **Notice:** `give_notice` (supplier or Director) ends the terms after NOTICE=2 rounds and refunds the bond. If a supplier leaves
     without matured notice, `on_exit` forfeits its BOND (5 penny) to A1. If A1 owes for GRACE=2 rounds, the supplier is released and
     its bond refunded. A1 terminating early pays PENALTY (6 penny) from its treasury.
   - **Renegotiation:** `propose_terms(farmer, qty, price)` by the Director; `accept_terms(n)` by the farmer; effective next round.
   - **Visibility:** terms and deliveries public in the contract's `public`, plus a per-round `notify` to each supplier.
   - **Courts:** under `contracts.enforcement: escrow_court`, breaches are actionable (Contract Enforcement Act, `library.py:1184`).
2. **Provision Subscription** (NEW). Each subscriber's penny allowance is pulled PRICE (2) per food, for the QTY (1) it chose, at
   most LIMIT (2) a round, and that food goes from S2 to the subscriber. Admission is open; there is no total cap.
   - Stockout: no charge, and the subscriber is told. Order: join order, or `PRIORITY: price`, where subscribers on a dearer tier
     go first; the tier is a decision.
   - `set_price` (Director): takes effect after NOTICE=1 round and is gazetted.
   - Cancel: allowance 0 or `leave_contract`, effective at once. No penalty: consumer exit is free.
3. **Wage Roll** (`library.py:4810`, via `start.wages`): Shopkeeper 3, Clerk 2.6 (the floor: 1.25 × the ration's 2.06₱ with levy).
4. **Granary Ration** on S2 (OFFICE A1.shopkeeper, CAP 30; `library.py:4742`): the draw book. To verify: is an established
   template valid as association code? `start.institutions[].laws` accepts any v2 template (`start.py:376-379`).

**Role cards (Private)**

| Role | Tier | Automatic | Decisions | Answers to / sees | Pay |
|---|---|---|---|---|---|
| Director | **Opus** | all three contracts run | set retail price (`invoke set_price`); propose or end supplier terms (`invoke propose_terms`, `give_notice`); hire or fire (`propose_contract_change` to WAGES, `expel`) | nobody (owner); sees treasury, S2 level, books, board | profit (treasury) |
| Shopkeeper | Sonnet | none | counter sales: `withdraw` ≤30 from S2 (≤3 per buyer), `transfer` food to buyers who paid by DM; report to the Director | Director; sees S2, DMs | wage 3 |
| Clerk | Haiku | none | post the price line on `market` each round; read the books and flag arrears | Director | wage 2.6 |
| Supplier farmer ×5 | Haiku ×3, Sonnet, **Opus** (lead supplier) | allowance pulled, paid per unit | keep, cut or raise the allowance; give notice; accept or refuse terms; sell extra on the board | the contract terms; sees own deliveries | per unit (1 penny): ≈4₱ a round |
| Supplier hunter ×2 | Haiku | the same, qty 3 (lumpy catches: expect ≈2.5) | the same | the same | the same |

**Channels: 0 own.** The company posts on the shared `market` board; supplier dealings run by DM. A private A1 channel is not
justified: it has 3 staff.

**Failure under blight.**
- Suppliers' holdings fall below KEEP+qty, so deliveries shrink automatically: recorded as short delivery without any act. The
  template must separate "could not" (holdings < qty + KEEP: no breach) from "would not" (allowance cut: breach).
- S2 drains about 11 a round (inflow ≈7-11 against 17 subscribers); it lasts the lean spell only if the Board keeps running.
- Stockouts, if they come, hit subscribers in join order.
- The Director's real choice comes here: raise the price (the poor drop out), cut subscribers, or buy on the board at spot to keep
  faith.

### 3.3 State: granary, quotas and rationing

**Institution: the State Granary (J0 offices + statutes)**

| Part | Content |
|---|---|
| Purpose | No one starves; the state owns the surplus. Beneficiaries: everyone, officials first in practice |
| Assets | granary S1 (cap 250, 130 food at start); J0 treasury (penny, for procurement); the 2 licensed forests |
| Roles | Food Commissioner (sets quotas and procurement price within statutory bounds); Keeper (controls S1, discretionary draws ≤6); Inspector, who also holds the Registrar seat (licence register, quota book, revokes evaders' licences) |
| Contracts | Procurement Quota (statute): each farmer's quota taken and paid; Ration Shop (Board preset, J0 principal): every non-producer seeded; Relief Act: top-up for the hungry and starving |
| Rules | statutes of J0; amended by the council's procedure (rules subsystem); the Commissioner's parameters by `invoke` within bounds |
| Channels | none of its own: quota, price and ration notices on the shared J0 `notices` channel (integrator's), petitions to `@J0` |
| Records | public: quota book (owed, delivered, short, fined), relief register (`library.py:3949`), ration book of Keeper draws (`library.py:4742`), licence register. Private: the granary level, seen only by the Keeper (and the council if it holds an office controlling S1) |
| Accountability | the council appoints and removes all three (succession by J0.council election); an Audit Office (`library.py:593`) is optional |
| Change | **people**: council elections and recall; **rules**: the council amends quotas, bounds, relief budget and stages (e.g. Hunger Disenfranchisement, `library.py:4073`); **existence**: repealing the Procurement Quota is privatisation; **entrenchment**: optional constitutional rank for the Relief Act |
| Capture surface | Keeper: 6 food a round for self and allies, plus knowledge of the level. Commissioner: low quotas for friends, high for rivals. Inspector: selective revocation |
| Failure under blight | quotas exceed what farmers hold, so shortfalls, fines and evasion follow (sell to a black market before round end, keeping holdings ≤ KEEP); the granary drains about 11 a round (quota ≈7-11 in, shop 17 out, spoilage), from ≈175 to ≈80; the council cuts the shop, relief stages or disenfranchises the hungry |

**Contracts.**
1. **Procurement Quota** (NEW, polity law; compulsory). At round end, before the ration, J0 takes
   min(quota, holdings − KEEP=1) from each named farmer into S1 and pays PRICE (1) penny per unit from the treasury, or records it
   as owed.
   - Shortfall against quota is entered in the quota book. FINE (2 penny) per unit short is charged only where the farmer held the
     food at some point in the round: that detects sale before the take. The fine applies only when `AUDIT` is on.
   - `set_quota(farmer, q)` and `set_price(p)` by J0.commissioner, within [0, MAXQ=6] and [MINP=0.5, MAXP=3], gazetted.
   - Cancel: only by amendment. The farmer's exit is to stop producing (lose income) or to hand back the licence.
2. **Ration Shop** (Board preset, 08 §2.1, with J0 as principal): 1 penny per food, at most 2 per customer a round, open to all;
   the 17 non-producers are seeded at 1 a round.
3. **Relief Act** (`STORE: S1, RATION: 1, BUDGET: 12, STAGES: [starving, hungry]`): anyone who missed a meal is topped up, the
   starving first (`library.py:3949-4001`).
4. **Granary Ration** (`STORE: S1, OFFICE: J0.keeper, CAP: 6`).
5. Optional: **Food Levy** with `RATE: 0, WITHDRAW_CAP: 2`, which rations private stores (anti-hoarding; `library.py:4003`).

**Role cards (State)**

| Role | Tier | Automatic | Decisions | Answers to / sees | Pay |
|---|---|---|---|---|---|
| Food Commissioner | **Opus** | quota, shop and relief run | set quotas and price (`invoke set_quota`, `set_price`); propose relief changes (`propose`); report on `notices` | council; sees quota book, relief register, not S1 | J0 wage |
| Keeper | **Opus** (or Haiku as swapped seat) | none (relief draws by law) | discretionary `withdraw` ≤6 (feed the sick, officials, or self); publish or withhold the granary level (`post` to `notices`) | council; sees S1 level, ration book | J0 wage |
| Inspector-Registrar | Haiku | none | `revoke_licence` of evaders; post shortfall lists; prosecute via Penal Code (rules subsystem) | Commissioner | J0 wage |
| State farmer ×5, hunter ×2 | Haiku ×5, Sonnet, Opus | quota taken and paid | produce more or less; sell surplus or the quota itself on the black market (`post` on board or DM); hold below KEEP | Inspector; sees own quota line | per unit |

**Channels: 0 own.** In a pure State world the `market` board is not created. A black market lives in DMs, which is measurable
(food transfers between agents). Allowing a board is a regime dial.

### 3.4 Cooperative: member-owned store and shares

**Institution: the Food Co-op (A1)**

| Part | Content |
|---|---|
| Purpose | Members feed each other; producers are paid in money and in pro-rata food, consumers in security |
| Assets | store S3 (cap 250, 130 food) is the co-op's reserve. To check: Cooperative pools into the *treasury* (`library.py:4418-4461`), which spoils at 15%, not into a store. Either accept that, or have the Steward move it into S3 (a decision), or make a NEW template variant with STORE (preferred, S). Also: a treasury of 100 penny |
| Roles | Steward (elected, term 6: draws from S3 for outsiders and sales; publishes the reserve level); Treasurer (elected: controls the treasury, pays wages); Tallyman (Haiku, appointed: keeps the minutes, admits members after a vote, `speak`) |
| Contracts | Cooperative, store variant (PERIOD 3, PAYOUT 0.5 of the stock above RESERVE 120): food pooled by allowance (farmers 4, hunters 3), shares, emergency meals to every member short of one (no cap). Member Dues (NEW, S): 2 penny a round from consumer members' allowance; MISSES 3, then expel. Wage Roll: farmers 3 penny |
| Rules | procedure `members` (majority of those voting); admission `closed`: applicants admitted by the Tallyman's `admit_member` after a vote (the admission code is in Member Dues) |
| Channels | `hall`: members only. The general meeting: motions, minutes, the Steward's reserve report |
| Records | shares and payout register (public in contract state); minutes (posts in `hall`, append-only); dues book; the S3 level, Steward and Treasurer only unless published |
| Accountability | officers elected by members; recall by majority (Recall, `library.py:464`, as co-op code, or an office's succession election) |
| Change | **people**: join and admit, leave (shares forfeited), expel for dues, elect and recall; **rules**: any member proposes a code change, majority; **existence**: dissolve, winding up the treasury to members equally (`contracts.py:1719`); split by founding a rival; **entrenchment**: `two_thirds` for Cooperative changes is a dial |
| Capture surface | consumers (17) outnumber producers (7): they can vote PAYOUT down and dues down, transferring farmers' surplus to themselves. Farmers can respond by cutting allowances (exit within). The Steward is the officer who knows the reserve |
| Failure under blight | contributions fall to ≈7-11 against 17 meals, so the reserve drains about 11 a round (≈140 to ≈45 over the spell); farmers lobby to cut RESERVE so payouts resume; negative shares pile up on consumers; farmers' payouts vanish, so farmers cut allowances and sell outside; a motion to suspend payouts or expel non-contributors follows |

**Role cards (Cooperative)**

| Role | Tier | Automatic | Decisions | Answers to / sees | Pay |
|---|---|---|---|---|---|
| Steward | **Opus** | pooling and meals | publish or withhold the reserve level; propose PAYOUT and PERIOD changes; sell to non-members by DM (`withdraw` S3) | the members; sees S3, shares | wage 2 |
| Treasurer | Sonnet | Wage Roll, dues | propose wage changes; pay extraordinary bills (`transfer as A1`) | the members; treasury | wage 2 |
| Tallyman | Haiku | none | admit applicants after a vote (`invoke admit_member`); post minutes in `hall` | Steward | wage 1 |
| Member farmer ×5, hunter ×2 | Haiku ×5, Sonnet, **Opus** (farmers' spokesperson) | allowance pooled; wages; payouts | keep or cut the allowance; vote; propose; leave and sell privately | the meeting; shares, hall | wage 3 + payouts |
| Consumer member | (other subsystems) | dues pulled; meals when short | vote on payouts, dues and wages | `hall` | none |

**Channel (1).**
- `hall`: readers and writers are members of A1, pull, retention all.
- Justification: 20 members cannot run a general meeting in DMs.
- Valid business: motions are announced and minuted here (the vote itself is `vote` on the contract proposal).

### 3.5 Calibration, scale and the blight (all regimes; verify by dry run)

**Engine basis.** Forests: ceil(N/`per_agent`) of them, plant capacity K = `capacity_per_agent` × N / forests, game K =
`game.capacity_per_agent` × N / forests (`subsistence.py:788-815`). A forage takes `yield` × S/K, never below the refuge
(`forest.py:198-200`); plants regrow logistically, S += r·S(1−S/K) − harvest, at round end (`camps.py:270-276`), r = `regrowth` ×
the season (`subsistence.py:225-249`). Hunts pay by party effort, about 2.1 food per unit for a party of 4 units at full game
(`forest.py:31`). Spoilage 15% in hand, 2% in a store (`subsistence.py:69-70`). Scheduled shocks cut stocks and force a season
(`subsistence.py:252-288`). All of these are per-spec dials (`schema.py:797-808`; Millbrook sets some, `millbrook.yaml:73-85`).

**Why the defaults fail §11a.** At `capacity_per_agent: 7, regrowth: 0.6, yield: 3` (K = 56), five farmers settle at s ≈ 0.6 and
harvest ≈16; with the hunters (≈7) licensed output is ≈23.5 against 24 eaten. The whole world's plant MSY is only r·7N/4 ≈ 25.

**Dials for every regime** (one set, so regimes differ only in institutions):

```yaml
subsistence:
  forest: {per_agent: 8, capacity_per_agent: 10, regrowth: 0.8, yield: 4}   # 3 forests, K = 80 plants each; game default (K 80)
  seasons: {lean: 0.5}                                                       # p_lean 0.25 as default
  shocks: [{round: 10, plants: 0.4, game: 0.5, season: lean, rounds: 8}]
```

The Forest Licence sets `COMMON_QUOTA: 3` forest actions a round on the common wood (`set_quota`, `library.py:4668`; it binds the
hunt too, `subsistence.py:852-857`). Without it the common wood is as rich as a licensed forest (MSY 16) and the chain is optional.

| Mean-field, 5 farmers × 2 forages + a party of 2 hunters × 2 units (alternating forests) | Normal | Random lean round | Blight (rounds 11-18) |
|---|---|---|---|
| Plants from the licensed forests (stock s) | 26 (s ≈ 0.72; 5.2 per farmer) | | 11.6-15 (s ≈ 0.3-0.4) |
| Game | ≈7 (3.6 per hunter, lumpy) | | ≈4-5 |
| **Licensed output vs 24 eaten** | **≈33 (1.38×)** | 5th percentile 27, worst 24 (400 seeds) | **14.3 → 19.0, mean 16.7 (0.70×)** |
| Left for the 17 non-producers after producers eat 7 | ≈26 (1.53× their 17); ≈25 reaches a store | | ≈7-11 |
| Common wood (quota 3) | ≈9 | | ≈5 |

The blight's cumulative shortfall is ≈60 over the 8 lean rounds and ≈68 (median; 95th percentile 91 with unlucky seasons) until
output is back above 24 around round 21. Stores grow ≈+5 a round before it, so every regime meets it with 150-175 in stock.

**Scale check per regime** (demand 24 a round, 17 of it through the institution; runway = stores ÷ net drain):

| | Merchant | Private | State | Cooperative |
|---|---|---|---|---|
| Producers / terms | 5 farmers, 2 hunters; 17 standing orders of 1 food | the same; Supply 4 per farmer, 3 per hunter (26) | the same; Quota 4 and 3 (26) | the same; allowances 4 and 3 |
| Normal inflow vs institutional demand | 15 + 2 ordered; ≈9 spare to sell | ≈25 into S2 vs 17 (1.47×) | ≈25 into S1 vs 17 | ≈25 into S3 vs 17 |
| Stores at start (≥120) | 120: dealer S2 60, 5 pantries × 12 | 140: S2 100, relief S1 40 | 130: S1 | 130: S3 |
| Runway, everyone idle (stores ÷ 24) | 5 | 5.8 | 5.4 | 5.4 |
| Stores at the blight → trough if all is released | ≈120 + what the dealer buys | ≈185 → ≈95 (S2 bottoms ≈60) | ≈175 → ≈80 | ≈140 → ≈45 (payouts above RESERVE) |
| Blight runway (stores ÷ net drain) | ≈15 rounds at a drain of 8 | ≈17 at 11 | ≈16 at 11 | ≈13 at 11 |
| Fed with zero consumer attention (normal / blight) | 100% / ≈50% (standing orders miss) | 100% / 100% while the Board runs | 100% / 100% while the shop runs | 100% / 100% while S3 lasts |
| Ration cost vs lowest income | 2₱ order; purse 25₱ (12 rounds); a worker-round at the window ≈5₱ | 2.06₱ with levy vs lowest wage 2.6₱ (1.26×) | 1.05₱ with levy vs lowest wage 2₱ (1.9×) | free against shares; farmers paid 3₱ |

"Zero attention" means consumers do nothing and producers forage and hunt as their role cards say. With everyone idle, nothing is
produced, and start food (5-8, about 4-5 rounds at 15%) plus the stores carry the world, which passes the 3-round check.

So the blight squeezes everywhere and kills nowhere *by physics*: released stores bottom out at 40-60% of their peak with no
announced end date. Hunger comes from decisions: the dealer's hoard, the Director's price, the Keeper's draws, the meeting's
RESERVE vote. Millbrook's lean 0.35 on these dials would push the licensed forests to the refuge; avoid it. Felling shrinks K for
good (`forest.py:218-220`); the Licence gates felling in the licensed forests, and fells in the common wood count against its quota.

These are mean-field estimates (scratch model of the engine formulas). They ignore within-party lumpiness, hunger multipliers and
agents' effort choices. **Dry run to confirm:** normal output ≥ 30, hunters' mean delivery ≈ 2.5 on a qty of 3, the store
trajectories above, and the common wood's yield under the quota.

## 4. Cross-links (interfaces other subsystems must provide)

| Need | Interface | Provider |
|---|---|---|
| Consumer income | every non-producer has ≥2.6 penny a round (1.25 × the 2₱ ration with a 3% levy) from a wage (`start.wages`) or a standing contract; otherwise Merchant and Private starve the poor by construction | Money / Materials / Force |
| Producers' spending | something farmers want to buy: materials (timber and stone for a store: 10 + 6, `subsistence.py:96`), protection, press | Materials |
| Currency | `penny` issued by J0 (`start.currencies`); procurement paid from the J0 treasury, which needs a tax (Payment Levy) | Money |
| Stores | building a new store costs materials; capacity is otherwise fixed at start | Materials |
| Theft | food carried can be taken by harm combat (review 27 §4); **stores cannot be looted by force**: there is no action. A seizure needs a law (Eminent Domain, the Seize block `library.py:1354`) applied by the owner's polity. Interface: "the watch enforces J0 seizure of a store" | Force / Rules |
| Breach | Contract Enforcement Act (MODE court) with `contracts.enforcement: escrow_court`; quota evasion is under the Penal Code and Prosecution Office | Rules (courts) |
| Records | J0 `notices` channel for State food notices; the public registers above are law `public` dicts, readable by anyone through the law | Information |
| Lawyers | draft and preview the five food templates' parameters (`preview_law`); represent suppliers in breach cases | Rules |
| Offices | Registrar, Keeper, Commissioner are J0 offices; A1 offices via `start.institutions[].offices` | Rules |

## 5. Spec sketches

### 5.1 Private regime (food slice)

```yaml
subsistence:
  enabled: true
  start_food: [5, 8]
  forest: {per_agent: 8, capacity_per_agent: 10, regrowth: 0.8, yield: 4}   # 3 forests at N=24, K 80 (§3.5)
  seasons: {lean: 0.5}
  shocks:
    - {round: 10, plants: 0.4, game: 0.5, season: lean, rounds: 8,
       text: "A blight has struck: more than half the plants and half the game are gone; a lean season follows."}
contracts: {enabled: true, max_laws: 5, enforcement: escrow_court, scripted: false}
channels: {v2: true, delivery: pull}           # global today; per-channel push/pull is NEW
institutions: {unified: true, grants: true, succession: true, office_control: true}
start:
  currencies: [{name: penny, issuer: J0}]
  rights: {Bryn: [forester], Cass: [forester], Dell: [forester], Edda: [forester], Fion: [forester],
           Gale: [forester], Hob: [forester]}            # the licence right, held at round 0
  institutions:
    - id: J0
      offices:
        registrar: {title: Forest Registrar, holders: [Ivy],
                    duties: "Keep the forest licence register; revoke a licence only for cause, with the reason.",
                    succession: {rule: election, electorate: J0.council}}
      laws:
        - template: Forest Licence                       # NEW (Licensing Authority + before_hunt, office registrar)
          params: {LICENCE: forester, REGISTRAR_RIGHT: J0.registrar, CAMPS: [camp7, camp8], FEE_ITEM: penny, FEE: 2, TERM: 8,
                   COMMON: [camp9], COMMON_QUOTA: 3}
    - id: A1
      name: Provisions Company
      founder: Anselm                                    # Director (Opus)
      members: [Quill, Tess, Bryn, Cass, Dell, Edda, Fion, Gale, Hob]
      admission: open
      procedure: founder
      charter: "The Provisions Company buys food from its suppliers under contract, keeps it in its store and sells it to its
        subscribers and over the counter. The Director sets its prices and terms."
      offices:
        director: {title: Director, holders: [founder], controls: [treasury], powers: [speak],
                   succession: {rule: hereditary, else: election}}
        shopkeeper: {title: Shopkeeper, holders: [Quill], controls: ["store:S2"],
                     duties: "Sell over the counter: take at most 30 food a round from store S2, at most 3 per buyer, for buyers who have paid."}
        clerk: {title: Clerk, holders: [Tess], powers: [speak],
                duties: "Post the Company's price on the market board each round; keep the books."}
      laws:
        - template: Supply Contract                      # NEW
          params: {STORE: S2, ITEM: penny, KEEP: 1, BOND: 5, NOTICE: 2, GRACE: 2, PENALTY: 6, OFFICE: A1.director,
                   TERMS: {Bryn: [4, 1], Cass: [4, 1], Dell: [4, 1], Edda: [4, 1], Fion: [4, 1],
                           Gale: [3, 1], Hob: [3, 1]}}
        - template: Provision Subscription               # NEW
          params: {STORE: S2, ITEM: penny, PRICE: 2, LIMIT: 2, NOTICE: 1, PRIORITY: join, OFFICE: A1.director,
                   STAFF: [Anselm, Quill, Tess]}
        - template: Granary Ration
          params: {STORE: S2, OFFICE: A1.shopkeeper, CAP: 30}
      treasury: {penny: 100}
  stores:
    - {id: S1, owner: J0, food: 40, capacity: 80, name: the town relief store}
    - {id: S2, owner: A1, food: 100, capacity: 200, name: the Company store}
  wages:
    - {employer: A1, worker: Quill, item: penny, qty: 3}
    - {employer: A1, worker: Tess, item: penny, qty: 2.6}
  allowances:                                            # NEW section: contract allowances at round 0
    - {member: Bryn, contract: A1, item: food, qty: 4}   # ... one per supplier (hunters 3)
    - {member: Ula, contract: A1, item: penny, qty: 2}   # ... one per subscriber: all 17 non-producers, 1 food a round
  escrow:                                                # NEW section: bonds at round 0
    - {member: Bryn, contract: A1, item: penny, qty: 5}  # ... one per supplier
  channels:
    - id: market
      owner: J0
      by: Ivy
      purpose: "The market board. One line per order: SELL <qty> food @ <price> penny [until R<n>] or BUY <qty> food @
        <price> penny. Settle by DM and transfer; delivery is not guaranteed."
      readers: {all: true}
      writers: {all: true}
      rate: 1
      retention: all
  laws:
    - template: Contract Enforcement Act
      params: {MODE: court, SANCTION: fine, ITEM: penny, FINE: 3, PAY: victim}
    - template: Relief Act                               # a thin public floor (starving only)
      params: {STORE: S1, RATION: 1, BUDGET: 6, STAGES: [starving]}
```

Notes:
- Camp ids depend on composition; `spec check` resolves them. A NEW `CAMPS: [forest1, forest2]` alias by forest order would be safer.
- Rights given in `start.rights` are created at round 0 (`start.py:14`). To verify: does the licence law's `create_right` on an
  existing right keep its holders?

### 5.2 State regime (food slice, differences only)

```yaml
start:
  institutions:
    - id: J0
      offices:
        commissioner: {title: Food Commissioner, holders: [Anselm], powers: [speak],
                       succession: {rule: election, electorate: J0.council}}
        keeper: {title: Keeper of the Granary, holders: [Rhoda], controls: ["store:S1"],
                 succession: {rule: election, electorate: J0.council}}
        registrar: {title: Inspector and Registrar, holders: [Ivy], succession: {rule: election, electorate: J0.council}}
      laws:
        - template: Forest Licence                       # NEW, as in 5.1
          params: {LICENCE: forester, REGISTRAR_RIGHT: J0.registrar, CAMPS: [camp7, camp8], FEE_ITEM: penny, FEE: 0, TERM: 0}
      treasury: {penny: 250}
  stores:
    - {id: S1, owner: J0, food: 130, capacity: 250, name: the state granary}
  laws:
    - template: Procurement Quota                        # NEW
      params: {STORE: S1, ITEM: penny, PRICE: 1, KEEP: 1, FINE: 2, AUDIT: true, OFFICE: J0.commissioner,
               MAXQ: 6, MINP: 0.5, MAXP: 3,
               QUOTAS: {Bryn: 4, Cass: 4, Dell: 4, Edda: 4, Fion: 4, Gale: 3, Hob: 3}}
    - template: Ration Shop                              # Board preset, J0 principal (08 §2.1); all 17 non-producers seeded
      params: {STORE: S1, ITEM: penny, PRICE: 1, LIMIT: 2, OFFICE: J0.commissioner}
    - template: Relief Act
      params: {STORE: S1, RATION: 1, BUDGET: 12, STAGES: [starving, hungry]}
    - template: Granary Ration
      params: {STORE: S1, OFFICE: J0.keeper, CAP: 6}
```

Merchant and Cooperative use the same pieces.
- **Merchant:** `start.wages` with `employer: <producer>, item: food, qty: 1` and `employer: <customer>, worker: <producer>, item:
  penny, qty: 2`, 17 pairs (both are standing orders, `start.py:368`, `contracts.py:2074`); the dealer's store `{id: S2, owner:
  Dorin, food: 60, capacity: 150}`; a pantry per farmer `{owner: <farmer>, food: 12, capacity: 40}`; the `market` channel.
- **Cooperative:** A1 with laws Cooperative, store variant (`STORE: S3, PERIOD: 3, PAYOUT: 0.5, RESERVE: 120`), and Member Dues
  (NEW); allowances 4 (farmers) and 3 (hunters); S3 `{food: 130, capacity: 250}`; `start.wages` for farmers; `hall` with `readers:
  {members: A1}`.

## 6. Code needed

| # | Piece | Exists today | Size | Library template or engine |
|---|---|---|---|---|
| 1 | **Forest Licence**: gate `before_harvest` and `before_hunt` on CAMPS, registrar as an office right, fee and term; `set_quota` on the COMMON wood each round | Licensing Authority gates harvest only, registrar by class (`library.py:2192-2265`); Forest Territory gates both, but by camp, not licence (`library.py:4606-4640`) | S | template |
| 2 | **Supply Contract**: per-supplier terms, allowance pull into STORE, unit pay or owed, KEEP, bond, `give_notice`, early-termination penalty, `propose_terms`/`accept_terms`, could-not vs would-not breach | standing orders (one-way, no notice, `contracts.py:479-503`); Day Labour (food wages for harvests, `library.py:4464`); `breach`, `pull`, `forfeit`, `define_action` exist in the contract API | M | template (contract code) |
| 3 | **Provision Subscription**: pull PRICE per unit, deliver the subscriber's QTY (≤ LIMIT) from store, stockout rule, `set_price` with notice | nothing for retail; Granary Charter's FEED loop is the pattern (`library.py:4288-4365`) | S-M | template |
| 4 | **Procurement Quota**: compulsory per-farmer take into a polity store, paid per unit, shortfall book and fine, office-set bounds | Food Levy takes a proportional share, unpaid (`library.py:4003-4070`); Regulatory Agency shows bounded office parameters (`library.py:2268`) | S-M | template |
| 5 | **Member Dues and admission** (co-op): penny dues by allowance, expel after misses, `admit_member` | Club dues logic (`contracts.py` TEMPLATES `club`); `admit` in contract code (`contracts.py:1037`) | S | template |
| 6 | Cooperative variant pooling into a **store** (2% spoilage) instead of the treasury (15%), payouts only from the stock above RESERVE | Cooperative pools into the treasury (`library.py:4418-4461`) | S | template |
| 7 | `start.allowances` and `start.escrow` sections | missing: `SECTIONS` has neither (`start.py:46`); only wages set allowances (standing orders) | S | engine (start.py) |
| 8 | **Per-channel push/pull** (`ch["delivery"]`, read in `pulled`) | global `channels.delivery` only (`channels.py:86-87`, `:938-946`). The docstring says pull is the default, but `DEFAULTS` says push (`channels.py:28` vs `:53`) | S-M | engine |
| 9 | Contract **exit notice** in the engine | `rec["exit"]["notice"]` is stored (`contracts.py:267`) but never read; exit happens at round end. Templates 2 and 3 emulate notice with bonds | M | engine (optional; templates suffice) |
| 10 | A contract's terms in its members' state lines | state shows membership, escrow, allowance and treasury, not the code's `public` (`contracts.py:2139-2150`); suppliers learn their terms only from `notify` | S | engine |
| 11 | Store level visibility as a dial (a "published" store) | levels are visible only to those who may withdraw (`subsistence.py:886-916`) | S | engine, or a law that gazettes `stores()` each round (template, S) |
| 12 | Market Board price parser and price index | none | S | analysis code |
| 13 | Scheduled blight on fields (when fields return) | shocks touch forests only (`subsistence.py:264-289`) | S-M | engine |
| 14 | `transfer as` an office into another association's treasury | `pay_as` accepts agents and stores only (`institutions.py:650`) | S | engine (needed for State-to-co-op or firm-to-firm payments) |
| 15 | Forest ids by order in templates (`forest1`) | camp ids come from composition | S | template helper or spec check |

What already exists and is enough: Relief Act, Food Levy (with WITHDRAW_CAP), Granary Ration, Cooperative, Wage Roll, standing
orders from `start.wages`, Exchange (atomic delivery versus payment, held back as a change process), Contract Enforcement Act,
Cartel, Licence Auction, Public Register, scheduled shocks, `start.stores` with capacity, office `controls: [store:Sx]`.

Not enforceable at all, and kept out of every design: **price ceilings on spot trades**. A sale is two independent transfers, and
no law sees them as one trade. Only the Exchange template, or a contract's code, binds the price.

## 7. Dry-run checks and metrics

Gates, run before any model run with scripted bots, seeds 1-2, `contracts.scripted: false`:

1. **Zero attention, 3 rounds:** with every agent idle, nobody misses a meal in rounds 1-3 in any regime. Fed by the seeded
   standing orders, subscriptions, quota plus relief, or co-op meals respectively.
2. **The chain closes:** the S2/S1/S3 level rises before the blight. Supplier payments equal units delivered × price (± owed).
   Money conservation holds, and subscribers' pennies reach farmers within 2 rounds.
3. **Scale (framework §11a):** with scripted producers and idle consumers, rounds 1-10: licensed output ≥ 30 a round, the
   institution's inflow ≥ 21 (1.25 × 17), every non-producer fed every round, stores ≥ 120 throughout.
4. **Blight bites, does not wipe out:** with released stores, deaths by round 24 are 0 in every regime but Merchant (≤2 there).
   With a hoarded or embezzled store, deaths are >2. The design must show sensitivity to the decision, not only to physics.
5. **Survival-action share ≤30%:** count harvest, hunt, withdraw, food transfers and food DMs over all actions, before and after
   the blight. Target ≈15-20% before; the common wood pushes it up after.
6. **Templates do what they say:** `preview_law` and scripted checks for each NEW template: notice matures, the bond is forfeited
   on a premature exit, a stockout charges nothing, and the quota fines only food that was held.

Run metrics (per round, per regime):

- **Price series:** parse `market` posts with `^(SELL|BUY) (\d+(\.\d+)?) food @ (\d+(\.\d+)?) penny`. Report the share of posts that
  parse, the median ask and bid, the spread, and the price ratio after vs before the blight. Add the Company price and the
  procurement price where they exist.
- **Settlement rate (Merchant):** prepaid transfers followed by delivery from the counterparty within 2 rounds, as a share of
  prepaid transfers. Fraud is the complement.
- **Contracts:**
  - cancellations (`leave_contract` on standing orders, supply and subscription contracts);
  - notices given, and bonds forfeited;
  - short deliveries split into could-not vs would-not;
  - owed balances;
  - renegotiations proposed and accepted, and price changes.
- **Stores:**
  - level and spoilage per store;
  - Keeper draws vs relief payouts;
  - the dealer's net position around the announcement round (hoarding index: Δstore in the 2 rounds after the shock
    announcement).
- **Distribution:** hunger stages by role; food Gini; officials' food vs consumers' food (a capture signal); relief recipients.
- **Divergence:** sales outside the role's channel:
  - State: farmer-to-agent food transfers, i.e. the black market;
  - Private: suppliers selling on the board while short on contract;
  - Cooperative: farmers' allowance cuts.
- **Change:** food laws and amendments proposed or passed, and by whom (consumer vs producer); Exchange adopted (round); licences
  revoked; co-op votes on PAYOUT and dues.
- **Channel use:** posts per round on `market` and `hall`; reads (pull) per agent. Target: both read by ≥50% of agents per round
  before the blight.

## 8. Open questions and critique

- **Is enclosure artificial?** Licensing the forests is what makes a food economy exist at all. Without it, the most efficient
  strategy is autarky, which is what review 26 measured (54-70% of actions on subsistence). With it, the design's interesting
  behaviour depends on the licence regime staying in place. Agents may repeal it in a famine, which is a legitimate finding, not a
  bug. The common wood is a compromise: too rich and the chain is optional; too poor and the unlicensed have no exit.
- **Forests are not farms.** There is no planting, no harvest cycle and no investment. Fields (`camptypes/fields.py`: sow, about 3
  rounds' growth, 3.5x return, rot) would give real farmers decisions (seed now vs eat) and a crop the blight can hit. That needs a
  fields shock (code #13) and a Tillers' Right template (deferred, `library.py` comment above FOOD_TEMPLATES). I recommend forests
  for the first world and fields as a single-domain swap.
- **Contract templates carry the institution.** The Supply Contract is the centre of the Private regime and is M-sized new law code.
  If it misbehaves (e.g. breaches recorded when the farmer simply had no food), the regime reads as a lie. The could-not vs would-not
  split must be tested.
- **Members everywhere.** Suppliers and subscribers must be *members* of A1, because a contract can only pull from members
  (`contracts.py` docstring). With admission open and procedure founder they have no vote, but everyone's state lists A1 and its
  laws. Is a "client" membership kind needed? Probably not for v1.
- **max_laws.** A1 needs 4-5 code modules (charter, offices, supply, subscription, wages, ration book), so `contracts.max_laws: 5`
  or 6. This is also a constraint on agents' own institutions: they cannot add law to a full company without replacing some.
- **Pull is global.** Until code #8 exists, `delivery: pull` hides the council's notices along with the board. The headline line
  helps (`channels.py:984-1000`), but Millbrook showed channels go unread. The board must carry business found nowhere else: prices
  are posted only there, and the Company's price is only there.
- **Visible state.** Suppliers' terms and quota lines are not in state lines today (code #10). Until then each template must
  `notify` every round, which is feed noise. This is a §12 lesson ("agents only use what they can see").
- **The State regime is the most automatic and may be the least interesting.** The Ration Shop feeds everyone until the granary
  empties. The decision points (quota levels, shop price and roll, Keeper draws, relief stages) all sit with 3 officials, and the 7
  farmers' only divergence is evasion. Relief at BUDGET 12 (starving and hungry only) keeps rationing a live choice.
- **Merchant is the least robust.** Every non-producer has a seeded standing order (§11a), so normal times feed 100%. But orders
  are paid from purses (25₱, about 12 rounds) unless consumers earn, and in the blight about half the orders miss: the other half
  must be bought from the dealer or the board. Merchant still punishes passivity, later and harder. The metric is who starves
  first.
- **Model confounds.** I put the Opus seats in the dealer, Director, Commissioner and Keeper, and Steward roles. One Opus farmer per
  regime and an optional Haiku Keeper are the swapped seats. More swaps would help attribution but cost decision quality.
- **Numbers are mean-field.** §3.5 should be checked by the scripted tuner (Millbrook's method) before any model run.
- **Richer forests make autarky tempting again.** At yield 4 one forage feeds a forager for about 3 rounds. The common wood's
  quota is what keeps the chain necessary; if agents repeal it, the institutions become optional. That is a finding, not a bug.
- **Engine facts that contradict or sharpen the framework:**
  - (a) `start.camp_rights` cannot enclose forests;
  - (b) contract exit notice is not implemented;
  - (c) `start` cannot set allowances or escrow, so contract defaults do not run from round 0 except standing orders;
  - (d) the channels docstring and the defaults disagree on push vs pull;
  - (e) store levels are private to those who may withdraw;
  - (f) "farmers" cannot farm while fields are parked;
  - (g) stores cannot be raided by force.
