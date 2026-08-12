import pytest
from unittest.mock import MagicMock

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GameEndConditionValidationException,
    ScenarioPredicateEvaluationException,
)
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import GameEndConditionEvaluator
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import GameEndCondition
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.predicate_result import PredicateResult
from ai_rpg_world.domain.world_graph.enum.game_result_enum import (
    GameResultEnum,
)

#: 「成立したか」だけを見る試験で使う既定。勝敗はシナリオがどちらのリストに
#: 書いたかで決まるので、成立の有無しか見ないなら片側に固定して構わない。
#:
#: 返り値が WIN であることまで見る試験は、**呼び出し側で WIN を渡す**。
#: ここを共有の既定にすると、勝敗が呼び出し側で決まるという要点が消える。
_SIDE = GameResultEnum.LOSE



def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def test_flag_set_win() -> None:
    ev = GameEndConditionEvaluator()
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.place_entity(EntityId.create(1), SpotId.create(1))
    cond = GameEndCondition(
        condition_type=GameEndConditionTypeEnum.FLAG_SET,
        target_flag="escaped",
    )
    r = ev.evaluate(g, cond, frozenset({"escaped"}), [PlayerId(1)],
        result_on_match=GameResultEnum.WIN,
    )
    assert r.is_ended and r.result == GameResultEnum.WIN


def test_flag_set_delegates_to_typed_common_evaluator() -> None:
    """終了条件固有の勝敗・理由文を保ち、FLAG_SETの真偽だけを共通核へ委譲する。"""
    common = MagicMock()
    common.evaluate.return_value = PredicateResult.satisfied()
    evaluator = GameEndConditionEvaluator(predicate_evaluator=common)
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    condition = GameEndCondition(
        condition_type=GameEndConditionTypeEnum.FLAG_SET,
        target_flag="escaped",
    )

    result = evaluator.evaluate(
        graph,
        condition,
        frozenset(),
        [],
        result_on_match=GameResultEnum.WIN,
    )

    assert result.is_ended is True
    assert result.reason == "フラグ成立: escaped"
    predicate, context = common.evaluate.call_args.args
    assert predicate.flag_name == "escaped"
    assert context.world_flags == frozenset()


@pytest.mark.parametrize("reason", ["missing", "unsupported"])
def test_flag_set_evaluation_failure_stops_game_end(reason: str) -> None:
    """共通評価核の入力不足・未対応は、通常の終了条件不成立へ縮退させない。"""
    common = MagicMock()
    failed = MagicMock()
    common.evaluate.return_value = (
        PredicateResult.context_missing(
            failed_predicate=failed,
            failed_path=(),
            required_context={"world_flags"},
        )
        if reason == "missing"
        else PredicateResult.unsupported(
            failed_predicate=failed,
            failed_path=(),
        )
    )
    condition = GameEndCondition(
        condition_type=GameEndConditionTypeEnum.FLAG_SET,
        target_flag="escaped",
    )

    with pytest.raises(ScenarioPredicateEvaluationException):
        GameEndConditionEvaluator(predicate_evaluator=common).evaluate(
            SpotGraphAggregate.empty(SpotGraphId.create(1)),
            condition,
            frozenset(),
            [],
            result_on_match=GameResultEnum.WIN,
        )


def test_all_at_spot_win() -> None:
    ev = GameEndConditionEvaluator()
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.place_entity(EntityId.create(1), SpotId.create(2))
    g.place_entity(EntityId.create(2), SpotId.create(2))
    cond = GameEndCondition(
        condition_type=GameEndConditionTypeEnum.ALL_AT_SPOT,
        target_spot_id=SpotId.create(2),
    )
    r = ev.evaluate(g, cond, frozenset(), [PlayerId(1), PlayerId(2)],
        result_on_match=GameResultEnum.WIN,
    )
    assert r.is_ended and r.result == GameResultEnum.WIN


def test_tick_limit_lose() -> None:
    ev = GameEndConditionEvaluator()
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.place_entity(EntityId.create(1), SpotId.create(1))
    cond = GameEndCondition(
        condition_type=GameEndConditionTypeEnum.TICK_LIMIT,
        tick_limit=10,
    )
    r = ev.evaluate(g, cond, frozenset(), [PlayerId(1)], current_tick=WorldTick(10),
        result_on_match=_SIDE,
    )
    assert r.is_ended and r.result == GameResultEnum.LOSE


def test_invalid_flag_set_condition_raises_domain_exception_on_construction() -> None:
    """FLAG_SET に target_flag が無い条件は、評価前の構築時点で拒否される。"""
    with pytest.raises(GameEndConditionValidationException, match="target_flag"):
        GameEndCondition(condition_type=GameEndConditionTypeEnum.FLAG_SET)


@pytest.mark.parametrize(
    ("condition_type", "kwargs", "message"),
    [
        (GameEndConditionTypeEnum.TICK_LIMIT, {}, "tick_limit"),
        (GameEndConditionTypeEnum.ALL_AT_SPOT, {}, "target_spot_id"),
        (GameEndConditionTypeEnum.ANY_AT_SPOT, {}, "target_spot_id"),
    ],
)
def test_required_game_end_condition_fields_are_rejected_on_construction(
    condition_type: GameEndConditionTypeEnum,
    kwargs: dict,
    message: str,
) -> None:
    """条件型ごとの必須フィールド欠落は、値オブジェクトの構築時点で拒否される。"""
    with pytest.raises(GameEndConditionValidationException, match=message):
        GameEndCondition(condition_type=condition_type, **kwargs)


class TestAllPlayerOutcomesResolved:
    """個人結果の混在を集団勝敗へ変換せず、中立の世界終了として扱う。"""

    @staticmethod
    def _evaluate(
        player_ids: list[PlayerId],
        outcomes: dict[int, PlayerOutcomeEnum] | None,
    ):
        graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
        condition = GameEndCondition(
            condition_type=GameEndConditionTypeEnum.ALL_PLAYER_OUTCOMES_RESOLVED
        )
        return GameEndConditionEvaluator().evaluate(
            graph,
            condition,
            frozenset(),
            player_ids,
            player_outcomes=outcomes,
            result_on_match=None,
        )

    def test_mixed_resolved_outcomes_end_without_collective_result(self) -> None:
        """RESCUED と STRANDED が混在しても、集団 WIN/LOSE ではなく中立終了にする。"""
        outcomes = {
            1: PlayerOutcomeEnum.RESCUED,
            2: PlayerOutcomeEnum.STRANDED,
        }

        result = self._evaluate([PlayerId(1), PlayerId(2)], outcomes)

        assert result.is_ended is True
        assert result.result is None
        assert result.player_outcomes == outcomes

    def test_one_unresolved_player_keeps_world_running(self) -> None:
        """一人でも UNRESOLVED なら個人結果の確定待ちとして終了しない。"""
        result = self._evaluate(
            [PlayerId(1), PlayerId(2)],
            {1: PlayerOutcomeEnum.RESCUED, 2: PlayerOutcomeEnum.UNRESOLVED},
        )

        assert result.is_ended is False

    def test_empty_player_set_does_not_end_persistent_world(self) -> None:
        """対象0人を「全員確定」とみなさず、終了条件なしの世界を誤終了させない。"""
        result = self._evaluate([], {})

        assert result.is_ended is False

    def test_missing_outcome_mapping_is_rejected(self) -> None:
        """結果表の配線漏れは永久未成立へ縮退させず、評価時に例外にする。"""
        with pytest.raises(GameEndConditionValidationException, match="player_outcomes"):
            self._evaluate([PlayerId(1)], None)
