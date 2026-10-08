"""P2.4d (ARCHITECTURE §11, review 03 §2.1, review 04 §4.1, review 08): rights change through the kernel's primitives only.

An agent's rights list (k.w["agents"][aid]["rights"]) and the rights catalogue (k.w["rights"]) are written by charter/dispatch.py
(grant_right, revoke_right, create_right: their physics checks and their `rights` events) and by the kernel itself. A grep over the
package's source (an AST walk, so formatting does not hide a write) finds every write to a `["rights"]` subscript (assignment,
augmented assignment, tuple assignment, a mutating method call) and every mutating call on a local named `rights`. Each one outside
the kernel and the dispatcher must be listed below with its reason. The list may only shrink: the packages that own the remaining
sites (P2.4b mortality/life/events, P2.4c projects, P5.x interventions) remove theirs by routing them through k.apply.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "charter"
ALLOWED_FILES = {"kernel.py": "the kernel (Kernel.__init__, checkpoint migration of renamed rights)",
                 "dispatch.py": "the primitives' changes: do_grant_right, do_revoke_right, do_create_right"}
MUTATORS = {"append", "remove", "extend", "sort", "insert", "clear", "pop", "reverse"}

# (file relative to charter/, qualname) -> why the write is not (yet) through grant_right/revoke_right/create_right
EXCEPTIONS = {
    ("events.py", "leave_world"): "a departure (end_life cause departure, P2.4b): the agent leaves play with its rights cleared, as "
                                  "today's depart did; recorded in the departure event, not a law's grant or revocation",
    ("lawpreview.py", "_procedure"): "the previewer lends the propose right for one call inside a transaction that is undone (P3.5)",
    # world generation: instance dicts before any kernel exists (no k.w, nothing to log)
    ("generator.py", "generate"): "generation: the instance's agents (no kernel yet)",
    ("generator.py", "validate"): "generation: the instance's repairs (no kernel yet)",
    ("regimes.py", "_grant"): "generation: a regime's rights on the instance's agents (no kernel yet)",
    ("regimes.py", "_revoke"): "generation: a regime's rights on the instance's agents (no kernel yet)",
    ("regimes.py", "apply_rights"): "generation: a regime's rights on the instance's agents (no kernel yet)",
    ("camptypes/framework.py", "generate"): "generation: typed camps' harvest rights on the instance's agents (no kernel yet)",
    ("roles.py", "assign"): "generation: role rights on the instance's agents (no kernel yet)",
    ("hidden.py", "generate"): "generation: secret camps' harvest rights on the instance's agents (no kernel yet)",
    ("__main__.py", "_same_instance"): "a saved instance file's renamed rights, compared with a regenerated one (not a world)",
    ("mortality.py", "restore"): "a regenerated instance (resuming from a checkpoint) given back its successors' class and rights",
    ("projects.py", "open_project"): "a project's own 'rights' setting (all | contributors), not a rights list",
    # owned by parallel packages: to be routed by them
    ("projects.py", "_new_camp"): "P2.4c: a funded camp's harvest right (create_right + grant_right, no rights event today)",
    ("events.py", "depart"): "P2.4b: a departing agent's rights cleared (end_life)",
    ("events.py", "h_camp_discovered"): "P2.4b: a discovered camp's harvest right (create_right + grant_right, no rights event today)",
    ("mortality.py", "_disable.lapse"): "P2.4b: a dead agent's rights cleared (end_life)",
    ("mortality.py", "take_seat"): "P2.4b: a Board seat's successor (appoint: the class and rights change together)",
    ("life.py", "ensure_maker"): "P2.4b: the Maker role's right (set_role)",
    ("interventions.py", "_grant"): "P5.x: an intervention's grant (its own logged op)",
    ("interventions.py", "_revoke"): "P5.x: an intervention's revoke (its own logged op)",
}


def _is_rights_subscript(n) -> bool:
    return isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == "rights"


def _targets(t):
    if isinstance(t, (ast.Tuple, ast.List)):
        for x in t.elts:
            yield from _targets(x)
    else:
        yield t


def rights_writes() -> list:
    """[(file, qualname, line)] of every write to a ["rights"] subscript or a local `rights` list, outside ALLOWED_FILES."""
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        rel = str(p.relative_to(ROOT))
        if rel in ALLOWED_FILES:
            continue
        stack: list = []

        class V(ast.NodeVisitor):
            def visit_FunctionDef(self, n):
                stack.append(n.name)
                self.generic_visit(n)
                stack.pop()

            visit_AsyncFunctionDef = visit_ClassDef = visit_FunctionDef

            def hit(self, n):
                out.append((rel, ".".join(stack) or "<module>", n.lineno))

            def visit_Assign(self, n):
                if any(_is_rights_subscript(t) for tt in n.targets for t in _targets(tt)):
                    self.hit(n)
                self.generic_visit(n)

            def visit_AugAssign(self, n):
                if _is_rights_subscript(n.target):
                    self.hit(n)
                self.generic_visit(n)

            def visit_Call(self, n):
                f = n.func
                if isinstance(f, ast.Attribute) and f.attr in MUTATORS and (
                        _is_rights_subscript(f.value) or (isinstance(f.value, ast.Name) and f.value.id == "rights")):
                    self.hit(n)
                self.generic_visit(n)

        V().visit(ast.parse(p.read_text()))
    return out


def test_the_scanner_finds_writes():
    found = {(f, q) for f, q, _ in rights_writes()}
    assert ("generator.py", "generate") in found or ("generator.py", "_assign_rights") in found


def test_rights_are_written_only_through_the_kernel():
    bad = sorted({(f, q, line) for f, q, line in rights_writes() if (f, q) not in EXCEPTIONS})
    assert not bad, ("rights written outside grant_right/revoke_right/create_right (route them through k.apply, or list them in "
                     f"EXCEPTIONS with the reason): {bad}")


def test_p2_4d_modules_write_no_rights():
    """camptypes, jurisdictions, media, roles and hidden write rights only through k.apply once the world exists."""
    mine = ("camptypes/", "jurisdictions.py", "media.py", "roles.py", "hidden.py")
    live = sorted((f, q, line) for f, q, line in rights_writes() if f.startswith(mine)
                  and EXCEPTIONS.get((f, q), "").split(":")[0] != "generation")
    assert not live, live
