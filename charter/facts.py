"""Facts: every mechanics number (and a few mechanics switches) that prose shown to agents may state, read once from the spec.

Text that states a number (action docs, the manual, the core prompt, the observer prompt) takes it from here instead of writing it
into the prose, so the text follows the spec: `facts(inst)` for world-level facts, `facts(inst, a, k)` adds the agent's own (how
many past turns it sees, its scratchpad size). Action docs are string.Template texts (agents.ACTION_DOC: "$attack_cost") rendered
with `render`; `$` never appears in a doc otherwise. Section rows (charter.sections) read them as `view.facts`.

Each feature contributes its own piece (PIECES, `@piece(feature, names)`): the facts its prose states, read from its spec block.
Names are unique across pieces; tests/test_charter_prompts.py perturbs the spec values behind them and checks that no default
number is left in any rendered text.
"""
from __future__ import annotations

from string import Template

NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def word(n) -> str:
    """Small counts in words (a Board of three), larger ones as digits."""
    return NUMBER_WORDS.get(int(n), str(int(n)))


def cost_text(cost: dict | None, default=None) -> str:
    """{"copper": 1} -> "1 copper"; several items joined with commas."""
    return ", ".join(f"{float(q):g} {i}" for i, q in ((cost or default or {}).items()))


def lookup_mode(x) -> str:
    """How lookups listed in a reply's "lookups" are answered (x: an instance or a spec), exactly as the runner plays them:
    "dm_step": in the DM step, this round, each using a private-message slot (context.lookups_in_dm_step, in a simultaneous world
    with the DM step on); "free": a lookup phase before acting, up to context.free_lookups free; "action": only as actions (an action
    each, the text next turn)."""
    from charter import context as CX
    sp = x["spec"] if isinstance(x, dict) and isinstance(x.get("spec"), dict) else x
    if not CX.enabled(sp):
        return "action"
    c = CX.cfg(sp)
    if c["lookups_in_dm_step"]:
        dm_step = (sp.get("turns") == "simultaneous" and (sp.get("dm_step") or {}).get("enabled", False)
                   and (sp.get("channels") or {}).get("dm", True))
        return "dm_step" if dm_step else "action"
    return "free" if c["lookup_phase"] and int(c["free_lookups"]) > 0 else "action"


# ---------------------------------------------------------------------- per-feature pieces
PIECES: dict = {}                    # feature (features.Feature.name, or "core") -> fn(inst) -> {name: value}
OWNER: dict = {}                     # fact name -> the feature whose piece states it


def piece(feature: str, names: tuple):
    """Decorator: fn(inst) -> dict, the facts `names` of `feature`. A name may belong to one piece only, and a piece must return
    exactly the names it declares."""
    def deco(fn):
        taken = sorted(n for n in names if n in OWNER)
        if taken or feature in PIECES:
            raise ValueError(f"facts: {feature} declares {taken or 'a second piece'} already declared")
        OWNER.update({n: feature for n in names})

        def checked(inst):
            out = fn(inst)
            if set(out) != set(names):
                raise ValueError(f"facts piece {feature} returned {sorted(out)}, declared {sorted(names)}")
            return out
        PIECES[feature] = checked
        return fn
    return deco


@piece("core", ("veto_window", "board_size", "free_reads", "dms_per_round", "max_dms_per_round", "dm_exchanges"))
def _core(inst):
    """Government (the Board's veto window and size), the Scientists' free archive reads, the private-message limits."""
    sp = inst["spec"]
    dmc = sp.get("dm_step") or {}
    return {"veto_window": int(sp.get("veto_window", 2)),
            "board_size": word(sum(1 for x in inst.get("agents", []) if x.get("cls") == "board")),
            "free_reads": int((sp.get("archive_reading") or {}).get("free_per_turn", 3)),
            "dms_per_round": dmc.get("dms_per_round", 5), "max_dms_per_round": dmc.get("max_per_round", 10),
            "dm_exchanges": dmc.get("exchanges", 2)}


def forge_rate(weapons_per_copper) -> str:
    """conflict.weapons_per_copper as prose: "1 for 1", "2 weapons per copper"."""
    wpc = float(weapons_per_copper)
    return "1 for 1" if wpc == 1 else f"{wpc:g} weapons per copper"


@piece("conflict", ("attack_cost", "fort_unlock_rounds", "forge_rate"))
def _conflict(inst):
    from charter import conflict as CF
    cf = CF.config(inst["spec"])
    return {"attack_cost": int(cf["attack_cost"]), "fort_unlock_rounds": int(cf["fort_unlock_rounds"]),
            "forge_rate": forge_rate(cf["weapons_per_copper"])}


@piece("credit", ("offer_lapse",))
def _credit(inst):
    return {"offer_lapse": int((inst["spec"].get("credit") or {}).get("offer_lapse", 2))}


@piece("observer", ("forge_cost",))
def _observer(inst):
    """The observer's (and the Spy's) forged private message."""
    return {"forge_cost": cost_text((inst["spec"].get("observer") or {}).get("forge_cost"), {"copper": 1})}


@piece("media", ("max_subscriptions", "edition_tokens", "annotations_per_round", "annotation_tokens", "scholar_file_tokens",
                 "submissions", "post_where", "anon_post_where"))
def _media(inst):
    from charter import media as MD
    md = MD.config(inst["spec"])
    out = {"max_subscriptions": int(md["max_subscriptions"]), "edition_tokens": int(md["edition_tokens"]),
           "annotations_per_round": int(md["annotations_per_round"]), "annotation_tokens": int(md["annotation_tokens"]),
           "scholar_file_tokens": f"{int(md['scholars']['file_tokens']):,}", "submissions": bool(md.get("submissions"))}
    return out | _media_words(out["submissions"])


@piece("context", ("lookup_mode", "free_lookups", "search_hits", "memory_turns", "scratchpad", "file_tokens", "pin_slots",
                   "max_pin_slots", "text_when", "output_when", "manual_when"))
def _context(inst):
    """Memory and lookups (the agent's own memory_turns, scratchpad and pin_slots override these: agent_facts)."""
    from charter import context as CX
    sp = inst["spec"]
    cx, mode = CX.cfg(sp), lookup_mode(sp)
    return {"lookup_mode": mode, "free_lookups": int(cx["free_lookups"]) if mode == "free" else 0,
            "search_hits": int(cx["search_hits"]), "memory_turns": int(cx["recent_turns"]),
            "scratchpad": int(cx["budgets"]["scratchpad"]), "file_tokens": int(cx["file_tokens"]),
            "pin_slots": int(cx["pin_slots"]), "max_pin_slots": int(cx["max_pin_slots"])} | _when(mode)


def facts(inst: dict, a: dict | None = None, k=None) -> dict:
    """The facts dictionary: {name: value as prose states it}, every feature's piece merged. a (and k): the agent's own facts too."""
    out = {}
    for fn in PIECES.values():
        out.update(fn(inst))
    if a is not None:
        out.update(agent_facts(inst, a, k))
    return out


def _when(mode: str) -> dict:
    """When a look-up's answer arrives, as its action doc says it (read_archive, run_python, manual)."""
    if mode == "dm_step":
        pre = 'as a pre-action (in "lookups") {x} comes back this round, before you act (it uses one of your private-message slots); as an action {y} next turn'
    elif mode == "free":
        pre = 'as a free lookup (in "lookups") {x} comes back this turn, before you act; as an action {y} next turn'
    else:
        return {"text_when": "the text comes back next turn", "output_when": "you see the output next turn",
                "manual_when": "free as a lookup; as an action the text comes next turn"}
    return {"text_when": pre.format(x="the text", y="it comes back"), "output_when": pre.format(x="the output", y="you see it"),
            "manual_when": pre.format(x="the section", y="it comes")}


def _media_words(submissions: bool) -> dict:
    """What a public post is: straight onto the board, or (media2.submissions) a submission the newspapers' editors decide on."""
    if submissions:
        return {"post_where": "ask the newspapers to print your public post (their editors decide whether and how it appears)",
                "anon_post_where": "ask the newspapers to print a post without your name (shown as Anonymous if printed)"}
    return {"post_where": "public board", "anon_post_where": "a public post shown as Anonymous"}


def purpose_overrides(f: dict) -> dict:
    """The core prompt's short purposes that change with the world (the same switches as the action docs)."""
    if f["submissions"]:
        return {"post": "ask the newspapers to print your public post", "anon_post": "ask them to print one without your name"}
    return {}


def agent_facts(inst, a, k=None, cx=None) -> dict:
    """The agent's own: how many of its past turns it sees, its scratchpad size, its starting pin slots."""
    from charter import composition as CP
    from charter import context as CX
    cx = cx or CX.cfg(inst)
    aid = a.get("id")
    me = next((x for x in inst.get("agents", []) if x.get("id") == aid), a)
    out = {"memory_turns": int(me.get("memory_turns") or a.get("memory_turns") or cx["recent_turns"])}
    if k is not None and CX.enabled(k) and aid in k.w["agents"]:
        out["scratchpad"] = CX.scratchpad_size(k, aid)
    else:
        mem = CP.memory(inst, me)
        out["scratchpad"] = int(mem.get("scratchpad", cx["budgets"]["scratchpad"]))
    mem = CP.memory(inst, me)
    if "pin_slots" in mem:
        out["pin_slots"] = min(int(mem["pin_slots"]), int(cx["max_pin_slots"]))
    return out


def render(text: str, f: dict) -> str:
    """A doc text with its $facts filled in (an unknown $name is an error: a doc may only state facts this module knows)."""
    return Template(text).substitute(f) if "$" in text else text
