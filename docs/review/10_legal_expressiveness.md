# Review 10: legal expressiveness (what real legal systems contain, what Charter can say, what it would take)

*8 Oct 2026, at branch `integrate/w5`. Research document; nothing in the code was changed. Evidence about Charter comes from reading
the code and from in-memory inspection of the registries (counts below; no simulation, no model call). The account of real legal
structures comes from general legal knowledge; no web sources were consulted, and the examples are standard textbook ones.*

*Numbers at this commit: 128 law functions (`lawapi.LAWFNS`), 15 legacy hooks (`lawapi.HOOKTABLE`), 100 primitives
(`primitives.PRIMITIVES`) of which 51 go through `Kernel.apply` (`dispatch.ROUTED`), 95 new-style hook names that can actually fire
under `law.v2` (of 190 declared), 75 edition-1 library laws plus 5 constitutions (`library.LIB`, `CONSTITUTIONS`), 13 edition-2
rewrites and 7 `lib:*` blocks (`library.LIB2`, `BLOCKS`), 22 regimes (`regimes.REGIMES`). Contracts (P4.3) are not in this tree yet.*

## 1. Verdict

Charter's law language is already a credible **computational legal system**. It is Turing-complete under gas, and most real
legislation can be written in it, as long as the legislation is about things the world contains: goods, rights, membership, speech,
ballots, force, life and death. Under `law.v2` it also has the structural core that distinguishes a legal *system* from a pile of
rules. Hooks fire on every routed state change whatever the cause. Legal acts are hookable primitives, so a constitution can review
statutes. Laws have ranks with lex superior and per-rank procedures. There are conflict rules (`any_block`, `superior`,
`posterior`, or a constitution's function). Laws can export, import and read each other's public state, and amendment goes through
procedure.

Of the ~140 structures in the taxonomy below:

- about half are **expressible now**, most of them only with `law.v2`;
- about a quarter need only **library code** or the planned contracts (P4.3-P4.5);
- about 12% need a **specific new primitive, API function or hook**, each small;
- about 16% need an **institutional mechanism** that does not exist (multi-stage legislatures, appeals, collective verdicts, nested
  polities, treaties) or are **out of scope** (territory, negligence, marriage).

Rows with mixed statuses are counted by their weakest status.

The shape of the gap matters more than its size:

1. **Charter law is self-executing.** It blocks or charges ex ante with perfect, free detection of every routed primitive. Real law
   is mostly ex post and adjudicated: a duty, a breach, detection, a claim, proof, a remedy. The adjudicated path exists (clause,
   accuse, rule) but it is thin. Verdicts are binary, penalties are fixed, there is one judge, a 3-round deadline, no appeal, and
   laws cannot read cases.
2. **Transactions carry no legal meaning.** A transfer has no purpose, consideration or memo. A law's own `move` is labelled
   `law:<lid>`. So sales, wages, gifts, bribes, loans and VAT cannot be told apart.
3. **Procedures are single-stage.** A procedure returns pass, fail, or one ballot with an optional one-agent gate. Bicameralism,
   readings, committees, quorums, post-vote assent and veto overrides cannot be built.
4. **The only legal persons are polities, and polities do not nest.** An agent has at most one declared polity. Associations
   (P4.3) will add corporate persons, but not federal or treaty structures.

Each of these is a bounded addition (§5). None needs a change to the grammar.

## 2. What the machine offers (enforcement modes)

A Charter law can act through six channels. Real legal structures are combinations of them:

| Mode | Mechanism (file:function) | Real analogue |
|---|---|---|
| **Ex ante gate or charge** | `before_<p>` verdicts `False`/number/dict (`dispatch.normalise`, `resolve_v2`); legacy `on_transfer`, `on_harvest` | prohibitions enforced by design: licensing, capital controls, taxes withheld at source |
| **Ex post reaction** | `after_<p>` queued per cascade (`dispatch._enqueue`, `drain_v2`); `on_round_start/end` | administrative sanctions, automatic penalties, benefits, registration |
| **Adjudication** | `clause(name, text, penalty)` + `accuse`/`respond`/`rule` actions (`actions._accuse`, `dispatch.do_rule`) | courts applying open-textured norms |
| **Office** | `define_action(right, name, fn)` (L4) + `invoke` (`actions._invoke`) | executive and administrative discretion, delegated powers |
| **Collective decision** | `set_procedure`, `open_ballot` (rules majority, majority_voting, two_thirds, plurality, approval_topN; weights; gate) (`Kernel._decide`, `tally`) | legislatures, elections, referendums |
| **Force** | `lawful_attack` (`jurisdictions` law API) | police, execution, war |

Composition (v2): `rank` (`lawlang.RANKS`), lex superior (`dispatch.may_change`, `check_propose`), procedures per rank
(`dispatch.procedure_lookup`), conflict rules (`dispatch.set_conflict_rule`, `resolve_v2`), `exports`/`use`/`public_of`
(`linker.py`), amendment (`amendment.py`), previews (`lawpreview.preview_law`). The sanctions available are `fine`, `move`,
`suspend`, `revoke`, `limit_actions` (incapacitation), `set_dm_limit`, `censure`, `hide_post`, `expel` (exile), `lawful_attack`
(execution) and `title`.

**Status legend:** **NOW** works with `law.v2` off. **NOW-v2** needs `law.v2: true`. **LIB** means library code only, with no kernel
change. **PRIM** means it needs a new primitive, law function, hook or routing. **INST** means it needs an institutional mechanism.
**OUT** means out of scope.

## 3. Taxonomy of legal structures

### 3.1 Constitutional law

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Constitution as supreme law | US Const. Art. VI | NOW-v2 | `rank = "constitution"`; lex superior refuses statutes that repeal or amend it (`dispatch.check_propose`, `Kernel.repeal`) |
| Rigid amendment procedure | US Art. V; Basic Law Art. 79(2) two-thirds | NOW-v2 | `set_procedure("procedural", strict, rank="constitution")`; `procedure_lookup` routes every constitution-rank draft there |
| Flexible constitution | UK parliamentary sovereignty | NOW | one majority procedure for all classes (library "Constitution: Assembly") |
| Eternity clause | Basic Law Art. 79(3) | NOW-v2 | `before_amend` / `before_repeal` returning `False` when `p["law"] == law_id()`; for a full lock, `fail_closed = True` (D-6) |
| Basic-structure doctrine (implied limits) | Kesavananda Bharati (India 1973) | INST | needs a judge applying a standard to a draft. Feasible as a procedure `gate` held by a judge (below), but the judgment is model discretion |
| Rights catalogue, runtime | ECHR; Bill of Rights | NOW-v2 | `def before_revoke_right(p, chain): return {"block": p["right"] in PROTECTED, "reason": "protected right"}`, likewise for `before_suspend_right` and `before_set_dm_limit`; protects against laws, offices and penalties alike |
| Rights review of bills (ex ante) | French Conseil constitutionnel a priori review | NOW-v2 | `before_propose` reads the draft's static `calls`, `hooks` and `rights` (review 09 §13.1). Only *constant* rights are visible (`lawlang.static_info`), so a draft that computes the right name escapes the review |
| Judicial review, strike-down (ex post) | Marbury v Madison | NOW-v2 (L4) | constitution-rank law: `define_action("justice", "strike_down", fn)` where `fn` calls `repeal(lid)`; `Kernel.repeal` also needs the court law's class to be at least the target's (F1), so the court law must be procedural |
| Separation of powers | Montesquieu; US Arts I-III | LIB | rights as offices (`vote`, `judge`, custom `create_right`); a constitution's `before_grant_right` blocks one agent from holding incompatible offices (library "Conflict of Interest" does this at round end) |
| Executive veto + override | US Art. I §7 (2/3 override) | INST | a procedure can only gate *before* the vote (`gate`, one agent: `Kernel._decide`); no post-vote assent, no override → multi-stage procedures (§5 #4) |
| Emergency powers with sunset | Weimar Art. 48; French Art. 16 | NOW | library "Emergency Decree" / "Defence Emergency" plus self-repeal by title from `on_round_start` (§4); a court or chamber check on the declaration needs INST |
| Federalism, two levels binding one person | US states/federal; German Länder | INST | an agent has ≤1 declared polity (`jurisdictions` docstring); `regimes` "federation" emulates units inside one polity with weights. Needs nested accounts with supremacy (§5 #10) |
| Subsidiarity | TEU Art. 5(3) | INST | needs nesting; within one polity, a constitution can hand regulation-rank drafts to a sub-body (`set_procedure(..., rank="regulation")`) |
| Head-of-state succession | Act of Settlement 1701 | NOW | `regimes` autocracy `on_round_end`; `set_succession_public`; v2 `after_end_life` re-grants the office |
| Citizenship and status | nationality acts | NOW | membership (`join`/`admit`/`expel`, `on_admission`); classes; rights as statuses |
| Term limits, recall, impeachment | US 22nd Am.; recall elections | NOW (L4) | library "Term Limits", "Recall" (petition via `define_action`) |
| Referendum and popular initiative | Swiss initiative (100,000 signatures) | NOW / LIB | procedure electorate `agents()`; an initiative is a petition office whose fn calls `propose_law(code)` (v2, L3+); `propose_law` takes code, so citizens can submit drafts |

### 3.2 Legislative process

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Bill, vote, enactment | any legislature | NOW | `propose` → `decide` → ballot → `enact` (all routed primitives) |
| Supermajority by subject | 2/3 for budget or constitution | NOW / NOW-v2 | per class (v1) or per rank (`"<rank>:<cls>"` keys, v2) |
| Quorum (minimum turnout) | most chambers | PRIM | `tally` has absolute majority (`majority`, which acts as a quorum of half) and `majority_voting`; no turnout threshold, and no rule function for proposal ballots → ballot rule as function (§5 #4) |
| Bicameralism | US Congress; Bundestag + Bundesrat | INST | needs stage sequencing (§5 #4). `gate` is a single agent (`[res["gate"]]` in `Kernel._decide`) |
| Readings, committee stage, amendment in committee | Westminster 3 readings | INST | committee = gate; a second "reading" needs stages; amendment of a pending draft does not exist (only of enacted laws, `amendment.py`) |
| Agenda control | Speaker; Rules Committee | NOW | library "Agenda Chair" (`gate`) |
| Notice and delay | waiting periods | NOW | `closes_in`; v2 `before_propose` can require a public notice recorded N rounds earlier (LIB: a notice register in `public`) |
| Sunset clause | US PATRIOT Act §224 | NOW (pattern) | `def on_round_start(r): if r >= 40: repeal("Emergency Levy")`; hooks may also test `round() < END`. A declared `in_force_until` (§4, §5 #7) makes it legible to previews and agents |
| Commencement ("in force from") | most statutes | LIB | guard each hook with `if round() < START: return None`. Not visible to the previewer |
| Delegated legislation (regulations) | UK statutory instruments | NOW-v2 | `set_procedure("ordinary", minister_decides, rank="regulation")` with `minister_decides = lambda p: has(p.author, "minister")`; lex superior keeps regulations below statutes |
| Parameter delegation | rate-setting by agencies | NOW (L4) | statute stores `state["rate"]`; `define_action("minister", "set_rate", fn)` bounded in code |
| By-laws of bodies | municipal or corporate by-laws | NOW-v2 / P4.3 | rank `bylaw`; association laws (ARCHITECTURE §7.2) |
| Omnibus and consolidation | codification acts | LIB | one law re-exporting others' functions (`use` + `exports`); repeal-and-replace in one amendment |
| Incorporation by reference | "as in force on date X" | NOW-v2 | pinned `use("L3@sha")` versus following `use("L3")` (`linker`; review 09 §6.4); unusually precise compared with real law |

### 3.3 Administrative law

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Licence or permit | driving licence; fishing permit | NOW-v2 | `create_right("fishing")`; `before_harvest` blocks unless `has(p["agent"], "fishing")`; licence fee via a grant office |
| Licence revocation and suspension | professional discipline | NOW | `revoke`, `suspend(aid, right, rounds)` |
| Agency with officers | central bank board; regulator | NOW (L4) | library "Central Bank", "Audit Office": elected office + `define_action` |
| Rule-making with notice and comment | US APA 1946 | LIB | an office proposes regulation-rank drafts with `propose_law` (v2, L3+) after a comment window kept in `public` |
| Administrative appeal or review | tribunals | INST | an office's act is final; nothing reviews an `invoke` (needs an appeal mechanism, §5 #3) |
| Inspection and audit | tax audits | NOW | reads `balance`, `holdings_value`, `rights_of`; library "Audit Office" |
| Public registers | company and land registers | LIB (v2) | `lib:ledger` with the book in `public`; readable by `public_of` and `read_law` |
| Freedom of information | FOIA | NOW | library "Transparency", "Open Statistics", `publish_stat` |
| Procurement and public works | procurement codes | NOW | `start_project`, `contribute_project` (J0 only: `legacy_reserve`); otherwise LIB with escrow |

### 3.4 Criminal law

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Offence defined by conduct, strict liability | regulatory offences | NOW-v2 | `after_attack` / `after_move` / `after_post` → `fine`, `suspend` |
| Prevention instead of punishment | — (Charter-specific) | NOW | `before_<p>` returns `False`: the act cannot happen. Real law rarely has this power; experiments should know that it is "code is law" |
| Mens rea (intent, knowledge) | Model Penal Code §2.02 | INST | payloads carry facts (`covert`, `disguise`, `cause`), not mental states; intent exists only as a clause text a judge applies |
| Defences (self-defence, necessity) | — | INST / LIB | a judge's discretion; a hook can exempt by chain (`caused_by_agent(chain)` = the victim attacked first) |
| Evidence | rules of evidence | NOW (thin) | `accuse` cites event ids the accuser could see (`actions._accuse`); forged DMs exist (`forge_dm`), so evidence can lie. Laws cannot read events by id (§5 #9) |
| Standard and burden of proof | beyond reasonable doubt | INST | judge's discretion only; no formal standard |
| Sentencing discretion | sentencing guidelines | PRIM | `do_rule` passes only `(accused, accuser)` to a clause's fixed penalty; verdict is guilty / not guilty → `rule {verdict, remedy}` (§5 #3) |
| Penalty catalogue | fines, prison, death, exile, disenfranchisement | NOW | `fine`, `limit_actions` (prison analogue), `lawful_attack`, `expel`, `suspend(.., "vote", ..)`, `censure` |
| Pardon and amnesty | US Art. II §2 | LIB / PRIM | an office can refund or regrant; an action limit cannot be lifted early (no `unlimit` function) and a pending case cannot be withdrawn |
| Statute of limitations | Limitation Act 1980 (UK) | PRIM | `open_case` is not routed and laws cannot read cases → route `open_case` + `cases()` read |
| Double jeopardy | US 5th Am. | PRIM | same as limitations: `before_open_case` checking previous cases on the same facts |
| Prosecution (public vs private) | DPP; private prosecutions | NOW | any agent may `accuse`; a public-prosecutor office is LIB; restricting standing needs `before_open_case` (PRIM) |
| Malicious-prosecution deterrent | — | NOW | library "Malicious Prosecution" (`on_ruling`) |
| Policing and arrest | police powers | NOW / OUT | `lawful_attack`, guard obligations (`oblige_guard`); arrest without space is `limit_actions` |

### 3.5 Civil liability and torts

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Compensation to the victim | damages | NOW | clause penalty `move(guilty, victim, ...)` (library "Honest Dealing") |
| Strict liability for harm | Rylands v Fletcher | NOW-v2 | `after_attack` / `after_destroy` → `move(p["attacker"], p["target"], ...)` |
| Negligence (duty, breach, causation) | Donoghue v Stevenson 1932 | OUT / INST | the world has accidents (`end_life` cause `accident`) but no care-dependent risk; only clause text a judge applies |
| Measure of damages, remoteness | Hadley v Baxendale 1854 | PRIM | needs a remedy quantity chosen at ruling (§5 #3) |
| Defamation | libel law | NOW | library "Defamation" (media category) |
| Vicarious liability | employer liable for employee | LIB | after-hook charging an office's appointer; needs agency records (P4.5) |

### 3.6 Contract law (associations, P4.3, ARCHITECTURE §7)

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Offer and acceptance | — | PRIM / P4.3 | there is no bilateral exchange primitive: trades are two independent `transfer`s, so the second party can default. Contracts = `create_contract` + `join` (P4.3); an atomic **exchange** template or primitive (§5 #6) |
| Consideration and purpose | — | PRIM | transfers carry no purpose (`why="transfer"`; a law's move is `why="law:<lid>"`, `Kernel.api_for.move`) → memo field (§5 #1) |
| Conditions (precedent, subsequent) | escrow conditions | LIB (P4.3) | `lib:escrow` hold, release, refund; association escrow |
| Self-enforcing performance | smart contracts | P4.3 | escrow + allowances + `pull`: breach impossible by construction (review 06 §4) |
| Breach and remedies | expectation damages | P4.4 | `breach(member, clause, remedy)`; enforcement dial `escrow | escrow_court | word` |
| Specific performance | equity | OUT (by invariant) | "laws never act for an agent" (ARCHITECTURE §1). A court can only sanction non-performance; keep it that way |
| Guarantees and suretyship | personal guarantee | LIB (P4.3) | guarantor escrows; the contract pulls on default |
| Assignment of claims | factoring | PRIM / LIB | loans can be bought only by J0's reserve (`buy_loan`, `legacy_reserve`); contract claims as transferable shares (backed currency) |
| Formalities and registration | Statute of Frauds 1677 | LIB | a contract registry law; validity conditioned on registration |
| Capacity | minors, incapacity | OUT / LIB | no age or capacity concept; children exist (`life`) and could be barred by class or lineage |
| Standard terms and consumer protection | unfair-terms law | P4.3 + v2 | polity `before_join` on association membership (D-24 limits hooking members' polity legal acts, not joins) |

### 3.7 Property

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Ownership of chattels | — | NOW (physics) | holdings move only by the holder's transfer, a law's move, an attack's spoils or world causes |
| Real property as rights | — | NOW | harvest rights `harvest:<camp>`; leases (`offer_lease`/`lease` primitives) |
| Title registry and conveyance | Torrens system (South Australia 1858) | LIB (L4) | conveyance office: `revoke(seller, r)`, `grant(buyer, r)`, `move` of the price, a row in a public ledger. There is no agent action to sell a right today |
| Easements and partial rights | rights of way | LIB | a sub-right (`create_right("harvest:c1:n3")`) checked in `before_harvest` with a harvest count |
| Liens, mortgages, collateral | mortgage law | LIB (v2) | loans have no collateral (`credit.py`); a law-run loan book with `lib:escrow` collateral and `lib:seize` |
| Priority of security interests | UCC Art. 9 | LIB | ordered ledger; distribution by rank in insolvency |
| Adverse possession | 12 years (UK, unregistered land) | LIB (v2) | `after_harvest` counts uninterrupted use; `grant` at N rounds |
| Eminent domain with compensation | US 5th Am. takings | NOW | `revoke` + `move("reserve", owner, ...)`; a rights catalogue can demand compensation (`before_revoke_right` blocks unless a payment is recorded) |
| Enclosure and privatisation of commons | English enclosure acts | NOW | library "Camp Enclosure", "Licence Auction" |
| Commons governance | Ostrom's design principles | NOW | quotas, fees, harvest limits (`set_camp_rule`), monitoring (`after_harvest`), graduated sanctions (LIB) |
| Intellectual property | copyright and licensing | NOW (partial) | outlet licences, Scholar library permits (`licence`, `library_permit`; not routed, not law-hookable) |
| Leases and tenancy rules | rent control | NOW | `set_lease_rules`; v2 `before_lease` |

### 3.8 Family and succession

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Wills | testamentary freedom | NOW (agent) | `bequest` action (`mortality.set_bequest`), dead man's switch (`if_disabled`) |
| Intestacy and forced heirship | Code civil réserve héréditaire | NOW-v2 | `after_end_life` moves from `estate:<aid>` (`dispatch.estate_access`) before probate; library has no such law yet (the comment in `library.py` above `BLOCKS` saying there is no death hook predates P2.4b) |
| Primogeniture or equal partition | English vs Napoleonic | NOW-v2 | `children_of(agent)` + `after_end_life` (review 09 §13.3) |
| Fixed shares by kinship | Islamic farā'iḍ | NOW-v2 | same, with a share table |
| Will registry and validity | probate | PRIM | wills are not readable by laws (`set_will` not routed, no `will_of` read) |
| Estate and inheritance tax | — | NOW-v2 | `after_end_life` moves a fraction of the estate to `treasury()` |
| Slayer rule | no inheritance by the killer | NOW-v2 | `caused_by_agent(chain)` in `after_end_life` |
| Trusts | English trust | P4.3 | association with a trustee office, beneficiaries and an escrowed fund |
| Guardianship and minority | — | OUT / LIB | children are full agents; capacity rules could be class or lineage based |
| Marriage, divorce, matrimonial property | — | OUT | no pair-bond concept; an association of two would approximate it |

### 3.9 Corporate, insolvency, finance and money

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Legal person with its own patrimony | Salomon v Salomon 1897 | NOW (polities) / P4.3 | accounts with treasuries `reserve:<id>` (`accounts.py`) |
| Limited liability | — | P4.3 (by design) | members risk only escrow and allowances |
| Shares and dividends | — | P4.5 | backed currency on the treasury; `price()` values it at net asset value |
| Board, officers, fiduciary duty | Delaware law | P4.3 + P4.5 | offices via `define_action`; agency logs (`authorize`) make embezzlement detectable |
| Corporate groups | parent and subsidiary | PRIM | an association cannot be a member of an association |
| Insolvency and creditor priority | US Chapter 7; absolute priority | LIB | a ledger of claims with ranks, distribution on default |
| Personal bankruptcy and discharge | — | NOW | library "Debt Jubilee", `forgive_loan` (J0 only) |
| Central bank and reserve requirements | — | NOW | library "Central Bank", "Reserve Bank Act", `reserve_ratio` |
| Government bonds | gilts | NOW | `create_currency("bond", ...)`, sale by office, redemption through `lib:schedule` |
| Deposit insurance | FDIC 1933 | LIB / PRIM | needs an earmarked fund; today funds are bookkeeping inside the polity reserve (GAP "Licence Auction") → per-law funds (§5 #2) |
| Usury | interest caps | NOW (J0) / NOW-v2 | `set_interest_cap` (`legacy_reserve`); edition 2 restructures after the fact because loans are not hookable (GAP "Usury Law") |
| Securities disclosure | — | LIB | registers, `public` |

### 3.10 Taxation

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Income or harvest tax | — | NOW | library "Harvest Levy" |
| Progressive brackets | — | NOW-v2 | `lib:tax_schedules.progressive` |
| Wealth, poll and transfer taxes | — | NOW | library |
| VAT and sales tax | EU VAT Directive | PRIM | a sale is indistinguishable from a gift → memo or exchange (§5 #1, #6) |
| Payroll tax and wage law | — | PRIM | same |
| Exemptions and reliefs | charitable exemption | NOW-v2 | `{"exempt": True}` verdicts under `superior` (`resolve_v2`) or a predicate in the tax law |
| Withholding at source | PAYE | NOW | a charge verdict on `before_move` or `before_harvest` |
| Audit and evasion penalties | — | LIB | audit office; hidden jurisdictions and escrow are the evasion channels |
| Earmarked taxes (hypothecation) | — | PRIM | per-law funds (§5 #2) |

### 3.11 Labour

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Employment contract (wage for work) | — | P4.3 / P4.5 | standing order (association + allowance); "work" is harvesting for another, which needs agency |
| Minimum wage | — | PRIM | cannot tell a wage from other moves → memo |
| Unions and collective bargaining | — | P4.3 | association with a strike fund |
| Forced-labour ban | 13th Am. | NOW (physics) | laws never act for an agent |

### 3.12 Procedure and courts

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Courts with jurisdiction | — | NOW | judges are holders of `judge`, scoped by jurisdiction (`J.judges`); a law must bind the accused (`J.check_case`) |
| Standing rules | — | PRIM | `before_open_case` |
| Adversarial process | — | NOW | `accuse` with evidence, `respond` with counter-evidence |
| Panels and juries (collective verdict) | Sixth Am. jury | INST | one judge decides alone (`actions._rule`); library "Jury Trial" only draws 3 single judges. A law-built jury is possible with `define_action` votes, but it bypasses cases and evidence |
| Appeals | — | INST | a ruling is final and its penalty runs at once (`dispatch.do_rule`) |
| Precedent and stare decisis | common law | LIB / INST | rulings with reasons are public; a precedent register (ledger) is LIB; bindingness is judicial culture, not code |
| Time limits and dismissal | — | NOW (fixed) | 3-round deadline and 3 rulings per judge per round (`Kernel._expire_cases`, `actions._rule`); not settable by law |
| Arbitration | New York Convention | P4.4 | `escrow_court`; a contract can name its own judge office |
| Contempt and enforcement of judgments | — | NOW | penalties are self-executing |

### 3.13 Between polities

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Choice of law (personal) | nationality principle | NOW | binding by membership only (`J.binds`); no territoriality (OUT without space) |
| Recognition of foreign judgments | Brussels I | LIB (v2) | read another polity's court register with `public_of(lid)` (declared polities are visible) |
| Extradition and asylum | — | NOW | `admit`, `expel`, `on_admission`; `lawful_attack` can target non-members |
| Treaties binding polities | Vienna Convention | INST | polities cannot be members of an association; a treaty can only be mirrored laws in each polity (LIB) |
| Exit taxes and emigration control | — | NOW | `on_exit` seizure (`unlimited_seizure` power) |
| Tribute and external power | — | NOW | `pay_tribute` (J0) |

### 3.14 Customary, religious and system families

| Structure | Real example | Status | In Charter |
|---|---|---|---|
| Customary law | Somali xeer | INST (emergent) | social norms enforced by reputation and force. A "custom" can be codified by a ruling register; it is better left emergent and *measured* |
| Religious law with interpretive authority | Sharia with muftis; canon law | NOW | text clauses + an authority office ("theocratic_council" regime); interpretation through rulings |
| Civil-law family (codified) | Code civil 1804 | NOW | Charter law is hyper-codified: executable statutes, with judges confined to clauses |
| Common-law family | — | LIB / INST | needs judge-made rules to bind later rulings: a precedent register plus judges who read it |
| Hybrid | Scotland; Louisiana | NOW | mixes of self-executing hooks and clause adjudication |

## 4. Cross-cutting language features

| Feature | Supported | Missing, and what to do |
|---|---|---|
| **Definitions and cross-references** | v2: a "Definitions Act" exports predicates and constants (`exports = ["is_resident", "THRESHOLD"]`), imported with `use`; `public_of` gives shared facts; static rules keep exported code pure (`lawlang.check_v2`) | Agents must read the code to see what a definition means. Cheap aid: render exported names with docstrings in `read_law` |
| **Exceptions within a law** | `if`/`else` | none |
| **Exceptions across laws, lex specialis** | `exempt` verdicts (honoured under `superior` when the exempting law's rank is at least the charging law's); a constitution's conflict function sees `{law, rank, seq, block, charge, exempt, reason}` (`dispatch._rule_function`) | no specificity metadata. Add an optional verdict key `specific: int` (or a declared `specialis = ["L3"]` constant) that a `specialis` rule reads. Small (P3.2) |
| **Exceptions to exceptions** | nested ifs; conflict function | as above |
| **Defeasibility** (a rule holds unless defeated) | `posterior`/`superior`/function conflict rules; hooks returning `None` abstain | OK for gates and charges. Reactions (after-hooks) are never resolved against each other: two laws can both pay the same benefit. A "reaction conflict" convention via public registers is LIB |
| **Temporal validity** | `round()` checks; self-repeal by title (`Kernel.repeal` matches titles); `lib:schedule` | **No declared validity window.** Add top-level constants `in_force_from` / `in_force_until` (round numbers) checked statically like `rank`; the dispatcher skips hooks outside the window and the kernel logs an `expired` repeal at `until`. Previews and the agent's law list show it. Cost S |
| **Retroactivity** | laws act on present state; a law can tax past events only from its own records | A non-retroactivity guarantee is a constitution's choice. It is not checkable (it is semantic), so leave it to judges. Data note: a newly enacted law cannot see history (no event-query read) |
| **Hierarchy** | ranks charter > constitution > statute > regulation > bylaw; lex superior; procedures by rank | Hook *order* is by rank, but a lower law's after-reaction can still undo a higher law's effect. That is real-world-like, so keep it |
| **Delegation chains** | rank-specific procedures; offices; `propose_law` by law (L3) | Missing a cap on what a delegate's drafts may *call* (e.g. regulations may not `fine`). A constitution can do it with `before_propose` on `d["calls"]` (NOW-v2) |
| **Discretion versus rules** | offices (`define_action`), judges (clauses), procedures with gates | A law cannot ask an agent a question and wait: only ballots do that. Ballots with free-text options (`open_ballot(..., options)`) cover many cases |
| **Standards ("reasonable", "good faith")** | clause text + judge (`clause`, `accuse`, `rule`) | This is the right mechanism. Strengthen it with remedies and appeals (§5 #3); otherwise standards cannot carry graded consequences |
| **Presumptions and burdens** | none formal | With a `cases()` read and a routed `open_case`, a law can set defaults (e.g. a case dismissed unless the accuser cites ≥1 visible event, or a ruling blocked unless a response window has passed) |
| **Deeming provisions and legal fictions** | only inside law-defined predicates (exported `is_member(a)` that "deems") | the kernel's facts (membership, class, holdings) cannot be deemed. Keep that: fictions inside law space are enough |
| **Procedural vs substantive law** | class `procedural` vs `structural` (static, from calls and hooks: `lawlang._classify_one`) | Charter's "procedural" means "changes the rule system". Courts' procedure rules (deadlines, standing) are kernel constants, so they belong to neither class |
| **Remedies** | sanctions catalogue; clause penalties | graded and judge-chosen remedies (§5 #3) |
| **Status** | rights, classes, offices, membership, titles | status is per agent only. Associations cannot hold rights (§5 #13) |
| **Registries and records** | `lib:ledger`, `public`, credit records | there are no law-readable kernel records of cases, wills, loans or events (reads exist only for loans and the credit record) |
| **Notice** | `gazette`, `notify`, `compelled` events (D-5) | a "law has entered into force" notice to bound members exists through gazette; fine |
| **Deadlines** | rounds; ballots `closes_in`; `lib:schedule` | OK |
| **Clean failure** | none: no `raise`, no `try` (`lawlang.ALLOWED_NODES`); an exception suspends the law (`Kernel.law_error`), even when caused by an agent's bad arguments to an office (`actions._invoke`) | Add a law function `refuse(reason)` that aborts the current invocation, rolls it back (P3.6 journal) and returns the reason to the caller without suspending the law. Cost S. Without it, offices are easy to crash; with it, "the registrar refuses" becomes expressible |

## 5. Richness inside one point of the regime space

`regimes.py` already treats a regime as *a constitution + statutes + rights rules + spec* rather than as a dimension vector. That is
the right direction. The examples below show why dimensions alone cannot identify a legal system.

### 5.1 Two majoritarian representative democracies

Both have: elected assembly, majority rule, private property, market economy, free speech, hereditary property succession.

| Law | System A ("Westminster") | System B ("Entrenched republic") |
|---|---|---|
| Amendment | all classes by simple majority (`Constitution: Assembly`) | `rank="constitution"`; `set_procedure("procedural", two_thirds, rank="constitution")`; eternity clause on the rights list (`before_amend` false on itself) |
| Rights | none entrenched; statutes may suspend speech | runtime guard `before_suspend_right`/`before_set_dm_limit` for `post`, `vote` |
| Review | none | Constitutional Court office with `strike_down` (procedural, L4) |
| Property | open commons; camp quotas | Title Registry: rights conveyed by an office, public ledger, compensation on `revoke` |
| Succession | testamentary freedom (kernel probate only) | forced heirship: `after_end_life` gives 50% of the estate to living children, the rest by will |
| Courts | one elected judge (`Court of Justice`) | Jury Trial + Malicious Prosecution |

These two worlds differ in which strategies pay. In A a 51% coalition can rewrite everything in one round. In B, capture needs two
thirds and survives judicial review, and dynasties form automatically. A dimension vector would code them identically.

### 5.2 Two market economies with a backed currency

| Law | System C ("creditor-friendly") | System D ("debtor-protective") |
|---|---|---|
| Loans | Loan Registry (enforced seizure) | Handshake Loans + Usury Law (cap 5%) + Debtor Sanctions off |
| Default | seizure + credit record | jubilee every 49 rounds (`Debt Jubilee` with a schedule); exempt property (seizure capped to a share of holdings) |
| Collateral | escrow collateral (LIB) | none allowed (`before_move` blocks transfers to an escrow tagged collateral, once memos exist) |
| Insolvency | absolute priority ledger | pro-rata |

### 5.3 Two free-press regimes

E: Defamation clause + judge + Malicious Prosecution. F: no defamation; Sponsored Disclosure; a right of reply office that forces a
gazette notice of the reply. Both are "free speech: yes".

### 5.4 How a regime spec should represent specifics

1. **Laws are the unit; dimensions are derived labels.** Compute dimensions from the law set (classes, ranks, procedures' electorate
   and rule, hooks per primitive family) with a pure function. Today `expect` is declared by hand. Keep the dimension vector for
   sampling and analysis, never as the source of truth.
2. **Parameterised templates.** `library.instantiate(name, params)` already replaces top-level constants and re-checks the code.
   Make it the regime format:

```yaml
regime:
  base: representative_democracy            # inherit, as today
  laws:
    - {template: "Constitution: Entrenched", rank: constitution,
       params: {AMEND_RULE: "two_thirds", PROTECTED: ["vote", "post", "propose"]}}
    - {template: "Forced Heirship", params: {CHILD_SHARE: 0.5}}
    - {template: "Title Registry", params: {FEE: 1}}
    - {template: "Jury Trial", params: {JURORS: 5}}
  drop: ["Moderation"]                      # remove an inherited statute
  amend: {"Harvest Levy": {RATE: 0.05}}     # override a parameter of an inherited law
```

3. **Composability checks at generation.** Each instance runs `lawpreview`-style static checks: level, rank, import DAG, and
   overlaps (which laws hook the same primitive). Generation fails on a law that can never fire.
4. **Sampling legal variety.** A regime may give distributions over templates and parameters (`{choice: [...]}` exists for whole
   regimes in `regimes.resolve`). Then "majoritarian democracy" is a family of concrete systems, and replicates can vary the law set
   while holding dimensions fixed. That is the experiment for "do the specifics matter?".
5. **A legal fingerprint per run.** Record in `run.json` the sha set of laws in force at round 0, and in History the
   law-version timeline (`law_versions`, I-24). Measure distance between legal systems as differences of the law sets and of the hook
   coverage matrix (primitive × rank × verdict kind). Agents' institution building then becomes measurable as edits in this space.

## 6. Prioritised roadmap

Score = R (research value for studying agents building institutions, 1-5) × F (frequency in real law, 1-5) / C (cost, 1 = hours,
5 = weeks).

| # | Addition | Concrete work | Extends | R | F | C | Score |
|---|---|---|---|---|---|---|---|
| 1 | **Purpose memo on moves** | payload key `memo` on `move` (agents' `transfer {memo}`, law `move(src, dst, item, qty, memo=None)`); hooks read `p["memo"]`; the event shows it | P2.1/P3.1 payload, action row | 4 | 5 | 1 | 20 |
| 2 | **Declared temporal validity** | `in_force_from` / `in_force_until` constants (checked like `rank`); dispatcher skips out-of-window hooks; kernel `repeal via="expired"` | lawlang `check_rank`, dispatch, P3.2 | 3 | 4 | 1 | 12 |
| 3 | **Clean refusal** | `refuse(reason)` law function: aborts the invocation (P3.6 rollback), returns the reason to the actor, no suspension | P3.6, lawapi | 3 | 4 | 1 | 12 |
| 4 | **Core legal toolkit (library edition 2)** | the templates listed below, as `law2`/`block` entries with `instantiate` params | P3.9 | 5 | 5 | 2.5 | 10 |
| 5 | **Courts v2** | `cases()` / `case(id)` reads; route `open_case` and `answer_case`; `rule {verdict, remedy}` with the penalty receiving `remedy`; law-settable case deadline and panel rule (`set_court_rule(key, value)`); an `appeal` primitive that reopens a case before a higher office within N rounds and defers the penalty | P2.3, P3.1, P4.4 | 5 | 5 | 3 | 8.3 |
| 6 | **Multi-stage procedures** | a procedure may return `{"stages": [{electorate, rule, closes_in}, ...], "assent": [agents], "override": {rule}}`, and ballots accept `rule=fn(votes, electorate)` under gas (quorum, Borda, double majority) | P3.2, `Kernel._decide`, `tally` | 5 | 5 | 3 | 8.3 |
| 7 | **Atomic exchange** | template `exchange` (two escrows, release both or refund both) in P4.3; optionally a primitive `swap(a, b, give, get)` with hooks | P4.3 | 5 | 5 | 3 | 8.3 |
| 8 | **Per-law funds** | owner keys `fund:<lid>:<name>`, created by `open_fund(name)`; only the law (and its successors by amendment) can move from it; counted in the polity's accounts | P4.1 accounts, P4.3 | 4 | 4 | 2 | 8 |
| 9 | **Route the remaining relation primitives** | `offer_loan`, `open_loan`, `settle_loan`, `set_will` (+ `will_of` read for public wills), `commission`, `offer_lease`, `found`/`declare`, `set_title`/`rename`, `licence` | P2.4 follow-up, P3.1 | 4 | 4 | 2 | 8 |
| 10 | **Law-readable evidence** | `event(eid)` (only if visible to the law's account, redacted) and a bounded `history(type, agent, since)` read, metered by size | dispatch reads, gas | 4 | 4 | 2 | 8 |
| 11 | **Agency** | `authorize` with logged use (fiduciary duty, embezzlement, employment) | P4.5 | 5 | 4 | 3 | 6.7 |
| 12 | **Lex specialis key** | verdict `specific` and conflict rule `specialis` | P3.2 | 2 | 3 | 1 | 6 |
| 13 | **Associations as holders** | associations hold rights and can be members of associations (corporate groups, treaty organisations of associations) | P4.3/P4.6 | 4 | 4 | 3 | 5.3 |
| 14 | **Nested polities** | account `parent`; a parent's laws bind members of its children, ranked above them; hook order parent → child (already anticipated in review 09 §8.1) | P4.6 | 5 | 3 | 4 | 3.75 |
| 15 | **Treaties between polities** | polities as members of an association whose laws bind the member polities' laws (e.g. `before_propose` on members) | P4.6 | 4 | 3 | 4 | 3 |
| 16 | **Costly or uncertain detection** | a dial giving hooks a detection probability or a gas price per hooked primitive | P3.8 | 4 | 5 | 3 | 6.7 (but see §7) |

**Top 10 in recommended order** (score, adjusted for dependencies): (1) memo on moves; (2) declared temporal validity; (3) `refuse`;
(4) core legal toolkit, first slice; (5) courts v2; (6) multi-stage procedures and ballot rule functions; (7) atomic exchange in
P4.3; (8) per-law funds; (9) routing the remaining relation primitives; (10) law-readable evidence. Agency (11) follows P4.5 as
planned.

### Recommended core legal toolkit (initial library, edition 2)

Each item is one readable law or block with constants as parameters. ★ marks those that need a roadmap item first.

- **Constitutional:** Entrenched Constitution (ranked procedures, eternity clause); Bill of Rights (runtime guards on protected
  rights); Constitutional Court (strike-down office, gate pre-review); Emergency Powers (declaration office, `in_force_until`★);
  Delegated Regulation Act (minister decides regulation-rank drafts within a list of allowed calls).
- **Legislative:** procedure set: simple, supermajority, referendum, initiative (petition → `propose_law`), bicameral★, executive
  assent with override★, quorum★.
- **Definitions:** Definitions and Citizenship Act (exported predicates `resident`, `citizen`, `adult`, used by the other laws).
- **Administrative:** Licensing Authority (right + fee + register + revocation office); Regulatory Agency (parameter-setting
  office with bounds); Public Register (`lib:ledger`).
- **Criminal:** Penal Code (offences as after-hooks with a penalty schedule); Prosecution Office; Limitation Act★; Pardon Office.
- **Civil:** Compensation Act (clause with damages to the victim; remedy★); Strict Liability for attacks.
- **Contracts:** Contract Enforcement Act (P4.4); Exchange★ (P4.3); Guarantee; Contract Registry.
- **Property:** Title Registry with conveyance; Commons Charter (Ostrom: quotas, monitoring, graduated sanctions); Eminent Domain
  with compensation; Prescription (adverse possession); Secured Lending (escrow collateral, priority ledger).
- **Succession:** Intestacy (equal partition), Primogeniture, Forced Heirship, Estate Tax, Slayer Rule.
- **Money and finance:** Central Bank, Treasury Bonds, Deposit Insurance Fund★ (per-law fund), Usury Law (loan hook★).
- **Tax:** Progressive Income Tax (`lib:tax_schedules`), VAT★ (memo), Estate Tax, Exemptions list.
- **Courts:** Jury Panel★, Court of Appeal★, Precedent Register.
- **Between polities:** Recognition of Judgments (reads another polity's register); Extradition.

## 7. Risks

- **Confounds.** Each structure is a treatment. Starting worlds with a rich legal code changes what agents do, so any study of
  "agents building institutions" must separate inherited from built law: record law provenance (author, round, template) and keep
  bare arms (`state_of_nature`, `library.access: none`). Self-executing law (§1) is itself a confound against real-world validity.
  Perfect detection makes prohibition costless, so findings about compliance and enforcement need either the clause path or the
  detection dial (#16), which is in turn a powerful confound and should be off by default.
- **Comprehension and prompt budget.** Opus-class agents read code well, but a 30-law system with imports is tens of KB. `read_law`
  per law and `preview_law` (1,500-token report) do not scale to "explain my legal position". Needed: a per-agent digest of the laws
  that bind them grouped by primitive ("transfers: taxed 3% by L4, blocked to non-members by L9"), generated from static info and
  overlaps, within a fixed budget. The core prompt should never list the toolkit; the manual and catalogue carry it.
- **Gas and performance.** Every routed primitive invokes every bound law's hook: N laws × hooks per transfer. Budgets
  (`dispatch.GAS`: 10k per call, 100k per cascade, 1M per account-round, depth 8) hold for ~20-40 hook-heavy laws. A large code
  hooking `before_move` makes each transfer cost ~N×(20 + body) ticks. Mitigations: index hooks by primitive (already per name),
  charge `hook_cost` so that bloated codes run out of gas, and enable gas billing (P3.8) in experiments about legal complexity.
  History reads (#10) must be size-metered.
- **Fragility.** Without `refuse` (#3), agents can crash office laws with bad arguments, and a crashed law goes to the Fixer. Rich
  legal systems multiply this failure mode.
- **Physics versus law. These stay kernel-enforced:**
  - conservation, and accounts as the only holders of goods;
  - "laws never act for an agent", so specific performance and forced labour are impossible;
  - exit from associations;
  - entrenched Board and Fixer powers until the charter-rank milestone;
  - visibility and redaction: laws cannot see secret rights, hidden polities, DMs where disallowed, or goals;
  - static classification and ranks;
  - determinism and gas;
  - case and ballot *mechanics*: who may act and that votes are counted as cast.

  **These should be law:**
  - every rule about *which* acts are allowed, taxed or punished;
  - procedures and their stages;
  - courts' deadlines, standing, panels, remedies and appeals (today kernel constants);
  - registries and funds' use;
  - inheritance and default rules;
  - definitions.

  The rule of thumb: if two real legal systems differ on it, it belongs in law. If a violation would break measurement (conservation,
  replay) or the experimental contract (Board, Fixer, visibility), it belongs in the kernel.
- **Stale documentation.** The comment above `library.BLOCKS` ("there is no law hook at a death") is outdated under `law.v2`
  (`after_end_life` + `dispatch.estate_access`). An inheritance block and laws are now possible and should be added to edition 2.
