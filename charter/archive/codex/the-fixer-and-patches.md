---
tier: uncommon
title: The Fixer and patches
capabilities: []
---
# The Fixer and patches

- A law whose hook raises an error is suspended at once and queued for the Fixer. Anyone can queue a law with request_fix.
- A patch replaces a law's code. Patches to ordinary laws take effect next round; patches that touch structural or
  procedural code (before or after) go through the Board's veto window like a new law.
- The patched law keeps its id, its state and its place in the order of enactment.
- The Fixer can patch at most a few laws per round; a long queue is a way to keep a law suspended.
- Under some worlds' rules the Fixer's diffs are hidden from everyone: only "patched, with a reason" is shown.
