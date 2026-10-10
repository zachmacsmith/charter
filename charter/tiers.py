"""Review 12 WP0 (W8a): the tier classification as data (docs/review/12_hardcoded_inventory.md §1, §2; ARCHITECTURE D-25, D-30).

Two registries carry a `tier`:
  - primitives.Primitive.tier, for every primitive row (primitives.TIER_OF): P, E, X, L (routed: a law may already hook it) or
    L-route (a free act or a law's rule setter the kernel does not route yet, review 12 §2.14);
  - RULES below, one row per item of review 12's inventory (§2.1-2.13, 112 rows): where the rule is made today (file:function
    references, "module:qualname" relative to charter/, and spec keys), what it does today, its target tier and the law that would
    carry it. A row with two tiers is counted by the first tier listed, except that E->L counts as L (review 12 §2.15).

Tiers (review 12 §1):
  P        physics: no two real legal systems differ on it, or breaking it breaks conservation, causality, replay or determinism;
           laws cannot block it (blockable=False, world causes), they may react to its consequences
  E        epistemics: what an agent perceives by nature or what the world's technology allows; laws cannot make an agent un-know
           what it perceives, nor read beyond the technology
  X        experimental contract: exists for the researcher (measurement, scoring, the run's safety, comparability, treatment
           dials); invisible to law or entrenched
  L        law, already (wholly or partly) in law's hands: a routed primitive, or a rule laws already set
  L-route  law, but a hookability gap: a free agent choice the kernel does not route, so law cannot see it (fix: route it)
  L-rule   law, but a hard-coded social rule: the kernel imposes a gate, a default or a publication (fix: a default Act that
           reproduces today, review 12 §3)
Metadata only: nothing reads these at run time (tests/test_charter_tiers.py checks them)."""
from __future__ import annotations

from dataclasses import dataclass

TIERS = ("P", "E", "X", "L", "L-route", "L-rule")
PRIMITIVE_TIERS = ("P", "E", "X", "L", "L-route")          # a primitive is never an L-rule: rules are not changes


@dataclass(frozen=True)
class Rule:
    id: str                  # review 12's row id (B1, F1, G1, V1, C1, M1, D1, J1, N1, I1, K1, R1, K-1)
    rule: str                # the rule, as the review names it
    where: tuple             # "module:qualname" references (relative to charter/; module-level names count) where it is made
    tier: str                # TIERS: the target tier (review 12's first tier listed; L: already law, wholly or partly)
    today: str               # what the code does today
    target: str = ""         # the law version (the default Act or primitive), or why it stays
    spec: tuple = ()         # spec keys (schema.keys()) that set it today
    note: str = ""           # the review's tier text where it says more than the tier (alternatives, decisions)


R = Rule
RULES = (
    # ------------------------------------------------------------------ 2.1 Board (Decision 1; D-30: Board Charter, entrenched in presets)
    R("B1", "Veto power and holders", ("rights:ENTRENCHED", "rights:NEVER", "actions:_veto", "dispatch.changes.legal:do_veto",
                                        "powers:POWERS"), "L-rule", "only the board class vetoes; no law can touch it",
      "Board Charter (rank charter): veto stays a routed legal act; holders by right; board_veto entrenched while in force",
      note="L at charter rank (or X, D1)"),
    R("B2", "Veto window length", ("kernel:Kernel.pass_or_veto", "actions:_patch"), "L-rule", "spec constant",
      "Board Charter parameter WINDOW", spec=("veto_window",)),
    R("B3", "Scope (non-ordinary laws; founding polity only)", ("kernel:Kernel.pass_or_veto", "powers:_resolve",
                                                                  "jurisdictions:board_reviews"), "L-rule",
      "law cls != ordinary; spec jurisdictions.board_scope", "Board Charter SCOPE (classes, ranks, polities)",
      spec=("jurisdictions.board_scope",)),
    R("B4", "Size (3) and membership; class not law-writable", ("generator:generate", "kernel:Kernel.board"), "L-rule",
      "fixed at generation; no law adds or removes members", "Board Charter: seats as a right board_seat; appointment rule",
      note="L at charter rank (or X)"),
    R("B5", "Succession by naming", ("mortality:name_successor", "mortality:take_seat"), "L-rule",
      "a named living non-Board agent takes the seat (giving up every right except veto); else the seat stays empty",
      "route name_successor; Board Charter SUCCESSION (default: naming); set_succession_rule"),
    R("B6", "Veto majority", ("kernel:Kernel.process_veto_queue",), "L-rule", "len // 2 + 1 of held seats", "Board Charter QUORUM"),
    R("B7", "Board vote secrecy", ("dispatch.changes.legal:do_veto", "kernel:Kernel.process_veto_queue"), "L-rule", "spec dial",
      "Publication Act row veto_vote; the Board Charter may require secrecy", spec=("conditions.board_votes",)),
    R("B8", "Board immunities: no DM limit, no action limit, holds only veto, no harvest",
      ("dispatch.checks:check_set_dm_limit", "dispatch.checks:check_limit_actions", "dispatch.checks:check_grant_right",
       "rights:NEVER"), "X", "PhysicsError", "while the Board is a control arm; if it becomes law: the Board Charter's privileges"),
    R("B9", "Board vulnerable to attack", ("conflict:DEFAULTS",), "X", "spec dial", "treatment dial",
      spec=("conflict.board_vulnerable",)),
    # ------------------------------------------------------------------ 2.2 Fixer (Decision 2: stays X)
    R("F1", "Patch right, Fixer class only", ("actions:_patch", "rights:ENTRENCHED"), "X", "kernel",
      "code repair is maintenance of the instrument"),
    R("F2", "3 fixes per round", ("actions:_patch",), "X", "spec", "cost and safety", spec=("fixer_per_round",)),
    R("F3", "Law errors suspend the law and go to the Fixer queue", ("kernel:Kernel.law_error", "actions:_request_fix"), "X",
      "kernel", "keep; contract errors already skip the Fixer (P4.3)"),
    R("F4", "A non-ordinary patch waits in the Board's window", ("actions:_patch",), "X", "kernel",
      "Board Charter scope covers patches", note="X/L"),
    R("F5", "Fixer cannot die, be limited, or hold vote, propose, veto or harvest",
      ("roles:can_be_disabled", "dispatch.checks:check_limit_actions", "dispatch.checks:check_grant_right", "rights:NEVER"), "X",
      "kernel", "neutrality of maintenance"),
    R("F6", "Fixer honesty", (), "X", "spec", "treatment", spec=("conditions.fixer",)),
    # ------------------------------------------------------------------ 2.3 Legislation
    R("G1", "Law levels L0-L4", ("powers:LEVEL_PRESETS", "actions:_propose"), "X", "spec preset",
      "experimental ceiling on expressiveness", spec=("law_level",)),
    R("G2", "3-round dry run; a failing proposal is rejected", ("kernel:Kernel.dry_run", "actions:_propose", "actions:_amend"),
      "X", "kernel", "keeps broken code out of the world (D9)"),
    R("G3", "J0 proposals need the propose right", ("actions:_propose", "powers:POWERS"), "L-rule", "power propose_right (j0)",
      "Franchise Act: before_propose refuses without propose; residual: every member may propose (D10)"),
    R("G4", "Starting rights by class", ("generator:CLASS_RIGHTS", "regimes:apply_rights"), "L-rule", "drawn at generation",
      "Franchise Act on_enact grants", note="L (grants), X (classes)"),
    R("G5", "Who votes on a proposal", ("kernel:Kernel._decide", "jurisdictions:decide"), "L", "procedures (law)"),
    R("G6", "Tally rules", ("kernel:Kernel.tally",), "P", "kernel builtins plus W6c rule functions",
      "counting as cast is physics; the rule is chosen by law", note="P (counting) / L (choice, already law)"),
    R("G7", "Votes are public, with the choice", ("dispatch.changes.legal:do_cast_vote",), "L-rule", "vis public",
      "Publication Act row vote (secret-ballot regimes: parties plus a public tally)"),
    R("G8", "Proposals published with full code (and the dry-run diff)", ("dispatch.changes.legal:do_propose",), "L-rule",
      "public; the preview is a spec dial", "Publication Act row proposal", spec=("conditions.effect_preview",),
      note="L (publication), X (preview dial)"),
    R("G9", "No procedure for a class: the proposal fails", ("kernel:Kernel._decide",), "L", "kernel", "already the residual"),
    R("G10", "A new polity starts with a built-in members-vote procedure", ("jurisdictions:_procedure_spec", "jurisdictions:decide"),
      "L-rule", "kernel", "Founding Act: a seeded constitution for new polities"),
    R("G11", "Anyone reads any law's full code; laws() lists every active law", ("context:read_law", "kernel:Kernel.api_for"),
      "L-rule", "hard-coded", "Publication Act rows law_code and law_index (today: public)"),
    R("G12", "Entrenched rights veto, patch, archive; reserved names", ("rights:ENTRENCHED", "dispatch.checks:check_create_right"),
      "X", "kernel", "experimental contract"),
    R("G13", "Rank, conflict rule, amendment", ("dispatch.ranks:rank_of", "dispatch.ranks:conflict_rule", "amendment:law_api"),
      "L", "law (v2)"),
    R("G14", "Ballots close at round end; gates; stages", ("kernel:Kernel.close_ballots", "stages:begin"), "P",
      "kernel timing, law content", "time structure", note="P/L (content already law)"),
    # ------------------------------------------------------------------ 2.4 Publication and epistemics (§4)
    R("V1", "Kernel.log's vis=\"public\" default and the literal vis=\"public\" sites", ("kernel:Kernel.log",), "L-rule",
      "each call site decides publication", "§4: natural visibility at the call sites; the Publication Act maps type to audience",
      note="L (publication) over E (natural)"),
    R("V2", "channel_created, channel_member, channel_closed are public, with the members",
      ("actions:_create_channel", "actions:_add_member", "actions:_remove_member", "actions:_close_channel"), "L-rule", "public",
      "Publication Act rows (today: public); residual: members only"),
    R("V3", "Public board posts", ("actions:_post",), "E", "public", "posting is publishing"),
    R("V4", "Transfers to parties; the move record to the monitor", ("actions:_send", "dispatch.changes.economy:do_move"), "E",
      "parties", "natural"),
    R("V5", "DMs to parties; surveil reads unencrypted DMs", ("dispatch.changes.speech:do_dm", "kernel:Kernel.can_see"), "E",
      "parties plus a right", "natural; surveillance by grant (already law)", note="E + L (surveil)"),
    R("V6", "invoke logged public with arguments and result", ("actions:_invoke",), "L-rule", "public",
      "Publication Act row invoke"),
    R("V7", "Loans, payments, defaults public", ("credit:change_offer", "credit:change_default", "credit:settle"), "L-rule",
      "public", "Publication Act rows loan_*"),
    R("V8", "Contract creation and joining public", ("contracts:change_create", "contracts:change_join"), "L-rule", "public",
      "Publication Act rows contract_*"),
    R("V9", "Bequests and successor namings private unless public; set_succession_public",
      ("mortality:set_bequest", "mortality:name_successor"), "L", "mixed", "fold into the Publication Act",
      note="L (partly law already)"),
    R("V10", "Round record gazette (laws enacted, prices, camp stocks)", ("kernel:Kernel.round_summary", "media:compile_official"),
      "L-rule", "hard-coded (media2: publish_stat is law)", "Statistics section of the Publication Act (media.STATS keys)"),
    R("V11", "Deaths public; the attacker named per named", ("mortality:end",), "E", "public",
      "absence is observable; attribution is the attack's own physics"),
    R("V12", "World-event audiences", ("events:REGISTRY",), "E", "spec per type", "nature decides who notices",
      spec=("events.types",)),
    R("V13", "Rights and sanction events public", ("dispatch.changes.status:do_grant_right",
                                                   "dispatch.changes.status:do_suspend_right"), "L-rule", "public",
      "Publication Act rows rights, sanction"),
    R("V14", "Hidden-power use monitor-only unless disclose_capability_use", ("hidden:invoke",), "L", "law switch"),
    R("V15", "Project contributions public", (), "L-rule", "spec", "Publication Act row project_contribution",
      spec=("projects.public_contributions",)),
    R("V16", "Whether laws can read DM text", ("dispatch.checks:check_dm", "dispatch.hooks:hook_payload"), "E",
      "spec dial", "a world dial (technology)", spec=("conditions.law_reads_dms",)),
    R("V17", "Laws read every channel's owner and members", ("kernel:Kernel.api_for",), "L-rule", "unrestricted",
      "gate on a channels.registry dial or the Publication Act's register", note="E->L"),
    R("V18", "What new-style hooks may read of a DM or a post (D-29)", ("dispatch.hooks:hook_payload",), "E",
      "fixed (W7e/D-29): no DM text unless law_reads_dms and unencrypted, no private channel post text",
      "the world's technology bounds what hooks see"),
    R("V19", "Cases and rulings public and gazetted", ("actions:_accuse", "actions:_rule", "courts:change_open_case"), "L-rule",
      "public", "Publication Act rows accuse, respond, ruling"),
    R("V20", "Visibility of failed attacks", (), "E", "spec", "who notices", spec=("conflict.visibility",)),
    R("V21", "effect_preview, model_identity_visible, feed_mode", (), "X", "spec", "treatment dials",
      spec=("conditions.effect_preview", "conditions.model_identity_visible", "conditions.feed_mode")),
    # ------------------------------------------------------------------ 2.5 Channels and groups
    R("C1", "Creating a channel needs press", ("actions:_create_channel", "action_registry:REG"), "L-rule", "ActionError",
      "Association Act: before_found(kind=channel) refuses without press; residual: anyone"),
    R("C2", "Channel operations not routed", ("actions:_create_channel", "actions:_add_member", "actions:_remove_member",
                                              "actions:_close_channel"), "L",
      "W8b: routed (found, admit, expel, dissolve with kind channel; was: k.log directly, no hook could fire)",
      "route found/admit/expel/dissolve with kind=channel (WP1, done)", note="L-route until W8b"),
    R("C3", "Owner-only control of membership and closing", ("actions:_own_channel",), "L-rule", "kernel",
      "Association Act default"),
    R("C4", "Channel posts visible to members (or everyone if open)", ("kernel:Kernel.can_see",), "E", "kernel",
      "natural presence"),
    # ------------------------------------------------------------------ 2.6 Communications
    R("M1", "Default DM limit (dms_per_round plus per-agent jitter)", ("kernel:Kernel.dm_limit", "generator:generate"), "L-rule",
      "spec", "Communications Act LIMIT; the jitter stays drawn", spec=("dm_step.dms_per_round", "dm_step.capacity"),
      note="L (the limit), P (the jitter); dm_step.capacity natural: P (capacity = dms_per_round + jitter, under the X cap), "
           "law (the Act's LIMIT, set_dm_limit) only caps it, never raises it; the residual without law is the capacity, not M3's cap"),
    R("M2", "The dm_rules office held by Media at the start", (), "L-rule", "spec", "Communications Act on_enact grant",
      spec=("dm_step.controller",)),
    R("M3", "Hard cap of 10 DMs", ("kernel:Kernel.dm_cap",), "X", "spec", "model cost"),
    R("M4", "DMs and encryption exist", (), "P", "spec", "technology", spec=("channels.dm", "channels.encryption")),
    R("M5", "Encryption needs encrypt", ("actions:_dm_check",), "L", "right"),
    # ------------------------------------------------------------------ 2.7 Media
    R("D1", "press carried by the Media role", ("rights:REG", "roles:pass_on"), "L-rule", "role plus right",
      "Press Act grants press to role holders at enactment"),
    R("D2", "publish, write_digest, report need press; a story heads every feed", ("actions:_publish", "context:_priority"),
      "L-rule", "kernel", "Press Act before_post(kind in story/report); feed priority stays in the kernel"),
    R("D3", "Posting needs a licence from an outlet (media2)", ("media:check_post",), "L-rule", "spec", "Press Act; licence routed",
      spec=("media2.licences",)),
    R("D4", "One outlet per Media and press holder", ("media:refresh_outlets",), "L-rule", "spec", "Press Act",
      spec=("media2.press_outlets",)),
    R("D5", "Official outlet and its statistics", ("media:compile_official", "media:law_api"), "L", "law"),
    R("D6", "licence, set_price, library_doc, library_permit, set_capacity not routed",
      ("media:grant_licence", "media:set_subscription_fee", "scholars:_new_doc", "scholars:library_permit", "scholars:buy_memory"),
      "L", "W8b: routed (licence, set_price, library_doc, library_permit, set_capacity; was unhookable)", "route (WP1, done)",
      note="L-route until W8b"),
    # ------------------------------------------------------------------ 2.8 Courts
    R("J1", "3 rulings per judge per round", ("actions:_rule",), "L-rule", "constant (W7e: court rule rulings_per_round)",
      "Court Rules Act seeds 3"),
    R("J2", "v1: 3-round deadline; binary verdict; fixed penalty", ("kernel:Kernel._expire_cases", "actions:_rule"), "L-rule",
      "constants (v1)", "Court Rules Act for v1 worlds too, or v1 frozen", note="L (already law in v2: court_rules, remedies)"),
    R("J3", "No pardon or clemency", (), "L-rule", "missing", "pardon(case) law function plus routed rule with stage 3"),
    R("J4", "Evidence must have been visible to the citer", ("actions:_accuse", "actions:_cited"), "E", "kernel",
      "you can only cite what you perceived"),
    R("J5", "Judges need judge; scoped to the polity", ("actions:_rule", "jurisdictions:judges"), "L", "right"),
    # ------------------------------------------------------------------ 2.9 Membership and jurisdictions (Decision 5; D-26)
    R("N1", "Founding is hidden; invite, declare; declare cost and minimum members",
      ("jurisdictions:act_found", "jurisdictions:act_declare"), "L-rule",
      "spec; W8b routed found, invite, declare and set_charter (the hidden ones seen by no other polity's law)",
      "the parent polity's Nationality Act may hook declare (before_declare, routed by W8b); declare cost and minimum members",
      spec=("jurisdictions.declare_cost", "jurisdictions.declare_min_members"),
      note="L-route plus a world rule; W8b did the routing, the world rule remains"),
    R("N2", "Default admission rule (ballot, open or closed)", ("jurisdictions:change_join",), "L-rule", "spec",
      "Nationality Act ADMISSION", spec=("jurisdictions.admission",)),
    R("N3", "Exit always possible at round end; on_exit may tax or seize", ("jurisdictions:act_leave", "jurisdictions:change_leave"),
      "L-rule", "kernel guarantee", "Nationality Act EXIT (D-26: law, unbounded)", note="L or X (D5); D-26: law"),
    R("N4", "One declared jurisdiction per agent", ("jurisdictions:member_of",), "X", "kernel", "ontology"),
    R("N5", "Newborns join the parent's polity unless on_birth", ("jurisdictions:assign_newborn",), "L", "law hook"),
    R("N6", "Arrivals assigned to a polity", ("jurisdictions:assign_arrival",), "L-rule", "kernel", "Nationality Act ARRIVALS"),
    R("N7", "max_charter 5; contracts.max_founded, max_laws", (), "X", "spec", "budget",
      spec=("jurisdictions.max_charter", "contracts.max_founded", "contracts.max_laws")),
    R("N8", "Exit from associations always allowed, escrow kept", ("contracts:change_leave",), "X", "kernel guarantee",
      "exit as a safeguard", note="X/L (D5)"),
    R("N9", "Contract enforcement dial (escrow, escrow_court, word)", ("contracts:enforcement",), "E", "spec",
      "a world dial: physics sets what can be enforced", spec=("contracts.enforcement",), note="E/P"),
    # ------------------------------------------------------------------ 2.10 Mortality and inheritance
    R("I1", "Intestacy: unbequeathed goods go to the polity's reserve", ("mortality:_run_bequest", "jurisdictions:reserve_of"),
      "L-rule", "kernel", "Succession Act INTESTACY (today: reserve)"),
    R("I2", "Unbequeathed files are destroyed", ("mortality:_run_bequest",), "L-rule", "kernel", "Succession Act"),
    R("I3", "Rights, titles and offices lapse at death", ("mortality:_disable.lapse",), "L-rule", "kernel",
      "Succession Act OFFICES (today: lapse)"),
    R("I4", "Secret roles pass at random", ("roles:pass_on",), "X", "kernel", "instrument"),
    R("I5", "Death by old age or accident", ("life:end_of_round", "conflict:after_harvest"), "P", "world"),
    R("I6", "set_will, name_successor not routed", ("mortality:set_bequest", "mortality:name_successor"), "L",
      "W8b: routed (was unhookable)", "route (WP1, done)", note="L-route until W8b"),
    R("I7", "Dead man's switch causes", ("mortality:SWITCH_CAUSES",), "L-rule", "kernel", "Succession Act parameter"),
    # ------------------------------------------------------------------ 2.11 Economy
    R("K1", "Harvesting needs harvest:<camp>; exclusion enforced perfectly", ("actions:_harvest", "action_registry:REG"),
      "L-rule", "kernel gate", "Land Registry Act: before_harvest refuses without the right (D8; D-30: seeded everywhere)"),
    R("K2", "2 harvests per right per round", (), "P", "spec", "labour per round", spec=("harvests_per_right",)),
    R("K3", "Board and Fixer cannot harvest", ("action_registry:REG",), "X", "kernel (notcls)"),
    R("K4", "Loans exist only after enable_loans; default consequences", ("kernel:Kernel.loans_enabled", "credit:settle"), "L",
      "law switch plus spec", "the Credit Act carries the consequence defaults", spec=("credit",),
      note="L (switch, already law), L (consequence defaults)"),
    R("K5", "credit.max_rate 1.0", (), "X", "spec", "numerical guard", spec=("credit.max_rate",)),
    R("K6", "Only laws create currencies (associations: shares)", ("kernel:Kernel.api_for",), "L", "law-only"),
    R("K7", "J0's reserve owner key; conservation", ("accounts:J0_KEY", "accounts:SOURCES_SINKS"), "P", "kernel",
      "accounting identity"),
    R("K8", "Tribute demands and raids", ("outside:demand_tribute",), "P", "world", "laws react (pay, levy, relieve)"),
    R("K9", "Random projects appear; road and discovery rights go to contributors (or all)", ("projects:open_project",), "P",
      "world plus spec", "project rights rule as a law parameter (set_project_rule)", note="P (opportunity) / L (who gets rights)"),
    R("K10", "Spoils of attack 50/50; grace and cooldown", ("conflict:DEFAULTS",), "P", "spec", note="P (spoils) / X (grace)"),
    R("K11", "Initial endowments", ("generator:generate",), "X", "spec", "initial condition", spec=("endowment_gini",)),
    # ------------------------------------------------------------------ 2.12 Roles, hidden powers, offices
    R("R1", "The Spy reads transcripts", ("roles:ROLES", "observer:render_transcripts"), "X", "kernel", "instrument"),
    R("R2", "Assassin role; hire_assassin not routed", ("conflict:act_contract",), "P", "unhookable",
      "route with HIDE on the hirer", note="P (capability) + L-route (concealed)"),
    R("R3", "maker and scholar role-bound (D-23)", ("rights:role_bound",), "P", "role",
      "a natural capability; licensing is L via after-hooks on begin_life"),
    R("R4", "Hidden powers held by chance; use_power not routed", ("hidden:invoke",), "E", "secret",
      "route with the actor concealed"),
    R("R5", "archive entrenched; archive split", ("rights:ENTRENCHED",), "X", "kernel", "the treatment",
      spec=("archive_split",)),
    R("R6", "invoke (offices) not routed; members only", ("actions:_invoke", "jurisdictions:check_invoke"), "L",
      "W8b: routed (before_invoke/after_invoke under law.v2; was unhookable); members only stays the polity's scope check",
      "route invoke (before_invoke/after_invoke; done)", note="L-route until W8b"),
    R("R7", "define_action needs L4", ("powers:LEVEL_PRESETS",), "X", "level"),
    # ------------------------------------------------------------------ 2.13 Kernel invariants (stay)
    R("K-1", "Conservation; goods are held only by accounts", ("accounts:add", "dispatch.changes.economy:do_move"), "P", "kernel"),
    R("K-2", "Laws never act for an agent", ("kernel:Kernel.api_for",), "P", "kernel"),
    R("K-3", "Gas, depth cap, halting, determinism, seeded streams", ("dispatch.base:GAS", "gas:Meter"), "P", "kernel"),
    R("K-4", "Rounds, phases, order of steps", ("features:PHASES",), "P", "kernel"),
    R("K-5", "Cause stack and the monitor record", ("kernel:Kernel.cause", "kernel:Kernel.log"), "E", "kernel",
      note="E/X (provenance)"),
    R("K-6", "Observer, scoring, goal secrecy, goal changes (set_goal)", ("observer:score", "scorer:score", "events:change_goal"),
      "X", "kernel"),
    R("K-7", "actions_per_turn plus jitter", (), "P", "spec", spec=("actions_per_turn", "actions_jitter")),
    R("K-8", "Classes", ("kernel:CLASSES",), "X", "kernel"),
)

RULE = {r.id: r for r in RULES}
