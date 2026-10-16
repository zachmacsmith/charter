"""Laws that work or fail loudly (docs/review/31_institutions/07_rules_courts.md §4: E2, E4, T1; 08_integration.md Phase 0).

The Millbrook council amended J0's Offices Act to unseat the Keeper and wrote "the keeper's hoard is seized" in its intent. Nothing
changed, and nothing said so. This module makes every legal act report what it changed and every failed law call visible:

  law_effect      (spec law.effects, default true) do_enact, do_amend and do_repeal (dispatch.changes.legal) are wrapped in
                  before/after views of the world (Kernel.view, which under law.effects also compares offices, food stores,
                  association treasuries, clauses and open ballots: extra_view). A public `law_effect` event follows each act:
                  {law, title, act: enact|amend|repeal, changes: [diff lines], n_changes, inert, failed_calls}. `inert` is true when
                  nothing changed and the law installs (or, amended, changes) no hook that could act later: "L35 passed but changed
                  nothing". The proposal event's preview carries the same flag (dispatch do_propose), and preview_law shows the
                  diff of the enactment itself ("At enactment: ..."; amendments are previewed as amendments).
  law_call_failed (spec law.call_failures, default true) a law's move, fine (short), grant, revoke, suspend, burn or reseat that
                  fails records {law, fn, args, reason}, told to the law's author and its institution's officers (monitor when
                  there are none), at most once per law, function and round; a dry run or preview lists them instead.
  expects         (spec law.expects, default true) a law may declare its intended effect as a constant, checked right after
                  its enactment or amendment:
                      expects = [{"office": "J0.keeper", "holders": ["Osric"]},
                                 {"holding": "Elspeth", "item": "food", "at_most": 0},
                                 {"store": "S1", "item": "food", "at_least": 120},
                                 {"treasury": "A1", "item": "penny", "at_least": 10},
                                 {"right": "J0.keeper", "agent": "Osric", "has": True}]
                  In the proposal's dry run a failed expectation refuses the proposal ("your law does not do what it expects:
                  ..."); for real it is a public `law_expectation_failed` event (never a roll-back: the law is in force).

Every setting is read through setting(): the spec's value, else schema.EXTRA's (which frozen settings swap, so a run made before
these keys existed plays them at the old value once they are listed in provenance.ENGINE_FLIPS). Off, nothing here logs or adds
to a view, and every world is unchanged.
"""
from __future__ import annotations

import ast
import functools
import json
from contextlib import contextmanager

EFFECT_LINES = 30                    # diff lines a law_effect event carries
FAILED_SHOWN = 10                    # failed calls a law_effect event carries
WATCHED = ("move", "fine", "grant", "revoke", "suspend", "burn", "reseat")   # the law functions whose failure is recorded
COMPARE = ("at_least", "at_most", "equals")
_NOT_ACTING = ("on_enact",)          # hooks that do not act after the act itself (on_enact ran inside it; its effect is in the diff)


# ---------------------------------------------------------------------- settings
KEYS = ("law.effects", "law.call_failures", "law.expects", "institutions.amend_offices")
OFF = tuple(f"{x}=false" for x in KEYS)   # spec overrides that restore the behaviour before (regression tests use them)
BEFORE = {x: False for x in KEYS}          # schema.EXTRA values of the behaviour before (the engine flips, when they are assigned)


def setting(spec, path: str):
    """The spec's value at the dotted path, else schema.EXTRA's default (swapped by frozen settings)."""
    cur = spec or {}
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            from charter import schema as SC
            return SC.EXTRA.get(path)
        cur = cur[p]
    return cur


def effects_on(k) -> bool:
    return bool(setting(k.spec, "law.effects"))


def failures_on(k) -> bool:
    return bool(setting(k.spec, "law.call_failures"))


def expects_on(k) -> bool:
    return bool(setting(k.spec, "law.expects"))


# ---------------------------------------------------------------------- the extended view (Kernel.view under law.effects)
def _public_inst(k, iid) -> bool:
    from charter import institutions as IN
    try:
        return IN.published(k, iid) in (None, "public") and IN.status(k, iid) != "forming"
    except Exception:                                                   # noqa: BLE001 (an odd record never breaks a preview)
        return False


def extra_view(k) -> dict:
    """offices (public institutions'), food stores, association treasuries, clauses and open ballots, for the preview diff."""
    from charter import institutions as IN
    offices = {}
    for iid, offs in sorted((k.w.get(IN.OFFICES) or {}).items()):
        if not _public_inst(k, iid):
            continue
        for name, o in offs.items():
            offices[o.get("id") or f"{iid}.{name}"] = {
                "title": o.get("title"), "holders": sorted(IN.holders(k, iid, name)), "powers": list(o.get("powers") or ()),
                "grants": len(o.get("grants") or ()), "controls": list(o.get("controls") or ()), "term": o.get("term"),
                "seats": o.get("seats"), "duties": o.get("duties"),
                "succession": (o.get("succession") or {}).get("rule") if isinstance(o.get("succession"), dict) else o.get("succession")}
    stores = {}
    for sid, s in sorted(((k.w.get("subsistence") or {}).get("stores") or {}).items()):
        stores[sid] = {"owner": s.get("owner"), "holdings": {i: round(float(q), 6) for i, q in (s.get("holdings") or {}).items()
                                                            if abs(float(q)) > 1e-9}}
    treasuries = {}
    if k.w.get("contracts"):
        from charter import accounts as AC
        for cid, rec in sorted(AC.assocs(k).items()):
            if rec.get("status") == "dissolved" or not _public_inst(k, cid):
                continue
            try:
                h = AC.holdings(k, f"{AC.ASSOC}{cid}")
            except Exception:                                           # noqa: BLE001
                continue
            treasuries[cid] = {i: round(float(q), 6) for i, q in h.items() if abs(float(q)) > 1e-9}
    clauses = {c: v.get("law") for c, v in sorted((k.w.get("clauses") or {}).items())
               if (k.w["laws"].get(v.get("law")) or {}).get("status") == "active"}
    ballots = {b: str(v.get("question"))[:80] for b, v in sorted((k.w.get("ballots") or {}).items()) if v.get("status") == "open"}
    return {"offices": offices, "stores": stores, "treasuries": treasuries, "clauses": clauses, "ballots": ballots}


def _names(x) -> str:
    return ", ".join(x) if x else "nobody"


def diff_extra(a: dict, b: dict) -> list:
    """Diff lines of the extended view (nothing when neither view has it)."""
    out = []
    if "offices" not in a and "offices" not in b:
        return out
    oa, ob = a.get("offices") or {}, b.get("offices") or {}
    for o in sorted(set(oa) | set(ob)):
        x, y = oa.get(o), ob.get(o)
        if x is None:
            out.append(f"office {o} created (holders: {_names(y['holders'])})")
        elif y is None:
            out.append(f"office {o} abolished (held by {_names(x['holders'])})")
        else:
            if x["holders"] != y["holders"]:
                out.append(f"office {o} holders: {_names(x['holders'])} -> {_names(y['holders'])}")
            for f in sorted(set(x) | set(y)):
                if f != "holders" and x.get(f) != y.get(f):
                    out.append(f"office {o} {f}: {x.get(f)} -> {y.get(f)}")
    for key, label in (("stores", "store"), ("treasuries", "treasury")):
        sa, sb = a.get(key) or {}, b.get(key) or {}
        for s in sorted(set(sa) | set(sb)):
            x, y = sa.get(s), sb.get(s)
            if key == "stores":
                if x is None or y is None:
                    out.append(f"store {s} {'created' if x is None else 'removed'} (owner {(y or x)['owner']})")
                    continue
                if x["owner"] != y["owner"]:
                    out.append(f"store {s} owner: {x['owner']} -> {y['owner']}")
                x, y = x["holdings"], y["holdings"]
            x, y = x or {}, y or {}
            for it in sorted(set(x) | set(y)):
                d = y.get(it, 0) - x.get(it, 0)
                if abs(d) > 1e-6:
                    out.append(f"{label} {s} {it} {d:+.3g}")
    ca, cb = a.get("clauses") or {}, b.get("clauses") or {}
    out += [f"clause {c} created" for c in sorted(set(cb) - set(ca))] + [f"clause {c} gone" for c in sorted(set(ca) - set(cb))]
    ba, bb = a.get("ballots") or {}, b.get("ballots") or {}
    out += [f"ballot {x} opened: {bb[x]}" for x in sorted(set(bb) - set(ba))]
    return out


# ---------------------------------------------------------------------- inert
def _tree(code):
    try:
        return ast.parse(str(code or ""))
    except SyntaxError:
        return None


def acting(code) -> list:
    """What in a law's code can act after the act: hooks (on_*, before_*, after_*, but not on_enact) and exports."""
    from charter import lawlang as L
    tree = _tree(code)
    if tree is None:
        return []
    out = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith(("on_", "before_", "after_"))
           and n.name not in _NOT_ACTING]
    try:
        out += [f"export:{x}" for x in (L.exports_of(tree) or [])]
    except Exception:                                                   # noqa: BLE001
        pass
    return sorted(out)


def _sig(code) -> str | None:
    """The code without its title, intent, offices and expects (what runs later)."""
    tree = _tree(code)
    if tree is None:
        return None
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                                              and n.targets[0].id in ("title", "intent", "offices", "expects"))]
    return ast.unparse(tree)


def inert(act: str, diff: list, old_code=None, new_code=None) -> bool:
    """Nothing changed and nothing will: an empty diff, and (enact) no acting hook, (repeal) none stopped, (amend) none installed or
    changed."""
    if diff:
        return False
    if act == "enact":
        return not acting(new_code)
    if act == "repeal":
        return not acting(old_code)
    if not acting(old_code) and not acting(new_code):
        return True
    return _sig(old_code) == _sig(new_code)


# ---------------------------------------------------------------------- failed law calls (E4)
def note_reason(k, reason) -> None:
    """Why the current law call failed (Kernel.move, the api's refusals, scope refusals, reseat): read by the watcher."""
    k.__dict__["_lcf_reason"] = str(reason)


def _short(x) -> str:
    s = json.dumps(x, default=str) if not isinstance(x, str) else repr(x)
    return s if len(s) <= 60 else s[:57] + "..."


def _audience(k, lid) -> list:
    from charter import grants as G
    from charter import institutions as IN
    from charter import jurisdictions as J
    rec = k.w["laws"].get(lid) or {}
    out = []
    for a in [rec.get("author")] + [p.get("by") for p in rec.get("patches") or ()]:
        if isinstance(a, str) and a in k.w["agents"] and a not in out:
            out.append(a)
    if G.on(k):
        for a in IN.officers(k, J.law_jur(k, lid)):
            if a not in out:
                out.append(a)
    return out


def call_failed(k, lid, fn, args, reason) -> None:
    """Record a failed law call: in the open collectors (an act's law_effect, a dry run, a preview), and (not in a dry run) as a
    law_call_failed event, once per law, function and round."""
    if not failures_on(k):
        return
    rec = {"law": lid, "fn": fn, "args": [_short(a) for a in args][:5], "reason": str(reason or "refused")[:300]}
    for c in k.__dict__.get("_lcf_collect") or ():
        if len(c) < 50:
            c.append(rec)
    if k.dry:
        return
    seen = k.__dict__.get("_lcf_seen")
    if not seen or seen[0] != k.r:
        seen = k.__dict__["_lcf_seen"] = (k.r, set())
    key = (lid, fn)
    if key in seen[1]:
        return
    seen[1].add(key)
    aud = _audience(k, lid)
    k.log("law_call_failed", None, rec, vis=aud or "monitor")


def wrap_api(k, lid, api: dict) -> dict:
    """The law's api with its WATCHED functions recording their failures (law.call_failures)."""
    if not failures_on(k):
        return api
    out = dict(api)

    def watch(fn, f):
        @functools.wraps(f)                                             # signature and name stay the function's (lawapi tests read them)
        def call(*args, **kw):
            k.__dict__["_lcf_reason"] = None
            res = f(*args, **kw)
            failed = res is False
            if fn == "fine" and not failed and isinstance(res, (int, float)) and len(args) >= 3:
                try:
                    failed = float(res) + 1e-9 < float(args[2])
                except (TypeError, ValueError):
                    failed = False
                if failed and not k.__dict__.get("_lcf_reason"):
                    note_reason(k, f"{args[0]} held only {float(res):g} {args[1]} of the {float(args[2]):g} fined")
            if failed:
                call_failed(k, lid, fn, list(args) + [f"{x}={v}" for x, v in kw.items()],
                            k.__dict__.get("_lcf_reason") or "refused (outside the law's reach, or blocked)")
            return res
        return call

    for fn in WATCHED:
        if fn in out and callable(out[fn]):
            out[fn] = watch(fn, out[fn])
    return out


@contextmanager
def collect(k):
    """Collect the failed law calls made inside (a list, filled as they happen)."""
    st = k.__dict__.setdefault("_lcf_collect", [])
    got: list = []
    st.append(got)
    try:
        yield got
    finally:
        st = k.__dict__.get("_lcf_collect") or []                      # a transaction may have replaced the kernel's attributes
        if any(x is got for x in st):
            st[:] = [x for x in st if x is not got]


# ---------------------------------------------------------------------- expectations (T1)
def parse_expects(code) -> list:
    """The `expects` constant of a law's code ([] when none), checked: a LawError says what is wrong."""
    from charter import grants as G
    from charter import lawlang as L
    v = G._declared(str(code or ""), "expects")
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
        raise L.LawError("expects is a list of {office, holders} | {holding|store|treasury, item, at_least|at_most|equals} | "
                         "{right, agent, has}")
    for x in v:
        kinds = [f for f in ("office", "holding", "store", "treasury", "right") if f in x]
        if len(kinds) != 1:
            raise L.LawError(f"expects: each entry names one of office, holding, store, treasury, right (got {sorted(x)})")
        if kinds[0] == "office" and not isinstance(x.get("holders"), list):
            raise L.LawError("expects: an office entry needs holders (a list of agent ids)")
        if kinds[0] in ("holding", "store", "treasury"):
            if not isinstance(x.get("item"), str) or sum(c in x for c in COMPARE) != 1:
                raise L.LawError(f"expects: a {kinds[0]} entry needs item and one of at_least, at_most, equals")
            c = next(c for c in COMPARE if c in x)
            if isinstance(x[c], bool) or not isinstance(x[c], (int, float)):
                raise L.LawError(f"expects: {c} is a number")
        if kinds[0] == "right" and not isinstance(x.get("agent"), str):
            raise L.LawError("expects: a right entry needs agent (and has: true or false)")
    return v


def unmet(k, code) -> list:
    """The expectations of `code` the world does not meet now (texts). A malformed expects is one unmet text."""
    from charter import accounts as AC
    from charter import institutions as IN
    from charter import lawlang as L
    try:
        exp = parse_expects(code)
    except L.LawError as e:
        return [str(e)]
    out = []
    for x in exp:
        if "office" in x:
            iid, _, name = str(x["office"]).partition(".")
            have = sorted(IN.holders(k, iid, name)) if IN.office(k, iid, name) is not None else None
            want = sorted(dict.fromkeys(str(a) for a in x["holders"]))
            if have is None:
                out.append(f"there is no office {x['office']}")
            elif have != want:
                out.append(f"{x['office']} is held by {_names(have)}, not {_names(want)}")
            continue
        if "right" in x:
            has = str(x["right"]) in ((k.w["agents"].get(x["agent"]) or {}).get("rights") or ())
            if has != bool(x.get("has", True)):
                out.append(f"{x['agent']} {'has' if has else 'does not have'} the right {x['right']}")
            continue
        if "holding" in x:
            owner, label = str(x["holding"]), str(x["holding"])
        elif "store" in x:
            owner, label = f"{AC.STORE}{x['store']}", f"store {x['store']}"
        else:
            owner, label = AC.treasury_of(k, str(x["treasury"])), f"{x['treasury']}'s treasury"
        try:
            q = float(AC.bal(k, owner, x["item"]))
        except Exception:                                               # noqa: BLE001 (an unknown account holds nothing)
            q = 0.0
        c = next(c for c in COMPARE if c in x)
        n = float(x[c])
        bad = (c == "at_least" and q + 1e-9 < n) or (c == "at_most" and q - 1e-9 > n) or (c == "equals" and abs(q - n) > 1e-6)
        if bad:
            out.append(f"{label} holds {q:g} {x['item']}, expected {c.replace('_', ' ')} {n:g}")
    return out


# ---------------------------------------------------------------------- the act wrapper (E2)
def _vis(k):
    """Setup acts (the start block, round 0) are recorded for the monitor; every other act is public."""
    return "monitor" if any(f.get("phase") == "setup" for f in k.current_cause()) else "public"


@contextmanager
def effect(k, act: str, lid: str, old_code=None, **meta):
    """Wrap a legal act (dispatch do_enact / do_amend / do_repeal). Yields a dict the body may set "skip" in (nothing happened: a
    void, dormant or failed act). After it, a law_effect event and, for enact and amend, the expectations check. Off (law.effects)
    or in a dry run: nothing (a dry run's own view diff is the preview)."""
    ctl: dict = {}
    if not effects_on(k) or k.dry:
        with collect(k) as _:
            yield ctl
        return
    before = k.view()
    with collect(k) as failed:
        yield ctl
    if ctl.get("skip"):
        return
    own = tuple(f"law {x}: " for x in (lid, meta.get("proposal")) if x)
    diff = [x for x in k.diff(before, k.view()) if not x.startswith(own)]    # the act's own status line is the act, not its effect
    rec = k.w["laws"].get(lid) or {}
    code = rec.get("code")
    data = {"law": lid, "title": rec.get("title"), "act": act, **meta, "changes": diff[:EFFECT_LINES], "n_changes": len(diff),
            "inert": inert(act, diff, old_code if act != "enact" else None, code if act != "repeal" else None),
            "failed_calls": failed[:FAILED_SHOWN]}
    k.log("law_effect", None, data, vis=_vis(k))
    if act != "repeal" and expects_on(k):
        bad = unmet(k, code)
        if bad:
            k.log("law_expectation_failed", None, {"law": lid, "title": rec.get("title"), "act": act, "unmet": bad[:10]}, vis=_vis(k))


# ---------------------------------------------------------------------- feed lines (agents.render_event)
_VERB = {"enact": "passed", "amend": "was amended", "repeal": "was repealed"}


def render(k, e, tag) -> str | None:
    t, d = e["type"], e.get("data") or {}
    if t == "law_effect":
        head = f"{tag} {d.get('law')} '{d.get('title')}' {_VERB.get(d.get('act'), d.get('act'))}"
        fails = d.get("failed_calls") or []
        tail = ("; failed calls: " + "; ".join(f"{f['fn']}({', '.join(f['args'])}): {f['reason']}" for f in fails[:4])) if fails else ""
        if d.get("inert"):
            return head + " but changed nothing (inert: no holdings, rights, offices, stores, treasuries or rules changed, and no " \
                          "hook of it acts later)" + tail
        ch = d.get("changes") or []
        if not ch:
            return (head + "; no immediate change (it acts through its hooks)" + tail) if fails else None
        more = d.get("n_changes", len(ch)) - min(len(ch), 12)
        return head + "; it changed: " + "; ".join(ch[:12]) + (f" (+{more} more)" if more > 0 else "") + tail
    if t == "law_call_failed":
        return f"{tag} law {d.get('law')}: {d.get('fn')}({', '.join(d.get('args') or ())}) failed: {d.get('reason')}"
    if t == "law_expectation_failed":
        return f"{tag} {d.get('law')} '{d.get('title')}' does not do what it expects: " + "; ".join(d.get("unmet") or ())
    return None
