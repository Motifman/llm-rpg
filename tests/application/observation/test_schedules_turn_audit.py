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

    def test_自分の_revived_は_schedules_turn_True(self) -> None:
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

    def test_inventory_overflow_は_schedules_turn_True(self) -> None:
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

    def test_monster_respawned_は_schedules_turn_True(self) -> None:
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

    def test_harvest_cancelled_は_schedules_turn_True(self) -> None:
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

    def test_harvest_completed_は_schedules_turn_True(self) -> None:
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


class TestWorldFormatterAudit:
    """``world_formatter`` audit 修正の回帰テスト。"""

    def test_自分の_location_entered_は_schedules_turn_True(self) -> None:
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
