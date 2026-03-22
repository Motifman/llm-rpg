"""PlayerCurrentStateDto の phase 1 sub DTO 分割テスト。"""

from ai_rpg_world.application.world.contracts.dtos import (
    AvailableTradeSummaryDto,
    PlayerAppSessionStateDto,
    PlayerCurrentStateDto,
    PlayerRuntimeContextDto,
    PlayerWorldStateDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _make_current_state(**overrides) -> PlayerCurrentStateDto:
    params = {
        "player_id": 1,
        "player_name": "Hero",
        "current_spot_id": 10,
        "current_spot_name": "Town",
        "current_spot_description": "Peaceful town",
        "x": 1,
        "y": 2,
        "z": 0,
        "current_player_count": 0,
        "current_player_ids": set(),
        "connected_spot_ids": {11},
        "connected_spot_names": {"Field"},
        "weather_type": "clear",
        "weather_intensity": 0.2,
        "current_terrain_type": "grass",
        "visible_objects": [],
        "view_distance": 5,
        "available_moves": [],
        "total_available_moves": 0,
        "attention_level": AttentionLevel.FULL,
    }
    params.update(overrides)
    return PlayerCurrentStateDto(**params)


class TestPlayerCurrentStateSubDtos:
    def test_world_state_groups_world_owned_fields(self):
        dto = _make_current_state(
            area_ids=[1, 2],
            area_names=["Town", "Square"],
            area_id=1,
            area_name="Town",
            is_busy=True,
            busy_until_tick=42,
            has_active_path=True,
            current_game_time_label="Day 1 08:00",
        )

        world = dto.world_state

        assert world.player_id == 1
        assert world.current_spot_name == "Town"
        assert world.area_ids == [1, 2]
        assert world.is_busy is True
        assert world.busy_until_tick == 42
        assert world.has_active_path is True
        assert world.current_game_time_label == "Day 1 08:00"

    def test_runtime_context_groups_tool_facing_lists(self):
        trade = AvailableTradeSummaryDto(trade_id=5, item_name="Iron Sword", requested_gold=120)
        dto = _make_current_state(
            inventory_items=[],
            available_trades=[trade],
            guild_memberships=[],
            nearby_shops=[],
            can_destroy_placeable=True,
        )

        runtime = dto.runtime_context

        assert runtime.available_trades == [trade]
        assert runtime.can_destroy_placeable is True
        assert runtime.inventory_items == []

    def test_app_session_state_normalizes_legacy_mode_flags(self):
        dto = _make_current_state(
            active_game_app="none",
            is_sns_mode_active=True,
            sns_virtual_page_kind="home",
        )

        app = dto.app_session_state

        assert dto.active_game_app == "sns"
        assert dto.is_sns_mode_active is True
        assert dto.is_trade_mode_active is False
        assert app.active_game_app == "sns"
        assert app.is_sns_mode_active is True
        assert app.is_trade_mode_active is False
        assert app.sns_virtual_page_kind == "home"

    def test_app_session_state_recomputes_when_top_level_flags_change(self):
        dto = _make_current_state(active_game_app="trade")

        dto.active_game_app = "none"
        dto.is_trade_mode_active = True
        dto.is_sns_mode_active = False

        app = dto.app_session_state

        assert app.active_game_app == "trade"
        assert app.is_trade_mode_active is True
        assert app.is_sns_mode_active is False

    def test_player_app_session_state_normalizes_direct_instances(self):
        app = PlayerAppSessionStateDto(
            active_game_app="none",
            is_trade_mode_active=True,
            trade_virtual_page_kind="market",
        )

        assert app.active_game_app == "trade"
        assert app.is_trade_mode_active is True
        assert app.is_sns_mode_active is False
        assert app.trade_virtual_page_kind == "market"

    def test_from_components_normalizes_app_session_before_exposing_facade(self):
        world = PlayerWorldStateDto(
            player_id=1,
            player_name="Hero",
            current_spot_id=10,
            current_spot_name="Town",
            current_spot_description="Peaceful town",
            x=1,
            y=2,
            z=0,
            current_player_count=0,
            current_player_ids=set(),
            connected_spot_ids={11},
            connected_spot_names={"Field"},
            weather_type="clear",
            weather_intensity=0.2,
            current_terrain_type="grass",
            visible_objects=[],
            view_distance=5,
            available_moves=[],
            total_available_moves=0,
            attention_level=AttentionLevel.FULL,
        )
        runtime = PlayerRuntimeContextDto()
        app = PlayerAppSessionStateDto(
            active_game_app="none",
            is_sns_mode_active=True,
            sns_virtual_page_kind="home",
        )

        dto = PlayerCurrentStateDto.from_components(
            world_state=world,
            runtime_context=runtime,
            app_session_state=app,
        )

        assert dto.active_game_app == "sns"
        assert dto.is_sns_mode_active is True
        assert dto.is_trade_mode_active is False
        assert dto.app_session_state.active_game_app == "sns"

    def test_player_app_session_state_rejects_conflicting_flags(self):
        try:
            PlayerAppSessionStateDto(
                active_game_app="none",
                is_sns_mode_active=True,
                is_trade_mode_active=True,
            )
        except ValueError as exc:
            assert "cannot both be true" in str(exc)
        else:
            raise AssertionError("ValueError was not raised")
