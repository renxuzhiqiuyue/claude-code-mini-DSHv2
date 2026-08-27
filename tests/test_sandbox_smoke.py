"""sandbox 烟雾测试：可写工作区、拒写 /etc。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import config as cfg  # noqa: E402
from harness.sandbox import (  # noqa: E402
    resolve_backend,
    run_bash,
    sandbox_status_line,
)


def main() -> int:
    cfg.ensure_runtime_dirs()
    print(sandbox_status_line())
    print("backend=", resolve_backend())

    r1 = run_bash("echo ok > _sb_test.txt && python3 -c \"open('_sb_py.txt','w').write('py')\" && ls _sb_test.txt _sb_py.txt")
    print("write_ok:", r1.returncode, (r1.stdout + r1.stderr).strip()[:200])
    if r1.returncode != 0:
        return 1
    if not (cfg.OUTPUT_DIR / "_sb_test.txt").is_file():
        print("missing host file")
        return 1

    r2 = run_bash("echo bad > /etc/_sb_escape.txt")
    print("escape_etc:", r2.returncode, (r2.stdout + r2.stderr).strip()[:200])
    if r2.returncode == 0:
        print("ERROR: write to /etc should fail")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
