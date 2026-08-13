"""取引用providerが同じSQLite transactionへrepositoryを参加させることを保証する。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.common.command_scope import CommandContext, CommandScope
from ai_rpg_world.application.common.events import DomainEventCollector
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_command_repository_provider import (
    SqliteTradeCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    SqliteUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


class _NoOpSyncDispatcher:
    def dispatch(self, event: object, context: object) -> None:
        pass


class _NoOpAfterCommitHandoff:
    def handoff(self, events: object) -> None:
        pass


class _RecordingSyncDispatcher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def dispatch(self, event: object, context: object) -> None:
        self.events.append(event)


class _RecordingAfterCommitHandoff:
    def __init__(self) -> None:
        self.events: tuple[object, ...] = ()

    def handoff(self, events: tuple[object, ...]) -> None:
        self.events = events


def _initialize_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        init_game_write_schema(connection)
        connection.commit()
    finally:
        connection.close()


def _create_scope(
    path: Path,
    *,
    sync_dispatcher: object | None = None,
    after_commit_handoff: object | None = None,
) -> tuple[CommandScope[Any], SqliteUnitOfWork]:
    unit_of_work = SqliteUnitOfWork(path)
    scope = CommandScope(
        SqliteUnitOfWorkTransactionAdapter(unit_of_work),
        sync_dispatcher=sync_dispatcher or _NoOpSyncDispatcher(),  # type: ignore[arg-type]
        after_commit_handoff=after_commit_handoff
        or _NoOpAfterCommitHandoff(),  # type: ignore[arg-type]
        repository_provider_factory=(
            SqliteTradeCommandRepositoryProviderFactory()
        ),
    )
    return scope, unit_of_work


def _table_count(path: Path, table_name: str) -> int:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        assert row is not None
        return int(row[0])
    finally:
        connection.close()


class TestSqliteTradeCommandRepositoryProvider:
    """providerの生成、可視性、rollback、終了後利用禁止を保証する。"""

    def test_all_repositories_share_the_active_unit_of_work_connection(
        self,
        tmp_path: Path,
    ) -> None:
        """provider内の5repositoryは開始済みUnitOfWorkの同じ接続を共有する。"""
        database = tmp_path / "game.db"
        _initialize_database(database)
        scope, unit_of_work = _create_scope(database)

        with scope as context:
            provider = context.repositories
            repositories = (
                provider.trades,
                provider.player_inventories,
                provider.player_statuses,
                provider.player_profiles,
                provider.items,
            )
            target_connections = {
                id(repository._repository._conn)  # type: ignore[attr-defined]
                for repository in repositories
            }
            assert target_connections == {id(unit_of_work.connection)}
            assert all(
                repository._repository._commits_after_write is False  # type: ignore[attr-defined]
                for repository in repositories
            )

    def test_factory_rejects_transaction_other_than_sqlite_adapter(self) -> None:
        """provider factoryは別資源を持つtransaction実装との誤配線を開始前に拒否する。"""
        factory = SqliteTradeCommandRepositoryProviderFactory()
        context: CommandContext[Any] = CommandContext(DomainEventCollector())

        with pytest.raises(TypeError, match="SqliteUnitOfWorkTransactionAdapter"):
            factory.create(context, object())  # type: ignore[arg-type]

    def test_save_is_visible_inside_scope_but_not_before_commit(
        self,
        tmp_path: Path,
    ) -> None:
        """scope内のsaveは直後のfindに見え、別接続にはcommit後だけ見える。"""
        database = tmp_path / "game.db"
        _initialize_database(database)
        scope, _ = _create_scope(database)
        player_id = PlayerId(1)
        profile = PlayerProfileAggregate.create(player_id, PlayerName("Alice"))

        with scope as context:
            repository = context.repositories.player_profiles
            repository.save(profile)

            restored = repository.find_by_id(player_id)
            assert restored is not None
            assert restored.name == profile.name
            assert _table_count(database, "game_player_profiles") == 0

        assert _table_count(database, "game_player_profiles") == 1

    def test_error_rolls_back_writes_from_multiple_repositories(
        self,
        tmp_path: Path,
    ) -> None:
        """command失敗時はprofileとinventoryの書込みをまとめて破棄する。"""
        database = tmp_path / "game.db"
        _initialize_database(database)
        scope, _ = _create_scope(database)
        player_id = PlayerId(1)

        with pytest.raises(RuntimeError, match="command failed"):
            with scope as context:
                context.repositories.player_profiles.save(
                    PlayerProfileAggregate.create(player_id, PlayerName("Alice"))
                )
                context.repositories.player_inventories.save(
                    PlayerInventoryAggregate.create_new_inventory(player_id)
                )
                raise RuntimeError("command failed")

        assert _table_count(database, "game_player_profiles") == 0
        assert _table_count(database, "game_player_inventories") == 0

    def test_repository_obtained_from_closed_scope_rejects_reads(
        self,
        tmp_path: Path,
    ) -> None:
        """scope内で取得済みのrepositoryもscope終了後は読み取りを拒否する。"""
        database = tmp_path / "game.db"
        _initialize_database(database)
        scope, _ = _create_scope(database)

        with scope as context:
            repository = context.repositories.player_profiles
            captured_find = repository.find_by_id

        with pytest.raises(CommandScopeStateException):
            repository.find_by_id(PlayerId(1))
        with pytest.raises(CommandScopeStateException):
            captured_find(PlayerId(1))

    def test_saved_aggregate_events_move_to_command_context(
        self,
        tmp_path: Path,
    ) -> None:
        """scope参加repositoryは集約イベントを旧UnitOfWorkでなくcontextへ移す。"""
        database = tmp_path / "game.db"
        _initialize_database(database)
        dispatcher = _RecordingSyncDispatcher()
        handoff = _RecordingAfterCommitHandoff()
        scope, unit_of_work = _create_scope(
            database,
            sync_dispatcher=dispatcher,
            after_commit_handoff=handoff,
        )
        profile = PlayerProfileAggregate.create(PlayerId(1), PlayerName("Alice"))
        profile.change_name(PlayerName("Alicia"))
        pending_event = profile.get_events()[0]

        with scope as context:
            context.repositories.player_profiles.save(profile)
            assert profile.get_events() == []
            assert unit_of_work.has_pending_events() is False

        assert dispatcher.events == [pending_event]
        assert handoff.events == (pending_event,)

    def test_failed_save_does_not_dispatch_phantom_event(
        self,
        tmp_path: Path,
    ) -> None:
        """SQL保存失敗をcommand内で処理しても未保存集約のイベントを配送しない。"""
        database = tmp_path / "game.db"
        _initialize_database(database)
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                """
                CREATE TRIGGER reject_profile_insert
                BEFORE INSERT ON game_player_profiles
                BEGIN
                    SELECT RAISE(ABORT, 'profile rejected');
                END
                """
            )
            connection.commit()
        finally:
            connection.close()
        dispatcher = _RecordingSyncDispatcher()
        handoff = _RecordingAfterCommitHandoff()
        scope, unit_of_work = _create_scope(
            database,
            sync_dispatcher=dispatcher,
            after_commit_handoff=handoff,
        )
        profile = PlayerProfileAggregate.create(PlayerId(1), PlayerName("Alice"))
        profile.change_name(PlayerName("Alicia"))
        pending_event = profile.get_events()[0]

        with scope as context:
            with pytest.raises(sqlite3.IntegrityError, match="profile rejected"):
                context.repositories.player_profiles.save(profile)
            assert unit_of_work.has_pending_events() is False

        assert _table_count(database, "game_player_profiles") == 0
        assert profile.get_events() == [pending_event]
        assert dispatcher.events == []
        assert handoff.events == ()
