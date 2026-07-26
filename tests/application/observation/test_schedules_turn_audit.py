"""``schedules_turn=True`` 網羅性 audit の回帰テスト (#404 後続)。

per-agent idle timer (#346 Step 3) の下では、event 駆動の起床経路が
網羅されていないと「重要な変化が起きても idle_timeout (既定 6 tick) 経過
まで気づかない」silent failure になる。audit で True に倒した経路が、
後の rename / refactor で False に戻る回帰を検知する。

audit 表 (#404 後続):

| event | schedules_turn | 理由 |
|---|---|---|
| PlayerRevivedEvent (self) | True | 行動再開した瞬間 |
| InventorySlotOverflowEvent | True | アイテム消失リスク (致命) |
| MonsterRespawnedEvent | True | 敵が再出現 = spawned と同等 |
| HarvestCancelledEvent | True | 予約行動が失敗 |
| HarvestCompletedEvent | True | 採集完了で再び動ける |
| LocationEnteredEvent (self, 特殊 location) | True | summit / shore 等の到達 |
| PlayerDroppedItemEvent | True | 目の前に資材が現れた = 拾える |
| PlayerPickedUpItemEvent | True | 狙っていた資材が消えた = 計画変更 |
| PlayerGaveItemEvent | True | 受け手は所持品が増えた = 次の手が変わる |

アイテム移動 3 種は初回 audit から漏れていた (v4 第 3 回 run で発覚)。
`say_inline` を伴わない drop / give は同席者を起こさないため、相手が
idle_timeout まで気づかず、渡した資材が使われないまま停滞する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.player_formatter import (
    PlayerObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.monster_formatter import (
    MonsterObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.harvest_formatter import (
    HarvestObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.world_formatter import (
    WorldObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters._spot_graph_object_handler import (
    SpotGraphObjectHandler,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerDroppedItemEvent,
    PlayerGaveItemEvent,
    PlayerPickedUpItemEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.event.monster_events import MonsterRespawnedEvent
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.event.inventory_events import (
    InventorySlotOverflowEvent,
)
from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestCancelledEvent,
    HarvestCompletedEvent,
)
from ai_rpg_world.domain.world.event.map_events import LocationEnteredEvent
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def _context() -> ObservationFormatterContext:
    name_resolver = ObservationNameResolver()
    name_resolver.player_name = lambda pid: "テスト"
    name_resolver.item_instance_name = lambda iid: "テストアイテム"
    name_resolver.spot_name = lambda sid: "テスト地点"
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=MagicMock(find_by_id=MagicMock(return_value=None)),
    )


class TestPlayerFormatterAudit:
    """``player_formatter`` audit 修正の回帰テスト。"""

    def test_self_revived_schedules_turn_true(self) -> None:
        """復帰で行動再開できる状態 → 即起床。"""
        formatter = PlayerObservationFormatter(_context())
        event = PlayerRevivedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            hp_recovered=10,
            total_hp=100,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.schedules_turn is True

    def test_inventory_overflow_schedules_turn_true(self) -> None:
        """アイテム消失リスク → 即起床して捨てる / 装備し直す判断を促す。"""
        formatter = PlayerObservationFormatter(_context())
        event = InventorySlotOverflowEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            overflowed_item_instance_id=ItemInstanceId(100),
            reason="test",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.schedules_turn is True


class TestMonsterFormatterAudit:
    """``monster_formatter`` audit 修正の回帰テスト。"""

    def test_monster_respawned_schedules_turn_true(self) -> None:
        """spawned と同じく敵が居る状態への遷移 → 即起床。"""
        formatter = MonsterObservationFormatter(_context())
        event = MonsterRespawnedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            coordinate={"x": 0, "y": 0, "z": 0},
            spot_id=SpotId.create(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.schedules_turn is True


class TestHarvestFormatterAudit:
    """``harvest_formatter`` audit 修正の回帰テスト。"""

    def test_harvest_cancelled_schedules_turn_true(self) -> None:
        """予約行動失敗 → 別行動を選ばせる。"""
        formatter = HarvestObservationFormatter(_context())
        event = HarvestCancelledEvent.create(
            aggregate_id=WorldObjectId.create(1),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId.create(1),
            target_id=WorldObjectId.create(2),
            reason="resource_depleted",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.schedules_turn is True

    def test_harvest_completed_schedules_turn_true(self) -> None:
        """予約行動完了 → 次の行動を選ばせる。"""
        formatter = HarvestObservationFormatter(_context())
        event = HarvestCompletedEvent.create(
            aggregate_id=WorldObjectId.create(1),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId.create(1),
            target_id=WorldObjectId.create(2),
            loot_table_id=LootTableId.create(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.schedules_turn is True


class TestItemTransferAudit:
    """アイテム移動 3 種 (drop / pickup / give) の起床経路の回帰テスト。

    say_inline を伴わない受け渡しでも同席者が即座に気づけることを保証する。
    """

    def _handler(self) -> SpotGraphObjectHandler:
        return SpotGraphObjectHandler(_context())

    def test_item_dropped_schedules_turn_true(self) -> None:
        """同席者の目の前に資材が置かれた → 拾う判断をさせるため即起床。"""
        out = self._handler().format(
            PlayerDroppedItemEvent.create(
                aggregate_id=SpotGraphId.create(999),
                aggregate_type="SpotGraphAggregate",
                entity_id=EntityId.create(1),
                spot_id=SpotId(1),
                item_instance_id=ItemInstanceId.create(7),
                item_spec_id=ItemSpecId.create(100),
                item_name="流木",
            ),
            PlayerId(2),
        )
        assert out is not None
        assert out.schedules_turn is True

    def test_item_picked_up_schedules_turn_true(self) -> None:
        """狙っていた地面の資材が他人に拾われた → 計画変更のため即起床。"""
        out = self._handler().format(
            PlayerPickedUpItemEvent.create(
                aggregate_id=SpotGraphId.create(999),
                aggregate_type="SpotGraphAggregate",
                entity_id=EntityId.create(1),
                spot_id=SpotId(1),
                item_instance_id=ItemInstanceId.create(7),
                item_spec_id=ItemSpecId.create(100),
                item_name="流木",
            ),
            PlayerId(2),
        )
        assert out is not None
        assert out.schedules_turn is True

    def test_item_given_schedules_turn_true(self) -> None:
        """アイテムを渡された / 受け渡しを目撃した → 所持品が変わるため即起床。"""
        out = self._handler().format(
            PlayerGaveItemEvent.create(
                aggregate_id=SpotGraphId.create(999),
                aggregate_type="SpotGraphAggregate",
                entity_id=EntityId.create(1),
                recipient_entity_id=EntityId.create(2),
                spot_id=SpotId(1),
                item_instance_id=ItemInstanceId.create(7),
                item_spec_id=ItemSpecId.create(100),
                item_name="貝",
            ),
            PlayerId(2),
        )
        assert out is not None
        assert out.schedules_turn is True


class TestWorldFormatterAudit:
    """``world_formatter`` audit 修正の回帰テスト。"""

    def test_self_location_entered_schedules_turn_true(self) -> None:
        """summit / shore 等の特殊 location 到着 → 即起床。"""
        formatter = WorldObservationFormatter(_context())
        event = LocationEnteredEvent.create(
            aggregate_id=LocationAreaId(1),
            aggregate_type="LocationArea",
            location_id=LocationAreaId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId.create(1),
            name="頂上",
            description="島の頂",
            player_id_value=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.schedules_turn is True
