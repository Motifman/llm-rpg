"""取引outboxの実行時組み立てとFastAPI lifespan接続を保証する。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.event.trade_event import TradeOfferedEvent
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_listing_projection import (
    TradeListingProjection,
)
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import (
    TradeRequestedGold,
)
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.infrastructure.events.trade_event_json_serializer import (
    TradeEventJsonSerializer,
)
from ai_rpg_world.infrastructure.repository.trade_read_model_repository_factory import (
    create_trade_read_model_repository_from_path,
)

from ai_rpg_world.presentation.spot_graph_game.outbox_runtime import (
    build_trade_outbox_delivery_loop_from_env,
)


def test_missing_game_database_disables_outbox_loop() -> None:
    """GAME_DB_PATH未設定ならインメモリ実行を変えずloopを構築しない。"""
    assert build_trade_outbox_delivery_loop_from_env(environ={}) is None


def test_game_database_builds_single_process_outbox_loop(tmp_path: Path) -> None:
    """GAME_DB_PATHがあれば取引codec・handler・SQLite storeを束ねたloopを返す。"""
    database = tmp_path / "nested" / "game.db"

    loop = build_trade_outbox_delivery_loop_from_env(
        environ={"GAME_DB_PATH": str(database)},
        interval_seconds=0.02,
        batch_limit=9,
    )

    assert loop is not None
    assert loop.interval_seconds == 0.02
    assert loop.batch_limit == 9
    assert database.exists()


def test_loop_redelivers_pending_event_into_trade_read_model(tmp_path: Path) -> None:
    """実SQLiteのpending行を自動配送し、投影とdelivered記録を確定する。"""
    database = tmp_path / "game.db"
    loop = build_trade_outbox_delivery_loop_from_env(
        environ={"GAME_DB_PATH": str(database)},
        interval_seconds=0.02,
    )
    assert loop is not None
    event = TradeOfferedEvent(
        event_id=12345678901234567890,
        occurred_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        aggregate_id=TradeId(7),
        aggregate_type="TradeAggregate",
        seller_id=PlayerId(1),
        offered_item_id=ItemInstanceId(10),
        requested_gold=TradeRequestedGold.of(50),
        trade_scope=TradeScope.global_trade(),
        listing_projection=TradeListingProjection(
            seller_display_name="Alice",
            item_name="Key",
            item_quantity=1,
            item_type=ItemType.CONSUMABLE,
            item_rarity=Rarity.RARE,
            item_description="A key",
            item_equipment_type=None,
            durability_current=None,
            durability_max=None,
        ),
        trade_created_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )
    serializer = TradeEventJsonSerializer()
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            INSERT INTO command_event_outbox (
                event_id, event_type, payload, payload_schema_version,
                status, created_at, delivered_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, NULL)
            """,
            (
                str(event.event_id),
                f"{type(event).__module__}:{type(event).__qualname__}",
                serializer.serialize(event),
                serializer.schema_version,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    async def scenario() -> bool:
        loop.start()
        try:
            deadline = asyncio.get_running_loop().time() + 2.0
            while asyncio.get_running_loop().time() < deadline:
                check = sqlite3.connect(database)
                try:
                    row = check.execute(
                        "SELECT status FROM command_event_outbox WHERE event_id = ?",
                        (str(event.event_id),),
                    ).fetchone()
                finally:
                    check.close()
                if row is not None and row[0] == "delivered":
                    return True
                await asyncio.sleep(0.01)
            return False
        finally:
            await loop.stop()

    assert asyncio.run(scenario()) is True
    read_model = create_trade_read_model_repository_from_path(database).find_by_id(
        TradeId(7)
    )
    assert read_model is not None
    assert read_model.item_name == "Key"


class _LifecycleLoop:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


def test_fastapi_lifespan_owns_outbox_loop_start_and_stop(tmp_path: Path) -> None:
    """アプリ起動時にloopを開始し、終了時に同じloopを停止する。"""
    from ai_rpg_world.presentation.spot_graph_game.app import create_game_app

    lifecycle_loop = _LifecycleLoop()
    app = create_game_app(
        scenarios_dir=tmp_path,
        outbox_loop_factory=lambda: lifecycle_loop,
    )

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            assert lifecycle_loop.started == 1
            assert lifecycle_loop.stopped == 0

    asyncio.run(scenario())
    assert lifecycle_loop.stopped == 1
