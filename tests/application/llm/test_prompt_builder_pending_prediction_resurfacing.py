"""DefaultPromptBuilder の pending prediction 再浮上 (U10a) を検証する。

U10a (予測誤差統一設計 部品6・pending prediction): ``_build_pending_predictions_text``
が pending prediction store から解決 cue (spot / player) が現在の状況と一致し、
かつ tick 範囲が到来しているものだけを再浮上させ、【保留中の予測】section の
本体を返すことを保証する。cue 不一致・tick 範囲外は再浮上せず、cap 件数を
超えたものは切り捨てる。store 未配線 (flag OFF 相当) なら常に空文字。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.contracts.dtos import LlmUiContextDto, ToolRuntimeContextDto
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IAvailableToolsProvider,
    ICurrentStateFormatter,
    ILlmUiContextBuilder,
    IRecentEventsFormatter,
    ISlidingWindowMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.application.llm.services.in_memory_pending_prediction_store import (
    InMemoryPendingPredictionStore,
)
from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
from ai_rpg_world.application.llm.services.prompt_builder_config import (
    EpisodicRecallConfig,
    PromptBuilderCoreServices,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
)
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.enum.player_enum import ControlType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.world.value_object.world_id import DEFAULT_SINGLE_WORLD_ID
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)

_ACTING_PLAYER_ID = 1
_KAITO_PLAYER_ID = 2


def _pending(
    pending_id: str,
    *,
    resolution_cues: tuple[str, ...],
    tick_from: int,
    tick_to: int,
) -> PendingPrediction:
    return PendingPrediction(
        pending_id=pending_id,
        text=f"約束({pending_id})",
        resolution_cues=resolution_cues,
        tick_from=tick_from,
        tick_to=tick_to,
        origin_episode_id="ep-1",
        created_tick=0,
    )


def _profile_repo() -> InMemoryPlayerProfileRepository:
    data_store = InMemoryDataStore()
    data_store.clear_all()
    repo = InMemoryPlayerProfileRepository(data_store, None)
    repo.save(
        PlayerProfileAggregate.create(
            PlayerId(_ACTING_PLAYER_ID), PlayerName("Self"), control_type=ControlType.LLM
        )
    )
    repo.save(
        PlayerProfileAggregate.create(
            PlayerId(_KAITO_PLAYER_ID), PlayerName("カイト"), control_type=ControlType.LLM
        )
    )
    return repo


def _world_query_stub(state=None):
    w = object.__new__(WorldQueryService)
    w.get_player_current_state = MagicMock(return_value=state)
    return w


def _make_builder(
    *,
    pending_prediction_store,
    current_tick: int,
    current_state_dto,
    resurface_cap: int = 2,
):
    buffer = MagicMock(spec=IObservationContextBuffer)
    buffer.drain = MagicMock(return_value=[])
    sliding = MagicMock(spec=ISlidingWindowMemory)
    sliding.append_all = MagicMock(return_value=[])
    sliding.get_recent = MagicMock(return_value=[])
    actions = MagicMock(spec=IActionResultStore)
    actions.get_recent = MagicMock(return_value=[])
    world = _world_query_stub(state=current_state_dto)
    current_fmt = MagicMock(spec=ICurrentStateFormatter)
    current_fmt.format = MagicMock(return_value="fmt")
    recent_fmt = MagicMock(spec=IRecentEventsFormatter)
    recent_fmt.format = MagicMock(return_value="recent")
    sys_builder = MagicMock(spec=ISystemPromptBuilder)
    sys_builder.build = MagicMock(return_value="sys")
    tools_p = MagicMock(spec=IAvailableToolsProvider)
    tools_p.get_available_tools = MagicMock(return_value=[])
    ui_builder = MagicMock(spec=ILlmUiContextBuilder)
    ui_builder.build = MagicMock(
        return_value=LlmUiContextDto(
            current_state_text="ui",
            tool_runtime_context=ToolRuntimeContextDto.empty(),
        )
    )

    being_repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(being_repo)
    BeingProvisioningService(being_repo).ensure_attached(PlayerId(_ACTING_PLAYER_ID))

    return DefaultPromptBuilder(
        PromptBuilderCoreServices(
            observation_buffer=buffer,
            sliding_window_memory=sliding,
            action_result_store=actions,
            world_query_service=world,
            player_profile_repository=_profile_repo(),
            current_state_formatter=current_fmt,
            recent_events_formatter=recent_fmt,
            context_format_strategy=SectionBasedContextFormatStrategy(),
            system_prompt_builder=sys_builder,
            available_tools_provider=tools_p,
        ),
        episodic=EpisodicRecallConfig(
            pending_prediction_store=pending_prediction_store,
            pending_prediction_resurface_cap=resurface_cap,
        ),
        ui_context_builder=ui_builder,
        current_tick_provider=lambda: current_tick,
        being_attachment_resolver=resolver,
        default_world_id=DEFAULT_SINGLE_WORLD_ID,
    )


class TestPendingPredictionResurfacing:
    def test_store_unconfigured_returns_empty_and_section_omitted(self) -> None:
        """store 未配線 (flag OFF 相当) なら【保留中の予測】は出ない。"""
        builder = _make_builder(
            pending_prediction_store=None,
            current_tick=10,
            current_state_dto=None,
        )
        out = builder.build(PlayerId(_ACTING_PLAYER_ID))
        assert "【保留中の予測】" not in out["messages"][1]["content"]

    def test_spot_cue_match_within_tick_range_resurfaces(self) -> None:
        store = InMemoryPendingPredictionStore()
        current_state_dto = SimpleNamespace(current_spot_id=77, current_player_ids=set())
        builder = _make_builder(
            pending_prediction_store=store,
            current_tick=10,
            current_state_dto=current_state_dto,
        )
        being_id = builder._resolve_being_id(PlayerId(_ACTING_PLAYER_ID))
        assert being_id is not None
        store.add_by_being(
            being_id,
            _pending("p1", resolution_cues=("spot:77",), tick_from=5, tick_to=15),
        )

        text = builder._build_pending_predictions_text(
            player_id=PlayerId(_ACTING_PLAYER_ID),
            current_state_dto=current_state_dto,
        )
        assert "約束(p1)" in text

        out = builder.build(PlayerId(_ACTING_PLAYER_ID))
        assert "【保留中の予測】" in out["messages"][1]["content"]

    def test_spot_cue_mismatch_does_not_resurface(self) -> None:
        store = InMemoryPendingPredictionStore()
        current_state_dto = SimpleNamespace(current_spot_id=999, current_player_ids=set())
        builder = _make_builder(
            pending_prediction_store=store,
            current_tick=10,
            current_state_dto=current_state_dto,
        )
        being_id = builder._resolve_being_id(PlayerId(_ACTING_PLAYER_ID))
        store.add_by_being(
            being_id,
            _pending("p1", resolution_cues=("spot:77",), tick_from=5, tick_to=15),
        )
        text = builder._build_pending_predictions_text(
            player_id=PlayerId(_ACTING_PLAYER_ID),
            current_state_dto=current_state_dto,
        )
        assert text == ""

    def test_tick_out_of_range_does_not_resurface(self) -> None:
        store = InMemoryPendingPredictionStore()
        current_state_dto = SimpleNamespace(current_spot_id=77, current_player_ids=set())
        builder = _make_builder(
            pending_prediction_store=store,
            current_tick=100,
            current_state_dto=current_state_dto,
        )
        being_id = builder._resolve_being_id(PlayerId(_ACTING_PLAYER_ID))
        store.add_by_being(
            being_id,
            _pending("p1", resolution_cues=("spot:77",), tick_from=5, tick_to=15),
        )
        text = builder._build_pending_predictions_text(
            player_id=PlayerId(_ACTING_PLAYER_ID),
            current_state_dto=current_state_dto,
        )
        assert text == ""

    def test_player_cue_match_by_nearby_profile_name(self) -> None:
        store = InMemoryPendingPredictionStore()
        current_state_dto = SimpleNamespace(
            current_spot_id=1, current_player_ids={_KAITO_PLAYER_ID}
        )
        builder = _make_builder(
            pending_prediction_store=store,
            current_tick=5,
            current_state_dto=current_state_dto,
        )
        being_id = builder._resolve_being_id(PlayerId(_ACTING_PLAYER_ID))
        store.add_by_being(
            being_id,
            _pending("p1", resolution_cues=("player:カイト",), tick_from=0, tick_to=10),
        )
        text = builder._build_pending_predictions_text(
            player_id=PlayerId(_ACTING_PLAYER_ID),
            current_state_dto=current_state_dto,
        )
        assert "約束(p1)" in text

    def test_player_cue_without_nearby_match_does_not_resurface(self) -> None:
        store = InMemoryPendingPredictionStore()
        current_state_dto = SimpleNamespace(current_spot_id=1, current_player_ids=set())
        builder = _make_builder(
            pending_prediction_store=store,
            current_tick=5,
            current_state_dto=current_state_dto,
        )
        being_id = builder._resolve_being_id(PlayerId(_ACTING_PLAYER_ID))
        store.add_by_being(
            being_id,
            _pending("p1", resolution_cues=("player:カイト",), tick_from=0, tick_to=10),
        )
        text = builder._build_pending_predictions_text(
            player_id=PlayerId(_ACTING_PLAYER_ID),
            current_state_dto=current_state_dto,
        )
        assert text == ""

    def test_all_resolution_cues_must_match_and(self) -> None:
        """resolution_cues が複数ある場合、全件一致しないと再浮上しない (AND)。"""
        store = InMemoryPendingPredictionStore()
        current_state_dto = SimpleNamespace(current_spot_id=77, current_player_ids=set())
        builder = _make_builder(
            pending_prediction_store=store,
            current_tick=5,
            current_state_dto=current_state_dto,
        )
        being_id = builder._resolve_being_id(PlayerId(_ACTING_PLAYER_ID))
        store.add_by_being(
            being_id,
            _pending(
                "p1",
                resolution_cues=("spot:77", "player:カイト"),
                tick_from=0,
                tick_to=10,
            ),
        )
        # spot は一致するが player は同席していない
        text = builder._build_pending_predictions_text(
            player_id=PlayerId(_ACTING_PLAYER_ID),
            current_state_dto=current_state_dto,
        )
        assert text == ""

    def test_cap_limits_resurfaced_count(self) -> None:
        store = InMemoryPendingPredictionStore()
        current_state_dto = SimpleNamespace(current_spot_id=77, current_player_ids=set())
        builder = _make_builder(
            pending_prediction_store=store,
            current_tick=5,
            current_state_dto=current_state_dto,
            resurface_cap=2,
        )
        being_id = builder._resolve_being_id(PlayerId(_ACTING_PLAYER_ID))
        for i in range(4):
            store.add_by_being(
                being_id,
                _pending(
                    f"p{i}", resolution_cues=("spot:77",), tick_from=0, tick_to=10
                ),
            )
        text = builder._build_pending_predictions_text(
            player_id=PlayerId(_ACTING_PLAYER_ID),
            current_state_dto=current_state_dto,
        )
        matched_count = sum(1 for i in range(4) if f"約束(p{i})" in text)
        assert matched_count == 2

    def test_current_tick_provider_unset_returns_empty(self) -> None:
        store = InMemoryPendingPredictionStore()
        current_state_dto = SimpleNamespace(current_spot_id=77, current_player_ids=set())
        builder = _make_builder(
            pending_prediction_store=store,
            current_tick=5,
            current_state_dto=current_state_dto,
        )
        being_id = builder._resolve_being_id(PlayerId(_ACTING_PLAYER_ID))
        store.add_by_being(
            being_id,
            _pending("p1", resolution_cues=("spot:77",), tick_from=0, tick_to=10),
        )
        # current_tick_provider を後から None に差し替えて再確認
        builder._current_tick_provider = None
        text = builder._build_pending_predictions_text(
            player_id=PlayerId(_ACTING_PLAYER_ID),
            current_state_dto=current_state_dto,
        )
        assert text == ""
