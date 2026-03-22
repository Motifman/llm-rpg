"""SNS モード: create_llm_agent_wiring → prompt_builder のツール一覧回帰テスト。

composition root が sns_mode_session / post_query_service / SNS command 系を渡したとき、
DefaultPromptBuilder.build が PlayerCurrentStateDto.is_sns_mode_active に応じた tools を返すことを固定する。

取引所ツールは別カタログとして同梱されうるが、SNS モード ON では取引ファミリーは非表示（相互排他）。
"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SNS_CREATE_POST,
    TOOL_NAME_SNS_ENTER,
    TOOL_NAME_SNS_LOGOUT,
    TOOL_NAME_SNS_VIEW_CURRENT_PAGE,
    TOOL_NAME_TRADE_ENTER,
    TOOL_NAME_TRADE_OFFER,
)
from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring
from ai_rpg_world.application.social.services.sns_mode_session_service import (
    SnsModeSessionService,
)
from ai_rpg_world.application.social.sns_virtual_pages import SnsPageSessionService
from ai_rpg_world.application.world.contracts.dtos import (
    AvailableMoveDto,
    AvailableTradeSummaryDto,
    InventoryItemDto,
    PlayerCurrentStateDto,
)
from ai_rpg_world.application.world.services.movement_service import (
    MovementApplicationService,
)
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.enum.player_enum import ControlType
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)


def _minimal_wiring_deps():
    uow_factory = MagicMock(spec=UnitOfWorkFactory)
    uow_factory.create.return_value = MagicMock()
    uow_factory.create.return_value.__enter__ = MagicMock(return_value=MagicMock())
    uow_factory.create.return_value.__exit__ = MagicMock(return_value=False)
    world_query = MagicMock(spec=WorldQueryService)
    world_query.get_player_current_state = MagicMock(return_value=None)
    movement = MagicMock(spec=MovementApplicationService)
    movement.move_to_destination = MagicMock()
    movement.cancel_movement = MagicMock()
    return {
        "player_status_repository": MagicMock(spec=PlayerStatusRepository),
        "physical_map_repository": MagicMock(spec=PhysicalMapRepository),
        "world_query_service": world_query,
        "movement_service": movement,
        "player_profile_repository": MagicMock(spec=PlayerProfileRepository),
        "unit_of_work_factory": uow_factory,
    }


def _player_current_state_for_sns_tools(
    *,
    is_sns_mode_active: bool,
    sns_virtual_page_kind: str | None = None,
    sns_current_page_snapshot_json: str | None = None,
) -> PlayerCurrentStateDto:
    moves = [
        AvailableMoveDto(
            spot_id=2,
            spot_name="B",
            road_id=1,
            road_description="",
            conditions_met=True,
            failed_conditions=[],
        )
    ]
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=1,
        current_spot_name="A",
        current_spot_description="",
        x=0,
        y=0,
        z=0,
        area_id=None,
        area_name=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="clear",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=5,
        available_moves=moves,
        total_available_moves=1,
        attention_level=AttentionLevel.FULL,
        is_sns_mode_active=is_sns_mode_active,
        sns_virtual_page_kind=sns_virtual_page_kind,
        sns_current_page_snapshot_json=sns_current_page_snapshot_json,
        inventory_items=[InventoryItemDto(1, 10, "剣", 1)],
        available_trades=[
            AvailableTradeSummaryDto(trade_id=1, item_name="盾", requested_gold=10)
        ],
    )


def _profile_repo_with_player_one() -> InMemoryPlayerProfileRepository:
    data_store = InMemoryDataStore()
    data_store.clear_all()
    repo = InMemoryPlayerProfileRepository(data_store, None)
    profile = PlayerProfileAggregate.create(
        PlayerId(1), PlayerName("WiringSns"), control_type=ControlType.LLM
    )
    repo.save(profile)
    return repo


@pytest.fixture
def sns_wiring_deps():
    deps = _minimal_wiring_deps()
    post_query = MagicMock()
    post_query.get_home_timeline = MagicMock(return_value=[])
    post_query.get_user_timeline = MagicMock(return_value=[])
    session = SnsModeSessionService()
    deps["post_service"] = MagicMock()
    deps["reply_service"] = MagicMock()
    deps["user_command_service"] = MagicMock()
    deps["notification_command_service"] = MagicMock()
    deps["trade_command_service"] = MagicMock()
    deps["sns_mode_session"] = session
    deps["post_query_service"] = post_query
    deps["player_profile_repository"] = _profile_repo_with_player_one()
    return deps


class TestSnsModeWiringPromptTools:
    """create_llm_agent_wiring 経由の PromptBuilder がモードに応じた tools を返す"""

    def test_prompt_tools_sns_mode_off_shows_only_sns_enter_from_sns_family(
        self, sns_wiring_deps
    ):
        world_query: MagicMock = sns_wiring_deps["world_query_service"]
        world_query.get_player_current_state.return_value = (
            _player_current_state_for_sns_tools(is_sns_mode_active=False)
        )
        result = create_llm_agent_wiring(**sns_wiring_deps)
        prompt_builder = result.llm_turn_trigger._turn_runner._orchestrator._prompt_builder
        built = prompt_builder.build(PlayerId(1))
        names = [
            t["function"]["name"]
            for t in built["tools"]
            if t.get("type") == "function"
        ]
        assert TOOL_NAME_SNS_ENTER in names
        assert TOOL_NAME_SNS_LOGOUT not in names
        assert TOOL_NAME_SNS_CREATE_POST not in names
        assert TOOL_NAME_TRADE_ENTER in names
        assert TOOL_NAME_TRADE_OFFER not in names
        assert "sns_home_timeline" not in names
        assert "sns_list_my_posts" not in names
        assert "sns_list_user_posts" not in names
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE not in names

    def test_prompt_tools_sns_mode_on_hides_trade_family_and_legacy_read_tools(
        self, sns_wiring_deps
    ):
        world_query: MagicMock = sns_wiring_deps["world_query_service"]
        world_query.get_player_current_state.return_value = (
            _player_current_state_for_sns_tools(is_sns_mode_active=True)
        )
        result = create_llm_agent_wiring(**sns_wiring_deps)
        prompt_builder = result.llm_turn_trigger._turn_runner._orchestrator._prompt_builder
        built = prompt_builder.build(PlayerId(1))
        names = [
            t["function"]["name"]
            for t in built["tools"]
            if t.get("type") == "function"
        ]
        assert TOOL_NAME_SNS_ENTER not in names
        assert TOOL_NAME_SNS_LOGOUT in names
        assert TOOL_NAME_SNS_CREATE_POST in names
        assert TOOL_NAME_TRADE_ENTER not in names
        assert TOOL_NAME_TRADE_OFFER not in names
        assert "sns_home_timeline" not in names
        assert "sns_list_my_posts" not in names
        assert "sns_list_user_posts" not in names
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE not in names

    def test_prompt_tools_sns_mode_on_with_virtual_pages_shows_view_current_page(
        self, sns_wiring_deps
    ):
        deps = dict(sns_wiring_deps)
        deps["sns_page_query_service"] = MagicMock()
        deps["sns_page_session"] = SnsPageSessionService()
        world_query: MagicMock = deps["world_query_service"]
        world_query.get_player_current_state.return_value = _player_current_state_for_sns_tools(
            is_sns_mode_active=True,
            sns_virtual_page_kind="home",
        )
        result = create_llm_agent_wiring(**deps)
        prompt_builder = result.llm_turn_trigger._turn_runner._orchestrator._prompt_builder
        built = prompt_builder.build(PlayerId(1))
        names = [
            t["function"]["name"]
            for t in built["tools"]
            if t.get("type") == "function"
        ]
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE in names

    def test_prompt_includes_current_virtual_page_snapshot_when_present(
        self, sns_wiring_deps
    ):
        deps = dict(sns_wiring_deps)
        deps["sns_page_query_service"] = MagicMock()
        deps["sns_page_session"] = SnsPageSessionService()
        world_query: MagicMock = deps["world_query_service"]
        world_query.get_player_current_state.return_value = _player_current_state_for_sns_tools(
            is_sns_mode_active=True,
            sns_virtual_page_kind="home",
            sns_current_page_snapshot_json='{"page_kind":"home","home":{"posts":[{"post_ref":"r_post_01"}]}}',
        )
        result = create_llm_agent_wiring(**deps)
        prompt_builder = result.llm_turn_trigger._turn_runner._orchestrator._prompt_builder
        built = prompt_builder.build(PlayerId(1))
        user_content = built["messages"][1]["content"]
        assert "現在のSNS画面:" in user_content
        assert '"page_kind":"home"' in user_content
        assert '"post_ref":"r_post_01"' in user_content

    def test_wiring_result_exposes_same_sns_mode_session_instance(self, sns_wiring_deps):
        session = sns_wiring_deps["sns_mode_session"]
        result = create_llm_agent_wiring(**sns_wiring_deps)
        assert result.sns_mode_session is session
