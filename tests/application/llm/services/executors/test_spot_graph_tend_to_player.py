"""_tend_to_player executor の挙動検証 (Issue #621 Phase 3b)。

resolver で target_player_id まで解決済みの args を受けて、
同 spot にいる倒れた仲間を revive する handler。

検証範囲:
- 正常系: 同 spot に倒れた仲間 → revive 成功
- 失敗系: 自分自身 / 元気な相手 / 別 spot / 自分が倒れている / wiring 不足
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_navigation_state import (
    PlayerNavigationState,
)
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def _build_player(
    *,
    player_id: int,
    is_down: bool,
    spot_id: int,
    hp_current: int = 100,
    hp_max: int = 100,
) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    nav = PlayerNavigationState.from_parts(
        current_spot_id=SpotId(spot_id),
        current_coordinate=Coordinate(0, 0, 0),
    )
    status = PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(hp_max, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp.create(hp_current, hp_max),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100),
        navigation_state=nav,
        is_down=is_down,
    )
    return status


def _build_executor() -> tuple[SpotGraphToolExecutor, MagicMock, MagicMock]:
    """tend_to_player 用の最小 executor を返す。

    Returns:
        (executor, player_status_repository, event_publisher)
    """
    services = SpotGraphWorldServices(
        interaction=MagicMock(),
        exploration=MagicMock(),
        world_flags=MagicMock(as_frozen_set=MagicMock(return_value=frozenset())),
        game_end_evaluator=MagicMock(),
        exploration_progress=MagicMock(),
        movement=MagicMock(),
        simulation=None,
    )
    inv_repo = MagicMock()
    item_repo = MagicMock()
    status_repo = MagicMock()
    publisher = MagicMock()
    exec = SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=inv_repo,
        item_repository=item_repo,
        event_publisher=publisher,
        player_status_repository=status_repo,
    )
    return exec, status_repo, publisher


def _args(target_player_id: int, **extra) -> dict:
    base = {
        "target_player_id": target_player_id,
        "target_display_name": "エイダ",
        "inner_thought": "助ける",
    }
    base.update(extra)
    return base


class TestTendToPlayerSuccess:
    """同 spot にいる倒れた仲間を介抱して revive する。"""

    def test_倒れた仲間を_revive_して_HP_40_で_復帰させる(self) -> None:
        exec, status_repo, publisher = _build_executor()
        actor = _build_player(player_id=1, is_down=False, spot_id=10)
        target = _build_player(
            player_id=2, is_down=True, spot_id=10, hp_current=0, hp_max=100
        )
        status_repo.find_by_id.side_effect = lambda pid: {
            PlayerId(1): actor, PlayerId(2): target,
        }.get(pid)

        result = exec._tend_to_player(player_id=1, args=_args(2))

        assert result.success is True
        assert target.is_down is False
        # TEND_REVIVE_HP_RATE=0.4 × max_hp 100 = 40
        assert target.hp.value == 40
        status_repo.save.assert_called_with(target)
        # PlayerRevivedEvent が pipeline に流れる
        publisher.publish_all.assert_called_once()

    def test_成功メッセージに_HP_と_対象名が含まれる(self) -> None:
        exec, status_repo, publisher = _build_executor()
        actor = _build_player(player_id=1, is_down=False, spot_id=10)
        target = _build_player(
            player_id=2, is_down=True, spot_id=10, hp_current=0, hp_max=100
        )
        status_repo.find_by_id.side_effect = lambda pid: {
            PlayerId(1): actor, PlayerId(2): target,
        }.get(pid)

        result = exec._tend_to_player(player_id=1, args=_args(2))

        assert "エイダ" in result.message
        assert "40" in result.message
        assert "100" in result.message  # max_hp


class TestTendToPlayerFailures:
    """前提条件違反の各ケース。"""

    def test_自分自身を_対象に_すると_INVALID_TARGET_KIND(self) -> None:
        exec, status_repo, publisher = _build_executor()
        result = exec._tend_to_player(player_id=1, args=_args(1))
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_KIND"

    def test_target_player_id_が_int_でない場合_INVALID_TARGET_LABEL(self) -> None:
        exec, status_repo, publisher = _build_executor()
        result = exec._tend_to_player(
            player_id=1,
            args={"target_player_id": "abc", "inner_thought": ""},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"

    def test_対象が_元気だと_INTERACTION_PRECONDITION_FAILED(self) -> None:
        exec, status_repo, publisher = _build_executor()
        actor = _build_player(player_id=1, is_down=False, spot_id=10)
        target = _build_player(player_id=2, is_down=False, spot_id=10)
        status_repo.find_by_id.side_effect = lambda pid: {
            PlayerId(1): actor, PlayerId(2): target,
        }.get(pid)

        result = exec._tend_to_player(player_id=1, args=_args(2))
        assert result.success is False
        assert result.error_code == "INTERACTION_PRECONDITION_FAILED"
        assert "倒れていない" in result.message

    def test_自分が_倒れている_と_EXHAUSTED(self) -> None:
        """倒れた player は他人を介抱できない。"""
        exec, status_repo, publisher = _build_executor()
        actor = _build_player(player_id=1, is_down=True, spot_id=10, hp_current=0)
        target = _build_player(player_id=2, is_down=True, spot_id=10, hp_current=0)
        status_repo.find_by_id.side_effect = lambda pid: {
            PlayerId(1): actor, PlayerId(2): target,
        }.get(pid)

        result = exec._tend_to_player(player_id=1, args=_args(2))
        assert result.success is False
        assert result.error_code == "EXHAUSTED"

    def test_別_spot_の_対象は_INTERACTION_PRECONDITION_FAILED(self) -> None:
        exec, status_repo, publisher = _build_executor()
        actor = _build_player(player_id=1, is_down=False, spot_id=10)
        target = _build_player(player_id=2, is_down=True, spot_id=20)  # 別 spot
        status_repo.find_by_id.side_effect = lambda pid: {
            PlayerId(1): actor, PlayerId(2): target,
        }.get(pid)

        result = exec._tend_to_player(player_id=1, args=_args(2))
        assert result.success is False
        assert result.error_code == "INTERACTION_PRECONDITION_FAILED"
        assert "同じ場所" in result.message

    def test_対象が_repository_に存在しない場合_TARGET_NOT_FOUND(self) -> None:
        exec, status_repo, publisher = _build_executor()
        status_repo.find_by_id.return_value = None
        result = exec._tend_to_player(player_id=1, args=_args(99))
        assert result.success is False
        assert result.error_code == "TARGET_NOT_FOUND"

    def test_player_status_repository_未注入で_UNSUPPORTED_TOOL(self) -> None:
        services = SpotGraphWorldServices(
            interaction=MagicMock(),
            exploration=MagicMock(),
            world_flags=MagicMock(
                as_frozen_set=MagicMock(return_value=frozenset())
            ),
            game_end_evaluator=MagicMock(),
            exploration_progress=MagicMock(),
            movement=MagicMock(),
            simulation=None,
        )
        exec = SpotGraphToolExecutor(
            spot_graph_world_services=services,
            player_inventory_repository=MagicMock(),
            item_repository=MagicMock(),
            player_status_repository=None,  # 未注入
        )
        result = exec._tend_to_player(player_id=1, args=_args(2))
        assert result.success is False
        assert result.error_code == "UNSUPPORTED_TOOL"


class TestDispatch:
    def test_get_handlers_に_TEND_TO_PLAYER_が_登録(self) -> None:
        """executor が新 tool の handler を expose する (regression test)。"""
        from ai_rpg_world.application.llm.tool_constants import (
            TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
        )
        exec, _, _ = _build_executor()
        handlers = exec.get_handlers()
        assert TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER in handlers
