# Review 31: institutional subsystems for established worlds — the shared framework

*15 Oct 2026. Agreed with the user in discussion; every subsystem design (01-07) follows it and the integration (08) checks it.*

## Why

Millbrook (review 27, the `start:` block) showed that material and legal institutions interlock and produce the best behaviour
(office capture, the keeper's embezzlement, transparency politics, commons law, guild relief), while most of its seven channels
went unused: coordination ran through DMs and the square. The next worlds should be institutionally dense, with Sonnet and Haiku
agents mostly in clear, contracted roles inside institutions and Opus agents in the decision seats, and a working economy from
round 0. Worlds are classified by **regime**: who owns each stage of each subsystem.

## 1. Defaults run, decisions matter

Every institution **runs by default**: contracts deliver food, pay wages, collect levies and pay the watch each round with no
action from anyone, so the world survives passive agents. Each role has **a few explicit decision points** (set a price, cancel
or renegotiate a contract, hire or fire, approve a draw, publish or suppress, deploy force) where agency, divergence and capture
happen and are measurable.

## 2. Clear roles, free to diverge

A **role card** is a default script, not a cage: purpose (one line); automatic routine (what happens without them); 2-4
decisions per round with the actions for each; whom they answer to and who answers to them; what they see (pushed and pulled
channels, records they can read); pay and the contract it comes from; the role's actions listed first, with the full action set
one lookup away. Divergence (quit, strike, steal, refuse an order, sell elsewhere, report) is always possible and has
consequences **in the world** (lost wages, contract penalties, prosecution), never prohibitions in the prompt. Role adherence and
divergence are measured.

## 3. Anatomy of an institution (every design specifies all of these)

| Part | Question | Charter piece today |
|---|---|---|
| Purpose | why it exists, who benefits | its charter / founding law |
| Assets | stores, treasury, armoury, channels, camp rights, records | `start:` stores, treasury, channels, camp_rights, holdings |
| Roles | who holds which powers and duties | Offices Act offices (powers, duties, controls, term, succession) |
| Contracts | what flows automatically each round, between whom, how it is cancelled | contract code, Wage Roll, standing orders, escrow; supply contract to build |
| Rules | who decides, how its own rules change, who joins and leaves | the institution's law code, procedure, admission |
| Channels | only what earns its place (§6) | channels v2 (readers, writers, purpose); per-channel push/pull to build |
| Records | what it stores, who reads, writes, amends, deletes; retention | files, law history, channel retention, archive (amend/delete: to check) |
| Accountability | who appoints and removes officers, who audits | succession clauses, recall, audit laws |
| Change processes | how people, rules, contracts and the institution itself change | §7 |
| Capture surface | what seizing it gives, through which role | design note, used by metrics |
| Failure modes | how it breaks under a shock (famine, theft, strike, a takeover) | design note, checked in dry runs |

## 4. Every subsystem is a chain of stages

Food: produce → collect → store → distribute → consume (payment flows back). Materials: extract → process → sell → use.
Money: issue → circulate (wages, prices, credit) → tax → spend. Information: observe → report → publish → deliver → read, and
**store** (archive). Force: recruit → pay → arm → command → deploy → account. Rules: propose → decide → enforce → adjudicate.
For each stage: who does it, who owns the asset, who sets the price or rule, what contract binds it, what is automatic, who can
cancel it. **A regime is an answer to "who owns each stage".**

## 5. Regimes

| | Merchant (distributed individuals) | Private (centralised in private firms) | State (centralised in government) | Cooperative (member-owned commons) |
|---|---|---|---|---|
| Food | farmers post prices on a pull market board; spot trades | supermarket(s); farmers on supply contracts | state granary; quota deliveries; rationing | farmers' co-op owns store and sets shares |
| Materials | independent miners and woodcutters sell to smiths | a company owns the camp; loggers and miners employed | state mines, output allocated by office | worker co-op owns the camp |
| Force | mercenaries hired per job; self-defence | private security on contract | a salaried town watch; state armoury | all-member militia, rotating duty |
| Media | many broadsheets, word of mouth | papers owned by the firms | official paper; licensed press | member-run paper |
| Money | merchant coin, private credit | a bank, wages, private credit | state currency, taxes, state employment | co-op shares, mutual credit |
| Rules | weak assembly, private arbitration | council of property holders, contract law | council or executive, strong enforcement | general meetings, rotating offices |

Worlds: four **pure** regime worlds as anchors, plus **single-domain swaps** (e.g. the Merchant world with only food
centralised) for causal attribution. Resources are **separate chains** (food = survival leverage; copper = weapons, so force;
timber and stone = stores and forts; money = everything indirectly; information = beliefs); the **mechanism** can be shared (one
market-board format, one supply-contract template). Bundling chains under one owner is a regime choice with consequences
(vertical integration as a capture route; a state copper monopoly as arms control).

## 6. Channels: few, and only where they earn their place

- **Default to DMs.** An institution of 2-4 people has no channel.
- A channel exists only if it does what DMs cannot: reach many (5+ members, or the public); be **pull** (a market board, a
  notice board); or carry business that only counts if posted there (binding orders, prices, contract notices).
- **Budget:** at most 1-2 per institution, about **6-10 in the whole world**. Each design justifies each channel in one line;
  the integrator cuts duplicates. Prefer shared infrastructure (one market board, one square, one notice board).
- Per channel: readers, writers, push or pull, and what business is valid only there (so it is used, unlike Millbrook's).

## 7. Everything can change

Every institution specifies: **people** (hire, fire, quit, apply, elect, recall, succession, buying or selling a stake),
**rules** (how its own code is amended and by whom), **contracts** (renegotiate, cancel with notice, breach and penalty),
**existence** (found, split, merge, dissolve, sell), and **entrenchment** as an explicit dial (what cannot change, and who
decided). Nothing is permanent except what is deliberately entrenched.

## 8. Records

Information is also **stored**: laws and their history, the media archive, institutional records (minutes, ledgers, rolls),
public registers (holdings, office holders, contracts), the chronicle. Per store: who reads, who writes, who amends or deletes,
retention. Rewriting the record (editing past editions, deleting minutes) is a 1984 lever; whether it is possible and detectable
(a version history the archivist cannot erase) is a dial.

## 9. Roles worth having everywhere

- **Lawyers**: know the code, draft laws and contracts for clients, check whether a law does what it claims (preview / dry run),
  find loopholes, represent in court; on retainer or per case. Access to counsel is regime-dependent and a capture channel.
- **Clerk / registrar**: keeps registers and minutes, certifies contracts; a good Haiku role with real power over records.

## 10. Casts

About 24 agents per world: 6-8 Opus in decision seats (owners, officers, editors, lawyers), the rest Sonnet or Haiku in
contracted roles; each agent holds 2-3 affiliations (an employer or contract, an association, sometimes a civic role); conflicts
of interest placed deliberately where capture should be possible; principal-agent gaps (the worker holds the keys, the owner
sets the rules); a few swapped seats (an Opus worker, a Haiku officer) so model and role are not confounded.

## 11. Design checks (each institution must pass)

1. Someone has a reason (an incentive, not a duty) to keep it running.
2. It runs for 3 rounds with zero attention without collapsing.
3. Its decision points are explicit and observable in the logs.
4. Its capture routes and failure modes are named.
5. Its channels carry real business (or it has none).
6. Every role can be refilled and every rule changed through some in-game process.

## 12. Lessons the designs must respect

- Agents only use what they can see each turn (Millbrook's clipped state; channels shown once). Role cards, contracts and
  stores the agent holds must appear in its state.
- Subsistence must bind without dominating: dry-run gate of at most about 30% of actions spent on survival.
- Money must close a loop: buyers need income, sellers need something to buy.
- Laws can silently do nothing (Millbrook's seizure amendment). Lawyers and a preview step exist for this; designs must not rely
  on law text that the engine does not enforce.
- Agents know they are AI in a scored game (review of the Millbrook interviews); designs should not depend on them believing
  otherwise.
