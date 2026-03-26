"""create_unit_of_work_factory_from_env の切替"""

from pathlib import Path

from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import (
    SqliteUnitOfWork,
    SqliteUnitOfWorkFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.unit_of_work_factory_impl import (
    ENV_USE_SQLITE_UNIT_OF_WORK,
    create_unit_of_work_factory_from_env,
)


class TestCreateUnitOfWorkFactoryFromEnv:
    def test_default_is_in_memory(self) -> None:
        fac = create_unit_of_work_factory_from_env(environ={})
        uow = fac.create()
        assert isinstance(uow, InMemoryUnitOfWork)

    def test_sqlite_when_flag_and_game_db_path(self, tmp_path: Path) -> None:
        db = tmp_path / "uow.db"
        fac = create_unit_of_work_factory_from_env(
            environ={
                ENV_USE_SQLITE_UNIT_OF_WORK: "1",
                "GAME_DB_PATH": str(db),
            },
        )
        assert isinstance(fac, SqliteUnitOfWorkFactory)
        uow = fac.create()
        assert isinstance(uow, SqliteUnitOfWork)
        uow.begin()
        uow.rollback()

    def test_flag_without_game_path_falls_back_in_memory(self) -> None:
        fac = create_unit_of_work_factory_from_env(
            environ={ENV_USE_SQLITE_UNIT_OF_WORK: "true"},
        )
        assert isinstance(fac.create(), InMemoryUnitOfWork)
