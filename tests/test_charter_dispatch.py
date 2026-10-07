"""P2.1: Kernel.apply, charter/dispatch.py and the legacy hook aliases (ARCHITECTURE §3.3, §5, §10 I-1..I-3; review 09 §4, §9.3).

Behaviour preservation is checked two ways:
  - a scripted scenario (every routed primitive, every legacy alias of a routed primitive, both through actions and through the law
    API) logs every law-function invocation (law, function, args, result, order), every event and the final state; the record must
    equal tests/fixtures/charter_dispatch_hooks.json, recorded at 88ab356 (before P2.1) with `python tests/test_charter_dispatch.py`;
  - the same hook log over scripted preset runs (E4, society, and society with hook-heavy start laws) against the same fixture.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE = Path(__file__).parent / "fixtures" / "charter_dispatch_hooks.json"

HOOK_LAWS = ['start_laws=["Harvest Levy", "Transfer Tax", "Bribery Disclosure", "Moderation", "Open Data", "Research Grant", '
             '"Communications Act", "Poll Tax", "Universal Dividend"]', "conditions.law_reads_dms=true"]
PRESET_CASES = {"E4": ("E4", ()), "society": ("society", ()), "society_hooks": ("society", tuple(HOOK_LAWS))}


def _plain(x):
    """A JSON stand-in for objects law code receives (Proposal): class and attributes, never a memory address."""
    return {"__class__": type(x).__name__, **vars(x)} if hasattr(x, "__dict__") else repr(x)


def _logging_calls():
    from charter.kernel import Kernel
    calls, orig = [], Kernel.call

    def call(self, lid, fn, *args):
        out = orig(self, lid, fn, *args)
        calls.append(json.dumps([self.r, lid, getattr(fn, "__name__", None), list(args), out], default=_plain, sort_keys=True))
        return out
    return calls, orig, call


def hook_calls(preset, seed=1, rounds=3, sets=()):
    """Every law-function invocation (Kernel.call) of a scripted run, in order."""
    from charter import agents as AG, generator, runner, spec as S
    from charter.kernel import Kernel
    calls, orig, call = _logging_calls()
    Kernel.call = call
    try:
        sp = S.apply_overrides(S.load(preset), [f"rounds={rounds}", "shared_archive.enabled=false", *sets])
        inst = generator.generate(sp, seed)
        inst["run_id"] = f"hooklog_{preset}"
        with tempfile.TemporaryDirectory() as d:
            runner.run(inst, AG.ScriptedPolicy(seed), Path(d) / "out", log=lambda *a: None)
    finally:
        Kernel.call = orig
    return calls


LAW_A = '''title = "Hook Probe A"
intent = "probe every routed primitive"

def on_enact():
    create_right("probe_right")
    grant("{w1}", "probe_right")
    grant("{w1}", "anon")
    grant("{w1}", "encrypt")
    grant("{w1}", "veto")
    create_currency("pc", True, "reserve")
    set_convertible("pc")
    mint("pc", 5, "{w1}")
    burn("pc", 2, "{w1}")
    burn("pc", 100, "{w1}")
    set_quota("{camp}", 50)
    set_harvest_limit("{camp}", 5)
    set_fee("{camp}", "stone", 0.5)
    set_dm_limit(4)
    set_dm_limit(3, "{w2}")
    set_dm_limit(3, "{board}")
    limit_actions("{board}", 1, 1)
    suspend("{w1}", "veto", 1)
    revoke("{w1}", "veto")

def on_transfer(src, dst, item, qty):
    if qty > 5:
        return False
    return 0.5

def on_harvest(agent, camp, x, y):
    return 1

def on_post(agent, text):
    if contains(text, "hide"):
        hide_post(current_post())

def on_dm(sender, recipient, text, encrypted):
    move(sender, "reserve", "timber", 0.1)

def on_round_end(r):
    fine("{w2}", "timber", 1)
    suspend("{w2}", "probe_right", 1)
    limit_actions("{w2}", 2, 1)
    revoke("{w1}", "probe_right")
    for p in hidden_posts():
        unhide_post(p)
    move("reserve", "{w2}", "timber", 0.5)
'''

LAW_B = '''title = "Hook Probe B"
intent = "a second law with the same hooks"

def on_transfer(src, dst, item, qty):
    return 0.25

def on_harvest(agent, camp, x, y):
    return True

def on_post(agent, text):
    state["n"] = state.get("n", 0) + 1

def on_dm(sender, recipient, text, encrypted):
    state["dms"] = state.get("dms", 0) + 1
'''


def scenario() -> dict:
    """A scripted E4 world with two probe laws; agents act through actions.act. Returns everything observable."""
    from charter import actions as A, generator, spec as S
    from charter.kernel import Kernel
    calls, orig, call = _logging_calls()
    Kernel.call = call
    try:
        sp = S.apply_overrides(S.load("E4"), ["conditions.law_reads_dms=true", "channels.encryption=true", "shared_archive.enabled=false"])
        k = Kernel(generator.generate(sp, 1))
        roster = k.roster()
        workers = [a for a in roster if any(r.startswith("harvest:") for r in k.w["agents"][a]["rights"])]
        w1, w2 = workers[0], workers[1]
        media = next(a for a in roster if k.has(a, "press"))
        board = next(a for a in roster if k.cls_of(a) == "board")
        camp = next(r.split(":", 1)[1] for r in k.w["agents"][w1]["rights"] if r.startswith("harvest:"))
        dials = k.w["camps"][camp]["dials"]
        results = []
        k.begin_round_cause(phase="setup")
        for code in (LAW_A.format(w1=w1, w2=w2, camp=camp, board=board), LAW_B):
            k.enact(k.new_law(code, "constitution"))
        k.phase("turns")

        def act(aid, name, args):
            with k.cause("turn", aid, call=f"r0:{aid}:0"):
                try:
                    results.append([aid, name, A.act(k, aid, name, args)])
                except A.ActionError as e:
                    results.append([aid, name, f"ERROR {e}"])

        act(w1, "harvest", {"camp": camp, "x": [1] * dials})
        act(w1, "harvest", {"camp": camp, "x": [2] * dials})
        act(w1, "transfer", {"to": w2, "item": "timber", "qty": 2})
        act(w1, "transfer", {"to": w2, "item": "timber", "qty": 9})
        act(w1, "transfer", {"to": w2, "item": "timber", "qty": 10000})
        act(w1, "dm", {"to": w2, "text": "hello there"})
        act(w1, "dm", {"to": w2, "text": "secret", "encrypted": True})
        dm_id = next(e["id"] for e in reversed(k.events) if e["type"] == "dm")
        act(w2, "reply", {"message": dm_id, "text": "thanks", "item": "timber", "qty": 1})
        act(w1, "post", {"text": "a plain post"})
        act(w1, "post", {"text": "please hide this"})
        act(w1, "anon_post", {"text": "anonymous hide"})
        act(media, "publish", {"headline": "News", "text": "nothing to see"})
        post_id = next(e["id"] for e in k.events if e["type"] == "post")
        act(media, "report", {"event": post_id, "text": "someone posted"})
        act(media, "set_dm_limit", {"n": 6})
        act(media, "set_dm_limit", {"n": 2, "agent": w2})
        act(media, "set_dm_limit", {"n": 2, "agent": board})
        act(w1, "deposit", {"currency": "pc", "item": "timber", "qty": 2})
        act(w1, "redeem", {"currency": "pc", "item": "timber", "coins": 0.05})
        act(w1, "deposit", {"currency": "pc", "item": "stone", "qty": 1})
        act(w2, "transfer", {"to": w1, "item": "stone", "qty": 1})
        k.phase("end_of_round")
        k.hooks("on_round_end", k.r)
        k.phase("turns")
        act(media, "publish", {"headline": "Story", "text": "hide this story"})   # on_post sees no current_post: L1 is suspended
        k.end_round_cause()
        probes = [k.probe("harvest"), k.probe("transfer"), k.probe("transfer_to_official")]
        state = {x: k.w[x] for x in ("agents", "reserve", "currencies", "rights", "camps", "hidden", "dm_limit", "dm_sent",
                                     "harvest_count", "quota_used")}
        effects = {x: (sorted(v) if isinstance(v, set) else v) for x, v in k.w["effects"].items()}
        return json.loads(json.dumps({"calls": calls, "results": results, "events": k.events, "probes": probes, "state": state,
                                      "effects": effects, "laws": {i: l["state"] for i, l in k.w["laws"].items()}},
                                     default=_plain, sort_keys=True))
    finally:
        Kernel.call = orig


def record() -> dict:
    return {"scenario": scenario(), "presets": {name: hook_calls(p, sets=sets) for name, (p, sets) in PRESET_CASES.items()}}


@pytest.fixture(scope="module")
def recorded():
    return json.loads(FIXTURE.read_text())


def _first_diff(a, b, path=""):
    if type(a) is not type(b):
        return path, a, b
    if isinstance(a, dict):
        for x in sorted(set(a) | set(b)):
            if x not in a or x not in b:
                return f"{path}.{x}", a.get(x), b.get(x)
            d = _first_diff(a[x], b[x], f"{path}.{x}")
            if d:
                return d
        return None
    if isinstance(a, list):
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return (f"{path}.len", len(a), len(b)) if len(a) != len(b) else None
    return None if a == b else (path, a, b)


def test_scenario_is_identical_to_before_p2_1(recorded):
    """Every hook invocation (law, name, args, result, order), every event (cause included) and the final state."""
    now = scenario()
    assert not _first_diff(recorded["scenario"], now), _first_diff(recorded["scenario"], now)
    assert any('"on_transfer"' in c for c in now["calls"]) and any('"on_harvest"' in c for c in now["calls"])
    assert any('"on_post"' in c for c in now["calls"]) and any('"on_dm"' in c for c in now["calls"])


@pytest.mark.parametrize("name", list(PRESET_CASES))
def test_preset_hook_sequences_are_identical_to_before_p2_1(recorded, name):
    preset, sets = PRESET_CASES[name]
    now = hook_calls(preset, sets=sets)
    assert now == recorded["presets"][name], _first_diff(recorded["presets"][name], now)


# ---------------------------------------------------------------------- the dispatcher itself
@pytest.fixture()
def k():
    from charter import generator, spec as S
    from charter.kernel import Kernel
    return Kernel(generator.generate(S.apply_overrides(S.load("E4"), ["shared_archive.enabled=false"]), 1))


def _enact(k, body):
    lid = k.new_law(f'title = "T"\nintent = "t"\n{body}', "constitution")
    k.enact(lid)
    return lid


def test_routed_rows_name_dispatch_functions():
    from charter import dispatch as D, primitives as PR
    want = {"move", "harvest", "mint", "burn", "create_currency", "grant_right", "revoke_right", "suspend_right", "limit_actions",
            "create_right", "post", "dm", "hide_post", "set_camp_rule", "set_dm_limit",
            "begin_life", "end_life"}                                                          # P2.4b
    want |= {"regrow", "drift", "destroy", "set_camp_state", "create_camp", "contribute", "settle_project"}       # P2.4c: world causes
    assert set(D.ROUTED) == want
    for n in want:
        p = PR.get(n)
        assert p.fn == f"dispatch:do_{n}" and p.fn in p.sites and callable(getattr(D, f"do_{n}"))
        assert set(D.OPTIONS[n]).isdisjoint(p.params), n


def test_apply_returns_an_outcome_and_refuses_with_physics_errors(k):
    from charter import dispatch as D
    a, b = k.roster()[0], k.roster()[2]
    have = k.bal(a, "timber")
    out = k.apply("move", src=a, dst=b, item="timber", qty=1, why="gift")
    assert isinstance(out, D.Outcome) and out.ok and out.result == {"moved": 1.0, "charged": 0.0} and k.bal(a, "timber") == have - 1
    assert k.events[-1]["type"] == "move" and k.events[-1]["data"]["why"] == "gift" and k.events[-1]["agent"] is None
    with pytest.raises(D.PhysicsError) as e:
        k.apply("move", src=a, dst=b, item="timber", qty=10 ** 6, why="gift")
    assert e.value.reason == "insufficient"
    assert k.move(a, b, "timber", 10 ** 6) is False                    # Kernel.move keeps its yes/no contract
    assert k.apply("move", src=a, dst=b, item="timber", qty=0, why="gift").ok
    with pytest.raises(D.L.LawError, match="non-negative"):
        k.apply("move", src=a, dst=b, item="timber", qty=-1, why="gift")
    with pytest.raises(TypeError, match="unexpected payload keys: colour"):
        k.apply("move", src=a, dst=b, item="timber", qty=1, why="gift", colour="red")
    with pytest.raises(D.NotRouted):
        k.apply("attack", attacker=a, target=b, units=1, covert=False, disguise=False, lawful=False)
    with pytest.raises(D.PR.UnknownPrimitive):
        k.apply("teleport", agent=a)


def test_law_functions_convert_refusals(k):
    board = next(a for a in k.roster() if k.cls_of(a) == "board")
    lid = _enact(k, f'def on_enact():\n    state["r"] = [grant("{board}", "propose"), limit_actions("{board}", 1, 1), '
                    f'set_dm_limit(2, "{board}"), suspend("{board}", "veto", 1), burn("nothing", 1, "{board}")]')
    assert k.w["laws"][lid]["state"]["r"] == [False, False, False, False, False]
    assert k.w["effects"]["kernel_refusals"] == ["grant propose to board " + board, "limit_actions on board",
                                                 "set_dm_limit on board", "suspend veto"]


def test_chain_and_root_frames(k):
    from charter import actions as A
    assert k.chain() == () and k.cascade() is None
    seen = {}
    real = k.apply

    def spy(name, /, **payload):
        seen.setdefault(name, k.chain())
        return real(name, **payload)
    k.apply = spy
    a, b = k.roster()[0], k.roster()[2]
    k.begin_round_cause(phase="turns")
    with k.cause("turn", a, call="r0:x:0"):
        A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
        assert k.cascade() is None                                       # the action's cascade closed with its frame
    k.end_round_cause()
    assert seen["move"] == ({"kind": "action", "id": "action:transfer"},)
    assert [f["kind"] for f in k.current_cause()] == []
    ev = next(e for e in reversed(k.events) if e["type"] == "move")
    assert ev["cause"] == [{"round": 0}, {"phase": "turns"}, {"turn": a, "call": "r0:x:0"}, {"action": "transfer"}]   # unchanged
    from charter import dispatch as D
    assert D.chain_for(k, "move") == ({"kind": "kernel", "id": "kernel:move"},)                                       # implicit root
    with k.cause("action", "x", root=True):
        with k.cause("action", "y", root=True):                          # a nested root joins the outer cascade
            assert len(k._cascade_stack()) == 1 and [f["id"] for f in k.chain()] == ["action:x", "action:y"]
        with k.cause("law", "L1", hook="on_dm"):
            assert k.chain(viewer="L1")[-1] == {"kind": "law", "id": "law:L1", "hook": "on_dm"}


def test_law_caused_moves_fire_no_legacy_hook(k):
    """review 09 §2.1 fact 7, now as an alias filter: on_transfer fires for an agent's transfer only (root kind action)."""
    from charter import actions as A
    a, b = k.roster()[0], k.roster()[2]
    _enact(k, 'def on_transfer(src, dst, item, qty):\n    state["n"] = state.get("n", 0) + 1\n    return 0.5\n')
    lid = next(iter(k.w["laws"]))
    k.move(a, b, "timber", 1, why="transfer")                            # outside any action: the implicit kernel root
    assert k.w["laws"][lid]["state"].get("n") is None
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 2})
    assert k.w["laws"][lid]["state"]["n"] == 1
    moves = [e["data"] for e in k.events if e["type"] == "move"][-2:]
    assert [(m["qty"], m["why"]) for m in moves] == [(1.5, "transfer"), (0.5, "transfer_tax")]


if __name__ == "__main__":                                              # re-record (only on the pre-P2.1 revision)
    FIXTURE.write_text(json.dumps(record(), indent=0, sort_keys=True))
    print("wrote", FIXTURE)
