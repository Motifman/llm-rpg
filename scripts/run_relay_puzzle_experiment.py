#!/usr/bin/env python3
"""relay_puzzle_demo の LLM 実験ランナー（エントリポイント）。

実装本体は ``issue154_full_tables_experiment.py``（Issue #154 / #188 系の集計付き）。
手順・環境変数・はまりどころは ``docs/running_scenarios.md`` を参照。

例::

    make experiment-relay
    make experiment-relay-r1 ISSUE154_MAX_TICKS=30
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
for p in (_ROOT, _SCRIPTS):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from issue154_full_tables_experiment import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
