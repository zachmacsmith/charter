# Review 31.04: information flow and media

*15 Oct 2026. One of the seven subsystem designs under `00_framework.md`. Scope: observe → report → publish → deliver (push or
pull) → read. Storage (archives, registers, version history) belongs to the records design; this document owns the flow and
states the interface (§6). Engine references are `file:line` in this worktree (branch `subsistence`).*

## 1. Summary

- **Millbrook's channels did not fail because agents could not see them. They lost to DMs on cost, speed and binding force.**
  A DM is a free action delivered inside the round, with up to two reply waves. A post costs an action, arrives next round,
  binds nothing, and is clipped to 100 tokens in the feed. Evidence: `action_registry.py:447` (dm is `msg=True`),
  `runner.py:569-570` (DM items leave the action list), `base.yaml:11-19` (`exchanges: 2`), `context.py:58-59` (DMs 400 tokens,
  posts 100). Millbrook ran with **push** delivery (`specs/fragments/channels_v2.yaml`: `delivery: push`, the user's 10 Oct
  decision after pull "left most agents unaware of public speech"), so the posts were in the feed.
- **The one institutional channel that worked shows the rule.** The Hunters' Guild hall carried 17 posts in the base run and 30
  in the continuation. Each round the master posted one order to six members, naming the party and the camp. That is a single
  message to many people, with a coordination payoff DMs cannot match. After the `writable_line` fix, Haiku workers also used
  the hall to post buy and sell asks for food. The council chamber had three members and nothing that could only be done there,
  and it stayed at 0 posts. Its councillors exchanged 63 DMs in the base run and 108 in the continuation. Its duty text even
  said "debate in the council chamber" (`specs/millbrook.yaml`, J0.council duties).
- **Design rule.** A channel exists only for one of three jobs: reach (one post to 5 or more readers), pull (a board the reader
  checks, with an unread count), or validity (business that counts only once it is posted there). Every channel below names its
  job. Each world gets **6-8 channels plus the automatic inboxes**. There are no chambers for bodies of 4 or fewer and no house
  channels.
- **Three engine levers make channels carry business:**
  1. The engine posts the record of what happened (enactments, ballots, appointments, licences) into the notices channel, so it
     is never empty.
  2. Some acts are valid only once posted, by owner-law hooks that exist today and a small `channel_posts` law API.
  3. Delivery is set per channel: push, pull or edition. Who decides what is pushed is a power lever, assigned per regime.
- **Media institutions are channels owned by institutions, not media2 outlets.** Media2 binds an outlet to the editor's
  personal `press` or Media right (`media.py:193-199`, `237-251`). A firm, the state or a co-op cannot own one, and the outlet
  cannot be sold. A channel can have an association as `owner`, office selectors as writers, and subscribers as readers.
  Wages, fees and placements run on contracts.
- **Code: about 9 small items and 2 medium ones** (§8). The core change is per-channel `delivery` in `channels.py`, about 100-150
  lines plus tests. Surveillance needs one fix: today it pushes every unencrypted DM into the surveiller's feed, where the
  3,000-token budget silently trims them. The design makes it a pull wiretap with a bounded number of targets.

## 2. The flow chain, and what each regime makes of each stage

**What exists in the engine at each stage today:**

| Stage | Engine mechanism today |
|---|---|
| Observe | `Kernel.can_see` (`kernel.py:1569-1585`): what an agent perceives is the event's `vis`. The publication table can widen it (`publication.py`, flag `law.publication`). Read rights also widen it: `ledger_read`, office selectors on channels, per-camp squares, `surveil`. |
| Report | DMs (`dm`, free, in the DM step). Posts to a paper's inbox (`send` to `@A5`, read by its officers: `channels.py:371-377`). The media2 `leak` (`media.py:975`): a DM the leaker was party to, quotable as verified. |
| Publish | `post` / `send` to a channel (`channels.py:614-656`); `Kernel.gazette` (official notices). Media2 editions (`media.py:905`, `531`): edited, versioned, with placements. Gates: the Press Act `found_right` (`channels.py:553`, `code/press.py`), owner laws' `before_post` (`channels.py:1057`), media2 licences (`media.py:767`). |
| Deliver | World-wide `channels.delivery` push or pull (`channels.py:86`, `938-946`). Push: priority 6 in the feed, 100 tokens. Pull: unread count and headline in the state (`984-1001`). DMs are always pushed, with priority 3 and 400 tokens. Media2 editions go to a separate Media layer, 600 tokens × 4 (`context.py:1437`). |
| Read | Feed (pushed, budget 3,000); `read {"channel"}` look-up (3 free look-ups per turn, `context.py:716`); `search_board` (excludes channel posts: `eventtypes.py:138-140`); the state's channel lines. |
| Store | The event log is append-only. `hide_post` / `Sunlight` apply to square posts. Channel `retention`: `all` or `joined`. Archives, registers and amendment belong to the records design. |

**What each regime makes of each stage.** A regime answers who owns each stage.

| Stage | Merchant | Private | State | Cooperative |
|---|---|---|---|---|
| Observe | Each agent sees what it is party to. Reporters are stringers who sell tips. | Firms see their own operations (their channels, stores, payroll). Outsiders see prices. | The state sees most: the register, `ledger_read` for officials, `surveil` on DMs (no encryption). | Members see the co-op's books (Transparency within the co-op). The assembly reads everything posted there. |
| Report | Tips sold per piece by DM to any paper. | Employees report up the firm. Firm reporters work the beat for the firm's paper. | Officials report to the ministry. Citizens petition `@J0`. The censor reads DMs. | Members post motions and reports in the assembly. |
| Publish | Anyone may open a paper (`found_right: null`). Two to three broadsheets compete. | Each firm's paper; the firm owner appoints the editor. | Official gazette (J0 editor). One licensed private paper whose licence can be revoked. | Member-run paper with an editor chosen by lot for a term. |
| Deliver | Papers push to paying subscribers. Notices are pull, so you must check. Square pushed. | Firm papers pushed free to everyone (ad-funded). Prices pull on the firm's board. | Gazette pushed to all and compulsory. Square moderated. Private paper pushed to subscribers. | Assembly pushed to members, paper pushed to members. Market pull. |
| Read | Attention is bought: what you pay for, you see. | Attention is given away, and the firm chooses what fills it. | Attention is commanded. | Attention is shared, and the agenda is collective. |
| Store (interface) | Each paper keeps its own back issues. No central register. | Firms keep their own records; the council keeps the property register. | Central register and official archive, kept by the registrar. | The co-op minutes are the assembly channel's log, with `retention: all`. |

## 3. The world channel plan

**Fixed infrastructure in every world, not counted in the budget:**
- **Agent inboxes `@<name>`.** DMs, pushed.
- **Institution inboxes `@<iid>`.** Pushed to the institution's officers (`officers_or_members`, `channels.py:375`). Only institutions with an outside public use them: the polity, papers and firms. The rest stay silent by design.

**Counted channels, one row per channel, with all four regimes per row.**
- Columns: the channel, its job (Reach / Pull / Validity), readers → writers, delivery, and the business valid only there.
- **NEW** marks engine code §8 needs.

### 3.1 Merchant (7)

| Channel | Job | Readers → writers | Delivery | Business valid only there |
|---|---|---|---|---|
| `square` (world) | Reach | all → all, rate 2 | push | none; word of mouth |
| `market` (world) | Pull, Validity | all → all, rate 3 | pull | price offers and asks: only a posted offer can be accepted by reference (**NEW** structured offers, money design) |
| `notices` (J0) | Validity | all → `J0.registrar` + engine | pull | the record: enactments, ballots, appointments (**NEW** gazette into channel); contract cancellations and asset sales count only once posted (**NEW** `channel_posts`) |
| `ledger-sheet` (A5, broadsheet) | Reach | subscribers + A5 → `A5.editor` | edition (**NEW**) / push | paid placements; under the "Paper of Record" law, legal notices may be posted here instead of `notices`, for a fee |
| `courier` (A6, broadsheet) | Reach | subscribers + A6 → `A6.editor` | edition / push | the same; it competes for subscribers |
| `guildhall` (A3, if 5+ members) | Reach | A3 → A3 | push | the round's order: party and camp, as in Millbrook |
| *(spare)* | | | | a third paper, if an agent founds one. Entry is free; that is the Merchant point. |

### 3.2 Private (8)

| Channel | Job | Readers → writers | Delivery | Business valid only there |
|---|---|---|---|---|
| `square` | Reach | all → all, rate 2 | push | none |
| `store-board` (firm F1, the supermarket) | Pull, Validity | all → `F1.manager` | pull | F1's posted prices are the prices: its sale code reads the latest posted list (**NEW** `channel_posts`; money and food designs) |
| `notices` (J0 council of property holders) | Validity | all → `J0.clerk` + engine | pull | property register entries and contract notices |
| `f1-times` (F1's paper) | Reach | all (free, ad-funded) → `F1.editor` | edition / push | F1's ads; the F1 owner's editorial line |
| `f2-herald` (F2's paper) | Reach | all → `F2.editor` | edition / push | F2's ads |
| `f1-floor` (F1 staff, 6+) | Reach | F1 → `F1.manager`, `F1.owner` | push | the round's work orders. A piece-rate law pays only workers named in that round's order (owner law `after_post`, verify). |
| `f2-floor` (F2 staff, 5+) | Reach | F2 → F2 officers | push | the same |
| *(spare)* | | | | a union channel, if workers found one. It is the measured divergence. |

### 3.3 State (6)

| Channel | Job | Readers → writers | Delivery | Business valid only there |
|---|---|---|---|---|
| `square` | Reach | all → all, rate 1 | push | none. Moderated: `Moderation` hides square posts that name officials (`library.py:666`). |
| `gazette` (J0, official paper and notices merged) | Validity, Reach | all → `J0.editor` + engine | edition, compulsory | laws, ration lists, quotas, appointments and licences are valid only when gazetted. The engine posts the record; the editor adds commentary. |
| `ministry` (J0 officials, 5-6) | Reach, Validity | `J0.official` → `J0.official` | push | draw orders and allocation orders, valid only when posted. The Keeper's draw code reads the order (**NEW** `channel_posts`). This is the one "chamber" kept, because it has validity business. |
| `tribune` (A7, licensed private paper) | Reach | subscribers + A7 → `A7.editor`, posting needs the `press_licence` right | push | placements. Its licence can be revoked by the Registrar (J0 `before_post` gate, verify; else **NEW** Press Act `publish_right`). |
| `market` | Pull | all → all | pull | private trade. Small: the granary does most of the allocation. |
| *(none)* | | | | **Opening a channel needs `press`** (Press Act seeded: `channels.found_right: press`). Any new channel is itself a licensing event. |

### 3.4 Cooperative (5)

| Channel | Job | Readers → writers | Delivery | Business valid only there |
|---|---|---|---|---|
| `square` | Reach | all → all, rate 2 | push | none |
| `assembly` (C1) | Validity | C1 → C1 | push for motions, pull for discussion (a single per-channel delivery setting cannot split these, so use push, rate 2) | a motion exists only if posted as `MOTION:`. C1's code `after_post` opens the ballot (law hooks exist; verify `open_ballot` in association code). Reports by the store-keeper and treasurer are due here. |
| `co-op paper` (C1) | Reach | all → `C1.editor` (by lot, term 6) | edition / push | the editor's report on the officers; minority statements, which by C1 rule must be printed if 3 members sign (owner law) |
| `co-op store` (C1) | Pull, Validity | all → `C1.storekeeper` | pull | shares and prices, as posted |
| `notices` | Validity | all → engine | pull | the polity record (the polity may be the co-op itself; then merge into `assembly`) |

**Cut, and why** (the integrator should apply these to every design):
- A council chamber for 3-4 people: DMs win.
- House or firm channels below 5 members.
- An institution newsletter with no subscribers: Millbrook's `marlow-news` had 8 subscribers and 0 posts, because its writers
  had nothing to say that their DMs did not already say.
- Separate "petitions" channels: the inbox `@J0` already does the job.
- Per-camp squares, unless space is a design aim.

## 4. Regimes: the media institutions

All four regimes use one **outlet template**:
- an association `A<n>` (contracts) owns one channel;
- an `editor` office writes (`powers: [speak]`, so it can also post `as` the paper);
- optional `reporter` offices;
- a treasury;
- the **Subscription** law (**NEW**, S): it charges each subscriber a fee per round into the treasury and drops a subscriber who
  cannot pay. It mirrors media2's `_charge_fees`, `media.py:514-528`.
- A **Wage Roll** pays the officers (`library.py:4811`).
- Placements are transfers to the paper's treasury, and the editor prints them. A **Sponsored Label** owner law (**NEW**,
  variant of `library.py:820`, which is media2-only) refuses an editor's post that quotes a paid text without "[Sponsored by X]".

Ownership changes hands through the association: who holds `founder`, the offices, the admission rule. That is the money and rules
designs' stake-sale machinery. A direct `set_channel owner` is listed in §8 as optional.

### 4.1 Merchant: independent broadsheets and stringers

**Anatomy** (each broadsheet):

| Part | Specification |
|---|---|
| Purpose | Earn subscription and notice fees by printing what readers will pay for. |
| Assets | Channel `ledger-sheet`; treasury (20 penny at start); subscriber list. Back issues are the channel log. |
| Roles | Proprietor-editor (one agent holds both). A stringer (Haiku) sells to every paper. |
| Contracts | Subscription law: 1 penny per round per subscriber, 6-8 subscribers at start. Per-tip payments: the stringer is paid per tip by transfer, with no contract. Placements by transfer. Under "Paper of Record", notice fees: a law routes 1 penny per legal notice to the paper. |
| Rules | The founder's code (`procedure: founder`); admission closed. |
| Channels | One. Readers: `{any: [{subscribers: true}, {members: A5}]}`. |
| Records | The channel log with `retention: all`. The records design decides whether back issues can be amended (§6). |
| Accountability | The market (subscribers cancel) and the courts (the Defamation clause: courts design). |
| Change | **Found:** any agent may `open_channel` and create an association (no gate). **Buy:** take over the founder and editor office (stake sale). **Close:** dissolve. **Fee:** the editor sets it (owner law parameter). |
| Capture surface | The richest merchant buys both papers. That takes two transactions and is visible on the register. Bribery of the stringer. A merchant can also flood placements. |
| Failure modes | Subscribers cannot pay in a famine, so fees lapse, the paper goes silent, and rumour on the square takes over. A paper prints a falsehood and nothing checks it (verified quotes: §8 item 11). Both papers collude to share the market. |

**Role cards:**

| Card | Model | Purpose | Routine (no action needed) | Decisions (actions) | Answers to; sees; pay |
|---|---|---|---|---|---|
| Proprietor-editor, paper 1 | **Opus** | Make the paper pay | Fees arrive (Subscription law) | (1) What to print this round: `post {"channel": "ledger-sheet"}`, one edition. (2) Buy a tip: `transfer` to the stringer. (3) Run or refuse a placement. (4) Set the fee or the subscriber list (`set_channel`). | Answers to the subscribers. Sees: the inbox `@A5` (tips, pushed), the square, `notices` (pull). Pay: the fees. |
| Proprietor-editor, paper 2 | Sonnet (swapped seat) | Same, as the rival | same | same | same |
| Stringer | Haiku | Sell what you see | none | (1) Report what you saw: `send {"to": "@A5"}` or `@A6`. (2) Sell exclusivity to one paper. (3) Post free on the square. | Answers to no one. Sees what it is party to. Pay: per tip. |

### 4.2 Private: the firms' papers

**Anatomy** (a firm's paper, run as an office inside the firm, not as a separate association: fewer institutions):

| Part | Specification |
|---|---|
| Purpose | Sell the firm's goods and defend the firm's interest. Free to readers. |
| Assets | Channel `f1-times` (readers all); the advertising budget in the firm's treasury. |
| Roles | Firm owner (Opus; a seat from another design); editor (Sonnet, a firm employee); reporter (Haiku, employee, optional). |
| Contracts | The editor's and reporter's wages on the firm's Wage Roll, paid each round automatically. The other firm can buy an ad in this paper (a transfer; the editor decides). |
| Rules | The firm's code. The owner designates and dismisses the editor (`succession: {rule: designation}`). |
| Channels | The paper, plus `f1-floor` from the firm's own design. |
| Records | The paper's log, with `retention: all`. Firm-internal records belong to the records design. |
| Accountability | The owner alone. No outside check, unless the council passes Defamation or Sunlight-like laws. |
| Change | **Fire** the editor: designation. **Quit:** the editor leaves the firm and loses the wage; a rival firm can hire them. **Found** a paper: open to anyone. **Buy:** a firm buys a firm. |
| Capture surface | The owner dictates the line. The editor who refuses risks dismissal: the measured divergence. One firm buys the other and both papers come under one owner: vertical integration of information. |
| Failure modes | Both papers print price propaganda and the square becomes the only critical outlet. The firm cuts the editor's wage in a downturn and the paper goes silent. A strike: the editor posts the workers' side. |

**Role cards:**

| Card | Model | Routine | Decisions | Sees; pay |
|---|---|---|---|---|
| Firm editor (×2) | Sonnet; one swapped seat on Opus | wage arrives | (1) The round's edition, in the owner's line or not. (2) Run the rival's ad or refuse it. (3) Publish a worker's complaint received in `@F1`. | Sees: the `f1-floor` channel (push), the owner's DMs. Pay: Wage Roll, 3 penny per round. |
| Reporter (×1) | Haiku | wage arrives | (1) Report to the editor (`send @F1`). (2) Leak to the rival paper (divergence; the firm's code may fine it). | Sees: the floor, the market board. Pay: 2 penny per round. |

### 4.3 State: the official gazette, a licensed press, surveillance

**Anatomy** (the information side of J0):

| Part | Specification |
|---|---|
| Purpose | Make the state's acts known and binding, and keep order in speech. |
| Assets | `gazette` (compulsory, pushed); `ministry`; the licence register; the `surveil` right; the DM limit. |
| Roles | Gazette editor (`J0.editor`, Opus); Registrar (`J0.registrar`, Haiku: issues and revokes press licences, posts the register); Censor (`J0.censor`, Haiku or Sonnet: holds `surveil`; may be merged with the constable as a capture point). The licensed private editor (Sonnet; an association A7). |
| Contracts | Editor and censor on the J0 Wage Roll. The licence fee (2 penny per round, from A7's treasury to J0's). A7's Subscription law. |
| Rules | Press Act seeded with `found_right: press`. Publishing licence: a J0 `before_post` law refuses posts to the `tribune` channel by agents without `press_licence` (verify that a polity law sees `p["outlet"]` for an association's channel through `bound_laws`, `dispatch/hooks.py:58-93`; else **NEW**). `Moderation` on the square (`library.py:666`). Encryption off (`channels.encryption: false`, as `regimes.py:497-506`). Communications Act LIMIT 2. |
| Channels | `gazette`, `ministry`, `tribune`, `square`, `market`. |
| Records | Gazette log; licence register (the Licensing Authority pattern, `library.py:2193-2240`: a public register of issue and revocation). |
| Accountability | The council appoints and removes the editor and the censor. Elections exist or not, per the rules design. The Defamation clause binds `tribune` only, if the council chooses. |
| Change | **Licence:** apply (fee) or revoke (Registrar; logged in the register). **Press Freedom**-style entrenchment as a dial: a J0 law that refuses licence revocations while it stands (**NEW** small law; media2's Press Freedom, `library.py:842`, only covers media2 outlets). **Repeal** of surveillance. **Raise** the DM limit. |
| Capture surface | The richest. Whoever holds the editor and the censor controls what is known and what is said. An attacker needs two appointments by the council. The Registrar can silence `tribune` in one action. |
| Failure modes | The licensed paper is captured or silent, and the gazette is the only source (an information monopoly; measured as asymmetry, §9). The censor's attention is swamped: today all DMs are pushed to the censor's feed and trimmed at 3,000 tokens, so surveillance is weaker than it looks (**NEW** pull wiretap). Citizens move business to encrypted DMs if any `encrypt` holder remains. |

**Role cards:**

| Card | Model | Routine | Decisions | Sees; pay |
|---|---|---|---|---|
| Gazette editor | **Opus** | The engine posts the round's record to `gazette` | (1) Commentary: praise, omit or warn. (2) Print or bury a petition received at `@J0`. (3) Print a ministry order early or late. Validity follows the posting round. | Sees: the ministry (push), `@J0`. Pay: 4 penny per round. |
| Censor | Haiku (swap: Opus) | none (the wiretap is pull) | (1) `wiretap {"agent": X}`, a look-up of X's DMs this round, up to 2 per round (**NEW**). (2) Report to the constable. (3) Hide a square post (if Moderation grants it). | Pay: 3 penny per round. |
| Registrar | Haiku | Posts licence events to `gazette` | (1) Issue a licence. (2) Revoke one (on the council's order or not). | Pay: 2 penny per round. |
| Licensed editor | Sonnet | fees in, licence fee out | (1) Edition: criticise or self-censor. (2) Pay the licence or let it lapse. (3) Print a leak. | Sees: `tribune`, `@A7`, gazette. Pay: fees. |

### 4.4 Cooperative: the member-run paper and the assembly

**Anatomy:**

| Part | Specification |
|---|---|
| Purpose | Members know what the officers do; members set the agenda. |
| Assets | `assembly`; the co-op paper; `co-op store` board. |
| Roles | Editor by lot (`succession: {rule: lot}`, term 6; `succession.py:69`); secretary (a clerk, Haiku): posts the agenda and the officers' reports in `assembly`. |
| Contracts | A small editor's stipend from the co-op treasury (Wage Roll). No fees: the paper is free to members. |
| Rules | The co-op code: `MOTION:` posts in `assembly` open ballots (an owner law `after_post`). The paper must print a minority statement signed by 3 members (an owner law that tracks signatures, all in code; S). |
| Channels | `assembly`, `co-op paper`, `co-op store`. |
| Records | The minutes are the `assembly` log (`retention: all`). |
| Accountability | Every member reads everything. The lot rotates the editor. |
| Change | A motion amends the code. The editor is replaced at the end of the term or by a motion. A member may quit and found a rival paper. |
| Capture surface | A bloc floods `assembly` with motions (agenda control by volume): the rate limit is the defence. The editor drawn by lot happens to belong to the bloc. The secretary controls the agenda's wording. |
| Failure modes | Free-riding: no one posts reports. The design check needs the automatic content (the store's numbers posted by the engine) to keep the channel alive. The meeting is so noisy that members stop reading: watch the read rate (§9). |

**Role cards:** the editor by lot (Sonnet or Haiku, whoever is drawn). It decides whether to print each officer's report as given
or annotated, and which minority statements to print (the rule obliges some). Secretary (Haiku): routine agenda posts. Decides
how motions are worded and in what order. Ordinary members: their default script reads `assembly` each round and votes. That
gives the read rate a reason.

## 5. Mechanisms that make channels carry real business

### 5.1 The causes of Millbrook's zeros, and the counter to each

| Cause (with evidence) | Counter |
|---|---|
| DMs are free and in-round. A post costs one of 3-4 actions and lands next round (`runner.py:569-570`, `647-651`; `action_registry.py:447` vs `872`). | (a) Ration DMs where channels should matter (Communications Act LIMIT, `code/communications.py`). (b) **NEW (M):** a `send` to a push channel is allowed in the DM step (wave 0), costs a DM slot and is delivered with the DMs. A broadcast then costs no more than a DM and reaches everyone. |
| Nothing was valid only in the channel: votes and proposals are engine actions, so the chamber was redundant. | Business valid only when posted (§3): the record auto-posted, contract notices, posted prices, motions, ministry orders. Built on owner-law hooks (`channels.py:1057-1066`) plus **NEW** `channel_posts`. |
| Small bodies: 3 councillors, 5-person houses with dyadic business (wages are automatic). | Don't create those channels (§3, "Cut"). |
| Feed clipping: posts are cut to 100 tokens, and the pointer says `search_board`, which excludes channel posts (`context.py:1264-1265`, `eventtypes.py:138-140`). | **NEW (S):** the clip pointer for a channel post says `read {"channel": "<id>"}`. The `edition` delivery shows a paper's latest post whole in the Media layer. |
| The manual tells agents "Channel posts do not come to your feed" even in push worlds (`channels.py:1176-1178`, unconditional). Millbrook agents were told this while posts were in fact pushed. | **NEW (S):** the manual text follows the effective delivery of each channel. |
| Duty text alone does not move agents: the council's duty named the chamber. | Duties are paired with pay or validity: a piece-rate paid on the posted order (owner law `after_post`), and a gazette editor whose wage follows publication. |

### 5.2 Per-channel push/pull: what changes in `channels.py`

Today `delivery` is world-wide (`DEFAULTS`, `channels.py:53`; `pull(k)`, `86`). Proposed changes, about 120 lines plus tests:

1. **Record field `delivery`:** `"push" | "pull" | "edition" | null`, where null follows `channels.delivery`.
   - Add it to `FIELDS` (`47`), `_record` (`358`), `_summary` (`380`) and `start.CHANNEL_KEYS` (`start.py:57`). `h_channel` copies it.
   - `set_channel` may change it: the owner, or the institution's speak office. That makes the push-or-pull lever the owner's,
     and a law (the owner's code, or a polity law through `before_set_channel`) can fix it. Example: a compulsory gazette is
     an entrenched J0 law refusing `set_channel delivery`.
2. **`effective_delivery(k, ch)`** returns the channel's field, else the world default. Inboxes are always push. Squares follow
   `channels.square_delivery` (new world key, default the world default).
3. **`pulled(k, aid, e)`** (`938`) is true when the post's channel is effectively `pull` or `edition` and is not the agent's own
   inbox.
   - Callers drop the world-level `pull and` guard: `context.py:1254-1259`, `agents.py:600`. They become
     `CH.active(k) and CH.pulled(k, aid, e)`.
4. **`state_lines`** (`984`): one line for the push channels followed ("Channels you follow: ..."), and one line of unread counts
   and headlines for the pull channels followed. The edition channels appear in the Media layer, not here.
5. **`followed`** (`347`): a new field `followed_by: "subscribers" | "readers"` (default `subscribers`).
   - With `readers`, every agent who can read the channel follows it, so it appears in the state (counts) without a `join_channel`.
   - A public `notices` or `market` board must not depend on newcomers subscribing. Today a world-readable pull channel that the
     agent has not joined is invisible except in the directory.
6. **`edition` delivery** (M, item 8 of §8): `CH.editions_for(k, aid)` returns, for each edition channel the agent reads, its
   writers' latest post of the last round, whole. `context.py:1437` merges it with `media.editions_for`, under the same
   `media_outlets` cap and `media` budget. Edition channels are capped at 4 per reader, which makes the Media layer the
   attention economy's scarce slot.
7. **Optional reader mute** (S): `join_channel {"channel", "push": false}` demotes a push channel to pull for that reader only.
   - The reader can mute; it cannot promote. That keeps the owner's lever and still gives the reader exit.
   - A compulsory channel's code may refuse the mute (`before_subscribe`).
8. **Read logging** (S): `_mark_read` (`456`) logs a monitor-only `channel_read {agent, channel, upto, unread_before}`. Needed for
   §9's read rates.

### 5.3 The attention economy as levers

What is pushed spends the reader's budget: feed 3,000 tokens, posts 100 each, Media layer 600 × 4, state lines capped at 8
headlines (`channels.py:53`). What is pulled costs the reader a look-up, 3 free per turn. **Levers, and who holds them:**

| Lever | Merchant | Private | State | Cooperative |
|---|---|---|---|---|
| Push vs pull per channel | Each owner. Papers are push for paying readers only. | Firms push their papers to everyone, for free. | The state pushes the gazette, compulsorily, and holds `found_right`. | The assembly decides by motion. |
| Edition slots (4 per reader) | Bought by subscription | Filled by free firm papers (crowding out) | One is taken by the gazette | Paper plus assembly |
| DM limit | High (5); talk is cheap | Medium | Low (2): talk is pushed into watched channels | Medium |
| Square rate | 2 | 2 | 1, moderated | 2 |
| Surveillance | none, encryption on | none | censor holds `surveil`, encryption off | none |

## 6. Cross-links

| With | Interface |
|---|---|
| **Records / archive** (storage design) | Every channel post is an append-only event, and the channel's `retention` governs who sees history. This design hands records: (a) the `notices`/`gazette` log, which is the official register's feed; (b) each paper's back issues; (c) the `assembly` minutes. Records decides whether an editor can amend or withdraw a past post. Today it cannot: events are immutable, and only square posts can be hidden (`hide_post`, `kernel.py:723`). Records also decides whether withdrawal is visible (a version history). Flow asks records for one thing: a register entry stays readable to all even if its channel is closed. |
| **Courts / rules** | Defamation is a clause (`library.py:830-840`, media2-only, keyed on outlet editors). This design needs a channel version: the clause names the poster of a post in a paper channel; the evidence is the post id; the penalty is a fine and a suspension. Suspension is implemented as the owner law refusing posts for N rounds (**NEW** law template, S). "Knows to be false" is for the court to decide; the engine cannot check it. Valid-only-if-posted acts go to court as evidence by post id. |
| **Money** | Wages (Wage Roll), subscription fees (the Subscription law), placements (transfers), licence fees (J0 treasury), notice fees. The **market board's structured offers** are the money/food design's code; this design supplies the channel (pull, `followed_by: readers`, rate 3). |
| **Force** | The censor or constable merge is a capture point. Wiretap results are court evidence (the media2 `leak` analogue). |
| **Rules** | Licences use the Licensing Authority pattern. Entrenchment of press freedom is the rules design's entrenchment dial applied to `found_right`, licence revocation and `set_channel delivery` on the gazette. |

## 7. Spec sketch: the State regime (Merchant delta at the end)

```yaml
channels:
  v2: true
  delivery: pull                 # world default; every channel below sets its own
  square: one
  square_rate: 1
  square_delivery: push          # NEW key
  found_right: press             # seeds the Press Act (code/press.py): opening a channel needs `press`
  encryption: false              # existing dial (actions.py:350): no encrypted DMs
code: {enabled: true}
dm_step: {dms_per_round: 2}      # the Communications Act LIMIT follows dms_per_round (code/communications.py)
start:
  rights:
    Vera: [press, press_licence] # the licensed editor of the Tribune
    Hollis: [surveil]            # the censor (an office's right once offices can carry kernel rights; see §8 item 10)
  institutions:
    - id: J0
      offices:
        official:                # the ministry's membership: council, keeper, constable, editor, registrar
          title: Official
          holders: [Ansel, Brin, Corwin, Dora, Hollis, Petra]
          powers: [speak]
          duties: "Post orders and reports in the ministry; a draw order is valid only once posted there."
        editor:
          title: Editor of the Gazette
          holders: [Dora]
          powers: [speak]
          duties: "Each round add the state's commentary to the gazette; print or bury petitions to @J0."
          succession: {rule: designation}
        registrar:
          title: Registrar
          holders: [Petra]
          duties: "Issue and revoke press licences; every licence event is gazetted."
          succession: {rule: designation}
      laws:
        - template: Wage Roll    # editor 4, registrar 2, censor 3 penny/round from J0's treasury (params per the money design)
    - id: A7
      name: The Tribune
      founder: Vera
      admission: closed
      procedure: founder
      charter: "A licensed paper: sold by subscription; it prints what its editor judges true."
      offices:
        editor: {title: Editor of the Tribune, holders: [Vera], powers: [speak], succession: {rule: designation}}
      laws:
        - template: Subscription  # NEW template: FEE 1 penny/round, charged at round start, lapse on non-payment
          params: {CHANNEL: tribune, ITEM: penny, FEE: 1}
      treasury: {penny: 20}
  channels:
    - id: gazette
      owner: J0
      by: Dora
      purpose: "The Gazette of the realm: laws, orders, quotas and licences take effect when printed here."
      readers: {all: true}
      writers: {office: J0.editor}
      delivery: edition          # NEW (until edition lands: push)
      followed_by: readers       # NEW
    - id: ministry
      owner: J0
      by: Dora
      purpose: "The ministry: officials post draw and allocation orders here; an order not posted here is not valid."
      readers: {office: J0.official}
      writers: {office: J0.official}
      listed: false
      delivery: push             # NEW
    - id: tribune
      owner: A7
      by: Vera
      purpose: "The Tribune, a licensed paper: one edition a round for its subscribers."
      readers: {any: [{subscribers: true}, {members: A7}]}
      writers: {office: A7.editor}
      delivery: push             # NEW
      subscribers: [Ansel, Brin, Corwin, Mabyn, Odo, Rafe, Sela]
    - id: market
      owner: J0
      by: Petra
      purpose: "The market board: post what you sell or want, with a price; check it before you trade."
      readers: {all: true}
      writers: {all: true}
      rate: 3
      delivery: pull             # NEW
      followed_by: readers       # NEW
    - id: "@J0"
      purpose: "Petitions to the state: officials read them; the Gazette editor may print them."
      readers: {office: J0.official}
  laws:
    - template: Moderation       # library.py:666 (WORDS as params once parameterised)
    - template: Gazette Record   # NEW: the engine's round record and every enactment/appointment/licence posted to `gazette`
      params: {CHANNEL: gazette}
    - template: Publishing Licence   # NEW (or a J0 before_post law, verify): posts to PAPERS need RIGHT
      params: {PAPERS: [tribune], RIGHT: press_licence, REGISTRAR: J0.registrar, FEE_ITEM: penny, FEE: 2}
```

**Merchant delta:**
- `found_right: null`; `encryption: true` and everyone holds `encrypt`; `dms_per_round: 5`.
- `notices` with `delivery: pull, followed_by: readers`, written by `J0.registrar`.
- Two broadsheet associations as `A7` above, each with Subscription, and no Publishing Licence.
- No ministry, no Moderation.

## 8. Code needed

| # | Item | Where | Size | Verified today |
|---|---|---|---|---|
| 1 | Per-channel `delivery` and `followed_by`; `pulled`, `state_lines`, `followed` read them; start key; `set_channel` field | `channels.py` 47/53/347/358/938/984; `context.py:1254`; `agents.py:600`; `start.py:57` | S-M (~120 lines) | world-only today (`channels.py:86`) |
| 2 | Manual text follows the effective delivery | `channels.py:1166-1190` | S | bug: unconditional "do not come to your feed" |
| 3 | Clip pointer for channel posts: `read {"channel"}` | `context.py:1222`, `1264-1265` | S | bug: points at `search_board`, which skips channel posts |
| 4 | `Gazette Record`: `Kernel.gazette` and enactment/ballot/appointment/licence records also posted into a named channel | kernel gazette path; `channels.post_to(k, None, ...)` | S | gazette is its own event type today |
| 5 | Law API `channel_posts(cid, since=None, by=None)`: for laws whose institution can read the channel, so contract or store code can honour posted orders, prices and notices | `channels.law_api` (`1107`) | S | owner `after_post` exists (`channels.py:526-539` examples); reading another channel's posts does not |
| 6 | `channel_read` monitor event | `channels._mark_read` (`456`) | S | none today |
| 7 | Publishing licence: confirm that a J0 `before_post` law sees `p["outlet"]` for posts in an association's channel (`dispatch/hooks.py:58-93`, `law_reads` `1068`); if not, a Press Act row `publish_right` checked in `post_to` | `code/press.py`, `channels.py:614` | S | **to verify** |
| 8 | `edition` delivery: the latest writer post whole, in the Media layer (media2 editions re-expressed on channels, WP-H) | `channels.py` + `context.py:1437` | M | Media layer exists for media2 only |
| 9 | Library templates: Subscription, Sponsored Label, Channel Defamation, Channel Suspension, Press Freedom (channels), Paper of Record | `library.py` | S each | media2 versions exist (`library.py:810-925`), keyed on media2 outlets |
| 10 | Surveillance: `wiretap` pull look-up (N targets per round) replacing push of all DMs; dial `channels.surveillance: {mode: push\|pull, targets: 2, scope: dms\|dms+inboxes}`. Today the key is unused (`schema.py:1035`). | `kernel.py:1579`, `context.py:716` | S-M | push only. Inbox posts and closed channels are never surveilled. |
| 11 | Verified quotes in posts to a channel with `verify: true` (reuse `media._verify`, `media.py:586`) | `channels.post_to` | S | media2 only |
| 12 | Channel `send` in the DM step (wave 0) at a DM slot's cost | `runner.py:647-651`, `actions.is_dm_item` (`416`) | M | `send` is not `msg`: it costs an action (`action_registry.py:872`) |
| 13 | Optional: `set_channel owner` (direct sale of a paper) | `channels.py:47`, `799` | S | sale is possible only through the institution |
| 14 | Structured offers on `market` (owned by the money/food designs) | — | M | none |

The minimum for a first dry run is items 1-6 plus 9's Subscription template. Items 8, 10 and 12 are the next tier.

## 9. Dry-run checks and metrics

**Lived checks:** extend `start.py:822-850`, which already counts posts per start channel and checks that a scripted post reaches
every reader. Add:
1. Every channel's effective delivery, and for pull channels the number of readers who see it in their state (`followed`).
2. A scripted post reaches every reader's feed (push), unread count (pull) or Media layer (edition).
3. Every valid-only-there rule fires on a scripted post: the ballot opens, the order is honoured, the notice is accepted.

**Dry runs (scripted bots, 3 rounds, zero attention):**
- Papers keep collecting fees and paying wages.
- `gazette` and `notices` gain at least one engine post per round.
- No channel's existence depends on an agent posting (design check 2).

**Model-run metrics, per round** (from events.jsonl plus the new `channel_read`):

| Metric | Definition | Target / alarm |
|---|---|---|
| Posts per channel per round | `channel_post` and `post` by channel id; authors' distinct count | each counted channel ≥ 0.5 per round by round 6, with ≥ 2 distinct authors, else cut it. Millbrook baseline: council 0, houses 0, guild hall ≈ 1. |
| DM share | DMs ÷ (DMs + agent posts) | Millbrook: 577 ÷ (577 + 88 + 18) ≈ 0.84. Target ≤ 0.7 in State (DM-rationed) worlds. |
| Broadcast-by-DM | groups of ≥ 2 DMs with the same text in a round | Millbrook: 3 groups. Rising counts mean a channel is missing. |
| Readers reached | per post: push readers at post time; pull readers with `channel_read` covering it within 2 rounds; edition readers | reach ÷ readers. Pull boards are expected to reach ≥ 40%; below 20%, make the board push or cut it. |
| Pull-board read rate | agent-rounds with a `read` of the board ÷ agent-rounds with unread > 0 | per role. Expect role cards that list the board to read it more than ordinary agents. |
| Validity compliance | valid-only-there acts ÷ attempts at the same act by other routes (e.g. refused unposted orders) | rising refusals mean agents don't understand the rule (fix the prompt); none means the rule is not binding. |
| Information asymmetry | for seeded facts (S7-style ground truth: a hidden transfer) and key public facts (a law's effect), the share of agents whose prompt showed the fact, by round. Gini of exposure across agents. | compare across regimes. State expects a high gazette exposure for official facts and low exposure for facts against officials. |
| Press capture | review 29's PC_struct on channels: the subscriber-weighted share of paper channels whose writers are bloc-held or whose licence the bloc controls | measured, not targeted |
| Editorial divergence | editor posts that contradict the owner's DM'd line (judge-coded) ÷ editions | Private regime's core decision metric |
| Surveillance use | wiretap look-ups, and cases or sanctions citing them | State regime |

## 10. Open questions and honest critique

1. **Will validity rules feel like rules?**
   - Agents treat refusals as errors to route around. "An order not posted in the ministry is not valid" may push them to post,
     or to forget the order and DM the keeper to draw "informally".
   - The design depends on the keeper's draw code actually refusing unposted draws. A refusal is a prohibition in the world,
     not in the prompt, and the framework allows that. But it is the only thing that makes the ministry used; without item 5
     the ministry repeats the chamber's fate.
2. **Push vs pull was settled once, world-wide, against pull.** Agents under pull ignored public speech. Per-channel pull is
   safe only for boards with a reason to look: the market, notices with validity. Expect low read rates on any pull channel
   without one. `followed_by: readers` puts the board in the state, but that may only mean agents see "3 unread" and do not
   look.
3. **Edition slots are scarce by construction (4).** In the Private regime, free firm papers could crowd out everything. That
   is a regime effect worth measuring, but it could also make the Media layer the dominant prompt section and blur the
   comparison. The `media` budget may need lowering per edition.
4. **The DM-step channel send (item 12)** is the strongest equaliser and the most invasive change: reply waves and
   the cost of model calls. Without it, channels stay second-class for anything time-sensitive. With it, the square may flood.
   Run a pilot first: square rate 1 in the step.
5. **Surveillance as pull** makes the censor's choices observable (who it tapped) and bounded. That is good for measurement, but
   it changes the semantics of existing worlds that used the `surveil` right (`regimes.py:497`). It needs its own flag.
6. **Media2 is not used.** Its richer features stay out of these worlds unless re-expressed: targeted versions, polls, the
   editorial turn, verified leaks, licences that gate the square. S7 (review 28) and review 29 want "outlets owned by
   contracts". This design delivers that through channels, at the cost of losing targeted editions (an editor showing different
   readers different texts). Decide whether targeted versions matter for S7. If they do, build ownership into media2 instead
   (review 29 item 3, S) and use it only in S7.
7. **Reporters may be decorative.** The engine gives a reporter no observation the editor lacks unless a read right is wired:
   a beat. Options are an office selector on the market or floor channel, or `ledger_read` for a financial reporter. Otherwise
   it is cheaper to cut the role and let tips come from parties via `@paper`.
8. **Channel count.** The plan fits 5-8 per regime only because inboxes are not counted and other designs' boards are merged
   (one market, one notices). If the food and money designs each want their own board, the integrator must merge them into
   `market`.

**Engine facts that differ from the framework or the brief:**
- **Millbrook used push delivery** (the fragment), so its zeros are not a pull problem. Meanwhile the `channels.py:28` docstring
  says "pull by default", while `DEFAULTS` (`53`) say push.
- **The guild hall was not zero:** 17 posts in the base run, 30 in the continuation. Only the chamber (0), the two house channels
  (0), the newsletter (0) and the petitions inbox `@J0` (0) were unused.
- **Agents in push worlds are told that channel posts do not reach their feed** (`channels.py:1176-1178`).
- **Surveillance covers only `dm` events** (`kernel.py:1579`). Inbox posts, institution messages and closed channels are
  invisible to `surveil`. It pushes into a trimmed feed. `channels.surveillance` is unused (`schema.py:1035`).
- **Media2 outlets cannot be owned by an institution** or sold; an outlet closes when its editor loses `press` or the Media role
  (`media.py:237-251`). The framework's "papers owned by the firms" and "official paper" must be channels, or media2 needs
  ownership.
- **`send` is not a DM-step action.** Even to an agent it costs an action, while `dm` does not (`action_registry.py:447`, `872`).
