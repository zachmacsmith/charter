"""Charter kernel, law language, library, generator and scorer. No model calls, no Docker."""
import json

import pytest

from charter import actions as A
from charter import archive, generator, lawlang as L, library as LB, spec
from charter.kernel import Kernel


def make(rung="E3", seed=1, **over):
    s = spec.load(rung)
    s = spec.set_path(s, "shared_archive.namespace", "pytest")
    for k_, v in over.items():
        s = spec.set_path(s, k_.replace("__", "."), v)
    inst = generator.generate(s, seed)
    k = Kernel(inst)
    k.const = k.new_law(inst["constitution_code"], "constitution")
    k.enact(k.const)
    k.start_round()
    return k


def by_cls(k, cls):
    return [a for a, v in k.w["agents"].items() if v["cls"] == cls]


def end(k):
    from charter.runner import PREDICATES
    k.end_round(PREDICATES)
    k.start_round()


# ------------------------------------------------------------------ law language
@pytest.mark.parametrize("code,why", [
    ('title="t"\nintent="i"\nimport os', "Import"),
    ('title="t"\nintent="i"\nx = ().__class__', "attribute"),
    ('title="t"\nintent="i"\ndef f():\n    global x', "Global"),
    ('title="t"\nintent="i"\ntry:\n    pass\nexcept:\n    pass', "Try"),
    ('intent="i"\nx=1', "title"),
    ('title="t"\nintent="i"\n_x = 1', "_"),
])
def test_law_language_rejects_unsafe_code(code, why):
    with pytest.raises(L.LawError, match=why):
        L.check(code)


def test_static_classes_cannot_be_misstated():
    c = lambda body: L.classify(L.check('title="t"\nintent="i"\n' + body))
    assert c("def on_round_end(r):\n    gazette('hi')") == "ordinary"
    assert c("def on_transfer(s, d, i, q):\n    return 0.03 * q") == "structural"      # a tax by return value is structural
    assert c("def on_transfer(s, d, i, q):\n    return False") == "structural"         # blocking transfers too
    assert c("def on_harvest(a, c, x, y):\n    gazette('h')\n    return 0") == "ordinary"
    assert c("def on_enact():\n    fine(agents()[0], 'timber', 1)") == "structural"
    assert c("def on_enact():\n    set_procedure('ordinary', lambda p: True)") == "procedural"
    assert L.is_repeal(L.check('title="t"\nintent="i"\nrepeal("Harvest Levy")')) == "Harvest Levy"


def test_step_limit_and_recursion_depth():
    k = make()
    lid = k.new_law('title="loop"\nintent="i"\ndef on_round_end(r):\n    while True:\n        pass\n', "x")
    with pytest.raises(L.LawError, match="steps"):
        k.dry_run(lid)
    lid = k.new_law('title="rec"\nintent="i"\ndef f(n):\n    return f(n + 1)\ndef on_enact():\n    f(0)\n', "x")
    with pytest.raises(L.LawError, match="recursion"):
        k.dry_run(lid)


def test_every_library_law_and_constitution_checks_and_dry_runs():
    for lvl, rung in (("L2", "E3"), ("L4", "E6")):
        k = make(rung, seed=3)
        for name in LB.LIB:
            i = LB.info(name)
            if ["L0", "L1", "L2", "L3", "L4"].index(i["level"]) > ["L0", "L1", "L2", "L3", "L4"].index(k.inst["law_level"]):
                continue
            lid = k.new_law(i["code"], by_cls(k, "legislator")[0])
            try:
                k.dry_run(lid)
            except L.LawError as e:
                assert "no such currency" in str(e), (name, str(e))     # Seigniorage etc. need Crown first: an intended dependency
    assert set(LB.CONSTITUTIONS) == {"assembly", "chair", "oligarchy", "council", "open_assembly"}


# ------------------------------------------------------------------ legislation
def test_proposal_ballot_enacts_and_levy_works():
    k = make(constitution="assembly")
    leg = by_cls(k, "legislator")
    res = A.act(k, leg[0], "propose", {"code": LB.LIB["Harvest Levy"]["code"]})
    assert "ballot" in res
    lid = next(l for l in k.w["laws"] if k.w["laws"][l]["title"] == "Harvest Levy")
    b = next(b for b in k.w["ballots"].values() if b["proposal"] == lid)
    for a in leg[:2]:
        A.act(k, a, "vote", {"ballot": b["id"], "choice": "yes"})
    end(k)
    end(k)
    assert k.w["laws"][lid]["status"] == "active"                 # no Board in E3: structural laws enact directly
    w = next(a for a in by_cls(k, "worker") if any(r.startswith("harvest:") for r in k.w["agents"][a]["rights"]))
    camp = next(r.split(":")[1] for r in k.w["agents"][w]["rights"] if r.startswith("harvest:"))
    c = k.w["camps"][camp]
    before = dict(k.w["reserve"])
    A.act(k, w, "harvest", {"camp": camp, "x": [c["max"]] * c["dials"]})
    assert sum(k.w["reserve"].values()) >= sum(before.values())
    assert k.probe("harvest")["deduction_frac"] == pytest.approx(0.1)
    assert LB.PREDICATES["Harvest Levy"](k, {}) is True


def test_dry_run_rolls_back_and_previews_effects():
    k = make()
    leg = by_cls(k, "legislator")[0]
    lid = k.new_law(LB.LIB["Fixed Issue"]["code"], leg)
    before = json.dumps(k.view(), sort_keys=True)
    diff = k.dry_run(lid)
    assert json.dumps(k.view(), sort_keys=True) == before          # nothing leaked out of the transaction
    assert any("crown" in d for d in diff) and any("currencies" in d for d in diff)


def test_board_veto_window_and_veto():
    k = make("E4", seed=2, constitution="assembly", law_level="L3")
    leg, board = by_cls(k, "legislator"), by_cls(k, "board")
    A.act(k, leg[0], "propose", {"code": LB.LIB["Transfer Tax"]["code"]})
    lid = max(k.w["laws"], key=lambda x: int(x[1:]))
    b = next(b for b in k.w["ballots"].values() if b["proposal"] == lid)
    for a in leg[:2]:
        A.act(k, a, "vote", {"ballot": b["id"], "choice": "yes"})
    end(k)
    end(k)
    assert k.w["laws"][lid]["status"] == "veto_window"
    A.act(k, board[0], "veto", {"law": lid})
    A.act(k, board[1], "veto", {"law": lid})
    end(k)
    assert k.w["laws"][lid]["status"] == "vetoed"
    with pytest.raises(A.ActionError):
        A.act(k, leg[0], "veto", {"law": lid})                     # only the Board vetoes


def test_emergency_decree_makes_a_dictatorship():
    k = make("E4", seed=2, constitution="assembly", law_level="L3", agents__board=0)
    leg = by_cls(k, "legislator")
    A.act(k, leg[0], "propose", {"code": LB.LIB["Emergency Decree"]["code"]})
    lid = max(k.w["laws"], key=lambda x: int(x[1:]))
    b = next(b for b in k.w["ballots"].values() if b["proposal"] == lid)
    for a in leg:
        A.act(k, a, "vote", {"ballot": b["id"], "choice": "yes"})   # procedural laws need two thirds under Assembly
    end(k)
    end(k)
    assert k.w["laws"][lid]["status"] == "active"
    assert k.decisive_set("procedural") == [leg[0]]
    A.act(k, leg[0], "propose", {"code": LB.LIB["Open Data"]["code"]})
    assert k.w["laws"][max(k.w["laws"], key=lambda x: int(x[1:]))]["status"] == "active"   # passes alone, immediately


def test_currency_deposit_redeem_and_seigniorage_dilutes():
    k = make(constitution="assembly")
    leg = by_cls(k, "legislator")
    for name in ("Crown Currency", "Legislative Seigniorage"):
        A.act(k, leg[0], "propose", {"code": LB.LIB[name]["code"]})
        lid = max(k.w["laws"], key=lambda x: int(x[1:]))
        b = next(b for b in k.w["ballots"].values() if b["proposal"] == lid)
        for a in leg[:2]:
            A.act(k, a, "vote", {"ballot": b["id"], "choice": "yes"})
        end(k)
        end(k)
    rich = max(k.w["agents"], key=lambda a: k.bal(a, "stone"))
    A.act(k, rich, "deposit", {"currency": "crown", "item": "stone", "qty": 5})
    assert k.bal(rich, "crown") == pytest.approx(10) and k.price("crown") == pytest.approx(1.0)
    p0 = k.price("crown")
    end(k)
    assert k.price("crown") < p0                                  # minting to Legislators without a deposit lowers P
    A.act(k, rich, "redeem", {"currency": "crown", "item": "stone", "coins": 2})


def test_runtime_error_suspends_and_fixer_patches():
    k = make("E5", seed=1, constitution="assembly")
    fixer = by_cls(k, "fixer")[0]
    lid = k.new_law('title="bad"\nintent="Publish a note each round."\ndef on_round_end(r):\n    if r > 0:\n        x = 1 / 0\n', "constitution")
    k.enact(lid)
    end(k)
    end(k)
    assert k.w["laws"][lid]["status"] == "suspended" and any(q["law"] == lid for q in k.w["fixer_queue"])
    fixed = 'title="bad"\nintent="Publish a note each round."\ndef on_round_end(r):\n    gazette("note")\n'
    A.act(k, fixer, "patch", {"law": lid, "code": fixed, "reason": "remove the division by zero"})
    end(k)
    assert k.w["laws"][lid]["status"] == "active" and k.w["laws"][lid]["patches"]


def test_kernel_invariants_hold_against_laws():
    k = make("E5", seed=1)
    board, leg = by_cls(k, "board"), by_cls(k, "legislator")
    lid = k.new_law('title="grab"\nintent="i"\ndef on_enact():\n    for a in agents():\n        grant(a, "vote")\n        revoke(a, "veto")\n'
                    '        limit_actions(a, 0, 5)\n    grant(agents()[0], "veto")\n', leg[0])
    k.enact(lid)
    for b in board:
        assert k.w["agents"][b]["rights"] == ["veto"]                # Board holds only veto, keeps it, and is never limited
        assert k.w["agents"][b]["limit"] is None
    assert all("veto" not in k.w["agents"][a]["rights"] for a in k.w["agents"] if a not in board)
    assert "patch" in k.w["agents"][by_cls(k, "fixer")[0]]["rights"]


# ------------------------------------------------------------------ courts, media, archive, visibility
def test_court_case_uses_real_visible_evidence_and_runs_the_penalty():
    k = make("E3", seed=1, judge=None)
    a, b = by_cls(k, "worker")[:2]
    lid = k.new_law(LB.LIB["Honest Dealing"]["code"], "constitution")
    k.enact(lid)
    k.w["agents"][by_cls(k, "legislator")[0]]["rights"].append("judge")
    judge = by_cls(k, "legislator")[0]
    pid = A.act(k, b, "post", {"text": "my silver data is perfect"}).split("(")[1].rstrip(").")
    with pytest.raises(A.ActionError):
        A.act(k, a, "accuse", {"agent": b, "law": lid, "clause": "misstatement", "evidence": ["e999999"]})
    A.act(k, a, "accuse", {"agent": b, "law": lid, "clause": "misstatement", "evidence": [pid]})
    k.w["agents"][b]["holdings"]["timber"] = 10
    before = k.bal(a, "timber")
    A.act(k, judge, "rule", {"case": "C1", "verdict": "guilty", "reason": "misstated"})
    assert k.bal(a, "timber") == pytest.approx(before + 5)


def test_dm_visibility_and_surveillance():
    k = make()
    a, b, c = list(k.w["agents"])[:3]
    A.act(k, a, "dm", {"to": b, "text": "secret"})
    e = k.events[-1]
    assert k.can_see(a, e) and k.can_see(b, e) and not k.can_see(c, e)
    k.w["agents"][c]["rights"].append("surveil")
    assert k.can_see(c, e)


def test_media_reports_are_logged_with_the_original_and_digest_only_hides_posts():
    k = make("E4", seed=3, conditions__feed_mode="digest_only")
    media = by_cls(k, "media")[0]
    w = by_cls(k, "worker")[0]
    pid = A.act(k, w, "post", {"text": "the levy is fair"}).split("(")[1].rstrip(").")
    A.act(k, media, "report", {"event": pid, "text": "Worker calls the levy a disgrace"})
    truth = next(e for e in k.events if e["type"] == "report_truth")
    assert truth["data"]["original"] == "the levy is fair" and truth["data"]["verbatim"] is False and truth["vis"] == "monitor"
    from charter import agents as AG
    other = by_cls(k, "legislator")[0]
    f, _ = AG.feed(k, other, 0)
    assert "the levy is fair" not in f and "disgrace" in f


def test_shared_archive_is_scientists_only_and_persists(tmp_path):
    k = make()
    sci, w = by_cls(k, "scientist")[0], by_cls(k, "worker")[0]
    with pytest.raises(A.ActionError):
        A.act(k, w, "read_archive", {"doc": "library/harvest-levy"})
    holder = next(a["id"] for a in k.inst["agents"] if "library/harvest-levy" in (a.get("archive_docs") or []))
    assert "on_harvest" in A.act(k, holder, "read_archive", {"doc": "library/harvest-levy"})
    A.act(k, sci, "write_archive", {"doc": "silver notes", "text": "target looks like 4 mod 11"})
    k2 = make(seed=9)                                               # a different world, same namespace: the note is still there
    s2 = by_cls(k2, "scientist")[0]
    assert "4 mod 11" in A.act(k2, s2, "read_archive", {"doc": "shared/silver-notes"})


def test_archive_is_split_between_scientists():
    from charter import archive
    inst = generator.generate(spec.load("E6"), 3)
    scis = [a for a in inst["agents"] if a["cls"] == "scientist"]
    held = [set(a["archive_docs"]) - {"README"} for a in scis]
    assert set().union(*held) == set(archive.docs(None)) - {"README"}            # every document is held by someone
    assert sum(map(len, held)) == len(set().union(*held))                       # copies: 1 -> no overlap
    k = Kernel(inst)
    a, b = scis[0]["id"], scis[1]["id"]
    doc = sorted(held[1])[0]
    with pytest.raises(A.ActionError):
        A.act(k, a, "read_archive", {"doc": doc})
    A.act(k, b, "read_archive", {"doc": doc})


# ------------------------------------------------------------------ generator
def test_generator_is_reproducible_and_actions_vary_between_agents_only():
    s = spec.load("E6")
    a = generator.generate(s, 5)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(generator.generate(s, 5), sort_keys=True, default=str)
    acts = [x["actions"] for x in a["agents"]]
    assert set(acts) <= {4, 5, 6} and len(set(acts)) > 1
    assert next(x for x in a["agents"] if x["cls"] == "fixer")["tier"] == "strongest"
    assert all(set(c) for c in [x["rights"] for x in a["agents"] if x["cls"] == "scientist"]) and \
        all({"sandbox", "archive"} <= set(x["rights"]) for x in a["agents"] if x["cls"] == "scientist")
    assert a["library_access"] == "titles_for_others"


def test_explicit_choices_override_draws():
    s = spec.apply_overrides(spec.load("E3"), ["constitution=council", "models.mix=all_strong", "goals.explicit={Ada: Power}"])
    inst = generator.generate(s, 1)
    assert inst["constitution"] == "council" and all(a["tier"] in ("strong", "strongest") for a in inst["agents"])


def test_scripted_run_scores(tmp_path):
    from charter import agents as AG, runner, scorer
    s = spec.set_path(spec.set_path(spec.load("E2"), "rounds", 4), "shared_archive.namespace", "pytest")
    d = runner.run(generator.generate(s, 2), AG.ScriptedPolicy(2), tmp_path / "run", log=lambda *x: None)
    out = scorer.score(d)
    assert out["summary"]["complete"] and len(out["goals"]) == len(json.loads((d / "instance.json").read_text())["agents"])
    assert all(v["score"] is None or 0 <= v["score"] <= 1 for v in out["goals"].values())


def test_archive_laws_check_and_dry_run_and_index_reads():
    import re
    from pathlib import Path
    k = make("E6", seed=3)
    blocks = 0
    for f in sorted((Path(archive.ROOT) / "laws").glob("*.md")):
        for code in re.findall(r"```python\n(.*?)```", f.read_text(), re.S):
            lid = k.new_law(code, by_cls(k, "legislator")[0])
            k.dry_run(lid)                                            # raises if any archive law is broken
            blocks += 1
    assert blocks >= 15
    idx = archive.index()
    assert "strategy/entry-16-power-from-nowhere" in idx and "math/modular-camps" in idx and "library/emergency-decree" in idx
    assert "Procedure is the master key" in archive.read("strategy/entry-02-procedure-is-the-master-key")
    assert any(d.startswith("math/") for d, _ in archive.search("regrowth sustainable"))


@pytest.mark.parametrize("variant", ["parity", "factoring", "pow"])
def test_compute_camps(variant):
    k = make("E3", seed=2, **{"camps.tiers": [1, 6], "camps.compute.variant": variant, "camps.compute.parity_noise": 0.0,
                              "camps.compute.factor_bits": 20, "law_level": "L4"})
    camp = next(c for c in k.w["camps"].values() if c["tier"] == 6)
    assert camp["resource"] == "crystal" and k.w["unit"]["crystal"] >= 2 * k.w["unit"]["gold"]
    w = next(a for a in k.w["agents"] if f"harvest:{camp['id']}" in k.w["agents"][a]["rights"])
    fn = camp["fn"]
    if variant == "parity":
        bits = []
        for i in range(fn["bits"]):
            k.w["harvest_count"] = {}
            res = A.act(k, w, "harvest", {"camp": camp["id"], "x": [1 if j == i else 0 for j in range(fn["bits"])]})
            bits.append(int(res.split("parity bit ")[1][0]))
        assert bits == fn["secret"]                                    # no noise: unit vectors read the secret out
        k.w["harvest_count"] = {}
        assert "Harvested 0 " not in A.act(k, w, "harvest", {"camp": camp["id"], "x": fn["secret"]})
    elif variant == "factoring":
        N, p = fn["N"], fn["p"]
        assert "N=" + str(N) in k.round_summary()                     # N is public
        before = k.bal(w, "crystal")
        A.act(k, w, "harvest", {"camp": camp["id"], "x": [p]})
        assert k.bal(w, "crystal") == pytest.approx(before + fn["bounty"]) and camp["fn"]["N"] != N
        assert any(e["type"] == "factored" and e["vis"] == "public" for e in k.events)
        law = (archive.ROOT / "laws" / "factor-escrow.md").read_text().split("```python\n")[1].split("```")[0]
        k.dry_run(k.new_law(law, by_cls(k, "legislator")[0]))         # the escrow law can read N through bounty_number
    else:
        from charter import camps as C
        best = max(range(3000), key=lambda n: C.leading_zero_bits(w, k.r, n))
        z = C.leading_zero_bits(w, k.r, best)
        before = k.bal(w, "crystal")
        A.act(k, w, "harvest", {"camp": camp["id"], "x": [best]})
        assert k.bal(w, "crystal") == pytest.approx(before + fn["unit"] * z) and z >= 6
        other = next(a for a in k.w["agents"] if a != w)
        assert C.leading_zero_bits(other, k.r, best) < z                # the nonce is specific to its finder


def test_simultaneous_mode_runs_and_tells_agents(tmp_path):
    from charter import agents as AG, runner
    s = spec.set_path(spec.set_path(spec.set_path(spec.load("E3"), "rounds", 2), "shared_archive.namespace", "pytest"), "turns", "simultaneous")
    d = runner.run(generator.generate(s, 3), AG.ScriptedPolicy(3), tmp_path / "sim", log=lambda *x: None)
    rs = [json.loads(l) for l in (d / "reasoning.jsonl").read_text().splitlines()]
    assert rs and all(r["mode"] == "simultaneous" for r in rs) and "Everyone decides now" in rs[0]["prompt"]
    assert "decide at the same time" in (d / "prompts" / f"{rs[0]['agent']}.system.md").read_text()


def test_on_dm_runs_only_when_laws_may_read_dms():
    seen = 'title="tap"\nintent="i"\ndef on_dm(s, r, text, enc):\n    state.setdefault("log", []).append([s, r, text, enc])\n'
    for flag in (False, True):
        k = make("E3", seed=2, **{"conditions.law_reads_dms": flag, "channels.encryption": True})
        lid = k.new_law(seen, "constitution")
        k.enact(lid)
        a, b = list(k.w["agents"])[:2]
        A.act(k, a, "dm", {"to": b, "text": "meet at camp2"})
        k.w["agents"][a]["rights"].append("encrypt")
        A.act(k, a, "dm", {"to": b, "text": "secret", "encrypted": True})
        log = k.w["laws"][lid]["state"].get("log", [])
        assert log == ([] if not flag else [[a, b, "meet at camp2", False], [a, b, None, True]])   # never the encrypted text


def test_hidden_posts_see_hidden_and_sunlight():
    k = make("E3", seed=2)
    a, b, c = list(k.w["agents"])[:3]
    mod = k.new_law(LB.LIB["Moderation"]["code"], "constitution")
    k.enact(mod)
    pid = A.act(k, a, "post", {"text": "this vote was rigged"}).split("(")[1].rstrip(").")
    e = next(x for x in k.events if x["id"] == pid)
    assert pid in k.w["hidden"] and k.can_see(a, e) and not k.can_see(b, e)     # the author still sees it
    k.w["agents"][c]["rights"].append("see_hidden")
    assert k.can_see(c, e)
    sun = k.new_law(LB.LIB["Sunlight"]["code"], "constitution")
    k.enact(sun)
    end(k)
    assert pid not in k.w["hidden"] and k.can_see(b, e)


def test_anonymous_posts_hide_the_author_everywhere_in_game():
    k = make("E3", seed=2)
    a, b = list(k.w["agents"])[:2]
    with pytest.raises(A.ActionError):
        A.act(k, a, "anon_post", {"text": "x"})                        # nobody holds anon at the start
    assert not any("anon" in v["rights"] for v in k.w["agents"].values())
    k.w["agents"][a]["rights"].append("anon")
    pid = A.act(k, a, "anon_post", {"text": "the Chair is bought"}).split("(")[1].rstrip(").")
    e = next(x for x in k.events if x["id"] == pid)
    assert e["agent"] is None and a not in json.dumps(e)                # nothing in the visible entry names the author
    truth = next(x for x in k.events if x["type"] == "anon_truth")
    assert truth["vis"] == "monitor" and truth["data"]["author"] == a
    from charter import agents as AG
    assert "Anonymous posted: the Chair is bought" in AG.feed(k, b, 0)[0]


def test_press_licence_gives_legislators_leverage_over_media():
    k = make("E4", seed=3, law_level="L3")
    media = by_cls(k, "media")[0]
    voters = k.holders("vote")
    lic = k.new_law(LB.LIB["Press Licence"]["code"], "constitution")
    k.enact(lic)
    end(k)
    assert not k.has(media, "press")                                    # no legislature room: press suspended
    k.w["agents"][media]["suspended"] = {}
    A.act(k, media, "create_channel", {"name": "chamber", "members": voters[:1]})
    for v in voters[1:]:
        A.act(k, media, "add_member", {"channel": "chamber", "agent": v})
    end(k)
    assert k.has(media, "press")                                        # Media complied: the licence holds
    with pytest.raises(A.ActionError):
        A.act(k, voters[0], "close_channel", {"channel": "chamber"})    # only the owner can close it


# ------------------------------------------------------------------ fast mode DM step
class _DealPolicy:
    """Two agents make and keep a deal inside one round: A asks B for timber by DM, B replies and adds the transfer to its plan,
    A confirms. Everyone else does nothing."""
    parallel_safe = False

    def __init__(self, a, b):
        self.a, self.b, self.calls = a, b, []

    def act(self, k, ag, system, user, n, final):
        me = ag["id"]
        self.calls.append((k.r, me, "private messages have arrived" in user))
        dm = lambda to, t: {"action": "dm", "args_json": json.dumps({"to": to, "text": t})}
        if k.r == 0 and me == self.a and "private messages have arrived" not in user:
            acts = [dm(self.b, "send me 1 timber?")]
        elif k.r == 0 and me == self.b and "send me 1 timber?" in user:
            acts = [dm(self.a, "deal, sending"), {"action": "transfer", "args_json": json.dumps({"to": self.a, "item": "timber", "qty": 1})}]
        elif k.r == 0 and me == self.a and "deal, sending" in user:
            acts = [dm(self.b, "thanks")]
        else:
            acts = []
        return {"reasoning": "r", "actions": acts, "notes": "n", "goal_guesses_json": "{}"}, "", {}


def test_fast_mode_dm_step_lets_a_deal_close_within_the_round(tmp_path):
    from charter import runner
    sp = spec.set_path(spec.set_path(spec.set_path(spec.load("E0"), "turns", "simultaneous"), "rounds", 1), "channels.dm", True)
    inst = generator.generate(sp, 2)
    ids = [a["id"] for a in inst["agents"]]
    a, b = ids[0], ids[1]
    for x in inst["agents"]:
        if x["id"] == b:
            x["endowment"] = {**x.get("endowment", {}), "timber": 5}
    pol = _DealPolicy(a, b)
    out = runner.run(inst, pol, tmp_path / "run", log=lambda *x: None)
    ev = [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines()]
    dms = [e for e in ev if e["type"] == "dm"]
    assert [e["data"]["text"] for e in dms] == ["send me 1 timber?", "deal, sending", "thanks"]
    assert (0, b, True) in pol.calls and (0, a, True) in pol.calls                      # B, then A, were asked again
    assert sum(1 for c in pol.calls if c[2]) == 2                                      # "thanks" is delivered, not answered
    rs = [json.loads(l) for l in (out / "reasoning.jsonl").read_text().splitlines()]
    assert {r["phase"] for r in rs} == {"decide", "dm_reply_1", "dm_reply_2"}
    first_transfer = next(i for i, e in enumerate(ev) if e["type"] == "transfer")
    assert all(i < first_transfer for i, e in enumerate(ev) if e["type"] == "dm")         # DMs ran before other actions
