"""Gas v2 (charter/gas.py): compile-time instrumentation, size-charged builtins and operators, the meter stack. No model calls."""
import time

import pytest

from charter import gas as G
from charter import lawlang as L


def run(body, fn="f", *args, limited=None):
    """Load a law whose module defines `f`, call it under a fresh Limited; returns (result, ticks used)."""
    lim = limited or L.Limited()
    ns = L.load_module('title="t"\nintent="i"\n' + body, "T1", {}, {}, lim)
    out = lim(ns[fn], *args)
    return out, lim.meter.last


def fails(body, match=None):
    t0 = time.perf_counter()
    with pytest.raises(L.LawError, match=match):
        run(body)
    assert time.perf_counter() - t0 < 2.0                          # stopped before doing the work, not after


# ------------------------------------------------------------------ review 09 F2: work inside builtins is metered
@pytest.mark.parametrize("expr", [
    "sum(range(10**8))",
    '"a" * 10**8',
    "7 ** 10**8",
    "[x for x in range(10**8)]",
    "len([[0] * 1000 for i in range(10**5)])",
    "[[x for x in range(10**4)] for y in range(10**4)]",
    '",".join(["abcdefghij"] * 100000)',
    '",".join(str(i) for i in range(10**7))',
    '"-".join(["a" * 1000] * 50000)',
    "list(range(10**8))",
    "sorted(range(10**8))",
    "max(range(10**8))",
    "set(range(10**8))",
    "any(x > 10**9 for x in range(10**8))",
    "sum([[1] * 1000] * 1000, [])",
    "1 << 10**8",
    "(2 ** 5000) * (2 ** 5000) * (2 ** 5000)",
    "[*range(10**8)]",
    "None in range(10**18)",
    'f"{1:>100000000}"',
    '"%100000000d" % 1',
    "str([\"x\" * 1000] * 100000)",
    '("ab" * 50000).replace("a", "a" * 1000)',
])
def test_f2_cases_stop_with_a_law_error(expr):
    fails(f"def f():\n    return {expr}\n")


def test_f2_growth_loops_stop():
    fails('def f():\n    s = "ab"\n    for i in range(100):\n        s += s\n    return len(s)\n')
    fails("def f():\n    x = [1]\n    for i in range(100):\n        x.extend(x)\n    return len(x)\n")
    fails("def f():\n    x = [1]\n    for i in range(100):\n        x = [*x, *x]\n    return len(x)\n")
    fails("def f():\n    n = 3\n    for i in range(100):\n        n = n * n\n    return n\n")
    fails("def f():\n    d = {'a': 'x'}\n    for i in range(100):\n        d['a'] += d['a']\n    return 1\n")
    fails("def f():\n    a, *b = range(10**8)\n    return a\n")


def test_step_and_depth_limits_keep_their_messages():
    with pytest.raises(L.StepLimit, match="law exceeded 10000 steps"):
        run("def f():\n    while True:\n        pass\n")
    with pytest.raises(L.LawError, match="recursion depth 20"):
        run("def f(n=0):\n    return f(n + 1)\n")
    with pytest.raises(L.LawError, match="recursion depth 20"):
        run("g = lambda n: g(n + 1)\ndef f():\n    return g(0)\n")
    lim = L.Limited(max_depth=5)
    assert run("def g(n):\n    return 0 if n == 0 else 1 + g(n - 1)\ndef f():\n    return g(3)\n", limited=lim)[0] == 3
    with pytest.raises(L.LawError, match="recursion depth 5"):
        run("def g(n):\n    return 0 if n == 0 else 1 + g(n - 1)\ndef f():\n    return g(4)\n", limited=lim)


def test_ticks_count_statements_and_iterations_deterministically():
    body = "def f(n):\n    t = 0\n    for i in range(n):\n        t += i\n    return t\n"
    assert run(body, "f", 0)[1] == run(body, "f", 0)[1]
    a, b = run(body, "f", 10)[1], run(body, "f", 20)[1]
    assert b - a == 20                                              # two ticks per iteration (the header and the body statement)
    assert run("def f():\n    return [x for x in range(50)]\n")[1] == 51
    assert run("def f():\n    return sum([1] * 1000)\n")[1] == 1 + 10 + 10     # statement + list build + sum, by size
    # normal laws stay well within budget: exactly the per-call limit is allowed, one more tick is not
    assert run("def f():\n    for i in range(4999):\n        pass\n")[1] == 9999


def test_normal_operations_behave_as_python():
    src = '''
def f():
    d = {"a": [1, 2], "b": (3,)}
    d["a"] += [3]
    d["a"][0] *= 5
    s = "x" + "y" * 3 + f"{len(d):>3}|{d['b']!r}|{1.5:.2f}"
    xs = sorted([3, 1, 2], key=lambda v: -v)
    first, *rest = xs
    ok = 1 < 2 <= 2 and "y" in s and 4 not in xs and xs != [] and (2 ** 10) << 2 == 4096
    return d, s, xs, first, rest, ok, "%s-%d" % ("a", 7), ",".join(str(x) for x in xs), dict(zip("ab", [1, 2])), list(enumerate("ab"))
'''
    assert run(src)[0] == ({"a": [5, 2, 3], "b": (3,)}, "xyyy  2|(3,)|1.50", [3, 2, 1], 3, [2, 1], True, "a-7", "3,2,1",
                           {"a": 1, "b": 2}, [(0, "a"), (1, "b")])


def test_aug_assign_keeps_evaluation_order_and_aliasing():
    src = '''
def f():
    log = []
    d = {"k": [1]}
    alias = d["k"]
    def key():
        log.append("key")
        return "k"
    def val():
        log.append("val")
        return [2]
    d[key()] += val()
    return alias, d["k"] is alias, log
'''
    assert run(src)[0] == ([1, 2], True, ["key", "val"])


# ------------------------------------------------------------------ no new escape surface
@pytest.mark.parametrize("code,why", [
    ("def f(__gas__=None):\n    pass", "parameter"),
    ("g = lambda __gas__: 1", "parameter"),
    ("x = __gas__", "_"),
    ("__gas__ = 1", "_"),
    ("def f():\n    __gas_in__()", "_"),
    ("def __gas__():\n    pass", "underscores"),
    ("for a, *b in [[1, 2]]:\n    pass", "starred"),
    ("x = [b for a, *b in [[1, 2]]]", "starred"),
    ("import os", "Import"),
    ("x = (1).__class__", "attribute"),
    ("def f():\n    global x", "Global"),
    ("try:\n    pass\nexcept Exception:\n    pass", "Try"),
])
def test_instrumentation_names_cannot_be_named_or_shadowed(code, why):
    with pytest.raises(L.LawError, match=why):
        L.check('title="t"\nintent="i"\n' + code)


def test_meter_stack_budgets_are_per_frame_and_shared_budgets_charge_too():
    m = G.Meter()
    used = {}

    def inner():
        m.tick(30)
        return "ok"

    def outer():
        m.tick(50)
        r = m.run(inner, per_call=40)                               # a nested call has its own per-call budget
        m.tick(40)
        used["outer"] = m.top.used
        return r

    assert m.run(outer, per_call=100) == "ok"
    assert used["outer"] == 90 and m.total == 120
    with pytest.raises(G.GasExhausted) as e:
        m.run(lambda: m.tick(41), per_call=40)
    assert e.value.kind == "call"
    cas = G.Budget("cascade", 100)
    m.run(lambda: m.tick(60), cascade=cas)
    with pytest.raises(G.GasExhausted) as e:
        m.run(lambda: m.tick(60), cascade=cas)
    assert e.value.kind == "cascade" and isinstance(e.value, L.StepLimit)
    acct = G.Budget("account", 10)
    with pytest.raises(G.GasExhausted) as e:
        m.run(lambda: m.tick(11), account=acct)
    assert e.value.kind == "account"
    assert m.top is None and m.stack == []
    m.tick(10 ** 9)                                                  # no frame open: not charged (law code outside a metered call)


def test_gas_names_are_not_saved_as_module_data():
    lim = L.Limited()
    ns = L.load_module('title="t"\nintent="i"\nx = [1]\n', "T1", {}, {}, lim)
    data = {n for n, v in ns.items() if not callable(v) and n not in {"__builtins__", "title", "intent", "state", *L.SAFE_BUILTINS}}
    assert data == {"x"}


def test_checkpointed_callbacks_stay_metered():
    from charter.kernel import _dump_fn, _load_fn
    lim = L.Limited()
    ns = L.load_module('title="t"\nintent="i"\ndef mk(n):\n    return lambda p: sum([n] * p)\ncb = mk(3)\n', "T1", {}, {}, lim)
    fn = _load_fn(_dump_fn(ns["cb"], ns), ns)
    assert fn is not ns["cb"] and lim(fn, 500) == lim(ns["cb"], 500) == 1500
    a = lim.meter.last
    assert a == 1 + 5 + 5                                           # the lambda, [n] * 500 and sum over 500 elements
    with pytest.raises(L.StepLimit):
        lim(lambda: [fn(10 ** 5) for i in range(20)])                # 20 x 2,000 ticks of size charges
