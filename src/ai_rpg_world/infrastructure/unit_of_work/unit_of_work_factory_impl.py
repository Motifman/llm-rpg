"""
Unit of Work Factory Implementation - Unit of Workファクトリの具体実装
"""
import os
from typing import Mapping, Optional, TYPE_CHECKING

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.infrastructure.repository.game_db_path import get_game_db_path_from_env

from .in_memory_unit_of_work import InMemoryUnitOfWork
from .sqlite_unit_of_work import SqliteUnitOfWorkFactory

if TYPE_CHECKING:
    from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import (
        InMemoryEventPublisherWithUow,
    )

ENV_USE_SQLITE_UNIT_OF_WORK = "USE_SQLITE_UNIT_OF_WORK"


def create_unit_of_work_factory_from_env(
    *,
    environ: Optional[Mapping[str, str]] = None,
    event_publisher: Optional["InMemoryEventPublisherWithUow"] = None,
) -> UnitOfWorkFactory:
    """環境に応じて `SqliteUnitOfWorkFactory` または `InMemoryUnitOfWorkFactory` を返す。

    `USE_SQLITE_UNIT_OF_WORK` が真（`1` / `true` / `yes`、大文字小文字無視）かつ
    `GAME_DB_PATH` が解決できるときだけ SQLite。それ以外は常にインメモリ。

    .. note::
        `InMemoryEventPublisherWithUow` は `InMemoryUnitOfWork` 専用（`is_in_transaction` 等）。
        SQLite ファクトリを有効にした構成では、当該パブリッシャーと **併用しない** こと。
    """
    env = environ if environ is not None else os.environ
    flag_raw = (env.get(ENV_USE_SQLITE_UNIT_OF_WORK, "") or "").strip().lower()
    use_sqlite = flag_raw in ("1", "true", "yes")
    game_path = get_game_db_path_from_env(environ=env)
    if use_sqlite and game_path is not None:
        return SqliteUnitOfWorkFactory(game_path)
    return InMemoryUnitOfWorkFactory(event_publisher=event_publisher)


class InMemoryUnitOfWorkFactory(UnitOfWorkFactory):
    """インメモリUnit of Workファクトリ実装

    イベントパブリッシャーと連携し、循環参照を避けたUnit of Work作成を提供します。
    """

    def __init__(self, event_publisher: Optional["InMemoryEventPublisherWithUow"] = None):
        """初期化

        Args:
            event_publisher: 関連付けるイベントパブリッシャー（任意）
        """
        self._event_publisher = event_publisher
        self._factory_function: Optional[callable] = None

    def create(self) -> UnitOfWork:
        """Unit of Workインスタンスを作成

        初回呼び出し時にファクトリ関数を作成し、
        以後は同じファクトリ関数を使用してインスタンスを作成します。

        Returns:
            UnitOfWork: 新しいUnit of Workインスタンス
        """
        if self._factory_function is None:
            # 初回のみファクトリ関数を作成（循環参照を避ける）
            self._factory_function = lambda: InMemoryUnitOfWork(
                event_publisher=self._event_publisher,
            )

        return self._factory_function()
