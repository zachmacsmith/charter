"""Laws that work or fail loudly (docs/review/31_institutions/07_rules_courts.md §4; charter/laweffects.py): amendments reach the
offices their law declares, reseat, law_effect with `inert`, previews of amendments and of the enactment itself, failed law calls,
expects, and the Millbrook keeper lesson."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from charter import actions as A
from charter import agents as AG
from charter import generator as GN
from charter import institutions as IN
from charter import runner
from charter import start as STT
from charter.actions import ActionError

import test_established_worlds as TW


@pytest.fixture(scope="module")
def village_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lawfx")
    out = {}
    for name, over in (("refuse", {}), ("apply", {"institutions": {"reseat": "apply"}}),
                       ("off", {"institutions": {"amend_offices": False},
                                "law": {"effects": False, "call_failures": False, "expects": False}})):
        sp = TW.village(rounds=1)
        for sec, kv in over.items():
            sp.setdefault(sec, {}).update(kv)
        inst = GN.generate(sp, 1)
        out[name] = Path(runner.run(inst, AG.ScriptedPolicy(1), tmp / name, log=lambda *a: None))
    return out


def kernel(village_run, name="refuse"):
    return STT._kernel_at(village_run[name], 0)[1]


def offices_act(k):
    return next(l for l in k.active_laws() if l["title"] == "Offices Act" and l.get("jurisdiction") in (None, "J0"))


def events(k, t, since=0):
    return [e for e in k.events[since:] if e["type"] == t]


def enact(k, code, author="Ada"):
    lid = k.new_law(code, author)
    k.enact(lid)
    return lid


def amend_now(k, target, code, author="Ada"):
    """An amendment draft enacted at once (as if its ballot passed)."""
    from charter import amendment as AM
    lid = AM.amendment_draft(k, target, code, author, "test")
    k.enact(lid)
    return lid


SEIZE_INTENT = 'intent = "The keeper\'s hoard is seized. '
UNSEAT = ("'holders': ['Cy']", "'holders': ['Bo']")


# ---------------------------------------------------------------------- the Millbrook lesson
def test_millbrook_keeper_amendment_is_refused_at_proposal(village_run):
    k = kernel(village_run)
    off = offices_act(k)
    new = off["code"].replace(*UNSEAT)
    with pytest.raises(ActionError, match=r"offices\.keeper\.holders only seats an office when it is first declared.*"
                                          r"revoke and grant the right J0\.keeper.*reseat\(\"J0\", \"keeper\""):
        A.act(k, "Ada", "amend", {"law": off["id"], "code": new, "reason": "unseat the keeper"})
    assert IN.holders(k, "J0", "keeper") == ["Cy"]


def test_millbrook_keeper_amendment_reseats_under_apply(village_run):
    k = kernel(village_run, "apply")
    off = offices_act(k)
    n = len(k.events)
    amend_now(k, off["id"], off["code"].replace(*UNSEAT).replace('intent = "', SEIZE_INTENT))
    assert IN.holders(k, "J0", "keeper") == ["Bo"]
    assert "J0.keeper" in k.w["agents"]["Bo"]["rights"] and "J0.keeper" not in k.w["agents"]["Cy"]["rights"]
    fx = events(k, "law_effect", n)[-1]["data"]
    assert fx["act"] == "amend" and not fx["inert"]
    assert "office J0.keeper holders: Cy -> Bo" in fx["changes"]
    filled = events(k, "office_filled", n)
    assert filled and filled[-1]["data"]["rule"] == "reseat" and filled[-1]["agent"] == "Bo"
    from charter import succession as SU
    assert all(v["status"] != "open" for v in SU.state(k)["vacancies"] if v["office"] == "keeper")   # filled: no election


def test_intent_only_seizure_is_inert(village_run):
    k = kernel(village_run)
    off = offices_act(k)
    n = len(k.events)
    A.act(k, "Ada", "amend", {"law": off["id"], "code": off["code"].replace('intent = "', SEIZE_INTENT), "reason": "seize"})
    prop = events(k, "proposal", n)[-1]
    assert prop["data"]["inert"] is True and prop["data"]["at_enactment"] == []
    assert "INERT" in AG.render_event(k, prop, "[t]")
    amend_now(k, off["id"], off["code"].replace('intent = "', SEIZE_INTENT))
    fx = events(k, "law_effect", n)[-1]
    assert fx["data"]["inert"] is True and fx["data"]["changes"] == [] and fx["vis"] == "public"
    line = AG.render_event(k, fx, "[t]")
    assert f"{off['id']} 'Offices Act' was amended but changed nothing" in line
    assert IN.holders(k, "J0", "keeper") == ["Cy"]


def test_new_law_with_only_intent_is_inert_and_a_real_seizure_is_not(village_run):
    k = kernel(village_run)
    n = len(k.events)
    lid = enact(k, 'title = "Seizure"\nintent = "The keeper\'s hoard is seized."\n')
    fx = events(k, "law_effect", n)[-1]["data"]
    assert fx["law"] == lid and fx["inert"] is True
    assert "passed but changed nothing" in AG.render_event(k, events(k, "law_effect", n)[-1], "[t]")
    k.w["agents"]["Cy"]["holdings"]["food"] = 9.0
    lid = enact(k, 'title = "Seizure"\nintent = "Seize."\ndef on_enact():\n    move("Cy", "store:S1", "food", 9)\n')
    fx = events(k, "law_effect", n)[-1]["data"]
    assert fx["law"] == lid and not fx["inert"] and "Cy food -9" in fx["changes"] and "store S1 food +9" in fx["changes"]


# ---------------------------------------------------------------------- reconciling an amended Offices Act
def test_amendment_applies_changed_fields_and_new_and_removed_offices(village_run):
    k = kernel(village_run)
    off = dict(offices_act(k))
    code = off["code"].replace("'duties': 'Keep the granary.'", "'duties': 'Keep the granary well.', 'term': 3")
    code = code.replace("offices = {", "offices = {'herald': {'title': 'Herald', 'holders': ['Di']}, ")
    n = len(k.events)
    amend_now(k, off["id"], code)
    o = IN.office(k, "J0", "keeper")
    assert o["duties"] == "Keep the granary well." and o["term"] == 3
    assert IN.holders(k, "J0", "herald") == ["Di"] and IN.holders(k, "J0", "keeper") == ["Cy"]
    ch = events(k, "law_effect", n)[-1]["data"]["changes"]
    assert "office J0.herald created (holders: Di)" in ch and any(x.startswith("office J0.keeper duties") for x in ch)
    # the herald removed again: abolished (institutions.succession on)
    amend_now(k, off["id"], off["code"])
    assert IN.office(k, "J0", "herald") is None
    assert "J0.herald" not in k.w["agents"]["Di"]["rights"]


def test_off_keeps_the_old_silent_no_op(village_run):
    k = kernel(village_run, "off")
    off = offices_act(k)
    n = len(k.events)
    amend_now(k, off["id"], off["code"].replace(*UNSEAT).replace("'duties': 'Keep the granary.'", "'duties': 'X.'"))
    assert IN.holders(k, "J0", "keeper") == ["Cy"] and IN.office(k, "J0", "keeper")["duties"] == "Keep the granary."
    assert not events(k, "law_effect", n) and "offices" not in k.view()
    assert "reseat" not in k.api_for(off["id"])


# ---------------------------------------------------------------------- reseat
def test_reseat_law_function(village_run):
    k = kernel(village_run)
    n = len(k.events)
    enact(k, 'title = "New Keeper"\nintent = "Osric for Elspeth."\ndef on_enact():\n    reseat("J0", "keeper", ["Ed"])\n')
    assert IN.holders(k, "J0", "keeper") == ["Ed"]
    assert "office J0.keeper holders: Cy -> Ed" in events(k, "law_effect", n)[-1]["data"]["changes"]
    n = len(k.events)
    enact(k, 'title = "Bad Keeper"\nintent = "Nobody."\ndef on_enact():\n    reseat("J0", "keeper", ["Ghost"])\n')
    assert IN.holders(k, "J0", "keeper") == ["Ed"]
    fail = events(k, "law_call_failed", n)
    assert fail and fail[-1]["data"]["fn"] == "reseat" and "Ghost cannot hold J0.keeper" in fail[-1]["data"]["reason"]
    assert "Ada" in fail[-1]["vis"]                                      # the author (and the officers)
    fx = events(k, "law_effect", n)[-1]["data"]
    assert fx["inert"] is True and fx["failed_calls"][0]["fn"] == "reseat"


# ---------------------------------------------------------------------- failed law calls
def test_failed_move_is_logged_once_per_round_and_shown_to_the_author(village_run):
    k = kernel(village_run)
    k.w["agents"]["Cy"]["holdings"]["food"] = 3.0
    n = len(k.events)
    lid = enact(k, 'title = "Hoard Seizure"\nintent = "Seize."\ndef on_enact():\n    move("Cy", "reserve", "food", 1000)\n'
                   'def on_round_end(r):\n    move("Cy", "reserve", "food", 1000)\n    move("Cy", "reserve", "food", 1000)\n', "Bo")
    fails = events(k, "law_call_failed", n)
    assert len(fails) == 1 and fails[0]["data"]["law"] == lid and fails[0]["data"]["fn"] == "move"
    assert "Bo" in fails[0]["vis"] and fails[0]["data"]["reason"]
    assert "failed:" in AG.render_event(k, fails[0], "[t]")
    fx = events(k, "law_effect", n)[-1]["data"]
    assert fx["failed_calls"] and fx["inert"] is False                   # its round hook still acts later
    k.hooks("on_round_end", k.r)                                         # same round: already reported
    assert len(events(k, "law_call_failed", n)) == 1
    k.w["round"] += 1
    k.hooks("on_round_end", k.r)
    assert len(events(k, "law_call_failed", n)) == 2


def test_dry_run_lists_failed_calls(village_run):
    k = kernel(village_run)
    lid = k.new_law('title = "Hoard Seizure"\nintent = "Seize."\ndef on_enact():\n    move("Cy", "reserve", "food", 1000)\n', "Ada")
    diff = k.dry_run(lid)
    assert any(x.startswith(f"failed call by {lid}: move(") for x in diff)


# ---------------------------------------------------------------------- expects
EXPECTING = ('title = "New Keeper"\nintent = "Ed keeps the granary."\nexpects = [{"office": "J0.keeper", "holders": ["Ed"]}]\n'
             'def on_enact():\n    reseat("J0", "keeper", ["{who}"])\n')


def test_expects_refuses_at_dry_run_and_is_published_in_force(village_run):
    k = kernel(village_run)
    with pytest.raises(ActionError, match=r"does not do what it expects: J0\.keeper is held by Di, not Ed"):
        A.act(k, "Ada", "propose", {"code": EXPECTING.replace("{who}", "Di")})
    A.act(k, "Ada", "propose", {"code": EXPECTING.replace("{who}", "Ed")})       # meets it: proposed
    n = len(k.events)
    enact(k, EXPECTING.replace("{who}", "Di"))                                   # for real: announced, not undone
    bad = events(k, "law_expectation_failed", n)
    assert bad and "J0.keeper is held by Di, not Ed" in bad[-1]["data"]["unmet"][0] and bad[-1]["vis"] == "public"
    assert IN.holders(k, "J0", "keeper") == ["Di"]


def test_expects_shapes():
    from charter import laweffects as LE
    from charter import lawlang as L
    assert LE.parse_expects('expects = [{"store": "S1", "item": "food", "at_least": 1}]')
    for bad in ('expects = {"x": 1}', 'expects = [{"store": "S1", "item": "food"}]', 'expects = [{"office": "J0.k"}]',
                'expects = [{"store": "S1", "holding": "Ada", "item": "food", "at_least": 1}]'):
        with pytest.raises(L.LawError):
            LE.parse_expects(bad)


# ---------------------------------------------------------------------- the previewer
def test_preview_law_previews_amendments_and_the_enactment(village_run):
    from charter import lawpreview as LP
    k = kernel(village_run, "apply")
    off = dict(offices_act(k))
    before = copy.deepcopy(k.w)
    rep = LP.preview_law(k, "Ada", off["code"].replace(*UNSEAT), amends=off["id"], scenario="none", rounds=1)
    assert rep["ok"] and rep["enact"]["ok"] and rep["enact"]["status"] == "enacted_amendment"
    assert "office J0.keeper holders: Cy -> Bo" in rep["enact"]["diff"] and not rep["enact"]["inert"]
    assert "At enactment: " in LP.render(rep) and k.w == before
    rep = LP.preview_law(k, "Ada", off["code"].replace('intent = "', SEIZE_INTENT), amends=off["id"], scenario="none", rounds=1)
    assert rep["enact"]["inert"] is True and "INERT" in LP.render(rep)
    k2 = kernel(village_run)                                             # reseat refuse: the amendment's refusal is the preview
    rep = LP.preview_law(k2, "Ada", off["code"].replace(*UNSEAT), amends=off["id"], scenario="none", rounds=1)
    assert "only seats an office when it is first declared" in (rep.get("error") or rep["procedure"].get("refusal") or "")


def test_extended_view_lists_offices_stores_and_treasuries(village_run):
    k = kernel(village_run)
    v = k.view()
    assert v["offices"]["J0.keeper"]["holders"] == ["Cy"] and v["offices"]["J0.keeper"]["controls"] == ["store:S1"]
    assert v["stores"]["S1"]["owner"] == "J0" and v["stores"]["S1"]["holdings"]["food"] > 0
    assert "A1" in v["treasuries"] and v["treasuries"]["A1"]["penny"] > 0
