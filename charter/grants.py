"""Grants: where an institution's powers come from (review 14 §2.3, §3.2, §6.1 row E; ARCHITECTURE §3.7, D-35, D-37).

Spec flag `institutions.grants` (default false; it needs `institutions.unified`). Off, nothing here is consulted: the power table's
`kinds` column decides, as before, and every world is byte-identical. On, `powers.has_power` asks this module instead of the kind:
an institution holds a power when a grant source gives it one. The sources, in the order they are asked:

  seed         the preset's grant to a node of its institution tree (`regime.tree`, below): an initial condition (X). The seeded
               root J0 holds today's polity column, j0 values included (legacy_reserve, propose_right: SEED_ONLY), so any root a
               preset seeds may hold them. A node may give its own {power: value} instead (`grants: {...}`), or `seed` (today's).
  consent      what members accepted by joining: the institution's template declares a default set (the polity template: today's
               polity column without the seed-only powers; the association template: today's association column), and the code it
               was founded with may claim more with a top-level `powers = ["compel_members", ...]` (CONSENTABLE only). Frozen at
               founding (record key `consent`, written only when the code claims something): members who join later see it before
               they join (informed consent, D11); an amendment that claims more is not a grant (that needs per-member consent
               tracking: later). Binding only members: every compulsion function stays member-only (jurisdictions.scope_api's
               `bound`, contracts.scope_api's member checks).
  parent       what a parent institution's law grants its children: the child rule `grants` (company rules are child rules; the
               old names stay as aliases), a list of GRANTABLE powers, each only if the parent holds it itself (within the
               parent's reach). Recursive: a parent's own powers come from its sources.
  recognition  a stub (WP-G, postponed): always {}.
  force        nothing is granted. Reach over non-members is physics (conflict), never a grant (D-37).

The tree (`regime.tree`, review 14 §2.3). A regime may give its institution tree; every preset without one compiles to a one-node
tree whose root is J0 with today's code and the seed grant:
    tree:
      - id: J0                 # the root's id stays J0 (D7)
        name: the Commonwealth # default: spec jurisdictions.j0_name
        members: all           # initial condition (the only one supported: everyone is born a member)
        code: today            # the default code seeded in this node (today | none | {Act: params | null}); default: the
                               # regime's `code`, else spec code.select
        grants: seed           # seed (today's polity column) | {power: value}
        opts: {fixer: true, code_default: true}
    fixer: false drops fixer_patch from the node's seed grant (D10: the Fixer is opt-in per institution).
    code_default: true makes the node's default code also the fallback for institutions outside its subtree (today: every polity
    reads J0's rows). Default true for the compiled one-node tree (byte-identity), false in a written tree unless set.
A state-of-nature start (jurisdictions.start: nature) seeds no root: its tree is empty. Child nodes (a central bank under the root)
are validated but not seeded yet (WP-I seeds them with their Acts); a written tree must have exactly one node for now.

Default-code resolution (code.rule) under the flag: the institution's own node, then its ancestors (`parent`, any depth), then the
tree nodes marked code_default, then the Act's residual (code.chain).
"""
from __future__ import annotations

import ast
import functools

KEY = "institutions"
SOURCES = ("seed", "consent", "parent", "recognition")
# Powers a code may claim by consent (members accept them by joining): compulsion beyond escrow over members, seizure from members,
# allegiance (hooking members' legal acts elsewhere, D11). Never force, never the X machinery (Board, Fixer, levels, dry run), never
# the seed-only powers, never rules that reach agents at camps who are not members.
CONSENTABLE = ("compel_members", "unlimited_seizure", "hook_legal_acts")
# What a parent's law may grant its children (within its own reach: only powers the parent holds).
GRANTABLE = CONSENTABLE + ("take_deposits", "hook_members")
NODE_KEYS = ("id", "name", "parent", "members", "code", "grants", "opts")
NODE_OPTS = ("fixer", "code_default")


# ---------------------------------------------------------------------- the flag
def on_spec(spec) -> bool:
    i = (spec or {}).get(KEY) or {}
    return bool(i.get("grants")) and bool(i.get("unified"))


def on(k) -> bool:
    return on_spec(k.spec)


# ---------------------------------------------------------------------- the tree
def _definition(sp):
    reg = (sp or {}).get("regime")
    if reg is None:
        return {}
    from charter import regimes as RG
    try:
        return RG.definition(reg)[1]
    except (KeyError, ValueError):
        return {}


def check_tree(path: str, v) -> list:
    """Schema check of a written tree (regime field `tree`)."""
    from charter import powers as PW
    if not isinstance(v, list) or not v:
        return [f"{path}: a tree is a list of nodes [{{id: J0, ...}}]"]
    errs = []
    roots = [n for n in v if isinstance(n, dict) and n.get("parent") is None]
    for i, n in enumerate(v):
        p = f"{path}[{i}]"
        if not isinstance(n, dict):
            errs.append(f"{p}: a node is an object {{id, name, parent, members, code, grants, opts}}")
            continue
        errs += [f"{p}.{x}: unknown node field (fields: {', '.join(NODE_KEYS)})" for x in n if x not in NODE_KEYS]
        if not isinstance(n.get("id"), str) or not n.get("id"):
            errs.append(f"{p}.id: every node has an id")
        if n.get("members", "all") != "all":
            errs.append(f"{p}.members: only `all` (everyone is born a member) is supported")
        g = n.get("grants", "seed")
        if g != "seed" and not (isinstance(g, dict) and all(x in PW.POWERS for x in g)):
            errs.append(f"{p}.grants: seed or {{power: value}} (powers: {', '.join(PW.POWERS)})")
        o = n.get("opts") or {}
        if not isinstance(o, dict) or any(x not in NODE_OPTS for x in o):
            errs.append(f"{p}.opts: an object with {', '.join(NODE_OPTS)}")
        if "code" in n:
            from charter import code as DC
            errs += DC.check_selection(f"{p}.code", n["code"])
    if len(roots) != 1 or (roots and roots[0].get("id") != "J0"):
        errs.append(f"{path}: exactly one root, with id J0 (the id and the reserve key stay forever: D7)")
    if len(v) > 1:
        errs.append(f"{path}: child nodes are not seeded yet (review 14 WP-I); a tree has one node for now")
    return errs


def compile_tree(sp) -> tuple:
    """The world's institution tree as a tuple of nodes (dicts with every NODE_KEYS field). A preset without a written tree: one node,
    J0, members all, the regime's or the spec's code, the seed grant, opts {fixer: true, code_default: true}. A state-of-nature start
    (jurisdictions on, start: nature): no node."""
    from charter import jurisdictions as J
    if J.nature_start(sp or {}):
        return ()
    d = _definition(sp)
    written = d.get("tree")
    if written:
        out = []
        for n in written:
            node = {"id": n["id"], "name": n.get("name") or J.cfg_of(sp)["j0_name"], "parent": n.get("parent"),
                    "members": n.get("members", "all"), "grants": n.get("grants", "seed"),
                    "opts": {"fixer": True, "code_default": False, **(n.get("opts") or {})}}
            if "code" in n:
                node["code"] = n["code"]
            out.append(node)
        return tuple(out)
    return ({"id": "J0", "name": J.cfg_of(sp or {})["j0_name"], "parent": None, "members": "all", "grants": "seed",
             "opts": {"fixer": True, "code_default": True}},)


def tree(k) -> tuple:
    c = getattr(k, "_grant_tree", None)
    if c is None or c[0] is not k.spec:
        c = k._grant_tree = (k.spec, compile_tree(k.spec))
    return c[1]


def node(k, iid):
    return next((n for n in tree(k) if n["id"] == iid), None)


def written_code(sp):
    """The code a written tree's root lists (code.selection reads it first), or None."""
    if not on_spec(sp):
        return None
    for n in (_definition(sp).get("tree") or ()):
        if isinstance(n, dict) and n.get("parent") is None and "code" in n:
            return n["code"]
    return None


def code_root(k) -> str:
    """The tree node the default code is seeded in (the root; J0 in every preset)."""
    roots = [n["id"] for n in tree(k) if n["parent"] is None]
    return roots[0] if roots else "J0"


def code_defaults(k) -> list:
    return [n["id"] for n in tree(k) if (n.get("opts") or {}).get("code_default")]


def parent_of(k, iid):
    from charter import institutions as IN
    n = node(k, iid)
    if n is not None:
        return n["parent"]
    rec = IN.get(k, iid)
    return (rec or {}).get("parent")


def ancestors(k, iid) -> list:
    """iid, its parent, the parent's parent, ... (any depth; a cycle stops)."""
    out = []
    x = iid
    while isinstance(x, str) and x not in out:
        out.append(x)
        x = parent_of(k, x)
    return out


# ---------------------------------------------------------------------- the sources
def template_grant(kind: str) -> dict:
    """The consent a template's code declares by default: its column of the table, without the seed-only powers."""
    from charter import powers as PW
    return {n: v for n, p in PW.POWERS.items() if (v := p.value(kind)) is not False and v != "j0"}


def seed_grant(node_: dict) -> dict:
    from charter import powers as PW
    g = node_.get("grants", "seed")
    if g == "seed":
        out = {n: v for n, p in PW.POWERS.items() if (v := p.value("polity")) is not False}
    else:
        out = {n: v for n, v in g.items() if v is not False}
    if (node_.get("opts") or {}).get("fixer") is False:
        out.pop("fixer_patch", None)
    return out


@functools.lru_cache(maxsize=512)
def _declared(code: str, name: str):
    try:
        tree_ = ast.parse(code)
    except SyntaxError:
        return None
    for n in tree_.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name:
            try:
                return ast.literal_eval(n.value)
            except (ValueError, SyntaxError):
                return "<not a literal>"
    return None


def declared_powers(codes) -> list:
    """The powers a founding code claims (`powers = [...]` in any of its laws), checked: a LawError names a power no consent can give."""
    from charter import lawlang as L
    from charter import powers as PW
    out = []
    for c in codes or ():
        v = _declared(str(c), "powers")
        if v is None:
            continue
        if not isinstance(v, (list, tuple)) or not all(isinstance(x, str) for x in v):
            raise L.LawError("powers is a list of power names, e.g. powers = [\"compel_members\"]")
        for x in v:
            if x not in PW.POWERS:
                raise L.LawError(f"powers: no power {x!r}; a code may claim {', '.join(CONSENTABLE)}")
            if x not in CONSENTABLE:
                raise L.LawError(f"powers: {x} cannot be claimed by consent (members may consent to {', '.join(CONSENTABLE)}; "
                                 "reach over non-members is force, never a grant)")
            if x not in out:
                out.append(x)
    return out


def record_consent(k, rec: dict, codes) -> list:
    """At founding (flag on): the powers its code claims become its consent grant (record key `consent`, only when non-empty)."""
    got = declared_powers(codes)
    if got:
        rec["consent"] = sorted(got)
    return got


def consent(k, rec, kind) -> dict:
    out = template_grant(kind)
    for x in (rec or {}).get("consent") or ():
        out.setdefault(x, True)
    return out


def parent_grant(k, iid) -> dict:
    """The child rule `grants` of iid's parent, each power only if the parent holds it (within its reach)."""
    from charter import incorporation as INC
    from charter import powers as PW
    par = parent_of(k, iid)
    if par is None or node(k, iid) is not None:
        return {}
    want = INC.rules(k, par).get("grants") or ()
    return {x: True for x in want if x in GRANTABLE and PW.has_power(k, par, x)}


def recognition(k, iid) -> dict:
    """WP-G (recognize) is postponed: no recognition grants."""
    return {}


def sources(k, account) -> dict:
    """{source: {power: value}} for the account (an institution id, J0, or an unknown account: the polity template, as today)."""
    from charter import powers as PW
    n = node(k, account)
    rec = PW._record(k, account)
    kind = (rec or {}).get("kind", "polity")
    return {"seed": seed_grant(n) if n is not None else {},
            "consent": {} if n is not None else consent(k, rec, kind),
            "parent": parent_grant(k, account),
            "recognition": recognition(k, account)}


def value(k, account, power: str):
    """The value the power table resolves for the account (True | "board_scope" | "spec" | "j0" | False), from the first source
    that gives it."""
    n = node(k, account)
    if n is not None:
        v = seed_grant(n).get(power, False)
        if v is not False:
            return v
    else:
        from charter import powers as PW
        rec = PW._record(k, account)
        v = consent(k, rec, (rec or {}).get("kind", "polity")).get(power, False)
        if v is not False:
            return v
    if power in GRANTABLE:
        if parent_grant(k, account).get(power):
            return True
    return False


def source_of(k, account, power: str):
    """Which source gives the account the power ("seed" | "consent" | "parent" | None)."""
    for s, g in sources(k, account).items():
        if g.get(power, False) is not False:
            return s
    return None


def extra(k, iid) -> set:
    """Powers an association holds beyond its template's column (by its code's consent claim or its parent's grant): the
    functions contracts.scope_api opens for it, member-only."""
    from charter import powers as PW
    if not on(k):
        return set()
    base = template_grant("association")
    return {x for x in GRANTABLE if x not in base and PW.has_power(k, iid, x)}
