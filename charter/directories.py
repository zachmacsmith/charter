"""Directories: named, owned trees of text files that agents write, edit and share (behind spec flags; off by default).

A directory is a generic store, not a historian feature: the Historian's chronicle is one configuration of it.

  owner      who has full access (read, write, grant): "role:<role>" (every living holder of a role), "agent:<id>", "right:<r>"
             (every holder of a right), "class:<cls>", or "institution:<id>" (OWNER_KINDS: an institution's resolver is the hook for
             later work: contracts, polities and their offices; today it grants nobody)
  scope      "run" (the directory starts empty and lives only in this run) or "namespace" (persistent: it lives on disk under
             <directories.path>/<namespace>/<name>/ and every run on the same namespace inherits it)
  limits     max_bytes (the whole directory) and max_file_bytes (one file)
  grants     the owner may grant any agent read or write access to a path or a path prefix ("people/", "" = everything), and revoke
             it (access "none"; the longest matching prefix decides). A grant's subject is a string, "agent:<id>" today; the
             format leaves room for "office:<contract>.<office>" and "institution:<id>" subjects later (SUBJECT_KINDS).
  readonly   path prefixes nobody may write (the chronicle's "_records/", written by the runner)
  records    the runner appends a compact public digest of each completed run as _records/<run_id>.md (namespace scope only)

Provisioning. Spec `directories.stores: {<name>: {owner, scope, namespace, max_bytes, max_file_bytes, records, title}}` with
`directories.enabled: true`. The `chronicle` block is the Historian's shorthand: `chronicle.enabled` (default: on exactly when the
historian role is in play, roles.explicit.historian or roles.counts.historian > 0) provisions the store "chronicle", owned by
role:historian, namespace-scoped (chronicle.namespace, else shared_archive.namespace, else "default"), with records. Later work can
create stores in-world (an institution's records office, a bought library) through `create(k, name, cfg)`: the hook is there, the
purchase or founding mechanic is not.

Actions (action_registry, module "directories"; every argument may name the directory with "dir", which may be left out when the
agent can reach exactly one): look-ups dir_list, dir_read, dir_search (pre-actions: free where lookups are free); changes
dir_write, dir_edit, dir_move, dir_delete (the routed primitive dir_write, ops write/append/edit/move/delete) and dir_grant (the
routed primitive dir_grant). Each agent sees the directory actions only while it can reach a directory (`when`).

State, persistence and replay. k.w["dirs"][name] = {owner, scope, namespace, limits, readonly, records, files: {path: text},
grants: {subject: {prefix: level}}}: a run's working copy lives in the world state, so checkpoints, resumes, rewinds and replays
carry it. Namespace stores are frozen per run (Frozen): at a fresh start the live tree is snapshotted into the run directory
(directories/base.json: store -> path -> blob sha, texts in blobs/), and the kernel starts from that base; a replay starts from
the source run's base (archive_from), so it is exact whatever the live tree holds by then. Write-back (each checkpoint and the end
of a complete run, unless the run does not publish: replays, forks, and dry runs unless directories.publish_dry) applies this run's
changes since its last write-back to the live tree, file by file: each changed file is written atomically (temp file + rename),
last writer wins at whole-file granularity; a file this run deleted is removed only if the live copy is still the one this run
last saw. Parallel runs on one namespace therefore never corrupt a file; a file both edit ends with the later write. Grants are
run state only (they are not written back): each run's digest under _records/ lists the access granted in that run.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from pathlib import Path

from charter import features as FT

DEFAULTS = {
    "enabled": False,                    # provision directories.stores (the chronicle block provisions its own store)
    "path": "runs/charter/directories",  # root of namespace-scoped stores (relative to the repository root)
    "namespace": None,                   # default namespace (None: shared_archive.namespace, else "default")
    "publish_dry": False,                # dry (scripted) runs write back to the live store too
    "max_bytes": 2_000_000,              # default size limit of a directory
    "max_file_bytes": 200_000,           # default size limit of one file
    "tree_lines": 40,                    # paths shown in the turn prompt's tree
    "stores": {},                        # {name: {owner, scope, namespace, max_bytes, max_file_bytes, records, title}}
}
CHRONICLE_DEFAULTS = {
    "enabled": None,                     # None: on exactly when the historian role is in play
    "namespace": None,                   # None: directories.namespace, shared_archive.namespace, else "default"
    "max_bytes": 2_000_000,
    "max_file_bytes": 200_000,
    "records": True,                     # the runner appends _records/<run_id>.md (a public digest of each completed run)
    "readonly": [],                      # extra read-only prefixes (e.g. "archive/": an earlier chronicle kept for reference)
    "grants": {},                        # initial grants, e.g. clerks: {"agent:Cleo": {"people/": "write", "": "read"}}
}
STORE_KEYS = ("owner", "scope", "namespace", "max_bytes", "max_file_bytes", "records", "title", "readonly", "grants")
SCOPES = ("run", "namespace")
RECORDS = "_records/"
LOOKUPS = ("dir_list", "dir_read", "dir_search")
WRITES = ("dir_write", "dir_edit", "dir_move", "dir_delete")
ACTIONS = LOOKUPS + WRITES + ("dir_grant",)
LEVELS = ("none", "read", "write")
PATH_MAX = 120
PATH_RE = re.compile(r"^[A-Za-z0-9._\- /]+$")
SEARCH_HITS = 30
READ_LINES = 400
AGNET = Path(__file__).resolve().parents[1]


def _err(msg):
    from charter.actions import ActionError
    return ActionError(msg)


# ====================================================================== configuration
def _spec(x) -> dict:
    if x is None:
        return {}
    if isinstance(x, dict):
        return x["spec"] if isinstance(x.get("spec"), dict) else x
    return x.spec


def cfg(x) -> dict:
    out = copy.deepcopy(DEFAULTS)
    out.update({k: v for k, v in ((_spec(x).get("directories") or {}).items()) if k != "stores"})
    out["stores"] = copy.deepcopy((_spec(x).get("directories") or {}).get("stores") or {})
    return out


def chronicle_cfg(x) -> dict:
    out = copy.deepcopy(CHRONICLE_DEFAULTS)
    out.update(_spec(x).get("chronicle") or {})
    return out


def historian_in_play(sp: dict) -> bool:
    r = (sp or {}).get("roles") or {}
    ex = (r.get("explicit") or {}).get("historian")
    return bool(ex) or float((r.get("counts") or {}).get("historian", 0) or 0) > 0


def chronicle_on(x) -> bool:
    sp = _spec(x)
    v = chronicle_cfg(sp)["enabled"]
    return historian_in_play(sp) if v is None else bool(v)


def default_namespace(sp: dict) -> str:
    c = cfg(sp)
    return str(c.get("namespace") or ((sp.get("shared_archive") or {}).get("namespace")) or "default")


def stores(x) -> dict:
    """The directories this world provisions: {name: resolved config}, in name order ({} when off)."""
    sp = _spec(x)
    c = cfg(sp)
    raw = dict(c["stores"]) if c.get("enabled") else {}
    if chronicle_on(sp):
        ch = chronicle_cfg(sp)
        raw.setdefault("chronicle", {"owner": "role:historian", "scope": "namespace", "namespace": ch["namespace"],
                                     "max_bytes": ch["max_bytes"], "max_file_bytes": ch["max_file_bytes"],
                                     "records": ch["records"], "title": "the chronicle", "grants": ch.get("grants") or {},
                                     "readonly": list(ch.get("readonly") or [])})
    out = {}
    for name, s in sorted(raw.items()):
        s = dict(s or {})
        bad = sorted(set(s) - set(STORE_KEYS))
        if bad:
            raise ValueError(f"directories.stores.{name}: unknown key(s) {', '.join(bad)}; keys: {', '.join(STORE_KEYS)}")
        scope = s.get("scope") or "run"
        if scope not in SCOPES:
            raise ValueError(f"directories.stores.{name}.scope must be one of {SCOPES}, not {scope!r}")
        owner = str(s.get("owner") or "")
        if owner.partition(":")[0] not in OWNER_KINDS:
            raise ValueError(f"directories.stores.{name}.owner {owner!r}: use one of {', '.join(k + ':<x>' for k in OWNER_KINDS)}")
        out[str(name)] = {"owner": owner, "scope": scope, "namespace": str(s.get("namespace") or default_namespace(sp)),
                          "max_bytes": int(s.get("max_bytes") or c["max_bytes"]),
                          "max_file_bytes": int(s.get("max_file_bytes") or c["max_file_bytes"]),
                          "records": bool(s.get("records", False)) and scope == "namespace",
                          "title": str(s.get("title") or f"the directory {name}"),
                          "readonly": sorted(set(s.get("readonly") or []) | ({RECORDS} if s.get("records") else set())),
                          "grants": _initial_grants(name, s.get("grants"))}
    return out


def _initial_grants(name, g) -> dict:
    """A store's initial grants from the spec ({"agent:<id>": {prefix: read|write|none}}): run state from the start, so clerks
    hold access before the owner's first turn. The owner may change them with dir_grant."""
    out = {}
    for subj, prefixes in sorted((g or {}).items()):
        kind, _, v = str(subj).partition(":")
        if kind != "agent" or not v:
            raise ValueError(f"directories.stores.{name}.grants: subject {subj!r} must be agent:<id>")
        if not isinstance(prefixes, dict):
            raise ValueError(f"directories.stores.{name}.grants.{subj} must be {{prefix: level}}")
        for prefix, lv in prefixes.items():
            if lv not in LEVELS:
                raise ValueError(f"directories.stores.{name}.grants.{subj}.{prefix!r}: level must be one of {LEVELS}")
        out[f"agent:{v}"] = {str(pf): str(lv) for pf, lv in sorted(prefixes.items())}
    return out


def enabled(x) -> bool:
    """x: a kernel, an instance or a spec. On when any directory is provisioned (the world's state holds them once installed)."""
    if x is None:
        return False
    if not isinstance(x, dict) and hasattr(x, "w"):
        return bool(x.w.get("dirs") is not None)
    try:
        return bool(stores(x))
    except ValueError:
        return False


# ====================================================================== owners and grant subjects
def _owner_role(k, aid, v):
    from charter import roles as RO
    return RO.has_role(k, aid, v)


def _owner_right(k, aid, v):
    return v in (k.w["agents"].get(aid) or {}).get("rights", [])


def _owner_class(k, aid, v):
    a = k.w["agents"].get(aid) or {}
    return a.get("cls") == v or v in (a.get("also") or ())


def _owner_institution(k, aid, v):
    """Hook: an institution (a contract or a polity) owning a directory; its members or offices get access once this resolves
    them. Nobody yet."""
    return False


OWNER_KINDS = {"agent": lambda k, aid, v: aid == v, "role": _owner_role, "right": _owner_right, "class": _owner_class,
               "institution": _owner_institution}
SUBJECT_KINDS = ("agent",)              # grant subjects today; "office", "institution" later (subjects_of)


def subjects_of(k, aid) -> list:
    """The grant subjects an agent answers to (today: itself)."""
    return [f"agent:{aid}"]


# ====================================================================== state
def install(k) -> None:
    """Kernel construction: an empty working copy of every provisioned directory (nothing when off; Frozen.load fills the
    namespace stores from the run's frozen base)."""
    st = stores(k.spec)
    if not st:
        return
    k.w["dirs"] = {n: {**s, "files": {}, "grants": copy.deepcopy(s.get("grants") or {})} for n, s in st.items()}


def create(k, name, conf) -> None:
    """The hook for directories made in-world (an institution's records office, a bought library): a run-scoped store. The
    mechanic that calls it (founding, purchase) is future work."""
    k.w.setdefault("dirs", {})
    if name in k.w["dirs"]:
        raise _err(f"a directory {name} exists")
    k.w["dirs"][name] = {"owner": conf["owner"], "scope": "run", "namespace": None, "max_bytes": int(conf.get("max_bytes", DEFAULTS["max_bytes"])),
                         "max_file_bytes": int(conf.get("max_file_bytes", DEFAULTS["max_file_bytes"])), "records": False,
                         "title": conf.get("title") or f"the directory {name}", "readonly": [], "files": {}, "grants": {}}


def _dirs(k) -> dict:
    return k.w.get("dirs") or {}


def is_owner(k, aid, d) -> bool:
    kind, _, v = d["owner"].partition(":")
    a = k.w["agents"].get(aid)
    if not a or a.get("departed") is not None:
        return False
    return bool(OWNER_KINDS[kind](k, aid, v))


def _match(path: str, prefix: str) -> bool:
    return prefix == "" or path == prefix or path.startswith(prefix if prefix.endswith("/") else prefix + "/") \
        or (prefix.endswith("/") and path.startswith(prefix))


def level(k, aid, d, path: str | None = None) -> str:
    """An agent's access to a path of a directory (or, with path None, its best access anywhere): write | read | none."""
    if is_owner(k, aid, d):
        return "write"
    a = k.w["agents"].get(aid)
    if not a or a.get("departed") is not None:
        return "none"
    best, blen = "none", -1
    for subj in subjects_of(k, aid):
        for prefix, lv in (d["grants"].get(subj) or {}).items():
            if path is None:
                if LEVELS.index(lv) > LEVELS.index(best):
                    best = lv
            elif _match(path, prefix) and len(prefix) > blen:
                best, blen = lv, len(prefix)
    return best


def reachable(k, aid) -> list:
    """The directories an agent can reach (owner, or any grant above none), in name order."""
    return [n for n, d in sorted(_dirs(k).items()) if level(k, aid, d) != "none"]


def static_access(inst, a) -> bool:
    """action_registry "dir:any": directories are provisioned here; with no kernel (the system prompt written at the start), only
    owners see the actions (by role holders in the instance, id, class or rights); with a kernel `when` (has_any) decides."""
    try:
        st = stores(inst)
    except ValueError:
        return False
    if not st:
        return False
    holders = ((inst.get("roles") or {}).get("holders") or {}) if isinstance(inst, dict) else {}
    for d in st.values():
        if any(lv != "none" for lv in ((d.get("grants") or {}).get(f"agent:{a['id']}") or {}).values()):
            return True                                                 # an initial grant (a clerk)
        kind, _, v = d["owner"].partition(":")
        if (kind == "agent" and a["id"] == v or kind == "role" and a["id"] in (holders.get(v) or ())
                or kind == "class" and (a.get("cls") == v or v in (a.get("also") or ())) or kind == "right" and v in (a.get("rights") or ())):
            return True
    return False


def has_any(inst, k, a, rights) -> bool:
    """action_registry `when`: the agent can reach a directory."""
    return bool(reachable(k, a["id"]))


def can_write_any(inst, k, a, rights) -> bool:
    return any(level(k, a["id"], _dirs(k)[n]) == "write" for n in reachable(k, a["id"]))


def owns_any(inst, k, a, rights) -> bool:
    return any(is_owner(k, a["id"], d) for d in _dirs(k).values())


def _pick(k, aid, name=None):
    names = reachable(k, aid)
    if name in (None, ""):
        if len(names) == 1:
            return names[0], _dirs(k)[names[0]]
        raise _err("say which directory (\"dir\"): " + (", ".join(names) if names else "you cannot reach any directory"))
    name = str(name)
    if name not in names:
        raise _err(f"no directory {name!r} you can reach; yours: {', '.join(names) or 'none'}")
    return name, _dirs(k)[name]


def norm_path(path, what="path") -> str:
    """A relative file path ('people/Siv.md'): letters, digits, . _ - space and /; no '..', no leading /, at most PATH_MAX."""
    p = str(path if path is not None else "").strip().replace("\\", "/")
    if p.startswith("/"):
        raise _err(f"{what} {p!r}: paths are relative (no leading '/')")
    p = re.sub(r"/+", "/", p).strip("/")
    if not p:
        raise _err(f"a {what} is needed (e.g. \"rounds/r03.md\")")
    if len(p) > PATH_MAX:
        raise _err(f"{what} too long ({len(p)} characters; at most {PATH_MAX})")
    if not PATH_RE.match(p):
        raise _err(f"{what} {p!r}: use letters, digits, '.', '_', '-', spaces and '/' only")
    if any(seg in ("", ".", "..") for seg in p.split("/")):
        raise _err(f"{what} {p!r}: no '.' or '..' segments")
    if p.count("/") > 6:
        raise _err(f"{what} {p!r}: at most 7 levels deep")
    return p


def norm_prefix(prefix) -> str:
    """A grant's or a listing's prefix: '' (everything), a folder ('people/') or a file path."""
    if prefix in (None, "", "/", "*"):
        return ""
    s = str(prefix).strip()
    folder = s.endswith("/") or s.endswith("*")
    p = norm_path(s.rstrip("*"), "prefix")
    return p + "/" if folder else p


def _size(d) -> int:
    return sum(len(t.encode()) for t in d["files"].values())


def _need(k, aid, d, path, want):
    lv = level(k, aid, d, path)
    if want == "read" and lv == "none" or want == "write" and lv != "write":
        raise _err(f"you have no {want} access to {path}")
    if want == "write" and any(_match(path, r) for r in d.get("readonly") or ()):
        raise _err(f"{path} is read-only (written by the world, not by agents)")


def _readable(k, aid, d) -> list:
    return [p for p in sorted(d["files"]) if level(k, aid, d, p) != "none"]


# ====================================================================== look-ups
def dir_list(k, aid, dir=None, prefix=None) -> str:
    name, d = _pick(k, aid, dir)
    pre = norm_prefix(prefix)
    paths = [p for p in _readable(k, aid, d) if _match(p, pre)]
    head = (f"Directory {name} ({d['title']}): {len(d['files'])} file(s), {_size(d)} of {d['max_bytes']} bytes; your access: "
            f"{'owner' if is_owner(k, aid, d) else level(k, aid, d)}.")
    if not paths:
        return head + (f" Nothing under {pre!r}." if pre else " Nothing you can read yet.")
    return head + "\n" + "\n".join(f"- {p} ({len(d['files'][p].encode())} bytes, {d['files'][p].count(chr(10)) + 1} lines)"
                                   for p in paths)


def dir_read(k, aid, path=None, dir=None, from_line=None, to_line=None) -> str:
    name, d = _pick(k, aid, dir)
    p = norm_path(path)
    if p not in d["files"]:
        raise _err(f"no file {p} in {name} (dir_list lists them)")
    _need(k, aid, d, p, "read")
    lines = d["files"][p].split("\n")
    a = max(1, int(from_line or 1))
    b = min(len(lines), int(to_line or (a + READ_LINES - 1)), a + READ_LINES - 1)
    body = "\n".join(f"{i:>4} {lines[i - 1]}" for i in range(a, b + 1))
    more = f" (more: from_line {b + 1})" if b < len(lines) else ""
    return f"{name}/{p}: lines {a}-{b} of {len(lines)}{more}\n{body}"


def dir_search(k, aid, query=None, dir=None, prefix=None) -> str:
    name, d = _pick(k, aid, dir)
    words = [w for w in re.findall(r"\w+", str(query or "").lower()) if w]
    if not words:
        raise _err("dir_search needs a query")
    pre = norm_prefix(prefix)
    hits, files = [], 0
    for p in _readable(k, aid, d):
        if not _match(p, pre):
            continue
        got = False
        for i, line in enumerate(d["files"][p].split("\n"), 1):
            low = (p + " " + line).lower()
            if all(w in low for w in words):
                got = True
                if len(hits) < SEARCH_HITS:
                    hits.append(f"{p}:{i}: {line.strip()[:200]}")
        files += got
    if not hits:
        return f"No lines in {name} match {query!r}."
    return f"{name}: lines matching {query!r} in {files} file(s)" + (f" (first {SEARCH_HITS})" if len(hits) >= SEARCH_HITS else "") \
        + ":\n" + "\n".join(hits)


def lookup(k, aid, name, args: dict) -> str:
    """context.lookup's branch for the directory look-ups."""
    args = dict(args or {})
    fn = {"dir_list": dir_list, "dir_read": dir_read, "dir_search": dir_search}[name]
    allowed = {"dir_list": ("dir", "prefix"), "dir_read": ("path", "dir", "from_line", "to_line"),
               "dir_search": ("query", "dir", "prefix")}[name]
    if "q" in args and "query" not in args:
        args["query"] = args.pop("q")
    return fn(k, aid, **{x: v for x, v in args.items() if x in allowed})


# ====================================================================== changes (routed primitives)
def _apply(k, name, **payload):
    out = k.apply(name, **payload)
    if not out.ok:
        raise _err("a law blocked this" + (f" (law {', '.join(out.blocked_by)}: {out.reason})" if getattr(out, "reason", None) else ""))
    return out.result


def _check_size(d, path, new_text, old_path=None):
    b = len(str(new_text).encode())
    if b > d["max_file_bytes"]:
        raise _err(f"a file holds at most {d['max_file_bytes']} bytes; this one would be {b}")
    total = _size(d) - len(d["files"].get(path, "").encode()) - (len(d["files"].get(old_path, "").encode()) if old_path else 0) + b
    if total > d["max_bytes"]:
        raise _err(f"the directory holds at most {d['max_bytes']} bytes; this would make it {total}")


def dir_write(k, aid, path=None, text=None, mode="replace", dir=None) -> str:
    name, d = _pick(k, aid, dir)
    p = norm_path(path)
    _need(k, aid, d, p, "write")
    mode = str(mode or "replace")
    if mode not in ("replace", "append"):
        raise _err('mode is "replace" or "append"')
    text = "" if text is None else str(text)
    old = d["files"].get(p)
    new = (old.rstrip("\n") + "\n" + text) if mode == "append" and old else text
    _check_size(d, p, new)
    _apply(k, "dir_write", agent=aid, dir=name, path=p, op="append" if mode == "append" and old else "write", text=new)
    return f"Saved {name}/{p} ({len(new.encode())} bytes); the directory now holds {_size(d)} of {d['max_bytes']} bytes."


def dir_edit(k, aid, path=None, find=None, replace="", dir=None) -> str:
    name, d = _pick(k, aid, dir)
    p = norm_path(path)
    _need(k, aid, d, p, "write")
    if p not in d["files"]:
        raise _err(f"no file {p} in {name}")
    find = "" if find is None else str(find)
    if not find:
        raise _err('dir_edit needs "find": the exact text to replace')
    n = d["files"][p].count(find)
    if not n:
        raise _err(f"{p} does not contain that text (dir_read shows it; the match is exact)")
    new = d["files"][p].replace(find, "" if replace is None else str(replace))
    _check_size(d, p, new)
    _apply(k, "dir_write", agent=aid, dir=name, path=p, op="edit", text=new)
    return f"Edited {name}/{p}: {n} replacement(s); it now holds {len(new.encode())} bytes."


def dir_move(k, aid, path=None, to=None, dir=None) -> str:
    name, d = _pick(k, aid, dir)
    p, q = norm_path(path), norm_path(to, "destination")
    _need(k, aid, d, p, "write")
    _need(k, aid, d, q, "write")
    if p not in d["files"]:
        raise _err(f"no file {p} in {name}")
    if q in d["files"]:
        raise _err(f"{q} exists (delete it first, or choose another name)")
    _apply(k, "dir_write", agent=aid, dir=name, path=p, op="move", to=q)
    return f"Moved {name}/{p} to {q}."


def dir_delete(k, aid, path=None, dir=None) -> str:
    name, d = _pick(k, aid, dir)
    p = norm_path(path)
    _need(k, aid, d, p, "write")
    if p not in d["files"]:
        raise _err(f"no file {p} in {name}")
    _apply(k, "dir_write", agent=aid, dir=name, path=p, op="delete")
    return f"Deleted {name}/{p}."


def change_dir_write(k, agent, dir, path, op, text=None, to=None) -> dict:
    """The dir_write primitive: one file of a directory written (write, append, edit), moved or deleted (the action has checked
    access, paths and sizes). Hooks see who changed which path of which directory, never the text."""
    files = k.w["dirs"][dir]["files"]
    if op == "move":
        files[to] = files.pop(path)
    elif op == "delete":
        files.pop(path, None)
    else:
        files[path] = str(text)
    return {"dir": dir, "path": to if op == "move" else path}


def dir_grant(k, aid, agent=None, path=None, access="read", dir=None, path_or_prefix=None, prefix=None) -> str:
    name, d = _pick(k, aid, dir)
    if not is_owner(k, aid, d):
        raise _err(f"only the owner of {name} can grant access")
    who = str(agent or "")
    if who not in k.w["agents"] or who == aid or k.w["agents"][who].get("cls") == "observer":
        raise _err(f"unknown agent {who!r}")
    access = str(access or "read")
    if access not in LEVELS:
        raise _err('access is "read", "write" or "none" (revokes)')
    pre = norm_prefix(next((x for x in (path, path_or_prefix, prefix) if x not in (None,)), ""))
    _apply(k, "dir_grant", agent=aid, dir=name, grantee=who, path=pre, access=access)
    what = f"{name}/{pre}" if pre else f"all of {name}"
    return f"{who} now has {access} access to {what}." if access != "none" else f"{who}'s access to {what} is revoked."


def change_dir_grant(k, agent, dir, grantee, path, access) -> dict:
    """The dir_grant primitive: the owner sets a subject's access to a path or prefix (none revokes). The grantee is told."""
    d = k.w["dirs"][dir]
    g = d["grants"].setdefault(f"agent:{grantee}", {})
    g[path] = access
    if access == "none" and not any(_match(path, p) and p != path for p in g):
        g.pop(path)                                                   # nothing broader to override: drop the entry
    if not g:
        d["grants"].pop(f"agent:{grantee}", None)
    where = f"{dir}/{path}" if path else f"the whole of {dir}"
    k.notify(grantee, f"{agent} gave you {access} access to {where} ({d['title']}): dir_list, dir_read and dir_search "
             f"{{\"dir\": \"{dir}\", ...}}" + (", dir_write and dir_edit" if access == "write" else "") + "." if access != "none" else
             f"{agent} revoked your access to {where}.", by=agent)
    return {"dir": dir, "grantee": grantee, "access": access}


# ====================================================================== prompt
def tree(d, paths, n) -> str:
    out = [f"- {p} ({len(d['files'][p].encode())} bytes)" for p in paths[:n]]
    if len(paths) > n:
        out.append(f"- ... {len(paths) - n} more (dir_list)")
    return "\n".join(out) or "(empty)"


CHRONICLE_GUIDE = ("Suggested structure: evidence/ (copies of documents, posts, messages and records, one file per item, with the "
                   "round and source), rounds/ (one account per round: rounds/r01.md, rounds/r02.md, ...), people/ (a profile per "
                   "individual: people/<Name>.md), institutions/ (laws, polities, contracts, outlets), timeline.md (the whole story "
                   "in brief).")


def turn_section(k, aid) -> str:
    """The turn prompt's "Your directories" section: each directory the agent can reach, with a compact tree."""
    names = reachable(k, aid)
    if not names:
        return ""
    n = int(cfg(k)["tree_lines"])
    parts = []
    for name in names:
        d = _dirs(k)[name]
        own = is_owner(k, aid, d)
        paths = _readable(k, aid, d)
        recs = [p for p in paths if p.startswith(RECORDS)]
        rest = [p for p in paths if not p.startswith(RECORDS)]
        head = (f"{name} ({d['title']}; {'yours' if own else 'shared with you: ' + level(k, aid, d)}; {len(d['files'])} file(s), "
                f"{_size(d)} of {d['max_bytes']} bytes"
                + (", persists into later worlds" if d["scope"] == "namespace" else "") + "):")
        body = tree(d, rest, n)
        if not own:
            lv = level(k, aid, d)
            body += ("\nUse dir_list, dir_read and dir_search (look-ups)" + (", and dir_write, dir_edit, dir_move, dir_delete where "
                     "you may write" if lv == "write" else "") + f", with \"dir\": \"{name}\".")
        if recs:
            body += f"\nRecords of {len(recs)} earlier world(s) (read-only): " + ", ".join(recs[-8:]) \
                + (" ..." if len(recs) > 8 else "")
        parts.append(head + "\n" + body)
    return "\n\n".join(parts)


def role_text(inst) -> str:
    """The Historian's role text (roles.role_text)."""
    st = stores(inst).get("chronicle")
    keep = (" It persists: what you write is inherited by the Historians of later worlds on this world's line, and you inherit "
            "theirs, with a digest of each earlier world (rounds, laws, deaths, headlines) under _records/ (read-only).") \
        if st and st["scope"] == "namespace" else ""
    return ("You hold the role Historian (the chronicle right): you keep the chronicle, a directory of text files that only you "
            "and those you grant can read." + keep + " Write, edit, move and delete files (dir_write, dir_edit, dir_move, "
            "dir_delete), read, list and search them (dir_read, dir_list, dir_search: look-ups), and grant any agent read or write "
            "access to a file or a folder (dir_grant; access none revokes). " + CHRONICLE_GUIDE)


# ====================================================================== scripted bots (dry runs)
def scripted_actions(k, a, n_actions) -> list:
    """ScriptedPolicy: an owner's bot writes this round's account, a profile, a piece of evidence, and in its second round grants
    the first other agent read access to people/ (deterministic; no RNG)."""
    aid = a["id"]
    mine = [n for n, d in sorted(_dirs(k).items()) if is_owner(k, aid, d)]
    if not mine or not n_actions:
        return []
    name, r = mine[0], k.r + 1
    seen = [e for e in k.events if e.get("vis") == "public" and e.get("round") == k.r - 1]
    others = [x for x in k.players() if x != aid]
    who = others[(r - 1) % len(others)] if others else aid
    acts = [("dir_write", {"dir": name, "path": f"rounds/r{r:02d}.md",
                           "text": f"# Round {r}\n\nIn round {max(1, r - 1)} the board showed {len(seen)} public items. " * 4}),
            ("dir_write", {"dir": name, "path": f"people/{who}.md", "mode": "append",
                           "text": f"Round {r}: {who} was seen in the world; notes on {who} continue. " * 4}),
            ("dir_write", {"dir": name, "path": f"evidence/r{r:02d}-board.md",
                           "text": f"Evidence from round {r}: {len(seen)} public items on the board. " * 4})]
    if r == 2 and others:
        acts.append(("dir_grant", {"dir": name, "agent": others[0], "path": "people/", "access": "read"}))
    return [{"action": n, "args_json": json.dumps(x)} for n, x in acts]


# ====================================================================== snapshots (scoring)
ROUND_PATH = re.compile(r"(?:^|/)r(?:ound)?[ _-]?0*(\d{1,3})(?=\D|$)", re.I)
ROUND_TEXT = re.compile(r"\bround[ _-]?0*(\d{1,3})\b", re.I)


def file_index(text: str, path: str, names) -> dict:
    """What a file covers: its size, the rounds it names (path or text, 1-based) and the agents it mentions."""
    rounds = {int(x) for x in ROUND_PATH.findall(path)} | {int(x) for x in ROUND_TEXT.findall(text)}
    hay = path + "\n" + text
    agents = [n for n in names if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", hay)]
    return {"bytes": len(text.encode()), "rounds": sorted(rounds), "agents": agents}


def round_record(k) -> dict:
    """snapshot["directories"] (monitor-only): per directory, its owners and each file's index (not its text). {} when off."""
    if not _dirs(k):
        return {}
    names = [a for a in k.w["agents"] if k.w["agents"][a].get("cls") != "observer"]
    out = {}
    for name, d in sorted(_dirs(k).items()):
        owners = [a for a in names if is_owner(k, a, d)]
        writers = [a for a in names if a not in owners and level(k, a, d) == "write"]
        out[name] = {"owners": owners, **({"writers": writers} if writers else {}),
                     "files": {p: file_index(t, p, names) for p, t in sorted(d["files"].items())
                               if not p.startswith(RECORDS) and not any(_match(p, ro) for ro in d.get("readonly") or ())}}
    return {"directories": out}


# ====================================================================== persistence (frozen per run, written back)
FROZEN_DIR = "directories"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def live_dir(sp, name, store) -> Path:
    """<directories.path>/<namespace>/<name>/ (a relative path is under the repository root, like the shared archive)."""
    root = Path(cfg(sp)["path"])
    root = root if root.is_absolute() else AGNET / root
    return root / (re.sub(r"[^A-Za-z0-9_.-]+", "-", store["namespace"]).strip("-") or "default") / name


def read_tree(root: Path) -> dict:
    """{relative path: text} of every file under root (dot files and temp files skipped)."""
    out = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts):
            try:
                rel = norm_path(str(p.relative_to(root)))
            except Exception:
                continue
            out[rel] = p.read_text(errors="replace")
    return out


def _atomic_write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.parent / f".{p.name}.{os.getpid()}.tmp"
    tmp.write_text(text)
    os.replace(tmp, p)


class Frozen:
    """A run's frozen directories: base.json (store -> path -> blob sha, the live tree at the start), state.json (publish flag and
    the manifest last written back), and the write-back. Only namespace-scoped stores are frozen."""

    def __init__(self, out, spec):
        self.out, self.spec = Path(out), spec
        self.dir = self.out / FROZEN_DIR
        self.stores = {n: s for n, s in stores(spec).items() if s["scope"] == "namespace"}

    @classmethod
    def open(cls, out, spec, resume=False, base_from=None, publish=None, dry=False):
        """None when no directory is provisioned. A fresh start snapshots the live trees (or copies base_from's base: a replay); a
        resume keeps its base. publish: False never writes back (replays, forks); None keeps the stored choice (default: write
        back unless the run is dry and directories.publish_dry is off)."""
        if not stores(spec):
            return None
        from charter import provenance as PV
        fz = cls(out, spec)
        fz.dir.mkdir(parents=True, exist_ok=True)
        bp = fz.dir / "base.json"
        src = Path(base_from) / FROZEN_DIR / "base.json" if base_from is not None else None
        if src is not None and src.exists():
            base = json.loads(src.read_text())
            PV.copy_blobs(base_from, out, [h for files in base["stores"].values() for h in files.values()])
            bp.write_text(json.dumps({**base, "copied_from": str(Path(base_from).resolve())}, indent=1))
        elif not (resume and bp.exists()):
            fz.take()
        st = fz.state()
        if not resume:
            st["published"] = fz.base()["stores"]
        if publish is not None:
            st["publish"] = bool(publish)
        st.setdefault("publish", bool(cfg(spec)["publish_dry"]) or not dry)
        st.setdefault("published", fz.base()["stores"])
        fz._write_state(st)
        return fz

    def take(self) -> dict:
        from charter import provenance as PV
        out = {}
        for name, s in self.stores.items():
            files = read_tree(live_dir(self.spec, name, s))
            out[name] = {p: PV.put_blob(self.out, t) for p, t in sorted(files.items())}
        base = {"stores": out, "taken": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "sources": {n: str(live_dir(self.spec, n, s)) for n, s in self.stores.items()},
                "hash": hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()[:16]}
        (self.dir / "base.json").write_text(json.dumps(base, indent=1))
        return base

    def base(self) -> dict:
        return json.loads((self.dir / "base.json").read_text())

    def state(self) -> dict:
        try:
            return json.loads((self.dir / "state.json").read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_state(self, st) -> None:
        (self.dir / "state.json").write_text(json.dumps(st, indent=1))

    def info(self) -> dict:
        b = self.base()
        return {"hash": b.get("hash"), "stores": {n: len(f) for n, f in b["stores"].items()}, "publish": self.state().get("publish")}

    def load(self, k) -> None:
        """A fresh start: the kernel's working copies start from the frozen base."""
        from charter import provenance as PV
        for name, files in self.base()["stores"].items():
            if name in k.w.get("dirs", {}):
                k.w["dirs"][name]["files"] = {p: PV.get_blob(self.out, h) for p, h in sorted(files.items())}

    def write_back(self, k) -> int:
        """Apply this run's changes since its last write-back to the live trees (see the module docstring). The files written."""
        st = self.state()
        if not st.get("publish"):
            return 0
        from charter import provenance as PV
        pub = st.get("published") or {}
        n = 0
        for name, s in self.stores.items():
            d = (k.w.get("dirs") or {}).get(name)
            if d is None:
                continue
            root = live_dir(self.spec, name, s)
            prev = pub.get(name) or {}
            now = {}
            for p, t in sorted(d["files"].items()):
                h = PV.put_blob(self.out, t)
                now[p] = h
                if prev.get(p) != h:
                    _atomic_write(root / p, t)
                    n += 1
            for p, h in prev.items():
                if p not in now:
                    f = root / p
                    if f.exists() and PV.blob_sha(f.read_bytes()) == h:  # untouched by another run since this one saw it
                        f.unlink()
                        n += 1
            pub[name] = now
        st["published"] = pub
        st["written_back_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self._write_state(st)
        return n

    def finish(self, k, run_id: str, events: list, inst: dict) -> int:
        """End of a complete run: write back, then the public digest of the run into each store with records."""
        n = self.write_back(k)
        if not self.state().get("publish"):
            return n
        for name, s in self.stores.items():
            if s["records"]:
                text = digest(k, run_id, events, inst, name)
                (self.dir / f"records-{name}.md").write_text(text)
                _atomic_write(live_dir(self.spec, name, s) / RECORDS / f"{run_id}.md", text)
                n += 1
        return n


def digest(k, run_id, events, inst, store) -> str:
    """A compact public digest of a run: per round, the laws enacted and repealed, deaths, and public post headlines; then who
    held the store and the access granted in it."""
    pub = [e for e in events if e.get("vis") == "public"]
    rounds = int(inst.get("rounds") or 0)
    lines = [f"# Record of world {run_id}", "",
             f"{len([a for a in inst['agents']])} agents, {rounds} rounds. Public record only (what anyone could see).", ""]
    for r in range(rounds):
        evs = [e for e in pub if e.get("round") == r]
        items = []
        for e in evs:
            t, a, dd = e.get("type"), e.get("agent"), e.get("data") or {}
            if t == "enact":
                items.append(f"law enacted: {dd.get('law') or dd.get('id') or ''} {dd.get('title') or ''}".strip())
            elif t == "repeal":
                items.append(f"law repealed: {dd.get('law') or ''}")
            elif t in ("disabled", "death", "died"):
                items.append(f"{dd.get('agent') or a} left the game ({dd.get('cause') or t})")
            elif t in ("post", "publish", "story", "edition"):
                txt = str(dd.get("text") or dd.get("title") or dd.get("headline") or "").strip().split("\n")[0][:100]
                if txt:
                    items.append(f"{a or 'anonymous'}: {txt}")
        if items:
            lines.append(f"## Round {r + 1}")
            lines += [f"- {x}" for x in items[:25]] + ([f"- ... {len(items) - 25} more public items"] if len(items) > 25 else [])
            lines.append("")
    d = (k.w.get("dirs") or {}).get(store) or {}
    owners = [a for a in k.w["agents"] if d and is_owner(k, a, d)]
    lines.append(f"## The {store}")
    lines.append(f"Kept by: {', '.join(owners) or 'nobody at the end'}; {len(d.get('files') or {})} file(s) at the end.")
    for subj, g in sorted((d.get("grants") or {}).items()):
        lines.append(f"- {subj.split(':', 1)[1]}: " + ", ".join(f"{lv} {p or '(all)'}" for p, lv in sorted(g.items())))
    return "\n".join(lines) + "\n"
