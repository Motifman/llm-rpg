"""
受動想起用: place ファミリー（複数論理軸の束ね）および object の value 粒度による純粋な重み付け。

永続化する EpisodicCue の軸／値／canonical は変更しない。検索クエリ側の並べ替え・ラウンドロビンのみに利用する。
"""

from __future__ import annotations

# spot_graph 前提。tile 単位での場所ゆれへのチューニングは別フェーズ。
# （将来タイル単位移動で頻繁に変わる局面では、ファミリー内重み見直しまたは安定キー検討。）

PASSIVE_RECALL_PLACE_FAMILY_LABEL = "cue:place_family"

PLACE_FAMILY_AXES: frozenset[str] = frozenset({"place_spot", "sub_loc", "tile_area"})

PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY = "__passive_place_family__"


def passive_recall_place_axis_granularity_weight(axis: str) -> float:
    """
    place ファミリー内で「より細かい一致」を高い重みとする。
    place_spot > sub_loc > tile_area、ファミリー外は中立（1.0）。
    """
    if axis == "place_spot":
        return 3.0
    if axis == "sub_loc":
        return 2.0
    if axis == "tile_area":
        return 1.0
    return 1.0


OBJECT_VALUE_PREFIX_WEIGHTS: tuple[tuple[str, float], ...] = (
    # longest-match 優先のため冗長でも長いプレフィックスを先に並べる
    ("chest_world_object_", 4.0),
    ("world_object_", 3.0),
    ("item_instance_", 5.0),
)


def passive_recall_object_value_granularity_weight(value: str) -> float:
    """
    object 軸の value（例: world_object_7）の種類により相対強度を返す。
    プレフィックス非一致は既定 2.5（canonical だけ一致する異形や将来接頭辞）。
    """
    default = 2.5
    if not isinstance(value, str) or not value:
        return default
    for prefix, w in OBJECT_VALUE_PREFIX_WEIGHTS:
        if value.startswith(prefix):
            return float(w)
    return default


def passive_recall_cue_bucket_key(axis: str) -> str:
    """一覧取得・ソースラベル束ね用の論理バケツ。場所ファミリーは単一バケツ。"""
    if axis in PLACE_FAMILY_AXES:
        return PASSIVE_RECALL_PLACE_FAMILY_BUCKET_KEY
    return axis
