"""MonsterObservationFormatter の単体テスト。"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.monster_formatter import (
    MonsterObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.monster.event.monster_events import (
    ActorStateChangedEvent,
    BehaviorStuckEvent,
    MonsterCreatedEvent,
    MonsterDamagedEvent,
    MonsterDecidedToInteractEvent,
    MonsterDecidedToMoveEvent,
    MonsterDecidedToUseSkillEvent,
    MonsterDiedEvent,
    MonsterEvadedEvent,
    MonsterFedEvent,
    MonsterHealedEvent,
    MonsterMpRecoveredEvent,
    MonsterRespawnedEvent,
    MonsterSpawnedEvent,
    TargetLostEvent,
    TargetSpottedEvent,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.guild.event.guild_event import GuildCreatedEvent
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId


def _make_context() -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver(
        spot_repository=None,
        player_profile_repository=None,
        item_spec_repository=None,
        item_repository=None,
        shop_repository=None,
        guild_repository=None,
        monster_repository=None,
        skill_spec_repository=None,
        sns_user_repository=None,
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
    )


class TestMonsterObservationFormatterCreation:
    """MonsterObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる（parent 不要）。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format(event, recipient_player_id) が呼び出し可能。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestMonsterObservationFormatterMonsterCreated:
    """MonsterCreatedEvent のフォーマットテスト（観測対象外）"""

    def test_returns_none(self):
        """MonsterCreated は観測対象外で None。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterCreatedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            template_id=1,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestMonsterObservationFormatterMonsterSpawned:
    """MonsterSpawnedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return MonsterObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """モンスター出現は prose と structured を返す。"""
        event = MonsterSpawnedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            coordinate={"x": 0, "y": 0, "z": 0},
            spot_id=SpotId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert isinstance(out, ObservationOutput)
        assert "現れ" in out.prose
        assert out.structured.get("type") == "monster_spawned"
        assert out.structured.get("monster_id_value") == 1
        assert out.structured.get("spot_id_value") == 1
        assert out.observation_category == "environment"
        assert out.schedules_turn is True


class TestMonsterObservationFormatterMonsterRespawned:
    """MonsterRespawnedEvent のフォーマットテスト"""

    def test_returns_prose_and_structured(self):
        """モンスター再出現は prose を返す。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterRespawnedEvent.create(
            aggregate_id=MonsterId(2),
            aggregate_type="MonsterAggregate",
            coordinate={"x": 1, "y": 0, "z": 0},
            spot_id=SpotId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "再出現" in out.prose
        assert out.structured.get("type") == "monster_respawned"
        assert out.observation_category == "environment"


class TestMonsterObservationFormatterMonsterDamaged:
    """MonsterDamagedEvent のフォーマットテスト"""

    def test_includes_damage_and_current_hp(self):
        """ダメージは damage と current_hp を prose に含む。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterDamagedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            damage=25,
            current_hp=75,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "25ダメージ" in out.prose
        assert out.structured.get("type") == "monster_damaged"
        assert out.structured.get("damage") == 25
        assert out.structured.get("current_hp") == 75


class TestMonsterObservationFormatterMonsterDied:
    """MonsterDiedEvent のフォーマットテスト"""

    def test_returns_generic_prose_when_not_killer(self):
        """倒した本人でない場合「モンスターが倒れました。」"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=50,
            gold=10,
            killer_player_id=PlayerId(2),
            spot_id=SpotId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "モンスターが倒れました" in out.prose
        assert "倒しました" not in out.prose
        assert out.structured.get("type") == "monster_died"
        assert out.structured.get("gold") == 10
        assert out.structured.get("exp") == 50
        assert out.schedules_turn is True

    def test_returns_killer_prose_when_recipient_is_killer(self):
        """倒した本人には報酬付きの prose。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=50,
            gold=10,
            killer_player_id=PlayerId(1),
            spot_id=SpotId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "倒しました" in out.prose
        assert "ゴールド" in out.prose
        assert "EXP" in out.prose

    def test_handles_missing_spot_id(self):
        """spot_id が None でも structured に含める。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=0,
            gold=0,
            spot_id=None,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured.get("spot_id_value") is None


class TestMonsterObservationFormatterMonsterEvaded:
    """MonsterEvadedEvent のフォーマットテスト"""

    def test_returns_evaded_prose(self):
        """回避は prose を返す。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterEvadedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            coordinate={"x": 0, "y": 0, "z": 0},
            current_hp=100,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "回避" in out.prose
        assert out.structured.get("type") == "monster_evaded"


class TestMonsterObservationFormatterMonsterHealed:
    """MonsterHealedEvent のフォーマットテスト"""

    def test_includes_amount_and_current_hp(self):
        """回復は amount と current_hp を prose に含む。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterHealedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            amount=20,
            current_hp=80,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "+20" in out.prose
        assert out.structured.get("type") == "monster_healed"
        assert out.structured.get("amount") == 20
        assert out.structured.get("current_hp") == 80


class TestMonsterObservationFormatterMonsterMpRecovered:
    """MonsterMpRecoveredEvent のフォーマットテスト（観測対象外）"""

    def test_returns_none(self):
        """MP回復は観測対象外で None。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterMpRecoveredEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            amount=5,
            current_mp=15,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestMonsterObservationFormatterMonsterDecidedToMove:
    """MonsterDecidedToMoveEvent のフォーマットテスト（観測対象外）"""

    def test_returns_none(self):
        """移動決定は観測対象外で None。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterDecidedToMoveEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            actor_id=WorldObjectId(1),
            coordinate={"x": 0, "y": 0, "z": 0},
            spot_id=SpotId(1),
            current_tick=WorldTick(10),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestMonsterObservationFormatterMonsterFed:
    """MonsterFedEvent のフォーマットテスト"""

    def test_returns_fed_prose(self):
        """採食は prose を返す。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterFedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="MonsterFeed",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_coordinate=Coordinate(0, 0, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "採食" in out.prose
        assert out.structured.get("type") == "monster_fed"
        assert out.observation_category == "environment"


class TestMonsterObservationFormatterActorStateChanged:
    """ActorStateChangedEvent のフォーマットテスト"""

    def test_includes_old_and_new_state(self):
        """状態変化は old/new state を prose に含む。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = ActorStateChangedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="MonsterBehavior",
            actor_id=WorldObjectId(1),
            old_state=BehaviorStateEnum.IDLE,
            new_state=BehaviorStateEnum.PATROL,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "状態" in out.prose
        assert "IDLE" in out.prose
        assert "PATROL" in out.prose
        assert out.structured.get("type") == "monster_state_changed"
        assert out.structured.get("old") == "IDLE"
        assert out.structured.get("new") == "PATROL"


class TestMonsterObservationFormatterTargetSpotted:
    """TargetSpottedEvent のフォーマットテスト（観測対象外）"""

    def test_returns_none(self):
        """ターゲット視認は観測対象外で None。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = TargetSpottedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="MonsterBehavior",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            coordinate=Coordinate(0, 0, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestMonsterObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    @pytest.fixture
    def formatter(self):
        return MonsterObservationFormatter(_make_context())

    def test_returns_none_for_unknown_event(self, formatter):
        """対象外イベントは None。"""

        class UnknownEvent:
            pass

        out = formatter.format(UnknownEvent(), PlayerId(1))
        assert out is None

    def test_returns_none_for_guild_event(self, formatter):
        """Guild イベントは None。"""
        event = GuildCreatedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            name="紅蓮",
            description="guild",
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            creator_player_id=PlayerId(1),
            creator_role=GuildRole.LEADER,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestMonsterObservationFormatterRecipientIndependence:
    """recipient_player_id への依存テスト"""

    def test_monster_spawned_output_does_not_depend_on_recipient(self):
        """MonsterSpawned は recipient に依存しない。"""
        ctx = _make_context()
        formatter = MonsterObservationFormatter(ctx)
        event = MonsterSpawnedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            coordinate={"x": 0, "y": 0, "z": 0},
            spot_id=SpotId(1),
        )
        out1 = formatter.format(event, PlayerId(1))
        out2 = formatter.format(event, PlayerId(999))
        assert out1 is not None
        assert out2 is not None
        assert out1.prose == out2.prose
        assert out1.structured == out2.structured
