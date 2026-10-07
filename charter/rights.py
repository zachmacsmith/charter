"""The rights registry: every right the code knows by name, declared once, with what the manual says about it and how the kernel
treats it. The old constants (kernel.KERNEL_RIGHTS, ENTRENCHED, NEVER, SECRET_RIGHTS, RENAMED_RIGHTS, manual.RIGHT_DOC,
roles.RIGHTS) are derived from it, so call sites do not change.

An entry:  register(name, doc, kind, origin, secret=False, entrenched=False, never=(), role=None, aliases=())
  doc         the manual's line for the right ("Your rights")
  kind        office    a position of power (vote, propose, veto, judge, ...): what goals count as offices
              tool      a class's tool (sandbox, archive, encrypt, see_hidden, anon)
              property  a harvest right (the `harvest:*` family)
              role      carried by a role and by nothing else (maker, scholar, impersonate)
  origin      kernel    in the starting catalogue of every world
              camp      one per camp (`harvest:<camp>`), added with the camp
              role      added to the catalogue by the roles module
              law       created by a law (create_right), e.g. by library laws and regime constitutions
  secret      bool, or a predicate (k, name) -> bool: the right and who holds it are invisible to laws (holders, has, rights_of),
              to public previews and to other agents. Its holder still sees it in its own manual.
  entrenched  no law can grant, revoke or suspend it, nor create a right of that name
  never       classes that can never be granted it by law (the Board holds nothing but veto: kernel.NEVER)
  role        the role that carries it (roles.RIGHTS). A right of kind "role" changes only with its role: laws cannot grant, revoke
              or suspend it, nor create a right of its name, so the role and the right cannot disagree.
  aliases     old names (checkpoint migration, kernel.norm_right, __main__'s instance check)

Rights that laws create (create_right) are not registered unless the code depends on their names (decree, elector); any other
name is valid only once it is in the world's catalogue (k.w["rights"]). `lookup(name, catalogue)` resolves both; any other name
raises UnknownRight.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

KINDS = ("office", "tool", "property", "role")
ORIGINS = ("kernel", "camp", "role", "law")
HARVEST = "harvest:*"


class UnknownRight(KeyError):
    pass


@dataclass(frozen=True)
class Right:
    name: str
    doc: str
    kind: str
    origin: str
    secret: bool | Callable = False
    entrenched: bool = False
    never: tuple = ()
    role: str | None = None
    aliases: tuple = ()

    def doc_for(self, name: str) -> str:
        return self.doc.format(camp=name.split(":", 1)[1]) if self.name == HARVEST else self.doc


REG: dict[str, Right] = {}
ALIASES: dict[str, str] = {}


def register(name, doc, kind, origin, secret=False, entrenched=False, never=(), role=None, aliases=()) -> Right:
    if kind not in KINDS or origin not in ORIGINS:
        raise ValueError(f"right {name}: bad kind {kind!r} or origin {origin!r}")
    if name in REG or name in ALIASES:
        raise ValueError(f"right {name} registered twice")
    REG[name] = Right(name, doc, kind, origin, secret, entrenched, tuple(never), role, tuple(aliases))
    for a in aliases:
        ALIASES[a] = name
    return REG[name]


def _secret_camp(k, name) -> bool:
    return bool(k is not None and k.w["camps"].get(name.split(":", 1)[1], {}).get("secret"))


R = register
# the kernel's catalogue (every world)
R("vote", "vote in ballots you are in the electorate of", "office", "kernel", never=("fixer",))
R("propose", "propose laws (propose)", "office", "kernel", never=("fixer",))
R("veto", "veto structural and procedural laws in their window", "office", "kernel", entrenched=True, never=("fixer",))
R("patch", "patch laws (Fixer)", "office", "kernel", entrenched=True)
R("archive", "read, search and write the Scientists' archive", "tool", "kernel", entrenched=True)
R("sandbox", "run code (run_python)", "tool", "kernel")
R("judge", "rule on court cases (rule)", "office", "kernel")
R("press", "Media's press: publish, write_digest, report, channels", "office", "kernel", role="media")
R("dm_rules", "set the private-message limit (set_dm_limit)", "office", "kernel")
R("surveil", "read others' unencrypted private messages in your feed", "office", "kernel")
R("ledger_read", "see everyone's holdings value", "office", "kernel")
R("encrypt", "send encrypted private messages", "tool", "kernel")
R("see_hidden", "see posts hidden by law", "tool", "kernel")
R("anon", "post anonymously (anon_post)", "tool", "kernel")
# one per camp; secret when the camp is (hidden powers: secret camps)
R(HARVEST, "harvest at {camp}", "property", "camp", secret=_secret_camp)
# carried by roles (the roles module adds them to the catalogue)
R("maker", "make new agents: to order (a commission) or your own (create_agent, copy_agent)", "role", "role", role="maker")
R("scholar", "sell memory (file space and pin slots) and keep a library", "role", "role", role="scholar")
R("impersonate", "send private messages that look like another agent's (forge_dm)", "role", "role", secret=True, role="spy",
  aliases=("forge",))
# created by library laws and regime constitutions, named in code (goals' offices)
R("decree", "a right created by law", "office", "law")
R("elector", "a right created by law", "office", "law")


# ---------------------------------------------------------------------- lookups
def canonical(name: str) -> str:
    """An old name -> today's (forge -> impersonate); any other name unchanged."""
    return ALIASES.get(str(name), str(name))


def get(name: str) -> Right:
    """The registered entry for a right (`harvest:<camp>` -> the harvest family). Raises UnknownRight for anything else."""
    n = canonical(name)
    if n in REG:
        return REG[n]
    if n.startswith("harvest:") and n != HARVEST:
        return REG[HARVEST]
    raise UnknownRight(f"unknown right {name!r}: register it in charter/rights.py, or create it by law (create_right)")


def created_by_law(name: str) -> Right:
    return Right(str(name), "a right created by law", "office", "law")


def lookup(name: str, catalogue=()) -> Right:
    """The entry for a right: registered, a harvest right, or one a law created (it is in `catalogue`, the world's k.w["rights"]).
    Raises UnknownRight for a name that is none of these."""
    try:
        return get(name)
    except UnknownRight:
        if str(name) in set(catalogue):
            return created_by_law(name)
        raise


def doc(name: str, catalogue=()) -> str:
    return lookup(name, catalogue).doc_for(str(name))


def is_registered(name: str) -> bool:
    try:
        get(name)
        return True
    except UnknownRight:
        return False


def is_secret(k, name: str) -> bool:
    """The one secrecy check: a secret right (and who holds it) is never shown to laws, previews or other agents.
    Rights created by law are never secret."""
    if not is_registered(name):
        return False
    s = get(name).secret
    return bool(s(k, canonical(name))) if callable(s) else bool(s)


def role_bound(name: str) -> bool:
    """Carried by a role and by nothing else: laws cannot grant, revoke or suspend it, or create a right of its name."""
    return is_registered(name) and get(name).kind == "role"


def reserved(name: str) -> bool:
    """A name create_right refuses: entrenched, carried by a role, or an old name of a registered right."""
    n = str(name)
    return n in ALIASES or (n in REG and (REG[n].entrenched or REG[n].kind == "role"))


def names(**where) -> tuple:
    """Registered right names whose fields match, in registry order (the harvest family excluded)."""
    return tuple(n for n, r in REG.items() if n != HARVEST and all(getattr(r, f) == v for f, v in where.items()))


# ---------------------------------------------------------------------- derived constants (their old homes import these)
KERNEL_RIGHTS = frozenset(names(origin="kernel"))
ENTRENCHED = frozenset(n for n, r in REG.items() if r.entrenched)
NEVER = {"board": None,                                                 # the Board holds nothing but veto (None = all)
         "fixer": {n for n, r in REG.items() if "fixer" in r.never}}
SECRET_RIGHTS = tuple(n for n, r in REG.items() if r.secret is True)   # rights secret by name (harvest:* is secret per camp)
RENAMED_RIGHTS = dict(ALIASES)
ROLE_RIGHTS = frozenset(names(kind="role"))                             # the roles module adds these to the catalogue
RIGHT_OF_ROLE = {r.role: n for n, r in REG.items() if r.role}          # role -> the right it carries (the Spy's included)
PUBLIC_ROLE_RIGHTS = {r.role: n for n, r in REG.items() if r.role and not r.secret}
RIGHT_DOC = {n: r.doc for n, r in REG.items() if n != HARVEST}
OFFICE_RIGHTS = frozenset(names(kind="office"))
TOOL_RIGHTS = frozenset(names(kind="tool"))
