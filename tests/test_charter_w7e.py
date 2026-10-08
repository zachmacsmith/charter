"""W7e: wave-6 follow-ups under law.v2 (and contracts): a law's validity window shown to agents and reviewers, an after-hook's
refusal told to the acting agent, law helpers is_number / is_text, court-rule follow-ups (appellate rule, a cap on rulings), stage
plans for contracts' own procedures and in the jurisdiction probes, history() filtered by agents named in event data, an
association's law reading its members-only record, context's lookup error path, breach victims, and the enforcement seams of review
11 §4 (case source, law_can_see). Offline: no model calls."""
from __future__ import annotations

import copy
import re

import pytest

from charter import actions as A
from charter import agents as AG
from charter import context as CX
from charter import dispatch as D
from charter import generator
from charter import lawpreview as LP
from charter import spec as S
from charter.kernel import Kernel

_INST: dict = {}


def world(v2=True, sets=(), preset="E4"):
    key = (v2, preset, tuple(sets))
    if key not in _INST:
        sp = S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", *(["law.v2=true"] if v2 else []), *sets])
        _INST[key] = generator.generate(sp, 1)
    inst = copy.deepcopy(_INST[key])
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return k


def enact(k, code):
    lid = k.new_law(code, "constitution")
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active", k.w["laws"][lid]
    return lid


def law(title, body):
    return f'title = "{title}"\nintent = "test"\n' + body


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def agents(k, n=3):
    return [a for a in k.roster() if k.cls_of(a) not in ("board", "fixer")][:n]


# ====================================================================== 2. W6a: windows shown; after-hook refusals told
WINDOWED = law("Sunset", "in_force_from = 2\nin_force_until = 5\ndef on_round_end(r):\n    pass\n")


def test_the_draft_carries_the_window_under_v2_only():
    k = world()
    lid = k.new_law(WINDOWED, "a")
    d = D.draft(k, lid)
    assert (d["in_force_from"], d["in_force_until"]) == (2, 5)
    plain = k.new_law(law("Plain", "x = 1\n"), "a")
    assert (D.draft(k, plain)["in_force_from"], D.draft(k, plain)["in_force_until"]) == (None, None)
    k1 = world(v2=False)
    assert "in_force_from" not in D.draft(k1, k1.new_law(WINDOWED, "a"))


def test_agents_see_the_window_in_the_law_list_and_read_law():
    k = world()
    lid = enact(k, WINDOWED)
    a = agents(k)[0]
    note = D.window_note(k, lid)
    assert note == " [in force while round() is 2-5; out of force now]" and k.r < 2
    assert f"'Sunset' (" in AG.state_view(k, a) and note in AG.state_view(k, a)
    assert note in CX.read_law(k, a, lid)
    k.w["round"] = 3
    assert D.window_note(k, lid) == " [in force while round() is 2-5]"
    assert D.window_note(k, k.active_laws()[0]["id"]) == ""                 # no window: no note
    k1 = world(v2=False)
    l1 = enact(k1, WINDOWED)
    assert D.window_note(k1, l1) == "" and "in force while" not in CX.read_law(k1, a, l1)


def test_the_preview_shows_the_window():
    k = world()
    a = agents(k)[0]
    rep = LP.preview_law(k, a, WINDOWED)
    assert rep["static"]["in_force"] == [2, 5]
    assert "in force while round() is 2-5" in LP.render(rep)
    rep = LP.preview_law(k, a, law("Open", "in_force_until = 4\nx = 1\n"))
    assert rep["static"]["in_force"] == [None, 4] and "round() <= 4" in LP.render(rep)


def test_a_refusal_in_an_after_hook_is_told_to_the_acting_agent():
    k = world()
    a, b, _ = agents(k)
    lid = enact(k, law("Undo", "def after_move(p, chain):\n    if p['why'] == 'transfer':\n        state['n'] = 1\n"
                               "        refuse('no gifts on Sunday')\n"))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert events(k, "transfer") and k.w["laws"][lid]["state"] == {}
    e = events(k, "law_refused")[-1]
    assert e["vis"] == [a] and e["data"] == {"law": lid, "hook": "after_move", "primitive": "move", "reason": "no gifts on Sunday"}
    txt = AG.render_event(k, e, a)
    assert "refused after your move" in txt and "no gifts on Sunday" in txt and "your action stands" in txt
    assert events(k, "hook_aborted")[-1]["data"]["kind"] == "refused"      # the monitor's record as before


def test_a_refusal_without_an_acting_agent_tells_nobody():
    k = world()
    a, b, _ = agents(k)
    enact(k, law("Undo", "def after_move(p, chain):\n    refuse('no')\n"))
    with k.cause("kernel", "test", root=True):
        k.apply("move", src=a, dst=b, item="timber", qty=1, why="kernel")
    assert events(k, "hook_aborted") and not events(k, "law_refused")
