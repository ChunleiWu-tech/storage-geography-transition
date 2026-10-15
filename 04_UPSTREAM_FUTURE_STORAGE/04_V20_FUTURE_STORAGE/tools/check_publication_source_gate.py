#!/usr/bin/env python3
"""Backward-compatible command-line wrapper for the canonical publication gate.

Preferred usage is ``publication_source_gate.py --stage source|cases|results``.
Legacy flags remain accepted so older local commands fail closed rather than
silently running a second, divergent implementation.
"""
from __future__ import annotations
import sys


def _normalise_argv(argv: list[str]) -> list[str]:
    if "--stage" in argv:
        return argv
    if "--require-results" in argv:
        return [x for x in argv if x != "--require-results"] + ["--stage", "results"]
    if "--require-prepared-cases" in argv:
        return [x for x in argv if x != "--require-prepared-cases"] + ["--stage", "cases"]
    return argv + ["--stage", "source"]


if __name__ == "__main__":
    sys.argv = _normalise_argv(sys.argv)
    from publication_source_gate import main
    main()
