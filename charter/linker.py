"""The linker (P3.3; review 09 §6; ARCHITECTURE §6, I-10, D-8): laws build on laws. Everything here runs only in law.v2 worlds
(spec `law.v2: true`); with it off the kernel never calls this module and `use`/`public_of` do not exist.

Law code
  exports = ["RATE", "tax_due"]     names a law offers to others (lawlang.check_v2: defs or constants; a declarative top level)
  tax = use("L3")                   follow L3's current version
  tax = use("L3@9f1c2ab4")          pin one version of L3's code (8-16 hex digits of its code_sha)
  esc = use("lib:escrow@3c9d01aa")  a library entry, by hash (just code: nothing is enacted)
  tax["tax_due"](qty)               a Link is a read-only mapping export name -> object
  public["raised"] = 3              the law's public dict (JSON data); others read a deep copy with public_of("L7")

Linking (review 09 §6.2: no confused deputy). An import is never the exporter's namespace: the exporter's (declarative) module is
executed again in a fresh namespace built from the IMPORTER's law API (its jurisdiction, its binding, its rng stream, its name on
gazettes) and SAFE_BUILTINS, compiled as `<law:L3@<sha>>` with the kernel's meter, so an imported function can do exactly what the
importer could do with the same code in its own body, and its work is charged to the importer's call. The exporter's `state` and
`public` are unreachable (exported closures may not name them; the linked namespace has neither). Nested imports (L3's own
`use("L2")`) are linked the same way, under the same importer's authority.

Records (in k.w, so checkpoints and dry runs cover them)
  law["version"], law["code_sha"], law["versions"] = [{v, sha, round, via, by}]   (I-11)
  law["public"] = {}                                                               (JSON-able; Kernel.call checks it after each call)
  law["imports"] = [{ref, alias, target, mode: follow|pinned, sha, names, auto}]   (names: export names read, None = any)
  w["code_store"][sha] = code                                                      (every version of every law; linked library code)
  w["law_deps"][target] = [{law, mode, sha}]                                       (derived from the records: rebuild_deps)
  k.links[importer] = [Link, ...]                                                  (live objects, rebuilt when a module is loaded)

Versions and dependents (review 09 §6.4, D-8)
  amendment of L3 (its code changes in Kernel._load): following importers are relinked to the new version and reclassified, unless
    the new version no longer exports what they read: then they are auto-pinned to the version they were linked to
    (`import_pinned`). Pinned importers are unaffected (their code comes from the code store).
  repeal of L3: following importers are auto-pinned to L3's last version (`import_pinned`); pinned ones are unaffected.
  suspension of L3: nothing changes (it stops L3's hooks, not its exports).

Interfaces (I-10): parse_ref, link, code_store, dependents, on_amend, on_repeal; plus law_api (use, public_of), load (Kernel._load),
new_law_class / on_new_law (Kernel.new_law), check_public (Kernel.call), snapshot_links / restore_links (dry runs),
preview_amend / amendment_class (for P3.4 and the previewer).
"""
from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Mapping

from charter import lawlang as L

LawError = L.LawError


def enabled(k) -> bool:
    return bool((k.spec.get("law") or {}).get("v2"))


def sha(code: str) -> str:
    """A code version's id: sha256 of the code, 16 hex digits (review 09 §6.4)."""
    return hashlib.sha256(str(code).encode()).hexdigest()[:16]


def parse_ref(ref: str) -> tuple:
    """"L3" -> ("law", "L3", None); "L3@9f1c2ab4" -> ("law", "L3", "9f1c2ab4"); "lib:escrow@3c9d01aa" -> ("lib", "escrow", ...)."""
    m = L.REF_RE.match(str(ref))
    if not m:
        raise LawError(f"use({ref!r}): a reference is \"L3\", \"L3@<8-16 hex digits>\" or \"lib:<name>@<8-16 hex digits>\"")
    return ("law", m.group(1), m.group(2)) if m.group(1) else ("lib", m.group(3), m.group(4))


def code_store(k) -> dict:
    return k.w.setdefault("code_store", {})


def lib_name(name: str) -> str:
    """A library entry's name in a ref: "Loan Registry" -> "loan_registry"."""
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def lib_ref(name: str) -> str:
    """The pinned ref of a library entry: use(lib_ref("Loan Registry")) (a block's, else the edition-1 law's code)."""
    from charter import library as LB
    return f"lib:{lib_name(name)}@{sha(LB.entry_code(name))}"


# ---------------------------------------------------------------------- resolution
def _visible(k, reader: str | None, target: str) -> bool:
    """A law in a hidden jurisdiction is invisible to laws of other jurisdictions (as if it did not exist)."""
    if "jur" not in k.w or reader is None or reader not in k.w["laws"]:
        return True
    from charter import jurisdictions as J
    tj = J.law_jur(k, target)
    j = J.jurs(k).get(tj)
    return not (j and J.secret(j) and J.law_jur(k, reader) != tj)


def _decl_law(declarer: str | None) -> str | None:
    """The law id of a declaring module key ("L7", "L3@<sha>"); None for library code and drafts not yet recorded."""
    if not declarer or declarer.startswith("lib:"):
        return None
    return declarer.split("@")[0]


def _record(k, declarer, ref) -> dict | None:
    lid = _decl_law(declarer)
    law = k.w["laws"].get(lid) if lid else None
    return next((i for i in (law or {}).get("imports") or () if i["ref"] == ref), None)


def resolve(k, declarer: str | None, ref: str, overrides: dict | None = None) -> tuple:
    """(key "<target>@<sha>", code, {target, mode, sha}) of what `ref` names when the module `declarer` uses it now. A follow
    import its declarer's record has auto-pinned resolves to the pinned version. overrides: {lid: code} read instead of a law's
    current code (a proposed amendment). Raises LawError for anything that cannot be linked."""
    kind, ident, pin = parse_ref(ref)
    if kind == "lib":
        from charter import library as LB
        code, s = LB.lib_code(ident, pin)                              # edition-1 laws, edition-2 laws and blocks (P3.9)
        if code is None and not s:
            raise LawError(f"use({ref!r}): no library entry {ident}")
        if code is None:
            raise LawError(f"use({ref!r}): lib:{ident} has no version {pin} (its versions: {', '.join(s)})")
        if not getattr(k, "dry", False):
            code_store(k).setdefault(s, code)
        return f"lib:{ident}@{s}", code, {"target": f"lib:{ident}", "mode": "pinned", "sha": s}
    law = k.w["laws"].get(ident)
    overrides = overrides or {}
    reader = _decl_law(declarer)
    if law is None or (law.get("enacted_round") is None and ident not in overrides) or not _visible(k, reader, ident):
        raise LawError(f"use({ref!r}): no such law")
    if pin is None:
        rec = _record(k, declarer, ref)
        if rec and rec["mode"] == "pinned":                            # auto-pinned (D-8)
            pin = rec["sha"]
        else:
            if ident in overrides:
                code = overrides[ident]
            elif law["status"] not in ("active", "suspended"):
                raise LawError(f"use({ref!r}): {ident} is not in force; pin a version: use(\"{ident}@<sha>\")")
            else:
                code = law["code"]
            s = sha(code)
            return f"{ident}@{s}", code, {"target": ident, "mode": "follow", "sha": s}
    full = next((v["sha"] for v in law.get("versions") or () if v["sha"].startswith(pin)), None)
    if full is None or full not in code_store(k):
        raise LawError(f"use({ref!r}): {ident} has no version {pin}")
    return f"{ident}@{full}", code_store(k)[full], {"target": ident, "mode": "pinned", "sha": full}


def check_graph(k, root_key: str, code: str, overrides: dict | None = None) -> list:
    """lawlang.check_graph with the kernel's resolver: a DAG, at most 6 deep, at most 64 KB linked."""
    return L.check_graph(root_key, code, lambda decl, ref: resolve(k, decl, ref, overrides)[:2])


# ---------------------------------------------------------------------- links
class Link(Mapping):
    """What use(ref) returns: a read-only mapping export name -> object, from one version of the exporter linked under the
    importer's authority. Relinking (a following import after an amendment) replaces its contents in place, so the importer's
    module name keeps working. It is never saved: modules relink when they are loaded again (checkpoints, restores)."""

    def __init__(self, authority: str, declarer: str, ref: str):
        self.authority, self.declarer, self.ref = authority, declarer, ref
        self.key = self.sha = None
        self.names: tuple = ()
        self.children: list = []
        self._ns: dict = {}

    def __getitem__(self, name):
        if name not in self.names:
            raise KeyError(f"{self.ref} does not export {name!r} (it exports {', '.join(self.names) or 'nothing'})")
        return self._ns[name]

    def __iter__(self):
        return iter(self.names)

    def __len__(self):
        return len(self.names)

    def __repr__(self):
        return f"<link {self.ref} -> {self.key}>"

    def __deepcopy__(self, memo):                                       # dry runs copy module data: a link is not data
        return self

    def __copy__(self):
        return self

    def __reduce__(self):
        raise TypeError(f"the link {self.ref} cannot be saved: keep it in a module name, not in state or public")

    def _state(self) -> tuple:
        return self.key, self.sha, self.names, list(self.children), self._ns

    def _set_state(self, st) -> None:
        self.key, self.sha, self.names, self.children, self._ns = st


def _build(k, lk: Link, key: str, code: str, depth: int) -> None:
    """(Re)fill a link: execute the exporter's module in a fresh namespace with the importer's API (lk.authority)."""
    children: list = []

    def use(ref):                                                       # the exporter's own imports, under the same authority
        return _link(k, lk.authority, key, ref, depth + 1, children)

    api = {**k.api_for(lk.authority), "use": use}
    ns = L.load_module(code, key, api, {}, k.limited)                   # compiled as <law:L3@sha>: metered by the kernel's meter
    names = tuple(L.exports_of(L.check(code, v2=True)) or ())
    lk._ns = {n: ns[n] for n in names}
    lk.key, lk.sha, lk.names, lk.children = key, key.rsplit("@", 1)[1], names, children


def _link(k, authority, declarer, ref, depth, collector) -> Link:
    if depth > L.MAX_IMPORT_DEPTH:
        raise LawError(f"imports nest deeper than {L.MAX_IMPORT_DEPTH}")
    key, code, _ = resolve(k, declarer, ref)
    lk = Link(authority, declarer, ref)
    _build(k, lk, key, code, depth)
    collector.append(lk)
    return lk


def link(k, importer: str, ref: str) -> Mapping:
    """use(ref) in law `importer`'s module (I-10): link the export under the importer's authority, recorded in k.links[importer]."""
    lk = _link(k, importer, importer, ref, 1, k.links.setdefault(importer, []))
    rec = _record(k, importer, ref)
    if rec is not None and rec["mode"] == "follow":
        rec["sha"] = lk.sha
    return lk


def _all_links(k):
    stack = [lk for lst in k.links.values() for lk in lst]
    while stack:
        lk = stack.pop()
        yield lk
        stack.extend(lk.children)


def snapshot_links(k) -> tuple:
    """For a dry run (Kernel._snapshot): the link lists and every link's contents (relinking changes them in place)."""
    return {a: list(v) for a, v in k.links.items()}, [(lk, lk._state()) for lk in _all_links(k)]


def restore_links(k, snap) -> None:
    lists, states = snap
    k.links = lists
    for lk, st in states:
        lk._set_state(st)


def relink(k) -> None:
    """Bring every link to what its ref resolves to now (after an amendment or an auto-pin); unchanged links are kept."""
    def refresh(lk, depth):
        try:
            key, code, _ = resolve(k, lk.declarer, lk.ref)
        except LawError:
            return                                                       # cannot happen after on_repeal / on_amend: keep the link
        if key != lk.key:
            _build(k, lk, key, code, depth)
        else:
            for c in lk.children:
                refresh(c, depth + 1)

    for importer, lst in k.links.items():
        for lk in lst:
            refresh(lk, 1)
            rec = _record(k, importer, lk.ref)
            if rec is not None and rec["mode"] == "follow":
                rec["sha"] = lk.sha


# ---------------------------------------------------------------------- the law API (lawapi rows: module "linker")
def law_api(k, lid) -> dict:
    def use(ref):
        return link(k, lid, str(ref))

    def public_of(law_id):
        t = str(law_id)
        law = k.w["laws"].get(t)
        if law is None or law.get("enacted_round") is None or not _visible(k, lid, t):
            raise LawError(f"public_of({t!r}): no such law")
        return copy.deepcopy(law.get("public") or {})

    return {"use": use, "public_of": public_of}


def _jsonable(x, depth=0) -> bool:
    if depth > 50:
        return False
    if x is None or isinstance(x, (bool, int, float, str)):
        return True
    if isinstance(x, list):
        return all(_jsonable(v, depth + 1) for v in x)
    if isinstance(x, dict):
        return all(isinstance(kk, str) and _jsonable(v, depth + 1) for kk, v in x.items())
    return False


def check_public(k, lid) -> None:
    """After every invocation of a law (Kernel.call): its public dict must hold JSON data only."""
    law = k.w["laws"].get(lid) if isinstance(lid, str) else None
    if law is not None and "public" in law and not _jsonable(law["public"]):
        raise LawError("public may hold only JSON data: dicts with string keys, lists, strings, numbers, booleans and None")


# ---------------------------------------------------------------------- classification
def import_closures(k, declarer: str | None, tree, overrides: dict | None = None, only=None, depth=0) -> list:
    """The exported closures a module imports (as AST modules), transitively through the imports those closures reach: what
    lawlang.classify(tree, imported) needs. only: restrict to these use-aliases."""
    if depth > L.MAX_IMPORT_DEPTH:
        raise LawError(f"imports nest deeper than {L.MAX_IMPORT_DEPTH}")
    used = L.used_exports(tree)
    out = []
    for alias, ref in L.use_refs(tree).items():
        if only is not None and alias not in only:
            continue
        key, code, _ = resolve(k, declarer, ref, overrides)
        sub = L.check(code, v2=True)
        clo, reached = L.export_closure(sub, used.get(alias))
        out.append(clo)
        if reached:
            out += import_closures(k, key, sub, overrides, reached, depth + 1)
    return out


def classify(k, lid: str, code: str | None = None, overrides: dict | None = None) -> str:
    """A law's class with its imports (transitive), for its current code or `code`."""
    tree = L.check(code if code is not None else k.w["laws"][lid]["code"], v2=True)
    return L.classify(tree, import_closures(k, lid, tree, overrides))


def new_law_class(k, code: str) -> str:
    """Kernel.new_law under law.v2: the static rules, the import graph, and the class with what the draft imports."""
    tree = L.check(code, v2=True)
    check_graph(k, f"draft@{sha(code)}", code)
    return L.classify(tree, import_closures(k, None, tree))


def _imports(k, declarer, tree, old=()) -> list:
    """The import records of a module; an auto-pin of the same ref in `old` (the previous version's records) is kept."""
    used = L.used_exports(tree)
    pins = {i["ref"]: i for i in old if i.get("auto")}
    out = []
    for alias, ref in L.use_refs(tree).items():
        if ref in pins:
            out.append({**pins[ref], "alias": alias, "names": used[alias]})
            continue
        _, _, info = resolve(k, declarer, ref)
        out.append({"ref": ref, "alias": alias, "target": info["target"], "mode": info["mode"], "sha": info["sha"],
                    "names": used[alias], "auto": False})
    return out


def on_new_law(k, lid: str) -> None:
    """Kernel.new_law under law.v2: version 1 of the law's code, its public dict, its import records."""
    law = k.w["laws"][lid]
    s = sha(law["code"])
    code_store(k)[s] = law["code"]
    law.update({"version": 1, "code_sha": s, "versions": [{"v": 1, "sha": s, "round": k.r, "via": "propose", "by": law["author"]}],
                "public": {}, "imports": _imports(k, None, L.check(law["code"], v2=True))})


# ---------------------------------------------------------------------- loading, amendment, repeal
def load(k, lid: str) -> dict:
    """Kernel._load under law.v2: check the import graph, (re)link the module's imports, and when its code changed since the
    recorded version (an amendment: do_amend replaced the code), record the new version and update its dependents (on_amend).
    Returns the module namespace (Kernel._exec). A failure changes nothing (the caller restores the old code and loads again)."""
    law = k.w["laws"][lid]
    law.setdefault("public", {})
    s = sha(law["code"])
    old_sha = law.get("code_sha")
    changed = old_sha is not None and s != old_sha
    old_imports = law.get("imports") or []
    tree = L.check(law["code"], v2=True)
    if changed:
        law["imports"] = _imports(k, lid, tree, old_imports)
    try:
        check_graph(k, f"{lid}@{s}", law["code"])
        k.links[lid] = []
        ns = k._exec(lid)
        cls = L.classify(tree, import_closures(k, lid, tree))
    except Exception:
        law["imports"] = old_imports
        raise
    if changed:
        law["cls"] = cls
        code_store(k)[s] = law["code"]
        by = (law.get("patches") or [{}])[-1].get("by")
        law["version"] = int(law.get("version") or 1) + 1
        law.setdefault("versions", []).append({"v": law["version"], "sha": s, "round": k.r, "via": "amend", "by": by})
        law["code_sha"] = s
        on_amend(k, lid, old_sha, s)
    if law.get("imports"):
        rebuild_deps(k, loading=lid)
    return ns


def _satisfies(new_code: str, names, linked_sha: str | None, store: dict) -> bool:
    """Does a new version still export what a following importer reads (names; None: everything the linked version exported)?"""
    try:
        ex = L.exports_of(L.check(new_code, v2=True)) or []
    except LawError:
        return False
    if names is None:
        old = store.get(linked_sha)
        names = (L.exports_of(L.check(old, v2=True)) or []) if old else []
    return bool(ex) and set(names) <= set(ex)


def _pin(k, imp: dict, importer: str, target: str, why: str) -> None:
    imp.update({"mode": "pinned", "auto": True})
    v = next((x["v"] for x in k.w["laws"][target].get("versions") or () if x["sha"] == imp["sha"]), None)
    k.log("import_pinned", None, {"law": importer, "import": target, "to": imp["sha"], "version": v, "why": why}, vis="monitor")
    if not k.dry:                                                       # the public face of import_pinned (agents read the gazette)
        k.gazette(f"Law {importer}'s import of {target} is now pinned to version {v} of {target} ({why}).",
                  by=f"law:{importer}")


def dependents(k, lid: str) -> list[dict]:
    """The laws in force that import `lid` directly: [{law, mode, sha}] (I-10)."""
    return list((k.w.get("law_deps") or {}).get(lid, []))


def rebuild_deps(k, loading: str | None = None) -> None:
    """w["law_deps"] from the import records of the laws in force (and `loading`, a law being enacted)."""
    deps: dict = {}
    for l in k.w["laws"].values():
        if l.get("status") not in ("active", "suspended") and l["id"] != loading:
            continue
        for i in l.get("imports") or ():
            deps.setdefault(i["target"], []).append({"law": l["id"], "mode": i["mode"], "sha": i["sha"]})
    k.w["law_deps"] = deps


def _following(k, lid):
    for l in k.w["laws"].values():
        if l.get("status") in ("active", "suspended", "draft", "proposed"):
            for i in l.get("imports") or ():
                if i["target"] == lid and i["mode"] == "follow":
                    yield l, i


def reclassify(k) -> None:
    """Every law in force that imports something gets its class recomputed (imports can change what it can do)."""
    for l in k.w["laws"].values():
        if l.get("imports") and l.get("status") in ("active", "suspended"):
            try:
                l["cls"] = classify(k, l["id"])
            except LawError:
                pass


def on_amend(k, lid: str, old_sha: str, new_sha: str) -> None:
    """L's code changed from old_sha to new_sha (I-10): following importers that still find what they read are relinked to the
    new version (and reclassified); the others are auto-pinned to the version they were linked to (D-8)."""
    store = code_store(k)
    for l, imp in list(_following(k, lid)):
        if not _satisfies(store[new_sha], imp.get("names"), imp.get("sha"), store):
            _pin(k, imp, l["id"], lid, f"the new version of {lid} no longer exports what it uses")
        else:
            imp["sha"] = new_sha
    relink(k)
    reclassify(k)
    rebuild_deps(k)


def on_repeal(k, lid: str) -> None:
    """L was repealed (I-10): following importers are auto-pinned to its last version (D-8); its hooks stop, its code stays."""
    for l, imp in list(_following(k, lid)):
        imp["sha"] = k.w["laws"][lid].get("code_sha") or imp["sha"]
        _pin(k, imp, l["id"], lid, f"{lid} was repealed")
    rebuild_deps(k)


# ---------------------------------------------------------------------- what an amendment would do (P3.4, the previewer)
def preview_amend(k, lid: str, new_code: str) -> list[dict]:
    """Each law importing `lid` and what amending it to new_code would do to it: unaffected (pinned), relinked (with its class
    after), or auto-pinned."""
    out = []
    for l in k.w["laws"].values():
        if l.get("status") not in ("active", "suspended"):
            continue
        for imp in l.get("imports") or ():
            if imp["target"] != lid:
                continue
            row = {"law": l["id"], "mode": imp["mode"], "cls": l["cls"]}
            if imp["mode"] == "pinned":
                row.update(outcome="unaffected", cls_after=l["cls"])
            elif _satisfies(new_code, imp.get("names"), imp.get("sha"), code_store(k)):
                row.update(outcome="relinked", cls_after=classify(k, l["id"], overrides={lid: new_code}))
            else:
                row.update(outcome="auto_pinned", cls_after=l["cls"])
            out.append(row)
    return out


def amendment_class(k, lid: str, new_code: str) -> str:
    """The class an amendment of `lid` to new_code needs (review 09 §6.4): the maximum over the new code's class and every
    following dependent's class after relinking."""
    cls = classify(k, lid, code=new_code, overrides={lid: new_code})
    for row in preview_amend(k, lid, new_code):
        cls = max(cls, row["cls_after"], key=L.CLASS_RANK.get)
    return cls
