"""フェーズの切り替わりが、全員に観測として届くことを保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md) の PR 2。

会議が始まったことが届かないと、誰も会議に参加できない。しかも
「会議が始まっていない」のか「始まったが自分に届いていない」のかを
エージェントは区別できない。

## ここで守る 2 つの必須条件

- **`schedules_turn=True`** (設計 doc H-4)。これが False だと会議が始まっても
  誰も起きず、沈黙上限で即座に終わる。MEMORY に残した「行動密度の親原因は
  `schedules_turn`」を一度踏んでいる
- **`breaks_movement=True`** (H-2)。立てないと、会議が始まっても歩き続ける
  プレイヤーが出る
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    GamePhaseChangedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId

_VIEWER = PlayerId(1)


def _event(
    *,
    new_phase: GamePhase = GamePhase.MEETING,
    trigger: str = "emergency_button",
    initiator_name: str = "カイト",
) -> GamePhaseChangedEvent:
    return GamePhaseChangedEvent.create(
        aggregate_id=SpotGraphId.create(1),
        aggregate_type="SpotGraphAggregate",
        old_phase=GamePhase.FREE_ROAM,
        new_phase=new_phase,
        trigger=trigger,
        initiator_display_name=initiator_name,
    )


class TestRegistration:
    """登録漏れがあると配信 0 件のまま例外もログも出ない。"""

    def test_event_is_registered_in_the_observed_registry(self) -> None:
        """ObservedEventRegistry に載っている。

        `is_observed` は完全型一致なので、登録漏れは静かに配信 0 件になる。
        """
        registry = ObservedEventRegistry()
        assert registry.get_strategy_for_event(_event()) == "spot_graph"


class TestWakesEveryone:
    """フェーズ変化の観測は全員を起こす。"""

    def test_schedules_turn(self) -> None:
        """schedules_turn=True。

        False だと会議が始まっても誰も起きず、沈黙上限で即終了する。
        """
        output = _format(_event())
        assert output.schedules_turn is True

    def test_breaks_movement(self) -> None:
        """breaks_movement=True。

        立てないと、会議が始まっても歩き続けるプレイヤーが出る。
        """
        output = _format(_event())
        assert output.breaks_movement is True


class TestProse:
    """何が起きたかが読める文になる。"""

    def test_meeting_start_mentions_the_initiator(self) -> None:
        """誰が招集したかが出る。

        招集した人は疑いの的にも信頼の的にもなる。名前が出ないと、会議の
        きっかけそのものが推理の材料にならない。
        """
        assert "カイト" in _format(_event()).prose

    def test_meeting_start_mentions_the_trigger(self) -> None:
        """緊急ボタンと死体発見が読み分けられる。

        どちらで始まったかで議論の意味がまったく変わる。
        """
        by_button = _format(_event(trigger="emergency_button")).prose
        by_body = _format(_event(trigger="body_report")).prose
        assert by_button != by_body

    def test_meeting_end_is_announced(self) -> None:
        """会議が終わったことも届く。

        終わったことが届かないと、いつまで発言してよいのか分からない。
        """
        output = _format(
            _event(new_phase=GamePhase.FREE_ROAM, trigger="vote_concluded")
        )
        assert output.prose


class TestStructuredPayload:
    """trace と分析のために構造化データも残す。"""

    def test_carries_both_phases_and_trigger(self) -> None:
        """遷移前後のフェーズと理由が structured に入る。"""
        structured = _format(_event()).structured
        assert structured["type"] == "game_phase_changed"
        assert structured["old_phase"] == GamePhase.FREE_ROAM.value
        assert structured["new_phase"] == GamePhase.MEETING.value
        assert structured["trigger"] == "emergency_button"


def _format(event: GamePhaseChangedEvent):
    """viewer 向けの ObservationOutput を組む。"""
    from ai_rpg_world.application.observation.services.formatters._formatter_context import (  # noqa: E501
        ObservationFormatterContext,
    )
    from ai_rpg_world.application.observation.services.formatters._spot_graph_object_handler import (  # noqa: E501
        SpotGraphObjectHandler,
    )
    from ai_rpg_world.application.observation.services.formatters.name_resolver import (  # noqa: E501
        ObservationNameResolver,
    )

    handler = SpotGraphObjectHandler(
        ObservationFormatterContext(
            name_resolver=ObservationNameResolver(), item_repository=None
        )
    )
    output = handler.format(event, _VIEWER)
    assert output is not None, "フェーズ変化の観測が作られていない"
    return output
