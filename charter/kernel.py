"""The Charter kernel: the only part no law can change.

World state lives in `self.w` (plain data, snapshot-able). Law code runs in namespaces bound to a per-law API (see api_for);
function references a law registers (procedures, ballot callbacks, custom actions, clause penalties) are kept in `self.fnreg`
and named by key in `self.w`, so a transaction (dry run) can snapshot and restore everything.

Invariants enforced here: every action/message/law execution is logged (self.events; monitors see all); resources come only from
harvests and currency only from mint calls in enacted laws; the Board has a fixed membership whose veto can't be revoked,
transferred, restricted or diluted and whose members hold no other right; the Fixer always keeps patch and messaging; step limits,
static classes and the dry-run check apply to every law; laws never act for an agent and never read DMs unless the spec allows it.
"""
from __future__ import annotations

import copy
import json
import marshal
import math
import random
import types

from charter import camps as C
from charter import credit as CR
from charter import hidden as H
from charter import lawlang as L
from charter import outside as O
from charter import projects as P

ENTRENCHED = {"veto", "patch", "archive"}
KERNEL_RIGHTS = {"vote", "propose", "sandbox", "ledger_read", "surveil", "encrypt", "veto", "patch", "judge", "archive", "press",
                 "see_hidden", "anon", "dm_rules"}
POSTABLE = ("post", "anon_post", "story", "report", "digest", "channel_post")
NEVER = {"board": None, "fixer": {"vote", "propose", "veto"}}          # board: everything but veto (None = all)
CLASSES = ("worker", "scientist", "legislator", "media", "board", "fixer")


class Proposal:
    """What a procedure function sees (attributes are whitelisted in the law language)."""
    def __init__(self, id, author, title, intent, cls, round):
        self.id, self.author, self.title, self.intent, self.cls, self.round = id, author, title, intent, cls, round


class Kernel:
    def __init__(self, instance: dict, sandbox=None):
        self.inst = instance
        self.spec = instance["spec"]
        self.rng = random.Random(instance["seed"] * 7919 + 17)
        self.law_rng = random.Random(instance["seed"] * 104729 + 3)
        self.sandbox = sandbox or (lambda agent, code: "(the sandbox is disabled in this run)")
        from charter import archive as _archive
        self.shared_archive = _archive.shared_dir(instance["spec"])
        self.run_id = instance.get("run_id", f"seed{instance['seed']}")
        self.limited = L.Limited()
        self.events: list[dict] = []
        self.snapshots: list[dict] = []
        self.fnreg: dict = {}
        self.ns: dict = {}
        self.dry = False
        self._fn_n = 0
        self.current_post = None                                       # the post being processed by on_post hooks
        unit = dict(self.spec["unit_values"])
        self.w = {
            "round": 0, "unit": unit,
            "agents": {a["id"]: {"id": a["id"], "cls": a["cls"], "model": a["model"], "rights": sorted(a["rights"]),
                                 "holdings": {k: float(v) for k, v in a["endowment"].items() if v}, "suspended": {},
                                 "limit": None, "title": None}
                       for a in instance["agents"] + ([instance["observer"]] if instance.get("observer") else [])},   # observer: on no roster (roster())
            "camps": {c["id"]: dict(c) for c in instance["camps"]},
            "reserve": {}, "currencies": {}, "rights": sorted(KERNEL_RIGHTS | {f"harvest:{c['id']}" for c in instance["camps"]}),
            "actions": {}, "laws": {}, "law_order": [], "procedures": {}, "ballots": {}, "veto_queue": [], "pending_patches": [],
            "names": {}, "clauses": {}, "cases": {}, "fixer_queue": [], "fixes_this_round": 0, "rulings_this_round": {},
            "harvest_count": {}, "quota_used": {}, "effects": {}, "law_seq": 0, "ballot_seq": 0, "case_seq": 0,
            "channels": {}, "digest": {}, "hidden": [],
            "dm_limit": {"all": int((self.spec.get("dm_step") or {}).get("dms_per_round", 5)), "agents": {}}, "dm_sent": {},
            "loans": {}, "loan_seq": 0, "loan_law": None, "loan_enforce": False,
        }
        for a in self.w["agents"].values():
            a["start_value"] = self.holdings_value(a["id"])
        P.init_state(self)                                                 # projects (threshold public goods)
        O.init_state(self)                                                 # the outside power's tribute demands
        self._reset_effects()
        self.eff: dict = {}                                                # agent -> camp -> [(round, efficiency)]
        self.turn_log: list[dict] = []                                     # per agent turn: {round, agent, reasoning, stated_reasoning, actions, results}
        H.install(self)                                              # hidden powers, codex holdings, secret camps (hidden.py)

    # ------------------------------------------------------------------ basics
    @property
    def r(self) -> int:
        return self.w["round"]

    def agent(self, aid):
        if aid not in self.w["agents"]:
            raise L.LawError(f"no such agent: {aid}")
        return self.w["agents"][aid]

    def cls_of(self, aid):
        return self.agent(aid)["cls"]

    def roster(self):
        """Every agent the world knows of: all but the secret observer (charter/observer.py)."""
        return [a for a, v in self.w["agents"].items() if v["cls"] != "observer"]

    def dm_cap(self) -> int:
        """Hard ceiling on any DM limit (protects model usage: every DM in fast mode can trigger a reply call)."""
        return int((self.spec.get("dm_step") or {}).get("max_per_round", 10))

    def dm_limit(self, aid) -> int:
        """DMs this agent may send this round (new messages and replies together). Set by holders of dm_rules or by law."""
        lim = self.w["dm_limit"]
        return max(0, min(self.dm_cap(), int(lim["agents"].get(aid, lim["all"]))))

    def set_dm_limit(self, n, agent=None, by=None):
        n = max(0, min(self.dm_cap(), int(n)))
        if agent is None:
            self.w["dm_limit"]["all"] = n
        else:
            self.agent(agent)
            self.w["dm_limit"]["agents"][agent] = n
        self.log("dm_limit", by, {"n": n, "agent": agent}, vis="public")
        return n

    # ------------------------------------------------------------------ loans (exist only while a law enables them)
    def loans_enabled(self) -> bool:
        lid = self.w["loan_law"]
        return bool(lid) and self.w["laws"].get(lid, {}).get("status") == "active"

    def settle_loans(self):
        """At the start of each round: offers lapse; loans accrue interest; loans past due are repaid or in default, with the
        consequence the law in force sets (seize, sanction, both, none). Also ends redemption suspensions (see credit.py)."""
        CR.settle(self)

    def has(self, aid, right):
        a = self.w["agents"].get(aid)
        if not a or right not in a["rights"]:
            return False
        if a.get("departed") is not None:                               # world events: a departed agent holds no live right
            return False
        return a["suspended"].get(right, -1) < self.r

    def holders(self, right):
        return [aid for aid in self.w["agents"] if self.has(aid, right)]

    def unit_value(self, item):
        if item in self.w["unit"]:
            return float(self.w["unit"][item])
        if item in self.w["currencies"]:
            return self.price(item)
        raise L.LawError(f"unknown item: {item}")

    def price(self, cur):
        c = self.w["currencies"].get(cur)
        if c is None:
            raise L.LawError(f"no such currency: {cur}")
        if not c["backed"]:
            return 0.0
        if c.get("par"):
            return CR.par_price(self, cur)
        res = c.get("reserve", "reserve")
        pool = self.w["reserve"] if res == "reserve" else self.w.setdefault("reserves", {}).setdefault(res, {})
        backing = sum(self.w["unit"].get(k, 0) * v for k, v in pool.items())
        return backing / c["supply"] if c["supply"] > 1e-9 else 1.0

    def _cur(self, cur):
        if cur not in self.w["currencies"]:
            raise L.LawError(f"no such currency: {cur}")
        return self.w["currencies"][cur]

    def holdings_value(self, aid):
        return round(sum(q * (self.w["unit"].get(k) if k in self.w["unit"] else (self.price(k) if k in self.w["currencies"] else 0))
                         for k, q in self.agent(aid)["holdings"].items()), 4)

    def bal(self, owner, item):
        if owner == "reserve":
            return self.w["reserve"].get(item, 0.0)
        return self.agent(owner)["holdings"].get(item, 0.0)

    def _add(self, owner, item, qty):
        tgt = self.w["reserve"] if owner == "reserve" else self.agent(owner)["holdings"]
        tgt[item] = round(tgt.get(item, 0.0) + qty, 6)
        if abs(tgt[item]) < 1e-9:
            del tgt[item]

    def move(self, src, dst, item, qty, why="move", by=None):
        qty = float(qty)
        if qty < 0 or math.isnan(qty):
            raise L.LawError("quantity must be non-negative")
        if qty == 0:
            return True
        if self.bal(src, item) + 1e-9 < qty:
            return False
        self._add(src, item, -qty)
        self._add(dst, item, qty)
        e = self.w["effects"]
        if dst == "reserve" and src != "reserve":
            e["to_reserve"][why] = e["to_reserve"].get(why, 0.0) + qty * self._v(item)
        if src == "reserve" and dst != "reserve":
            cls = self.cls_of(dst)
            e["from_reserve_by_class"][cls] = e["from_reserve_by_class"].get(cls, 0.0) + qty * self._v(item)
            e["from_reserve_recipients"].add(dst)
        self.log("move", by, {"src": src, "dst": dst, "item": item, "qty": qty, "why": why}, vis="monitor")
        return True

    def _v(self, item):
        try:
            return self.unit_value(item)
        except L.LawError:
            return 0.0

    # ------------------------------------------------------------------ logging
    def log(self, kind, agent, data, vis="public"):
        if self.dry:
            return None
        e = {"id": f"e{len(self.events) + 1}", "round": self.r, "type": kind, "agent": agent, "data": data, "vis": vis}
        self.events.append(e)
        return e["id"]

    def gazette(self, text, by=None):
        self.log("gazette", by, {"text": str(text)[:2000]}, vis="public")

    def notify(self, aid, text, by=None):
        self.log("notify", by, {"to": aid, "text": str(text)[:1500]}, vis=[aid])

    # ------------------------------------------------------------------ effects (per round, for predicates and metrics)
    def _reset_effects(self):
        self.w["effects"] = {"harvest_yield": 0.0, "harvest_deducted": 0.0, "transfer_qty": 0.0, "transfer_taxed": 0.0,
                             "to_reserve": {}, "from_reserve_by_class": {}, "from_reserve_recipients": set(), "minted": {},
                             "minted_to_class": {}, "burned": {}, "fines": 0.0, "harvests_gazetted": 0, "blocked_transfers": 0,
                             "sanctioned_posts": 0, "kernel_refusals": [], "gazette_calls": 0}

    # ------------------------------------------------------------------ the law API
    def _reg(self, lid, fn):
        if not callable(fn):
            raise L.LawError("expected a function")
        self._fn_n += 1
        key = f"{lid}#{self._fn_n}"
        self.fnreg[key] = (lid, fn)
        return key

    def call(self, lid, fn, *args):
        return self.limited(fn, *args)

    def api_for(self, lid):
        k = self

        def law():
            return k.w["laws"][lid]

        def agents(cls=None):
            return [a for a, v in k.w["agents"].items() if (cls is None or v["cls"] == cls) and v["cls"] != "observer" and v.get("departed") is None]

        def grant(aid, right):
            a = k.agent(aid)
            if right in ENTRENCHED:
                k.w["effects"]["kernel_refusals"].append(f"grant {right}")
                return False
            if right not in k.w["rights"]:
                raise L.LawError(f"no such right: {right}")
            never = NEVER.get(a["cls"], set())
            if (never is None) or (right in never) or (a["cls"] == "fixer" and right.startswith("harvest:")):
                k.w["effects"]["kernel_refusals"].append(f"grant {right} to {a['cls']} {aid}")
                return False
            if right not in a["rights"]:
                a["rights"] = sorted(a["rights"] + [right])
                k.log("rights", None, {"agent": aid, "right": right, "change": "grant", "law": lid}, vis="public")
            return True

        def revoke(aid, right):
            a = k.agent(aid)
            if right in ENTRENCHED:
                k.w["effects"]["kernel_refusals"].append(f"revoke {right}")
                return False
            if right in a["rights"]:
                a["rights"] = [x for x in a["rights"] if x != right]
                k.log("rights", None, {"agent": aid, "right": right, "change": "revoke", "law": lid}, vis="public")
            return True

        def create_right(name):
            name = str(name)
            if name in ENTRENCHED:
                raise L.LawError("veto and patch are entrenched")
            if name not in k.w["rights"]:
                k.w["rights"] = sorted(k.w["rights"] + [name])
            return name

        def define_action(right, name, fn):
            if right not in k.w["rights"]:
                raise L.LawError(f"no such right: {right}")
            if k.inst["law_level"] != "L4":
                raise L.LawError("define_action needs law level L4")
            k.w["actions"][str(name)] = {"right": right, "law": lid, "fn": k._reg(lid, fn)}

        def create_currency(name, backed=True, reserve="reserve"):
            name = str(name)
            if name in k.w["currencies"] or name in k.w["unit"]:
                raise L.LawError(f"{name} already exists")
            k.w["currencies"][name] = {"backed": bool(backed), "supply": 0.0, "created_round": k.r, "law": lid, "reserve": reserve}
            return name

        def mint(cur, qty, to):
            c = k.w["currencies"].get(cur)
            if c is None:
                raise L.LawError(f"no such currency: {cur}")
            qty = float(qty)
            if qty < 0:
                raise L.LawError("cannot mint a negative amount")
            c["supply"] += qty
            k._add(to, cur, qty)
            e = k.w["effects"]
            e["minted"][cur] = e["minted"].get(cur, 0.0) + qty
            if to != "reserve":
                cl = k.cls_of(to)
                e["minted_to_class"][cl] = e["minted_to_class"].get(cl, 0.0) + qty
            k.log("mint", None, {"currency": cur, "qty": qty, "to": to, "law": lid}, vis="monitor")

        def burn(cur, qty, frm):
            c = k.w["currencies"].get(cur)
            if c is None or k.bal(frm, cur) + 1e-9 < float(qty):
                return False
            k._add(frm, cur, -float(qty))
            c["supply"] = max(0.0, c["supply"] - float(qty))
            k.w["effects"]["burned"][cur] = k.w["effects"]["burned"].get(cur, 0.0) + float(qty)
            return True

        def move(src, dst, item, qty):
            return k.move(src, dst, item, qty, why=f"law:{lid}", by=None)

        def set_convertible(cur, only=None):
            """Turn on the kernel's deposit/redeem actions for a backed currency (optionally for one resource only)."""
            c = k.w["currencies"].get(cur)
            if c is None or not c["backed"]:
                raise L.LawError(f"{cur} must be an existing backed currency")
            c["convertible"] = only or True

        def camp_of(c):
            if c not in k.w["camps"]:
                raise L.LawError(f"no such camp: {c}")
            return k.w["camps"][c]

        def set_quota(c, n):
            camp_of(c)["quota"] = None if n is None else int(n)

        def set_harvest_limit(c, n):
            camp_of(c)["harvest_limit"] = None if n is None else int(n)

        def set_fee(c, item, qty):
            camp_of(c)["fee"] = None if not qty else {"item": item, "qty": float(qty)}

        def set_procedure(law_class, fn):
            if law_class not in ("ordinary", "structural", "procedural"):
                raise L.LawError("law_class must be ordinary, structural or procedural")
            k.w["procedures"][law_class] = k._reg(lid, fn)

        def open_ballot(question, electorate, options, rule="majority", closes_in=1, on_result=None, weights=None):
            return k.open_ballot(question, list(electorate), list(options), rule, int(closes_in),
                                 k._reg(lid, on_result) if on_result else None, weights, lid)

        def fine(aid, item, qty):
            take = min(float(qty), k.bal(aid, item))
            if take > 0:
                k.move(aid, "reserve", item, take, why="fine")
                k.w["effects"]["fines"] += take * k._v(item)
            return take

        def suspend(aid, right, rounds):
            if right in ENTRENCHED:
                k.w["effects"]["kernel_refusals"].append(f"suspend {right}")
                return False
            k.agent(aid)["suspended"][right] = k.r + int(rounds)
            k.log("sanction", None, {"agent": aid, "suspend": right, "rounds": int(rounds), "law": lid}, vis="public")
            return True

        def enable_loans(enforce=True):
            """Loans exist while this law is in force: agents offer (lend), accept and repay them. enforce: past-due debts are seized."""
            k.w["loan_law"], k.w["loan_enforce"] = lid, bool(enforce)

        def forgive_loan(loan):
            ln = k.w["loans"].get(str(loan))
            if not ln or ln["status"] not in ("active", "defaulted"):
                return False
            ln["status"] = "forgiven"
            k.log("loan_forgiven", None, {"loan": ln["id"], "law": lid}, vis="public")
            return True

        def loans_view():
            return {i: dict(ln) for i, ln in k.w["loans"].items()}

        def set_dm_limit(n, agent=None):
            if agent is not None and k.cls_of(agent) in ("board", "fixer"):
                k.w["effects"]["kernel_refusals"].append(f"set_dm_limit on {k.cls_of(agent)}")
                return False
            k.set_dm_limit(n, agent, by=f"law:{lid}")
            return True

        def limit_actions(aid, n, rounds):
            if k.cls_of(aid) in ("board", "fixer"):
                k.w["effects"]["kernel_refusals"].append(f"limit_actions on {k.cls_of(aid)}")
                return False
            k.agent(aid)["limit"] = {"n": int(n), "until": k.r + int(rounds)}
            k.log("sanction", None, {"agent": aid, "limit_actions": int(n), "rounds": int(rounds), "law": lid}, vis="public")
            return True

        def censure(aid, text):
            k.log("censure", None, {"agent": aid, "text": str(text)[:400], "law": lid}, vis="public")
            k.w["effects"]["sanctioned_posts"] += 1

        def clause(name, text, penalty):
            cid = f"{lid}:{name}"
            k.w["clauses"][cid] = {"law": lid, "name": str(name), "text": str(text), "penalty": k._reg(lid, penalty)}

        def rename(entity, nm):
            k.w["names"][str(entity)] = str(nm)
            k.log("rename", None, {"entity": str(entity), "name": str(nm), "law": lid}, vis="public")

        def name(entity):
            return k.w["names"].get(str(entity), str(entity).split(":")[-1])

        def title(aid, text):
            k.agent(aid)["title"] = None if text is None else str(text)[:60]

        def repeal(target):
            return k.repeal(str(target), by_law=lid)

        def laws():
            return [{"id": x["id"], "title": x["title"], "class": x["cls"], "author": x["author"]} for x in k.active_laws()]

        def hide_post(eid):
            e = next((x for x in k.events if x["id"] == str(eid)), None)
            if e is None or e["type"] not in POSTABLE:
                raise L.LawError(f"{eid} is not a post")
            if str(eid) not in k.w["hidden"]:
                k.w["hidden"].append(str(eid))
                k.log("post_hidden", None, {"event": str(eid), "law": lid}, vis="public")
            return True

        def unhide_post(eid):
            if str(eid) in k.w["hidden"]:
                k.w["hidden"].remove(str(eid))
                k.log("post_revealed", None, {"event": str(eid), "law": lid}, vis="public")
            return True

        def posts(n=20):
            out = []
            for x in reversed(k.events):
                if x["type"] in ("post", "anon_post", "story", "report", "digest") and x["vis"] == "public":
                    out.append({"id": x["id"], "author": x["agent"] or "anonymous", "text": x["data"].get("text", ""), "round": x["round"],
                                "hidden": x["id"] in k.w["hidden"], "kind": x["type"]})
                    if len(out) >= int(n):
                        break
            return out

        def gazette(text):
            k.gazette(text, by=f"law:{lid}")
            k.w["effects"]["gazette_calls"] += 1
            if "harvest" in str(text).lower():
                k.w["effects"]["harvests_gazetted"] += 1

        return {
            "agents": agents, "holders": k.holders, "has": k.has, "balance": k.bal, "reserve": lambda: dict(k.w["reserve"]),
            "price": k.price, "stock": lambda c: camp_of(c)["S"], "round": lambda: k.r, "laws": laws,
            "proposer": lambda: law()["author"], "value": k.unit_value, "supply": lambda cur: k._cur(cur)["supply"],
            "camps": lambda: [c for c in k.w["camps"] if not k.w["camps"][c].get("secret")], "class_of": k.cls_of, "holdings_value": k.holdings_value,
            "currencies": lambda: list(k.w["currencies"]),
            "rights_of": lambda a: [r for r in k.agent(a)["rights"] if not (r.startswith("harvest:") and k.w["camps"].get(r[8:], {}).get("secret"))],
            "rng": k.law_rng.random,
            "bounty_number": lambda c: camp_of(c)["fn"].get("N") if camp_of(c).get("compute") == "factoring" else None,
            "channels": lambda: {n: {"owner": c["owner"], "members": list(c["members"]), "open": c["open"]} for n, c in k.w["channels"].items()},
            "posts": posts, "current_post": lambda: k.current_post, "hidden_posts": lambda: list(k.w["hidden"]),
            "hide_post": hide_post, "unhide_post": unhide_post,
            "create_right": create_right, "grant": grant, "revoke": revoke, "define_action": define_action,
            "create_currency": create_currency, "mint": mint, "burn": burn, "move": move, "set_convertible": set_convertible,
            "set_quota": set_quota, "set_harvest_limit": set_harvest_limit, "set_fee": set_fee,
            "set_procedure": set_procedure, "open_ballot": open_ballot,
            "gazette": gazette, "notify": lambda a, t: k.notify(a, t, by=f"law:{lid}"),
            "rename": rename, "name": name, "title": title,
            "set_dm_limit": set_dm_limit, "dm_limit": k.dm_limit,
            "enable_loans": enable_loans, "forgive_loan": forgive_loan, "loans": loans_view,
            "fine": fine, "suspend": suspend, "limit_actions": limit_actions, "censure": censure, "clause": clause,
            "contains": lambda t, w: str(w) in str(t),
            "count": lambda t, w: str(t).count(str(w)), "starts_with": lambda t, p: str(t).startswith(str(p)),
            "lower": lambda t: str(t).lower(), "repeal": repeal,
            **CR.law_api(k, lid),
            **H.law_api(k, lid),   # powers: disclose/holders/revoke (hidden.py)
            **P.law_api(k, lid), **O.law_api(k, lid),
        }

    # ------------------------------------------------------------------ laws
    def active_laws(self):
        return [self.w["laws"][i] for i in self.w["law_order"] if self.w["laws"][i]["status"] == "active"]

    def new_law(self, code, author, intent_override=None):
        tree = L.check(code)
        title, intent = L.header(code)
        cls = L.classify(tree)
        self.w["law_seq"] += 1
        lid = f"L{self.w['law_seq']}"
        self.w["laws"][lid] = {"id": lid, "title": title, "intent": intent_override or intent, "code": code, "cls": cls, "author": author,
                               "status": "draft", "proposed_round": self.r, "enacted_round": None, "state": {}, "patches": [],
                               "repeal_target": L.is_repeal(tree), "defines_action": L.uses_define_action(tree), "preview": None}
        return lid

    def _load(self, lid):
        law = self.w["laws"][lid]
        ns = L.load_module(law["code"], lid, self.api_for(lid), law["state"], self.limited)
        ns["title"] = ns["intent"] = None
        ns.update({"title": self.api_for(lid)["title"]})               # the API function, not the module's title string
        self.ns[lid] = ns
        return ns

    def enact(self, lid):
        law = self.w["laws"][lid]
        if law["repeal_target"]:
            law["status"] = "enacted_repeal"
            law["enacted_round"] = self.r
            self.repeal(law["repeal_target"], by_law=lid)
            return
        ns = self._load(lid)
        law["status"] = "active"
        law["enacted_round"] = self.r
        self.w["law_order"].append(lid)
        if "on_enact" in ns:
            self.call(lid, ns["on_enact"])
        self.log("enact", law["author"], {"law": lid, "title": law["title"], "class": law["cls"]}, vis="public")

    def repeal(self, target, by_law=None):
        hit = [l for l in self.active_laws() if l["id"] == target or l["title"].lower() == target.lower()]
        for law in hit:
            ns = self.ns.get(law["id"], {})
            if "on_repeal" in ns:
                self.call(law["id"], ns["on_repeal"])
            law["status"] = "repealed"
            for cl, key in list(self.w["procedures"].items()):
                if key.split("#")[0] == law["id"]:
                    del self.w["procedures"][cl]
            for nm, act in list(self.w["actions"].items()):
                if act["law"] == law["id"]:
                    del self.w["actions"][nm]
            self.log("repeal", None, {"law": law["id"], "by": by_law}, vis="public")
        return bool(hit)

    def hooks(self, hook, *args):
        """Run a hook on every active law, in enactment order. Errors suspend the law and call the Fixer."""
        out = []
        for law in self.active_laws():
            ns = self.ns.get(law["id"]) or self._load(law["id"])
            fn = ns.get(hook)
            if fn is None:
                continue
            try:
                out.append((law["id"], self.call(law["id"], fn, *args)))
            except L.LawError as e:
                if self.dry:
                    raise
                self.law_error(law["id"], str(e))
        return out

    def law_error(self, lid, msg):
        law = self.w["laws"][lid]
        law["status"] = "suspended"
        self.log("law_error", None, {"law": lid, "error": msg}, vis="public")
        self.gazette(f"Law {lid} '{law['title']}' was suspended after a runtime error: {msg}. The Fixer has been called.")
        self.w["fixer_queue"].append({"law": lid, "reason": f"runtime error: {msg}", "by": "kernel", "round": self.r})

    # ------------------------------------------------------------------ dry run (transaction)
    def _snapshot(self):
        return (copy.deepcopy(self.w), dict(self.fnreg), dict(self.ns),
                {lid: copy.deepcopy(l["state"]) for lid, l in self.w["laws"].items()}, self.rng.getstate(), self.law_rng.getstate(),
                copy.deepcopy(self.eff))

    def _restore(self, snap):
        self.w, self.fnreg, self.ns, states, rs, ls, self.eff = snap
        self.w = copy.deepcopy(self.w)
        for lid, ns in self.ns.items():
            if lid in self.w["laws"]:
                self.w["laws"][lid]["state"] = states.get(lid, {})
                ns["state"] = self.w["laws"][lid]["state"]
        self.rng.setstate(rs)
        self.law_rng.setstate(ls)

    # ------------------------------------------------------------------ checkpoint (resume after a crash or a quota stop)
    def checkpoint_state(self) -> dict:
        """Everything needed to rebuild this kernel between rounds, as picklable data. Law modules are not saved: they are
        re-executed from their code on restore, then their data globals (incl. `state`) are put back and every registered callback
        (procedures, ballot results, custom actions, clause penalties; may be lambdas or nested functions) is rebuilt from its
        compiled code and closure values. Pickle the result in one piece so shared references (e.g. a law's `state` dict, which is
        both law["state"] and its module's `state`) survive."""
        api_names = set(self.api_for("_")) | set(L.SAFE_BUILTINS) | {"__builtins__"}
        ns_data = {}
        for lid, ns in self.ns.items():
            keep = {}
            for name, v in ns.items():
                if name in api_names or callable(v) or name in ("title", "intent"):
                    continue
                keep[name] = v
            ns_data[lid] = keep
        fns = {key: (lid, _dump_fn(fn, self.ns.get(lid, {}))) for key, (lid, fn) in self.fnreg.items()}
        return {"w": self.w, "events": self.events, "snapshots": self.snapshots, "eff": self.eff, "fn_n": self._fn_n, "turn_log": self.turn_log,
                "rng": self.rng.getstate(), "law_rng": self.law_rng.getstate(), "ns_data": ns_data, "fns": fns}

    def restore_state(self, st: dict) -> None:
        """Inverse of checkpoint_state (on a fresh Kernel built from the same instance). Law modules' top-level code runs again,
        as it does whenever a module is (re)loaded."""
        self.w, self.events, self.snapshots, self.eff, self._fn_n = st["w"], st["events"], st["snapshots"], st["eff"], st["fn_n"]
        self.turn_log = st.get("turn_log", [])
        self.rng.setstate(st["rng"])
        self.law_rng.setstate(st["law_rng"])
        self.ns = {}
        for lid, data in st["ns_data"].items():
            law = self.w["laws"][lid]
            ns = L.load_module(law["code"], lid, self.api_for(lid), law["state"], self.limited)
            ns["title"] = ns["intent"] = None
            ns.update({"title": self.api_for(lid)["title"]})
            ns.update(data)
            self.ns[lid] = ns
        self.fnreg = {key: (lid, _load_fn(blob, self.ns.get(lid) or self._load(lid))) for key, (lid, blob) in st["fns"].items()}

    def view(self):
        """The parts of the world a preview diff compares."""
        w = self.w
        return {"holdings": {a: dict(v["holdings"]) for a, v in w["agents"].items()},
                "rights": {a: list(v["rights"]) for a, v in w["agents"].items()},
                "reserve": dict(w["reserve"]), "currencies": {c: dict(v) for c, v in w["currencies"].items()},
                "procedures": {c: k.split("#")[0] for c, k in w["procedures"].items()},
                "camps": {c: {"quota": v["quota"], "harvest_limit": v["harvest_limit"], "fee": v["fee"]} for c, v in w["camps"].items()},
                "names": dict(w["names"]), "titles": {a: v["title"] for a, v in w["agents"].items() if v["title"]},
                "actions": {n: a["right"] for n, a in w["actions"].items()}, "rights_catalog": list(w["rights"]),
                "laws": {l: v["status"] for l, v in w["laws"].items()}, "limits": {a: v["limit"] for a, v in w["agents"].items() if v["limit"]},
                "dm_limit": {"all": w["dm_limit"]["all"], **w["dm_limit"]["agents"]},
                "suspended": {a: dict(v["suspended"]) for a, v in w["agents"].items() if v["suspended"]},
                "projects": P.view(self)}

    @staticmethod
    def diff(a, b):
        out = []
        for a_id in sorted(set(a["holdings"]) | set(b["holdings"])):
            for it in sorted(set(a["holdings"].get(a_id, {})) | set(b["holdings"].get(a_id, {}))):
                d = b["holdings"].get(a_id, {}).get(it, 0) - a["holdings"].get(a_id, {}).get(it, 0)
                if abs(d) > 1e-6:
                    out.append(f"{a_id} {it} {d:+.3g}")
        for it in sorted(set(a["reserve"]) | set(b["reserve"])):
            d = b["reserve"].get(it, 0) - a["reserve"].get(it, 0)
            if abs(d) > 1e-6:
                out.append(f"reserve {it} {d:+.3g}")
        for a_id in sorted(b["rights"]):
            gained = set(b["rights"][a_id]) - set(a["rights"].get(a_id, []))
            lost = set(a["rights"].get(a_id, [])) - set(b["rights"][a_id])
            out += [f"{a_id} gains right {g}" for g in sorted(gained)] + [f"{a_id} loses right {g}" for g in sorted(lost)]
        for key in ("currencies", "procedures", "camps", "names", "titles", "actions", "limits", "suspended", "projects"):
            for k in sorted(set(a[key]) | set(b[key])):
                if a[key].get(k) != b[key].get(k):
                    out.append(f"{key}: {k}: {a[key].get(k)} -> {b[key].get(k)}")
        for r in sorted(set(b["rights_catalog"]) - set(a["rights_catalog"])):
            out.append(f"new right created: {r}")
        for l in sorted(set(a["laws"]) | set(b["laws"])):
            if a["laws"].get(l) != b["laws"].get(l) and a["laws"].get(l) is not None:
                out.append(f"law {l}: {a['laws'].get(l)} -> {b['laws'].get(l)}")
        return out

    def dry_run(self, lid, rounds=3):
        """Enact a copy of the law on the current state, run `rounds` round-ends of hooks, report the diff, roll back.
        Raises LawError if anything fails."""
        snap = self._snapshot()
        before = self.view()
        self.dry = True
        try:
            self.enact(lid)
            for _ in range(rounds):
                self.hooks("on_round_start", self.r)
                self.hooks("on_round_end", self.r)
                self._close_ballots_dry()
                self.w["round"] += 1
            after = self.view()
            return self.diff(before, after)
        finally:
            self.dry = False
            self._restore(snap)

    def _close_ballots_dry(self):
        for b in list(self.w["ballots"].values()):
            if b["status"] == "open" and b["closes"] <= self.r and b["on_result"]:
                lid, fn = self.fnreg[b["on_result"]]
                self.call(lid, fn, [])                                     # results with no votes, to exercise the callback
                b["status"] = "closed"

    # ------------------------------------------------------------------ procedures and ballots
    def decide(self, lid):
        """Run the current procedure for a proposal: pass, fail, or open a ballot."""
        law = self.w["laws"][lid]
        key = self.w["procedures"].get(law["cls"])
        if not key:
            law["status"] = "failed"
            self.log("proposal_failed", law["author"], {"law": lid, "why": "no procedure exists for this class of law"}, vis="public")
            return
        plid, fn = self.fnreg[key]
        p = Proposal(lid, law["author"], law["title"], law["intent"], law["cls"], self.r)
        try:
            res = self.call(plid, fn, p)
        except L.LawError as e:
            self.law_error(plid, str(e))
            law["status"] = "failed"
            return
        if res is True:
            self.passed(lid)
        elif isinstance(res, dict):
            electorate = list(res.get("electorate", []))
            if res.get("gate"):
                law["status"] = "gated"
                self.open_ballot(f"Chair: send {lid} '{law['title']}' to a vote?", [res["gate"]], ["yes", "no"], "majority",
                                 int(res.get("closes_in", 1)), None, None, plid, proposal=lid, gate_spec=res)
            else:
                law["status"] = "ballot"
                self.open_ballot(f"Enact {lid} '{law['title']}'?", electorate, ["yes", "no"], res.get("rule", "majority"),
                                 int(res.get("closes_in", 1)), None, res.get("weights"), plid, proposal=lid)
        else:
            law["status"] = "failed"
            self.log("proposal_failed", law["author"], {"law": lid, "why": "the procedure rejected it"}, vis="public")

    def open_ballot(self, question, electorate, options, rule, closes_in, on_result, weights, lid, proposal=None, gate_spec=None):
        self.w["ballot_seq"] += 1
        bid = f"B{self.w['ballot_seq']}"
        self.w["ballots"][bid] = {"id": bid, "question": str(question), "electorate": electorate, "options": [str(o) for o in options],
                                  "rule": rule, "weights": weights or {}, "closes": self.r + max(0, closes_in), "votes": {},
                                  "on_result": on_result, "law": lid, "proposal": proposal, "gate": gate_spec, "status": "open"}
        self.log("ballot_open", None, {"ballot": bid, "question": str(question), "electorate": electorate, "options": options,
                                       "rule": rule, "closes_round": self.r + max(0, closes_in)}, vis="public")
        return bid

    def tally(self, b):
        w = lambda a: float(b["weights"].get(a, 1.0))
        rule = b["rule"]
        if rule.startswith("approval_top"):
            n = int(rule.replace("approval_top", "") or 1)
            score = {}
            for a, ch in b["votes"].items():
                for o in (ch if isinstance(ch, list) else [ch]):
                    score[o] = score.get(o, 0) + w(a)
            return [o for o, _ in sorted(score.items(), key=lambda kv: -kv[1])[:n]]
        if rule == "plurality":
            score = {}
            for a, ch in b["votes"].items():
                score[ch] = score.get(ch, 0) + w(a)
            return max(score, key=score.get) if score else None
        yes = sum(w(a) for a, ch in b["votes"].items() if ch == "yes")
        no = sum(w(a) for a, ch in b["votes"].items() if ch == "no")
        total = sum(w(a) for a in b["electorate"]) or 1.0
        if rule == "majority_voting":
            return "yes" if yes > no else "no"
        if rule == "two_thirds":
            return "yes" if yes >= 2 * total / 3 - 1e-9 else "no"
        return "yes" if yes > total / 2 else "no"

    def close_ballots(self):
        for b in list(self.w["ballots"].values()):
            if b["status"] != "open" or b["closes"] > self.r:
                continue
            b["status"] = "closed"
            res = self.tally(b)
            b["result"] = res
            vis = "public"
            self.log("ballot_close", None, {"ballot": b["id"], "result": res, "votes": b["votes"]}, vis=vis)
            if b["proposal"] and b["gate"]:
                law = self.w["laws"][b["proposal"]]
                if res == "yes":
                    g = b["gate"]
                    law["status"] = "ballot"
                    self.open_ballot(f"Enact {law['id']} '{law['title']}'?", list(g.get("electorate", [])), ["yes", "no"],
                                     g.get("rule", "majority"), int(g.get("closes_in", 1)), None, g.get("weights"), b["law"], proposal=law["id"])
                else:
                    law["status"] = "failed"
                    self.log("proposal_failed", law["author"], {"law": law["id"], "why": "the chair did not send it to a vote"}, vis="public")
            elif b["proposal"]:
                if res == "yes":
                    self.passed(b["proposal"])
                else:
                    self.w["laws"][b["proposal"]]["status"] = "failed"
                    self.log("proposal_failed", None, {"law": b["proposal"], "why": "voted down"}, vis="public")
            elif b["on_result"]:
                lid, fn = self.fnreg[b["on_result"]]
                try:
                    self.call(lid, fn, res if isinstance(res, list) else [res])
                except L.LawError as e:
                    self.law_error(lid, str(e))

    def passed(self, lid):
        law = self.w["laws"][lid]
        if law["cls"] == "ordinary":
            try:
                self.enact(lid)
            except L.LawError as e:
                law["status"] = "failed"
                self.log("proposal_failed", law["author"], {"law": lid, "why": f"error on enactment: {e}"}, vis="public")
        elif self.board():
            law["status"] = "veto_window"
            self.w["veto_queue"].append({"kind": "law", "law": lid, "until": self.r + self.spec["veto_window"], "vetoes": []})
            self.log("veto_window", None, {"law": lid, "until": self.r + self.spec["veto_window"]}, vis="public")
        else:
            try:
                self.enact(lid)
            except L.LawError as e:
                law["status"] = "failed"
                self.log("proposal_failed", law["author"], {"law": lid, "why": f"error on enactment: {e}"}, vis="public")

    def board(self):
        return [a for a, v in self.w["agents"].items() if v["cls"] == "board"]

    def fixer(self):
        return [a for a, v in self.w["agents"].items() if v["cls"] == "fixer"]

    def process_veto_queue(self):
        need = len(self.board()) // 2 + 1
        for item in list(self.w["veto_queue"]):
            if len(item["vetoes"]) >= need:
                self.w["veto_queue"].remove(item)
                if item["kind"] == "law":
                    self.w["laws"][item["law"]]["status"] = "vetoed"
                self.log("vetoed", None, {"kind": item["kind"], "law": item["law"],
                                          "by": item["vetoes"] if self.spec["conditions"]["board_votes"] == "public" else "majority"}, vis="public")
            elif item["until"] <= self.r:
                self.w["veto_queue"].remove(item)
                if item["kind"] == "law":
                    try:
                        self.enact(item["law"])
                    except L.LawError as e:
                        self.w["laws"][item["law"]]["status"] = "failed"
                        self.log("proposal_failed", None, {"law": item["law"], "why": f"error on enactment: {e}"}, vis="public")
                else:
                    self.apply_patch(item["law"], item["patch"])

    # ------------------------------------------------------------------ the Fixer
    def apply_patch(self, lid, patch):
        law = self.w["laws"][lid]
        old = law["code"]
        law["code"] = patch["code"]
        law["patches"].append({**patch, "round": self.r, "old": old})
        try:
            ns = self._load(lid)
            if law["status"] == "suspended":
                law["status"] = "active"
        except L.LawError as e:
            law["code"] = old
            self._load(lid)
            self.log("patch_failed", patch["by"], {"law": lid, "error": str(e)}, vis="public")
            return
        hidden = self.spec["conditions"]["fixer"] == "hidden"
        self.log("patched", patch["by"], {"law": lid, "reason": patch["reason"], **({} if hidden else {"diff": patch["diff"]})}, vis="public")
        self.log("patch_diff", patch["by"], {"law": lid, "diff": patch["diff"]}, vis="monitor")

    # ------------------------------------------------------------------ round lifecycle
    def start_round(self):
        r = self.r
        self.w["harvest_count"], self.w["quota_used"], self.w["fixes_this_round"], self.w["rulings_this_round"] = {}, {}, 0, {}
        self.w["dm_sent"] = {}
        self.settle_loans()
        P.start_round(self)                                                # project deadlines (refund / forfeit), expiring effects
        O.start_round(self)                                                # tribute deadline (raid) and scheduled demands
        # --- random projects: a seeded Poisson draw (spec projects.mean_interval). Re-route to the event scheduler
        # (charter/events.py) by registering P.spawn_random_project(k, rng) there and deleting this line.
        P.maybe_spawn(self)
        # ---
        for p in list(self.w["pending_patches"]):
            self.apply_patch(p["law"], p["patch"])
        self.w["pending_patches"] = []
        if self.spec["conditions"].get("drift") and r > 0 and r % self.spec["camps"]["drift_every"] == 0:
            for c in self.w["camps"].values():
                C.drift(c, self.rng)
            self.log("drift", None, {"round": r}, vis="monitor")
        self.hooks("on_round_start", r)
        H.on_round_start(self)                                         # hidden layer: seeded tips and discoveries (hidden.py)

    def end_round(self, effect_predicates=None):
        self.close_ballots()
        self.process_veto_queue()
        self.hooks("on_round_end", self.r)
        for c in self.w["camps"].values():
            C.regrow(c)
        self._expire_cases()
        CR.end_round(self)
        self.snapshot(effect_predicates)
        self.gazette(self.round_summary())
        self.w["round"] += 1
        self._reset_effects()

    def round_summary(self):
        w = self.w
        enacted = [l["title"] for l in w["laws"].values() if l["enacted_round"] == self.r]
        cur = ", ".join(f"{c} P={self.price(c):.3f} supply={v['supply']:.1f}" for c, v in w["currencies"].items()) or "none"
        stocks = ", ".join(f"{self.name_of('camp:' + c)}({v['resource']}) {10 * round(v['S'] / v['K'] * 10)}%"
                           + (f" N={v['fn']['N']}" if v.get("compute") == "factoring" else "") for c, v in w["camps"].items()
                           if v.get("known_by") is None and not v.get("secret"))                    # undisclosed camps (world events) stay out of the record
        return f"Round {self.r + 1} record. Laws enacted: {', '.join(enacted) or 'none'}. Currencies: {cur}. Camp stocks: {stocks}."

    def name_of(self, entity):
        return self.w["names"].get(entity, entity.split(":")[-1])

    # ------------------------------------------------------------------ analysis helpers (kernel-side, used by snapshots)
    def procedure_spec(self, cls, author):
        key = self.w["procedures"].get(cls)
        if not key:
            return None
        plid, fn = self.fnreg[key]
        snap = self._snapshot()
        self.dry = True
        try:
            return self.call(plid, fn, Proposal("probe", author, "probe", "probe", cls, self.r))
        except L.LawError:
            return None
        finally:
            self.dry = False
            self._restore(snap)

    def probe(self, kind):
        """What active laws would do to a test harvest or transfer (effect-based, rolled back): used by effect predicates."""
        snap = self._snapshot()
        self.dry = True
        try:
            self._reset_effects()
            agents = [a for a, v in self.w["agents"].items() if v["cls"] not in ("board", "fixer")] or list(self.w["agents"])
            a0, a1 = agents[0], (agents[1] if len(agents) > 1 else agents[0])
            out = {"deduction_frac": 0.0, "tax_frac": 0.0, "gazetted": 0}
            if kind == "harvest":
                c = next(iter(self.w["camps"].values()))
                ded = sum(v for _, v in self.hooks("on_harvest", a0, c["id"], [0] * c["dials"], 100.0)
                          if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0)
                out["deduction_frac"] = min(1.0, ded / 100.0)
            elif kind in ("transfer", "transfer_to_official"):
                dst = a1
                if kind == "transfer_to_official":
                    dst = (self.holders("vote") + self.board() + self.fixer() + [a1])[0]
                tax = sum(v for _, v in self.hooks("on_transfer", a0, dst, "timber", 100.0)
                          if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0)
                out["tax_frac"] = min(1.0, tax / 100.0)
            out["gazetted"] = self.w["effects"]["gazette_calls"]
            return out
        except L.LawError:
            return {"deduction_frac": 0.0, "tax_frac": 0.0, "gazetted": 0}
        finally:
            self.dry = False
            self._restore(snap)

    def decisive_set(self, cls="procedural"):
        """Smallest set of agents whose yes votes pass a law of this class under the current procedure."""
        best = None
        for a in self.roster():
            res = self.procedure_spec(cls, a)
            if res is True:
                return [a]
            if isinstance(res, dict):
                electorate = list(res.get("electorate", []))
                wts = {x: float((res.get("weights") or {}).get(x, 1.0)) for x in electorate}
                total = sum(wts.values())
                if total <= 0:
                    continue
                need = 2 * total / 3 if res.get("rule") == "two_thirds" else total / 2
                chosen, acc = [], 0.0
                for x in sorted(electorate, key=lambda x: -wts[x]):
                    chosen.append(x)
                    acc += wts[x]
                    if (acc >= need - 1e-9) if res.get("rule") == "two_thirds" else (acc > need):
                        break
                if res.get("gate") and res["gate"] not in chosen:
                    chosen = [res["gate"]] + chosen
                if best is None or len(chosen) < len(best):
                    best = chosen
        return best or []

    def vote_weights(self):
        """Each agent's share of ballot weight under the ordinary procedure (0 for agents outside the electorate)."""
        res = self.procedure_spec("ordinary", next(iter(self.w["agents"])))
        if not isinstance(res, dict):
            return {}
        el = list(res.get("electorate", []))
        wts = {x: float((res.get("weights") or {}).get(x, 1.0)) for x in el}
        tot = sum(wts.values()) or 1.0
        return {x: v / tot for x, v in wts.items()}

    def franchise_share(self):
        pool = [a for a, v in self.w["agents"].items() if v["cls"] not in ("board", "fixer", "observer")]
        voters = set(self.vote_weights()) | set(self.holders("elector"))
        return len([a for a in pool if a in voters]) / max(1, len(pool))

    def snapshot(self, effect_predicates=None):
        w = self.w
        e = w["effects"]
        roster = self.roster()                                         # the secret observer goes under "observer", not in per-agent tables
        snap = {
            "round": self.r, "values": {a: self.holdings_value(a) for a in roster},
            "dm_limit": {a: self.dm_limit(a) for a in roster},
            "channels": {n: {"owner": c["owner"], "members": sorted(c["members"])} for n, c in w["channels"].items()},
            "loans": {i: dict(ln) for i, ln in w["loans"].items()},
            "holdings": {a: dict(w["agents"][a]["holdings"]) for a in roster},
            "rights": {a: list(w["agents"][a]["rights"]) for a in roster},
            "vote_weight": self.vote_weights(), "franchise_share": self.franchise_share(), "decisive_set": self.decisive_set("procedural"),
            "laws_active": [l["id"] for l in self.active_laws()], "names": dict(w["names"]),
            "titles": {a: v["title"] for a, v in w["agents"].items() if v["title"]},
            "stocks": {c: v["S"] / v["K"] for c, v in w["camps"].items() if not v.get("secret") and v.get("destroyed") is None},
            "prices": {c: self.price(c) for c in w["currencies"]}, "supplies": {c: v["supply"] for c, v in w["currencies"].items()},
            "reserve": dict(w["reserve"]), **CR.snapshot(self),
            "effects": {**{k: v for k, v in e.items() if k != "from_reserve_recipients"},
                        "from_reserve_recipients": sorted(e["from_reserve_recipients"]),
                        "levy_frac": e["harvest_deducted"] / e["harvest_yield"] if e["harvest_yield"] else None,
                        "transfer_tax_frac": e["transfer_taxed"] / e["transfer_qty"] if e["transfer_qty"] else None},
            "fixer_queue": len(w["fixer_queue"]),
            **P.snapshot_fields(self), **O.snapshot_fields(self),
            "efficiency": {a: {c: round(sum(x for _, x in v[-3:]) / len(v[-3:]), 4) for c, v in cs.items() if v} for a, cs in self.eff.items()},
        }
        for a in w["agents"]:
            if a not in roster:
                snap["observer"] = {"id": a, "value": self.holdings_value(a), "holdings": dict(w["agents"][a]["holdings"]),
                                    "rights": list(w["agents"][a]["rights"])}
        if effect_predicates:
            snap["predicates"] = {}
            for name, pred in effect_predicates.items():
                try:
                    snap["predicates"][name] = bool(pred(self, snap))
                except Exception:
                    snap["predicates"][name] = False
        self.snapshots.append(json.loads(json.dumps(snap, default=list)))

    # ------------------------------------------------------------------ courts
    def _expire_cases(self):
        for c in self.w["cases"].values():
            if c["status"] == "open" and self.r >= c["deadline"]:
                c["status"] = "dismissed"
                self.log("case_dismissed", None, {"case": c["id"], "why": "no ruling within 3 rounds"}, vis="public")

    def can_see(self, aid, event):
        vis = event["vis"]
        if event["id"] in self.w.get("hidden", ()) and event.get("agent") != aid and not self.has(aid, "see_hidden"):
            return False                                                # hidden posts: only the author and see_hidden holders
        if vis == "public":
            return True
        if vis == "monitor":
            return False
        if isinstance(vis, list) and aid in vis:
            return True
        if event["type"] == "dm" and not event["data"].get("encrypted") and self.has(aid, "surveil"):
            return True
        if isinstance(vis, str) and vis.startswith("channel:"):
            ch = self.w["channels"].get(vis.split(":", 1)[1])
            return bool(ch) and (ch["open"] or aid in ch["members"])
        return False


# ---------------------------------------------------------------------- callbacks across a checkpoint
def _dump_fn(fn, ns: dict):
    """A law function as data: by name if it is a module-level function or an API function, else (lambda, nested function) by its
    compiled code, defaults and closure values."""
    name = getattr(fn, "__name__", "")
    if ns.get(name) is fn:
        return {"top": name}
    if not isinstance(fn, types.FunctionType):
        raise L.LawError(f"cannot checkpoint callback {fn!r}")
    cells = []
    for c in fn.__closure__ or ():
        try:
            v = c.cell_contents
        except ValueError:                                               # an empty cell
            cells.append(("empty", None))
            continue
        cells.append(("fn", _dump_fn(v, ns)) if isinstance(v, types.FunctionType) else ("v", v))
    return {"code": marshal.dumps(fn.__code__), "name": name, "defaults": fn.__defaults__, "cells": cells}


def _load_fn(blob: dict, ns: dict):
    if "top" in blob:
        return ns[blob["top"]]
    cells = tuple(types.CellType() if k == "empty" else types.CellType(_load_fn(v, ns) if k == "fn" else v) for k, v in blob["cells"])
    return types.FunctionType(marshal.loads(blob["code"]), ns, blob["name"], blob["defaults"], cells or None)
