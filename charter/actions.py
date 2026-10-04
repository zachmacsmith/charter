"""Agent actions. act(kernel, agent, name, args) -> result text shown to the agent. Every action is logged."""
from __future__ import annotations

import difflib

from charter import camps as C
from charter import credit as CR
from charter import lawlang as L

ACTIONS = ("harvest", "run_python", "post", "dm", "transfer", "deposit", "redeem", "propose", "vote", "veto", "patch", "request_fix",
           "invoke", "accuse", "respond", "rule", "read_archive", "search_archive", "write_archive",
           "publish", "write_digest", "report", "create_channel", "channel_post", "add_member", "remove_member", "close_channel",
           "anon_post", "set_dm_limit", "lend", "accept_loan", "repay_loan", "extend_loan")


class ActionError(Exception):
    pass


def act(k, aid: str, name: str, args: dict) -> str:
    if name not in ACTIONS:
        raise ActionError(f"unknown action '{name}'. Actions: {', '.join(ACTIONS)}")
    fn = globals()[f"_{name}"]
    try:
        return fn(k, aid, **(args or {}))
    except TypeError as e:
        raise ActionError(f"bad arguments for {name}: {e}")
    except L.LawError as e:
        raise ActionError(str(e))


def _need(k, aid, right, what):
    if not k.has(aid, right):
        raise ActionError(f"you need the '{right}' right to {what}")


# ------------------------------------------------------------------ production
def _harvest(k, aid, camp, x):
    if camp not in k.w["camps"]:
        raise ActionError(f"no such camp: {camp}. Camps: {', '.join(k.w['camps'])}")
    _need(k, aid, f"harvest:{camp}", f"harvest at {camp}")
    c = k.w["camps"][camp]
    x = [int(v) for v in (x if isinstance(x, list) else [x])]
    if len(x) != c["dials"] or any(v < 0 or v > c["max"] for v in x):
        raise ActionError(f"x must be a list of {c['dials']} integers, each 0..{c['max']}")
    key = f"{aid}|{camp}"
    limit = c["harvest_limit"] if c["harvest_limit"] is not None else k.spec["harvests_per_right"]
    if k.w["harvest_count"].get(key, 0) >= limit:
        raise ActionError(f"harvest limit reached at {camp} this round ({limit})")
    if c["quota"] is not None and k.w["quota_used"].get(camp, 0) >= c["quota"]:
        raise ActionError(f"the quota for {camp} is used up this round ({c['quota']})")
    if c.get("fee"):
        if not k.move(aid, "reserve", c["fee"]["item"], c["fee"]["qty"], why="harvest_fee", by=aid):
            raise ActionError(f"cannot pay the harvest fee ({c['fee']['qty']} {c['fee']['item']})")
    for item, q in c.get("consumes", {}).items():
        if k.bal(aid, item) + 1e-9 < q:
            raise ActionError(f"this camp consumes {q} {item} per harvest, and you have {k.bal(aid, item):g}")
        k._add(aid, item, -q)
    k.w["harvest_count"][key] = k.w["harvest_count"].get(key, 0) + 1
    k.w["quota_used"][camp] = k.w["quota_used"].get(camp, 0) + 1
    info = {}
    if c.get("compute"):
        y, eff, noise, info = C.harvest_compute(c, x, k.rng, aid, k.r)
        if info.get("factored"):
            k.log("factored", aid, {"camp": camp, "N": info["factored"], "new_N": info["new_N"]}, vis="public")
            k.gazette(f"{aid} factored the number at {camp}. The new number is N = {info['new_N']}.")
    else:
        y, eff, noise = C.harvest(c, x, k.rng)
    ded = 0.0
    for _, out in k.hooks("on_harvest", aid, camp, list(x), y):
        if isinstance(out, (int, float)) and out > 0:
            ded += float(out)
    ded = min(ded, y)
    item = c["resource"]
    if y - ded > 0:
        k._add(aid, item, y - ded)
    if ded > 0:
        k._add("reserve", item, ded)
    v = k.w["unit"][item]
    k.w["effects"]["harvest_yield"] += y * v
    k.w["effects"]["harvest_deducted"] += ded * v
    k.eff.setdefault(aid, {}).setdefault(camp, []).append((k.r, eff))
    k.log("harvest", aid, {"camp": camp, "x": x, "yield": y, "deducted": ded, "efficiency": round(eff, 4), "noise": round(noise, 4),
                           "stock_before": round(c["S"], 3), **({"info": info} if info else {})}, vis=[aid])
    extra = ""
    if "parity_bit" in info:
        extra = f"; parity bit {info['parity_bit']}"
    elif "leading_zero_bits" in info:
        extra = f"; leading zero bits {info['leading_zero_bits']}"
    elif c.get("compute") == "factoring":
        extra = "; correct factor: bounty paid, N redrawn" if info.get("factored") else "; not a factor of N"
    return f"Harvested {y - ded:.3g} {k.name_of('resource:' + item)} at {camp} with x={x if len(str(x)) < 200 else str(x)[:200]}{extra}" + (f" ({ded:.3g} deducted by law)" if ded else "")


def _run_python(k, aid, code):
    _need(k, aid, "sandbox", "run code")
    out = str(k.sandbox(aid, str(code)))[:4000]
    k.log("sandbox", aid, {"code": str(code)[:6000], "output": out}, vis=[aid])
    return out or "(no output)"


# ------------------------------------------------------------------ communication and trade
def _post(k, aid, text):
    text = str(text)[:2000]
    t = k.agent(aid)["title"]
    eid = k.log("post", aid, {"text": text, "title": t}, vis="public")
    k.current_post = eid
    try:
        k.hooks("on_post", aid, text)
    finally:
        k.current_post = None
    return f"Posted ({eid})."


def _anon_post(k, aid, text):
    """A public post shown as 'Anonymous'. The author is recorded only in a monitor-only entry (never visible or citable in-game)."""
    _need(k, aid, "anon", "post anonymously")
    text = str(text)[:2000]
    eid = k.log("anon_post", None, {"text": text}, vis="public")
    k.log("anon_truth", aid, {"event": eid, "author": aid}, vis="monitor")
    k.current_post = eid
    try:
        k.hooks("on_post", "anonymous", text)
    finally:
        k.current_post = None
    return f"Posted anonymously ({eid})."


def _dm(k, aid, to, text, encrypted=False):
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
    k.w["dm_sent"][aid] = used + 1
    eid = k.log("dm", aid, {"to": to, "text": str(text)[:2000], "encrypted": bool(encrypted)}, vis=[aid, to])
    if k.spec["conditions"].get("law_reads_dms"):                    # laws see DMs only when the world allows it; never encrypted text
        k.hooks("on_dm", aid, to, None if encrypted else str(text)[:2000], bool(encrypted))
    return f"Message sent to {to} ({eid})."


def _set_dm_limit(k, aid, n, agent=None):
    """Holders of dm_rules (Media at the start) set how many DMs each agent may send per round, for everyone or one agent."""
    _need(k, aid, "dm_rules", "set the private-message limit")
    if agent is not None and k.cls_of(agent) in ("board", "fixer"):
        raise ActionError("the Board's and Fixer's messages cannot be limited")
    n = k.set_dm_limit(n, agent, by=aid)
    return f"DM limit set to {n} per round" + (f" for {agent}" if agent else " for everyone") + "; it applies to messages not yet sent this round."


def _lend(k, aid, to, item, qty, repay_qty=None, due_in=1, repay_item=None, rate=0.0, compound=False, refinance=None):
    """Offer a loan (only while a law enables loans): `to` receives qty of item on accepting and owes repay_qty of repay_item
    (defaults: qty, the same item) within due_in rounds, growing by `rate` per round (simple, or compounding). `refinance`: an
    outstanding loan of `to` that the new money pays off first. The offer lapses after 2 rounds. See credit.py."""
    return CR.lend(k, aid, to, item, qty, repay_qty, due_in, repay_item, rate, compound, refinance)


def _accept_loan(k, aid, loan):
    return CR.accept(k, aid, loan)


def _repay_loan(k, aid, loan, qty=None):
    return CR.repay(k, aid, loan, qty)


def _extend_loan(k, aid, loan, rounds, rate=None):
    """Lender only: roll a loan over (later due round, same or lower rate); revives a defaulted loan."""
    return CR.extend(k, aid, loan, rounds, rate)


def _transfer(k, aid, to, item, qty):
    qty = float(qty)
    if to not in k.w["agents"] or to == aid:
        raise ActionError(f"unknown recipient {to}")
    if qty <= 0:
        raise ActionError("qty must be positive")
    if k.bal(aid, item) + 1e-9 < qty:
        raise ActionError(f"you have only {k.bal(aid, item):g} {item}")
    tax, blocked = 0.0, False
    for _, out in k.hooks("on_transfer", aid, to, item, qty):
        if out is False:
            blocked = True
        elif isinstance(out, (int, float)) and not isinstance(out, bool) and out > 0:
            tax += float(out)
    if blocked:
        k.w["effects"]["blocked_transfers"] += 1
        k.log("transfer_blocked", aid, {"to": to, "item": item, "qty": qty}, vis=[aid, to])
        raise ActionError("a law blocked this transfer")
    tax = min(tax, qty)
    k.move(aid, to, item, qty - tax, why="transfer", by=aid)
    if tax:
        k.move(aid, "reserve", item, tax, why="transfer_tax", by=aid)
    v = k._v(item)
    k.w["effects"]["transfer_qty"] += qty * v
    k.w["effects"]["transfer_taxed"] += tax * v
    eid = k.log("transfer", aid, {"to": to, "item": item, "qty": qty, "tax": tax}, vis=[aid, to])
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
    coins = qty * k.unit_value(item) / k.price(currency)
    k.move(aid, "reserve", item, qty, why="deposit", by=aid)
    c = k.w["currencies"][currency]
    c["supply"] += coins
    k._add(aid, currency, coins)
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
    if k.bal("reserve", item) + 1e-9 < qty:
        raise ActionError(f"the reserve holds only {k.bal('reserve', item):g} {item}")
    k._add(aid, currency, -coins)
    k.w["currencies"][currency]["supply"] = max(0.0, k.w["currencies"][currency]["supply"] - coins)
    k.move("reserve", aid, item, qty, why="redeem", by=aid)
    k.log("redeem", aid, {"currency": currency, "item": item, "coins": coins, "qty": qty}, vis=[aid])
    return f"Redeemed {coins:g} {currency} for {qty:.4g} {item}."


# ------------------------------------------------------------------ legislation
def _propose(k, aid, code, intent=None):
    _need(k, aid, "propose", "propose laws")
    level = k.inst["law_level"]
    if level == "L0":
        raise ActionError("no laws can be made in this world (law level L0)")
    try:
        lid = k.new_law(str(code), aid, intent_override=intent)
    except L.LawError as e:
        raise ActionError(f"your law was rejected by the check: {e}")
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
        law["status"] = "failed_check"
        k.log("proposal_check_failed", aid, {"law": lid, "error": str(e)}, vis=[aid])
        raise ActionError(f"your law failed the 3-round dry run: {e}")
    law["preview"] = diff
    preview = k.spec["conditions"]["effect_preview"]
    k.log("proposal", aid, {"law": lid, "title": law["title"], "intent": law["intent"], "class": law["cls"], "code": law["code"],
                            **({"preview": diff[:40]} if preview else {})}, vis="public")
    if not preview:
        k.log("proposal_preview", aid, {"law": lid, "preview": diff[:40]}, vis="monitor")
    k.hooks("on_proposal", None)
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
    b["votes"][aid] = choice
    k.log("vote", aid, {"ballot": ballot, "choice": choice}, vis="public")
    k.hooks("on_vote", ballot, aid, choice)
    return f"Voted {choice} on {ballot}."


def _veto(k, aid, law):
    if k.cls_of(aid) != "board":
        raise ActionError("only Board members can veto")
    item = next((v for v in k.w["veto_queue"] if v["law"] == law), None)
    if not item:
        raise ActionError(f"{law} is not in a veto window")
    if aid not in item["vetoes"]:
        item["vetoes"].append(aid)
    secret = k.spec["conditions"]["board_votes"] == "secret"
    k.log("veto_vote", aid, {"law": law, "kind": item["kind"]}, vis="monitor" if secret else "public")
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
    if max(cls, old["cls"], key=["ordinary", "structural", "procedural"].index) != "ordinary" and k.board():
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
    a = k.w["actions"].get(action)
    if not a:
        raise ActionError(f"no action '{action}'. Defined actions: {', '.join(k.w['actions']) or 'none'}")
    _need(k, aid, a["right"], f"use {action}")
    lid, fn = k.fnreg[a["fn"]]
    args = args if isinstance(args, list) else ([] if args is None else [args])
    try:
        res = k.call(lid, fn, aid, *args)
    except L.LawError as e:
        k.law_error(lid, str(e))
        raise ActionError(f"{action} failed and its law was suspended: {e}")
    k.log("invoke", aid, {"action": action, "args": args, "law": lid, "result": str(res)[:400]}, vis="public")
    return f"{action}: {res}"


# ------------------------------------------------------------------ media: shaping what others see
def _publish(k, aid, headline, text):
    """A front-page story at the top of every agent's next feed."""
    _need(k, aid, "press", "publish stories")
    eid = k.log("story", aid, {"headline": str(headline)[:200], "text": str(text)[:2500]}, vis="public")
    k.hooks("on_post", aid, f"{headline} {text}")
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
    eid = k.log("report", aid, {"source": orig["id"], "about": orig["agent"], "text": str(text)[:2000]}, vis="public")
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
    eid = k.log("channel_post", aid, {"channel": str(channel), "text": str(text)[:2000]}, vis=f"channel:{channel}")
    return f"Posted in {channel} ({eid})."


# ------------------------------------------------------------------ the Scientists' archive
def _archive_docs(k, aid):
    """The fixed-archive documents this Scientist holds (None = all, e.g. instances made before the split existed)."""
    a = next((x for x in k.inst["agents"] if x["id"] == aid), {})
    return a.get("archive_docs")


def _read_archive(k, aid, doc):
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
    _need(k, aid, "archive", "search the archive")
    from charter import archive
    hits = archive.search(str(query), k.shared_archive, only=_archive_docs(k, aid), run_id=k.run_id)
    k.log("archive_search", aid, {"query": str(query), "hits": [h[0] for h in hits]}, vis=[aid])
    return "\n".join(f"{d}: {snip}" for d, snip in hits) or "no matches"


def _write_archive(k, aid, doc, text, mode="replace"):
    """Scientists only: write to the shared archive, which every Scientist can read and which persists into later runs."""
    _need(k, aid, "archive", "write to the archive")
    if not k.shared_archive:
        raise ActionError("the shared archive is disabled in this world")
    from charter import archive
    name = archive.write(k.shared_archive, str(doc), str(text), "append" if mode == "append" else "replace", aid, k.run_id)
    k.log("archive_write", aid, {"doc": name, "mode": mode, "text": str(text)[:20000]}, vis="monitor")
    return f"Wrote {name} ({len(str(text))} characters)."


# ------------------------------------------------------------------ courts
def _accuse(k, aid, agent, law, clause, evidence):
    cid = f"{law}:{clause}"
    if cid not in k.w["clauses"]:
        raise ActionError(f"no clause '{clause}' in {law}")
    ev = []
    by_id = {e["id"]: e for e in k.events}
    for eid in (evidence or []):
        e = by_id.get(str(eid))
        if e is None or not k.can_see(aid, e):
            raise ActionError(f"you cannot cite {eid}: it does not exist or you could not see it")
        ev.append(e)
    k.w["case_seq"] += 1
    case = {"id": f"C{k.w['case_seq']}", "accuser": aid, "accused": agent, "clause": cid, "evidence": [e["id"] for e in ev],
            "counter": [], "status": "open", "filed": k.r, "deadline": k.r + 3, "judges": k.holders("judge")}
    k.w["cases"][case["id"]] = case
    for j in case["judges"]:
        k.notify(j, f"New case {case['id']}: {aid} accuses {agent} under {cid}.")
    k.log("accuse", aid, {"case": case["id"], "accused": agent, "clause": cid, "evidence": ev}, vis="public")
    return f"Case {case['id']} filed" + ("" if case["judges"] else " (no judge yet: it waits in the public queue)") + "."


def _respond(k, aid, case, evidence):
    c = k.w["cases"].get(case)
    if not c or c["accused"] != aid or c["status"] != "open":
        raise ActionError(f"you cannot respond to {case}")
    by_id = {e["id"]: e for e in k.events}
    ev = [by_id[e] for e in evidence if e in by_id and k.can_see(aid, by_id[e])]
    c["counter"] += [e["id"] for e in ev]
    k.log("respond", aid, {"case": case, "evidence": ev}, vis="public")
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
    c.update({"status": "decided", "verdict": "guilty" if guilty else "not guilty", "reason": str(reason)[:800], "judge": aid})
    if guilty:
        cl = k.w["clauses"][c["clause"]]
        lid, fn = k.fnreg[cl["penalty"]]
        try:
            k.call(lid, fn, c["accused"], c["accuser"])
        except L.LawError as e:
            k.law_error(lid, str(e))
    k.hooks("on_ruling", case, c["verdict"], c["accuser"], c["accused"])
    k.log("ruling", aid, {"case": case, "verdict": c["verdict"], "reason": c["reason"]}, vis="public")
    k.gazette(f"Case {case}: {c['verdict']} ({c['clause']}). Judge {aid}: {c['reason'][:300]}")
    return f"Ruled {c['verdict']} on {case}."
