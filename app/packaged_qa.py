"""Frozen entry point for the strictly synthetic deployment candidate."""
from __future__ import annotations

import sys

from app.main import main


def packaged_main() -> int:
    """Force QA mode so a distributed candidate cannot fall back to normal mode."""
    if '--qa-ui' not in sys.argv:
        sys.argv.append('--qa-ui')
    return main()


if __name__ == '__main__':
    raise SystemExit(packaged_main())
