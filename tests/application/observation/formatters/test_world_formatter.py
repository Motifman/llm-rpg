"""WorldObservationFormatter の単体テスト。"""

from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.world_formatter import (
    WorldObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier
from ai_rpg_world.domain.skill.event.skill_events import SkillEquippedEvent
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.event.map_events import (
    SpotWeatherChangedEvent,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState


def _make_context(
    player_profile_repository=None,
    item_spec_repository=None,
    item_repository=None,
) -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver(
        spot_repository=None,
        player_profile_repository=player_profile_repository,
        item_spec_repository=item_spec_repository,
        item_repository=item_repository,
        shop_repository=None,
        guild_repository=None,
        monster_repository=None,
        skill_spec_repository=None,
        sns_user_repository=None,
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=item_repository,
    )


class TestWorldObservationFormatterCreation:
    """WorldObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる（parent 不要）。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format(event, recipient_player_id) が呼び出し可能。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestWorldObservationFormatterResourceHarvested:
    """ResourceHarvestedEvent のフォーマットテスト"""


    """SpotWeatherChangedEvent のフォーマットテスト"""

    def test_includes_old_and_new_weather(self):
        """天気変化は old/new を prose に含む。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        event = SpotWeatherChangedEvent.create(
            aggregate_id=SpotId(1),
            aggregate_type="Spot",
            spot_id=SpotId(1),
            old_weather_state=WeatherState(WeatherTypeEnum.CLEAR),
            new_weather_state=WeatherState(WeatherTypeEnum.RAIN),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "CLEAR" in out.prose or "clear" in out.prose
        assert "RAIN" in out.prose or "rain" in out.prose
        assert out.structured.get("type") == "weather_changed"
        assert out.schedules_turn is True


class TestWorldObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    def test_returns_none_for_skill_event(self):
        """Skill イベントは None。"""
        ctx = _make_context()
        formatter = WorldObservationFormatter(ctx)
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None
