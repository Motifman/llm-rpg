# Phase 3 Step 3e-3 bulk migration: episode_store の player_id 経路撤去に
# 伴い、本ファイルの ``being_id`` 参照を deterministic な ``BeingId`` の
# 既定値で受ける (= テスト内で異なる player_id を使う箇所は個別に上書き)。
# BeingProvisioningService は ``being_w<world>_p<player>`` 形式を使う。
from ai_rpg_world.domain.being.value_object.being_id import (
    BeingId as _MIG_BeingId,
)

being_id = _MIG_BeingId("being_w1_p1")
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
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import EpisodicReinterpretationEntry
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
    InMemoryEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
from ai_rpg_world.application.llm.services.prompt_builder_config import (
    EpisodicRecallConfig,
    PromptBuilderCoreServices,
)
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

    def test_without_service_relevant_memories_section_is_omitted(self) -> None:
        """受動想起未注入時は【関連する記憶】section ごと省略される (chore β: world_runtime format)。"""
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
            ui_context_builder=ui_builder,
        )
        out = builder.build(PlayerId(1))
        user = out["messages"][1]["content"]
        # chore β: 受動想起未注入時は section ごと出力されない (world_runtime format)
        assert "【関連する記憶】" not in user
        assert out["current_beliefs_snapshot"] == ""

    def test_with_service_joins_recall_texts_into_related_memories_section(self) -> None:
        """
        situation_cues（runtime + 最新観測 structured）で retrieve し、
        候補 episode の recall_text が 【関連する記憶】 に載る。
        """
        from ai_rpg_world.application.being.being_provisioning_service import (
            BeingProvisioningService,
        )
        from ai_rpg_world.domain.being.service.being_attachment_resolver import (
            BeingAttachmentResolver,
        )
        from ai_rpg_world.domain.world.value_object.world_id import (
            DEFAULT_SINGLE_WORLD_ID,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
            InMemoryBeingRepository,
        )

        player_num = 3
        # Phase 3 Step 3e-3: episode_store / passive recall は being_id 経路のみ
        _being_repo = InMemoryBeingRepository()
        _resolver = BeingAttachmentResolver(_being_repo)
        being_id_3 = BeingProvisioningService(_being_repo).ensure_attached(
            PlayerId(player_num)
        )
        place_c = EpisodicCue(axis="place_spot", value="77", source=EpisodicCueSource.RUNTIME_CONTEXT)
        base = datetime(2026, 5, 2, 8, 0, tzinfo=timezone.utc)
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(
            being_id_3,
            _episode(
                episode_id="e_recent",
                player_id=player_num,
                occurred_at=base + timedelta(hours=1),
                recall_text="最近の出来事",
                cues=(place_c,),
            ),
        )
        store.put_by_being(
            being_id_3,
            _episode(
                episode_id="e_old",
                player_id=player_num,
                occurred_at=base,
                recall_text="古いが cue で拾える",
                cues=(place_c,),
            ),
        )
        recall_svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=_resolver,
            default_world_id=DEFAULT_SINGLE_WORLD_ID,
        )

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
            PromptBuilderCoreServices(
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
            ),
            ui_context_builder=ui_builder,
            episodic=EpisodicRecallConfig(
                passive_recall=recall_svc,
                passive_recall_limit_per_axis=_TEST_PASSIVE_RECALL_LIMIT_PER_AXIS,
                passive_recall_max_candidates=_TEST_PASSIVE_RECALL_MAX_CANDIDATES,
            ),
        )
        out = builder.build(PlayerId(player_num))
        user = out["messages"][1]["content"]
        section = user.split("【関連する記憶】", 1)[1]
        assert "最近の出来事" in section
        assert "古いが cue で拾える" in section
        expected_joined = "最近の出来事\n古いが cue で拾える"
        assert expected_joined in user
        assert out["current_beliefs_snapshot"] == expected_joined

    def test_u1_prediction_context_id_recall_episode_recall_observation_stamp(
        self,
    ) -> None:
        """build() が発行する prediction_context_id に、その build で
        【関連する記憶】に載せた episode_id 群が ledger 経由で紐づき (2 段目 attach)、
        かつ生成された EpisodicRecallObservation にも同じ id が stamp されること
        (部品5 想起の信用割り当ての実配線。id が死んだフィールドにならないこと)。"""
        from ai_rpg_world.application.llm.services.prediction_context_ledger import (
            PredictionContextLedger,
        )
        from tests.application.llm._reinterpretation_being_test_helpers import (
            make_reinterpretation_being_setup,
        )

        player_num = 5
        setup = make_reinterpretation_being_setup()
        being_id_5 = setup.provision(player_num)
        place_c = EpisodicCue(axis="place_spot", value="77", source=EpisodicCueSource.RUNTIME_CONTEXT)
        base = datetime(2026, 5, 2, 8, 0, tzinfo=timezone.utc)
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(
            being_id_5,
            _episode(
                episode_id="e_for_ledger",
                player_id=player_num,
                occurred_at=base,
                recall_text="ledger 紐付け確認用",
                cues=(place_c,),
            ),
        )
        recall_svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )

        buffer = MagicMock(spec=IObservationContextBuffer)
        buffer.drain = MagicMock(return_value=[])
        sliding = MagicMock(spec=ISlidingWindowMemory)
        sliding.append_all = MagicMock(return_value=[])
        sliding.get_recent = MagicMock(
            return_value=[
                ObservationEntry(
                    occurred_at=base + timedelta(hours=1),
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

        ledger = PredictionContextLedger()
        builder = DefaultPromptBuilder(
            PromptBuilderCoreServices(
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
            ),
            ui_context_builder=ui_builder,
            episodic=EpisodicRecallConfig(
                passive_recall=recall_svc,
                passive_recall_limit_per_axis=_TEST_PASSIVE_RECALL_LIMIT_PER_AXIS,
                passive_recall_max_candidates=_TEST_PASSIVE_RECALL_MAX_CANDIDATES,
                recall_buffer_store=setup.recall_buffer,
                turn_index_provider=lambda _pid: 12,
            ),
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
            prediction_context_ledger=ledger,
        )
        out = builder.build(PlayerId(player_num))
        issued_id = out["prediction_context_id"]
        assert issued_id is not None
        assert issued_id.startswith("predctx-")

        # 2 段目 attach: ledger に in-context episode 群が紐づく
        pending = ledger.peek(PlayerId(player_num))
        assert pending is not None
        assert pending.prediction_context_id == issued_id
        assert "e_for_ledger" in pending.episode_ids

        # 1 段目 stamp: 生成された recall observation に同じ id が載る (死んでいない)
        observations = setup.recall_buffer.peek_batch_by_being(
            being_id_5, batch_size=8, max_contexts_per_episode=3
        )
        assert len(observations) == 1
        assert observations[0].episode_id == "e_for_ledger"
        assert observations[0].prediction_context_id == issued_id

    def test_u1_flag_off_ledger_uninjected_recall_observation_id_none(
        self,
    ) -> None:
        """id 機構 OFF (ledger 未注入) では recall observation の
        prediction_context_id は None (後方互換)。"""
        from tests.application.llm._reinterpretation_being_test_helpers import (
            make_reinterpretation_being_setup,
        )

        player_num = 6
        setup = make_reinterpretation_being_setup()
        being_id_6 = setup.provision(player_num)
        place_c = EpisodicCue(axis="place_spot", value="77", source=EpisodicCueSource.RUNTIME_CONTEXT)
        base = datetime(2026, 5, 2, 8, 0, tzinfo=timezone.utc)
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(
            being_id_6,
            _episode(
                episode_id="e_no_id",
                player_id=player_num,
                occurred_at=base,
                recall_text="id 無し確認用",
                cues=(place_c,),
            ),
        )
        recall_svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )

        buffer = MagicMock(spec=IObservationContextBuffer)
        buffer.drain = MagicMock(return_value=[])
        sliding = MagicMock(spec=ISlidingWindowMemory)
        sliding.append_all = MagicMock(return_value=[])
        sliding.get_recent = MagicMock(
            return_value=[
                ObservationEntry(
                    occurred_at=base + timedelta(hours=1),
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
            PromptBuilderCoreServices(
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
            ),
            ui_context_builder=ui_builder,
            episodic=EpisodicRecallConfig(
                passive_recall=recall_svc,
                passive_recall_limit_per_axis=_TEST_PASSIVE_RECALL_LIMIT_PER_AXIS,
                passive_recall_max_candidates=_TEST_PASSIVE_RECALL_MAX_CANDIDATES,
                recall_buffer_store=setup.recall_buffer,
                turn_index_provider=lambda _pid: 12,
            ),
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
            # prediction_context_ledger は注入しない (= 機構 OFF)
        )
        out = builder.build(PlayerId(player_num))
        assert out["prediction_context_id"] is None
        observations = setup.recall_buffer.peek_batch_by_being(
            being_id_6, batch_size=8, max_contexts_per_episode=3
        )
        assert len(observations) == 1
        assert observations[0].prediction_context_id is None

    def test_active_reinterpretation_overrides_episode_recall_and_records_observation(self) -> None:
        """
        active な再解釈がある episode は current_recall_text を prompt に使い、
        想起された episode と状況 snapshot は recall buffer に積まれる。

        Phase 3 Step 3d-3: legacy 撤去後、journal / recall_buffer は being_id
        経路必須。Resolver+WorldId を inject し、provision 済の Being で
        active entry を書く形に揃える。
        """
        from tests.application.llm._reinterpretation_being_test_helpers import (
            make_reinterpretation_being_setup,
        )

        player_num = 4
        place_c = EpisodicCue(axis="place_spot", value="77", source=EpisodicCueSource.RUNTIME_CONTEXT)
        base = datetime(2026, 5, 2, 8, 0, tzinfo=timezone.utc)
        store = InMemorySubjectiveEpisodeStore()
        # Phase 3 Step 3e-3: 統合テスト用に reinterp_setup を先に作って being_id を
        # 取得 (= journal と episode_store で同じ being_id を共有する)
        reinterp_setup = make_reinterpretation_being_setup()
        being_id_4 = reinterp_setup.provision(player_num)
        store.put_by_being(
            being_id_4,
            _episode(
                episode_id="e_reinterpreted",
                player_id=player_num,
                occurred_at=base + timedelta(hours=1),
                recall_text="古い回想は使われない",
                cues=(place_c,),
            ),
        )
        recall_svc = EpisodicPassiveRecallRetrievalService(
            store,
            being_attachment_resolver=reinterp_setup.resolver,
            default_world_id=reinterp_setup.world_id,
        )
        being_id = being_id_4
        journal = reinterp_setup.journal
        journal.put_active_by_being(
            being_id,
            EpisodicReinterpretationEntry(
                entry_id="j-active",
                player_id=player_num,
                episode_id="e_reinterpreted",
                created_at=base + timedelta(hours=2),
                turn_index=10,
                current_interpretation="今なら罠への警戒として意味づけられる。",
                current_recall_text="私はあの場で感じた違和感を、今もはっきり覚えている。",
                source_recall_ids=("r-old",),
            ),
        )
        recall_buffer = reinterp_setup.recall_buffer

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
        recent_fmt.format = MagicMock(return_value="recent-events")
        sys_builder = MagicMock(spec=ISystemPromptBuilder)
        sys_builder.build = MagicMock(return_value="sys")
        tools_p = MagicMock(spec=IAvailableToolsProvider)
        tools_p.get_available_tools = MagicMock(return_value=[])

        rt = ToolRuntimeContextDto(targets={}, current_spot_id=77)
        ui_builder = MagicMock(spec=ILlmUiContextBuilder)
        ui_builder.build = MagicMock(
            return_value=LlmUiContextDto(current_state_text="ui-current", tool_runtime_context=rt)
        )

        builder = DefaultPromptBuilder(
            PromptBuilderCoreServices(
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
            ),
            ui_context_builder=ui_builder,
            episodic=EpisodicRecallConfig(
                passive_recall=recall_svc,
                passive_recall_limit_per_axis=_TEST_PASSIVE_RECALL_LIMIT_PER_AXIS,
                passive_recall_max_candidates=_TEST_PASSIVE_RECALL_MAX_CANDIDATES,
                recall_buffer_store=recall_buffer,
                reinterpretation_journal_store=journal,
                turn_index_provider=lambda _pid: 12,
            ),
            being_attachment_resolver=reinterp_setup.resolver,
            default_world_id=reinterp_setup.world_id,
        )
        out = builder.build(PlayerId(player_num))
        user = out["messages"][1]["content"]
        assert "私はあの場で感じた違和感" in user
        assert "古い回想は使われない" not in user
        pending = recall_buffer.peek_batch_by_being(
            being_id, batch_size=8, max_contexts_per_episode=3
        )
        assert len(pending) == 1
        assert pending[0].episode_id == "e_reinterpreted"
        assert pending[0].current_state_snapshot == "ui-current"
        assert pending[0].recent_events_snapshot == "recent-events"
        assert pending[0].turn_index == 12
