"""DependencyInjectionContainer の Sqlite UoW 補助"""

from pathlib import Path

from ai_rpg_world.infrastructure.di.container import DependencyInjectionContainer
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWorkFactory


def test_create_sqlite_unit_of_work_factory_for_game_db(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    fac = DependencyInjectionContainer.create_sqlite_unit_of_work_factory_for_game_db(db)
    assert isinstance(fac, SqliteUnitOfWorkFactory)
