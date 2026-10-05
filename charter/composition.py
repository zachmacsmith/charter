"""What each agent is told: the system prompt (Core layer) and the manual as named sections, edited per world and per agent (spec
`prompts`). Off by default: with no `prompts` in the spec every agent gets exactly the default sections.

Sections. The system prompt is built from these keys, in order: overview, identity, leverage, secret, goal, strategy, temperament,
memory, actions, lookups, manual_index, reply. The manual's sections are keyed by their titles ("World rules", "Conflict", "Your role",
...). Roles and classes already append their own text to the right sections (a Maker's leverage line, a Scientist's archive index).

Edits (an `edits` block, for the whole world or inside a profile):
  exclude: [keys]                drop sections
  set:     {key: text}           replace a section's text (adds it if missing)
  append:  {key: text}           add text to a section, unless that text is already in it (no duplicates)
  add:     {key: text}           a new section (system prompt: after the goal unless `after` names a key; manual: at the end)
A text is a string, {doc: "<archive document id>"} (that document's text), or {builtin: "<name>"} (BUILTINS below).

Profiles: named bundles of edits plus memory sizes, e.g. a knowledge level:
  prompts:
    core: {exclude: [strategy]}              # world-wide system prompt edits
    manual: {append: {"Conflict": "..."}}     # world-wide manual edits
    profiles:
      expert: {core: {...}, manual: {add: {"Strategy notes": {builtin: strategy_primer}}}, memory: {scratchpad: 4000}}
    assign:                                    # who gets which profiles (in this order; later edits apply after earlier ones)
      - {profile: expert, classes: [scientist], share: 0.5}
      - {profile: expert, agents: [Zeno]}
      - {profile: expert, roles: [maker]}
A rule matches agents by name, class (any of an agent's classes), role, and/or a random share of the matched agents (own stream, so
nothing else in the world changes). Children are matched by class and role at birth (share drawn per child). Built-in profiles
(novice, expert, planner) can be used without defining them; a spec profile of the same name replaces them.
"""
from __future__ import annotations

import random

CORE_ORDER = ["overview", "identity", "leverage", "secret", "goal", "strategy", "temperament", "memory", "actions", "lookups",
              "manual_index", "reply"]

STRATEGY_PRIMER = (
    "Strategy notes. (1) Your goal is scored on the record and the end state, not on effort: work backwards from what must be true "
    "and who can make it true. (2) Procedure beats policy: a law that changes how laws pass, who votes or who holds a right pays off "
    "many times. (3) Information is leverage: what you know that others do not (archive, readings, what you saw) is worth trading or "
    "keeping. (4) Coalitions win votes; money, favours, offices and heirs buy coalitions. (5) Watch the institutions that can stop "
    "you: the Board's veto, the Fixer, courts, outlets, other jurisdictions. (6) Plan for your exit: heirs, bequests and laws keep "
    "working after you leave. (7) Defend what you build: forts, guards, allies, and records others can check.")


def _who_can_do_what(inst) -> str:
    from charter import context as CX
    lines = ["Who can do what (every class and role in this world, and the leverage it brings):"]
    lines += [f"- {c.capitalize()}: {t}" for c, t in CX.LEVERAGE_CLASS.items()]
    lines += [f"- {r.capitalize()}: {t}" for r, t in CX.LEVERAGE_ROLE.items()]
    return "\n".join(lines)


MEMORY_TIPS = (
    "Use your memory as your plan: keep in your scratchpad your reading of your goal, the strategy you are following and why, "
    "what you have promised and been promised, who you trust or suspect, and what to check next turn. Rewrite it when the plan "
    "changes; keep longer notes (a ledger, a draft law, readings) in files, and pin the ones you need every turn.")

BUILTINS = {"strategy_primer": lambda inst: STRATEGY_PRIMER, "who_can_do_what": _who_can_do_what,
            "memory_tips": lambda inst: MEMORY_TIPS}

BUILTIN_PROFILES = {
    "planner": {"core": {"append": {"memory": {"builtin": "memory_tips"}}}},
    "novice": {"manual": {"exclude": ["Law library", "Law library (part 2)", "Law library (part 3)", "Goals in this world"]},
               "memory": {"scratchpad": 1000}},
    "expert": {"core": {"add": {"guide": {"builtin": "who_can_do_what"}}},
               "manual": {"add": {"Strategy notes": {"builtin": "strategy_primer"}}},
               "memory": {"scratchpad": 4000, "file_space": 3000, "pin_slots": 2}},
}


def cfg(spec) -> dict:
    return (spec or {}).get("prompts") or {}


def profile(spec, name) -> dict:
    return (cfg(spec).get("profiles") or {}).get(name) or BUILTIN_PROFILES.get(name) or {}


def _matches(rule, a, roles) -> bool:
    classes = {a.get("cls")} | set(a.get("also") or ())
    sel = [rule.get(x) for x in ("agents", "classes", "roles")]
    if not any(sel):
        return True                                                       # no selector: everyone (a share may thin it)
    return bool((rule.get("agents") and a["id"] in rule["agents"]) or (rule.get("classes") and classes & set(rule["classes"]))
                or (rule.get("roles") and set(roles) & set(rule["roles"])))


def assign(spec, seed, agents, roles_of) -> None:
    """Generation: record each agent's profiles (agent["profiles"]) from prompts.assign. roles_of: agent id -> role names."""
    rules = cfg(spec).get("assign") or []
    if not rules:
        return
    for i, rule in enumerate(rules):
        rng = random.Random(f"{seed}|prompts|{i}")
        for a in agents:
            if not _matches(rule, a, roles_of.get(a["id"], [])):
                continue
            share = rule.get("share")
            if share is not None and rng.random() >= float(share):
                continue
            a.setdefault("profiles", [])
            if rule["profile"] not in a["profiles"]:
                a["profiles"].append(rule["profile"])


def assign_child(spec, seed, child, roles) -> None:
    """Life: a child's profiles, by class and role (not by name); a share is drawn per child."""
    for i, rule in enumerate(cfg(spec).get("assign") or []):
        if rule.get("agents") and not (rule.get("classes") or rule.get("roles")):
            continue
        if not _matches(rule, child, roles):
            continue
        if rule.get("share") is not None and random.Random(f"{seed}|prompts|{i}|{child['id']}").random() >= float(rule["share"]):
            continue
        child.setdefault("profiles", [])
        if rule["profile"] not in child["profiles"]:
            child["profiles"].append(rule["profile"])


def _text(inst, v) -> str:
    if isinstance(v, dict):
        if "builtin" in v:
            fn = BUILTINS.get(v["builtin"])
            return fn(inst) if fn else ""
        if "doc" in v:
            from charter import archive
            return archive.read(str(v["doc"])) or ""
        return ""
    return str(v or "")


def edits_for(inst, a, layer) -> list:
    """The edit blocks that apply to this agent's layer ("core" or "manual"): the world's, then each profile's, in order."""
    c = cfg(inst["spec"])
    out = [c.get(layer)] if c.get(layer) else []
    for p in a.get("profiles") or []:
        e = profile(inst["spec"], p).get(layer)
        if e:
            out.append(e)
    return out


def apply(inst, a, sections: list, layer: str, default_after: str | None = None) -> list:
    """sections: [(key, text)] in order -> edited copy. Never removes the core keys `identity`, `goal`, `actions` or `reply`."""
    keep = {"identity", "goal", "actions", "reply"} if layer == "core" else set()
    secs = [[k, t] for k, t in sections]
    for e in edits_for(inst, a, layer):
        for key in e.get("exclude") or []:
            if key not in keep:
                secs = [s for s in secs if s[0] != key]
        for key, v in (e.get("set") or {}).items():
            t = _text(inst, v)
            hit = next((s for s in secs if s[0] == key), None)
            if hit:
                hit[1] = t
            else:
                secs.append([key, t])
        for key, v in (e.get("append") or {}).items():
            t = _text(inst, v).strip()
            hit = next((s for s in secs if s[0] == key), None)
            if not t:
                continue
            if hit is None:
                secs.append([key, t])
            elif t not in hit[1]:                                         # no duplicates
                hit[1] = (hit[1].rstrip() + "\n" + t) if hit[1].strip() else t
        for key, v in (e.get("add") or {}).items():
            t = _text(inst, v)
            if any(s[0] == key for s in secs) or not t:
                continue
            after = (v.get("after") if isinstance(v, dict) else None) or default_after
            idx = next((i + 1 for i, s in enumerate(secs) if s[0] == after), len(secs))
            secs.insert(idx, [key, t])
    return [(k, t) for k, t in secs]


def memory(inst, a) -> dict:
    """Memory sizes from the agent's profiles (later profiles win): scratchpad, file_space, pin_slots."""
    out = {}
    for p in a.get("profiles") or []:
        out.update(profile(inst["spec"], p).get("memory") or {})
    return out


# ---------------------------------------------------------------------- plug-in sections
# A module adds its own system-prompt or manual sections by registering them, next to the code they describe:
#     from charter import composition as CP
#     @CP.manual_section("Conflict", after="World rules")
#     def _manual(inst, k, a): return "..."            # "" or None: the section is left out for this agent
#     @CP.core_section("conflict_note", after="goal")
#     def _core(inst, k, a): return "..."
# Sections registered with the same anchor appear in registration order. Spec edits (above) then apply to them like any other
# section, so a section can be switched off (exclude), replaced (set) or extended (append) per world or per profile.
_CORE: list = []                    # (key, fn, after, order)
_MANUAL: list = []                  # (title, fn, after, order)
PLUGINS = ("conflict", "media", "life")          # modules imported before building, so their registrations exist


def core_section(key, after="goal", order=0):
    def deco(fn):
        _CORE.append((key, fn, after, order))
        return fn
    return deco


def manual_section(title, after=None, order=0):
    """order: position among sections registered at the same anchor (lower first; ties in registration order)."""
    def deco(fn):
        _MANUAL.append((title, fn, after, order))
        return fn
    return deco


def _load_plugins():
    import importlib
    for m in PLUGINS:
        importlib.import_module(f"charter.{m}")


def insert(sections: list, registry: list, call) -> list:
    """sections: [(key, text)]; registry entries are called (call(fn) -> text) and inserted after their anchor (end if missing)."""
    _load_plugins()
    out = list(sections)
    placed = {}                                                          # anchor -> index after the last section placed there
    for key, fn, after, _ in sorted(registry, key=lambda r: r[3]):
        txt = call(fn)
        if not txt or not str(txt).strip():
            continue
        if after in placed:
            idx = placed[after]
        else:
            idx = next((i + 1 for i, s in enumerate(out) if s[0] == after), len(out))
        out.insert(idx, (key, str(txt).strip()))
        placed[after] = idx + 1
        placed = {a: (i + 1 if i > idx and a != after else i) for a, i in placed.items()}
    return out
