"""Established starting worlds (docs/review/27 §6 item 3, §7): spec `start`, who and what exists at round 0.

A spec today can choose a constitution, laws in force, rights by class and switches; `start` places the rest: institutions with
named members and officers, their treasuries and stores, money held, wages, loans, kin, channels and camp rights. The generator
compiles it (compile, below) into a schedule of round-0 setup interventions, one `establish` op per entry (charter/interventions.py:
recorded in k.w["interventions"], interventions.jsonl and interventions.yaml like any intervention, each with its state diff, in a
cause frame of its own), stored in instance.json as inst["start"]["schedule"]. The runner applies it once, at a fresh start, after
the constitution and the regime's statutes and before spec start_laws; a resume never applies it again. Every name must resolve:
an agent (agents.names should fix them; generator.check_placements fails generation otherwise), an institution declared here (or
J0), a store declared here, an office declared here. `python -m charter spec check` generates the world and reports what does not.

    start:
      rights: {Name: [right, ...]}                    rights at round 0 (a new right is created); "all" for every founder
      currencies: [{name: penny, issuer: J0, backed: true}]    a currency of the issuer (created at round 0)
      institutions:                                   associations (contracts.enabled), in id order A1, A2, ...; and J0 (the polity)
        - id: A1
          name: House Ashby
          founder: Name                               its first member (the contract's founder)
          members: [Name, ...]                        joined at round 0 (whatever its admission)
          admission: closed                           open | closed (default closed)
          procedure: members                          members | two_thirds | founder: how its code changes
          charter: "text"                             what it is for: its first law, a public statement of purpose
          laws: [{template, params} | {code}]         further code (library templates, e.g. Day Labour; or law code)
          offices: {name: {title, holders, duties, controls, powers, seats, term, succession}}   (an Offices Act in its code)
          treasury: {item: qty}
        - id: J0                                      the polity: offices (an Offices Act of J0), treasury, laws
      stores: [{id: S1, owner: J0 | A1 | Name, food: 60, capacity: 150, name: granary}]   in id order S1, S2, ...
      holdings: {Name | A1 | J0 | S1: {item: qty}}    goods (currencies are minted, other items brought into the world)
      wages: [{employer: A1 | Name, worker: Name, item: penny, qty: 2, every: 1}]   an association pays out of its treasury (its
                                                      Wage Roll); an agent by standing order (its allowance)
      loans: [{lender, borrower, item, qty, repay_qty, due_in, rate}]   needs a law that enables loans
      kin: [{parents: [A, B], child: C}]              founding families (life on): children(), heirs and hereditary succession
      channels: [{id, owner, by, purpose, readers, writers, listed, identity, retention, rate, members, subscribers}]
                                                      an id starting with @ changes an existing inbox (e.g. @J0's readers)
      camp_rights: [{resource: copper | camp: camp3, holders: [Name, ...] | members: A1, exclusive: true}]
      laws: [{template, params, rank} | {code}]       J0 laws enacted at round 0, after everything above exists
Offices (charter/institutions.py): duties and controls are read under institutions.office_control; succession clauses under
institutions.succession (an election may name its electorate: a right, e.g. vote, or an office, e.g. J0.council).
"""
from __future__ import annotations

import copy
import re

OP = "establish"
SECTIONS = ("rights", "currencies", "institutions", "stores", "holdings", "wages", "loans", "kin", "channels", "camp_rights", "laws")
INST_KEYS = ("id", "name", "founder", "members", "admission", "procedure", "charter", "laws", "offices", "treasury", "kind")
STORE_KEYS = ("id", "owner", "food", "capacity", "name")
WAGE_KEYS = ("employer", "worker", "item", "qty", "every")
LOAN_KEYS = ("lender", "borrower", "item", "qty", "repay_qty", "due_in", "rate", "repay_item")
KIN_KEYS = ("parents", "parent", "child")
CHANNEL_KEYS = ("id", "owner", "by", "purpose", "readers", "writers", "listed", "identity", "retention", "rate", "members",
                "subscribers")
CAMP_KEYS = ("resource", "camp", "holders", "members", "exclusive")
LAW_KEYS = ("template", "params", "rank", "code")
ASSOC = re.compile(r"^A[1-9][0-9]*$")
STORE_ID = re.compile(r"^S[1-9][0-9]*$")


def on(sp) -> bool:
    return bool((sp or {}).get("start"))


def _block(sp) -> dict:
    return (sp or {}).get("start") or {}


# ---------------------------------------------------------------------- static check (schema.validate)
def check(path, v) -> list:
    """The shape of a start block (names are resolved at generation: compile)."""
    if v is None:
        return []
    if not isinstance(v, dict):
        return [f"{path}: a mapping of {', '.join(SECTIONS)}"]
    errs = [f"{path}.{k}: unknown section (sections: {', '.join(SECTIONS)})" for k in v if k not in SECTIONS]

    def lst(key, fields, need=()):
        x = v.get(key)
        if x is None:
            return []
        if not isinstance(x, list) or not all(isinstance(e, dict) for e in x):
            return [f"{path}.{key}: a list of mappings"]
        out = []
        for i, e in enumerate(x):
            out += [f"{path}.{key}[{i}].{f}: unknown key (keys: {', '.join(fields)})" for f in e if f not in fields]
            out += [f"{path}.{key}[{i}]: needs {f}" for f in need if f not in e]
        return out

    def goods(p, g):
        if not isinstance(g, dict) or not all(isinstance(q, (int, float)) and not isinstance(q, bool) and q >= 0 for q in g.values()):
            return [f"{p}: {{item: quantity >= 0}}"]
        return []

    r = v.get("rights")
    if r is not None and not (isinstance(r, dict) and all(isinstance(x, list) and all(isinstance(y, str) for y in x) for x in r.values())):
        errs.append(f"{path}.rights: {{Name: [right, ...]}}")
    errs += lst("currencies", ("name", "issuer", "backed"), ("name",))
    errs += lst("institutions", INST_KEYS, ("id",))
    for i, e in enumerate(v.get("institutions") or () if isinstance(v.get("institutions"), list) else ()):
        if not isinstance(e, dict):
            continue
        q = f"{path}.institutions[{i}]"
        iid = e.get("id")
        if iid != "J0" and not (isinstance(iid, str) and ASSOC.match(iid)):
            errs.append(f"{q}.id: J0 or an association id A1, A2, ... (in order)")
        if iid != "J0" and not e.get("founder"):
            errs.append(f"{q}: an association needs a founder")
        if e.get("admission") not in (None, "open", "closed"):
            errs.append(f"{q}.admission: open or closed")
        if e.get("procedure") not in (None, "members", "two_thirds", "founder"):
            errs.append(f"{q}.procedure: members, two_thirds or founder")
        if "offices" in e and not isinstance(e["offices"], dict):
            errs.append(f"{q}.offices: {{name: {{title, holders, duties, controls, powers, seats, term, succession}}}}")
        if "treasury" in e:
            errs += goods(f"{q}.treasury", e["treasury"])
        errs += _check_laws(f"{q}.laws", e.get("laws"))
    errs += lst("stores", STORE_KEYS, ("id", "owner"))
    h = v.get("holdings")
    if h is not None:
        if not isinstance(h, dict):
            errs.append(f"{path}.holdings: {{Name | institution | store: {{item: qty}}}}")
        else:
            for a, g in h.items():
                errs += goods(f"{path}.holdings.{a}", g)
    errs += lst("wages", WAGE_KEYS, ("employer", "worker", "qty"))
    errs += lst("loans", LOAN_KEYS, ("lender", "borrower", "item", "qty"))
    errs += lst("kin", KIN_KEYS, ("child",))
    errs += lst("channels", CHANNEL_KEYS, ("id",))
    errs += lst("camp_rights", CAMP_KEYS)
    errs += _check_laws(f"{path}.laws", v.get("laws"))
    return errs


def _check_laws(p, laws) -> list:
    from charter import library as LB
    if laws is None:
        return []
    if not isinstance(laws, list):
        return [f"{p}: a list of {{template, params}} or {{code}}"]
    out = []
    for i, e in enumerate(laws):
        if not isinstance(e, dict) or not (("template" in e) ^ ("code" in e)):
            out.append(f"{p}[{i}]: {{template, params, rank}} or {{code}}")
            continue
        out += [f"{p}[{i}].{f}: unknown key" for f in e if f not in LAW_KEYS]
        t = e.get("template")
        if t is not None and t not in LB.LIB and t not in LB.v2_templates():
            out.append(f"{p}[{i}].template: unknown law template {t!r}")
    return out


# ---------------------------------------------------------------------- names (generator.check_placements)
def _inst_ids(b) -> set:
    return {e.get("id") for e in b.get("institutions") or () if isinstance(e, dict)} | {"J0"}


def _store_ids(b) -> set:
    return {e.get("id") for e in b.get("stores") or () if isinstance(e, dict)}


def _is_account(b, x) -> bool:
    x = str(x)
    return x in _inst_ids(b) or x in _store_ids(b) or x.startswith("store:") or x in ("world", "reserve")


def placed_names(sp: dict) -> list:
    """Every agent name the start block names, as (path, name)."""
    b = _block(sp)
    if not isinstance(b, dict):
        return []
    out = []
    add = lambda p, n: out.append((f"start.{p}", str(n)))
    for a in (b.get("rights") or {}) if isinstance(b.get("rights"), dict) else ():
        if a != "all":
            add("rights", a)
    for e in b.get("institutions") or ():
        if not isinstance(e, dict):
            continue
        if e.get("founder"):
            add(f"institutions.{e.get('id')}.founder", e["founder"])
        for m in e.get("members") or ():
            add(f"institutions.{e.get('id')}.members", m)
        for o, d in (e.get("offices") or {}).items() if isinstance(e.get("offices"), dict) else ():
            for h in (d or {}).get("holders") or ():
                if h != "founder":
                    add(f"institutions.{e.get('id')}.offices.{o}", h)
    for e in b.get("stores") or ():
        if isinstance(e, dict) and e.get("owner") is not None and not _is_account(b, e["owner"]):
            add("stores.owner", e["owner"])
    for a in (b.get("holdings") or {}) if isinstance(b.get("holdings"), dict) else ():
        if not _is_account(b, a):
            add("holdings", a)
    for e in b.get("wages") or ():
        if isinstance(e, dict):
            if e.get("employer") is not None and not _is_account(b, e["employer"]):
                add("wages.employer", e["employer"])
            if e.get("worker") is not None:
                add("wages.worker", e["worker"])
    for e in b.get("loans") or ():
        if isinstance(e, dict):
            for f in ("lender", "borrower"):
                if e.get(f) is not None and not _is_account(b, e[f]):
                    add(f"loans.{f}", e[f])
    for e in b.get("kin") or ():
        if isinstance(e, dict):
            for p in list(e.get("parents") or ()) + ([e["parent"]] if e.get("parent") else []):
                add("kin.parents", p)
            if e.get("child"):
                add("kin.child", e["child"])
    for e in b.get("channels") or ():
        if not isinstance(e, dict):
            continue
        for f in ("owner", "by"):
            if e.get(f) is not None and not _is_account(b, e[f]):
                add(f"channels.{e.get('id')}.{f}", e[f])
        for f in ("members", "subscribers"):
            for m in e.get(f) or ():
                add(f"channels.{e.get('id')}.{f}", m)
        for f in ("readers", "writers"):
            for m in _selector_agents(e.get(f)):
                add(f"channels.{e.get('id')}.{f}", m)
    for e in b.get("camp_rights") or ():
        if isinstance(e, dict):
            for h in e.get("holders") or ():
                add("camp_rights.holders", h)
    return out


def granted_rights(sp) -> set:
    """The rights start.rights grants to someone (generator.validate: no repair for a missing proposer or voter)."""
    r = _block(sp).get("rights") if isinstance(_block(sp), dict) else None
    return {x for v in (r or {}).values() if isinstance(v, list) for x in v} if isinstance(r, dict) else set()


def _selector_agents(sel) -> list:
    if isinstance(sel, list):
        return [a for x in sel for a in _selector_agents(x)]
    if not isinstance(sel, dict):
        return []
    out = list(sel.get("agents") or ())
    for x in sel.get("any") or ():
        out += _selector_agents(x)
    return out


# ---------------------------------------------------------------------- compile (generation)
def _entry(kind, i, spec, note=None) -> dict:
    return {"id": f"start:{kind}:{i}", "at": {"round": 0, "phase": "setup"}, "op": OP, "args": {"kind": kind, "spec": spec},
            **({"note": note} if note else {})}


def _resolve_members(b, ref) -> list:
    """members: A1 (an institution declared here): its members."""
    for e in b.get("institutions") or ():
        if e.get("id") == ref:
            return list(dict.fromkeys([e["founder"]] + list(e.get("members") or ()))) if e.get("founder") else list(e.get("members") or ())
    raise ValueError(f"start: no institution {ref} declared")


def _offices_code(iid, offices: dict, succession_on: bool) -> str:
    """The Offices Act instantiated with the declaration (checked by institutions.parse_offices)."""
    from charter import institutions as IN
    from charter import lawlang as L
    from charter import library as LB
    decl = {}
    for name, d in offices.items():
        d = dict(d or {})
        decl[name] = {f: d[f] for f in ("title", "powers", "holders", "seats", "term", "duties", "controls", "succession",
                                        "term_calendar")
                      if d.get(f) is not None}
        if not succession_on:
            decl[name].pop("succession", None)
    code = LB.instantiate("Offices Act", {"offices": decl})
    try:
        IN.parse_offices(code, succession_on)
    except L.LawError as e:
        raise ValueError(f"start.institutions.{iid}.offices: {e}")
    return code


def _law_code(p, e) -> tuple:
    """(code, template record or None) of a law entry."""
    from charter import lawlang as L
    from charter import regimes as RG
    try:
        if "template" in e:
            code = RG.template_code(e["template"], e.get("params"), None, e.get("rank"))
            return code, {"name": e["template"], "params": dict(e.get("params") or {}), "rank": e.get("rank")}
        code = str(e["code"])
        L.check(code, v2=True)
        return code, None
    except (L.LawError, KeyError, SyntaxError) as ex:
        raise ValueError(f"{p}: {ex}")


def _charter_code(e) -> str:
    from charter import lawlang as L
    name = str(e.get("name") or e["id"])
    text = " ".join(str(e["charter"]).split())
    code = (f"title = {name + ' Charter'!r}\nintent = {text!r}\n\ndef on_enact():\n"
            f"    public[\"charter\"] = {text!r}\n")
    L.check(code, v2=True)
    return code


def _wage_code(employer, wages) -> str:
    from charter import library as LB
    items = {w.get("item", "penny") for w in wages}
    every = {int(w.get("every", 1)) for w in wages}
    if len(items) > 1 or len(every) > 1:
        raise ValueError(f"start.wages: {employer} pays every wage in one item at one interval (got {sorted(items)}, {sorted(every)})")
    return LB.instantiate("Wage Roll", {"ITEM": items.pop(), "EVERY": every.pop(),
                                        "WAGES": {str(w["worker"]): float(w["qty"]) for w in wages}})


def compile(sp: dict, inst: dict) -> dict:
    """The start block resolved against the world: {"schedule": [interventions], "camp_rights": {resource: [camps]}}.
    Raises ValueError for anything that does not resolve (ids out of order, unknown agents, institutions, stores, offices, camps)."""
    from charter import features as FT
    from charter import succession as SU
    b = copy.deepcopy(_block(sp))
    names = {a["id"] for a in inst["agents"]}
    insts = [e for e in b.get("institutions") or () if e.get("id") != "J0"]
    j0 = [e for e in b.get("institutions") or () if e.get("id") == "J0"]
    if len(j0) > 1:
        raise ValueError("start.institutions: J0 is declared twice")
    for i, e in enumerate(insts):
        if e["id"] != f"A{i + 1}":
            raise ValueError(f"start.institutions: associations take the ids A1, A2, ... in order; {e['id']} is number {i + 1}")
    if insts and not FT.on("contracts", sp):
        raise ValueError("start.institutions: associations need contracts.enabled")
    if any(e.get("offices") for e in insts + j0) and not ((sp.get("institutions") or {}).get("grants")):
        raise ValueError("start.institutions: offices need institutions.grants (and institutions.unified)")
    stores = b.get("stores") or []
    for i, e in enumerate(stores):
        if e["id"] != f"S{i + 1}":
            raise ValueError(f"start.stores: stores take the ids S1, S2, ... in order; {e['id']} is number {i + 1}")
    if stores and not FT.on("subsistence", sp):
        raise ValueError("start.stores: stores need subsistence.enabled")
    accounts = {e["id"] for e in insts} | {"J0"} | {e["id"] for e in stores}

    def agent(p, x):
        if x not in names:
            raise ValueError(f"{p}: no agent {x!r} in this world")
        return x

    def account(p, x):
        x = str(x)
        if x.startswith("store:"):
            x = x[6:]
        if x in accounts or x in names:
            return x
        raise ValueError(f"{p}: {x!r} is neither an agent, an institution nor a store declared in start")

    sched = []
    succ = SU.on_spec(sp)
    for a, rs in (b.get("rights") or {}).items():
        sched.append(_entry("rights", len(sched), {"agents": sorted(names) if a == "all" else [agent("start.rights", a)],
                                                    "rights": list(rs)}))
    for i, c in enumerate(b.get("currencies") or ()):
        sched.append(_entry("currency", i, {"name": str(c["name"]), "issuer": account("start.currencies", c.get("issuer", "J0")),
                                            "backed": bool(c.get("backed", True))}))
    wages = b.get("wages") or []
    by_emp: dict = {}
    for w in wages:
        agent("start.wages.worker", w["worker"])
        emp = account("start.wages.employer", w["employer"])
        if emp in names:
            continue
        if emp not in {e["id"] for e in insts}:
            raise ValueError(f"start.wages: employer {emp} is not an association declared in start (or an agent)")
        by_emp.setdefault(emp, []).append(w)
    for e in insts:
        iid = e["id"]
        founder = agent(f"start.institutions.{iid}.founder", e["founder"])
        members = [agent(f"start.institutions.{iid}.members", m) for m in e.get("members") or ()]
        members = [m for m in dict.fromkeys(members) if m != founder]
        codes, tpls = [], []
        if e.get("charter"):
            codes.append(_charter_code(e))
            tpls.append(None)
        for j, le in enumerate(e.get("laws") or ()):
            c, t = _law_code(f"start.institutions.{iid}.laws[{j}]", le)
            codes.append(c)
            tpls.append(t)
        offices = e.get("offices") or {}
        holders = {}
        if offices:
            for o, d in offices.items():
                for h in (d or {}).get("holders") or ():
                    if h != "founder":
                        agent(f"start.institutions.{iid}.offices.{o}", h)
                        if h != founder and h not in members:
                            raise ValueError(f"start.institutions.{iid}.offices.{o}: {h} holds an office of {iid} but is not a member")
                holders[o] = [founder if h == "founder" else h for h in (d or {}).get("holders") or ()]
            codes.append(_offices_code(iid, offices, succ))
            tpls.append({"name": "Offices Act", "params": {"offices": "(start)"}, "rank": None})
        if iid in by_emp:
            for w in by_emp[iid]:
                if w["worker"] != founder and w["worker"] not in members:
                    raise ValueError(f"start.wages: {w['worker']} is paid by {iid} but is not a member")
            codes.append(_wage_code(iid, by_emp[iid]))
            tpls.append({"name": "Wage Roll", "params": None, "rank": None})
        if not codes:
            raise ValueError(f"start.institutions.{iid}: an association needs code (a charter, laws, offices or wages)")
        sched.append(_entry("institution", iid, {"id": iid, "name": str(e.get("name") or iid), "founder": founder,
                                                  "members": members, "admission": e.get("admission") or "closed",
                                                  "procedure": e.get("procedure"), "codes": codes, "templates": tpls,
                                                  "holders": holders}))
    for e in j0:
        if e.get("offices"):
            holders = {}
            for o, d in e["offices"].items():
                holders[o] = [agent(f"start.institutions.J0.offices.{o}", h) for h in (d or {}).get("holders") or ()]
            sched.append(_entry("polity_offices", "J0", {"id": "J0", "code": _offices_code("J0", e["offices"], succ),
                                                         "holders": holders}))
        for j, le in enumerate(e.get("laws") or ()):
            c, t = _law_code(f"start.institutions.J0.laws[{j}]", le)
            sched.append(_entry("law", f"J0.{j}", {"code": c, "template": t}))
    for e in stores:
        sched.append(_entry("store", e["id"], {"id": e["id"], "owner": account(f"start.stores.{e['id']}.owner", e["owner"]),
                                               "capacity": e.get("capacity"), "name": e.get("name")}))
    for e in insts + j0:
        for item, q in (e.get("treasury") or {}).items():
            sched.append(_entry("holding", f"{e['id']}.{item}", {"account": e["id"], "item": str(item), "qty": float(q)}))
    for e in stores:
        if e.get("food"):
            sched.append(_entry("holding", f"{e['id']}.food", {"account": f"store:{e['id']}", "item": "food", "qty": float(e["food"])}))
    for a, g in (b.get("holdings") or {}).items():
        acc = account("start.holdings", a)
        acc = f"store:{acc}" if acc in {s["id"] for s in stores} else acc
        for item, q in g.items():
            sched.append(_entry("holding", f"{acc}.{item}", {"account": acc, "item": str(item), "qty": float(q)}))
    for i, w in enumerate(wages):
        if w["employer"] in names:
            sched.append(_entry("standing_wage", i, {"employer": w["employer"], "worker": w["worker"], "item": w.get("item", "penny"),
                                                     "qty": float(w["qty"]), "every": int(w.get("every", 1))}))
    for i, ln in enumerate(b.get("loans") or ()):
        sched.append(_entry("loan", i, {**{f: ln[f] for f in LOAN_KEYS if f in ln}, "lender": account("start.loans", ln["lender"]),
                                        "borrower": agent("start.loans.borrower", ln["borrower"])}))
    for i, e in enumerate(b.get("kin") or ()):
        ps = [agent("start.kin", p) for p in (list(e.get("parents") or ()) + ([e["parent"]] if e.get("parent") else []))]
        if not 1 <= len(ps) <= 2:
            raise ValueError("start.kin: one or two parents")
        sched.append(_entry("kin", i, {"parents": ps, "child": agent("start.kin.child", e["child"])}))
    camp_map = {}
    for i, e in enumerate(b.get("camp_rights") or ()):
        if ("camp" in e) == ("resource" in e):
            raise ValueError("start.camp_rights: give a camp or a resource")
        if "camp" in e:
            camps = [c["id"] for c in inst["camps"] if c["id"] == e["camp"]]
        else:
            camps = [c["id"] for c in inst["camps"] if c.get("resource") == e["resource"] and not c.get("open")
                     and c.get("role") != "subsistence"]
            camp_map[e["resource"]] = camps
        if not camps:
            raise ValueError(f"start.camp_rights: no camp {e.get('camp') or 'producing ' + str(e.get('resource'))} that takes a "
                             "harvest right in this world")
        hs = [agent("start.camp_rights.holders", h) for h in e.get("holders") or ()]
        if e.get("members"):
            hs += _resolve_members(b, e["members"])
        sched.append(_entry("camp_rights", i, {"camps": camps, "holders": list(dict.fromkeys(hs)),
                                               "exclusive": bool(e.get("exclusive", False))}))
    for e in b.get("channels") or ():
        cid = str(e["id"])
        spec = {f: e[f] for f in CHANNEL_KEYS if f in e}
        if "owner" in spec:
            spec["owner"] = account(f"start.channels.{cid}.owner", spec["owner"])
        if "by" in spec:
            spec["by"] = agent(f"start.channels.{cid}.by", spec["by"])
        for f in ("members", "subscribers"):
            spec[f] = [agent(f"start.channels.{cid}.{f}", m) for m in spec.get(f) or ()]
        if not cid.startswith("@") and "owner" not in spec:
            raise ValueError(f"start.channels.{cid}: needs an owner")
        sched.append(_entry("channel", cid, spec))
    for j, le in enumerate(b.get("laws") or ()):
        c, t = _law_code(f"start.laws[{j}]", le)
        sched.append(_entry("law", j, {"code": c, "template": t}))
    from charter import interventions as IV
    sched = IV.load_schedule(sched)                                     # the schedule's own checks (ids, op, phase)
    return {"schedule": sched, **({"camp_rights": camp_map} if camp_map else {})}


def schedule(inst: dict) -> list:
    """The start schedule of an instance (runner: applied once at a fresh start)."""
    return list(((inst.get("start") or {}).get("schedule")) or [])


# ---------------------------------------------------------------------- the establish op (applied by interventions.apply_due)
def _ops():
    from charter import interventions as IV

    @IV.op(OP, phases=("setup",), args={"kind": "str", "spec": "dict"})
    def _establish(k, inst, rs, kind, spec):
        """Round-0 establishment from spec `start` (charter/start.py): one entry of the start block."""
        fn = HANDLERS.get(kind)
        if fn is None:
            raise IV.InterventionError(f"establish: unknown kind {kind}")
        return fn(k, inst, spec) or {}
    return _establish


def _fail(msg):
    from charter import interventions as IV
    return IV.InterventionError(msg)


def _grant(k, aid, right, lid=None):
    if right not in k.w["rights"]:
        k.apply("create_right", right=right)
    if right in k.w["agents"][aid]["rights"]:
        return
    out = k.apply("grant_right", agent=aid, right=right, **({"lid": lid} if lid else {}))
    if not out.ok or right not in k.w["agents"][aid]["rights"]:
        raise _fail(f"could not grant {right} to {aid}" + (f" ({out.reason})" if getattr(out, "reason", None) else ""))


def h_rights(k, inst, spec):
    from charter import rights as RT
    for aid in spec["agents"]:
        for r in spec["rights"]:
            r = k.norm_right(r)
            if r in RT.ENTRENCHED:
                raise _fail(f"start.rights: {r} is entrenched (a class right): choose the agent's class instead")
            _grant(k, aid, r)
    return {"granted": {a: spec["rights"] for a in spec["agents"]}}


def h_currency(k, inst, spec):
    from charter import accounts as AC
    name = spec["name"]
    if name in k.w["currencies"]:
        raise _fail(f"currency {name} exists")
    out = k.apply("create_currency", name=name, backed=spec["backed"], reserve=AC.treasury_of(k, spec["issuer"]))
    if not out.ok:
        raise _fail(f"could not create {name}")
    k.w["currencies"][name].setdefault("issuer", spec["issuer"])
    return {"currency": name}


def h_institution(k, inst, spec):
    from charter import contracts as KC
    from charter import lawlang as L
    iid = spec["id"]
    if f"A{k.w['contracts']['seq'] + 1}" != iid:
        raise _fail(f"{iid} would not be the next association id (A{k.w['contracts']['seq'] + 1})")
    try:
        KC.act_create_contract(k, spec["founder"], name=spec["name"], code=list(spec["codes"]), admission=spec["admission"])
    except L.LawError as e:
        raise _fail(f"founding {iid}: {e}")
    rec = KC.recs(k)[iid]
    for lid, t in zip(rec["laws"], spec.get("templates") or ()):
        if t is not None:
            k.w["laws"][lid]["template"] = copy.deepcopy(t)
    for m in spec["members"]:
        out = k.apply("join", agent=m, polity=iid, via="start")
        if m not in KC.recs(k)[iid]["members"]:
            raise _fail(f"{m} could not join {iid}" + (f" ({out.reason})" if getattr(out, "reason", None) else ""))
    if spec.get("procedure"):
        rec["procedure"] = spec["procedure"]
    offices_lid = rec["laws"][-1] if spec.get("holders") else None
    for i, t in enumerate(spec.get("templates") or ()):
        if t and t.get("name") == "Offices Act":
            offices_lid = rec["laws"][i]
    for o, hs in (spec.get("holders") or {}).items():
        for h in hs:
            _grant(k, h, f"{iid}.{o}", offices_lid)
    return {"institution": iid, "laws": list(rec["laws"]), "members": list(KC.recs(k)[iid]["members"])}


def h_polity_offices(k, inst, spec):
    lid = k.new_law(spec["code"], "constitution")
    k.w["laws"][lid]["template"] = {"name": "Offices Act", "params": {"offices": "(start)"}, "rank": None}
    k.enact(lid)
    if k.w["laws"][lid]["status"] != "active":
        raise _fail(f"the Offices Act of J0 did not come into force ({k.w['laws'][lid]['status']})")
    for o, hs in spec["holders"].items():
        for h in hs:
            _grant(k, h, f"J0.{o}", lid)
    return {"law": lid}


def h_law(k, inst, spec):
    lid = k.new_law(spec["code"], "constitution")
    if spec.get("template"):
        k.w["laws"][lid]["template"] = copy.deepcopy(spec["template"])
    k.enact(lid)
    if k.w["laws"][lid]["status"] != "active":
        raise _fail(f"law {lid} did not come into force ({k.w['laws'][lid]['status']})")
    return {"law": lid}


def h_store(k, inst, spec):
    from charter import subsistence as SB
    if not SB.on(k):
        raise _fail("stores need subsistence")
    st = SB.state(k)
    sid = spec["id"]
    if sid in st["stores"] or f"S{st['seq'] + 1}" != sid:
        raise _fail(f"{sid} would not be the next store id (S{st['seq'] + 1})")
    owner = spec["owner"]
    cap = float(spec["capacity"] if spec.get("capacity") is not None else SB.cfg(k.spec)["store"]["capacity"])
    st["seq"] += 1
    st["stores"][sid] = {"id": sid, "owner": owner, "capacity": cap, "built": k.r, "builder": None, "holdings": {},
                         **({"name": str(spec["name"])} if spec.get("name") else {})}
    label = f" ({spec['name']})" if spec.get("name") else ""
    k.log("store_built", None, {"store": sid, "owner": owner, "capacity": cap,
                                "text": f"Store {sid}{label} stands, owned by {owner} (it holds up to {cap:g} food)."}, vis="public")
    return {"store": sid}


def h_holding(k, inst, spec):
    from charter import accounts as AC
    from charter import interventions as IV
    acc = spec["account"]
    if acc == "J0" or acc in AC.assocs(k):
        acc = AC.treasury_of(k, acc)
    if acc.startswith("store:"):
        from charter import subsistence as SB
        s = SB.state(k)["stores"].get(acc[6:])
        if s is None:
            raise _fail(f"no store {acc}")
        if spec["item"] != "food":
            raise _fail("a store holds food only")
        if float(s["holdings"].get("food", 0.0)) + spec["qty"] > float(s["capacity"]) + 1e-9:
            raise _fail(f"store {acc[6:]} holds at most {s['capacity']:g} food")
    IV.OPS["mint"].fn(k, inst, None, item=spec["item"], qty=spec["qty"], to=acc)
    return {"account": acc, "item": spec["item"], "qty": spec["qty"]}


def h_standing_wage(k, inst, spec):
    from charter import contracts as KC
    from charter import lawlang as L
    try:
        out = KC.act_standing_order(k, spec["employer"], spec["worker"], spec["item"], spec["qty"], every=spec["every"],
                                    name=f"wage of {spec['worker']}")
    except L.LawError as e:
        raise _fail(f"wage {spec['employer']} -> {spec['worker']}: {e}")
    return {"result": out}


def h_loan(k, inst, spec):
    from charter import credit as CR
    from charter import lawlang as L
    try:
        CR.lend(k, spec["lender"], spec["borrower"], spec["item"], spec["qty"], repay_qty=spec.get("repay_qty"),
                due_in=int(spec.get("due_in", 5)), repay_item=spec.get("repay_item"), rate=float(spec.get("rate", 0.0)))
        lid = f"N{k.w['loan_seq']}"
        CR.accept(k, spec["borrower"], lid)
    except L.LawError as e:
        raise _fail(f"loan {spec['lender']} -> {spec['borrower']}: {e}")
    return {"loan": lid}


def h_kin(k, inst, spec):
    life = k.w.get("life")
    if life is None:
        raise _fail("kin needs life.enabled")
    c, ps = spec["child"], list(spec["parents"])
    if c in ps:
        raise _fail(f"{c} cannot be its own parent")
    life.setdefault("parent", {})[c] = ps[0]
    if len(ps) == 2:
        life.setdefault("parents", {})[c] = ps
    k.log("kin", None, {"child": c, "parents": ps, "text": f"{c} is the child of {' and '.join(ps)}."}, vis="public")
    return {"child": c, "parents": ps}


def h_camp_rights(k, inst, spec):
    for cid in spec["camps"]:
        right = f"harvest:{cid}"
        if spec["exclusive"]:
            for aid, a in sorted(k.w["agents"].items()):
                if right in a["rights"] and aid not in spec["holders"]:
                    k.apply("revoke_right", agent=aid, right=right)
        for h in spec["holders"]:
            _grant(k, h, right)
    return {"camps": spec["camps"], "holders": spec["holders"]}


def h_channel(k, inst, spec):
    from charter import channels as CH
    from charter.actions import ActionError
    if not CH.active(k):
        raise _fail("channels need channels.v2")
    CH.sync(k)
    cid = spec["id"]
    extra = CH.extra_selectors(k)
    try:
        sel = {f: CH.check_selector(spec[f], f, extra) for f in ("readers", "writers") if f in spec}
    except ActionError as e:
        raise _fail(f"channel {cid}: {e}")
    if cid.startswith("@"):
        ch = k.w["channels"].get(cid)
        if ch is None:
            raise _fail(f"no inbox {cid}")
        for f in ("purpose", "listed", "identity", "retention", "rate"):
            if f in spec:
                ch[f] = spec[f]
        for f, v in sel.items():
            ch[f] = v
            if f == "writers":
                ch["open"] = v == {"all": True}
        k.log("channel_set", None, {"channel": cid, "key": "start", "value": {f: spec[f] for f in spec if f != "id"}},
              vis=f"channel:{cid}")
    else:
        if cid in k.w["channels"]:
            raise _fail(f"channel {cid} exists")
        owner = spec["owner"]
        by = spec.get("by") or (owner if owner in k.w["agents"] else None)
        if by is None:
            from charter import institutions as IN
            by = next(iter(IN.officers(k, owner) or IN.members(k, owner) or ()), None)
            if by is None:
                raise _fail(f"channel {cid}: nobody to open it for {owner} (give `by`)")
        readers = sel.get("readers", {"all": True})
        writers = sel.get("writers", {"all": True})
        settings = {"purpose": str(spec.get("purpose") or "")[:200], "readers": readers, "writers": writers,
                    "listed": bool(spec.get("listed", True)), "identity": spec.get("identity", "named"),
                    "retention": spec.get("retention", "all"), "rate": spec.get("rate"), "owner": owner}
        mem = sorted(set(spec.get("members") or ()))
        k.apply("found", agent=by, polity=cid, kind="channel", members=mem, open=writers == {"all": True}, settings=settings)
        if cid not in k.w["channels"]:
            raise _fail(f"channel {cid} was not opened")
    ch = k.w["channels"][cid]
    for a in spec.get("subscribers") or ():
        if a not in ch["subscribers"]:
            ch["subscribers"].append(a)
            ch["since"][a] = len(k.events)
            if a not in ch["known"]:
                ch["known"].append(a)
    if spec.get("subscribers"):
        k.log("channel_subscribed", None, {"channel": cid, "agents": list(spec["subscribers"]), "on": True, "by": "start"},
              vis=sorted(spec["subscribers"]))
    return {"channel": cid}


HANDLERS = {"rights": h_rights, "currency": h_currency, "institution": h_institution, "polity_offices": h_polity_offices,
            "law": h_law, "store": h_store, "holding": h_holding, "standing_wage": h_standing_wage, "loan": h_loan, "kin": h_kin,
            "camp_rights": h_camp_rights, "channel": h_channel}
_ops()


# ---------------------------------------------------------------------- lived checks (docs/review/27 §7.2), on a run directory
def _kernel_at(run, n: int):
    """The kernel after the per-round checkpoint n (0: after the setup, before round 1), under the run's frozen settings."""
    import json
    from pathlib import Path
    from charter import runner
    from charter.kernel import Kernel
    run = Path(run)
    inst = json.loads((run / "instance.json").read_text())
    idx = json.loads((run / runner.CKPT_DIR / "index.json").read_text())
    key = (str(run), n)
    if key not in _CK:
        _CK.clear()
        _CK[key] = runner.load_checkpoint(run, run / runner.CKPT_DIR / idx[str(n)]["file"])
    k = Kernel(inst)
    k.restore_state(copy.deepcopy(_CK[key]["kernel"]))
    return inst, k, sorted(int(x) for x in idx)


_CK: dict = {}


def lived(run) -> list:
    """The "lived institution" checks of a run whose spec has a start block: [{check, ok, detail}]. At round 0 (after the setup):
    every office has a living holder whose turn shows the office and its duties; every start channel has readers and writers and
    each office its selectors name can use it; a store an office controls can be drawn from by that office's holders only. Over the
    run: wages paid, the levy collected, channel subscribers and posts, elections at the terms' ends, withdrawals by holder, and the
    food curve before and after a scheduled shock."""
    import copy
    import json
    from pathlib import Path
    from charter import agents as AG
    from charter import channels as CH
    from charter import institutions as IN
    from charter import settings as ST
    from charter import subsistence as SB
    from charter import actions as AC_
    from charter.actions import ActionError
    run = Path(run)
    out = []
    add = lambda name, ok, detail: out.append({"check": name, "ok": bool(ok), "detail": detail})
    inst = json.loads((run / "instance.json").read_text())
    events = [json.loads(x) for x in (run / "events.jsonl").read_text().splitlines() if x.strip()]
    sp = inst["spec"]
    b = _block(sp)
    with ST.use(inst.get("settings")):
        _, k0, rounds = _kernel_at(run, 0)
        _, k1, _ = _kernel_at(run, rounds[-1])
        # 1. offices: a living holder, shown the office and its duties
        for iid, offs in sorted((k0.w.get(IN.OFFICES) or {}).items()):
            for name, o in offs.items():
                hs = IN.holders(k0, iid, name)
                views = {h: AG.state_view(k0, h) for h in hs}
                shown = all(f"Your office: {o['title']}" in v and (not o.get("duties") or o["duties"][:40] in v) for v in views.values())
                pays = None
                if hs and ("treasury" in (o.get("controls") or ()) or any(g["action"] == "transfer" for g in o.get("grants") or ())):
                    from charter import accounts as AC                  # the office pays out of the treasury; a plain member cannot
                    k2 = _kernel_at(run, 0)[1]
                    pool = AC.holdings(k2, AC.treasury_of(k2, iid))
                    item = next((i for i, q in sorted(pool.items()) if q >= 1), None)
                    other = next((m for m in IN.members(k2, iid) if not any(m in IN.holders(k2, iid, n2) for n2 in offs)), None)
                    to = next(a for a in k2.players() if a != hs[0])
                    try:
                        IN.pay_as(k2, hs[0], iid, to, item, 1)
                        pays = True
                    except ActionError as ex:
                        pays = f"refused ({ex})"
                    if other is not None and pays is True:
                        try:
                            IN.pay_as(k2, other, iid, to, item, 1)
                            pays = f"a plain member ({other}) could pay too"
                        except ActionError:
                            pass
                add(f"office {iid}.{name}", hs and shown and pays in (None, True),
                    f"holders {hs or 'none'}; shown with duties: {shown}; "
                    + ("" if pays is None else f"pays out of {iid}'s treasury (a plain member cannot): {pays}; ")
                    + f"controls {o.get('controls') or []}; "
                    f"powers {o.get('powers') or []}{' + grants' if o.get('grants') else ''}; succession {(o.get('succession') or {}).get('rule')}")
        # 2. channels: readers, writers, office access, subscribers, use
        players = k0.players()
        posts = {}
        for e in events:
            cid = (e.get("data") or {}).get("channel_id") or (e.get("data") or {}).get("channel")
            if e["type"] in ("channel_post", "dm", "post") and cid:
                posts[cid] = posts.get(cid, 0) + 1
        for c in b.get("channels") or ():
            cid = str(c["id"])
            ch0, ch1 = k0.w["channels"].get(cid), k1.w["channels"].get(cid)
            if ch0 is None:
                add(f"channel {cid}", False, "not opened")
                continue
            rd = [a for a in players if CH.can_read(k0, a, ch0)]
            wr = [a for a in players if CH.can_write(k0, a, ch0)]
            offices = [s["office"] for s in _flat_selectors(ch0["readers"]) + _flat_selectors(ch0["writers"]) if "office" in s]
            office_ok = all(all(CH.can_read(k0, h, ch0) for h in IN.holders(k0, r.split(".", 1)[0], r)) for r in offices)
            subs = len((ch1 or ch0)["subscribers"])
            holders = [h for r in offices for h in IN.holders(k0, r.split(".", 1)[0], r) if h in wr]
            w = (holders or wr or [None])[0]
            reached = None
            if w is not None:                                           # a scripted post by a writer reaches every reader
                k2 = _kernel_at(run, 0)[1]
                try:
                    CH.act_post(k2, w, "lived check", channel=cid)
                    e = k2.events[-1]
                    reached = all(k2.can_see(r, e) for r in rd)
                except ActionError as ex:
                    reached = f"refused ({ex})"
            add(f"channel {cid}", rd and wr and office_ok and reached is True,
                f"owner {ch0['owner']}; readers {len(rd)}, writers {len(wr)}; office holders named in its selectors can use it: "
                f"{office_ok}; a post by {w} reaches every reader: {reached}; subscribers {len(ch0['subscribers'])} at start, "
                f"{subs} at the end; posts during the run {posts.get(cid, 0)}")
        # 3. controlled stores: only the controlling office's holders can draw (tried on a copy of the round-0 world)
        for sid, s in sorted(SB.state(k0)["stores"].items()):
            owner = s["owner"]
            if owner in k0.w["agents"]:
                continue
            ctl = IN.controlling(k0, owner, STORE_PREFIX + sid)
            holders = sorted({h for o in ctl for h in IN.holders(k0, owner, o)})
            could = []
            for a in players:
                k2 = _kernel_at(run, 0)[1]
                try:
                    AC_.act(k2, a, "withdraw", {"store": sid, "qty": 1})
                    could.append(a)
                except ActionError:
                    pass
            drew = sorted({e["agent"] for e in events if e["type"] == "store_withdrawal" and e["data"].get("store") == sid})
            add(f"store {sid} ({owner})", (could == holders) if ctl else True,
                f"controlled by {', '.join(owner + '.' + o for o in ctl) or 'no office (any officer)'}; holders {holders}; agents able "
                f"to withdraw at round 0: {could}; withdrew during the run: {drew or 'nobody'}")
        # 4. wages and levies: law moves
        laws = k1.w["laws"]
        for lid, rec in sorted(laws.items(), key=lambda kv: int(kv[0][1:]) if kv[0][1:].isdigit() else 0):
            t = (rec.get("template") or {}).get("name") or ""
            if t == "Wage Roll" or (rec.get("code") or "").startswith('title = "Wage Roll"'):
                pays = [e for e in events if e["type"] == "move" and e["data"].get("why") == f"law:{lid}"]
                rounds_paid = sorted({e["round"] + 1 for e in pays})
                owed = (rec.get("public") or {}).get("owed") or {}
                add(f"wages {lid}", rounds_paid, f"{len(pays)} payments in {len(rounds_paid)} rounds "
                    f"({rounds_paid[:3]}..{rounds_paid[-2:]}); {round(sum(e['data']['qty'] for e in pays), 2)} paid in all; "
                    f"owed at the end: {owed or 'nothing'}")
            if t == "Payment Levy":
                got = [e for e in events if e["type"] == "move" and e["data"].get("why") == f"charge:{lid}"]
                add(f"levy {lid}", got, f"{len(got)} charges, {round(sum(e['data']['qty'] for e in got), 2)} "
                    f"{(got[0]['data']['item'] if got else '')} collected in {len({e['round'] for e in got})} rounds")
        # 5. elections: vacancies at the end of a term, ballots, fills
        vac = [(e["round"] + 1, e["data"]["institution"] + "." + e["data"]["office"], e["data"]["from"]) for e in events
               if e["type"] == "office_vacant" and e["data"].get("cause") == "term"]
        filled = [(e["round"] + 1, e["data"]["institution"] + "." + e["data"]["office"], e["agent"], e["data"].get("rule"))
                  for e in events if e["type"] == "office_filled"]
        ballots = [(e["round"] + 1, e["data"]["question"][:60]) for e in events if e["type"] == "ballot_open"
                   and str(e["data"].get("question", "")).startswith("Elect")]
        add("elections", vac and ballots, f"term ends {sorted({(r, o) for r, o, _ in vac})}; election ballots opened in rounds "
            f"{sorted({r for r, _ in ballots})}; filled {filled}")
        # 6. food: before and after the first scheduled shock
        rows = [e["data"] for e in events if e["type"] == "subsistence_round"]
        shocks = (SB.cfg(sp).get("shocks") or [])
        cut = int(shocks[0]["round"]) if shocks else None
        if rows and cut:
            def share(rs):
                n = sum(sum(r["stages"].values()) for r in rs) or 1
                return round(sum(r["stages"].get("hungry", 0) + r["stages"].get("starving", 0) for r in rs) / n, 3)
            pre, post = [r for r in rows if r["round"] + 1 <= cut], [r for r in rows if r["round"] + 1 > cut]
            deaths = [(r["round"] + 1, d) for r in rows for d in r.get("deaths") or ()]
            per = lambda rs: round(sum((r["food"] + r.get("stored", 0)) / max(1, sum(r["stages"].values())) for r in rs) / max(1, len(rs)), 2)
            add("food before/after the shock", share(pre) <= 0.1 and share(post) > share(pre),
                f"hungry-or-starving share of agent-rounds: rounds 1-{cut} {share(pre)}, after {share(post)}; food per head (hand + "
                f"stores) {per(pre)} -> {per(post)}; starvation deaths {deaths or 'none'}")
    return out


STORE_PREFIX = "store:"


def _flat_selectors(sel) -> list:
    if isinstance(sel, list):
        return [x for s in sel for x in _flat_selectors(s)]
    if not isinstance(sel, dict):
        return []
    out = [{k: v} for k, v in sel.items() if k != "any"]
    for x in sel.get("any") or ():
        out += _flat_selectors(x)
    return out


def lived_text(run) -> str:
    rows = lived(run)
    return "\n".join(f"[{'ok' if r['ok'] else 'NO'}] {r['check']}: {r['detail']}" for r in rows) + \
        f"\n{sum(r['ok'] for r in rows)}/{len(rows)} checks pass"
