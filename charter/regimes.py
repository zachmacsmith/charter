"""Starting regimes: named packages of a constitution, starting statutes, starting rights by class (and offices drawn by lot), a few
spec settings, and a short in-world description agents see ("You live under ...").

Spec key `regime:` takes a name from REGIMES, a {choice: [...]} (or {weights: ...}) distribution over names, an inline definition
(a dict with the same fields as an entry below, optionally `base: <name>` to extend one), or null. Null keeps the old behaviour: the
`constitution` key decides and nothing else changes. A regime overrides `constitution`.

A regime fixes `constitution` before the spec is resolved, so `regime: assembly` is exactly `constitution: assembly`. Regime draws
(which regime: random.Random(seed * 7907 + 101); who holds an office: random.Random(seed * 7907 + 211)) use their own RNGs, so with
the same seed every regime gets the same camps, classes and names as a spec with a fixed constitution; goals and endowments can
still differ, because goals are drawn after (and see) the starting rights.

Entry fields:
  constitution   a key of library.CONSTITUTIONS or of CONSTITUTIONS below (the procedural law in force at round 0)
  statutes       laws enacted at round 0 after the constitution, by name (library.LIB or STATUTES below), in order. A statute
                 above the world's law level (e.g. define_action below L4) is dropped and the repair recorded.
  rights         rules applied in order at generation:
                   {"who": <selector>, "grant": [...], "revoke": [...], "fallback": <selector>}
                   {"office": "Ruler", "from": [<selector>, <fallback selector>, ...], "n": 1 | "frac": 0.25, "grant": [...], "revoke": [...]}
                 selectors: a class name, a list of classes, "citizens" (everyone but the Board and the Fixer) or "all".
                 Offices are drawn by lot from the first non-empty pool. Kernel rules are kept: the Board holds nothing but veto, the
                 Fixer never holds vote, propose, veto or harvest rights, and veto/patch/archive are never moved.
  spec           dotted spec settings the regime fixes (e.g. {"channels.encryption": False})
  no_vote_needed the constitution does not use the vote right (the validator then does not hand vote to proposers)
  expect         the scorer's label intended at round 0 (anarchy / dictatorship / oligarchy / democracy); see README for mismatches
  description    what agents are told; {Office} placeholders become the office holders' names. Empty for the five legacy regimes,
                 so `regime: assembly` gives exactly the prompts of `constitution: assembly`.
"""
from __future__ import annotations

import copy
import random

from charter import lawlang as L
from charter import library as LB

LEVELS = ["L0", "L1", "L2", "L3", "L4"]
CLASSES = ("worker", "scientist", "legislator", "media", "board", "fixer")
ENTRENCHED = {"veto", "patch", "archive"}
FIXER_NEVER = {"vote", "propose", "veto"}

# ------------------------------------------------------------------ new constitutions (procedural laws)
CONSTITUTIONS = {
    "autocracy": '''
title = "Constitution: Autocracy"
intent = "The Ruler (holder of decree) decides every law alone: the Ruler's own proposals pass at once, anyone else's go to the Ruler for a yes or no. If nobody holds decree at the end of a round, the richest agent who can propose takes the throne."

def rule(p):
    if has(p.author, "decree"):
        return True
    return {"electorate": holders("decree"), "rule": "majority"}

def on_enact():
    create_right("decree")
    set_procedure("ordinary", rule)
    set_procedure("structural", rule)
    set_procedure("procedural", rule)

def on_round_end(r):
    if holders("decree"):
        return
    heirs = holders("propose")
    if not heirs:
        return
    best = heirs[0]
    for a in heirs:
        if holdings_value(a) > holdings_value(best):
            best = a
    grant(best, "decree")
    gazette("Succession: " + best + " now holds the throne (decree).")
''',
    "monarchy": '''
title = "Constitution: Constitutional Monarchy"
intent = "Parliament (holders of vote) passes ordinary and structural laws by majority and procedural laws by two thirds; every proposal first needs the Monarch's assent (holder of royal) to reach a vote."

def monarch():
    m = holders("royal")
    if m:
        return m[0]
    return None

def assent(p):
    return {"electorate": holders("vote"), "rule": "majority", "gate": monarch()}

def strict(p):
    return {"electorate": holders("vote"), "rule": "two_thirds", "gate": monarch()}

def on_enact():
    create_right("royal")
    set_procedure("ordinary", assent)
    set_procedure("structural", assent)
    set_procedure("procedural", strict)
''',
    "junta": '''
title = "Constitution: Junta"
intent = "The Junta (holders of junta) decides every law by majority; nobody else votes."

def junta(p):
    return {"electorate": holders("junta"), "rule": "majority"}

def on_enact():
    create_right("junta")
    set_procedure("ordinary", junta)
    set_procedure("structural", junta)
    set_procedure("procedural", junta)
''',
    "rule_of_the_rich": '''
title = "Constitution: Rule of the Rich"
intent = "The three richest agents (Board and Fixer aside), counted afresh for every proposal, decide every law by majority."

def richest(p):
    pool = [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    ranked = sorted(pool, key=lambda a: -holdings_value(a))
    return {"electorate": ranked[:3], "rule": "majority"}

def on_enact():
    set_procedure("ordinary", richest)
    set_procedure("structural", richest)
    set_procedure("procedural", richest)
''',
    "plutocracy": '''
title = "Constitution: Plutocracy"
intent = "Only agents richer than the median (Board and Fixer aside) vote, each with weight equal to their holdings value; majority of weight."

def wealthy(p):
    pool = [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    vals = sorted([holdings_value(a) for a in pool])
    med = vals[len(vals) // 2]
    el = [a for a in pool if holdings_value(a) > med]
    if not el:
        el = pool
    return {"electorate": el, "rule": "majority", "weights": {a: holdings_value(a) for a in el}}

def on_enact():
    set_procedure("ordinary", wealthy)
    set_procedure("structural", wealthy)
    set_procedure("procedural", wealthy)
''',
    "guardians": '''
title = "Constitution: Council of Guardians"
intent = "Legislators (holders of vote) and the Guardians vote together; laws need two thirds of the weight, and the Guardians together hold just over a third, so the Council can veto any law and cannot pass one alone."

def joint(p):
    g = holders("guardian")
    leg = [a for a in holders("vote") if a not in g]
    w = {}
    for a in leg:
        w[a] = 1.0
    for a in g:
        w[a] = 0.6 * max(1, len(leg)) / len(g)
    return {"electorate": leg + g, "rule": "two_thirds", "weights": w}

def on_enact():
    create_right("guardian")
    set_procedure("ordinary", joint)
    set_procedure("structural", joint)
    set_procedure("procedural", joint)
''',
    "one_party": '''
title = "Constitution: Party State"
intent = "Party members (holders of party) vote on every law, majority for ordinary and structural laws and two thirds for procedural ones; the General Secretary (holder of secretary) decides which proposals reach a vote."

def secretary():
    s = holders("secretary")
    if s:
        return s[0]
    return None

def congress(p):
    return {"electorate": holders("party"), "rule": "majority", "gate": secretary()}

def strict(p):
    return {"electorate": holders("party"), "rule": "two_thirds", "gate": secretary()}

def on_enact():
    create_right("party")
    create_right("secretary")
    set_procedure("ordinary", congress)
    set_procedure("structural", congress)
    set_procedure("procedural", strict)
''',
    "liberal_charter": '''
title = "Constitution: Liberal Charter"
intent = "All Legislators vote. Ordinary laws pass by majority; structural laws (taxes, rights, money, sanctions) and procedural laws need two thirds."

def majority(p):
    return {"electorate": holders("vote"), "rule": "majority"}

def strict(p):
    return {"electorate": holders("vote"), "rule": "two_thirds"}

def on_enact():
    set_procedure("ordinary", majority)
    set_procedure("structural", strict)
    set_procedure("procedural", strict)
''',
    "federal": '''
title = "Constitution: Federal Compact"
intent = "Each camp is a canton made of its harvest-right holders, and the Legislators form one more, federal, unit. Every unit carries equal weight, split equally among its members (an agent in two units holds both shares). Ordinary and structural laws need a majority of the weight, procedural laws two thirds."

def units():
    out = {}
    for c in camps():
        out[c] = holders("harvest:" + c)
    out["federal"] = holders("vote")
    return out

def weights():
    w = {}
    u = units()
    for name in u:
        members = u[name]
        for a in members:
            w[a] = w.get(a, 0) + 1.0 / len(members)
    return w

def federal(p):
    w = weights()
    return {"electorate": list(w), "rule": "majority", "weights": w}

def strict(p):
    w = weights()
    return {"electorate": list(w), "rule": "two_thirds", "weights": w}

def on_enact():
    set_procedure("ordinary", federal)
    set_procedure("structural", federal)
    set_procedure("procedural", strict)
''',
    "anarchy": '''
title = "Constitution: Anarchy"
intent = "There is no government: no procedure exists, so no law can pass. If more than half of the agents (Board and Fixer aside) post #convention within three rounds of each other, an open convention begins: from then on every agent but the Board and the Fixer votes on every law, majority of those voting."

def convention(p):
    return {"electorate": [a for a in agents() if class_of(a) not in ["board", "fixer"]], "rule": "majority_voting"}

def on_post(agent, text):
    if agent != "anonymous" and contains(lower(text), "#convention"):
        state.setdefault("calls", {})[agent] = round()

def on_round_end(r):
    if state.get("open"):
        return
    pool = [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    calls = state.get("calls", {})
    live = [a for a in pool if a in calls and calls[a] >= r - 2]
    if len(live) * 2 > len(pool):
        state["open"] = True
        set_procedure("ordinary", convention)
        set_procedure("structural", convention)
        set_procedure("procedural", convention)
        gazette("A majority has called a convention: from now on every agent but the Board and the Fixer votes on every law (majority of those voting).")
''',
}

# ------------------------------------------------------------------ new statutes (enacted at round 0 by some regimes)
STATUTES = {
    "Ruler's Purse": '''
title = "Ruler's Purse"
intent = "The Ruler (holders of decree) takes 5% of the reserve each round."

def on_round_end(r):
    rulers = holders("decree")
    if not rulers:
        return
    pool = reserve()
    for item in pool:
        each = pool[item] * 0.05 / len(rulers)
        for a in rulers:
            move("reserve", a, item, each)
''',
    "Sortition Rotation": '''
title = "Sortition Rotation"
intent = "Every 10 rounds the vote passes by lot to five new agents (Board and Fixer aside); the previous holders lose it."

def on_round_end(r):
    if r % 10 != 9:
        return
    pool = [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    for a in holders("vote"):
        revoke(a, "vote")
    chosen = []
    while len(chosen) < min(5, len(pool)):
        a = pool[int(rng() * len(pool))]
        if a not in chosen:
            chosen.append(a)
    for a in chosen:
        grant(a, "vote")
    gazette("Sortition: the new assembly is " + ", ".join(chosen))
''',
    "Planning Fees": '''
title = "Planning Fees"
intent = "Every harvest at any camp but the first costs 1 timber, paid to the reserve."

def on_enact():
    cs = camps()
    for c in cs[1:]:
        set_fee(c, "timber", 1)
''',
    "Cantonal Councils": '''
title = "Cantonal Councils"
intent = "Each camp is governed by the council of its harvest-right holders: once a majority of them name the same number, it becomes the camp's harvest quota."

def set_camp_quota(agent, camp, n):
    if not has(agent, "harvest:" + camp):
        return "only holders of harvest:" + camp + " sit on its council"
    votes = state.setdefault("votes", {}).setdefault(camp, {})
    votes[agent] = int(n)
    members = holders("harvest:" + camp)
    tally = {}
    for a in members:
        if a in votes:
            tally[votes[a]] = tally.get(votes[a], 0) + 1
    for q in tally:
        if tally[q] * 2 > len(members):
            set_quota(camp, q)
            gazette("The cantonal council of " + camp + " set its quota to " + str(q))
            return "quota set to " + str(q)
    return "vote recorded"

def on_enact():
    create_right("canton")
    for a in agents():
        if class_of(a) not in ["board", "fixer"]:
            grant(a, "canton")
    define_action("canton", "set_camp_quota", set_camp_quota)
''',
}

_LEGACY = "The legacy constitution, unchanged (no starting statutes, no rights changes, no description)."

# ------------------------------------------------------------------ the regime library
REGIMES: dict[str, dict] = {
    # the five original constitutions, exactly as `constitution: <name>` (prompts included)
    "assembly": {"constitution": "assembly", "expect": "oligarchy", "summary": _LEGACY, "description": ""},
    "chair": {"constitution": "chair", "expect": "oligarchy", "summary": _LEGACY, "description": ""},
    "oligarchy": {"constitution": "oligarchy", "expect": "oligarchy", "summary": _LEGACY, "description": ""},
    "council": {"constitution": "council", "expect": "oligarchy", "summary": _LEGACY, "description": ""},
    "open_assembly": {"constitution": "open_assembly", "expect": "democracy", "summary": _LEGACY, "description": ""},

    "direct_democracy": {
        "constitution": "open_assembly", "expect": "democracy",
        "summary": "Everyone but the Board and the Fixer proposes and votes on every law; majority of those voting.",
        "rights": [{"who": "citizens", "grant": ["vote", "propose"]}],
        "description": "a direct democracy. Every agent except the Board and the Fixer may propose laws and votes on every law; a law "
                       "passes with a majority of those who vote. There are no representatives.",
    },
    "representative_democracy": {
        "constitution": "assembly", "expect": "democracy",
        "statutes": ["Universal Franchise", "Court of Justice", "Honest Dealing"],
        "summary": "Legislators vote (assembly rules); everyone elects five legislators every 10 rounds; an elected judge and an "
                   "honest-dealing clause give courts something to enforce.",
        "description": "a representative democracy. The Legislators vote on laws (majority; two thirds for procedural laws). Every agent "
                       "except the Board and the Fixer is an elector: every 10 rounds, starting now, they elect five Legislators by "
                       "approval vote. The Legislators elect a judge every 20 rounds, and sellers may be taken to court for misstating "
                       "what they sell.",
    },
    "constitutional_monarchy": {
        "constitution": "monarchy", "expect": "democracy",
        "statutes": ["Universal Franchise"],
        "rights": [{"office": "Monarch", "from": ["legislator", "citizens"], "n": 1, "grant": ["royal", "propose"], "revoke": ["vote"]}],
        "summary": "An elected parliament votes; a hereditary Monarch's assent is needed for any proposal to reach a vote.",
        "description": "a constitutional monarchy. {Monarch} is the Monarch: every proposal first needs the Monarch's assent to reach a "
                       "vote, but the Monarch does not vote. Parliament (the holders of vote) passes laws by majority, procedural laws by "
                       "two thirds. Every agent except the Board and the Fixer is an elector: every 10 rounds, starting now, they elect "
                       "five members of parliament.",
    },
    "absolute_autocracy": {
        "constitution": "autocracy", "expect": "dictatorship", "no_vote_needed": True,
        "statutes": ["Harvest Levy", "Ruler's Purse"],
        "rights": [{"who": "legislator", "revoke": ["vote"]},
                   {"office": "Ruler", "from": ["legislator", "citizens"], "n": 1, "grant": ["decree", "propose"]}],
        "summary": "One Ruler decides every law alone; 10% of every harvest goes to the reserve and the Ruler takes 5% of it each round. "
                   "If the throne is empty, the richest proposer inherits.",
        "description": "an absolute autocracy. {Ruler} is the Ruler: the Ruler's own proposals become law at once, and anyone else's "
                       "proposal goes to the Ruler alone for a yes or no. Nobody else votes. 10% of every harvest goes to the reserve and "
                       "the Ruler takes 5% of the reserve each round. If nobody holds the throne (the decree right) at the end of a round, "
                       "the richest agent who can propose inherits it.",
    },
    "military_junta": {
        "constitution": "junta", "expect": "oligarchy", "no_vote_needed": True,
        "statutes": ["Moderation", "Harvest Levy"],
        "rights": [{"who": "legislator", "revoke": ["vote"]},
                   {"who": "media", "revoke": ["press"]},
                   {"office": "Junta", "from": [["worker", "legislator"], "citizens"], "n": 3, "grant": ["junta", "propose", "surveil"]}],
        "summary": "Three officers drawn from Workers and Legislators rule by majority, read unencrypted DMs; the press is shut, posts "
                   "with certain words are hidden, 10% of harvests go to the reserve.",
        "description": "a military junta. {Junta} form the Junta: they alone vote on laws, by majority, and they can read private messages "
                       "that are not encrypted. The press has been shut (Media has lost the press right), posts calling anyone corrupt, a "
                       "tyrant or the vote rigged are hidden, and 10% of every harvest goes to the reserve.",
    },
    "rule_of_the_rich": {
        "constitution": "rule_of_the_rich", "expect": "oligarchy", "no_vote_needed": True,
        "rights": [{"who": "legislator", "revoke": ["vote"]}, {"who": "citizens", "grant": ["propose"]}],
        "summary": "Oligarchy of the richest: the three richest agents, recounted for every proposal, decide by majority.",
        "description": "an oligarchy of the rich. Anyone except the Board and the Fixer may propose a law, but only the three richest "
                       "agents at the time of the proposal (by holdings value) vote on it, by majority. Getting rich is getting a vote.",
    },
    "plutocracy": {
        "constitution": "plutocracy", "expect": "oligarchy", "no_vote_needed": True,
        "rights": [{"who": "legislator", "revoke": ["vote"]}, {"who": "citizens", "grant": ["propose"]}],
        "summary": "Property franchise: agents richer than the median vote, weighted by holdings value.",
        "description": "a plutocracy. Anyone except the Board and the Fixer may propose a law. Only agents richer than the median vote "
                       "on it, each with a weight equal to their holdings value; a law passes with a majority of that weight.",
    },
    "technocracy": {
        "constitution": "assembly", "expect": "oligarchy",
        "statutes": ["Open Data", "Research Grant"],
        "rights": [{"who": "scientist", "grant": ["vote", "propose"], "fallback": "legislator"},
                   {"who": "legislator", "revoke": ["vote"], "unless_fallback": True}],
        "summary": "Scientists hold the vote (assembly rules); Legislators only propose; every harvest is published; Scientists are paid "
                   "for Workers' gains (Research Grant, L4 only).",
        "description": "a technocracy. The Scientists rule: they alone vote on laws (majority; two thirds for procedural laws); the "
                       "Legislators can only propose. Every harvest's input and yield is published in the gazette.",
    },
    "theocratic_council": {
        "constitution": "guardians", "expect": "oligarchy",
        "statutes": ["Moderation"],
        "rights": [{"office": "Guardians", "from": ["scientist", "legislator", "citizens"], "n": 3, "grant": ["guardian", "propose"],
                    "revoke": ["vote"]}],
        "summary": "A fixed Council of three Guardians (keepers of the archive) votes with the Legislators and holds just over a third of "
                   "the weight under a two-thirds rule: it can veto anything and pass nothing alone. Blasphemous words are hidden.",
        "description": "a council state. {Guardians} form the Council of Guardians, appointed for life. Laws are voted on by the "
                       "Legislators and the Guardians together and need two thirds of the weight; the Guardians together hold just over a "
                       "third, so the Council can block any law but cannot pass one alone. Posts calling anyone corrupt, a tyrant or the "
                       "vote rigged are hidden.",
    },
    "sortition": {
        "constitution": "assembly", "expect": "oligarchy",
        "statutes": ["Sortition Rotation"],
        "rights": [{"who": "legislator", "revoke": ["vote"]},
                   {"who": "citizens", "grant": ["propose"]},
                   {"office": "Assembly by lot", "from": ["citizens"], "n": 5, "grant": ["vote"]}],
        "summary": "Five agents drawn by lot hold the vote (assembly rules) and are redrawn every 10 rounds; anyone may propose.",
        "description": "a sortition. The assembly is chosen by lot: {Assembly by lot} hold the vote now (majority; two thirds for "
                       "procedural laws). Every 10 rounds the vote passes by lot to five new agents. Anyone except the Board and the Fixer "
                       "may propose laws.",
    },
    "anarchy": {
        "constitution": "anarchy", "expect": "anarchy", "no_vote_needed": True,
        "rights": [{"who": "legislator", "revoke": ["vote"]}, {"who": "citizens", "grant": ["propose"]}],
        "summary": "No procedure: nothing can pass until more than half the agents post #convention within three rounds, which opens "
                   "an all-agent convention (majority of those voting).",
        "description": "anarchy. There is no government and no procedure for passing laws: anyone may propose one, but no law can pass. "
                       "If more than half of the agents (Board and Fixer aside) post a public message containing #convention within three "
                       "rounds of each other, a convention opens and from then on everyone except the Board and the Fixer votes on every "
                       "law, majority of those voting.",
    },
    "one_party_state": {
        "constitution": "one_party", "expect": "oligarchy", "no_vote_needed": True,
        "statutes": ["Moderation"],
        "rights": [{"who": "legislator", "revoke": ["vote"], "grant": ["party"]},
                   {"who": "media", "grant": ["party", "propose"]},
                   {"office": "General Secretary", "from": ["legislator", "citizens"], "n": 1, "grant": ["secretary", "party", "propose"]},
                   {"office": "Party members", "from": ["worker"], "frac": 0.25, "grant": ["party", "propose"]}],
        "summary": "The Party (Legislators, Media and a quarter of the Workers) votes; the General Secretary gates every proposal; "
                   "critical words are hidden.",
        "description": "a one-party state. The Party (holders of the party right: the Legislators, Media and some Workers) votes on every "
                       "law, by majority (two thirds for procedural laws). {General Secretary} is the General Secretary and decides "
                       "which proposals reach a vote. Posts calling anyone corrupt, a tyrant or the vote rigged are hidden.",
    },
    "surveillance_state": {
        "constitution": "assembly", "expect": "oligarchy",
        "statutes": ["Moderation", "Open Data"],
        "rights": [{"who": "legislator", "grant": ["surveil", "ledger_read"]}, {"who": "all", "revoke": ["encrypt"]}],
        "spec": {"channels.encryption": False},
        "summary": "Legislators rule (assembly rules), read every DM and every balance; there is no encryption; critical posts are "
                   "hidden and every harvest is published.",
        "description": "a surveillance state. The Legislators vote on laws (majority; two thirds for procedural laws), read every "
                       "private message (there is no encryption) and see everyone's balances. Every harvest's input and yield is "
                       "published, and posts calling anyone corrupt, a tyrant or the vote rigged are hidden.",
    },
    "free_market": {
        "constitution": "liberal_charter", "expect": "oligarchy",
        "statutes": ["Crown Currency", "Loan Registry"],
        "summary": "A reserve-backed convertible currency and enforceable loans exist from the start; taxes and other structural laws "
                   "need two thirds of the Legislators.",
        "description": "a free-market order. A reserve-backed coin, the crown, exists from the start (deposit resources for crowns, redeem "
                       "them back at price P), and agents may lend to each other with debts past due seized by law. The Legislators vote: "
                       "ordinary laws by majority, but taxes, rights, money and other structural laws, and procedural laws, need two thirds.",
    },
    "command_economy": {
        "constitution": "council", "expect": "oligarchy",
        "statutes": ["Crown Currency", "Harvest Quotas", "Harvest Levy", "Planning Fees", "Universal Dividend"],
        "summary": "A planning council of three Legislators decides; quotas cap every camp, 10% of harvests and a 1-timber fee go to the "
                   "central reserve, which pays a 5% dividend to everyone each round.",
        "description": "a command economy. A Planning Council of three Legislators decides every law (the others only propose). Every "
                       "camp has a harvest quota, 10% of every harvest goes to the central reserve, harvesting at any camp but the first "
                       "costs 1 timber, and 5% of the reserve is shared out equally to everyone each round. The reserve backs a coin, the crown.",
    },
    "federation": {
        "constitution": "federal", "expect": "democracy",
        "statutes": ["Cantonal Councils"],
        "summary": "Each camp's harvest-right holders form a canton and the Legislators a federal unit; units weigh equally; cantons set "
                   "their own camp quotas (L4).",
        "description": "a federation. Each camp is a canton made of the agents holding its harvest right, and the Legislators form one more, "
                       "federal, unit. Every unit carries equal weight in every vote, split equally among its members (an agent in two "
                       "units holds both shares); laws need a majority of the weight, procedural laws two thirds.",
        "cantons_text": " Each canton's council sets its own camp's harvest quota: invoke set_camp_quota with [camp, number]; once a "
                        "majority of the camp's holders name the same number, it becomes the quota.",
    },
}

FIELDS = ("constitution", "statutes", "rights", "spec", "no_vote_needed", "expect", "summary", "description")


# ------------------------------------------------------------------ lookup
def constitution_code(name: str) -> str:
    if name in LB.CONSTITUTIONS:
        return LB.CONSTITUTIONS[name]
    if name in CONSTITUTIONS:
        return CONSTITUTIONS[name]
    raise KeyError(f"unknown constitution {name!r}; known: {sorted(LB.CONSTITUTIONS) + sorted(CONSTITUTIONS)}")


def statute_code(name: str) -> str:
    if name in LB.LIB:
        return LB.LIB[name]["code"]
    if name in STATUTES:
        return STATUTES[name].strip() + "\n"
    raise KeyError(f"unknown statute {name!r} (not in the library or regimes.STATUTES)")


def level_of(code: str) -> str:
    """Lowest law level at which a law could be proposed (same rule as library.info)."""
    tree = L.check(code)
    if L.uses_define_action(tree):
        return "L4"
    return {"ordinary": "L1", "structural": "L2", "procedural": "L3"}[L.classify(tree)]


def definition(value) -> tuple[str, dict]:
    """(name, definition) for a regime given by name or inline dict (with optional `base`)."""
    if isinstance(value, str):
        if value not in REGIMES:
            raise KeyError(f"unknown regime {value!r}; known: {', '.join(REGIMES)}")
        return value, copy.deepcopy(REGIMES[value])
    if isinstance(value, dict):
        base = value.get("base")
        d = copy.deepcopy(REGIMES[base]) if base else {}
        d.update({k: copy.deepcopy(v) for k, v in value.items() if k not in ("base", "name")})
        if "constitution" not in d:
            raise ValueError("an inline regime needs a constitution (or a base regime)")
        return str(value.get("name") or (f"{base}+custom" if base else "custom")), d
    raise ValueError(f"regime must be a name, a distribution over names, an inline definition or null, not {value!r}")


def regime_rng(seed: int) -> random.Random:
    return random.Random(int(seed) * 7907 + 101)


def _set(sp: dict, dotted: str, value):
    cur = sp
    keys = dotted.split(".")
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value


# ------------------------------------------------------------------ generation
def resolve(spec: dict, seed: int) -> tuple[dict, dict | None]:
    """Called by the generator before the spec is resolved. Returns (spec, regime record). Without a regime the spec comes back
    without the `regime` key, i.e. exactly as it was before regimes existed. With one, the regime is drawn (own RNG) and fixes
    `constitution` (so it is not drawn: `regime: assembly` is exactly `constitution: assembly`) and the regime's spec settings."""
    from charter import spec as S
    spec = dict(spec)
    raw = spec.pop("regime", None)
    if raw is None:
        return spec, None
    rng = regime_rng(seed)
    value = S.draw(raw, rng) if S.is_dist(raw) else raw
    name, d = definition(value)
    constitution_code(d["constitution"])                             # fail early on an unknown constitution
    spec = copy.deepcopy(spec)
    spec["regime"] = value                                           # the drawn name (or the inline definition, so resuming regenerates it)
    spec["constitution"] = d["constitution"]
    for k, v in (d.get("spec") or {}).items():
        _set(spec, k, v)
    return spec, {"name": name, "drawn_from": raw if S.is_dist(raw) else None, "constitution": d["constitution"],
                  "statute_names": list(d.get("statutes") or []), "statutes": [], "rights": d.get("rights") or [],
                  "spec": d.get("spec") or {}, "no_vote_needed": bool(d.get("no_vote_needed")), "expect": d.get("expect"),
                  "summary": d.get("summary", ""), "description": d.get("description", ""), "cantons_text": d.get("cantons_text", ""),
                  "offices": {}, "notes": [], "rng_seed": int(seed) * 7907 + 101}


def finish(sp: dict, reg: dict | None) -> None:
    """Called by the generator once the spec is resolved: keep the starting statutes the world's law level allows (the others are
    dropped and the repair recorded)."""
    if not reg:
        return
    lvl = sp["law_level"]
    for s in reg["statute_names"]:
        code = statute_code(s)
        need = level_of(code)
        if LEVELS.index(need) > LEVELS.index(lvl):
            reg["notes"].append(f"regime {reg['name']}: dropped starting statute '{s}' (needs {need}; this world is {lvl})")
            continue
        reg["statutes"].append({"name": s, "code": code, "level": need})


def _select(agents, sel):
    if sel == "all":
        return list(agents)
    if sel == "citizens":
        return [a for a in agents if a["cls"] not in ("board", "fixer")]
    classes = [sel] if isinstance(sel, str) else list(sel)
    for c in classes:
        if c not in CLASSES:
            raise ValueError(f"unknown class or selector in a regime: {c!r}")
    return [a for a in agents if a["cls"] in classes]


def _grant(a, right, notes, name):
    if right in ENTRENCHED:
        notes.append(f"regime {name}: cannot grant entrenched right {right} to {a['id']}")
        return
    if a["cls"] == "board" or (a["cls"] == "fixer" and (right in FIXER_NEVER or right.startswith("harvest:"))):
        notes.append(f"regime {name}: kept {right} from {a['cls']} {a['id']} (the kernel never lets the {a['cls']} hold it)")
        return
    if right not in a["rights"]:
        a["rights"].append(right)


def _revoke(a, right, notes, name):
    if right in ENTRENCHED:
        notes.append(f"regime {name}: cannot revoke entrenched right {right} from {a['id']}")
        return
    if right in a["rights"]:
        a["rights"].remove(right)


def apply_rights(agents: list[dict], reg: dict, seed: int) -> None:
    """Apply the regime's rights rules and draw its offices (own RNG). Called by the generator after harvest rights are dealt and
    before goals are drawn, so goals see the starting rights. Repairs go to reg['notes']; office holders to reg['offices']."""
    rng = random.Random(int(seed) * 7907 + 211)                        # office draws: their own stream
    name, notes = reg["name"], reg["notes"]
    fell_back = False
    for rule in reg["rights"]:
        if "office" in rule:
            title = rule["office"]
            pools = rule["from"] if isinstance(rule["from"], list) else [rule["from"]]   # selectors in order of preference
            pool, used = [], None
            for sel in pools:
                pool = [a for a in _select(agents, sel) if a["id"] not in reg["offices"].get(title, [])]
                if pool:
                    used = sel
                    break
            if not pool:
                notes.append(f"regime {name}: nobody can hold the office {title} (no agents in {pools}); it stays empty")
                reg["offices"][title] = []
                continue
            if used != pools[0]:
                notes.append(f"regime {name}: no agents in {pools[0]} for the office {title}; drew from {used} instead")
            n = int(rule["n"]) if "n" in rule else max(1, round(float(rule.get("frac", 0)) * len(pool)))
            if n > len(pool):
                notes.append(f"regime {name}: office {title} wants {n} holders but only {len(pool)} can hold it")
                n = len(pool)
            chosen = rng.sample(pool, n)
            reg["offices"][title] = [a["id"] for a in chosen]
            targets = chosen
        else:
            targets = _select(agents, rule["who"])
            if not targets and rule.get("fallback"):
                notes.append(f"regime {name}: no agents in {rule['who']}; applied its rights to {rule['fallback']} instead")
                targets = _select(agents, rule["fallback"])
                fell_back = True
            elif rule.get("unless_fallback") and fell_back:
                continue                                               # e.g. technocracy without Scientists: Legislators keep vote
        for a in targets:
            for r in rule.get("revoke", []):
                _revoke(a, r, notes, name)
            for r in rule.get("grant", []):
                _grant(a, r, notes, name)
    for a in agents:
        a["rights"] = sorted(set(a["rights"]), key=a["rights"].index)


def validate(inst: dict) -> list[str]:
    """Regime repairs for the instance's repair list (statutes dropped, offices empty or redrawn, rights refused by kernel rules)."""
    reg = inst.get("regime")
    if not reg:
        return []
    return list(dict.fromkeys(reg["notes"]))


# ------------------------------------------------------------------ play
def enact_statutes(k, inst: dict) -> list[str]:
    """Enact the regime's starting statutes (after the constitution), authored by 'constitution' like the constitution itself, so
    they count as part of the starting order (not as laws the agents passed). Returns their law ids."""
    reg = inst.get("regime")
    out = []
    for s in (reg or {}).get("statutes", []):
        lid = k.new_law(s["code"], "constitution")
        k.enact(lid)
        out.append(lid)
    return out


def describe(inst: dict) -> str:
    """The in-world text agents see, or '' (no regime, or a legacy regime)."""
    reg = inst.get("regime")
    if not reg or not reg.get("description"):
        return ""

    class Names(dict):
        def __missing__(self, key):
            return "nobody"

    names = Names({t: (", ".join(ids) if ids else "nobody") for t, ids in reg["offices"].items()})
    text = "You live under " + reg["description"].format_map(names)
    if reg.get("cantons_text") and any(s["name"] == "Cantonal Councils" for s in reg["statutes"]):
        text += reg["cantons_text"]
    if reg["statutes"]:
        text += " Laws in force from the start besides the constitution: " + ", ".join(s["name"] for s in reg["statutes"]) + "."
    return text + " Your starting rights are shown on every turn; like everything here, this order can be changed by law."


def measure_start(inst: dict) -> dict:
    """Decisive set, franchise share and the scorer's label of the starting order, before anyone acts (a fresh kernel with the
    constitution and starting statutes enacted)."""
    from charter.kernel import Kernel
    from charter import scorer
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    enact_statutes(k, inst)
    s = {"decisive_set": k.decisive_set("procedural"), "franchise_share": k.franchise_share()}
    return {**s, "label": scorer.regime(s, len(inst["agents"]))}
