"""Law-API metadata: which parameters of a law function name agents, and how jurisdictions scope the call.

Behaviour stays in `Kernel.api_for` and the module `law_api(k, lid)` closures; this table only describes them. Jurisdiction scoping
(`jurisdictions.AGENT_ARGS`, `REFUSED`, `LEGACY_ONLY`) is generated from it, and tests/test_charter_jurisdictions.py checks that every
law function with a parameter that can name an agent (see AGENTISH) is declared here, with positions matching its real signature.

scope:
  "bound"   generic: the call silently does nothing (returns `refused`, logs a monitor-only jur_out_of_scope) unless the law binds
            every agent passed in `agents`. Used to build jurisdictions.AGENT_ARGS.
  "custom"  scope_api handles it by hand (owners that may be a reserve, per-agent defaults, events' authors, member electorates).
  "read"    a read: scope_api filters what it returns, or it is harmless outside the jurisdiction.
  "none"    deliberately not scoped; `why` says why.
"""
from __future__ import annotations

from dataclasses import dataclass

# Parameter names that can name an agent in a law function's signature. A law function with one of these must be declared below.
AGENTISH = {"a", "aid", "agent", "guard", "borrower", "attacker", "target", "src", "dst", "to", "frm", "owner", "entity", "members",
            "electorate", "who"}


@dataclass(frozen=True)
class LawFn:
    name: str
    agents: tuple = ()          # ((position, parameter name), ...) of the parameters that name agents
    scope: str = "bound"        # bound | custom | read | none (see the module docstring)
    refused: object = None      # what an out-of-scope call returns
    legacy_only: bool = False   # works only in J0 (uses J0's reserve): a LawError in any other jurisdiction
    why: str = ""               # for scope "none", or parameters in AGENTISH that are not agents


def _fns(*fns: LawFn) -> dict:
    out = {}
    for f in fns:
        assert f.name not in out, f.name
        assert f.scope in ("bound", "custom", "read", "none"), f
        out[f.name] = f
    return out


LAWFNS = _fns(
    # ---- kernel: rights, sanctions, names (kernel.Kernel.api_for)
    LawFn("grant", ((0, "aid"),), refused=False),
    LawFn("revoke", ((0, "aid"),), refused=False),
    LawFn("fine", ((0, "aid"),), scope="custom", refused=0.0),          # also pays into this jurisdiction's reserve
    LawFn("suspend", ((0, "aid"),), refused=False),
    LawFn("limit_actions", ((0, "aid"),), refused=False),
    LawFn("censure", ((0, "aid"),), refused=None),
    LawFn("title", ((0, "aid"),), refused=None),
    LawFn("move", ((0, "src"), (1, "dst")), scope="custom", refused=False),     # either side may be a reserve
    LawFn("mint", ((2, "to"),), scope="custom", refused=None),
    LawFn("burn", ((2, "frm"),), scope="custom", refused=False),
    LawFn("set_dm_limit", ((1, "agent"),), scope="custom", refused=False),       # None: every member
    LawFn("hide_post", (), scope="custom", refused=False),                       # scoped by the post's author
    LawFn("open_ballot", ((1, "electorate"),), scope="custom", why="the electorate is filtered to members"),
    LawFn("notify", ((0, "a"),), scope="none", why="a message, binds nobody"),
    LawFn("rename", ((0, "entity"),), scope="none", why="a display name, binds nobody"),
    LawFn("name", ((0, "entity"),), scope="read"),
    LawFn("repeal", (), scope="custom", why="target is a law; only this jurisdiction's laws"),
    LawFn("balance", ((0, "owner"),), scope="read"),
    LawFn("has", ((0, "aid"),), scope="read"),
    LawFn("rights_of", ((0, "aid"),), scope="read"),
    LawFn("class_of", ((0, "a"),), scope="read"),
    LawFn("holdings_value", ((0, "aid"),), scope="read"),
    LawFn("dm_limit", ((0, "aid"),), scope="read"),
    # ---- hidden powers (hidden.py)
    LawFn("revoke_capability", ((0, "agent"),), refused=0),
    LawFn("disclose_capability_use", legacy_only=True),
    # ---- credit (credit.py)
    LawFn("credit_record", ((0, "a"),), scope="read"),
    LawFn("lend_from_reserve", ((0, "borrower"),), refused=None, legacy_only=True),
    LawFn("enable_loans", legacy_only=True),
    LawFn("forgive_loan", legacy_only=True),
    LawFn("set_par", legacy_only=True),
    LawFn("suspend_redemption", legacy_only=True),
    LawFn("set_interest_cap", legacy_only=True),
    LawFn("set_default_consequence", legacy_only=True),
    LawFn("restructure_loan", legacy_only=True),
    LawFn("buy_loan", legacy_only=True),
    # ---- projects and tribute (projects.py, outside.py)
    LawFn("start_project", legacy_only=True),
    LawFn("contribute_project", legacy_only=True),
    LawFn("set_refund", legacy_only=True),
    LawFn("pay_tribute", legacy_only=True),
    # ---- conflict (conflict.py)
    LawFn("oblige_guard", ((0, "guard"), (1, "agent")), refused=False),   # neither the guard nor the guarded may be outsiders
    LawFn("weapons_of", ((0, "agent"),), scope="read"),
    LawFn("defense_of", ((0, "agent"),), scope="read"),
    # ---- jurisdictions (jurisdictions.py)
    LawFn("admit", ((0, "agent"),), scope="none", why="admits a non-member by design"),
    LawFn("expel", ((0, "agent"),), scope="none", why="checks membership itself"),
    LawFn("lawful_attack", ((0, "attacker"), (1, "target")), scope="none",
          why="checks the attacker is a member itself; the target can be anyone"),
    # ---- media2 (media.py)
    LawFn("compel_subscription", ((0, "agent"),), refused=False, why="target is an outlet"),
    LawFn("set_official_editor", ((0, "agent"),), scope="none", why="appoints the editor of this jurisdiction's own outlet"),
    LawFn("suspend_outlet", (), scope="none", why="target is an outlet"),
    LawFn("official_stream", ((0, "members"),), scope="none", why="names, classes or roles whose posts are streamed"),
    # ---- life (life.py)
    LawFn("children_of", ((0, "agent"),), scope="read"),
    LawFn("lifespan_left", ((0, "agent"),), scope="read"),
)

AGENT_ARGS = {f.name: f.agents for f in LAWFNS.values() if f.scope == "bound" and f.agents}
REFUSED = {f.name: f.refused for f in LAWFNS.values() if f.name in AGENT_ARGS or f.scope == "custom"}
LEGACY_ONLY = {f.name for f in LAWFNS.values() if f.legacy_only}
