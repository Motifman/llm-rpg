"""取引read model更新がcommit後配送としてだけ登録されることを保証する。"""

from unittest.mock import Mock

from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.infrastructure.events.trade_event_handler_registry import (
    TradeEventHandlerRegistry,
)


def test_trade_handlers_are_registered_as_durable_read_model_delivery() -> None:
    """取引4イベントはcommit前処理へ混入せず、再試行対象のread model更新として登録する。"""
    registry = TradeEventHandlerRegistry(Mock())
    registrar = Mock()

    registry.register_command_handlers(registrar)

    assert registrar.register_required_before_commit.call_count == 0
    assert registrar.register_after_commit.call_count == 4
    assert all(
        call.kwargs
        == {
            "channel": DeliveryChannel.READ_MODEL,
            "guarantee": DeliveryGuarantee.DURABLE_RETRY,
        }
        for call in registrar.register_after_commit.call_args_list
    )


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
