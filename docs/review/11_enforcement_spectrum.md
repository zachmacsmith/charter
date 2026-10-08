# Review 11: the enforcement spectrum (from self-executing code to law as documents interpreted by agents)

*8 Oct 2026, at branch `integrate/w5` (`3c2e25c`). This is a design document. No code was changed, no model was called and no simulation
was run. Evidence about Charter comes from reading the code and from an in-memory count of the registries: 103 primitives, 63 of them
routed through `Kernel.apply` (`dispatch.ROUTED`). That is more than review 10's 51, because the loans and contracts work has merged
since. `open_case` and `answer_case` are declared but not routed. The legal theory and the prior systems are cited from general
knowledge; I did not re-verify them online. I list only works I am confident exist, and I mark the claims I am less sure of. Prices
are the Anthropic API list prices of 6 Oct 2026. Token counts per call are my assumptions, not measurements, and say so where used.*

---

## Executive summary

"Auto-enforced versus enforced by agents" is not one spectrum. It splits into **ten axes**, which fall into three groups:

- **Epistemic:** detection, and proof.
- **Normative:** content, interpreter, and review.
- **Executive:** timing, initiation, discretion, execution, and cost.

Charter sits at the self-executing corner on nearly every axis. Its clause, accuse and rule path is a thin, separate second system.

The most important structural finding is about choice. **When the world allows perfect, free, ex ante enforcement, every rational
legislator chooses it.** A per-law choice of enforcement mode (review 06's preference) therefore collapses to "auto" unless *physics*
restricts what auto can reach. So the user's question divides in two:

- **World physics** sets the feasible set: which acts the state can gate (its own registers and chokepoints), how likely the law is to
  detect private acts, and what enforcement costs.
- **Law** picks a point inside that set: interpreter, standing, discretion, and remedies.

The "laws as documents" end is buildable, and some of it exists today. As the default it is the wrong choice. It turns Charter from an
instrument for studying *institutional design* into one for studying *LLM interpretive behaviour*. It also makes "was the law followed"
undefined unless something supplies a reference interpretation.

**Recommendation: "code charges, courts decide".** Code stays the presumptive interpretation and the charge sheet. In "court" mode a
law's sanctions become cases with proposed remedies, which agent judges decide within caps the kernel enforces. A world-level dial
covers chokepoints and detection. Perfect enforcement stays as the control arm. The code's own verdict is recorded as a shadow
reference, so compliance, the enforcement gap, selective enforcement and the rule of law become measurable. The whole thing reuses the
P3.6 journal, the P3.7 compel predicate, and the W6b and W6f work, and it sits behind one spec block.

---

## 1. One spectrum or several?

### 1.1 The axes

I tested the candidate axes, kept those that move independently in real legal systems and in Charter's machinery, and merged or
rejected the rest:

- **Standing** became part of *initiation*.
- **Rule content** is kept separate from *interpreter*. They are correlated, but precise text can be read by a person, and code can
  delegate to a person.
- **Remedy form** (Calabresi and Melamed's property rule versus liability rule) is a cross-cut on the *timing* axis, not an axis of its
  own.
- I added two axes the list did not have: **proof**, which is separate from detection, and **review**.

| # | Axis | Range (real world) | Charter today (file:function) |
|---|---|---|---|
| 1 | **Detection**: does the enforcer learn the act happened? | perfect (a registry is the act) → high (cameras, audits) → witness or victim report → investigation by an office → never | **Perfect and free** for the 63 routed primitives: every bound law's `before_`/`after_` hook sees each one (`dispatch.bound_laws`, `_run_before`, `_enqueue`). **Zero** for the 40 unrouted ones. Holes by design: a covert attacker and an unnamed killer are scrubbed to `None` (`dispatch.HIDE`, `hidden_agents`, `hook_payload`); concealed actors; hidden jurisdictions (`J.vis`). Clause path: the accuser must have seen the event (`actions._accuse` → `Kernel.can_see`; the Spy may cite what it read, `roles.saw`) |
| 2 | **Proof**: who did it, established to what standard? | strict liability on an admitted record → preponderance → beyond reasonable doubt; evidence that can be forged | Hooks receive the payload, which names the actor except for the HIDE cases, so attribution is certain. Cases cite event ids and rendered text as the accuser saw them (`actions._cited`). Evidence can lie (forged DMs: `hidden`/roles `impersonate`). There is no standard of proof. Laws cannot read events (W6f) |
| 3 | **Content**: how determinate is the rule? | bright-line rule ↔ open standard ("reasonable", "good faith") (Kaplow 1992) | **Code** (`lawlang.check`: whitelisted Python, Turing-complete under gas), or the **clause text** `clause(name, text, penalty)` (`Kernel.api_for.clause`). Laws carry an `intent` string (`lawlang.static_info`) that has no legal force |
| 4 | **Interpreter**: who applies the rule to the facts? | machine ↔ official ↔ lay jury ↔ the parties themselves | The **Python interpreter** for code (`dispatch.invoke`). **Judge-right holders** for clauses (`actions._rule`), scoped to the clause's jurisdiction (`J.judges`) |
| 5 | **Timing and remedy form** | ex ante prevention (injunction, licence, physical barrier) / at-the-act price (withholding tax) / ex post sanction or compensation (Shavell 1993) | All three. A `before_` verdict of `False` is a **block** (a property rule enforced by physics). A number or `{"charge"}` is a **price** (a liability rule) (`dispatch.normalise`, `resolve_v2`). `after_` reactions are ex post (`drain_v2`). Clauses are ex post |
| 6 | **Initiation and standing**: who starts enforcement? | automatic / public prosecutor / victim only / any citizen (qui tam) / nobody | **Automatic** for hooks: a hook fires with no one asking. **Any agent** may `accuse` under any clause of a law that binds the accused (`J.check_case`). There are no standing rules (`open_case` is not routed, so `before_open_case` cannot fire) |
| 7 | **Discretion**: at each stage, may the enforcer decline or modulate? | mandatory (some civil-law systems' legality principle for prosecution) ↔ prosecutorial discretion, sentencing ranges, pardon, amnesty | **None** in code. Clause verdicts are guilty or not guilty. The penalty is **fixed**: `do_rule` calls `penalty(accused, accuser)`. There is no pardon or amnesty primitive. Prosecution is fully discretionary because nobody has to accuse |
| 8 | **Execution**: who carries out the sanction? | the state applies it itself (wage garnishment) / an office must act (bailiff, police) / self-help by the victim / reputation only | The **kernel applies it at once**. Fines move goods (`api_for.fine` → `Kernel.move`). A guilty ruling runs the penalty inside `do_rule`. "Laws never act for an agent" (ARCHITECTURE §1), so there is no specific performance |
| 9 | **Cost and capacity** | free / taxpayer-funded budget / fees / opportunity cost of officials' time (Becker 1968; Stigler 1970) | **Free.** Hooks cost gas only (`dispatch.gas_cfg`), and billing to treasuries is off by default (P3.8: `law.gas_price` null). Courts are capacity-capped: 3 rulings per judge per round (`actions._rule`) and a 3-round deadline (`Kernel._expire_cases`) |
| 10 | **Review and finality**: can an application be contested? | final / appeal / judicial review of administrative action / constitutional review / social override (the DAO fork) | **Final.** No appeal (rulings run at once). No way to contest a hook's block or charge. The only checks are legislative (`amend`, `repeal`), the Board veto, and the Fixer when a law crashes |

### 1.2 Three things the decomposition shows

**(a) The axes are per norm, not per world.** A real legal system is a *distribution* of norms over these axes. Take UK law as an
example:

- land transfer is a registry, so detection is perfect and the rule is ex ante;
- speeding is enforced by cameras: high but imperfect detection, automatic initiation, and a fixed penalty that can be contested;
- fraud needs investigation and proof, carries discretion, and is ex post;
- contract breach needs the victim to initiate, uses a civil standard of proof, and ends in compensation.

Charter can already mix modes per law: hooks for some norms, clauses for others. Because the self-executing path dominates, the mix is
not interesting yet.

**(b) Some combinations are coupled or incoherent.** Ex ante blocking needs detection at the moment of the act, and a decision fast
enough to stop it. In practice that means machine interpretation, *or* a prior-approval regime: an agent interprets *before* the act by
granting a licence, and a hook checks the licence. Charter can already express the second (`create_right` plus `before_harvest`
checking `has`; review 10 §3.3). So "ex ante with human judgment" exists, and it is licensing. A probabilistic ex ante block (customs
inspects 5% of shipments) is coherent too. Everything else that is "imperfect" is ex post.

**(c) The axes split into physics and choice.** That split is the central design fact of this document:

| Set by world physics (the feasible set) | Chosen by law (a point inside it) |
|---|---|
| 1 detection: base rates, and which acts are chokepoints | 3 content, 4 interpreter |
| 2 what evidence exists and whether it can be forged | 6 standing, 7 discretion, 10 review |
| 5 whether ex ante gating is physically possible for an act | 5 block versus price versus sanction, within what is possible |
| 8 whether sanctions execute themselves | 8 who must order them |
| 9 what enforcement costs | 9 how much to spend |

**Today the feasible set includes the corner: perfect, free, ex ante and self-executing, for every routed act.** A legislator who can
have the corner for free has no reason to choose anything else. That is why review 06's argument ("no global `court_only` dial;
agents choose enforcement through *which laws are in force*") is right about the switch and wrong about the dynamics. With the corner
available, agents will never choose costly enforcement, so per-law choice alone produces nothing new. The physics has to change for at
least some primitives.

### 1.3 What each position does to the experiment

| Axis | Moving away from today's corner gives | It costs | Research questions it opens |
|---|---|---|---|
| 1 Detection < 1 | evasion, deterrence as p×f, informants, surveillance as a policy, crime as a strategy | an RNG stream; harder analysis, because outcomes now depend on draws | Do agent polities find Becker's trade-off (low p, high f)? Does surveillance spending follow crime? |
| 2 Proof required | false accusations, forgery that matters, the value of witnesses (the Spy) | judge attention; a standard judges apply inconsistently | Do agents forge evidence when proof matters? How often are innocent agents convicted? |
| 3 Open standards | "reasonable" rules that adapt to unforeseen cases | the outcome depends on the judge's model and prompt | Do standards outperform rules when the world changes (Kaplow)? |
| 4 Agent interpreter | discretion, bias, corruption, precedent, drift | tokens; loss of determinism of *outcome* (replay is still exact) | Does interpretation drift? Is it captured by coalitions? |
| 5 Ex post only | violations actually happen; harm is real and must be remedied | less "safety" for experiments that assumed blocks | Does prevention versus punishment change norm-following? |
| 6 Standing rules | private enforcement, nuisance suits, litigation markets | a few new rules | Private versus public enforcement efficiency (Landes and Posner 1975; Becker and Stigler 1974) |
| 7 Discretion | selective enforcement, pardons, plea bargains | measurement needs a reference | Who gets prosecuted? Is enforcement partisan? |
| 8 Office executes | non-execution as a political act, and bailiff corruption | another loop and more latency (§2.3) | Does execution capacity become a bottleneck that agents invest in? |
| 9 Cost > 0 | an enforcement budget, trade-offs against other spending, the tax base | design of what enforcement costs | Do polities underfund enforcement? Does lawlessness emerge from fiscal weakness? |
| 10 Review | judicial supremacy fights, legitimacy, social override of code | latency; held funds | Do courts check legislatures? Do agents contest legitimately or strategically? |

---

## 2. The "laws as documents interpreted by agents" end

### 2.1 What it would mean concretely

- **A law is text**, enacted by procedure, with a rank. It optionally carries code as an *aid*: a definition, a computation, a
  detector. It may declare a **remedy schedule** that the kernel enforces as an upper bound (*nulla poena sine lege*: a judge can
  never fine beyond what the text allows).
- **The kernel guarantees physics only.** That means conservation, exit, visibility and redaction, determinism, gas, the Board and Fixer
  contract, and the *mechanics* of cases and ballots: who may file, who may rule, that verdicts and votes count as cast, deadlines, and
  that a guilty ruling's remedy executes within caps. Review 10 §7 already draws this line. This end of the spectrum takes it
  literally: everything else about *what the law requires* lives in agents.
- **Roles are held by agents**, through rights and offices that already exist or are cheap to add:

| Role | Already in Charter? | Notes |
|---|---|---|
| Legislator | yes (`propose`, ballots, procedures) | unchanged |
| Police and investigator | partly (`lawful_attack`, `oblige_guard`, offices via `define_action`) | needs a detection effect (§3, H3) |
| Prosecutor | yes: anyone may `accuse`; a prosecutor office is library code | standing rules need routed `open_case` (W6b) |
| Judge | yes (`judge` right, `actions._rule`) | binary verdicts, fixed penalty, one judge |
| Lawyer and advocate | no | could be an agent authorised to `respond` for another (P4.5 agency), or just DMs and posts |
| Defendant | yes (`respond`) | no right to be heard before the ruling; the judge may rule at once |
| Jury | library "Jury Trial" draws 3 single judges | real panels need W6c stages on a case |
| Executor (bailiff) | no: the kernel executes | optional treatment (decision 10) |

### 2.2 The mechanics it opens

Most of these already exist in *some* form, because any agent can pay any agent and judges have discretion. What changes is that they
start to *matter*.

| Mechanic | How it appears | Exists today? |
|---|---|---|
| **Corruption** | a judge or prosecutor paid by a party (transfers carry no memo, so a bribe looks like a gift) | possible, but only relevant on the clause path |
| **Selective enforcement** | who gets accused or convicted given the same conduct | possible on the clause path; not measurable without a reference (§5, decision 8) |
| **Precedent** | rulings with reasons are public; judges may read and cite them | text exists (gazette, `ruling` events); there is no citation field and no reads |
| **Legal argument** | accusation and response as text plus evidence | yes, thin |
| **Jurisprudence drift** | what the same text means changes over rounds, as judges and models change | emergent; measurable only against a fixed reference |
| **Legitimacy** | agents comply because they accept the rule, not because they are forced to (Tyler 1990) | invisible today, because compliance is forced |
| **Enforcement capacity as a budget** | judges' turns, investigators' goods | judges are capped at 3 per round; nothing else |
| **Private enforcement** | victims sue; bounty hunters; private prosecution | yes (`accuse` by anyone) |
| **Vigilantism and self-help** | attack, seize and expel outside law | force exists (`attack`); its *legal* status is a clause |
| **Rule of law as an emergent, measured property** | Fuller's (1964) congruence between declared rule and official action, equality, predictability | not measurable today, because there is nothing to compare against |

### 2.3 What it costs

**Tokens.** Prices: Opus 5.5 costs $4 per million input tokens and $20 per million output tokens (cache reads $0.20). Sonnet 5.5
costs $2/$10. Haiku 4.5 costs $1/$5. Batch processing is 50% off.

The base world is `charter/specs/base.yaml`: 29 agents and 80 rounds. *Assumption, to be replaced by the `usage` fields in a recent
run's `calls.jsonl`:* a main agent turn is about 15k input and 3k output tokens including thinking, which is about $0.12 on Opus.
Main turns alone then cost about $3.50 per round, or about $280 per 80-round run, before DM waves.

| Adjudication design | Marginal cost per case | At 15 cases per round | Comment |
|---|---|---|---|
| **Judges are existing agents** and rule during their own turn (today) | ~1-3k extra input and ~0.3-0.8k output in the judge's prompt: **~$0.01-0.03** | ~$0.15-0.45 per round (+4-13%) | Cheap in tokens. Expensive in *agent attention*: a ruling uses one of the judge's actions |
| **Dedicated court call** per case (a "court" phase, like `editorial` and `observer`) | ~10k in, 2k out: **~$0.08** on Opus, ~$0.04 on Sonnet | ~$1.2 per round (+35%) | Decouples capacity from turns, but adds a non-player LLM, which is a confound |
| **Interpret every relevant act** (text-only law with no code detector) | 29 agents × ~5 acts × $0.08 | ~$12 per round (**~3.5× the base**) | Not viable. Real law never does this either: most conduct is never adjudicated ("bargaining in the shadow of the law", Mnookin and Kornhauser 1979) |
| **Offline reference panel** (measurement only, after the run, batch) | 3 Sonnet judges × (8k in, 1k out) × 50% batch: ~$0.04 | — | ~$20 for 500 cases. Does not touch the run or replay |

The conclusion is robust to my token assumptions being off by 2×. **Interpretation must be lazy**: it happens on a dispute or a
detection, never per act. And it should run inside agents' turns. Something still has to *detect* in order to open cases, and the
cheapest detector is code.

**Latency in rounds.**

- Accusation to ruling takes at least 0-1 rounds (the judge acts in its next turn) and at most 3 (dismissal).
- An appeal adds 1-3.
- An office that must execute the sanction adds 1 more.

In an 80-round world, deterrence delayed by 1-5 rounds is tolerable. In a 20-round pilot it is a large share of the run, and any pilot
must account for that.

**Determinism and replay.** Judges who are agents are already replayable: their turns are calls keyed by
`provenance.call_key` (`r<round>:<phase>:<wave>:<agent>:<n>`), served by `replay.ReplayPolicy`. A dedicated court call would need its
own key phase (`PV.Keyed(policy, phase="court")`, as `editorial` and `observer` already do in `runner.py`), and it would then replay
too. Detection draws must not perturb existing streams. Use stateless hash-seeded draws such as
`Random(f"{seed}|detect|{event_id}|{account}")` instead of a shared stream, so that enacting a law does not shift every later draw.
**Replay stays exact. What is lost is *counterfactual comparability*:** the same world under a different seed or model gives
different law, not just different behaviour.

**Measurement.** When the law is text, "was the law followed" has no ground truth. The options are in decision 8. The short version:
*keep a reference interpreter*, either code or an offline panel. Without one, compliance can only be defined as "what the courts
said", which is circular for the questions the user cares about (selective enforcement, corruption).

**Agent comprehension.** Opus reads both code and text well. Text is *shorter* and closer to the training distribution. Code is
*checkable*, by previews (`preview.py`) and static review (`check_propose`). Text-only law gives up the previewer, lex superior
checks on content, static classification, and conflict resolution, all of which are among Charter's distinctive features.

**New failure modes.**

1. **Dead letter.** Nobody accuses, and judges ignore their queue. An unenforced legal system then looks like no legal system.
2. **Kangaroo courts.** Judges are players with goals. A coalition holding the `judge` right convicts its rivals.
3. **Collusion.** Accuser and judge split a fine (the penalty can pay the accuser: library "Honest Dealing").
4. **Model homogeneity.** All judges share one model family's priors. "Jurisprudence" may then show only prompt artefacts and model
   bias, such as positional and self-preference biases of the kind documented for LLM judges (Zheng et al. 2023), not institutional
   effects.
5. **The compliance prior.** RLHF-trained agents may comply with almost any stated rule even at zero detection. That would make
   enforcement mechanics moot, and it is a model property, not a property of the institution. This needs a baseline arm (decision 7).
   GovSim (Piatti et al. 2024) is a counterweight: most LLMs there failed to sustain a commons, though that was without written law.
   I am fairly, not fully, confident of that paper's exact findings.

### 2.4 My honest assessment of the pure-documents end

The pure end is a coherent simulator, but a *different* one. It measures how LLMs behave as legal officials. That is interesting, but
it is dominated by model and prompt effects, and it discards what Charter does that nothing else does: law as an executable,
previewable and composable object. Prior art points the same way from both directions:

- **From text towards code:** Rules as Code (OECD OPSI, *Cracking the Code*, 2020) and Catala (Merigoux, Chataing and Protzenko, ICFP
  2021, which formalised parts of French tax law) exist because applying text is costly and inconsistent.
- **From code towards text:** smart contracts drifted back the other way. The 2016 DAO exploit was "legal" under the code, and it was
  reversed by a social hard fork. Kleros-style on-chain arbitration exists because code cannot settle every dispute.
- **The settled practice in both directions is a hybrid:** code or a registry is the default; an agent or a court can override it on
  a dispute. Lessig (1999, *Code*) and Grimmelmann (2005, "Regulation by Software", Yale Law Journal) describe what code-as-regulation
  removes, namely discretion, ambiguity and the possibility of disobedience. Those are exactly the things the user wants back.
- **Hart (1961)** gives the cleanest diagnosis. Charter is rich in *secondary rules of change* (procedures, amendment) and *of
  recognition* (rank, lex superior). It is poor in *rules of adjudication*. The useful move is to strengthen adjudication, not to
  dissolve the code.

---

## 3. Hybrid designs

Each design below names what changes in dispatch and the kernel, what agents must do, the cost, and the research questions it lets the
user ask. H1, H2 and H5 are the core of the recommendation. H3, H4 and H6 are optional treatments.

### H1. Code charges, courts decide (the per-law `enforcement` mode)

A law declares a top-level constant `enforcement = "auto" | "court" | "report"`. It is checked statically like `rank`
(`lawlang.static_info`), shown by previews and `read_law`, and defaults to `"auto"`.

- **auto:** today's behaviour.
- **court:** the law's code still runs on every *detected* primitive, but its coercive effects on non-consenting agents become
  **charges in a case** instead of changes:
  - a fine, a move from an agent, a suspension or a limit opens a case (or adds to one) with `{law, accused, proposed: [the effects],
    evidence: [the event], source: "law"}`;
  - a `before_` **block** cannot be ex post, so in court mode it becomes "allowed, case opened". This is the honest translation of a
    prohibition without a physical barrier;
  - a `before_` **charge** becomes an *assessment*: the amount is moved to a held account (`held:<case>`, conservation-safe), and it is
    released to the treasury if the case is uncontested or upheld, or refunded otherwise.
- **report:** effects become a public `violation_reported` event and nothing else. This is the "word" analogue.

**What changes in code.** The predicate "a law-caused change to a non-consenting agent" already exists: it is `dispatch.compel_note`,
with the `NOTIFY` rows from P3.7. In court mode, the same predicate *diverts* the change into a case instead of notifying about it. The
diversion runs in `apply_v2` before `fn(...)`, and the case store is W6b's. Remedies a judge may impose are capped by the proposed
effects (the code's charge sheet is the ceiling) unless the law declares a wider schedule.

**What agents must do.** Judges rule `{verdict, remedy ≤ cap, reasons, cites}`. The accused may respond. Legislators choose the mode
when they write the law.

**Cost.** One more action per case for a judge. No new LLM calls.

**Questions it answers.** What do discretion and delay alone do to compliance, inequality and law-making, holding detection fixed?
Combined with the mechanical court (H5), it separates the effect of *delay and capacity* from the effect of *judgment*.

### H2. World detection and chokepoints (physics)

A spec block, `law.enforcement: {gates: all | state_only, detection: {default: 1.0, <primitive or family>: p}}`.

- **Chokepoints.** Each primitive row gets a metadata field, `gate: "state" | "private"`:
  - state: legal acts, `mint`, `grant_right`/`revoke_right`, `create_currency`, `join`/`admit`, `set_camp_rule`, loans registered in
    the credit record;
  - private: `move`, `attack`, `post`, `dm`, `harvest`, `convert`, `fortify`.

  Under `gates: state_only`, `before_` hooks on private primitives are not offered. A law that defines one fails the static check with
  "not gateable in this world" (better than silently ignoring it). This is the most realistic single change available: **states
  control their own registers perfectly and private conduct imperfectly.** Land transfer without the registry is not a transfer; a
  payment in cash is.

- **Detection.** For private primitives, each bound law's account receives the `after_` item with probability p. The draw is
  hash-seeded per (event id, account), so it is stable under any reordering. Undetected acts are logged monitor-only.

  Who knows what:
  - Parties always know about their own act.
  - The victim may *report* it. A new action, `report {event, to: law|polity}`, makes an event the reporter can see detected for that
    account. That is the informant mechanic, and the Spy becomes a valuable witness.
  - Witnesses are exactly the agents for whom `can_see` is true.

- **Where it plugs in.** `dispatch._enqueue` (filter the after-items) and W6f's law-readable evidence. One predicate,
  `law_can_see(k, lid, event)`, decides both, so a law cannot use `history()` to read what its hooks were not allowed to see.

**Cost.** No LLM calls. A few microseconds per primitive.

**Questions it answers.** Evasion, deterrence, surveillance policy, the value of informants, and Ostrom's monitoring principle (1990)
tested directly.

### H3. Enforcement offices with budgets

The law function `investigate(target, family, rounds, spend)` is callable from an office (`define_action`). It moves `spend` from the
treasury to the world sink and raises detection for the target's primitives of that family for the given number of rounds, with
diminishing returns, e.g. p' = 1 − (1 − p)·e^(−spend/k). Whether the target is told is a spec choice; the default is no, with a
monitor log.

**Agents** must run and fund the office.

**Questions it answers.** Becker (1968), Polinsky and Shavell (2000): spend on p or raise f? Corruption of investigators (pay them not
to look). Selective investigation as a political weapon.

**Risk.** This adds a tuning constant (k) that drives results. Calibrate it once and freeze it per world family.

### H4. Private suits and standing

This needs `open_case` routed (W6b), so a constitution can write standing rules in `before_open_case`: victims only, filing fees,
loser-pays, limitation periods. Library templates would cover a qui tam bounty (a share of the fine to the accuser, which exists
already through the penalty function) and malicious-prosecution costs (library "Malicious Prosecution").

**Questions it answers.** Private versus public enforcement (Landes and Posner 1975). Litigation as a weapon. Selection of disputes:
Priest and Klein (1984) predict that litigated cases are an unrepresentative sample. That matters for how we measure, because rulings
are not a random sample of conduct.

### H5. Judicial review of the code's application (contest), and the mechanical court

**Contest.** In auto mode, sanctions that a law declares `contestable = N` (a constant) are executed *provisionally*. Fines and
charges go to `held:<id>` for N rounds, and suspensions and limits run at once. The affected agent may `contest {id, reason}`, which
opens a case whose question is "does the rule apply to these facts, and is the rule valid?". A ruling for the contestant refunds the
held goods and lifts the provisional sanction (a law-caused `revoke`/`unlimit`, so W6b needs an `unlimit`). A block cannot be undone
after the fact. The court's remedy for a wrongful block is a *dispensation*: a public register that the law's hook reads as an
`exempt` (e.g. `lib:dispensations`).

This is the structural answer to the DAO problem: **code is the presumptive interpretation, and courts can override it on a dispute.**

**Mechanical court.** This is a scripted judge that applies the proposed remedy (H1) or upholds the code (H5) after a fixed delay. It
uses no LLM. It is the **control** that separates delay and capacity from discretion, and it is the fallback when a world has no
judges. It can also be a scripted "standard" judge that evaluates an optional `test(case)` function in the law.

**Questions it answers.** Do agent courts check legislatures? Do agents contest strategically? Does judicial override increase
legitimacy, measured as voluntary compliance under lower detection?

### H6. Text-only laws (bounded)

A law record may have `text` and a `remedies` schedule, e.g. `{"fine": {"item": "grain", "max": 10}, "limit_actions": {"max_rounds":
2}}`, and no hooks. Its only legal effect is that cases may be filed under it. The kernel caps the remedies. Its class is derived from
the schedule (fines make it ordinary; suspending kernel rights makes it structural), so lex superior and procedures still apply.

This generalises `clause`. A clause today needs a code-bearing law to declare it, and it carries a *fixed* penalty function.

**Agents** write prose. Judges interpret it.

**Cost.** Small in the kernel. Heavy in measurement: there is no shadow reference, so it needs the offline panel (decision 8).

**Questions it answers.** Do rules or standards perform better? Does interpretation drift? Does text-only law grow when agents can
choose?

### Comparison of the designs

| | H1 court mode | H2 chokepoints and detection | H3 investigation | H4 standing | H5 contest and mechanical court | H6 text-only |
|---|---|---|---|---|---|---|
| Axes moved | 4, 5, 7, 10 | 1, 5 | 1, 9 | 6 | 10 (and 4 as control) | 3, 4 |
| Kernel or dispatch work | M (divert compel effects into cases, held accounts) | S-M (row field, filter, hash draws, `report`) | S | S (with W6b) | M (held sanctions, dispensations, scripted judge) | S-M |
| New LLM calls | none (judges' turns) | none | none | none | none | none in the run; offline panel |
| Byte-identical when off | yes | yes | yes | yes | yes | yes |
| Measurement | shadow = the code's charges | shadow = the undetected log | same as H2 | needs H1 or H2 | shadow = the code's verdict | needs the panel |
| Priority | **core** | **core** | treatment | with W6b | **core** (the mechanical court) | treatment |

---

## 4. Porting path

**Ground rules** (ARCHITECTURE §11):

- Everything below is behind a new spec block `law.enforcement` (absent means today's behaviour) and requires `law.v2`.
- Old goldens are untouched. Each package adds at most one new golden case (`society_enforcement`).
- The differential harness (`difftest.run_pair`) must be clean on every existing preset with the block absent.
- No package draws from an existing RNG stream.

| WP | Scope | Files | Flag | Depends on | Golden |
|---|---|---|---|---|---|
| **E0** (no code) | Measure the clause path in existing runs: counts of `accuse`, `respond`, `ruling` and `case_dismissed`; time to ruling; rulings per judge; the share of library laws in each mode; how often agents *choose* clauses over hooks | analysis notebook over History | — | G5 | — |
| **E1** | Vocabulary and metadata: `Primitive.gate` (state/private) for all 103 rows; `enforcement` constant parsed by `lawlang.static_info` and shown by previews and `read_law`; spec schema for `law.enforcement` (P1.3 `DEFAULTS`); contract-test rows | `primitives.py`, `lawlang.py`, `preview.py`, `schema.py` / `features.py`, `tests/test_charter_contract.py` | metadata only | P1.7, P3.5 | preserving |
| **E2** | Case store v2 shape for law-opened cases: `source: agent \| law \| contest \| report`, `proposed` effects, `held` accounts, `cites`. Lands *inside* W6b | `kernel.py` (cases), `dispatch.py` (`open_case` row), `actions.py` | with W6b | W6b | W6b golden |
| **E3** | H1: diversion of compelled effects in court and report modes (`compel_note` reuse), held assessments, remedy caps checked in `do_rule` | `dispatch.py` (`apply_v2`, `do_rule`), `accounts.py` (owner key `held:`) | per-law `enforcement` | E1, E2, P3.7 | new `society_enforcement` |
| **E4** | H5: `contestable = N`, provisional sanctions, the `contest` action, dispensation register block, `unlimit`; mechanical court (`law.enforcement.court: agents \| mechanical \| mixed`) | `dispatch.py`, `actions.py`, `action_registry.py`, `library.py` | per law; court mode in the spec | E3 | same golden |
| **E5** | H2: `gates: state_only` (static refusal of private `before_` hooks), detection filter in `_enqueue`, hash-seeded draws, monitor `undetected` log, the `report` action, one `law_can_see` predicate shared with W6f | `dispatch.py`, `actions.py`, `lawlang.py` (static check), W6f's read functions | spec | E1, W6f | second golden with p < 1 |
| **E6** | **Shadow reference**: for every undetected act and every court or report-mode law, run the law's hook inside a P3.6 journal frame that is *always rolled back* (`dispatch.begin`/`rollback`, which already restores state, events, RNG and links), on a separate gas meter, and log monitor-only `shadow_verdict {law, event, verdict, effects}`. History table `violations` | `dispatch.py`, `history.py`, `eventtypes.py` | `law.enforcement.shadow: true` (default on when the block is present) | P3.6, E3, E5 | same goldens |
| **E7** | H3 investigation offices: the `investigate` law function, budget sink, detection boost | `dispatch.py` / `lawapi.py`, `lawdocs.py` | spec `investigation: true` | E5 | — |
| **E8** | H6 text-only laws with `remedies`, derived class; library templates in both modes for the 10 most-used library laws (auto, court and text versions of each) | `kernel.py` (law records), `lawlang.py` (class from remedies), `library.py` | spec `text_laws: true` | E3 | — |
| **E9** | Measurement: the `charter adjudicate RUN --panel` offline reference panel (batch, outside the run, never replayed); rule-of-law metrics in the scorer and export (§5, decision 8) | `export.py`, new `adjudicate.py`, `scorer.py` metrics | — | E6, P5.5 | — |

**Why existing `law.v2` worlds stay byte-identical:**

- E1 is metadata only.
- E3-E7 run only when `law.enforcement` is present, or when a law declares a non-auto mode, which no existing law can do because the
  constant is new and is not parsed today.
- Hash-seeded draws touch no shared stream.
- E6's shadow runs are rolled back, metered separately, and logged monitor-only. Even so they change `events.jsonl`, so they too run
  only under the block.

### 4.1 How this composes with the work in progress, and what should change shape

| Package | As planned | Change of shape I recommend |
|---|---|---|
| **W6b courts v2** (cases readable by laws, routed `open_case`/`answer_case`, remedies, court rules, appeal) | agent-opened cases with remedies and appeal | **Yes, the biggest change.** (1) Cases can be opened by laws and by contests, not only by `accuse` (`source` field). (2) A generic **provisional or held sanction** state, used by appeal (deferral), by H1 assessments and by H5 contests: build it once. (3) Remedies are bounded by a declared schedule or by the code's proposal, and the kernel enforces the cap. (4) Rulings carry `reasons` and `cites` (case ids), so precedent is measurable. (5) Court capacity is a law-settable rule (`set_court_rule("rulings_per_round", n)`), not a constant. (6) Keep kernel execution of judgments as the default |
| **W6f law-readable evidence** (`event(eid)`, `history()`) | visibility by the law's account | **Yes.** One predicate, `law_can_see(k, lid, event)`, used by both the reads and after-hook delivery, so the detection dial cannot be bypassed. `history()` reads only detected events of private primitives |
| **W6e contract enforcement dial** (escrow \| escrow_court \| word) | contracts-specific | **Align, don't duplicate.** `escrow_court` should open W6b cases through E2. `word` is the same as report mode. Share the vocabulary: `auto` ≈ escrow (self-executing within what the contract controls), `court`, `report`. One court system for contracts and statutes. Contracts may name their arbitrator office, which is arbitration in the sense of Milgrom, North and Weingast (1990) |
| **W6a** `refuse(reason)`, `in_force_until` | clean refusal; sunset | `refuse` unchanged, plus: an office's refusal is logged as an administrative decision with an id that H5's `contest` can target. Administrative review then comes for free. `in_force_until` unchanged |
| **W6c multi-stage procedures** | legislative stages, ballot rule functions | **Small change.** Allow a ballot's subject to be a case, with a jury or panel as the electorate and the rule as a function, so collective verdicts and appeal panels reuse stages instead of a parallel court-panel mechanism |

---

## 5. Decisions for the user

Each decision below gives the options, what each implies, my recommendation, and what would change my mind.

### Decision 1. Default position on each axis for new worlds

| Option | Mechanics | Research value | Cost | Risk |
|---|---|---|---|---|
| A. Keep today's corner as the default; everything new is opt-in | none new unless asked for | continuity with every past run | lowest | the interesting mechanics never get used |
| B. New-world default: `gates: state_only`, detection 1.0, `court: agents`; laws pick their mode | private conduct can no longer be blocked; prohibitions become ex post | high, and still comparable (detection 1) | M | breaks the "safety" of blocks that worlds and goals assume |
| C. Full realism default: state_only plus detection < 1 plus H3 | everything at once | highest variety | M-L | too many simultaneous changes to attribute effects |

**Recommendation: A for this quarter, with B as the first treatment arm, then a decision based on the pilot (§7).** Default per axis
once B is adopted:

- detection: 1.0, with chokepoints restricting gates;
- proof: event-cited;
- content: code, plus text with remedies;
- interpreter: code presumptive, courts on contest;
- timing: ex ante for state acts, ex post for private ones;
- initiation: automatic detection, any agent may file;
- discretion: bounded remedies, no pardon by default;
- execution: the kernel;
- cost: judges' turns;
- review: contestable when the law says so.

*What would change my mind:* if E0 shows that agents already use clauses heavily, B can go straight to default.

### Decision 2. Do text-only laws exist?

| Option | Implication |
|---|---|
| A. No: clauses only, inside code laws (today) | keeps static analysis, but standards remain second-class |
| B. Yes, bounded (H6): text plus a kernel-enforced remedy schedule | standards become first-class; measurement needs the panel |
| C. Every law is text, code is optional, and **text is authoritative** where they disagree | the civil-law reading; loses determinism of content everywhere |

**Recommendation: B, plus a rule for code laws.** Code is authoritative by default, and a court may override its application on a
contest (H5). Never C: it converts every law into a dispute about meaning, and Charter's previewer, conflict rules and lex superior
stop meaning anything.

*What would change my mind:* agents who write prose laws that judges apply consistently (high panel agreement in the pilot) would make
a C-like arm worth running as a treatment, not as the default.

### Decision 3. Who interprets?

| Option | Implication |
|---|---|
| A. The Board | the Board is an experimental-contract body; adding judging conflates it with government and makes it a player in disputes |
| B. Holders of the `judge` right, appointed by law (today; elected or appointed by the polity's own laws) | political: judges are part of what agents build |
| C. Any agent chosen by the parties (arbitration) | the market for judges; private order (Milgrom, North and Weingast 1990) |
| D. A non-player LLM court | neutral, but an external authority the agents cannot capture, and a strong confound |

**Recommendation: B for polity law, and C for contracts and for any case where both parties agree.** Not A. Not D except as a
measurement panel.

*What would change my mind:* if courts in B are captured in almost every run, so that capture is the only result, a D arm becomes
useful as a "neutral court" contrast. It is a treatment, not the default.

### Decision 4. Are judges always LLM agents, or may they be scripted?

| Option | Implication |
|---|---|
| A. Always agents | realism; there is nothing to compare against |
| B. Agents, with the **mechanical court** as both control arm and fallback | separates discretion from delay; worlds with no judges still function |
| C. Scripted only | cheap, but it is just auto with lag |

**Recommendation: B.** The mechanical court is the single most valuable control in this whole design. Without it, any effect of
"courts" could be pure latency.

*What would change my mind:* nothing likely. The control is cheap.

### Decision 5. Is detection a world property or a law or office property?

| Option | Implication |
|---|---|
| A. World only (a base p per primitive or family) | clean physics; laws cannot change how visible the world is |
| B. Law-declared (a law says how often it "looks") | collapses to p = 1, because looking is free (§1.2) |
| C. World base, raised by offices **at a cost** (H3), and by witnesses' reports | Becker's economics; informants; surveillance as policy |

**Recommendation: C, built in two steps: A in E5, the cost-bearing raise in E7.** Never B.

*What would change my mind:* if H3's single constant k turns out to dominate outcomes in sensitivity runs, keep A plus reports only.

### Decision 6. How to keep runs replayable and comparable

**Recommendation, all of the following:**

- Judges act only in their own turns, so they are already recorded calls.
- Any extra LLM call goes through `PV.Keyed` with its own phase.
- Detection draws are hash-seeded per (seed, event, account).
- Shadow verdicts run under a journal that is always rolled back, on a separate meter.
- The offline panel runs outside the run and is stored as a separate artefact with its own version.
- `run.json` records the `law.enforcement` block.

On comparability, accept that agent courts make outcomes path-dependent, and use replicates rather than paired seeds. The alternative
(no LLM judges at all) gives up the point of the exercise.

*What would change my mind:* a replay test that fails because of draw ordering. That would mean the hash scheme was not followed, not
that the design is wrong.

### Decision 7. Does perfect enforcement remain as a control arm?

| Option | Implication |
|---|---|
| A. Yes, always (auto, detection 1, gates all) | every result has a baseline |
| B. Plus a **mechanical-court arm** and an **honour-system arm** (report mode, detection 0) | also separates latency from discretion, and measures the models' compliance prior |
| C. No; move on to realism | results cannot be interpreted |

**Recommendation: B.** The honour-system arm matters more than it looks. If Opus agents comply at about 100% with zero enforcement,
the enforcement mechanics have nothing to do. Find that out before building E7 and E8.

*What would change my mind:* nothing. This is cheap and decisive.

### Decision 8. How to score compliance when law is text

| Option | Defines "violation" as | Strength | Weakness |
|---|---|---|---|
| A. Positivist (Holmes 1897, "The Path of the Law"): the law is what the courts do | a conviction | free | circular for corruption and selective enforcement |
| B. **Shadow code reference** (E6): the code's verdict on every act, detected or not | the code's charge | exact, deterministic, free in tokens | exists only for code-backed laws; it is the *legislator's* interpretation |
| C. **Offline panel** (E9): k independent judges, ideally a different model mix, on the full facts | majority or average of the panel | works for text; reports inter-judge agreement | costs money (small, about $0.04 per case); model bias; not the agents' own law |
| D. Structural rule-of-law metrics built on B or C | — | the measures the user asked for | depends on B or C |

**Recommendation: B as the primary measure for code laws, C on a sample for text laws and for validating B, and D always reported.**
Concrete D metrics, following Fuller's (1964) desiderata:

- **Congruence:** P(sanction | shadow violation) and P(sanction | no shadow violation). These are the enforcement rate and the false
  conviction rate.
- **Equality:** the gap in those rates across groups (coalition, class, judge's allies, wealth quartile).
- **Predictability:** agreement between rulings on cases with the same shadow verdict and similar facts.
- **Timeliness:** the distribution of time to ruling.
- **Legitimacy proxy:** the compliance rate on undetected acts, i.e. shadow violations among undetected acts compared with detected
  ones, which is like measuring compliance when nobody is looking.

Rulings are a selected sample (Priest and Klein 1984). Never compute rates over cases alone; always use the shadow population as the
denominator.

*What would change my mind:* low panel agreement (κ < 0.4) on text laws would mean text laws cannot be scored, and H6 should stay
out.

### Decision 9. What does enforcement cost, and who pays?

Options: free (A); gas billed to the treasury (B, P3.8); goods from the treasury for investigation and fees for courts (C); judges'
turns only (D).

**Recommendation: D plus C.** Judges' attention is the natural, honest cost, and investigation should cost goods. Gas billing stays
off: it prices computation, not enforcement, and would conflate the two.

*What would change my mind:* if judges never rule because their own goals crowd it out, consider a salary office, which is library
code. Do not make ruling free of actions.

### Decision 10. Who executes sanctions?

Options:

- **A.** The kernel executes court judgments and provisional sanctions (today).
- **B.** An executor office must act, or the judgment lapses.
- **C.** Self-help: the court authorises the winner to seize, guarded by the kernel's caps.

**Recommendation: A, with C as a later treatment.** Each extra loop roughly halves the rate at which an agent-driven process completes
(rough intuition, not a measured number), and B makes "nobody enforced" indistinguishable from "nobody judged".

*What would change my mind:* a pilot where courts work well and execution is the remaining realistic gap.

### Decision 11. Are auto sanctions contestable by default?

Options: never (A, today); only when the law declares `contestable` (B); always, with a constitution able to exempt laws (C).

**Recommendation: B.** It lets agents build judicial review, or not, and that is itself a research outcome.

*What would change my mind:* if no agent-written law ever declares it, run C as an arm to see whether courts check legislation when
given the chance.

### Decision 12. Does the per-law mode exist at all, or only world dials?

Options:

- **A.** Per-law mode (H1) plus world dials (H2).
- **B.** World dials only: all laws are auto inside what physics allows.
- **C.** Per-law mode only.

**Recommendation: A.** C collapses (§1.2). B misses the interesting fact that, under `state_only`, a polity *chooses* between a court
and a reporting law for private conduct.

---

## 6. What would make this fail

1. **Dead letter.** Agents rarely accuse, contest or rule, so every non-auto law is inert and the world reads as lawless. E0 measures
   this before any building. If accusations are rare today, add a cheap nudge before concluding anything: a case queue in judges'
   turn context, and a share of the fine to the accuser.
2. **The compliance prior swamps everything.** Agents obey stated rules regardless of enforcement, so all arms look the same. The
   honour-system arm detects this. If it happens, the interesting experiments use goals that *reward* violation (Saboteur- and
   Havoc-type goals), and the question becomes "under which enforcement does a motivated violator get caught", not "do agents comply".
3. **Capture as the only equilibrium.** Courts become coalition weapons in every run. That is a result, but it ends research on the
   downstream mechanics. A judge-selection rule (lottery, terms) as a treatment tests whether it can be fixed.
4. **Measurement debt.** Shipping H6 before E6 and E9 produces runs whose compliance cannot be scored. Order matters: shadow
   measurement first.
5. **Latency in short runs.** Twenty-round pilots with 1-5 rounds of enforcement delay show "courts don't deter" as an artefact. The
   mechanical court controls for this. Run long enough.
6. **Prompt growth.** Cases, precedents and held sanctions all need context. Without a fixed-budget legal digest per agent (review 10
   §7), costs and confusion grow. Budget it in the Section system (`fit()` with priorities).
7. **Determinism bugs.** A detection draw from a shared stream, or a shadow run that leaks state, breaks replay silently. Acceptance
   tests: replay byte-identical with detection < 1; a shadow run with a deliberately state-mutating hook leaves the snapshot unchanged.
8. **Single-model jurisprudence.** If all judges are Opus, "drift" is noise. Use a model mix for judges in a treatment, and keep the
   panel on a different model than the agents where possible.

---

## 7. The smallest experiment that tells us whether this is worth it

**Before any code: E0.** Count accusations, rulings, dismissals and time to ruling in existing runs. This is free. If judges
already rule on most filed cases, the plan holds. If cases mostly expire, fix attention first.

**Minimal build:** E1 + E2 (inside W6b) + E3 + E4's mechanical court + E5's detection filter + E6. E7, E8 and E9 are not needed, and
neither is any new law-language feature beyond the `enforcement` constant.

**World.** One preset: society-like with jurisdictions off, `law.v2: true`, about 12-16 agents (smaller than base, to control cost),
40 rounds, and `roles` on so the Spy exists as a witness. A **fixed law set**, written once in three modes, in force from round 0 and
amendable as usual:

- a harvest quota (private: harvest);
- a theft or attack prohibition with compensation (private: attack);
- a transfer tax (private: move);
- a registry rule (state: grant of a harvest licence).

At least two agents get goals that reward breaking one of these laws, so violation has a motive.

**Arms** (3 replicates each, with the same seeds across arms where possible):

| Arm | gates | detection (private) | enforcement mode | court |
|---|---|---|---|---|
| 0 Control | all | 1.0 | auto | — |
| 1 Honour system | state_only | 0 | report | — |
| 2 Mechanical court | state_only | 1.0 | court | mechanical, ruling after 1 round |
| 3 Agent court | state_only | 1.0 | court | agents |
| 4 Agent court, imperfect detection | state_only | 0.5 (+ reports) | court | agents |

**Pre-registered measures.** Shadow violation rate per law. Enforcement rate and false conviction rate. The equality gap across
coalitions. Time to ruling and backlog. Contests and laws amended or repealed. New enforcement-related laws written by agents (offices,
standing rules). Inequality (Gini of holdings). Model cost per round.

**Contrasts:**

- 1 vs 0: the compliance prior.
- 2 vs 0: delay and capacity.
- 3 vs 2: **judgment**, which is the question.
- 4 vs 3: detection.

**Go criteria** (all three):

1. Arm 1's shadow violation rate is clearly above 0 for motivated agents. Otherwise enforcement has nothing to do.
2. Arm 3 differs from arm 2 on at least one pre-registered measure beyond replicate spread.
3. Arm 3 resolves at least half of its cases before the deadline, at less than 30% extra cost per round over arm 0.

If 1 fails, study compliance, not enforcement. If 2 fails, judgment adds nothing beyond delay: keep auto plus detection (H2) and stop.
If 3 fails, fix judicial attention before anything else.

**Cost** (with my per-turn assumption; replace it with measured usage). Arms are 15 runs × 40 rounds × about 14 agents ≈ 8,400 main
turns ≈ $1,000 on all-Opus. With the honour and control arms on a Sonnet-heavy mix, roughly $600-700.

---

## Sources cited

From general knowledge; not re-verified online in this session.

- Becker, G. S. (1968). Crime and Punishment: An Economic Approach. *Journal of Political Economy* 76(2).
- Becker, G. S. and Stigler, G. J. (1974). Law Enforcement, Malfeasance, and Compensation of Enforcers. *Journal of Legal Studies* 3(1).
- Calabresi, G. and Melamed, A. D. (1972). Property Rules, Liability Rules, and Inalienability: One View of the Cathedral. *Harvard Law
  Review* 85.
- Fuller, L. L. (1964). *The Morality of Law*. Yale University Press.
- Grimmelmann, J. (2005). Regulation by Software. *Yale Law Journal* 114.
- Hart, H. L. A. (1961). *The Concept of Law*. Oxford.
- Holmes, O. W. (1897). The Path of the Law. *Harvard Law Review* 10.
- Kaplow, L. (1992). Rules versus Standards: An Economic Analysis. *Duke Law Journal* 42.
- Landes, W. M. and Posner, R. A. (1975). The Private Enforcement of Law. *Journal of Legal Studies* 4(1).
- Lessig, L. (1999). *Code and Other Laws of Cyberspace*. Basic Books.
- Merigoux, D., Chataing, N. and Protzenko, J. (2021). Catala: A Programming Language for the Law. *ICFP*.
- Milgrom, P., North, D. and Weingast, B. (1990). The Role of Institutions in the Revival of Trade: The Law Merchant, Private Judges,
  and the Champagne Fairs. *Economics and Politics* 2(1).
- Mnookin, R. and Kornhauser, L. (1979). Bargaining in the Shadow of the Law: The Case of Divorce. *Yale Law Journal* 88.
- OECD OPSI (2020). *Cracking the Code: Rulemaking for Humans and Machines*.
- Ostrom, E. (1990). *Governing the Commons*. Cambridge.
- Piatti, G. et al. (2024). Cooperate or Collapse: Emergence of Sustainable Cooperation in a Society of LLM Agents (GovSim). NeurIPS
  2024. *I am confident the paper exists; less sure of the exact claims as summarised in §2.3.*
- Polinsky, A. M. and Shavell, S. (2000). The Economic Theory of Public Enforcement of Law. *Journal of Economic Literature* 38(1).
- Priest, G. and Klein, B. (1984). The Selection of Disputes for Litigation. *Journal of Legal Studies* 13(1).
- Shavell, S. (1993). The Optimal Structure of Law Enforcement. *Journal of Law and Economics* 36(1).
- Stigler, G. J. (1970). The Optimum Enforcement of Laws. *Journal of Political Economy* 78(3).
- Tyler, T. R. (1990). *Why People Obey the Law*. Yale.
- Zheng, L. et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. NeurIPS 2023 Datasets and Benchmarks.
- Events: The DAO exploit and the Ethereum hard fork (2016). Kleros, a decentralised arbitration protocol, cited as a project rather
  than a specific paper.
