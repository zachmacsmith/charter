"""The default code (review 12 §3 and WP3; ARCHITECTURE D-25, D-30): today's hard-coded social rules as Acts a regime seeds, which
agents read and may amend or repeal like any law. Spec flag `code.enabled` (default off: nothing here runs, every world is
byte-identical to before).

An Act (charter/code/<act>.py, registered in ACTS) is
  (a) law-language source: the text agents read (read_law A1) and may amend. A store-based Act's text is a few top-level constants
      (LIMIT = 3, ...) with an intent that says what each sets; its parameters are those constants.
  (b) a native twin: Python the kernel runs while the Act is unamended, charged no gas and logging nothing agents see. For a
      store-based Act the twin is twin_rows(): the constants, statically parsed and checked, become rows of the rule store.
Amending an Act (the amend primitive: an agent's `amend`, a Fixer's patch) switches it to its source: it joins the enactment order as
ordinary law code (its hooks run, it is metered) and the store is refilled from the constants its loaded module defines
(source_rows). Repealing an Act empties its rows: every seam then reads the Act's residual rule (review 12 §3: liberty, natural
perception, no offices). tests/test_charter_code.py runs each Act's source as law code against its twin on scripted scenarios.

The rule store (store-based Acts: review 12 §3 "rule stores first, hooks second"; the model is courts' court_rules):
  k.w["default_code"] = {"code": <selection name>, "acts": {Act name: law id}, "store": {polity: {Act name: {key: value}}}}
  rule(k, polity, act, key, default)   the seam: what the kernel reads where it used to read a constant or a spec value.
      code off (or a kernel the runner never seeded): `default`, i.e. today's value, unchanged;
      the polity's rows for the Act (else the root polity J0's, where the regime seeds them): rows[key];
      the Act absent (code: none, dropped) or repealed, or a key its amended source no longer sets: the Act's residual.
  start_rule(code_rec, act, key, default)   the same for the few keys read once, at generation (Communications Act OFFICE).

Ids and records. Acts get ids A1..An from their own sequence (the order of the selected code), so agents' law ids (L1, ...) never
shift. Each is a law record in k.w["laws"] with author "code", template {name, params, rank}, rank (the Act's), `code_act` True and
`native` True until amended or repealed. A native Act is in force (status "active") but not in k.w["law_order"]: no hook loop,
snapshot or legal count sees it, which is what keeps code: today byte-identical to code off. laws_in_force(k) adds native Acts to
k.active_laws() where a law is looked up to be repealed. Seeding logs one monitor-only `code_act` record per Act at round 0, before
the constitution (difftest --ignore-code-acts drops them and renumbers event ids).

Selecting a code: regimes.FIELDS["code"] (a regime's `code:`), else spec code.select; validated by schema (check_selection).
  today            every registered Act with today's parameters (Act.today(spec): the spec values the kernel used to read)
  none             no Act: the residual everywhere (review 12: state_of_nature)
  {Act: params | null, ...}   today's code with these changes: null drops the Act, {CONSTANT: value} overrides its constants
The resolved selection is recorded at generation as inst["code"] = {"name", "acts": [{id, name, rank, params, code}]} (only when
code.enabled), so a run's code is fixed by its instance.

Agents' view (only with code.enabled; D7): state_view lists the Acts with the laws in force and gives one line per Act (prompt_lines);
read_law marks an Act as default code; the legal digest (law.v2, law.digest) has a "default code" line; previews show store changes.
docs/default_code.md has the template and checklist for writing the next Acts.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Callable

from charter import lawlang as L

ROOT = "J0"                         # the polity the regime seeds the code in (jurisdictions off: the only one)
EVENT = "code_act"                  # the monitor-only record of an Act's enactment, switch to source, or repeal
AUTHOR = "code"
SELECTIONS = ("today", "none")
FIXED = ("title", "intent", "rank", "exports")


@dataclass(frozen=True)
class Act:
    """One Act of the default code. See docs/default_code.md for the template."""
    name: str                                   # the law's title, and its key in ACTS and in the store
    rank: str                                   # its rank (dispatch.RANKS): statute, constitution or charter
    source: str                                 # law-language text with today's constants as written (params replace them)
    keys: dict                                  # {CONSTANT: store key}: the parameters, and the store rows they set
    residual: dict                              # {store key: value} the seams read when the Act is absent or repealed
    today: Callable                             # spec -> {CONSTANT: value}: today's parameters (the values the kernel read)
    check: Callable                             # (key, value, spec) -> the checked value; raises lawlang.LawError
    describe: Callable                          # ({key: value}) -> one line for the prompt and the digest
    covers: tuple = ()                          # review 12 inventory rows it carries (charter/tiers.py RULE ids)
    seams: tuple = ()                           # "module:qualname" where the kernel reads its rows
    start: tuple = ()                           # store keys read once, at generation (start_rule), not at run time
    doc: str = ""
    when: Callable | None = None                # spec -> bool: selected only in worlds where it holds (None: always; the Press Act:
                                                # channels.v2), so no other world's code or Act ids change

    def __post_init__(self):
        tree = L.check(self.source)
        consts = _constants(tree)
        missing = [c for c in self.keys if c not in consts]
        assert not missing, f"{self.name}: constants {missing} are not top-level constants of its source"
        assert L.header(self.source)[0] == self.name, f"{self.name}: its source's title must be its name"
        assert set(self.residual) == set(self.keys.values()), f"{self.name}: every store key needs a residual"


ACTS: dict[str, Act] = {}


def register(act: Act) -> Act:
    assert act.name not in ACTS, act.name
    ACTS[act.name] = act
    return act


# ---------------------------------------------------------------------- the flag and the selection
def _spec(x) -> dict:
    sp = getattr(x, "spec", None)
    if sp is None and isinstance(x, dict):
        sp = x["spec"] if isinstance(x.get("spec"), dict) else x
    return sp or {}


def enabled(x) -> bool:
    """Spec code.enabled (x: a kernel, an instance or a spec)."""
    return bool((_spec(x).get("code") or {}).get("enabled"))


def selection(sp: dict):
    """The code a world selects: (institutions.grants) its written tree's root `code`; its regime's `code` field, else spec
    code.select, else "today"."""
    from charter import grants as G
    tc = G.written_code(sp)
    if tc is not None:
        return tc
    reg = sp.get("regime")
    if reg is not None:
        from charter import regimes as RG
        try:
            d = RG.definition(reg)[1]
        except (KeyError, ValueError):
            d = {}
        if "code" in d:
            return d["code"]
    sel = (sp.get("code") or {}).get("select")
    return "today" if sel is None else sel


def check_selection(path: str, v) -> list:
    """Schema check of a code selection (regime field `code`, spec code.select)."""
    if v is None or v in SELECTIONS:
        return []
    if isinstance(v, str):
        return [f"{path}: expected today, none or {{Act: params | null}}, got {v!r}; Acts: {', '.join(ACTS)}"]
    if not isinstance(v, dict):
        return [f"{path}: expected today, none or {{Act: params | null}}, got {v!r}"]
    errs = []
    for name, prm in v.items():
        act = ACTS.get(name)
        if act is None:
            errs.append(f"{path}.{name}: no Act {name!r} in the default code; Acts: {', '.join(ACTS)}")
            continue
        if prm is None:
            continue
        if not isinstance(prm, dict):
            errs.append(f"{path}.{name}: expected {{CONSTANT: value}} or null, got {prm!r}")
            continue
        for c, val in prm.items():
            if c not in act.keys:
                errs.append(f"{path}.{name}.{c}: {name} has no constant {c}; it has {', '.join(act.keys)}")
                continue
            try:
                act.check(act.keys[c], val, {})
            except L.LawError as e:
                errs.append(f"{path}.{name}.{c}: {e}")
    return errs


def resolve(sp: dict) -> dict | None:
    """The instance's code record (generation; None with code off): the selected Acts in order, with ids, parameters and code."""
    if not enabled(sp):
        return None
    sel = selection(sp)
    errs = check_selection("code", sel)
    if errs:
        raise ValueError("; ".join(errs))
    if sel == "none":
        chosen, name = [], "none"
    else:
        over = sel if isinstance(sel, dict) else {}
        chosen = [(a, {**a.today(sp), **(over.get(a.name) or {})}) for a in ACTS.values()
                  if not (a.name in over and over[a.name] is None) and (a.when is None or a.when(sp))]
        name = "today" if not over else "today+custom"
    acts = []
    for i, (a, params) in enumerate(chosen, 1):
        code = set_params(a, params)
        acts.append({"id": f"A{i}", "name": a.name, "rank": a.rank, "params": dict(params), "code": code})
    return {"name": name, "acts": acts}


def set_params(act: Act, params: dict) -> str:
    """The Act's source with its constants set (library.set_constants), each value checked."""
    from charter import library as LB
    for c, v in params.items():
        if c not in act.keys:
            raise L.LawError(f"{act.name} has no constant {c}")
        act.check(act.keys[c], v, {})
    return LB.set_constants(act.source, params, act.name)


# ---------------------------------------------------------------------- the twin and the source
def _constants(tree) -> dict:
    return {n.targets[0].id: n.value for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name) and n.targets[0].id not in FIXED}


def twin_rows(act: Act, code: str, sp: dict | None = None) -> dict:
    """The native twin of a store-based Act: its constants, read statically from its code and checked -> {key: value}."""
    out = {}
    for c, node in _constants(L.check(code)).items():
        if c not in act.keys:
            continue
        try:
            value = ast.literal_eval(node)                              # literals only: a computed constant runs only as law
        except ValueError:
            continue
        out[act.keys[c]] = act.check(act.keys[c], value, sp or {})
    return out


def source_rows(act: Act, ns: dict, sp: dict | None = None) -> dict:
    """The same rows from the Act run as law code: the constants its loaded module (Kernel._load) defines, checked."""
    return {key: act.check(key, ns[c], sp or {}) for c, key in act.keys.items() if c in ns and not callable(ns[c])}


def start_rule(code_rec: dict | None, act: str, key: str, default):
    """A key read once, at generation (before any kernel exists): code off -> default; else the twin's value from the instance's
    code record, or the residual when the Act is absent or does not set it."""
    if code_rec is None:
        return default
    a = ACTS[act]
    rec = next((x for x in code_rec["acts"] if x["name"] == act), None)
    rows = twin_rows(a, rec["code"]) if rec else {}
    return rows.get(key, a.residual[key])


# ---------------------------------------------------------------------- the store and the seam
def store(k) -> dict | None:
    return k.w.get("default_code")


def root(k) -> str:
    """The node the regime seeds the default code in: ROOT ("J0"); institutions.grants: the tree's root (J0 in every preset)."""
    from charter import grants as G
    return G.code_root(k) if G.on(k) else ROOT


def chain(k, polity) -> list:
    """Whose rows a polity reads, in order. Off: its own, then ROOT's. institutions.grants (review 14 §6.2 W8d): its own node, its
    ancestors (parent links, any depth), then the tree nodes marked code_default (the compiled one-node tree marks J0: today);
    after these, the Act's residual. institutions.succession: resolve_clause walks the same chain with each Act's mandatory flag."""
    from charter import grants as G
    if not G.on(k):
        return ([polity] if polity else []) + [ROOT]
    out = G.ancestors(k, polity) if polity else []
    return out + [x for x in G.code_defaults(k) if x not in out]


def rule(k, polity, act: str, key: str, default):
    """The seam: the value of `key` of `act` in `polity` (see the module docstring)."""
    dc = k.w.get("default_code")
    if dc is None:
        return default
    st = dc["store"]
    rows = None
    for x in chain(k, polity):
        rows = (st.get(x) or {}).get(act)
        if rows is not None:
            break
    if rows is None or key not in rows:
        return ACTS[act].residual[key]
    return rows[key]


def governing(k, iid, act: str) -> list:
    """[(node, rows)] for every node in chain(k, iid) holding rows of `act`, nearest first ([] with the code off)."""
    dc = k.w.get("default_code")
    if dc is None:
        return []
    st = dc["store"]
    return [(x, rows) for x in chain(k, iid) if (rows := (st.get(x) or {}).get(act)) is not None]


def resolve_clause(k, iid, act: str, own):
    """institutions.succession (review 14 §7.2): a polity Act against an institution's own clause. Each Act's `mandatory` row says
    whether it applies regardless of the institution's clause (mandatory) or only where the institution declared nothing
    (overridable). The nearest mandatory Act up the chain wins; else the institution's own clause (own, when not None); else the
    nearest Act; else the Act's residual. Returns (source, node, value): ("act", node, rows) | ("own", None, own) |
    ("residual", None, residual rows)."""
    found = governing(k, iid, act)
    a = ACTS[act]
    full = lambda rows: {**a.residual, **rows}
    m = next(((n, r) for n, r in found if r.get("mandatory")), None)
    if m is not None:
        return "act", m[0], full(m[1])
    if own is not None:
        return "own", None, own
    if found:
        return "act", found[0][0], full(found[0][1])
    return "residual", None, dict(a.residual)


def is_act(rec) -> bool:
    return bool(rec and rec.get("code_act"))


def act_of(rec) -> Act:
    return ACTS[(rec.get("template") or {}).get("name") or rec["title"]]


def acts_in_force(k) -> list:
    """Every Act record in force (native or run as source), in id order."""
    dc = k.w.get("default_code")
    if dc is None:
        return []
    laws = k.w["laws"]
    return [laws[i] for i in dc["acts"].values() if laws.get(i, {}).get("status") in ("active", "suspended")]


def native_acts(k) -> list:
    return [r for r in acts_in_force(k) if r.get("native") and r["status"] == "active"]


def laws_in_force(k) -> list:
    """k.active_laws() plus the native Acts (they are in force but not in the enactment order): where a repeal finds its target."""
    return k.active_laws() + native_acts(k) if "default_code" in k.w else k.active_laws()


# ---------------------------------------------------------------------- seeding (round 0, before the constitution)
def seed(k, inst: dict) -> list:
    """Enact the instance's default code: one record per Act (ids A1..), its store rows from the twin, a monitor-only record each.
    Returns the Acts' ids. Nothing happens with code off or without a code record."""
    rec = inst.get("code")
    if not enabled(k) or rec is None:
        return []
    from charter import linker as LK
    v2 = LK.enabled(k)
    node = root(k)
    dc = k.w["default_code"] = {"code": rec["name"], "acts": {}, "store": {node: {}}}
    out = []
    for a in rec["acts"]:
        act = ACTS[a["name"]]
        lid, code = a["id"], a["code"]
        title, intent = L.header(code)
        k.w["laws"][lid] = {"id": lid, "title": title, "intent": intent, "code": code, "cls": L.classify(L.check(code)),
                            "author": AUTHOR, "status": "active", "proposed_round": k.r, "enacted_round": k.r, "state": {},
                            "patches": [], "repeal_target": None, "defines_action": False, "preview": None,
                            "template": {"name": act.name, "params": dict(a["params"]), "rank": a["rank"]}, "rank": a["rank"],
                            "code_act": True, "native": True}
        if v2:
            LK.on_new_law(k, lid)                                     # version 1 and the code store: an amendment's base
        dc["acts"][act.name] = lid
        dc["store"][node][act.name] = twin_rows(act, code, k.spec)
        k.log("code_act", None, {"law": lid, "title": title, "rank": a["rank"], "params": dict(a["params"]), "run": "native"},
              vis="monitor")
        out.append(lid)
    return out


def on_code_changed(k, lid: str) -> None:
    """Kernel: an Act's code was replaced (the amend primitive, dispatch do_amend, after the new code loaded). Its constants are
    checked (a LawError fails the amendment: do_amend restores the old code), then the Act runs as its source: it joins the
    enactment order (among the Acts, before the laws enacted after them) and its rows come from the loaded module."""
    rec = k.w["laws"][lid]
    act = act_of(rec)
    rows = source_rows(act, k.ns[lid], k.spec)
    if rec.get("native"):
        rec["native"] = False
        order = k.w["law_order"]
        acts = list(k.w["default_code"]["acts"].values())
        pos = next((i for i, x in enumerate(order) if x not in acts or acts.index(x) > acts.index(lid)), len(order))
        order.insert(pos, lid)
    k.w["default_code"]["store"].setdefault(root(k), {})[act.name] = rows
    k.log("code_act", None, {"law": lid, "title": rec["title"], "run": "source", "rows": dict(rows)}, vis="monitor")


def on_repeal(k, lid: str) -> None:
    """Kernel (dispatch do_repeal): an Act was repealed. Its rows go (in every polity), so its seams read the residual."""
    rec = k.w["laws"][lid]
    act = act_of(rec)
    rec["native"] = False
    for rows in k.w["default_code"]["store"].values():
        rows.pop(act.name, None)
    k.log("code_act", None, {"law": lid, "title": rec["title"], "run": "repealed"}, vis="monitor")


def switch_to_source(k, lid: str) -> None:
    """Run an Act as its source without changing its code (tests; an intervention): load it and switch, as an amendment would."""
    k._load(lid)
    on_code_changed(k, lid)


# ---------------------------------------------------------------------- what agents see (code.enabled only)
def rows_of(k, act: str) -> dict:
    """The rows in force for an Act (the root polity's), with the residual for keys it does not set."""
    a = ACTS[act]
    return {key: rule(k, root(k), act, key, a.residual[key]) for key in a.residual}


def label(rec) -> str:
    return f"{rec['id']} '{rec['title']}'"


def prompt_lines(k) -> list:
    """One line per Act in force (D7): what it sets now. [] with code off."""
    out = []
    for rec in acts_in_force(k):
        act = act_of(rec)
        how = "default code, inherited" if rec.get("native") else "default code, amended"
        out.append(f"Default code {label(rec)} ({act.rank}; {how}; read_law {rec['id']}, amendable or repealable like any law): "
                   f"{act.describe(rows_of(k, act.name))}.")
    return out


def law_list(k) -> list:
    """The Acts as entries of the 'Laws in force' list."""
    return [f"{label(r)} (default code)" for r in native_acts(k)]


def digest_line(k) -> str:
    """The legal digest's line for the default code ('' when there is none)."""
    acts = acts_in_force(k)
    if not acts:
        return ""
    return "default code (inherited Acts; amend or repeal like laws): " + "; ".join(
        f"{label(r)} [{act_of(r).rank}] {act_of(r).describe(rows_of(k, act_of(r).name))}" for r in acts)


def read_note(rec) -> str:
    """read_law's note on an Act."""
    if not is_act(rec):
        return ""
    if rec.get("native"):
        return ("\nDefault code: an inherited Act, in force from the start (author code, not passed by anyone). It runs as built-in "
                "code until amended; amending it (amend with its whole new code) makes it ordinary law; repealing it leaves the "
                "residual rule (no rule of its own).")
    return "\nDefault code: an inherited Act, amended since the start: it now runs as ordinary law."


def view_rules(k) -> dict:
    """Kernel.view's rules (previews of an amendment or repeal show what changes)."""
    dc = k.w.get("default_code")
    if dc is None:
        return {}
    return {f"code {act}": rows_of(k, act) for act in dc["acts"]}


from charter.code import communications, court_rules, press   # noqa: E402,F401  (registration order: today's ids A1, A2, ...)
from charter.code import succession_act   # noqa: E402,F401  (institutions.succession only: the Succession and Escheat Acts)
