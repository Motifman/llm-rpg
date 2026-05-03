"""DefaultPromptBuilder の受動想起（エピソード recall_text）注入の検証。"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

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
from ai_rpg_world.application.llm.contracts.episodic_memory import (
    EpisodicCue,
    EpisodicCueSource,
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.observation.contracts.interfaces import IObservationContextBuffer
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.enum.player_enum import ControlType
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)

# テストで retrieve に渡す件数上限（本番は後から設定化）
_TEST_PASSIVE_RECALL_LIMIT_PER_AXIS = 4
_TEST_PASSIVE_RECALL_MAX_CANDIDATES = 6


def _profile_repo(player_id: int = 1) -> PlayerProfileRepository:
    data_store = InMemoryDataStore()
    data_store.clear_all()
    repo = InMemoryPlayerProfileRepository(data_store, None)
    profile = PlayerProfileAggregate.create(
        PlayerId(player_id), PlayerName("PromptTest"), control_type=ControlType.LLM
    )
    repo.save(profile)
    return repo


def _episode(
    *,
    episode_id: str,
    player_id: int,
    occurred_at: datetime,
    recall_text: str,
    cues: tuple[EpisodicCue, ...],
) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=occurred_at,
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-x",)),
        location=EpisodeLocation(),
        action=EpisodeAction(tool_name="t"),
        who=("p",),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=cues,
        recall_text=recall_text,
    )


# DefaultPromptBuilder は WorldQueryService インスタンスを要求するため、__init を呼ばず最小スタブとする。
def _world_query_stub(state=None):
    w = object.__new__(WorldQueryService)
    w.get_player_current_state = MagicMock(return_value=state)
    return w


class TestPromptBuilderPassiveRecall:
    """Optional 注入時のみ関連記憶セクションに recall_text が載ること"""

    def test_without_service_relevant_memories_section_is_placeholder(self) -> None:
        """受動想起未注入時は relevant_memories が空のまま（従来どおり ## 関連する記憶 は （なし））。"""
        buffer = MagicMock(spec=IObservationContextBuffer)
        buffer.drain = MagicMock(return_value=[])
        sliding = MagicMock(spec=ISlidingWindowMemory)
        sliding.append_all = MagicMock(return_value=[])
        sliding.get_recent = MagicMock(return_value=[])
        actions = MagicMock(spec=IActionResultStore)
        actions.get_recent = MagicMock(return_value=[])
        world = _world_query_stub(state=None)
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

        builder = DefaultPromptBuilder(
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
            ui_context_builder=ui_builder,
            episodic_passive_recall=None,
        )
        out = builder.build(PlayerId(1))
        user = out["messages"][1]["content"]
        assert "## 関連する記憶" in user
        assert "（なし）" in user.split("## 関連する記憶", 1)[1]
        assert out["current_beliefs_snapshot"] == ""

    def test_with_service_joins_recall_texts_into_related_memories_section(self) -> None:
        """
        situation_cues（runtime + 最新観測 structured）で retrieve し、
        候補 episode の recall_text が ## 関連する記憶 に載る。
        """
        player_num = 3
        place_c = EpisodicCue(axis="place_spot", value="77", source=EpisodicCueSource.RUNTIME_CONTEXT)
        base = datetime(2026, 5, 2, 8, 0, tzinfo=timezone.utc)
        store = InMemorySubjectiveEpisodeStore()
        store.put(
            _episode(
                episode_id="e_recent",
                player_id=player_num,
                occurred_at=base + timedelta(hours=1),
                recall_text="最近の出来事",
                cues=(place_c,),
            )
        )
        store.put(
            _episode(
                episode_id="e_old",
                player_id=player_num,
                occurred_at=base,
                recall_text="古いが cue で拾える",
                cues=(place_c,),
            )
        )
        recall_svc = EpisodicPassiveRecallRetrievalService(store)

        buffer = MagicMock(spec=IObservationContextBuffer)
        buffer.drain = MagicMock(return_value=[])
        sliding = MagicMock(spec=ISlidingWindowMemory)
        sliding.append_all = MagicMock(return_value=[])
        sliding.get_recent = MagicMock(
            return_value=[
                ObservationEntry(
                    occurred_at=base + timedelta(hours=2),
                    output=ObservationOutput(
                        prose="look",
                        structured={"spot_id_value": 77},
                        observation_category="environment",
                    ),
                    game_time_label=None,
                )
            ]
        )
        actions = MagicMock(spec=IActionResultStore)
        actions.get_recent = MagicMock(return_value=[])
        world = _world_query_stub(state=None)
        current_fmt = MagicMock(spec=ICurrentStateFormatter)
        current_fmt.format = MagicMock(return_value="fmt")
        recent_fmt = MagicMock(spec=IRecentEventsFormatter)
        recent_fmt.format = MagicMock(return_value="recent")
        sys_builder = MagicMock(spec=ISystemPromptBuilder)
        sys_builder.build = MagicMock(return_value="sys")
        tools_p = MagicMock(spec=IAvailableToolsProvider)
        tools_p.get_available_tools = MagicMock(return_value=[])

        rt = ToolRuntimeContextDto(targets={}, current_spot_id=77)
        ui_builder = MagicMock(spec=ILlmUiContextBuilder)
        ui_builder.build = MagicMock(
            return_value=LlmUiContextDto(current_state_text="ui", tool_runtime_context=rt)
        )

        builder = DefaultPromptBuilder(
            observation_buffer=buffer,
            sliding_window_memory=sliding,
            action_result_store=actions,
            world_query_service=world,
            player_profile_repository=_profile_repo(player_id=player_num),
            current_state_formatter=current_fmt,
            recent_events_formatter=recent_fmt,
            context_format_strategy=SectionBasedContextFormatStrategy(),
            system_prompt_builder=sys_builder,
            available_tools_provider=tools_p,
            ui_context_builder=ui_builder,
            episodic_passive_recall=recall_svc,
            episodic_passive_recall_limit_per_axis=_TEST_PASSIVE_RECALL_LIMIT_PER_AXIS,
            episodic_passive_recall_max_candidates=_TEST_PASSIVE_RECALL_MAX_CANDIDATES,
        )
        out = builder.build(PlayerId(player_num))
        user = out["messages"][1]["content"]
        section = user.split("## 関連する記憶", 1)[1]
        assert "最近の出来事" in section
        assert "古いが cue で拾える" in section
        expected_joined = "最近の出来事\n古いが cue で拾える"
        assert expected_joined in user
        assert out["current_beliefs_snapshot"] == expected_joined
