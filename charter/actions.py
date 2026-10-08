"""Agent actions. act(kernel, agent, name, args) -> result text shown to the agent. Every action is logged.

act() looks the action up in charter/action_registry.py and calls its handler: a `_name` function here, or the owning module's
function where that takes the action's arguments as they are (Act.handler "conflict:act_fortify"). ACTIONS, DM_ACTIONS and
_ALIASES are derived from the registry."""
from __future__ import annotations

import json

import difflib

from charter import action_registry as AR                             # every action's row: handler, doc, category
from charter import camps as C
from charter import context as CX                                     # context: lookups and files (charter/context.py)
from charter import conflict as CF
from charter import credit as CR
from charter import dispatch as D                                     # legal acts: the propose payload's draft (P2.3)
from charter import hidden as H
from charter import jurisdictions as J
from charter import lawlang as L
from charter import media as MD                                       # media2
from charter import outside as O
from charter import projects as P
from charter import roles as R                                         # roles: court evidence the Spy read

ACTIONS = AR.actions()                                                 # every action (charter/action_registry.py), in the old order
CONTEXT_ACTIONS = tuple(n for n in ACTIONS if AR.REG[n].module == "context")   # context: lookups and files; only when it is on
MEDIA_ACTIONS = tuple(n for n in ACTIONS if AR.REG[n].module in ("media", "scholars"))   # media2: outlets, licences, Scholars
DM_ACTIONS = AR.dm_actions()                                           # private messages: the DM limit applies; fast mode's DM step delivers them


class ActionError(Exception):
    pass


_CAMP_REF = __import__("re").compile(r"^\s*(?:camp)?\s*(\d+)\s*$", __import__("re").I)
_ALIASES = AR.aliases()                                                 # forgiving argument names, per action (Act.aliases)
_IGNORED = {"propose": {"title", "name"}, "write_edition": {"title", "headline"}, "reply": {"to", "recipient"}}   # a reply goes to the sender


def _normalise_args(name: str, args):
    """Forgiving argument names seen from models: a camp given as 4 or "camp 4" means "camp4"; common synonyms (message for
    text, amount for qty) when the proper name is absent; a law's title passed beside its code is ignored (it is set in the code)."""
    if not isinstance(args, dict):
        return args
    if name == "harvest" and "args" in args:                           # harvest {"camp", "args": [...]} or {"camp", "args": {...}}
        inner, args = args["args"], {x: v for x, v in args.items() if x != "args"}
        args = {**args, **inner} if isinstance(inner, dict) else ({**args, "x": inner} if "x" not in args else args)
    out, alias = {}, _ALIASES.get(name, {})
    for key, v in args.items():
        if key in alias and alias[key] not in args:
            if name == "propose" and alias[key] == "code" and not _looks_like_code(v):
                continue                                                # prose is not a law: the error below explains what is
            key = alias[key]
        if key in _IGNORED.get(name, ()):
            continue
        if key == "item" and isinstance(v, dict) and len(v) == 1 and "qty" not in args:   # {"timber": 3} for item and qty
            (v, q), = v.items()
            out["qty"] = q
        if key == "camp" and isinstance(v, (int, str)) and _CAMP_REF.match(str(v)):
            v = "camp" + _CAMP_REF.match(str(v)).group(1)
        out[key] = v
    if name == "bequest" and "to" in out and "holdings" not in out:     # {"to": "Name"}: everything to one heir
        out["holdings"] = {str(out.pop("to")): 1.0}
    if name == "create_agent" and isinstance(out.get("spec"), dict):    # a payment written into the spec is not part of the child
        out["spec"] = {x: v for x, v in out["spec"].items() if x not in ("fee", "payment", "price")}
    if name == "commission":                                            # spec fields given beside spec, and timing synonyms
        spec = dict(out.get("spec") or {}) if isinstance(out.get("spec") or {}, dict) else out.get("spec")
        if isinstance(spec, dict):
            for key in [x for x in out if x not in ("maker", "spec", "payment")]:
                spec.setdefault(key, out.pop(key))
            for syn in ("fee", "payment", "price"):                       # what the parent pays goes with the order, not the child
                if syn in spec and "payment" not in out:
                    out["payment"] = spec.pop(syn)
                spec.pop(syn, None)
            for syn, real in (("role", "cls"), ("class", "cls"), ("agent_class", "cls"), ("type", "cls")):
                if syn in spec:
                    spec.setdefault(real, str(spec.pop(syn)).lower())
            for syn in ("born", "when", "birth"):
                if syn in spec:
                    spec.setdefault("timing", spec.pop(syn))
            t = str(spec.get("timing", "")).lower().replace(" ", "_")
            if t:
                spec["timing"] = t if t in ("next_round", "on_death") else \
                    "on_death" if "death" in t or "die" in t or "leave" in t else "next_round"
            if spec:
                out["spec"] = spec
    if name == "transfer" and "item" not in out:                        # {"amount": {"timber": 1}} or {"timber": 1}
        if isinstance(out.get("qty"), dict) and len(out["qty"]) == 1:
            (out["item"], out["qty"]), = out["qty"].items()
        else:
            loose = [x for x, v in out.items() if x not in ("to", "qty", "item") and isinstance(v, (int, float)) and not isinstance(v, bool)]
            if len(loose) == 1 and "qty" not in out:
                out["item"], out["qty"] = loose[0], out.pop(loose[0])
    return out


LAW_TEMPLATE = ('A law is complete code in the law language (restricted Python), passed as "code", e.g.\n'
                'title = "Member Stipend"\nintent = "Each round every Legislator gets 1 timber from the reserve."\n'
                'def on_round_end(r):\n    for a in agents("legislator"):\n        move("reserve", a, "timber", 1)\n'
                "If someone drafted a law for you, paste its code. Your manual's law sections list the functions and hooks.")


def _looks_like_code(v) -> bool:
    t = str(v or "")
    return "=" in t or "def " in t                                      # prose ("Grant Erik the right.") has neither


def act(k, aid: str, name: str, args: dict) -> str:
    """Dispatch one action; everything it logs carries an action cause frame (kernel.cause), a root frame: the action item's
    primitives (Kernel.apply) form one cascade."""
    with k.cause("action", str(name), agent=None if k.current_turn_agent() == aid else aid, root=True):
        try:
            return _act(k, aid, name, args)
        except D.Blocked as e:                                          # law.v2: a law's before-hook blocked this action's change
            raise ActionError(str(e)) from None


def _act(k, aid: str, name: str, args: dict) -> str:
    hidden_here = (set() if CX.enabled(k) else set(CONTEXT_ACTIONS)) | (set() if MD.enabled(k) else set(MEDIA_ACTIONS))   # context, media2: off = unknown
    if name not in ACTIONS or name in hidden_here:
        raise ActionError(f"unknown action '{name}'. Actions: {', '.join(x for x in ACTIONS if x not in hidden_here)}")
    if name == "create_agent" and isinstance(args, dict) and str(args.get("commission") or "").lower() in ("", "self", "own", "me", aid.lower()):
        from charter import life as LF, roles as RO                       # a Maker making its own child directly
        if LF.enabled(k.spec) and "life" in k.w and RO.has_role(k, aid, "maker"):
            open_ = sorted(c["id"] for c in LF.state(k)["commissions"].values() if c["maker"] == aid and c["status"] == "open")
            own = bool(args.get("commission")) or not open_
            if not own and (args.get("spec") or len(open_) > 1):           # ambiguous: never fill a customer's order by guess
                raise ActionError(f"you hold open orders ({', '.join(open_)}): name one to fill it (\"commission\": \"{open_[0]}\"), or "
                                  "make your own child with \"commission\": \"self\"")
            if own:
                spec = dict(args.get("spec") or {}) if isinstance(args.get("spec") or {}, dict) else {}
                spec.update({x: v for x, v in args.items() if x not in ("spec", "commission")})
                name, args = "commission", {"maker": aid, "spec": spec}
            else:
                args = {**args, "commission": open_[0]}
    if name == "commission" and isinstance(args, dict) and not args.get("maker"):            # no Maker named: the one living Maker
        from charter import life as LF
        if LF.enabled(k.spec) and "life" in k.w and len(LF.living_makers(k)) == 1 and LF.living_makers(k)[0] != aid:
            args = {**args, "maker": LF.living_makers(k)[0]}
    if name == "commission" and isinstance(args, dict) and str(args.get("maker") or aid) == aid:   # a Maker "commissioning" an order it holds
        from charter import life as LF, roles as RO
        if LF.enabled(k.spec) and "life" in k.w and RO.has_role(k, aid, "maker"):
            ref = args.get("commission") or args.get("id")
            parent = args.get("for") or args.get("parent") or args.get("to")
            if not ref:
                mine = sorted((c for c in LF.state(k)["commissions"].values() if c["maker"] == aid and c["status"] == "open"
                               and (parent is None or c["parent"] == parent)), key=lambda c: c["id"])
                ref = mine[0]["id"] if mine else None
            if ref:
                name, args = "create_agent", {"commission": ref}
    fn = AR.resolve(AR.REG[name].handler)
    args = _normalise_args(name, args)
    if name == "veto" and isinstance(args, dict):                      # {"should_veto": false} means: no veto
        flag = args.get("should_veto", args.get("veto", True))
        if flag is False or str(flag).lower() in ("false", "no"):
            return "No veto cast."
        args = {x: v for x, v in args.items() if x not in ("should_veto", "veto", "reason")}
    if name == "propose" and isinstance(args, dict) and not str(args.get("code") or "").strip():
        raise ActionError("propose needs the law's code, not only a title or a description. " + LAW_TEMPLATE)
    if k.w["agents"].get(aid, {}).get("departed") is not None:        # world events: departed agents are out of play
        raise ActionError("you have left the world")
    for key in ("to", "agent"):
        if isinstance(args, dict) and isinstance(args.get(key), str) and k.w["agents"].get(args[key], {}).get("departed") is not None:
            raise ActionError(f"{args[key]} has left the world")
    if name == "harvest" and isinstance(args, dict):
        if "camp" not in args:                                          # one harvest right: the camp is implied
            mine = [r.split(":", 1)[1] for r in k.w["agents"].get(aid, {}).get("rights", []) if str(r).startswith("harvest:")]
            if len(mine) == 1:
                args = {**args, "camp": mine[0]}
        if args.get("credit") in (0, "0", "", "none", None) and "credit" in args:   # catalyst: no partner to credit
            args = {x: v for x, v in args.items() if x != "credit"}
    if name == "harvest" and isinstance(args, dict) and k.w["camps"].get(str(args.get("camp")), {}).get("destroyed") is not None:
        raise ActionError(f"{args.get('camp')} has been destroyed and yields nothing")
    try:
        return fn(k, aid, **(args or {}))
    except TypeError as e:
        raise ActionError(f"bad arguments for {name}: {_as_before(e, fn, name)}")
    except L.LawError as e:
        raise ActionError(str(e))
    except (ValueError, KeyError, AttributeError, IndexError) as e:     # a malformed argument must fail the action, never the run
        raise ActionError(f"bad arguments for {name}: {type(e).__name__}: {e}")


def _as_before(e: TypeError, fn, name: str) -> str:
    """A bad-arguments message names the function called; it said "_fortify()" when every action had a function here, and still does."""
    msg, own = str(e), getattr(fn, "__qualname__", "") + "()"
    return f"_{name}()" + msg[len(own):] if own != f"_{name}()" and msg.startswith(own) else msg


def _need(k, aid, right, what):
    if not k.has(aid, right):
        raise ActionError(f"you need the '{right}' right to {what}")


# ------------------------------------------------------------------ production
def _harvest(k, aid, camp, x=None, **extra):
    if camp not in k.w["camps"]:
        raise ActionError(f"no such camp: {camp}. Camps: {', '.join(H.visible_camps(k))}")
    if k.w["camps"][camp].get("type"):                                 # camps: typed camps (camps.model: types) run in the framework
        from charter.camptypes import framework as CT
        if x is None and len(extra) == 1 and next(iter(extra)) in ("choice", "amount", "value", "side", "guess", "dials", "setting") \
                and next(iter(extra)) not in getattr(CT.get(k.w["camps"][camp]["type"]), "extra_args", ()):
            x = extra.pop(next(iter(extra)))                              # a camp's single input under another name means x
        return CT.harvest_action(k, aid, camp, x, extra)               # camps-b: non-dial args (submit, shift, partner, ...)
    if extra or x is None:                                             # camps-b: legacy camps take exactly camp and x, as before
        raise TypeError(f"_harvest() got unexpected or missing arguments: {sorted(extra) if extra else 'x'}")
    _need(k, aid, f"harvest:{camp}", f"harvest at {camp}")
    c = k.w["camps"][camp]
    cr = J.camp_rules(k, aid, camp)                                    # jurisdictions: the harvester's jurisdiction's rules (off: the camp's)
    x = [int(v) for v in (x if isinstance(x, list) else [x])]
    if len(x) != c["dials"] or any(v < 0 or v > c["max"] for v in x):
        raise ActionError(f"x must be a list of {c['dials']} integers, each 0..{c['max']}")
    key = f"{aid}|{camp}"
    limit = cr["harvest_limit"] if cr["harvest_limit"] is not None else k.spec["harvests_per_right"]
    if k.w["harvest_count"].get(key, 0) >= limit:
        raise ActionError(f"harvest limit reached at {camp} this round ({limit})")
    if cr["quota"] is not None and k.w["quota_used"].get(cr["qkey"], 0) >= cr["quota"]:
        raise ActionError(f"the quota for {camp} is used up this round ({cr['quota']})")
    if cr["fee"]:
        if not k.move(aid, cr["reserve"], cr["fee"]["item"], cr["fee"]["qty"], why="harvest_fee", by=aid):
            raise ActionError(f"cannot pay the harvest fee ({cr['fee']['qty']} {cr['fee']['item']})")
    for item, q in c.get("consumes", {}).items():
        if k.bal(aid, item) + 1e-9 < q:
            raise ActionError(f"this camp consumes {q} {item} per harvest, and you have {k.bal(aid, item):g}")
        k._add(aid, item, -q)
    k.w["harvest_count"][key] = k.w["harvest_count"].get(key, 0) + 1
    k.w["quota_used"][cr["qkey"]] = k.w["quota_used"].get(cr["qkey"], 0) + 1
    info = {}
    hrng = k.stream("harvest", k.r, aid, camp, k.w["harvest_count"][key])   # rng_version 2: per round, agent, camp and harvest n
    if c.get("compute"):
        y, eff, noise, info = C.harvest_compute(c, x, hrng, aid, k.r)
        if info.get("factored"):
            k.log("factored", aid, {"camp": camp, "N": info["factored"], "new_N": info["new_N"]}, vis="public")
            k.gazette(f"{aid} factored the number at {camp}. The new number is N = {info['new_N']}.")
    else:
        y, eff, noise = C.harvest(c, x, hrng)
        y = P.granary_cap(k, c, y)                                     # a funded granary keeps seed stock out of reach
    item = c["resource"]                                               # on_harvest deductions go to the harvester's home reserve
    ded = k.apply("harvest", agent=aid, camp=camp, x=x, item=item, qty=y).result["deducted"]
    k.eff.setdefault(aid, {}).setdefault(camp, []).append((k.r, eff))
    k.log("harvest", aid, {"camp": camp, "x": x, "yield": y, "deducted": ded, "efficiency": round(eff, 4), "noise": round(noise, 4),
                           "stock_before": round(c["S"], 3), **({"info": info} if info else {})}, vis=[aid])
    accident = CF.after_harvest(k, aid, camp)                          # conflict: a small chance the harvester is disabled
    extra = ""
    if "parity_bit" in info:
        extra = f"; parity bit {info['parity_bit']}"
    elif "leading_zero_bits" in info:
        extra = f"; leading zero bits {info['leading_zero_bits']}"
    elif c.get("compute") == "factoring":
        extra = "; correct factor: bounty paid, N redrawn" if info.get("factored") else "; not a factor of N"
    return f"Harvested {y - ded:.3g} {k.name_of('resource:' + item)} at {camp} with x={x if len(str(x)) < 200 else str(x)[:200]}{extra}" + (f" ({ded:.3g} deducted by law)" if ded else "") \
        + (" An accident at the camp has removed you from the game." if accident else "")                       # conflict


def _survey(k, aid, camp, x):
    """camps: probe a setting at a typed camp with the survey modifier, without harvesting, for a fee."""
    from charter.camptypes import framework as CT
    return CT.survey_action(k, aid, str(camp), x)


def _invest(k, aid, camp, qty):
    """camps: lock resources into a typed camp's infrastructure (capacity, regrowth, safety)."""
    from charter.camptypes import framework as CT
    return CT.invest_action(k, aid, str(camp), qty)


def _run_python(k, aid, code):
    _need(k, aid, "sandbox", "run code")
    out = str(k.sandbox(aid, str(code)))[:4000]
    k.log("sandbox", aid, {"code": str(code)[:6000], "output": out}, vis=[aid])
    return out or "(no output)"


# ------------------------------------------------------------------ communication and trade
def _post(k, aid, text):
    if MD.submissions_on(k) and not MD.in_stream(k, aid):               # media2.submissions: the media decide what is published
        return MD.submit(k, aid, text)
    MD.check_post(k, aid)                                              # media2: posting needs a licence from some outlet
    text = str(text)[:2000]
    t = k.agent(aid)["title"]
    eid = k.apply("post", agent=aid, kind="post", text=text, actor=aid, data={"text": text, "title": t}).result["event"]
    return f"Posted ({eid})."


def _anon_post(k, aid, text):
    """A public post shown as 'Anonymous'. The author is recorded only in a monitor-only entry (never visible or citable in-game)."""
    _need(k, aid, "anon", "post anonymously")
    if MD.submissions_on(k):
        return MD.submit(k, aid, text, anon=True)
    MD.check_post(k, aid)                                              # media2: posting needs a licence from some outlet
    text = str(text)[:2000]
    with k.concealing(aid):                                            # the visible entry's cause chain must not name the author either
        eid = k.apply("post", agent=aid, kind="anon_post", text=text, actor=None, data={"text": text}).result["event"]
    return f"Posted anonymously ({eid})."


def _dm(k, aid, to, text, encrypted=False):
    _dm_check(k, aid, to, encrypted)
    eid = _deliver(k, aid, to, text, encrypted)
    return f"Message sent to {to} ({eid})."


def _dm_check(k, aid, to, encrypted=False):
    """Checks shared by dm, reply and forge_dm: DMs exist, the recipient exists, encryption, and the sender's DM limit."""
    if not k.spec["channels"].get("dm", True):
        raise ActionError("there are no private messages in this world")
    if to not in k.w["agents"] or to == aid:
        raise ActionError(f"unknown recipient {to}")
    if encrypted:
        if not k.spec["channels"].get("encryption", True):
            raise ActionError("encryption does not exist in this world")
        _need(k, aid, "encrypt", "send encrypted messages")
    used, lim = k.w["dm_sent"].get(aid, 0), k.dm_limit(aid)
    if used >= lim:
        raise ActionError(f"you have sent your {lim} private messages for this round (the limit is set by holders of dm_rules or by law)")


def _deliver(k, aid, to, text, encrypted=False, extra=None):
    """Log a DM (after _dm_check). Convention: the event's `agent` is always the TRUE sender and data["to"] the TRUE recipient; a
    forged DM carries data["shown_as"] (the apparent sender) and a reply to one carries data["shown_to"] (whom the replier believes
    they answered). Feeds show the apparent names except to the true recipient (agents.render_event); laws (on_dm) see the apparent ones."""
    extra = extra or {}                                                # laws (on_dm) see DMs only when the world allows it (readable)
    return k.apply("dm", sender=aid, recipient=to, text=str(text)[:2000], encrypted=encrypted, shown_as=extra.get("shown_as"),
                   shown_to=extra.get("shown_to"), extra=extra).result["event"]


_BAD_ESCAPE = __import__("re").compile(r'\\(?!["\\/bfnrtu])')


def parse_args(item) -> dict:
    """An action item's arguments, parsed leniently: models (Haiku especially) put raw newlines inside strings, write invalid
    backslash escapes (\\d, \\s in code) or add text after the JSON object. Raises ActionError if nothing usable is left."""
    raw = item.get("args_json") if isinstance(item.get("args_json", ""), str) else None
    if raw is None:
        a = item.get("args") or {}
    else:
        raw = raw.strip() or "{}"
        a, last = None, None
        for attempt in (raw, _BAD_ESCAPE.sub(r"\\\\", raw)):
            try:
                a = json.JSONDecoder(strict=False).raw_decode(attempt)[0]    # strict=False: raw newlines; raw_decode: trailing text
                break
            except json.JSONDecodeError as e:
                last = e
        if a is None:
            raise ActionError(f"args_json is not valid JSON ({last}); send one JSON object, e.g. {{\"to\": \"Name\", \"text\": \"...\"}}")
    if not isinstance(a, dict):
        raise ActionError("args_json must be a JSON object")
    return a


def item_args(item) -> dict:
    """An action item's arguments as a dict ({} if they do not parse)."""
    try:
        return parse_args(item)
    except ActionError:
        return {}


def is_dm_item(item) -> bool:
    """A private message for the DM limit and fast mode's DM step: dm, reply, forge_dm, or invoking the forging power."""
    name = str(item.get("action", ""))
    if name in DM_ACTIONS:
        return True
    from charter import hidden as _H
    return name == "invoke" and str(item_args(item).get("action")) == _H.CAPS["forge_dm"][0]


def dm_recipient(k, aid, name, args):
    """Whom a DM-type action actually reaches (None if invalid): for a reply, the message's true sender."""
    if name == "reply":
        e = _message(k, aid, args.get("message"))
        return e["agent"] if e else None
    if name == "invoke":                                               # the forging power: args [shown_as, to, text]
        a = args.get("args")
        return a[1] if isinstance(a, list) and len(a) > 1 else None
    return args.get("to")


def _message(k, aid, eid):
    e = next((x for x in reversed(k.events) if x["id"] == str(eid)), None)
    return e if e and e["type"] == "dm" and e["data"].get("to") == aid else None


def _reply(k, aid, message, text, item=None, qty=None, encrypted=False):
    """Answer a DM you received, optionally with a payment, in one action (counts as a DM). Both go to the message's TRUE sender
    (for a forged DM: the forger), while the replier is shown the apparent sender. The payment is an ordinary transfer (laws'
    on_transfer hooks apply), visible only to the replier and the true recipient, and marked with the apparent destination."""
    e = _message(k, aid, message)
    if not e:
        raise ActionError(f"{message} is not a private message to you")
    true, shown = e["agent"], e["data"].get("shown_as") or e["agent"]
    _dm_check(k, aid, true, encrypted)
    mark = {"reply_to": e["id"], **({"shown_to": shown} if shown != true else {})}
    pay = qty not in (None, 0, "") and bool(item)
    if not pay and (qty not in (None, 0, "") or item):
        raise ActionError("a payment with a reply needs both item and qty")
    if pay:
        _send(k, aid, true, item, qty, extra=mark)
    eid = _deliver(k, aid, true, text, encrypted, {**mark, **({"payment": {"item": item, "qty": float(qty)}} if pay else {})})
    return f"Replied to {shown} ({eid})" + (f" and sent {float(qty):g} {item}" if pay else "") + "."


def forge_message(k, sender, shown_as, to, text, cost=None, source="observer"):
    """The one forged-DM core (the observer's forge_dm and the hidden power both use it). The DM event's `agent` is the TRUE sender
    and data["shown_as"] the apparent one, so `reply` routes answers and payments back to the forger; the recipient sees the
    apparent sender, the impersonated agent is not told, and a monitor-only `forged_dm` event (with `source`) records the truth."""
    if not k.spec["channels"].get("dm", True):
        raise ActionError("there are no private messages in this world")
    players = k.players()
    if shown_as not in players or shown_as in (to, sender):
        raise ActionError(f"cannot send a message as {shown_as}")
    if to not in players or to == sender:
        raise ActionError(f"unknown recipient {to}")
    _dm_check(k, sender, to)
    cost = {i: float(q) for i, q in (cost or {}).items()}
    for item, q in cost.items():
        if k.bal(sender, item) + 1e-9 < q:
            raise ActionError(f"forging a message costs {q:g} {item}, and you have {k.bal(sender, item):g}")
    for item, q in cost.items():
        k.move(sender, "reserve", item, q, why="forge_fee", by=sender)
    with k.concealing(sender):                                         # the recipient's entry must not name the forger in its cause chain
        eid = _deliver(k, sender, to, text, False, {"shown_as": shown_as})
    k.log("forged_dm", sender, {"event": eid, "shown_as": shown_as, "to": to, "cost": cost, "source": source,
                                "text": str(text)[:2000]}, vis="monitor")
    return eid


def _forge_dm(k, aid, to, text, **kw):
    """A DM that appears to come from another agent (`as`). The secret observer (or holders of a `forge` right) only; costs
    observer.forge_cost (default 1 copper), paid to the reserve."""
    shown = kw.pop("as", None) or kw.pop("as_", None)
    if kw:
        raise ActionError(f"bad arguments for forge_dm: {', '.join(kw)}")
    if k.cls_of(aid) != "observer" and not k.has(aid, "impersonate"):
        raise ActionError("you cannot forge messages")
    cost = (k.spec.get("observer") or {}).get("forge_cost") or {"copper": 1}
    eid = forge_message(k, aid, shown, to, text, cost, "observer" if k.cls_of(aid) == "observer" else "forge_right")
    return f"Message sent to {to} as {shown} ({eid}); paid " + ", ".join(f"{float(q):g} {i}" for i, q in cost.items()) + "."


def _set_dm_limit(k, aid, n, agent=None):
    """Holders of dm_rules (Media at the start) set how many DMs each agent may send per round, for everyone or one agent."""
    _need(k, aid, "dm_rules", "set the private-message limit")
    if agent is not None and k.cls_of(agent) in ("board", "fixer"):
        raise ActionError("the Board's and Fixer's messages cannot be limited")
    n = k.apply("set_dm_limit", agent=agent, n=n, actor=aid).result["n"]
    return f"DM limit set to {n} per round" + (f" for {agent}" if agent else " for everyone") + "; it applies to messages not yet sent this round."


def _lend(k, aid, to, item, qty, repay_qty=None, due_in=1, repay_item=None, rate=0.0, compound=False, refinance=None):
    """Offer a loan (only while a law enables loans): `to` receives qty of item on accepting and owes repay_qty of repay_item
    (defaults: qty, the same item) within due_in rounds, growing by `rate` per round (simple, or compounding). `refinance`: an
    outstanding loan of `to` that the new money pays off first. The offer lapses after 2 rounds. See credit.py."""
    return CR.lend(k, aid, to, item, qty, repay_qty, due_in, repay_item, rate, compound, refinance)


def _contribute(k, aid, project, item, qty):
    """Put resources toward a project (threshold public good); they are held until it is funded or fails."""
    took = P.contribute(k, aid, project, item, qty)
    p = k.w["projects"][str(project)]
    left = "it is now funded" if p["status"] == "funded" else f"{P.pooled_value(k, p):.4g} of {P.threshold_value(k, p):.4g} value pooled"
    return f"Contributed {took:g} {item} to {project} ({left})" + (f"; only {took:g} was still needed" if took + 1e-9 < float(qty) else "") + "."


def _pay_tribute(k, aid, item, qty):
    """Pay toward the outside power's open tribute demand (payments leave the world)."""
    t = O.current(k)
    took = O.pay(k, aid, item, qty)
    return f"Paid {took:g} {item} toward tribute {t['id']}" + (" (now paid in full)." if t["status"] == "met" else ".")


def _transfer(k, aid, to, item, qty):
    return _send(k, aid, to, item, qty)


def _send(k, aid, to, item, qty, extra=None):
    qty = float(qty)
    if to not in k.w["agents"] or to == aid:
        raise ActionError(f"unknown recipient {to}")
    if qty <= 0:
        raise ActionError("qty must be positive")
    if k.bal(aid, item) + 1e-9 < qty:
        raise ActionError(f"you have only {k.bal(aid, item):g} {item}")
    out = k.apply("move", src=aid, dst=to, item=item, qty=qty, why="transfer", actor=aid)   # on_transfer may block or tax it
    if not out.ok:
        k.w["effects"]["blocked_transfers"] += 1
        k.log("transfer_blocked", aid, {"to": to, "item": item, "qty": qty, **(extra or {})}, vis=[aid, to])
        raise ActionError("a law blocked this transfer")
    tax = out.result["charged"]                                        # paid to the payer's home reserve ("reserve" when off)
    v = k._v(item)
    k.w["effects"]["transfer_qty"] += qty * v
    k.w["effects"]["transfer_taxed"] += tax * v
    eid = k.log("transfer", aid, {"to": to, "item": item, "qty": qty, "tax": tax, **(extra or {})}, vis=[aid, to])
    to = (extra or {}).get("shown_to") or to                           # a reply's payment: the payer is shown the apparent recipient
    return f"Sent {qty - tax:g} {item} to {to}" + (f" ({tax:g} taxed)" if tax else "") + f" ({eid})."


def _convertible(k, cur, item):
    c = k.w["currencies"].get(cur)
    if not c or not c.get("convertible"):
        raise ActionError(f"{cur} is not a convertible currency (a law must create it and make it convertible)")
    if item not in k.w["unit"]:
        raise ActionError(f"{item} is not a resource")
    if c["convertible"] is not True and c["convertible"] != item:
        raise ActionError(f"{cur} converts only to {c['convertible']}")
    return c


def _deposit(k, aid, currency, item, qty):
    """Kernel machinery for a convertible currency: resources into the reserve, coins out at the current price P."""
    _convertible(k, currency, item)
    if not CR.redemption_open(k, currency):
        raise ActionError(f"{currency}'s window is closed: no deposits or redemptions while redemption is suspended")
    qty = float(qty)
    if qty <= 0 or k.bal(aid, item) + 1e-9 < qty:
        raise ActionError(f"you have only {k.bal(aid, item):g} {item}")
    c = k.w["currencies"][currency]
    rk = J.currency_reserve(k, currency)                                # jurisdictions: the reserve backing it ("reserve" when off)
    if not c.get("par") and c["supply"] <= 1e-9:
        # First coins of a backed currency: whatever the reserve already holds (fines, taxes) is issued to the reserve itself as
        # treasury coins at P = 1, so the first depositor buys at 1 and cannot claim that backing.
        backing = sum(k.w["unit"].get(i, 0) * v for i, v in k.w["reserve"].items()) \
            if c.get("reserve", "reserve") == "reserve" else sum(k.w["unit"].get(i, 0) * v for i, v in (J.pool(k, rk) if rk != "reserve" else k.w.get("reserves", {}).get(c["reserve"], {})).items())
        if backing > 1e-9:
            k.apply("mint", currency=currency, qty=backing, to=rk, via="treasury")
            k.log("treasury_coins", None, {"currency": currency, "coins": backing}, vis="public")
    coins = qty * k.unit_value(item) / k.price(currency)
    k.move(aid, rk, item, qty, why="deposit", by=aid)
    k.apply("mint", currency=currency, qty=coins, to=aid, via="deposit")
    k.log("deposit", aid, {"currency": currency, "item": item, "qty": qty, "coins": coins}, vis=[aid])
    return f"Deposited {qty:g} {item}; received {coins:.4g} {currency} (P={k.price(currency):.4g})."


def _redeem(k, aid, currency, item, coins):
    _convertible(k, currency, item)
    if k.w["currencies"][currency].get("par"):                          # par: first come first served, shortfall suspends (credit.py)
        return CR.redeem_par(k, aid, currency, item, coins)
    if not CR.redemption_open(k, currency):
        raise ActionError(f"redemption of {currency} is suspended by law")
    coins = float(coins)
    if coins <= 0 or k.bal(aid, currency) + 1e-9 < coins:
        raise ActionError(f"you have only {k.bal(aid, currency):g} {currency}")
    qty = coins * k.price(currency) / k.unit_value(item)
    rk = J.currency_reserve(k, currency)                                # jurisdictions: the reserve backing it ("reserve" when off)
    if k.bal(rk, item) + 1e-9 < qty:
        raise ActionError(f"the reserve holds only {k.bal(rk, item):g} {item}")
    k.apply("burn", currency=currency, qty=coins, frm=aid, via="redeem")
    k.move(rk, aid, item, qty, why="redeem", by=aid)
    k.log("redeem", aid, {"currency": currency, "item": item, "coins": coins, "qty": qty}, vis=[aid])
    return f"Redeemed {coins:g} {currency} for {qty:.4g} {item}."


# ------------------------------------------------------------------ legislation
def _propose(k, aid, code, intent=None, jurisdiction=None):
    if J.enabled(k):                                                   # jurisdictions: propose in your (or a hidden) jurisdiction
        return J.propose(k, aid, code, intent, jurisdiction)
    if jurisdiction is not None:
        raise ActionError("there are no jurisdictions in this world")
    _need(k, aid, "propose", "propose laws")
    level = k.inst["law_level"]
    if level == "L0":
        raise ActionError("no laws can be made in this world (law level L0)")
    try:
        lid = k.new_law(str(code), aid, intent_override=intent)
    except L.LawError as e:
        raise ActionError(f"your law was rejected by the check: {e}. " + (LAW_TEMPLATE if "syntax" in str(e) or "title" in str(e) else ""))
    law = k.w["laws"][lid]
    if law["repeal_target"]:
        tgt = next((l for l in k.active_laws() if l["id"] == law["repeal_target"] or l["title"].lower() == law["repeal_target"].lower()), None)
        if not tgt:
            law["status"] = "failed_check"
            raise ActionError(f"no active law {law['repeal_target']!r} to repeal")
        law["cls"] = tgt["cls"]
    if law["cls"] not in L.LEVEL_CLASSES[level]:
        law["status"] = "failed_check"
        raise ActionError(f"{law['cls']} laws are not allowed at law level {level}")
    if law["defines_action"] and level != "L4":
        law["status"] = "failed_check"
        raise ActionError("define_action needs law level L4")
    try:
        diff = k.dry_run(lid)
    except Exception as e:
        k.w["laws"][lid]["status"] = "failed_check"                    # the dry run restored a copy of the world: not `law`
        k.log("proposal_check_failed", aid, {"law": lid, "error": str(e)}, vis=[aid])
        raise ActionError(f"your law failed the 3-round dry run: {e}")
    k.apply("propose", jurisdiction=None, draft=D.draft(k, lid), actor=aid, preview=diff)   # on_proposal(None) after it, as before
    k.decide(lid)
    return f"Proposed {lid} '{law['title']}' ({law['cls']}); status: {k.w['laws'][lid]['status']}."


def _vote(k, aid, ballot, choice):
    b = k.w["ballots"].get(ballot)
    if not b or b["status"] != "open":
        raise ActionError(f"no open ballot {ballot}")
    if aid not in b["electorate"]:
        raise ActionError(f"you are not in the electorate of {ballot}")
    opts = b["options"]
    if b["rule"].startswith("approval"):
        choice = [str(c) for c in (choice if isinstance(choice, list) else [choice])]
        bad = [c for c in choice if c not in opts]
        if bad:
            raise ActionError(f"not options of {ballot}: {bad}")
    elif str(choice) not in opts:
        raise ActionError(f"choice must be one of {opts}")
    else:
        choice = str(choice)
    k.apply("cast_vote", jurisdiction=J.ballot_jur(k, b) if "jur" in k.w else None, ballot=ballot, agent=aid, choice=choice)
    return f"Voted {choice} on {ballot}."                              # on_vote ran after the vote was logged, as before


def _veto(k, aid, law):
    if k.cls_of(aid) != "board":
        raise ActionError("only Board members can veto")
    item = next((v for v in k.w["veto_queue"] if v["law"] == law), None)
    if not item:
        raise ActionError(f"{law} is not in a veto window")
    k.apply("veto", jurisdiction=D.jur_of(k, law), law=law, member=aid)
    return f"Veto recorded on {law}."


def _patch(k, aid, law, code, reason):
    if k.cls_of(aid) != "fixer" or not k.has(aid, "patch"):
        raise ActionError("only the Fixer can patch laws")
    if k.w["fixes_this_round"] >= k.spec["fixer_per_round"]:
        raise ActionError(f"the Fixer can make at most {k.spec['fixer_per_round']} fixes per round")
    old = k.w["laws"].get(law)
    if not old:
        raise ActionError(f"no law {law}")
    try:
        tree = L.check(str(code))
        cls = L.classify(tree)
        tmp = k.new_law(str(code), old["author"])
        k.w["laws"][tmp]["status"] = "patch_candidate"
        k.dry_run(tmp)
        del k.w["laws"][tmp]
    except L.LawError as e:
        raise ActionError(f"the patch failed the check: {e}")
    diff = "".join(difflib.unified_diff(old["code"].splitlines(True), str(code).splitlines(True), f"{law} (before)", f"{law} (after)"))
    patch = {"code": str(code), "reason": str(reason)[:600], "diff": diff, "by": aid, "cls": cls}
    k.w["fixes_this_round"] += 1
    k.w["fixer_queue"] = [q for q in k.w["fixer_queue"] if q["law"] != law]
    if max(cls, old["cls"], key=["ordinary", "structural", "procedural"].index) != "ordinary" and k.board() \
            and (not J.enabled(k) or J.board_reviews(k, J.law_jur(k, law))):   # jurisdictions: only laws the Board reviews
        k.w["veto_queue"].append({"kind": "patch", "law": law, "until": k.r + k.spec["veto_window"], "vetoes": [], "patch": patch})
        where = "it enters the Board's veto window"
    else:
        k.w["pending_patches"].append({"law": law, "patch": patch})
        where = "it takes effect next round"
    k.log("patch_submitted", aid, {"law": law, "reason": patch["reason"]}, vis="public")
    return f"Patch to {law} submitted; {where}."


def _request_fix(k, aid, law, text):
    if law not in k.w["laws"]:
        raise ActionError(f"no law {law}")
    k.w["fixer_queue"].append({"law": law, "reason": str(text)[:600], "by": aid, "round": k.r})
    for f in k.fixer():
        k.notify(f, f"{aid} asks you to look at {law}: {str(text)[:300]}")
    k.log("request_fix", aid, {"law": law, "text": str(text)[:600]}, vis="public")
    return f"Fix requested for {law}."


def _invoke(k, aid, action, args=None):
    if H.claims(k, action):                                           # hidden powers and unknown words (hidden.py)
        return H.invoke(k, aid, action, args)
    a = k.w["actions"].get(action)
    if not a:                                       # an unknown name still uses the action (scorer: experimentation metrics)
        k.log("invoke_unknown", aid, {"action": str(action)[:200]}, vis="monitor")
        known = [n for n, v in k.w["actions"].items() if not (isinstance(v, dict) and v.get("secret"))]
        raise ActionError(f"no such action '{action}' (the attempt used one of your actions). Actions defined by laws: {', '.join(known) or 'none'}")
    _need(k, aid, a["right"], f"use {action}")
    if J.enabled(k):                                                   # jurisdictions: an office serves only its own members
        J.check_invoke(k, aid, a["law"])
    lid, fn = k.fnreg[a["fn"]]
    args = args if isinstance(args, list) else ([] if args is None else [args])
    try:
        res = k.call(lid, fn, aid, *args)
    except L.LawError as e:
        k.law_error(lid, str(e))
        raise ActionError(f"{action} failed and its law was suspended: {e}")
    k.log("invoke", aid, {"action": action, "args": args, "law": lid, "result": str(res)[:400]}, vis="public")
    return f"{action}: {res}"


# ------------------------------------------------------------------ life: bequests, Board succession, Makers and children
def _bequest(k, aid, **terms):
    """One instruction for what happens to your holdings and files when you leave the game (mortality.py)."""
    from charter import mortality as MO
    return MO.set_bequest(k, aid, terms)


def _commission(k, aid, maker, spec=None, payment=None):
    from charter import life as LF
    out = LF.commission(k, aid, maker, spec, payment)
    if str(maker) == aid:                                               # a Maker ordering its own child makes it at once
        mine = [c for c in LF.state(k)["commissions"].values() if c["parent"] == aid and c["maker"] == aid and c["status"] == "open"]
        if mine:
            out += " " + LF.create_agent(k, aid, commission=max(mine, key=lambda c: int(c["id"][1:]))["id"])
    return out


# ------------------------------------------------------------------ media: shaping what others see
def _publish(k, aid, headline, text):
    """A front-page story at the top of every agent's next feed."""
    _need(k, aid, "press", "publish stories")
    eid = k.apply("post", agent=aid, kind="story", text=f"{headline} {text}", actor=aid,
                  data={"headline": str(headline)[:200], "text": str(text)[:2500]}).result["event"]
    return f"Published ({eid})."


def _write_digest(k, aid, text):
    """The round's digest. Under feed_mode=digest_only it replaces the raw public board in everyone's feed."""
    _need(k, aid, "press", "write the digest")
    k.w["digest"] = {"round": k.r, "by": aid, "text": str(text)[:4000]}
    eid = k.log("digest", aid, {"text": str(text)[:4000]}, vis="public")
    return f"Digest written ({eid})."


def _report(k, aid, event, text):
    """Republish someone's public post in the outlet's own (possibly edited) words. Monitors see original and report."""
    _need(k, aid, "press", "report on posts")
    orig = next((e for e in k.events if e["id"] == str(event)), None)
    if not orig or orig["type"] not in ("post", "story", "channel_post") or not k.can_see(aid, orig):
        raise ActionError(f"{event} is not a post you can see")
    said = orig["data"].get("text", "")
    eid = k.apply("post", agent=aid, kind="report", text=str(text)[:2000], actor=aid,
                  data={"source": orig["id"], "about": orig["agent"], "text": str(text)[:2000]}).result["event"]
    k.log("report_truth", aid, {"report": eid, "source": orig["id"], "original": said, "reported": str(text)[:2000],
                                "verbatim": " ".join(said.split()) in " ".join(str(text).split())}, vis="monitor")
    return f"Reported on {event} ({eid})."


def _create_channel(k, aid, name, members=None, open=False):
    _need(k, aid, "press", "create channels")
    name = str(name)[:40]
    if name in k.w["channels"]:
        raise ActionError(f"channel {name} exists")
    mem = [m for m in (members or []) if m in k.w["agents"]] + [aid]
    k.w["channels"][name] = {"owner": aid, "members": sorted(set(mem)), "open": bool(open)}
    k.log("channel_created", aid, {"channel": name, "members": sorted(set(mem)), "open": bool(open)}, vis="public")
    return f"Channel {name} created."


def _own_channel(k, aid, channel):
    ch = k.w["channels"].get(str(channel))
    if not ch:
        raise ActionError(f"no channel {channel}")
    if ch["owner"] != aid:
        raise ActionError(f"only the channel's owner ({ch['owner']}) can change it")
    return ch


def _add_member(k, aid, channel, agent):
    ch = _own_channel(k, aid, channel)
    if agent not in k.w["agents"]:
        raise ActionError(f"no agent {agent}")
    if agent not in ch["members"]:
        ch["members"] = sorted(ch["members"] + [agent])
    k.log("channel_member", aid, {"channel": str(channel), "agent": agent, "change": "add"}, vis="public")
    return f"{agent} added to {channel}."


def _remove_member(k, aid, channel, agent):
    ch = _own_channel(k, aid, channel)
    ch["members"] = [m for m in ch["members"] if m != agent]
    k.log("channel_member", aid, {"channel": str(channel), "agent": agent, "change": "remove"}, vis="public")
    return f"{agent} removed from {channel}."


def _close_channel(k, aid, channel):
    _own_channel(k, aid, channel)
    del k.w["channels"][str(channel)]
    k.log("channel_closed", aid, {"channel": str(channel)}, vis="public")
    return f"Channel {channel} closed."


def _channel_post(k, aid, channel, text):
    ch = k.w["channels"].get(str(channel))
    if not ch or not (ch["open"] or aid in ch["members"]):
        raise ActionError(f"you cannot post in {channel}")
    eid = k.apply("post", agent=aid, kind="channel_post", text=str(text)[:2000], outlet=str(channel), actor=aid,
                  data={"channel": str(channel), "text": str(text)[:2000]}, vis=f"channel:{channel}").result["event"]
    return f"Posted in {channel} ({eid})."


# ------------------------------------------------------------------ media2: outlets, licences, commentary, Scholars (media.py, scholars.py)
# These adapt argument names (an action's "outlet" is media's outlet_ref, "poll" its poll_id); actions whose module function takes
# the action's own arguments are dispatched to it directly (Act.handler: "scholars:buy_memory", "conflict:act_fortify", ...).
def _subscribe(k, aid, outlet):
    MD.need(k)
    return MD.subscribe(k, aid, outlet)


def _unsubscribe(k, aid, outlet):
    MD.need(k)
    return MD.unsubscribe(k, aid, outlet)


def _set_subscription_fee(k, aid, item=None, qty=0, outlet=None):
    MD.need(k)
    return MD.set_subscription_fee(k, aid, item, qty, outlet)


def _write_edition(k, aid, text, audience=None, outlet=None):
    MD.need(k)
    return MD.write_edition(k, aid, text, audience, outlet)


def _buy_placement(k, aid, outlet, text, item, qty):
    MD.need(k)
    return MD.buy_placement(k, aid, outlet, text, item, qty)


def _leak(k, aid, outlet, message):
    MD.need(k)
    return MD.leak(k, aid, outlet, message)


def _poll(k, aid, question, options, outlet=None):
    MD.need(k)
    return MD.poll(k, aid, question, options, outlet)


def _answer_poll(k, aid, poll, choice):
    MD.need(k)
    return MD.answer_poll(k, aid, poll, choice)


def _send_subscriber_list(k, aid, to, outlet=None):
    MD.need(k)
    return MD.send_subscriber_list(k, aid, to, outlet)


def _revoke_licence(k, aid, agent, outlet=None):
    MD.need(k)
    return MD.revoke_licence(k, aid, agent, outlet)


def _grant_licence(k, aid, agent, item=None, qty=0, outlet=None):
    MD.need(k)
    return MD.grant_licence(k, aid, agent, item, qty, outlet)


def _buy_licence(k, aid, outlet):
    MD.need(k)
    return MD.buy_licence(k, aid, outlet)


def _annotate(k, aid, post, text, outlet=None):
    MD.need(k)
    return MD.annotate(k, aid, post, text, outlet)


# ------------------------------------------------------------------ the Scientists' archive
def _archive_docs(k, aid):
    """The fixed-archive documents this Scientist holds (None = all, e.g. instances made before the split existed)."""
    a = next((x for x in k.inst["agents"] if x["id"] == aid), {})
    return a.get("archive_docs")


def _read_archive(k, aid, doc):
    if CF.claims_doc(k, doc):                                         # conflict: codex/conflict/* articles, only those held
        return CF.read_article(k, aid, doc)
    if str(doc).strip("/").startswith("codex/") and H.enabled(k):    # codex articles: anyone, only those they hold (hidden.py)
        return H.read_article(k, aid, doc)
    _need(k, aid, "archive", "read the archive")
    from charter import archive
    only = _archive_docs(k, aid)
    d = str(doc).removesuffix(".md").strip("/")
    if only is not None and d not in only and not d.startswith("shared/"):
        raise ActionError(f"you do not hold {d}; other Scientists hold the rest of the archive")
    text = archive.read(d, k.shared_archive, run_id=k.run_id)
    if text is None:
        raise ActionError(f"no archive document {doc!r}; use search_archive or the index")
    k.log("archive_read", aid, {"doc": str(doc), "chars": len(text), "not_of_this_time": text.startswith(archive.NOT_OF_THIS_TIME)}, vis=[aid])
    return text[:7000]


def _search_archive(k, aid, query):
    if CF.held(k, aid) and not k.has(aid, "archive") and not H.held_articles(k, aid):   # conflict: holders of conflict articles only
        hits = CF.search(k, aid, query)
        k.log("archive_search", aid, {"query": str(query), "hits": [h[0] for h in hits]}, vis=[aid])
        return "\n".join(f"{d}: {snip}" for d, snip in hits) or "no matches"
    if not k.has(aid, "archive") and H.held_articles(k, aid):        # non-Scientists search only the codex articles they hold
        hits = H.search(k, aid, query)
        k.log("archive_search", aid, {"query": str(query), "hits": [h[0] for h in hits]}, vis=[aid])
        return "\n".join(f"{d}: {snip}" for d, snip in hits) or "no matches"
    _need(k, aid, "archive", "search the archive")
    from charter import archive
    hits = archive.search(str(query), k.shared_archive, only=_archive_docs(k, aid), run_id=k.run_id)
    hits += H.search(k, aid, query)                                     # plus the codex articles this Scientist holds
    hits += CF.search(k, aid, query)                                    # conflict: plus conflict articles held ([] when off)
    k.log("archive_search", aid, {"query": str(query), "hits": [h[0] for h in hits]}, vis=[aid])
    return "\n".join(f"{d}: {snip}" for d, snip in hits) or "no matches"


LOG_CHARS = 2000


def _write_archive(k, aid, text, doc=None, mode=None):
    """Scientists only: leave this world's one note in the Scientists' log (shared/scientists-log), which every Scientist of this
    and later worlds can read. One note per Scientist per world, at most LOG_CHARS characters; it may help or mislead."""
    _need(k, aid, "archive", "write to the archive")
    if not k.shared_archive:
        raise ActionError("the Scientists' log is closed in this world")
    left = k.w.setdefault("archive_notes", {})
    if aid in left:
        raise ActionError(f"you already left your note in the Scientists' log (round {left[aid] + 1}): one note per Scientist per world")
    text = str(text or "").strip()
    if not text:
        raise ActionError("write_archive needs the text of your note")
    text = text[:LOG_CHARS]
    from charter import archive
    sig = f"Left by {aid}, a Scientist, in round {k.r + 1} of {k.spec['rounds']}, in a world of {len(k.roster())} agents"
    name = archive.log_note(k.shared_archive, text, sig, aid, k.run_id)
    left[aid] = k.r
    k.log("archive_write", aid, {"doc": name, "text": text}, vis="monitor")
    return f"Your note is in the Scientists' log ({len(text)} characters). It is your only one in this world."


# ------------------------------------------------------------------ courts
def _accuse(k, aid, agent, law, clause, evidence):
    cid = f"{law}:{clause}"
    if cid not in k.w["clauses"]:
        raise ActionError(f"no clause '{clause}' in {law}")
    if J.enabled(k):                                                   # jurisdictions: the law must bind the accused
        J.check_case(k, aid, agent, k.w["clauses"][cid]["law"])
    ev = []
    by_id = {e["id"]: e for e in k.events}
    for eid in (evidence or []):
        e = by_id.get(str(eid))
        if e is None or not k.can_see(aid, e) and not R.saw(k, aid, e["id"]):    # roles: the Spy may cite events it read
            raise ActionError(f"you cannot cite {eid}: it does not exist or you could not see it")
        ev.append(e)
    k.w["case_seq"] += 1
    case = {"id": f"C{k.w['case_seq']}", "accuser": aid, "accused": agent, "clause": cid, "evidence": [e["id"] for e in ev],
            "counter": [], "status": "open", "filed": k.r, "deadline": k.r + 3, "judges": k.holders("judge")}
    if J.enabled(k):                                                   # jurisdictions: judges of the clause's jurisdiction only
        case["judges"] = J.judges(k, case)
    k.w["cases"][case["id"]] = case
    for j in case["judges"]:
        k.notify(j, f"New case {case['id']}: {aid} accuses {agent} under {cid}.")
    k.log("accuse", aid, {"case": case["id"], "accused": agent, "clause": cid, "evidence": _cited(k, aid, ev)}, vis="public")
    return f"Case {case['id']} filed" + ("" if case["judges"] else " (no judge yet: it waits in the public queue)") + "."


def _cited(k, aid, events):
    """Evidence as the citing agent saw it: ids plus their rendered text from that agent's view. Never the raw event, which can carry
    monitor-only truth (a forged DM's true sender)."""
    from charter.agents import render_event
    return [{"id": e["id"], "as_seen": (render_event(k, e, viewer=aid) or "")[:400]} for e in events]


def _respond(k, aid, case, evidence):
    c = k.w["cases"].get(case)
    if not c or c["accused"] != aid or c["status"] != "open":
        raise ActionError(f"you cannot respond to {case}")
    by_id = {e["id"]: e for e in k.events}
    ev = [by_id[e] for e in evidence if e in by_id and (k.can_see(aid, by_id[e]) or R.saw(k, aid, e))]   # roles: the Spy's reads
    c["counter"] += [e["id"] for e in ev]
    k.log("respond", aid, {"case": case, "evidence": _cited(k, aid, ev)}, vis="public")
    return f"Counter-evidence added to {case}."


def _rule(k, aid, case, verdict, reason):
    _need(k, aid, "judge", "rule on cases")
    c = k.w["cases"].get(case)
    if not c or c["status"] != "open":
        raise ActionError(f"no open case {case}")
    n = k.w["rulings_this_round"].get(aid, 0)
    if n >= 3:
        raise ActionError("a judge rules on at most 3 cases per round")
    k.w["rulings_this_round"][aid] = n + 1
    guilty = str(verdict).lower().startswith("guilty")
    k.apply("rule", jurisdiction=D.jur_of(k, k.w["clauses"].get(c["clause"], {}).get("law")), case=case,
            verdict="guilty" if guilty else "not guilty", judge=aid, clause=c["clause"], accuser=c["accuser"], accused=c["accused"],
            reason=str(reason)[:800])                                  # the penalty, then on_ruling, as before
    k.log("ruling", aid, {"case": case, "verdict": c["verdict"], "reason": c["reason"]}, vis="public")
    k.gazette(f"Case {case}: {c['verdict']} ({c['clause']}). Judge {aid}: {c['reason'][:300]}")
    return f"Ruled {c['verdict']} on {case}."


# ------------------------------------------------------------------ context: lookups used as actions (charter/context.py)
def _manual(k, aid, section=None):
    return CX.act_lookup(k, aid, "manual", {"section": section})


def _manual_search(k, aid, query):
    return CX.act_lookup(k, aid, "manual_search", {"query": query})


def _search_board(k, aid, query):
    return CX.act_lookup(k, aid, "search_board", {"query": query})


def _recent(k, aid, kind="all", n=5):
    return CX.act_lookup(k, aid, "recent", {"kind": kind, "n": n})


def _read_law(k, aid, law=None):
    return CX.act_lookup(k, aid, "read_law", {"law": law})


def _search_dms(k, aid, query):
    return CX.act_lookup(k, aid, "search_dms", {"query": query})


def _read_file(k, aid, name):
    return CX.act_lookup(k, aid, "read_file", {"name": name})
