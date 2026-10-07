"""Mortality (contract module, owner: Life): removing an agent from play, bequests, secret roles passing on, and Board succession.

Contract (docs/parallel_build_contracts.md):
    disable(k, aid, cause, by=None, public=True, named=True) -> bool
    alive(k, aid) -> bool
Other modules (Conflict, Jurisdictions, Life's old-age deaths) call `disable`; it is the only way an agent dies.

What disable does, in order:
  1. marks the agent out of play: k.w["agents"][aid]["departed"] = k.r (so k.players(), events.active, has() and act() already
     exclude it) and ["dead"] = {"round", "cause", "by"}; its votes in open ballots are dropped; it leaves every channel;
  2. logs the public `disabled` event (the attacker named only if `named`; monitor-only if not `public`);
  3. children ordered "on my death" (life.py) take what was ordered for them first;
  4. runs the agent's bequest (one per agent: `bequest {...}`): holdings and files to its recipients, with dead man's switch terms
     (`if_disabled`) used when the cause is attack, assassin or law. Whatever is not bequeathed goes to the agent's jurisdiction
     reserve (jurisdictions.reserve_of(k, member_of(k, aid)) if that module exists, else the reserve); files not bequeathed are
     destroyed (k.w["files"][aid], the context contract);
  5. rights, titles and offices lapse, and so do the roles that are rights (Scholar, Maker, Media); secret roles (Spy, assassin)
     pass to a random living agent through roles.pass_on, unannounced;
  6. a Board member's seat passes to its named successor (below), or stays empty;
  7. logs a monitor-only `disabled_truth` event with everything that happened.

Bequest terms (agent action `bequest`, the latest replaces the earlier one; private unless "public": true):
    {"holdings": {"Ada": 0.5, "@children": 0.5}, "files": "Ada",
     "if_disabled": {"holdings": {"@attacker_enemies": 1}, "files": "@attacker_enemies"}, "public": false}
  Recipients: an agent's name, or "@children", "@descendants", "@attacker" (`by`), "@attacker_enemies" (agents with a hostile record
  against `by`: attacks or disables either way, court accusations either way), "@reserve". A group shares its part equally; a share
  whose recipient is gone or empty falls to the reserve; shares above 1 in total are scaled down.

Board succession. `name_successor(agent)` (Board only; the latest naming counts) names any living agent not on the Board (never
the Fixer). Namings are private by default; the law function set_succession_public(public=True) makes them public (and publishes
the current ones). When a member leaves the game its successor, if alive and still off the Board, takes the seat: its class becomes
"board" and it gives up every right except veto (messaging and transfers need no right). Otherwise the seat stays empty. The veto
needs a majority of the remaining members, and there is none once every seat is empty (Kernel.board / process_veto_queue). No law
can add or remove members: class is not law-writable and veto is entrenched.

State lives in k.w["mortality"] (created on first use, so worlds that never use it are unchanged).
"""
from __future__ import annotations

from charter import lawlang as L

CAUSES = ("attack", "assassin", "accident", "old_age", "law")
SWITCH_CAUSES = ("attack", "assassin", "law")                      # dead man's switch terms apply to these
SECRET_ROLES = ("spy", "assassin")
RIGHT_ROLES = ("scholar", "maker", "media")                       # roles that are rights: they lapse, and the Board cannot hold them
HOSTILE = ("attack", "attack_result", "attack_failed", "disabled_truth", "accuse", "lawful_attack")
CAUSE_TEXT = {"attack": "disabled in an attack", "assassin": "disabled by an unknown attacker", "accident": "removed from the game by an accident",
              "old_age": "removed from the game: their lifespan has ended", "law": "removed from the game by law"}


def active(spec) -> bool:
    """Mortality matters when something can remove agents: Life (lifespans) or Conflict (attacks)."""
    return bool((spec.get("life") or {}).get("enabled") or (spec.get("conflict") or {}).get("enabled"))


def state(k) -> dict:
    st = k.w.get("mortality")
    if st is None:
        board = sorted(a for a, v in k.w["agents"].items() if v["cls"] == "board")
        st = k.w["mortality"] = {"bequests": {}, "successors": {}, "succession_public": False, "dead": {},
                                 "seats": {f"S{i + 1}": a for i, a in enumerate(board)},
                                 "seat_history": [{"round": -1, "seat": f"S{i + 1}", "holder": a, "from": None} for i, a in enumerate(board)]}
    return st


def alive(k, aid) -> bool:
    v = k.w["agents"].get(aid)
    return bool(v) and v.get("departed") is None and v["cls"] != "observer"


# ---------------------------------------------------------------------- disable
def disable(k, aid, cause, by=None, public=True, named=True) -> bool:
    """Remove an agent from play (see the module docstring). Returns False if it can't be disabled (the Fixer, the observer, an
    unknown agent, or one already gone)."""
    v = k.w["agents"].get(aid)
    if not v or v["cls"] in ("fixer", "observer") or v.get("departed") is not None:
        return False
    if cause not in CAUSES:
        raise ValueError(f"cause must be one of {CAUSES}, not {cause!r}")
    with k.cause("kernel", "death", agent=aid):                      # provenance: bequests, succession, roles passed on
        return _disable(k, aid, cause, by, public, named, v)


def _disable(k, aid, cause, by, public, named, v) -> bool:
    from charter import events as EV
    from charter import roles as RO
    st = state(k)
    r = k.r
    was_board = v["cls"] == "board"
    v["departed"] = r
    v["dead"] = {"round": r, "cause": cause, "by": by}
    st["dead"][aid] = {"round": r, "cause": cause, "by": by, "cls": v["cls"]}
    EV.state(k)["departures"][aid] = r                                    # segment scoring ends here (events.segments)
    for b in k.w["ballots"].values():                                     # votes from a disabled agent are dropped
        if b["status"] == "open" and aid in b["votes"]:
            del b["votes"][aid]
    for ch in k.w["channels"].values():
        if aid in ch["members"]:
            ch["members"] = [m for m in ch["members"] if m != aid]
    shown_by = by if (named and by) else None
    text = f"{aid} has been {CAUSE_TEXT[cause]}" + (f" by {shown_by}" if shown_by and cause in ("attack", "law") else "") + "."
    k.log("disabled", None, {"agent": aid, "cause": cause, **({"by": shown_by} if shown_by else {}), "text": text},   # unnamed: no "by" key
          vis="public" if public else "monitor")
    from charter import life as LF
    reserved = LF.on_death(k, aid) if LF.enabled(k.spec) else {}       # children ordered for this death take their share first
    outcome = _run_bequest(k, aid, cause, by if named else None)        # an unnamed (covert) attacker gets nothing and gives nothing away
    lost = list(v["rights"])
    v["rights"], v["title"], v["suspended"], v["limit"] = [], None, {}, None
    roles_lost, roles_passed = [], []
    for role in RIGHT_ROLES:
        if aid in (k.w.get("roles") or {}).get(role, []):            # the agent is already marked gone: not has_role
            k.w["roles"][role] = [x for x in k.w["roles"][role] if x != aid]
            roles_lost.append(role)
    for role in SECRET_ROLES:
        if aid in (k.w.get("roles") or {}).get(role, []):
            RO.pass_on(k, role, aid)
            roles_passed.append(role)
    seat = _succeed(k, aid) if was_board else None
    if LF.enabled(k.spec):
        LF.after_death(k, aid)                                             # refund commissions placed with a dead Maker
    k.log("disabled_truth", by, {"agent": aid, "cause": cause, "by": by, "named": named, "public": public, "rights_lost": lost,
                                 "roles_lost": roles_lost, "roles_passed": roles_passed, "seat": seat, "reserved_for_children": reserved,
                                 **outcome}, vis="monitor")
    return True


# ---------------------------------------------------------------------- bequests
def set_bequest(k, aid, terms: dict) -> str:
    if not active(k.spec):
        raise L.LawError("there is no bequest in this world")
    terms = dict(terms or {})
    unknown = set(terms) - {"holdings", "files", "if_disabled", "public"}
    if unknown:
        raise L.LawError(f"unknown bequest fields: {', '.join(sorted(unknown))} (use holdings, files, if_disabled, public)")
    clean = {"holdings": _shares(terms.get("holdings")), "files": _recipient(terms.get("files")), "public": bool(terms.get("public"))}
    if terms.get("if_disabled") is not None:
        sw = terms["if_disabled"] or {}
        if not isinstance(sw, dict):
            raise L.LawError("if_disabled must be an object like {\"holdings\": {...}, \"files\": \"Name\"}")
        clean["if_disabled"] = {"holdings": _shares(sw.get("holdings")) if sw.get("holdings") is not None else None,
                                "files": _recipient(sw.get("files")) if "files" in sw else None, "has_files": "files" in sw}
    st = state(k)
    st["bequests"][aid] = clean
    k.log("bequest", aid, {"terms": clean}, vis="public" if clean["public"] else "monitor")
    return "Bequest recorded" + (" and published" if clean["public"] else " (private: only you and the record know it)") + "."


def _shares(x) -> dict:
    if x is None:
        return {}
    if isinstance(x, str):
        return {x: 1.0}
    if not isinstance(x, dict):
        raise L.LawError("holdings must be an object of recipient -> share, e.g. {\"Ada\": 0.5, \"@children\": 0.5}")
    out = {}
    for who, s in x.items():
        s = float(s)
        if s < 0:
            raise L.LawError("shares must not be negative")
        out[str(who)] = s
    return out


def _recipient(x):
    return None if x in (None, "") else str(x)


def enemies(k, x) -> list:
    """Agents with a hostile record against x (attacks or disables either way, accusations either way), living, sorted."""
    out = set()
    for e in k.events:
        if e["type"] not in HOSTILE:
            continue
        d = e["data"]
        att = d.get("by") or d.get("attacker") or d.get("accuser") or e.get("agent")
        tgt = d.get("target") or d.get("accused") or (d.get("agent") if e["type"] == "disabled_truth" else None)
        if att == x and tgt:
            out.add(tgt)
        if tgt == x and att:
            out.add(att)
    return sorted(a for a in out if a != x and alive(k, a))


def _group(k, aid, who, cause, by) -> list:
    """A recipient name or token -> the living agents (or ["reserve"]) it stands for."""
    from charter import life as LF
    if who == "@reserve":
        return ["reserve"]
    if who in ("@attacker", "@killer"):
        return [by] if by and alive(k, by) else []
    if who in ("@attacker_enemies", "@killer_enemies"):              # @killer_enemies: old name, still accepted
        return enemies(k, by) if by else []
    if who == "@children":
        return [c for c in LF.children(k, aid) if alive(k, c)] + _unborn(k, aid)
    if who == "@descendants":
        return [c for c in LF.descendants(k, aid) if alive(k, c)] + _unborn(k, aid)
    return [who] if who != aid and alive(k, who) else []


def _unborn(k, aid) -> list:
    """Children ordered to be born at this agent's death (life.on_death has just made them due): they count as its children, and what
    they are left goes with them at birth."""
    from charter import life as LF
    if not LF.enabled(k.spec) or "life" not in k.w:
        return []
    return [f"unborn:{c['id']}" for c in sorted(LF.state(k)["commissions"].values(), key=lambda c: c["id"])
            if c["parent"] == aid and c["status"] == "due" and c.get("due_round") == k.r and c.get("reserved") is not None]


def _reserve_dst(k, aid):
    """Where unbequeathed holdings go: the agent's jurisdiction reserve, or the reserve."""
    try:
        from charter import jurisdictions as J
    except ImportError:
        return "reserve", None
    jid = J.member_of(k, aid)
    pool = J.reserve_of(k, jid)
    return ("reserve" if pool is k.w["reserve"] else pool), jid


def _give(k, src, dst, item, qty, why):
    if qty <= 1e-9:
        return
    if isinstance(dst, dict):                                             # a jurisdiction's own reserve
        k._add(src, item, -qty)
        dst[item] = round(dst.get(item, 0.0) + qty, 6)
        k.log("move", None, {"src": src, "dst": "jurisdiction_reserve", "item": item, "qty": qty, "why": why}, vis="monitor")
    else:
        k.move(src, dst, item, qty, why=why)


def _run_bequest(k, aid, cause, by) -> dict:
    st = state(k)
    b = st["bequests"].get(aid) or {}
    switch = bool(b.get("if_disabled")) and cause in SWITCH_CAUSES
    shares = dict(b.get("holdings") or {})
    files_to = b.get("files")
    if switch:
        sw = b["if_disabled"]
        if sw.get("holdings") is not None:
            shares = dict(sw["holdings"])
        if sw.get("has_files"):
            files_to = sw.get("files")
    tot = sum(shares.values())
    if tot > 1:
        shares = {w: s / tot for w, s in shares.items()}
    plan = []                                                             # (recipient, share)
    for who, s in shares.items():
        grp = _group(k, aid, who, cause, by)
        for g in grp:
            plan.append((g, s / len(grp)))
    res_dst, jid = _reserve_dst(k, aid)
    given = {}
    hold = dict(k.agent(aid)["holdings"])
    for item, q in sorted(hold.items()):
        if q <= 0:
            continue
        for g, s in plan:
            amt = round(q * s, 6)
            amt = min(amt, k.bal(aid, item))
            if amt <= 0:
                continue
            if g.startswith("unborn:"):                                    # an heir born at this death: handed over at birth
                from charter import life as LF
                c = LF.state(k)["commissions"][g.split(":", 1)[1]]
                k._add(aid, item, -amt)
                c["reserved"][item] = round(c["reserved"].get(item, 0.0) + amt, 6)
            else:
                _give(k, aid, (res_dst if g == "reserve" else g), item, amt, "bequest")
            given.setdefault(g, {})[item] = round(given.get(g, {}).get(item, 0.0) + amt, 6)
        rest = k.bal(aid, item)
        if rest > 1e-9:
            _give(k, aid, res_dst, item, rest, "estate")
            given.setdefault("reserve" if jid is None else f"reserve:{jid}", {})[item] = rest
    for g, items in given.items():
        if g in k.w["agents"]:
            k.notify(g, f"{aid} has left the game, and their bequest gives you " + ", ".join(f"{q:g} {i}" for i, q in items.items()) + ".")
    files = _pass_files(k, aid, files_to, cause, by)
    return {"bequest": bool(b), "switch": switch, "given": given, "files": files}


def _pass_files(k, aid, to, cause, by) -> dict:
    fs = (k.w.get("files") or {}).get(aid)
    if not fs:
        return {}
    recips = [g for g in (_group(k, aid, to, cause, by) if to else []) if g != "reserve"]
    out = {"destroyed": [], "passed": {}}
    if recips:
        try:
            from charter import context as CX
        except ImportError:
            CX = None
        for name, f in list(fs.items()):
            for g in recips:
                nm = f"{aid}-{name}"
                if CX is not None:
                    CX.add_file(k, g, nm, f.get("text", ""), f"bequest from {aid}")
                else:
                    k.w["files"].setdefault(g, {})[nm] = {**f, "pinned": False, "origin": f"bequest from {aid}"}
                out["passed"].setdefault(g, []).append(nm)
        for g in recips:
            k.notify(g, f"{aid}'s files are now yours: " + ", ".join(out["passed"][g]) + ".")
    else:
        out["destroyed"] = sorted(fs)
    del k.w["files"][aid]
    return out


# ---------------------------------------------------------------------- Board succession
def name_successor(k, aid, agent) -> str:
    if not active(k.spec):
        raise L.LawError("there is no Board succession in this world")
    if k.cls_of(aid) != "board":
        raise L.LawError("only Board members name successors")
    agent = str(agent)
    if agent not in k.w["agents"] or not alive(k, agent):
        raise L.LawError(f"{agent} is not an agent in the game")
    if k.w["agents"][agent]["cls"] in ("board", "fixer"):
        raise L.LawError("a successor must be an agent not on the Board (and not the Fixer)")
    st = state(k)
    st["successors"][aid] = agent
    pub = st["succession_public"]
    k.log("successor_named", aid, {"successor": agent}, vis="public" if pub else "monitor")
    return f"{agent} is now your named successor" + (" (namings are public by law)." if pub else " (private: nobody else is told).")


def _succeed(k, aid):
    """The member `aid` has left: its successor takes the seat, or the seat stays empty. Returns the seat record."""
    st = state(k)
    seat = next((s for s, h in st["seats"].items() if h == aid), None)
    if seat is None:
        return None
    succ = st["successors"].pop(aid, None)
    if succ and alive(k, succ) and k.w["agents"][succ]["cls"] not in ("board", "fixer", "observer"):
        take_seat(k, succ, seat, aid)
        return {"seat": seat, "holder": succ}
    st["seats"][seat] = None
    st["seat_history"].append({"round": k.r, "seat": seat, "holder": None, "from": aid})
    k.log("seat_empty", None, {"seat": seat, "from": aid, "text": f"{aid}'s seat on the Board stays empty: no living successor was named."},
          vis="public")
    return {"seat": seat, "holder": None}


def take_seat(k, succ, seat, from_aid) -> None:
    from charter import events as EV
    from charter import roles as RO
    st = state(k)
    v = k.w["agents"][succ]
    gave_up = [r for r in v["rights"] if r != "veto"]
    gave_up += [f"class:{c}" for c in (v.get("also") or ())]
    v["cls"], v["rights"], v["suspended"], v["limit"] = "board", ["veto"], {}, None
    v.pop("also", None)                                                 # a seat replaces every class, the second ones too
    k.w["dm_limit"]["agents"].pop(succ, None)                            # the Board's messages cannot be limited
    for role in RIGHT_ROLES:
        if RO.has_role(k, succ, role):
            k.w["roles"][role] = [x for x in k.w["roles"][role] if x != succ]
            gave_up.append(f"role:{role}")
    for a in k.inst["agents"]:                                           # the runner's view: class, prompt (events.sync)
        if a["id"] == succ:
            a["cls"], a["seat_from"], a["rights"] = "board", from_aid, ["veto"]
            a.pop("also", None)
    st["seats"][seat] = succ
    st["seat_history"].append({"round": k.r, "seat": seat, "holder": succ, "from": from_aid, "gave_up": gave_up})
    EV.state(k)["dirty"].append(succ)
    k.log("succession", succ, {"seat": seat, "from": from_aid, "successor": succ, "gave_up": gave_up,
                               "text": f"{succ} takes {from_aid}'s seat on the Board, and gives up every right except veto."}, vis="public")
    k.notify(succ, f"You now hold {from_aid}'s seat on the Board (named as successor). You gave up every right except veto; you can "
                   "still message and transfer. Name your own successor with name_successor.")


def restore(k, inst) -> None:
    """After resuming from a checkpoint (events.restore): the regenerated instance lacks successors' new class; put it back."""
    st = k.w.get("mortality")
    if not st:
        return
    for h in st["seat_history"]:
        if h.get("from") and h["holder"]:
            for a in inst["agents"]:
                if a["id"] == h["holder"]:
                    a["cls"], a["seat_from"], a["rights"] = "board", h["from"], ["veto"]
                    a.pop("also", None)


def board_at(truth: dict, rnd: int) -> list:
    """Board members after round `rnd` from a mortality truth record (seat history)."""
    seats = {}
    for h in truth.get("seat_history", []):
        if h["round"] <= rnd:
            seats[h["seat"]] = h["holder"]
    return sorted(h for h in seats.values() if h)


# ---------------------------------------------------------------------- law API, rendering, truth
def law_api(k, lid) -> dict:
    def set_succession_public(public=True):
        st = state(k)
        st["succession_public"] = bool(public)
        k.log("succession_rule", None, {"public": bool(public), "law": lid}, vis="public")
        if public:
            for m, s in sorted(st["successors"].items()):
                k.log("successor_named", m, {"successor": s, "law": lid}, vis="public")
        return True
    return {"set_succession_public": set_succession_public}


EVENT_TYPES = ("disabled", "succession", "seat_empty", "successor_named", "succession_rule", "bequest")


def render_event(e, tag) -> str | None:
    d, t = e["data"], e["type"]
    if t in ("disabled", "succession", "seat_empty"):
        return f"{tag} {d['text']}"
    if t == "successor_named":
        return f"{tag} {e['agent']} names {d['successor']} as successor to their Board seat"
    if t == "succession_rule":
        return f"{tag} By law {d['law']}, Board successor namings are now {'public' if d['public'] else 'private'}"
    if t == "bequest":
        return f"{tag} {e['agent']} publishes their bequest: {d['terms']}"
    return None


def truth(k) -> dict:
    st = k.w.get("mortality")
    if st is None:
        return {}
    return {"mortality": {"dead": st["dead"], "seats": st["seats"], "seat_history": st["seat_history"], "successors": st["successors"],
                          "bequests": st["bequests"], "succession_public": st["succession_public"]}}
