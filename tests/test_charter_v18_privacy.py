"""V18 (review 12): under law.v2 a law's new-style hooks must not read what the legacy hooks could not: an encrypted DM's text, any
DM's text where conditions.law_reads_dms is off, or a private channel post's text. Offline."""
from __future__ import annotations

from charter import actions as A
from charter import generator
from charter import spec as S
from charter.kernel import Kernel


def world(reads=False):
    sp = S.apply_overrides(S.load("society"), ["law.v2=true", "shared_archive.enabled=false", "jurisdictions.enabled=false",
                                               f"conditions.law_reads_dms={str(reads).lower()}"])
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    lid = k.new_law('title = "Tap"\nintent = "t"\ndef after_dm(p, chain):\n    public["dm"] = public.get("dm", []) + [p["text"]]\n'
                    'def after_post(p, chain):\n    public["post"] = public.get("post", []) + [p["text"]]\n', "constitution")
    k.enact(lid)
    a, b = [x for x in k.roster() if k.cls_of(x) not in ("board", "fixer", "observer")][:2]
    return k, lid, a, b


def act(k, aid, name, args):
    with k.cause("turn", aid, call=f"r0:{aid}:0"):
        return A.act(k, aid, name, args)


def test_dm_text_is_hidden_from_laws_unless_the_world_lets_laws_read_dms():
    k, lid, a, b = world(reads=False)
    act(k, a, "dm", {"to": b, "text": "plain secret"})
    assert k.w["laws"][lid]["public"]["dm"] == [None]
    k, lid, a, b = world(reads=True)
    act(k, a, "dm", {"to": b, "text": "plain readable"})
    assert k.w["laws"][lid]["public"]["dm"] == ["plain readable"]


def test_encrypted_dm_text_is_never_read_by_laws():
    k, lid, a, b = world(reads=True)
    if "encrypt" not in k.w["agents"][a]["rights"]:
        k.w["agents"][a]["rights"].append("encrypt")
    act(k, a, "dm", {"to": b, "text": "TOPSECRET", "encrypted": True})
    assert k.w["laws"][lid]["public"]["dm"] == [None]


def test_private_channel_post_text_is_hidden_from_laws_but_public_posts_are_not():
    k, lid, a, b = world()
    k.w["channels"]["c1"] = {"owner": a, "members": sorted([a, b]), "open": False}
    act(k, a, "channel_post", {"channel": "c1", "text": "members only"})
    with k.cause("turn", a, call=f"r0:{a}:1"):                         # a plain public post (society routes agents' posts to editors)
        k.apply("post", agent=a, kind="post", text="hello all", outlet=None, actor=a)
    assert k.w["laws"][lid]["public"]["post"] == [None, "hello all"]
