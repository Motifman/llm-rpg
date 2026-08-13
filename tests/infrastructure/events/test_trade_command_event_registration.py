"""取引read model更新がcommit後配送としてだけ登録されることを保証する。"""

from unittest.mock import Mock

from ai_rpg_world.infrastructure.events.trade_event_handler_registry import (
    TradeEventHandlerRegistry,
)


def test_trade_handlers_are_registered_only_for_async_post_commit() -> None:
    """取引4イベントは必須同期へ混入せず、commit後配送へ明示登録する。"""
    registry = TradeEventHandlerRegistry(Mock())
    registrar = Mock()

    registry.register_command_handlers(registrar)

    assert registrar.register_async_post_commit.call_count == 4
    assert registrar.register_critical_sync.call_count == 0
    assert registrar.register_best_effort_sync.call_count == 0
    assert registrar.register_sync_observation.call_count == 0
    assert registrar.register_observe_after_commit.call_count == 0


def test_legacy_trade_registry_still_marks_all_handlers_as_asynchronous() -> None:
    """未移行publisher向け互換入口も取引4イベントを非同期登録のまま維持する。"""
    registry = TradeEventHandlerRegistry(Mock())
    publisher = Mock()

    registry.register_handlers(publisher)

    assert publisher.register_handler.call_count == 4
    assert all(
        call.kwargs == {"is_synchronous": False}
        for call in publisher.register_handler.call_args_list
    )
