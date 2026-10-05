"""Jurisdictions and the state of nature (spec key `jurisdictions`, off by default).

Laws bind only the members of the jurisdiction that passed them. With the module off, everyone is in J0, `binds` is always True
and nothing here runs: the kernel's legacy path is untouched (golden tests). With it on:

Membership
  An agent belongs to at most one *declared* jurisdiction (k.w["jur"]["member"][aid] = jid or None) and to any number of *hidden*
  ones. A law's jurisdiction is the one it was passed in (law["jurisdiction"], "J0" when absent: the constitution, regime statutes,
  start_laws). `binds(k, law, aid)` is True only when the law's jurisdiction is declared and the agent is a member of it. An agent
  outside every jurisdiction is bound by no law and protected by none.

Where the law reaches (enforced in the law API, `scope_api`)
  Functions that act on an agent (grant, revoke, fine, suspend, limit_actions, censure, title, move, mint to, burn from,
  revoke_capability, set_dm_limit for one agent, hide_post of a member's post) silently do nothing for an agent the law does not
  bind (a monitor-only `jur_out_of_scope` event records the attempt). Hooks that concern one agent (on_harvest and on_transfer
  deductions, on_post, on_dm) run only for laws that bind that agent; on_vote and on_ruling only for the ballot's / case's
  jurisdiction. Reads (agents, holders, laws, currencies, reserve, balance("reserve")) see only the law's own jurisdiction.

Separate institutions (state under k.w["jurisdictions"][jid])
  {"id", "name", "status": hidden|declared|dissolved, "founder", "founded_round", "declared_round", "declare_pending",
   "hidden_members", "dormant": [laws passed in secret], "procedures", "procedure_history", "reserve", "camp_rules", "legacy"}
  J0 is "legacy": its procedures, reserve, currencies and camp rules stay where they always were (k.w["procedures"],
  k.w["reserve"], top-level currencies, the camp dicts), so existing code and the legacy path work unchanged. Any other
  jurisdiction keeps its own procedures (a new one starts with a built-in rule: its members vote, majority of those voting),
  reserve (owner key "reserve:<jid>" in moves), currencies (tagged currency["jurisdiction"], backed by its reserve), judges
  (judge holders who are members), offices (define_action rights; only members can invoke them), ballots (electorates filtered
  to members) and camp rules (quota, harvest limit, fee for its own members only). Loans, par coins, projects, tribute and the
  powers-disclosure switch run on the legacy reserve, so their law functions work only in J0 (a LawError elsewhere).
  The Fixer serves every jurisdiction. The Board reviews the founding jurisdiction's laws only (`board_scope: founding`; also
  `all` or `none`); in a state-of-nature start the first jurisdiction declared is the founding one.

Joining and leaving: actions found, invite, join, leave, declare (see ACTION_DOC). Joining a declared jurisdiction runs its laws'
  on_admission(agent) hooks (any False refuses, any True admits); with no answer the default `admission` rule applies (ballot: the
  members vote, majority of those voting, closes at the end of the round; open; closed). Leaving takes effect at the end of the
  round after the jurisdiction's on_exit(agent) hooks run (laws can tax or seize). Its police can still attack leavers.
Secret founding: found(name) makes a hidden jurisdiction only its invited members see (events about it are shown only to them);
  laws passed there are "dormant" (no effect). declare() makes it public at the end of the round: its members leave their old
  jurisdiction (whose on_exit runs) and its dormant laws are enacted in order.
Lawful force: law API lawful_attack(attacker, target, units) -> conflict.attack(..., lawful=True, armory=jid), paid from the
  jurisdiction's armory (weapons in reserve_of(jid)); the attacker must be a member; the target can be anyone.
Birth: assign_newborn(k, child, parent) puts a child in its parent's jurisdiction unless an on_birth(child, parent) hook of that
  jurisdiction returns another declared jurisdiction id (or False: none).
State of nature (`start: nature`, or regime state_of_nature): no jurisdiction exists; the constitution, regime statutes and
  start_laws are void (status "void", never in force). The only way out is to found and declare.

Scope confusion (scorer metrics, `metrics`): counts of agents' messages and stated reasoning that cite (by id or title) an enacted
  law of a jurisdiction they are not a member of, in a sentence with an obligation word (must, owe, tax, fee, comply, ...); transfers
  made in a round in which the payer did so; and actions refused because the law cited does not reach them (accuse under a law that
  does not bind the accused, invoking another jurisdiction's office, proposing in a jurisdiction one is not in).
"""
from __future__ import annotations

import json
import random
import re

from charter import lawlang as L

KEY = "jurisdictions"
DEFAULTS = {"enabled": False, "start": "j0", "board_scope": "founding", "admission": "ballot", "j0_name": "the Commonwealth",
            "scripted_founder": None}
ACTIONS = ("found", "invite", "join", "leave", "declare")
ACTION_DOC = {
    "found": 'found {"name": "..."}: secretly found a new jurisdiction; only members you invite will know it exists. Laws passed there have no effect until it is declared',
    "invite": 'invite {"jurisdiction": "J2", "agent": "Name"}: offer an agent a place in a hidden jurisdiction you belong to (they are told it exists; nobody else is). They become a member only if they pledge (join)',
    "join": 'join {"jurisdiction": "J1"}: a declared jurisdiction: ask to move there publicly; its admission law decides (by default its members vote this round) and you leave your old one at the end of the round. A hidden one you were invited to: pledge to it; you become a secret member, can see and vote on its draft laws, and move into it when it is declared',
    "leave": 'leave {"jurisdiction": null}: leave your declared jurisdiction at the end of the round (its laws may tax or seize from you as you go), or a hidden one at once',
    "declare": 'declare {"jurisdiction": "J2"}: make a hidden jurisdiction public (its founder, or any member once the founder is gone): at the end of the round its laws take effect and its members leave their old jurisdiction',
}
AGENT_HOOKS = {"on_harvest": 0, "on_transfer": 0, "on_post": 0, "on_dm": 0}        # hook -> index of the agent it concerns
OWN_HOOKS = ("on_exit", "on_admission", "on_birth")                                 # run only for one jurisdiction's laws
LEGACY_ONLY = {"enable_loans", "forgive_loan", "set_par", "suspend_redemption", "set_interest_cap", "set_default_consequence",
               "restructure_loan", "lend_from_reserve", "buy_loan", "start_project", "contribute_project", "set_refund",
               "pay_tribute", "disclose_capability_use"}
AGENT_ARGS = {"grant": ((0, "aid"),), "revoke": ((0, "aid"),), "fine": ((0, "aid"),), "suspend": ((0, "aid"),),
              "limit_actions": ((0, "aid"),), "censure": ((0, "aid"),), "title": ((0, "aid"),), "revoke_capability": ((0, "agent"),)}
REFUSED = {"grant": False, "revoke": False, "fine": 0.0, "suspend": False, "limit_actions": False, "censure": None, "title": None,
           "revoke_capability": 0, "move": False, "mint": None, "burn": False, "set_dm_limit": False, "hide_post": False}
OBLIGATION = re.compile(r"\b(must|required|requires|owe|owed|owes|obliged|obligated|bound|binding|comply|complying|obey|tax|taxes|"
                        r"taxed|fee|fees|levy|fine|fined|penalt\w*|liable|due|mandatory|illegal|forbidden|prohibited)\b", re.I)


# ---------------------------------------------------------------------- config and basics
def cfg_of(spec: dict) -> dict:
    return {**DEFAULTS, **((spec or {}).get(KEY) or {})}


def enabled_spec(spec: dict) -> bool:
    return bool(((spec or {}).get(KEY) or {}).get("enabled"))


def enabled(k) -> bool:
    return "jur" in k.w


def cfg(k) -> dict:
    return cfg_of(k.spec)


def jurs(k) -> dict:
    return k.w["jurisdictions"]


def install(k) -> None:
    """Called at the end of Kernel.__init__. Off: nothing (the world is unchanged)."""
    if not enabled_spec(k.spec):
        return
    c = cfg(k)
    nature = c["start"] == "nature"
    k.w["jurisdictions"] = {}
    k.w["jur"] = {"member": {}, "seq": 1, "founding": None if nature else "J0", "start": "nature" if nature else "j0",
                  "pending": {"leave": {}, "join": {}}, "admission": {}}
    if not nature:
        k.w["jurisdictions"]["J0"] = _new_j("J0", c["j0_name"], "declared", None, 0, legacy=True)
        k.w["jurisdictions"]["J0"]["declared_round"] = 0
    for aid in k.w["agents"]:
        k.w["jur"]["member"][aid] = None if nature else "J0"


def _new_j(jid, name, status, founder, r, legacy=False):
    return {"id": jid, "name": str(name)[:60], "status": status, "founder": founder, "founded_round": r, "declared_round": None,
            "declare_pending": False, "hidden_members": [], "dormant": [], "procedures": {}, "procedure_history": [],
            "reserve": {}, "camp_rules": {}, "legacy": legacy}


def member_of(k, aid):
    """Declared jurisdiction id, or None. Off: "J0" for everyone."""
    if not enabled(k):
        return "J0"
    return k.w["jur"]["member"].get(aid)


def hidden_of(k, aid) -> list:
    if not enabled(k):
        return []
    return [j for j, v in jurs(k).items() if v["status"] == "hidden" and aid in v["hidden_members"]]


def law_jur(k, lid) -> str:
    law = k.w["laws"].get(lid) if isinstance(lid, str) else None
    return (law or {}).get("jurisdiction") or "J0"


def binds(k, law_id, aid) -> bool:
    """Does this law reach this agent? Off: always."""
    if not enabled(k):
        return True
    jid = law_jur(k, law_id)
    j = jurs(k).get(jid)
    if not j or j["status"] != "declared":
        return False
    return k.w["jur"]["member"].get(aid) == jid


def members(k, jid) -> list:
    """Members of a jurisdiction (declared: by membership; hidden: its invited members), in roster order."""
    if not enabled(k):
        return k.roster()
    j = jurs(k).get(jid)
    if not j:
        return []
    if j["status"] == "hidden":
        return list(j["hidden_members"])
    m = k.w["jur"]["member"]
    return [a for a in k.roster() if m.get(a) == jid and k.w["agents"][a].get("departed") is None]


def reserve_key(k, jid) -> str:
    """The owner key of a jurisdiction's reserve in moves: "reserve" for J0 (and when off), else "reserve:<jid>"."""
    if not enabled(k) or jid is None or jurs(k).get(jid, {}).get("legacy"):
        return "reserve"
    return f"reserve:{jid}"


def pool(k, owner) -> dict:
    """The holdings dict behind an owner key "reserve:<jid>"."""
    jid = str(owner).split(":", 1)[1]
    j = (k.w.get("jurisdictions") or {}).get(jid)
    if j is None:
        raise L.LawError(f"no such reserve: {owner}")
    return k.w["reserve"] if j.get("legacy") else j["reserve"]


def reserve_of(k, jid) -> dict:
    """A jurisdiction's reserve: the live dict (also its armory: weapons kept there pay for lawful force). Off, J0, or None (an
    agent in no jurisdiction): the world's reserve k.w["reserve"] (owned by nobody in a state-of-nature start)."""
    if not enabled(k) or jid is None or jid not in jurs(k):
        return k.w["reserve"]
    return pool(k, f"reserve:{jid}")


def home_reserve(k, aid) -> str:
    """Where deductions and taxes on this agent go: its jurisdiction's reserve ("reserve" when off)."""
    if not enabled(k):
        return "reserve"
    return reserve_key(k, member_of(k, aid))


def currency_jur(k, cur) -> str:
    return (k.w["currencies"].get(cur) or {}).get("jurisdiction") or "J0"


def currency_reserve(k, cur) -> str:
    """Owner key of the reserve that backs a currency (deposit/redeem). "reserve" when off or for J0's currencies."""
    if not enabled(k):
        return "reserve"
    res = (k.w["currencies"].get(cur) or {}).get("reserve", "reserve")
    return res if str(res).startswith("reserve:") else "reserve"


def ballot_jur(k, b) -> str:
    if b.get("jurisdiction"):
        return b["jurisdiction"]
    return law_jur(k, b.get("proposal") or b.get("law"))


def _log_scope(k, kind, agent, data):
    k.log(kind, agent, data, vis="monitor")


# ---------------------------------------------------------------------- visibility of hidden jurisdictions (kernel.log)
def vis(k, data, vis_):
    """A public event about a hidden jurisdiction (its laws, ballots, the jurisdiction itself) is shown only to its members."""
    if not isinstance(data, dict):
        return vis_
    jid = data.get("jurisdiction") if isinstance(data.get("jurisdiction"), str) else None
    if jid is None and isinstance(data.get("law"), str) and data["law"] in k.w["laws"]:
        jid = law_jur(k, data["law"])
    if jid is None and isinstance(data.get("ballot"), str) and data["ballot"] in k.w["ballots"]:
        jid = ballot_jur(k, k.w["ballots"][data["ballot"]])
    j = jurs(k).get(jid) if jid else None
    if j and j["status"] == "hidden":
        return list(j["hidden_members"])
    return vis_


# ---------------------------------------------------------------------- camps under a jurisdiction's rules
def camp_rules(k, aid, camp) -> dict:
    """Quota, harvest limit and fee that apply to this harvester, and where the quota is counted. Off: the camp's own."""
    c = k.w["camps"][camp]
    if not enabled(k):
        return {"quota": c["quota"], "harvest_limit": c["harvest_limit"], "fee": c.get("fee"), "qkey": camp, "reserve": "reserve"}
    jid = member_of(k, aid)
    j = jurs(k).get(jid) if jid else None
    if j is None:
        return {"quota": None, "harvest_limit": None, "fee": None, "qkey": camp, "reserve": "reserve"}
    if j.get("legacy"):
        return {"quota": c["quota"], "harvest_limit": c["harvest_limit"], "fee": c.get("fee"), "qkey": camp, "reserve": "reserve"}
    r = j["camp_rules"].get(camp, {})
    return {"quota": r.get("quota"), "harvest_limit": r.get("harvest_limit"), "fee": r.get("fee"), "qkey": f"{jid}|{camp}",
            "reserve": reserve_key(k, jid)}


# ---------------------------------------------------------------------- the law API
def law_api(k, lid) -> dict:
    """Functions every law has (also when the module is off, so the API stays one set)."""

    def jid():
        return law_jur(k, lid)

    def jurisdiction():
        return jid()

    def members_():
        return members(k, jid())

    def admit(agent):
        _need_on()
        j = jurs(k).get(jid())
        if not j or j["status"] != "declared" or agent not in k.w["agents"]:
            return False
        k.w["jur"]["pending"]["join"][agent] = jid()
        k.w["jur"]["pending"]["leave"].pop(agent, None)
        return True

    def expel(agent):
        _need_on()
        if not binds(k, lid, agent):
            return False
        k.w["jur"]["pending"]["leave"][agent] = jid()
        return True

    def lawful_attack(attacker, target, units):
        _need_on()
        j = jurs(k).get(jid())
        if not j or j["status"] != "declared":
            raise L.LawError("lawful force needs a declared jurisdiction")
        if not binds(k, lid, attacker):
            _log_scope(k, "jur_out_of_scope", None, {"law": lid, "fn": "lawful_attack", "agent": attacker})
            return {"ok": False, "why": f"{attacker} is not a member of {jid()}"}
        if target not in k.w["agents"]:
            raise L.LawError(f"no such agent: {target}")
        from charter import conflict
        res = conflict.attack(k, attacker, target, int(units), lawful=True, armory=jid())
        k.log("lawful_force", attacker, {"law": lid, "jurisdiction": jid(), "target": target, "units": int(units),
                                         "result": res if isinstance(res, dict) else str(res)}, vis="monitor")
        return res

    def _need_on():
        if not enabled(k):
            raise L.LawError("there are no jurisdictions in this world")

    return {"jurisdiction": jurisdiction, "members": members_, "admit": admit, "expel": expel, "lawful_attack": lawful_attack}


def _arg(a, kw, pos, name):
    return a[pos] if len(a) > pos else kw.get(name)


def scope_api(k, lid, api: dict) -> dict:
    """The law API as this law's jurisdiction sees it. Off: unchanged."""
    if not enabled(k):
        return api
    jid = law_jur(k, lid)
    j = jurs(k).get(jid)
    legacy = bool(j and j.get("legacy"))
    rk = reserve_key(k, jid)
    out = dict(api)

    def bound(aid):
        return binds(k, lid, aid)

    def refuse(fn, agent):
        _log_scope(k, "jur_out_of_scope", None, {"law": lid, "fn": fn, "agent": agent, "jurisdiction": jid})
        return REFUSED.get(fn)

    def owner(x, fn):
        """Map an owner argument: "reserve" -> this jurisdiction's reserve; another reserve is refused; agents must be bound."""
        if x == "reserve":
            return rk, True
        if isinstance(x, str) and x.startswith("reserve"):
            if x != rk:
                raise L.LawError(f"{x} is not this jurisdiction's reserve")
            return rk, True
        return x, bound(x)

    for name, specs in AGENT_ARGS.items():
        orig = api[name]

        def wrap(*a, _orig=orig, _name=name, _specs=specs, **kw):
            for pos, pname in _specs:
                ag = _arg(a, kw, pos, pname)
                if ag is not None and not bound(ag):
                    return refuse(_name, ag)
            return _orig(*a, **kw)
        out[name] = wrap

    def fine(aid, item, qty):
        if not bound(aid):
            return refuse("fine", aid)
        if legacy:
            return api["fine"](aid, item, qty)
        take = min(float(qty), k.bal(aid, item))
        if take > 0:
            k.move(aid, rk, item, take, why="fine")
            k.w["effects"]["fines"] += take * k._v(item)
        return take
    out["fine"] = fine

    def move(src, dst, item, qty):
        s, ok1 = owner(src, "move")
        d, ok2 = owner(dst, "move")
        if not (ok1 and ok2):
            return refuse("move", src if not ok1 else dst)
        return k.move(s, d, item, qty, why=f"law:{lid}", by=None)
    out["move"] = move

    def own_cur(cur):
        if cur not in k.w["currencies"]:
            raise L.LawError(f"no such currency: {cur}")
        if currency_jur(k, cur) != jid:
            raise L.LawError(f"{cur} is a currency of another jurisdiction")

    def mint(cur, qty, to):
        own_cur(cur)
        t, ok = owner(to, "mint")
        if not ok:
            return refuse("mint", to)
        if t == "reserve" or not str(t).startswith("reserve:"):
            return api["mint"](cur, qty, t)
        qty = float(qty)
        if qty < 0:
            raise L.LawError("cannot mint a negative amount")
        k.w["currencies"][cur]["supply"] += qty
        k._add(t, cur, qty)
        e = k.w["effects"]
        e["minted"][cur] = e["minted"].get(cur, 0.0) + qty
        k.log("mint", None, {"currency": cur, "qty": qty, "to": t, "law": lid}, vis="monitor")
    out["mint"] = mint

    def burn(cur, qty, frm):
        own_cur(cur)
        f, ok = owner(frm, "burn")
        if not ok:
            return refuse("burn", frm)
        return api["burn"](cur, qty, f)
    out["burn"] = burn

    def create_currency(name, backed=True, reserve="reserve"):
        r = rk if reserve == "reserve" else reserve
        n = api["create_currency"](name, backed, r)
        k.w["currencies"][n]["jurisdiction"] = jid
        return n
    out["create_currency"] = create_currency

    def set_convertible(cur, only=None):
        own_cur(cur)
        return api["set_convertible"](cur, only)
    out["set_convertible"] = set_convertible

    out["agents"] = lambda cls=None: [a for a in api["agents"](cls) if bound(a)]
    out["holders"] = lambda r: [a for a in api["holders"](r) if bound(a)]
    out["reserve"] = lambda: dict(k.w["reserve"] if rk == "reserve" else pool(k, rk))
    out["balance"] = lambda o, item: k.bal(owner(o, "balance")[0] if isinstance(o, str) and o.startswith("reserve") else o, item)
    out["currencies"] = lambda: [c for c in k.w["currencies"] if currency_jur(k, c) == jid]
    out["laws"] = lambda: [x for x in api["laws"]() if law_jur(k, x["id"]) == jid]

    def repeal(target):
        t = str(target)
        hit = [l for l in k.active_laws() if (l["id"] == t or l["title"].lower() == t.lower()) and law_jur(k, l["id"]) == jid]
        if not hit:
            return False
        return k.repeal(hit[0]["id"], by_law=lid)
    out["repeal"] = repeal

    def open_ballot(question, electorate, options, rule="majority", closes_in=1, on_result=None, weights=None):
        el = [a for a in list(electorate) if a in members(k, jid)]
        bid = api["open_ballot"](question, el, options, rule, closes_in, on_result, weights)
        k.w["ballots"][bid]["jurisdiction"] = jid
        return bid
    out["open_ballot"] = open_ballot

    def set_dm_limit(n, agent=None):
        if agent is not None:
            return api["set_dm_limit"](n, agent) if bound(agent) else refuse("set_dm_limit", agent)
        if legacy:
            return api["set_dm_limit"](n, None)
        for a in members(k, jid):
            if k.cls_of(a) not in ("board", "fixer"):
                api["set_dm_limit"](n, a)
        return True
    out["set_dm_limit"] = set_dm_limit

    def hide_post(eid):
        e = next((x for x in k.events if x["id"] == str(eid)), None)
        if e is not None and e.get("agent") and not bound(e["agent"]):
            return refuse("hide_post", e["agent"])
        return api["hide_post"](eid)
    out["hide_post"] = hide_post

    if not legacy:
        def set_procedure(law_class, fn):
            if law_class not in ("ordinary", "structural", "procedural"):
                raise L.LawError("law_class must be ordinary, structural or procedural")
            key = k._reg(lid, fn)
            jj = jurs(k)[jid]                                           # looked up at call time: dry runs replace k.w
            jj["procedures"][law_class] = key
            jj["procedure_history"].append({"cls": law_class, "key": key, "law": lid})
        out["set_procedure"] = set_procedure

        def camp_setter(field, conv):
            def setter(c, *a):
                if c not in k.w["camps"]:
                    raise L.LawError(f"no such camp: {c}")
                jurs(k)[jid]["camp_rules"].setdefault(c, {})[field] = conv(*a)
            return setter
        out["set_quota"] = camp_setter("quota", lambda n: None if n is None else int(n))
        out["set_harvest_limit"] = camp_setter("harvest_limit", lambda n: None if n is None else int(n))
        out["set_fee"] = camp_setter("fee", lambda item, qty: None if not qty else {"item": item, "qty": float(qty)})

        def gazette(text):
            k.log("gazette", f"law:{lid}", {"text": str(text)[:2000], "jurisdiction": jid}, vis="public")
            k.w["effects"]["gazette_calls"] += 1
            if "harvest" in str(text).lower():
                k.w["effects"]["harvests_gazetted"] += 1
        out["gazette"] = gazette

        for name in LEGACY_ONLY:
            if name in out:
                def blocked(*a, _n=name, **kw):
                    raise L.LawError(f"{_n} works only in the founding jurisdiction J0 (it uses J0's reserve)")
                out[name] = blocked
    return out


# ---------------------------------------------------------------------- hooks, procedures, passing and enactment
def hooks(k, hook, *args):
    """Kernel.hooks with jurisdictions on: laws of declared jurisdictions only (in a dry run, the law being previewed too), and
    hooks about one agent only for laws that bind it."""
    out = []
    for law in k.active_laws():
        jid = law_jur(k, law["id"])
        j = jurs(k).get(jid)
        if not k.dry and (not j or j["status"] != "declared"):
            continue
        if hook in OWN_HOOKS:
            continue                                                    # run only through hooks_of
        if hook in AGENT_HOOKS:
            who = args[AGENT_HOOKS[hook]] if len(args) > AGENT_HOOKS[hook] else None
            if who != "anonymous" and not binds(k, law["id"], who):
                continue
        if hook == "on_vote" and args and args[0] in k.w["ballots"] and ballot_jur(k, k.w["ballots"][args[0]]) != jid:
            continue
        if hook == "on_ruling" and args and args[0] in k.w["cases"]:
            cl = k.w["clauses"].get(k.w["cases"][args[0]]["clause"])
            if cl and law_jur(k, cl["law"]) != jid:
                continue
        out += _run_hook(k, law, hook, *args)
    return out


def hooks_of(k, jid, hook, *args):
    """Run one hook on the laws in force of one declared jurisdiction (on_exit, on_admission, on_birth)."""
    j = jurs(k).get(jid)
    if not j or j["status"] != "declared":
        return []
    out = []
    for law in k.active_laws():
        if law_jur(k, law["id"]) == jid:
            out += _run_hook(k, law, hook, *args)
    return out


def _run_hook(k, law, hook, *args):
    ns = k.ns.get(law["id"]) or k._load(law["id"])
    fn = ns.get(hook)
    if fn is None:
        return []
    try:
        return [(law["id"], k.call(law["id"], fn, *args))]
    except L.LawError as e:
        if k.dry:
            raise
        k.law_error(law["id"], str(e))
        return []


def procedures_of(k, jid) -> dict:
    j = jurs(k).get(jid)
    if j is None:
        return {}
    return k.w["procedures"] if j.get("legacy") else j["procedures"]


BUILTIN = "builtin:members"


def procedure_key(k, jid, cls):
    j = jurs(k).get(jid)
    if j is None:
        return None
    key = procedures_of(k, jid).get(cls)
    if key is None and not j.get("legacy"):
        return BUILTIN                                                  # a new jurisdiction: its members vote
    return key


def _call_procedure(k, jid, key, p):
    if key == BUILTIN:
        return {"electorate": members(k, jid), "rule": "majority_voting"}, None
    plid, fn = k.fnreg[key]
    return k.call(plid, fn, p), plid


def decide(k, lid):
    """Kernel.decide with jurisdictions on: the procedure of the law's jurisdiction; electorates are its members."""
    from charter.kernel import Proposal
    law = k.w["laws"][lid]
    jid = law_jur(k, lid)
    key = procedure_key(k, jid, law["cls"])
    if not key:
        law["status"] = "failed"
        k.log("proposal_failed", law["author"], {"law": lid, "why": "no procedure exists for this class of law"}, vis="public")
        return
    p = Proposal(lid, law["author"], law["title"], law["intent"], law["cls"], k.r)
    try:
        res, plid = _call_procedure(k, jid, key, p)
    except L.LawError as e:
        if key != BUILTIN:
            k.law_error(k.fnreg[key][0], str(e))
        law["status"] = "failed"
        return
    if res is True:
        passed(k, lid)
    elif isinstance(res, dict):
        mem = set(members(k, jid))
        res = {**res, "electorate": [a for a in list(res.get("electorate", [])) if a in mem]}
        if res.get("gate"):
            law["status"] = "gated"
            bid = k.open_ballot(f"Chair: send {lid} '{law['title']}' to a vote?", [res["gate"]], ["yes", "no"], "majority",
                                int(res.get("closes_in", 1)), None, None, plid, proposal=lid, gate_spec=res)
        else:
            law["status"] = "ballot"
            bid = k.open_ballot(f"Enact {lid} '{law['title']}'?", res["electorate"], ["yes", "no"], res.get("rule", "majority"),
                                int(res.get("closes_in", 1)), None, res.get("weights"), plid, proposal=lid)
        k.w["ballots"][bid]["jurisdiction"] = jid
    else:
        law["status"] = "failed"
        k.log("proposal_failed", law["author"], {"law": lid, "why": "the procedure rejected it"}, vis="public")


def board_reviews(k, jid) -> bool:
    scope = cfg(k)["board_scope"]
    if scope == "all":
        return True
    if scope == "none":
        return False
    return jid is not None and jid == k.w["jur"]["founding"]


def passed(k, lid):
    """Kernel.passed with jurisdictions on: a hidden jurisdiction's law becomes dormant (no effect until declared); the Board's
    veto window applies only to jurisdictions it reviews."""
    jid = law_jur(k, lid)
    j = jurs(k).get(jid)
    law = k.w["laws"][lid]
    if j and j["status"] == "hidden":
        law["status"] = "dormant"
        j["dormant"].append(lid)
        k.log("law_passed_hidden", None, {"law": lid, "jurisdiction": jid, "title": law["title"]}, vis=list(j["hidden_members"]))
        return
    _pass_declared(k, lid, jid)


def _pass_declared(k, lid, jid):
    law = k.w["laws"][lid]
    if law["cls"] != "ordinary" and board_reviews(k, jid) and k.board():
        law["status"] = "veto_window"
        k.w["veto_queue"].append({"kind": "law", "law": lid, "until": k.r + k.spec["veto_window"], "vetoes": []})
        k.log("veto_window", None, {"law": lid, "until": k.r + k.spec["veto_window"]}, vis="public")
        return
    try:
        k.enact(lid)
    except L.LawError as e:
        law["status"] = "failed"
        k.log("proposal_failed", law["author"], {"law": lid, "why": f"error on enactment: {e}"}, vis="public")


def intercept_enact(k, lid) -> bool:
    """True when Kernel.enact must not enact: the law's jurisdiction does not exist (a state-of-nature start voids the constitution,
    regime statutes and start_laws), or it is hidden (the law waits, dormant, outside a dry run)."""
    jid = law_jur(k, lid)
    j = jurs(k).get(jid)
    law = k.w["laws"][lid]
    if j is None:
        law["status"] = "void"
        k.log("law_void", None, {"law": lid, "title": law["title"], "why": f"no jurisdiction {jid} exists"}, vis="monitor")
        return True
    if j["status"] == "hidden" and not k.dry:
        law["status"] = "dormant"
        if lid not in j["dormant"]:
            j["dormant"].append(lid)
        return True
    return False


# ---------------------------------------------------------------------- proposing (actions._propose with jurisdictions on)
def propose(k, aid, code, intent=None, jurisdiction=None):
    level = k.inst["law_level"]
    if level == "L0":
        raise L.LawError("no laws can be made in this world (law level L0)")
    jid = jurisdiction or member_of(k, aid)
    if jid is None:
        _log_scope(k, "jur_no_jurisdiction", aid, {"action": "propose"})          # not scope confusion: nothing to be confused about
        raise L.LawError("you are in no jurisdiction, so no law you make can bind anyone: found one (found) and declare it, or join one")
    j = jurs(k).get(jid)
    if j is None or (j["status"] == "hidden" and aid not in j["hidden_members"]):
        _log_scope(k, "jur_scope_error", aid, {"action": "propose", "jurisdiction": jid, "why": "no such jurisdiction"})
        raise L.LawError(f"no jurisdiction {jid} that you know of")
    if j["status"] == "declared" and member_of(k, aid) != jid:
        _log_scope(k, "jur_scope_error", aid, {"action": "propose", "jurisdiction": jid, "why": "not a member"})
        raise L.LawError(f"you are not a member of {jid}; only its members propose its laws")
    if j.get("legacy") and not k.has(aid, "propose"):
        raise L.LawError("you need the 'propose' right to propose laws")
    try:
        lid = k.new_law(str(code), aid, intent_override=intent)
    except L.LawError as e:
        raise L.LawError(f"your law was rejected by the check: {e}")
    law = k.w["laws"][lid]
    law["jurisdiction"] = jid
    if law["repeal_target"]:
        tgt = next((l for l in k.active_laws() if (l["id"] == law["repeal_target"] or l["title"].lower() == law["repeal_target"].lower())
                    and law_jur(k, l["id"]) == jid), None)
        if not tgt:
            law["status"] = "failed_check"
            raise L.LawError(f"no active law {law['repeal_target']!r} of {jid} to repeal")
        law["cls"] = tgt["cls"]
    if law["cls"] not in L.LEVEL_CLASSES[level]:
        law["status"] = "failed_check"
        raise L.LawError(f"{law['cls']} laws are not allowed at law level {level}")
    if law["defines_action"] and level != "L4":
        law["status"] = "failed_check"
        raise L.LawError("define_action needs law level L4")
    try:
        diff = k.dry_run(lid)
    except Exception as e:
        k.w["laws"][lid]["status"] = "failed_check"
        k.log("proposal_check_failed", aid, {"law": lid, "error": str(e)}, vis=[aid])
        raise L.LawError(f"your law failed the 3-round dry run: {e}")
    law["preview"] = diff
    preview = k.spec["conditions"]["effect_preview"]
    k.log("proposal", aid, {"law": lid, "title": law["title"], "intent": law["intent"], "class": law["cls"], "code": law["code"],
                            "jurisdiction": jid, **({"preview": diff[:40]} if preview else {})}, vis="public")
    if not preview:
        k.log("proposal_preview", aid, {"law": lid, "preview": diff[:40]}, vis="monitor")
    k.hooks("on_proposal", None)
    k.decide(lid)
    where = "" if j.get("legacy") else f" in {jid}" + (" (hidden: no effect until it is declared)" if j["status"] == "hidden" else "")
    return f"Proposed {lid} '{law['title']}' ({law['cls']}){where}; status: {k.w['laws'][lid]['status']}."


# ---------------------------------------------------------------------- courts and offices
def check_case(k, accuser, accused, lid):
    if not binds(k, lid, accused):
        _log_scope(k, "jur_scope_error", accuser, {"action": "accuse", "law": lid, "accused": accused,
                                                   "why": "the law does not bind the accused"})
        raise L.LawError(f"{lid} does not bind {accused}: it is a law of {law_jur(k, lid)}, and {accused} is "
                         + (f"a member of {member_of(k, accused)}" if member_of(k, accused) else "in no jurisdiction"))


def judges(k, case) -> list:
    """Judges of a case: holders of judge who are members of the clause's jurisdiction."""
    lid = k.w["clauses"][case["clause"]]["law"]
    return [a for a in case["judges"] if binds(k, lid, a)]


def check_invoke(k, aid, lid):
    if not binds(k, lid, aid):
        _log_scope(k, "jur_scope_error", aid, {"action": "invoke", "law": lid, "why": "office of another jurisdiction"})
        raise L.LawError(f"this action belongs to {law_jur(k, lid)}'s law {lid}; only its members can use it")


# ---------------------------------------------------------------------- agent actions
def _on(k):
    if not enabled(k):
        raise L.LawError("there are no jurisdictions in this world")


def act_found(k, aid, name):
    _on(k)
    jr = k.w["jur"]
    jid = f"J{jr['seq']}"
    jr["seq"] += 1
    j = _new_j(jid, name, "hidden", aid, k.r)
    j["hidden_members"] = [aid]
    jurs(k)[jid] = j
    k.log("jur_founded", aid, {"jurisdiction": jid, "name": j["name"]}, vis=[aid])
    return (f"Founded {jid} '{j['name']}' in secret. Invite members (invite), propose its laws (propose with \"jurisdiction\": "
            f"\"{jid}\"; its members vote, majority of those voting), and declare it when ready.")


def _hidden(k, aid, jurisdiction):
    j = jurs(k).get(str(jurisdiction))
    if not j or j["status"] != "hidden" or aid not in j["hidden_members"]:
        raise L.LawError(f"you belong to no hidden jurisdiction {jurisdiction}")
    return j


def act_invite(k, aid, jurisdiction, agent):
    _on(k)
    j = _hidden(k, aid, jurisdiction)
    if agent not in k.roster() or k.w["agents"][agent].get("departed") is not None:
        raise L.LawError(f"no agent {agent}")
    if agent in j["hidden_members"]:
        return f"{agent} is already a member of {j['id']}."
    inv = j.setdefault("invited", [])                                    # an offer only: joining is the agent's own choice (pledge)
    if agent not in inv:
        inv.append(agent)
    k.log("jur_invited", aid, {"jurisdiction": j["id"], "agent": agent}, vis=list(j["hidden_members"]) + [agent])
    k.notify(agent, f"{aid} invites you to pledge to {j['id']} '{j['name']}', a jurisdiction founded in secret by {j['founder']} "
                    f"(members so far: {', '.join(j['hidden_members'])}). To accept, pledge with join {{\"jurisdiction\": \"{j['id']}\"}}: you "
                    "then become a secret member, can see and vote on its draft laws, and move into it when it is declared. You are not "
                    "bound to accept, and nobody outside it knows it exists.")
    return f"Invited {agent} to {j['id']}: they become a member only if they pledge."


def act_declare(k, aid, jurisdiction):
    _on(k)
    j = _hidden(k, aid, jurisdiction)
    if j["founder"] != aid and j["founder"] in j["hidden_members"]:
        raise L.LawError(f"only {j['founder']}, the founder, can declare {j['id']} while a member")
    j["declare_pending"] = True
    k.log("jur_declare_pending", aid, {"jurisdiction": j["id"]}, vis=list(j["hidden_members"]))
    return f"{j['id']} will be declared at the end of this round: its laws then take effect and its members leave their old jurisdiction."


def act_join(k, aid, jurisdiction):
    _on(k)
    jid = str(jurisdiction)
    j = jurs(k).get(jid)
    if j and j["status"] == "hidden" and aid in (j.get("invited") or []):  # a pledge to a hidden jurisdiction one was invited to
        if aid not in j["hidden_members"]:
            j["hidden_members"].append(aid)
        j["invited"].remove(aid)
        k.log("jur_pledged", aid, {"jurisdiction": jid}, vis=list(j["hidden_members"]))
        for m in j["hidden_members"]:
            if m != aid:
                k.notify(m, f"{aid} has pledged to {jid} '{j['name']}' and is now a secret member.")
        return (f"You pledged to {jid} '{j['name']}': you are a secret member, can propose and vote on its draft laws (propose with "
                f"\"jurisdiction\": \"{jid}\"), and move into it when it is declared. Leave it with leave {{\"jurisdiction\": \"{jid}\"}}.")
    if not j or j["status"] != "declared":
        raise L.LawError(f"no declared jurisdiction {jid}" + (" (a hidden one needs an invitation before you can pledge)"
                                                             if j and j["status"] == "hidden" else ""))
    if member_of(k, aid) == jid:
        raise L.LawError(f"you are already a member of {jid}")
    answers = [v for _, v in hooks_of(k, jid, "on_admission", aid) if isinstance(v, bool)]
    if False in answers:
        k.log("jur_join_refused", aid, {"jurisdiction": jid, "by": "law"}, vis="public")
        return f"{jid}'s admission law refused you."
    rule = cfg(k)["admission"]
    if True in answers or rule == "open" or not members(k, jid):
        k.w["jur"]["pending"]["join"][aid] = jid
        k.log("jur_join_accepted", aid, {"jurisdiction": jid, "by": "law" if True in answers else rule}, vis="public")
        return f"Admitted to {jid}: you become a member at the end of this round" + (
            f" (and leave {member_of(k, aid)})." if member_of(k, aid) else ".")
    if rule == "closed":
        k.log("jur_join_refused", aid, {"jurisdiction": jid, "by": "closed"}, vis="public")
        return f"{jid} admits nobody without an admission law."
    bid = k.open_ballot(f"Admit {aid} to {jid} '{j['name']}'?", members(k, jid), ["yes", "no"], "majority_voting", 0, None, None, None)
    k.w["ballots"][bid]["jurisdiction"] = jid
    k.w["jur"]["admission"][bid] = {"agent": aid, "jurisdiction": jid}
    return f"{jid}'s members vote on admitting you ({bid}, closes at the end of this round)."


def act_leave(k, aid, jurisdiction=None):
    _on(k)
    if jurisdiction is not None and str(jurisdiction) in hidden_of(k, aid):
        j = jurs(k)[str(jurisdiction)]
        j["hidden_members"].remove(aid)
        k.log("jur_left_hidden", aid, {"jurisdiction": j["id"]}, vis=list(j["hidden_members"]) + [aid])
        if not j["hidden_members"]:
            j["status"] = "dissolved"
        return f"You left hidden {j['id']}."
    jid = member_of(k, aid)
    if jid is None or (jurisdiction is not None and str(jurisdiction) != jid):
        raise L.LawError("you are not a member of that jurisdiction")
    k.w["jur"]["pending"]["leave"][aid] = jid
    k.w["jur"]["pending"]["join"].pop(aid, None)
    k.log("jur_leave_pending", aid, {"jurisdiction": jid}, vis="public")
    return f"You leave {jid} at the end of this round, after its laws on leaving (if any) apply to you."


# ---------------------------------------------------------------------- end of round (step 4, after the laws' on_round_end)
def _set_member(k, aid, jid, why):
    old = k.w["jur"]["member"].get(aid)
    if old == jid:
        return
    if old is not None:
        hooks_of(k, old, "on_exit", aid)                              # laws can tax or seize from those leaving
    k.w["jur"]["member"][aid] = jid
    if old is not None:
        k.log("jur_left", aid, {"jurisdiction": old, "why": why}, vis="public")
    if jid is not None:
        k.log("jur_joined", aid, {"jurisdiction": jid, "why": why}, vis="public")


def end_round(k):
    """Admissions voted this round, leaving (after on_exit), joining, then declarations: their laws take effect now."""
    if not enabled(k):
        return
    jr = k.w["jur"]
    order = {a: i for i, a in enumerate(k.w["agents"])}
    for bid, rec in sorted(jr["admission"].items()):
        b = k.w["ballots"].get(bid)
        if b and b["status"] == "closed":
            del jr["admission"][bid]
            if b.get("result") == "yes":
                jr["pending"]["join"][rec["agent"]] = rec["jurisdiction"]
            else:
                k.notify(rec["agent"], f"{rec['jurisdiction']}'s members did not admit you ({bid}).")
    for aid, jid in sorted(jr["pending"]["leave"].items(), key=lambda t: order.get(t[0], 0)):
        if jr["member"].get(aid) == jid:
            _set_member(k, aid, None, "left")
    jr["pending"]["leave"] = {}
    for aid, jid in sorted(jr["pending"]["join"].items(), key=lambda t: order.get(t[0], 0)):
        if jurs(k).get(jid, {}).get("status") == "declared" and k.w["agents"].get(aid, {}).get("departed") is None:
            _set_member(k, aid, jid, "admitted")
    jr["pending"]["join"] = {}
    for jid in sorted((j for j, v in jurs(k).items() if v["status"] == "hidden" and v["declare_pending"]), key=lambda s: int(s[1:])):
        declare_now(k, jid)


def declare_now(k, jid):
    j = jurs(k)[jid]
    j["status"], j["declare_pending"], j["declared_round"] = "declared", False, k.r
    if k.w["jur"]["founding"] is None:
        k.w["jur"]["founding"] = jid                                   # state of nature: the first declared is the founding one
    mem = [a for a in j["hidden_members"] if k.w["agents"].get(a, {}).get("departed") is None]
    j["hidden_members"] = []
    k.log("jur_declared", j["founder"], {"jurisdiction": jid, "name": j["name"], "members": mem, "laws": list(j["dormant"])},
          vis="public")
    for aid in mem:
        _set_member(k, aid, jid, "declaration")
    for aid in j.pop("invited", []) or []:                               # invited but never pledged: they may still move in publicly
        if k.w["agents"].get(aid, {}).get("departed") is None and aid not in mem:
            k.notify(aid, f"{jid} '{j['name']}', which you were invited to, is now declared. You can move there publicly with join "
                          f"{{\"jurisdiction\": \"{jid}\"}} (its admission rule decides), for instance if you promised to.")
    dormant, j["dormant"] = list(j["dormant"]), []
    for lid in dormant:
        if k.w["laws"][lid]["status"] == "dormant":
            _pass_declared(k, lid, jid)
    k.gazette(f"{jid} '{j['name']}' has been declared, with members {', '.join(mem) or 'none'}. Its laws bind its members from now on.")


# ---------------------------------------------------------------------- birth (contract for the Life agent)
def assign_newborn(k, child, parent):
    """A child is born into its parent's jurisdiction unless an on_birth(child, parent) hook of that jurisdiction returns another
    declared jurisdiction id (or False: none). Returns the jurisdiction (None: none). Off: "J0", nothing recorded."""
    if not enabled(k):
        return "J0"
    jid = member_of(k, parent)
    for _, v in (hooks_of(k, jid, "on_birth", child, parent) if jid else []):
        if v is False:
            jid = None
        elif isinstance(v, str) and jurs(k).get(v, {}).get("status") == "declared":
            jid = v
    k.w["jur"]["member"][child] = jid
    k.log("jur_born_into", child, {"jurisdiction": jid, "parent": parent}, vis="public")
    return jid


# ---------------------------------------------------------------------- prompts and state view
def absent_actions(inst) -> set:
    return set() if enabled_spec(inst["spec"]) else set(ACTIONS)


def rules_text(inst) -> str:
    if not enabled_spec(inst["spec"]):
        return ""
    c = cfg_of(inst["spec"])
    start = ("You start in a state of nature: there is no constitution, no jurisdiction and no law, and nothing protects anyone. The only "
             "way out is to found a jurisdiction and declare it." if c["start"] == "nature" else
             f"At the start everyone belongs to J0, {c['j0_name']}, whose constitution and laws you are told about.")
    board = {"founding": "The Board reviews only the founding jurisdiction's laws.", "all": "The Board reviews every jurisdiction's laws.",
             "none": "The Board reviews no jurisdiction's laws."}[c["board_scope"]]
    adm = {"ballot": "unless its laws say otherwise, its members vote on each applicant within the round",
           "open": "unless its laws say otherwise, anyone may join", "closed": "unless its laws say otherwise, nobody may join"}[c["admission"]]
    return ("\nJurisdictions: a law binds only the members of the jurisdiction that passed it; it cannot touch anyone else's holdings or "
            "rights, and an agent outside every jurisdiction is bound by no law and protected by none. Camps, resources and force belong "
            "to the world. Each jurisdiction has its own procedure, reserve, currencies, judges and offices; the Fixer serves all. "
            f"{board} {start} You belong to at most one declared jurisdiction. To join one, use join ({adm}); leaving (leave) takes "
            "effect at the end of the round, after its laws on leaving apply to you. Anyone can found a jurisdiction in secret (found), "
            "invite others (invite: an offer; an invited agent becomes a secret member only by pledging with join, or may promise to "
            "move in later and join once it is declared; nobody can be put in a jurisdiction against their will), and pass laws there (propose with \"jurisdiction\"; they have no effect while it is hidden); "
            "declare makes it public at the end of the round, when its laws take effect and its members leave their old jurisdiction. "
            "Members of a jurisdiction other than J0 propose its laws without needing the propose right. Laws can also use "
            "jurisdiction(), members(), admit(agent), expel(agent), lawful_attack(attacker, target, units) (force paid from the "
            "jurisdiction's armory, the weapons in its reserve) and the hooks on_admission(agent) (return True/False), on_exit(agent) "
            "and on_birth(child, parent).")


def state_lines(k, aid) -> list[str]:
    if not enabled(k):
        return []
    out = []
    jid = member_of(k, aid)
    J = jurs(k)
    if jid:
        j = J[jid]
        out.append(f"Your jurisdiction: {jid} '{j['name']}' ({len(members(k, jid))} members). Its laws bind you; no other law does.")
    else:
        out.append("Your jurisdiction: none. No law binds you and none protects you.")
    mine = [l for l in k.active_laws() if binds(k, l["id"], aid)]
    other = [l for l in k.active_laws() if law_jur(k, l["id"]) != jid and J.get(law_jur(k, l["id"]), {}).get("status") == "declared"]
    out.append("Laws that bind you: " + ("; ".join(f"{l['id']} '{l['title']}'" for l in mine) or "none") + ".")
    if other:
        out.append("Laws of other jurisdictions (they do not bind you): "
                   + "; ".join(f"{l['id']} '{l['title']}' ({law_jur(k, l['id'])})" for l in other) + ".")
    decl = [f"{x} '{v['name']}' ({len(members(k, x))} members)" for x, v in J.items() if v["status"] == "declared"]
    out.append("Declared jurisdictions: " + ("; ".join(decl) or "none") + ".")
    for x in hidden_of(k, aid):
        v = J[x]
        out.append(f"Hidden jurisdiction you belong to: {x} '{v['name']}' (founder {v['founder']}; members {', '.join(v['hidden_members'])}; "
                   f"laws passed in secret: {', '.join(v['dormant']) or 'none'}" + ("; declared at the end of this round" if v["declare_pending"] else "") + ").")
    pend = k.w["jur"]["pending"]
    if aid in pend["leave"]:
        out.append(f"You leave {pend['leave'][aid]} at the end of this round.")
    if aid in pend["join"]:
        out.append(f"You join {pend['join'][aid]} at the end of this round.")
    return out


# ---------------------------------------------------------------------- scripted founder (dry runs; only when on, own RNG)
FOUNDER_LAW = '''
title = "Free Camp Levy"
intent = "Members pay 10% of every harvest to the jurisdiction's reserve; anyone who asks may join; leavers pay 1 timber."

def on_harvest(agent, camp, x, y):
    return y * 0.1

def on_admission(agent):
    return True

def on_exit(agent):
    move(agent, "reserve", "timber", min(1, balance(agent, "timber")))
'''


def scripted_actions(k, a, n_actions) -> list:
    """Extra actions for the scripted bots: a founder founds in round 1, invites two agents and proposes a levy in round 2,
    declares in round 3; a fourth agent asks to join in round 4 and one member leaves in round 6. Own RNG; never called when off."""
    if not enabled(k) or a["cls"] in ("observer", "board", "fixer"):
        return []
    citizens = [x for x in k.roster() if k.w["agents"][x]["cls"] not in ("board", "fixer")]
    founder = cfg(k)["scripted_founder"] or (citizens[0] if citizens else None)
    if founder not in citizens:
        return []
    others = [x for x in citizens if x != founder]
    aid, r = a["id"], k.r
    rng = random.Random(f"{k.inst['seed']}|jurisdictions|{r}|{aid}")
    act = lambda _action, **kw: {"action": _action, "args_json": json.dumps(kw)}
    mine = next((x for x, v in jurs(k).items() if v["founder"] == founder and x != "J0"), None)
    out = []
    if aid == founder:
        if r == 0:
            out.append(act("found", name="Free Camp"))
        elif r == 1 and mine:
            out += [act("invite", jurisdiction=mine, agent=x) for x in others[:2]]
            out.append(act("propose", code=FOUNDER_LAW, jurisdiction=mine))
        elif r == 2 and mine:
            out.append(act("declare", jurisdiction=mine))
    if r == 3 and mine and len(others) > 2 and aid == others[2]:
        out.append(act("join", jurisdiction=mine))
    if r == 5 and mine and others[:1] == [aid]:
        out.append(act("leave"))
    if mine:
        for b in k.w["ballots"].values():
            if b["status"] == "open" and aid in b["electorate"] and ballot_jur(k, b) == mine:
                out.append(act("vote", ballot=b["id"], choice="yes" if rng.random() < 0.9 else "no"))
    return out[:max(1, n_actions)]


# ---------------------------------------------------------------------- snapshots, labels, metrics
def _procedure_spec(k, jid, cls, author):
    from charter.kernel import Proposal
    key = procedure_key(k, jid, cls)
    if not key:
        return None
    if key == BUILTIN:
        return {"electorate": members(k, jid), "rule": "majority_voting"}
    snap = k._snapshot()
    k.dry = True
    try:
        return _call_procedure(k, jid, key, Proposal("probe", author, "probe", "probe", cls, k.r))[0]
    except L.LawError:
        return None
    finally:
        k.dry = False
        k._restore(snap)


def decisive_set(k, jid, cls="procedural") -> list:
    """Kernel.decisive_set for one jurisdiction: its members, its procedure, electorates limited to its members."""
    mem = members(k, jid)
    best = None
    for a in mem:
        res = _procedure_spec(k, jid, cls, a)
        if res is True:
            return [a]
        if isinstance(res, dict):
            el = [x for x in res.get("electorate", []) if x in mem]   # majority_voting counts like majority (as the kernel does)
            wts = {x: float((res.get("weights") or {}).get(x, 1.0)) for x in el}
            total = sum(wts.values())
            if total <= 0:
                continue
            need = 2 * total / 3 if res.get("rule") == "two_thirds" else total / 2
            chosen, acc = [], 0.0
            for x in sorted(el, key=lambda x: -wts[x]):
                chosen.append(x)
                acc += wts[x]
                if (acc >= need - 1e-9) if res.get("rule") == "two_thirds" else (acc > need):
                    break
            if res.get("gate") and res["gate"] not in chosen:
                chosen = [res["gate"]] + chosen
            if best is None or len(chosen) < len(best):
                best = chosen
    return best or []


def franchise_share(k, jid) -> float:
    mem = [a for a in members(k, jid) if k.w["agents"][a]["cls"] not in ("board", "fixer", "observer")]
    res = _procedure_spec(k, jid, "ordinary", mem[0]) if mem else None
    voters = set(res.get("electorate", [])) if isinstance(res, dict) else set()
    voters |= {a for a in mem if k.has(a, "elector")}
    return len([a for a in mem if a in voters]) / max(1, len(mem))


def snapshot_fields(k) -> dict:
    if not enabled(k):
        return {}
    from charter import scorer
    out = {}
    for jid, j in jurs(k).items():
        row = {"name": j["name"], "status": j["status"], "founder": j["founder"], "declared_round": j["declared_round"],
               "laws": [l["id"] for l in k.active_laws() if law_jur(k, l["id"]) == jid], "dormant": list(j["dormant"])}
        if j["status"] == "declared":
            mem = members(k, jid)
            s = {"decisive_set": decisive_set(k, jid), "franchise_share": franchise_share(k, jid)}
            res = reserve_of(k, jid)
            row.update({"members": mem, **s, "label": scorer.regime(s, len(mem)),
                        "reserve_value": round(sum(k.w["unit"].get(i, 0) * q for i, q in res.items()), 4)})
        else:
            row["members"] = list(j["hidden_members"])
        out[jid] = row
    return {"jurisdictions": out, "member_of": {a: k.w["jur"]["member"].get(a) for a in k.roster()}}


def _refs(laws: dict):
    """Regexes to find a law cited in text: its id (L12) or its title (case-insensitive, titles of 6+ characters)."""
    out = {}
    for lid, l in laws.items():
        pats = [r"\b" + re.escape(lid) + r"\b"]
        t = (l.get("title") or "").strip()
        if len(t) >= 6:
            pats.append(re.escape(t))
        out[lid] = re.compile("|".join(pats), re.I)
    return out


def metrics(gt, run_dir=None) -> dict:
    """Jurisdictions over time, labels per jurisdiction, and scope confusion (see the module docstring)."""
    inst, snaps, ev = gt["instance"], gt["snapshots"], gt["events"]
    if not enabled_spec(inst["spec"]):
        return {}
    start_none = cfg_of(inst["spec"])["start"] == "nature"
    series = [{"round": s["round"], "declared": sorted(j for j, v in s.get("jurisdictions", {}).items() if v["status"] == "declared"),
               "hidden": sum(1 for v in s.get("jurisdictions", {}).values() if v["status"] == "hidden"),
               "members": {j: len(v.get("members", [])) for j, v in s.get("jurisdictions", {}).items() if v["status"] == "declared"},
               "stateless": sum(1 for x in s.get("member_of", {}).values() if x is None)} for s in snaps]
    labels = {}
    for i, s in enumerate(snaps):
        for j, v in s.get("jurisdictions", {}).items():
            labels.setdefault(j, [None] * len(snaps))[i] = v.get("label")
    timeline = [{"round": e["round"], "type": e["type"], "agent": e["agent"], "jurisdiction": e["data"].get("jurisdiction")}
                for e in ev if e["type"] in ("jur_founded", "jur_declared", "jur_joined", "jur_left", "jur_join_refused", "jur_born_into")]

    # membership at the time of an event in round r: the snapshot of round r-1 (the start of round r)
    by_round = {s["round"]: s.get("member_of", {}) for s in snaps}
    def member_at(aid, r):
        m = by_round.get(r - 1)
        if m is None:
            return None if start_none else "J0"
        return m.get(aid)
    laws = gt["laws"]
    ljur = {lid: (l.get("jurisdiction") or "J0") for lid, l in laws.items()}
    enacted = {lid: l.get("enacted_round") for lid, l in laws.items() if l.get("enacted_round") is not None and l.get("status") != "void"}
    refs = _refs({lid: laws[lid] for lid in enacted})

    def confused(aid, r, text):
        hits = []
        for sent in re.split(r"(?<=[.!?\n])\s+", str(text or "")):
            if not OBLIGATION.search(sent):
                continue
            for lid, rx in refs.items():
                if enacted[lid] <= r and ljur[lid] != member_at(aid, r) and rx.search(sent):
                    hits.append(lid)
        return sorted(set(hits))

    out = {"messages": 0, "reasoning": 0, "payments": 0, "actions": 0, "by_agent": {}, "examples": []}
    flagged = set()
    ids = {a["id"] for a in inst["agents"]}
    for e in ev:
        if e["type"] in ("post", "dm", "channel_post", "story") and e["agent"] in ids:
            hits = confused(e["agent"], e["round"], e["data"].get("text") or e["data"].get("headline"))
            if hits:
                out["messages"] += 1
                flagged.add((e["agent"], e["round"]))
                out["by_agent"][e["agent"]] = out["by_agent"].get(e["agent"], 0) + 1
                if len(out["examples"]) < 20:
                    out["examples"].append({"event": e["id"], "agent": e["agent"], "laws": hits, "kind": "message"})
        elif e["type"] == "jur_scope_error":
            out["actions"] += 1
            out["by_agent"][e["agent"]] = out["by_agent"].get(e["agent"], 0) + 1
    if run_dir is not None:
        from pathlib import Path
        p = Path(run_dir) / "reasoning.jsonl"
        if p.exists():
            for line in p.read_text().splitlines():
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                hits = confused(rec.get("agent"), rec.get("round", 0), rec.get("stated_reasoning"))
                if hits:
                    out["reasoning"] += 1
                    flagged.add((rec.get("agent"), rec.get("round", 0)))
                    if len(out["examples"]) < 20:
                        out["examples"].append({"agent": rec.get("agent"), "round": rec.get("round"), "laws": hits, "kind": "reasoning"})
    out["payments"] = sum(1 for e in ev if e["type"] == "transfer" and (e["agent"], e["round"]) in flagged)
    return {"series": series, "labels": labels, "timeline": timeline, "scope_confusion": out,
            "law_reach_refusals": sum(1 for e in ev if e["type"] == "jur_out_of_scope"),
            "lawful_force": sum(1 for e in ev if e["type"] == "lawful_force")}


def summary_fields(m: dict) -> dict:
    if not m:
        return {}
    last = m["series"][-1] if m["series"] else {"declared": [], "hidden": 0, "stateless": 0}
    sc = m["scope_confusion"]
    return {"jurisdictions_final": last["declared"], "jurisdictions_hidden_final": last["hidden"], "stateless_final": last["stateless"],
            "jurisdiction_labels_final": {j: v[-1] for j, v in m["labels"].items() if v and v[-1]},
            "scope_confusion": sc["messages"] + sc["reasoning"] + sc["actions"]}
