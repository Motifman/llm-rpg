"""単一ゲーム DB パス（`GAME_DB_PATH`）— Phase 3 ReadModel ファクトリが参照する。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional

ENV_GAME_DB_PATH = "GAME_DB_PATH"


def get_game_db_path_from_env(
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """環境変数 `GAME_DB_PATH` を正規化して返す。未設定・空のときは None。"""
    env = environ if environ is not None else os.environ
    raw = (env.get(ENV_GAME_DB_PATH, "") or "").strip()
    if not raw:
        return None
    return str(Path(raw).expanduser().resolve())


def ensure_parent_dir(path: str) -> None:
    """ファイルパス用に親ディレクトリを作成する（`:memory:` は何もしない）。"""
    if path == ":memory:":
        return
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


__all__ = [
    "ENV_GAME_DB_PATH",
    "ensure_parent_dir",
    "get_game_db_path_from_env",
]
