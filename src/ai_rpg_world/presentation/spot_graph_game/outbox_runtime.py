"""取引outbox定期配送の実行時組み立て。"""

from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
from collections.abc import Mapping
from pathlib import Path
from threading import Lock
from typing import Any

from ai_rpg_world.application.trace.events import TraceEvent
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.application.trade.handlers.trade_event_handler import (
    TradeEventHandler,
)
from ai_rpg_world.application.trade.trade_read_model_wiring import (
    resolve_trade_read_model_persisted_path,
)
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
    WorldTickFailureIsolator,
    WorldTickFailurePolicy,
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

logger = logging.getLogger(__name__)


class _OutboxTraceRecorder(NullTraceRecorder):
    """書き込む間だけファイルを開き、停止期限後に完了する再送の失敗も残す。"""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._file_lock = Lock()

    def record(
        self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any
    ) -> TraceEvent:
        with self._file_lock:
            event = super().record(kind, tick=tick, player_id=player_id, **payload)
            with self._path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(event.to_jsonable(), ensure_ascii=False) + "\n")
            return event


def build_trade_outbox_delivery_loop_from_env(
    *,
    environ: Mapping[str, str] | None = None,
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
    database_path = Path(game_database)
    with tempfile.NamedTemporaryFile(
        prefix=f"{database_path.name}.outbox-", suffix=".jsonl", dir=database_path.parent, delete=False
    ) as trace_file:
        trace_path = Path(trace_file.name)
    recorder = _OutboxTraceRecorder(trace_path)
    isolator = WorldTickFailureIsolator(
        policy=WorldTickFailurePolicy.ISOLATE, trace_recorder_provider=lambda: recorder
    )
    dispatcher = CommandEventDispatcher(
        failure_observer=isolator.after_commit_failure_observer(tick_provider=lambda: None)
    )
    logger.info("取引 outbox の失敗の記録先: %s", trace_path)
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
