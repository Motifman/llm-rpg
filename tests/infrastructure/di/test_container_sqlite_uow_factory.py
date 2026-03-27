"""DependencyInjectionContainer の Sqlite UoW 補助"""

from pathlib import Path

from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.di.container import (
    DependencyInjectionContainer,
    SqliteGameDependencyInjectionContainer,
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


def test_sqlite_game_container_returns_sqlite_bundles(tmp_path: Path) -> None:
    db = tmp_path / "game.db"
    container = SqliteGameDependencyInjectionContainer(db)
    try:
        assert isinstance(container.get_unit_of_work_factory(), SqliteUnitOfWorkFactory)
        world_state = container.get_world_state_repositories()
        static_master = container.get_static_master_repositories()
        shop = container.get_shop_repositories()
        social = container.get_social_repositories()

        assert world_state.player_state.player_statuses is not None
        assert static_master.readers.item_specs is not None
        assert shop.shops is not None
        assert social.users is not None
    finally:
        container.close()


def test_sqlite_game_container_reuses_shared_connection(tmp_path: Path) -> None:
    db = tmp_path / "game.db"
    container = SqliteGameDependencyInjectionContainer(db)
    try:
        first = container.get_shop_repositories()
        second = container.get_trade_command_repositories()
        third = container.get_world_state_repositories()

        assert first.shops._conn is second[0]._conn
        assert first.shops._conn is third.player_state.items._conn
    finally:
        container.close()
