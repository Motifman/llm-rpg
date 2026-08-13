"""TradeCommandService を SQLite 書き込み 5 リポジトリ＋SqliteUnitOfWork で検証する。"""
from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.application.trade.contracts.commands import AcceptTradeCommand
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.common.outbox_worker import OutboxDeliveryException
from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.trade.services.trade_command_service import TradeCommandService
from ai_rpg_world.application.trade.exceptions.base_exception import (
    TradeSystemErrorException,
)
from ai_rpg_world.application.trade.trade_command_sqlite_wiring import bootstrap_game_write_schema
from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import (
    SqliteItemWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_inventory_write_repository import (
    SqlitePlayerInventoryWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_profile_write_repository import (
    SqlitePlayerProfileWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_status_write_repository import (
    SqlitePlayerStatusWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_aggregate_repository import (
    SqliteTradeAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_command_repository_provider import (
    SqliteTradeCommandRepositoryProviderFactory,
)
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
    TradeOfferedEvent,
)
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.events.sqlite_transactional_outbox import (
    SqliteTransactionalOutbox,
)
from ai_rpg_world.infrastructure.events.trade_event_json_serializer import (
    TradeEventJsonSerializer,
)
from ai_rpg_world.infrastructure.events.trade_outbox_worker_factory import (
    build_trade_outbox_worker,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    SqliteUnitOfWorkTransactionFactory,
)

from tests.application.trade.services.test_trade_command_service import (
    TestTradeCommandService,
    _cmd_trade_listing_projection,
)
from tests.application.trade.services.test_trade_command_scope_migration import (
    _seed_offer_dependencies,
)


_TRADE_EVENT_TYPES = (
    TradeOfferedEvent,
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
)


def _build_sqlite_setup(
    database,
    *,
    handoff_error: Exception | None = None,
    sync_error: Exception | None = None,
):
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    bootstrap_game_write_schema(conn)
    conn.commit()

    trade_repo = SqliteTradeAggregateRepository.for_standalone_connection(conn)
    inv_repo = SqlitePlayerInventoryWriteRepository.for_standalone_connection(conn)
    status_repo = SqlitePlayerStatusWriteRepository.for_standalone_connection(conn)
    profile_repo = SqlitePlayerProfileWriteRepository.for_standalone_connection(conn)
    item_repo = SqliteItemWriteRepository.for_standalone_connection(conn)
    dispatcher = CommandEventDispatcher()
    for event_type in _TRADE_EVENT_TYPES:
        dispatcher.register_after_commit(
            event_type,
            (
                (lambda event: (_ for _ in ()).throw(handoff_error))
                if handoff_error is not None
                else (lambda event: None)
            ),
            channel=DeliveryChannel.READ_MODEL,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
    if sync_error is not None:
        dispatcher.register_required_before_commit(
            TradeOfferedEvent,
            lambda event, context: (_ for _ in ()).throw(sync_error),
        )
    outbox = SqliteTransactionalOutbox(
        database,
        serializer=TradeEventJsonSerializer(),
        is_durable=dispatcher.requires_durable_retry,
    )
    scope_factory = CommandScopeFactory(
        SqliteUnitOfWorkTransactionFactory(database),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=SqliteTradeCommandRepositoryProviderFactory(),
        transactional_outbox=outbox,
    )
    return (
        TradeCommandService(scope_factory),
        trade_repo,
        inv_repo,
        status_repo,
        scope_factory,
        None,
        profile_repo,
        item_repo,
    )


class TestTradeCommandServiceSqlite(TestTradeCommandService):
    @pytest.fixture
    def setup_service(self, tmp_path):
        database = tmp_path / "game.db"
        return _build_sqlite_setup(database)

    def test_trade_id_sequence_rolls_back_with_failed_transaction(self, setup_service):
        """UoW 内で採番した trade_id は rollback 後に永続化されず、採番も巻き戻る。"""
        from datetime import datetime

        from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.trade.aggregate.trade_aggregate import TradeAggregate
        from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
        from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope

        _, trade_repo, _, _, scope_factory, _, _, _ = setup_service

        with pytest.raises(RuntimeError, match="abort"):
            with scope_factory.create() as context:
                scoped_trade_repo = context.repositories.trades
                tid = scoped_trade_repo.generate_trade_id()
                trade = TradeAggregate.create_new_trade(
                    trade_id=tid,
                    seller_id=PlayerId(1),
                    offered_item_id=ItemInstanceId(1),
                    requested_gold=TradeRequestedGold.of(10),
                    created_at=datetime.now(),
                    trade_scope=TradeScope.global_trade(),
                    listing_projection=_cmd_trade_listing_projection(),
                )
                scoped_trade_repo.save(trade)
                raise RuntimeError("abort")

        with scope_factory.create() as context:
            tid2 = context.repositories.trades.generate_trade_id()
        assert tid2.value == 1
        assert trade_repo.find_by_id(TradeId(1)) is None


def _outbox_status(database, event_type: type[object]) -> str | None:
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT status FROM command_event_outbox WHERE event_type LIKE ?",
            (f"%:{event_type.__name__}",),
        ).fetchone()
        return None if row is None else str(row[0])
    finally:
        connection.close()


def _outbox_payload(database, event_type: type[object]) -> bytes:
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT payload FROM command_event_outbox WHERE event_type LIKE ?",
            (f"%:{event_type.__name__}",),
        ).fetchone()
        assert row is not None
        return bytes(row[0])
    finally:
        connection.close()


def test_trade_state_and_outbox_commit_together(tmp_path) -> None:
    """取引成功時は業務状態と配送予定を同時に確定し、handoff後に配達済みにする。"""
    database = tmp_path / "game.db"
    setup = _build_sqlite_setup(database)
    command = _seed_offer_dependencies(setup)

    setup[0].offer_item(command)

    assert setup[1].find_by_id(TradeId(1)) is not None
    assert _outbox_status(database, TradeOfferedEvent) == "delivered"


def test_offer_command_persists_a_restorable_event_payload(tmp_path) -> None:
    """実際の出品commandがoutboxへ保存したイベントを型付きで復元できる。"""
    database = tmp_path / "game.db"
    setup = _build_sqlite_setup(database)

    setup[0].offer_item(_seed_offer_dependencies(setup))

    restored = TradeEventJsonSerializer().deserialize(
        _outbox_payload(database, TradeOfferedEvent),
        TradeOfferedEvent,
    )
    assert isinstance(restored, TradeOfferedEvent)
    assert restored.trade_created_at.tzinfo is not None


def test_accept_command_persists_a_restorable_event_payload(tmp_path) -> None:
    """実際の受託commandがoutboxへ保存したイベントを型付きで復元できる。"""
    database = tmp_path / "game.db"
    setup = _build_sqlite_setup(database)
    trade_id, _ = TestTradeCommandService()._seed_active_trade(setup)

    setup[0].accept_trade(AcceptTradeCommand(trade_id=trade_id.value, buyer_id=2))

    restored = TradeEventJsonSerializer().deserialize(
        _outbox_payload(database, TradeAcceptedEvent),
        TradeAcceptedEvent,
    )
    assert isinstance(restored, TradeAcceptedEvent)
    assert restored.trade_created_at.tzinfo is not None


def test_handoff_failure_keeps_committed_trade_and_pending_outbox(tmp_path) -> None:
    """即時配送失敗後も確定済み取引と未配送outbox行を再試行元として残す。"""
    database = tmp_path / "game.db"
    setup = _build_sqlite_setup(
        database,
        handoff_error=RuntimeError("delivery failed"),
    )
    command = _seed_offer_dependencies(setup)

    with pytest.raises(CommandPostCommitException):
        setup[0].offer_item(command)

    assert setup[1].find_by_id(TradeId(1)) is not None
    assert _outbox_status(database, TradeOfferedEvent) == "pending"


def test_worker_redelivers_pending_trade_event_once_and_marks_it_delivered(
    tmp_path,
) -> None:
    """即時配送失敗で残った取引イベントをworkerが復元・再配送し、再実行しない。"""
    database = tmp_path / "game.db"
    setup = _build_sqlite_setup(
        database,
        handoff_error=RuntimeError("delivery failed"),
    )
    with pytest.raises(CommandPostCommitException):
        setup[0].offer_item(_seed_offer_dependencies(setup))

    dispatcher = CommandEventDispatcher()
    delivered_event_ids: list[int] = []
    best_effort_calls: list[int] = []
    dispatcher.register_after_commit(
        TradeOfferedEvent,
        lambda event: delivered_event_ids.append(event.event_id),
        channel=DeliveryChannel.READ_MODEL,
        guarantee=DeliveryGuarantee.DURABLE_RETRY,
    )
    dispatcher.register_after_commit(
        TradeOfferedEvent,
        lambda event: best_effort_calls.append(event.event_id),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    worker = build_trade_outbox_worker(database, dispatcher)

    first = worker.run_once()
    second = worker.run_once()

    assert first.delivered_count == 1
    assert second.delivered_count == 0
    assert len(delivered_event_ids) == 1
    assert best_effort_calls == []
    assert _outbox_status(database, TradeOfferedEvent) == "delivered"


def test_worker_keeps_pending_event_when_durable_handler_is_not_registered(
    tmp_path,
) -> None:
    """workerのhandler登録漏れは成功扱いにせず、取引イベントをpendingに保つ。"""
    database = tmp_path / "game.db"
    setup = _build_sqlite_setup(
        database,
        handoff_error=RuntimeError("delivery failed"),
    )
    with pytest.raises(CommandPostCommitException):
        setup[0].offer_item(_seed_offer_dependencies(setup))

    worker = build_trade_outbox_worker(database, CommandEventDispatcher())

    with pytest.raises(OutboxDeliveryException):
        worker.run_once()

    assert _outbox_status(database, TradeOfferedEvent) == "pending"


def test_sync_failure_rolls_back_trade_and_outbox_together(tmp_path) -> None:
    """同期必須処理の失敗時は取引とoutbox行のどちらも確定しない。"""
    database = tmp_path / "game.db"
    setup = _build_sqlite_setup(
        database,
        sync_error=RuntimeError("sync failed"),
    )
    command = _seed_offer_dependencies(setup)

    with pytest.raises(TradeSystemErrorException, match="sync failed"):
        setup[0].offer_item(command)

    assert setup[1].find_by_id(TradeId(1)) is None
    assert _outbox_status(database, TradeOfferedEvent) is None
