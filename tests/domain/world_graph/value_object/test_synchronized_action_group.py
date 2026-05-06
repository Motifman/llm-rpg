"""SynchronizedActionGroup のバリデーション挙動テスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SynchronizedActionGroupValidationException,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import (
    SynchronizedActionGroup,
)


def _show_msg(text: str = "ok") -> InteractionEffect:
    return InteractionEffect(
        effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
        parameters={"message": text},
    )


class TestSynchronizedActionGroupValidation:
    """SynchronizedActionGroup の構築バリデーション。"""

    def test_minimal_valid_group(self) -> None:
        """必須フィールドが揃っていれば構築できる。"""
        g = SynchronizedActionGroup(
            group_id="vault",
            required_action_ids=("a", "b"),
            window_ticks=2,
            on_complete=(_show_msg(),),
        )
        assert g.window_ticks == 2

    def test_empty_group_id_rejected(self) -> None:
        """group_id が空文字列なら拒否する。"""
        with pytest.raises(SynchronizedActionGroupValidationException, match="group_id"):
            SynchronizedActionGroup(
                group_id="",
                required_action_ids=("a", "b"),
                window_ticks=2,
                on_complete=(_show_msg(),),
            )

    def test_required_actions_must_be_at_least_two(self) -> None:
        """required_action_ids が 1 件以下なら拒否する（同期する意味がない）。"""
        with pytest.raises(SynchronizedActionGroupValidationException, match="at least 2"):
            SynchronizedActionGroup(
                group_id="x",
                required_action_ids=("a",),
                window_ticks=1,
                on_complete=(_show_msg(),),
            )

    def test_required_actions_must_be_unique(self) -> None:
        """required_action_ids に重複があれば拒否する。"""
        with pytest.raises(SynchronizedActionGroupValidationException, match="unique"):
            SynchronizedActionGroup(
                group_id="x",
                required_action_ids=("a", "a"),
                window_ticks=1,
                on_complete=(_show_msg(),),
            )

    def test_window_ticks_must_be_positive(self) -> None:
        """window_ticks が 0 以下なら拒否する。"""
        with pytest.raises(SynchronizedActionGroupValidationException, match="window_ticks"):
            SynchronizedActionGroup(
                group_id="x",
                required_action_ids=("a", "b"),
                window_ticks=0,
                on_complete=(_show_msg(),),
            )

    def test_on_complete_must_have_at_least_one_effect(self) -> None:
        """on_complete が空なら拒否する。"""
        with pytest.raises(SynchronizedActionGroupValidationException, match="on_complete"):
            SynchronizedActionGroup(
                group_id="x",
                required_action_ids=("a", "b"),
                window_ticks=1,
                on_complete=(),
            )
