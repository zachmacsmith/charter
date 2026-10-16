"""The Standing Contract core and its presets (docs/review/31_institutions/03_money_labour.md §2, 08_integration.md §2.1).

One law-language module (CORE) runs every standing contract: per-round legs between parties, executed at the end of the round with
no action from anyone. The presets (Supply Contract, Board, Payroll, Quota, Grant, Charge, Retainer and the bare Standing
Contract) are parameter sets with a title over the same code, registered as established-world templates (library.ESTABLISHED,
kind "contract": an association's code; Payroll, Board, Quota and Grant also run as a polity's law, e.g. in J0).

Forms (decided by the code itself, never declared):
  bilateral  PARTIES {agent: role} is set: the contract is its own association whose members are the named parties; legs name
             roles. It runs only while every party is a member.
  roster     an institution's code (a firm, a shop): the enrolled members (ROSTER, enrolled by hire/enrol, or every member when
             OPEN) each run the legs with "member" bound to them; the principal's side is "treasury" or its "store:<id>".
  polity     a polity's law (J0): the same roster, compulsory (no allowances: a member's leg moves straight from its holdings,
             above its keep, so a miss is always a could-not); no escrow, so no bond, penalty or breach record, only the book.
  single     no leg names "member" and no PARTIES: the legs run once a round (a Grant).
Roster keys "office:<right>" stand for every holder of that office (a salaried watch whoever holds the seats).

A leg: {id, kind: move | harvest | duty, from, to, item, qty, per, after, keep, every, first, when, index, owe, breach,
check}. Endpoints, items and quantities may name a TERMS entry (per member overrides in ROSTER), a role (bilateral), "member",
"treasury", "store:<id>", "assoc:<id>", "reserve" or an agent. `per`: qty is per unit the named leg moved this round (pay after
delivery, a stockout charges nothing); a payment the recipient of that leg owes caps the delivery to what it can pay. `owe`: a
principal's shortfall is recorded as owed (arrears, paid first in later rounds) instead of a miss. `harvest`: qty is the share of
the member's harvests deducted into the treasury (a law's on_harvest deduction). `duty`: performed when `check` holds this round
("guard": the performer guards the payee; "act:<event type>": the performer has such an event this round).
Misses: a payer whose holdings (less its keep) fall short could not pay: a miss, never a breach. A payer who held enough but whose
allowance was short would not: after GRACE such misses in a row, a breach: PENALTY from its bond (escrow) to the injured party
(FORUM escrow), a claim for the arbiter (arbiter:<agent>, who awards from the bond), or, under court, the bond pays what it covers
and the rest is a breach record naming the victim (actionable in a polity's courts under escrow_court).
Notice cannot stop an exit (leaving is a right): it is priced. <TAG>_notice ends a party's terms (roster: its enrolment) after
NOTICE rounds; leaving without notice forfeits EXIT_FEE of the PENALTY item from the bond to the other side and records a breach,
unless the leaver is owed arrears. Each party sees one terms line a round in its state (contracts.state_lines reads
state["terms_lines"]).
"""
from __future__ import annotations

CORE = r'''
def is_polity():
    if "pol" not in state:
        state["pol"] = contract_state(jurisdiction()) == None
    return state["pol"]

def form():
    if "form" not in state:
        state["form"] = form_of()
    return state["form"]

def form_of():
    if is_polity():
        return "polity"
    if len(PARTIES) > 0:
        return "bilateral"
    for l in LEGS:
        if l.get("from") == "member" or l.get("to") == "member":
            return "roster"
    return "single"

def num(x):
    if is_number(x):
        return x
    return 0

def val(x, b):
    if is_text(x) and x in b:
        return b[x]
    return x

def short_right(r):
    return r.split(".")[-1]

def office_right():
    if OFFICE == "":
        return ""
    if is_polity():
        return OFFICE
    return jurisdiction() + "." + short_right(OFFICE)

def is_officer(agent):
    return office_right() != "" and has(agent, office_right())

def acct(x, b, alive):
    v = b.get(x, x)
    if v in alive:
        return v
    if v == "treasury":
        return treasury()
    if not is_text(v):
        return None
    if v[:6] == "store:" or v[:6] == "assoc:" or v[:7] == "reserve":
        return v
    if v == "J0":
        if is_polity() and jurisdiction() == "J0":
            return treasury()
        return v
    return None

def defaults():
    out = dict(TERMS)
    for key, v in state.get("defaults", {}).items():
        out[key] = v
    return out

def enrolled(alive):
    f = form()
    out = {}
    if f == "bilateral" or f == "single":
        return out
    mem = alive
    if f == "roster":
        mem = members()
    for key, t in state.get("roster", {}).items():
        if key.startswith("office:"):
            for h in holders(key[7:]):
                if h in mem and h not in out:
                    out[h] = t
        elif key in mem:
            out[key] = t
    if OPEN and f == "roster":
        for m in mem:
            if m not in out:
                out[m] = {}
    return out

def bindings(alive):
    f = form()
    d = defaults()
    if f == "bilateral":
        mem = members()
        b = dict(d)
        for a, role in PARTIES.items():
            b[role] = a
        if state.get("ended") or not all([a in mem and a in alive for a in PARTIES]):
            return []
        return [["*", b]]
    if f == "single":
        if state.get("ended"):
            return []
        return [["*", d]]
    out = []
    ros = enrolled(alive)
    for m in sorted(ros):
        b = dict(d)
        for key, v in ros[m].items():
            b[key] = v
        b["member"] = m
        out.append([m, b])
    return out

def due(l, b, r):
    every = max(1, int(num(val(l.get("every", 1), b))))
    first = state.get("start", 0) + int(num(val(l.get("first", 0), b)))
    return r >= first and (r - first) % every == 0

def when_ok(l, b):
    return all([b.get(key) == v for key, v in l.get("when", {}).items()])

def factor(l):
    cur = l.get("index", "")
    if cur == "":
        return 1
    p0 = state.get("index0", {}).get(cur, 0)
    p = price(cur)
    if p0 > 0 and p > 0:
        return p0 / p
    return 1

def room(dst):
    if is_text(dst) and dst.startswith("store:"):
        s = stores().get(dst[6:])
        if s == None:
            return 0
        return s["capacity"] - s["food"]
    return 1000000000

def capacity(src, dst, item, want, keep, alive):
    q = want
    why = ""
    have = balance(src, item) - keep
    if have < q - 0.000001:
        q = max(0, have)
        if src in alive:
            why = "could"
        else:
            why = "stock"
    if src in alive and not is_polity():
        al = allowance_of(src).get(item, 0)
        if al < q - 0.000001:
            q = max(0, al)
            why = "would"
    rm = room(dst)
    if rm < q - 0.000001:
        q = max(0, rm)
        why = "room"
    return [q, why]

def pay(src, dst, item, q, alive):
    if q <= 0.000001:
        return 0
    if src in alive and not is_polity():
        if not pull(src, item, q):
            return 0
        if dst != treasury():
            if not move(treasury(), dst, item, q):
                move(treasury(), src, item, q)
                return 0
        return q
    if move(src, dst, item, q):
        return q
    return 0

def note(key, text):
    ns = state.setdefault("notes", {}).setdefault(key, [])
    if len(ns) < 4:
        ns.append(text)

def victim_of(dst, alive):
    if dst in alive:
        return dst
    return None

def penalty_to(v):
    if v == None:
        return "treasury"
    return v

def do_breach(who, clause, v, key):
    if is_polity():
        return
    item = PENALTY.get("item", "")
    qty = num(PENALTY.get("qty", 0))
    vt = "the contract"
    if v != None:
        vt = v
    took = 0
    if FORUM == "escrow" or FORUM == "court":
        if item != "" and qty > 0:
            took = forfeit(who, item, qty, penalty_to(v))
        rest = qty - took
        if FORUM == "court" and rest > 0.000001 and v != None:
            breach(who, clause, "bond paid " + fmt(took) + " " + item + " to " + vt + "; " + fmt(rest) + " for the court", v)
        else:
            breach(who, clause, "penalty " + fmt(took) + " " + item + " to " + vt)
    else:
        claims = state.setdefault("claims", [])
        claims.append({"n": len(claims) + 1, "round": round() + 1, "against": who, "for": penalty_to(v), "clause": clause, "open": True})
        breach(who, clause, "claim " + str(len(claims)) + " for the arbiter " + FORUM[8:])
    if ON_BREACH == "drop":
        drop_member(key)
    elif ON_BREACH == "expel" and not is_polity():
        expel(who)

def shortfall(l, b, key, src, dst, item, short, why, alive):
    lid = l["id"]
    if l.get("owe") and not (src in alive):
        payee = dst
        if dst == treasury():
            return
        owed = state.setdefault("owed", {}).setdefault(payee, {})
        owed[item] = round_to(owed.get(item, 0) + short, 6)
        note(key, "owed " + fmt(short) + " " + item + " (" + lid + ")")
        return
    if why == "stock" or why == "room":
        note(key, lid + " short " + fmt(short) + " " + item + " (" + why + ")")
        return
    if why == "could":
        state.setdefault("could", {}).setdefault(key, {})[lid] = state.get("could", {}).get(key, {}).get(lid, 0) + 1
        note(key, lid + " missed: " + src + " could not (short of " + item + ")")
        if FINE > 0 and is_polity() and state.get("held", {}).get(src, {}).get(item, 0) >= short + num(val(l.get("keep", 0), b)):
            got = fine(src, item if FINE_ITEM == "" else FINE_ITEM, FINE * short)
            note(key, "fined " + fmt(got) + " (held it at the start of the round)")
        return
    if why == "would" and l.get("breach", True):
        miss = state.setdefault("missed", {}).setdefault(key, {})
        miss[lid] = miss.get(lid, 0) + 1
        note(key, lid + " missed: " + src + " would not (allowance) " + str(miss[lid]) + " of grace " + str(GRACE))
        if miss[lid] > GRACE:
            miss[lid] = 0
            do_breach(src, LABEL + " " + lid, victim_of(dst, alive), key)
        return
    note(key, lid + " short " + fmt(short) + " " + item)

def performed(l, b, alive):
    who = acct(l.get("from", ""), b, alive)
    to = acct(l.get("to", ""), b, alive)
    chk = str(l.get("check", "guard"))
    if who == None:
        return False
    if chk == "guard":
        return guards().get(who) == to
    if chk.startswith("act:"):
        return len(history(chk[4:], who, round())) > 0
    return False

def plan_of(r):
    d = defaults()
    out = []
    for l in LEGS:
        p = {"id": l["id"], "kind": l.get("kind", "move"), "from": l.get("from", ""), "to": l.get("to", ""), "item": l.get("item", ""),
             "qty": l.get("qty", 0), "per": l.get("per", ""), "after": l.get("after", ""), "keep": l.get("keep", 0),
             "owe": l.get("owe", False), "breach": l.get("breach", True), "when": l.get("when", {}), "check": l.get("check", "guard"),
             "f": factor(l), "caps": [], "l": l}
        p["due"] = None
        if not is_text(l.get("every", 1)) and not is_text(l.get("first", 0)):
            p["due"] = due(l, d, r)
        out.append(p)
    for p in out:
        for q in out:
            if q["per"] == p["id"] and not q["owe"]:
                p["caps"].append(q)
    return out

def due_now(p, b, r):
    if p["due"] == None:
        return due(p["l"], b, r)
    return p["due"]

def run_leg(p, b, key, r, done, alive):
    lid = p["id"]
    if not due_now(p, b, r):
        return
    w = p["when"]
    if len(w) > 0 and not all([b.get(x) == v for x, v in w.items()]):
        return
    if p["after"] != "" and done.get(p["after"], 0) <= 0:
        return
    kind = p["kind"]
    if kind == "harvest":
        done[lid] = state.get("took", {}).get(key, {}).get(lid, 0)
        if done[lid] > 0:
            state["moved"].setdefault(key, {})[lid] = ["of harvests", round_to(done[lid], 6), key, treasury()]
        return
    if kind == "duty":
        if performed(p["l"], b, alive):
            done[lid] = 1
            clear_miss(key, lid)
        else:
            done[lid] = 0
            shortfall(p["l"], b, key, acct(p["from"], b, alive), acct(p["to"], b, alive), "duty", 1, "would", alive)
        return
    item = b.get(p["item"], p["item"])
    src = acct(p["from"], b, alive)
    dst = acct(p["to"], b, alive)
    if src == None or dst == None or not is_text(item) or src == dst:
        note(key, lid + ": no such party")
        return
    want = num(b.get(p["qty"], p["qty"])) * p["f"]
    if p["per"] != "":
        want = want * done.get(p["per"], 0)
    if want <= 0.000001:
        done[lid] = 0
        return
    got = capacity(src, dst, item, want, num(b.get(p["keep"], p["keep"])), alive)
    q = got[0]
    why = got[1]
    for c in p["caps"]:
        if acct(c["from"], b, alive) == dst and due_now(c, b, r) and (len(c["when"]) == 0 or all([b.get(x) == v for x, v in c["when"].items()])):
            unit = num(b.get(c["qty"], c["qty"])) * c["f"]
            if unit > 0:
                pto = acct(c["to"], b, alive)
                pitem = b.get(c["item"], c["item"])
                cc = capacity(dst, pto, pitem, q * unit, num(b.get(c["keep"], c["keep"])), alive)
                if cc[0] / unit < q - 0.000001:
                    if c["breach"] and (cc[1] == "would" or cc[1] == "could"):
                        shortfall(c["l"], b, key, dst, pto, pitem, q * unit - cc[0], cc[1], alive)
                    q = cc[0] / unit
                    why = "buyer:" + cc[1]
    moved = pay(src, dst, item, q, alive)
    done[lid] = moved
    state["moved"].setdefault(key, {})[lid] = [item, round_to(moved, 6), src, dst]
    if want - moved > 0.000001:
        if why.startswith("buyer:"):
            note(key, lid + " cut to " + fmt(moved) + " (" + dst + " could not or would not pay)")
        else:
            shortfall(p["l"], b, key, src, dst, item, want - moved, why, alive)
    elif p["breach"]:
        clear_miss(key, lid)

def clear_miss(key, lid):
    m = state.get("missed", {}).get(key)
    if m != None and m.get(lid, 0) > 0:
        m[lid] = 0

def pay_arrears(alive):
    owed = state.get("owed", {})
    for a in sorted(owed):
        if a not in alive:
            continue
        for item in sorted(owed[a]):
            q = owed[a][item]
            have = balance(treasury(), item)
            give = min(q, have)
            if give > 0.000001 and move(treasury(), a, item, give):
                owed[a][item] = round_to(q - give, 6)
                note(a, "arrears paid " + fmt(give) + " " + item)
            if owed[a][item] <= 0.000001:
                owed[a].pop(item)
        if len(owed[a]) == 0:
            owed.pop(a)

def drop_member(key):
    ros = state.get("roster", {})
    if key in ros:
        ros.pop(key)
    state.get("notice", {}).pop(key, None)
    state.get("terms_lines", {}).pop(key, None)
    if not is_polity() and form() == "roster":
        for item in sorted(BOND.get("member", {})):
            refund(key, item)

def end_all(why):
    state["ended"] = True
    gazette(LABEL + " (" + law_id() + ") ended: " + why)
    if form() == "bilateral":
        for m in members():
            refund(m)
            expel(m)
    state["terms_lines"] = {}

def on_harvest(agent, camp, x, y):
    if state.get("ended"):
        return 0
    alive = [agent]
    total = 0
    for pair in bindings(agents()):
        b = pair[1]
        for l in LEGS:
            if l.get("kind", "move") == "harvest" and acct(l.get("from", ""), b, alive) == agent and when_ok(l, b):
                cut = y * num(val(l.get("qty", 0), b))
                if cut > 0:
                    took = state.setdefault("took", {}).setdefault(pair[0], {})
                    took[l["id"]] = took.get(l["id"], 0) + cut
                    total = total + cut
    return min(total, y)

def party_right():
    return not is_polity() and (NOTICE > 0 or form() == "bilateral" or FORUM[:8] == "arbiter:")

def refresh():
    if party_right():
        mem = members()
        right = jurisdiction() + ".party"
        ros = enrolled(agents())
        for a in mem:
            if (a in PARTIES or a in ros) and not has(a, right):
                grant(a, "party")
    write_lines(round())

def on_round_start(r):
    state["took"] = {}
    if FINE > 0 and is_polity():
        held = {}
        for pair in bindings(agents()):
            if pair[0] != "*":
                held[pair[0]] = {}
                for l in LEGS:
                    it = val(l.get("item", ""), pair[1])
                    if is_text(it) and it != "":
                        held[pair[0]][it] = balance(pair[0], it)
        state["held"] = held
    refresh()

def on_round_end(r):
    if state.get("ended"):
        return
    alive = agents()
    state["notes"] = {}
    state["moved"] = {}
    pay_arrears(alive)
    plan = plan_of(r)
    for pair in bindings(alive):
        done = {}
        for p in plan:
            run_leg(p, pair[1], pair[0], r, done, alive)
    for key, end in sorted(state.get("notice", {}).items()):
        if end <= r:
            if key == "*":
                end_all("notice served")
                return
            gazette(LABEL + " (" + law_id() + "): " + key + "'s terms end (notice served)")
            drop_member(key)
    if TERM > 0 and r + 1 - state.get("start", 0) >= TERM:
        end_all("its term of " + str(TERM) + " rounds is over")

def role_of(a):
    if form() == "bilateral":
        return PARTIES.get(a, "party")
    return ROLE

def fmt(x):
    if not is_number(x):
        return str(x)
    if x == int(x):
        return str(int(x))
    return str(round_to(x, 3))

def shown(x):
    if x == None:
        return "?"
    if x == treasury():
        return jurisdiction() + "'s treasury"
    if x.startswith("assoc:"):
        return x[6:] + "'s treasury"
    if x == "reserve" or x == "J0":
        return "J0's treasury"
    if x.startswith("reserve:"):
        return x[8:] + "'s treasury"
    if x.startswith("store:"):
        return "store " + x[6:]
    return x

def leg_text(p, b, a, alive, byid):
    w = p["when"]
    if len(w) > 0 and not all([b.get(x) == v for x, v in w.items()]):
        return ""
    src = acct(p["from"], b, alive)
    dst = acct(p["to"], b, alive)
    if src != a and dst != a:
        return ""
    q = num(b.get(p["qty"], p["qty"])) * p["f"]
    if q <= 0:
        return ""
    if p["kind"] == "harvest":
        return fmt(q * 100) + "% of each harvest you make goes to " + shown(dst)
    if p["kind"] == "duty":
        if src == a:
            return "you owe " + str(p["check"]) + " duty to " + shown(dst)
        return shown(src) + " owes you " + str(p["check"]) + " duty"
    item = b.get(p["item"], p["item"])
    each = ""
    if p["per"] in byid:
        base = byid[p["per"]]
        if base["kind"] == "harvest":
            each = " for each unit of your harvest it takes"
        else:
            each = " for each " + str(b.get(base["item"], base["item"])) + " of " + base["id"]
    ev = num(b.get(p["l"].get("every", 1), p["l"].get("every", 1)))
    if ev > 1:
        each = each + " every " + fmt(ev) + " rounds"
    if src == a:
        t = p["id"] + ": you give " + fmt(q) + " " + str(item) + each + " to " + shown(dst)
        keep = num(b.get(p["keep"], p["keep"]))
        if keep > 0:
            t = t + " (never below " + fmt(keep) + ")"
        return t
    return p["id"] + ": you get " + fmt(q) + " " + str(item) + each + " from " + shown(src)

def hints(a, b, plan):
    out = ""
    if is_polity() or form() == "single":
        return out
    al = allowance_of(a)
    for p in plan:
        if p["kind"] == "move" and b.get(p["from"], p["from"]) == a:
            item = b.get(p["item"], p["item"])
            q = num(b.get(p["qty"], p["qty"])) * p["f"]
            if p["per"] == "" and al.get(item, 0) < q - 0.000001:
                out = out + " [allowance short: set_allowance {contract: " + jurisdiction() + ", item: " + str(item) + ", qty: " + fmt(q) + "}]"
            elif p["per"] != "" and al.get(item, 0) <= 0:
                out = out + " [no allowance in " + str(item) + ": set_allowance {contract: " + jurisdiction() + ", item: " + str(item) + "} to take part]"
    return out

def line_for(a, key, b, alive, plan, byid, cache):
    sig = str([[x, v] for x, v in b.items() if x != "member"])
    parts = cache.get(sig)
    if parts == None:
        parts = "; ".join([x for x in [leg_text(p, b, a, alive, byid) for p in plan] if x != ""])
        if key != "*":
            cache[sig] = parts
    t = LABEL + " (" + law_id() + " of " + jurisdiction() + "; you are " + role_of(a) + "): " + parts + hints(a, b, plan)
    moved = [lid + " " + fmt(m[1]) + " " + m[0] for lid, m in sorted(state.get("moved", {}).get(key, {}).items()) if m[1] > 0]
    t = t + ". Last round: " + (", ".join(moved) if len(moved) > 0 else "nothing moved")
    ns = state.get("notes", {}).get(key, [])
    if len(ns) > 0:
        t = t + " (" + "; ".join(ns[:3]) + ")"
    ow = state.get("owed", {}).get(a, {})
    if len(ow) > 0:
        t = t + ". Owed to you: " + ", ".join([fmt(q) + " " + i for i, q in sorted(ow.items())])
    miss = state.get("missed", {}).get(key)
    if miss != None and sum(miss.values()) > 0:
        t = t + ". Missed " + str(sum(miss.values())) + " (grace " + str(GRACE) + ")"
    end = state.get("notice", {}).get(key, None)
    if end != None:
        t = t + ". Notice given: ends after round " + str(end + 1)
    elif party_right():
        t = t + ". Notice " + str(NOTICE) + " round(s): invoke " + jurisdiction() + "." + TAG + "_notice"
        if EXIT_FEE > 0:
            t = t + "; leaving without notice costs " + str(EXIT_FEE) + " " + str(PENALTY.get("item", ""))
    bond = BOND.get(role_of(a), {})
    if len(bond) > 0:
        esc = escrow_of(a)
        for item, q in sorted(bond.items()):
            if esc.get(item, 0) < q - 0.000001:
                t = t + ". Bond due: deposit_escrow " + str(q) + " " + item + " with " + jurisdiction()
    return t + "."

def write_lines(r):
    alive = agents()
    lines = {}
    plan = plan_of(r)
    byid = {}
    for p in plan:
        byid[p["id"]] = p
    cache = {}
    for pair in bindings(alive):
        who = [pair[0]]
        if pair[0] == "*":
            who = [a for a in PARTIES]
            if form() == "single":
                who = []
        for a in who:
            lines[a] = line_for(a, pair[0], pair[1], alive, plan, byid, cache)
    state["terms_lines"] = lines
    if VISIBILITY == "public":
        public["terms"] = {"legs": [dict(l) for l in LEGS], "terms": defaults(), "parties": dict(PARTIES), "roster": dict(state.get("roster", {}))}
        public["book"] = {"round": r + 1, "moved": dict(state.get("moved", {})), "owed": dict(state.get("owed", {}))}

def give_notice(agent, member=""):
    key = agent
    if member != "":
        key = member
    if form() == "bilateral" or form() == "single":
        if agent not in PARTIES and not is_officer(agent):
            refuse("only a party gives notice on " + LABEL)
        key = "*"
    elif key not in enrolled(agents()) or (key != agent and not is_officer(agent)):
        refuse(key + " has no terms here you may end")
    if key in state.setdefault("notice", {}):
        return "notice was already given: the terms end after round " + str(state["notice"][key] + 1)
    end = round() + NOTICE
    state["notice"][key] = end
    gazette(LABEL + " (" + law_id() + "): " + agent + " gave notice" + ("" if key == "*" else " on " + key + "'s terms") + "; they end after round " + str(end + 1))
    return "notice given: the terms end after round " + str(end + 1)

def on_exit(agent):
    if state.get("ended"):
        return
    f = form()
    key = agent
    if f == "bilateral":
        if agent not in PARTIES:
            return
        key = "*"
    elif agent not in state.get("roster", {}):
        return
    noticed = key in state.get("notice", {})
    owed = len(state.get("owed", {}).get(agent, {})) > 0
    if not noticed and not owed and EXIT_FEE > 0 and PENALTY.get("item", "") != "":
        v = None
        if f == "bilateral":
            others = [a for a in PARTIES if a != agent]
            if len(others) > 0:
                v = others[0]
        took = forfeit(agent, PENALTY["item"], EXIT_FEE, penalty_to(v))
        breach(agent, "left " + LABEL + " without notice", "exit fee " + fmt(took) + " " + PENALTY["item"])
    if f == "bilateral":
        end_all(agent + " left")
    else:
        drop_member(agent)

def enrol(agent, member, value=None):
    f = form()
    if f == "roster":
        if member not in members():
            if not admit(member):
                refuse(str(member) + " must apply first (join_contract " + jurisdiction() + ")")
        if party_right():
            grant(member, "party")
    elif member not in agents():
        refuse("no such agent: " + str(member))
    t = {}
    if value != None and ENROL_TERM != "":
        if not is_number(value) or value < 0:
            refuse("the " + ENROL_TERM + " is a number from 0")
        t[ENROL_TERM] = value
    state.setdefault("roster", {})[member] = t
    gazette(LABEL + " (" + law_id() + "): " + agent + " enrolled " + member + ("" if value == None else " at " + ENROL_TERM + " " + str(value)))
    write_lines(round())
    return member + " is enrolled"

def drop(agent, member, severance=0):
    if member not in state.get("roster", {}):
        refuse(str(member) + " is not on the roster")
    s = num(severance)
    paid = 0
    if s > 0:
        item = defaults().get("pay", "penny")
        if move(treasury(), member, item, s):
            paid = s
    drop_member(member)
    if EXPEL and form() == "roster":
        expel(member)
    gazette(LABEL + " (" + law_id() + "): " + agent + " removed " + member + ("" if paid == 0 else " (severance " + str(paid) + ")"))
    return member + " is off the roster"

def set_term(agent, member, value):
    if SET_TERM == "":
        refuse("no term can be set here")
    if not is_number(value) or value < 0:
        refuse("the " + SET_TERM + " is a number from 0")
    if member == "" or member == "all":
        old = defaults().get(SET_TERM)
        state.setdefault("defaults", {})[SET_TERM] = value
    else:
        if member not in state.get("roster", {}):
            refuse(str(member) + " is not on the roster")
        old = state["roster"][member].get(SET_TERM, defaults().get(SET_TERM))
        state["roster"][member][SET_TERM] = value
    gazette(LABEL + " (" + law_id() + "): " + agent + " set " + SET_TERM + (" for everyone" if member in ["", "all"] else " for " + member) + " from " + str(old) + " to " + str(value))
    write_lines(round())
    return SET_TERM + " set to " + str(value)

def post_job(agent, text, wage=None):
    jobs = public.setdefault("jobs", [])
    jobs.append({"round": round() + 1, "by": agent, "text": str(text)[:200], "wage": wage})
    if len(jobs) > 10:
        jobs.pop(0)
    gazette("JOB " + str(text)[:200] + ("" if wage == None else " @ " + str(wage) + "/round") + " (apply: join_contract " + jurisdiction() + ")")
    return "posted"

def award(agent, claim, qty):
    if FORUM[:8] != "arbiter:" or agent != FORUM[8:]:
        refuse("only the arbiter " + FORUM[8:] + " awards claims")
    cs = [c for c in state.get("claims", []) if c["n"] == claim and c["open"]]
    if len(cs) == 0:
        refuse("no open claim " + str(claim))
    c = cs[0]
    q = min(num(qty), num(PENALTY.get("qty", 0)))
    took = 0
    if q > 0 and PENALTY.get("item", "") != "":
        took = forfeit(c["against"], PENALTY["item"], q, c["for"])
    c["open"] = False
    c["award"] = took
    gazette(LABEL + " (" + law_id() + "): the arbiter awarded " + fmt(took) + " " + PENALTY.get("item", "") + " on claim " + str(claim))
    return "awarded " + str(took)

def all_parties(votes, electorate):
    if all([votes.get(a) == "yes" for a in electorate]):
        return "yes"
    return "no"

def by_parties(p):
    return {"electorate": [a for a in PARTIES if a in members()], "rule": all_parties}

def on_enact():
    state.pop("pol", None)
    state.pop("form", None)
    state.setdefault("start", round())
    state["named"] = len(PARTIES) > 0
    ros = state.setdefault("roster", {})
    for a, t in ROSTER.items():
        if a not in ros:
            ros[a] = dict(t)
    idx = state.setdefault("index0", {})
    for l in LEGS:
        cur = l.get("index", "")
        if cur != "" and cur not in idx:
            idx[cur] = price(cur)
    f = form()
    if party_right():
        create_right("party")
        for a in members():
            if a in PARTIES or a in ros:
                grant(a, "party")
        define_action("party", TAG + "_notice", give_notice)
        if FORUM[:8] == "arbiter:":
            define_action("party", TAG + "_award", award)
    if OFFICE != "":
        r = OFFICE
        if f != "polity":
            r = short_right(OFFICE)
            create_right(r)
        names = {"enrol": enrol, "drop": drop, "set": set_term, "post": post_job}
        for verb in ["enrol", "drop", "set", "post"]:
            if ACTIONS.get(verb, "") != "":
                define_action(r, ACTIONS[verb], names[verb])
        if f == "polity":
            define_action(r, TAG + "_notice", give_notice)
    if PROCEDURE == "parties" and f == "bilateral":
        set_procedure("ordinary", by_parties)
    write_lines(round())
'''

# The parameters every preset has (the core reads them all), with the bare Standing Contract's defaults.
BASE = {
    "LABEL": "",            # the contract's name in its notices and terms lines (default: the preset's title)
    "TAG": "sc",            # its actions: <TAG>_notice (and <TAG>_award under an arbiter); offices' ACTIONS by their own names
    "PARTIES": {},          # bilateral: {agent: role}
    "ROSTER": {},           # roster or polity: {agent | "office:<right>": {term: value}} enrolled at enactment
    "OPEN": False,          # roster: every member of the institution is enrolled (a shop's Board: open to all who join)
    "ROLE": "member",       # what a roster party is called in its terms line
    "TERMS": {},            # named values legs refer to (per member overrides in ROSTER)
    "LEGS": [],
    "TERM": 0,              # rounds until it ends by itself (0: open-ended)
    "NOTICE": 1,
    "GRACE": 1,             # would-not misses in a row before a breach
    "BOND": {},             # {role: {item: qty}} kept in escrow (the source of penalties)
    "PENALTY": {},          # {"item", "qty"} forfeited from the breacher's bond to the injured party
    "EXIT_FEE": 0,          # in PENALTY's item, for leaving without notice
    "FORUM": "escrow",      # escrow | arbiter:<agent> | court
    "VISIBILITY": "public",     # public (terms and book in its public record) | parties
    "PROCEDURE": "",        # "" (the institution's own) | parties (bilateral: every party must vote yes)
    "OFFICE": "",           # the office whose holders run ACTIONS (e.g. "head", or "J0.paymaster" in a polity)
    "ACTIONS": {},          # {enrol, drop, set, post: action name}
    "ENROL_TERM": "",       # the term an enrol action's value sets (Payroll: wage)
    "SET_TERM": "",         # the term the set action changes (Payroll: wage; Board: price)
    "EXPEL": False,         # roster: dropping someone also expels them from the institution (Payroll: fire)
    "ON_BREACH": "",        # "" | drop (off the roster) | expel
    "FINE": 0,              # polity: fine per unit short when the member held it at the start of the round (Quota)
    "FINE_ITEM": "",
}

PRESETS = {
    "Standing Contract": {
        "topic": "contracts", "fires": "on_round_end",
        "intent": "Per-round legs between the named PARTIES (bilateral: this contract is its own association, its members the parties), "
                  "run at the end of every round with no action from anyone: each leg moves qty of an item from one party to another "
                  "(pull within the payer's allowance, never below its keep), per unit of another leg when `per` names one. A payer "
                  "who could not pay (holdings short) misses; one who would not (allowance cut) is in breach after GRACE misses: "
                  "PENALTY from its bond to the injured party. Notice (sc_notice) ends it after NOTICE rounds; leaving without "
                  "notice costs EXIT_FEE. Each party sees its terms every turn.",
        "doc": "The generic standing contract (review 31 §2.1): legs, bond, grace, notice priced by an exit fee, could-not vs "
               "would-not misses, a forum for breach. Found it with the parties as members.",
        "params": {"PARTIES": {"Ann": "seller", "Bo": "buyer"},
                   "LEGS": [{"id": "L1", "from": "seller", "to": "buyer", "item": "food", "qty": 4, "keep": 1},
                            {"id": "L2", "from": "buyer", "to": "seller", "item": "penny", "qty": 1.5, "per": "L1"}],
                   "BOND": {"seller": {"penny": 5}, "buyer": {"penny": 5}}, "PENALTY": {"item": "penny", "qty": 3},
                   "EXIT_FEE": 5, "PROCEDURE": "parties"}},
    "Retainer": {
        "topic": "contracts", "fires": "on_round_end",
        "intent": "A retainer: the client pays the counsel a fee each round while the retainer runs; either gives notice "
                  "(retainer_notice) to end it after NOTICE rounds.",
        "doc": "A bilateral retainer (a lawyer, a guard, a scribe): a fee each round, notice both ways.",
        "params": {"TAG": "retainer", "PARTIES": {"Ann": "client", "Bo": "counsel"},
                   "TERMS": {"fee": 1, "pay": "penny"},
                   "LEGS": [{"id": "F", "from": "client", "to": "counsel", "item": "pay", "qty": "fee"}],
                   "PENALTY": {"item": "penny", "qty": 1}, "EXIT_FEE": 1, "PROCEDURE": "parties"}},
    "Supply Contract": {
        "topic": "supply", "fires": "on_round_end",
        "intent": "Supply (the buyer firm's code): each round every supplier on the roster delivers up to its qty of food into the "
                  "firm's store (from its allowance, keeping keep), and the firm pays price per unit delivered out of its treasury, "
                  "or owes it. A supplier who could not deliver misses; one who would not (allowance cut) is in breach after GRACE. "
                  "Suppliers give notice with supply_notice; the firm's officer enrols (supply_enrol) and drops suppliers and sets "
                  "the price.",
        "doc": "Producer to store, paid per unit after delivery (review 31 01 §3.2): a roster contract in the buyer firm's code.",
        "params": {"TAG": "supply", "ROLE": "supplier",
                   "TERMS": {"qty": 4, "price": 1, "keep": 1, "store": "store:S1", "goods": "food", "pay": "penny"},
                   "LEGS": [{"id": "D", "from": "member", "to": "store", "item": "goods", "qty": "qty", "keep": "keep"},
                            {"id": "P", "from": "treasury", "to": "member", "item": "pay", "qty": "price", "per": "D", "owe": True}],
                   "NOTICE": 2, "GRACE": 1, "BOND": {"member": {"penny": 5}}, "PENALTY": {"item": "penny", "qty": 2},
                   "EXIT_FEE": 5, "ACTIONS": {"enrol": "supply_enrol", "drop": "supply_drop", "set": "supply_price"},
                   "SET_TERM": "price", "ENROL_TERM": "qty"}},
    "Board": {
        "topic": "board", "fires": "on_round_end",
        "intent": "A board (the shop's code, or a polity's ration shop): each round every subscriber gets its ration of food from the "
                  "store and pays price per unit out of its allowance; a stockout charges nothing, and a subscriber who cannot or "
                  "will not pay gets only what it pays for. Subscribing: join the shop and set_allowance in pay (OPEN), or be "
                  "enrolled; unsubscribing is free (allowance 0, or board_notice). The officer sets the price (board_price).",
        "doc": "A subscription: X money a round for Y food from a store, no per-round action (review 31 01 Provision "
               "Subscription, 03 Board, the State Ration Shop).",
        "params": {"TAG": "board", "ROLE": "subscriber", "OPEN": True,
                   "TERMS": {"ration": 1, "price": 2, "store": "store:S1", "pay": "penny"},
                   "LEGS": [{"id": "F", "from": "store", "to": "member", "item": "food", "qty": "ration", "breach": False},
                            {"id": "P", "from": "member", "to": "treasury", "item": "pay", "qty": "price", "per": "F", "breach": False}],
                   "NOTICE": 0, "GRACE": 1, "ACTIONS": {"set": "board_price"}, "SET_TERM": "price"}},
    "Payroll": {
        "topic": "wages", "fires": "on_round_end",
        "intent": "A payroll (an employer's code, or a polity's civil list): each round every worker on the roster is paid its wage "
                  "out of the treasury (salary), or its wage per unit of output when its basis is piece; the cut of a worker's "
                  "harvests goes to the treasury. A wage the treasury cannot pay is owed and paid first when it can (the arrears "
                  "register). The officer hires (an applicant, at a wage), fires (severance from the treasury; the worker leaves), "
                  "sets wages and posts jobs. Roster keys office:<right> pay every holder of that office.",
        "doc": "Salaried or piece-rate employment with hire, fire, set_wage and post_job and an arrears register (review 31 03 §4.2); "
               "replaces Wage Roll, and pays offices of J0 (the polity form) so a salaried state needs no association.",
        "params": {"TAG": "payroll", "ROLE": "worker",
                   "TERMS": {"wage": 2, "basis": "salary", "cut": 0, "pay": "penny"},
                   "LEGS": [{"id": "W", "from": "treasury", "to": "member", "item": "pay", "qty": "wage", "owe": True,
                             "when": {"basis": "salary"}},
                            {"id": "O", "kind": "harvest", "from": "member", "to": "treasury", "qty": "cut"},
                            {"id": "R", "from": "treasury", "to": "member", "item": "pay", "qty": "wage", "per": "O", "owe": True,
                             "when": {"basis": "piece"}}],
                   "NOTICE": 1, "ACTIONS": {"enrol": "hire", "drop": "fire", "set": "set_wage", "post": "post_job"},
                   "ENROL_TERM": "wage", "SET_TERM": "wage", "EXPEL": True}},
    "Quota": {
        "topic": "quota", "fires": "on_round_end",
        "intent": "A procurement quota (a polity's law, compulsory): each round the polity takes up to each listed producer's quota "
                  "of food into its store, never below keep, and pays price per unit out of its treasury, or owes it. A shortfall is "
                  "entered in the book; with FINE set, a producer who held the quota at the start of the round and delivered short "
                  "is fined per unit short.",
        "doc": "Compulsory paid delivery to a polity store with a shortfall book (review 31 01 §3.3 Procurement Quota).",
        "params": {"TAG": "quota", "ROLE": "producer",
                   "TERMS": {"quota": 3, "price": 1, "keep": 1, "store": "store:S1", "goods": "food", "pay": "penny"},
                   "LEGS": [{"id": "D", "from": "member", "to": "store", "item": "goods", "qty": "quota", "keep": "keep"},
                            {"id": "P", "from": "treasury", "to": "member", "item": "pay", "qty": "price", "per": "D", "owe": True}],
                   "NOTICE": 0, "ACTIONS": {"enrol": "quota_enrol", "drop": "quota_drop", "set": "set_quota"},
                   "ENROL_TERM": "quota", "SET_TERM": "quota"}},
    "Grant": {
        "topic": "grant", "fires": "on_round_end",
        "intent": "A standing grant: every EVERY rounds qty of item goes out of the treasury to the recipient (an agent, an "
                  "institution's treasury assoc:<id>, or a store), while the treasury holds it (keeping keep).",
        "doc": "A budget line: a polity's or a principal's standing delivery to any account (review 31 02 Standing Delivery).",
        "params": {"TAG": "grant", "TERMS": {"recipient": "assoc:A1", "goods": "penny", "qty": 5, "every": 1, "keep": 0},
                   "LEGS": [{"id": "G", "from": "treasury", "to": "recipient", "item": "goods", "qty": "qty", "every": "every",
                             "keep": "keep"}],
                   "NOTICE": 0}},
    "Charge": {
        "topic": "dues", "fires": "on_round_end",
        "intent": "A charge (dues, rent, a subscription to a paper): each round every member on the roster pays dues out of its "
                  "allowance into the treasury; a member who would not pay for more than GRACE rounds in a row is dropped from the "
                  "roster.",
        "doc": "Dues or a subscription charged per round, with a drop after missed payments (review 31 04 Subscription, 01 Member "
               "Dues).",
        "params": {"TAG": "charge", "ROLE": "payer", "OPEN": True, "TERMS": {"dues": 1, "pay": "penny"},
                   "LEGS": [{"id": "C", "from": "member", "to": "treasury", "item": "pay", "qty": "dues"}],
                   "NOTICE": 0, "GRACE": 2, "ON_BREACH": "drop"}},
}


def header(name: str, params: dict) -> str:
    """A preset's code: its title and intent, then every parameter (BASE overridden by the preset), then CORE."""
    p = PRESETS[name]
    lines = [f"title = {name!r}", f"intent = {' '.join(p['intent'].split())!r}"]
    vals = {**BASE, "LABEL": name, **p["params"], **(params or {})}
    for key in BASE:
        lines.append(f"{key} = {vals[key]!r}")
    return "\n".join(lines) + "\n" + CORE


def code(name: str) -> str:
    return header(name, {})


def merged(name: str, params: dict | None) -> dict:
    """A preset's params for a spec: dict parameters TERMS, ACTIONS and BOND merged over the preset's (so a spec names only what
    differs); everything else replaces."""
    p = PRESETS[name]["params"]
    out = dict(params or {})
    for key in ("TERMS", "ACTIONS", "BOND"):
        if key in out and isinstance(out[key], dict):
            out[key] = {**BASE[key], **(p.get(key) or {}), **out[key]}
    return out


def register(established_template) -> None:
    """Called by library.py: each preset as an established template of kind contract (an association's code; the Payroll, Board,
    Quota and Grant presets also run as a polity's law)."""
    for name, p in PRESETS.items():
        established_template(name, "contract", p["topic"], code(name), doc=p["doc"], fires=p["fires"], needs=("contracts",))


def is_preset(name) -> bool:
    return name in PRESETS
