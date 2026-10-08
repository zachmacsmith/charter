"""Cause chains as primitives and laws see them (P2.1 frames; P3.1 redaction, D-18), and the chain sugar of the law API.

frame_view turns a kernel cause frame into a chain frame; chain_for is the chain a primitive's legacy aliases filter on (the kernel's
own view); chain_view is the chain a new-style hook receives, redacted for the viewing law. root_kind, caused_by_agent,
caused_by_law and chain_laws are law-API reads over a chain (api.law_api puts them into law.v2 namespaces)."""
from __future__ import annotations

from charter import jurisdictions as J


# ---------------------------------------------------------------------- the chain
def frame_view(frame: dict, viewer: str | None = None) -> dict:
    """A kernel cause frame ({"action": "transfer", "agent": "a4"}) as a chain frame ({"kind": "action", "id": "action:transfer",
    "agent": "a4"}). A viewing law does not see a turn's model-call key."""
    kind = next(iter(frame))
    out = {"kind": kind, "id": f"{kind}:{frame[kind]}", **{x: v for x, v in frame.items() if x != kind}}
    if viewer is not None:
        out.pop("call", None)
    return out


def chain_for(k, name: str) -> tuple:
    """The chain a primitive sees: the kernel's chain from the open root frame, or the implicit kernel root."""
    return k.chain() or ({"kind": "kernel", "id": f"kernel:{name}"},)


# ---------------------------------------------------------------------- chains as a law sees them (D-18: redacted for the viewing law)
def _observer(k):
    o = k.inst.get("observer")
    return o.get("id") if isinstance(o, dict) else None


def chain_view(k, frames, viewer=None, *, implicit_root=None, concealed=(), turn_agent=None) -> tuple:
    """Raw kernel frames (from the cascade's root inward) as chain frames {"kind", "id", ...}. An action frame names its agent (the
    turn's agent when the frame leaves it out). With a viewer (a law id): no turn call key; concealed actors read as None; the
    observer's doings and unannounced interventions read as {"kind": "world", "id": "world"}; a law of a hidden jurisdiction the
    viewer does not belong to reads as {"kind": "law", "id": "hidden"}. A law frame is {"kind": "law", "id": "law:<lid>", "hook", ...}."""
    out = [dict(implicit_root)] if implicit_root else []
    obs = _observer(k) if viewer is not None else None
    hide = set(concealed or ())
    vj = J.law_jur(k, viewer) if viewer is not None and "jur" in k.w else None
    for f in frames:
        f = dict(f)
        kind = next(iter(f))
        if kind == "action" and "agent" not in f and turn_agent is not None:
            f["agent"] = turn_agent
        if viewer is not None:
            if obs is not None and obs in f.values():                    # the observer's doings read as the world's
                out.append({"kind": "world", "id": "world"})
                continue
            if hide:
                f = k._redact(f, hide)
            if kind == "intervention" and not f.get("announce"):
                out.append({"kind": "world", "id": "world"})
                continue
            if kind == "law" and "jur" in k.w and f.get("law"):
                lj = J.law_jur(k, f["law"])
                if lj != vj and k._hidden_jur(lj):
                    out.append({"kind": "law", "id": "hidden"})
                    continue
        out.append(frame_view(f, viewer))
    return tuple(out)


def _raw_laws(frames) -> list:
    """(law id, hook) of every law frame among raw kernel frames (unredacted: R1 and R2)."""
    return [(f["law"], f.get("hook")) for f in frames if next(iter(f)) == "law"]


# ---------------------------------------------------------------------- law-API reads over a chain (review 09 §4.4; api.law_api)
def root_kind(chain):
    return chain[0].get("kind") if chain else None


def _law_of(f):
    """The law id of a chain frame ("law:L7" -> "L7"), or None (not a law frame, or a hidden one)."""
    if f.get("kind") != "law":
        return None
    lid = str(f.get("id", "")).split(":", 1)[1] if ":" in str(f.get("id", "")) else None
    return lid


def caused_by_agent(chain):
    return next((f.get("agent") for f in reversed(chain) if f.get("kind") == "action"), None)


def caused_by_law(chain, lid):
    return any(_law_of(f) == lid for f in chain)


def chain_laws(chain):
    out = []
    for f in chain:
        lid = _law_of(f)
        if lid and lid not in out:
            out.append(lid)
    return out


HELPERS = ("root_kind", "caused_by_agent", "caused_by_law", "chain_laws", "law_id", "treasury")
