"""The per-agent legal digest (review 10 §7 "Comprehension and prompt budget"; law.v2 worlds, spec law.digest, default off): a short,
generated summary of the laws that bind one agent, grouped by what they act on, within a fixed token budget.

    transfers: L4 'Transfer Toll' charges 2% (before_move); L9 'Members Only' may block (before_move) [L4, L9 both gate it; conflicts: any_block]

Built only from static information, never by running law code: each law's hooks (the top-level functions named as hooks,
primitives.HOOKS: before_/after_<primitive>, the legacy aliases, the clock hooks), what a before-hook returns (False or a dict with
"block": may block; a number, or a dict with "charge": charges, with the rate when the return multiplies the change by a constant),
the law-API calls in each hook (what it does in reaction), the law's rank and class (dispatch.rank_of; the record's class), its
exports and imports (lawlang.static_info, the linker's records), and overlaps (two laws gating the same change) with the polity's
conflict rule (dispatch.conflict_rule). Hooks are grouped by the family of the primitive they act on (FAMILIES; anything else under
"other changes").

Which laws: the active laws the agent may see (lawpreview.visible: a hidden jurisdiction's or an association's laws only for its
members) and whose account binds it (accounts.binds). A hidden jurisdiction the agent belongs to is mentioned by its count of laws
only (they bind no one until it is declared); other hidden jurisdictions are never mentioned.

Where it is shown (both only under law.v2 with law.digest on, so every other world is byte-identical):
  - the core prompt's "laws" section (sections.Section, a "clip" row of low priority: placed after the overview, cut first), within
    spec law.digest_tokens (default TOKENS);
  - the `legal_position` look-up (action_registry), within LOOKUP_FACTOR times that budget.
Static facts are cached per law version (code sha) on the kernel, outside the world state.
"""
from __future__ import annotations

import ast

from charter import accounts as AC
from charter import dispatch as D
from charter import lawlang as L
from charter import primitives as PR

TOKENS = 300                       # the prompt section's budget (spec law.digest_tokens)
LOOKUP_FACTOR = 4                  # the legal_position look-up's budget: this many times the prompt's
FAMILIES = (
    ("transfers", ("move",)),
    ("harvests and camps", ("harvest", "set_camp_rule", "improve_camp", "lease", "regrow", "drift", "destroy", "set_camp_state",
                            "create_camp")),
    ("money", ("mint", "burn", "create_currency", "convert")),
    ("speech", ("post", "dm", "hide_post", "subscribe", "set_outlet_rule", "set_media_rule", "appoint")),
    ("rights and sanctions", ("grant_right", "revoke_right", "suspend_right", "limit_actions", "set_dm_limit", "create_right",
                              "define_action")),
    ("lawmaking", ("propose", "decide", "open_ballot", "cast_vote", "close_ballot", "veto", "enact", "repeal", "amend",
                   "set_procedure", "rule")),
    ("membership", ("join", "leave", "admit", "expel")),
    ("life and death", ("begin_life", "end_life", "commission")),
    ("force", ("attack", "fortify", "guard_bind", "guard_release")),
    ("loans", ("offer_loan", "accept_loan", "repay_loan", "extend_loan", "default_loan", "settle_loan")),
    ("projects", ("contribute", "settle_project")),
)
FAMILY_OF = {p: f for f, ps in FAMILIES for p in ps}
OTHER = "other changes"
ORDER = tuple(f for f, _ in FAMILIES) + (OTHER,)
# law-API calls worth naming as what a hook does (reads, text helpers and the like are left out)
ACTS = ("fine", "move", "grant", "revoke", "suspend", "limit_actions", "censure", "notify", "gazette", "expel", "admit", "hide_post",
        "mint", "burn", "propose_law", "propose_amendment", "repeal", "lawful_attack", "clause", "title", "set_dm_limit", "breach",
        "forfeit", "pull", "refund", "settle_loan", "open_ballot")


def enabled(k) -> bool:
    law = k.spec.get("law") or {}
    return bool(law.get("v2") and law.get("digest"))


def budget(k) -> int:
    return int((k.spec.get("law") or {}).get("digest_tokens") or TOKENS)


# ---------------------------------------------------------------------- static facts of one law (cached per code version)
def _num(n):
    return n.value if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool) else None


def _rate(expr) -> str:
    """'2%' when the expression multiplies by a constant between 0 and 1; a constant amount as itself; else ''."""
    c = _num(expr)
    if c is not None:
        return f"{c:g}"
    for n in ast.walk(expr):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult):
            for side in (n.left, n.right):
                c = _num(side)
                if c is not None and 0 < c < 1:
                    return f"{c * 100:g}%"
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
            c = _num(n.right)
            if c is not None and c > 1:
                return f"{100 / c:.3g}%"
    return ""


def _returns(fn) -> list:
    """(conditional, value node) of every return in the hook (not in nested functions)."""
    out = []

    def walk(body, cond):
        for st in body:
            if isinstance(st, ast.Return):
                out.append((cond, st.value))
            elif isinstance(st, (ast.FunctionDef, ast.Lambda)):
                continue
            else:
                for field in ("body", "orelse", "finalbody"):
                    sub = getattr(st, field, None)
                    if isinstance(sub, list):
                        walk(sub, True)
    walk(fn.body, False)
    return out


def _verdicts(fn) -> tuple:
    """(block, charge, reason) a before-hook's returns can give ('' when it cannot; reason: a constant one it states)."""
    block, charge, reason = "", "", ""
    for cond, v in _returns(fn):
        may = "may " if cond else ""
        if v is None:
            continue
        if isinstance(v, ast.Constant):
            if v.value is False:
                block = block or f"{may}block"
            elif _num(v) is not None and v.value > 0:
                charge = charge or f"{may}charge {_rate(v)}".rstrip()
            continue
        if isinstance(v, ast.Dict):
            keys = {kk.value: vv for kk, vv in zip(v.keys, v.values) if isinstance(kk, ast.Constant)}
            b = keys.get("block")
            if b is not None and not (isinstance(b, ast.Constant) and not b.value):
                block = block or f"{'may ' if cond or not isinstance(b, ast.Constant) else ''}block"
            if "charge" in keys:
                charge = charge or f"{may}charge {_rate(keys['charge'])}".rstrip()
            r = keys.get("reason")
            if isinstance(r, ast.Constant) and isinstance(r.value, str) and not reason:
                reason = r.value
            continue
        if isinstance(v, (ast.BinOp, ast.Call, ast.Name, ast.Subscript, ast.IfExp)):
            charge = charge or f"may charge {_rate(v)}".rstrip()
    return block, charge, reason


def _calls(fn) -> list:
    return sorted({n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ACTS})


def static(code: str) -> dict:
    """Hooks (name -> {primitive, phase, block, charge, does}), exports and the declared rank of a law's code."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"hooks": {}, "exports": [], "imports": []}
    hooks = {}
    for n in tree.body:
        if not (isinstance(n, ast.FunctionDef) and n.name in PR.HOOKS):
            continue
        row = PR.HOOKS[n.name]
        phase = row.kind if row.kind in ("before", "after") else None
        if row.kind == "alias":
            phase = PR.alias(n.name).phase if PR.alias(n.name).verdict in ("before", "admit", "refuse") else "after"
        block, charge, reason = _verdicts(n) if phase == "before" else ("", "", "")
        if row.kind == "alias" and PR.alias(n.name).verdict == "admit":
            block, charge = "decides admission", ""
        elif row.kind == "alias" and PR.alias(n.name).verdict == "refuse" and block:
            block = block.replace("block", "refuse")
        hooks[n.name] = {"primitive": row.primitive, "kind": row.kind, "phase": phase, "block": block, "charge": charge,
                         "reason": reason, "does": _calls(n)}
    info = L.static_info(tree)
    return {"hooks": hooks, "exports": list(info.get("exports") or ()),
            "imports": [i.get("ref") for i in info.get("imports") or () if isinstance(i, dict)]}


def _facts(k, lid) -> dict:
    code = k.w["laws"][lid]["code"]
    cache = k.__dict__.setdefault("_digest_static", {})
    key = (lid, D.sha(code))
    if key not in cache:
        cache[key] = static(code)
    return cache[key]


# ---------------------------------------------------------------------- the digest
def binding_laws(k, aid) -> list:
    """Active laws the agent may see and whose account binds it, in canonical order (rank, enactment, id)."""
    from charter import lawpreview as LP
    pos = {lid: i for i, lid in enumerate(k.w["law_order"])}
    out = [l["id"] for l in k.active_laws() if LP.visible(k, aid, l["id"]) and AC.binds(k, AC.account_of(k, l["id"]), aid)]
    return sorted(out, key=lambda x: (-D.RANKS[D.rank_of(k, x)], pos.get(x, 1 << 30), x))


def _label(k, lid) -> str:
    law = k.w["laws"][lid]
    rank = D.rank_of(k, lid)
    return f"{lid} '{str(law['title'])[:40]}'" + (f" [{rank}]" if rank != "statute" else "")


def _phrase(h) -> str:
    gate = " and ".join(x for x in (h["block"], h["charge"]) if x)
    if gate and h.get("reason"):
        gate += f" ('{h['reason'][:40]}')"
    does = ", ".join(h["does"])
    if gate:
        return gate + (f", then {does}" if does else "")
    return f"reacts with {does}" if does else "reacts"


def lines(k, aid) -> list:
    """The digest's lines, most important first (the header, then families in ORDER, round hooks, laws without hooks, links)."""
    laws = binding_laws(k, aid)
    fam: dict = {}
    gates: dict = {}                                                  # primitive -> laws with a before verdict on it
    rounds, plain, links = [], [], []
    for lid in laws:
        st = _facts(k, lid)
        acting = False
        for name, h in st["hooks"].items():
            if h["kind"] == "clock":
                rounds.append(f"{_label(k, lid)} ({name}" + (f": {', '.join(h['does'])}" if h["does"] else "") + ")")
                acting = True
                continue
            if h["kind"] == "lifecycle" or not h["primitive"]:
                continue
            acting = True
            f = FAMILY_OF.get(h["primitive"], OTHER)
            fam.setdefault(f, []).append(f"{_label(k, lid)} {_phrase(h)} ({name})")
            if h["phase"] == "before" and (h["block"] or h["charge"]):
                gates.setdefault((f, h["primitive"]), []).append(lid)
        if not acting:
            plain.append(f"{_label(k, lid)} ({k.w['laws'][lid]['cls']})")
        if st["exports"]:
            links.append(f"{lid} exports {', '.join(st['exports'][:6])}")
        for ref in st["imports"][:4]:
            links.append(f"{lid} uses {ref}")
    out = [f"Laws that bind you: {len(laws)} in force" + (", by what they act on (read_law for the code):" if laws else ".")]
    from charter import code as DC                                     # code.enabled: the default code's Acts (off: no line)
    out += [x for x in (DC.digest_line(k),) if x]
    for f in ORDER:
        if f not in fam:
            continue
        line = f"{f}: " + "; ".join(fam[f])
        for (gf, prim), who in sorted(gates.items()):
            if gf == f and len(who) > 1:
                rule = (D.conflict_rule(k, D._polity(k, who[0])) or {}).get("rule", "any_block")
                line += f" [{', '.join(who)} all gate each {prim}; conflicting verdicts: {rule}]"
        out.append(line)
    if rounds:
        out.append("every round: " + "; ".join(rounds))
    if plain:
        out.append("no hooks (functions, offices, procedures): " + "; ".join(plain))
    if links:
        out.append("links: " + "; ".join(links))
    out += _hidden_note(k, aid)
    return out


def _hidden_note(k, aid) -> list:
    if "jur" not in k.w:
        return []
    from charter import jurisdictions as J
    out = []
    for jid in J.hidden_of(k, aid):
        n = sum(1 for l in k.w["laws"].values() if J.law_jur(k, l["id"]) == jid and l["status"] in ("dormant", "charter", "active"))
        if n:
            out.append(f"your hidden jurisdiction {jid} has {n} law(s), binding no one until it is declared")
    return out


def render(k, aid, tokens_budget: int | None = None) -> str:
    """The digest within its budget: whole lines while they fit, then a count of the rest (the look-up has more room)."""
    from charter import context as CX
    b = budget(k) if tokens_budget is None else int(tokens_budget)
    ls = lines(k, aid)
    out, used, dropped = [], 0, 0
    for i, ln in enumerate(ls):
        t = CX.tokens(ln) + 1
        if not dropped and used + t <= b - 15:
            out.append(ln)
            used += t
        elif not dropped and i == 0:                                   # the header always shows, cut to fit
            out.append(CX.clip(ln, max(10, b - 15))[0])
            used += b
        else:
            if not dropped and used < b - 40:                          # the first line that does not fit: cut, not dropped
                out.append(CX.clip(ln, b - 15 - used)[0])
                used = b
                continue
            dropped += 1
    if dropped:
        out.append(f"({dropped} more line(s): the legal_position look-up)")
    return "\n".join(out)


def act_legal_position(k, aid, **args) -> str:
    """The legal_position look-up (action_registry; law.v2 with law.digest on)."""
    from charter.actions import ActionError
    if not enabled(k):
        raise ActionError("unknown action 'legal_position'")
    return "Your legal position:\n" + render(k, aid, budget(k) * LOOKUP_FACTOR)


# ------------------------------------------------------------------ the core prompt's row (sections.LAYOUTS["core"])
from charter import sections as _SC                                    # noqa: E402


@_SC.section("laws", layers=("core",), needs=("law:v2", "law:digest"), cut="clip", priority=-1,
             note="...(more: the legal_position look-up)")
def _laws(v):
    if v.k is None or v.aid not in v.k.w["agents"]:
        return ""
    return render(v.k, v.aid)
