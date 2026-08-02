"""陣営の全滅を終了条件として書けることを保証する。

既存の終了条件は場所 (ALL_AT_SPOT / ANY_AT_SPOT)・フラグ・tick 上限の 3 種
しかなく、**「crew が全滅したら終わり」が書けなかった**。秘匿役職シナリオ
(darkened_station) では crew 側の勝ち筋だけを条件に置き、襲う側の勝ちは
目的文で表現するしかなかった。

`SURVIVING_PLAYERS_WITH_STATE_AT_MOST` は「``required_state`` を満たす
**生存** プレイヤーが ``max_surviving`` 人以下なら成立」を表す。

## 「生存」の定義

倒れている (``is_down``) だけでは生存とみなす。倒れた仲間は蘇生できるので、
そこでゲームを終わらせると蘇生の意味が消える。数えないのは
``PlayerOutcomeEnum.DEAD`` が確定した相手だけ。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
    GameEndConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GameEndConditionValidationException,
)
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)
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


_CREW_A, _CREW_B, _KEEPER = PlayerId(1), PlayerId(2), PlayerId(3)
_ALL = [_CREW_A, _CREW_B, _KEEPER]

_ROLES = {
    int(_CREW_A): {"role": "crew"},
    int(_CREW_B): {"role": "crew"},
    int(_KEEPER): {"role": "keeper"},
}


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
    for pid in _ALL:
        graph.place_entity(EntityId.create(int(pid)), SpotId.create(1))
    return graph


def _condition(max_surviving: int = 0) -> GameEndCondition:
    return GameEndCondition(
        condition_type=GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST,
        required_state={"role": "crew"},
        max_surviving=max_surviving,
    )


def _evaluate(condition, outcomes, states=None):
    return GameEndConditionEvaluator().evaluate(
        _graph(),
        condition,
        frozenset(),
        _ALL,
        None,
        player_states=_ROLES if states is None else states,
        player_outcomes=outcomes,
        result_on_match=_SIDE,
    )


def _outcomes(**dead) -> dict:
    """全員 UNRESOLVED を既定に、指定した player だけ DEAD にする。"""
    table = {int(pid): PlayerOutcomeEnum.UNRESOLVED for pid in _ALL}
    for key, pid in dead.items():
        table[int(pid)] = PlayerOutcomeEnum.DEAD
    return table


class TestFactionElimination:
    """指定した陣営の生存者が閾値以下になったら成立する。"""

    def test_not_ended_while_the_faction_survives(self) -> None:
        """crew が 2 人生きている間は成立しない。"""
        result = _evaluate(_condition(max_surviving=0), _outcomes())
        assert result.is_ended is False

    def test_not_ended_with_one_left(self) -> None:
        """crew が 1 人でも残っていれば成立しない (max_surviving=0)。"""
        result = _evaluate(_condition(max_surviving=0), _outcomes(a=_CREW_A))
        assert result.is_ended is False

    def test_ended_when_the_whole_faction_is_dead(self) -> None:
        """crew が全員 DEAD になったら成立する。"""
        result = _evaluate(
            _condition(max_surviving=0), _outcomes(a=_CREW_A, b=_CREW_B)
        )
        assert result.is_ended is True

    def test_result_is_lose(self) -> None:
        """結果は LOSE。

        「自陣営が全滅した」は集団としての敗北。襲う側の勝ちという読み替えは
        シナリオの語りが担い、エンジンは集団の WIN / LOSE だけを返す。
        """
        result = _evaluate(
            _condition(max_surviving=0), _outcomes(a=_CREW_A, b=_CREW_B)
        )
        assert result.result == GameResultEnum.LOSE

    def test_other_factions_do_not_count(self) -> None:
        """条件に指定していない役割の生死は影響しない。

        keeper が死んでも crew の全滅条件は成立しない。役割で数える対象を
        絞れていなければ、誰か 1 人死ぬたびに終了してしまう。
        """
        result = _evaluate(_condition(max_surviving=0), _outcomes(k=_KEEPER))
        assert result.is_ended is False

    def test_threshold_above_zero(self) -> None:
        """max_surviving=1 なら、残り 1 人になった時点で成立する。

        「最後の一人になったら詰み」のような設定を書けるようにする。
        """
        result = _evaluate(_condition(max_surviving=1), _outcomes(a=_CREW_A))
        assert result.is_ended is True


class TestDownedPlayersStillCount:
    """倒れているだけの相手は生存として数える。"""

    def test_downed_but_not_dead_keeps_the_game_going(self) -> None:
        """crew 全員が倒れていても、DEAD が確定していなければ続行する。

        倒れた仲間は蘇生できる。ここで終わらせると蘇生の意味が消える。
        数えないのは PlayerOutcomeEnum.DEAD が確定した相手だけ。
        """
        outcomes = {int(pid): PlayerOutcomeEnum.UNRESOLVED for pid in _ALL}

        result = _evaluate(_condition(max_surviving=0), outcomes)

        assert result.is_ended is False

    def test_rescued_players_are_not_counted_as_dead(self) -> None:
        """RESCUED も生存として数える (DEAD 以外は全て生存)。"""
        outcomes = {int(pid): PlayerOutcomeEnum.UNRESOLVED for pid in _ALL}
        outcomes[int(_CREW_A)] = PlayerOutcomeEnum.RESCUED
        outcomes[int(_CREW_B)] = PlayerOutcomeEnum.DEAD

        result = _evaluate(_condition(max_surviving=0), outcomes)

        assert result.is_ended is False


class TestMissingInputsFailLoudly:
    """判定材料が渡っていなければ、黙って未成立にせず落とす。"""

    def test_missing_states_raises(self) -> None:
        """player_states が渡っていなければ例外にする。

        黙って「未成立」に倒すと、勝敗条件が永久に成立しないまま実験が
        走り続ける。配線漏れは大きく失敗させる。
        """
        with pytest.raises(GameEndConditionValidationException):
            GameEndConditionEvaluator().evaluate(
                _graph(), _condition(), frozenset(), _ALL, None,
                player_states=None,
                player_outcomes=_outcomes(),
        result_on_match=_SIDE,
    )

    def test_missing_outcomes_raises(self) -> None:
        """player_outcomes が渡っていなければ例外にする。"""
        with pytest.raises(GameEndConditionValidationException):
            GameEndConditionEvaluator().evaluate(
                _graph(), _condition(), frozenset(), _ALL, None,
                player_states=_ROLES,
                player_outcomes=None,
        result_on_match=_SIDE,
    )


class TestConditionValidation:
    """条件そのものの不備は構築時に弾く。"""

    def test_missing_required_state_is_rejected(self) -> None:
        """required_state が無いと、誰を数えるか決まらない。"""
        with pytest.raises(GameEndConditionValidationException):
            GameEndCondition(
                condition_type=(
                    GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST
                ),
                max_surviving=0,
            )

    def test_missing_max_surviving_is_rejected(self) -> None:
        """max_surviving が無いと閾値が決まらない。

        0 を既定にすると「書き忘れ」と「全滅を指定した」が区別できない。
        """
        with pytest.raises(GameEndConditionValidationException):
            GameEndCondition(
                condition_type=(
                    GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST
                ),
                required_state={"role": "crew"},
            )

    def test_negative_threshold_is_rejected(self) -> None:
        """負の閾値は成立しえないので弾く。"""
        with pytest.raises(GameEndConditionValidationException):
            GameEndCondition(
                condition_type=(
                    GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST
                ),
                required_state={"role": "crew"},
                max_surviving=-1,
            )


class TestOutcomeResolutionAndEndConditionsCannotCoexist:
    """outcome_resolution と game_end_conditions の同時宣言を読み込み時に落とす。

    ``outcome_resolution`` を宣言したシナリオでは、runtime は「全員の outcome が
    確定したら終わり」だけを見る経路に分岐し、**win / lose 条件を一切評価
    しない** (`WorldRuntime.check_game_end`)。

    両方書けてしまうと、陣営の敗北条件を書いたのに永久に成立しない。しかも
    その状態は「まだゲームが続いている」と区別が付かないので、実 run が最後
    まで走り切ってから気付くことになる。**この機能が乗りそうなのは協力・
    裏切り系のシナリオ (`*_coop`) で、それらはまさに outcome_resolution を
    使っている**ため、放置すると踏む可能性が高い。
    """

    def test_declaring_both_fails_to_load(self) -> None:
        """両方書いたシナリオは ScenarioLoadError で落ちる。"""
        import copy

        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError,
            ScenarioLoader,
        )
        from tests.infrastructure.scenario.test_scenario_loader import (
            _minimal_scenario,
        )

        scenario = copy.deepcopy(_minimal_scenario())
        scenario["outcome_resolution"] = {
            "stranded_at_tick": 100,
            "summit_spot": "room_a",
            "signal_fire_flag": "signal",
        }
        scenario["game_end_conditions"] = {
            "win": [],
            "lose": [{
                "type": "SURVIVING_PLAYERS_WITH_STATE_AT_MOST",
                "required_state": {"role": "crew"},
                "max_surviving": 0,
            }],
        }

        with pytest.raises(ScenarioLoadError) as exc_info:
            ScenarioLoader().load_from_dict(scenario)

        assert "outcome_resolution" in str(exc_info.value)

    def test_outcome_resolution_alone_still_loads(self) -> None:
        """outcome_resolution だけなら従来どおり読める (既存シナリオは不変)。"""
        import copy

        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader
        from tests.infrastructure.scenario.test_scenario_loader import (
            _minimal_scenario,
        )

        scenario = copy.deepcopy(_minimal_scenario())
        scenario["outcome_resolution"] = {
            "stranded_at_tick": 100,
            "summit_spot": "room_a",
            "signal_fire_flag": "signal",
        }
        scenario["game_end_conditions"] = {"win": [], "lose": []}

        result = ScenarioLoader().load_from_dict(scenario)

        assert result.outcome_resolution_config is not None
