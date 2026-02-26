"""EventHandlerProfile のテスト（正常・境界・値の一意性）"""

import pytest

from ai_rpg_world.infrastructure.events.event_handler_profile import EventHandlerProfile


class TestEventHandlerProfile:
    """EventHandlerProfile のテスト"""

    def test_movement_only_value(self):
        """MOVEMENT_ONLY の値が文字列として期待どおり"""
        assert EventHandlerProfile.MOVEMENT_ONLY == "movement_only"
        assert EventHandlerProfile.MOVEMENT_ONLY.value == "movement_only"

    def test_movement_combat_value(self):
        """MOVEMENT_COMBAT の値が文字列として期待どおり"""
        assert EventHandlerProfile.MOVEMENT_COMBAT.value == "movement_combat"

    def test_full_value(self):
        """FULL の値が文字列として期待どおり"""
        assert EventHandlerProfile.FULL.value == "full"

    def test_all_profiles_are_unique(self):
        """全プロファイルの value が一意"""
        values = [p.value for p in EventHandlerProfile]
        assert len(values) == len(set(values))

    def test_profile_count(self):
        """プロファイルは3種類定義されている"""
        assert len(EventHandlerProfile) == 3

    def test_can_compare_by_string(self):
        """str Enum のため文字列と比較可能（既存コードとの互換）"""
        profile = EventHandlerProfile.MOVEMENT_ONLY
        assert profile == "movement_only"
