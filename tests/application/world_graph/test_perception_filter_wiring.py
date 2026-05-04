"""知覚フィルタのワイヤリングが正しく接続されていることを検証するテスト。

SpotGraphCurrentStateBuilder に light_source_item_spec_ids と
owned_item_spec_ids_provider を渡した場合に、光源判定が機能することを確認する。
"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

from unittest.mock import MagicMock


def _create_builder(
    *,
    light_source_ids: frozenset[ItemSpecId] = frozenset(),
    owned_provider=None,
) -> SpotGraphCurrentStateBuilder:
    return SpotGraphCurrentStateBuilder(
        spot_graph_repository=MagicMock(),
        spot_interior_repository=MagicMock(),
        player_status_repository=MagicMock(),
        light_source_item_spec_ids=light_source_ids,
        owned_item_spec_ids_provider=owned_provider,
    )


class TestEntityHasLightSource:
    """_entity_has_light_source の光源判定テスト"""

    def test_no_light_source_ids_returns_false(self):
        """light_source_item_spec_ids が空なら常に False"""
        builder = _create_builder()
        assert builder._entity_has_light_source(1) is False

    def test_no_provider_returns_false(self):
        """owned_item_spec_ids_provider が None なら常に False"""
        torch = ItemSpecId(100)
        builder = _create_builder(light_source_ids=frozenset({torch}))
        assert builder._entity_has_light_source(1) is False

    def test_entity_owns_light_source(self):
        """エンティティが光源アイテムを所持している場合は True"""
        torch = ItemSpecId(100)
        provider = lambda eid: frozenset({ItemSpecId(100), ItemSpecId(200)})
        builder = _create_builder(
            light_source_ids=frozenset({torch}),
            owned_provider=provider,
        )
        assert builder._entity_has_light_source(1) is True

    def test_entity_does_not_own_light_source(self):
        """エンティティが光源を持っていない場合は False"""
        torch = ItemSpecId(100)
        provider = lambda eid: frozenset({ItemSpecId(200), ItemSpecId(300)})
        builder = _create_builder(
            light_source_ids=frozenset({torch}),
            owned_provider=provider,
        )
        assert builder._entity_has_light_source(1) is False

    def test_multiple_light_sources_any_match(self):
        """複数の光源定義のうちひとつでも所持していれば True"""
        torch = ItemSpecId(100)
        lantern = ItemSpecId(101)
        provider = lambda eid: frozenset({ItemSpecId(101)})
        builder = _create_builder(
            light_source_ids=frozenset({torch, lantern}),
            owned_provider=provider,
        )
        assert builder._entity_has_light_source(1) is True
