"""会議終了後は遺体だけが消え、死亡した主体の継続状態は残ることを保証する。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GamePhaseTransitionException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


_SCENARIO = Path(__file__).resolve().parents[2] / "data/scenarios/station_drill.json"
_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)
_AOI = PlayerId(4)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _spot_of(runtime, player_id: PlayerId):
    return runtime._spot_graph_repo.find_graph().get_entity_spot(
        EntityId.create(int(player_id))
    )


def _make_dead(runtime, player_id: PlayerId) -> None:
    spot_id = _spot_of(runtime, player_id)
    status = runtime._player_status_repo.find_by_id(player_id)
    assert status is not None
    status.apply_damage(status.hp.value)
    status.clear_events()
    runtime._player_status_repo.save(status)
    runtime._fallen_body_registry.record(
        player_id,
        spot_id,
        WorldTick(runtime.current_tick()),
    )
    runtime._departed_position_store.place(player_id, spot_id)
    runtime._player_outcome_registry.set_outcome(
        player_id,
        PlayerOutcomeEnum.DEAD,
    )


def _press_emergency_button(runtime) -> None:
    runtime.do_interact(
        _KUZE,
        "emergency_button",
        "press_emergency_button",
    )


class TestBodiesDisappearAfterMeeting:
    """会議の開始理由によらず、成功した終了遷移だけが遺体を片付ける。"""

    def test_all_bodies_disappear_after_an_emergency_button_meeting(
        self,
        runtime,
    ) -> None:
        """招集ボタンで始まった会議を終えると、その時点の全遺体が消える。"""
        _make_dead(runtime, _SENA)
        _make_dead(runtime, _AOI)
        _press_emergency_button(runtime)

        runtime.end_meeting(reason="vote_concluded")

        assert runtime._fallen_body_registry.snapshot() == {}

    def test_death_and_departed_position_survive_body_cleanup(self, runtime) -> None:
        """会議で消すのは遺体だけで、DEAD outcome と幽霊の別位置は残す。"""
        _make_dead(runtime, _SENA)
        departed_spot = runtime._departed_position_store.find(_SENA)
        _press_emergency_button(runtime)

        runtime.end_meeting(reason="vote_concluded")

        assert runtime._fallen_body_registry.find(_SENA) is None
        assert runtime._player_outcome_registry.get_outcome(_SENA) is (
            PlayerOutcomeEnum.DEAD
        )
        assert runtime._departed_position_store.find(_SENA) == departed_spot

    def test_a_reported_body_disappears_when_its_meeting_ends(self, runtime) -> None:
        """遺体の報告で始まった会議でも、終了後は同じ遺体を残さない。"""
        _make_dead(runtime, _SENA)

        result = runtime.report_body(_MORI, _SENA)
        assert result.success is True
        runtime.end_meeting(reason="vote_concluded")

        assert runtime._fallen_body_registry.find(_SENA) is None

    def test_a_rejected_end_does_not_remove_the_body(self, runtime) -> None:
        """自由時間中の終了要求が拒否されたときは、遺体だけを先に消さない。"""
        _make_dead(runtime, _SENA)

        with pytest.raises(GamePhaseTransitionException):
            runtime.end_meeting(reason="vote_concluded")

        assert runtime._fallen_body_registry.find(_SENA) is not None

    def test_ending_a_meeting_without_bodies_is_safe(self, runtime) -> None:
        """遺体が一件もない会議も、例外なく自由時間へ戻せる。"""
        _press_emergency_button(runtime)

        runtime.end_meeting(reason="vote_concluded")

        assert runtime._fallen_body_registry.snapshot() == {}
