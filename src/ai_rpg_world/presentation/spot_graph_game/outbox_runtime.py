"""取引outbox定期配送の実行時組み立て。"""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Mapping, Optional

from ai_rpg_world.application.trade.handlers.trade_event_handler import (
    TradeEventHandler,
)
from ai_rpg_world.application.trade.trade_read_model_wiring import (
    resolve_trade_read_model_persisted_path,
)
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.events.trade_event_handler_registry import (
    TradeEventHandlerRegistry,
)
from ai_rpg_world.infrastructure.events.trade_outbox_worker_factory import (
    build_trade_outbox_worker,
)
from ai_rpg_world.infrastructure.events.trade_projection_executor import (
    SqliteTradeProjectionExecutor,
)
from ai_rpg_world.infrastructure.repository.game_db_path import (
    ensure_parent_dir,
    get_game_db_path_from_env,
)
from ai_rpg_world.infrastructure.repository.game_db_schema import init_game_db_schema
from ai_rpg_world.presentation.spot_graph_game.outbox_delivery_loop import (
    OutboxDeliveryLoop,
)


def build_trade_outbox_delivery_loop_from_env(
    *,
    environ: Optional[Mapping[str, str]] = None,
    interval_seconds: float = 1.0,
    batch_limit: int = 100,
) -> OutboxDeliveryLoop | None:
    """GAME_DB_PATHがある場合だけ取引outboxの単一process loopを組み立てる。"""
    game_database = get_game_db_path_from_env(environ=environ)
    if game_database is None:
        return None

    ensure_parent_dir(game_database)
    connection = sqlite3.connect(game_database)
    try:
        init_game_db_schema(connection)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()

    read_model_database = resolve_trade_read_model_persisted_path(environ=environ)
    if read_model_database is None:
        raise RuntimeError(
            "GAME_DB_PATH設定時に取引read modelの永続化先を解決できません"
        )
    ensure_parent_dir(str(read_model_database))
    dispatcher = CommandEventDispatcher()
    handler = TradeEventHandler(
        SqliteTradeProjectionExecutor(Path(read_model_database)),
    )
    TradeEventHandlerRegistry(handler).register_command_handlers(dispatcher)
    worker = build_trade_outbox_worker(game_database, dispatcher)
    return OutboxDeliveryLoop(
        worker=worker,
        interval_seconds=interval_seconds,
        batch_limit=batch_limit,
    )


__all__ = ["build_trade_outbox_delivery_loop_from_env"]
