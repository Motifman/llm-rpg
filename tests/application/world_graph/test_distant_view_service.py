"""DistantViewService が area 単位の遠景候補を絞り込み、本文用の文にする挙動を保証する。"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.distant_view_service import (
    DistantViewArea,
    DistantViewConnection,
    DistantViewService,
    DistantViewSpot,
)


def _spot(
    spot_id: int,
    *,
    area_id: str | None,
    x: float,
    y: float,
    is_outdoor: bool = True,
) -> DistantViewSpot:
    return DistantViewSpot(
        spot_id=spot_id,
        area_id=area_id,
        x=x,
        y=y,
        is_outdoor=is_outdoor,
    )


def _area(
    area_id: str,
    visible_name: str,
    *,
    prominence: float,
    x: float,
    y: float,
    distant_descriptions: dict[str, str] | None = None,
) -> DistantViewArea:
    return DistantViewArea(
        area_id=area_id,
        name=visible_name,
        visible_name=visible_name,
        prominence=prominence,
        x=x,
        y=y,
        distant_descriptions=distant_descriptions or {},
    )


class TestDistantViewFiltering:
    """遠景の4段絞り込みと局所 area 除外を固定する。"""

    def test_indoor_spot_returns_no_lines(self) -> None:
        """現在地が屋内なら、目立つ area があっても遠景文は生成しない。"""
        result = DistantViewService().render(
            current_spot_id=1,
            spots=(
                _spot(1, area_id="base", x=0.0, y=0.0, is_outdoor=False),
                _spot(2, area_id="mountain", x=0.0, y=6.0),
            ),
            areas=(
                _area("base", "拠点", prominence=0.0, x=0.0, y=0.0),
                _area("mountain", "切り立った山影", prominence=0.95, x=0.0, y=6.0),
            ),
            connections=(),
        )

        assert result.lines == ()
        assert "indoor" in result.skipped_reasons

    def test_low_prominence_area_is_filtered_out(self) -> None:
        """目立ち度が閾値未満の area は、近くても遠景候補にしない。"""
        result = DistantViewService().render(
            current_spot_id=1,
            spots=(
                _spot(1, area_id="base", x=0.0, y=0.0),
                _spot(2, area_id="swamp", x=0.0, y=4.0),
            ),
            areas=(
                _area("base", "拠点", prominence=0.0, x=0.0, y=0.0),
                _area("swamp", "湿った低地", prominence=0.1, x=0.0, y=4.0),
            ),
            connections=(),
        )

        assert result.lines == ()
        assert "all_below_threshold" in result.skipped_reasons

    def test_current_and_outgoing_neighbor_area_are_excluded(self) -> None:
        """現在地 area と outgoing 接続先 area は、遠景ではなく局所説明の領分として除外する。"""
        result = DistantViewService().render(
            current_spot_id=1,
            spots=(
                _spot(1, area_id="base", x=0.0, y=0.0),
                _spot(2, area_id="forest", x=0.0, y=1.0),
                _spot(3, area_id="mountain", x=0.0, y=6.0),
            ),
            areas=(
                _area("base", "拠点", prominence=0.0, x=0.0, y=0.0),
                _area("forest", "深い森の緑", prominence=0.9, x=0.0, y=1.0),
                _area("mountain", "切り立った山影", prominence=0.95, x=0.0, y=6.0),
            ),
            connections=(DistantViewConnection(from_spot_id=1, to_spot_id=2),),
        )

        assert result.lines == ("北に切り立った山影が見える。",)
        assert result.rendered_area_ids == ("mountain",)

    def test_same_direction_keeps_highest_score_and_max_two_lines(self) -> None:
        """同方角は最上位候補1つに集約し、全体も2件までに抑える。"""
        result = DistantViewService().render(
            current_spot_id=1,
            spots=(
                _spot(1, area_id="base", x=0.0, y=0.0),
                _spot(2, area_id="north_a", x=0.0, y=4.0),
                _spot(3, area_id="north_b", x=0.2, y=5.0),
                _spot(4, area_id="east", x=4.0, y=0.0),
                _spot(5, area_id="west", x=-4.0, y=0.0),
            ),
            areas=(
                _area("base", "拠点", prominence=0.0, x=0.0, y=0.0),
                _area("north_a", "低い丘", prominence=0.5, x=0.0, y=4.0),
                _area("north_b", "高い山影", prominence=0.95, x=0.2, y=5.0),
                _area("east", "東の湿地", prominence=0.7, x=4.0, y=0.0),
                _area("west", "西の森", prominence=0.6, x=-4.0, y=0.0),
            ),
            connections=(),
        )

        assert len(result.lines) == 2
        assert result.rendered_area_ids == ("north_b", "east")
        assert all("低い丘" not in line for line in result.lines)

    def test_distant_description_for_distance_band_is_used(self) -> None:
        """area が距離帯別の文を持つ場合は、汎用文より宣言文を優先する。"""
        result = DistantViewService().render(
            current_spot_id=1,
            spots=(
                _spot(1, area_id="base", x=0.0, y=0.0),
                _spot(2, area_id="mountain", x=0.0, y=6.0),
            ),
            areas=(
                _area("base", "拠点", prominence=0.0, x=0.0, y=0.0),
                _area(
                    "mountain",
                    "切り立った山影",
                    prominence=0.95,
                    x=0.0,
                    y=6.0,
                    distant_descriptions={"far": "北の遠くに山影が霞んでいる。"},
                ),
            ),
            connections=(),
        )

        assert result.lines == ("北の遠くに山影が霞んでいる。",)


class TestDistantViewDirection:
    """地理座標から8方位を丸める挙動を保証する。"""

    def test_eight_direction_rounding_uses_north_as_positive_y(self) -> None:
        """y 正方向を北として、北・北東・東の方角を本文に出す。"""
        service = DistantViewService(max_lines=3)
        result = service.render(
            current_spot_id=1,
            spots=(
                _spot(1, area_id="base", x=0.0, y=0.0),
                _spot(2, area_id="north", x=0.0, y=4.0),
                _spot(3, area_id="northeast", x=4.0, y=4.0),
                _spot(4, area_id="east", x=4.0, y=0.0),
            ),
            areas=(
                _area("base", "拠点", prominence=0.0, x=0.0, y=0.0),
                _area("north", "北の山", prominence=0.9, x=0.0, y=4.0),
                _area("northeast", "北東の森", prominence=0.8, x=4.0, y=4.0),
                _area("east", "東の沼", prominence=0.7, x=4.0, y=0.0),
            ),
            connections=(),
        )

        assert result.lines == (
            "北に北の山が見える。",
            "北東に北東の森が見える。",
            "東に東の沼が見える。",
        )
