"""スポットの実効照明を、前提条件の評価用に 1 か所で解決する。

``SPOT_LIGHTING_IS`` は「明るすぎる。誰かに見られる」という意図を持つ条件
なので、判定は spot の静的 atmosphere ではなく **実効照明** で行う
(docs/memory_system/interpersonal_interaction_design.md §6 PR 3)。松明を
持った同席者が居るのに「暗がりだから襲える」が通ってしまうと、宣言した
意図と実際の挙動が食い違う。

計算そのものは ``SpotPerceptionService.compute_effective_lighting`` が持つ。
本 resolver は「その計算に要る材料 (spot の atmosphere / 同席者の光源 /
昼夜 / 天候) を集める」だけの薄い層である。

**現在状態の表示と同じ値を返すこと**が重要になる。prompt が「暗い」と書いて
いるのに前提条件は「明るい」と判定する状態は、LLM から見て理由の分からない
失敗になる。そのため ``SpotGraphCurrentStateBuilder`` も本 resolver 経由で
実効照明を求める。2 か所で同じ計算を書くと、片方だけ直したときに静かに
食い違う。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.service.spot_perception_service import (
    SpotPerceptionService,
)

logger = logging.getLogger(__name__)

#: 視界が落ちる天候。RAIN は微減なので含めない (state builder と同じ基準)。
_VISION_OBSCURING_WEATHER = ("STORM", "FOG")

EntityHasLightSource = Callable[[int], bool]


class SpotEffectiveLightingResolver:
    """spot_id から実効照明を求める。"""

    def __init__(
        self,
        *,
        spot_graph_repository,
        entity_has_light_source: EntityHasLightSource,
        time_of_day_provider: Optional[Callable[[], object]] = None,
        weather_provider: Optional[Callable[[], object]] = None,
        perception: Optional[SpotPerceptionService] = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._entity_has_light_source = entity_has_light_source
        self._time_of_day_provider = time_of_day_provider
        self._weather_provider = weather_provider
        self._perception = perception or SpotPerceptionService()

    def resolve(self, spot_id: SpotId) -> Optional[LightingEnum]:
        """``spot_id`` の実効照明を返す。spot が見つからなければ None。

        **例外は握りつぶさない。** 想定外の失敗を None に倒すと、前提条件は
        「暗くない」に、表示は「明るい」に倒れて食い違う。両者を揃えるために
        resolver を作ったのに、退化パスだけが食い違う状態になる。壊れている
        ことは呼び出し元まで届いたほうがよい。

        None を返すのは「その spot が graph に無い」場合だけで、呼び出し側は
        「照明条件を成立させない」に倒す。明るい場所で暗所限定の行為が通る
        よりは、一度も通らないほうが気付ける (前者は成功として返るので
        trace にも異常が出ない)。
        """
        graph = self._spot_graph_repository.find_graph()
        node = graph.get_spot(spot_id)
        if node is None:
            logger.warning(
                "spot が見つからないため照明条件は不成立として扱う (spot_id=%s)",
                spot_id,
            )
            return None
        has_light_bearer = any(
            self._entity_has_light_source(int(eid))
            for eid in graph.presence_at(spot_id).present_entity_ids
        )
        return self._perception.compute_effective_lighting(
            node.atmosphere,
            has_light_bearer,
            is_outdoor=bool(node.is_outdoor),
            time_of_day_is_dark=self._time_of_day_is_dark(),
            weather_obscures_vision=self._weather_obscures_vision(),
        )

    def _time_of_day_is_dark(self) -> bool:
        """現在が暗い時間帯か。provider 不在 / 失敗なら「暗くない」。"""
        if self._time_of_day_provider is None:
            return False
        try:
            tod = self._time_of_day_provider()
            return bool(getattr(tod, "is_dark", False)) if tod is not None else False
        except Exception:
            return False

    def _weather_obscures_vision(self) -> bool:
        """現在が視界の落ちる天候か。provider 不在 / 失敗なら「良天候」。"""
        if self._weather_provider is None:
            return False
        try:
            ws = self._weather_provider()
            if ws is None:
                return False
            weather_type = getattr(ws.weather_type, "value", None) or str(
                ws.weather_type
            )
            return weather_type in _VISION_OBSCURING_WEATHER
        except Exception:
            return False
