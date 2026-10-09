"""The power table (P4.2, docs/ARCHITECTURE.md §3.7 and §7.3; review 06 §9): what an account's laws and procedures may do, as data.

Every law belongs to an account (accounts.account_of: a jurisdiction id, "J0" when jurisdictions are off). Which kernel machinery
attaches to that account (the Board's veto window, the Fixer, law levels, the proposal dry run) and which law functions it may call
(LawFn.power in charter/lawapi.py) is decided here, by `has_power(k, account, power)`, instead of by `"jur" in k.w` / `legacy`
branches. P4.2 is behaviour-preserving: every polity's power set is exactly what the kernel and jurisdictions.py granted it before.

A power's `kinds` column maps an account kind to a value ("polity"; "association" since P4.3: every record in
k.w["contracts"]["assoc"]; "personal" is reserved):
    True / False    every account of that kind holds it / none does
    "j0"            only J0, the legacy polity whose state lives at the top level of k.w (k.w["reserve"], k.w["procedures"], the
                    camp dicts, top-level currencies): J0 with jurisdictions on (record["legacy"]), and the world itself with them
                    off. In a state-of-nature start there is no J0 and nobody holds it. NB: not the *founding* polity (k.w["jur"]
                    ["founding"]), which in a state of nature is the first jurisdiction declared and has no legacy storage.
    "board_scope"   the Board reviews this account's laws: jurisdictions off -> always; on -> spec jurisdictions.board_scope
                    ("founding": the account is k.w["jur"]["founding"]; "all"; "none"), exactly the old J.board_reviews.
    "spec"          the value is the world's spec setting (law_levels: k.inst["law_level"], a LEVEL_PRESETS name).
A record may carry `powers` overrides ({power: value}, absent today: no record has one, so state is unchanged); an override cannot
take an entrenched power away from its holder.

Branches that remain (not power questions; input for the J0-as-contract milestone, review 06 §9.3), see REMAINING below.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

LEVELS = ("L0", "L1", "L2", "L3", "L4")
# The law levels as presets of what a polity's laws may be (lawlang.LEVEL_CLASSES is the same table: tests check it). "classes": the
# law classes a proposal (or a founder's charter law) may have; "define_action": define_action is allowed (L4 only).
LEVEL_PRESETS = {
    "L0": {"classes": frozenset(), "define_action": False},
    "L1": {"classes": frozenset({"ordinary"}), "define_action": False},
    "L2": {"classes": frozenset({"ordinary", "structural"}), "define_action": False},
    "L3": {"classes": frozenset({"ordinary", "structural", "procedural"}), "define_action": False},
    "L4": {"classes": frozenset({"ordinary", "structural", "procedural"}), "define_action": True},
}


@dataclass(frozen=True)
class Power:
    name: str
    doc: str
    kinds: dict                     # account kind -> True | False | "j0" | "board_scope" | "spec" (see the module docstring)
    primitives: tuple = ()          # primitives it lets the account's laws apply to non-consenting members
    entrenched: bool = False        # a kernel invariant: no override removes it from its holder
    refusal: str = ""               # the LawError text when a law of an account without it calls one of its functions ({fn})
    consulted: tuple = ()           # where has_power is asked about it (file:function); () = attached by the table only, no branch
    lawfns: tuple = field(default=(), compare=False)   # law functions gated by it: lawapi.LAWFNS's `power` column (filled below)

    def value(self, kind: str):
        return self.kinds.get(kind, False)


def _powers(*ps: Power) -> dict:
    out = {}
    for p in ps:
        assert p.name not in out, p.name
        assert all(v in (True, False, "j0", "board_scope", "spec") for v in p.kinds.values()), p
        out[p.name] = p
    return out


POWERS = _powers(
    Power("board_veto", "The Board's veto window: the account's passed non-ordinary laws, and Fixer patches making one of its laws "
          "non-ordinary, wait veto_window rounds for a Board majority veto before they take effect.",
          {"polity": "board_scope", "association": False}, entrenched=True,
          consulted=("kernel.py:Kernel.pass_or_veto", "jurisdictions.py:board_reviews", "actions.py:_patch")),
    Power("fixer_patch", "The Fixer may patch the account's laws and receives their runtime errors (law_error -> fixer_queue). "
          "The Fixer serves every polity today.", {"polity": True, "association": False}, entrenched=True),
    Power("law_levels", "The law level preset (LEVEL_PRESETS) the account's proposals and charter laws are checked against: which "
          "classes are allowed and whether define_action is.", {"polity": "spec", "association": False},
          consulted=("actions.py:_propose", "jurisdictions.py:propose", "jurisdictions.py:_charter_laws")),
    Power("dry_run", "Every proposal runs a 3-round dry run (Kernel.dry_run) before it is decided; a failing law is rejected.",
          {"polity": True, "association": False}, consulted=("actions.py:_propose", "jurisdictions.py:propose")),
    Power("propose_right", "Proposing a law of this account needs the kernel 'propose' right (elsewhere membership suffices).",
          {"polity": "j0", "association": False}, consulted=("actions.py:_propose", "jurisdictions.py:propose")),
    Power("kernel_rights", "The account's laws may create kernel rights and grant, revoke and suspend them for its members.",
          {"polity": True, "association": False}, primitives=("grant_right", "revoke_right", "suspend_right"),
          refusal="{fn} needs the kernel_rights power, which this jurisdiction does not hold", consulted=("jurisdictions.py:scope_api",)),
    Power("compel_members", "Compulsion: the account's laws bind non-consenting members (fines, action limits, DM limits, censure, "
          "guard obligations, compelled subscriptions).", {"polity": True, "association": False},
          primitives=("move", "limit_actions", "set_dm_limit", "guard_bind", "subscribe"),
          refusal="{fn} needs the compel_members power, which this jurisdiction does not hold", consulted=("jurisdictions.py:scope_api",)),
    Power("lawful_force", "The account's laws may order lawful attacks paid from its armory (lawful_attack).", {"polity": True, "association": False},
          primitives=("attack",), refusal="{fn} needs the lawful_force power, which this jurisdiction does not hold",
          consulted=("jurisdictions.py:scope_api",)),
    Power("unlimited_seizure", "The account's laws may move or burn any amount a bound member holds (also from leavers, on_exit), "
          "not capped by an escrow.", {"polity": True, "association": False}, primitives=("move", "burn"),
          refusal="{fn} needs the unlimited_seizure power, which this jurisdiction does not hold", consulted=("jurisdictions.py:scope_api",)),
    Power("camp_rules", "The account's laws may set camp quotas, harvest limits, fees and lease rules (for its own members).",
          {"polity": True, "association": False}, primitives=("set_camp_rule", "set_lease_rules"),
          refusal="{fn} needs the camp_rules power, which this jurisdiction does not hold", consulted=("jurisdictions.py:scope_api",)),
    Power("legacy_reserve", "Loans, par coins, projects, tribute and the powers-disclosure switch run on J0's reserve: their law "
          "functions work only in J0.", {"polity": "j0", "association": False},
          refusal="{fn} works only in the founding jurisdiction J0 (it uses J0's reserve)", consulted=("jurisdictions.py:scope_api",)),
    # P4.3: the association column (review 06 §3, ARCHITECTURE §7.2). An association (a contract, charter/contracts.py) holds none of
    # the powers above: no Board, no Fixer (its law errors suspend the law and tell its members), no levels (its code is rank bylaw,
    # capped by this table and lawapi's `contract` column instead), no dry run, no compulsion, no lawful force, no kernel rights, no
    # camp rules, no seizure beyond escrow. What it may do positively is below and in the `contract` column (allow | escrow | deny).
    Power("take_deposits", "The account's laws may take what its members deposited in its escrow or pre-authorised as allowances "
          "(pull, forfeit, refund). Polities hold it vacuously: they keep no escrows or allowances (only an association's law can "
          "call these functions).", {"polity": True, "association": True},
          refusal="{fn} needs the take_deposits power, which this account does not hold", consulted=("contracts.py:law_api",)),
    Power("hook_members", "The account's laws' hooks see their members' changes (before_/after_ hooks and the legacy agent hooks "
          "on_harvest, on_transfer, on_post, on_dm), and their charges go to its treasury.", {"polity": True, "association": True},
          consulted=("contracts.py:sees",)),
    Power("hook_legal_acts", "The account's laws may hook legal acts (proposals, ballots, enactments, rulings) of the polities its "
          "members belong to. An association hooks only its own legal acts and its members' non-legal changes (D-24).",
          {"polity": True, "association": False}, consulted=("contracts.py:sees",)),
)
J0_ONLY = tuple(n for n, p in POWERS.items() if p.value("polity") == "j0")    # legacy_reserve, propose_right




def _with_lawfns(powers: dict) -> dict:
    """Each power's `lawfns`, from lawapi's `power` column (the table names the power; this is the reverse index)."""
    from charter import lawapi as LA
    return {n: replace(p, lawfns=tuple(f.name for f in LA.LAWFNS.values() if f.power == n)) for n, p in powers.items()}


POWERS = _with_lawfns(POWERS)


# ---------------------------------------------------------------------- lookups
def _on(k) -> bool:
    return "jur" in k.w                                                  # jurisdictions.install ran (it adds "jurisdictions" and "jur")


def _record(k, account):
    """The account's record: an association's (k.w["contracts"]["assoc"], P4.3); else its polity record: jurisdictions off -> J0
    is the world itself (a virtual legacy record); on -> its record or None."""
    from charter import jurisdictions as J
    assoc = J.association(k, account)
    if assoc is not None:
        return assoc
    if not _on(k):
        return {"id": "J0", "kind": "polity", "legacy": True} if account == "J0" else None
    return J.jurs(k).get(account)


def _resolve(k, account, rec, value):
    if value is True or value is False:
        return value
    if value == "j0":
        return bool(rec and rec.get("legacy"))
    if value == "board_scope":
        if not _on(k):
            return True
        from charter import jurisdictions as J
        scope = J.cfg(k)["board_scope"]
        if scope == "all":
            return True
        if scope == "none":
            return False
        return account is not None and account == k.w["jur"]["founding"]
    if value == "spec":
        return k.inst["law_level"]
    raise ValueError(value)


def has_power(k, account, power: str):
    """Does the account hold the power? True/False, or the setting's value for a "spec" power (law_levels: a LEVEL_PRESETS name).
    An unknown power is a KeyError."""
    p = POWERS[power]
    rec = _record(k, account)
    kind = (rec or {}).get("kind", "polity")
    got = _resolve(k, account, rec, p.value(kind))
    over = (rec or {}).get("powers") or {}
    if power in over and not (p.entrenched and got and not over[power]):
        got = _resolve(k, account, rec, over[power])
    return got


def power_set(k, account) -> dict:
    """The account's whole power set: power -> has_power."""
    return {n: has_power(k, account, n) for n in POWERS}


def law_level(k, account) -> str:
    """The law level preset an account's laws are checked at."""
    return has_power(k, account, "law_levels") or "L0"


def level_allows(k, account, cls: str) -> bool:
    return cls in LEVEL_PRESETS[law_level(k, account)]["classes"]


def level_allows_define_action(k, account) -> bool:
    return LEVEL_PRESETS[law_level(k, account)]["define_action"]


def refusal(power: str, fn: str) -> str:
    return POWERS[power].refusal.format(fn=fn)


# ---------------------------------------------------------------------- what is still a branch (review 06 §9.3 input)
# Jurisdiction and J0 branches P4.2 left in place, and why: none of them is a question of what an account may do; they are where
# J0's state lives, how a hidden jurisdiction behaves, or code outside this package's files.
REMAINING = {
    "kernel.py:Kernel.passed `\"jur\" in self.w`": "a hidden jurisdiction's passed law becomes dormant (J.passed); a lifecycle "
        "status, not a power. The Board/enact decision itself is one implementation, Kernel.pass_or_veto.",
    "kernel.py:Kernel.decide/hooks/log `\"jur\" in self.w`": "procedure lookup, hook routing by membership and hidden-event "
        "visibility: the account path (§9.3 step 4), out of P4.2's files.",
    "kernel.py:Kernel.api_for define_action L4 check": "the law-call-time check of the level preset; outside P4.2's kernel region "
        "(passed, veto queue). Same LEVEL_PRESETS semantics; route through level_allows_define_action with step 4.",
    "jurisdictions.py:scope_api `if not legacy` (set_procedure, set_quota/set_harvest_limit/set_fee, gazette)": "storage: J0's "
        "procedures and camp rules live at the top level of k.w, a declared jurisdiction's in its record (§9.3 step 5).",
    "jurisdictions.py:scope_api fine / set_dm_limit / mint `legacy`": "storage: J0's fines go to k.w['reserve'] through the kernel "
        "fine, a declared jurisdiction's to reserve:<jid>; J0's set_dm_limit(n) sets the world default (step 5).",
    "jurisdictions.py:scope_api `if not enabled(k): return api`": "with jurisdictions off the API is unscoped; J0 holds every power "
        "it uses, so gating would be a no-op (step 3 installs J0 in every world).",
    "jurisdictions.py reserve_key/pool/procedures_of/procedure_key/camp_rules/act_fund `legacy`": "storage of J0's reserve, "
        "procedures and camp rules (step 5); procedure_key's BUILTIN members' vote for a new polity is a default, not a power.",
    "jurisdictions.py:propose `where` text, J.passed hidden->dormant, intercept_enact void/dormant": "message text and lifecycle "
        "status (hidden, void in a state of nature).",
    "actions.py:_propose `if J.enabled(k): return J.propose(...)`": "two copies of proposing (§9.3 step 4); both consult the same "
        "powers (law_levels, dry_run, propose_right) now.",
    "accounts.py binds/treasury_of/keys `enabled`/`legacy`": "membership and storage, P4.1's.",
}
