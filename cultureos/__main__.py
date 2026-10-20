"""Entry point for ``python -m cultureos``."""

from __future__ import annotations

import sys

from cultureos.cli import main

if __name__ == "__main__":
    sys.exit(main())
