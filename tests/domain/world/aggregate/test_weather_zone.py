import pytest
from ai_rpg_world.domain.world.aggregate.weather_zone import WeatherZone
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.domain.world.value_object.weather_zone_name import WeatherZoneName
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.event.weather_events import WeatherChangedEvent
from ai_rpg_world.domain.world.exception.weather_exception import (
    WeatherIntensityValidationException,
    WeatherZoneIdValidationException,
    WeatherZoneNameValidationException,
    WeatherZoneSpotNotFoundException
)


class TestWeatherZone:
    """WeatherZone集約の包括的なテストスイート"""

    def test_create_weather_zone_success(self):
        """正常なWeatherZoneの作成テスト"""
        zone_id = WeatherZoneId(1)
        name = WeatherZoneName("Test Zone")
        spot_ids = {SpotId(1), SpotId(2)}
        initial_state = WeatherState.clear()
        
        zone = WeatherZone.create(zone_id, name, spot_ids, initial_state)
        
        assert zone.zone_id == zone_id
        assert zone.name == name
        assert zone.spot_ids == spot_ids
        assert zone.current_state == initial_state

    def test_validation_empty_id(self):
        """空のIDに対するバリデーションテスト"""
        with pytest.raises(WeatherZoneIdValidationException):
            WeatherZoneId(0)
        with pytest.raises(WeatherZoneIdValidationException):
            WeatherZoneId(-1)

    def test_validation_empty_name(self):
        """空の名前に対するバリデーションテスト"""
        with pytest.raises(WeatherZoneNameValidationException):
            WeatherZoneName("")
        with pytest.raises(WeatherZoneNameValidationException):
            WeatherZoneName("  ")

    def test_validation_invalid_intensity(self):
        """不正な天候強度に対するバリデーションテスト"""
        with pytest.raises(WeatherIntensityValidationException):
            WeatherState(WeatherTypeEnum.CLEAR, -0.1)
        with pytest.raises(WeatherIntensityValidationException):
            WeatherState(WeatherTypeEnum.CLEAR, 1.1)

    def test_change_weather_emits_event(self):
        """天候変更時のイベント発行テスト"""
        zone_id = WeatherZoneId(1)
        name = WeatherZoneName("Test Zone")
        zone = WeatherZone(zone_id, name, {SpotId(1)}, WeatherState.clear())
        zone.clear_events()
        
        new_state = WeatherState(WeatherTypeEnum.CLOUDY, 0.5)
        zone.change_weather(new_state)
        
        assert zone.current_state == new_state
        
        events = zone.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, WeatherChangedEvent)
        assert event.old_weather == WeatherTypeEnum.CLEAR
        assert event.new_weather == WeatherTypeEnum.CLOUDY
        assert event.intensity == 0.5

    def test_change_weather_no_change(self):
        """同じ天候への変更時にイベントが発行されないことのテスト"""
        zone = WeatherZone(WeatherZoneId(1), WeatherZoneName("Z"), {SpotId(1)}, WeatherState.clear())
        zone.clear_events()
        
        zone.change_weather(WeatherState.clear())
        
        assert len(zone.get_events()) == 0

    def test_spot_management(self):
        """スポット管理機能のテスト"""
        zone = WeatherZone(WeatherZoneId(1), WeatherZoneName("Z"), {SpotId(1)}, WeatherState.clear())
        
        assert zone.contains_spot(SpotId(1))
        assert not zone.contains_spot(SpotId(2))
        
        zone.add_spot(SpotId(2))
        assert zone.contains_spot(SpotId(2))
        
        zone.remove_spot(SpotId(1))
        assert not zone.contains_spot(SpotId(1))
        
        # 存在しないスポットの削除で例外が投げられること
        with pytest.raises(WeatherZoneSpotNotFoundException):
            zone.remove_spot(SpotId(999))

    def test_spot_ids_immutability(self):
        """spot_idsの不変性テスト"""
        spot_ids = {SpotId(1)}
        zone = WeatherZone(WeatherZoneId(1), WeatherZoneName("Z"), spot_ids, WeatherState.clear())
        
        # 内部セットがコピーされていることを確認
        zone.spot_ids.add(SpotId(2))
        assert not zone.contains_spot(SpotId(2))
        
        # 元のセットを変更しても影響を受けないことを確認
        spot_ids.add(SpotId(3))
        assert not zone.contains_spot(SpotId(3))
