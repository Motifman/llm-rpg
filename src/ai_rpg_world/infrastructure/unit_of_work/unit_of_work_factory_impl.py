"""
Unit of Work Factory Implementation - Unit of Workファクトリの具体実装
"""

import os
from collections.abc import Mapping

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.infrastructure.repository.game_db_path import get_game_db_path_from_env

from .in_memory_unit_of_work import InMemoryUnitOfWork
from .sqlite_unit_of_work import SqliteUnitOfWorkFactory

ENV_USE_SQLITE_UNIT_OF_WORK = "USE_SQLITE_UNIT_OF_WORK"


def create_unit_of_work_factory_from_env(
    *,
    environ: Mapping[str, str] | None = None,
) -> UnitOfWorkFactory:
    """環境に応じて `SqliteUnitOfWorkFactory` または `InMemoryUnitOfWorkFactory` を返す。

    `USE_SQLITE_UNIT_OF_WORK` が真（`1` / `true` / `yes`、大文字小文字無視）かつ
    `GAME_DB_PATH` が解決できるときだけ SQLite。それ以外は常にインメモリ。

    """
    env = environ if environ is not None else os.environ
    flag_raw = (env.get(ENV_USE_SQLITE_UNIT_OF_WORK, "") or "").strip().lower()
    use_sqlite = flag_raw in ("1", "true", "yes")
    game_path = get_game_db_path_from_env(environ=env)
    if use_sqlite and game_path is not None:
        return SqliteUnitOfWorkFactory(game_path)
    return InMemoryUnitOfWorkFactory()


class InMemoryUnitOfWorkFactory(UnitOfWorkFactory):
    """配送から独立したインメモリの保存用トランザクションを作る。"""

    def create(self) -> UnitOfWork:
        """未開始の Unit of Work を返す。"""
        return InMemoryUnitOfWork()
