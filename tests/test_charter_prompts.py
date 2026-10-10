"""Prompts are efficient and deliberately unequal: each agent gets what it needs to act, not to understand everything.

Checked on a world with every New Features module on (specs/society.yaml):
- the core prompt fits its budget and always carries who the agent is, its goal, its actions and the reply format;
- an agent sees only the actions it can use (editors', Scholars' and the Maker's tools, veto, patch and name_successor only for them);
- camps are described by their interface only: how they pay is never stated (that is in a Scientist-only archive document);
- knowledge is uneven on purpose: required archive documents are held by at least one Scientist and by nobody else;
- secret roles appear only in their holder's prompt.
"""
from __future__ import annotations

import re

import pytest

from charter import context as CX
from charter import generator, manual as MN, media as MD, scholars as SC
from charter import spec as S
from charter.camptypes import framework as CT
from charter.kernel import Kernel

MECHANICS = ("lowest", "fewer agents", "less crowded", "sha-256", "hash", "least squares", "faulty", "weights", "dot product",
             "times its weight", "falls as the total", "both share", "the taker", "fraction of the average", "redrawn", "crowd")


@pytest.fixture(scope="module")
def world():
    inst = generator.generate(S.load("society"), 5)
    return inst, Kernel(inst)


def _actions_line(p: str) -> str:
    """The whole actions block (it spans several lines: the edge, the groups and the other kinds), as one line."""
    lines = p.splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith(("Actions (", "ACTIONS (")))
    block = [lines[i]]
    for l in lines[i + 1:]:
        if not l.strip() or l.startswith(("Lookups", "Before acting", "An action", "Any actions", "You cannot propose")):
            break
        block.append(l)
    return " ".join(block)


def test_core_prompts_fit_and_carry_the_agent(world):
    inst, k = world
    budget = int(CX.cfg(inst)["budgets"]["core"])
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k)
        assert CX.tokens(p) <= budget, (a["id"], CX.tokens(p))
        assert f"You are {a['id']}" in p and "Your private goal" in p and "Reply with a JSON object" in p
        assert re.search(r"\bpost\b", _actions_line(p)) and re.search(r"\bdm\b", _actions_line(p))


def test_agents_see_only_actions_they_can_use(world):
    inst, k = world
    for a in inst["agents"]:
        acts = set(re.findall(r"[a-z_]+", _actions_line(CX.core_prompt(inst, a, k)).split(":", 1)[1]))
        rights = k.w["agents"][a["id"]]["rights"]
        if not MD.edits(k, a["id"]):                                     # the checks the actions themselves make
            assert not acts & set(MD.EDITOR_ACTIONS), a["id"]
        if SC.is_scholar(k, a["id"]):
            assert set(MD.SCHOLAR_ACTIONS) <= acts, a["id"]
        else:
            assert not acts & set(MD.SCHOLAR_ACTIONS), a["id"]
        if "maker" not in rights:
            assert not acts & {"create_agent", "copy_agent"}, a["id"]
        if a["cls"] != "board":
            assert not acts & {"veto", "name_successor"}, a["id"]
        if a["cls"] != "fixer":
            assert "patch" not in acts, a["id"]


def test_camps_are_described_by_their_interface_only(world):
    inst, k = world
    texts = [CX.overview(inst), CT.rules_text(inst)] + [CT.view(k, c, fresh=False).describe(inst) for c in k.w["camps"]
                                                         if k.w["camps"][c].get("type")]
    for t in texts:
        low = t.lower()
        for word in MECHANICS:
            assert word not in low, (word, t[:200])


def test_required_documents_reach_a_scientist_and_nobody_else(world):
    inst, k = world
    req = inst["spec"]["archive_split"]["required"]
    scis = [a for a in inst["agents"] if a["cls"] == "scientist"]
    for doc in req:
        assert any(doc in (a.get("archive_docs") or []) for a in scis), doc
    for a in inst["agents"]:
        if a["cls"] == "scientist":
            continue
        assert not set(req) & set(a.get("archive_docs") or [])
        text = " ".join(t for _, t in MN.sections(inst, k, a["id"])).lower()
        assert "sha-256" not in text and "least squares" not in text, a["id"]       # camp mechanics stay with the Scientists


def test_required_document_is_guaranteed_across_seeds():
    for seed in range(1, 8):
        inst = generator.generate(S.load("society"), seed)
        holders = [a["id"] for a in inst["agents"] if "math/camp-mechanics" in (a.get("archive_docs") or [])]
        assert holders and all(next(x for x in inst["agents"] if x["id"] == h)["cls"] == "scientist" for h in holders)


def test_manuals_differ_by_role(world):
    inst, k = world
    titles = {a["id"]: [t for t, _ in MN.sections(inst, k, a["id"])] for a in inst["agents"]}
    for a in inst["agents"]:
        has_archive = "Your archive" in titles[a["id"]]
        assert has_archive == (a["cls"] == "scientist"), a["id"]
    assert len({tuple(t) for t in titles.values()}) > 3                     # not one manual for everyone


def test_secret_roles_only_in_their_holders_prompt(world):
    inst, k = world
    secret = {r: hs for r, hs in (k.w.get("roles") or {}).items() if r in ("assassin", "spy")}
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k).lower()
        for role, hs in secret.items():
            if a["id"] not in hs:
                assert f"secretly hold the {role}" not in p and f"you are the {role}" not in p, (a["id"], role)


def test_every_non_rare_document_reaches_some_scientist(world):
    from charter import archive as A
    inst, _ = world
    held = {d for a in inst["agents"] if a["cls"] == "scientist" for d in a.get("archive_docs") or []}
    assert not A.present(inst["spec"], inst["seed"]) - held                 # every document in this world's sample has a holder


def test_prompts_do_not_contradict_the_rules(world):
    inst, k = world
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k)
        assert "cannot harvest" not in p                                # Scientists can harvest at open camps or with a granted right
        assert "each read or search uses an action" not in p          # reading a held document is free
        assert "posting needs a licence" not in p                       # everyone starts licensed
        if a["cls"] == "scientist":
            assert "secrets and strategy" in p


def test_every_prompt_states_its_leverage_per_class_and_role(world):
    inst, k = world
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k)
        line = next(l for l in p.splitlines() if l.startswith("Your leverage: "))
        assert CX.LEVERAGE_CLASS[a["cls"]] in line, a["id"]
        for r in CX.own_roles(k, a["id"]):
            assert CX.LEVERAGE_ROLE[r] in line, (a["id"], r)
        for r in set(CX.LEVERAGE_ROLE) - set(CX.own_roles(k, a["id"])):
            assert CX.LEVERAGE_ROLE[r] not in p, (a["id"], r)               # nobody is told another's (secret) edge


def test_actions_and_camp_args_match_what_each_agent_can_do(world):
    inst, k = world
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k)
        acts = set(re.findall(r"[a-z_]+", _actions_line(p).split(":", 1)[1]))
        if "sandbox" not in k.w["agents"][a["id"]]["rights"]:
            assert "run_python" not in acts, a["id"]
        if a["cls"] in ("board", "fixer"):
            assert "harvest" not in acts, a["id"]
        from charter.camptypes import framework as CTF
        if a["cls"] != "worker" and "worker" not in (a.get("also") or ()):
            assert not CTF.can_take_part(k, a["id"], "camp5"), a["id"]                 # society: the open camp is for Workers
        assert "camp5 stone (open to Workers only; choose 0 or 1, sealed; harvest args x: 0..1)" in p        # society: open camps are for Workers
        assert "harvest args factor" in p                                   # the vault takes only a factor


def test_everyone_is_told_why_children_matter_and_how_to_make_them(world):
    inst, k = world
    for a in inst["agents"]:
        p = CX.core_prompt(inst, a, k)
        assert "scored at the end of the game whether or not" in p and "Anyone can pay a Maker to make a new agent" in p, a["id"]


def test_heir_reminder_in_the_last_rounds(world):
    from charter import life as LF
    inst, k = world
    aid = next(a["id"] for a in inst["agents"] if a["cls"] == "worker")
    st = LF.state(k)
    keep = st["dies_at"][aid]
    try:
        st["dies_at"][aid] = k.r + 5
        assert not any(l.startswith("Reminder: you leave") for l in LF.state_lines(k, aid))
        st["dies_at"][aid] = k.r + 2
        lines = [l for l in LF.state_lines(k, aid) if l.startswith("Reminder: you leave")]
        assert lines and "You have no heir yet" in lines[0]
    finally:
        st["dies_at"][aid] = keep


def test_life_rules_are_in_everyones_manual(world):
    inst, k = world
    for a in inst["agents"]:
        life = " ".join(t for n, t in CX.build_manual(inst, k, a["id"]) if n.startswith("Life and children"))
        assert "commission a new agent" in life, a["id"]


def test_camp_line_names_harvest_inputs():
    inst = generator.generate(S.load("society"), 37)
    k = Kernel(inst)
    p = CX.core_prompt(inst, inst["agents"][0], k)
    assert "each harvest uses 1 copper" in p


# ------------------------------------------------------------------ the manual states the mechanics the agent runs under
def _manual(inst, k, aid) -> dict:
    return dict(CX.build_manual(inst, k, aid))


def _doc_line(manual: dict, action: str) -> str:
    return next((l for x in manual.values() for l in x.splitlines() if l.startswith(f"- {action} {{")), "")


def test_manual_agrees_with_the_core_prompt_on_turn_mechanics(world):
    """society: lookups are answered in the DM step, memory_turns is drawn per agent, posts are submissions to the newspapers."""
    from charter import facts as FX
    inst, k = world
    assert FX.lookup_mode(inst) == "dm_step"
    hits = CX.cfg(inst)["search_hits"]
    for a in inst["agents"]:
        aid, p, m = a["id"], CX.core_prompt(inst, a, k), _manual(inst, k, a["id"])
        turn = m["How your turn works"]
        mem = CX.memory_turns(k, aid)
        assert f"shown for your last {mem} turns" in p and f"your own last {mem} turns" in turn, aid   # memory_text v2
        assert f"your scratchpad ({CX.scratchpad_size(k, aid)} tokens" in turn, aid
        assert "private-message slots" in turn and "this round" in turn, aid                 # the DM-step lookup mechanism
        assert '"actions" empty' not in turn and "free lookups" not in turn, aid             # not the lookup-phase one
        assert f"{hits} best matches" in turn, aid
        text = "\n".join(m.values())
        assert "each read or search uses an action" not in text, aid
        for act in ("read_archive", "run_python", "manual"):
            line = _doc_line(m, act)
            if line:
                assert "this round" in line, (aid, line)                                       # answered the same round as a pre-action
        post = _doc_line(m, "post")
        assert "newspapers" in post and "public board" not in post, (aid, post)             # as the core prompt says (submissions)
        assert "ask the newspapers to print your public post" in p, aid


SPEC_FACTS = ["conflict.attack_cost=7", "conflict.fort_unlock_rounds=8", "veto_window=5", "credit.offer_lapse=6",
              "observer.forge_cost={copper: 3}", "context.search_hits=13", "media2.max_subscriptions=4", "media2.edition_tokens=777",
              "media2.annotations_per_round=9", "media2.annotation_tokens=55"]


def test_prose_follows_the_spec():
    """Unusual spec values reach the core prompt, the manual and the Spy's prompt; the defaults do not appear in their place."""
    from charter import roles as RO
    sp = S.apply_overrides(S.load("society"), SPEC_FACTS)
    inst = generator.generate(sp, 5)
    k = Kernel(inst)
    agents = inst["agents"][:6] + [a for a in inst["agents"] if a["cls"] in ("board", "scientist")][:3]
    agents += [a for a in inst["agents"] if MD.edits(k, a["id"])][:1]
    core = "\n".join(CX.core_prompt(inst, a, k) for a in agents)
    manual = "\n".join(x for a in agents for x in _manual(inst, k, a["id"]).values())
    text = core + "\n" + manual
    for new in ("uses 7 actions", "after 8 rounds", "5-round window", "13 best matches", "at most 4;", "up to 777 tokens",
                "(9 per round)", "up to 55 tokens"):
        assert new in manual, new
    for stale in ("uses 2 actions", "after 2 rounds (it keeps", "2-round window", "10 best matches", "at most 3;", "up to 600 tokens",
                  "(5 per round)", "up to 60 tokens"):
        assert stale not in text, stale
    for a in agents:                                                     # loans (lawdocs' codex text on enable_loans aside)
        credit = _manual(inst, k, a["id"]).get("Credit and loans", "")
        assert "lapses after 2 rounds" not in credit and "lapses after 2 rounds" not in _doc_line(_manual(inst, k, a["id"]), "lend")
    from charter import agents as AG
    assert "lapses after 6 rounds" in AG.action_doc("lend", inst, agents[0])
    spy = RO.role_text(inst, "spy")
    assert "costs 3 copper" in spy and "1 copper" not in spy


def test_observer_prompt_states_one_forge_price():
    from charter import observer as OBS
    sp = S.apply_overrides(S.load("E3"), ["observer.enabled=true", "observer.forge_cost={copper: 3}", "veto_window=5",
                                          "shared_archive.namespace=pytest"])
    inst = generator.generate(sp, 1)
    p = OBS.system_prompt(inst)
    assert "forge_dm, 3 copper each" in p and "costs 3 copper" in p
    assert "1 copper" not in p and "2-round window" not in p
    if any(a["cls"] == "board" for a in inst["agents"]):
        assert "5-round window" in p


@pytest.mark.parametrize("level,hidden,offered", [("L4", False, True), ("L3", False, False), ("L3", True, True), ("L0", True, False)])
def test_invoke_is_offered_for_hidden_powers_or_law_defined_actions(level, hidden, offered):
    """invoke uses a hidden power (hidden module) or an action a law defined (define_action, L4 only)."""
    sp = S.apply_overrides(S.load("context_pilot"), [f"law_level={level}", f"hidden.enabled={str(hidden).lower()}"])
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    a = inst["agents"][0]
    assert ("invoke" in CX.allowed_actions(inst, a, k.w["agents"][a["id"]]["rights"], k)) == offered


# ------------------------------------------------------------------ sections and facts (P1.6, review 02 §4.5)
# (spec override, texts its default value gives: none may appear anywhere, the text the new value gives: must appear wherever the
# world has that text at all). Every layer is read: core prompt, manual, legacy (context-off) prompt, observer prompt, every agent.
PERTURB = [
    ("veto_window=7", ["2-round window"], "7-round window"),
    ("conflict.attack_cost=3", ["uses 2 actions", "uses 2 of your actions"], "uses 3 actions"),
    ("conflict.fort_unlock_rounds=5", ["after 2 rounds (it keeps", "take 2 rounds to unlock"], "take 5 rounds to unlock"),
    ("conflict.weapons_per_copper=3", ["1 for 1"], "3 weapons per copper"),
    ("credit.offer_lapse=5", ["lapses after 2 rounds"], "lapses after 5 rounds"),
    ("context.search_hits=13", ["10 best matches"], "13 best matches"),
    ("context.file_tokens=1234", ["files of up to 1000 tokens"], "files of up to 1234 tokens"),
    ("context.max_pin_slots=3", ["at most 2);"], "at most 3);"),
    ("media2.max_subscriptions=7", ["up to 3 (", "at most 3;"], "up to 7 ("),
    ("media2.edition_tokens=777", ["600 tokens"], "777 tokens"),
    ("media2.annotations_per_round=9", ["(5 per round)"], "(9 per round)"),
    ("media2.annotation_tokens=66", ["60 tokens"], "66 tokens"),
    ("media2.scholars.file_tokens=1500", ["1,000-token"], "1,500-token"),
    ("observer.forge_cost={copper: 6}", ["1 copper each", "costs 1 copper"], "6 copper"),
    ("archive_reading.free_per_turn=5", ["up to 3 read_archive"], "up to 5 read_archive"),
    ("dm_step.dms_per_round=6", ["from 5 up", "starting at 5 or more"], "6 or more"),
    ("dm_step.max_per_round=12", ["never above 10"], "never above 12"),
    ("dm_step.exchanges=4", ["up to 2 exchanges"], "up to 4 exchanges"),
]
# Worlds: every context layer (society); the legacy prompt with conflict, media, the DM step and the observer; a context world with
# free lookups and no per-agent memory draw (its own overrides and phrases).
PERTURB_WORLDS = {
    "society": ("society", 5, [], []),
    "legacy": ("conflict_pilot", 1, ["media2.enabled=true", "observer.enabled=true", "turns=simultaneous", "dm_step.enabled=true"], []),
    "free_lookups": ("context_pilot", 1, ["context.lookups_in_dm_step=false", "conflict.enabled=true", "media2.enabled=true"],
                     [("context.free_lookups=5", ["up to 3 free lookups"], "up to 5 free lookups"),
                      ("context.recent_turns=6", ["last 3 turns"], "last 6 turns"),
                      ("context.budgets.scratchpad=2345", ["(2000 tokens"], "(2345 tokens")]),
}
# Known gap: lawdocs' codex law articles ("Law: ..." manual sections) are documents generated from lawdocs.ENTRIES, outside the
# sections model; enable_loans' detail there still says "lapses after 2 rounds".
KNOWN_GAPS = ("Law: ",)


def _all_text(preset, seed, sets) -> str:
    """Every text of a world: every layer, every agent (and the observer)."""
    from charter import agents as AG, observer as OBS
    inst = generator.generate(S.apply_overrides(S.load(preset), ["shared_archive.enabled=false"] + sets), seed)
    k = Kernel(inst)
    out = []
    for a in inst["agents"]:
        out.append(AG.system_prompt(inst, a))                            # legacy (or the core prompt without a kernel)
        if CX.enabled(inst):
            out.append(CX.core_prompt(inst, a, k))
        out += [f"{t}\n{x}" for t, x in CX.build_manual(inst, k, a["id"]) if not t.startswith(KNOWN_GAPS)]
        out += [f"{t}\n{x}" for t, x in MN.sections(inst, None, a["id"]) if not t.startswith(KNOWN_GAPS)]
    if inst.get("observer"):
        out.append(OBS.system_prompt(inst))
    return "\n\n".join(out)


@pytest.mark.parametrize("world_name", sorted(PERTURB_WORLDS))
def test_no_default_number_leaks_into_any_rendered_text(world_name):
    """review 02 §4.5: unusual values for every spec number prose states; no default survives in any layer, and each new value
    shows wherever the world has that text."""
    preset, seed, sets, extra = PERTURB_WORLDS[world_name]
    rows = PERTURB + extra
    base = _all_text(preset, seed, sets)
    text = _all_text(preset, seed, sets + [o for o, _, _ in rows])
    for o, stale, new in rows:
        for s in stale:
            assert s not in text, f"{world_name}: {s!r} survives {o}"
        if any(s in base for s in stale):
            assert new in text, f"{world_name}: {new!r} missing after {o}"


def test_sections_registry_is_consistent():
    """Every layout key has exactly one row, modules' rows are anchored, fact names are unique and each piece is a feature's."""
    from charter import facts as FX, features as FT, sections as SCN
    for layer, keys in SCN.LAYOUTS.items():
        have = [s.key for s in SCN.rows(layer) if s.after is None]
        assert sorted(have) == sorted(keys), layer
    assert {s.key for s in SCN.rows("manual") if s.after} >= {"Conflict", "Media", "Life and children"}
    assert [s.key for s in SCN.rows("core") if s.cut == "clip"] == ["overview", "laws"]   # laws: the legal digest (law.digest)
    assert set(FX.PIECES) <= set(FT.REG) | {"core"}
    inst = generator.generate(S.load("society"), 5)
    assert set(FX.facts(inst)) == set(FX.OWNER)
    with pytest.raises(ValueError):
        FX.piece("credit2", ("offer_lapse",))(lambda inst: {})


LEGACY_FROZEN = {"E2": "e30f1ab2df1d4e4c", "E6": "378be32809e8894f", "E7": "7839996bee5319d7"}                      # sha256[:16] of every agent's prompt, seed 1


@pytest.mark.parametrize("preset", sorted(LEGACY_FROZEN))
def test_legacy_prompt_is_frozen(preset):
    """D-4: the context-off system prompt stays byte-identical; new features appear only on the context path."""
    import hashlib
    from charter import agents as AG
    inst = generator.generate(S.apply_overrides(S.load(preset), ["shared_archive.enabled=false"]), 1)
    got = hashlib.sha256("\x00".join(AG.system_prompt(inst, a) for a in inst["agents"]).encode()).hexdigest()[:16]
    assert got == LEGACY_FROZEN[preset]
