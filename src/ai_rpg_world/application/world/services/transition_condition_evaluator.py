"""ゲートウェイ遷移条件の評価器。"""

from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.transition_condition import (
    TransitionCondition,
    RequireRelation,
    RequireToll,
    BlockIfWeather,
)
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum

if TYPE_CHECKING:
    from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate


@dataclass(frozen=True)
class TransitionContext:
    """遷移条件評価に必要なコンテキスト"""
    player_id: int
    player_status: "PlayerStatusAggregate"
    from_spot_id: SpotId
    to_spot_id: SpotId
    current_weather: WeatherState


class ITransitionRelationChecker:
    """RequireRelation 判定用のポート。ギルド・クエスト等の「関係」を確認する。"""

    def has_relation(
        self,
        player_id: int,
        relation_type: str,
        from_spot_id: SpotId,
        to_spot_id: SpotId,
    ) -> bool:
        """プレイヤーが指定の関係を満たすか"""
        raise NotImplementedError


class TransitionConditionEvaluator:
    """遷移条件リストをコンテキストに対して評価し、許可/不許可とメッセージを返す。"""

    def __init__(self, relation_checker: Optional[ITransitionRelationChecker] = None):
        self._relation_checker = relation_checker

    def evaluate(
        self,
        conditions: List[TransitionCondition],
        context: TransitionContext,
    ) -> tuple[bool, Optional[str]]:
        """
        全条件を評価する。すべて満たせば (True, None)、いずれか不満なら (False, 理由メッセージ)。
        """
        if not conditions:
            return True, None
        for cond in conditions:
            if isinstance(cond, RequireRelation):
                ok, msg = self._eval_require_relation(cond, context)
            elif isinstance(cond, RequireToll):
                ok, msg = self._eval_require_toll(cond, context)
            elif isinstance(cond, BlockIfWeather):
                ok, msg = self._eval_block_if_weather(cond, context)
            else:
                ok, msg = False, "不明な遷移条件です"
            if not ok:
                return False, msg
        return True, None

    def _eval_require_relation(self, cond: RequireRelation, context: TransitionContext) -> tuple[bool, Optional[str]]:
        if self._relation_checker is None:
            return False, "関係の確認ができません（設定されていません）"
        if self._relation_checker.has_relation(
            context.player_id,
            cond.relation_type,
            context.from_spot_id,
            context.to_spot_id,
        ):
            return True, None
        return False, "この出口は関係者のみ利用できます"

    def _eval_require_toll(self, cond: RequireToll, context: TransitionContext) -> tuple[bool, Optional[str]]:
        if cond.amount_gold <= 0:
            return True, None
        if not context.player_status.gold.can_subtract(cond.amount_gold):
            return False, f"通行料が不足しています（必要: {cond.amount_gold} G、所持: {context.player_status.gold.value} G）"
        return True, None

    def _eval_block_if_weather(self, cond: BlockIfWeather, context: TransitionContext) -> tuple[bool, Optional[str]]:
        if context.current_weather.weather_type in cond.blocked_weather_types:
            return False, "悪天候のため通行止めです"
        return True, None
