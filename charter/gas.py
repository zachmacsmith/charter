"""Gas v2: deterministic metering of law code (ARCHITECTURE P2.2, review 09 §9.6, decisions D-12 and D-20).

Law code is metered by compile-time instrumentation, not by tracing, so a count depends only on the code and its inputs, never on
the Python version or the machine:

* `instrument(tree)` rewrites a checked law module (lawlang.check) before it is compiled. Every block of statements starts with
  `__gas__(n)`, n being the number of statements in the block that run unconditionally from there (a statement that can transfer
  control -- if, for, while, return, break, continue -- ends a run; the next run is charged when it is reached), so a count equals
  one tick per statement executed, like the old one-per-line count. Every loop iteration charges one more tick (the loop header),
  every comprehension iteration one tick (`if __gas__()` is put first in its conditions), every lambda call one tick. Function
  bodies (and the module body) are wrapped in `__gas_d__ = __gas_in__()` / `try: ... finally: __gas_out__(__gas_d__)` to keep
  the Python depth (MAX_DEPTH law frames per call, as before); lambda bodies become `__gas_lin__() and __gas_lout__(body)`.
* Work done inside C code is charged by size, before it is done: the builtins (sum, min, max, sorted, list, tuple, set, dict, any,
  all, str) charge one tick per SIZE_UNIT input elements; `+ * ** << %` (and their augmented forms), comparisons, the costly
  str/list/dict/set methods (join, replace, split, extend, ...), `*`/`**` unpacking and f-string fields are routed through helpers
  that charge by size and refuse results above MAX_SIZE elements or characters, and integers above MAX_BITS bits. Operations
  that cannot outgrow their operands (`x + 1`, `x == 0`, `x in ("a", "b")`) are left as they are. `range` stays lazy and free:
  whatever consumes it is charged by its length.
* The instrumentation names start with `__`, which law code cannot name (lawlang.check rejects names, attributes and parameters
  with leading underscores, and starred targets outside plain assignments), so a law can neither call nor shadow them.

Not charged (bounded by MAX_SIZE times the per-call budget, and fast in C): slicing, hashing a tuple key, sorting comparisons.

The meter is a stack of frames, one per metered call (`Meter.run`). A tick charges the innermost frame's per-call budget and the
shared budgets that frame was opened with (per cascade, per account: plumbing for P3.1; only the per-call budget is used today), so
a law cannot be killed by work done in another law's call. Ticks with no frame open (law code run outside any metered call) are
not charged, as they were not counted before.
"""
from __future__ import annotations

import ast
import operator
import re
import types

MAX_STEPS, MAX_DEPTH = 10_000, 20         # per-call ticks, Python depth of law frames per call (spec law.gas.per_call/python_depth)
MAX_SIZE = 100_000                        # elements or characters of one str / list / tuple / dict / set a law operation may produce
MAX_BITS = 10_000                         # bits of one int a law operation may produce
SIZE_UNIT = 100                           # one tick per this many elements processed inside a builtin, operator or method


class LawError(Exception):
    """A law failed the static check or raised at runtime (message is shown to the proposer / the Fixer)."""


class StepLimit(LawError):
    pass


class GasExhausted(StepLimit):
    """A budget ran out. kind: "call" (today's per-call steps), "cascade" or "account"."""

    def __init__(self, kind: str, limit: int):
        self.kind, self.limit = kind, limit
        super().__init__(f"law exceeded {limit} steps" if kind == "call" else f"law exceeded the {kind} gas budget of {limit} steps")


class DepthExceeded(LawError):
    kind = "depth"

    def __init__(self, limit: int):
        super().__init__(f"law exceeded recursion depth {limit}")


class TooLarge(LawError):
    """An operation was refused before it ran because its result would be too large."""
    kind = "size"


class Budget:
    """A budget shared by several frames (a cascade's, an account's)."""
    __slots__ = ("kind", "limit", "used")

    def __init__(self, kind: str, limit: int, used: int = 0):
        self.kind, self.limit, self.used = kind, limit, used

    def charge(self, n: int) -> None:
        self.used += n
        if self.used > self.limit:
            raise GasExhausted(self.kind, self.limit)


class Frame:
    """One metered call: its own per-call budget and Python depth, plus the shared budgets it also charges."""
    __slots__ = ("limit", "used", "depth", "max_depth", "shared")

    def __init__(self, limit: int, max_depth: int, shared: tuple = ()):
        self.limit, self.used, self.depth, self.max_depth, self.shared = limit, 0, 0, max_depth, shared


class Meter:
    """The meter stack. `run` opens a frame for one call; the instrumented code's helpers (`runtime`) charge the innermost frame."""

    def __init__(self):
        self.stack: list[Frame] = []
        self.top: Frame | None = None
        self.total = 0                    # ticks charged by all frames closed so far (for monitors and tests)
        self.last = 0                     # ticks used by the frame closed last
        self.runtime, self.builtins = _runtime(self)   # name -> callable, put into every law module's namespace

    def run(self, fn, args=(), kw=None, *, per_call=MAX_STEPS, max_depth=MAX_DEPTH, cascade: Budget | None = None,
            account: Budget | None = None):
        f = Frame(per_call, max_depth, tuple(b for b in (cascade, account) if b is not None))
        self.stack.append(f)
        self.top = f
        try:
            return fn(*args, **(kw or {}))
        finally:
            self.stack.pop()
            self.top = self.stack[-1] if self.stack else None
            self.total += f.used
            self.last = f.used

    def tick(self, n=1):
        f = self.top
        if f is not None:
            f.used += n
            if f.used > f.limit:
                raise GasExhausted("call", f.limit)
            for b in f.shared:
                b.charge(n)
        return True

    def enter(self):
        """A law function (or the module body) starts: one more frame of Python depth. Returns the depth before it."""
        f = self.top
        if f is None:
            return 0
        d = f.depth
        if d >= f.max_depth:
            raise DepthExceeded(f.max_depth)
        f.depth = d + 1
        return d

    def exit(self, d=None):
        """A law function returns (or raises): back to depth `d` (which also undoes any lambda left unbalanced by an exception
        caught outside law code), or one less."""
        f = self.top
        if f is not None:
            f.depth = d if d is not None else max(f.depth - 1, 0)

    def enter_lambda(self):
        self.enter()
        return self.tick(1)

    def exit_lambda(self, value):
        f = self.top
        if f is not None and f.depth > 0:
            f.depth -= 1
        return value


# ------------------------------------------------------------------ runtime helpers (bound to one meter)
_SEQ = (str, list, tuple)
_NUM = (int, float, bool)
_INT = (int, bool)


def _runtime(meter: Meter) -> tuple[dict, dict]:
    tick = meter.tick

    def charge(n):
        if n >= SIZE_UNIT:
            tick(n // SIZE_UNIT)

    def cap(n, what="result"):
        if n > MAX_SIZE:
            raise TooLarge(f"{what} too large: {n} elements or characters (at most {MAX_SIZE})")
        charge(n)

    def cap_bits(n):
        if n > MAX_BITS:
            raise TooLarge(f"number too large: about {n} bits (at most {MAX_BITS})")

    def counted(it):
        i = 0
        for x in it:
            i += 1
            if i % SIZE_UNIT == 0:
                tick(1)
                if i > MAX_SIZE:
                    raise TooLarge(f"input too large: more than {MAX_SIZE} elements")
            yield x

    def consume(it, building=False):
        """Charge for an iterable a builtin is about to walk. Sized: by its length (refused above MAX_SIZE when a container is
        built from it); a generator from law code meters itself; anything else (zip, enumerate) is counted as it is walked."""
        try:
            n = len(it)
        except TypeError:
            return it if type(it) is types.GeneratorType else counted(it)
        except OverflowError:
            raise TooLarge("input too large")
        if building:
            cap(n, "input")
        else:
            charge(n)
        return it

    # -------- size of the text str() / format() would produce (containers only; walked, so charged by elements)
    def text_size(x):
        if type(x) not in (list, tuple, dict, set):
            return len(x) if type(x) is str else 0
        size, seen, todo, n = 0, set(), [x], 0
        while todo:
            v = todo.pop()
            n += 1
            t = type(v)
            if t is str:
                size += len(v) + 4
            elif t in _INT:
                size += v.bit_length() // 3 + 2
            elif t in (list, tuple, dict, set):
                if id(v) in seen:
                    size += 5
                    continue
                seen.add(id(v))
                size += 2
                todo.extend(v.items() if t is dict else v)
            else:
                size += 24
            if size > MAX_SIZE:
                break
        charge(n)
        if size > MAX_SIZE:
            raise TooLarge(f"text too large: more than {MAX_SIZE} characters")
        return size

    _width = re.compile(r"(\d+)")
    _pct = re.compile(r"%(?:\([^)]*\))?[#0 +\-]*(\*|\d+)?(?:\.(\*|\d+))?")

    def check_spec(spec):
        for m in _width.finditer(spec):
            if len(m.group(1)) > 6 or int(m.group(1)) > MAX_SIZE:
                raise TooLarge(f"format width too large: {m.group(1)}")

    # -------- builtins
    def m_sum(it, start=0):
        it = consume(it)
        if type(start) in _NUM:
            return sum(it, start)
        acc = start
        for x in it:
            acc = g_add(acc, x)
        return acc

    def m_min(*args, **kw):
        return min(consume(args[0]) if len(args) == 1 else args, **kw)

    def m_max(*args, **kw):
        return max(consume(args[0]) if len(args) == 1 else args, **kw)

    def m_sorted(it, **kw):
        return sorted(consume(it, True), **kw)

    def m_list(it=()):
        return list(consume(it, True))

    def m_tuple(it=()):
        return tuple(consume(it, True))

    def m_set(it=()):
        return set(consume(it, True))

    def m_dict(*args, **kw):
        if args:
            return dict(consume(args[0], True), **kw)
        return dict(**kw)

    def m_any(it):
        return any(consume(it))

    def m_all(it):
        return all(consume(it))

    def m_str(*args, **kw):
        if len(args) == 1 and not kw:
            text_size(args[0])
        return str(*args, **kw)

    builtins = {"sum": m_sum, "min": m_min, "max": m_max, "sorted": m_sorted, "list": m_list, "tuple": m_tuple, "set": m_set,
                "dict": m_dict, "any": m_any, "all": m_all, "str": m_str}

    # -------- operators
    def g_add(a, b):
        ta = type(a)
        if ta in _SEQ and type(b) is ta:
            cap(len(a) + len(b))
        return a + b

    def size_mul(a, b):
        ta, tb = type(a), type(b)
        if ta in _SEQ and tb in _INT:
            cap(len(a) * b if b > 0 else 0)
        elif tb in _SEQ and ta in _INT:
            cap(len(b) * a if a > 0 else 0)
        elif ta in _INT and tb in _INT:
            if a.bit_length() + b.bit_length() > MAX_BITS + 1:
                cap_bits(a.bit_length() + b.bit_length() - 1)
            return True
        return False

    def g_mul(a, b):
        if size_mul(a, b):
            r = a * b
            cap_bits(r.bit_length())
            return r
        return a * b

    def g_pow(a, b):
        if type(a) in _INT and type(b) in _INT and b > 0:
            bl = abs(a).bit_length()
            if bl > 1:
                cap_bits((bl - 1) * b + 1)            # a lower bound of the result's size: refused before computing
                r = a ** b
                cap_bits(r.bit_length())
                return r
        return a ** b

    def g_lshift(a, b):
        if type(a) in _INT and type(b) in _INT and a and b > 0:
            cap_bits(a.bit_length() + b)
        return a << b

    def g_mod(a, b):
        if type(a) is str:
            size = len(a)
            for m in _pct.finditer(a):
                for g in m.groups():
                    if g == "*":
                        raise TooLarge("'*' widths are not supported in % formatting")
                    if g:
                        check_spec(g)
                        size += int(g)
            for v in (b if type(b) is tuple else (b,)):
                size += text_size(v) if type(v) in (list, tuple, dict, set) else (len(v) if type(v) is str else 24)
            cap(size)
        return a % b

    def g_iadd(a, b):
        ta = type(a)
        if ta in _SEQ and type(b) is ta:
            cap(len(a) + len(b))
        elif ta is list:
            try:
                n = len(b)
            except TypeError:
                b = list(consume(b, True))
                n = len(b)
            cap(len(a) + n)
        return operator.iadd(a, b)

    def g_imul(a, b):
        if size_mul(a, b) and type(a) in _INT and type(b) in _INT:
            r = a * b
            cap_bits(r.bit_length())
            return r
        return operator.imul(a, b)

    INPLACE = {"+": g_iadd, "*": g_imul, "**": g_pow, "<<": g_lshift, "%": g_mod}

    def g_augsub(op, c, k, thunk):                    # c[k] op= v, with Python's evaluation order: c, k, c[k], v
        c[k] = INPLACE[op](c[k], thunk())

    def g_augattr(op, o, name, thunk):
        setattr(o, name, INPLACE[op](getattr(o, name), thunk()))

    # -------- comparisons
    def size_cmp(a, b):
        ta = type(a)
        if ta in (list, tuple, dict) and type(b) is ta:
            charge(min(len(a), len(b)))

    def g_in(a, b):
        tb = type(b)
        if tb in (list, tuple, str):
            charge(len(b))
        elif tb is range and type(a) not in _INT:
            charge(len(b))
        return a in b

    CMP = {"==": operator.eq, "!=": operator.ne, "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}

    def g_cmp(op, a, b):
        if op == "in":
            return g_in(a, b)
        if op == "not in":
            return not g_in(a, b)
        if op == "is":
            return a is b
        if op == "is not":
            return a is not b
        size_cmp(a, b)
        return CMP[op](a, b)

    def g_eq(a, b):
        size_cmp(a, b)
        return a == b

    def g_ne(a, b):
        size_cmp(a, b)
        return a != b

    def g_lt(a, b):
        size_cmp(a, b)
        return a < b

    def g_le(a, b):
        size_cmp(a, b)
        return a <= b

    def g_gt(a, b):
        size_cmp(a, b)
        return a > b

    def g_ge(a, b):
        size_cmp(a, b)
        return a >= b

    def g_notin(a, b):
        return not g_in(a, b)

    def g_chain(ops, a, *thunks):                     # a < b < c: each operand evaluated once, left to right, short-circuiting
        for op, th in zip(ops, thunks):
            b = th()
            r = g_cmp(op, a, b)
            if not r:
                return r
            a = b
        return r

    # -------- methods
    def join_cost(sep, items):
        try:
            n = len(items)
        except TypeError:
            items = list(consume(items, True))
            n = len(items)
        else:
            cap(n, "input")
            if type(items) not in (list, tuple):
                items = list(items)
        total = len(sep) * max(n - 1, 0)
        for x in items:
            if type(x) is str:
                total += len(x)
        cap(total)
        return (items,)

    def replace_cost(s, args):
        old, new = args[0], args[1]
        if type(old) is str and type(new) is str:
            hits = s.count(old) if old else len(s) + 1
            if len(args) > 2 and type(args[2]) in _INT and args[2] >= 0:
                hits = min(hits, args[2])
            cap(len(s) + max(len(new) - len(old), 0) * hits)
        return args

    def linear(obj, args):
        charge(len(obj))
        return args

    def extend_cost(lst, args):
        b = args[0]
        try:
            n = len(b)
        except TypeError:
            b = list(consume(b, True))
            n = len(b)
        cap(len(lst) + n)
        return (b,)

    def update_cost(obj, args):
        if args:
            try:
                charge(len(args[0]))
            except TypeError:
                return (list(consume(args[0], True)),) + tuple(args[1:])
        return args

    def range_scan(r, args):
        if args and type(args[0]) not in _INT:
            charge(len(r))
        return args

    METHODS = {
        str: {"join": lambda s, a: join_cost(s, a[0]) if len(a) == 1 else a, "replace": lambda s, a: replace_cost(s, a) if len(a) >= 2 else a,
              "split": linear, "strip": linear, "upper": linear, "count": linear, "index": linear},
        list: {"extend": lambda l_, a: extend_cost(l_, a) if len(a) == 1 else a, "copy": linear, "count": linear, "index": linear,
               "remove": linear, "insert": linear, "sort": linear},
        tuple: {"count": linear, "index": linear},
        dict: {"update": update_cost, "copy": linear},
        set: {"update": update_cost, "copy": linear},
        range: {"count": range_scan, "index": range_scan},
    }

    def g_call(obj, name, *args, **kw):
        cost = METHODS.get(type(obj))
        if cost is not None:
            c = cost.get(name)
            if c is not None:
                args = c(obj, args)
        return getattr(obj, name)(*args, **kw)

    def g_meth(obj, name):                            # a costly method read without calling it (f = s.join)
        if type(obj) in METHODS and name in METHODS[type(obj)]:
            return lambda *a, **kw: g_call(obj, name, *a, **kw)
        return getattr(obj, name)

    # -------- unpacking, f-strings, lambdas
    def g_star(v):
        return consume(v, True)

    def g_fmt(v, conv, spec):
        if conv == 114:
            text_size(v)
            v = repr(v)
        elif conv == 97:
            text_size(v)
            v = ascii(v)
        elif conv == 115:
            text_size(v)
            v = str(v)
        elif type(v) in (list, tuple, dict, set):
            text_size(v)
        if spec:
            check_spec(spec)
        return format(v, spec)

    return {"__gas__": tick, "__gas_in__": meter.enter, "__gas_out__": meter.exit, "__gas_lin__": meter.enter_lambda,
            "__gas_lout__": meter.exit_lambda,
            "__gas_add__": g_add, "__gas_mul__": g_mul, "__gas_pow__": g_pow, "__gas_lshift__": g_lshift, "__gas_mod__": g_mod,
            "__gas_augsub__": g_augsub, "__gas_augattr__": g_augattr, "__gas_slice__": slice,
            "__gas_in_op__": g_in, "__gas_cmp__": g_cmp, "__gas_eq__": g_eq, "__gas_ne__": g_ne,
            "__gas_lt__": g_lt, "__gas_le__": g_le, "__gas_gt__": g_gt, "__gas_ge__": g_ge, "__gas_notin__": g_notin, "__gas_chain__": g_chain,
            "__gas_call__": g_call, "__gas_meth__": g_meth, "__gas_star__": g_star, "__gas_fmt__": g_fmt,
            **{f"__gas_i{k}__": v for k, v in (("add", g_iadd), ("mul", g_imul), ("pow", g_pow), ("lshift", g_lshift), ("mod", g_mod))},
            }, builtins


# ------------------------------------------------------------------ the instrumenting pass
BINOPS = {ast.Add: "add", ast.Mult: "mul", ast.Pow: "pow", ast.LShift: "lshift", ast.Mod: "mod"}
AUGSYM = {ast.Add: "+", ast.Mult: "*", ast.Pow: "**", ast.LShift: "<<", ast.Mod: "%"}
CMPSYM = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.In: "in", ast.NotIn: "not in",
          ast.Is: "is", ast.IsNot: "is not"}
COSTLY_METHODS = {"join", "replace", "split", "strip", "upper", "count", "index", "extend", "copy", "remove", "insert", "sort", "update"}
SIMPLE_STMTS = (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Expr, ast.Pass, ast.Delete, ast.FunctionDef)
PREFIX = "__gas"


CMPFN = {"==": "__gas_eq__", "!=": "__gas_ne__", "<": "__gas_lt__", "<=": "__gas_le__", ">": "__gas_gt__", ">=": "__gas_ge__",
         "in": "__gas_in_op__", "not in": "__gas_notin__"}


def _scalar(n):
    """A constant number, string, bool or None (comparing anything with it takes constant time... or memcmp time for a str)."""
    return isinstance(n, ast.Constant) and type(n.value) in (int, float, bool, str, type(None))


def _number(n, types_=(int, float)):
    return isinstance(n, ast.Constant) and type(n.value) in types_


def _literal(n):
    """A small literal container of constants, or a constant string, as the right side of `in`."""
    return (isinstance(n, ast.Constant) and type(n.value) is str) or (isinstance(n, (ast.Tuple, ast.List, ast.Set))
                                                                       and all(isinstance(e, ast.Constant) for e in n.elts))


def _cheap_binop(node):
    """Operations whose result cannot outgrow their operands, whatever the variable operand is: x + 1 (a str or list plus a number
    fails), x * 0.5 or x ** 0.5 (a float operand), 3 % x."""
    op, a, b = type(node.op), node.left, node.right
    if op is ast.Add:
        return _number(a) or _number(b)
    if op in (ast.Mult, ast.Pow):
        return _number(a, (float,)) or _number(b, (float,))
    if op is ast.Mod:
        return _number(a)
    return False


def _name(n):
    return ast.Name(id=n, ctx=ast.Load())


def _call(fn, *args):
    return ast.Call(func=_name(fn), args=list(args), keywords=[])


def _thunk(body):
    return ast.Lambda(args=ast.arguments(posonlyargs=[], args=[], vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]),
                      body=body)


class _Instrument(ast.NodeTransformer):
    def block(self, stmts, loop=False):
        out, run, n = [], [], 1 if loop else 0
        for s in stmts:
            run.append(s)
            n += 1
            if not isinstance(s, SIMPLE_STMTS):
                out += [ast.Expr(_call("__gas__", ast.Constant(n)))] + run
                run, n = [], 0
        if run:
            out += [ast.Expr(_call("__gas__", ast.Constant(n)))] + run
        return out

    def scoped(self, body, module=False):
        if module:                                    # no local to keep the depth in (it would become module data)
            return [ast.Expr(_call("__gas_in__")), ast.Try(body=self.block(body), handlers=[], orelse=[],
                                                             finalbody=[ast.Expr(_call("__gas_out__"))])]
        return [ast.Assign(targets=[ast.Name(id="__gas_d__", ctx=ast.Store())], value=_call("__gas_in__")),
                ast.Try(body=self.block(body), handlers=[], orelse=[], finalbody=[ast.Expr(_call("__gas_out__", _name("__gas_d__")))])]

    def visit_Module(self, node):
        self.generic_visit(node)
        node.body = self.scoped(node.body, module=True)
        return node

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node.body = self.scoped(node.body)
        return node

    def visit_If(self, node):
        self.generic_visit(node)
        node.body = self.block(node.body)
        if node.orelse:
            node.orelse = self.block(node.orelse)
        return node

    def visit_For(self, node):
        self.generic_visit(node)
        node.body = self.block(node.body, loop=True)
        if node.orelse:
            node.orelse = self.block(node.orelse)
        return node

    visit_While = visit_For

    def visit_Lambda(self, node):
        self.generic_visit(node)
        node.body = ast.BoolOp(op=ast.And(), values=[_call("__gas_lin__"), _call("__gas_lout__", node.body)])
        return node

    def visit_comprehension(self, node):
        self.generic_visit(node)
        node.ifs = [_call("__gas__")] + node.ifs
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        op = BINOPS.get(type(node.op))
        if op is None or _cheap_binop(node):
            return node
        return _call(f"__gas_{op}__", node.left, node.right)

    def visit_AugAssign(self, node):
        self.generic_visit(node)
        op = type(node.op)
        if op not in AUGSYM or _cheap_binop(ast.BinOp(left=ast.Name(id="_", ctx=ast.Load()), op=node.op, right=node.value)):
            return node                                       # x += 1, x *= 0.5
        t = node.target
        if isinstance(t, ast.Name):
            return ast.Assign(targets=[t], value=_call(f"__gas_i{BINOPS[op]}__", ast.Name(id=t.id, ctx=ast.Load()), node.value))
        if isinstance(t, ast.Subscript):
            key = t.slice
            if isinstance(key, ast.Slice):
                key = _call("__gas_slice__", *(x or ast.Constant(None) for x in (key.lower, key.upper, key.step)))
            return ast.Expr(_call("__gas_augsub__", ast.Constant(AUGSYM[op]), t.value, key, _thunk(node.value)))
        if isinstance(t, ast.Attribute):
            return ast.Expr(_call("__gas_augattr__", ast.Constant(AUGSYM[op]), t.value, ast.Constant(t.attr), _thunk(node.value)))
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        syms = [CMPSYM[type(o)] for o in node.ops]
        if len(syms) == 1:
            s, right = syms[0], node.comparators[0]
            if s in ("is", "is not") or _scalar(right) and s not in ("in", "not in") or _scalar(node.left) and s != "in" and \
                    s != "not in" or s in ("in", "not in") and _literal(right):
                return node                                   # O(1) whatever the other operand is
            return _call(CMPFN[s], node.left, right)
        return _call("__gas_chain__", ast.Tuple(elts=[ast.Constant(s) for s in syms], ctx=ast.Load()), node.left,
                     *(_thunk(c) for c in node.comparators))

    def visit_Call(self, node):
        self.generic_visit(node)
        f = node.func
        for kw in node.keywords:
            if kw.arg is None:
                kw.value = _call("__gas_star__", kw.value)
        if isinstance(f, ast.Call) and isinstance(f.func, ast.Name) and f.func.id == "__gas_meth__":
            node.func = _name("__gas_call__")                # obj.join(x) -> __gas_call__(obj, "join", x)
            node.args = list(f.args) + node.args
        return node

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if isinstance(node.ctx, ast.Load) and node.attr in COSTLY_METHODS:
            return _call("__gas_meth__", node.value, ast.Constant(node.attr))
        return node

    def visit_Starred(self, node):
        self.generic_visit(node)
        if isinstance(node.ctx, ast.Load):
            node.value = _call("__gas_star__", node.value)
        return node

    def visit_Dict(self, node):
        self.generic_visit(node)
        node.values = [_call("__gas_star__", v) if k is None else v for k, v in zip(node.keys, node.values)]
        return node

    def visit_Assign(self, node):
        self.generic_visit(node)
        if any(isinstance(e, ast.Starred) for t in node.targets if isinstance(t, (ast.Tuple, ast.List)) for e in t.elts):
            node.value = _call("__gas_star__", node.value)
        return node

    def visit_FormattedValue(self, node):
        self.generic_visit(node)
        spec = node.format_spec if node.format_spec is not None else ast.Constant("")
        return ast.FormattedValue(value=_call("__gas_fmt__", node.value, ast.Constant(node.conversion), spec), conversion=-1,
                                  format_spec=None)


def instrument(tree: ast.Module) -> ast.Module:
    """Return an instrumented copy of a checked law module (the input is not changed)."""
    import copy
    new = _Instrument().visit(copy.deepcopy(tree))
    return ast.fix_missing_locations(new)
