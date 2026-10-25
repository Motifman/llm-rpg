"""現在状態の部品変換とSNS・取引の入力正規化を保証する。"""

from ai_rpg_world.application.world.contracts.dtos import (
    AvailableTradeSummaryDto,
    PlayerAppSessionStateDto,
    PlayerCurrentStateDto,
    PlayerRuntimeContextDto,
    PlayerWorldStateDto,
)


def _make_current_state(**overrides) -> PlayerCurrentStateDto:
    params = {
        "player_id": 1,
        "player_name": "Hero",
        "current_spot_id": 10,
    }
    params.update(overrides)
    return PlayerCurrentStateDto(**params)


class TestPlayerCurrentStateSubDtos:
    """場所・補助情報・ゲーム内アプリの状態を部品へ変換して保持する。"""

    def test_world_state_groups_world_owned_fields(self):
        """現在状態から世界の部品を取り出すと、本人・ギルド用の場所・エリア・時刻が保たれる。"""
        dto = _make_current_state(
            area_ids=[1, 2],
            current_game_time_label="Day 1 08:00",
        )

        world = dto.world_state

        assert world.player_id == 1
        assert world.current_spot_id == 10
        assert world.area_ids == [1, 2]
        assert world.current_game_time_label == "Day 1 08:00"

    def test_runtime_context_groups_tool_facing_lists(self):
        """補助情報の部品を取り出すと、参加可能な取引と所持品の一覧が保たれる。"""
        trade = AvailableTradeSummaryDto(trade_id=5, item_name="Iron Sword", requested_gold=120)
        dto = _make_current_state(
            inventory_items=[],
            available_trades=[trade],
            guild_memberships=[],
            nearby_shops=[],
        )

        runtime = dto.runtime_context

        assert runtime.available_trades == [trade]
        assert runtime.inventory_items == []

    def test_app_session_state_normalizes_legacy_mode_flags(self):
        """SNSの旧真偽値だけを指定しても、アプリ状態はSNS起動中に正規化される。"""
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
        """取引の旧真偽値を後から変更すると、部品の取得時にも取引起動中へ正規化される。"""
        dto = _make_current_state(active_game_app="trade")

        dto.active_game_app = "none"
        dto.is_trade_mode_active = True
        dto.is_sns_mode_active = False

        app = dto.app_session_state

        assert app.active_game_app == "trade"
        assert app.is_trade_mode_active is True
        assert app.is_sns_mode_active is False

    def test_player_app_session_state_normalizes_direct_instances(self):
        """アプリ部品を直接構築した場合も、取引の旧真偽値から起動状態を補う。"""
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
        """部品から現在状態を組み立てると、SNSの旧真偽値から補った起動状態を保つ。"""
        world = PlayerWorldStateDto(
            player_id=1,
            player_name="Hero",
            current_spot_id=10,
            area_ids=[1, 2],
            current_game_time_label="Day 1 08:00",
        )
        trade = AvailableTradeSummaryDto(5, "剣", 120)
        runtime = PlayerRuntimeContextDto(available_trades=[trade])
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

    def test_from_components_preserves_world_and_runtime_context(self):
        """部品から現在状態を組み立てて取り出すと、場所・エリア・時刻・取引情報が元の値と一致する。"""
        world = PlayerWorldStateDto(1, "本人", 10, [1, 2], "Day 1 08:00")
        runtime = PlayerRuntimeContextDto(
            available_trades=[AvailableTradeSummaryDto(5, "剣", 120)]
        )

        dto = PlayerCurrentStateDto.from_components(
            world_state=world,
            runtime_context=runtime,
            app_session_state=PlayerAppSessionStateDto(),
        )

        assert dto.world_state == world
        assert dto.runtime_context == runtime

    def test_player_app_session_state_rejects_conflicting_flags(self):
        """アプリ未指定でSNSと取引の旧真偽値を両方有効にするとValueErrorを投げる。"""
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
