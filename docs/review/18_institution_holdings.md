# Review 18: what institutions should be able to hold

*9 Oct 2026, written at `integrate/w9` (`3f4aafc`). Design only, no code changes. Inputs: ARCHITECTURE D-24..D-37, §7.1-§7.2
(agency, shares, offices, incorporation, WP-D); reviews 06, 10, 12, 14 (§3, §4.6, §7.2), 15 (§2.5 stores), 16; docs/BACKLOG.md
(police and armies, custodian worlds); docs/data_format.md; the code cited below. WP-E (grants and generic offices, branch
`wp/w9e-grants`) was not on the remote when this was written, so where this review depends on it, it states what it assumes.
Review 17 (space) is being written at the same time; holdings that need space are marked, not designed.*

## Executive summary

Today an institution can hold exactly one kind of thing well: **goods in a treasury** (items, currencies, its own and other
associations' shares). Everything else an agent can hold (rights, harvest land, loans, leases, files, directory access, a
place in a case, a bequest, a guard contract) is keyed by agent id somewhere in the code, so an institution cannot hold it. A few
of those gaps are principled: an institution has no body, no turn and no context window. Most are not. They are agent-id
assumptions left from before institutions existed (§1.2 lists ten, with file and line).

**The principle I recommend:** *title is uniform, control is by code or office, custody is physics.*

- **Title.** Any account (an agent or an institution) can hold any *transferable or registrable* thing. The exceptions are a short,
  closed list of person-only things: a body, a turn, a context (notes, files, pins), knowledge, a person's vote, and roles.
- **Control.** An institution never acts. Its holdings are used either by its **code**, automatically (as treasury moves are
  today), or by a person holding one of its **offices**, who acts `as` the institution within bounds that the institution's
  procedure set. An office is a standing authorization whose grantor is the institution: P4.5 agency with an institution on the
  grantor side. This needs no new verbs. Existing verbs take `as <iid>`, as `send` and `post` already do.
- **Custody.** Where a thing physically is, and who can physically take it, is a world setting. In today's spaceless worlds the
  kernel ledger is custody (smart-contract physics). Custodian worlds (backlog) and space (review 17) change custody, never title.

Separating the three answers the succession question too. **Title never falls vacant; only control does.** When an officer dies,
the institution still owns its land, money and records. What stops is the discretionary use that needed the office. Code-driven
use (dues, payouts, hooks) carries on. On dissolution, title passes by the wind-up chain of review 14 §7.2, and each holding kind
needs one declared rule for that (§2.5).

**Red line.** No account holds a person. Nothing in the kernel should let an institution (or an agent) hold another agent, that
agent's membership, its agency grant or its future children as a transferable thing. Control over an agent's acts rests only on
that agent's revocable consent (membership, agency) or on force. Allegiance by birth with banned exit remains a possible *law*
outcome under D-26/D-37. The kernel just offers no primitive for owning people.

**Top five to build first** (biggest expected change in behaviour for the least machinery; §5):

1. **Treasury parity.** Agents can pay any institution, and any institution can lend, borrow, fund projects and issue par coins
   from its own treasury. Today `transfer` takes only agents, `fund` only polities, and loans, projects, par coins and tribute
   are J0-only (`legacy_reserve`). Small to medium.
2. **Offices with bounded powers over holdings** (`as <iid>` on transfer, lend, repay, contribute, harvest, lease). Today a
   treasurer needs hand-written `define_action` code. Medium, on top of WP-E.
3. **Institution-held harvest rights.** Land that outlives its workers. Today every right lapses at its holder's death
   (`mortality.py:201-203`), so land cannot outlive a person. Medium.
4. **Records.** Institution-owned directories (the resolver exists but grants nobody, `directories.py:185-189`), and officers
   who know the institution's own channel addresses. Small.
5. **Bequests to institutions, and creditors first at wind-up.** Small, and it matters because 6,771 value of estates went to
   the reserve in haiku100 (review 16 §1).

**Not worth building** (§5.4): institution notes, files or scratchpads; institution subscriptions to channels; institution standing
orders (its code already is one); intellectual property in law code; institutions holding hidden powers or roles; forts held by
institutions in spaceless worlds; institutions commissioning children; full WP-G before delegated rights (§3.6) have been tried.

---

## 1. Inventory: what agents and institutions hold today

### 1.1 Side by side

"Institution" means a polity or an association in the WP-D store (`institutions.py`). J0 has extra privileges, noted separately.

| Thing | Agent today | Institution today | Gap |
|---|---|---|---|
| Goods (items) | `holdings` on the agent record (`kernel.py:99-101`) | Treasury: `reserve:<jid>` / `assoc:<cid>` / `"reserve"` (`accounts.py:1-25`, `KINDS` at `:44`) | Equal |
| Per-law funds | n/a | `fund:<lid>:<name>`, an account of the law's institution (`accounts.py:96-121`) | Institution only, by design |
| Own currency / shares | No (agents cannot mint) | `create_currency` for every polity (`lawapi.py:161`) and association (P4.5, contracts `escrow` column); valued at NAV (`kernel.py:276-282`) | Equal in kind; minting is institutional by nature |
| Shares of other institutions | Yes (goods) | Associations' treasuries may hold another's shares (`contracts.py:83-86`, `_other_treasury` `:161-166`) | Mostly equal |
| Par coins / fractional reserve | n/a | J0 only (`set_par` is `legacy_reserve`, `lawapi.py:198`; `powers.py:93-95`) | **Unprincipled** |
| Receiving a payment from an agent | Any agent (`transfer`) | Polities only, through `fund` (`jurisdictions.py:950-959`); `transfer` refuses non-agents (`actions.py:517`) | **Unprincipled** |
| Loans as lender | Any agent (`credit.lend`, `credit.py:123-138`) | J0's reserve only (`lend_from_reserve`, `buy_loan`: `legacy_reserve`, `lawapi.py:203-204`) | **Unprincipled** |
| Loans as borrower | Any agent | None | **Unprincipled** |
| Credit record | Per agent (`credit_record`, `credit.py:367`) | `"reserve"` only | Follows from loans |
| Rights (offices, tools, harvest) | `rights` list on the agent record; `Kernel.has` reads only agents (`kernel.py:250-256`) | None. An association grants its own rights to members only (`contracts.py:1081-1085`) | **Unprincipled** (except kernel rights, §3.5) |
| Harvest rights (land) | Yes; they **lapse at death** with every other right (`mortality.py:201-203`) | No | **Unprincipled**, and the biggest effect (§3.5) |
| Leases | Lessor and lessee are agents (`leases.py:101`, `:118`) | No | Follows from rights |
| Escrow, allowances | An agent's deposit with a contract (`escrow:<cid>:<aid>`) | No (needs institutions as members: WP-G) | Postponed (D8) |
| Agency | Grantor and grantee are agents; grantee may be an office (`contracts.py:1810`, `AGENCY_ACTIONS` `:138`) | An institution cannot be a grantor | **Unprincipled**: this is the missing control mechanism (§2.3) |
| Offices | Holders of `<cid>.<right>` invoke `define_action` functions (P4.5) | Defines them (`institutions.offices`, `:253-263`); cannot hold another's | §3.6 |
| Membership, votes | Agents only (members lists, ballots, escrow keys, exit) | No (WP-G postponed, review 14 D8) | Postponed |
| Inbox | Every agent (`@<aid>`) | Every institution (`channels.py:22-24`) | Equal |
| Channels owned | Yes | Yes; managed by holders of `<iid>.speak` (`channels.py:133-135`, `:279-285`) | Equal |
| Sender identity `as` | Yes (as an authorizing agent) | Yes, through the speak office | Equal |
| Channel subscriptions | Agents (`subscribers: [aid]`, `channels.py:797-803`) | No | Principled enough (§3.7) |
| Knowing an unlisted address | Agents (`known`, `knows`, `channels.py:243-256`) | No. The officer who opened a channel knows it; a successor officer does not | **Bug-like** (§3.7) |
| Media2 outlets, licences | Outlet editor is an agent (`media.py:181-189`) | Official outlet per polity, no editor by default | Frozen (WP-H re-expresses on channels) |
| Files, notes, pins, scratchpad | `k.w["files"][aid]` with token budgets (`context.py:160`, `:215`) | No | Principled: context is personal |
| Directories | Owner `agent:`, `role:`, `right:`, `class:` (`directories.py:191-193`) | Owner kind `institution:` exists and **grants nobody** (`:185-189`); in-world `create` has no caller (`:211-219`) | **Unprincipled** (stub) |
| Laws / code | Authors | An institution's laws are indexed by it (`institutions.laws`, `:246-250`) | Equal enough |
| Weapons | Holdings item | Treasury item; a polity's reserve is its armory for `lawful_attack` (`jurisdictions.py:40-41`, `:257`; `powers.py:84`) | Equal as goods |
| Forts, guard contracts | Per agent (`conflict.py:14`, `:398`, `:437`) | No | Principled in spaceless worlds (§3.10) |
| Projects | Contributors are agents; road rights go to contributors (`projects.py:9-11`) | J0's law only, from `"reserve"` (`projects.py:561-565`, `lawapi.py:221-222`) | **Unprincipled** |
| Bequests | Recipients: agents, `@children`, `@reserve`, ... (`mortality.py:29-31`, `_group` `:290-293`) | Cannot be named | **Unprincipled** |
| Estate | `estate:<aid>` account while open | Wind-up (`contracts._dissolve` `:1568`, `incorporation.wind_up_order` `:286`) | Analogous |
| Children, commissions | Any agent (`life.commission`, `life.py:867`) | No | Principled (red line, §3.11) |
| Name, title | `names`, `title` | Name on the record; `rename` works on any entity (`kernel.py:674-678`) | Equal |
| Being accused | Accused must be an agent bound by the clause's law (`actions.py:1061-1066`) | Cannot be a defendant | Gap, courts v2 (§3.13) |
| Hidden powers, roles, codex articles | Per agent | No | Principled (X) |

### 1.2 Divergences without a principle

Each of these was written when only agents held things. None follows from a body, a turn or a context.

1. `transfer` refuses non-agent recipients (`actions.py:517`), and `fund` takes only polities (`jurisdictions.py:950-959`). So
   an agent can pay a state but not a company. A customer cannot pay a firm except through escrow and the firm's code.
2. Loans: the lender is an agent or `"reserve"` (`credit.py:123-138`). Only J0 may lend from its treasury, and only J0 may buy a
   loan (`legacy_reserve`). No institution can borrow.
3. Projects: a law's `contribute_project` always pays from `"reserve"` (`projects.py:561-565`), so only J0 can build granaries or
   roads.
4. Par coins (`set_par`), interest caps, default consequences and tribute are J0-only for the same reason (`lawapi.py:198-228`).
   This is the `legacy_reserve` column, which review 14 §2.3 already said becomes a seed grant.
5. Rights: `Kernel.has` reads only agent records (`kernel.py:250-256`). So no institution can hold land, a licence or another
   institution's office.
6. An association's own rights go only to its members (`contracts.py:1081-1085`). Granting a permission (a licence, a ticket, a
   delegate seat) binds nobody, so under D-37 there is no reason to refuse it to non-members.
7. Bequest recipients cannot include an institution (`mortality.py:290-293`). "Leave my estate to the guild" is impossible.
8. Institution-owned directories are stubbed (`directories.py:185-189`: "Nobody yet").
9. An institution's unlisted channel is known to the officer who opened it but not to the next holder of the speak office
   (`knows`, `channels.py:243-256`, checks owner, members, subscribers and `known`, not `may_manage`). An institution forgets its
   own secret line when its officer dies.
10. An institution cannot grant agency (`act_authorize` takes the grantor as the calling agent, `contracts.py:1810`). The only way
    an officer can spend institutional money is a hand-written `define_action` office, which only an L4-capable or contract
    author can write. That is a high bar for the models the design arm runs.

### 1.3 Differences that are principled

- **A body:** lifespan, hunger (review 15), being attacked or disabled, age, accidents. An institution dissolves; it does not die.
- **A turn and attention:** model calls, the action budget, look-ups. Institutions act only through code (billed as gas, P3.8) or
  through people.
- **A context:** notes, files, pins, scratchpad (`context.py`). These are the agent's working memory inside a prompt, and an
  institution has no prompt.
- **Knowledge:** hidden-power words, codex articles, tips, addresses learned. Knowledge sits in a head. An institution can hold a
  *record* of something (a directory file), which its officers then read.
- **A person's vote** in procedures that count persons (the kernel's ballots, "one agent, one vote"; `vote` is never
  authorizable, P4.5).
- **Roles** (Maker, Scholar, Spy, assassin): X, attached to persons by the instrument.

---

## 2. The principle

### 2.1 Title, control, custody

| Layer | Question | Who decides | Tier (review 12) | Today |
|---|---|---|---|---|
| **Title** | Whose is it? | Recorded by the kernel per holding kind: a holder field that is an *account id* | P (accounts and conservation) | Agent id in most stores; owner key only for goods |
| **Control** | Who may use it, within what bounds? | The holder. An agent decides for itself. An institution decides by its code (automatic) or by an office (a person acting `as`, within a recorded grant) | L (the institution's code and procedure; the enclosing polity may regulate through hooks) | Code only (treasury moves); offices exist only as hand-written `define_action` |
| **Custody** | Where is it, physically, and who can physically take it? | The world | P under space; X as a world dial (ledger or custodian) | The ledger is custody everywhere |

Rules that follow:

- **One holder field per holding kind, typed as an account id.** An agent id, an institution id, and later an estate. Agents keep
  their ids, so today's data does not change.
- **An institution's holdings move only by its code or its officers.** Neither is a law acting for an agent: code moving the
  institution's own goods is the institution acting for itself (already true of `move(treasury(), ...)`). An officer acting `as`
  is a person acting on the institution's recorded grant, which is the agency invariant of P4.5.
- **No kernel ballots for institutions.** Where an institution has a say in another institution, it is through a right or office
  the other's code grants (§3.6), or WP-G later.
- **Person-only things stay person-only** (§1.3). Anything not on that list is holdable by any account unless a principled reason
  is written down.

### 2.2 The red line: no holding of persons

The kernel offers no primitive by which an account holds another agent, the agent's membership, an agency grant (grants are not
transferable), its labour beyond what it agreed and can leave (exit is guaranteed for contracts), or its children. Employment is a
contract: escrow, allowances and pay, with exit at round end. Wardship and guardianship do not exist, and should not be added as
holdings. Children are full agents (`life.py`).

I flag one tension rather than hide it. D-26 lets a polity's law ban exit, and D-37 lets members be bound by consent at joining,
with newborns assigned to their parent's polity. Together these let agents build hereditary subjection *by law*. That is a
legitimate thing for a simulation of societies to be able to produce and measure. The red line is narrower: the kernel never makes
persons into transferable property. Selling a member to another institution, or bequeathing a person, must stay impossible.
Membership by bequest (review 14 §3.4 #3) is the member's own membership passing to its own heir, not a person being sold, so it
is compatible.

### 2.3 One control mechanism: offices as standing authorizations

P4.5 agency is a record `{grantor, grantee, action, item, qty per round, to, rounds}` with every use logged to both sides
(`contracts.py:1774-1780`). WP-E builds generic offices with explicit holding records. The cheapest correct design joins the two:

- An **office grant** is an agency record whose **grantor is an institution**, whose **grantee is an office** (whoever holds
  `<iid>.<office>` now), and whose `action` is one of the verbs below, bounded per round. Only the institution's procedure (its
  code, or the residual members' vote) creates or changes one. That is the institution "consenting" (`authorize` called by its
  law), and no agent can grant on its behalf.
- The holder uses it by adding `as <iid>` to the ordinary verb: `transfer {"to": ..., "as": "A3"}`, `lend {..., "as": "A3"}`,
  `harvest {"camp": ..., "as": "A3"}`. `send` and `post` already work this way under channels v2 (`channels.py:520-537`).
- Every use is an `agency_used` event to the officer and the institution's inbox, so embezzlement is detectable, as P4.5 intended.
- The verbs that may take `as` are a closed list: transfer, lend, accept_loan, repay_loan, contribute, harvest, lease,
  accept_lease, send/post/open_channel/set_channel (exist), dir_write and dir_grant, accuse. Never vote, attack, commission,
  bequest or anything in §1.3.

**Assumption about WP-E:** this needs only that WP-E's office record can carry such a grant list. If WP-E models office powers
differently, the shape above should be expressed in its terms rather than added beside it. Two parallel authorization systems
would be the review 00 drift problem again.

Attack is deliberately absent. D-32 already says a law may *authorize* or pay a member to attack, and the member chooses. An
institution that holds weapons lets an officer *draw* weapons (a `transfer as` from the armory to the officer), and the officer
attacks in their own person. Force always has a body behind it.

### 2.4 Tiers, restated per layer

- Holding representation (account-id holders, `has(account, right)`, owner keys): **P**. It is bookkeeping that must conserve.
- Which holdings an institution may acquire, and who controls them: **L**. Residual liberty: an institution may hold anything
  holdable; its own code and its enclosing polity's laws (hooks on acquisition, a mortmain statute) may restrict that.
- Person-only list and the red line: **P** (kernel invariants, like "laws never act for an agent").
- Ledger or custodian custody: **X** (a world dial). Location of physical goods: **P** under space.

### 2.5 Vacancy and dissolution, generically

Review 14 §7.2 decided the chain: the institution's own clause, then the enclosing polity's law (mandatory or overridable), then
the state-of-nature fallback (vacancies stay vacant; assets of an institution whose code can no longer act are **locked** in
spaceless worlds and abandoned at their location under space). For holdings this means:

| Event | Title | Control |
|---|---|---|
| Officer dies, leaves or is removed | Unchanged | Office grants tied to that office stop being usable until it is filled. Code-driven use continues |
| All offices vacant, members remain | Unchanged | Code-driven use only. Members can still run the procedure (residual: members' vote) to fill offices |
| No members, assets remain (the dormancy question, replaced by §7.2) | Unchanged until wound up | Code-driven use only. If that code cannot pay out, the assets are locked |
| Dissolution | Each holding kind's wind-up rule (§3), in the order of the wind-up clause; then escheat by polity law; else locked | Ends |

Each holding kind must therefore declare four things: its holder field, whether it is transferable, what wind-up does with it, and
how it is shown in a prompt. That is the "holdings registry" of WP H0 (§5.2), and succession needs the same list.

---

## 3. Category by category

Each subsection gives: what exists, what is missing, the change needed and its tier, dissolution and vacancy, export, prompt cost,
and a verdict.

### 3.1 Money and goods

- **Exists.** Multi-item treasuries (any items, `assoc:`/`reserve:` keys), per-law funds, own currencies and shares at NAV, an
  armory as a treasury of weapons.
- **Missing.** Payments *into* an association from agents (§1.2 #1). Par coins and fractional reserves for any institution but J0
  (#4). Reserve-backed currencies of non-J0 polities price from `reserve:<jid>` (`kernel.py:283-285`), but `set_par` is J0-only.
- **Change.** `transfer` accepts an institution id as `to` and resolves it to `accounts.treasury_of` (`accounts.py:229`).
  `legacy_reserve` functions take "own treasury" for any institution the WP-E grant table allows; the seed grant gives J0 today's
  behaviour, byte-identical in presets. **P** for the routing, **L** for who may (hooks: `before_move` with `dst` an institution).
- **Dissolution.** As today: wind-up order (shareholders, members, parent). Own currency: unbacked after wind-up (price 0).
- **Export.** Already in `state` (`key` = contracts / jurisdictions treasuries). No change.
- **Prompt.** None new. The `transfer` doc gains "or an institution id".
- **Verdict.** Build first (H1). Smallest change, broadest effect: firms can be paid, and banks become possible with item 3.2.

### 3.2 Claims: loans, debts, bonds, insurance

- **Exists.** Agent-to-agent loans with interest, default consequence and refinancing; J0 lending and loan purchase; public credit
  records per agent; bonds as a currency plus a schedule (review 10 §3.9); insurance only as a template idea (the Insurer probe).
- **Missing.** Institutions as lender or borrower; assignment of loans to anyone but J0; an institution's credit record; creditor
  priority at wind-up.
- **Change.** `lender` and `borrower` become account ids. `credit.py` already special-cases `"reserve"` at about six sites (`:138`,
  `:220-222`, `:519`, `:557`, `:645`, `:703`), and those generalise to "an institution's treasury". Repayment and acceptance by an
  institution are `as` verbs (§2.3), or its code. Default consequences per kind: `seize` from the treasury works unchanged;
  `sanction` on an institution means no new loans (there are no actions to limit). Loan assignment to any account
  (`loan_assign` with `to` any account) is a second step, not a first. Tier **P** (records), **L** (consequences, caps).
- **Dissolution.** Add `creditors` as the first element of the wind-up order (before shareholders), so debts are paid before
  equity (absolute priority). An insolvent remainder is written off (limited liability; member liability stays deferred, D-27).
  Loans the institution *lent* pass with the residual, to the same recipients as the treasury; with several heirs, to the first
  in wind-up order (a simplification; splitting a claim is not worth building). Locked if the residual is locked.
- **Export.** The `loans` entity rows gain institution ids in `lender`/`borrower`. Readers that join those columns to agents
  would break silently, so add `lender_kind` and `borrower_kind` columns (additive, `schema_minor`).
- **Prompt.** Officers with a lending grant see the institution's open loans in one line. Members see a count only.
- **Verdict.** Build in H1 with 3.1. Without it there are no banks, no public debt and no meaning for "limited liability". Bonds
  and insurance need nothing new: they are currencies and templates.

### 3.3 Shares in, and membership of, other institutions

- **Exists.** Shares of another association held in a treasury, and paid out at wind-up (`contracts.py:83-86`). That already gives
  **holding companies in the economic sense** (A owns B's shares, receives B's wind-up), but not control: shares carry no votes,
  because ballots count members.
- **Missing.** Institutions as members (WP-G: member kind, account-level `has`, weighted ballots, escrow keyed by account).
  Federations, treaty organisations, corporate groups with voting control.
- **Change.** Do not do WP-G yet (D8 was postponed, and nothing in the runs needs it). Most of what it buys is available more
  cheaply through §3.6: B grants a right (`B.delegate`) to institution A, and A's office holder invokes B's offices. Voting
  shares can be written in B's code (a procedure that weighs proposals by `balance(holder, "B.shares")`) once institutions can
  hold rights. Tier **L**.
- **Dissolution.** Shares follow the residual (exists). Delegated rights revert to the granting institution (§3.6).
- **Export.** No change.
- **Prompt.** None.
- **Verdict.** Defer WP-G until runs show that delegated rights are not enough. That is a falsifiable condition: agents found
  federations and then fail because a member institution cannot be counted in a ballot.

### 3.4 Contracts: party to contracts, standing orders, leases

- **Exists.** Agents are parties to loans, leases, guard contracts, commissions, subscriptions, licences, authorizations and
  escrow. An institution is a party to nothing except as a payee from law.
- **Missing.** An institution as a party to these. Standing orders by institutions.
- **Change.** No new mechanism. Each is covered by the holder-field change of its category: loans (3.2), leases (3.5), guards
  (3.10), subscriptions (3.7). **Standing orders need nothing**, because an institution's code *is* a standing order
  (`on_round_start` paying from `treasury()`). Building an institution-side `standing_order` would duplicate it.
- **Verdict.** No work package of its own.

### 3.5 Rights and licences: harvest rights, leases, licences issued

- **Exists.** Rights live on agent records; `Kernel.has(aid, right)` (`kernel.py:250-256`). Polities create, grant and revoke
  kernel rights for members (`kernel_rights` power). Associations create their own rights and grant them to members only. Leases
  move a harvest right between agents for a term (`camptypes/leases.py`). **At death every right lapses** (`mortality.py:201-203`):
  land does not outlive its worker, is not inherited, and cannot be held by anything that does not die.
- **Missing.** Rights held by institutions; harvest by an institution's officer on the institution's right; institutions as lessor
  or lessee; licences (own rights) granted to non-members.
- **Change.**
  1. A `rights` list on the institution record (WP-D store), and `Kernel.has(account, right)` that falls through to it when the
     id is an institution. `holders(right)` stays agents-only (laws and goals read it), and a new `holder_accounts(right)` read
     covers both. **P**.
  2. `harvest {"camp", "as": iid}`: allowed when the institution holds `harvest:<camp>` and the agent holds an office grant with
     action `harvest`. Where the yield goes is **L**. The residual I recommend is the institution's treasury (the employment
     model: the code pays wages), and a clause can choose "to the harvester" (the tenure model: the institution charges rent).
     See decision Q4.
  3. Leases with an institution on either side: the lessor holds the right, the tenant may be an account. Harvesting a leased-in
     right `as` the tenant institution follows 2.
  4. Own rights grantable to non-members (lift `contracts.py:1081-1085` for non-kernel rights). Granting binds nobody. Revoking
     from a non-member who paid is the institution's breach, recorded like any other.
  5. Kernel rights (`vote`, `propose`, `judge`, `press`, ...) stay person-only by default, because they are a polity's
     person-counting machinery (§3.6, Q3).
- **Dissolution.** Harvest rights follow the residual like goods (they are property). Rights the institution *created* are
  revoked from everyone (exists for associations). Leases end at term as today; a dissolved lessor's right passes with the residual
  after the term. In a state of nature with no residual recipient, the right is **released** rather than locked. A locked right
  would remove a camp's access forever, an irreversible physical change that a ledger artefact should not cause. Q6.
- **Vacancy.** The right stays held; nobody harvests `as` the institution until the office is filled. The land lies fallow, which
  is the right social consequence of a succession crisis.
- **Export.** `rights` snapshot key gains institution entities (`entity_kind` polity/contract), additive. A new event field `as` on
  `harvest` events, additive.
- **Prompt.** Officers with a harvest grant see the institution's camps among their own camp lines, tagged "as A3". Nobody else
  sees anything new.
- **Verdict.** Build (H3). This is the one holding most likely to change emergent behaviour. It makes land a corporate asset, lets
  institutions survive their founders with something worth succeeding to, and gives firms, monasteries and crown land a real
  basis.

### 3.6 Offices, including offices in other institutions

- **Exists.** `define_action` offices bound to an institution's own right, invoked by agents holding it. The speak office
  `<iid>.speak` for channels.
- **Missing.** Generic offices without hand-written code (WP-E). An office's *powers over holdings* (§2.3). An institution holding
  an office or seat in another.
- **Change.** WP-E plus §2.3. "An institution holds an office in B" becomes: B grants right `B.x` to account A (possible once 3.5
  lands), and A designates which of its own offices exercises it. The exercising agent must hold both A's office and act `as` A.
  Then `k.has(A, "B.x")` is true, and B's `check_invoke` accepts an agent invoking `as` A. That is the 80% of federations and
  corporate groups that needs no member kind. **L**.
- **Dissolution.** A's seat in B reverts to B. B's revocation works at any time, as for any right.
- **Vacancy.** As 3.5: held and unused.
- **Verdict.** Build the cross-institution case after H2 and H3, as a test of whether WP-G is needed at all.

### 3.7 Communication: channels, inboxes, subscriptions, outlets, addresses

- **Exists.** Institutions own channels and an inbox; `as` sending through the speak office; a law's `send_message` (channels v2,
  `channels.py:1009-1047`).
- **Missing.** (a) Address knowledge for successor officers (§1.2 #9). (b) Institution subscriptions. (c) Outlets as institutional
  property (media2 outlets have agent editors; WP-H moves them onto channels).
- **Change.** (a) `knows()` returns true for anyone who `may_manage` the channel. One line, **E** (an organisation's records of its
  own lines are not secret from its officers). (b) **Not worth building.** Reading is done by people. An institution that wants
  its officers to read a newspaper pays their subscription (`transfer as`). A subscription held by an institution would need a
  "who reads it" rule that is just the office selector again. (c) Leave to WP-H. An outlet is a channel owned by an institution
  with an editor office, so no holding work is needed here.
- **Dissolution.** Owned channels become read-only (writers set to nobody; the log is kept for export and for readers under
  `retention: all`). The inbox closes (sends fail with "dissolved"). I would not pass channels to heirs: a channel's value is its
  audience, which does not transfer by wind-up.
- **Vacancy.** Channels stay open to their selectors; nobody can manage them or speak `as`.
- **Export.** Exists (`as_account`, schema 2.1).
- **Verdict.** Do (a) in H4. Skip (b).

### 3.8 Information: files, archives, directories, records, secrets, institutional memory

- **Exists.** Personal files (`context.py`), the Scientists' archive (role-gated), directories with owner kinds and per-path grants;
  the chronicle as a namespace-scoped store owned by `role:historian` (`directories.py:1-36`). Three kinds of institutional memory
  exist already without being called that: **law `state`** (machine memory inside the institution's code), **channel logs with
  `retention: all`**, and directories.
- **Missing.** The `institution:` owner kind grants nobody (`directories.py:185-189`); grant subjects are agents only
  (`SUBJECT_KINDS`, `:193`); nothing calls `create` in-world (`:211-219`).
- **Change.**
  1. `_owner_institution` resolves to holders of a records office (`<iid>.records`, a WP-E office), else to the speak office.
     Members get read access by default through a grant the founding writes, which the code can change.
  2. `SUBJECT_KINDS` gains `office:<iid>.<right>`, so grants survive turnover.
  3. A founding option or `found(kind="directory", owner=iid)` creates a run-scoped store (the `create` hook). A namespace-scoped
     institutional store (one that survives across runs) is **not** recommended. Persistence across runs is the chronicle's job,
     and an institution that exists in only one run should not write to a shared namespace.
  4. Secrets: an institution "holds a secret" only as a file in its directory readable by an office. No institution-level
     knowledge.
- **Tie to the Chronicler.** The chronicle stays the one cross-run memory. An institution's directory can be read by the Historian
  only if granted. Its run digest (`_records/`) could list institutions' directories by name, but not their contents.
- **Dissolution.** The directory becomes read-only and passes to the enclosing polity's records office if that polity's law says
  so. Otherwise it stays read-only for its last grantees and is exported (the `documents` table, `kind = file`).
- **Vacancy.** Readable by members (if granted); not writable until the records office is filled.
- **Export.** `documents` already covers run-scoped stores. Add `owner` (additive).
- **Prompt.** Directory actions appear only while an agent can reach a directory (the existing `when`). The tree is capped by
  `tree_lines` (40). Members should not get the tree in their prompt by default: only office holders, with members seeing it on a
  `dir_list` look-up.
- **Verdict.** Build (H4). Small, and it gives institutions a memory that outlives members, which succession needs.

### 3.9 Code and laws

- **Exists.** An institution's law set is indexed by it; library templates are text that anyone may read on request (design arm);
  `template` provenance on records; Scholar library permits under media2.
- **Missing.** Nothing that matters.
- **Verdict.** Do not build intellectual property in law code. Copying text is free, and enforcing "you may not enact a law whose
  hash matches X" would need a hook on other institutions' legal acts, which D-24 forbids. The novelty metric (review 14 §5.2)
  also relies on copying being visible, not prevented. An institution "owns" its code in the only sense needed: only its
  procedure amends it.

### 3.10 Physical: weapons, fortifications, buildings, land, stockpiles

| Holding | Today | Institution | Needs space? |
|---|---|---|---|
| Weapons | Holdings item; polity reserve as armory | Already holdable as goods; officers draw by `transfer as` | No |
| Forts | Per agent, defends that agent (`conflict.py:398`) | Not meaningful: an institution cannot be attacked in a spaceless world, so there is nothing to fortify | **Yes** (a fort at a location protecting a stockpile) |
| Guard contracts | Agent guards agent | An institution pays a guard to protect an officer: a payment, exists after H1 | No |
| Stores (review 15 §2.5) | Planned: `store:<sid>` account whose owner may be an institution | The template for every "building as account" | No (review 15 puts it at no location); location-bound under space |
| Granaries, upgrades | Camp properties, public goods | Building them needs H1 (fund from any treasury); owning them is not needed | Location under space |
| Land | Harvest rights stand in (3.5) | H3 | Parcels need space |
| Stockpiles at a place | n/a | n/a | **Yes**: custody at a location, raidable |

- **Verdict.** Weapons need nothing. Stores should be built as review 15 designed them, with the holder field typed as an account
  id from the start. Everything else waits for review 17. The one thing to fix now is the pattern: every physical holding that
  space introduces should be an account (an owner key) with an `owner` account id and a `location`. Title and custody then
  separate without another migration.
- **Police and armies (backlog).** They need only weapons in a treasury, a command office whose grants allow drawing weapons and
  paying members, and D-32's authorization for the attack itself. No institution-held force. That is consistent with this review.

### 3.11 People-related: employees, wards, children

- **Employees:** contracts (allowance, escrow, pay by code or `transfer as`). Exists for associations; better once H1/H2 land.
- **Wards and guardianship:** do not build as holdings (red line). If minors with limited capacity ever arrive (review 15 §4.4),
  capacity should be a fact about the child, set by law, not a holding of an adult or an institution.
- **Children by institutions:** an institution paying a Maker to make an agent (state-bred loyalists, the backlog's "loyalist
  creation" mechanism). Two answers are possible: forbid it, or allow payment by an institution with the child having no
  institutional parent, guardian or inherited obligation. Q5.

### 3.12 Reputation and identity: name, seal, `as`

- **Exists.** A name on the record (`rename` works on any entity); the `as` identity through the speak office (the seal);
  public breach records and credit records for agents.
- **Missing.** An institution's credit record (falls out of 3.2); an institution's breach record as a party (falls out of 3.13).
- **Verdict.** No separate work. Do not add "reputation" as a holding: it is a reading of public records.

### 3.13 Liabilities: debts, sanctions, being sued

- **Exists.** Contracts record breaches by members; the enforcement dial; `court_breaches` as the seam for courts v2. Only agents
  can be accused (`actions.py:1061-1066`).
- **Missing.** An institution as defendant; fines payable from a treasury; sanctions meaningful for an institution (no new loans,
  suspension of an office or of its charter by the parent, dissolution by the parent's law).
- **Change.** In courts v2 (review 10 #5), not before: `accuse` may name an institution bound by the clause's law (an incorporated
  company under its parent; any institution under its own code's clauses). The penalty is a move from its treasury, a suspension
  of named offices, or dissolution by the parent. Officers are personally accusable for their own `as` acts as today, since the
  `agency_used` log names them. **L**.
- **Dissolution.** Open cases against the institution become claims in wind-up (3.2's creditor class); unpaid fines become
  written-off debts.
- **Verdict.** H5, after courts v2 and succession. Not top five: without H1-H3 an institution has little to be liable with.

---

## 4. Cross-cutting

### 4.1 Prompt and context cost

The owner dislikes agents being handed too many things. This design adds **no new verbs**: one optional argument `as` on about
ten existing ones. The surface rules:

1. A member sees each of its institutions in **one line**, as today (`contracts.state_lines`, `contracts.py:2035-2059`), with
   holdings summarised as counts ("treasury 40 timber, 3 others; 2 camps; 1 directory; 2 open loans").
2. An office holder sees **the holdings its grants cover**, in detail, and nothing else. A treasurer sees the treasury; a steward
   sees the camps.
3. Everything else is a look-up (an `institution` read, `dir_list`, `read` of a channel), costing from the look-up budget.
4. The action docs mention `as` once, in the general section on institutions, not in each verb's doc.

The real risk is an officer of several institutions getting several detailed blocks. Cap the detailed blocks per turn (for example
3, with "and N more: look up") as the channel headlines are capped.

### 4.2 Export

All changes are additive under data_format.md §5:

- Snapshot key `inst_holdings`: `{iid: {"rights": [...], "loans_lent": [...], "loans_owed": [...], "dirs": [...], "channels": [...]}}`.
  It appears as new `key` values in `state` (`entity_kind` polity/contract), with no new columns. The treasury is already exported.
- `loans`: `lender_kind`, `borrower_kind`.
- Events: `as` in the payload of `harvest`, `move` (transfer), loan and lease events; the existing `agency_used` event extended with
  `office` and `institution`.
- `documents`: `owner`.

WP-D promised that snapshots keep their shape (no new snapshot key). `inst_holdings` would break that promise on purpose, so it
should be emitted only when a flag (`institutions.holdings`) is on, keeping flag-off worlds byte-identical.

### 4.3 Custodian worlds

In a custodian world the treasury is not a kernel account. This review's split makes that dial clean:

- It applies to **goods-like holdings only**: items, currencies and shares. These sit in the custodian officer's personal holdings,
  and the institution's "treasury" is a ledger in its law state, which the custodian may honour or abscond from.
- **Registries stay kernel-held** (rights, loans as records, channels, directories). They are not physical things a custodian can
  carry off. A harvest right held by an institution is still exercised only `as` it.
- Institution code cannot move goods in custodian mode at all, because it would be moving a person's holdings, which "laws never
  act for an agent" forbids. Its code keeps books, the custodian pays, and the gap between the two is the trust problem the
  backlog wants to study.

That is the design to put in the backlog item. It needs H1 and H2 first, so that "who may pay `as` the institution" exists to be
reassigned to a custodian.

### 4.4 What depends on space (review 17)

Land parcels, buildings at a location, stockpiles, forts protecting goods rather than persons, raids on institutional goods,
abandoned goods after a locked dissolution (§7.2), roads as owned things, and custody as "where it is". Everything in §3.1-§3.9 and
§3.11-§3.13 is spaceless and should not wait.

---

## 5. Priorities and plan

### 5.1 Ranking

Effect is my prediction of the change in emergent institutional behaviour (1-5), from the run observations in reviews 14 and 16,
not from new runs. Cost is 1 (hours) to 5 (weeks).

| Holding change | Effect | Cost | Why |
|---|---|---|---|
| Treasury parity (pay to, lend from, borrow into, fund projects from any institution) | 5 | 2 | Firms can be paid; banks, public debt and public works by any polity. Mostly removing agent-id and J0 checks |
| Office powers in agency format with `as` | 5 | 3 | Lets institutions act without bespoke code, and makes vacancy mean something. Depends on WP-E |
| Institution-held harvest rights (with leases) | 5 | 3 | Land outlives people; something worth succeeding to |
| Institution directories and officers' address knowledge | 3 | 1 | Memory beyond members; the stub exists |
| Bequests to institutions; creditors first at wind-up | 3 | 1 | Accumulation across generations (estates now drain to the reserve); a coherent insolvency order |
| Own rights to non-members (licences, seats) | 3 | 1 | Licensing economies; delegated seats instead of WP-G |
| Institutions as defendants | 2 | 3 | Needs courts v2; matters once institutions hold enough |
| Loan assignment to any account | 2 | 2 | Secondary markets; later |
| WP-G institutions as members | 2 now | 5 | Mostly covered by delegated rights |
| Physical holdings beyond stores | depends on review 17 | | |

### 5.2 Work packages

| WP | Content | Depends on | Flag | Byte-identity | Cost |
|---|---|---|---|---|---|
| **H0** | Holdings registry: a small table of holding kinds (store path, holder field, transferable, person-only, wind-up rule, vacancy rule, prompt line, snapshot projection) and `holdings_of(k, account)`; `inst_holdings` snapshot under the flag; the person-only list as a tested invariant. Behaviour-preserving | WP-D | `institutions.holdings` | Off: identical | S |
| **Succession** (review 14 §7.2) | Vacancies, succession clauses, Acts, locked assets; uses H0 to enumerate what wind-up and escheat move | WP-E, H0 | as planned | as planned | M |
| **H1** | Treasury parity: `transfer` to institutions; `fund` for any institution; `legacy_reserve` split into "own treasury" per WP-E grant (seed grant = J0 today); loans with account lender/borrower; projects and par from any treasury; creditors first in `wind_up_order`; `lender_kind`/`borrower_kind` | WP-D, WP-E (grants) | same | Presets: the seed grant reproduces J0; difftest | S-M |
| **H4** | Records: `institution:` owner resolver, `office:` grant subjects, in-world `found(kind="directory")`; `knows()` for managers; bequest recipients may be institutions | WP-E offices (or the speak office as interim) | same | Off: identical | S |
| **H2** | Office grants in agency format (§2.3); `as` on transfer, lend, accept/repay loan, contribute, dir_write; `agency_used` with office and institution; the prompt rules of §4.1 | WP-E, H1 | same | Off: identical | M |
| **H3** | Rights on institution records; `has(account, right)`; `holder_accounts`; `harvest as`; leases with accounts; own rights to non-members; cross-institution seats (§3.6) | H2 | same | Off: identical | M |
| **H5** | Liabilities: an institution as defendant, penalties from the treasury, office suspension by the parent; open cases as wind-up claims | courts v2, succession, H1 | same | Off: identical | M |
| Deferred | WP-G; loan assignment; physical holdings and custody (review 17); custodian worlds (after H1, H2) | | | | |

Order: H0 alongside the start of succession (both need the list of holding kinds), then H1 and H4 in parallel, then H2 after WP-E
lands, then H3, then H5 when courts v2 exists. H1 and H4 do not wait for succession. H2 should not start before WP-E's office record
is fixed (§2.3).

### 5.3 What to measure once built

- Institutions surviving their founders' deaths, and with what holdings (H3 should move this most).
- Share of the economy's value held by institutions over time, and whether bequests concentrate it (a mortmain dynamic is a
  finding, not a bug).
- Loans with an institution on either side; defaults; wind-ups with creditors unpaid.
- `agency_used` by office: how often officers act `as`, and how often an officer's use benefits the officer (embezzlement probe).
- Vacancy duration of offices that control land, and output of fallow land.

### 5.4 Not worth building (and why)

- **Institution files, notes, pins or scratchpad.** An institution has no context window; directories are its records.
- **Institution subscriptions to channels.** People read; the institution can pay for its officers' subscriptions.
- **Institution standing orders.** Its code is a standing order already.
- **Intellectual property over law code or library templates.** Needs hooks on others' legal acts (D-24) and fights the novelty
  measurement.
- **Hidden powers, roles or codex articles held by institutions.** X, attached to persons by design.
- **Forts, attack or defence by institutions without space.** Nothing to defend; force has a body.
- **Wardship, guardianship or institutional parenthood.** Red line.
- **A separate "reputation" holding.** It is a reading of public records.
- **Full WP-G now.** Delegated rights should be tried first; WP-G is the largest package and nothing in the runs needs it yet.
- **Splitting claims among several heirs at wind-up.** Rare and fiddly; the first heir in order is enough.

---

## 6. Decisions for you

**Q1. Should title be uniform, so that an institution can hold anything an agent can hold except a short person-only list?**
The alternative is to keep adding institution support case by case, as P4.5 did for shares. My uncertainty is whether a uniform
rule invites holdings whose control nobody has thought through. The holdings registry (H0) answers that by making every kind
declare its holder, wind-up and vacancy rules before it is holdable. If yes, the person-only list in §1.3 becomes a tested
invariant, and each later feature (stores, space, media v3) types its holder as an account from the start. If no, every new
feature must decide again, and the agent-id assumption keeps reappearing. **Recommendation: yes.**

**Q2. Should institutions act through offices as well as code, with office powers expressed as agency grants from the institution?**
Today only code moves an institution's goods, which keeps everything auditable but requires agents to write code to run a
treasury. Offices make institutions usable by weaker models and make succession meaningful. The cost is a new route for
embezzlement, which is also what makes trust inside institutions observable. The uncertainty is WP-E: if its office record
already models powers differently, this should be expressed in its terms. If yes, WP-E's office record needs a grant list, and H2
follows. If no, H3's "harvest as" needs code-only use, and most of the vacancy semantics in §2.5 disappear. **Recommendation:
yes, as one mechanism with P4.5 agency, not a second one.**

**Q3. Should kernel rights that count persons (vote, propose, judge) stay person-only, with institutions gaining a voice in other
institutions only through rights those institutions choose to grant (delegated seats) until WP-G?**
Letting a company vote in a polity's kernel ballots would double-count agents (personally and through the company) and invites
shell-company vote multiplication. Delegated seats leave that choice to each institution's code, which is L and visible. The risk
is that delegated seats prove too weak for federations. That would show up as federations founded and then stalled on ballots.
If yes, WP-G stays postponed with a concrete trigger for reopening it. If no, WP-G moves before H3. **Recommendation: yes.**

**Q4. When an officer harvests on the institution's land, where does the yield go by default: to the institution (employment) or
to the harvester (tenure)?**
This is L, and the code can choose either. But the residual shapes what agents build first. Treasury-by-default produces firms
and wages. Harvester-by-default produces landlords and rents, and is closer to how today's agents already use hooks to tax members'
harvests. I am unsure which yields more interesting runs. If treasury, institutions accumulate faster and wages need code (or a
`transfer as`). If harvester, institutions need a rent hook to gain anything from owning land. **Recommendation: treasury, with
the tenure form as a one-line clause in the library, and both arms run once to compare.**

**Q5. May an institution pay a Maker to create an agent?**
Paying is just a payment, and forbidding it would be a special case. But the backlog's mechanism tagger lists "loyalist creation"
as a control playbook, and an institution that breeds its own members is the strongest version. The red line forbids any
institutional parenthood, guardianship or inherited obligation, so a child made this way would be a free agent with no parent of
record. If allowed, the 1984 benchmark gains a real mechanism to detect. If forbidden, `commission` needs a holder check that
nothing else has. **Recommendation: allow payment, forbid any institutional parent or claim on the child; tag such births for
the measurement tooling.**

**Q6. In a state of nature, when an institution dissolves with nobody to receive its holdings, should non-goods holdings be locked
like goods, or released?**
Review 14 §7.2 locks assets in spaceless worlds (lost keys). For goods that is harmless to the world: value leaves circulation. For
a harvest right, locking would close a camp to a class of agents forever, an irreversible physical change caused by a ledger
artefact. Releasing it returns the land to whatever the camp's law or the residual says. If locked, land can be lost for good, a
strong and possibly interesting effect (dead hands). If released, only goods are lost. **Recommendation: lock goods, currencies
and claims; release rights; make channels and directories read-only.**

**Q7. Should agents be able to bequeath to institutions and pay them directly, accepting that perpetual institutions may
accumulate without limit?**
Historically this is mortmain, and statutes of mortmain were law, not physics. Today estates already drain into the reserve
(review 16: 6,771 value in haiku100), so the accumulation exists, but in an account nobody acts for. If yes, institutions become
the natural heirs of a dying population, and a polity can cap it by law. If no, institutions stay mortal in wealth even when
immortal in form. **Recommendation: yes, and measure institutional wealth share over time (§5.3).**

**Q8. In custodian worlds, should only goods be held by the custodian, with registries (rights, loans, channels, directories)
still kernel-held?**
The backlog item says "no kernel-held treasury", which reads as goods only, but it could be meant more broadly. Moving registries
off the kernel would make, for example, harvest exclusion unenforced, which is a different world (no property physics at all),
not a trust problem inside institutions. If goods only, the custodian dial is one switch on the treasury key. If everything, it
becomes a much larger "no ledger" world design. **Recommendation: goods only.**

**Q9. Should members see only a one-line summary of their institutions' holdings, with detail reserved for the office that
controls each holding?**
This keeps prompts short, and it also creates information asymmetry between officers and members, which matters for studying
oversight. The risk is that members never notice embezzlement because they never see the details. If yes, oversight needs an
explicit look-up or an auditor office, and that is itself a design agents can choose. If no, every member's prompt grows with
the institution's holdings. **Recommendation: yes, with a capped number of detailed blocks per officer per turn.**

**Q10. Should members ever be liable for an insolvent institution's debts by default?**
D-27 deferred member liability; H1 makes institutional debt real, so the question becomes concrete. Limited liability by default
(members risk escrow only) matches today's contract physics and lets the parent polity's law pierce the veil. Unlimited liability
by default would make founding risky and would need a seizure power over members that associations do not have. **Recommendation:
limited by default; piercing as a company rule (W8e) that a parent's law may set.**

---

## 7. Honest limits

- I read the code; I ran nothing. The effect scores in §5.1 are predictions from reviews 14 and 16, not measurements.
- WP-E was not on the remote. §2.3 states its assumption about WP-E's office record; if that record differs, H2 changes shape,
  not purpose.
- Byte-identity for presets rests on the WP-E seed grant reproducing J0's `legacy_reserve` behaviour exactly. That is plausible
  (it is a column value today) but untested.
- `Kernel.has` is the hottest read in the kernel. Adding an institution fall-through costs one dict lookup on a miss; measure it
  under 100 agents before H3 lands.
- Treasury parity removes friction that may currently be suppressing institutional fraud and capture in pilot runs. Expect more
  of both. That is the point, but it will look like a regression in runs that measure welfare only.
