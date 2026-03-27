"""DependencyInjectionContainer の Sqlite UoW 補助"""

from pathlib import Path

from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.di.container import (
    DependencyInjectionContainer,
    SqliteSocialDependencyInjectionContainer,
)
from ai_rpg_world.infrastructure.repository.sqlite_post_repository import SqlitePostRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_user_repository import SqliteSnsUserRepository
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWorkFactory


def test_create_sqlite_unit_of_work_factory_for_game_db(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    fac = DependencyInjectionContainer.create_sqlite_unit_of_work_factory_for_game_db(db)
    assert isinstance(fac, SqliteUnitOfWorkFactory)


def test_sqlite_social_container_returns_sqlite_repositories(tmp_path: Path) -> None:
    db = tmp_path / "social.db"
    container = SqliteSocialDependencyInjectionContainer(db)
    try:
        assert isinstance(container.get_unit_of_work_factory(), SqliteUnitOfWorkFactory)
        assert isinstance(container.get_user_repository(), SqliteSnsUserRepository)
        assert isinstance(container.get_post_repository(), SqlitePostRepository)
    finally:
        container.close()


def test_sqlite_social_container_persists_users(tmp_path: Path) -> None:
    db = tmp_path / "social.db"
    container = SqliteSocialDependencyInjectionContainer(db)
    try:
        user_repo = container.get_user_repository()
        saved = user_repo.save(
            UserAggregate.create_new_user(
                user_id=UserId(1),
                user_name="alice",
                display_name="Alice",
                bio="bio",
            )
        )
        assert saved.user_id == UserId(1)
    finally:
        container.close()

    second = SqliteSocialDependencyInjectionContainer(db)
    try:
        loaded = second.get_user_repository().find_by_id(UserId(1))
        assert loaded is not None
        assert loaded.profile.display_name == "Alice"
    finally:
        second.close()
