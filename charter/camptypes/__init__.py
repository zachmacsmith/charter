# STUB (owned by Camps-A): the registry and base class exactly per docs/parallel_build_contracts.md ("Camps").
# The framework's real package replaces this file at merge; it must keep the Camps-B import line at the bottom.
"""Camp types: a registry of classes that decide how harvest inputs become yield."""
from __future__ import annotations

TYPES: dict = {}


def register(name):
    def deco(cls):
        cls.name = name
        TYPES[name] = cls
        return cls
    return deco


class CampType:
    name = "base"

    def __init__(self, camp: dict, rng):
        self.camp = camp
        self.rng = rng

    def describe(self, inst) -> str:
        raise NotImplementedError

    def harvest(self, k, aid, args) -> dict:
        raise NotImplementedError

    def end_of_round(self, k) -> list[dict]:
        return []

    def state_line(self, k, aid) -> str:
        return ""

    def snapshot(self) -> dict:
        return {}

    def truth(self) -> dict:
        return {}


# camps-b: register the Camps-B types (keep this line when the framework replaces the stub above)
from charter.camptypes import consortium, weaklink, catalyst, partners, vault, guess  # noqa: E402,F401
