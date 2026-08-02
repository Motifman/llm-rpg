"""「作業を N 個終わらせたら勝ち」を宣言できることを保証する。

## なぜ要るか

クルー側の勝ち筋が「無線を直す」のようなフラグ 1 個だと、**手分けする理由が
生まれない**。誰か一人が最短で目的地へ向かえば終わる。本家のタスクが効いて
いるのは、複数の作業が別々の場所にあり、全員が散らばらないと終わらないから。
散らばるから襲われるし、誰がどこに居たかが手がかりになる。

既存の `FLAG_SET` は 1 個ずつしか見られないので、「8 個のうち 6 個」が
書けなかった。

## なぜ専用の store を作らないか

作業の完了は `SET_FLAG` effect で立つ既存のフラグで表せる。フラグは snapshot
に載っているので、途中再開でも進捗が消えない。専用 store を足すと codec の
追従が要る (`design_decisions.md` #27) わりに、得られるのは「数える」だけ。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
    GameEndConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GameEndConditionValidationException,
)
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import (
    GameEndCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import (
    GameResultEnum,
)

#: この単体試験は「成立したか」だけを見る。勝敗はシナリオがどちらの
#: リストに書いたかで決まるので、ここでは片側に固定して構わない。
_SIDE = GameResultEnum.LOSE


_TASKS = ("task_radio", "task_fuel", "task_wiring", "task_scan")


def _condition(*, flags=_TASKS, min_count=3) -> GameEndCondition:
    return GameEndCondition(
        condition_type=GameEndConditionTypeEnum.FLAGS_SET_AT_LEAST,
        required_flags=flags,
        min_set_count=min_count,
    )


def _graph() -> SpotGraphAggregate:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(
        SpotNode(
            spot_id=SpotId.create(1),
            name="S1",
            description="d",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
        )
    )
    graph.place_entity(EntityId.create(1), SpotId.create(1))
    return graph


def _evaluate(condition: GameEndCondition, flags: set[str]) -> bool:
    return GameEndConditionEvaluator().evaluate(
        _graph(), condition, frozenset(flags), [PlayerId(1)],
        result_on_match=_SIDE,
    ).is_ended


class TestCounting:
    """立っているフラグの数で成立する。"""

    def test_not_met_below_the_threshold(self) -> None:
        """2 個では成立しない (閾値は 3)。"""
        assert _evaluate(_condition(), {"task_radio", "task_fuel"}) is False

    def test_met_at_the_threshold(self) -> None:
        """ちょうど 3 個で成立する。

        境界を「より多い」にすると、宣言した数を満たしても終わらない。
        """
        assert _evaluate(_condition(), {"task_radio", "task_fuel", "task_wiring"}) is True

    def test_met_above_the_threshold(self) -> None:
        """4 個でも成立する。"""
        assert _evaluate(_condition(), set(_TASKS)) is True


class TestOnlyDeclaredFlagsCount:
    """宣言した作業だけを数える。"""

    def test_unrelated_flags_do_not_count(self) -> None:
        """関係の無いフラグは進捗にならない。

        ここが緩いと、**シナリオが別の用途で立てたフラグで勝ててしまう**。
        `darkened_station` は照明や救難信号でもフラグを立てるので、実害が
        ある。
        """
        assert _evaluate(_condition(), {"lights_off", "distress_sent", "door_open"}) is False

    def test_a_mix_counts_only_the_declared_ones(self) -> None:
        """混ざっていても、宣言したぶんだけ数える。"""
        flags = {"task_radio", "task_fuel", "lights_off", "distress_sent"}

        assert _evaluate(_condition(), flags) is False


class TestValidation:
    """書き間違いを読み込み時に落とす。"""

    def test_empty_flag_list_is_rejected(self) -> None:
        """対象の作業が空なら拒否する。

        空を許すと「0 個中 0 個」で **開始した瞬間に勝つ**。
        """
        with pytest.raises(GameEndConditionValidationException):
            _condition(flags=())

    def test_threshold_above_the_list_is_rejected(self) -> None:
        """宣言した数より大きい閾値は拒否する。

        **絶対に成立しない条件**になる。書いた本人は勝てるつもりでいるので、
        run が終わるまで気付けない。
        """
        with pytest.raises(GameEndConditionValidationException):
            _condition(flags=("a", "b"), min_count=3)

    def test_zero_threshold_is_rejected(self) -> None:
        """閾値 0 は拒否する。開始した瞬間に成立してしまう。"""
        with pytest.raises(GameEndConditionValidationException):
            _condition(min_count=0)

    def test_missing_threshold_is_rejected(self) -> None:
        """閾値の書き忘れを既定値で埋めない。

        既定を「全部」にすると、書き忘れと全部指定が区別できなくなる
        (SURVIVING_PLAYERS_WITH_STATE_AT_MOST と同じ判断)。
        """
        with pytest.raises(GameEndConditionValidationException):
            GameEndCondition(
                condition_type=GameEndConditionTypeEnum.FLAGS_SET_AT_LEAST,
                required_flags=_TASKS,
            )

    def test_duplicate_flags_are_rejected(self) -> None:
        """同じ作業を二度書いたら拒否する。

        重複を数えると「4 個中 3 個」のつもりが 1 個の作業で 2 進む。
        """
        with pytest.raises(GameEndConditionValidationException):
            _condition(flags=("task_radio", "task_radio", "task_fuel"))


class TestItCanBeWrittenInAScenario:
    """シナリオ JSON から読み込める。

    domain の VO と評価器が正しくても、loader が読まなければシナリオには
    書けない。**「参照はあるが本番経路に乗っていない」形**を作らないよう、
    JSON から読む経路まで確かめる (initial_state / initial_items で二度
    やった失敗)。
    """

    def _scenario(self, tmp_path, condition: dict):
        import json
        import shutil
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[3]
            / "data" / "scenarios" / "darkened_station.json"
        )
        raw = json.loads(src.read_text(encoding="utf-8"))
        raw["game_end_conditions"] = {"win": [condition], "lose": []}
        dst = tmp_path / "tasks.json"
        dst.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return dst

    def test_a_valid_declaration_loads(self, tmp_path) -> None:
        """宣言どおりの条件が組み上がる。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        path = self._scenario(tmp_path, {
            "type": "FLAGS_SET_AT_LEAST",
            "required_flags": list(_TASKS),
            "min_set_count": 3,
        })

        result = ScenarioLoader().load_from_file(path)

        (cond,) = result.win_conditions
        assert cond.required_flags == _TASKS
        assert cond.min_set_count == 3

    def test_an_impossible_threshold_is_rejected_at_load(self, tmp_path) -> None:
        """達成不能な閾値は読み込み時に落とす。

        run が始まってからでは、勝てないことに誰も気付けない。
        """
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        path = self._scenario(tmp_path, {
            "type": "FLAGS_SET_AT_LEAST",
            "required_flags": ["task_radio"],
            "min_set_count": 5,
        })

        with pytest.raises(Exception):
            ScenarioLoader().load_from_file(path)

    def test_a_missing_threshold_is_rejected_at_load(self, tmp_path) -> None:
        """閾値の書き忘れも読み込み時に落とす。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        path = self._scenario(tmp_path, {
            "type": "FLAGS_SET_AT_LEAST",
            "required_flags": list(_TASKS),
        })

        with pytest.raises(Exception):
            ScenarioLoader().load_from_file(path)
