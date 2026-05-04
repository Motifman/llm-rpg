"""受動想起用 place ファミリー・object 粒度重みの純関数テスト（定数契約固定）。"""

from ai_rpg_world.application.llm.passive_recall_cue_families import (
    OBJECT_VALUE_PREFIX_WEIGHTS,
    PLACE_FAMILY_AXES,
    PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY,
    PASSIVE_RECALL_PLACE_FAMILY_LABEL,
    passive_recall_cue_bucket_key,
    passive_recall_object_value_granularity_weight,
    passive_recall_place_axis_granularity_weight,
)


class TestPassiveRecallCueFamiliesPlaces:
    """場所論理ファミリーと粒度重み"""

    def test_place_family_axes_fixed(self) -> None:
        """spot_graph の主要ロケーション軸がファミリーに含まれる。"""
        assert {"place_spot", "sub_loc", "tile_area"} == PLACE_FAMILY_AXES

    def test_bucket_key_groups_place_axes(self) -> None:
        """場所関連軸は同一バケツキーへ束ねられる。"""
        assert passive_recall_cue_bucket_key("place_spot") == PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY
        assert passive_recall_cue_bucket_key("sub_loc") == PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY
        assert passive_recall_cue_bucket_key("tile_area") == PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY

    def test_bucket_key_non_place_is_identity(self) -> None:
        """場所以外は axis そのものが論理バケツ。"""
        assert passive_recall_cue_bucket_key("object") == "object"

    def test_place_granularity_spot_strongest(self) -> None:
        """同一ファミリー内で place_spot が最も高い重みになる。"""
        assert passive_recall_place_axis_granularity_weight("place_spot") > passive_recall_place_axis_granularity_weight(
            "sub_loc"
        )
        assert passive_recall_place_axis_granularity_weight("sub_loc") > passive_recall_place_axis_granularity_weight(
            "tile_area"
        )

    def test_place_family_rr_label_stable(self) -> None:
        """ラウンドロビン側の論理軸ラベル（デバッグ row 名）。"""
        assert PASSIVE_RECALL_PLACE_FAMILY_LABEL == "cue:place_family"


class TestPassiveRecallCueFamiliesObjects:
    """object 値プレフィックスの相対強度"""

    def test_known_prefix_tuple_nonempty(self) -> None:
        """prefix リストが空にならない（契約として固定）。"""
        assert OBJECT_VALUE_PREFIX_WEIGHTS

    def test_object_world_item_and_chest_distinct_weights(self) -> None:
        """主要プレフィックスで区別できる（細かさの順序は定数として固定）。"""
        wi = passive_recall_object_value_granularity_weight("world_object_7")
        ii = passive_recall_object_value_granularity_weight("item_instance_9")
        ch = passive_recall_object_value_granularity_weight("chest_world_object_3")
        assert len({wi, ii, ch}) == 3

    def test_object_unknown_prefix_defaults(self) -> None:
        """既知プレフィックス外は既定重みへ落ちる。"""
        u = passive_recall_object_value_granularity_weight("legacy_blob_1")
        k = passive_recall_object_value_granularity_weight("world_object_1")
        assert u != k

