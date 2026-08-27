#!/usr/bin/env python3
"""工程根便捷入口 → serve.main（CLI）。"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from serve.main import main

if __name__ == "__main__":
    main()
