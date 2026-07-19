"""inventory / ground_items 表記の ``""`` quote 化と、関連 tool description
への規約反映 (Y_after_pr_all_200tick 後続)。

Y_after_pr_all_200tick で観測された問題:
- ``spot_graph_use_item`` の失敗 6 件はすべて ``INVALID_TARGET_LABEL``
- inventory display は ``- 流木 x3 (素材・使用不可) (腐敗)`` のような
  装飾サフィックス付き。LLM がサフィックスごと item_label に含めて
  渡してしまうと resolver で hit しない

PR #639 で travel_to に導入した ``""`` 規約 (= ``""`` で囲まれた値が
tool に渡す値) を、所持アイテム / 地面アイテム / 関連 4 tool に拡張する。

### 変更点

1. **inventory 表示**: ``- "流木" x3 (素材・使用不可) (腐敗)`` のように
   item 名のみを ``""`` で囲む。x3 / 種別タグ / 腐敗 タグは囲まない
2. **ground_items 表示**: 同様に名前のみを ``""`` で囲む
3. **tool description**: use_item / drop_item / pickup_item / give_item /
   give_items の item_label / ground_item_label description で
   「``""`` 内の値をそのまま渡す」と明示

resolver の quote strip は PR #639 で導入済 → quote ごと渡されても OK。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    InventoryToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    DROP_ITEM_DEFINITION,
    GIVE_ITEM_DEFINITION,
    PICKUP_ITEM_DEFINITION,
    USE_ITEM_DEFINITION,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphGroundItemEntry,
    SpotGraphInventoryItemEntry,
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _make_dto(snap: SpotGraphPlayerSnapshotDto) -> PlayerCurrentStateDto:
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=snap.current_spot_id,
        current_spot_name=snap.current_spot_name,
        current_spot_description=snap.current_spot_description,
        x=None,
        y=None,
        z=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="晴れ",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=0,
        available_moves=None,
        total_available_moves=None,
        attention_level=AttentionLevel.FULL,
        spot_graph_snapshot=snap,
    )


def _snap_with_inventory() -> SpotGraphPlayerSnapshotDto:
    return SpotGraphPlayerSnapshotDto(
        current_spot_id=1,
        current_spot_name="拠点",
        current_spot_description="木陰",
        travel_status_line=None,
        inventory_items=(
            SpotGraphInventoryItemEntry(
                item_spec_id=100,
                item_instance_id=-1,
                slot_id=-1,
                name="流木",
                quantity=3,
                item_type="material",
                is_spoiled=False,
            ),
            SpotGraphInventoryItemEntry(
                item_spec_id=200,
                item_instance_id=-1,
                slot_id=-1,
                name="野いちご",
                quantity=2,
                item_type="consumable",
                is_spoiled=True,
            ),
        ),
        ground_items=(
            SpotGraphGroundItemEntry(
                item_instance_id=42,
                item_spec_id=101,
                name="石ころ",
                is_spoiled=False,
            ),
        ),
    )


class TestPromptQuotesInventoryItemName:
    """所持アイテム表示で item 名のみが ``""`` で囲まれる。"""

    def test_inventory_quotes_item_name(self) -> None:
        """inventory の item 名が クオートで囲まれる。"""
        result = SpotGraphUiContextBuilder().build(
            "現在地: 拠点", _make_dto(_snap_with_inventory())
        )
        text = result.current_state_text
        assert '"流木"' in text, "inventory item 名が \"\" で囲まれていない"
        assert '"野いちご"' in text

    def test_inventory(self) -> None:
        """``x3`` / ``(素材・使用不可)`` / ``(腐敗)`` は囲まない。
        ``""`` の有無で「渡すべき値」と「補足情報」を視覚的に区別する。"""
        result = SpotGraphUiContextBuilder().build(
            "現在地: 拠点", _make_dto(_snap_with_inventory())
        )
        text = result.current_state_text
        assert '"x3"' not in text
        assert '"(素材・使用不可)"' not in text
        assert '"(腐敗)"' not in text
        # 装飾そのものは表示されている (= 既存挙動を壊していない)
        assert "x3" in text
        assert "素材" in text
        assert "腐敗" in text


class TestPromptQuotesGroundItemName:
    """地面アイテム表示も同じ規約。"""

    def test_ground_item_name(self) -> None:
        """grounditem の名前がクオートで囲まれる。"""
        result = SpotGraphUiContextBuilder().build(
            "現在地: 拠点", _make_dto(_snap_with_inventory())
        )
        text = result.current_state_text
        assert '"石ころ"' in text, "ground item 名が \"\" で囲まれていない"


class TestUseItemDescriptionExplainsQuoteConvention:
    """use_item / drop_item / pickup_item / give_item / give_items の
    item_label description が ``""`` 規約を伝える。"""

    def _item_label_desc(self, defn) -> str:
        return defn.parameters["properties"]["item_label"]["description"]

    def test_use_item_label_included(self) -> None:
        """useitem の itemlabel にクオート規約が含まれる。"""
        desc = self._item_label_desc(USE_ITEM_DEFINITION)
        assert "\"" in desc
        assert (
            "囲ま" in desc or "クオート" in desc or "ダブルクォート" in desc
        ), "use_item の item_label に \"\" 規約が説明されていない"

    def test_drop_item_label_included(self) -> None:
        """dropitem の itemlabel にクオート規約が含まれる。"""
        desc = self._item_label_desc(DROP_ITEM_DEFINITION)
        assert "\"" in desc
        assert "囲ま" in desc or "クオート" in desc or "ダブルクォート" in desc

    # PR-α (Y_after_pr639_640 後続): give_item は top-level item_label を
    # 持たなくなった (gives 配列常時)。「give_item の item_label 規約」は
    # gives entry の item_label description 側でカバーされる
    # (test_give_item_の_gives_entry_の_item_label_にも_クオート規約が含まれる)。

    def test_pickup_item_ground_item_label_included(self) -> None:
        """pickupitem の grounditemlabel にクオート規約が含まれる。"""
        desc = PICKUP_ITEM_DEFINITION.parameters["properties"]["ground_item_label"][
            "description"
        ]
        assert "\"" in desc
        assert "囲ま" in desc or "クオート" in desc or "ダブルクォート" in desc

    def test_give_item_gives_entry_item_label_included(self) -> None:
        """PR-α (Y_after_pr639_640 後続): give_item は batch-always
        (gives: [...]) に統合された。gives 配列内の item_label description
        にも quote 規約が伝達される。"""
        item_label_desc = GIVE_ITEM_DEFINITION.parameters["properties"]["gives"][
            "items"
        ]["properties"]["item_label"]["description"]
        assert "\"" in item_label_desc
        assert (
            "囲ま" in item_label_desc
            or "クオート" in item_label_desc
            or "ダブルクォート" in item_label_desc
        )

    def test_drop_pickup_descriptions_hide_internal_terms(self) -> None:
        """drop/pickup の LLM 向け説明文には内部用語や不自然な対象名を出さない。"""
        descriptions = [
            DROP_ITEM_DEFINITION.description,
            DROP_ITEM_DEFINITION.parameters["properties"]["item_label"]["description"],
            DROP_ITEM_DEFINITION.parameters["properties"]["stealth"]["description"],
            PICKUP_ITEM_DEFINITION.description,
            PICKUP_ITEM_DEFINITION.parameters["properties"]["ground_item_label"][
                "description"
            ],
            PICKUP_ITEM_DEFINITION.parameters["properties"]["stealth"]["description"],
        ]
        forbidden = (
            "地面アイテム",
            "spec",
            "instance",
            "ordinal",
            "witness_policy",
            "ACTOR_ONLY",
        )
        for desc in descriptions:
            assert not any(term in desc for term in forbidden), desc


class TestDescriptionsAreStatic:
    """全 description が静的文字列 (prefix cache 安全)。"""

    @pytest.mark.parametrize(
        "defn,prop",
        [
            (USE_ITEM_DEFINITION, "item_label"),
            (DROP_ITEM_DEFINITION, "item_label"),
            # PR-α: GIVE_ITEM は gives 配列常時になったため top-level に
            # item_label は無い。gives 配列内の item_label description は
            # 別テストで static 性を確認する必要は薄い (親 description が
            # static なら子も追随する構造)
            (PICKUP_ITEM_DEFINITION, "ground_item_label"),
        ],
    )
    def test_description_is_static_string_without_placeholders(self, defn, prop) -> None:
        """description は str 型で placeholder なし。"""
        desc = defn.parameters["properties"][prop]["description"]
        assert isinstance(desc, str)
        assert "{" not in desc
