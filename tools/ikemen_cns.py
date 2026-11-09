#!/usr/bin/env python3
"""Compatibility entry point for the CNS compiler API and CLI."""
from __future__ import annotations

import sys

try:
    from . import ikemen_cns_compiler as _compiler
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    import ikemen_cns_compiler as _compiler


if __name__ == "__main__":
    raise SystemExit(_compiler.main())

# Keep the established import path and mutable compiler settings working while
# making the command entry point itself responsible only for dispatch.
sys.modules[__name__] = _compiler
