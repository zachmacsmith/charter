"""W8b (review 12 WP1): the 31 L-route primitives of review 12 §2.14 are routed through Kernel.apply, so laws can hook them under
law.v2 (before_<p> may refuse, after_<p> reacts), while every world without law.v2 logs exactly what it logged before (routing adds
hooks, never events). Channels (found, admit, expel, dissolve with kind "channel"), offices (invoke), wills, licences, libraries and
the laws' own rule setters. A hidden jurisdiction's founding, invitations and charter stay secret from other polities' laws
(dispatch.hooks.SECRET), a sealed contract hides its parties (HIDE), and a blocked declaration keeps a jurisdiction hidden.
Offline: no model calls."""
from __future__ import annotations

import copy

import pytest

from charter import actions as A
from charter import dispatch as D
from charter import generator
from charter import jurisdictions as J
from charter import lawlang as LL
from charter import primitives as PR
from charter import spec as S
from charter import tiers as T
from charter.kernel import Kernel

W8B = ("found", "invite", "declare", "set_charter", "dissolve", "invoke", "commission", "set_will", "name_successor", "licence",
       "set_price", "library_doc", "library_permit", "set_capacity", "share_note", "offer_lease", "set_initiative", "hire_assassin",
       "set_money_rule", "set_title", "rename", "set_arms_rule", "set_lease_rules", "set_birth_rules", "set_succession_rule",
       "set_project_rule", "set_power_rule", "loan_terms", "loan_assign", "create_clause", "start_project")

_INST: dict = {}


def world(v2=True, preset="society", sets=()):
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
    return f'title = "{title}"\nintent = "test"\nstate = {{}}\n' + body


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def press_holder(k):
    return next(a for a in k.roster() if "press" in k.w["agents"][a]["rights"] and k.cls_of(a) not in ("board", "fixer"))


def others(k, but, n=2):
    return [a for a in k.roster() if a != but and k.cls_of(a) not in ("board", "fixer", "observer")][:n]


# ====================================================================== the registry
def test_the_31_rows_are_routed_law():
    assert len(W8B) == 31 and set(W8B) <= set(D.ROUTED)
    for n in W8B:
        p = PR.get(n)
        assert p.routed and p.tier == "L" and p.fn in p.sites, n
        assert callable(D._fn(p)), n
        assert set(D.OPTIONS[n]).isdisjoint(p.params), n
        assert PR.json_roundtrip(p), n
    assert not PR.TIER_OF["L-route"]
    assert [p.name for p in PR.PRIMITIVES.values() if not p.routed and p.tier.startswith("L")] == []
    assert {r.id for r in T.RULES if r.note == "L-route until W8b"} == {"C2", "D6", "I6", "R6"}


def test_their_hooks_pass_the_v2_check_and_are_documented():
    from charter import lawdocs as LD
    tree = __import__("ast").parse("def before_found(p, chain):\n    return None\ndef after_invoke(p, chain):\n    return None\n")
    LL.check_hooks(tree, True, D.ROUTED)                               # law.v2: hooks of routed primitives are legal
    art = LD.v2_article(contracts=False)["text"]
    for n in W8B:
        assert f"- `{n}`: before_{n}, after_{n}" in art, n


def test_the_change_functions_are_the_rows_fn():
    """Owner modules' change functions are the apply functions themselves where the signature fits (W8b), and the old do_* style
    in dispatch.changes where a primitive spans several owners (found, dissolve, set_price) or the kernel owns it."""
    owner = {n: PR.get(n).fn for n in W8B if not PR.get(n).fn.startswith("dispatch.")}
    assert owner["invoke"] == "actions:change_invoke" and owner["licence"] == "media:change_licence"
    assert PR.get("found").fn == "dispatch.changes.membership:do_found"
    assert all(fn.split(":")[1].startswith("change_") for fn in owner.values()), owner


# ====================================================================== channels (review 12 C2)
NO_CLUBS = law("No Clubs", "def before_found(p, chain):\n    if p['kind'] == 'channel':\n"
                           "        return {'block': True, 'reason': 'no private clubs'}\n")


def test_a_before_found_hook_refuses_a_channel():
    k = world()
    lid = enact(k, NO_CLUBS)
    a = press_holder(k)
    with pytest.raises(A.ActionError, match="no private clubs"):
        A.act(k, a, "create_channel", {"name": "club", "members": others(k, a)})
    assert "club" not in k.w["channels"] and not events(k, "channel_created")
    blk = events(k, "primitive_blocked")[-1]
    assert blk["data"]["primitive"] == "found" and blk["data"]["by"] == [lid]


def test_channel_hooks_see_kind_channel_and_the_members():
    k = world()
    enact(k, law("Club Watch", "def after_found(p, chain):\n    state['found'] = [p['kind'], p['polity'], p['members']]\n"
                               "def before_admit(p, chain):\n    if p['kind'] == 'channel' and p['agent'] == state.get('bar'):\n"
                               "        return False\n"
                               "def after_expel(p, chain):\n    state['expel'] = [p['kind'], p['agent']]\n"
                               "def after_dissolve(p, chain):\n    state['gone'] = [p['kind'], p['polity'], p['agent']]\n"))
    lid = k.active_laws()[-1]["id"]
    a = press_holder(k)
    b, c = others(k, a)
    A.act(k, a, "create_channel", {"name": "club", "members": [b]})
    assert k.ns[lid]["state"]["found"] == ["channel", "club", sorted({a, b})]
    k.ns[lid]["state"]["bar"] = c
    with pytest.raises(A.ActionError):
        A.act(k, a, "add_member", {"channel": "club", "agent": c})
    assert c not in k.w["channels"]["club"]["members"]
    A.act(k, a, "remove_member", {"channel": "club", "agent": b})
    assert k.ns[lid]["state"]["expel"] == ["channel", b]
    A.act(k, a, "close_channel", {"channel": "club"})
    assert k.ns[lid]["state"]["gone"] == ["channel", "club", a] and "club" not in k.w["channels"]


def _channel_story(v2):
    k = world(v2=v2)
    a = press_holder(k)
    b, c = others(k, a)
    n = len(k.events)
    A.act(k, a, "create_channel", {"name": "club", "members": [b]})
    A.act(k, a, "add_member", {"channel": "club", "agent": c})
    A.act(k, a, "remove_member", {"channel": "club", "agent": b})
    A.act(k, a, "close_channel", {"channel": "club"})
    return [(e["type"], e["agent"], e["data"], e["vis"]) for e in k.events[n:]], [e["cause"] for e in k.events[n:]]


def test_without_law_v2_channels_log_exactly_what_they_did():
    got, causes = _channel_story(False)
    assert [t for t, *_ in got] == ["channel_created", "channel_member", "channel_member", "channel_closed"]
    assert got[0][2] == {"channel": "club", "members": got[0][2]["members"], "open": False} and got[0][3] == "public"
    assert all(not any("primitive" in f for f in ch) for ch in causes)    # no primitive frame without law.v2
    v2, v2_causes = _channel_story(True)
    assert v2 == got                                                    # the same events with law.v2 (no law hooks them)...
    assert all(ch[-1] in ({"primitive": "found"}, {"primitive": "admit"}, {"primitive": "expel"}, {"primitive": "dissolve"})
               for ch in v2_causes)                                     # ...in the change's frame


# ====================================================================== offices (review 12 R6)
OFFICE = law("Census Office", "def on_enact():\n    create_right('census')\n    define_action('census', 'census', count)\n"
                              "def count(agent, *args):\n    return 'counted ' + str(len(args))\n")


def _office(k):
    enact(k, OFFICE)
    a = others(k, None, 1)[0]
    k.apply("grant_right", agent=a, right="census", lid="test")
    return a


def test_an_after_invoke_hook_sees_an_office_use():
    k = world()
    a = _office(k)
    watch = enact(k, law("Office Watch", "def after_invoke(p, chain):\n"
                                         "    state['seen'] = [p['agent'], p['action'], p['args'], p['result']['result']]\n"))
    out = A.act(k, a, "invoke", {"action": "census", "args": [1, 2]})
    assert out == "census: counted 2"
    assert k.ns[watch]["state"]["seen"] == [a, "census", [1, 2], "counted 2"]
    assert events(k, "invoke")[-1]["data"]["result"] == "counted 2"


def test_a_before_invoke_hook_refuses_an_office_use():
    k = world()
    a = _office(k)
    lid = enact(k, law("No Census", "def before_invoke(p, chain):\n    if p['action'] == 'census':\n"
                                    "        refuse('the census is suspended')\n"))
    n = len(events(k, "invoke"))
    with pytest.raises(A.ActionError, match="the census is suspended"):
        A.act(k, a, "invoke", {"action": "census"})
    assert len(events(k, "invoke")) == n
    assert events(k, "primitive_blocked")[-1]["data"]["by"] == [lid]


def test_without_law_v2_an_office_use_is_logged_as_before():
    k = world(v2=False)
    a = _office(k)
    n = len(k.events)
    assert A.act(k, a, "invoke", {"action": "census", "args": ["x"]}) == "census: counted 1"
    new = k.events[n:]
    assert [e["type"] for e in new] == ["invoke"] and new[0]["data"] == {"action": "census", "args": ["x"], "law": new[0]["data"]["law"],
                                                                         "result": "counted 1"}
    assert new[0]["cause"][-1]["action"] == "invoke"                    # no primitive frame without law.v2


# ====================================================================== the laws' rule setters
def test_a_constitution_can_review_a_law_s_rule_setter():
    k = world()
    guard = enact(k, law("No Renaming", "def before_rename(p, chain):\n    return {'block': True, 'reason': 'names are fixed'}\n"))
    other = enact(k, law("Renamer", "def go():\n    rename('camp1', 'Bigwood')\n    state['after'] = 1\n"))
    with k.cause("kernel", "test", root=True):
        k.call(other, k.ns[other]["go"])
    assert "camp1" not in k.w["names"] and not events(k, "rename")       # the law's call ended at the block
    assert "after" not in k.ns[other]["state"]
    assert events(k, "primitive_blocked")[-1]["data"] == {"primitive": "rename", "by": [guard], "reason": "names are fixed"}


def test_rule_setters_reach_after_hooks_with_their_key_and_value():
    k = world()
    watch = enact(k, law("Watch", "def after_set_arms_rule(p, chain):\n    state['arms'] = [p['key'], p['value']]\n"
                                  "def after_set_title(p, chain):\n    state['title'] = [p['agent'], p['text']]\n"
                                  "def after_create_clause(p, chain):\n    state['clause'] = p['clause']\n"))
    a = others(k, None, 1)[0]
    setter = enact(k, law("Setter", f"def go():\n    ban_forging(True)\n    title('{a}', 'Warden')\n"
                                    "    clause('quiet', 'no shouting', pen)\ndef pen(g, acc):\n    return None\n"))
    with k.cause("kernel", "test", root=True):
        k.call(setter, k.ns[setter]["go"])
    st = k.ns[watch]["state"]
    assert st["arms"] == ["forge_ban", True] and st["title"] == [a, "Warden"] and st["clause"] == f"{setter}:quiet"
    assert k.w["agents"][a]["title"] == "Warden" and k.w["clauses"][f"{setter}:quiet"]["text"] == "no shouting"
    told = [e for e in events(k, "compelled") if e["data"]["primitive"] == "set_title"]
    assert told and told[-1]["vis"] == [a]                              # P3.7: still told (now by apply)


# ====================================================================== secrecy
def test_a_sealed_contract_hides_its_parties_from_hooks():
    k = world()
    a, b, c = others(k, None, 3)
    p = {"agent": a, "assassin": b, "target": c, "terms": {"item": "timber", "qty": 1.0}}
    hide = D.hidden_agents(k, "hire_assassin", p, {})
    seen = D.hook_payload(k, PR.get("hire_assassin"), p, "L1", hide)
    assert seen == {"agent": None, "assassin": None, "target": c, "terms": {"item": "timber", "qty": 1.0}}
    assert "text" not in PR.get("hire_assassin").params                  # the sealed message is a call option


def test_a_hidden_jurisdiction_s_founding_binds_no_other_polity_s_law():
    k = world()
    lid = enact(k, law("Watch", "def before_found(p, chain):\n    return None\ndef before_invite(p, chain):\n    return None\n"))
    a = others(k, None, 1)[0]
    found = PR.get("found")
    chan = {"agent": a, "polity": "club", "kind": "channel", "members": [a]}
    hidden = {"agent": a, "polity": "J99", "kind": "jurisdiction", "members": [a]}
    assert lid in [l["id"] for l in D.bound_laws(k, found, chan, "before")]
    assert D.bound_laws(k, found, hidden, "before") == []
    assert D.bound_laws(k, PR.get("invite"), {"polity": "J99", "agent": a}, "before") == []
    assert D.bound_laws(k, PR.get("set_charter"), {"polity": "J99", "laws": []}, "after") == []


def test_founding_inviting_and_setting_a_charter_log_as_before():
    k = world()
    a, b = others(k, None, 2)
    n = len(k.events)
    out = J.act_found(k, a, "Freeport")
    jid = next(j for j, v in J.jurs(k).items() if v["founder"] == a)
    assert out.startswith(f"Founded {jid} 'Freeport' in secret")
    J.act_invite(k, a, jid, b)
    assert b in J.jurs(k)[jid]["invited"]
    assert [e["type"] for e in k.events[n:] if e["type"] != "notify"] == ["jur_founded", "jur_invited"]
    assert events(k, "jur_founded")[-1]["vis"] == [a]


def test_a_blocked_declaration_keeps_the_jurisdiction_hidden():
    k = world(sets=("jurisdictions.declare_cost=0",))
    a, b = others(k, None, 2)
    J.act_found(k, a, "Freeport")
    jid = next(j for j, v in J.jurs(k).items() if v["founder"] == a)
    lid = enact(k, law("No Secession", "def before_declare(p, chain):\n    return {'block': True, 'reason': 'no secession'}\n"))
    J.declare_now(k, jid)
    j = J.jurs(k)[jid]
    assert j["status"] == "hidden" and not j["declare_pending"] and not events(k, "jur_declared")
    blk = events(k, "primitive_blocked")[-1]
    assert blk["data"] == {"primitive": "declare", "by": [lid], "reason": "no secession", "polity": jid} and blk["vis"] == [a]
    k.w["laws"][lid]["status"] = "repealed"
    J.declare_now(k, jid)
    assert J.jurs(k)[jid]["status"] == "declared" and events(k, "jur_declared")


# ====================================================================== the legacy alias of commission
def test_on_commission_still_refuses_through_its_legacy_alias():
    k = world(v2=False)
    from charter import life as LF, roles as RO
    maker = next((a for a in k.roster() if RO.has_role(k, a, "maker")), None)
    if maker is None:
        pytest.skip("no Maker in this world")
    lid = enact(k, law("No Children", "def on_commission(parent, maker, order):\n    return False\n"))
    parent = next(a for a in others(k, maker, 3) if a != maker)
    with k.cause("action", "commission", root=True):                   # the alias fires for an agent's commission (as always)
        with pytest.raises(D.L.LawError, match=f"law {lid} refuses this commission"):
            LF.commission(k, parent, maker, {"goal": "Wealth"})
