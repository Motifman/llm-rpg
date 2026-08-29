"""CALL_MEETING効果が宣言した招集理由を失わず、暗黙値へ縮退しないことを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionEffectValidationException,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object import interaction_effect
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef


def _apply(parameters: dict) -> tuple[str, ...]:
    result = WorldGraphEffectService().apply_effects(
        interior=SpotInterior((), (), (), ()),
        acting_object=None,
        effects=(
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.CALL_MEETING,
                parameters=parameters,
            ),
        ),
        world_flags=frozenset(),
    )
    return result.meeting_call_triggers


class TestCallMeetingEffect:
    """CALL_MEETINGのtrigger収集と不正値拒否を検証する。"""

    def test_preserves_the_declared_trigger(self, monkeypatch) -> None:
        """対応するtriggerは固定値に置き換えず効果結果へ保持する。"""
        monkeypatch.setattr(
            interaction_effect,
            "CALL_MEETING_EFFECT_TRIGGERS",
            frozenset({"emergency_button", "test_second_trigger"}),
        )

        assert _apply({"trigger": "test_second_trigger"}) == (
            "test_second_trigger",
        )

    def test_rejects_a_missing_trigger(self) -> None:
        """triggerの無い直接構築もemergency_buttonへ補完せず拒否する。"""
        with pytest.raises(InteractionEffectValidationException, match="trigger"):
            _apply({})

    def test_rejects_an_unknown_trigger(self) -> None:
        """未知のtriggerを渡した直接構築も効果結果へ流さず拒否する。"""
        with pytest.raises(InteractionEffectValidationException, match="typo_value"):
            _apply({"trigger": "typo_value"})

    def test_rejects_mixing_a_meeting_call_with_normal_effects(self) -> None:
        """会議開始と通常効果を同じinteractionへ直接構築しても拒否する。"""
        with pytest.raises(
            InteractionEffectValidationException,
            match="CALL_MEETING.*単独",
        ):
            InteractionDef(
                action_name="mixed_meeting",
                display_label="混在した会議",
                preconditions=(),
                effects=(
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.CALL_MEETING,
                        parameters={"trigger": "emergency_button"},
                    ),
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.SET_FLAG,
                        parameters={"flag_name": "must_not_be_set"},
                    ),
                ),
            )
