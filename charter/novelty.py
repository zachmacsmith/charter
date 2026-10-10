"""Novelty (review 14 §5.2, package A, first version): how much of what agents wrote in a run is copied from, adapted from or
unlike the code the world hands them. Offline (a run directory, or plain code); never shown to agents.

The reference set is everything an agent could have copied: the edition-1 library laws (library.LIB), their edition-2 rewrites
(LIB2), the lib:* building blocks (BLOCKS), the legal toolkit (TOOLKIT), the contract templates (contracts.TEMPLATES), the starting
constitutions (library.CONSTITUTIONS, regimes.CONSTITUTIONS), the regimes' own statutes (regimes.STATUTES) and the default code's
Acts (charter/code).

Similarity of two codes: both are reduced to a token sequence of their syntax tree (normalised: `title`, `intent`, `rank` and
`exports` lines and docstrings dropped; the agent's own identifiers become ID, every constant C, user-defined function names FN;
what stays is the tree's shape, the hook names it defines and the names it calls without defining them, i.e. the law API and
builtins), and compared with difflib's ratio (1.0: the same code up to names and constants). A law is
  copy         its sha (linker.sha) is a reference entry's
  adaptation   not a copy, and its nearest reference entry is at least THRESHOLD similar
  novel        nearest similarity below THRESHOLD; `novel_ran` further requires that it was enacted and acted (an event cites it as
               its cause, data `why` "law:<id>" or `law` <id>), so broken code does not count as invention
  no_effect    (W9) enacted, but nothing it did can be attributed to it: no primitive applied, blocked or charged with it on the
               cause stack (the law record's "effects", Kernel._credit_laws; for a run recorded before effects were, no event cites it
               as its cause). It overrides the three classes above: a law that does nothing is neither copied nor invented work. Laws
               never enacted keep their similarity class.
An author's own laws with identical code (title, intent, rank, exports and docstrings aside) are one design: the first is counted,
the others are listed as its duplicates (row "duplicate_of") and left out of every count but `laws` and `own_duplicates`, so twelve
copies of one law by one agent count once.
An institution (a contract, from contract_created) takes the highest similarity of its agent-written laws (one copied clause
makes it template-like) and is novel below THRESHOLD; one founded from a template by name has similarity 1.0. Distinct designs:
greedy clusters of the normalised codes (a code joins the first cluster whose first member it is THRESHOLD similar to).

  python -m charter novelty RUN_DIR [RUN_DIR ...] [--threshold 0.8] [--json OUT]   per-run summary (and novelty.json beside it)
"""
from __future__ import annotations

import ast
import difflib
import functools
import json
from pathlib import Path

THRESHOLD = 0.8
SYSTEM_AUTHORS = ("constitution", "code", "intervention")                # law authors that are not agents
DROP = ("title", "intent", "rank", "exports")


# ---------------------------------------------------------------------- normalised tokens and similarity
def _defined(tree) -> set:
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(n.name)
            out |= {a.arg for a in n.args.args + n.args.kwonlyargs}
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
    return out


def _hook(name: str) -> bool:
    from charter import primitives as PR
    return name in PR.HOOKS or name.startswith(("on_", "before_", "after_"))


@functools.lru_cache(maxsize=4096)
def tokens(code: str) -> tuple:
    """The normalised token sequence of law code (see the module docstring); () for code that does not parse."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError):
        return ()
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                                              and n.targets[0].id in DROP)
                 and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    mine = _defined(tree)
    out = []

    def visit(n):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append("def:" + (n.name if _hook(n.name) else "FN"))
            body = n.body[1:] if n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None),
                                                                                             ast.Constant) else n.body
            for c in body:
                visit(c)
            out.append("end")
            return
        if isinstance(n, ast.Name):
            out.append("ID" if n.id in mine else "N:" + n.id)
            return
        if isinstance(n, ast.Constant):
            out.append("C")
            return
        if isinstance(n, ast.Attribute):
            out.append("Attr")
            visit(n.value)
            return
        if isinstance(n, (ast.Load, ast.Store, ast.Del, ast.arguments, ast.arg)):
            return                                                      # context markers and parameter names carry no design
        out.append(type(n).__name__)
        for c in ast.iter_child_nodes(n):
            visit(c)

    for n in tree.body:
        visit(n)
    return tuple(out)


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return difflib.SequenceMatcher(None, ta, tb, autojunk=False).ratio()


# ---------------------------------------------------------------------- the reference set
@functools.lru_cache(maxsize=1)
def references() -> dict:
    """{label: code}: everything an agent could have copied (labels "<kind>:<name>")."""
    from charter import code as CODE
    from charter import contracts as C
    from charter import library as LB
    from charter import regimes as RG
    out = {}
    out.update({f"library:{n}": e["code"] for n, e in LB.LIB.items()})
    out.update({f"library2:{n}": e["code"] for n, e in LB.LIB2.items()})
    out.update({f"block:{n}": e["code"] for n, e in LB.BLOCKS.items()})
    out.update({f"toolkit:{n}": e["code"] for n, e in LB.TOOLKIT.items()})
    out.update({f"toolkit:{n}": e["code"] for n, e in LB.CONTRACT_TEMPLATES.items()})     # review 14 B: Assurance Founding
    out.update({f"toolkit:{n}": e["code"] for n, e in LB.FOOD_TEMPLATES.items()})         # review 15 S6: food and family templates
    out.update({f"template:{n}": C.instantiate(t["code"], {}) for n, t in C.TEMPLATES.items()})
    out.update({f"constitution:{n}": c for n, c in LB.CONSTITUTIONS.items()})
    out.update({f"constitution:{n}": c for n, c in getattr(RG, "CONSTITUTIONS", {}).items() if isinstance(c, str)})
    out.update({f"statute:{n}": c for n, c in RG.STATUTES.items()})
    out.update({f"act:{n}": a.source for n, a in CODE.ACTS.items()})
    return {k: v.strip() + "\n" for k, v in out.items() if isinstance(v, str) and tokens(v)}


@functools.lru_cache(maxsize=1)
def _ref_shas() -> dict:
    from charter import linker as LK
    return {LK.sha(c): k for k, c in references().items()}


def nearest(code: str) -> dict:
    """{"ref", "similarity", "copy"}: the most similar reference entry (ties: the first in references() order)."""
    from charter import linker as LK
    src = str(code or "").strip() + "\n"
    sha = LK.sha(src)
    if sha in _ref_shas():
        return {"ref": _ref_shas()[sha], "similarity": 1.0, "copy": True}
    t = tokens(src)
    best, ref = 0.0, None
    if t:
        for k, c in references().items():
            sm = difflib.SequenceMatcher(None, t, tokens(c), autojunk=False)
            if sm.real_quick_ratio() <= best or sm.quick_ratio() <= best:
                continue
            r = sm.ratio()
            if r > best:
                best, ref = r, k
                if r >= 1.0:
                    break
    return {"ref": ref, "similarity": round(best, 4), "copy": False}


def classify(sim: dict, threshold: float = THRESHOLD) -> str:
    return "copy" if sim["copy"] else "adaptation" if sim["similarity"] >= threshold else "novel"


def clusters(codes: list, threshold: float = THRESHOLD) -> list:
    """Greedy clusters of codes by similarity to each cluster's first member: [[index, ...], ...]."""
    out = []
    for i, c in enumerate(codes):
        for cl in out:
            if similarity(codes[cl[0]], c) >= threshold:
                cl.append(i)
                break
        else:
            out.append([i])
    return out


# ---------------------------------------------------------------------- a run
def _read(run_dir: Path):
    gt = json.loads((run_dir / "ground_truth.json").read_text())
    events = [json.loads(ln) for ln in (run_dir / "events.jsonl").read_text().splitlines() if ln.strip()]
    return gt, events


def _acted(events) -> set:
    """Law ids an event cites as its cause (data why "law:<id>", or data law <id> on a law's own act)."""
    skip = {"proposal", "enact", "vote", "ballot_open", "ballot_close", "proposal_check_failed", "proposal_preview", "veto_vote",
            "patch_submitted", "request_fix", "code_act", "contract_created", "contract_changed", "contract_change_failed"}
    out = set()
    for e in events:
        d = e.get("data") or {}
        if not isinstance(d, dict):
            continue
        why = d.get("why")
        if isinstance(why, str) and why.startswith("law:"):
            out.add(why[4:])
        if e.get("type") not in skip and isinstance(d.get("law"), str):
            out.add(d["law"])
    return out


def body_key(code: str) -> str:
    """Identity of law code for collapsing an author's duplicates: its syntax tree with the title, intent, rank and exports lines and
    docstrings dropped (identifiers and constants kept); the stripped text for code that does not parse."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError):
        return str(code or "").strip()
    body = [n for n in tree.body if not (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                                         and n.targets[0].id in DROP)
            and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    return ast.dump(ast.Module(body=body, type_ignores=[]))


def analyse(run_dir, threshold: float = THRESHOLD) -> dict:
    """The novelty summary of one run directory (ground_truth.json and events.jsonl)."""
    run_dir = Path(run_dir)
    gt, events = _read(run_dir)
    return analyse_parts(gt.get("laws") or {}, events, threshold, run=str(run_dir), effects_recorded=bool(gt.get("law_effects")))


def analyse_parts(laws: dict, events: list, threshold: float = THRESHOLD, run: str = "", effects_recorded: bool = False) -> dict:
    """effects_recorded: the law records carry "effects" (runs from W9 on, ground_truth "law_effects"); otherwise a law took
    effect when an event cites it as its cause (_acted)."""
    acted = _acted(events)
    rows, seen = [], {}
    for lid, l in sorted(laws.items(), key=lambda kv: (len(kv[0]), kv[0])):
        author = l.get("author")
        if not isinstance(author, str) or author in SYSTEM_AUTHORS or not l.get("code"):
            continue
        near = nearest(l["code"])
        enacted = l.get("enacted_round") is not None
        effect = enacted and (bool(l.get("effects")) if effects_recorded else lid in acted)
        cls = classify(near, threshold)
        key = (author, body_key(l["code"]))
        rows.append({"law": lid, "title": l.get("title"), "author": author, "jurisdiction": l.get("jurisdiction"),
                     "status": l.get("status"), "enacted": enacted, "ran": enacted and lid in acted, "effect": effect,
                     "nearest": near["ref"], "similarity": near["similarity"],
                     "class": "no_effect" if enacted and not effect else cls, "duplicate_of": seen.get(key)})
        seen.setdefault(key, lid)
    insts = {}
    for e in events:
        if e.get("type") == "contract_created":
            d = e["data"]
            insts[d["contract"]] = {"contract": d["contract"], "name": d.get("name"), "founder": e.get("agent"), "round": e.get("round"),
                                    "template": d.get("template"), "laws": []}
    for r in rows:
        if r["jurisdiction"] in insts:
            insts[r["jurisdiction"]]["laws"].append(r["law"])
    by_law = {r["law"]: r for r in rows}
    for c in insts.values():
        sims = [by_law[x]["similarity"] for x in c["laws"]]
        c["similarity"] = 1.0 if c["template"] else (max(sims) if sims else None)
        c["novel"] = None if c["similarity"] is None else c["similarity"] < threshold
        c["nearest"] = (f"template:{c['template']}" if c["template"] else
                        max(((by_law[x]["similarity"], by_law[x]["nearest"]) for x in c["laws"]), default=(0, None))[1])
    designs = [r for r in rows if r["duplicate_of"] is None]           # an author's identical laws: one design
    codes = {r["law"]: laws[r["law"]]["code"] for r in designs}
    law_ids = list(codes)
    cl = clusters([codes[x] for x in law_ids], threshold)
    inst_ids = [cid for cid, c in insts.items() if c["laws"]]
    inst_codes = ["\n".join(codes[x] for x in insts[cid]["laws"]) for cid in inst_ids]
    icl = clusters(inst_codes, threshold)
    n = len(designs)
    cnt = lambda k: sum(1 for r in designs if r["class"] == k)
    scored = [c for c in insts.values() if c["novel"] is not None]
    summary = {
        "run": run, "threshold": threshold,
        "laws": len(rows), "own_duplicates": len(rows) - n, "designs": n,
        "copies": cnt("copy"), "adaptations": cnt("adaptation"), "novel": cnt("novel"), "no_effect": cnt("no_effect"),
        "novel_ran": sum(1 for r in designs if r["class"] == "novel" and r["ran"]),
        "same_structure": sum(1 for r in designs if r["similarity"] >= 0.999),   # copies and copies with constants changed
        "copy_rate": round(cnt("copy") / n, 4) if n else None,
        "novel_share": round(cnt("novel") / n, 4) if n else None,
        "no_effect_share": round(cnt("no_effect") / n, 4) if n else None,
        "mean_similarity": round(sum(r["similarity"] for r in designs) / n, 4) if n else None,
        "distinct_law_designs": len(cl),
        "institutions": len(insts), "institutions_from_templates": sum(1 for c in insts.values() if c["template"]),
        "novel_institutions": sum(1 for c in scored if c["novel"]),
        "novel_institution_share": round(sum(1 for c in scored if c["novel"]) / len(scored), 4) if scored else None,
        "distinct_institution_designs": len(icl),
    }
    return {"summary": summary, "laws": rows, "institutions": list(insts.values()),
            "law_designs": [[law_ids[i] for i in c] for c in cl], "institution_designs": [[inst_ids[i] for i in c] for c in icl]}


def text(res: dict) -> str:
    s = res["summary"]
    out = [f"{s['run']}: {s['laws']} agent-written laws ({s['own_duplicates']} an author's own duplicates, so {s['designs']} "
           f"designs): {s['copies']} copies, {s['adaptations']} adaptations, {s['novel']} novel ({s['novel_ran']} of them ran), "
           f"{s['no_effect']} enacted without effect; copy rate {s['copy_rate']}, novel share {s['novel_share']}, mean similarity "
           f"{s['mean_similarity']}; {s['distinct_law_designs']} distinct designs",
           f"  institutions: {s['institutions']} ({s['institutions_from_templates']} from templates by name), {s['novel_institutions']} "
           f"novel (share {s['novel_institution_share']}), {s['distinct_institution_designs']} distinct designs"]
    for r in res["laws"]:
        out.append(f"  {r['law']:6} {r['class']:10} {r['similarity']:.2f} ~ {r['nearest']}  [{r['author']}, {r['status']}"
                   + (", ran" if r["ran"] else "") + (f", duplicate of {r['duplicate_of']}" if r["duplicate_of"] else "")
                   + f"] {r['title']}")
    return "\n".join(out)


# ---------------------------------------------------------------------- command line
def add_arguments(p) -> None:
    p.add_argument("runs", nargs="+", help="run directories")
    p.add_argument("--threshold", type=float, default=THRESHOLD, help="similarity below which a law or institution is novel")
    p.add_argument("--json", help="write the results (a list, one per run) here; default: novelty.json in each run directory")


def cmd(a) -> int:
    res = [analyse(r, a.threshold) for r in a.runs]
    for r, run in zip(res, a.runs):
        print(text(r))
        if not a.json:
            (Path(run) / "novelty.json").write_text(json.dumps(r, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))
    return 0
