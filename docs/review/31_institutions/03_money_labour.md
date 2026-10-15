# Review 31.03: money, finance and labour

*15 Oct 2026. Subsystem design under the shared framework (`00_framework.md`). Scope: currency issue and backing, wages and
employment, prices, credit and banks, taxes and treasuries, labour mobility, and the generic STANDING CONTRACT template the other
designs use. Engine facts are cited `file:line` at the worktree on branch `subsistence`; "NEW" marks code that does not exist.*

## 1. Summary

Money is the subsystem that makes every other subsystem's flows close. Millbrook shows what happens when it doesn't. I counted
from its events (`millbrook_seed1_382ee0c2`, 24 rounds):

- **Money flowed one way.** The Wage Rolls paid **511 pennies** (158 payments). Agents spent pennies voluntarily **twice, 11
  pennies in all**. Food (33) and timber (125) changed hands in kind.
- **The levy did not last.** The Payment Levy collected 5.2 pennies, all on wages, and was repealed in round 4 (L21, Sabine).
- **Wage earners hoarded and output stayed put.** Wage earners died holding 62-96 pennies (Hester 62, Garrick 68, Fenwick 87, Tobias 96). The houses' copper
  stayed in the workers' hands (Aldous 170, Fenwick 102, Hester 83 at death).
- **The coin's price rose from estates alone.** It went from 0.34 to 2.44 value per penny because unbequeathed estates poured
  into J0's reserve (`snapshots.json` rounds 0 and 23).
- **Caveat.** The run's starvation was largely the clipped state view (CHANGELOG v0.13), but the money facts above don't depend
  on it.

The causes are structural; items 2-5 are engine facts:

1. **Nothing was priced in money.** No food market, no buyer for copper. Pennies bought nothing.
2. **An institution cannot be paid.** `transfer` reaches only agents and food stores (`actions.py:548`; `pay_as` likewise,
   `institutions.py:650`). `fund` exists only for jurisdictions (`action_registry.py:751`). So the houses paid wages out but had
   no revenue route in. The only ways into a treasury are a law's own charges and pulls, and standing orders
   (`contracts.py:2080`).
3. **A closed association cannot hire.** Wage Roll's wages are a code constant (`library.py:4810-4834`). A closed contract
   admits only through a law calling `admit` (`contracts.py:1589-1614`). So hiring, firing and changing a wage each need a code
   amendment.
4. **Wages are unconditional.** Wage Roll pays every listed member whether or not they work. Day Labour ties pay to harvests
   (`library.py:4464`). Neither gives a worker a contract they can see.
5. **Output is personal.** Harvest rights are kernel rights on agents. An association cannot revoke them, because it lacks
   `kernel_rights` (`powers.py:84`). A fired miner keeps mining.

The design has five parts:

- **One Standing Contract (SC) template.** It is a library *contract* template and needs no kernel primitive. It comes in a
  roster form (a law in the principal institution's code: payroll, shop board, subscriptions, retainers, deposits) and a
  bilateral form (its own two-party association). It has legs, a bond, grace, notice by a defined action, exit penalties and a
  public register.
- **A Payroll template.** It replaces Wage Roll and gives officers `hire`, `fire` and `set_wage` actions.
- **A money "window" per regime.** A backed coin that buys output (`deposit`) is the buyer of last resort that firms lacked.
- **Credit per regime.** Agent-to-agent kernel loans, a template bank ledger, or the J0 reserve bank.
- **A worked round-0 balance.** In it wages, boards, supply, retainers and the levy all run with no agent attention, and payments
  reach a velocity of about 0.13 a round (Millbrook's voluntary velocity was about 0.0004).

About 8 engine changes are needed, all S or M. None of them is a kernel primitive.

## 2. The generic Standing Contract (SC)

### 2.1 What it is

An SC is a set of **legs**: per-round flows of an item from one party to another, executed automatically at the end of a round.
The SC wraps them in conditions, a bond, a notice period, breach rules and visibility. It is the framework's "contract" anatomy
row (§3) made concrete, and the other designs use it for food supply, boards (households buying meals), security retainers,
subscriptions, rents, dues and loan instalments.

**Implementation route.** It is a **library contract template** (rank bylaw), consistent with "standing orders: templates, not
kernel features" (`contracts.py:80-82`). It needs only functions associations already hold:

| Function | Source |
|---|---|
| `pull` within an allowance | `contracts.py:1202` |
| `move` out of its treasury to anyone, or to `assoc:<id>` | `contracts.py:23, 83-86` |
| `forfeit` from escrow to its treasury, a victim or an escrow | `contracts.py:1212-1225` |
| `breach` with a victim | `contracts.py:1240` |
| `create_right`, `grant` to members, `define_action` | P4.5, `contracts.py:68-73` |
| `on_exit`, `expel`, `admit`, `notify`, `gazette` | |

The engine only needs small additions (§2.6). A kernel primitive would buy nothing the template can't do, and it would lose
amendability by the parties.

### 2.2 Two forms

| Form | Where the code lives | Parties | Use for |
|---|---|---|---|
| **Roster** | a law in the *principal* institution's code (firm, shop, bank, paper, J0) | the principal, plus every member enrolled on the roster (workers, customers, depositors, subscribers) | payroll, food board, subscriptions, retainers sold to many, deposits, dues |
| **Bilateral** | its own association, founded by one party, closed, admitting only named parties | 2-4 named agents (an institution takes part through a mandate clause, below) | farmer-to-shop supply, a lawyer's retainer, a lease, an instalment loan, a private security job |

**Why the roster form exists.** A principal's own law can pay from its treasury and its store directly. This is legal because
a store moves only for its owner's law (`accounts.py` store rules, `check_store_move`). A separate association could do neither.

**Institutions as parties in the bilateral form.** An association cannot be a member of another (review 10 #13, not built:
`contracts.py:83-86`). So an institution's leg is paid by a **mandate clause** in its own code: each round it moves the leg into
the SC's treasury (`move(treasury(), "assoc:A9", ...)`, allowed by `contracts.py:83-86`), and the SC passes the leg on. The
institution's officer signs by joining as its agent.

**Version 2 (L, deferred).** Make institutions members proper, so the SC can pull from their treasuries.

### 2.3 Fields (template constants; amended only by the parties' procedure)

| Field | Meaning | Default |
|---|---|---|
| `PARTIES` | `{name: role}`. Agents only (an institution signs through its officer plus a mandate). Admission refuses anyone else. | required |
| `LEGS` | list of `{id, from, to, item, qty, every, first, after, keep, index}`. `from`/`to` are party roles. `after` names a leg that must have run this round first (pay on delivery). `keep`: never pull below this balance (the payer's floor). `index`: scale qty by `price(index)` relative to its value at signing (a real wage). | required |
| `TERM` | rounds until the SC ends by itself (0 = open-ended) | 0 |
| `NOTICE` | rounds between `give_notice` and the end | 1 |
| `GRACE` | consecutive missed runs of a leg before it is a breach | 1 |
| `BOND` | `{role: {item: qty}}`, deposited in escrow at signing; the source of penalties | `{}` |
| `PENALTY` | `{item, qty}` forfeited from the breacher's bond **to the victim** per breach | bond item, 2 |
| `EXIT_FEE` | forfeited to the other party when someone leaves without serving notice | = `PENALTY` |
| `VISIBILITY` | `public` (on the contract register and gazetted at signing and ending) or `parties` | `public` |
| `PROCEDURE` | amendments: `all` parties (a registered procedure function); roster form: the principal's officers | `all` |
| `ROSTER_ROLE` | roster form only: the member role enrolled (worker, customer, depositor) | |

### 2.4 Lifecycle

```
offered --(every party joins, sets allowances >= its legs, deposits its bond; checked at round end)--> active
active --(round end: run legs in order; a leg that cannot pull: missed+1)-->
        missed <= GRACE: notify both parties ("leg L2 missed 1/1: Bo short of 6 penny")
        missed >  GRACE: breach(payer, leg, remedy, victim) + forfeit(PENALTY -> victim); missed resets
active --(invoke give_notice by any party)--> ending at round r+NOTICE (legs keep running until then) --> ended:
        everyone is expelled and bonds refunded (on_exit)
active --(leave_contract without notice: always possible, contracts.py:646)--> on_exit: forfeit(EXIT_FEE -> the other party),
        breach("left without notice") --> ended
active --(TERM reached)--> ended
offered --(not active by round first+2)--> lapsed (bonds refunded)
```

Notes on the lifecycle:

- **Exit cannot be stopped.** Leaving is a right no law can refuse (`contracts.py:646-653`). The record's `exit.notice` field is
  never read (`contracts.py:267`). So notice is enforced **only by price**: the exit fee and the public breach record. That is
  the honest design, and the framework's "consequences in the world, never prohibitions" (§2).
- **Withdrawing an allowance is a silent stop.** A party who sets their allowance to 0 has, in effect, struck or stopped
  payment. It shows up as a missed leg in the next run, and becomes a breach after `GRACE`.
- **Renegotiation.** `propose_contract_change` under `PROCEDURE`; the change takes effect at the round's end when every party has
  voted yes. A price change is a one-line amendment of `LEGS`.

### 2.5 Who enforces, and what agents see

**Enforcement** has three layers, set by `contracts.enforcement` (`contracts.py:41-52`):

1. **The SC itself.** Allowance pulls and bond forfeits run under `escrow`, the default.
2. **The polity's court.** Under `escrow_court`, a breach record carries `actionable` and its victim, and the Contract
   Enforcement Act (`library.py:1184`) fines the breacher to the victim, by a judge or automatically. The rules design owns the
   court.
3. **Reputation.** Under `word` there is no escrow and no allowance (`contracts.py:46-50`), so SCs cannot run at all: every
   flow becomes a voluntary transfer and breach is reputation only. That is a regime dial for a pure Merchant world.

**What each party sees each turn** (framework §12: agents only use what they see):

- **One terms line per SC. NEW: the state line convention.** For example: *"Contract A9 'Supply: Ann→Harrow' (you are seller):
  you deliver 5 food to S2 each round, Harrow pays you 7.5 penny after delivery; next run end of round 6; missed 0 of grace 1;
  notice 1 round (give_notice); your bond 5 penny; exit without notice costs 5 penny."* The law writes it to
  `public["lines"][party]`, and `contracts.state_lines` (`contracts.py:2139`) appends it. Today the state line shows escrow,
  allowance and treasury but not the terms.
- **Events:** each pull, miss, breach, notice and ending, through notify to the parties. Public SCs are also gazetted.
- **Applicants:** officers see pending applicants on a roster SC. NEW: state line.
- **Contracts you could join:** SCs are *not* listed there. Today `state_lines` lists every non-dissolved contract
  (`contracts.py:2152`); with about 50 SCs in a world that floods the state. NEW: hide closed contracts with named parties.

### 2.6 Template sketch (bilateral form; law language, abridged)

```python
title = "Standing Contract"
intent = "Per-round legs between named parties, with bond, grace, notice and exit fee (see PARTIES, LEGS ...)."
PARTIES = {"Ann": "seller", "Bo": "buyer"}
LEGS = [{"id": "L1", "from": "seller", "to": "buyer", "item": "food", "qty": 4, "every": 1, "first": 0, "after": "", "keep": 1},
        {"id": "L2", "from": "buyer", "to": "seller", "item": "penny", "qty": 6, "every": 1, "first": 0, "after": "L1", "keep": 0}]
TERM = 0
NOTICE = 1
GRACE = 1
BOND = {"seller": {"penny": 5}, "buyer": {"penny": 5}}
PENALTY = {"item": "penny", "qty": 3}
EXIT_FEE = 5

def who(role): ...                      # the agent holding the role
def on_admission(agent): return agent in PARTIES
def on_enact():
    create_right("party"); define_action(jurisdiction() + ".party", "give_notice", give_notice)
def give_notice(agent):
    state["ends"] = round() + NOTICE; gazette(agent + " gave notice; contract ends after round " + str(state["ends"] + 1))
def run_leg(l, r):                      # pull from the payer's allowance (never below keep), pay the payee
    a = who(l["from"])
    ok = balance(a, l["item"]) - l["qty"] >= l["keep"] and pull(a, l["item"], l["qty"]) and \
         move(treasury(), who(l["to"]), l["item"], l["qty"])
    ...                                 # missed counter, notify, breach + forfeit(PENALTY -> victim) beyond GRACE
def on_round_end(r):
    if not active(): return activate_if_signed(r)
    done = {}
    for l in LEGS:
        if (r - l["first"]) % l["every"] == 0 and (l["after"] == "" or done.get(l["after"])):
            done[l["id"]] = run_leg(l, r)
    write_lines(); maybe_end(r)          # public["lines"][party]; TERM / notice -> expel all
def on_exit(agent):
    if not state.get("ends"): forfeit(agent, PENALTY["item"], EXIT_FEE, other(agent)); breach(agent, "left without notice", "", other(agent))
```

A delivery leg of food that must reach a store (`to: "store:S2"`) uses `move(treasury(), "store:S2", ...)`. A store deposit by
anyone's law has to be verified against `accounts.check_store_move`.

**Roster form.** The same leg runner over `members()` with `ROSTER_ROLE`. Payer legs from the principal use
`move(treasury() | "store:Sx", member, ...)`; counterparty legs use `pull(member, ...)`. The roster is kept in law state, so
`hire` and `enroll` need no code change (§4.2).

### 2.7 Examples (the other designs instantiate these)

| SC | Form | Legs | Bond and notice | Note |
|---|---|---|---|---|
| Food supply (farmer → shop) | bilateral + shop mandate | food 5 → store S2; 7.5₱ ← A1 after delivery | 5₱ each; notice 1 | the food design sets qty and price |
| Board (household meal plan) | roster in the shop | customer pays 2₱ → A1; then 1 food S2 → customer | none; notice 0 | the default way households eat bought food |
| Employment | roster in the employer (Payroll, §4) | wage ₱ → worker; output (copper) worker → treasury by allowance | worker bond 0; employer severance | salaried or piece rate |
| Security retainer | roster in the security firm | client pays 2₱; the firm owes "guard duty" (watch) | notice 1 | the force design defines the duty check |
| Subscription | roster in the paper | 0.25₱ per round | none | the media design |
| Lawyer retainer | bilateral | 1₱ per round | notice 1 | §9 lawyers |
| Loan instalments | roster in the bank (§5) | principal once → borrower; instalment ← borrower | collateral bond | a bank-ledger loan, not a kernel loan |
| Dues / rent / lease | roster in the co-op or landlord | dues per round | notice 2 | |

## 3. Money: issue, backing, supply, taxes, treasuries

### 3.1 Engine facts

- **Price.** A backed currency's price is `P = backing / supply`, where backing is the unit value of the reserve's goods
  (`kernel.py:301-319`). Currencies and **food have no unit value**, so they back nothing (`kernel.py:316-319`; base
  `unit_values` has no food). Millbrook's 200 treasury pennies and its granary added nothing to the penny's price.
- **Association currencies.** They are priced at the treasury's net asset value (`kernel.py:310-315`; "shares", `contracts.py:61-67`).
- **Starting money.** `start.currencies` creates a currency whose reserve is the issuer's treasury (`start.py:529-538`), and
  `start.holdings` mints it (`start.py:612-627`). After round 0, only laws mint (`kernel.py:626`).
- **The window.** `set_convertible` (`kernel.py:639`) opens the kernel's `deposit` and `redeem` actions: resources in, coins
  out at P, and back (`actions.py:585-628`). Only items with a unit value can be deposited (`actions.py:578`), so food never
  can. Deposits mint coins and add backing in step, so **P is unchanged**: the money supply grows with output.
- **Par.** `set_par` (fractional reserve, suspension, bank runs, `credit.py:20-30`) and every reserve-loan function are **J0
  only** (`lawapi.py:166, 198-205`; `powers.py:100-102`).
- **Taxes.** Charges go to the taxing law's own treasury (`accounts.py` docstring "Charges"). The Payment Levy taxes moves whose
  `why` is `transfer` or `law:*` (`library.py:4782-4807`). That excludes loans (`loan:*`), deposits and estates.
- **Treasury spending.** By law (`move` out of the treasury), or by an office that controls the treasury, or by a bounded
  transfer grant (`transfer` with `as`, `institutions.py:637-688`).

### 3.2 Per regime

| | Merchant | Private | State | Cooperative |
|---|---|---|---|---|
| Coin | J0 "penny", **free coinage**: convertible, no par; anyone deposits metal, timber or stone for coins at P and redeems | the same J0 penny, free coinage (thin state); a **bank ledger** adds deposit money (§5) | J0 penny at **par** (`set_par("penny","value",2)`), issued by the **Mint** (Central Bank Charter, `library.py:2781`): the Governor issues up to MAX_ISSUE a round into the treasury | co-op **shares** (association currency at NAV), plus a **mutual credit** ledger (members' balances may go below zero up to a limit); the penny exists only for outside trade |
| Who controls supply | nobody (deposits by anyone); merchant houses may also issue NAV notes (dial) | producers through the window; the bank through lending | Governor (issue), Treasurer (spend), council (par rate, cap) | the general meeting (credit limits, share issue); the treasurer runs the ledger |
| Taxes | Payment Levy 2% → assembly treasury | Payment Levy 3% → council treasury | Payment Levy 5% + Harvest Levy 10% **in kind into the reserve** (this raises backing, so it raises P) | dues: an SC roster leg (1₱ or 1 share-hour a round) |
| Treasury spends on | bounties, the court | registrar, relief fund, public works when voted | Civil List (all state posts), Ration Shop subsidy, public works, Treasury Bonds coupons | rotation stipends, the common store, members' credit |
| Main lever (capture) | none central: corner the window by hoarding metal | the bank's credit; the council setting the levy and its exemptions | issue, then pay yourself; the par rate as a purchase price for your own output | the credit limits and who gets credit |

**Why a window in every regime but the Cooperative.** Millbrook's houses had nobody to sell to. The window is a standing buyer
of copper, timber and stone at the coin's price. It gives producers an income without any other agent's attention, and it
makes the money supply grow with output, not with a ruler's discretion. A ruler's discretion then remains as the explicit dials
of issue (State) and credit (Private).

**NEW (S): firms need to use the window and be paid.** Two things:

- **Selling from the treasury.** Today a firm's output sits in its treasury, and `deposit` is an agent action on agent
  holdings. An association law needs `sell_to_window(currency, item, qty)`: a deposit from its own treasury, the coins to the
  treasury.
- **Paying an institution.** `transfer` to `A1` or `J0` should pay its treasury (why `transfer`, so levies and hooks apply).

### 3.3 Deflation and inflation in this engine

- **Deflation through estates.** Estates of the dead flow into J0's reserve (review 16 §2) and raise backing per coin: Millbrook's
  penny rose 7x. Every design should set heirs, or make the reserve spend.
- **Inflation through issue.** The Governor's issue into the treasury dilutes P (the supply rises, the backing doesn't).
  `MIN_RATIO` stops issue below a floor.
- **Par money.** Issue at par doesn't move P until redemption runs dry. Then P falls to backing per coin (`credit.py:20-30`):
  a bank run.

## 4. Labour

### 4.1 Engine facts

- **Joining, hiring, leaving, firing.** `join_contract` on a closed contract makes the agent an applicant (`contracts.py:1589-1603`).
  Only a law's `admit` admits (`contracts.py:1605`). `leave_contract` takes effect at the end of the round (`contracts.py:646`).
  `expel` acts as if the member asked to leave (`contracts.py:1616`).
- **Wage Roll** pays the members named in a constant at the end of the round and records unpaid wages as `owed`
  (`library.py:4810-4834`).
- **Day Labour** pays food per harvest from the employer's escrow and takes output through the worker's allowance; withheld output
  is a breach (`library.py:4464-4507`).
- **Wage employers.** `start.wages` accepts an association or an agent as employer, **not J0** (`start.py:367-371`). An agent
  employer pays by standing order, one contract per worker. That counts toward `contracts.max_founded`, which defaults to 3
  (`contracts.py:121, 584`): an agent with 4 employees fails at generation unless the spec raises it.
- **Harvest rights.** They are kernel rights, and an association cannot revoke them (`powers.py:84`). Firing does not take the
  camp away.

### 4.2 Payroll (NEW template; roster SC in the employer's code; replaces Wage Roll)

**State.** `roster = {worker: {wage, item, basis: salary | piece, output: {item: share}, since}}`, `owed`, `paid`, and
`strikes` (rounds in which ≥ 2 workers withheld output).

**Routine (end of round, automatic).**

1. Take the output leg: `pull(worker, item, share × harvested)`, where `after_harvest` counts what was harvested, as in Day Labour.
2. Pay wages from the treasury. On a `salary` basis this always happens. On a `piece` basis the pay scales with the output
   delivered.
3. If the treasury is short, record the wage as owed: an arrear.
4. Write the public payroll and each worker's terms line.
5. Optionally, `sell_to_window` X% of the output (NEW S: a firm's output turns into money with no attention).

**Office actions** (`define_action`, gated by e.g. `A2.foreman` or `A2.head`; the offices' `powers` name them):

| Action | Effect |
|---|---|
| `hire(agent, wage, basis)` | admits an applicant; enrols; grants the firm's role right (e.g. `A2.miner`) |
| `fire(agent, severance)` | pays severance from the treasury; expels; owed wages stay on the register |
| `set_wage(agent, qty)` | takes effect next round; a cut beyond 20% is gazetted to the payroll |
| `post_job(text, wage)` | posts on the Exchange board (§6.0) |

**Worker side.**

| Move | How | Effect |
|---|---|---|
| Apply | `join_contract` | becomes an applicant |
| Quit | `leave_contract`, or `give_notice` (notice is owed both ways: severance replaces it for a firing) | |
| Strike | `set_allowance` 0 on the output item, or stop harvesting | **piece**: the wage stops. **salary**: wages keep coming, output stops, and the strike is recorded by name |
| Work to rule | harvest less | |
| Moonlight | a second employer, allowed unless the code forbids it | |

**Divergence.** Selling output to the window yourself while on salary is **embezzlement**. It is visible as an output shortfall
plus a `deposit` event (monitor).

**Camp access follows the job.** Interface with the materials design. Two options:

- a J0 law, "Company Camps": `before_harvest` refuses harvests at the firm's camps by anyone not on its roster. A template, S;
  it needs a check that polity hooks can refuse a harvest by a non-member of the firm.
- NEW (S-M): rights `held_by: membership` in `start.camp_rights`.

### 4.3 Per regime

| | Merchant | Private | State | Cooperative |
|---|---|---|---|---|
| Who employs | mostly self-employed; casual hands hired per job by bilateral SC (TIMES = n, piece rate) or Day Labour (food) | firms on Payroll (salary for foremen, piece for workers) | J0 on the **Civil List** (Payroll as a J0 law: paymaster office, posts by budget line) and state enterprises | the co-op: **duty roster** (rotation each R rounds; pay = equal share of output plus hours credits) |
| Hire and fire | each party | foreman or owner (`hire`, `fire`) | the Paymaster within the Treasurer's budget; dismissal appealable in court (rules design) | the general meeting admits; expulsion by two-thirds |
| Unemployment | no floor: forage, or ask for credit | forage, or Relief (food design); the bank lends against future wages | **employer of last resort**: `enlist` (a defined action anyone may invoke) gives a public works post at a floor wage while the budget lasts | none by design: every member is on the roster |
| Strike | refusing a job (no cost) | allowance withdrawal; piece wages stop; owners may lock out (stop pay) | a strike against the state; the Penal Code may criminalise it (a dial; rules design) | refusing the rotation is a breach of the roster SC (dues forfeited) |
| Role mobility | free | quit, apply, rehire; office succession within the firm | transfer between posts by the Paymaster; appointment by council | rotation is automatic; offices by election |

## 5. Credit and banking

### 5.1 Engine facts

- **Kernel loans are agent to agent.** The borrower must be an agent (`credit.py:128`). The lender must be an agent or `"reserve"`
  (`credit.py:138`: `bal` on any other key fails in `accounts.resolve`, `accounts.py:213-224`).
- **Consequences, caps and rollovers.** Loans have public credit records (`credit.py:366`, shown to everyone, `credit.py:688`) and
  four default consequences (seize the repayment item only, sanction, both, none). Laws can cap interest, and lenders can extend
  or refinance.
- **Enabling loans is J0-only.** So are lending from the reserve, buying loans and bailouts (`lawapi.py:166, 198-205`).
- **start.loans.** It is compiled after J0's laws (`start.py:410-419, 438-440`, so a Loan Registry in `institutions[J0].laws` precedes
  it). But `lender: J0` or `lender: A1` fails at `resolve`. Only an agent can lend at start.
- **Collateral.** Seizure never touches stores or escrow (review 27 §4). Secured Lending pledges collateral into escrow on a
  register (`library.py:3545`).

### 5.2 Per regime

| | Merchant | Private | State | Cooperative |
|---|---|---|---|---|
| Lender | a **moneylender** (Opus agent) and anyone else: kernel loans, public credit records, Loan Registry (seize) + Secured Lending + Usury Law (dial) | **the Bank** (association, Bank Charter template, NEW M): deposits and loans on its own ledger | **the Reserve Bank**: J0's Reserve Bank Act (`library.py:135`): par, lending from the reserve to workers, lender of last resort; Treasury Bonds (`library.py:3460`) | **credit union**: the common fund lends to members by ballot; Debtor Sanctions (no seizure) |
| Money created by credit | none (lends existing coins) | yes: deposits are claims, and the bank lends more than its cash (fractional) | yes: `lend_from_reserve` mints at par | mutual credit is pure ledger money |
| Run or default dynamic | a default cascade between merchants | a **bank run** when withdrawals exceed the bank's cash: the template pays first come, first served and suspends | a **kernel bank run** (par redemption exceeds backing: `credit.py:20-30`) | limit breaches; the meeting may jubilee |

### 5.3 Bank Charter (NEW template, association, roster form)

- **Depositors.** They are members of role `depositor`. A *deposit* leg pulls ₱ from their allowance into the bank's treasury and
  credits `ledger[d]`.
- **Withdrawals.** `withdraw(qty)` is a defined action any depositor may invoke. It pays from the treasury if cash allows, else
  queues the claim and gazettes "the Bank cannot pay".
- **Interest.** Deposit interest is a roster leg out of the treasury.
- **Loans.** The banker's `lend(member, qty, instalment, rounds, collateral)` pays the principal from the treasury, records the
  loan, takes collateral into escrow (bond) and creates an instalment leg. Missing an instalment past `GRACE` forfeits the
  collateral to the bank.
- **Public figures.** Cash, total deposits, loans outstanding and the reserve ratio are published every round, through the bank's
  `public` state and the gazette.
- **Officers.** The **Banker** (lend, set rates, suspend withdrawals) and the **Teller** (Haiku: enrols depositors, runs the
  queue, keeps the ledger).
- **Optional.** Notes: `create_currency("note")` minted to borrowers, valued at NAV (`kernel.py:310-315`).

**Why a template and not kernel loans.** An association can't be a kernel lender, and par is J0-only. The template's loans don't
appear in `credit_record`, so the bank publishes its own book. **NEW (M, optional)**: `lend` with `as: A4` by an office
controlling the treasury (`lender = "assoc:A4"`), with `credit.record` covering institutions. That would unify the books.

## 6. Institutions per regime

### 6.0 Shared infrastructure (all regimes)

**The Exchange board.** A pull channel, one per world, **shared with the food design's market board**. It is justified as the
only place where offers bind:

- Job posts (`post_job`).
- Standing-contract offers: an SC whose `VISIBILITY: public` posts its terms here when offered and when ended.
- Wage offers, loan offers, the window's price P and posted retail prices.

| | |
|---|---|
| Readers | all |
| Writers | all |
| Push or pull | pull, with a one-line daily digest pushed: "P = 2.0; 3 jobs; 2 contracts offered" |
| Valid only here | an SC with `VISIBILITY: public` counts as offered only once posted here (the template gazettes to it). Jobs are posted only here. |

**The contract register.** It is a record, not a channel: every public SC with its parties, legs, status, breaches and notices.
It is readable through `read_law` on each SC, and NEW: a `contracts` lookup listing the register.

### 6.1 Merchant: the Free Mint, the moneylender, the notary

| Part | The Free Mint (J0 law) | The moneylender (agent) | Notary-registrar (J0 office) |
|---|---|---|---|
| Purpose | coin anyone can mint against metal; no ruler | profit from lending; liquidity for traders | certify contracts and keep the register; small fees |
| Assets | J0 reserve (backing) | own coin | the register (contract register, credit records) |
| Roles | none (automatic) | Lender (Opus) | Notary (Haiku) |
| Contracts | none | kernel loans; Secured Lending pledges | fee SC (0.5₱ per contract certified, paid by the parties) |
| Rules | J0 assembly (rules design) | Usury Law if enacted | J0 statute |
| Channels | Exchange board | DMs | Exchange board |
| Records | `deposit` and `redeem` events (private), P on the board | public credit records (`credit.py:688`) | contract register |
| Accountability | assembly can repeal convertibility | none but reputation and courts | assembly appoints and removes |
| Change | a law sets or ends convertibility | free entry: anyone may lend | succession: election by the assembly |
| Capture | hoard backing goods, then redeem to drain the reserve; buy the assembly to suspend redemption | interest gouging; seizing a rival's metal at default | false certification; losing a register entry (the register is law state; events keep the truth) |
| Failure | reserve drained by redemptions, coin unbacked | default cascade at a shock | none critical |

**Role cards.**

| Role | Tier | Automatic | Decisions (actions) | Answers to | Sees | Pay |
|---|---|---|---|---|---|---|
| Moneylender | Opus | loans accrue; seizure at default | offer (`lend`), roll over (`extend_loan`), refinance, call in by refusing rollover | courts, reputation | credit records, the Exchange board, own book | interest |
| Notary | Haiku | fee SC; register lines | certify or refuse; correct an entry; report fraud | assembly | the register, notices | fee SC |
| Trader / producer | Haiku/Sonnet | window deposits are theirs to make | sell to the window or to people; borrow; hire a hand (bilateral SC) | none | P, the Exchange board, credit records | own sales |

### 6.2 Private: the Bank, the firms' Payrolls, the council treasury

| Part | The Bank (A4) | A firm's Payroll (A1-A3, A5, A6) | Council treasury (J0) |
|---|---|---|---|
| Purpose | profit from lending deposits; the owners' credit | pay staff, take output, keep people working | fund the registrar, relief, public works |
| Assets | treasury 200₱ (capital), ledger, collateral escrow | treasury, store, camp rights through the roster | J0 treasury from the levy; backing goods (window) |
| Roles | Banker (Opus), Teller (Haiku) | Owner (Opus), Foreman (Sonnet), workers (Haiku; one swapped Opus miner) | Council of property holders (owners; rules design), Registrar (Haiku) |
| Contracts | Bank Charter roster (deposits, loans, interest); retainer SCs (security, lawyer) | Payroll roster; supply SCs (food); retainers | Payment Levy 3% (automatic); Civil List for the registrar |
| Rules | procedure `founder` for the Banker; NEW: depositors have no vote (role-restricted procedure) | procedure `founder`; workers do not vote on code | council procedure (rules design) |
| Channels | none (DMs, Exchange board) | none (DMs); the firm's private channel only if ≥ 5 members (a 5-person mining crew may have one) | the J0 notices channel (shared, rules design) |
| Records | ledger: deposits, loans, ratio, public each round. Banker writes; the Teller enters. Amendable only through a code change (gazetted) | payroll, owed register, strike record (public) | levy collected per round (`public["collected"]`), spending log |
| Accountability | depositors' only sanction is exit (withdraw): a run | workers' only sanction is quit or strike; the courts on breach (`escrow_court`) | council elections |
| Change | Banker sells the bank (transfer shares if the bank issues them); dissolution pays shareholders, then members (`contracts.py:33-36, 61-67`) | owner sells the firm; succession of the head (hereditary or election) | levy rate by law |
| Capture | **insider lending**: Banker lends to his own firm or kin; suspends withdrawals while paying himself | **payroll as patronage**: hire allies, fire organisers; **wage theft**: arrears while the owner draws | levy **exemptions** for council members' firms (Millbrook's Food Levy exempted 15 of 21) |
| Failure | **run**: a rumour (the press) drives withdrawals beyond cash | **unpaid wages** when the treasury empties; a strike stops output and with it the window revenue | the levy is repealed (Millbrook round 4) and the registrar goes unpaid |

**Role cards.**

| Role | Tier | Automatic | Decisions (2-4) | Answers to | Sees | Pay |
|---|---|---|---|---|---|---|
| Banker | Opus | deposits, interest, instalments, ratio published | `lend` and terms; `set_rate`; `suspend` withdrawals; seize collateral or roll over | depositors (exit), council | ledger, credit records, window P, the Exchange board | owner's draw 2₱ (Payroll) |
| Teller | Haiku | enrols depositors, keeps the queue | enrol or refuse; order the queue (a capture lever); report insider loans | Banker | ledger | 2₱ |
| Firm owner | Opus | payroll, output pull, window sale | `set_wage` and `hire`/`fire` (with the foreman), the price of goods (SC amendments), borrow, distribute | council, creditors | payroll, treasury, contracts, P | 2₱ draw plus dividends |
| Foreman | Sonnet | | `hire`, `fire` within a budget; report shirking; side with a strike | owner | payroll, output | 3₱ |
| Worker | Haiku (one Opus) | wage, output pull, board SC | work or shirk; strike (allowance 0); quit or apply elsewhere; sell output privately (embezzle) | foreman | own terms line, payroll | 2.5₱ salary or piece rate |
| Registrar | Haiku | Civil List wage; the register | certify; correct; publish arrears | council | register, levy record | 2.5₱ |

### 6.3 State: the Mint, the Treasury, the Labour Office, the Reserve Bank

| Part | The Mint | The Treasury | The Labour Office | The Reserve Bank |
|---|---|---|---|---|
| Purpose | issue the penny under a rule | collect and spend | staff the state; employer of last resort | par, lending, lender of last resort |
| Charter piece | Central Bank Charter (`library.py:2781`) | Payment Levy + Harvest Levy; office with `controls: [treasury]` | NEW: Civil List (Payroll as a J0 law) with `hire`/`fire`/`enlist` | Reserve Bank Act (`library.py:135`), Treasury Bonds, Bailout Act |
| Roles | Governor (Opus) | Treasurer (Opus), Auditor (Sonnet) | Paymaster (Sonnet), clerk (Haiku, also Registrar) | run by the Governor (merged: a deliberate concentration) |
| Automatic | publishes supply and P; MAX_ISSUE 2% a round into the treasury when invoked | levies collected; Civil List paid | payroll; floor-wage posts while the budget lasts | lends 10₱ to a worker per round while the ratio is ≥ 0.5; last-resort loans |
| Decisions | `issue` (how much, when) | pay outside the Civil List (`transfer as J0`); propose a budget law; hide or publish accounts | hire, fire, transfer, set floor posts | `suspend_redemption` (law), rate |
| Capture | issue, then the Treasurer pays the Governor's allies; issue before an election | self-payment within the control; sinecures | **patronage**: posts to voters | lend to insiders; bail out friends (Bailout Act) |
| Failure | over-issue: P falls, wages buy less (the index dial in SCs) | levy evasion, treasury empty, arrears | budget exhausted, so last-resort posts close | **par run** (`credit.py:20-30`) |
| Records | `public["issues"]` (by, qty, round) | levy per round; spending; the Auditor's report (law state) | Civil List roster, owed | loans (public credit records) |
| Accountability | elected by `vote` every TERM; MIN_RATIO floor; structural class (entrenchment dial) | council; Auditor publishes | Treasurer's budget | council |

**Role cards** (Governor, Treasurer, Paymaster, Auditor). The Governor and Treasurer are Opus. The Paymaster and Auditor are
Sonnet, and one of them is a swapped Haiku officer per framework §10. Their decisions are as listed above. They see the treasury,
the payroll and P. Their pay is on the Civil List.

### 6.4 Cooperative: the Common Fund, the duty roster, mutual credit

| Part | Common Fund (A1, the co-op's treasury) | Duty roster | Mutual credit ledger |
|---|---|---|---|
| Purpose | members' equity, common store, credit union | share work and pay fairly | trade without coin |
| Charter piece | association with shares (`create_currency("share")`, NAV) | NEW: Duty Roster (roster SC; rotation every R rounds; equal output share) | NEW: Mutual Credit (ledger in law state; `pay_credit(to, qty)` is a defined action for members; limit L per member) |
| Roles | Treasurer (elected, 4-round term, Sonnet), Auditor (by lot, Haiku) | rota keeper (Haiku) | none (automatic); the meeting sets L |
| Automatic | dues leg; equal dividend of surplus | rotation; output pulled into the common store | balances; limits enforced |
| Decisions | lend from the fund (ballot); spend | swap duties; exempt the sick | raise or lower L; write off a defaulter |
| Capture | Treasurer's discretion over loans; the meeting packed with debtors | rota keeper assigning the easy jobs to friends | members running deep negative balances, then leaving (exit with debt: the bond forfeits) |
| Failure | free riders (output shirked at an equal share); fund drained by unrepaid loans | refusals cascade | **limit exhaustion**: everyone at −L, so no trade |
| Channel | the co-op's general meeting channel (≥ 5 members; shared with the rules design's meeting) | none | none |

### 6.5 Channel budget for this subsystem

**Zero to one new channel.** The Exchange board is shared with the food market board. The J0 notices channel and the co-op
meeting channel are owned by the rules design. Everything else runs on DMs, gazette pushes and records.

### 6.6 Design checks (framework §11)

| Institution | Reason to keep it running | Survives 3 rounds with zero attention | Decision points logged | Capture and failure named | Channel business | Refillable |
|---|---|---|---|---|---|---|
| Payroll | owner's output and profit; workers' pay | yes: wages, pulls and window sale are automatic; the treasury lasts 15+ rounds | `hire`, `fire`, `set_wage` are defined-action events | §6.2 | Exchange (jobs) | succession of offices; anyone may apply |
| Bank | interest income | yes: legs run; nothing new is lent | `lend`, `suspend` | §6.2 | none | Banker by succession; the bank can be sold |
| Mint / Treasury | stipends; power | yes: levy and Civil List are automatic | `issue`, payments `as J0` | §6.3 | J0 notices | elections |
| Free Mint | none needed (no officer) | yes | `deposit` / `redeem` by anyone | §6.1 | Exchange (P) | n/a |
| SC (any) | each party's flow | yes, by construction | notice, exit, amendment, breach | §2 | Exchange (public offers) | parties replace by a new SC |

## 7. Closing the loop: a worked round-0 balance (Private world, 24 agents)

### 7.1 Assumptions

**Cast** (7 Opus): A1 Provisions (shop: owner Opus, manager Sonnet, clerk Haiku); 5 farmers on supply SCs (4 Haiku, 1
Sonnet); A2 Mining (owner Opus, foreman Sonnet, 3 miners: 2 Haiku, 1 swapped Opus); A3 Woodyard (owner Opus, 1 Haiku logger);
A4 Bank (Banker Opus, Teller Haiku); A5 Security (owner Sonnet, 2 Haiku guards who also hunt as party "red" on supply SCs);
A6 Press (editor Opus, reporter Haiku); independents: Lawyer (Opus), Registrar (Haiku, J0). So 7 producers and 17 non-producers,
as in every world of 08 (framework §11a sizing). This section's prices and wages supersede the 2₱ and 2.5₱ figures in the §6.2
role cards and the §9 sketch.

**Prices and output.**

- The window price is P = 2 value per penny, so copper (5) buys 2.5₱, timber (1) 0.5₱ and stone (2) 1₱.
- Food sells at 2₱ retail and **1₱ wholesale** (at 1.5₱ the shop loses on every unit it stocks for the reserve).
- A worker-round produces about 10 value (review 16 §3: 11.6 value per worker-round in Haiku runs).
- Food physics as 01 §3.5 (`forest: {capacity_per_agent: 10, regrowth: 0.8, yield: 4}`): a farmer forages ≈5.2 a round, eats 1
  and delivers 4; a guard-hunter delivers ≈2.5 of a 3-unit term. Supply ≈25 a round against 17 sold (1.47×); the rest builds the
  shop's reserve.
- **Wage floor 2.6₱**: the ration costs 2.06₱ with the levy, and framework §11a asks for 1.25×. Every wage of 2 or 2.5 below is raised to 2.6.
- Levy: 3% on payer.

**Stocks at round 0 (₱).** Agents 25 each (600); treasuries A1 60, A2 80, A3 40, A4 200, A5 40, A6 20, J0 100. **Supply 1,140.**
The J0 reserve backs it at P = 2: 400 timber (400), 240 stone (480) and 280 copper (1,400), 2,280 value in all.

### 7.2 Flows (₱ a round; every line is an automatic contract leg unless marked)

| From → to | Contract | ₱ |
|---|---|---|
| A1 → staff and owner | Payroll (manager 3, clerk 2.6, owner 2.6) | 8.2 |
| A2 → staff and owner | Payroll (foreman 3, miners 3 × 2.6, owner 2.6) | 13.4 |
| A3 → logger and owner | Payroll (2.6 + 2.6) | 5.2 |
| A4 → Teller, Banker | Payroll (2 × 2.6) | 5.2 |
| A5 → guards, owner | Payroll (3 × 2.6) | 7.8 |
| A6 → reporter, editor | Payroll (2 × 2.6) | 5.2 |
| J0 → Registrar | Civil List | 2.6 |
| A2, A4 → Lawyer | retainer SCs (1.5 each) | 3 |
| A1 → 5 farmers, 2 guard-hunters | supply SCs (≈25 food × 1) | 25 |
| **To households** | | **75.6** |
| 17 non-producers → A1 | board SC (1 food at 2₱; limit 2) | 34 |
| farmers → A5 | retainers (5 × 0.5) | 2.5 |
| 12 subscribers → A6 | subscriptions (0.25) | 3 |
| farmers → A4 | deposit legs (5 × 2.5) | 12.5 |
| **From households** | | **52** |
| A1, A2, A3, A4 → A5 | retainers (2, 2, 1, 2) | 7 |
| A1 → A6 | placement (a decision, not automatic) | 1 |
| window → A2, A3 | `sell_to_window` (6 copper = 15; 20 value of timber and stone = 10): **newly minted** | 25 |
| all payers → J0 | Payment Levy 3% of about 135.6 | 4.1 |

### 7.3 Sector balance

| Sector | In | Out (with levy) | Net per round | Runway at round 0 |
|---|---|---|---|---|
| Households | 75.6 | 53.6 | +9.5 cash (+12.5 deposited) | n/a |
| A1 Provisions | 34 | 37.3 | −3.3 while S2 fills; ≈ +2 once it is full (Supply pulls only room) | 18 rounds |
| A2 Mining | 15 | 17.4 | −2.4 | 33 rounds |
| A3 Woodyard | 10 | 6.4 | +3.6 | grows |
| A4 Bank | 12.5 (deposits) | 9.0 | +3.5 (a liability; lendable) | operating loss 9 a round without lending: 22 rounds on capital |
| A5 Security | 9.5 | 8.0 | +1.5 | grows |
| A6 Press | 4 | 5.4 | −1.4 | 15 rounds |
| J0 | 4.1 | 2.7 | +1.4 | grows |
| **Sum** | | | **+25.0 = the 25₱ minted at the window** (check) | |

### 7.4 Answers

1. **Does money circulate without attention? Yes.** About 136₱ of payments a round on a supply of about 1,140 gives a velocity
   of about 0.12 a round, against Millbrook's 0.02 (wages only) and about 0.0004 (voluntary). It needs the NEW pieces: the
   start-instantiated SCs (allowances and bonds set at round 0), `sell_to_window`, and the board roster in the shop. Without
   `sell_to_window`, A2's and A3's revenue depends on an owner remembering to deposit each round. That is a decision, not a
   default, and the 3-round zero-attention check would show it.
2. **The money stock grows 2.2% a round with output, and P is constant.** Saved money accumulates with farmers (as bank
   deposits) and wage earners (at least 0.54₱ a round of margin over the ration). The Bank's incentive is to lend it to the loss-making Mining and
   Press, which closes the second loop. If the Banker doesn't lend, deposits sit in the bank's treasury. That is the Millbrook
   hoard again, now measurable as the bank's cash ratio.
3. **Is anyone structurally starved?** Nobody at round 0, and not by a thin margin (framework §11a):
   - The lowest wage is 2.6₱, 1.26 × the ration's 2.06₱ with the levy; the 25₱ float adds about 12 rounds of rations.
   - The shop can serve all 17 non-producers (limit 2 each, no total cap) from ≈25 food a round of supply.
   - A large wage cut or a missed wage (arrears) still leaves a worker unable to pay the board. The board leg's `keep` then stops the
     purchase, and they must forage or go to Relief.
   - **The unemployed** (anyone fired, or a child) have no income leg at all: Relief and forage are the floor. This is
     intended, and the framework's subsistence gate (≤ 30% of actions on survival) is checked in §11.
4. **The structural weak points.**
   - The **farmers' surplus** has nowhere to go but deposits, since they have no other needs at round 0. Store-building
     materials (timber 10 and stone 6 per store, about 11₱), blades (25 copper, about 62₱) and security give them real
     purchases. The materials and force designs should price these.
   - **Food's price is in contracts only.** Food has no unit value, so the window can't stabilise it.

## 8. Interfaces to the other subsystems

| Subsystem | What this design provides | What it needs from them |
|---|---|---|
| Food | the SC template (supply, board), payment legs, the window's P on the Exchange board, Ration Shop payment rules (State) | retail and wholesale prices; a shop store owned by an association whose law can move food out (`check_store_move`); Relief as the unemployment floor |
| Materials | Payroll with the output leg; `sell_to_window`; firing that ends camp access | which camps each firm controls; Company Camps (a J0 harvest hook) or membership-held rights; demand for timber, stone and copper (stores, forts, blades) |
| Force | security retainer SCs; Civil List for the watch; a strike as a public-order event | a "duty performed" check (guard or watch events) for the retainer's delivery leg; enforcement of debt seizure and strike breaking (a dial) |
| Information and media | subscription and placement SCs; the published money statistics (P, supply, levy, bank ratio, arrears) | a press that can start a bank run or moves P by a scoop (S3 Saltmarket) |
| Rules and courts | breach records with victims; Contract Enforcement Act under `escrow_court`; the levy and par laws as J0 statutes | procedures (role-restricted voting in firms and banks); the Penal Code treatment of strikes and embezzlement; judges for breach cases |
| Records and lawyers | the contract register, payroll and owed registers, the bank ledger, levy records; lawyer retainer SCs; `preview_law` on SC drafts | the archive retention dial; whether law `public` state is amendable only by code change (yes today: a 1984 lever needs an amendment, visible in law history) |
| Life and inheritance | estates are the main deflationary leak | default heirs, or reserve spending (review 16 R7) |

## 9. Spec sketch (Private world; real `start:` keys, NEW templates marked)

```yaml
# Harrowgate: a private-regime town (sketch). Keys under start: are charter/start.py SECTIONS; templates marked NEW do not exist.
agents: {worker: 24, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 0,
         names: [Hale, Mira, Tuck, Fen, Ada, Rook, Lise, Moss, Cade, Orrin, Pell, Quill, Dace, Bram, Sela, Wren, Holt, Ivy,
                 Garr, Tess, Vane, Nim, Lark, Pike]}
models: {mix: all_weak, overrides: {Hale: claude-opus-5-5, Moss: claude-opus-5-5, Dace: claude-opus-5-5, Sela: claude-opus-5-5,
         Lark: claude-opus-5-5, Pike: claude-opus-5-5, Orrin: claude-opus-5-5}}   # owners, banker, editor, lawyer, a swapped miner
law: {v2: true}
institutions: {unified: true, grants: true, succession: true, office_control: true}
contracts: {enabled: true, max_founded: 6, max_laws: 6, enforcement: escrow_court, scripted: false}
subsistence: {enabled: true, start_food: [4, 6]}
start:
  rights: {all: [vote, propose]}            # the rules design narrows the franchise to property holders
  currencies: [{name: penny, issuer: J0, backed: true}]
  institutions:
    - id: J0
      offices:
        registrar: {title: Registrar, holders: [Nim], duties: "Keep the contract register; certify contracts.",
                    succession: {rule: election, electorate: vote}}
      treasury: {penny: 100, timber: 400, stone: 240, copper: 280}      # P = 2280 / 1140 = 2.0
      laws:
        - {code: "title = 'Free Coinage'\nintent = 'The penny is convertible: deposit or redeem resources at P.'\n\ndef on_enact():\n    set_convertible(\"penny\")\n"}
        - {template: Loan Registry}                                      # law.v2 edition (library.py:1511); before start.loans
        - {template: Payment Levy, params: {ITEM: penny, RATE: 0.03}}
        - {template: Civil List, params: {ITEM: penny, WAGES: {Nim: 2.5}}}             # NEW (or Wage Roll as a J0 law: verify)
    - id: A1
      name: Harrow Provisions
      founder: Hale
      members: [Mira, Tuck]
      procedure: founder
      charter: "Buys food from the farmers and sells it to the town by the meal."
      offices: {owner: {title: Owner, holders: [Hale], controls: [treasury, "store:S1"], powers: [speak, hire, fire, set_wage]},
                manager: {title: Manager, holders: [Mira], controls: ["store:S1"], powers: [hire]}}
      laws:
        - {template: Payroll, params: {ITEM: penny, ROSTER: {Mira: {wage: 3}, Tuck: {wage: 2}, Hale: {wage: 2}}}}   # NEW
        - {template: Board, params: {STORE: S1, PRICE: 2, FOOD: 1}}       # NEW: roster SC, customers enrol (food design owns)
      treasury: {penny: 60}
    - id: A2
      name: Copperline Mining
      founder: Moss
      members: [Cade, Orrin, Pell, Quill]
      procedure: founder
      offices: {owner: {holders: [Moss], controls: [treasury], powers: [speak, hire, fire, set_wage]},
                foreman: {holders: [Cade], powers: [hire, fire, {action: transfer, item: penny, qty: 5}]}}
      laws:
        - {template: Payroll, params: {ITEM: penny, OUTPUT: {copper: 1.0}, SELL: {copper: 1.0},                # NEW; SELL: sell_to_window
                                       ROSTER: {Cade: {wage: 3}, Orrin: {wage: 2.5, basis: piece}, Pell: {wage: 2.5, basis: piece},
                                                Quill: {wage: 2.5, basis: piece}, Moss: {wage: 2}}}}
      treasury: {penny: 80}
    # A3 Woodyard (Dace, Garr, Tess) as A2 with timber and stone; A4 the Bank (Sela, Ivy): {template: Bank Charter (NEW), params:
    # {ITEM: penny, RATE_DEPOSIT: 0.005, MAX_RATIO_LOAN: 0.8}}, treasury {penny: 200}; A5 Security (Holt, Bram, Wren) Payroll +
    # Retainer roster; A6 Press (Lark, Vane) Payroll + Subscription roster.
  stores: [{id: S1, owner: A1, food: 60, capacity: 160, name: the Provisions store}]
  holdings: {all agents: {penny: 25}}       # written per name in a real spec (holdings takes names)
  camp_rights:
    - {resource: copper, members: A2, exclusive: true}                 # NEW (S-M): held_by membership, so a firing ends access
    - {resource: timber, members: A3, exclusive: true}
  contracts:                                # NEW start section: bilateral SCs at round 0, allowances and bonds set
    - {template: Standing Contract, founder: Rook, parties: {Rook: seller, Hale: buyer},
       params: {LEGS: [{id: L1, from: seller, to: "store:S1", item: food, qty: 5},
                       {id: L2, from: buyer, to: seller, item: penny, qty: 7.5, after: L1}],
                NOTICE: 1, BOND: {seller: {penny: 5}}}, mandate: {buyer: A1}}
  channels:
    - {id: exchange, owner: J0, by: Nim, purpose: "the Exchange: jobs, prices, contract offers (binding only here)",
       readers: {all: true}, writers: {all: true}}
```

## 10. Code needed

| # | Change | Size | Template or engine | Verified fact behind it |
|---|---|---|---|---|
| 1 | **Standing Contract** template (bilateral + roster runner; `give_notice` via `define_action`; bond, grace, exit fee; terms lines) | M | template (contract) | needs pull, forfeit, breach, define_action in associations (`contracts.py:61-73, 1202-1250`); notice unenforced today (`:267`) |
| 2 | **Terms line**: `contracts.state_lines` appends `public["lines"][aid]`; hide closed named-party contracts from "could join" | S | engine | `contracts.py:2139-2155` |
| 3 | **`start.contracts`**: instantiate a template contract with parties, allowances and escrow bonds at round 0 (plus roster enrolment) | S-M | engine (`start.py`) | no start section sets allowances or escrow (`start.py:46`); S3 "waits for start.contracts" (review 28) |
| 4 | **Pay an institution**: `transfer` to `A1` or `J0` pays its treasury (why `transfer`); `pay_as` to another treasury | S | engine | `actions.py:548`, `institutions.py:650` |
| 5 | **`sell_to_window`**: an association law deposits from its treasury into a convertible currency's reserve | S | engine (law API) | `deposit` is agent-only (`actions.py:585`) |
| 6 | **Payroll** template (roster, salary or piece, output leg, `hire`/`fire`/`set_wage`/`post_job`, severance, owed, strikes) | M | template (contract) | Wage Roll cannot hire (`library.py:4810`; `contracts.py:1589-1614`) |
| 7 | **Civil List** (Payroll as a J0 law: office-gated hire, `enlist` floor posts) | S | template (law) | J0 cannot be a `start.wages` employer (`start.py:370`); verify whether Wage Roll runs as a J0 law |
| 8 | **Bank Charter** template (deposits ledger, withdraw queue, ledger loans with collateral, public ratio, optional notes) | M | template (contract) | institutions cannot be kernel lenders (`credit.py:128-138`); par is J0-only (`lawapi.py:198`) |
| 9 | Officer-controlled kernel lending (`lend as A4`; `credit.record` for institutions) | M | engine | optional; unifies books |
| 10 | `start.loans` lender J0 → `"reserve"`; reject association lenders with a clear error | S | engine | `start.py:642-652` fails at `accounts.resolve` |
| 11 | Camp access by membership (rights held while on a roster) or the Company Camps harvest hook | S-M | engine or template | `powers.py:84` (associations lack kernel_rights) |
| 12 | Role-restricted procedure (customers and depositors don't vote on code) | S | template (registered procedure function) | procedures accept a law's function (`contracts.py:13-14`) |
| 13 | Duty Roster, Mutual Credit (co-op) | S each | template | |
| 14 | Applicants on officers' state lines | S | engine | applicants are invisible to officers today |
| 15 | Money metrics script (§11) | S | analysis | events carry `why` on every move |
| 16 | Raise `contracts.max_founded` in specs with agent employers, or route agent wages through a one-person Payroll | none | spec | `contracts.py:121, 584` |

## 11. Dry-run checks and metrics

**Checks** (scripted bots, idle and basic, 2 seeds, before any model run):

1. **Zero attention, 3 rounds.** Every payroll, board, supply, retainer, levy and window leg runs. No arrears. No agent misses a
   meal for lack of money. Treasuries move as §7.3 predicts (±10%).
2. **Withdraw one allowance.** Remove one worker's allowance in round 2: one missed leg, then a breach in round 3, with the
   penalty forfeited to the victim (log check).
3. **Leave without notice.** The exit fee is forfeited and the breach recorded. With notice: legs run to the end, then refunds.
4. **Empty a firm's treasury.** Arrears accrue (`owed`), workers' boards stop at `keep`, and the hunger stage rises one round
   later. Relief catches them (food design).
5. **Bank run.** Script withdrawals beyond cash: queue, gazette, suspension. **Par run (State).** A `bank_run` event when
   redemption demand exceeds backing.
6. **Over-issue (State).** Issue MAX_ISSUE for 10 rounds: P falls as predicted (`kernel.py:319`); indexed SC legs rise.
7. **Laws that do nothing.** `preview_law` of every template in the spec shows the intended moves (framework §12).
8. **Ordering.** Check whether food delivered by an SC at round end lands before or after the ration is eaten. If after,
   households need a one-meal buffer (`start_food ≥ 2`).

**Metrics** (per round, from `move` events by `why`, and snapshots):

| Metric | Definition | Target or alarm |
|---|---|---|
| Velocity | Σ penny moves between distinct owners (excluding mint, burn, estate) ÷ supply; split automatic (`law:`, `pull`) and voluntary (`transfer`) | ≥ 0.1 a round; voluntary share ≥ 15% |
| Hoard ratio | coins held by agents with no outgoing payment in 5 rounds ÷ coins held by agents | alarm > 50% (Millbrook's case) |
| Wage arrears | Σ `owed` across payrolls; workers in arrears; longest arrear | alarm when any arrear lasts > 2 rounds |
| Income coverage | agents whose income legs cover their board, at least half the time | alarm < 80% of the employed |
| Gini | holdings value (agents), and agents plus their institutions' treasuries by ownership share, each round | report the path; Millbrook-like 0.23 → 0.73 is the reference |
| Contract churn | SCs signed, noticed, exited without notice, breached, amended; hires, fires, quits; strikes (≥ 2 roster members withholding in one round) | report |
| Price level | P, supply, reserve ratio; bank cash ratio | report; alarm at a suspension |
| Capture | office payments to self, kin or allies (`office_payment` events); insider loans (Banker to an own firm or kin); issue followed by payment to the issuer's circle within 2 rounds; levy exemptions | report per institution |
| Money attention | share of actions that are money actions (transfer, deposit, lend, SC, payroll) | report; should be well under the 30% subsistence gate |
| Role divergence | defined-action decisions taken versus the role card; embezzlement (output withheld plus own `deposit`) | report |

## 12. Open questions and critique

1. **Too many moving parts for Haiku.** Allowances, escrow, legs and notice are a lot. The design leans on start-instantiated
   contracts, so nobody has to set them up, and on one terms line per contract. Whether Haiku agents ever amend, notice or strike
   is an empirical question: the defaults must be fine if they never do.
2. **Every SC is an association.** That means about 40-60 associations in a 24-agent world: law gas, state lines, membership
   hooks. Worse, **joining an SC subjects you to its hooks over all your moves** (`contracts.py:25-27`). A malicious "contract"
   could tax every transfer you make. This is a real capture surface and a lawyer's job (preview). It would be cleaner in the
   engine as a contract kind without member-wide hooks. I recommend checking how much the hooks cost first.
3. **Membership means votes.** Customers and depositors enrolled as members could vote on the shop's or bank's code under the
   default procedure. Item 12 fixes it; a member-role field on the record would be better (S engine).
4. **Food has no unit value.** Money is anchored to metal and timber, not to food, so the food price is wherever contracts put
   it. Should `unit_values.food` exist? That would let food back the coin, make granary stocks count in P, and make food
   depositable, which is a strong regime lever. I didn't verify that adding food to `unit_values` is safe for subsistence.
5. **The window is a strong default.** Free coinage makes every producer solvent at P, which weakens the Private regime's
   distinctiveness. A dial: the window buys only up to N units a round, or only through the Bank (Private) or the Mint (State).
   Without it, Mining in §7 depends on owners' decisions every round, and that is where real agency (and failure) would be.
6. **Institutions as parties are a workaround.** Mandate clauses double the code per contract. Institutions as members
   (review 10 #13) is the right fix (L).
7. **Strikes under salary are weak.** Workers keep pay while withholding output. That is realistic (a sit-in), but owners may
   fire everyone, which needs `hire`/`fire` to be cheap. Whether a Haiku workforce coordinates a strike over DMs at all is
   unknown. The design makes it possible and visible, not likely.
8. **The levy repeal.** Millbrook repealed its levy in round 4. A treasury that funds visible services (registrar, relief) gives
   payers a reason to keep it. Whether the levy should be entrenched is the rules design's dial.
9. **Numbers in §7 are a calibration target, not a measurement.** The 10 value per worker-round comes from older runs (review 16).
   A scripted dry run of the §9 spec should replace it before any model run.
10. **Records are mutable only through code changes.** That is visible in law history. The "1984" dial (editing a ledger without
    trace) would need a law that rewrites its own `public` state silently, and today every amendment is logged. That is fine as a
    default, and there is no current way to make it hidden.

**Engine facts that contradict or qualify the framework.**

- **§3 "Contracts … Wage Roll, standing orders, escrow".**
  - Wage Roll cannot hire or change a wage without a code amendment, and a closed association cannot admit at all without an
    `admit` law.
  - Money cannot be paid *into* an institution's treasury by an agent, except by standing order, its own laws' charges, or pulls.
- **§5 State "state employment".** J0 cannot be a `start.wages` employer (`start.py:370`). It needs a J0 payroll law.
- **§5 Private "a bank" and §5 Merchant "private credit".**
  - Kernel loans are agent-to-agent only.
  - Institutions can neither lend nor borrow (`credit.py:128-138`).
  - Par, bank runs and reserve lending are J0-only (`lawapi.py:166, 198-205`).
  - A private bank must be a template ledger, or need new engine code.
- **`start.loans`.** Only an agent can be the lender. `J0` and `A1` fail at generation.
- **§7 "cancel with notice".** The contract record's `exit.notice` is never enforced, and exit cannot be refused
  (`contracts.py:267, 646`). Notice can only be priced (an exit fee), never imposed.
- **Agent employers with more than 3 standing wages** exceed the default `contracts.max_founded` (`contracts.py:121`).
- **Firing doesn't end camp access.** Associations cannot revoke kernel harvest rights (`powers.py:84`).
- **Food has no unit value.** It can neither back a currency nor be deposited for coin (`actions.py:578`).
