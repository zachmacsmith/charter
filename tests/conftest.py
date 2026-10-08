"""Shared test configuration.

- `golden_runs`: the golden cases (tests/charter_golden_cases.py), each run once per session and shared, read-only, by
  test_charter_golden.py and test_charter_history.py.
- Under pytest-xdist, plain `--dist load` (what `-n N` picks) becomes `loadgroup`, so tests marked
  `xdist_group("golden_runs")` share one worker and the golden runs are built once rather than once per worker. Everything
  else is distributed as with `load`.
- library.LIB (the law library, a module-level registry some tests register fixture laws in) is restored after every test, so a
  test that forgets to unregister cannot leak into another test on the same worker.

Markers (registered in pyproject.toml): `slow` for tests that take more than ~10 s; `python -m pytest -m "not slow"` is the quick
loop. See README "Tests".
"""
from __future__ import annotations

import pytest

import charter_golden_cases as GC


def pytest_configure(config):
    if config.pluginmanager.hasplugin("xdist") and getattr(config.option, "dist", "no") == "load":
        config.option.dist = "loadgroup"


@pytest.fixture(scope="session")
def golden_runs(tmp_path_factory):
    """name -> (run directory, in-memory parts) for every golden case, built on first use (charter_golden_cases.Runs)."""
    return GC.Runs(tmp_path_factory.mktemp("golden_runs"))


@pytest.fixture(autouse=True)
def _library_registry_is_restored():
    from charter import library as LB
    before = dict(LB.LIB)
    yield
    if LB.LIB != before:
        LB.LIB.clear()
        LB.LIB.update(before)
