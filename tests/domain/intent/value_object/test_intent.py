"""``Intent`` 値オブジェクトのバリデーション挙動。"""

from dataclasses import FrozenInstanceError

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.exception.intent_exception import (
    IntentValidationException,
)
from ai_rpg_world.domain.intent.value_object.intent import Intent
from ai_rpg_world.domain.intent.value_object.intent_id import IntentId
from ai_rpg_world.domain.intent.value_object.intent_phase import IntentPhase
from ai_rpg_world.domain.intent.value_object.intent_priority import (
    IntentPriority,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _build_intent(
    *,
    intent_id: int = 1,
    player_id: int = 100,
    tool_name: str = "travel_to",
    arguments: dict | None = None,
    phase: IntentPhase = IntentPhase.MOVEMENT,
    submitted_tick: int = 5,
    complete_tick: int | None = None,
    priority: int = 0,
    target_descriptor: dict | None = None,
) -> Intent:
    return Intent(
        intent_id=IntentId(intent_id),
        player_id=PlayerId(player_id),
        tool_name=tool_name,
        arguments=arguments if arguments is not None else {"destination": "spot_2"},
        phase=phase,
        submitted_at_tick=WorldTick(submitted_tick),
        complete_at_tick=WorldTick(
            complete_tick if complete_tick is not None else submitted_tick
        ),
        priority=IntentPriority(priority),
        target_descriptor=target_descriptor,
    )


class TestIntent:
    """``Intent`` 値オブジェクトの構築・バリデーション挙動。"""

    def test_default_intent_is_instant(self) -> None:
        """complete_at_tick == submitted_at_tick の intent は is_instant が True。"""
        intent = _build_intent(submitted_tick=10, complete_tick=10)
        assert intent.is_instant is True

    def test_future_complete_tick_is_not_instant(self) -> None:
        """complete_at_tick が未来の intent は is_instant が False。"""
        intent = _build_intent(submitted_tick=10, complete_tick=13)
        assert intent.is_instant is False

    def test_complete_before_submitted_is_rejected(self) -> None:
        """complete_at_tick < submitted_at_tick は IntentValidationException。"""
        with pytest.raises(IntentValidationException):
            _build_intent(submitted_tick=10, complete_tick=8)

    def test_empty_tool_name_is_rejected(self) -> None:
        """tool_name が空文字なら弾く。"""
        with pytest.raises(IntentValidationException):
            _build_intent(tool_name="")

    def test_arguments_must_be_mapping(self) -> None:
        """arguments は Mapping でなければならない。"""
        with pytest.raises(IntentValidationException):
            _build_intent(arguments=["not", "a", "dict"])  # type: ignore[arg-type]

    def test_target_descriptor_optional(self) -> None:
        """target_descriptor は None で構築可能 (late-binding 未使用)。"""
        intent = _build_intent(target_descriptor=None)
        assert intent.target_descriptor is None

    def test_target_descriptor_accepts_mapping(self) -> None:
        """target_descriptor に Mapping を渡せる。"""
        intent = _build_intent(target_descriptor={"label": "前にいるゴブリン"})
        assert intent.target_descriptor == {"label": "前にいるゴブリン"}

    def test_frozen_immutable(self) -> None:
        """Intent は frozen dataclass なので属性変更を禁止。"""
        intent = _build_intent()
        with pytest.raises(FrozenInstanceError):
            intent.tool_name = "other"  # type: ignore[misc]
