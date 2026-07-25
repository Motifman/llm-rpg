"""SpotGraphAggregate.update_spot_atmosphere が spot の環境を書き換えることを保証する。

`CHANGE_ATMOSPHERE` 効果 (停電・気温変化・危険度上昇) を成立させるための操作。
`SpotNode` も `SpotAtmosphere` も frozen なので、指定された項目だけ差し替えた
新しい値へ置き換える。指定しなかった項目は元の値を保つ (部分更新)。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotNotInGraphException,
)
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _node(i: int, atmosphere: SpotAtmosphere | None) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
        atmosphere=atmosphere,
    )


def _graph(atmosphere: SpotAtmosphere | None) -> SpotGraphAggregate:
    return SpotGraphAggregate(
        graph_id=SpotGraphId.create(1),
        spots={SpotId.create(1): _node(1, atmosphere)},
        connections_by_id={},
    )


class TestUpdateSpotAtmosphere:
    """update_spot_atmosphere が指定項目だけを差し替える。"""

    def test_lighting_is_replaced(self) -> None:
        """lighting を渡すと、その spot の明るさが指定値に変わる。"""
        graph = _graph(SpotAtmosphere(lighting=LightingEnum.BRIGHT))

        graph.update_spot_atmosphere(SpotId.create(1), lighting=LightingEnum.DARK)

        assert graph.get_spot(SpotId.create(1)).atmosphere.lighting is LightingEnum.DARK

    def test_unspecified_fields_are_preserved(self) -> None:
        """指定しなかった項目 (sound_ambient など) は元の値のまま残る。"""
        graph = _graph(
            SpotAtmosphere(
                lighting=LightingEnum.BRIGHT,
                sound_ambient="機械の駆動音",
                hazard_level=2,
            )
        )

        graph.update_spot_atmosphere(SpotId.create(1), lighting=LightingEnum.PITCH_BLACK)

        atmosphere = graph.get_spot(SpotId.create(1)).atmosphere
        assert atmosphere.lighting is LightingEnum.PITCH_BLACK
        assert atmosphere.sound_ambient == "機械の駆動音"
        assert atmosphere.hazard_level == 2

    def test_hazard_level_and_description_are_replaced(self) -> None:
        """hazard_level と hazard_description を渡すと危険度の表示が入れ替わる。"""
        graph = _graph(SpotAtmosphere(lighting=LightingEnum.BRIGHT))

        graph.update_spot_atmosphere(
            SpotId.create(1), hazard_level=3, hazard_description="有毒ガスが漏れている"
        )

        atmosphere = graph.get_spot(SpotId.create(1)).atmosphere
        assert atmosphere.hazard_level == 3
        assert atmosphere.hazard_description == "有毒ガスが漏れている"

    def test_spot_without_atmosphere_gains_one(self) -> None:
        """atmosphere を持たない spot に指定すると、既定値を土台にした atmosphere が作られる。"""
        graph = _graph(None)

        graph.update_spot_atmosphere(SpotId.create(1), lighting=LightingEnum.DARK)

        assert graph.get_spot(SpotId.create(1)).atmosphere.lighting is LightingEnum.DARK

    def test_spot_without_atmosphere_gets_bright_when_lighting_is_unspecified(
        self,
    ) -> None:
        """atmosphere が無い spot に lighting 以外だけを指定すると、明るさは既定の BRIGHT になる。

        「未設定 = 明るい」を安全側の既定とする。暗いと視認や戦闘の判定が変わって
        しまうため、書かれていない spot を勝手に暗くしない。
        """
        graph = _graph(None)

        graph.update_spot_atmosphere(SpotId.create(1), hazard_level=2)

        atmosphere = graph.get_spot(SpotId.create(1)).atmosphere
        assert atmosphere.hazard_level == 2
        assert atmosphere.lighting is LightingEnum.BRIGHT

    def test_unknown_spot_raises(self) -> None:
        """グラフに存在しない spot を指定すると SpotNotInGraphException。"""
        graph = _graph(SpotAtmosphere(lighting=LightingEnum.BRIGHT))

        with pytest.raises(SpotNotInGraphException):
            graph.update_spot_atmosphere(SpotId.create(99), lighting=LightingEnum.DARK)

    def test_no_field_specified_leaves_atmosphere_untouched(self) -> None:
        """更新項目を 1 つも渡さない呼び出しでは atmosphere が変化しない。"""
        original = SpotAtmosphere(lighting=LightingEnum.BRIGHT, hazard_level=1)
        graph = _graph(original)

        graph.update_spot_atmosphere(SpotId.create(1))

        assert graph.get_spot(SpotId.create(1)).atmosphere == original
