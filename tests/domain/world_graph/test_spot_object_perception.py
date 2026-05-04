"""SpotObject の知覚関連機能のユニットテスト。

detail_read_by と requires_read バリアントの動作を検証する。
"""

from __future__ import annotations

from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.object_description_variant import (
    ObjectDescriptionVariant,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _letter_object() -> SpotObject:
    """読む操作で内容が見えるようになる手紙オブジェクト"""
    return SpotObject(
        object_id=SpotObjectId.create(1),
        name="手紙",
        description="古びた手紙が置いてある。",
        object_type=SpotObjectTypeEnum.OTHER,
        state={},
        interactions=(),
        description_variants=(
            ObjectDescriptionVariant(
                description="手紙にはコード「4821」と書かれている。",
                requires_read=True,
            ),
        ),
    )


class TestDetailReadBy:
    """detail_read_by と requires_read バリアントのテスト"""

    def test_unread_shows_base_description(self) -> None:
        """読んでいないエージェントには基本説明のみ表示される"""
        letter = _letter_object()
        desc = letter.resolved_description(frozenset(), viewer_entity_id=1)
        assert desc == "古びた手紙が置いてある。"

    def test_read_shows_detailed_description(self) -> None:
        """読んだエージェントには詳細説明が表示される"""
        letter = _letter_object().with_detail_read(entity_id=1)
        desc = letter.resolved_description(frozenset(), viewer_entity_id=1)
        assert "4821" in desc

    def test_other_agent_still_sees_base(self) -> None:
        """Aが読んでもBには基本説明のみ表示される"""
        letter = _letter_object().with_detail_read(entity_id=1)
        desc = letter.resolved_description(frozenset(), viewer_entity_id=2)
        assert desc == "古びた手紙が置いてある。"

    def test_no_viewer_id_shows_base(self) -> None:
        """viewer_entity_id 未指定では基本説明"""
        letter = _letter_object().with_detail_read(entity_id=1)
        desc = letter.resolved_description(frozenset())
        assert desc == "古びた手紙が置いてある。"

    def test_with_detail_read_is_immutable(self) -> None:
        """with_detail_read は新しいオブジェクトを返す"""
        original = _letter_object()
        updated = original.with_detail_read(entity_id=1)
        assert 1 not in original.detail_read_by
        assert 1 in updated.detail_read_by

    def test_multiple_readers(self) -> None:
        """複数エージェントがそれぞれ読める"""
        letter = _letter_object().with_detail_read(1).with_detail_read(2)
        assert letter.resolved_description(frozenset(), viewer_entity_id=1) != "古びた手紙が置いてある。"
        assert letter.resolved_description(frozenset(), viewer_entity_id=2) != "古びた手紙が置いてある。"
        assert letter.resolved_description(frozenset(), viewer_entity_id=3) == "古びた手紙が置いてある。"


class TestRequiresReadWithStateCondition:
    """requires_read と state 条件の組み合わせテスト"""

    def test_requires_read_and_state_both_needed(self) -> None:
        """requires_read + required_state の両方を満たす必要がある"""
        obj = SpotObject(
            object_id=SpotObjectId.create(2),
            name="ロック付き日記",
            description="鍵のかかった日記がある。",
            object_type=SpotObjectTypeEnum.OTHER,
            state={"unlocked": True},
            interactions=(),
            description_variants=(
                ObjectDescriptionVariant(
                    description="日記には秘密のメモが書かれている。",
                    required_state={"unlocked": True},
                    requires_read=True,
                ),
            ),
        )
        # 読んでない → 基本説明
        assert obj.resolved_description(frozenset(), viewer_entity_id=1) == "鍵のかかった日記がある。"
        # 読んだ + state条件OK → 詳細
        read_obj = obj.with_detail_read(1)
        assert "秘密のメモ" in read_obj.resolved_description(frozenset(), viewer_entity_id=1)
