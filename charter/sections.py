"""Sections (docs/ARCHITECTURE.md §3.10, work package P1.6; review 02 §4.4): every text an agent or the observer is given is a
rendering of `Section` rows. One row per piece of text, registered next to the code it describes; four layers read them:

  core      the context module's system prompt (context.core_prompt): CORE layout, spec/profile edits, then `fit` to the core budget
  manual    the per-agent manual (manual.sections, context.build_manual): MANUAL layout, then the modules' anchored sections
  legacy    the context-off system prompt (agents.system_prompt), frozen as it is (decision D-4: no new text goes here)
  observer  the secret observer's system prompt (observer.system_prompt)

A row:

    Section(key, render, layers, needs, after, order, cut, priority, budget, sep, note)
      key       the section's name ("identity", "World rules"); a manual row's key is the title shown (a row whose render
                returns a list of (title, text) expands into several sections, e.g. "Actions" -> "Actions: your edge", ...)
      render    View -> str, or None (the section is absent for this view), or [(title, text)]
      layers    the layers it appears in
      needs     requirements, all of which must hold: the action registry's language ("mod:conflict", "level:2", "cls:scientist",
                "right:press", "any:a|b", ...; action_registry._need) plus "role:<r>" (the agent holds role r)
      after     a module's section: inserted after this key (in `order`, ties in registration order); blank text leaves it out.
                None: the row has a place in the layer's LAYOUT
      order     position among rows anchored at the same key (lower first)
      cut       budget policy in a fitted layer (core): "never" (always kept whole) or "clip" (rendered last, cut to the room the
                "never" rows leave; `note` marks the cut)
      priority  among clip rows, the higher is fitted first (lower is cut first)
      budget    a clip row's own cap in tokens (None: whatever room is left)
      sep       joined layers: the text placed before this section (core: only between non-empty sections)

Layouts. A layer lists its rows' keys in order (LAYOUTS); a row may be in several layers (World rules: manual, legacy, observer),
each placing it where that text has always been. `render(layer, view)` returns [(key, text)]; `join` and `fit` turn that into a
prompt. Spec and profile edits (composition.apply) stay with the callers, unchanged.

View: what every render receives instead of (inst, k, aid) / (inst, a) / (k, aid): the instance, the kernel (or None), the agent
record, the rights this layer documents, and per-view caches (`facts`, `allowed`, `layout`, `roles`; `memo` for a layer's own).
Every number prose states comes from `view.facts` (charter.facts).
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from functools import cached_property
from typing import Callable

LAYERS = ("core", "manual", "legacy", "observer")
CUTS = ("never", "clip")


@dataclass(frozen=True)
class Section:
    key: str
    render: Callable
    layers: tuple = ("manual",)
    needs: tuple = ()
    after: str | None = None
    order: int = 0
    cut: str = "never"
    priority: int = 0
    budget: int | None = None
    sep: str = "\n"
    note: str = "...(trimmed)"


SECTIONS: list[Section] = []

# The layers' orders (keys of rows with a place; anchored module rows are inserted after their anchor).
LAYOUTS = {
    "core": ("overview", "laws", "identity", "leverage", "secret", "goal", "strategy", "temperament", "memory", "lookups", "actions",
             "manual_index", "reply"),
    "manual": ("World rules", "How your turn works", "Memory and files", "Your role", "Your rights", "Goals in this world", "Actions",
               "Private messages and the DM step", "Law language", "Law library", "Credit and loans", "Projects and tribute",
               "Codex articles you hold", "Words of power you have heard of", "Scientists' archive"),
    "legacy": ("World rules", "life", "identity", "goal", "temperament", "Goals in this world", "models", "actions", "law_language",
               "module_notes", "library", "reply"),
    "observer": ("World rules", "observer_role", "Goals in this world", "observer_actions", "observer_reply"),
}


def section(key, layers=("manual",), **kw):
    """Decorator: register `fn(view)` as a Section row."""
    def deco(fn):
        register(Section(key, fn, tuple(layers), **{k: tuple(v) if k == "needs" else v for k, v in kw.items()}))
        return fn
    return deco


def register(s: Section) -> Section:
    bad = [x for x in s.layers if x not in LAYERS]
    if bad or s.cut not in CUTS:
        raise ValueError(f"section {s.key!r}: layers must be in {LAYERS} and cut in {CUTS}")
    if any(x.key == s.key and set(x.layers) & set(s.layers) for x in SECTIONS):
        raise ValueError(f"section {s.key!r} registered twice for a layer")
    if s.after is None and any(s.key not in LAYOUTS[x] for x in s.layers):
        raise ValueError(f"section {s.key!r}: not in the layout of {[x for x in s.layers if s.key not in LAYOUTS[x]]} (give it a place "
                         "there, or an anchor with after=)")
    SECTIONS.append(s)
    return s


_LOADED = []


def load() -> None:
    """Import every module that registers rows: the prompt modules and each feature's module (features.FEATURES)."""
    if _LOADED:
        return
    from charter import features as FT
    for m in ("charter.manual", "charter.context", "charter.agents", "charter.observer", "charter.digest"):
        importlib.import_module(m)
    for f in FT.FEATURES:
        f.mod()
    _LOADED.append(True)


def rows(layer: str) -> list:
    load()
    return [s for s in SECTIONS if layer in s.layers]


# ---------------------------------------------------------------------- the view
@dataclass(frozen=True, eq=False)
class View:
    inst: dict
    k: object
    a: dict                          # the agent's record (the observer's for the observer layer)
    rights: tuple = ()               # the rights this layer documents (core: all held; manual: those not secret)
    layer: str = ""
    raw: dict | None = None          # the record modules' sections receive (the instance's, or {"id": aid} for a newcomer)
    cache: dict = field(default_factory=dict)

    @property
    def aid(self) -> str:
        return self.a["id"]

    @property
    def spec(self) -> dict:
        return self.inst["spec"]

    @cached_property
    def facts(self) -> dict:
        from charter import facts as FX
        if self.layer == "observer":                                    # no agent of the world: the world's facts only
            return FX.facts(self.inst)
        return FX.facts(self.inst, self.a, self.k)

    @cached_property
    def allowed(self) -> list:
        from charter import context as CX
        return CX.allowed_actions(self.inst, self.a, list(self.rights), self.k)

    @cached_property
    def layout(self) -> tuple:
        from charter import context as CX
        return CX.action_layout(self.allowed, list(self.rights))

    @cached_property
    def roles(self) -> list:
        from charter import context as CX
        return CX.own_roles(self.k, self.aid)

    @cached_property
    def lvl(self) -> int:
        return ["L0", "L1", "L2", "L3", "L4"].index(self.inst["law_level"])

    def on(self, feature: str) -> bool:
        from charter import features as FT
        return FT.on(feature, self.inst)

    def memo(self, fn: Callable):
        """fn(view), computed once per view (a layer's shared values: the core prompt's action list, ...)."""
        if fn not in self.cache:
            self.cache[fn] = fn(self)
        return self.cache[fn]


def view(inst, k, a, rights=(), layer="", raw=None) -> View:
    return View(inst, k, a, tuple(rights), layer, raw if raw is not None else a)


def needs_ok(v: View, needs) -> bool:
    from charter import action_registry as AR
    for n in needs:
        if n.startswith("role:"):
            if n[5:] not in v.roles:
                return False
        elif not AR._need(v.inst, v.a, list(v.rights), n):
            return False
    return True


# ---------------------------------------------------------------------- rendering
def render(layer: str, v: View, anchored: bool = True) -> list:
    """[(key, text)] for this view: the layer's rows in LAYOUT order (rows whose needs fail or whose render gives None are left out;
    a list expands into its sections), then (anchored=True) the modules' rows after their anchors."""
    secs = rows(layer)
    placed = {s.key: s for s in secs if s.after is None}
    out = []
    for key in LAYOUTS[layer]:
        s = placed.get(key)
        if s is None or not needs_ok(v, s.needs):
            continue
        t = "" if s.cut == "clip" else s.render(v)                     # a clip row is rendered by fit(), into the room left
        if t is None:
            continue
        out += [(x, y) for x, y in t] if isinstance(t, list) else [(key, t)]
    if anchored:
        out = _insert(out, [s for s in secs if s.after is not None], v)
    return out


def _insert(out: list, anchored: list, v: View) -> list:
    """Anchored rows after their anchor (the end if it is missing); rows at one anchor in `order`, then registration order."""
    out = list(out)
    placed = {}                                                          # anchor -> index after the last row placed there
    for s in sorted(anchored, key=lambda s: s.order):
        txt = s.render(v) if needs_ok(v, s.needs) else None
        if not txt or not str(txt).strip():
            continue
        if s.after in placed:
            idx = placed[s.after]
        else:
            idx = next((i + 1 for i, x in enumerate(out) if x[0] == s.after), len(out))
        out.insert(idx, (s.key, str(txt).strip()))
        placed[s.after] = idx + 1
        placed = {a: (i + 1 if i > idx and a != s.after else i) for a, i in placed.items()}
    return out


def sep(layer: str, key: str) -> str:
    s = next((x for x in rows(layer) if x.key == key), None)
    return s.sep if s is not None else "\n"


def join(layer: str, secs: list) -> str:
    """A fixed layout joined verbatim: each section preceded by its `sep`, empty sections included (legacy, observer)."""
    return "".join(sep(layer, key) + t for key, t in secs)


def fit(layer: str, v: View, secs: list, budget: int) -> tuple[str, int]:
    """A budgeted layer (core): the "never" sections joined (a blank line before rows whose sep says so, nothing before the first),
    then each "clip" section, highest priority first, rendered and cut to the room left (at least 200 tokens) and placed before
    them. secs: [(key, text)] after edits; a clip row's text there is a placeholder. Returns (text, tokens cut), the cut False when
    no clip section is present (as the context record has always had it)."""
    from charter.context import clip, tokens
    by = {s.key: s for s in rows(layer)}
    clip_keys = [key for key, _ in secs if key in by and by[key].cut == "clip"]
    essentials = ""
    for key, t in secs:
        if key in clip_keys:
            continue
        essentials += (sep(layer, key) if essentials else "") + t.strip("\n")
    head, cut = [], 0
    for key in sorted(clip_keys, key=lambda x: -by[x].priority):
        s = by[key]
        room = max(200, int(budget) - tokens(essentials) - 10)
        text, n = clip(s.render(v), min(room, s.budget) if s.budget else room, s.note)
        head.append(text)
        cut += n
    head = [h for h in head if h]
    return ("\n\n".join(head) + "\n\n" + essentials) if head else essentials, (cut if clip_keys else False)
